"""Today aggregation and analytics."""

from datetime import timedelta

from apihelpers import make_app, make_eval, make_lead
from sqlmodel import Session

from jobhunter.api.deps import week_start
from jobhunter.models import (
    Actor,
    ApplyChannel,
    AppStatus,
    Event,
    Outreach,
    OutreachKind,
    Proposal,
    ProposalState,
    ProposalType,
    ResumeVariant,
    RoleFamily,
    Source,
    utcnow,
)

pytest_plugins = ["apihelpers"]


def add_event(db: Session, app, to: AppStatus, at):
    db.add(Event(application_id=app.id, to_status=to, at=at, actor=Actor.owner))
    db.commit()


def this_week():
    return week_start(utcnow()) + timedelta(seconds=1)


def last_week():
    return week_start(utcnow(), 1) + timedelta(hours=1)


# ---------- today ----------


def test_today_counters(client, db):
    app = make_app(db, make_lead(db), AppStatus.applied)
    for _ in range(2):
        add_event(db, app, AppStatus.screening, this_week())
    add_event(db, app, AppStatus.screening, last_week())
    add_event(db, app, AppStatus.screening, last_week() - timedelta(weeks=3))
    for _ in range(3):
        add_event(db, app, AppStatus.applied, this_week())
    add_event(db, app, AppStatus.applied, last_week())
    for kind, at in [(OutreachKind.referral, this_week()), (OutreachKind.referral, this_week()),
                     (OutreachKind.referral, last_week()), (OutreachKind.follow_up, this_week())]:
        db.add(Outreach(kind=kind, sent_at=at))
    db.add(Outreach(kind=OutreachKind.referral))  # unsent
    db.commit()
    body = client.get("/api/today").json()
    assert body["interview_calls_week"] == 2 and body["interview_calls_prev_week"] == 1
    assert body["applied_week"] == 3 and body["applied_target"] == 60
    assert body["referrals_week"] == 2 and body["referrals_target"] == 15


def test_today_fresh_hot_leads(client, db):
    now = utcnow()
    best = make_lead(db, quick_score=0.3, company="BestEval")
    make_eval(db, best, 4.6)
    high = make_lead(db, quick_score=0.9, company="HighQuick")
    low = make_lead(db, quick_score=0.6, company="LowQuick")
    make_lead(db, quick_score=0.99, posted_at=now - timedelta(days=5))  # not fresh
    make_app(db, make_lead(db, quick_score=0.95), AppStatus.shortlisted)  # not New
    make_lead(db, quick_score=0.95, prefilter_pass=False)  # dropped
    make_lead(db, quick_score=0.95, dedupe_group="dup-of-high")
    second = make_lead(db, quick_score=0.95, dedupe_group="dup-of-high")
    assert second.id  # non-primary member stays out
    body = client.get("/api/today").json()
    ids = [x["id"] for x in body["fresh_hot_leads"]]
    assert ids[0] == best.id  # evaluated first, then by quick score
    assert ids.index(high.id) < ids.index(low.id)
    assert second.id not in ids
    assert all(x["is_fresh"] and x["status"] == "New" and x["prefilter_pass"] for x in body["fresh_hot_leads"])


def test_today_hot_leads_capped_at_ten(client, db):
    for _ in range(13):
        make_lead(db)
    assert len(client.get("/api/today").json()["fresh_hot_leads"]) == 10


