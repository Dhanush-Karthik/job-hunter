"""/api/reachout: find a job's HR mailbox, auto-filled drafts, owner-confirmed sends and Gmail drafts (SMTP/IMAP and web faked)."""

import base64
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from typing import ClassVar

import pytest
from apihelpers import make_app, make_eval, make_lead
from sqlmodel import select

from jobhunter import paths, reachout
from jobhunter.models import AppStatus, HrEmail, Source, utcnow
from jobhunter.reachout import finder

pytest_plugins = ["apihelpers"]

PORTALS = """\
tracked_companies:
- name: PhonePe
  careers_url: https://www.phonepe.com/careers/
- name: Acceldata
  careers_url: https://www.acceldata.io/careers
"""
PDF = b"%PDF-1.4\n% fake resume\n"


class FakeSmtp:
    sent: ClassVar[list[EmailMessage]] = []
    fail: Exception | None = None

    def __init__(self, host, port, context=None, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, address, password):
        if FakeSmtp.fail:
            raise FakeSmtp.fail

    def send_message(self, msg):
        FakeSmtp.sent.append(msg)


class FakeBox:
    appended: ClassVar[list[tuple[bytes, str, list]]] = []

    def __init__(self, host, port=993):
        pass

    def login(self, address, password, initial_folder=None):
        pass

    def append(self, data, folder, dt=None, flag_set=None):
        FakeBox.appended.append((data, folder, list(flag_set or [])))

    def logout(self):
        pass


@pytest.fixture(autouse=True)
def seams(monkeypatch):
    FakeSmtp.sent, FakeSmtp.fail, FakeBox.appended = [], None, []
    monkeypatch.setattr(reachout, "smtp_factory", FakeSmtp)
    monkeypatch.setattr(reachout, "mailbox_factory", FakeBox)


@pytest.fixture()
def portals(engine):
    p = paths.CAREEROPS_DATA / "portals.yml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(PORTALS)


@pytest.fixture()
def gmail(fakes):
    fakes.keyring.store[("jobhunter", "gmail_address")] = "me@example.com"
    fakes.keyring.store[("jobhunter", "gmail_app_password")] = "abcdabcdabcdabcd"


@pytest.fixture()
def resume(engine):
    paths.CV_DIR.mkdir(parents=True, exist_ok=True)
    (paths.CV_DIR / "resume.pdf").write_bytes(PDF)


@pytest.fixture()
def jobs(db):
    a = make_lead(db, company="PhonePe", title="Backend Engineer", source=Source.linkedin, source_ref="li-4475286970", location="Bengaluru")
    b = make_lead(db, company="PhonePe", title="Java Developer", source=Source.linkedin, source_ref="li-999", quick_score=0.9)
    skipped = make_lead(db, company="PhonePe", title="Skipped one")
    make_app(db, skipped, AppStatus.skipped)
    dropped = make_lead(db, company="PhonePe", title="Filtered out", prefilter_pass=False)
    other = make_lead(db, company="Acceldata", title="Staff Engineer", source_ref="li-4392079926", source=Source.linkedin)
    make_eval(db, a, 4.5)
    return a, b, skipped, dropped, other


def test_job_id_prefers_board_id(db):
    assert reachout.job_id(make_lead(db, source_ref="li-4493202067")) == "4493202067"
    assert reachout.job_id(make_lead(db, source_ref="gd-1010333257419")) == "1010333257419"
    lead = make_lead(db, source_ref="https://boards.example.com/job/with/a/very/long/path?id=1234567890&x=1")
    assert reachout.job_id(lead) == f"JH-{lead.id}"


@pytest.fixture(autouse=True)
def no_web(monkeypatch):
    """Tests never touch the network: pages come from `PAGES`, DNS from `RESOLVES`."""
    PAGES.clear()
    monkeypatch.setattr(finder, "http_get", lambda url: PAGES.get(url))
    monkeypatch.setattr(finder, "resolves", lambda domain: domain in RESOLVES)


PAGES: dict[str, str] = {}
RESOLVES = {"phonepe.com"}


def job_url(lead):
    return f"/api/reachout/jobs/{lead.id}"


def payload(email="hr@phonepe.com", **kw):
    return {"to_email": email, "to_name": "Asha Rao", "subject": "Hello", "body": "Body text", "confirm": True, "attach": "base", **kw}


# ---------- finding the address ----------


def test_job_post_email_is_found_without_the_network(client, jobs, db):
    a = jobs[0]
    a.jd_text = "Send your CV to talent@phonepe.com or no-reply@phonepe.com. Not sales@phonepe.com."
    db.add(a)
    db.commit()
    r = client.get(job_url(a))
    assert r.status_code == 200, r.text
    got = r.json()
    assert [(c["email"], c["source"], c["confidence"]) for c in got["candidates"]] == [("talent@phonepe.com", "job_post", "high")]
    assert got["searched_at"] is None and got["job_id"] == "4475286970"
    assert "Hello," in got["draft"]["body"] and "Job ID 4475286970" in got["draft"]["subject"]


