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

import asyncio
import logging
import threading
import traceback
from collections import deque
from collections.abc import AsyncIterator, Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from typing import Any, TextIO

from sqlmodel import Session, select

from jobhunter import careerops, paths
from jobhunter.db import get_engine
from jobhunter.models import Lead, ResumeVariant, Run, RunKind, RunState, utcnow
from jobhunter.schemas import RunOut
from jobhunter.settings import get_settings

engine_factory = get_engine
executor_factory = ThreadPoolExecutor
# Synchronous observers receive the same snapshots as SSE clients (also useful for tests).
event_hooks: list[Callable[[RunOut], None]] = []
_lock = threading.RLock()
_subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[RunOut]]] = set()
_cancel_flags: dict[int, threading.Event] = {}
_claude_pool: Executor | None = None
_intake_pool: Executor | None = None
_accepting = True
_CLAUDE_KINDS = {RunKind.evaluate, RunKind.verify, RunKind.cv, RunKind.contacts, RunKind.assist_apply}
_ACTIVE = (RunState.queued, RunState.running)
_logger = logging.getLogger(__name__)


def _publish(run: Run) -> None:
    snapshot = to_out(run)
    with _lock:
        subscribers = tuple(_subscribers)
        hooks = tuple(event_hooks)
    for loop, queue in subscribers:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, snapshot.model_copy(deep=True))
        except RuntimeError:  # A disconnected client's event loop may already have closed.
            with _lock:
                _subscribers.discard((loop, queue))
    for hook in hooks:
        try:
            hook(snapshot.model_copy(deep=True))
        except Exception:
            _logger.exception("Run event observer failed")


def _dispatch(session: Session, run: Run, log: TextIO, flag: threading.Event) -> str:
    with _lock:
        settings = get_settings(session)
        session.rollback()
    if run.kind == RunKind.intake_gmail:
        return "Gmail intake arrives in Wave 3"
    if run.kind == RunKind.intake_boards:
        from jobhunter.intake import boards
        from jobhunter.pipeline import ingest

        raws = boards.fetch_boards(session, settings)
        if flag.is_set():
            raise careerops.Cancelled("cancelled")
        return ingest(session, raws, settings).summary()
    if run.kind in (RunKind.careerops_scan, RunKind.intake_remote):
        return careerops.scan(session, settings, log=log, should_cancel=flag.is_set).summary()
    kwargs = {"run_id": run.id, "log": log, "should_cancel": flag.is_set}
    if run.kind == RunKind.cv:
        careerops.generate_cv(session, run.lead_id, ResumeVariant(run.params["variant"]), **kwargs)
    else:
        function = {
            RunKind.evaluate: careerops.evaluate,
            RunKind.verify: careerops.verify,
            RunKind.contacts: careerops.find_contacts,
            RunKind.assist_apply: careerops.assist_apply,
        }.get(run.kind)
        if function is None:
            raise ValueError(f"unsupported run kind: {run.kind}")
        function(session, run.lead_id, **kwargs)
    return f"{run.kind.value} completed"


def _work(run_id: int, flag: threading.Event) -> None:
    try:
        with Session(engine_factory()) as session:
            with _lock:
                run = session.get(Run, run_id)
                if run is None or run.state != RunState.queued:
                    session.rollback()
                    return
                run.state = RunState.running
                run.started_at = utcnow()
                run.log_path = f"logs/runs/{run_id}.log"
                session.add(run)
                session.commit()
                session.refresh(run)
                session.expunge(run)
                session.rollback()
                _publish(run)
            state, summary, error = RunState.succeeded, None, None
            try:
                paths.RUN_LOGS.mkdir(parents=True, exist_ok=True)
                with (paths.RUN_LOGS / f"{run_id}.log").open("a", encoding="utf-8", buffering=1) as log:
                    log.write(f"Starting {run.kind.value}\n")
                    try:
                        if flag.is_set():
                            raise careerops.Cancelled("cancelled")
                        summary = _dispatch(session, run, log, flag)
                        if flag.is_set():
                            raise careerops.Cancelled("cancelled")
                    except careerops.Cancelled as exc:
                        state, error = RunState.cancelled, str(exc)
                    except careerops.BridgeError as exc:
                        state, error = RunState.failed, str(exc)
                    except Exception as exc:  # noqa: BLE001 - every task failure must become a Run result
                        state, error = RunState.failed, f"internal error: {type(exc).__name__}: {exc}"
                        traceback.print_exc(file=log)
                    log.write(f"{state.value}: {error or summary or ''}\n")
            except Exception as exc:
                state, error = RunState.failed, f"internal error: {type(exc).__name__}: {exc}"
                _logger.exception("Could not open run log for %s", run_id)
            with _lock:
                session.rollback()  # Bridge failures may leave a transaction needing rollback.
                session.expire_all()
                run = session.get(Run, run_id)
                if run is None:
                    session.rollback()
                    return
                if flag.is_set():
                    state, summary, error = RunState.cancelled, None, "cancelled"
                run.state, run.summary, run.error = state, summary, error
                run.finished_at = utcnow()
                session.add(run)
                session.commit()
                session.refresh(run)
                session.expunge(run)
                session.rollback()
                _publish(run)
    finally:
        with _lock:
            _cancel_flags.pop(run_id, None)


