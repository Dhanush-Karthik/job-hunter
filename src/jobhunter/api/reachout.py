"""Reach-out from the job page: find the job's HR mailbox, auto-fill the email, send it on one click.

Every send is an explicit owner action (`confirm: true`), subject to the cool-down and daily cap in Settings > Reach-out.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response
from keyring.errors import KeyringError
from sqlalchemy import func
from sqlmodel import Session, col, select

from jobhunter import paths, reachout, secrets
from jobhunter import settings as app_settings
from jobhunter.api import companies as portals
from jobhunter.api.deps import SessionDep, as_utc, db_dt, fits, now_utc
from jobhunter.api.workflow import get_lead_or_404, unprocessable
from jobhunter.models import Application, AppStatus, Evaluation, HrContact, HrEmail, HrLookup, Lead
from jobhunter.reachout import finder
from jobhunter.schemas import (
    EmailCandidate,
    EmailDraft,
    HrEmailOut,
    JobReachout,
    ReachoutDraftRequest,
    ReachoutJob,
    ReachoutSend,
    ReachoutSettings,
    ReachoutStatus,
    ResumeStatus,
    ResumeUpload,
)

router = APIRouter(prefix="/api/reachout", tags=["reachout"])

_HIDDEN = (AppStatus.skipped, AppStatus.expired, AppStatus.rejected, AppStatus.withdrawn, AppStatus.declined)
_WEB_SOURCES = {"posting_page", "company_site", "guess"}


def _key(name: str) -> str:
    return " ".join(name.casefold().split())


def _cfg(session: Session) -> ReachoutSettings:
    return app_settings.get_settings(session).reachout


def _credentials() -> tuple[str, str] | None:
    try:
        address, password = secrets.get("gmail_address"), secrets.get("gmail_app_password")
    except (KeyringError, OSError, RuntimeError):
        return None
    return (address, password) if address and password else None


def _resume_status() -> ResumeStatus:
    f = reachout.resume_path()
    if not f.is_file():
        return ResumeStatus(present=False)
    st = f.stat()
    return ResumeStatus(present=True, filename=f.name, size_kb=max(1, st.st_size // 1024),
                        updated_at=datetime.fromtimestamp(st.st_mtime).astimezone())


def _sent_since(session: Session, since: datetime) -> int:
    return len(session.exec(select(HrEmail.id).where(HrEmail.state == "sent", HrEmail.created_at >= db_dt(since))).all())


def _last_sent(session: Session) -> dict[str, datetime]:
    out: dict[str, datetime] = {}
    for to_email, at in session.exec(select(HrEmail.to_email, HrEmail.created_at).where(HrEmail.state == "sent")):
        key = to_email.casefold()
        if key not in out or at > out[key]:
            out[key] = at
    return out


def _status(session: Session, cfg: ReachoutSettings) -> ReachoutStatus:
    creds = _credentials()
    return ReachoutStatus(
        enabled=cfg.enabled, gmail_ready=creds is not None, sender=creds[0] if creds else None,
        sent_today=_sent_since(session, now_utc() - timedelta(hours=24)), daily_cap=cfg.daily_cap,
        cooldown_days=cfg.cooldown_days, resume=_resume_status())


@router.get("/status", response_model=ReachoutStatus, operation_id="getReachoutStatus")
def status(session: SessionDep) -> ReachoutStatus:
    return _status(session, _cfg(session))


@router.put("/resume", response_model=ResumeStatus, operation_id="putReachoutResume")
def put_resume(body: ResumeUpload) -> ResumeStatus:
    try:
        data = base64.b64decode(body.data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise unprocessable("data_base64", "file is not valid base64") from None
    if not data.startswith(b"%PDF"):
        raise unprocessable("data_base64", "the resume must be a PDF file")
    if len(data) > reachout.MAX_RESUME_BYTES:
        raise unprocessable("data_base64", "the resume must be 5 MB or smaller")
    paths.CV_DIR.mkdir(parents=True, exist_ok=True)
    tmp = reachout.resume_path().with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(reachout.resume_path())
    return _resume_status()


@router.delete("/resume", status_code=204, operation_id="deleteReachoutResume")
def delete_resume() -> Response:
    reachout.resume_path().unlink(missing_ok=True)
    return Response(status_code=204)


# ---------- jobs of one company ----------


def _company_leads(session: Session, company: str) -> list[tuple[Lead, Application | None]]:
    key = _key(company)
    if len(key) < 2:
        return []
    rows = session.exec(
        select(Lead, Application).join(Application, Application.lead_id == Lead.id, isouter=True)
        .where(func.lower(Lead.company).contains(key, autoescape=True))
    ).all()
    out = []
    for lead, app in rows:
        lk = _key(lead.company)
        if not (lk == key or lk.startswith(key + " ") or key.startswith(lk + " ")):
            continue
        if not (lead.prefilter_pass or lead.restored) or (app is not None and app.status in _HIDDEN):
            continue
        out.append((lead, app))
    return out


def _tailored_pdf(app: Application | None) -> Path | None:
    pdf = Path(app.cv_pdf_path) if app and app.cv_pdf_path else None
    return pdf if pdf is not None and pdf.is_file() else None


def _jobs(session: Session, company: str, exclude: int | None = None) -> list[ReachoutJob]:
    rows = [(lead, app) for lead, app in _company_leads(session, company) if lead.id != exclude]
    ids = [lead.id for lead, _ in rows if lead.id is not None]
    scores: dict[int, float] = {}
    if ids:
        for lead_id, score in session.exec(select(Evaluation.lead_id, Evaluation.score).where(col(Evaluation.lead_id).in_(ids))):
            if score is not None:
                scores[lead_id] = max(score, scores.get(lead_id, 0.0))
    out = []
    for lead, app in sorted(rows, key=lambda r: (-(scores.get(r[0].id or 0, 0.0)), -r[0].quick_score, r[0].id or 0)):
        out.append(ReachoutJob(
            lead_id=lead.id or 0, job_id=reachout.job_id(lead), title=lead.title, location=lead.location,
            url=lead.apply_url or lead.canonical_url, source=lead.source, score=scores.get(lead.id or 0),
            status=app.status if app else None, has_tailored_cv=_tailored_pdf(app) is not None,
        ))
    return out


def _application(session: Session, lead_id: int) -> Application | None:
    return session.exec(select(Application).where(Application.lead_id == lead_id)).first()


# ---------- finding the HR address ----------


def _careers_url(company: str) -> str | None:
    key = _key(company)
    try:
        for c in portals.list_companies():
            if _key(c.name) == key and c.careers_url:
                return c.careers_url
    except HTTPException:  # unreadable portals.yml: the lookup still works from the job post
        pass
    return None


def _saved(session: Session, company: str) -> list[HrContact]:
    return list(session.exec(select(HrContact).where(HrContact.company_key == _key(company)).order_by(HrContact.id)))


def _candidates(session: Session, lead: Lead) -> list[EmailCandidate]:
    """Local knowledge only (no network): job text, the recruiter who wrote, saved contacts, the cached web lookup."""
    found = [*finder.from_text(lead.jd_text), *finder.from_sender(
        str(lead.raw.get("sender") or "") or None, str(lead.raw.get("sender_name") or "") or None)]
    cached = session.get(HrLookup, lead.id) if lead.id is not None else None
    for item in (cached.found if cached else []):
        try:
            found.append(finder.Found(**item))
        except TypeError:
            continue
    contacts = {c.email.casefold(): c for c in _saved(session, lead.company)}
    for c in contacts.values():
        found.append(finder.make(c.email, "saved", c.name))
    last = _last_sent(session)
    out = []
    for f in finder.rank(found):
        c = contacts.get(f.email.casefold())
        out.append(EmailCandidate(
            email=f.email, name=(c.name if c else None) or f.name, source=f.source, label=f.label,
            confidence=f.confidence, contact_id=c.id if c else None, last_emailed_at=last.get(f.email.casefold())))
    return out


def _history(session: Session, lead_id: int) -> list[HrEmailOut]:
    rows = session.exec(select(HrEmail).order_by(HrEmail.created_at.desc(), HrEmail.id.desc()).limit(200)).all()
    return [_email_out(e) for e in rows if lead_id in (e.lead_ids or [])]


def _draft(session: Session, cfg: ReachoutSettings, lead: Lead, to_name: str | None, extra: list[int]) -> EmailDraft:
    leads = _selected(session, lead, extra)
    creds = _credentials()
    me = reachout.candidate(cfg, creds[0] if creds else None)
    subject, text = reachout.compose(lead.company, to_name, [(x, reachout.job_id(x)) for x in leads], me, cfg)
    return EmailDraft(subject=subject, body=text)


def _job_reachout(session: Session, lead: Lead) -> JobReachout:
    cfg = _cfg(session)
    app = _application(session, lead.id or 0)
    tailored = _tailored_pdf(app) is not None
    status_ = _status(session, cfg)
    attach = cfg.default_attach
    if attach == "tailored" and not tailored:
        attach = "base"
    if attach == "base" and not status_.resume.present:
        attach = "tailored" if tailored else "none"
    cached = session.get(HrLookup, lead.id)
    return JobReachout(
        lead_id=lead.id or 0, company=lead.company, job_id=reachout.job_id(lead), status=status_,
        candidates=_candidates(session, lead), searched_at=as_utc(cached.searched_at) if cached else None,
        other_jobs=_jobs(session, lead.company, exclude=lead.id), draft=_draft(session, cfg, lead, None, []),
        attach_default=attach, has_tailored_cv=tailored, history=_history(session, lead.id or 0))


@router.get("/jobs/{lead_id}", response_model=JobReachout, operation_id="getJobReachout")
def job_reachout(lead_id: int, session: SessionDep) -> JobReachout:
    """The Email-HR card for one job: candidate addresses found so far, the written email, attachments, history."""
    return _job_reachout(session, get_lead_or_404(session, lead_id))


@router.post("/jobs/{lead_id}/find", response_model=JobReachout, operation_id="findJobHrEmails")
def find_hr_emails(lead_id: int, session: SessionDep) -> JobReachout:
    """Look the HR address up on the web (job page, company site, common addresses) and remember what was found."""
    lead = get_lead_or_404(session, lead_id)
    cfg = _cfg(session)
    found = finder.lookup(
        jd_text=lead.jd_text, sender=str(lead.raw.get("sender") or "") or None,
        job_urls=[lead.apply_url, lead.canonical_url], careers_url=_careers_url(lead.company),
        guess=cfg.guess_addresses, guess_prefixes=cfg.guess_prefixes, pages=cfg.look_up_web)
    row = session.get(HrLookup, lead_id) or HrLookup(lead_id=lead_id)
    row.found = [f.as_dict() for f in found if f.source in _WEB_SOURCES]
    row.searched_at = now_utc()
    session.add(row)
    session.commit()
    return _job_reachout(session, lead)


@router.post("/jobs/{lead_id}/draft", response_model=EmailDraft, operation_id="draftJobEmail")
def draft(lead_id: int, body: ReachoutDraftRequest, session: SessionDep) -> EmailDraft:
    """The email text for this job (and any extra jobs of the same company). Nothing is sent."""
    return _draft(session, _cfg(session), get_lead_or_404(session, lead_id), body.to_name, body.extra_lead_ids)


def _selected(session: Session, lead: Lead, extra_ids: list[int]) -> list[Lead]:
    if len(set(extra_ids)) != len(extra_ids) or lead.id in extra_ids:
        raise unprocessable("extra_lead_ids", "duplicate jobs selected")
    allowed = {x.id: x for x, _ in _company_leads(session, lead.company)}
    missing = [i for i in extra_ids if i not in allowed]
    if missing:
        raise unprocessable("extra_lead_ids", f"jobs {missing} do not belong to {lead.company}")
    return [lead, *(allowed[i] for i in extra_ids)]


# ---------- sending ----------


def _attachment(session: Session, attach: str, lead: Lead) -> tuple[str, bytes] | None:
    if attach == "none":
        return None
    if attach == "tailored":
        pdf = _tailored_pdf(_application(session, lead.id or 0))
        if pdf is None:
            raise unprocessable("attach", "this job has no tailored CV PDF yet; generate one or pick another attachment")
        return pdf.name, pdf.read_bytes()
    f = reachout.resume_path()
    if not f.is_file():
        raise unprocessable("attach", "upload your resume PDF in Settings first, or send without an attachment")
    return "resume.pdf", f.read_bytes()


def _remember(session: Session, lead: Lead, email: str, name: str | None) -> HrContact:
    """The address becomes a saved contact for this company, so the next job there offers it first."""
    key = _key(lead.company)
    row = session.exec(select(HrContact).where(HrContact.company_key == key, func.lower(HrContact.email) == email.casefold())).first()
    if row is None:
        row = HrContact(company=lead.company, company_key=key, email=email, name=(name or "").strip() or None)
        session.add(row)
        session.commit()
        session.refresh(row)
    elif name and not row.name:
        row.name = name.strip()
        session.add(row)
        session.commit()
    return row


def _log(session: Session, lead: Lead, leads: list[Lead], contact_id: int | None, body: ReachoutSend, email: str,
         attachment: str | None, state: str, error: str | None = None) -> HrEmail:
    row = HrEmail(
        contact_id=contact_id, company=lead.company, to_email=email, to_name=(body.to_name or "").strip() or None,
        subject=body.subject, body=body.body, lead_ids=[x.id for x in leads if x.id is not None],
        attachment=attachment, state=state, error=error)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.post("/jobs/{lead_id}/send", response_model=HrEmailOut, operation_id="sendJobEmail")
def send(lead_id: int, body: ReachoutSend, session: SessionDep) -> HrEmailOut:
    """Send (or save as a Gmail draft) the email. Needs confirm=true; refuses repeats and over-the-cap sends."""
    cfg = _cfg(session)
    if not cfg.enabled:
        raise HTTPException(409, "Reach-out is turned off in Settings.")
    if not body.confirm:
        raise unprocessable("confirm", "sending needs the owner's confirmation")
    email = body.to_email.strip()
    if not reachout.valid_email(email):
        raise unprocessable("to_email", "enter a valid email address")
    lead = get_lead_or_404(session, lead_id)
    leads = _selected(session, lead, body.extra_lead_ids)
    creds = _credentials()
    if creds is None:
        raise HTTPException(409, "Gmail is not connected. Add the Gmail address and app password in Settings.")
    if body.mode == "send":
        if _sent_since(session, now_utc() - timedelta(hours=24)) >= cfg.daily_cap:
            raise HTTPException(429, f"Daily limit of {cfg.daily_cap} emails reached. Try again tomorrow.")
        recent = _last_sent(session).get(email.casefold())
        if recent and not body.force and now_utc() - as_utc(recent) < timedelta(days=cfg.cooldown_days):
            raise HTTPException(409, f"{email} was emailed less than {cfg.cooldown_days} days ago.")
    attachment = _attachment(session, body.attach, lead)
    msg = reachout.build_message(creds[0], email, body.to_name, body.subject, body.body, attachment)
    name = attachment[0] if attachment else None
    try:
        (reachout.send if body.mode == "send" else reachout.save_draft)(creds[0], creds[1], msg)
    except reachout.ReachoutError as e:
        _log(session, lead, leads, None, body, email, name, "failed", str(e))
        raise HTTPException(502, str(e)) from None
    contact = _remember(session, lead, email, body.to_name)
    return _email_out(_log(session, lead, leads, contact.id, body, email, name, "sent" if body.mode == "send" else "drafted"))


def _email_out(e: HrEmail) -> HrEmailOut:
    return HrEmailOut(
        id=e.id or 0, company=e.company, to_email=e.to_email, to_name=e.to_name, subject=e.subject,
        lead_ids=list(e.lead_ids), attachment=e.attachment, state=e.state, error=e.error, created_at=e.created_at)  # type: ignore[arg-type]


@router.get("/emails", response_model=list[HrEmailOut], operation_id="listReachoutEmails")
def list_emails(session: SessionDep, company: str | None = None, limit: int = Query(50, ge=1, le=200)) -> list[HrEmailOut]:
    stmt = select(HrEmail).order_by(HrEmail.created_at.desc(), HrEmail.id.desc()).limit(limit)
    if company:
        stmt = stmt.where(func.lower(HrEmail.company) == _key(company))
    return [_email_out(e) for e in session.exec(stmt)]


@router.delete("/contacts/{contact_id}", status_code=204, operation_id="deleteHrContact")
def delete_contact(contact_id: int, session: SessionDep) -> Response:
    row = session.get(HrContact, contact_id) if fits(contact_id) else None
    if row is None:
        raise HTTPException(404, "contact not found")
    for e in session.exec(select(HrEmail).where(HrEmail.contact_id == row.id)):
        e.contact_id = None  # keep the log
        session.add(e)
    session.delete(row)
    session.commit()
    return Response(status_code=204)
