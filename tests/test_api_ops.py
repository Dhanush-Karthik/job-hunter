"""Runs + SSE + intake, sources, settings, secrets, profiles, setup, health, lifespan."""

import json
from datetime import timedelta

import keyring
from apihelpers import make_lead
from fastapi.testclient import TestClient

from jobhunter import gmail, paths, secrets
from jobhunter.api.app import create_app
from jobhunter.models import Profile, Run, RunKind, RunState, SourceHealth, utcnow
from jobhunter.schemas import Settings

pytest_plugins = ["apihelpers"]


def add_run(db, kind=RunKind.evaluate, state=RunState.queued, **kw):
    run = Run(kind=kind, state=state, **kw)
    db.add(run)
    db.commit()
    return run


# ---------- runs ----------


def test_runs_list_filters_and_get(client, db):
    lead = make_lead(db)
    a = add_run(db, RunKind.evaluate, lead_id=lead.id, created_at=utcnow() - timedelta(hours=2))
    b = add_run(db, RunKind.verify, RunState.succeeded, lead_id=lead.id, summary="live")
    c = add_run(db, RunKind.intake_boards, RunState.failed, error="429")
    assert [r["id"] for r in client.get("/api/runs").json()] == [c.id, b.id, a.id]
    assert [r["id"] for r in client.get("/api/runs", params={"kind": "verify"}).json()] == [b.id]
    assert [r["id"] for r in client.get("/api/runs", params={"state": "failed"}).json()] == [c.id]
    assert [r["id"] for r in client.get("/api/runs", params={"lead_id": lead.id}).json()] == [b.id, a.id]
    assert client.get("/api/runs", params={"lead_id": 10**30}).json() == []
    assert len(client.get("/api/runs", params={"limit": 1}).json()) == 1
    assert client.get("/api/runs", params={"limit": 0}).status_code == 422
    one = client.get(f"/api/runs/{b.id}").json()
    assert (one["kind"], one["state"], one["summary"]) == ("verify", "succeeded", "live")
    assert client.get("/api/runs/999").status_code == 404
    assert client.get(f"/api/runs/{10**30}").status_code == 404


def test_run_log_and_cancel(client, db):
    run = add_run(db)
    log = client.get(f"/api/runs/{run.id}/log", params={"tail": 5}).json()
    assert log == {"run_id": run.id, "text": f"log of run {run.id} (tail 5)", "truncated": False}
    assert client.get(f"/api/runs/{run.id}/log", params={"tail": 0}).status_code == 422
    assert client.get("/api/runs/999/log").status_code == 404
    out = client.post(f"/api/runs/{run.id}/cancel").json()
    assert out["state"] == "cancelled" and out["finished_at"] is not None
    assert client.post("/api/runs/999/cancel").status_code == 404


def test_run_stream_emits_run_events(client, db):
    run = add_run(db, RunKind.cv, params={"variant": "A"})
    with client.stream("GET", "/api/runs/stream") as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        lines = [ln for ln in r.iter_lines() if ln]
    assert "event: run" in lines
    data = json.loads(next(ln for ln in lines if ln.startswith("data:"))[5:])
    assert data["id"] == run.id and data["kind"] == "cv" and data["params"] == {"variant": "A"}


def test_intake_default_runs_boards_and_scan(client, db, fakes):
    out = client.post("/api/intake/run", json={}).json()
    assert [r["kind"] for r in out] == ["intake_boards", "careerops_scan"]
    assert [(k, params) for k, _, params in fakes.submitted] == [
        (RunKind.intake_boards, None), (RunKind.careerops_scan, None)]


def test_intake_default_adds_gmail_when_configured_and_skips_disabled_scan(client, db, fakes):
    keyring.set_password("jobhunter", "gmail_address", "me@example.com")
    keyring.set_password("jobhunter", "gmail_app_password", "pw")
    db.add(SourceHealth(source="careerops_scan", enabled=False))
    db.commit()
    kinds = [r["kind"] for r in client.post("/api/intake/run", json={}).json()]
    assert kinds == ["intake_boards", "intake_gmail"]


