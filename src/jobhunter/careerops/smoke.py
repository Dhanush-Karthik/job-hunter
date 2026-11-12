"""Opt-in real Claude evaluation with an isolated temporary database.

Run: uv run python -m jobhunter.careerops.smoke --lead-url https://...
Only the database is temporary. Reports use the configured career-ops data root.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlmodel import Session, create_engine

from jobhunter.careerops import BridgeError, evaluate
from jobhunter.db import migrate
from jobhunter.models import Lead, Run, RunKind, Source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lead-url", required=True)
    parser.add_argument("--jd-file", type=Path, help="Optional prefetched posting text")
    args = parser.parse_args()
    if not args.lead_url.startswith(("https://", "http://")):
        parser.error("--lead-url must be an HTTP(S) URL")
    with TemporaryDirectory(prefix="jobhunter-cops-smoke-") as directory:
        engine = create_engine(f"sqlite:///{Path(directory) / 'smoke.sqlite'}")
        try:
            migrate(engine)
            with Session(engine) as session:
                lead = Lead(
                    source=Source.manual, source_ref=args.lead_url, canonical_url=args.lead_url,
                    company="Smoke evaluation", title="Manual posting", restored=True,
                    jd_text=args.jd_file.read_text(encoding="utf-8") if args.jd_file else None,
                )
                session.add(lead)
                session.commit()
                session.refresh(lead)
                run = Run(kind=RunKind.evaluate, lead_id=lead.id)
                session.add(run)
                session.commit()
                session.refresh(run)
                evaluation = evaluate(session, lead.id, run_id=run.id, log=sys.stdout, should_cancel=lambda: False)
                print(f"score={evaluation.score} grade={evaluation.grade} report={evaluation.report_path}")
        except BridgeError as exc:
            print(f"Evaluation failed: {exc}", file=sys.stderr)
            return 1
        finally:
            engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
