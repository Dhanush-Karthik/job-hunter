"""Shared fixtures for tests/test_api_*.py: in-memory DB, TestClient, faked runner/scheduler/careerops/keyring.

Load with `pytest_plugins = ["apihelpers"]` in the test module; helper functions import by name.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from datetime import timedelta

import keyring
import pytest
from fastapi.testclient import TestClient
from keyring.backend import KeyringBackend
from sqlmodel import Session, select

from jobhunter import careerops, paths
from jobhunter.api.app import create_app
from jobhunter.db import get_engine, get_session, migrate
from jobhunter.jobs import power, runner, scheduler
from jobhunter.models import (
    Actor,
    Application,
    ApplyChannel,
    AppStatus,
    Evaluation,
    Event,
    Lead,
    Run,
    RunKind,
    RunState,
    Source,
    utcnow,
)
from jobhunter.schemas import RunOut, ServiceHealth

_refs = itertools.count(1)


class MemoryKeyring(KeyringBackend):
    priority = 99

    def __init__(self):
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        self.store.pop((service, username), None)


class Fakes:
    """What the API calls out to; tests read `.submitted`, `.reloaded`, `.keyring` and tweak `.services`."""

    def __init__(self, engine):
        self.engine = engine
        self.submitted: list[tuple[RunKind, int | None, dict | None]] = []
        self.reloaded: list = []
        self.lifecycle: list[str] = []
        self.keyring = MemoryKeyring()
        self.services = [
            ServiceHealth(name="scheduler", ok=True, detail="next run 08:00"),
            ServiceHealth(name="claude CLI", ok=True),
            ServiceHealth(name="career-ops", ok=True),
            ServiceHealth(name="playwright", ok=False, detail="chromium missing"),
            ServiceHealth(name="gmail", ok=False, detail="Wave 3"),
        ]

    # runner
    def submit(self, kind, *, lead_id=None, params=None):
        self.submitted.append((kind, lead_id, params))
        with Session(self.engine) as s:
            run = s.exec(
                select(Run).where(Run.kind == kind, Run.lead_id == lead_id, Run.state == RunState.queued)
            ).first()
            if run is None:
                run = Run(kind=kind, lead_id=lead_id, params=params or {})
                s.add(run)
                s.commit()
            s.refresh(run)
            return run

    def cancel(self, run_id):
        with Session(self.engine) as s:
            run = s.get(Run, run_id)
            if run is None:
                raise KeyError(run_id)
            if run.state == RunState.queued:
                run.state, run.finished_at = RunState.cancelled, utcnow()
                s.add(run)
                s.commit()
            s.refresh(run)
            return run

    def read_log(self, run_id, tail=200):
        with Session(self.engine) as s:
            if s.get(Run, run_id) is None:
                raise KeyError(run_id)
        return f"log of run {run_id} (tail {tail})", False

    @staticmethod
    def to_out(run):
        return RunOut.model_validate(run, from_attributes=True)

    async def events(self):
        with Session(self.engine) as s:
            runs = list(s.exec(select(Run).order_by(Run.id)))
        for run in runs:
            yield self.to_out(run)


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    for name, sub in (("DATA", ""), ("CV_DIR", "cv"), ("CAREEROPS_DATA", "careerops"),
                      ("CONFIG_PATH", "absent.yml"), ("DB_PATH", "x.sqlite")):
        monkeypatch.setattr(paths, name, tmp_path / sub if sub else tmp_path)
    monkeypatch.setattr(paths, "CONFIG_EXAMPLE", paths.ROOT / "config/jobhunter.example.yml")
    get_engine.cache_clear()
    eng = get_engine("sqlite://")
    migrate(eng)
    yield eng
    eng.dispose()
    get_engine.cache_clear()


@pytest.fixture()
def fakes(engine, monkeypatch):
    f = Fakes(engine)
    monkeypatch.setattr(runner, "submit", f.submit)
    monkeypatch.setattr(runner, "cancel", f.cancel)
    monkeypatch.setattr(runner, "read_log", f.read_log)
    monkeypatch.setattr(runner, "to_out", f.to_out)
    monkeypatch.setattr(runner, "events", f.events)
    monkeypatch.setattr(runner, "shutdown", lambda wait=False: f.lifecycle.append("runner.shutdown"))
    monkeypatch.setattr(runner, "engine_factory", lambda: engine)  # jobs.nightly opens its own sessions
    monkeypatch.setattr(power, "ok_to_run", lambda: (True, "AC power"))
    monkeypatch.setattr(power, "hold_awake", lambda seconds: True)
    monkeypatch.setattr(scheduler, "start", lambda: f.lifecycle.append("scheduler.start"))
    monkeypatch.setattr(scheduler, "shutdown", lambda: f.lifecycle.append("scheduler.shutdown"))
    monkeypatch.setattr(scheduler, "reload", lambda settings: f.reloaded.append(settings))
    monkeypatch.setattr(scheduler, "is_running", lambda: True)
    monkeypatch.setattr(scheduler, "services", lambda: f.services)
    monkeypatch.setattr(careerops, "report_md", lambda ev: f"# Report {ev.id}\n\nA-G")
    monkeypatch.setattr("jobhunter.api.health.get_engine", lambda: engine)
    previous = keyring.get_keyring()
    keyring.set_keyring(f.keyring)
    yield f
    keyring.set_keyring(previous)


@pytest.fixture()
def app(engine, fakes):
    app = create_app(serve_web=False)

    def _session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _session
    return app


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db(engine):
    """A fresh session for seeding and for checking what the API wrote."""
    with Session(engine) as s:
        yield s


# ---------- seed helpers ----------


def make_lead(db: Session, **kw) -> Lead:
    n = next(_refs)
    fields = {"source": Source.naukri, "source_ref": f"ref{n}", "company": f"Company {n}", "title": "Java Developer",
                  "apply_channel": ApplyChannel.company_ats, "quick_score": 0.5}
    fields.update(kw)
    lead = Lead(**fields)
    db.add(lead)
    db.commit()
    if lead.dedupe_group is None and "dedupe_group" not in kw:
        lead.dedupe_group = f"d{lead.id}"
        db.commit()
    return lead


def make_app(db: Session, lead: Lead, status: AppStatus = AppStatus.new, **kw) -> Application:
    app = Application(lead_id=lead.id, status=status, **kw)
    db.add(app)
    db.commit()
    return app


def make_event(db: Session, app: Application, to: AppStatus, *, days_ago: float = 0, actor=Actor.owner) -> Event:
    ev = Event(application_id=app.id, to_status=to, at=utcnow() - timedelta(days=days_ago), actor=actor)
    db.add(ev)
    db.commit()
    return ev


def make_eval(db: Session, lead: Lead, score: float | None = 4.0, grade: str | None = "B", **kw) -> Evaluation:
    ev = Evaluation(lead_id=lead.id, score=score, grade=grade, **kw)
    db.add(ev)
    db.commit()
    return ev
