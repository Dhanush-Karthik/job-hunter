"""Filesystem layout. Everything personal lives under data/ (gitignored)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("JOBHUNTER_DATA", ROOT / "data"))
DB_PATH = DATA / "jobhunter.sqlite"
CONFIG_PATH = DATA / "config.yml"
CONFIG_EXAMPLE = ROOT / "config" / "jobhunter.example.yml"
LOGS = DATA / "logs"
RUN_LOGS = LOGS / "runs"
RUN = DATA / "run"  # pidfile, install stamps
CAREEROPS_DATA = DATA / "careerops"  # career-ops writes reports/PDFs here
CV_DIR = DATA / "cv"  # owner's CV variants (A/B) as markdown
CAREEROPS_VENDOR = ROOT / "vendor" / "career-ops"
WEB_DIST = ROOT / "web" / "dist"
CONTRACT = ROOT / "contracts" / "openapi.json"


def ensure_dirs() -> None:
    for d in (DATA, LOGS, RUN_LOGS, RUN, CAREEROPS_DATA, CV_DIR):
        d.mkdir(parents=True, exist_ok=True)
