from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from jobhunter import paths


@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    """One engine per URL. Default: data/jobhunter.sqlite. Tests pass 'sqlite://' for in-memory."""
    if url is None:
        paths.ensure_dirs()
        url = f"sqlite:///{paths.DB_PATH}"
    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if url in ("sqlite://", "sqlite:///:memory:"):
        from sqlalchemy.pool import StaticPool

        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    return engine


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with Session(get_engine()) as s:
        yield s


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """For jobs/scripts: commits on success, rolls back on error."""
    with Session(engine or get_engine()) as s:
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
