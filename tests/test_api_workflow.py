"""Applications (transitions, patch, events, cv.pdf, CSV), proposals and outreach."""

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest
from apihelpers import make_app, make_eval, make_event, make_lead
from sqlmodel import select

from jobhunter import paths
from jobhunter.api.deps import LOCAL_TZ, add_weekdays, week_start
from jobhunter.models import (
    Actor,
    Application,
    AppStatus,
    Event,
    Outreach,
    OutreachKind,
    Proposal,
    ProposalState,
    ProposalType,
    ResumeVariant,
    utcnow,
)

pytest_plugins = ["apihelpers"]


def post_transition(client, app_id, to, **kw):
    return client.post(f"/api/applications/{app_id}/transition", json={"to_status": to, **kw})


def events_of(db, app):
    db.expire_all()
    return list(db.exec(select(Event).where(Event.application_id == app.id).order_by(Event.id)))


# ---------- list / get / patch ----------


def test_list_get_and_filters(client, db):
    a = make_lead(db, company="Acme Corp", title="Backend")
    b = make_lead(db, company="Globex", title="SDE 2")
    app_a = make_app(db, a, AppStatus.applied)
    make_app(db, b, AppStatus.shortlisted)
    make_eval(db, a, 4.2)
    rows = client.get("/api/applications").json()
    assert {r["company"] for r in rows} == {"Acme Corp", "Globex"}
    assert [r["id"] for r in client.get("/api/applications", params={"status": "Applied"}).json()] == [app_a.id]
    assert [r["company"] for r in client.get("/api/applications", params={"q": "glob"}).json()] == ["Globex"]
    one = client.get(f"/api/applications/{app_a.id}").json()
    assert (one["eval_score"], one["source"], one["has_cv_pdf"]) == (4.2, "naukri", False)
    assert client.get("/api/applications/999").status_code == 404
    assert client.get(f"/api/applications/{10**30}").status_code == 404


def test_patch_fields_and_clearing(client, db):
    app = make_app(db, make_lead(db), AppStatus.applied, notes="old", recruiter="R")
    before = app.updated_at
    r = client.patch(f"/api/applications/{app.id}", json={
        "notes": "hello", "resume_variant": "B", "referral_contact": "Sam", "recruiter": None,
        "next_follow_up_at": "2026-12-01T10:00:00Z"})
    body = r.json()
    assert (body["notes"], body["resume_variant"], body["referral_contact"], body["recruiter"]) == (
        "hello", "B", "Sam", None)
    assert body["next_follow_up_at"].startswith("2026-12-01T10:00:00")
    assert body["status"] == "Applied" and body["updated_at"] > before.isoformat()[:19]
    assert client.patch(f"/api/applications/{app.id}", json={"next_follow_up_at": None}).json()[
        "next_follow_up_at"] is None
    assert client.patch("/api/applications/999", json={}).status_code == 404


def test_cv_approved_moves_shortlisted_to_ready(client, db):
    app = make_app(db, make_lead(db), AppStatus.shortlisted, cv_pdf_path="cv/x.pdf")
    body = client.patch(f"/api/applications/{app.id}", json={"cv_approved": True}).json()
    assert body["status"] == "Ready" and body["cv_approved"] is True
    ev = events_of(db, app)[0]
    assert (ev.from_status, ev.to_status, ev.actor) == (AppStatus.shortlisted, AppStatus.ready, Actor.owner)


def test_cv_approved_on_other_status_only_sets_flag(client, db):
    app = make_app(db, make_lead(db), AppStatus.new)
    body = client.patch(f"/api/applications/{app.id}", json={"cv_approved": True}).json()
    assert body["status"] == "New" and body["cv_approved"] is True and events_of(db, app) == []
    assert client.patch(f"/api/applications/{app.id}", json={"cv_approved": False}).json()["cv_approved"] is False


# ---------- transitions ----------


def test_plain_transition_writes_event_and_bumps_updated_at(client, db):
    app = make_app(db, make_lead(db), AppStatus.applied)
    before = app.updated_at
    body = post_transition(client, app.id, "Screening", note="HR call").json()
    assert body["status"] == "Screening"
    (ev,) = events_of(db, app)
    assert (ev.from_status, ev.to_status, ev.note, ev.actor) == (
        AppStatus.applied, AppStatus.screening, "HR call", Actor.owner)
    db.refresh(app)
    assert app.updated_at.replace(tzinfo=None) > before.replace(tzinfo=None)


