"""Follow-ups, business days and the ghosted rule.

Business days = Monday-Friday in Asia/Kolkata minus IST public holidays (built-in list for 2026-2027 national +
Tamil Nadu/Karnataka bank holidays, plus settings.followups.extra_holidays).

`run` (RunKind.followups, scheduled hourly 08:00-21:00 local) is idempotent:
  - Applied applications whose next_follow_up_at <= now and no follow-up Outreach yet -> create
    Outreach(kind=follow_up, application_id, lead_id, due_at=next_follow_up_at, draft=<template text>), and
    notify once ("Follow-up due: <company>"). A due unsent follow-up whose notification was skipped (quiet
    hours) is notified again on a later run; notify() de-duplicates by key.
  - first follow-up marked sent and still Applied -> next_follow_up_at = sent_at + second_follow_up_business_days;
    when that is due, one second follow-up is drafted (never a third). Once the second one is marked sent,
    next_follow_up_at is cleared.
  - Applied with no Event for settings.followups.ghosted_after_days -> Proposal(type=ghosted, application_id,
    payload {"to_status": "Ghosted"}), once per application (a dismissed proposal is not re-created).
  - Profile.refresh_due (e.g. Naukri daily) -> one notification per local day.
Never sends anything; drafts are copy-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from jobhunter import notify as notifier
from jobhunter.followups.holidays import HOLIDAYS
from jobhunter.models import (
    Application,
    AppStatus,
    Event,
    Lead,
    Outreach,
    OutreachKind,
    Profile,
    Proposal,
    ProposalType,
)
from jobhunter.schemas import Settings

LOCAL_TZ = ZoneInfo("Asia/Kolkata")


@dataclass
class FollowupResult:
    follow_ups_created: int = 0
    ghosted_proposals: int = 0
    notifications: int = 0

    def summary(self) -> str:
        return (f"{self.follow_ups_created} follow-ups due, {self.ghosted_proposals} ghosted proposals, "
                f"{self.notifications} notifications")


def _aware(dt: datetime) -> datetime:
    """Naive datetimes are UTC (models.py convention)."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _holidays(extra_holidays: list[str] | None) -> set[date]:
    days = set()
    for text in [*HOLIDAYS, *(extra_holidays or [])]:
        try:
            days.add(date.fromisoformat(text.strip()))
        except ValueError:
            continue  # a typo in settings must not break scheduling
    return days


def is_business_day(day: date, extra_holidays: list[str] | None = None) -> bool:
    return day.weekday() < 5 and day not in _holidays(extra_holidays)


def add_business_days(dt: datetime, days: int, extra_holidays: list[str] | None = None) -> datetime:
    """`dt` (aware) plus `days` IST business days, same local time of day. Replaces api.deps.add_weekdays."""
    dt = _aware(dt)
    if days <= 0:
        return dt
    off = _holidays(extra_holidays)
    local = dt.astimezone(LOCAL_TZ)
    while days > 0:
        local += timedelta(days=1)
        if local.weekday() < 5 and local.date() not in off:
            days -= 1
    return local.astimezone(dt.tzinfo)


def draft_follow_up(company: str, title: str, applied_at: datetime | None, second: bool = False) -> str:
    """Short, polite follow-up text the owner copies (no placeholders left unfilled except the recruiter name)."""
    when = f" on {_aware(applied_at).astimezone(LOCAL_TZ):%d %b %Y}" if applied_at else " recently"
    if second:
        return (
            f"Hi [recruiter name],\n\n"
            f"I'm following up once more on my application for the {title} role at {company}{when}. "
            f"I'm still very interested and would be glad to share anything that helps with the next step. "
            f"If the position has moved on, a quick note would be much appreciated.\n\n"
            f"Thank you for your time."
        )
    return (
        f"Hi [recruiter name],\n\n"
        f"I applied for the {title} role at {company}{when} and wanted to check on the status of my application. "
        f"I'm keen on the role and happy to provide any further details you need.\n\n"
        f"Thank you for your time."
    )


def _followup_rows(session: Session) -> dict[int, list[Outreach]]:
    by_app: dict[int, list[Outreach]] = {}
    rows = session.exec(
        select(Outreach).where(Outreach.kind == OutreachKind.follow_up, Outreach.application_id.is_not(None))
        .order_by(Outreach.id)
    )
    for row in rows:
        by_app.setdefault(row.application_id, []).append(row)
    return by_app


