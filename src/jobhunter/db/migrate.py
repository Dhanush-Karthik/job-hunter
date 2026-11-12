"""Schema migrations. v1 = create_all. Later versions append ALTERs to STEPS; never edit a shipped step."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session, SQLModel, select

from jobhunter import models  # noqa: F401  (registers tables)
from jobhunter.db.engine import get_engine
from jobhunter.models import SchemaVersion, utcnow

STEPS: list[Callable[[Connection], None]] = [
    lambda conn: SQLModel.metadata.create_all(conn),  # v1
]
SCHEMA_VERSION = len(STEPS)


def current_version(engine: Engine) -> int:
    SchemaVersion.__table__.create(engine, checkfirst=True)
    with Session(engine) as s:
        row = s.exec(select(SchemaVersion)).first()
        return row.version if row else 0


def migrate(engine: Engine | None = None) -> int:
    """Apply pending steps. Idempotent. Returns the resulting version."""
    engine = engine or get_engine()
    v = current_version(engine)
    for i in range(v, SCHEMA_VERSION):
        with engine.begin() as conn:
            STEPS[i](conn)
    if v != SCHEMA_VERSION:
        with Session(engine) as s:
            row = s.exec(select(SchemaVersion)).first() or SchemaVersion(version=0)
            row.version, row.applied_at = SCHEMA_VERSION, utcnow()
            s.add(row)
            s.commit()
    return SCHEMA_VERSION
