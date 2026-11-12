from __future__ import annotations

from fastapi import APIRouter, Query

from jobhunter.api._stub import todo
from jobhunter.models import RunKind, RunState
from jobhunter.schemas import IntakeRequest, RunLog, RunOut

router = APIRouter(prefix="/api", tags=["runs"])


@router.get("/runs", response_model=list[RunOut], operation_id="listRuns")
def list_runs(
    kind: RunKind | None = None,
    state: RunState | None = None,
    lead_id: int | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> list[RunOut]:
    raise todo()


@router.get(
    "/runs/stream",
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE: event 'run' data=RunOut"}},
    operation_id="streamRuns",
)
def stream_runs():
    raise todo()


@router.get("/runs/{run_id}", response_model=RunOut, operation_id="getRun")
def get_run(run_id: int) -> RunOut:
    raise todo()


@router.get("/runs/{run_id}/log", response_model=RunLog, operation_id="getRunLog")
def get_run_log(run_id: int, tail: int = Query(200, ge=1, le=5000)) -> RunLog:
    raise todo()


@router.post("/runs/{run_id}/cancel", response_model=RunOut, operation_id="cancelRun")
def cancel_run(run_id: int) -> RunOut:
    raise todo()


@router.post("/intake/run", response_model=list[RunOut], status_code=202, operation_id="runIntake")
def run_intake(body: IntakeRequest) -> list[RunOut]:
    raise todo()