def test_recruiter_sender_of_an_inbound_lead_is_offered(client, jobs, db):
    a = jobs[0]
    a.raw = {"sender": "priya.s@phonepe.com"}
    db.add(a)
    db.commit()
    (c,) = client.get(job_url(a)).json()["candidates"]
    assert (c["email"], c["source"]) == ("priya.s@phonepe.com", "recruiter")


def test_find_reads_the_posting_page_and_company_site(client, portals, jobs, db):
    a = jobs[0]
    a.apply_url = "https://boards.greenhouse.io/phonepe/jobs/1"
    db.add(a)
    db.commit()
    PAGES["https://boards.greenhouse.io/phonepe/jobs/1"] = '<a href="mailto:jobs@phonepe.com?subject=hi">Mail us</a>'
    PAGES["https://www.phonepe.com/careers/"] = "<p>Questions? people [at] phonepe [dot] com</p> <p>ask@elsewhere.org</p>"
    r = client.post(f"{job_url(a)}/find")
    assert r.status_code == 200, r.text
    got = {c["email"]: c["source"] for c in r.json()["candidates"]}
    assert got["jobs@phonepe.com"] == "posting_page"
    assert got["people@phonepe.com"] == "company_site"
    assert "ask@elsewhere.org" not in got  # not the company's own domain
    assert got["careers@phonepe.com"] == "guess" and r.json()["searched_at"] is not None
    # the result is remembered: a plain GET returns the same addresses without searching again
    PAGES.clear()
    again = {c["email"] for c in client.get(job_url(a)).json()["candidates"]}
    assert {"jobs@phonepe.com", "people@phonepe.com", "careers@phonepe.com"} <= again


def test_guesses_need_a_domain_that_resolves_and_can_be_switched_off(client, portals, jobs):
    got = client.post(f"{job_url(jobs[4])}/find").json()  # Acceldata: acceldata.io does not resolve in this test
    assert got["candidates"] == []
    s = client.get("/api/settings").json()
    s["reachout"]["guess_addresses"] = False
    assert client.put("/api/settings", json=s).status_code == 200
    got = client.post(f"{job_url(jobs[0])}/find").json()
    assert all(c["source"] != "guess" for c in got["candidates"])


def test_lookup_off_never_fetches(client, portals, jobs, db):
    s = client.get("/api/settings").json()
    s["reachout"]["look_up_web"] = False
    client.put("/api/settings", json=s)
    PAGES["https://www.phonepe.com/careers/"] = "hr@phonepe.com"
    got = client.post(f"{job_url(jobs[0])}/find").json()
    assert all(c["source"] != "company_site" for c in got["candidates"])


def test_finder_unit_cases():
    assert finder.emails_in("a@b.co, x@2x.png, noreply@acme.com, joe [at] acme [dot] co [dot] in") == ["a@b.co", "joe@acme.co.in"]
    key = 0x5A
    enc = bytes([key, *(b ^ key for b in b"careers@acme.com")]).hex()  # Cloudflare's data-cfemail encoding
    assert finder.emails_in_html(f'<span data-cfemail="{enc}">[email protected]</span>') == ["careers@acme.com"]
    assert finder.company_domain("https://careers.acme.co.in/jobs") == "acme.co.in"
    assert finder.company_domain("https://www.linkedin.com/jobs/1", "https://boards.greenhouse.io/x", "https://x.com/y") is None
    assert finder.company_domain("https://jobs.lever.co/acme", "https://www.acme.io/careers") == "acme.io"
    assert finder.fetch("http://localhost:8787/api/settings") is None and finder.fetch("file:///etc/passwd") is None
    assert finder.fetch("http://169.254.169.254/latest") is None


# ---------- the email ----------


def test_draft_uses_greeting_name_and_extra_jobs(client, portals, jobs):
    a, b, *_ = jobs
    one = client.post(f"{job_url(a)}/draft", json={"to_name": "Asha Rao"}).json()
    assert "Backend Engineer (Job ID 4475286970)" in one["subject"] and one["body"].startswith("Hi Asha,")
    two = client.post(f"{job_url(a)}/draft", json={"extra_lead_ids": [b.id]}).json()
    assert "2 roles at PhonePe" in two["subject"] and "Job ID 4475286970" in two["body"] and "Job ID 999" in two["body"]
    others = client.get(job_url(a)).json()["other_jobs"]
    assert [j["job_id"] for j in others] == ["999"]  # skipped / filtered-out leads and other companies excluded


