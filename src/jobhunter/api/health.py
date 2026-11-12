from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from jobhunter import __version__
from jobhunter.db import get_engine
from jobhunter.schemas import Health

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=Health, operation_id="getHealth")
def health() -> Health:
    try:
        with get_engine().connect() as c:
            c.execute(text("select 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    # scheduler + services are filled in by Wave 2 (jobs/) — false until then
    return Health(ok=db_ok, version=__version__, db=db_ok, scheduler=False, services=[])
