"""Offline run engine and scheduler checks; no real scraper, Claude or owner data."""

import asyncio
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session, select

from jobhunter import careerops, paths, pipeline
from jobhunter.intake import boards
from jobhunter.intake.types import IngestResult
from jobhunter.jobs import runner, scheduler
from jobhunter.models import (
    Application,
    AppStatus,
    Evaluation,
    Lead,
    ResumeVariant,
    Run,
    RunKind,
    RunState,
    Source,
    SourceHealth,
)
from jobhunter.settings import load_defaults, save_settings

NOW = datetime(2026, 11, 12, 19, tzinfo=UTC)  # Already Nov 13 in India.


class DeferredExecutor:
    def __init__(self, **kwargs):
        self.calls = []

    def submit(self, fn, *args):
        future = Future()
        self.calls.append((future, fn, args))
        return future

    def drain(self):
        while self.calls:
            future, fn, args = self.calls.pop(0)
            if future.set_running_or_notify_cancel():
                future.set_result(fn(*args))

    def shutdown(self, wait=True, *, cancel_futures=False):
        for future, _, _ in self.calls:
            if cancel_futures:
                future.cancel()


class ImmediateExecutor(DeferredExecutor):
    def submit(self, fn, *args):
        future = super().submit(fn, *args)
        self.drain()
        return future


@pytest.fixture
def jobs(session, monkeypatch, tmp_path):
    engine = session.get_bind()
    settings = load_defaults(paths.CONFIG_EXAMPLE)
    save_settings(session, settings)
    monkeypatch.setattr(runner, "engine_factory", lambda: engine)
    monkeypatch.setattr(runner, "executor_factory", DeferredExecutor)
    monkeypatch.setattr(runner, "_claude_pool", None)
    monkeypatch.setattr(runner, "_intake_pool", None)
    monkeypatch.setattr(runner, "_cancel_flags", {})
    monkeypatch.setattr(runner, "_subscribers", set())
    monkeypatch.setattr(runner, "event_hooks", [])
    monkeypatch.setattr(runner, "_accepting", True)
    monkeypatch.setattr(runner, "utcnow", lambda: NOW)
    monkeypatch.setattr(scheduler, "now", lambda: NOW)
    monkeypatch.setattr(paths, "RUN_LOGS", tmp_path / "logs/runs")
    monkeypatch.setattr(
        scheduler,
        "_scheduler",
        BackgroundScheduler(
            timezone=scheduler.TIMEZONE,
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600},
        ),
    )
    yield settings
    if scheduler.is_running():
        scheduler._scheduler.shutdown(wait=True)
    runner.shutdown(wait=True)


def lead(session, ref="job", **kwargs):
    values = {
        "source": Source.manual,
        "source_ref": ref,
        "title": "Java Developer",
        "company": "Acme",
        "quick_score": 0.8,
        "found_at": NOW,
    }
    values.update(kwargs)
    row = Lead(**values)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def stored(session, run_id):
    session.expire_all()
    return session.get(Run, run_id)


def wait_terminal(engine, run_id, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with runner._lock, Session(engine) as session:
            row = session.get(Run, run_id)
            if row.state not in (RunState.queued, RunState.running):
                return row
        time.sleep(0.01)
    pytest.fail(f"run {run_id} did not finish")


def test_submit_deduplicates_and_validates_lead(jobs, session):
    row = lead(session)
    first = runner.submit(RunKind.evaluate, lead_id=row.id, params={"auto": True})
    again = runner.submit(RunKind.evaluate, lead_id=row.id)
    assert first.id == again.id
    assert first.state == RunState.queued
    assert again.params == {"auto": True}
    assert len(runner._claude_pool.calls) == 1
    assert runner.submit(RunKind.intake_boards).id == runner.submit(RunKind.intake_boards).id
    assert len(runner._intake_pool.calls) == 1
    with pytest.raises(ValueError, match="does not exist"):
        runner.submit(RunKind.evaluate, lead_id=9999)


def test_concurrent_submit_is_atomic(jobs, session):
    row = lead(session)
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(lambda _: runner.submit(RunKind.evaluate, lead_id=row.id), range(20)))
    assert len({row.id for row in rows}) == 1
    assert len(runner._claude_pool.calls) == 1