def test_draft_rejects_jobs_of_another_company(client, portals, jobs):
    r = client.post(f"{job_url(jobs[0])}/draft", json={"extra_lead_ids": [jobs[4].id]})
    assert r.status_code == 422


def test_templates_come_from_settings(client, jobs):
    s = client.get("/api/settings").json()
    s["reachout"].update(subject_one="{title} / {job_id} / {name}", body="{greeting} {unknown_later} Bye {signature}",
                         me={"name": "Sam Doe", "phone": "+1 555", "linkedin": "", "github": "", "headline": "Go engineer | x"})
    assert client.put("/api/settings", json=s).status_code == 422  # {unknown_later} is not a placeholder
    s["reachout"]["body"] = "{greeting} I am a {role}. Bye\n{signature}"
    assert client.put("/api/settings", json=s).status_code == 200
    d = client.post(f"{job_url(jobs[0])}/draft", json={}).json()
    assert d["subject"] == "Backend Engineer / 4475286970 / Sam Doe"
    assert d["body"] == "Hello, I am a Go engineer. Bye\nSam Doe\n+1 555\n"


# ---------- sending ----------


def test_send_needs_confirm_and_a_valid_address(client, jobs, gmail, resume):
    assert client.post(f"{job_url(jobs[0])}/send", json=payload(confirm=False)).status_code == 422
    assert client.post(f"{job_url(jobs[0])}/send", json=payload(email="nope")).status_code == 422
    assert FakeSmtp.sent == []


def test_send_attaches_resume_logs_and_remembers_the_contact(client, jobs, gmail, resume, db):
    a = jobs[0]
    r = client.post(f"{job_url(a)}/send", json=payload())
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "sent" and r.json()["attachment"] == "resume.pdf" and r.json()["lead_ids"] == [a.id]
    (msg,) = FakeSmtp.sent
    assert "Asha Rao" in str(msg["To"]) and "hr@phonepe.com" in str(msg["To"]) and msg["From"] == "me@example.com"
    (att,) = list(msg.iter_attachments())
    assert att.get_content() == PDF and att.get_filename() == "resume.pdf"
    assert db.exec(select(HrEmail)).one().state == "sent"
    got = client.get(job_url(a)).json()
    assert got["status"]["sent_today"] == 1 and got["history"][0]["to_email"] == "hr@phonepe.com"
    saved = [c for c in got["candidates"] if c["source"] == "saved"]
    assert saved and saved[0]["last_emailed_at"] is not None and saved[0]["contact_id"] is not None
    # another PhonePe job offers the same saved contact
    assert client.get(job_url(jobs[1])).json()["candidates"][0]["email"] == "hr@phonepe.com"


def test_cooldown_blocks_repeat_unless_forced(client, jobs, gmail, resume):
    assert client.post(f"{job_url(jobs[0])}/send", json=payload()).status_code == 200
    again = client.post(f"{job_url(jobs[1])}/send", json=payload())
    assert again.status_code == 409 and "days ago" in again.json()["detail"]
    assert client.post(f"{job_url(jobs[1])}/send", json=payload(force=True)).status_code == 200
    assert len(FakeSmtp.sent) == 2


def test_daily_cap_comes_from_settings(client, jobs, gmail, resume):
    s = client.get("/api/settings").json()
    s["reachout"]["daily_cap"] = 1
    client.put("/api/settings", json=s)
    assert client.post(f"{job_url(jobs[0])}/send", json=payload()).status_code == 200
    assert client.post(f"{job_url(jobs[0])}/send", json=payload(email="other@phonepe.com")).status_code == 429
    # drafts do not count against the cap
    assert client.post(f"{job_url(jobs[0])}/send", json=payload(email="other@phonepe.com", mode="draft")).status_code == 200


def test_turned_off_blocks_sending(client, jobs, gmail, resume):
    s = client.get("/api/settings").json()
    s["reachout"]["enabled"] = False
    client.put("/api/settings", json=s)
    assert client.post(f"{job_url(jobs[0])}/send", json=payload()).status_code == 409
    assert client.get("/api/reachout/status").json()["enabled"] is False


def test_draft_mode_saves_to_gmail_drafts_and_does_not_send(client, jobs, gmail, resume):
    r = client.post(f"{job_url(jobs[0])}/send", json=payload(mode="draft"))
    assert r.status_code == 200 and r.json()["state"] == "drafted"
    assert FakeSmtp.sent == []
    ((data, folder, flags),) = FakeBox.appended
    assert folder == "[Gmail]/Drafts" and b"resume.pdf" in data and flags


def test_missing_resume_and_missing_gmail(client, jobs, gmail):
    r = client.post(f"{job_url(jobs[0])}/send", json=payload())
    assert r.status_code == 422 and "resume" in r.text
    none = client.post(f"{job_url(jobs[0])}/send", json=payload(attach="none"))
    assert none.status_code == 200 and none.json()["attachment"] is None