@pytest.mark.parametrize(("start", "to"), [
    (AppStatus.new, AppStatus.screening), (AppStatus.shortlisted, AppStatus.screening),
    (AppStatus.applied, AppStatus.offer), (AppStatus.skipped, AppStatus.shortlisted),
    (AppStatus.rejected, AppStatus.applied), (AppStatus.ready, AppStatus.shortlisted),
    (AppStatus.applied, AppStatus.applied), (AppStatus.offer, AppStatus.rejected),
    (AppStatus.technical, AppStatus.screening),
])
def test_illegal_transitions_are_409_and_change_nothing(client, db, start, to):
    app = make_app(db, make_lead(db), start)
    r = post_transition(client, app.id, to.value, rejected_at_stage="Screening")
    assert r.status_code == 409 and "cannot move" in r.json()["detail"]
    assert events_of(db, app) == []
    db.refresh(app)
    assert app.status == start


def test_every_legal_transition_is_accepted(client, db):
    from jobhunter.models import TRANSITIONS

    for start, targets in TRANSITIONS.items():
        for to in targets:
            app = make_app(db, make_lead(db), start)
            r = post_transition(client, app.id, to.value, rejected_at_stage="Applied")
            assert r.status_code == 200, (start, to, r.text)
            assert r.json()["status"] == to.value


@pytest.mark.parametrize("start", [AppStatus.new, AppStatus.shortlisted, AppStatus.ready])
def test_applied_walks_the_main_line(client, db, start):
    app = make_app(db, make_lead(db), start)
    body = post_transition(client, app.id, "Applied", note="submitted").json()
    assert body["status"] == "Applied"
    line = [AppStatus.new, AppStatus.shortlisted, AppStatus.ready, AppStatus.applied]
    expected = line[line.index(start) + 1 :]
    evs = events_of(db, app)
    assert [e.to_status for e in evs] == expected
    assert [e.from_status for e in evs] == line[line.index(start) : -1]
    for e in evs[:-1]:
        assert (e.actor, e.note) == (Actor.system, "quick apply")
    assert (evs[-1].actor, evs[-1].note) == (Actor.owner, "submitted")
    assert body["applied_at"] is not None


def test_applied_sets_follow_up_five_weekdays_out(client, db):
    app = make_app(db, make_lead(db), AppStatus.ready)
    body = post_transition(client, app.id, "Applied").json()
    applied, due = (datetime.fromisoformat(body[k]) for k in ("applied_at", "next_follow_up_at"))
    assert due.astimezone(LOCAL_TZ).weekday() < 5
    assert timedelta(days=5) <= due - applied <= timedelta(days=7)
    assert due == add_weekdays(applied, 5)


def test_add_weekdays_skips_weekends():
    ist = lambda *a: datetime(*a, tzinfo=LOCAL_TZ)
    assert add_weekdays(ist(2026, 11, 13, 10), 5) == ist(2026, 11, 20, 10)  # Fri -> next Fri
    assert add_weekdays(ist(2026, 11, 9, 10), 5) == ist(2026, 11, 16, 10)  # Mon -> next Mon
    assert add_weekdays(ist(2026, 11, 14, 10), 1) == ist(2026, 11, 16, 10)  # Sat -> Mon
    assert add_weekdays(ist(2026, 11, 12, 10), 3) == ist(2026, 11, 17, 10)  # Thu -> Tue


def test_week_start_is_monday_midnight_ist():
    now = datetime(2026, 11, 12, 20, 0, tzinfo=UTC)  # Thu 13 Nov 01:30 IST
    assert week_start(now) == datetime(2026, 11, 8, 18, 30, tzinfo=UTC)  # Mon 9 Nov 00:00 IST
    assert week_start(now, 1) == datetime(2026, 11, 1, 18, 30, tzinfo=UTC)
    sunday_late = datetime(2026, 11, 15, 18, 0, tzinfo=UTC)  # Sun 23:30 IST: still the same week
    assert week_start(sunday_late) == datetime(2026, 11, 8, 18, 30, tzinfo=UTC)
    assert week_start(datetime(2026, 11, 15, 18, 30, tzinfo=UTC)) == datetime(2026, 11, 15, 18, 30, tzinfo=UTC)


