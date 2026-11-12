"""Wave 0 contract sanity: schema, transitions, settings, contract freshness, health."""

from fastapi.testclient import TestClient
from sqlmodel import select

from jobhunter import paths
from jobhunter.api import dump_openapi
from jobhunter.api.app import create_app
from jobhunter.db import SCHEMA_VERSION, migrate
from jobhunter.models import TERMINAL, TRANSITIONS, AppStatus, Lead, Source
from jobhunter.settings import get_settings, load_defaults


def test_migrate_idempotent(session):
    assert migrate(session.get_bind()) == SCHEMA_VERSION


def test_lead_roundtrip(session):
    session.add(Lead(source=Source.naukri, source_ref="1", company="Acme", title="Java Dev",
                     prefilter_reasons=["x"]))
    session.commit()
    lead = session.exec(select(Lead)).one()
    assert lead.prefilter_reasons == ["x"] and lead.found_at is not None


def test_transitions_cover_all_states():
    assert set(TRANSITIONS) == set(AppStatus)
    assert AppStatus.rejected in TERMINAL and AppStatus.applied not in TERMINAL
    assert AppStatus.screening in TRANSITIONS[AppStatus.ghosted]


def test_settings_defaults_seed(session, monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "CONFIG_PATH", tmp_path / "absent.yml")  # ignore local data/config.yml
    s = get_settings(session)
    assert s.auto_evaluate_top_n == 10 and s.prefilter.ctc_min_lpa == 10
    assert get_settings(session) == s == load_defaults(paths.CONFIG_EXAMPLE)


def test_contract_fresh():
    assert paths.CONTRACT.read_text() == dump_openapi.render()


def test_health(monkeypatch, tmp_path):
    from jobhunter.db import get_engine
    get_engine.cache_clear()
    monkeypatch.setattr(paths, "DATA", tmp_path)
    monkeypatch.setattr(paths, "DB_PATH", tmp_path / "t.sqlite")
    r = TestClient(create_app(serve_web=False)).get("/api/health")
    get_engine.cache_clear()
    assert r.status_code == 200 and r.json()["db"] is True
