from pathlib import Path

import pytest
from sqlmodel import Session

from jobhunter import paths
from jobhunter.db import get_engine, migrate
from jobhunter.settings import get_settings, save_settings

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def session():
    get_engine.cache_clear()
    engine = get_engine("sqlite://")
    migrate(engine)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()
        get_engine.cache_clear()


@pytest.fixture()
def settings(session, monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "CONFIG_PATH", tmp_path / "absent.yml")
    monkeypatch.setattr(paths, "CONFIG_EXAMPLE", ROOT / "config/jobhunter.example.yml")
    settings = get_settings(session)
    settings.query_matrix.titles = ["Java Developer"]
    settings.query_matrix.locations = ["Chennai"]
    settings.evaluator.mode = "full"  # these flows drive the career-ops fake (tests/fakes/claude)
    save_settings(session, settings)
    return settings