def test_rejected_needs_stage(client, db):
    app = make_app(db, make_lead(db), AppStatus.screening)
    assert post_transition(client, app.id, "Rejected").status_code == 422
    assert events_of(db, app) == []
    body = post_transition(client, app.id, "Rejected", rejected_at_stage="Screening").json()
    assert body["status"] == "Rejected" and body["rejected_at_stage"] == "Screening"
    assert [e.to_status for e in events_of(db, app)] == [AppStatus.rejected]


def test_transition_validation_and_404(client, db):
    app = make_app(db, make_lead(db), AppStatus.new)
    assert post_transition(client, app.id, "Nonsense").status_code == 422
    assert post_transition(client, 999, "Skipped").status_code == 404


def test_events_endpoint(client, db):
    app = make_app(db, make_lead(db), AppStatus.new)
    post_transition(client, app.id, "Shortlisted")
    post_transition(client, app.id, "Skipped", note="no")
    evs = client.get(f"/api/applications/{app.id}/events").json()
    assert [e["to_status"] for e in evs] == ["Shortlisted", "Skipped"]
    assert client.get("/api/applications/999/events").status_code == 404


# ---------- cv.pdf ----------


def test_cv_pdf(client, db, tmp_path):
    none = make_app(db, make_lead(db), AppStatus.shortlisted)
    assert client.get(f"/api/applications/{none.id}/cv.pdf").status_code == 404
    missing = make_app(db, make_lead(db), AppStatus.shortlisted, cv_pdf_path="careerops/output/nope.pdf")
    assert client.get(f"/api/applications/{missing.id}/cv.pdf").status_code == 404
    (paths.CAREEROPS_DATA / "output").mkdir(parents=True)
    (paths.CAREEROPS_DATA / "output" / "cv.pdf").write_bytes(b"%PDF-1.4 fake")
    ok = make_app(db, make_lead(db), AppStatus.shortlisted, cv_pdf_path="careerops/output/cv.pdf")
    r = client.get(f"/api/applications/{ok.id}/cv.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content == b"%PDF-1.4 fake"
    secret = tmp_path.parent / "outside.pdf"
    secret.write_bytes(b"secret")
    evil = make_app(db, make_lead(db), AppStatus.shortlisted, cv_pdf_path=f"../{secret.name}")
    assert client.get(f"/api/applications/{evil.id}/cv.pdf").status_code == 404


# ---------- CSV ----------


def test_csv_export(client, db):
    lead = make_lead(db, company="=cmd|' /C calc'!A0", title="Dev, Senior", location="Chennai")
    app = make_app(db, lead, AppStatus.applied, resume_variant=ResumeVariant.b, notes="line1\nline2")
    make_eval(db, lead, 3.9)
    make_app(db, make_lead(db, company="Other"), AppStatus.shortlisted)
    r = client.get("/api/applications/export.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 2
    mine = next(x for x in rows if x["application_id"] == str(app.id))
    assert mine["title"] == "Dev, Senior" and mine["status"] == "Applied" and mine["resume_variant"] == "B"
    assert mine["eval_score"] == "3.9" and mine["source"] == "naukri" and mine["location"] == "Chennai"
    assert mine["company"].startswith("'=")  # formula neutralised
    assert mine["notes"] == "line1\nline2"
    assert client.get("/api/applications/export.csv").text.splitlines()[0].startswith("application_id,lead_id")


# ---------- proposals ----------


def make_proposal(db, **kw):
    p = Proposal(type=kw.pop("type", ProposalType.status_change), **kw)
    db.add(p)
    db.commit()
    return p


def test_list_proposals_by_state(client, db):
    lead = make_lead(db, company="Acme", title="Dev")
    app = make_app(db, lead, AppStatus.applied)
    pending = make_proposal(db, application_id=app.id, payload={"to_status": "Screening"}, evidence="call?",
                            confidence=0.9)
    make_proposal(db, state=ProposalState.dismissed)
    rows = client.get("/api/proposals").json()
    assert [r["id"] for r in rows] == [pending.id]
    assert (rows[0]["company"], rows[0]["title"], rows[0]["confidence"]) == ("Acme", "Dev", 0.9)
    assert len(client.get("/api/proposals", params={"state": "dismissed"}).json()) == 1
    assert client.get("/api/proposals", params={"state": "bogus"}).status_code == 422


def test_accept_status_change_applies_payload(client, db):
    app = make_app(db, make_lead(db), AppStatus.applied)
    p = make_proposal(db, application_id=app.id, payload={"to_status": "Screening"})
    out = client.post(f"/api/proposals/{p.id}/accept", json={}).json()
    assert out["state"] == "accepted"
    db.refresh(app)
    assert app.status == AppStatus.screening
    (ev,) = events_of(db, app)
    assert (ev.actor, ev.to_status) == (Actor.proposal, AppStatus.screening)
    db.refresh(p)
    assert p.decided_at is not None


def test_accept_with_owner_edit_and_rejection_stage(client, db):
    app = make_app(db, make_lead(db), AppStatus.screening)
    p = make_proposal(db, application_id=app.id, payload={"to_status": "Technical"})
    body = {"payload": {"to_status": "Rejected", "rejected_at_stage": "Screening"}}
    out = client.post(f"/api/proposals/{p.id}/accept", json=body).json()
    assert out["payload"]["to_status"] == "Rejected"
    db.refresh(app)
    assert (app.status, app.rejected_at_stage) == (AppStatus.rejected, AppStatus.screening)


def test_accept_illegal_or_invalid_leaves_proposal_pending(client, db):
    app = make_app(db, make_lead(db), AppStatus.new)
    p = make_proposal(db, application_id=app.id, payload={"to_status": "Offer"})
    assert client.post(f"/api/proposals/{p.id}/accept", json={}).status_code == 409
    bad = make_proposal(db, application_id=app.id, payload={"to_status": "Banana"})
    assert client.post(f"/api/proposals/{bad.id}/accept", json={}).status_code == 422
    noreject = make_proposal(db, application_id=make_app(db, make_lead(db), AppStatus.applied).id,
                             payload={"to_status": "Rejected"})
    assert client.post(f"/api/proposals/{noreject.id}/accept", json={}).status_code == 422
    db.expire_all()
    assert {x.state for x in db.exec(select(Proposal)).all()} == {ProposalState.pending}


def test_accept_ghosted_defaults_to_ghosted(client, db):
    app = make_app(db, make_lead(db), AppStatus.applied)
    p = make_proposal(db, type=ProposalType.ghosted, application_id=app.id)
    assert client.post(f"/api/proposals/{p.id}/accept", json={}).status_code == 200
    db.refresh(app)
    assert app.status == AppStatus.ghosted


def test_accept_status_change_to_applied_walks_main_line(client, db):
    lead = make_lead(db)
    p = make_proposal(db, lead_id=lead.id, payload={"to_status": "Applied"})  # no application yet
    assert client.post(f"/api/proposals/{p.id}/accept", json={}).status_code == 200
    app = db.exec(select(Application)).one()
    assert app.status == AppStatus.applied
    assert [e.to_status for e in events_of(db, app)] == [AppStatus.shortlisted, AppStatus.ready, AppStatus.applied]
    assert {e.actor for e in events_of(db, app)[:2]} == {Actor.system}
    assert events_of(db, app)[2].actor == Actor.proposal


def test_dismiss_and_double_decision(client, db):
    p = make_proposal(db, payload={})
    assert client.post(f"/api/proposals/{p.id}/dismiss").json()["state"] == "dismissed"
    assert client.post(f"/api/proposals/{p.id}/dismiss").status_code == 409
    assert client.post(f"/api/proposals/{p.id}/accept", json={}).status_code == 409
    assert client.post("/api/proposals/999/dismiss").status_code == 404
    assert client.post("/api/proposals/999/accept", json={}).status_code == 404
    assert client.post("/api/proposals/999/convert").status_code == 404


def test_convert_inbound_creates_shortlisted_application(client, db):
    lead = make_lead(db, is_inbound=True)
    p = make_proposal(db, type=ProposalType.inbound, lead_id=lead.id, evidence="Hi from recruiter")
    body = client.post(f"/api/proposals/{p.id}/convert").json()
    assert body["status"] == "Shortlisted" and body["lead_id"] == lead.id
    db.refresh(p)
    assert p.state == ProposalState.accepted and p.decided_at is not None
    assert client.post(f"/api/proposals/{p.id}/convert").status_code == 409


def test_convert_rejects_other_types_and_leadless(client, db):
    other = make_proposal(db, lead_id=make_lead(db).id)
    assert client.post(f"/api/proposals/{other.id}/convert").status_code == 409
    leadless = make_proposal(db, type=ProposalType.inbound)
    assert client.post(f"/api/proposals/{leadless.id}/convert").status_code == 422


# ---------- outreach ----------


def make_outreach(db, **kw):
    kw.setdefault("kind", OutreachKind.referral)
    row = Outreach(**kw)
    db.add(row)
    db.commit()
    return row


def test_outreach_filters(client, db):
    now = utcnow()
    lead = make_lead(db, company="Acme", title="Dev")
    due = make_outreach(db, lead_id=lead.id, due_at=now - timedelta(days=1))
    future = make_outreach(db, due_at=now + timedelta(days=2))
    snoozed = make_outreach(db, due_at=now - timedelta(days=3), snoozed_until=now + timedelta(days=1))
    woke = make_outreach(db, due_at=now - timedelta(days=3), snoozed_until=now - timedelta(hours=1))
    sent = make_outreach(db, due_at=now - timedelta(days=3), sent_at=now)
    follow = make_outreach(db, kind=OutreachKind.follow_up, due_at=now - timedelta(days=2))
    nodue = make_outreach(db)

    def got(**params):
        return [r["id"] for r in client.get("/api/outreach", params=params).json()]

    assert got(due_only=True) == [woke.id, follow.id, due.id]  # oldest due first
    assert got(due_only=True, kind="follow_up") == [follow.id]
    assert got(sent=True) == [sent.id]
    assert sorted(got(sent=False)) == sorted([due.id, future.id, snoozed.id, woke.id, follow.id, nodue.id])
    assert sorted(got(kind="referral")) == sorted([due.id, future.id, snoozed.id, woke.id, sent.id, nodue.id])
    first = client.get("/api/outreach", params={"kind": "referral", "sent": False}).json()
    assert first[0]["due_at"] is not None and first[-1]["id"] == nodue.id  # null due_at sorts last
    assert next(r for r in client.get("/api/outreach").json() if r["id"] == due.id)["company"] == "Acme"


def test_outreach_patch_mark_sent_snooze(client, db):
    row = make_outreach(db, contact="Old", draft="Hi")
    out = client.patch(f"/api/outreach/{row.id}", json={"draft": "Hello there"}).json()
    assert (out["contact"], out["draft"]) == ("Old", "Hello there")
    assert client.patch(f"/api/outreach/{row.id}", json={"contact": "New"}).json()["contact"] == "New"
    sent = client.post(f"/api/outreach/{row.id}/mark-sent").json()
    assert sent["sent_at"] is not None
    again = client.post(f"/api/outreach/{row.id}/mark-sent").json()
    assert again["sent_at"] == sent["sent_at"]
    other = make_outreach(db)
    snoozed = client.post(f"/api/outreach/{other.id}/snooze", json={"days": 3}).json()
    until = datetime.fromisoformat(snoozed["snoozed_until"])
    assert timedelta(days=2, hours=23) < until - utcnow() < timedelta(days=3, minutes=1)
    assert client.post(f"/api/outreach/{other.id}/snooze", json={"days": 0}).status_code == 422
    assert client.post(f"/api/outreach/{other.id}/snooze", json={"days": 31}).status_code == 422
    for path in ("mark-sent", "snooze"):
        r = client.post(f"/api/outreach/999/{path}", json={"days": 1})
        assert r.status_code == 404
    assert client.patch("/api/outreach/999", json={}).status_code == 404


def test_make_event_helper_is_used(db):
    app = make_app(db, make_lead(db), AppStatus.applied)
    make_event(db, app, AppStatus.applied)
    assert len(events_of(db, app)) == 1
