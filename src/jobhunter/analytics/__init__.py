"""Rule-based insights for the Analytics page (Wave 3 contract, lead-owned signatures; builder implements).

The funnel / breakdown / weekly / response-time / reject numbers stay in api/insight.py (Wave 2). This module
turns them into a few plain-English observations. Rules need minimum samples (e.g. >= 5 applies per source)
before claiming anything; with too little data return one "info" insight saying how many applies are needed.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from jobhunter.schemas import Insight


def insights(session: Session, *, days: int = 30, now: datetime | None = None) -> list[Insight]:
    """At most 6 insights, most useful first: best/weak source by calls per apply, CV variant A vs B,
    apply channel, title cluster, weekly pace vs settings.targets, median response time, top prefilter drop."""
    raise NotImplementedError
