"""Today page and analytics."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter

from jobhunter.api._stub import todo
from jobhunter.schemas import Breakdown, Funnel, RejectAuditRow, ResponseTimes, TodaySummary, WeeklyPoint

router = APIRouter(prefix="/api", tags=["insight"])


@router.get("/today", response_model=TodaySummary, operation_id="getToday")
def today() -> TodaySummary:
    raise todo()


@router.get("/analytics/funnel", response_model=Funnel, operation_id="analyticsFunnel")
def funnel(date_from: datetime | None = None, date_to: datetime | None = None) -> Funnel:
    raise todo()


@router.get("/analytics/breakdown", response_model=Breakdown, operation_id="analyticsBreakdown")
def breakdown(
    by: Literal["source", "channel", "title", "variant", "role_family"],
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Breakdown:
    raise todo()


@router.get("/analytics/weekly", response_model=list[WeeklyPoint], operation_id="analyticsWeekly")
def weekly(weeks: int = 8) -> list[WeeklyPoint]:
    raise todo()


@router.get("/analytics/response-times", response_model=ResponseTimes, operation_id="analyticsResponseTimes")
def response_times() -> ResponseTimes:
    raise todo()


@router.get("/analytics/rejects", response_model=list[RejectAuditRow], operation_id="analyticsRejects")
def rejects(date_from: datetime | None = None, date_to: datetime | None = None) -> list[RejectAuditRow]:
    """Prefilter drop audit: reasons with counts and sample leads (restorable from Leads)."""
    raise todo()
