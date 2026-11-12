import json
from pathlib import Path

from fastapi.testclient import TestClient

from jobhunter.api.app import create_app


def test_health_uses_isolated_db(session, monkeypatch):
    monkeypatch.setattr("jobhunter.api.health.get_engine", lambda: session.bind)
    with TestClient(create_app(serve_web=False)) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["db"] is True


def test_runtime_openapi_paths_match_contract():
    contract = json.loads((Path(__file__).resolve().parents[2] / "contracts/openapi.json").read_text())
    with TestClient(create_app(serve_web=False)) as client:
        response = client.get("/api/openapi.json")
    assert response.status_code == 200
    assert set(response.json()["paths"]) == set(contract["paths"])
