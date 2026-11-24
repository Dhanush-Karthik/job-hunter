from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import select
from sse_starlette.sse import EventSourceResponse

from jobhunter import secrets
from jobhunter.api.deps import SessionDep, fits
from jobhunter.jobs import nightly, runner
from jobhunter.models import Run, RunKind, RunState, Source, SourceHealth
from jobhunter.schemas import IntakeRequest, RunLog, RunOut

router = APIRouter(prefix="/api", tags=["runs"])

BOARD_SOURCES = {Source.linkedin, Source.naukri, Source.indeed, Source.glassdoor, Source.google}
GMAIL_SOURCES = {Source.gmail_alert, Source.gmail_inbound}


@router.get("/runs", response_model=list[RunOut], operation_id="listRuns")
def list_runs(
    session: SessionDep,
    kind: RunKind | None = None,
    state: RunState | None = None,
    lead_id: int | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> list[RunOut]:
    stmt = select(Run)
    if kind is not None:
        stmt = stmt.where(Run.kind == kind)
    if state is not None:
        stmt = stmt.where(Run.state == state)
    if lead_id is not None:
        if not fits(lead_id):
            return []
        stmt = stmt.where(Run.lead_id == lead_id)
    rows = session.exec(stmt.order_by(Run.created_at.desc(), Run.id.desc()).limit(limit))
    return [runner.to_out(r) for r in rows]


@router.get(
    "/runs/stream",
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE: event 'run' data=RunOut"}},
    operation_id="streamRuns",
)
async def stream_runs() -> EventSourceResponse:
    async def gen():
        async for out in runner.events():
            yield {"event": "run", "data": out.model_dump_json()}

    return EventSourceResponse(gen(), ping=15)


def _run(session: SessionDep, run_id: int) -> Run:
    run = session.get(Run, run_id) if fits(run_id) else None
    if run is None:
        raise HTTPException(404, "run not found")
    return run


@router.get("/runs/{run_id}", response_model=RunOut, operation_id="getRun")
def get_run(run_id: int, session: SessionDep) -> RunOut:
    return runner.to_out(_run(session, run_id))


@router.get("/runs/{run_id}/log", response_model=RunLog, operation_id="getRunLog")
def get_run_log(run_id: int, session: SessionDep, tail: int = Query(200, ge=1, le=5000)) -> RunLog:
    _run(session, run_id)
    try:
        text, truncated = runner.read_log(run_id, tail)
    except KeyError as e:
        raise HTTPException(404, "run not found") from e
    return RunLog(run_id=run_id, text=text, truncated=truncated)


@router.post("/runs/{run_id}/cancel", response_model=RunOut, operation_id="cancelRun")
def cancel_run(run_id: int, session: SessionDep) -> RunOut:
    _run(session, run_id)
    try:
        return runner.to_out(runner.cancel(run_id))
    except KeyError as e:
        raise HTTPException(404, "run not found") from e


def _intake_plan(session: SessionDep, sources: list[Source] | None) -> list[tuple[RunKind, dict | None]]:
    """Which runs an intake request starts, one per kind."""
    if sources is None:
        plan: list[tuple[RunKind, dict | None]] = [(RunKind.intake_boards, None)]
        scan = session.get(SourceHealth, Source.careerops_scan.value)
        if scan is None or scan.enabled:
            plan.append((RunKind.careerops_scan, None))
        if secrets.present("gmail_address") and secrets.present("gmail_app_password"):
            plan.append((RunKind.intake_gmail, None))
        return plan
    chosen = set(sources)
    boards = sorted(s.value for s in chosen & BOARD_SOURCES)
    plan = []
    if boards:
        plan.append((RunKind.intake_boards, {"sources": boards}))
    if chosen & GMAIL_SOURCES:
        plan.append((RunKind.intake_gmail, None))
    if chosen - BOARD_SOURCES - GMAIL_SOURCES - {Source.manual}:  # careerops_scan + remote boards
        plan.append((RunKind.careerops_scan, None))
    return plan


@router.post("/intake/run", response_model=list[RunOut], status_code=202, operation_id="runIntake")
def run_intake(body: IntakeRequest, session: SessionDep) -> list[RunOut]:
    return [runner.to_out(runner.submit(kind, params=params)) for kind, params in _intake_plan(session, body.sources)]


@router.post("/nightly/run", response_model=list[RunOut], status_code=202, operation_id="runNightly")
def run_nightly(stage: Literal["start", "evaluate"] = "start") -> list[RunOut]:
    """Run tonight's funnel now: start = fresh intake then lean evaluation; evaluate = skip intake. Idempotent per
    IST date (a second call the same day queues nothing)."""
    runs = nightly.start(reason="manual") if stage == "start" else nightly.evaluate()
    return [runner.to_out(r) for r in runs]