def test_states_and_gmail_placeholder(jobs, session):
    updates = []
    runner.event_hooks.append(updates.append)
    queued = runner.submit(RunKind.intake_gmail)
    assert runner.read_log(queued.id) == ("", False)
    runner._intake_pool.drain()
    done = stored(session, queued.id)
    assert done.state == RunState.succeeded
    assert done.started_at and done.finished_at
    assert done.summary == "Gmail intake arrives in Wave 3"
    assert done.error is None
    assert [event.state for event in updates] == [RunState.queued, RunState.running, RunState.succeeded]
    assert runner.to_out(done).model_dump() == updates[-1].model_dump()
    assert runner.submit(RunKind.intake_gmail).id != queued.id
    assert runner.cancel(done.id).state == RunState.succeeded


@pytest.mark.parametrize(
    ("kind", "function"),
    [
        (RunKind.evaluate, "evaluate"),
        (RunKind.verify, "verify"),
        (RunKind.contacts, "find_contacts"),
        (RunKind.assist_apply, "assist_apply"),
        (RunKind.cv, "generate_cv"),
    ],
)
def test_bridge_dispatch(jobs, session, monkeypatch, kind, function):
    row = lead(session)
    calls = []

    def bridge(worker_session, lead_id, *args, **kwargs):
        assert worker_session is not session
        assert lead_id == row.id
        assert kwargs["run_id"] == run.id
        assert not kwargs["should_cancel"]()
        kwargs["log"].write("bridge progress\n")
        calls.append(args)

    monkeypatch.setattr(careerops, function, bridge)
    run = runner.submit(kind, lead_id=row.id, params={"variant": "B"})
    runner._claude_pool.drain()
    assert stored(session, run.id).state == RunState.succeeded
    assert calls == [(ResumeVariant.b,)] if kind == RunKind.cv else calls == [()]
    assert "bridge progress" in runner.read_log(run.id)[0]


@pytest.mark.parametrize("kind", [RunKind.careerops_scan, RunKind.intake_remote])
def test_scan_alias_dispatch(jobs, session, monkeypatch, kind):
    calls = []

    def scan(worker_session, settings, **kwargs):
        calls.append(settings)
        assert worker_session is not session
        assert not kwargs["should_cancel"]()
        return IngestResult(fetched=3, new=2)

    monkeypatch.setattr(careerops, "scan", scan)
    run = runner.submit(kind)
    runner._intake_pool.drain()
    assert stored(session, run.id).summary == IngestResult(fetched=3, new=2).summary()
    assert calls == [jobs]


def test_board_dispatch_ingests_fetched_rows(jobs, session, monkeypatch):
    raws, calls = [object()], []

    def fetch(worker_session, settings):
        assert worker_session is not session
        assert settings == jobs
        return raws

    def ingest(worker_session, values, settings):
        assert values is raws
        calls.append(values)
        return IngestResult(fetched=1, new=1)

    monkeypatch.setattr(boards, "fetch_boards", fetch)
    monkeypatch.setattr(pipeline, "ingest", ingest)
    run = runner.submit(RunKind.intake_boards)
    runner._intake_pool.drain()
    assert stored(session, run.id).summary == IngestResult(fetched=1, new=1).summary()
    assert calls == [raws]


@pytest.mark.parametrize(
    ("exception", "state", "error"),
    [
        (careerops.BridgeError("sign in again"), RunState.failed, "sign in again"),
        (careerops.Cancelled("stopped"), RunState.cancelled, "stopped"),
        (ValueError("broken"), RunState.failed, "internal error: ValueError: broken"),
    ],
)
def test_failures_are_persisted_and_logged(jobs, session, monkeypatch, exception, state, error):
    row = lead(session)

    def fail(*args, **kwargs):
        raise exception

    monkeypatch.setattr(careerops, "evaluate", fail)
    run = runner.submit(RunKind.evaluate, lead_id=row.id)
    runner._claude_pool.drain()
    result = stored(session, run.id)
    assert result.state == state
    assert result.error == error
    assert result.finished_at
    log, truncated = runner.read_log(run.id)
    assert error in log and not truncated
    if isinstance(exception, ValueError):
        assert "Traceback (most recent call last)" in log


def test_cancel_queued_never_dispatches(jobs, session, monkeypatch):
    row = lead(session)
    calls = []
    monkeypatch.setattr(careerops, "evaluate", lambda *a, **kw: calls.append(a))
    run = runner.submit(RunKind.evaluate, lead_id=row.id)
    assert runner.cancel(run.id).state == RunState.cancelled
    runner._claude_pool.drain()
    assert stored(session, run.id).started_at is None
    assert not calls
    with pytest.raises(KeyError):
        runner.cancel(999)
    with pytest.raises(KeyError):
        runner.read_log(999)


