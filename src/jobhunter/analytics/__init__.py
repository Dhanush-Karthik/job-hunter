"""Rule-based insights for the Analytics page.

The funnel / breakdown / weekly / response-time / reject numbers stay in api/insight.py. This module turns them
into a few plain-English observations. Rules need minimum samples (>= 5 applies per source / channel / title /
variant, >= 5 responses, >= 5 dropped leads) before claiming anything; with fewer than 5 applies in the window
it returns one "info" insight saying how many more applies are needed.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from jobhunter.models import Application, AppStatus, Event, Lead
from jobhunter.schemas import Insight
from jobhunter.settings import get_settings

MIN_SAMPLE = 5
MAX_INSIGHTS = 6
MIN_RATE_GAP = 0.10  # percentage points (as a fraction) before two groups count as "different"


@dataclass
class _Group:
    key: str
    applied: int = 0
    calls: int = 0

    @property
    def rate(self) -> float:
        return self.calls / self.applied if self.applied else 0.0

    def line(self) -> str:
        return f"{self.calls} call{'s' if self.calls != 1 else ''} from {self.applied} applies ({self.rate:.0%})"


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _label(key: str) -> str:
    return key.replace("_", " ").capitalize() if key.islower() else key


def _groups(rows: list[tuple[str, bool]]) -> list[_Group]:
    """(key, got_call) per application -> groups with at least MIN_SAMPLE applies, best rate first."""
    acc: dict[str, _Group] = {}
    for key, call in rows:
        g = acc.setdefault(key, _Group(key))
        g.applied += 1
        g.calls += call
    big = [g for g in acc.values() if g.applied >= MIN_SAMPLE]
    return sorted(big, key=lambda g: (-g.rate, -g.applied, g.key))


def _spread(groups: list[_Group]) -> tuple[_Group, _Group] | None:
    if len(groups) < 2:
        return None
    best, worst = groups[0], groups[-1]
    return (best, worst) if best.rate - worst.rate >= MIN_RATE_GAP else None


def insights(session: Session, *, days: int = 30, now: datetime | None = None) -> list[Insight]:
    """At most 6 insights, most useful first: best/weak source by calls per apply, CV variant A vs B,
    apply channel, title cluster, weekly pace vs settings.targets, median response time, top prefilter drop."""
    now = _aware(now) if now else datetime.now(UTC)
    since = now - timedelta(days=days)
    events = session.exec(select(Event).where(Event.at >= since).order_by(Event.at, Event.id)).all()
    applied_at: dict[int, datetime] = {}
    for e in events:
        if e.to_status == AppStatus.applied and e.application_id not in applied_at:
            applied_at[e.application_id] = _aware(e.at)
    if len(applied_at) < MIN_SAMPLE:
        need = MIN_SAMPLE - len(applied_at)
        return [Insight(
            kind="pace", severity="info",
            text=(f"{len(applied_at)} applies in the last {days} days. Apply to {need} more "
                  f"to unlock source, CV and channel insights ({MIN_SAMPLE} are needed)."))]

    called = {e.application_id for e in session.exec(select(Event).where(Event.to_status == AppStatus.screening))}
    rows = session.exec(
        select(Application, Lead).join(Lead, Lead.id == Application.lead_id)
        .where(Application.id.in_(list(applied_at)))
    ).all()
    out: list[Insight] = []

    sources = _groups([(lead.source.value, app.id in called) for app, lead in rows])
    if sources and sources[0].calls:
        g = sources[0]
        out.append(Insight(kind="best_source", severity="good", metric=g.rate,
                           text=f"{_label(g.key)}: {g.line()}, best source in the last {days} days"))
    if len(sources) >= 2 and sources[-1].rate < sources[0].rate:
        g = sources[-1]
        out.append(Insight(kind="weak_source", severity="warn", metric=g.rate,
                           text=f"{_label(g.key)}: {g.line()}, the weakest source; spend less time there"))

    variants = {g.key: g for g in _groups([(app.resume_variant.value, app.id in called)
                                           for app, _ in rows if app.resume_variant])}
    if "A" in variants and "B" in variants and variants["A"].rate != variants["B"].rate:
        win, lose = sorted(variants.values(), key=lambda g: -g.rate)
        out.append(Insight(kind="variant", severity="info", metric=win.rate,
                           text=f"CV {win.key}: {win.line()} vs CV {lose.key}: {lose.line()}"))

    week = sum(1 for e in events if e.to_status == AppStatus.applied and _aware(e.at) >= now - timedelta(days=7))
    target = get_settings(session).targets.applied_per_week
    if week >= target:
        pace = Insight(kind="pace", severity="good", metric=float(week),
                       text=f"{week} applies in the last 7 days, on or above your target of {target}")
    elif week < 0.7 * target:
        pace = Insight(kind="pace", severity="warn", metric=float(week),
                       text=f"{week} applies in the last 7 days, behind your target of {target}")
    else:
        pace = Insight(kind="pace", severity="info", metric=float(week),
                       text=f"{week} applies in the last 7 days, close to your target of {target}")
    out.append(pace)

    if spread := _spread(_groups([(lead.apply_channel.value, app.id in called) for app, lead in rows])):
        best, worst = spread
        out.append(Insight(kind="channel", severity="info", metric=best.rate,
                           text=f"{_label(best.key)} applies: {best.line()} vs {_label(worst.key)}: {worst.line()}"))

    titles = _groups([(" ".join(lead.title.lower().split()), app.id in called) for app, lead in rows])
    if titles and titles[0].calls:
        g = titles[0]
        out.append(Insight(kind="title", severity="info", metric=g.rate,
                           text=f'"{g.key}" roles: {g.line()}, your best title so far'))

    first_response = _response_days(session, set(applied_at))
    if len(first_response) >= MIN_SAMPLE:
        median = statistics.median(first_response)
        out.append(Insight(kind="response_time", severity="info", metric=round(median, 1),
                           text=f"Companies take a median of {median:.1f} days to respond "
                                f"({len(first_response)} responses)"))

    drops: Counter[str] = Counter()
    for reasons in session.exec(select(Lead.prefilter_reasons).where(
            Lead.prefilter_pass.is_(False), Lead.found_at >= since)):
        drops.update(set(reasons or ["unspecified"]))
    total_dropped = sum(1 for _ in session.exec(
        select(Lead.id).where(Lead.prefilter_pass.is_(False), Lead.found_at >= since)))
    if total_dropped >= MIN_SAMPLE:
        reason, n = min(drops.items(), key=lambda kv: (-kv[1], kv[0]))
        out.append(Insight(kind="rejects", severity="info", metric=float(n),
                           text=f'Top prefilter drop: "{reason}" ({n} of {total_dropped} dropped leads); '
                                f"restore from Leads if it is too strict"))
    return out[:MAX_INSIGHTS]


def _response_days(session: Session, app_ids: set[int]) -> list[float]:
    by_app: dict[int, list[Event]] = defaultdict(list)
    for e in session.exec(select(Event).where(Event.application_id.in_(app_ids)).order_by(Event.at, Event.id)):
        by_app[e.application_id].append(e)
    days = []
    for events in by_app.values():
        applied = next((e for e in events if e.to_status == AppStatus.applied), None)
        later = next((e for e in events if applied and (e.at, e.id) > (applied.at, applied.id)), None)
        if applied and later:
            days.append((_aware(later.at) - _aware(applied.at)).total_seconds() / 86400)
    return days
