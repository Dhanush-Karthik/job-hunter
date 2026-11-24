"""Posting age, honest about date-only postings.

Naukri, Indeed, LinkedIn and Glassdoor (via JobSpy) give a calendar date only, stored as 00:00:00 UTC. For those,
"posted within 24 h" means the posting's date is today or yesterday in IST: a midnight run then covers exactly the
previous day. Postings with a real timestamp use the exact age; postings with no date use found_at.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from jobhunter.pipeline.normalize import as_utc

IST = ZoneInfo("Asia/Kolkata")


def is_date_only(posted_at: datetime | None) -> bool:
    if posted_at is None:
        return False
    value = as_utc(posted_at)
    return (value.hour, value.minute, value.second, value.microsecond) == (0, 0, 0, 0)


def age_hours(posted_at: datetime | None, found_at: datetime, now: datetime) -> float:
    ref = as_utc(posted_at) or as_utc(found_at)
    return max(0.0, (as_utc(now) - ref).total_seconds() / 3600)


def within_24h(posted_at: datetime | None, found_at: datetime, now: datetime) -> bool:
    if is_date_only(posted_at):
        return as_utc(posted_at).date() >= as_utc(now).astimezone(IST).date() - timedelta(days=1)
    return age_hours(posted_at, found_at, now) <= 24
