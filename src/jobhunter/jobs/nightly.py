"""Nightly funnel: fresh intake -> pick the best new leads -> lean evaluation -> Today's picks.

Stages (all runs carry params {"nightly": "<IST date>"}; the key makes every stage idempotent per night):
  1. start()      at settings.nightly.time: keep the Mac awake, queue intake_boards + careerops_scan
                  (params stage="intake"). Skipped on a nearly empty battery.
  2. evaluate()   when both intakes finished (any outcome), or 50 minutes after start as a fallback: choose
                  settings.nightly.candidates leads (select_candidates) and queue one lean evaluate run each.
  3. picks()      read live by GET /api/today: evaluated leads with score >= pick_min_eval, ranked by
                  score + interview-call chance + freshness, at most picks_max.
catch_up() runs every 30 minutes until noon, so a Mac that slept through midnight still gets its run on waking.

Token budget: only `candidates` (default 40) LLM calls per night, never the backlog; a lead is evaluated once.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, time, timedelta

from sqlmodel import Session, select

from jobhunter.jobs import power, runner
from jobhunter.models import (
    Application,
    AppStatus,
    Evaluation,
    Lead,
    RoleFamily,
    Run,
    RunKind,
    RunState,
    SourceHealth,
    utcnow,
)
from jobhunter.pipeline.freshness import IST, age_hours, within_24h
from jobhunter.schemas import RunOut, Settings
from jobhunter.settings import get_settings

_logger = logging.getLogger(__name__)
now = utcnow  # tests override the clock
_ACTIVE = (RunState.queued, RunState.running)
_TERMINAL = (RunState.succeeded, RunState.failed, RunState.cancelled)
_OPEN = (AppStatus.new, AppStatus.shortlisted)
FALLBACK_AFTER = timedelta(minutes=50)
CATCH_UP_UNTIL = time(12, 0)
OTHER_ROLE_MIN_SCORE = 0.55  # non-target role families need a strong quick score to be evaluated
_CHANCE_BONUS = {"high": 0.5, "medium": 0.2, "low": 0.0}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def night_key(at: datetime | None = None) -> str:
    return _utc(at or now()).astimezone(IST).date().isoformat()


def _night_runs(session: Session, key: str) -> list[Run]:
    since = datetime.combine(datetime.fromisoformat(key).date(), time.min, IST).astimezone(UTC) - timedelta(hours=2)
    rows = session.exec(select(Run).where(Run.created_at >= since)).all()
    return [r for r in rows if r.params.get("nightly") == key]


def _available(session: Session, source: str, at: datetime) -> bool:
    health = session.get(SourceHealth, source)
    return health is None or (health.enabled and (health.paused_until is None or _utc(health.paused_until) <= at))


def start(*, reason: str = "schedule") -> list[Run]:
    """Stage 1. Returns the runs queued (empty if tonight already started or the battery is too low)."""
    with runner._lock, Session(runner.engine_factory()) as session:
        settings = get_settings(session)
        at = _utc(now())
        key = night_key(at)
        if not settings.nightly.enabled or _night_runs(session, key):
            return []
        ok, why = power.ok_to_run()
        if not ok:
            _logger.warning("nightly run postponed: %s", why)
            return []
        power.hold_awake(int(FALLBACK_AFTER.total_seconds()) + 3600)
        params = {"nightly": key, "stage": "intake", "reason": reason}
        runs = []
        if any(_available(session, site.value, at) for site in settings.query_matrix.sites):
            runs.append(runner.submit(RunKind.intake_boards, params=params))
        if _available(session, RunKind.careerops_scan.value, at):
            runs.append(runner.submit(RunKind.careerops_scan, params=params))
        _logger.info("nightly %s started (%s, %s): %d intake runs", key, reason, why, len(runs))
    if not runs:
        return evaluate(key)
    return runs


def on_run_finished(event: RunOut) -> None:
    """runner event hook: when tonight's last intake run ends, start stage 2."""
    key = event.params.get("nightly")
    if not key or event.params.get("stage") != "intake" or event.state not in _TERMINAL:
        return
    with Session(runner.engine_factory()) as session:
        if any(r.state in _ACTIVE for r in _night_runs(session, key) if r.params.get("stage") == "intake"):
            return
    evaluate(key)


def evaluate(key: str | None = None) -> list[Run]:
    """Stage 2. Queue lean evaluations for tonight's candidates; idempotent per night key."""
    with runner._lock, Session(runner.engine_factory()) as session:
        settings = get_settings(session)
        key = key or night_key()
        if any(r.kind == RunKind.evaluate for r in _night_runs(session, key)):
            return []
        leads = select_candidates(session, settings, _utc(now()))
        runs = [runner.submit(RunKind.evaluate, lead_id=lead.id, params={"nightly": key, "auto": True})
                for lead in leads]
        _logger.info("nightly %s: %d leads queued for lean evaluation", key, len(runs))
        return runs