def test_cancel_running_worker_polls_flag(jobs, session, monkeypatch):
    monkeypatch.setattr(runner, "executor_factory", ThreadPoolExecutor)
    started = threading.Event()
    row = lead(session)

    def evaluate(*args, should_cancel, **kwargs):
        started.set()
        deadline = time.monotonic() + 5
        while not should_cancel() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert should_cancel()
        raise careerops.Cancelled("owner cancelled")

    monkeypatch.setattr(careerops, "evaluate", evaluate)
    run = runner.submit(RunKind.evaluate, lead_id=row.id)
    assert started.wait(3)
    assert runner.submit(RunKind.evaluate, lead_id=row.id).id == run.id
    assert runner.cancel(run.id).state == RunState.running
    assert wait_terminal(session.get_bind(), run.id).state == RunState.cancelled


def test_log_tail_is_bounded_and_reports_truncation(jobs, session, monkeypatch):
    row = lead(session)

    def evaluate(*args, log, **kwargs):
        for index in range(300):
            log.write(f"line {index}\n")

    monkeypatch.setattr(careerops, "evaluate", evaluate)
    run = runner.submit(RunKind.evaluate, lead_id=row.id)
    runner._claude_pool.drain()
    full, cut = runner.read_log(run.id, tail=500)
    assert len(full.splitlines()) == 302 and not cut
    tail, cut = runner.read_log(run.id, tail=2)
    assert tail == "line 299\nsucceeded: evaluate completed\n" and cut
    assert runner.read_log(run.id, tail=0) == ("", True)
    assert (paths.RUN_LOGS / f"{run.id}.log").is_file()


def test_events_fan_out_from_worker_thread(jobs, monkeypatch):
    monkeypatch.setattr(runner, "executor_factory", ThreadPoolExecutor)

    async def exercise():
        first, second = runner.events(), runner.events()
        pending = [asyncio.create_task(anext(first)), asyncio.create_task(anext(second))]
        await asyncio.sleep(0)
        run = await asyncio.to_thread(runner.submit, RunKind.intake_gmail)
        for stream, initial in zip((first, second), pending, strict=True):
            snapshots = [await asyncio.wait_for(initial, 3)]
            snapshots.extend([await asyncio.wait_for(anext(stream), 3) for _ in range(2)])
            assert [item.state for item in snapshots] == [
                RunState.queued,
                RunState.running,
                RunState.succeeded,
            ]
            assert {item.id for item in snapshots} == {run.id}
            await stream.aclose()
        assert not runner._subscribers

    asyncio.run(exercise())


def test_recover_marks_only_interrupted_runs(jobs, session):
    rows = [Run(kind=RunKind.intake_gmail, state=state) for state in RunState]
    session.add_all(rows)
    session.commit()
    assert runner.recover_on_boot() == 2
    session.expire_all()
    for row in rows[:2]:
        assert row.state == RunState.failed
        assert row.error == "server restarted"
        assert row.finished_at
    assert rows[2].state == RunState.succeeded
    assert rows[4].state == RunState.cancelled
    assert runner.recover_on_boot() == 0


def test_pool_never_exceeds_settings_concurrency(jobs, session, monkeypatch):
    jobs.claude_concurrency = 2
    save_settings(session, jobs)
    monkeypatch.setattr(runner, "executor_factory", ThreadPoolExecutor)
    gate, two_started = threading.Event(), threading.Event()
    lock, counters = threading.Lock(), {"active": 0, "peak": 0}
    rows = [lead(session, str(index)) for index in range(6)]

    def evaluate(*args, **kwargs):
        with lock:
            counters["active"] += 1
            counters["peak"] = max(counters["peak"], counters["active"])
            if counters["active"] == 2:
                two_started.set()
        assert gate.wait(5)
        with lock:
            counters["active"] -= 1

    monkeypatch.setattr(careerops, "evaluate", evaluate)
    runs = [runner.submit(RunKind.evaluate, lead_id=row.id) for row in rows]
    try:
        assert two_started.wait(3)
        assert counters["peak"] == 2
        # Intake uses its own pool and can finish while both Claude slots are occupied.
        intake = runner.submit(RunKind.intake_gmail)
        assert wait_terminal(session.get_bind(), intake.id).state == RunState.succeeded
    finally:
        gate.set()
    for run in runs:
        assert wait_terminal(session.get_bind(), run.id).state == RunState.succeeded
    assert counters["peak"] == jobs.claude_concurrency


def test_shutdown_cancels_queue_and_rejects_work(jobs, session):
    run = runner.submit(RunKind.intake_gmail)
    runner.shutdown(wait=True)
    assert stored(session, run.id).state == RunState.cancelled
    with pytest.raises(RuntimeError, match="shutting down"):
        runner.submit(RunKind.intake_gmail)


