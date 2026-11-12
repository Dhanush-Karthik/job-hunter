"""Run engine (Wave 2 contract, lead-owned signatures; codex_jobs implements the bodies).

A Run row is the unit of background work. `submit` inserts it as queued and hands it to a worker pool:
  - LLM/browser kinds (evaluate, cv, contacts, assist_apply, verify) share one pool of
    settings.claude_concurrency workers,
  - intake kinds (intake_boards, intake_remote, careerops_scan, intake_gmail) share a single worker.
The worker sets running/started_at, opens data/logs/runs/<id>.log (Run.log_path), calls the matching function
(intake.boards.fetch_boards + pipeline.ingest, or jobhunter.careerops.*), then writes succeeded/failed/cancelled,
finished_at, summary, error. Every state change is published to subscribers (SSE).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from jobhunter.models import Run, RunKind
from jobhunter.schemas import RunOut


def submit(kind: RunKind, *, lead_id: int | None = None, params: dict[str, Any] | None = None) -> Run:
    """Queue a run and return the committed row. If a queued/running run with the same kind and lead_id exists,
    return that one instead (no duplicate work). Raises ValueError for a lead_id that does not exist."""
    raise NotImplementedError


def cancel(run_id: int) -> Run:
    """Queued -> cancelled immediately; running -> should_cancel() turns True and the worker ends it as cancelled.
    Finished runs are returned unchanged. Raises KeyError if missing."""
    raise NotImplementedError


def read_log(run_id: int, tail: int = 200) -> tuple[str, bool]:
    """Last `tail` lines of the run log and whether lines were cut. Raises KeyError if the run is missing."""
    raise NotImplementedError


def to_out(run: Run) -> RunOut:
    raise NotImplementedError


async def events() -> AsyncIterator[RunOut]:
    """Async stream of RunOut on every run state change (for GET /api/runs/stream). One iterator per client."""
    raise NotImplementedError
    yield  # pragma: no cover


def recover_on_boot() -> int:
    """Mark runs left queued/running by a previous process as failed ("server restarted"). Returns the count."""
    raise NotImplementedError


def shutdown(wait: bool = False) -> None:
    """Stop accepting work, signal running subprocesses to cancel, stop the pools."""
    raise NotImplementedError
