from __future__ import annotations

import json
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from jobhunter import cli, paths
from jobhunter.api import health as health_module
from jobhunter.db import get_engine
from jobhunter.schemas import Health


@pytest.fixture()
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("JOBHUNTER_DATA", str(tmp_path))
    for name, relative in {
        "DATA": "",
        "DB_PATH": "jobhunter.sqlite",
        "CONFIG_PATH": "config.yml",
        "LOGS": "logs",
        "RUN_LOGS": "logs/runs",
        "RUN": "run",
        "CAREEROPS_DATA": "careerops",
        "CV_DIR": "cv",
    }.items():
        monkeypatch.setattr(paths, name, tmp_path / relative)
    get_engine.cache_clear()
    yield tmp_path
    get_engine.cache_clear()


# ---------- db migrate / health ----------


def test_db_migrate_creates_database(data_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["db", "migrate"]) == 0
    assert (data_root / "jobhunter.sqlite").is_file()
    assert capsys.readouterr().out.strip() == "schema version 1"
    assert cli.main(["db", "migrate"]) == 0  # idempotent


def test_health_ok_prints_json(data_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["db", "migrate"])
    capsys.readouterr()
    assert cli.main(["health"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["ok"] is True and body["db"] is True


def test_health_not_ok_exits_1(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    bad = Health(ok=False, version="0", db=False, scheduler=False, services=[])
    monkeypatch.setattr(health_module, "health", lambda: bad)
    assert cli.main(["health"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False


# ---------- run ----------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_run_with_server_down_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("JOBHUNTER_PORT", str(_free_port()))
    assert cli.main(["run", "intake_boards", "--wait"]) == 2
    assert "not running" in capsys.readouterr().err


class FakeServer:
    """Just enough of the API: health, intake/run, lead actions and run polling."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, object]] = []
        self.final_state = "succeeded"
        self.polls_until_done = 2
        self._polls = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:  # silence
                pass

            def _send(self, status: int, payload: object) -> None:
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _body(self) -> object:
                n = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(n)) if n else None

            def do_GET(self) -> None:
                outer.requests.append(("GET", self.path, None))
                if self.path == "/api/health":
                    return self._send(200, {"ok": True})
                if self.path.startswith("/api/runs/"):
                    outer._polls += 1
                    done = outer._polls >= outer.polls_until_done
                    run = outer.run("intake_boards", outer.final_state if done else "running")
                    if done:
                        run["summary"] = "42 fetched, 7 new"
                        run["error"] = "boom" if outer.final_state == "failed" else None
                    return self._send(200, run)
                self._send(404, {"detail": "nope"})

            def do_POST(self) -> None:
                body = self._body()
                outer.requests.append(("POST", self.path, body))
                if self.path == "/api/intake/run":
                    return self._send(202, [outer.run("intake_boards", "queued")])
                if self.path.startswith("/api/leads/"):
                    if self.path.startswith("/api/leads/404/"):
                        return self._send(404, {"detail": "lead not found"})
                    return self._send(202, outer.run(self.path.rsplit("/", 1)[1], "queued"))
                self._send(404, {"detail": "nope"})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @staticmethod
    def run(kind: str, state: str) -> dict:
        return {
            "id": 7,
            "kind": kind,
            "state": state,
            "params": {},
            "summary": None,
            "error": None,
            "created_at": "2026-11-12T00:00:00Z",
        }

    def __enter__(self) -> FakeServer:  # noqa: PYI034
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture()
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeServer]:
    monkeypatch.setattr(cli, "POLL_SECONDS", 0.01)
    with FakeServer() as srv:
        monkeypatch.setenv("JOBHUNTER_PORT", str(srv.port))
        yield srv


def test_run_without_wait_prints_queued(server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "intake_boards"]) == 0
    assert "run 7 intake_boards: queued" in capsys.readouterr().out
    post = next(r for r in server.requests if r[0] == "POST")
    assert post[1] == "/api/intake/run"
    assert post[2] == {"sources": ["linkedin", "naukri", "indeed", "glassdoor", "google"]}
    assert not any(r[1].startswith("/api/runs/") for r in server.requests)


def test_run_wait_polls_until_succeeded(server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "careerops_scan", "--wait"]) == 0
    assert "succeeded - 42 fetched, 7 new" in capsys.readouterr().out
    assert [r for r in server.requests if r[1] == "/api/runs/7"]
    assert server.requests[-1][1] == "/api/runs/7"


def test_run_wait_failed_exits_1(server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    server.final_state = "failed"
    assert cli.main(["run", "intake_gmail", "--wait"]) == 1
    out = capsys.readouterr().out
    assert "failed" in out and "error: boom" in out


def test_run_wait_timeout_exits_1(server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    server.polls_until_done = 10**9
    assert cli.main(["run", "intake_boards", "--wait", "--timeout", "0.05"]) == 1
    assert "still running" in capsys.readouterr().err


def test_run_lead_kind_posts_to_lead_endpoint(server: FakeServer) -> None:
    assert cli.main(["run", "cv", "--lead", "5", "--variant", "B"]) == 0
    assert ("POST", "/api/leads/5/cv", {"variant": "B"}) in server.requests
    assert cli.main(["run", "assist_apply", "--lead", "5"]) == 0
    assert ("POST", "/api/leads/5/assist-apply", None) in server.requests


def test_run_lead_kind_requires_lead(server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "evaluate"]) == 2
    assert "--lead" in capsys.readouterr().err
    assert not [r for r in server.requests if r[0] == "POST"]


def test_run_kind_without_api_entry_exits_2(server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "followups"]) == 2
    assert "scheduler" in capsys.readouterr().err


def test_run_api_error_exits_1(server: FakeServer, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "evaluate", "--lead", "404"]) == 1
    assert "lead not found" in capsys.readouterr().err


def test_run_unknown_kind_is_argparse_error() -> None:
    with pytest.raises(SystemExit) as e:
        cli.main(["run", "bogus"])
    assert e.value.code == 2


# ---------- doctor-json ----------


def _fake_bin(directory: Path, name: str, script: str) -> None:
    path = directory / name
    path.write_text(f"#!/bin/sh\n{script}\n")
    path.chmod(0o755)


def test_doctor_json_fails_without_claude(
    data_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = data_root / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    monkeypatch.setattr(cli, "_keychain_has", lambda name: False)
    assert cli.main(["doctor-json"]) == 1
    out = json.loads(capsys.readouterr().out)
    checks = {c["name"]: c for c in out["checks"]}
    assert out["ok"] is False
    assert checks["claude"]["ok"] is False and "claude login" in checks["claude"]["fix"]
    assert checks["node"]["ok"] is False
    assert checks["gmail_password"]["required"] is False


def test_doctor_json_ok_with_tools(
    data_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bin_dir = data_root / "bin"
    bin_dir.mkdir()
    _fake_bin(bin_dir, "claude", "echo claude")
    _fake_bin(bin_dir, "node", 'echo "v22.13.0"')
    (data_root / "cv").mkdir()
    (data_root / "cv" / "cv_a.md").write_text("a")
    (data_root / "cv" / "cv_b.md").write_text("b")
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setattr(cli, "_keychain_has", lambda name: True)
    assert cli.main(["doctor-json"]) == 0
    checks = {c["name"]: c for c in json.loads(capsys.readouterr().out)["checks"]}
    assert checks["claude"]["ok"] and checks["node"]["ok"]
    assert checks["cvs"]["ok"] and checks["gmail_password"]["ok"]


def test_doctor_json_rejects_old_node(data_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = data_root / "bin"
    bin_dir.mkdir()
    _fake_bin(bin_dir, "node", 'echo "v22.12.9"')
    monkeypatch.setenv("PATH", str(bin_dir))
    assert cli._node_version() == ("22.12.9", False)