def test_intake_explicit_sources_map_once_per_kind(client, db, fakes):
    body = {"sources": ["linkedin", "naukri", "remotive", "himalayas", "careerops_scan", "gmail_alert"]}
    out = client.post("/api/intake/run", json=body).json()
    assert sorted(r["kind"] for r in out) == ["careerops_scan", "intake_boards", "intake_gmail"]
    boards = next(p for k, _, p in fakes.submitted if k == RunKind.intake_boards)
    assert boards == {"sources": ["linkedin", "naukri"]}
    assert client.post("/api/intake/run", json={"sources": ["remoteok"]}).json()[0]["kind"] == "careerops_scan"
    assert client.post("/api/intake/run", json={"sources": ["manual"]}).json() == []
    assert client.post("/api/intake/run", json={"sources": ["nope"]}).status_code == 422


# ---------- sources ----------


def test_sources_created_from_query_matrix_and_patched(client, db):
    rows = client.get("/api/sources").json()
    assert {r["source"] for r in rows} == {"careerops_scan", "glassdoor", "indeed", "linkedin", "naukri"}
    assert all(r["enabled"] and r["consecutive_failures"] == 0 for r in rows)
    db.add(SourceHealth(source="careerops:acme"))
    row = db.get(SourceHealth, "linkedin")
    row.paused_until, row.consecutive_failures, row.last_error = utcnow() + timedelta(hours=6), 3, "429"
    db.add(row)
    db.commit()
    assert "careerops:acme" not in {r["source"] for r in client.get("/api/sources").json()}
    off = client.patch("/api/sources/indeed", json={"enabled": False}).json()
    assert off["enabled"] is False
    un = client.patch("/api/sources/linkedin", json={"unpause": True}).json()
    assert un["paused_until"] is None and un["consecutive_failures"] == 0 and un["enabled"] is True
    assert client.patch("/api/sources/careerops:acme", json={"enabled": False}).json()["enabled"] is False
    assert client.patch("/api/sources/nope", json={}).status_code == 404


# ---------- settings ----------


def test_settings_roundtrip_reloads_scheduler(client, fakes):
    current = client.get("/api/settings").json()
    assert current["targets"]["applied_per_week"] == 60
    current["targets"]["applied_per_week"] = 40
    current["query_matrix"]["titles"] = ["Only This"]
    r = client.put("/api/settings", json=current)
    assert r.status_code == 200 and r.json()["targets"]["applied_per_week"] == 40
    assert client.get("/api/settings").json()["query_matrix"]["titles"] == ["Only This"]
    assert len(fakes.reloaded) == 1 and isinstance(fakes.reloaded[0], Settings)
    assert fakes.reloaded[0].targets.applied_per_week == 40
    bad = {**current, "claude_concurrency": 99}
    assert client.put("/api/settings", json=bad).status_code == 422


def test_settings_saved_even_if_reload_fails(client, monkeypatch):
    from jobhunter.jobs import scheduler

    def boom(settings):
        raise RuntimeError("scheduler down")

    monkeypatch.setattr(scheduler, "reload", boom)
    current = client.get("/api/settings").json()
    current["auto_evaluate_top_n"] = 3
    assert client.put("/api/settings", json=current).status_code == 200
    assert client.get("/api/settings").json()["auto_evaluate_top_n"] == 3


# ---------- secrets ----------


def test_secrets_presence_only_and_never_echoed(client, fakes, caplog):
    assert client.get("/api/secrets").json() == [
        {"name": "gmail_address", "present": False}, {"name": "gmail_app_password", "present": False}]
    with caplog.at_level("DEBUG"):
        r = client.put("/api/secrets/gmail_app_password", json={"value": "s3cr3t-pass"})
    assert r.status_code == 204 and r.content == b""
    assert fakes.keyring.store == {("jobhunter", "gmail_app_password"): "s3cr3t-pass"}
    listing = client.get("/api/secrets")
    assert listing.json() == [
        {"name": "gmail_address", "present": False}, {"name": "gmail_app_password", "present": True}]
    assert "s3cr3t-pass" not in listing.text and "s3cr3t-pass" not in caplog.text
    assert client.put("/api/secrets/other", json={"value": "x"}).status_code == 404
    assert client.put("/api/secrets/gmail_address", json={"value": ""}).status_code == 422


def test_keychain_failure_is_503_without_leaking(client, fakes, monkeypatch):
    from keyring.errors import KeyringError

    def boom(*a):
        raise KeyringError("locked: s3cr3t")

    monkeypatch.setattr(fakes.keyring, "set_password", boom)
    r = client.put("/api/secrets/gmail_address", json={"value": "me@example.com"})
    assert r.status_code == 503 and "s3cr3t" not in r.text and "me@example.com" not in r.text


