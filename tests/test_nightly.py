"""Nightly funnel: intake -> candidate selection -> lean evaluation -> Today's picks. Offline, fake clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select
from test_jobs import NOW, jobs, lead, stored  # noqa: F401  (jobs is a fixture)

from jobhunter import careerops
from jobhunter.intake.types import IngestResult
from jobhunter.jobs import nightly, power, runner
from jobhunter.models import Application, AppStatus, Evaluation, RoleFamily, Run, RunKind, RunState
from jobhunter.pipeline.freshness import within_24h

KEY = "2026-11-13"  # NOW is 00:30 IST on 13 Nov


@pytest.fixture
def night(jobs, monkeypatch):  # noqa: F811
    monkeypatch.setattr(nightly, "now", lambda: NOW)
    monkeypatch.setattr(power, "ok_to_run", lambda: (True, "AC power"))
    monkeypatch.setattr(power, "hold_awake", lambda seconds: True)
    monkeypatch.setattr(careerops, "scan", lambda *args, **kwargs: IngestResult())
    runner.event_hooks.append(nightly.on_run_finished)
    return jobs


def _evaluations(session):
    return session.exec(select(Run).where(Run.kind == RunKind.evaluate).order_by(Run.id)).all()


def test_night_runs_intake_then_evaluates_once(night, session, monkeypatch):
    from jobhunter.intake import boards

    monkeypatch.setattr(boards, "fetch_boards", lambda *args, **kwargs: [])
    best = lead(session, "best", quick_score=0.9)
    intake = nightly.start()
    assert {r.kind for r in intake} == {RunKind.intake_boards, RunKind.careerops_scan}
    assert all(r.params["nightly"] == KEY and r.params["stage"] == "intake" for r in intake)
    assert _evaluations(session) == []  # waits for intake
    runner._intake_pool.drain()
    queued = _evaluations(session)
    assert [r.lead_id for r in queued] == [best.id] and queued[0].params == {"nightly": KEY, "auto": True}
    assert nightly.start() == [] and nightly.evaluate(KEY) == []  # idempotent per night


def test_low_battery_postpones(night, session, monkeypatch):
    monkeypatch.setattr(power, "ok_to_run", lambda: (False, "on battery at 12%"))
    assert nightly.start() == []
    assert session.exec(select(Run)).all() == []


def test_catch_up_starts_missed_night_and_forces_stage_two(night, session, monkeypatch):
    lead(session, "x")
    runs = nightly.catch_up()  # 00:30 IST, nothing ran yet
    assert {r.kind for r in runs} == {RunKind.intake_boards, RunKind.careerops_scan}
    assert nightly.catch_up() == []  # intake still queued, fallback not due
    monkeypatch.setattr(nightly, "now", lambda: NOW + timedelta(minutes=51))
    assert [r.kind for r in nightly.catch_up()] == [RunKind.evaluate]


def test_catch_up_only_until_noon(night, monkeypatch):
    monkeypatch.setattr(nightly, "now", lambda: datetime(2026, 11, 13, 7, tzinfo=UTC))  # 12:30 IST
    assert nightly.catch_up() == []


def test_candidate_rules(night, session):
    s = night
    s.nightly.candidates, s.nightly.per_company = 10, 2
    inbound = lead(session, "inbound", quick_score=0.36, is_inbound=True, company="Recruiter Co")
    fresh = lead(session, "fresh", quick_score=0.70, company="B", posted_at=NOW - timedelta(hours=3))
    stale = lead(session, "stale", quick_score=0.72, company="C", posted_at=NOW - timedelta(hours=60))
    lead(session, "too-old", quick_score=0.99, company="D", posted_at=NOW - timedelta(hours=73))
    lead(session, "weak", quick_score=0.34, company="E")
    lead(session, "dropped", quick_score=0.9, company="F", prefilter_pass=False)
    primary = lead(session, "primary", quick_score=0.5, company="G", dedupe_group="g", role_family=RoleFamily.p1)
    lead(session, "dup", quick_score=0.95, company="G2", dedupe_group="g")
    a1 = lead(session, "a1", quick_score=0.9, company="Acme", title="Java Developer")
    lead(session, "a1-same-title", quick_score=0.89, company="acme", title="Java Developer (Remote)")
    a2 = lead(session, "a2", quick_score=0.85, company="Acme", title="Backend Engineer")
    lead(session, "a3", quick_score=0.8, company="Acme", title="Platform Engineer")
    lead(session, "four-years", quick_score=0.95, company="J", exp_min=4, exp_max=8)
    three = lead(session, "three-years", quick_score=0.3 + 0.06 + 0.04, company="M", exp_min=3, exp_max=6,
                 role_family=RoleFamily.p1)
    lead(session, "support", quick_score=0.5, company="K", title="Customer Support Engineer", role_family=RoleFamily.other)
    strong_other = lead(session, "strong-other", quick_score=0.56, company="L", role_family=RoleFamily.other)
    scored = lead(session, "scored", quick_score=0.9, company="H")
    shortlisted = lead(session, "shortlisted", quick_score=0.9, company="I")
    session.add_all([Evaluation(lead_id=scored.id, score=3.0, created_at=NOW - timedelta(days=30)),
                     Application(lead_id=shortlisted.id, status=AppStatus.shortlisted)])
    session.commit()
    chosen = nightly.select_candidates(session, s, NOW)
    # inbound first; fresh (0.70 + 0.06 for <24 h) beats stale 0.72; max 2 per company, one per title
    assert [c.id for c in chosen] == [inbound.id, a1.id, a2.id, fresh.id, stale.id, strong_other.id, primary.id, three.id]


def test_picks_rank_and_quality_bar(night, session):
    s = night
    s.nightly.picks_max = 3
    rows = {}
    for ref, score, chance, extra in [
        ("strong-high", 4.2, "high", {}), ("strong-low", 4.1, "low", {}), ("ok-medium", 3.6, "medium", {}),
        ("weak-low", 3.7, "low", {}), ("below-bar", 3.4, "high", {}), ("closed", 4.8, "high", {"is_live": False}),
        ("old-eval", 4.9, "high", {"created_at": NOW - timedelta(hours=49)}), ("applied", 4.9, "high", {}),
        ("four-plus-years", 4.9, "high", {"exp_min": 4}),
    ]:
        row = lead(session, ref, exp_min=extra.get("exp_min"))
        rows[ref] = row
        session.add(Evaluation(lead_id=row.id, score=score, call_chance=chance, verdict=ref,
                               created_at=extra.get("created_at", NOW - timedelta(hours=1)),
                               is_live=extra.get("is_live")))
    session.add(Application(lead_id=rows["applied"].id, status=AppStatus.applied))
    session.commit()
    picked = [p.source_ref for p in nightly.picks(session, s, NOW)]
    assert picked == ["strong-high", "strong-low", "ok-medium"]
    s.nightly.picks_max = 20
    assert "weak-low" not in [p.source_ref for p in nightly.picks(session, s, NOW)]


def test_within_24h_date_only_uses_ist_calendar():
    found = NOW
    # NOW = 00:30 IST 13 Nov. Date-only postings dated 12 or 13 Nov count; 11 Nov does not.
    assert within_24h(datetime(2026, 11, 12), found, NOW)
    assert not within_24h(datetime(2026, 11, 11), found, NOW)
    assert within_24h(NOW - timedelta(hours=23, minutes=59), found, NOW)
    assert not within_24h(NOW - timedelta(hours=25, seconds=1), found, NOW)
    assert within_24h(None, NOW - timedelta(hours=2), NOW)


def test_api_triggers_night(night, session):
    from fastapi.testclient import TestClient

    from jobhunter.api.app import app
    from jobhunter.api.deps import get_session

    app.dependency_overrides[get_session] = lambda: session
    try:
        lead(session, "only")
        body = TestClient(app).post("/api/nightly/run?stage=evaluate").json()
        assert [r["kind"] for r in body] == ["evaluate"]
        assert stored(session, body[0]["id"]).state == RunState.queued
    finally:
        app.dependency_overrides.clear()
