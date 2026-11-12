"""Today page and analytics."""

from __future__ import annotations

import logging
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter
from sqlmodel import Session, select

from jobhunter.api import convert, queries
from jobhunter.api._stub import todo
from jobhunter.api.config import ensure_profiles, profile_due
from jobhunter.api.deps import SessionDep, db_dt, now_utc, week_start
from jobhunter.jobs import scheduler
from jobhunter.models import (
    TERMINAL,
    Application,
    ApplyChannel,
    AppStatus,
    Event,
    Lead,
    Outreach,
    OutreachKind,
    Proposal,
    ProposalState,
    ProposalType,
)
from jobhunter.schemas import (
    ActionItem,
    Breakdown,
    BreakdownRow,
    Funnel,
    FunnelStage,
    Insight,
    RejectAuditRow,
    ResponseTimes,
    TodaySummary,
    WeeklyPoint,
)
from jobhunter.settings import get_settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["insight"])

FUNNEL = [
    AppStatus.shortlisted, AppStatus.ready, AppStatus.applied, AppStatus.screening, AppStatus.technical,
    AppStatus.final, AppStatus.offer, AppStatus.accepted,
]
CALL = AppStatus.screening  # "interview call" = any move into Screening


def _count_events(session: Session, to: AppStatus, start: datetime, end: datetime | None = None) -> int:
    stmt = select(Event.id).where(Event.to_status == to, Event.at >= db_dt(start))
    if end is not None:
        stmt = stmt.where(Event.at < db_dt(end))
    return len(session.exec(stmt).all())


def _count_referrals(session: Session, start: datetime, end: datetime | None = None) -> int:
    stmt = select(Outreach.id).where(Outreach.kind == OutreachKind.referral, Outreach.sent_at >= db_dt(start))
    if end is not None:
        stmt = stmt.where(Outreach.sent_at < db_dt(end))
    return len(session.exec(stmt).all())


def _actions(session: Session, now: datetime) -> list[ActionItem]:
    items: list[ActionItem] = []
    pending = list(session.exec(
        select(Proposal).where(Proposal.state == ProposalState.pending).order_by(Proposal.created_at, Proposal.id)
    ))
    outs = {o.id: o for o in convert.proposal_outs(session, pending)}
    for inbound_first in (True, False):
        for p in pending:
            if (p.type == ProposalType.inbound) != inbound_first:
                continue
            o = outs[p.id]
            label = " — ".join(x for x in (o.company, o.title) if x)
            items.append(ActionItem(
                kind="inbound" if inbound_first else "proposal",
                title=label or ("Inbound recruiter" if inbound_first else f"{p.type.value} proposal"),
                subtitle=p.evidence if inbound_first else f"{p.type.value}: {p.evidence or ''}".strip(": "),
                lead_id=o.lead_id, application_id=o.application_id, proposal_id=p.id,
            ))

    due = session.exec(
        select(Application, Lead).join(Lead, Lead.id == Application.lead_id)
        .where(Application.next_follow_up_at.is_not(None), Application.next_follow_up_at <= db_dt(now))
        .where(Application.status.not_in(list(TERMINAL))).order_by(Application.next_follow_up_at)
    ).all()
    for app, lead in due:
        items.append(ActionItem(
            kind="follow_up", title=f"Follow up: {lead.company}", subtitle=lead.title, lead_id=lead.id,
            application_id=app.id, due_at=convert.as_utc(app.next_follow_up_at),
        ))

    # only Shortlisted: Applied/Skipped ones keep a PDF that never needs approving
    review = session.exec(
        select(Application, Lead).join(Lead, Lead.id == Application.lead_id)
        .where(Application.cv_pdf_path.is_not(None), Application.cv_approved.is_(False))
        .where(Application.status == AppStatus.shortlisted).order_by(Application.updated_at)
    ).all()
    for app, lead in review:
        variant = f"variant {app.resume_variant.value} generated" if app.resume_variant else "CV generated"
        items.append(ActionItem(
            kind="cv_review", title=f"Approve CV for {lead.company} {lead.title}", subtitle=variant,
            lead_id=lead.id, application_id=app.id,
        ))

    quick = len(session.exec(
        select(Lead.id).join(Application, Application.lead_id == Lead.id)
        .where(Application.status.in_([AppStatus.shortlisted, AppStatus.ready]))
        .where(Lead.apply_channel == ApplyChannel.platform_quick)
    ).all())
    if quick:
        items.append(ActionItem(kind="quick_apply", title=f"{quick} quick-apply job{'s' if quick != 1 else ''} waiting"))

    drafts = session.exec(
        select(Outreach).where(Outreach.kind == OutreachKind.referral, Outreach.sent_at.is_(None))
        .where(Outreach.draft.is_not(None)).order_by(Outreach.created_at, Outreach.id).limit(10)
    ).all()
    for o in convert.outreach_outs(session, list(drafts)):
        items.append(ActionItem(
            kind="referral", title=f"Referral draft: {o.company or 'company'}", subtitle=o.contact,
            lead_id=o.lead_id, application_id=o.application_id, outreach_id=o.id, due_at=o.due_at,
        ))

    for p in ensure_profiles(session):
        if profile_due(p, now):
            items.append(ActionItem(
                kind="profile_refresh", title=f"Refresh your {p.platform} profile", subtitle=p.edit_url,
                platform=p.platform,
            ))
    return items


