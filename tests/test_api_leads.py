"""Leads routes: list rules, detail, shortlist/skip/restore, runs, manual lead, bulk."""

from datetime import timedelta

from apihelpers import make_app, make_eval, make_event, make_lead
from sqlmodel import select

from jobhunter.models import (
    Actor,
    Application,
    ApplyChannel,
    AppStatus,
    Event,
    Lead,
    Outreach,
    OutreachKind,
    RunKind,
    Source,
    utcnow,
)

pytest_plugins = ["apihelpers"]


def ids(response):
    assert response.status_code == 200, response.text
    return [i["id"] for i in response.json()["items"]]


# ---------- list ----------


def test_list_status_new_without_application_and_status_filter(client, db):
    a = make_lead(db)
    b = make_lead(db)
    c = make_lead(db)
    make_app(db, b, AppStatus.shortlisted)
    make_app(db, c, AppStatus.new)
    body = client.get("/api/leads").json()
    assert body["total"] == 3
    status = {i["id"]: i["status"] for i in body["items"]}
    assert status == {a.id: "New", b.id: "Shortlisted", c.id: "New"}
    assert {i["id"]: i["application_id"] for i in body["items"]}[a.id] is None
    assert sorted(ids(client.get("/api/leads", params={"status": "New"}))) == sorted([a.id, c.id])
    assert ids(client.get("/api/leads", params=[("status", "Shortlisted"), ("status", "Applied")])) == [b.id]


def test_list_hides_prefilter_drops_and_non_primary_duplicates(client, db):
    keep = make_lead(db)
    dropped = make_lead(db, prefilter_pass=False, prefilter_reasons=["exp"])
    restored = make_lead(db, prefilter_pass=True, restored=True)
    first = make_lead(db, dedupe_group="g1")
    second = make_lead(db, dedupe_group="g1", source=Source.linkedin)
    third = make_lead(db, dedupe_group="g1", source=Source.indeed)
    assert sorted(ids(client.get("/api/leads"))) == sorted([keep.id, restored.id, first.id])
    everything = client.get("/api/leads", params={"include_rejected": True, "include_duplicates": True}).json()
    assert everything["total"] == 6
    by_id = {i["id"]: i for i in everything["items"]}
    assert by_id[dropped.id]["prefilter_pass"] is False and by_id[dropped.id]["prefilter_reasons"] == ["exp"]
    assert by_id[first.id]["duplicates"] == 2 and by_id[third.id]["duplicates"] == 2
    assert by_id[keep.id]["duplicates"] == 0
    assert sorted(ids(client.get("/api/leads", params={"include_duplicates": True}))) == sorted(
        [keep.id, restored.id, first.id, second.id, third.id]
    )
    assert dropped.id in ids(client.get("/api/leads", params={"include_rejected": True}))


def test_list_sorts_nulls_last_and_paginates(client, db):
    now = utcnow()
    lo = make_lead(db, quick_score=0.2, posted_at=now - timedelta(days=3), found_at=now - timedelta(days=1))
    hi = make_lead(db, quick_score=0.9, posted_at=None, found_at=now - timedelta(days=5))
    mid = make_lead(db, quick_score=0.5, posted_at=now - timedelta(days=1), found_at=now - timedelta(days=9))
    make_eval(db, lo, 4.5)
    make_eval(db, mid, 3.0)
    make_eval(db, mid, 2.0)  # the latest evaluation wins
    assert ids(client.get("/api/leads")) == [hi.id, mid.id, lo.id]
    assert ids(client.get("/api/leads", params={"sort": "found_at"})) == [lo.id, hi.id, mid.id]
    assert ids(client.get("/api/leads", params={"sort": "posted_at"})) == [mid.id, lo.id, hi.id]  # null last
    assert ids(client.get("/api/leads", params={"sort": "eval_score"})) == [lo.id, mid.id, hi.id]  # null last
    page = client.get("/api/leads", params={"limit": 2, "offset": 1}).json()
    assert page["total"] == 3 and page["limit"] == 2 and page["offset"] == 1
    assert [i["id"] for i in page["items"]] == [mid.id, lo.id]


