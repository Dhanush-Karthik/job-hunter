"""Real API -> real thread pools -> subprocess bridge -> SQLite, with offline external services."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from jobhunter import paths
from jobhunter.api.app import create_app
from jobhunter.db import get_engine, migrate
from jobhunter.intake.boards import fetch_boards
from jobhunter.jobs import runner
from jobhunter.pipeline import ingest
from jobhunter.settings import get_settings

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def real_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # paths is imported by the app; patch the derived constants as well as the process environment.
    monkeypatch.setenv("JOBHUNTER_DATA", str(tmp_path))
    monkeypatch.setenv("JOBHUNTER_NO_SCHEDULER", "1")
    monkeypatch.setenv("JOBHUNTER_CLAUDE_BIN", str(ROOT / "tests/fakes/claude"))
    monkeypatch.setenv("JOBHUNTER_NODE_BIN", str(ROOT / "tests/fakes/node"))
    monkeypatch.setenv("JOBHUNTER_FAKE_SCENARIO", "happy")
    for name, relative in {
        "DATA": "", "DB_PATH": "jobhunter.sqlite", "CONFIG_PATH": "config.yml",
        "LOGS": "logs", "RUN_LOGS": "logs/runs", "RUN": "run",
        "CAREEROPS_DATA": "careerops", "CV_DIR": "cv",
    }.items():
        monkeypatch.setattr(paths, name, tmp_path / relative)
    # Import the shared input writer without making tests a production Python package.
    import runpy

    runpy.run_path(str(ROOT / "tests/fakes/prepare.py"))["prepare"](tmp_path)
    runner.shutdown(wait=True)
    monkeypatch.setattr(runner, "_accepting", True)
    get_engine.cache_clear()
    engine = get_engine()
    migrate(engine)
    try:
        with TestClient(create_app(serve_web=False)) as client:
            yield client
    finally:
        runner.shutdown(wait=True)
        engine.dispose()
        get_engine.cache_clear()


def response_json(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def manual_lead(client: TestClient) -> dict[str, Any]:
    return response_json(client.post("/api/leads", json={
        "company": "Offline Example", "title": "Java Backend Engineer", "location": "Chennai",
        "url": "https://example.test/jobs/java", "jd_text": "Java Spring Boot backend, 3 years experience",
    }), 201)


def wait_run(client: TestClient, run_id: int, expected: str = "succeeded") -> dict[str, Any]:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        run = response_json(client.get(f"/api/runs/{run_id}"))
        if run["state"] in {"succeeded", "failed", "cancelled"}:
            log = response_json(client.get(f"/api/runs/{run_id}/log"))
            assert run["state"] == expected, {"run": run, "log": log}
            assert run["finished_at"]
            return run
        time.sleep(0.025)
    pytest.fail(f"Run {run_id} did not finish: {run}")


def test_board_to_interview_flow(real_client: TestClient) -> None:
    client = real_client
    with Session(get_engine()) as session:
        settings = get_settings(session)
        settings.query_matrix.titles = ["Java Developer"]
        settings.query_matrix.locations = ["Chennai"]

        def scrape(**kwargs: Any) -> pd.DataFrame:
            site = kwargs["site_name"][0]
            return pd.DataFrame(json.loads((ROOT / f"tests/fixtures/boards/{site}.json").read_text()))

        now = datetime(2026, 11, 12, 12, tzinfo=UTC)
        raw = fetch_boards(session, settings, scrape=scrape, sleep=lambda _: None, now=now)
        result = ingest(session, raw, settings, now=now, cv_text="Java Spring Boot")
        assert result.new == 20
    leads = response_json(client.get("/api/leads"))["items"]
    assert len(leads) > 1
    scores = [lead["quick_score"] for lead in leads]
    assert scores == sorted(scores, reverse=True)
    lead_id = leads[0]["id"]
    detail = response_json(client.post(f"/api/leads/{lead_id}/shortlist"))
    assert detail["status"] == "Shortlisted"
    app_id = detail["application"]["id"]
    evaluation = response_json(client.post(f"/api/leads/{lead_id}/evaluate"), 202)
    wait_run(client, evaluation["id"])
    detail = response_json(client.get(f"/api/leads/{lead_id}"))
    assert detail["eval_score"] == detail["evaluation"]["score"] == 3.7
    assert "## Machine Summary" in detail["evaluation"]["report_md"]
    cv = response_json(client.post(f"/api/leads/{lead_id}/cv", json={"variant": "A"}), 202)
    wait_run(client, cv["id"])
    app = response_json(client.get(f"/api/applications/{app_id}"))
    assert app["has_cv_pdf"] and app["resume_variant"] == "A" and not app["cv_approved"]
    pdf = client.get(f"/api/applications/{app_id}/cv.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert pdf.headers["content-type"] == "application/pdf"
    ready = response_json(client.patch(f"/api/applications/{app_id}", json={"cv_approved": True}))
    assert ready["status"] == "Ready"
    applied = response_json(client.post(f"/api/applications/{app_id}/transition", json={"to_status": "Applied"}))
    assert applied["status"] == "Applied" and applied["applied_at"] and applied["next_follow_up_at"]
    assert datetime.fromisoformat(applied["next_follow_up_at"]) > datetime.fromisoformat(applied["applied_at"])
    events = response_json(client.get(f"/api/applications/{app_id}/events"))
    assert [(event["from_status"], event["to_status"]) for event in events] == [
        ("New", "Shortlisted"), ("Shortlisted", "Ready"), ("Ready", "Applied"),
    ]
    screening = response_json(client.post(
        f"/api/applications/{app_id}/transition", json={"to_status": "Screening"},
    ))
    assert screening["status"] == "Screening"
    assert response_json(client.get("/api/today"))["interview_calls_week"] == 1


def test_manual_lead_and_illegal_transition(real_client: TestClient) -> None:
    lead = manual_lead(real_client)
    assert lead["source"] == "manual" and lead["status"] == "New"
    shortlisted = response_json(real_client.post(f"/api/leads/{lead['id']}/shortlist"))
    app_id = shortlisted["application"]["id"]
    response_json(real_client.post(f"/api/applications/{app_id}/transition", json={"to_status": "Offer"}), 409)
    assert response_json(real_client.get(f"/api/applications/{app_id}"))["status"] == "Shortlisted"


def test_failed_claude_has_readable_error(real_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBHUNTER_FAKE_SCENARIO", "fail")
    lead = manual_lead(real_client)
    run = response_json(real_client.post(f"/api/leads/{lead['id']}/evaluate"), 202)
    failed = wait_run(real_client, run["id"], "failed")
    assert "Offline Claude: session unavailable" in failed["error"]
    assert "Offline Claude: session unavailable" in response_json(
        real_client.get(f"/api/runs/{run['id']}/log"),
    )["text"]


def test_cancel_running_subprocess(
    real_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    marker = tmp_path / "claude-started"
    monkeypatch.setenv("JOBHUNTER_FAKE_SCENARIO", "slow")
    monkeypatch.setenv("JOBHUNTER_FAKE_STARTED", str(marker))
    lead = manual_lead(real_client)
    run = response_json(real_client.post(f"/api/leads/{lead['id']}/evaluate"), 202)
    deadline = time.monotonic() + 10
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.025)
    assert marker.exists(), response_json(real_client.get(f"/api/runs/{run['id']}/log"))
    assert response_json(real_client.get(f"/api/runs/{run['id']}"))["state"] == "running"
    response_json(real_client.post(f"/api/runs/{run['id']}/cancel"))
    wait_run(real_client, run["id"], "cancelled")
    assert response_json(real_client.get(f"/api/leads/{lead['id']}"))["evaluation"] is None


def test_run_stream_emits_real_worker_event(real_client: TestClient) -> None:
    lead = manual_lead(real_client)

    async def exercise() -> None:
        # TestClient buffers infinite SSE responses. Drive ASGI directly and disconnect after one event.
        disconnected = asyncio.Event()
        messages: list[dict[str, Any]] = []
        submitted: dict[str, Any] = {}

        async def receive() -> dict[str, Any]:
            await disconnected.wait()
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            messages.append(message)
            if message["type"] == "http.response.body" and b"event: run" in message.get("body", b""):
                disconnected.set()

        async def produce() -> None:
            deadline = time.monotonic() + 5
            while not runner._subscribers and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            assert runner._subscribers, "SSE route did not subscribe"
            submitted.update(await asyncio.to_thread(
                lambda: response_json(real_client.post(f"/api/leads/{lead['id']}/evaluate"), 202),
            ))

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "method": "GET", "scheme": "http",
            "path": "/api/runs/stream", "raw_path": b"/api/runs/stream", "query_string": b"",
            "headers": [], "client": ("127.0.0.1", 1234), "server": ("testserver", 80),
            "http_version": "1.1", "root_path": "",
        }
        await asyncio.wait_for(asyncio.gather(real_client.app(scope, receive, send), produce()), timeout=10)
        assert messages[0]["status"] == 200
        body = b"".join(message.get("body", b"") for message in messages).decode()
        event = json.loads(next(line[6:] for line in body.splitlines() if line.startswith("data: ")))
        assert event["id"] == submitted["id"] and event["kind"] == "evaluate"
        assert event["state"] in {"queued", "running", "succeeded"}
        wait_run(real_client, submitted["id"])

    asyncio.run(exercise())
