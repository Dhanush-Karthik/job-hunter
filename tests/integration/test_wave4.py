"""Wave 4 regressions through the API worker and installed CLI subprocesses."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from sqlmodel import Session, select

from jobhunter.db import get_engine
from jobhunter.models import Evaluation, Lead, Source, SourceHealth

from . import test_wave2_flow
from .test_wave2_flow import (
    ROOT,
    manual_lead,
    response_json,
    wait_run,
)

wave4_client = test_wave2_flow.real_client


def test_partial_scan_ingests_and_succeeds(wave4_client, monkeypatch):
    real_client = wave4_client
    monkeypatch.setenv("JOBHUNTER_FAKE_SCENARIO", "partial_scan")
    queued, = response_json(real_client.post(
        "/api/intake/run", json={"sources": ["careerops_scan"]},
    ), 202)
    assert queued["kind"] == "careerops_scan"
    finished = wait_run(real_client, queued["id"])
    assert finished["error"] is None
    with Session(get_engine()) as session:
        lead, = session.exec(select(Lead)).all()
        assert lead.source == Source.careerops_scan
        assert lead.canonical_url == "https://example.test/jobs/partial-java"
        health = session.get(SourceHealth, "careerops_scan")
        assert health.last_ok_at is not None and health.last_run_at is not None
        assert health.last_count == 1 and health.consecutive_failures == 0
        assert "Slow tenant: deadline" in health.last_error
        assert "Broken tenant: upstream timeout" in health.last_error


def test_usage_limit_fails_run_with_reset_time(wave4_client, monkeypatch):
    real_client = wave4_client
    monkeypatch.setenv("JOBHUNTER_FAKE_SCENARIO", "usage_limit")
    lead = manual_lead(real_client)
    queued = response_json(real_client.post(f"/api/leads/{lead['id']}/evaluate"), 202)
    failed = wait_run(real_client, queued["id"], "failed")
    assert "usage limit" in failed["error"].lower()
    assert "21:30 IST" in failed["error"]
    with Session(get_engine()) as session:
        assert session.exec(select(Evaluation)).all() == []


def test_cli_migrate_health_and_server_down(tmp_path):
    # Bind port zero to choose an unused loopback port; never contact the owner's 8787 server.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    assert port != 8787
    env = {**os.environ, "JOBHUNTER_DATA": str(tmp_path), "JOBHUNTER_PORT": str(port),
           "JOBHUNTER_NO_SCHEDULER": "1", "JOBHUNTER_NOTIFY": "0",
           "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring"}

    def cli(*args):
        return subprocess.run(["uv", "run", "jobhunter", *args], check=False, cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=30)

    migrated = cli("db", "migrate")
    assert migrated.returncode == 0, migrated.stderr
    assert "schema version 1" in migrated.stdout
    assert (tmp_path / "jobhunter.sqlite").is_file()
    with (tmp_path / "server.log").open("w+") as log:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "jobhunter.api.app:app", "--host", "127.0.0.1",
             "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=log,
            start_new_session=True,
        )
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            deadline = time.monotonic() + 15
            while True:
                try:
                    with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                        assert json.load(response)["ok"] is True
                    break
                except (urllib.error.URLError, TimeoutError):
                    if server.poll() is not None or time.monotonic() >= deadline:
                        log.seek(0)
                        raise AssertionError(log.read())
                    time.sleep(0.05)
            healthy = cli("health")
            assert healthy.returncode == 0, healthy.stderr
            assert json.loads(healthy.stdout)["ok"] is True
        finally:
            if server.poll() is None:
                os.killpg(server.pid, signal.SIGTERM)
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait(timeout=5)
    down = cli("run", "intake_boards", "--wait")
    assert down.returncode == 2, (down.stdout, down.stderr)
    assert "server is not running" in down.stderr
    assert str(port) in down.stderr