def catch_up() -> list[Run]:
    """Every 30 min until noon: start a missed night, or force stage 2 if intake hung past the fallback."""
    with Session(runner.engine_factory()) as session:
        settings = get_settings(session)
        at = _utc(now())
        local = at.astimezone(IST)
        hour, minute = map(int, settings.nightly.time.split(":"))
        if not settings.nightly.enabled or not (time(hour, minute) <= local.time() < CATCH_UP_UNTIL):
            return []
        key = night_key(at)
        runs = _night_runs(session, key)
    if not runs:
        return start(reason="catch-up")
    intakes = [r for r in runs if r.params.get("stage") == "intake"]
    started = min(_utc(r.created_at) for r in intakes) if intakes else at
    if not any(r.kind == RunKind.evaluate for r in runs) and at - started >= FALLBACK_AFTER:
        return evaluate(key)
    return []


def _title_key(lead: Lead) -> tuple[str, str]:
    title = re.sub(r"\(.*?\)|[^a-z0-9 ]+", " ", lead.title.lower())
    return lead.company.strip().lower(), " ".join(title.split())


def select_candidates(session: Session, settings: Settings, at: datetime) -> list[Lead]:
    """Best unevaluated fresh leads: prefilter pass, primary of its dedupe group, posted (or found) within
    nightly.max_age_hours, quick_score >= nightly.min_quick_score, application New/none, never scored before,
    stated minimum experience <= nightly.max_exp_min (3), and role family P1/P2 (others need OTHER_ROLE_MIN_SCORE).
    Ranked by quick_score (+0.06 when posted within 24 h); recruiter-inbound leads first; at most
    nightly.per_company per company and one per (company, title)."""
    rules = settings.nightly
    leads = session.exec(select(Lead).where(
        Lead.prefilter_pass.is_(True), Lead.quick_score >= rules.min_quick_score,
        Lead.found_at >= at - timedelta(hours=rules.max_age_hours + 24 * 7),
    )).all()
    scored = set(session.exec(select(Evaluation.lead_id).where(Evaluation.score.is_not(None))).all())
    pending = set(session.exec(select(Run.lead_id).where(
        Run.kind == RunKind.evaluate, Run.state.in_(_ACTIVE))).all())
    apps = {a.lead_id: a.status for a in session.exec(select(Application)).all()}
    primary: dict[str, int] = {}
    for lead in leads:
        if lead.dedupe_group:
            primary[lead.dedupe_group] = min(primary.get(lead.dedupe_group, lead.id), lead.id)
    top_years = rules.max_exp_min
    pool = [
        lead for lead in leads
        if (not lead.dedupe_group or primary[lead.dedupe_group] == lead.id)
        and lead.id not in scored and lead.id not in pending
        and apps.get(lead.id, AppStatus.new) == AppStatus.new
        and age_hours(lead.posted_at, lead.found_at, at) <= rules.max_age_hours
        # Out of reach for an interview call: no tokens spent (the prefilter keeps them for recall).
        and (lead.is_inbound or lead.exp_min is None or lead.exp_min <= top_years)
        and (lead.is_inbound or lead.role_family != RoleFamily.other or lead.quick_score >= OTHER_ROLE_MIN_SCORE)
    ]

    def rank(lead: Lead) -> tuple[bool, float]:
        return lead.is_inbound, lead.quick_score + (0.06 if within_24h(lead.posted_at, lead.found_at, at) else 0)

    chosen: list[Lead] = []
    per_company: dict[str, int] = {}
    titles: set[tuple[str, str]] = set()
    for lead in sorted(pool, key=rank, reverse=True):
        company, title = _title_key(lead)
        if (company, title) in titles or per_company.get(company, 0) >= rules.per_company:
            continue
        titles.add((company, title))
        per_company[company] = per_company.get(company, 0) + 1
        chosen.append(lead)
        if len(chosen) >= rules.candidates:
            break
    return chosen


def pick_rank(lead: Lead, evaluation: Evaluation, at: datetime) -> float:
    return ((evaluation.score or 0) + _CHANCE_BONUS.get(evaluation.call_chance or "", 0.1)
            + (0.15 if within_24h(lead.posted_at, lead.found_at, at) else 0) + (0.3 if lead.is_inbound else 0))


def picks(session: Session, settings: Settings, at: datetime | None = None) -> list[Lead]:
    """Today's picks: latest evaluation newer than picks_window_hours with score >= pick_min_eval, still open
    (application New/Shortlisted or none), not known closed; a "low" call chance needs 4.0+. Best first."""
    at = _utc(at or now())
    rules = settings.nightly
    rows = session.exec(
        select(Evaluation, Lead).join(Lead, Lead.id == Evaluation.lead_id)
        .where(Evaluation.score.is_not(None), Evaluation.created_at >= at - timedelta(hours=rules.picks_window_hours))
        .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())
    ).all()
    apps = {a.lead_id: a.status for a in session.exec(select(Application)).all()}
    latest: dict[int, tuple[Evaluation, Lead]] = {}
    for evaluation, lead in rows:
        latest.setdefault(lead.id, (evaluation, lead))
    chosen = [
        (pick_rank(lead, ev, at), lead) for ev, lead in latest.values()
        if ev.score >= rules.pick_min_eval and ev.is_live is not False
        and apps.get(lead.id, AppStatus.new) in _OPEN
        and (ev.call_chance != "low" or ev.score >= 4.0)
        and (lead.is_inbound or lead.exp_min is None or lead.exp_min <= rules.max_exp_min)
    ]
    chosen.sort(key=lambda item: (-item[0], item[1].id))
    return [lead for _, lead in chosen[: rules.picks_max]]