@router.get("/today", response_model=TodaySummary, operation_id="getToday")
def today(session: SessionDep) -> TodaySummary:
    now = now_utc()
    this_week, prev_week = week_start(now), week_start(now, 1)
    targets = get_settings(session).targets
    hot = session.exec(
        queries.lead_query(status=[AppStatus.new], fresh_only=True, sort="eval_score", now=now).limit(10)
    ).all()
    try:
        health = scheduler.services()
    except Exception:
        log.warning("scheduler probe failed", exc_info=True)
        health = []
    return TodaySummary(
        interview_calls_week=_count_events(session, CALL, this_week),
        interview_calls_prev_week=_count_events(session, CALL, prev_week, this_week),
        applied_week=_count_events(session, AppStatus.applied, this_week),
        applied_target=targets.applied_per_week,
        referrals_week=_count_referrals(session, this_week),
        referrals_target=targets.referrals_per_week,
        fresh_hot_leads=convert.lead_summaries(session, list(hot), now),
        actions=_actions(session, now),
        health=health,
    )


# ---------- analytics ----------


def _events_in_range(date_from: datetime | None, date_to: datetime | None):
    stmt = select(Event)
    if date_from is not None:
        stmt = stmt.where(Event.at >= db_dt(date_from))
    if date_to is not None:
        stmt = stmt.where(Event.at <= db_dt(date_to))
    return stmt


@router.get("/analytics/funnel", response_model=Funnel, operation_id="analyticsFunnel")
def funnel(session: SessionDep, date_from: datetime | None = None, date_to: datetime | None = None) -> Funnel:
    reached: dict[AppStatus, set[int]] = defaultdict(set)
    for e in session.exec(_events_in_range(date_from, date_to)):
        reached[e.to_status].add(e.application_id)
    stages, prev = [], None
    for status in FUNNEL:
        n = len(reached[status])
        stages.append(FunnelStage(
            status=status, count=n, conversion_from_prev=(n / prev) if prev else None
        ))
        prev = n
    return Funnel(stages=stages, date_from=date_from, date_to=date_to)


def _breakdown_key(by: str, lead: Lead, app: Application) -> str:
    if by == "source":
        return lead.source.value
    if by == "channel":
        return lead.apply_channel.value
    if by == "title":
        return " ".join(lead.title.split())
    if by == "variant":
        return app.resume_variant.value if app.resume_variant else "none"
    return lead.role_family.value


