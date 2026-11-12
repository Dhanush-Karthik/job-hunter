"""Application status workflow shared by leads, applications and proposals (plan section 6.3 + Wave 2 rules)."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlmodel import Session, select

from jobhunter.api.deps import add_weekdays, fits, now_utc
from jobhunter.models import TRANSITIONS, Actor, Application, AppStatus, Event, Lead

MAIN_LINE = [AppStatus.new, AppStatus.shortlisted, AppStatus.ready, AppStatus.applied]


def unprocessable(field: str, msg: str, where: str = "body") -> HTTPException:
    """422 shaped like FastAPI's own validation errors, which is what the contract documents."""
    return HTTPException(422, [{"loc": [where, field], "msg": msg, "type": "value_error"}])


def detail_text(e: HTTPException) -> str:
    if isinstance(e.detail, list):
        return "; ".join(str(d.get("msg", d)) if isinstance(d, dict) else str(d) for d in e.detail)
    return str(e.detail)


def get_lead_or_404(session: Session, lead_id: int) -> Lead:
    lead = session.get(Lead, lead_id) if fits(lead_id) else None
    if lead is None:
        raise HTTPException(404, "lead not found")
    return lead


def get_application_or_404(session: Session, app_id: int) -> Application:
    app = session.get(Application, app_id) if fits(app_id) else None
    if app is None:
        raise HTTPException(404, "application not found")
    return app


def ensure_application(session: Session, lead_id: int) -> Application:
    """The lead's Application, created as New when it has none yet (no event: nothing changed)."""
    app = session.exec(select(Application).where(Application.lead_id == lead_id)).first()
    if app is None:
        app = Application(lead_id=lead_id)
        session.add(app)
        session.flush()
    return app


def _move(
    session: Session, app: Application, to: AppStatus, actor: Actor, note: str | None, at: datetime
) -> None:
    session.add(Event(application_id=app.id, from_status=app.status, to_status=to, at=at, actor=actor, note=note))
    app.status = to
    app.updated_at = at


def transition(
    session: Session,
    app: Application,
    to: AppStatus,
    *,
    rejected_at_stage: AppStatus | None = None,
    note: str | None = None,
    actor: Actor = Actor.owner,
) -> Application:
    """Move `app` to `to` or raise 409 (illegal) / 422 (Rejected without a stage). Does not commit.

    Applied from New/Shortlisted/Ready walks the main line, one Event per step; the auto steps are
    actor=system, note "quick apply".
    """
    now = now_utc()
    walk = to == AppStatus.applied and app.status in MAIN_LINE[:-1]
    if not walk and to not in TRANSITIONS[app.status]:
        raise HTTPException(409, f"cannot move {app.status.value} -> {to.value}")
    if to == AppStatus.rejected:
        if rejected_at_stage is None:
            raise unprocessable("rejected_at_stage", "rejected_at_stage is required when rejecting")
        app.rejected_at_stage = rejected_at_stage
    if walk:
        for step in MAIN_LINE[MAIN_LINE.index(app.status) + 1 : -1]:
            _move(session, app, step, Actor.system, "quick apply", now)
    _move(session, app, to, actor, note, now)
    if to == AppStatus.applied:
        app.applied_at = now
        app.next_follow_up_at = add_weekdays(now, 5)
    session.add(app)
    return app


def shortlist_lead(session: Session, lead: Lead) -> Application:
    app = ensure_application(session, lead.id)
    if app.status != AppStatus.shortlisted:
        transition(session, app, AppStatus.shortlisted)
    return app


def skip_lead(session: Session, lead: Lead, reason: str) -> Application:
    if not reason.strip():
        raise unprocessable("reason", "reason is required to skip")
    app = ensure_application(session, lead.id)
    if app.status != AppStatus.skipped:
        transition(session, app, AppStatus.skipped, note=reason.strip())
    return app


def restore_lead(lead: Lead) -> None:
    lead.restored = True
    lead.prefilter_pass = True
