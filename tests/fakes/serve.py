"""Bootstrap only a fresh test data root, migrate, then serve the built dashboard."""

import os
import runpy
from pathlib import Path

root = Path(__file__).resolve().parents[2]
os.chdir(root)
runpy.run_path(str(root / "tests/fakes/prepare.py"))["prepare"](Path(os.environ["JOBHUNTER_DATA"]))

from jobhunter.db import migrate

migrate()
os.execvp("uv", ["uv", "run", "uvicorn", "jobhunter.api.app:app", "--host", "127.0.0.1", "--port", "8799"])
