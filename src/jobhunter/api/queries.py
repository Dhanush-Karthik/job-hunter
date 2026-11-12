"""Lead list query shared by GET /api/leads and the Today page."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import aliased
from sqlmodel import Session, select

from jobhunter.api.convert import FRESH_HOURS
from jobhunter.api.deps import db_dt, now_utc
from jobhunter.models import Application, ApplyChannel, AppStatus, Evaluation, Lead, Source


def lead_query(
    *,
    q: str | None = None,
    status: list[AppStatus] | None = None,
    source: list[Source] | None = None,
    channel: list[ApplyChannel] | None = None,
    min_score: float | None = None,
    fresh_only: bool = False,
    inbound_only: bool = False,
    include_rejected: bool = False,
    include_duplicates: bool = False,
    sort: str = "score",
    now: datetime | None = None,
):
    """Filtered + ordered `select(Lead)`. min_score filters quick_score (as the web mocks do)."""
    stmt = select(Lead).outerjoin(Application, Application.lead_id == Lead.id)
    if sort == "eval_score":
        e2 = aliased(Evaluation)
        latest = select(func.max(e2.id)).group_by(e2.lead_id)
        stmt = stmt.outerjoin(Evaluation, and_(Evaluation.lead_id == Lead.id, Evaluation.id.in_(latest)))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Lead.company.ilike(like), Lead.title.ilike(like), Lead.jd_text.ilike(like)))
    if status:
        cond = Application.status.in_(status)
        if AppStatus.new in status:
            cond = or_(cond, Application.id.is_(None))  # no application yet == New
        stmt = stmt.where(cond)
    if source:
        stmt = stmt.where(Lead.source.in_(source))
    if channel:
        stmt = stmt.where(Lead.apply_channel.in_(channel))
    if min_score is not None:
        stmt = stmt.where(Lead.quick_score >= min_score)
    if fresh_only:
        cutoff = db_dt((now or now_utc()) - timedelta(hours=FRESH_HOURS))
        stmt = stmt.where(or_(Lead.posted_at >= cutoff, and_(Lead.posted_at.is_(None), Lead.found_at >= cutoff)))
    if inbound_only:
        stmt = stmt.where(Lead.is_inbound.is_(True))
    if not include_rejected:
        stmt = stmt.where(or_(Lead.prefilter_pass.is_(True), Lead.restored.is_(True)))
    if not include_duplicates:
        l2 = aliased(Lead)
        primary = select(func.min(l2.id)).where(l2.dedupe_group.is_not(None)).group_by(l2.dedupe_group)
        stmt = stmt.where(or_(Lead.dedupe_group.is_(None), Lead.id.in_(primary)))
    return stmt.order_by(*_order(sort))


def _order(sort: str):
    if sort == "eval_score":
        return (Evaluation.score.desc().nulls_last(), Lead.quick_score.desc(), Lead.id.desc())
    if sort == "posted_at":
        return (Lead.posted_at.desc().nulls_last(), Lead.quick_score.desc(), Lead.id.desc())
    if sort == "found_at":
        return (Lead.found_at.desc(), Lead.id.desc())
    return (Lead.quick_score.desc(), Lead.found_at.desc(), Lead.id.desc())


def count(session: Session, stmt) -> int:
    return session.exec(select(func.count()).select_from(stmt.order_by(None).subquery())).one()