def test_today_actions_in_order(client, db, fakes):
    now = utcnow()
    inbound_lead = make_lead(db, company="Recruiter Co", title="SDE", is_inbound=True)
    db.add(Proposal(type=ProposalType.inbound, lead_id=inbound_lead.id, evidence="Hi, role at RC"))
    reply_app = make_app(db, make_lead(db, company="Replier"), AppStatus.applied)
    db.add(Proposal(type=ProposalType.status_change, application_id=reply_app.id, payload={"to_status": "Screening"},
                    evidence="invite"))
    db.add(Proposal(type=ProposalType.inbound, state=ProposalState.dismissed))
    due_lead = make_lead(db, company="DueCo")
    due_app = make_app(db, due_lead, AppStatus.applied, next_follow_up_at=now - timedelta(days=1))
    day = timedelta(days=1)
    # only an unsent, unsnoozed, due follow-up on a still-Applied application is an action
    db.add(Outreach(kind=OutreachKind.follow_up, application_id=due_app.id, lead_id=due_lead.id, due_at=now - day))
    not_due = make_app(db, make_lead(db), AppStatus.applied)
    db.add(Outreach(kind=OutreachKind.follow_up, application_id=not_due.id, due_at=now + 2 * day))
    sent = make_app(db, make_lead(db), AppStatus.applied)
    db.add(Outreach(kind=OutreachKind.follow_up, application_id=sent.id, due_at=now - day, sent_at=now))
    snoozed = make_app(db, make_lead(db), AppStatus.applied)
    db.add(Outreach(kind=OutreachKind.follow_up, application_id=snoozed.id, due_at=now - day,
                    snoozed_until=now + day))
    closed = make_app(db, make_lead(db), AppStatus.rejected)
    db.add(Outreach(kind=OutreachKind.follow_up, application_id=closed.id, due_at=now - day))
    make_app(db, make_lead(db), AppStatus.applied, next_follow_up_at=now - day)  # due, but run() has not drafted it
    cv_lead = make_lead(db, company="CvCo", title="Dev")
    make_app(db, cv_lead, AppStatus.shortlisted, cv_pdf_path="x.pdf", resume_variant=ResumeVariant.a)
    make_app(db, make_lead(db), AppStatus.applied, cv_pdf_path="y.pdf")  # applied without approval: no review
    make_app(db, make_lead(db, apply_channel=ApplyChannel.platform_quick), AppStatus.shortlisted)
    make_app(db, make_lead(db, apply_channel=ApplyChannel.platform_quick), AppStatus.ready)
    db.add(Outreach(kind=OutreachKind.referral, draft="Hi Sam", contact="Sam", lead_id=due_lead.id))
    db.add(Outreach(kind=OutreachKind.referral, sent_at=now, draft="done"))  # sent: not an action
    db.commit()

    body = client.get("/api/today").json()
    kinds = [a["kind"] for a in body["actions"]]
    assert kinds == ["inbound", "proposal", "follow_up", "cv_review", "quick_apply", "referral", "profile_refresh"]
    by_kind = {a["kind"]: a for a in body["actions"]}
    assert by_kind["inbound"]["title"] == "Recruiter Co — SDE" and by_kind["inbound"]["lead_id"] == inbound_lead.id
    assert by_kind["inbound"]["proposal_id"] is not None and by_kind["inbound"]["subtitle"] == "Hi, role at RC"
    assert "Replier" in by_kind["proposal"]["title"] and by_kind["proposal"]["application_id"] == reply_app.id
    assert [a["title"] for a in body["actions"] if a["kind"] == "follow_up"] == ["Follow up: DueCo"]
    assert by_kind["follow_up"]["due_at"] is not None and by_kind["follow_up"]["outreach_id"] is not None
    assert by_kind["follow_up"]["application_id"] == due_app.id
    assert by_kind["cv_review"]["title"] == "Approve CV for CvCo Dev"
    assert by_kind["quick_apply"]["title"].startswith("2 ")
    assert by_kind["referral"]["outreach_id"] is not None and by_kind["referral"]["subtitle"] == "Sam"
    assert by_kind["profile_refresh"]["platform"] == "naukri"
    assert [h["name"] for h in body["health"]] == [s.name for s in fakes.services]


def test_today_empty(client):
    body = client.get("/api/today").json()
    assert body["interview_calls_week"] == 0 and body["fresh_hot_leads"] == []
    assert [a["kind"] for a in body["actions"]] == ["profile_refresh"]  # naukri never refreshed


# ---------- analytics ----------