def test_auto_evaluate_candidate_rules(jobs, session):
    best = lead(session, "best", quick_score=0.95)
    boundary = lead(session, "boundary", quick_score=0.45, found_at=NOW - timedelta(days=3))
    primary = lead(session, "primary", quick_score=0.7, dedupe_group="same")
    lead(session, "duplicate", quick_score=1.0, dedupe_group="same")
    lead(session, "filtered", prefilter_pass=False)
    lead(session, "weak", quick_score=0.449)
    lead(session, "old", found_at=NOW - timedelta(days=3, seconds=1))
    lead(session, "future", found_at=NOW + timedelta(days=1))
    scored = lead(session, "scored")
    unscored = lead(session, "unscored", quick_score=0.6)
    expired_score = lead(session, "expired-score", quick_score=0.5)
    applied = lead(session, "applied")
    skipped = lead(session, "skipped")
    shortlisted = lead(session, "shortlisted", quick_score=0.9)
    session.add_all(
        [
            Evaluation(lead_id=scored.id, score=4, created_at=NOW - timedelta(days=14)),
            Evaluation(lead_id=unscored.id, score=None, created_at=NOW),
            Evaluation(lead_id=expired_score.id, score=4, created_at=NOW - timedelta(days=14, seconds=1)),
            Application(lead_id=applied.id, status=AppStatus.applied),
            Application(lead_id=skipped.id, status=AppStatus.skipped),
            Application(lead_id=shortlisted.id, status=AppStatus.shortlisted),
        ]
    )
    session.commit()
    queued = scheduler.auto_evaluate(session, jobs)
    assert [run.lead_id for run in queued] == [
        best.id,
        shortlisted.id,
        primary.id,
        unscored.id,
        expired_score.id,
        boundary.id,
    ]
    assert all(run.params == {"auto": True} for run in queued)
    assert scheduler.auto_evaluate(session, jobs) == []


def test_auto_evaluate_daily_cap_uses_india_midnight(jobs, session):
    jobs.auto_evaluate_top_n = 3
    rows = [lead(session, str(index)) for index in range(8)]
    session.add_all(
        [
            # 18:30 UTC is midnight in India, even though UTC still says Nov 12.
            Run(
                kind=RunKind.evaluate,
                state=RunState.failed,
                params={"auto": True},
                created_at=NOW.replace(hour=18, minute=30),
            ),
            Run(
                kind=RunKind.evaluate,
                state=RunState.cancelled,
                params={"auto": True},
                created_at=NOW.replace(hour=18, minute=45),
            ),
            Run(
                kind=RunKind.evaluate,
                state=RunState.succeeded,
                params={"auto": True},
                created_at=NOW.replace(hour=18, minute=29),
            ),
            Run(kind=RunKind.evaluate, state=RunState.succeeded, params={"auto": False}, created_at=NOW),
            Run(kind=RunKind.verify, state=RunState.succeeded, params={"auto": True}, created_at=NOW),
        ]
    )
    session.commit()
    queued = scheduler.auto_evaluate(session, jobs)
    assert [run.lead_id for run in queued] == [rows[0].id]
    assert scheduler.auto_evaluate(session, jobs) == []


def test_auto_evaluate_zero_budget(jobs, session):
    lead(session)
    jobs.auto_evaluate_top_n = 0
    assert scheduler.auto_evaluate(session, jobs) == []


def test_reload_replaces_jobs_and_matches_local_hours(jobs):
    scheduler.reload(jobs)
    scheduled = {job.id: job for job in scheduler._scheduler.get_jobs()}
    assert set(scheduled) == {"intake_boards", "careerops_scan_0800", "careerops_scan_1700"}
    boards_job = scheduled["intake_boards"]
    assert str(boards_job.trigger.timezone) == "Asia/Kolkata"
    fire = datetime(2026, 11, 12, 0, tzinfo=scheduler.TIMEZONE)
    hours = []
    while True:
        fire = boards_job.trigger.get_next_fire_time(None, fire)
        if fire.day != 12:
            break
        hours.append(fire.hour)
        fire += timedelta(seconds=1)
    assert hours == [7, 10, 13, 16, 19, 22]
    assert all(job.func is scheduler._scheduled for job in scheduled.values())
    assert scheduled["careerops_scan_0800"].args == (RunKind.careerops_scan,)
    jobs.schedules.careerops_scan_times = ["09:15"]
    jobs.schedules.boards_window = (8, 20)
    jobs.schedules.boards_every_hours = 4
    scheduler.reload(jobs)
    assert {job.id for job in scheduler._scheduler.get_jobs()} == {
        "intake_boards",
        "careerops_scan_0915",
    }