def test_list_filters(client, db):
    now = utcnow()
    fresh = make_lead(db, title="Spring Boot Engineer", company="Acme", posted_at=now - timedelta(hours=5))
    stale = make_lead(db, posted_at=now - timedelta(hours=60), found_at=now - timedelta(hours=1))
    found_only = make_lead(db, posted_at=None, found_at=now - timedelta(hours=10), source=Source.linkedin,
                           apply_channel=ApplyChannel.platform_quick, quick_score=0.9, is_inbound=True)
    jd = make_lead(db, jd_text="We use Keycloak heavily", posted_at=now - timedelta(days=10), quick_score=0.1)
    assert sorted(ids(client.get("/api/leads", params={"fresh_only": True}))) == sorted([fresh.id, found_only.id])
    assert ids(client.get("/api/leads", params={"q": "spring"})) == [fresh.id]
    assert ids(client.get("/api/leads", params={"q": "acme"})) == [fresh.id]
    assert ids(client.get("/api/leads", params={"q": "keycloak"})) == [jd.id]
    assert ids(client.get("/api/leads", params={"source": "linkedin"})) == [found_only.id]
    assert ids(client.get("/api/leads", params={"channel": "platform_quick"})) == [found_only.id]
    assert ids(client.get("/api/leads", params={"inbound_only": True})) == [found_only.id]
    assert sorted(ids(client.get("/api/leads", params={"min_score": 0.4}))) == sorted(
        [fresh.id, stale.id, found_only.id]
    )
    flags = {i["id"]: i["is_fresh"] for i in client.get("/api/leads").json()["items"]}
    assert flags == {fresh.id: True, stale.id: False, found_only.id: True, jd.id: False}


def test_list_summary_carries_evaluation(client, db):
    lead = make_lead(db)
    make_eval(db, lead, 3.7, "B", is_live=True)
    item = client.get("/api/leads").json()["items"][0]
    assert (item["eval_score"], item["eval_grade"], item["is_live"]) == (3.7, "B", True)
    assert item["found_at"].endswith(("Z", "+00:00"))  # aware UTC on the wire


def test_list_validation(client):
    assert client.get("/api/leads", params={"limit": 0}).status_code == 422
    assert client.get("/api/leads", params={"sort": "nope"}).status_code == 422
    assert client.get("/api/leads", params={"offset": 10**30}).status_code == 200


def test_quick_apply(client, db):
    ok1 = make_lead(db, apply_channel=ApplyChannel.platform_quick, quick_score=0.4)
    ok2 = make_lead(db, apply_channel=ApplyChannel.platform_quick, quick_score=0.8)
    make_app(db, ok1, AppStatus.shortlisted)
    make_app(db, ok2, AppStatus.ready)
    make_app(db, make_lead(db, apply_channel=ApplyChannel.platform_quick), AppStatus.applied)
    make_app(db, make_lead(db, apply_channel=ApplyChannel.company_ats), AppStatus.shortlisted)
    make_lead(db, apply_channel=ApplyChannel.platform_quick)  # New: not queued yet
    body = client.get("/api/leads/quick-apply").json()
    assert [i["id"] for i in body] == [ok2.id, ok1.id]
    assert client.get("/api/leads/quick-apply", params={"limit": 1}).json()[0]["id"] == ok2.id


# ---------- detail ----------


def test_detail_has_everything(client, db):
    lead = make_lead(db, jd_text="the JD", dedupe_group="g")
    twin = make_lead(db, dedupe_group="g")
    ev = make_eval(db, lead, 4.1, "A", is_live=True)
    app = make_app(db, lead, AppStatus.shortlisted)
    make_event(db, app, AppStatus.shortlisted)
    db.add_all([Outreach(lead_id=lead.id, kind=OutreachKind.referral, contact="Jo"),
                Outreach(application_id=app.id, kind=OutreachKind.follow_up)])
    db.commit()
    body = client.get(f"/api/leads/{lead.id}").json()
    assert body["jd_text"] == "the JD" and body["duplicate_ids"] == [twin.id]
    assert body["evaluation"]["report_md"] == f"# Report {ev.id}\n\nA-G"
    assert body["evaluation"]["grade"] == "A"
    assert body["application"]["status"] == "Shortlisted" and body["application"]["company"] == lead.company
    assert [e["to_status"] for e in body["events"]] == ["Shortlisted"]
    assert sorted(o["kind"] for o in body["outreach"]) == ["follow_up", "referral"]
    assert {o["company"] for o in body["outreach"]} == {lead.company}
    assert [o["kind"] for o in client.get(f"/api/leads/{lead.id}/outreach").json()].count("referral") == 1


def test_detail_survives_report_failure(client, db, monkeypatch):
    from jobhunter import careerops

    def boom(ev):
        raise NotImplementedError

    monkeypatch.setattr(careerops, "report_md", boom)
    lead = make_lead(db)
    make_eval(db, lead)
    body = client.get(f"/api/leads/{lead.id}").json()
    assert body["evaluation"]["report_md"] is None and body["evaluation"]["score"] == 4.0