# ---------- profiles ----------


def test_profiles_seed_and_refresh_due(client, db):
    rows = client.get("/api/profiles").json()
    assert [r["platform"] for r in rows] == [
        "naukri", "linkedin", "instahyre", "hirist", "cutshort", "wellfound", "uplers", "foundit", "turing", "arc"]
    naukri = rows[0]
    assert naukri["edit_url"] == "https://www.naukri.com/mnjuser/profile"
    assert (naukri["refresh_every_days"], naukri["refresh_due"]) == (1, True)
    assert all(r["refresh_due"] is False and r["refresh_every_days"] is None for r in rows[1:])
    assert rows[1]["checklist"] == {"created": False, "alerts_on": False, "cv_uploaded": False}
    assert len(client.get("/api/profiles").json()) == 10  # seeded once


def test_profile_patch_checklist_and_refresh(client, db):
    client.get("/api/profiles")
    out = client.patch("/api/profiles/linkedin", json={"checklist": {"created": True}}).json()
    assert out["checklist"] == {"created": True, "alerts_on": False, "cv_uploaded": False}
    done = client.patch("/api/profiles/naukri", json={"refreshed_now": True}).json()
    assert done["refresh_due"] is False and done["last_refreshed_at"] is not None
    row = db.get(Profile, "naukri")
    row.last_refreshed_at = utcnow() - timedelta(days=2)
    db.add(row)
    db.commit()
    assert next(r for r in client.get("/api/profiles").json() if r["platform"] == "naukri")["refresh_due"] is True
    assert client.patch("/api/profiles/nope", json={}).status_code == 404


# ---------- setup ----------


def test_setup_status_and_cv_upload(client, fakes):
    s = client.get("/api/setup").json()
    assert s == {"cv_a": False, "cv_b": False, "gmail": False, "claude_cli": True, "careerops": True,
                 "playwright": False, "complete": False}
    md = "# Jane Doe\n\n" + "Java engineer with Spring Boot experience. " * 3
    s = client.put("/api/setup/cv", json={"variant": "A", "markdown": md}).json()
    assert s["cv_a"] is True and s["cv_b"] is False and s["complete"] is True
    assert (paths.CV_DIR / "cv_a.md").read_text() == md
    assert (paths.CAREEROPS_DATA / "cv.md").read_text() == md  # copied: master was missing
    md2 = "# Variant B\n\n" + "Adds AI developer tooling work. " * 4
    s = client.put("/api/setup/cv", json={"variant": "B", "markdown": md2}).json()
    assert s["cv_b"] is True and (paths.CV_DIR / "cv_b.md").read_text() == md2
    assert (paths.CAREEROPS_DATA / "cv.md").read_text() == md  # B never touches the master
    md3 = "# Variant A v2\n\n" + "Rewritten for a better fit overall. " * 4
    client.put("/api/setup/cv", json={"variant": "A", "markdown": md3})
    assert (paths.CV_DIR / "cv_a.md").read_text() == md3
    assert (paths.CAREEROPS_DATA / "cv.md").read_text() == md  # existing master kept
    assert client.put("/api/setup/cv", json={"variant": "A", "markdown": "short"}).status_code == 422


def test_setup_gmail_needs_both_secrets_and_complete_needs_cli(client, fakes):
    keyring.set_password("jobhunter", "gmail_address", "me@example.com")
    assert client.get("/api/setup").json()["gmail"] is False
    keyring.set_password("jobhunter", "gmail_app_password", "pw")
    assert client.get("/api/setup").json()["gmail"] is True
    (paths.CV_DIR).mkdir(parents=True)
    (paths.CV_DIR / "cv_a.md").write_text("x")
    fakes.services[1].ok = False  # claude CLI missing
    s = client.get("/api/setup").json()
    assert s["cv_a"] is True and s["claude_cli"] is False and s["complete"] is False


# ---------- health + lifespan ----------


def test_health(client, fakes):
    body = client.get("/api/health").json()
    assert body["ok"] is True and body["db"] is True and body["scheduler"] is True
    assert [s["name"] for s in body["services"]][:2] == ["scheduler", "claude CLI"]


