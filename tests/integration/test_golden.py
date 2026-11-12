import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlmodel import select

from jobhunter.intake.types import RawJob
from jobhunter.models import Lead, Source
from jobhunter.pipeline import ingest


def test_seed_apply_recall(session, settings):
    seed = Path(__file__).resolve().parents[1] / "fixtures/golden/seed.jsonl"
    rows = [json.loads(line) for line in seed.read_text().splitlines() if line.strip()]
    now = datetime(2026, 11, 12, 12, tzinfo=UTC)
    jobs = []
    for row in rows:
        values = {k: v for k, v in row.items() if k not in {"label", "dup_key", "posted_days_ago"}}
        values["source"] = Source(values["source"])
        if values.get("posted_at"):
            values["posted_at"] = datetime.fromisoformat(values["posted_at"])
        elif row.get("posted_days_ago") is not None:
            values["posted_at"] = now - timedelta(days=row["posted_days_ago"])
        jobs.append(RawJob(**values))
    ingest(session, jobs, settings, now=now, cv_text="")
    leads = {(lead.source.value, lead.source_ref): lead for lead in session.exec(select(Lead))}
    labelled = [leads[(row["source"], row["source_ref"])] for row in rows if row["label"] == "apply"]
    assert labelled, "The recall gate needs apply labels"
    misses = [(lead.source_ref, lead.prefilter_reasons) for lead in labelled if not lead.prefilter_pass]
    recall = (len(labelled) - len(misses)) / len(labelled)
    assert recall >= 0.95, f"apply recall={recall:.3f}; misses={misses}"