@pytest.mark.parametrize("kind", [RunKind.intake_boards, RunKind.careerops_scan])
@pytest.mark.parametrize("blocked", ["disabled", "paused"])
def test_scheduled_source_skips_disabled_and_paused(jobs, session, monkeypatch, kind, blocked):
    sources = jobs.query_matrix.sites if kind == RunKind.intake_boards else [Source.careerops_scan]
    for source in sources:
        session.add(
            SourceHealth(
                source=source.value,
                enabled=blocked != "disabled",
                paused_until=NOW + timedelta(hours=1) if blocked == "paused" else None,
            )
        )
    session.commit()
    calls = []
    monkeypatch.setattr(runner, "submit", lambda *args, **kwargs: calls.append(args))
    scheduler._scheduled(kind)
    assert not calls
    first = session.get(SourceHealth, sources[0].value)
    first.enabled, first.paused_until = True, NOW - timedelta(seconds=1)
    session.add(first)
    session.commit()
    scheduler._scheduled(kind)
    assert calls == [(kind,)]


def test_scheduler_start_is_idempotent_and_recovers(jobs, session, monkeypatch):
    session.add(Run(kind=RunKind.intake_boards))
    session.commit()
    scheduler.start()
    scheduler.start()
    assert scheduler.is_running()
    assert len(scheduler._scheduler.get_jobs()) == 3
    assert runner.event_hooks.count(scheduler._scan_finished) == 1
    assert session.exec(select(Run)).one().error == "server restarted"
    for job in scheduler._scheduler.get_jobs():
        assert job.coalesce and job.max_instances == 1 and job.misfire_grace_time == 3600
    scheduler.shutdown()
    assert not scheduler.is_running()
    scheduler.start()
    assert scheduler.is_running()


def test_scan_success_triggers_auto_evaluate(jobs, session, monkeypatch):
    monkeypatch.setattr(careerops, "scan", lambda *args, **kwargs: IngestResult())
    row = lead(session)
    scheduler.start()
    scan = runner.submit(RunKind.careerops_scan)
    runner._intake_pool.drain()
    assert stored(session, scan.id).state == RunState.succeeded
    evaluated = session.exec(select(Run).where(Run.kind == RunKind.evaluate)).one()
    assert evaluated.lead_id == row.id and evaluated.params == {"auto": True}


def test_services_reports_runtime_and_board_health(jobs, session, monkeypatch, tmp_path):
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "package.json").write_text("{}")
    (vendor / "node_modules").mkdir()
    home = tmp_path / "home"
    (home / "Library/Caches/ms-playwright/chromium-123").mkdir(parents=True)
    monkeypatch.setattr(paths, "CAREEROPS_VENDOR", vendor)
    monkeypatch.setattr(scheduler.Path, "home", lambda: home)
    monkeypatch.setenv("JOBHUNTER_CLAUDE_BIN", "fake-claude")
    monkeypatch.setattr(
        scheduler.shutil, "which", lambda binary: "/test/claude" if binary == "fake-claude" else None
    )
    session.add_all(
        [
            SourceHealth(source="linkedin", last_run_at=NOW, last_ok_at=NOW, last_count=4),
            SourceHealth(source="naukri", enabled=False),
            SourceHealth(source="indeed", paused_until=NOW + timedelta(hours=1)),
            SourceHealth(source="glassdoor", last_error="429", consecutive_failures=1),
        ]
    )
    session.commit()
    scheduler.reload(jobs)
    result = {service.name: service for service in scheduler.services()}
    assert set(result) == {
        "scheduler",
        "claude",
        "career-ops",
        "playwright chromium",
        "gmail",
        *[site.value for site in jobs.query_matrix.sites],
    }
    assert not result["scheduler"].ok and "intake_boards" in result["scheduler"].detail
    assert result["claude"].ok and result["career-ops"].ok and result["playwright chromium"].ok
    assert result["linkedin"].ok
    assert not result["naukri"].ok and result["naukri"].detail == "disabled"
    assert not result["indeed"].ok and "paused" in result["indeed"].detail
    assert not result["glassdoor"].ok and result["glassdoor"].detail == "429"
    assert not result["gmail"].ok and result["gmail"].detail == "Wave 3"


def test_synchronous_executor_can_be_injected(jobs, session, monkeypatch):
    monkeypatch.setattr(runner, "executor_factory", ImmediateExecutor)
    run = runner.submit(RunKind.intake_gmail)
    assert stored(session, run.id).state == RunState.succeeded
