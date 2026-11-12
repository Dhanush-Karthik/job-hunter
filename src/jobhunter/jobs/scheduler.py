"""APScheduler wiring.

Local timezone (Asia/Kolkata on the owner's Mac). Jobs, all via runner.submit:
  - intake_boards every settings.schedules.boards_every_hours inside boards_window [start, end)
  - careerops_scan at careerops_scan_times; when it succeeds -> auto_evaluate()
  - intake_gmail every settings.schedules.gmail_every_minutes; each firing is skipped quietly unless both Gmail
    secrets are in the Keychain and SourceHealth "gmail_alert" is enabled and not paused
  - followups hourly 08:00-21:00 local
Skips a source whose SourceHealth is disabled or paused. coalesce=True, max_instances=1, misfire grace 1 h.
"""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from keyring.errors import KeyringError
from sqlmodel import Session, select

from jobhunter import gmail, paths, secrets
from jobhunter.jobs import runner
from jobhunter.models import (
    Application,
    AppStatus,
    Evaluation,
    Lead,
    Run,
    RunKind,
    RunState,
    Source,
    SourceHealth,
    utcnow,
)
from jobhunter.schemas import RunOut, ServiceHealth, Settings
from jobhunter.settings import get_settings

TIMEZONE = ZoneInfo("Asia/Kolkata")
now = utcnow  # Override the clock in tests without changing the public contract.
_scheduler = BackgroundScheduler(
    timezone=TIMEZONE,
    job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600},
)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _available(health: SourceHealth | None, at: datetime) -> bool:
    return health is None or (
        health.enabled and (health.paused_until is None or _utc(health.paused_until) <= at)
    )


def _gmail_configured() -> bool:
    try:
        return all(secrets.present(name) for name in secrets.NAMES)
    except KeyringError:
        return False


def _scheduled(kind: RunKind) -> None:
    if kind == RunKind.intake_gmail and not _gmail_configured():
        return
    with Session(runner.engine_factory()) as session:
        settings = get_settings(session)
        at = _utc(now())
        if kind == RunKind.intake_boards:
            if not any(
                _available(session.get(SourceHealth, site.value), at) for site in settings.query_matrix.sites
            ):
                return
        elif kind == RunKind.intake_gmail:
            if not _available(session.get(SourceHealth, Source.gmail_alert.value), at):
                return
        elif not _available(session.get(SourceHealth, kind.value), at):
            return
    runner.submit(kind)


def _scan_finished(event: RunOut) -> None:
    if event.kind in (RunKind.careerops_scan, RunKind.intake_remote) and event.state == RunState.succeeded:
        with Session(runner.engine_factory()) as session:
            auto_evaluate(session, get_settings(session))


def start() -> None:
    """runner.recover_on_boot(), then start the scheduler with the jobs above from the DB settings. Idempotent."""
    if is_running():
        return
    with runner._lock:
        runner._accepting = True
    runner.recover_on_boot()
    with Session(runner.engine_factory()) as session:
        settings = get_settings(session)
    if _scan_finished not in runner.event_hooks:
        runner.event_hooks.append(_scan_finished)
    reload(settings)
    _scheduler.start()


def shutdown() -> None:
    global _scheduler
    if _scan_finished in runner.event_hooks:
        runner.event_hooks.remove(_scan_finished)
    if is_running():
        _scheduler.shutdown(wait=False)
    else:
        _scheduler.remove_all_jobs()
    # APScheduler's executors cannot restart after shutdown.
    _scheduler = BackgroundScheduler(
        timezone=TIMEZONE,
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600},
    )
    runner.shutdown()


def reload(settings: Settings) -> None:
    """Re-create the jobs after PUT /api/settings (new times / intervals)."""
    _scheduler.remove_all_jobs()
    start_hour, end_hour = settings.schedules.boards_window
    if not (0 <= start_hour < 24 and 0 <= end_hour <= 24):
        raise ValueError("boards_window hours must be between 0 and 24")
    hours = (
        list(range(start_hour, end_hour))
        if end_hour >= start_hour
        else (list(range(start_hour, 24)) + list(range(end_hour)))
    )
    hours = hours[:: settings.schedules.boards_every_hours]
    if hours:
        _scheduler.add_job(
            _scheduled,
            CronTrigger(hour=",".join(map(str, hours)), minute=0, timezone=TIMEZONE),
            args=[RunKind.intake_boards],
            id="intake_boards",
            replace_existing=True,
        )
    for clock in sorted(set(settings.schedules.careerops_scan_times)):
        hour, minute = map(int, clock.split(":"))
        _scheduler.add_job(
            _scheduled,
            CronTrigger(hour=hour, minute=minute, timezone=TIMEZONE),
            args=[RunKind.careerops_scan],
            id=f"careerops_scan_{hour:02d}{minute:02d}",
            replace_existing=True,
        )
    _scheduler.add_job(
        _scheduled,
        IntervalTrigger(minutes=settings.schedules.gmail_every_minutes, timezone=TIMEZONE),
        args=[RunKind.intake_gmail],
        id="intake_gmail",
        replace_existing=True,
    )
    _scheduler.add_job(
        _scheduled,
        CronTrigger(hour="8-21", minute=0, timezone=TIMEZONE),
        args=[RunKind.followups],
        id="followups",
        replace_existing=True,
    )


def is_running() -> bool:
    return _scheduler.running