def test_no_gmail_credentials(client, jobs, resume):
    r = client.post(f"{job_url(jobs[0])}/send", json=payload())
    assert r.status_code == 409 and "Gmail" in r.json()["detail"]


def test_smtp_failure_is_logged_and_hides_password(client, jobs, gmail, resume, db):
    FakeSmtp.fail = smtplib.SMTPAuthenticationError(535, b"bad abcdabcdabcdabcd")
    r = client.post(f"{job_url(jobs[0])}/send", json=payload())
    assert r.status_code == 502 and "abcdabcd" not in r.text
    assert db.exec(select(HrEmail)).one().state == "failed"
    # a failed attempt does not start the cool-down
    FakeSmtp.fail = None
    assert client.post(f"{job_url(jobs[0])}/send", json=payload()).status_code == 200


def test_tailored_cv_is_the_default_attachment(client, jobs, gmail, resume, db, tmp_path):
    a = jobs[0]
    assert client.get(job_url(a)).json()["attach_default"] == "base"
    pdf = tmp_path / "Sam_PhonePe.pdf"
    pdf.write_bytes(PDF + b"tailored")
    make_app(db, a, AppStatus.ready, cv_pdf_path=str(pdf))
    got = client.get(job_url(a)).json()
    assert got["attach_default"] == "tailored" and got["has_tailored_cv"] is True
    bad = client.post(f"{job_url(jobs[1])}/send", json=payload(attach="tailored"))
    assert bad.status_code == 422
    ok = client.post(f"{job_url(a)}/send", json=payload(attach="tailored"))
    assert ok.status_code == 200 and ok.json()["attachment"] == "Sam_PhonePe.pdf"


def test_other_jobs_can_be_listed_in_the_same_email(client, jobs, gmail, resume):
    a, b, *_ = jobs
    r = client.post(f"{job_url(a)}/send", json=payload(extra_lead_ids=[b.id]))
    assert r.status_code == 200 and r.json()["lead_ids"] == [a.id, b.id]
    assert client.get(job_url(b)).json()["history"][0]["lead_ids"] == [a.id, b.id]


def test_resume_upload_validates(client, engine):
    enc = lambda b: base64.b64encode(b).decode()
    assert client.put("/api/reachout/resume", json={"filename": "cv.pdf", "data_base64": enc(b"not a pdf")}).status_code == 422
    assert client.put("/api/reachout/resume", json={"filename": "cv.pdf", "data_base64": "!!!notbase64!!!"}).status_code == 422
    r = client.put("/api/reachout/resume", json={"filename": "cv.pdf", "data_base64": enc(PDF)})
    assert r.status_code == 200 and r.json()["present"] is True
    assert client.get("/api/reachout/status").json()["resume"]["present"] is True
    assert client.delete("/api/reachout/resume").status_code == 204
    assert client.get("/api/reachout/status").json()["resume"]["present"] is False


def test_email_log_newest_first_and_contact_delete(client, jobs, gmail, resume):
    for mail in ("a@phonepe.com", "b@phonepe.com"):
        client.post(f"{job_url(jobs[0])}/send", json=payload(email=mail, attach="none", mode="draft"))
    rows = client.get("/api/reachout/emails").json()
    assert [r["id"] for r in rows] == sorted((r["id"] for r in rows), reverse=True) and len(rows) == 2
    assert client.get("/api/reachout/emails", params={"company": "acceldata"}).json() == []
    saved = [c for c in client.get(job_url(jobs[0])).json()["candidates"] if c["source"] == "saved"]
    assert client.delete(f"/api/reachout/contacts/{saved[0]['contact_id']}").status_code == 204
    assert client.delete(f"/api/reachout/contacts/{saved[0]['contact_id']}").status_code == 404
    assert utcnow() - timedelta(minutes=1) < utcnow()


def test_example_config_matches_the_built_in_email_defaults():
    """config/jobhunter.example.yml documents the defaults: it must not drift from schemas.py."""
    from jobhunter.schemas import ReachoutSettings
    from jobhunter.settings import load_defaults

    assert load_defaults(paths.CONFIG_EXAMPLE).reachout == ReachoutSettings()


def test_gmail_credentials_fall_back_to_environment(client, jobs, resume, monkeypatch):
    assert client.get("/api/reachout/status").json()["gmail_ready"] is False
    monkeypatch.setenv("JOBHUNTER_GMAIL_ADDRESS", "env@example.com")
    monkeypatch.setenv("JOBHUNTER_GMAIL_APP_PASSWORD", "abcdabcdabcdabcd")
    status = client.get("/api/reachout/status").json()
    assert status["gmail_ready"] is True and status["sender"] == "env@example.com"
    assert client.post(f"{job_url(jobs[0])}/send", json=payload()).status_code == 200
