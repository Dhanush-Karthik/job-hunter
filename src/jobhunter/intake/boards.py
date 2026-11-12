"""Rate-capped public JobSpy intake; scheduling is the caller's responsibility.

The JSON cursor stores an offset per site and the next site for round-robin
fairness when ``max_queries`` limits the whole run. Retries consume call caps.
"""

from __future__ import annotations

import hashlib
import math
import random
import time
from datetime import UTC, date, datetime, timedelta
from itertools import product
from typing import Any

import jobspy
import pandas as pd
from sqlmodel import Session

from jobhunter.intake.types import RawJob
from jobhunter.models import SettingRow, Source, SourceHealth
from jobhunter.schemas import Settings

CURSOR_KEY = "intake.boards.cursor"
BOARD_SITES = {"linkedin", "naukri", "indeed", "glassdoor", "google"}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return _json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _boolean(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "easy apply", "easy_apply"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
        return None
    if isinstance(value, (bool, int, float)):
        return bool(value)
    return None


def _posted_at(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        stamp = pd.to_datetime(value, utc=True)
        return None if pd.isna(stamp) else stamp.to_pydatetime()
    except (ValueError, TypeError, OverflowError):
        return None


def _map_row(row: dict, site: str, title: str, location: str) -> RawJob:
    raw = _json_safe(row)
    url = raw.get("job_url")
    skills = raw.get("skills") or []
    if isinstance(skills, str):
        skills = [part.strip() for part in skills.split(",") if part.strip()]
    easy_apply = None
    if site in {"linkedin", "naukri"}:
        for key in ("easy_apply", "is_easy_apply", "is_easy_application"):
            if raw.get(key) is not None:
                easy_apply = _boolean(raw[key])
                break
    return RawJob(
        source=Source(site),
        source_ref=str(raw.get("id") or hashlib.sha1((url or "").encode()).hexdigest()),
        title=raw.get("title") or "",
        company=raw.get("company") or "",
        location=raw.get("location"),
        job_url=url,
        apply_url=raw.get("job_url_direct"),
        description=raw.get("description"),
        posted_at=_posted_at(raw.get("date_posted")),
        is_remote=_boolean(raw.get("is_remote")),
        salary_min=raw.get("min_amount"),
        salary_max=raw.get("max_amount"),
        salary_interval=raw.get("interval"),
        currency=raw.get("currency"),
        experience_text=raw.get("experience_range") if site == "naukri" else None,
        skills=skills if site == "naukri" else [],
        job_level=raw.get("job_level"),
        easy_apply=easy_apply,
        source_detail=f"{title} @ {location}",
        raw=raw,
    )


def fetch_boards(
    session: Session,
    settings: Settings,
    *,
    scrape=jobspy.scrape_jobs,
    sleep=time.sleep,
    now: datetime | None = None,
    max_queries: int | None = None,
) -> list[RawJob]:
    """Fetch the next daily matrix slice and commit cursor + per-site health.

    ``max_queries`` caps total scrape calls (including retries). A site's first
    failed query stops that site for the run. Empty responses are successful.
    Disabled/paused sites keep their offsets and last-run health unchanged.
    Very large matrices take more than a day when the safety caps require it.
    """
    now = _utc(now or datetime.now(UTC))
    matrix = settings.query_matrix
    queries = list(product(matrix.titles, matrix.locations))
    sites = list(dict.fromkeys(str(site) for site in matrix.sites if str(site) in BOARD_SITES))
    if not queries or not sites or (max_queries is not None and max_queries <= 0):
        return []

    cursor = session.get(SettingRow, CURSOR_KEY) or SettingRow(key=CURSOR_KEY, value={})
    state = cursor.value if isinstance(cursor.value, dict) else {}
    offsets = dict(state.get("offsets", {}))
    start = int(state.get("next_site", 0)) % len(sites)
    ordered_sites = sites[start:] + sites[:start]
    window_start, window_end = settings.schedules.boards_window
    window_hours = (window_end - window_start) % 24 or 24
    runs_per_day = max(1, math.ceil(window_hours / settings.schedules.boards_every_hours))
    slice_size = math.ceil(len(queries) / runs_per_day)
    healths = {}
    quotas = {}
    calls = dict.fromkeys(sites, 0)
    counts = dict.fromkeys(sites, 0)
    errors = {}
    attempted = set()
    for site in sites:
        health = session.get(SourceHealth, site) or SourceHealth(source=site)
        if not health.enabled or (health.paused_until and _utc(health.paused_until) > now):
            continue
        healths[site] = health
        quotas[site] = min(slice_size, 6 if site == "linkedin" else 10)

    jobs = []
    total_calls = 0
    next_site = start
    while any(quota > 0 for quota in quotas.values()):
        for site in ordered_sites:
            if quotas.get(site, 0) <= 0:
                continue
            if max_queries is not None and total_calls >= max_queries:
                break
            index = int(offsets.get(site, 0)) % len(queries)
            title, location = queries[index]
            offsets[site] = (index + 1) % len(queries)
            quotas[site] -= 1
            attempted.add(site)
            next_site = (sites.index(site) + 1) % len(sites)
            remote = location.strip().lower() == "remote india"
            kwargs = {
                "site_name": [site], "search_term": title,
                "location": "India" if remote else location,
                "results_wanted": matrix.results_wanted, "hours_old": matrix.hours_old,
                "verbose": 0,
            }
            if remote:
                kwargs["is_remote"] = True
            if site in {"indeed", "glassdoor"}:
                kwargs["country_indeed"] = "India"
            if site == "linkedin":
                kwargs["linkedin_fetch_description"] = True
            if site == "naukri":
                kwargs["fetch_description"] = True
            cap = 6 if site == "linkedin" else 10
            for attempt in range(2):
                if total_calls:
                    sleep(random.uniform(2, 6))
                total_calls += 1
                calls[site] += 1
                try:
                    frame = scrape(**kwargs)
                    batch = [_map_row(row, site, title, location)
                             for row in frame.to_dict(orient="records")]
                    jobs.extend(batch)
                    counts[site] += len(batch)
                    break
                except Exception as exc:  # noqa: BLE001 — one bad scraper must not abort other sites
                    message = str(exc)
                    rate_limited = any(token in message.lower()
                                       for token in ("429", "too many requests", "blocked"))
                    budget_left = max_queries is None or total_calls < max_queries
                    if attempt == 0 and rate_limited and calls[site] < cap and budget_left:
                        # Consecutive failed runs double the initial retry delay (capped).
                        sleep(min(300, 2 ** min(healths[site].consecutive_failures + 3, 9)))
                        continue
                    errors[site] = message
                    quotas[site] = 0
                    break
            if calls[site] >= cap:
                quotas[site] = 0
        if max_queries is not None and total_calls >= max_queries:
            break

    for site in attempted:
        health = healths[site]
        health.last_run_at = now
        health.last_count = counts[site]
        if site in errors:
            health.last_error = errors[site]
            health.consecutive_failures += 1
            if health.consecutive_failures >= 3:
                health.paused_until = now + timedelta(hours=6)
        else:
            health.last_ok_at = now
            health.last_error = None
            health.consecutive_failures = 0
            health.paused_until = None
        session.add(health)
    cursor.value = {"offsets": offsets, "next_site": next_site}
    session.add(cursor)
    session.commit()
    return jobs