def services() -> list[ServiceHealth]:
    """For /api/health and the Today page: scheduler (next run times), claude CLI on PATH (or
    JOBHUNTER_CLAUDE_BIN), career-ops checked out + node_modules, playwright chromium, one row per board source
    from SourceHealth (ok = enabled, not paused, last run ok), gmail via gmail.health."""
    at = _utc(now())
    next_runs = []
    for job in _scheduler.get_jobs():
        upcoming = getattr(job, "next_run_time", None)
        if upcoming is None:
            upcoming = job.trigger.get_next_fire_time(None, at)
        next_runs.append(f"{job.id}: {upcoming.astimezone(TIMEZONE).isoformat()}" if upcoming else job.id)
    claude = shutil.which(os.environ.get("JOBHUNTER_CLAUDE_BIN", "claude"))
    vendor_ok = (paths.CAREEROPS_VENDOR / "package.json").is_file()
    deps_ok = (paths.CAREEROPS_VENDOR / "node_modules").is_dir()
    chromium = any((Path.home() / "Library/Caches/ms-playwright").glob("chromium*"))
    result = [
        ServiceHealth(name="scheduler", ok=is_running(), detail="; ".join(next_runs) or "no jobs scheduled"),
        ServiceHealth(name="claude", ok=bool(claude), detail=claude or "claude CLI not found"),
        ServiceHealth(
            name="career-ops",
            ok=vendor_ok and deps_ok,
            detail="ready" if vendor_ok and deps_ok else "checkout or node_modules missing",
        ),
        ServiceHealth(name="playwright chromium", ok=chromium, detail="installed" if chromium else "not installed"),
    ]
    with Session(runner.engine_factory()) as session:
        settings = get_settings(session)
        for site in settings.query_matrix.sites:
            health = session.get(SourceHealth, site.value)
            ok = bool(
                health
                and _available(health, at)
                and health.last_ok_at
                and not health.last_error
                and not health.consecutive_failures
                and (not health.last_run_at or _utc(health.last_ok_at) >= _utc(health.last_run_at))
            )
            detail = "not run yet"
            if health:
                if not health.enabled:
                    detail = "disabled"
                elif health.paused_until and _utc(health.paused_until) > at:
                    detail = f"paused until {_utc(health.paused_until).isoformat()}"
                else:
                    detail = (
                        health.last_error or f"{health.last_count} fetched; last run {health.last_run_at}"
                    )
            result.append(ServiceHealth(name=site.value, ok=ok, detail=detail))
        try:
            result.append(gmail.health(session))
        except Exception as exc:  # noqa: BLE001 - a broken probe is a red row, not a failed health check
            result.append(ServiceHealth(name="gmail", ok=False, detail=str(exc) or type(exc).__name__))
    return result


def auto_evaluate(session: Session, settings: Settings) -> list[Run]:
    """Queue evaluate runs (params {"auto": true}) for the best unevaluated leads, up to
    settings.auto_evaluate_top_n per local day minus auto runs already created today. Candidates:
    prefilter_pass, primary of their dedupe group (lowest id), no Evaluation with a score in the last 14 days,
    application status New/Shortlisted (or none), found in the last 3 days, quick_score >= 0.45; best first."""
    # Serialize selection and submission with other submissions, including scan-success observers.
    with runner._lock:
        at = _utc(now())
        local_midnight = datetime.combine(at.astimezone(TIMEZONE).date(), time.min, TIMEZONE)
        start_day = local_midnight.astimezone(UTC)
        end_day = (local_midnight + timedelta(days=1)).astimezone(UTC)
        runs = session.exec(
            select(Run).where(
                Run.kind == RunKind.evaluate,
                Run.created_at >= start_day,
                Run.created_at < end_day,
            )
        ).all()
        remaining = max(0, settings.auto_evaluate_top_n - sum(r.params.get("auto") is True for r in runs))
        if not remaining:
            return []
        leads = session.exec(select(Lead).order_by(Lead.quick_score.desc(), Lead.id)).all()
        applications = {a.lead_id: a.status for a in session.exec(select(Application)).all()}
        evaluated = set(
            session.exec(
                select(Evaluation.lead_id).where(
                    Evaluation.score.is_not(None),
                    Evaluation.created_at >= at - timedelta(days=14),
                )
            ).all()
        )
        pending = set(
            session.exec(
                select(Run.lead_id).where(
                    Run.kind == RunKind.evaluate,
                    Run.state.in_((RunState.queued, RunState.running)),
                )
            ).all()
        )
        primary: dict[str, int] = {}
        for lead in leads:
            if lead.dedupe_group:
                primary[lead.dedupe_group] = min(primary.get(lead.dedupe_group, lead.id), lead.id)
        candidates = [
            lead
            for lead in leads
            if (
                lead.prefilter_pass
                and lead.quick_score >= 0.45
                and at - timedelta(days=3) <= _utc(lead.found_at) <= at
                and (not lead.dedupe_group or primary[lead.dedupe_group] == lead.id)
                and lead.id not in evaluated
                and lead.id not in pending
                and applications.get(lead.id, AppStatus.new) in (AppStatus.new, AppStatus.shortlisted)
            )
        ]
        return [
            runner.submit(RunKind.evaluate, lead_id=lead.id, params={"auto": True})
            for lead in candidates[:remaining]
        ]
