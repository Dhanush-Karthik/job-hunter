from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text

from jobhunter import __version__
from jobhunter.db import get_engine
from jobhunter.jobs import scheduler
from jobhunter.schemas import Health

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=Health, operation_id="getHealth")
def health() -> Health:
    try:
        with get_engine().connect() as c:
            c.execute(text("select 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    try:
        running, services = scheduler.is_running(), scheduler.services()
    except Exception:
        log.warning("scheduler probe failed", exc_info=True)
        running, services = False, []
    return Health(ok=db_ok, version=__version__, db=db_ok, scheduler=running, services=services)
