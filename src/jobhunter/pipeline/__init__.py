"""Intake pipeline: normalize -> dedupe -> India prefilter -> quick score -> store.

Entry point: `ingest(session, raw_jobs, settings, *, now=None, cv_text=None) -> IngestResult`.
"""

from jobhunter.pipeline.store import ingest, rescore

__all__ = ["ingest", "rescore"]