@router.get("/analytics/breakdown", response_model=Breakdown, operation_id="analyticsBreakdown")
def breakdown(
    session: SessionDep,
    by: Literal["source", "channel", "title", "variant", "role_family"],
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Breakdown:
    reached: dict[AppStatus, set[int]] = defaultdict(set)
    for e in session.exec(_events_in_range(date_from, date_to)):
        reached[e.to_status].add(e.application_id)
    applied, calls = Counter(), Counter()
    rows = session.exec(
        select(Application, Lead).join(Lead, Lead.id == Application.lead_id)
        .where(Application.id.in_(reached[AppStatus.applied]))
    ).all() if reached[AppStatus.applied] else []
    for app, lead in rows:
        key = _breakdown_key(by, lead, app)
        applied[key] += 1
        calls[key] += app.id in reached[CALL]
    out = [
        BreakdownRow(key=k, applied=n, calls=calls[k], rate=calls[k] / n if n else None)
        for k, n in sorted(applied.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return Breakdown(by=by, rows=out)


@router.get("/analytics/weekly", response_model=list[WeeklyPoint], operation_id="analyticsWeekly")
def weekly(session: SessionDep, weeks: int = 8) -> list[WeeklyPoint]:
    weeks = max(1, min(weeks, 52))
    now = now_utc()
    targets = get_settings(session).targets
    out = []
    for back in range(weeks - 1, -1, -1):
        start = week_start(now, back)
        end = start + timedelta(weeks=1)
        out.append(WeeklyPoint(
            week_start=start,
            applied=_count_events(session, AppStatus.applied, start, end),
            calls=_count_events(session, CALL, start, end),
            referrals=_count_referrals(session, start, end),
            applied_target=targets.applied_per_week,
            referrals_target=targets.referrals_per_week,
        ))
    return out


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Nearest-rank percentile of an ascending list."""
    return sorted_values[max(math.ceil(len(sorted_values) * pct), 1) - 1]


@router.get("/analytics/response-times", response_model=ResponseTimes, operation_id="analyticsResponseTimes")
def response_times(session: SessionDep) -> ResponseTimes:
    by_app: dict[int, list[Event]] = defaultdict(list)
    for e in session.exec(select(Event).order_by(Event.at, Event.id)):
        by_app[e.application_id].append(e)
    days: list[float] = []
    for events in by_app.values():
        applied = next((e for e in events if e.to_status == AppStatus.applied), None)
        if applied is None:
            continue
        later = next((e for e in events if (e.at, e.id) > (applied.at, applied.id)), None)
        if later is not None:
            days.append((convert.as_utc(later.at) - convert.as_utc(applied.at)).total_seconds() / 86400)
    if not days:
        return ResponseTimes(samples=0)
    days.sort()
    return ResponseTimes(
        median_days_to_first_response=round(statistics.median(days), 2),
        p90_days_to_first_response=round(_percentile(days, 0.9), 2),
        samples=len(days),
    )


@router.get("/analytics/rejects", response_model=list[RejectAuditRow], operation_id="analyticsRejects")
def rejects(
    session: SessionDep, date_from: datetime | None = None, date_to: datetime | None = None
) -> list[RejectAuditRow]:
    """Prefilter drop audit: reasons with counts and sample leads (restorable from Leads)."""
    stmt = select(Lead.id, Lead.prefilter_reasons).where(Lead.prefilter_pass.is_(False))
    if date_from is not None:
        stmt = stmt.where(Lead.found_at >= db_dt(date_from))
    if date_to is not None:
        stmt = stmt.where(Lead.found_at <= db_dt(date_to))
    counts: Counter[str] = Counter()
    samples: dict[str, list[int]] = defaultdict(list)
    for lead_id, reasons in session.exec(stmt.order_by(Lead.id.desc())):
        for reason in reasons or ["unspecified"]:
            counts[reason] += 1
            if len(samples[reason]) < 5:
                samples[reason].append(lead_id)
    return [
        RejectAuditRow(reason=r, count=n, sample_lead_ids=samples[r])
        for r, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


@router.get("/analytics/insights", response_model=list[Insight], operation_id="analyticsInsights")
def insights(session: SessionDep, days: int = 30) -> list[Insight]:
    """Rule-based observations over the last `days` days (jobhunter.analytics.insights)."""
    raise todo()