def test_missing_lead_404s(client):
    for method, path, kw in [
        ("get", "/api/leads/999", {}), ("post", "/api/leads/999/shortlist", {}),
        ("post", "/api/leads/999/skip", {"json": {"reason": "x"}}), ("post", "/api/leads/999/restore", {}),
        ("post", "/api/leads/999/evaluate", {}), ("post", "/api/leads/999/verify", {}),
        ("post", "/api/leads/999/cv", {"json": {"variant": "A"}}), ("post", "/api/leads/999/assist-apply", {}),
        ("post", "/api/leads/999/contacts", {}), ("get", "/api/leads/999/outreach", {}),
        ("get", f"/api/leads/{10**30}", {}),
    ]:
        assert getattr(client, method)(path, **kw).status_code == 404, path


# ---------- shortlist / skip / restore ----------


def test_shortlist_creates_application_and_event(client, db):
    lead = make_lead(db)
    body = client.post(f"/api/leads/{lead.id}/shortlist").json()
    assert body["status"] == "Shortlisted" and body["application"]["status"] == "Shortlisted"
    ev = db.exec(select(Event)).one()
    assert (ev.from_status, ev.to_status, ev.actor) == (AppStatus.new, AppStatus.shortlisted, Actor.owner)
    assert client.post(f"/api/leads/{lead.id}/shortlist").status_code == 200  # idempotent
    assert len(db.exec(select(Event)).all()) == 1


def test_skip_stores_reason_and_blocks_later_shortlist(client, db):
    lead = make_lead(db)
    body = client.post(f"/api/leads/{lead.id}/skip", json={"reason": "bad pay"}).json()
    assert body["status"] == "Skipped"
    ev = db.exec(select(Event)).one()
    assert (ev.to_status, ev.note, ev.actor) == (AppStatus.skipped, "bad pay", Actor.owner)
    assert client.post(f"/api/leads/{lead.id}/shortlist").status_code == 409
    assert client.post(f"/api/leads/{make_lead(db).id}/skip", json={"reason": "  "}).status_code == 422


def test_skip_after_applied_is_409(client, db):
    lead = make_lead(db)
    make_app(db, lead, AppStatus.applied)
    assert client.post(f"/api/leads/{lead.id}/skip", json={"reason": "x"}).status_code == 409


def test_restore(client, db):
    lead = make_lead(db, prefilter_pass=False, prefilter_reasons=["ctc"])
    assert ids(client.get("/api/leads")) == []
    body = client.post(f"/api/leads/{lead.id}/restore").json()
    assert body["restored"] is True and body["prefilter_pass"] is True
    assert ids(client.get("/api/leads")) == [lead.id]


# ---------- background runs ----------


def test_run_endpoints_return_202_run_out(client, db, fakes):
    lead = make_lead(db)
    cases = [("evaluate", None, RunKind.evaluate, None), ("verify", None, RunKind.verify, None),
             ("assist-apply", None, RunKind.assist_apply, None), ("contacts", None, RunKind.contacts, None),
             ("cv", {"variant": "B"}, RunKind.cv, {"variant": "B"})]
    for path, body, kind, params in cases:
        r = client.post(f"/api/leads/{lead.id}/{path}", **({"json": body} if body else {}))
        assert r.status_code == 202, r.text
        out = r.json()
        assert out["kind"] == kind.value and out["lead_id"] == lead.id and out["state"] == "queued"
        assert fakes.submitted[-1] == (kind, lead.id, params)
    assert client.post(f"/api/leads/{lead.id}/cv", json={"variant": "C"}).status_code == 422


# ---------- manual lead ----------


def test_manual_lead_is_restored_and_never_dropped(client, db):
    body = {"company": "Zoho", "title": "Senior PHP Wizard", "url": "https://jobs.example.com/1",
            "location": "Mumbai", "jd_text": "php wordpress sales"}
    r = client.post("/api/leads", json=body)
    assert r.status_code == 201, r.text
    out = r.json()
    assert (out["source"], out["restored"], out["prefilter_pass"]) == ("manual", True, True)
    assert out["company"] == "Zoho" and out["status"] == "New" and out["jd_text"] == "php wordpress sales"
    assert out["is_fresh"] is True
    assert ids(client.get("/api/leads")) == [out["id"]]
    again = client.post("/api/leads", json=body).json()  # same url = same lead
    assert again["id"] == out["id"]
    assert db.exec(select(Lead).where(Lead.source == Source.manual)).all().__len__() == 1


