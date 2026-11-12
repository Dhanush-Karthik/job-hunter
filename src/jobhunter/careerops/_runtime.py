"""Cancellable process transport shared by the bridge's Node and Claude calls."""

from __future__ import annotations

import json
import os
import re
import selectors
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO
from zoneinfo import ZoneInfo

from jobhunter import paths

NODE_DIR = Path(__file__).with_name("node")
CLAUDE_ISOLATION_ARGS = [
    "--safe-mode", "--setting-sources", "", "--strict-mcp-config", "--no-session-persistence",
]


def scan_timeout() -> float:
    """Match Node's deadline validation and leave five minutes for transport."""
    try:
        deadline = float(os.environ.get("JOBHUNTER_SCAN_DEADLINE_S", "1200"))
    except ValueError:
        deadline = 1200
    if not 0 < deadline <= 2_147_483.647:
        deadline = 1200
    return deadline + 300


def usage_limit_error(output: str) -> str | None:
    """Read quota diagnostics before a nonzero exit hides the streamed result."""
    rejected = False
    reset = None
    result_text = ""
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "rate_limit_event":
            info = event.get("rate_limit_info") or event
            if info.get("status") == "rejected":
                rejected = True
                reset = info.get("resetsAt") or reset
        elif event.get("type") == "result":
            text = str(event.get("result", ""))
            quota_result = event.get("is_error") or text.lower().startswith((
                "you've hit", "you’ve hit", "you have hit", "usage limit", "claude usage limit",
                "limit reached", "rate limit",
            ))
            if quota_result and re.search(r"(?:usage|rate|weekly|session|extra usage) limit|limit (?:reached|exceeded)|"
                         r"(?:hit|reached|exceeded) (?:your |the )?limit|out of (?:extra )?usage",
                         text, re.IGNORECASE):
                rejected = True
                result_text = text
                reset = event.get("resetsAt") or reset
    if not rejected:
        return None
    message = "Claude usage limit reached"
    if reset is not None:
        try:
            reset_time = datetime.fromtimestamp(float(reset), ZoneInfo("Asia/Kolkata"))
            return f"{message}; resets at {reset_time:%H:%M} IST"
        except (ValueError, TypeError, OverflowError, OSError):
            pass
    # Older CLI versions only include a human-readable reset in the result.
    if match := re.search(r"\bresets?\b[^\n]*", result_text, re.IGNORECASE):
        return f"{message}; {match.group(0)[:160]}"
    return message


def run(
    args: list[str], *, log: TextIO, should_cancel: Callable[[], bool],
    payload: dict[str, Any] | None = None, timeout: float = 600, owner_browser: bool = False,
) -> str:
    from jobhunter.careerops import BridgeError, Cancelled

    if should_cancel():
        raise Cancelled("Cancelled before starting career-ops")
    paths.CAREEROPS_DATA.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(
        CAREER_OPS_DATA_DIR=str(paths.CAREEROPS_DATA.resolve()),
        CAREER_OPS_ROOT=str(paths.CAREEROPS_DATA.resolve()),
        CAREER_OPS_TRACKER=str(paths.CAREEROPS_DATA.resolve() / ".jobhunter-tracker-scratch.md"),
    )
    # Do not echo argv: it can contain the owner's CV and full posting text.
    log.write(f"Starting {Path(args[0]).name}\n")
    log.flush()
    try:
        proc = subprocess.Popen(
            args, cwd=paths.CAREEROPS_DATA, env=env, start_new_session=True,
            stdin=subprocess.PIPE if payload is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise BridgeError(f"Could not start {Path(args[0]).name}: {exc.strerror}") from exc

    def send() -> None:
        try:
            proc.stdin.write(json.dumps(payload).encode())
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    if payload is not None:
        threading.Thread(target=send, daemon=True).start()
    selector = selectors.DefaultSelector()
    chunks: dict[str, list[bytes]] = {"stdout": [], "stderr": []}
    pending = {"stdout": b"", "stderr": b""}
    for name in chunks:
        stream = getattr(proc, name)
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ, name)
    started = time.monotonic()
    handed_off = False
    try:
        while selector.get_map() or proc.poll() is None:
            if should_cancel():
                raise Cancelled("Cancelled; career-ops process group stopped")
            if time.monotonic() - started > timeout:
                raise BridgeError(f"career-ops timed out after {timeout:g} seconds")
            for key, _ in selector.select(timeout=0.1):
                data = os.read(key.fileobj.fileno(), 65536)
                name = key.data
                if not data:
                    selector.unregister(key.fileobj)
                    if pending[name]:
                        log.write(pending[name].decode("utf-8", errors="replace") + "\n")
                        pending[name] = b""
                    continue
                chunks[name].append(data)
                pending[name] += data
                while b"\n" in pending[name]:
                    line, pending[name] = pending[name].split(b"\n", 1)
                    decoded = line.decode("utf-8", errors="replace")
                    log.write(decoded + "\n")
                    if owner_browser and name == "stdout":
                        try:
                            ready = json.loads(decoded).get("owner_browser_ready") is True
                        except (ValueError, AttributeError):
                            ready = False
                        if ready:
                            handed_off = True
                log.flush()
                if handed_off:
                    # A headed owner window deliberately outlives the filling run.
                    threading.Thread(target=proc.wait, daemon=True).start()
                    return b"".join(chunks["stdout"]).decode("utf-8", errors="replace")
        output = b"".join(chunks["stdout"]).decode("utf-8", errors="replace")
        if limit_error := usage_limit_error(output):
            raise BridgeError(limit_error)
        if proc.wait() != 0:
            stderr = b"".join(chunks["stderr"]).decode("utf-8", errors="replace").strip()
            reason = stderr.splitlines()[-1] if stderr else f"exit status {proc.returncode}"
            raise BridgeError(f"career-ops failed: {reason[:400]}")
        return output
    finally:
        selector.close()
        if not handed_off:
            # Kill descendants too, including a child whose parent already exited.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
        proc.stdout.close()
        proc.stderr.close()
        log.flush()


def node(
    helper: str, payload: dict[str, Any], *, log: TextIO, should_cancel: Callable[[], bool],
    owner_browser: bool = False, timeout: float = 600,
) -> Any:
    from jobhunter.careerops import BridgeError

    output = run(
        [os.environ.get("JOBHUNTER_NODE_BIN", "node"), str(NODE_DIR / helper),
         str(paths.CAREEROPS_VENDOR.resolve())],
        payload=payload, log=log, should_cancel=should_cancel, owner_browser=owner_browser, timeout=timeout,
    )
    try:
        return json.loads(output)
    except ValueError as exc:
        raise BridgeError(f"Invalid JSON from career-ops {helper}") from exc


def claude_text(output: str) -> str:
    """Prefer the final result; assistant snapshots and deltas otherwise overlap."""
    from jobhunter.careerops import BridgeError

    if limit_error := usage_limit_error(output):
        raise BridgeError(limit_error)
    snapshots: list[str] = []
    deltas: list[str] = []
    plain: list[str] = []
    result: str | None = None
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            plain.append(line)
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "result":
            if event.get("is_error"):
                raise BridgeError("Claude could not complete the run; see run log")
            if isinstance(event.get("result"), str):
                result = event["result"]
        elif event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    snapshots.append(block["text"])
        elif event.get("type") == "stream_event":
            delta = event.get("event", {}).get("delta", {})
            if delta.get("type") == "text_delta":
                deltas.append(delta.get("text", ""))
    return result if result is not None else "\n".join(snapshots) or "".join(deltas) or "\n".join(plain)