def submit(kind: RunKind, *, lead_id: int | None = None, params: dict[str, Any] | None = None) -> Run:
    """Queue a run and return the committed row. If a queued/running run with the same kind and lead_id exists,
    return that one instead (no duplicate work). Raises ValueError for a lead_id that does not exist."""
    global _claude_pool, _intake_pool
    kind = RunKind(kind)
    with _lock:
        if not _accepting:
            raise RuntimeError("run engine is shutting down")
        with Session(engine_factory()) as session:
            if lead_id is not None and session.get(Lead, lead_id) is None:
                raise ValueError(f"lead {lead_id} does not exist")
            existing = session.exec(
                select(Run)
                .where(Run.kind == kind, Run.lead_id == lead_id, Run.state.in_(_ACTIVE))
                .order_by(Run.id)
            ).first()
            if existing is not None:
                return existing
            settings = get_settings(session)
            run = Run(kind=kind, lead_id=lead_id, params=dict(params or {}), created_at=utcnow())
            session.add(run)
            session.commit()
            session.refresh(run)
            flag = threading.Event()
            _cancel_flags[run.id] = flag
            _publish(run)
            if kind in _CLAUDE_KINDS:
                if _claude_pool is None:
                    _claude_pool = executor_factory(
                        max_workers=settings.claude_concurrency, thread_name_prefix="jobhunter-claude"
                    )
                pool = _claude_pool
            else:
                if _intake_pool is None:
                    _intake_pool = executor_factory(max_workers=1, thread_name_prefix="jobhunter-intake")
                pool = _intake_pool
            try:
                pool.submit(_work, run.id, flag)
            except Exception as exc:  # noqa: BLE001 - executor rejection must become a Run result
                run.state, run.error = RunState.failed, f"internal error: {type(exc).__name__}: {exc}"
                run.finished_at = utcnow()
                session.add(run)
                session.commit()
                session.refresh(run)
                _cancel_flags.pop(run.id, None)
                _publish(run)
            return run


def cancel(run_id: int) -> Run:
    """Queued -> cancelled immediately; running -> should_cancel() turns True and the worker ends it as cancelled.
    Finished runs are returned unchanged. Raises KeyError if missing."""
    with _lock, Session(engine_factory()) as session:
        run = session.get(Run, run_id)
        if run is None:
            raise KeyError(run_id)
        if run.state not in _ACTIVE:
            return run
        _cancel_flags.setdefault(run_id, threading.Event()).set()
        if run.state == RunState.queued:
            run.state, run.finished_at = RunState.cancelled, utcnow()
            session.add(run)
            session.commit()
            session.refresh(run)
            _publish(run)
        return run


def read_log(run_id: int, tail: int = 200) -> tuple[str, bool]:
    """Last `tail` lines of the run log and whether lines were cut. Raises KeyError if the run is missing."""
    with _lock, Session(engine_factory()) as session:
        run = session.get(Run, run_id)
        if run is None:
            raise KeyError(run_id)
        if not run.log_path:
            return "", False
    path = paths.RUN_LOGS / f"{run_id}.log"
    if not path.exists():
        return "", False
    count = max(0, tail)
    with path.open(encoding="utf-8", errors="replace") as log:
        lines = deque(log, maxlen=count + 1)
    truncated = len(lines) > count
    return "".join(list(lines)[-count:]) if count else "", truncated


def to_out(run: Run) -> RunOut:
    return RunOut.model_validate(run, from_attributes=True)


async def events() -> AsyncIterator[RunOut]:
    """Async stream of RunOut on every run state change (for GET /api/runs/stream). One iterator per client."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[RunOut] = asyncio.Queue()
    subscriber = (loop, queue)
    with _lock:
        _subscribers.add(subscriber)
    try:
        while True:
            yield await queue.get()
    finally:
        with _lock:
            _subscribers.discard(subscriber)


def recover_on_boot() -> int:
    """Mark runs left queued/running by a previous process as failed ("server restarted"). Returns the count."""
    with _lock, Session(engine_factory()) as session:
        runs = session.exec(select(Run).where(Run.state.in_(_ACTIVE))).all()
        for run in runs:
            run.state, run.error, run.finished_at = RunState.failed, "server restarted", utcnow()
            session.add(run)
        session.commit()
        for run in runs:
            session.refresh(run)
            _publish(run)
        return len(runs)


def shutdown(wait: bool = False) -> None:
    """Stop accepting work, signal running subprocesses to cancel, stop the pools."""
    global _accepting, _claude_pool, _intake_pool
    with _lock:
        _accepting = False
        for run_id in tuple(_cancel_flags):
            cancel(run_id)
        pools = (_claude_pool, _intake_pool)
        _claude_pool = _intake_pool = None
    for pool in pools:
        if pool is not None:
            pool.shutdown(wait=wait, cancel_futures=True)
