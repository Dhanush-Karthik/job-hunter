import pytest
from sqlmodel import Session

from jobhunter.db import get_engine, migrate


@pytest.fixture()
def session():
    get_engine.cache_clear()
    engine = get_engine("sqlite://")
    migrate(engine)
    with Session(engine) as s:
        yield s
    get_engine.cache_clear()
