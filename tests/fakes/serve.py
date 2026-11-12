"""Bootstrap only a fresh test data root, migrate, then serve the built dashboard."""

import os
import runpy
from pathlib import Path

root = Path(__file__).resolve().parents[2]
os.chdir(root)
# The browser suite must never touch the owner's Keychain or desktop.
os.environ["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
os.environ["JOBHUNTER_NOTIFY"] = "0"
runpy.run_path(str(root / "tests/fakes/prepare.py"))["prepare"](Path(os.environ["JOBHUNTER_DATA"]))

from jobhunter.db import migrate

migrate()
os.execvp("uv", ["uv", "run", "uvicorn", "jobhunter.api.app:app", "--host", "127.0.0.1", "--port", "8799"])
