"""Golden evaluation of the intake pipeline (plan section 9).

Reads labelled postings from data/golden/*.jsonl when present, else tests/fixtures/golden/seed.jsonl. Each line
is a RawJob dict plus "label": "apply" | "skip", optional "dup_key" (rows sharing it are the same job) and
optional "posted_days_ago" (converted to posted_at against a fixed clock so the run is reproducible).

Runs `ingest` on an in-memory DB and prints prefilter recall on "apply" rows and dedupe precision/recall.
Exit 1 if recall < 0.95 or dedupe precision < 0.99.

    uv run python scripts/eval_golden.py [--now 2026-11-12T12:00:00+00:00] [--verbose]
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlmodel import Session, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jobhunter import paths
from jobhunter.db import get_engine, migrate
from jobhunter.intake.types import RawJob
from jobhunter.models import Lead, Source
from jobhunter.pipeline import ingest
from jobhunter.settings import load_defaults

FIXED_NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
RECALL_MIN = 0.95
DEDUPE_PRECISION_MIN = 0.99
SEED = ROOT / "tests" / "fixtures" / "golden" / "seed.jsonl"


def load_rows(now: datetime) -> tuple[list[dict], Path | str]:
    files = sorted((paths.DATA / "golden").glob("*.jsonl"))
    sources: list[Path] = files or [SEED]
    rows: list[dict] = []
    for f in sources:
        rows += [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    for r in rows:
        days = r.get("posted_days_ago")
        if days is not None and not r.get("posted_at"):
            r["posted_at"] = (now - timedelta(days=days)).isoformat()
    return rows, ", ".join(str(f.relative_to(ROOT)) if f.is_relative_to(ROOT) else str(f) for f in sources)


def to_raw(row: dict) -> RawJob:
    d = {k: v for k, v in row.items() if k not in {"label", "dup_key", "posted_days_ago"}}
    d["source"] = Source(d["source"])
    if d.get("posted_at"):
        d["posted_at"] = datetime.fromisoformat(d["posted_at"])
    return RawJob(**d)


def pairs(keys: list) -> set[frozenset[int]]:
    by: dict = {}
    for i, k in enumerate(keys):
        if k is not None:
            by.setdefault(k, []).append(i)
    return {frozenset(p) for ids in by.values() for p in itertools.combinations(ids, 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", help="ISO timestamp; default fixed 2026-11-12T12:00Z")
    ap.add_argument("--verbose", action="store_true", help="list misses and wrong groupings")
    args = ap.parse_args()
    now = datetime.fromisoformat(args.now) if args.now else FIXED_NOW

    rows, origin = load_rows(now)
    settings = load_defaults(paths.CONFIG_EXAMPLE)
    get_engine.cache_clear()
    engine = get_engine("sqlite://")
    migrate(engine)
    with Session(engine) as s:
        result = ingest(s, [to_raw(r) for r in rows], settings, now=now, cv_text="")
        leads = {(ld.source, ld.source_ref): ld for ld in s.exec(select(Lead))}
    got = [leads[(Source(r["source"]), r["source_ref"])] for r in rows]

    apply_idx = [i for i, r in enumerate(rows) if r["label"] == "apply"]
    skip_idx = [i for i, r in enumerate(rows) if r["label"] == "skip"]
    kept = [i for i in apply_idx if got[i].prefilter_pass]
    recall = len(kept) / len(apply_idx) if apply_idx else 1.0
    dropped_skip = sum(not got[i].prefilter_pass for i in skip_idx)

    truth = pairs([r.get("dup_key") for r in rows])
    pred = pairs([ld.dedupe_group for ld in got])
    tp = len(truth & pred)
    precision = tp / len(pred) if pred else 1.0
    d_recall = tp / len(truth) if truth else 1.0

    print(f"golden set: {origin} ({len(rows)} postings: {len(apply_idx)} apply, {len(skip_idx)} skip)")
    print(f"ingest: {result.summary()}")
    print(f"prefilter recall on 'apply': {recall:.3f} ({len(kept)}/{len(apply_idx)})  [gate >= {RECALL_MIN}]")
    print(f"prefilter drops on 'skip' (info): {dropped_skip}/{len(skip_idx)}")
    print(f"dedupe precision: {precision:.3f} ({tp}/{len(pred)} predicted pairs)  [gate >= {DEDUPE_PRECISION_MIN}]")
    print(f"dedupe recall (info): {d_recall:.3f} ({tp}/{len(truth)} true pairs)")

    if args.verbose or recall < RECALL_MIN or precision < DEDUPE_PRECISION_MIN:
        for i in apply_idx:
            if not got[i].prefilter_pass:
                print(f"  MISSED apply: {rows[i]['company']} / {rows[i]['title']}: {got[i].prefilter_reasons}")
        for p in sorted(pred - truth, key=sorted):
            a, b = sorted(p)
            print(f"  WRONG group: {rows[a]['company']} / {rows[a]['title']}  ==  {rows[b]['company']} / {rows[b]['title']}")
        for p in sorted(truth - pred, key=sorted):
            a, b = sorted(p)
            print(f"  UNGROUPED:   {rows[a]['company']} / {rows[a]['title']}  !=  {rows[b]['company']} / {rows[b]['title']}")

    return 0 if recall >= RECALL_MIN and precision >= DEDUPE_PRECISION_MIN else 1


if __name__ == "__main__":
    sys.exit(main())