def _follow_ups(session: Session, settings: Settings, now: datetime, result: FollowupResult) -> None:
    rules = settings.followups
    rows = _followup_rows(session)
    applied = session.exec(
        select(Application, Lead).join(Lead, Lead.id == Application.lead_id)
        .where(Application.status == AppStatus.applied).order_by(Application.id)
    ).all()
    for app, lead in applied:
        mine = rows.get(app.id, [])
        sent = [o for o in mine if o.sent_at is not None]
        unsent = [o for o in mine if o.sent_at is None]
        due = _aware(app.next_follow_up_at) if app.next_follow_up_at else None
        if len(sent) == 1 and not unsent and (due is None or due <= _aware(sent[0].sent_at)):
            due = add_business_days(
                _aware(sent[0].sent_at), rules.second_follow_up_business_days, rules.extra_holidays)
            app.next_follow_up_at = due
            session.add(app)
        elif len(sent) >= 2 and due is not None and due <= _aware(sent[1].sent_at):
            app.next_follow_up_at = None  # at most one second follow-up
            session.add(app)
        if not mine and due is not None and due <= now:
            row = Outreach(
                application_id=app.id, lead_id=lead.id, kind=OutreachKind.follow_up, due_at=due,
                draft=draft_follow_up(lead.company, lead.title, app.applied_at))
            session.add(row)
            session.flush()
            unsent = [row]
            result.follow_ups_created += 1
        elif len(sent) == 1 and not unsent and due is not None and due <= now:
            row = Outreach(
                application_id=app.id, lead_id=lead.id, kind=OutreachKind.follow_up, due_at=due,
                draft=draft_follow_up(lead.company, lead.title, app.applied_at, second=True))
            session.add(row)
            session.flush()
            unsent = [row]
            result.follow_ups_created += 1
        session.commit()
        for row in unsent:
            if row.due_at is not None and _aware(row.due_at) <= now and (
                    row.snoozed_until is None or _aware(row.snoozed_until) <= now):
                result.notifications += notifier.notify(
                    session, settings, key=f"followup:{row.id}", title=f"Follow-up due: {lead.company}",
                    body=lead.title, now=now)


def _ghosted(session: Session, settings: Settings, now: datetime, result: FollowupResult) -> None:
    cutoff = timedelta(days=settings.followups.ghosted_after_days)
    seen = set(session.exec(
        select(Proposal.application_id).where(Proposal.type == ProposalType.ghosted)).all())
    last_event: dict[int, datetime] = {}
    for app_id, at in session.exec(select(Event.application_id, Event.at)):
        at = _aware(at)
        if app_id not in last_event or at > last_event[app_id]:
            last_event[app_id] = at
    applied = session.exec(
        select(Application, Lead).join(Lead, Lead.id == Application.lead_id)
        .where(Application.status == AppStatus.applied).order_by(Application.id)
    ).all()
    for app, lead in applied:
        if app.id in seen:
            continue
        last = last_event.get(app.id) or (_aware(app.applied_at) if app.applied_at else _aware(app.created_at))
        if now - last < cutoff:
            continue
        days = (now - last).days
        session.add(Proposal(
            type=ProposalType.ghosted, application_id=app.id, lead_id=lead.id, payload={"to_status": "Ghosted"},
            evidence=f"No response for {days} days since {last.astimezone(LOCAL_TZ):%d %b %Y}", confidence=0.6))
        result.ghosted_proposals += 1
    session.commit()


def _profiles(session: Session, settings: Settings, now: datetime, result: FollowupResult) -> None:
    today = now.astimezone(LOCAL_TZ).date().isoformat()
    for profile in session.exec(select(Profile).order_by(Profile.platform)):
        days = profile.refresh_every_days
        if days is None:
            continue
        last = _aware(profile.last_refreshed_at) if profile.last_refreshed_at else None
        if last is not None and now - last < timedelta(days=days):
            continue
        result.notifications += notifier.notify(
            session, settings, key=f"profile_refresh:{profile.platform}:{today}",
            title=f"Refresh your {profile.platform} profile", body="Open the Today page for the link", now=now)


def run(session: Session, settings: Settings, *, now: datetime | None = None) -> FollowupResult:
    now = _aware(now) if now else datetime.now(UTC)
    result = FollowupResult()
    _follow_ups(session, settings, now, result)
    _ghosted(session, settings, now, result)
    _profiles(session, settings, now, result)
    return result