def seed_funnel(db):
    now = utcnow()
    a = make_app(db, make_lead(db, source=Source.linkedin, apply_channel=ApplyChannel.platform_quick,
                               title="Java Developer", role_family=RoleFamily.p1), AppStatus.screening,
                 resume_variant=ResumeVariant.a)
    b = make_app(db, make_lead(db, source=Source.naukri, title="Java  Developer", role_family=RoleFamily.p1),
                 AppStatus.applied, resume_variant=ResumeVariant.b)
    c = make_app(db, make_lead(db, source=Source.naukri, title="SDE 2"), AppStatus.skipped)
    d = make_app(db, make_lead(db, source=Source.linkedin, title="Platform Engineer"), AppStatus.applied)
    for app, steps in [(a, ["Shortlisted", "Ready", "Applied", "Screening"]), (b, ["Shortlisted", "Ready", "Applied"]),
                       (c, ["Shortlisted", "Skipped"]), (d, ["Shortlisted", "Ready", "Applied"])]:
        for i, s in enumerate(steps):
            add_event(db, app, AppStatus(s), now - timedelta(days=10 - i))
    return a, b, c, d


def test_funnel_counts_reached_status_with_conversion(client, db):
    seed_funnel(db)
    stages = {s["status"]: s for s in client.get("/api/analytics/funnel").json()["stages"]}
    assert [s for s in stages] == ["Shortlisted", "Ready", "Applied", "Screening", "Technical", "Final", "Offer",
                                   "Accepted"]
    assert [stages[k]["count"] for k in stages] == [4, 3, 3, 1, 0, 0, 0, 0]
    assert stages["Shortlisted"]["conversion_from_prev"] is None
    assert stages["Ready"]["conversion_from_prev"] == 0.75
    assert stages["Applied"]["conversion_from_prev"] == 1.0
    assert abs(stages["Screening"]["conversion_from_prev"] - 1 / 3) < 1e-9
    assert stages["Technical"]["conversion_from_prev"] == 0.0
    assert stages["Final"]["conversion_from_prev"] is None  # nothing to divide by


def test_funnel_date_range(client, db):
    seed_funnel(db)
    frm = (utcnow() - timedelta(days=7, hours=12)).isoformat()  # only the Screening event (7 d ago) is inside
    body = client.get("/api/analytics/funnel", params={"date_from": frm}).json()
    counts = {s["status"]: s["count"] for s in body["stages"]}
    assert counts["Shortlisted"] == 0 and counts["Applied"] == 0 and counts["Screening"] == 1
    assert body["date_from"] is not None and body["date_to"] is None


def test_breakdown_by_every_dimension(client, db):
    seed_funnel(db)

    def rows(by):
        data = client.get("/api/analytics/breakdown", params={"by": by}).json()
        assert data["by"] == by
        return {r["key"]: (r["applied"], r["calls"], r["rate"]) for r in data["rows"]}

    assert rows("source") == {"linkedin": (2, 1, 0.5), "naukri": (1, 0, 0.0)}
    assert rows("channel") == {"platform_quick": (1, 1, 1.0), "company_ats": (2, 0, 0.0)}
    assert rows("variant") == {"A": (1, 1, 1.0), "B": (1, 0, 0.0), "none": (1, 0, 0.0)}
    assert rows("role_family") == {"P1": (2, 1, 0.5), "other": (1, 0, 0.0)}
    assert rows("title")["Java Developer"] == (2, 1, 0.5)  # whitespace-normalised
    first = client.get("/api/analytics/breakdown", params={"by": "source"}).json()["rows"][0]
    assert first["key"] == "linkedin"  # most applied first
    assert client.get("/api/analytics/breakdown").status_code == 422
    assert client.get("/api/analytics/breakdown", params={"by": "colour"}).status_code == 422


