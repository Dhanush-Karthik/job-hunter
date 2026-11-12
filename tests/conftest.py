import os

import pytest
from sqlmodel import Session

from jobhunter.db import get_engine, migrate

# The API lifespan starts the real scheduler unless told not to; no test wants that.
os.environ.setdefault("JOBHUNTER_NO_SCHEDULER", "1")


@pytest.fixture()
def session():
    get_engine.cache_clear()
    engine = get_engine("sqlite://")
    migrate(engine)
    with Session(engine) as s:
        yield s
    get_engine.cache_clear()
