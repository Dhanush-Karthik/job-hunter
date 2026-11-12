"""Follow-ups, business days and the ghosted rule (Wave 3 contract, lead-owned signatures; builder implements).

Business days = Monday-Friday in Asia/Kolkata minus IST public holidays (built-in list for 2026-2027 national +
Tamil Nadu/Karnataka bank holidays, plus settings.followups.extra_holidays).

`run` (RunKind.followups, scheduled hourly 08:00-21:00 local) is idempotent:
  - Applied applications whose next_follow_up_at <= now and no unsent follow-up Outreach -> create
    Outreach(kind=follow_up, application_id, lead_id, due_at=next_follow_up_at, draft=<template text>), and
    notify once ("Follow-up due: <company>").
  - follow-up marked sent and still Applied -> next_follow_up_at = sent_at + second_follow_up_business_days
    (one second follow-up at most).
  - Applied with no Event for settings.followups.ghosted_after_days -> Proposal(type=ghosted, application_id,
    payload {"to_status": "Ghosted"}), once per application.
  - Profile.refresh_due (e.g. Naukri daily) -> one notification per local day.
Never sends anything; drafts are copy-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlmodel import Session

from jobhunter.schemas import Settings


@dataclass
class FollowupResult:
    follow_ups_created: int = 0
    ghosted_proposals: int = 0
    notifications: int = 0

    def summary(self) -> str:
        return (f"{self.follow_ups_created} follow-ups due, {self.ghosted_proposals} ghosted proposals, "
                f"{self.notifications} notifications")


def is_business_day(day: date, extra_holidays: list[str] | None = None) -> bool:
    raise NotImplementedError


def add_business_days(dt: datetime, days: int, extra_holidays: list[str] | None = None) -> datetime:
    """`dt` (aware) plus `days` IST business days, same local time of day. Replaces api.deps.add_weekdays."""
    raise NotImplementedError


def draft_follow_up(company: str, title: str, applied_at: datetime | None, second: bool = False) -> str:
    """Short, polite follow-up text the owner copies (no placeholders left unfilled except the recruiter name)."""
    raise NotImplementedError


def run(session: Session, settings: Settings, *, now: datetime | None = None) -> FollowupResult:
    raise NotImplementedError
