"""DB rows -> API schemas. Batch loaders avoid per-row queries; all datetimes leave as aware UTC."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, or_
from sqlmodel import Session, select

from jobhunter import careerops
from jobhunter import schemas as sc
from jobhunter.api.deps import as_utc, now_utc
from jobhunter.models import Application, AppStatus, Evaluation, Event, Lead, Outreach, Proposal

log = logging.getLogger(__name__)

FRESH_HOURS = 48


def is_fresh(lead: Lead, now: datetime) -> bool:
    return as_utc(lead.posted_at or lead.found_at) >= now - timedelta(hours=FRESH_HOURS)


def latest_evaluations(session: Session, lead_ids: list[int]) -> dict[int, Evaluation]:
    if not lead_ids:
        return {}
    rows = session.exec(select(Evaluation).where(Evaluation.lead_id.in_(lead_ids)).order_by(Evaluation.id)).all()
    return {e.lead_id: e for e in rows}  # ascending id: the latest row wins


def lead_summaries(session: Session, leads: list[Lead], now: datetime | None = None) -> list[sc.LeadSummary]:
    now = now or now_utc()
    ids = [lead.id for lead in leads]
    apps = {a.lead_id: a for a in session.exec(select(Application).where(Application.lead_id.in_(ids)))} if ids else {}
    evals = latest_evaluations(session, ids)
    groups = {lead.dedupe_group for lead in leads if lead.dedupe_group}
    sizes = (
        dict(session.exec(
            select(Lead.dedupe_group, func.count()).where(Lead.dedupe_group.in_(groups)).group_by(Lead.dedupe_group)
        ).all())
        if groups
        else {}
    )
    out = []
    for lead in leads:
        app, ev = apps.get(lead.id), evals.get(lead.id)
        out.append(sc.LeadSummary(
            id=lead.id, source=lead.source, source_detail=lead.source_detail, company=lead.company,
            title=lead.title, location=lead.location, work_mode=lead.work_mode,
            apply_channel=lead.apply_channel, apply_url=lead.apply_url, canonical_url=lead.canonical_url,
            exp_min=lead.exp_min, exp_max=lead.exp_max, ctc_min=lead.ctc_min, ctc_max=lead.ctc_max,
            posted_at=as_utc(lead.posted_at), found_at=as_utc(lead.found_at), is_fresh=is_fresh(lead, now),
            role_family=lead.role_family, quick_score=lead.quick_score,
            eval_score=ev.score if ev else None, eval_grade=ev.grade if ev else None,
            is_live=ev.is_live if ev else None, is_inbound=lead.is_inbound,
            prefilter_pass=lead.prefilter_pass, prefilter_reasons=lead.prefilter_reasons,
            prefilter_tags=lead.prefilter_tags, restored=lead.restored,
            duplicates=max(sizes.get(lead.dedupe_group, 1) - 1, 0) if lead.dedupe_group else 0,
            status=app.status if app else AppStatus.new, application_id=app.id if app else None,
        ))
    return out


def lead_summary(session: Session, lead: Lead) -> sc.LeadSummary:
    return lead_summaries(session, [lead])[0]


def report_text(ev: Evaluation) -> str | None:
    try:
        return careerops.report_md(ev)
    except Exception:
        log.warning("report_md failed for evaluation %s", ev.id, exc_info=True)
        return None


def application_outs(session: Session, apps: list[Application]) -> list[sc.ApplicationOut]:
    ids = list({a.lead_id for a in apps})
    leads = {lead.id: lead for lead in session.exec(select(Lead).where(Lead.id.in_(ids)))} if ids else {}
    evals = latest_evaluations(session, ids)
    out = []
    for a in apps:
        lead, ev = leads[a.lead_id], evals.get(a.lead_id)
        out.append(sc.ApplicationOut(
            id=a.id, lead_id=a.lead_id, company=lead.company, title=lead.title, status=a.status,
            resume_variant=a.resume_variant, has_cv_pdf=bool(a.cv_pdf_path), cv_approved=a.cv_approved,
            applied_at=as_utc(a.applied_at), next_follow_up_at=as_utc(a.next_follow_up_at),
            referral_contact=a.referral_contact, recruiter=a.recruiter, notes=a.notes,
            rejected_at_stage=a.rejected_at_stage, source=lead.source, apply_channel=lead.apply_channel,
            eval_score=ev.score if ev else None, created_at=as_utc(a.created_at), updated_at=as_utc(a.updated_at),
        ))
    return out


def application_out(session: Session, app: Application) -> sc.ApplicationOut:
    return application_outs(session, [app])[0]


def event_out(e: Event) -> sc.EventOut:
    return sc.EventOut(
        id=e.id, application_id=e.application_id, from_status=e.from_status, to_status=e.to_status,
        at=as_utc(e.at), actor=e.actor, note=e.note,
    )


def _lead_labels(session: Session, lead_ids: set[int | None], app_ids: set[int | None]) -> tuple[dict, dict]:
    """(lead id -> (company, title), application id -> lead id) for the given ids."""
    lead_ids = {i for i in lead_ids if i is not None}
    app_ids = {i for i in app_ids if i is not None}
    app_lead = (
        dict(session.exec(select(Application.id, Application.lead_id).where(Application.id.in_(app_ids))).all())
        if app_ids
        else {}
    )
    wanted = lead_ids | set(app_lead.values())
    labels = (
        {i: (c, t) for i, c, t in session.exec(select(Lead.id, Lead.company, Lead.title).where(Lead.id.in_(wanted)))}
        if wanted
        else {}
    )
    return labels, app_lead


def outreach_outs(session: Session, rows: list[Outreach]) -> list[sc.OutreachOut]:
    labels, app_lead = _lead_labels(session, {r.lead_id for r in rows}, {r.application_id for r in rows})
    out = []
    for r in rows:
        company, title = labels.get(r.lead_id or app_lead.get(r.application_id), (None, None))
        out.append(sc.OutreachOut(
            id=r.id, application_id=r.application_id, lead_id=r.lead_id, company=company, title=title,
            kind=r.kind, contact=r.contact, draft=r.draft, due_at=as_utc(r.due_at),
            snoozed_until=as_utc(r.snoozed_until), sent_at=as_utc(r.sent_at), created_at=as_utc(r.created_at),
        ))
    return out


def proposal_outs(session: Session, rows: list[Proposal]) -> list[sc.ProposalOut]:
    labels, app_lead = _lead_labels(session, {r.lead_id for r in rows}, {r.application_id for r in rows})
    out = []
    for r in rows:
        company, title = labels.get(r.lead_id or app_lead.get(r.application_id), (None, None))
        out.append(sc.ProposalOut(
            id=r.id, type=r.type, application_id=r.application_id, lead_id=r.lead_id, company=company,
            title=title, payload=r.payload, evidence=r.evidence, confidence=r.confidence, state=r.state,
            created_at=as_utc(r.created_at),
        ))
    return out


def lead_outreach_rows(session: Session, lead_id: int, app_id: int | None) -> list[Outreach]:
    cond = Outreach.lead_id == lead_id
    if app_id is not None:
        cond = or_(cond, Outreach.application_id == app_id)
    return list(session.exec(select(Outreach).where(cond).order_by(Outreach.id)))


def lead_detail(session: Session, lead: Lead) -> sc.LeadDetail:
    summary = lead_summary(session, lead)
    app = session.exec(select(Application).where(Application.lead_id == lead.id)).first()
    ev = latest_evaluations(session, [lead.id]).get(lead.id)
    events = (
        list(session.exec(select(Event).where(Event.application_id == app.id).order_by(Event.at, Event.id)))
        if app
        else []
    )
    dup_ids = (
        list(session.exec(
            select(Lead.id).where(Lead.dedupe_group == lead.dedupe_group, Lead.id != lead.id).order_by(Lead.id)
        ))
        if lead.dedupe_group
        else []
    )
    return sc.LeadDetail(
        **summary.model_dump(),
        jd_text=lead.jd_text,
        evaluation=sc.Evaluation(
            id=ev.id, score=ev.score, grade=ev.grade, report_md=report_text(ev), is_live=ev.is_live,
            live_verified_at=as_utc(ev.live_verified_at), created_at=as_utc(ev.created_at),
        )
        if ev
        else None,
        application=application_out(session, app) if app else None,
        events=[event_out(e) for e in events],
        outreach=outreach_outs(session, lead_outreach_rows(session, lead.id, app.id if app else None)),
        duplicate_ids=dup_ids,
    )