def test_health_survives_probe_failure(client, monkeypatch):
    from jobhunter.jobs import scheduler

    monkeypatch.setattr(scheduler, "services", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    body = client.get("/api/health").json()
    assert body["ok"] is True and body["scheduler"] is False and body["services"] == []


def test_lifespan_starts_and_stops_background_work(app, fakes, monkeypatch):
    monkeypatch.delenv("JOBHUNTER_NO_SCHEDULER")
    with TestClient(app):
        assert fakes.lifecycle == ["scheduler.start"]
    assert fakes.lifecycle == ["scheduler.start", "scheduler.shutdown", "runner.shutdown"]


def test_lifespan_skipped_with_env(app, fakes, monkeypatch):
    monkeypatch.setenv("JOBHUNTER_NO_SCHEDULER", "1")
    with TestClient(app):
        pass
    assert fakes.lifecycle == []


def test_spa_mount_still_serves(tmp_path, monkeypatch, fakes):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>spa</html>")
    (dist / "assets" / "a.js").write_text("1")
    monkeypatch.setattr(paths, "WEB_DIST", dist)
    with TestClient(create_app()) as c:
        assert c.get("/leads/42").text == "<html>spa</html>"
        assert c.get("/assets/a.js").text == "1"
        assert c.get("/api/openapi.json").status_code == 200


# ---------- gmail-test ----------


def stub_login(monkeypatch, result):
    calls = []

    def check_login(address, app_password):
        calls.append((address, app_password))
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(gmail, "check_login", check_login)
    return calls


def test_gmail_test_without_secrets_never_calls_gmail(client, fakes, monkeypatch):
    calls = stub_login(monkeypatch, None)
    assert client.post("/api/setup/gmail-test").json() == {"ok": False, "detail": "Gmail address and app password not set"}
    keyring.set_password("jobhunter", "gmail_address", "me@example.com")
    assert client.post("/api/setup/gmail-test").json() == {"ok": False, "detail": "Gmail app password not set"}
    keyring.delete_password("jobhunter", "gmail_address")
    keyring.set_password("jobhunter", "gmail_app_password", "pw")
    assert client.post("/api/setup/gmail-test").json() == {"ok": False, "detail": "Gmail address not set"}
    assert calls == []


def test_gmail_test_success_passes_keychain_secrets_and_never_echoes_the_password(client, fakes, monkeypatch):
    keyring.set_password("jobhunter", "gmail_address", "me@example.com")
    keyring.set_password("jobhunter", "gmail_app_password", "s3cr3t-app-pass")
    calls = stub_login(monkeypatch, None)
    r = client.post("/api/setup/gmail-test")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert calls == [("me@example.com", "s3cr3t-app-pass")]
    assert "s3cr3t-app-pass" not in r.text


def test_gmail_test_failure_reason_is_returned_as_ok_false(client, fakes, monkeypatch):
    keyring.set_password("jobhunter", "gmail_address", "me@example.com")
    keyring.set_password("jobhunter", "gmail_app_password", "s3cr3t-app-pass")
    stub_login(monkeypatch, "Gmail rejected the app password")
    r = client.post("/api/setup/gmail-test")
    assert r.json() == {"ok": False, "detail": "Gmail rejected the app password"}
    stub_login(monkeypatch, "server said: bad s3cr3t-app-pass")
    assert "s3cr3t-app-pass" not in client.post("/api/setup/gmail-test").text


def test_gmail_test_survives_a_crashing_check_without_leaking(client, fakes, monkeypatch, caplog):
    keyring.set_password("jobhunter", "gmail_address", "me@example.com")
    keyring.set_password("jobhunter", "gmail_app_password", "s3cr3t-app-pass")
    stub_login(monkeypatch, OSError("connection to s3cr3t-app-pass failed"))
    r = client.post("/api/setup/gmail-test")
    assert r.status_code == 200 and r.json() == {"ok": False, "detail": "Gmail login check failed (OSError)"}
    assert "s3cr3t-app-pass" not in r.text + caplog.text


def test_gmail_test_keychain_failure_is_503(client, fakes, monkeypatch):
    from keyring.errors import KeyringError

    def boom(*a):
        raise KeyringError("locked")

    monkeypatch.setattr(secrets, "get", boom)
    assert client.post("/api/setup/gmail-test").status_code == 503