def test_manual_lead_with_malformed_url_is_not_a_500(client):
    for url in ("http://[", "https://[::1"):
        r = client.post("/api/leads", json={"company": "Acme", "title": "Dev", "url": url})
        assert r.status_code in (201, 422), r.text
        if r.status_code == 201:
            assert r.json()["canonical_url"] is None and r.json()["restored"] is True


def test_manual_lead_without_url_hashes_company_and_title(client):
    a = client.post("/api/leads", json={"company": "Acme", "title": "Dev"}).json()
    b = client.post("/api/leads", json={"company": "ACME", "title": "dev"}).json()
    c = client.post("/api/leads", json={"company": "Other", "title": "Dev"}).json()
    assert a["id"] == b["id"] != c["id"]


# ---------- bulk ----------


def test_bulk_shortlist_restore_and_missing(client, db):
    a, b = make_lead(db), make_lead(db, prefilter_pass=False)
    r = client.post("/api/leads/bulk", json={"ids": [a.id, 999, b.id], "action": "shortlist"}).json()
    assert r["ok"] == [a.id, b.id] and r["failed"] == {"999": "lead not found"}
    assert {x.status for x in db.exec(select(Application)).all()} == {AppStatus.shortlisted}
    r = client.post("/api/leads/bulk", json={"ids": [b.id], "action": "restore"}).json()
    assert r["ok"] == [b.id]
    db.expire_all()
    assert db.get(Lead, b.id).restored is True


def test_bulk_skip_needs_reason_per_id(client, db):
    a, b = make_lead(db), make_lead(db)
    r = client.post("/api/leads/bulk", json={"ids": [a.id, b.id], "action": "skip"})
    assert r.status_code == 200
    assert r.json()["ok"] == [] and set(r.json()["failed"]) == {str(a.id), str(b.id)}
    assert db.exec(select(Application)).all() == []
    r = client.post("/api/leads/bulk", json={"ids": [a.id, b.id], "action": "skip", "reason": "meh"}).json()
    assert r["ok"] == [a.id, b.id] and r["failed"] == {}
    assert {e.note for e in db.exec(select(Event)).all()} == {"meh"}


def test_bulk_illegal_transition_is_a_failure_entry(client, db):
    a, b = make_lead(db), make_lead(db)
    make_app(db, a, AppStatus.applied)
    r = client.post("/api/leads/bulk", json={"ids": [a.id, b.id], "action": "skip", "reason": "x"}).json()
    assert r["ok"] == [b.id] and "cannot move Applied -> Skipped" in r["failed"][str(a.id)]


def test_bulk_evaluate_and_verify_return_run_ids(client, db, fakes):
    a, b = make_lead(db), make_lead(db)
    r = client.post("/api/leads/bulk", json={"ids": [a.id, b.id, 999], "action": "evaluate"}).json()
    assert r["ok"] == [a.id, b.id] and len(r["run_ids"]) == 2 and 999 in map(int, r["failed"])
    r = client.post("/api/leads/bulk", json={"ids": [a.id], "action": "verify"}).json()
    assert len(r["run_ids"]) == 1
    assert [k for k, *_ in fakes.submitted] == [RunKind.evaluate, RunKind.evaluate, RunKind.verify]


def test_bulk_validation(client):
    assert client.post("/api/leads/bulk", json={"ids": [], "action": "skip"}).status_code == 422
    assert client.post("/api/leads/bulk", json={"ids": [1], "action": "explode"}).status_code == 422


# ---------- experience fit, source email link ----------


def test_exp_fit_compares_stated_minimum_with_the_owner_range(client, db):
    ok = make_lead(db, exp_min=2, exp_max=4)
    stretch = make_lead(db, exp_min=4, exp_max=8)
    above = make_lead(db, exp_min=5, exp_max=9)
    unknown = make_lead(db)
    fit = {i["id"]: i["exp_fit"] for i in client.get("/api/leads").json()["items"]}
    assert fit == {ok.id: "ok", stretch.id: "stretch", above.id: "above", unknown.id: "unknown"}


def test_detail_links_an_inbound_lead_to_its_email_in_gmail(client, db):
    inbound = make_lead(db, source=Source.gmail_inbound, source_ref="<abc.123@mail.example>", is_inbound=True,
                        apply_channel=ApplyChannel.email)
    other = make_lead(db)
    url = client.get(f"/api/leads/{inbound.id}").json()["source_email_url"]
    assert url == "https://mail.google.com/mail/u/0/#search/rfc822msgid:abc.123%40mail.example"
    assert client.get(f"/api/leads/{other.id}").json()["source_email_url"] is None
