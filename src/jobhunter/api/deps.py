"""Shared FastAPI dependencies and small time helpers for the routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends
from sqlmodel import Session

from jobhunter.db import get_session
from jobhunter.pipeline.normalize import as_utc

SessionDep = Annotated[Session, Depends(get_session)]

LOCAL_TZ = ZoneInfo("Asia/Kolkata")  # the owner's calendar: weeks start Monday 00:00 IST

SQLITE_MAX_INT = 2**63 - 1

__all__ = ["LOCAL_TZ", "SQLITE_MAX_INT", "SessionDep", "add_weekdays", "as_utc", "db_dt", "fits", "now_utc", "week_start"]


def fits(n: int) -> bool:
    """False for ids SQLite cannot bind (they raise OverflowError); such a row cannot exist, so treat as missing."""
    return -SQLITE_MAX_INT <= n <= SQLITE_MAX_INT


def now_utc() -> datetime:
    return datetime.now(UTC)


def db_dt(dt: datetime) -> datetime:
    """Aware UTC for use as a query parameter (SQLModel's datetime type rejects naive values)."""
    return as_utc(dt)


def add_weekdays(dt: datetime, days: int) -> datetime:
    """`dt` plus `days` Monday-Friday days (holidays come in Wave 3)."""
    while days > 0:
        dt += timedelta(days=1)
        if dt.astimezone(LOCAL_TZ).weekday() < 5:
            days -= 1
    return dt


def week_start(now: datetime, weeks_back: int = 0) -> datetime:
    """Monday 00:00 Asia/Kolkata of the week containing `now` (minus `weeks_back` weeks), as aware UTC."""
    local = now.astimezone(LOCAL_TZ)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return (monday - timedelta(weeks=weeks_back)).astimezone(UTC)
