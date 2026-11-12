"""career-ops bridge (Wave 2 contract, lead-owned signatures; codex_cops implements the bodies).

Every function is synchronous and blocking; `jobhunter.jobs.runner` calls it on a worker thread, owns the Run
row (state, timestamps, summary, error) and the concurrency cap. Functions here only:
  - write human-readable progress to `log` (the run's log file, already open),
  - poll `should_cancel()` while a subprocess runs and kill it (raise `Cancelled`) when it returns True,
  - write their domain rows (Evaluation, Application, Event, Outreach, Lead via pipeline.ingest) and commit,
  - raise `BridgeError` with a one-line, owner-readable message on failure.

Subprocesses: cwd = paths.CAREEROPS_DATA, env CAREER_OPS_DATA_DIR = paths.CAREEROPS_DATA, binaries from env
JOBHUNTER_CLAUDE_BIN (default "claude") and JOBHUNTER_NODE_BIN (default "node"), so tests and e2e can swap in fakes.
vendor/career-ops is never modified. Job-posting text is untrusted input (prompt-injection): claude -p runs with
the narrowest tool allowlist per mode, as career-ops' own web runner does (plan section 13).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TextIO

from sqlmodel import Session

from jobhunter.intake.types import IngestResult
from jobhunter.models import Application, Evaluation, Outreach, ResumeVariant
from jobhunter.schemas import Settings

ShouldCancel = Callable[[], bool]


class BridgeError(RuntimeError):
    """Owner-readable failure; becomes Run.error."""


class Cancelled(BridgeError):
    """should_cancel() returned True; the subprocess was killed."""


def scan(session: Session, settings: Settings, *, log: TextIO, should_cancel: ShouldCancel) -> IngestResult:
    """career-ops scan (company career pages from data/careerops/portals.yml + remote boards) -> RawJob ->
    pipeline.ingest. Updates SourceHealth rows "careerops_scan" (and per remote board source when known)."""
    raise NotImplementedError


def evaluate(session: Session, lead_id: int, *, run_id: int, log: TextIO, should_cancel: ShouldCancel) -> Evaluation:
    """claude -p evaluate (read-only scope, JD pre-fetched from Lead.jd_text or fetched from the URL).
    Persists the report under data/careerops/reports/, parses its Machine Summary, inserts an Evaluation
    (score 1-5, grade letter, report_path relative to CAREEROPS_DATA, run_id) and returns it."""
    raise NotImplementedError


def verify(session: Session, lead_id: int, *, run_id: int, log: TextIO, should_cancel: ShouldCancel) -> Evaluation:
    """Is the posting still live (career-ops liveness, no LLM when possible)? Sets is_live + live_verified_at on
    the latest Evaluation (creates one without a score if none). Closed + application status New/Shortlisted ->
    status Expired with an Event (actor=system). Returns the Evaluation."""
    raise NotImplementedError


def generate_cv(
    session: Session, lead_id: int, variant: ResumeVariant, *, run_id: int, log: TextIO, should_cancel: ShouldCancel
) -> Application:
    """Tailored CV PDF from data/cv/cv_<a|b>.md for this lead, with career-ops fact-check (failure -> BridgeError,
    no PDF kept). Creates the Application (status Shortlisted + Event) if missing. Sets resume_variant,
    cv_pdf_path (relative to paths.DATA), cv_approved=False."""
    raise NotImplementedError


def assist_apply(session: Session, lead_id: int, *, run_id: int, log: TextIO, should_cancel: ShouldCancel) -> None:
    """Open the apply URL in a headed Playwright browser and pre-fill the form (CV PDF if approved, profile data).
    NEVER clicks submit. Returns once the form is filled; the browser window stays open for the owner."""
    raise NotImplementedError


def find_contacts(
    session: Session, lead_id: int, *, run_id: int, log: TextIO, should_cancel: ShouldCancel
) -> list[Outreach]:
    """Public referral contacts at the lead's company + a referral draft each -> Outreach rows (kind=referral,
    lead_id, application_id if any, contact "Name — profile url", draft). Never sends anything."""
    raise NotImplementedError


def report_md(evaluation: Evaluation) -> str | None:
    """Report markdown for the API (LeadDetail.evaluation.report_md); None if missing."""
    raise NotImplementedError