def test_weekly_points(client, db):
    app = make_app(db, make_lead(db), AppStatus.applied)
    add_event(db, app, AppStatus.applied, this_week())
    add_event(db, app, AppStatus.applied, this_week())
    add_event(db, app, AppStatus.screening, last_week())
    db.add(Outreach(kind=OutreachKind.referral, sent_at=last_week()))
    db.commit()
    pts = client.get("/api/analytics/weekly", params={"weeks": 3}).json()
    assert len(pts) == 3
    starts = [p["week_start"] for p in pts]
    assert starts == sorted(starts)  # oldest first
    assert (pts[2]["applied"], pts[2]["calls"], pts[2]["referrals"]) == (2, 0, 0)
    assert (pts[1]["applied"], pts[1]["calls"], pts[1]["referrals"]) == (0, 1, 1)
    assert pts[0]["applied"] == 0 and pts[2]["applied_target"] == 60 and pts[2]["referrals_target"] == 15
    assert len(client.get("/api/analytics/weekly").json()) == 8
    assert len(client.get("/api/analytics/weekly", params={"weeks": 1000}).json()) == 52
    assert len(client.get("/api/analytics/weekly", params={"weeks": -4}).json()) == 1


def test_response_times(client, db):
    now = utcnow()
    for applied_days_ago, reply_days_ago in [(10, 8), (5, 1)]:
        app = make_app(db, make_lead(db), AppStatus.screening)
        add_event(db, app, AppStatus.applied, now - timedelta(days=applied_days_ago))
        add_event(db, app, AppStatus.screening, now - timedelta(days=reply_days_ago))
    silent = make_app(db, make_lead(db), AppStatus.applied)
    add_event(db, silent, AppStatus.applied, now - timedelta(days=3))
    body = client.get("/api/analytics/response-times").json()
    assert body["samples"] == 2
    assert body["median_days_to_first_response"] == 3.0 and body["p90_days_to_first_response"] == 4.0


def test_response_times_empty(client):
    assert client.get("/api/analytics/response-times").json() == {
        "median_days_to_first_response": None, "p90_days_to_first_response": None, "samples": 0}


def test_reject_audit(client, db):
    ids = [make_lead(db, prefilter_pass=False, prefilter_reasons=["exp_too_high"]).id for _ in range(7)]
    both = make_lead(db, prefilter_pass=False, prefilter_reasons=["ctc_low", "exp_too_high"])
    make_lead(db, prefilter_pass=False, prefilter_reasons=["ctc_low"])
    make_lead(db, prefilter_pass=True, restored=True, prefilter_reasons=["exp_too_high"])  # restored: not a drop
    make_lead(db, prefilter_pass=True)
    rows = client.get("/api/analytics/rejects").json()
    assert [(r["reason"], r["count"]) for r in rows] == [("exp_too_high", 8), ("ctc_low", 2)]
    assert len(rows[0]["sample_lead_ids"]) == 5
    assert rows[0]["sample_lead_ids"][0] == both.id  # newest first
    assert set(rows[0]["sample_lead_ids"]) <= {*ids, both.id}
    old = client.get("/api/analytics/rejects", params={"date_to": (utcnow() - timedelta(days=1)).isoformat()})
    assert old.json() == []


# ---------- insights route ----------


def test_insights_with_little_data_is_one_info_item(client):
    body = client.get("/api/analytics/insights").json()
    assert [(i["kind"], i["severity"]) for i in body] == [("pace", "info")]
    assert "5 more" in body[0]["text"]


def test_insights_with_data_and_days_window(client, db):
    for i in range(6):
        app = make_app(db, make_lead(db, source=Source.naukri), AppStatus.applied)
        add_event(db, app, AppStatus.applied, utcnow() - timedelta(days=40))
        if i < 3:
            add_event(db, app, AppStatus.screening, utcnow() - timedelta(days=38))
    assert [i["kind"] for i in client.get("/api/analytics/insights").json()] == ["pace"]  # outside 30 days
    wide = client.get("/api/analytics/insights", params={"days": 90}).json()
    kinds = {i["kind"]: i for i in wide}
    assert "best_source" in kinds and "Naukri: 3 calls from 6 applies (50%)" in kinds["best_source"]["text"]
    assert set(kinds["best_source"]) == {"kind", "text", "severity", "metric"}
    assert client.get("/api/analytics/insights", params={"days": 0}).status_code == 200  # clamped, not rejected
    assert client.get("/api/analytics/insights", params={"days": "x"}).status_code == 422
