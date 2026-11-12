"""APScheduler wiring (Wave 2 contract, lead-owned signatures; codex_jobs implements the bodies).

Local timezone (Asia/Kolkata on the owner's Mac). Jobs, all via runner.submit:
  - intake_boards every settings.schedules.boards_every_hours inside boards_window [start, end)
  - careerops_scan at careerops_scan_times; when it succeeds -> auto_evaluate()
  - intake_gmail: Wave 3 (not scheduled yet)
Skips a source whose SourceHealth is disabled or paused. coalesce=True, max_instances=1, misfire grace 1 h.
"""

from __future__ import annotations

from sqlmodel import Session

from jobhunter.models import Run
from jobhunter.schemas import ServiceHealth, Settings


def start() -> None:
    """runner.recover_on_boot(), then start the scheduler with the jobs above from the DB settings. Idempotent."""
    raise NotImplementedError


def shutdown() -> None:
    raise NotImplementedError


def reload(settings: Settings) -> None:
    """Re-create the jobs after PUT /api/settings (new times / intervals)."""
    raise NotImplementedError


def is_running() -> bool:
    raise NotImplementedError


def services() -> list[ServiceHealth]:
    """For /api/health and the Today page: scheduler (next run times), claude CLI on PATH (or
    JOBHUNTER_CLAUDE_BIN), career-ops checked out + node_modules, playwright chromium, one row per board source
    from SourceHealth (ok = enabled, not paused, last run ok), gmail (ok=False, detail "Wave 3")."""
    raise NotImplementedError


def auto_evaluate(session: Session, settings: Settings) -> list[Run]:
    """Queue evaluate runs (params {"auto": true}) for the best unevaluated leads, up to
    settings.auto_evaluate_top_n per local day minus auto runs already created today. Candidates:
    prefilter_pass, primary of their dedupe group (lowest id), no Evaluation with a score in the last 14 days,
    application status New/Shortlisted (or none), found in the last 3 days, quick_score >= 0.45; best first."""
    raise NotImplementedError
