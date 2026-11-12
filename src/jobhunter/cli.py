"""`jobhunter` command line: migrate, health, run, doctor-json (plan section 10).

Stdlib only at import time; heavy modules load inside the commands that need them. `run` never starts work
in-process: the server owns the scheduler and run engine, so it talks to the running server over HTTP.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

from jobhunter.models import RunKind

EXIT_FAIL = 1
EXIT_USAGE = 2  # bad arguments, or the server is not running

TERMINAL_STATES = {"succeeded", "failed", "cancelled"}
POLL_SECONDS = 2.0

# Run kinds started through /api/intake/run (one run each), with the sources that select them.
_INTAKE_SOURCES: dict[RunKind, list[str]] = {
    RunKind.intake_boards: ["linkedin", "naukri", "indeed", "glassdoor", "google"],
    RunKind.intake_gmail: ["gmail_alert", "gmail_inbound"],
    RunKind.careerops_scan: ["careerops_scan"],
}
# Run kinds that act on one lead, started through /api/leads/{id}/<path>.
_LEAD_PATHS: dict[RunKind, str] = {
    RunKind.evaluate: "evaluate",
    RunKind.verify: "verify",
    RunKind.cv: "cv",
    RunKind.assist_apply: "assist-apply",
    RunKind.contacts: "contacts",
}
# intake_remote and followups have no API entry point; the scheduler starts them.


def base_url() -> str:
    return f"http://127.0.0.1:{os.environ.get('JOBHUNTER_PORT', '8787')}"


class ServerDown(Exception):
    pass


class UsageError(Exception):
    pass


class ApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status


_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # loopback only, never via a proxy


def _http(method: str, path: str, body: dict[str, Any] | None = None, timeout: float = 10.0) -> Any:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        base_url() + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with _opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        try:
            detail = str(json.loads(detail).get("detail", detail))
        except (ValueError, AttributeError):
            pass
        raise ApiError(e.code, detail) from e
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
        raise ServerDown(str(e)) from e


# ---------- db migrate ----------


def cmd_db_migrate(_: argparse.Namespace) -> int:
    from jobhunter.db import migrate

    print(f"schema version {migrate()}")
    return 0


# ---------- health ----------


def cmd_health(_: argparse.Namespace) -> int:
    from jobhunter.api.health import health

    result = health()
    print(result.model_dump_json(indent=2))
    return 0 if result.ok else EXIT_FAIL


# ---------- run ----------


def _start(args: argparse.Namespace) -> list[dict[str, Any]]:
    kind = RunKind(args.kind)
    if kind in _INTAKE_SOURCES:
        runs = _http("POST", "/api/intake/run", {"sources": _INTAKE_SOURCES[kind]})
        return [r for r in runs if r["kind"] == kind.value] or runs
    if kind in _LEAD_PATHS:
        if args.lead is None:
            raise UsageError(f"run {kind.value} needs --lead ID")
        body = None
        if kind == RunKind.cv:
            body = {"variant": args.variant}
        return [_http("POST", f"/api/leads/{args.lead}/{_LEAD_PATHS[kind]}", body)]
    raise UsageError(f"run {kind.value} cannot be started over the API (the scheduler runs it)")


def _usage_error(message: str) -> int:
    print(f"jobhunter: {message}", file=sys.stderr)
    return EXIT_USAGE


def _describe(run: dict[str, Any]) -> str:
    text = f"run {run['id']} {run['kind']}: {run['state']}"
    if run.get("summary"):
        text += f" - {run['summary']}"
    if run.get("error"):
        text += f" - error: {run['error']}"
    return text


def _wait(run: dict[str, Any], timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while run["state"] not in TERMINAL_STATES:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"run {run['id']} still {run['state']} after {timeout:.0f}s")
        time.sleep(POLL_SECONDS)
        run = _http("GET", f"/api/runs/{run['id']}")
    return run


def cmd_run(args: argparse.Namespace) -> int:
    try:
        _http("GET", "/api/health", timeout=3.0)
    except ServerDown:
        return _usage_error(f"server is not running at {base_url()}; start it with ./start.sh")
    try:
        runs = _start(args)
        if not args.wait:
            for run in runs:
                print(_describe(run))
            return 0
        failed = False
        for run in runs:
            run = _wait(run, args.timeout)
            print(_describe(run))
            failed |= run["state"] != "succeeded"
        return EXIT_FAIL if failed else 0
    except UsageError as e:
        return _usage_error(str(e))
    except ServerDown:
        return _usage_error(f"server stopped answering at {base_url()}")
    except ApiError as e:
        print(f"jobhunter: {e}", file=sys.stderr)
        return EXIT_FAIL
    except TimeoutError as e:
        print(f"jobhunter: {e}", file=sys.stderr)
        return EXIT_FAIL


# ---------- doctor-json ----------


def _node_version() -> tuple[str | None, bool]:
    node = shutil.which("node")
    if not node:
        return None, False
    try:
        out = subprocess.run(
            [node, "-v"], check=False, capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None, False
    m = re.match(r"v?(\d+)\.(\d+)", out)
    return out.lstrip("v") or None, bool(m) and (int(m[1]), int(m[2])) >= (22, 13)


def _check(name: str, ok: bool, detail: str, fix: str, required: bool) -> dict[str, Any]:
    return {"name": name, "ok": ok, "required": required, "detail": detail, "fix": None if ok else fix}


def _keychain_has(name: str) -> bool:
    try:
        from jobhunter import secrets

        return secrets.present(name)
    except Exception:  # noqa: BLE001  (no keyring backend counts as absent)
        return False


def doctor_checks() -> list[dict[str, Any]]:
    from jobhunter import paths

    claude = shutil.which("claude")
    node_v, node_ok = _node_version()
    cv_missing = [n for n in ("cv_a.md", "cv_b.md") if not (paths.CV_DIR / n).is_file()]
    return [
        _check(
            "claude",
            claude is not None,
            claude or "not on PATH",
            "npm install -g @anthropic-ai/claude-code && claude login",
            True,
        ),
        _check(
            "node",
            node_ok,
            f"node {node_v}" if node_v else "not on PATH",
            "brew install node@22 && brew link --overwrite node@22 (career-ops needs >= 22.13)",
            True,
        ),
        _check(
            "careerops_deps",
            (paths.CAREEROPS_VENDOR / "node_modules").is_dir(),
            str(paths.CAREEROPS_VENDOR / "node_modules"),
            "(cd vendor/career-ops && npm install --no-package-lock)",
            False,
        ),
        _check(
            "gmail_password",
            _keychain_has("gmail_app_password"),
            "Keychain item jobhunter/gmail_app_password",
            "enter it in the dashboard Setup page",
            False,
        ),
        _check(
            "cvs",
            not cv_missing,
            "both CV variants present" if not cv_missing else f"missing {', '.join(cv_missing)}",
            f"save them under {paths.CV_DIR} (or upload in the dashboard Setup page)",
            False,
        ),
    ]


def cmd_doctor_json(_: argparse.Namespace) -> int:
    checks = doctor_checks()
    ok = all(c["ok"] for c in checks if c["required"])
    print(json.dumps({"ok": ok, "checks": checks}, indent=2))
    return 0 if ok else EXIT_FAIL


# ---------- entry ----------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobhunter", description="job-hunter command line")
    sub = parser.add_subparsers(dest="command", required=True)

    db = sub.add_parser("db", help="database commands").add_subparsers(dest="db_command", required=True)
    db.add_parser("migrate", help="apply pending schema migrations").set_defaults(func=cmd_db_migrate)

    sub.add_parser("health", help="print the health JSON; exit 1 if not ok").set_defaults(func=cmd_health)

    run = sub.add_parser("run", help="start a run on the running server")
    run.add_argument("kind", choices=[k.value for k in RunKind])
    run.add_argument("--wait", action="store_true", help="poll until the run finishes and print its summary")
    run.add_argument("--lead", type=int, help="lead id (evaluate, verify, cv, assist_apply, contacts)")
    run.add_argument("--variant", choices=["A", "B"], default="A", help="CV variant (kind cv)")
    run.add_argument("--timeout", type=float, default=1800.0, help="--wait limit in seconds (default 1800)")
    run.set_defaults(func=cmd_run)

    sub.add_parser("doctor-json", help="machine-readable preflight").set_defaults(func=cmd_doctor_json)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
