"""Ingest orchestration: normalize -> dedupe -> prefilter -> quick score -> upsert into `leads`."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, select

from jobhunter.intake.types import IngestResult, RawJob
from jobhunter.models import Lead, Source, utcnow
from jobhunter.pipeline.dedupe import DedupeIndex
from jobhunter.pipeline.experience import ExpInfo, parse_experience
from jobhunter.pipeline.normalize import Normalized, as_utc, normalize
from jobhunter.pipeline.prefilter import prefilter
from jobhunter.pipeline.score import Scorer, read_default_cv
from jobhunter.schemas import Settings


def _keep_known(norm: Normalized, lead: Lead) -> None:
    """A refetch that lacks a field (no description this time, salary hidden) must not erase what we know."""
    if norm.posted_at is None:
        norm.posted_at = as_utc(lead.posted_at)
    if norm.exp.exp_min is None and norm.exp.exp_max is None:
        norm.exp.exp_min, norm.exp.exp_max = lead.exp_min, lead.exp_max
    if norm.ctc_min is None and norm.ctc_max is None:
        norm.ctc_min, norm.ctc_max = lead.ctc_min, lead.ctc_max
    norm.description = norm.description or lead.jd_text
    norm.apply_url = norm.apply_url or lead.apply_url
    norm.canonical_url = norm.canonical_url or lead.canonical_url
    norm.location = norm.location or lead.location


def _fill(lead: Lead, raw: RawJob, norm: Normalized) -> None:
    lead.source_detail = raw.source_detail
    lead.canonical_url = norm.canonical_url
    lead.apply_url = norm.apply_url
    lead.apply_channel = norm.apply_channel
    lead.company = norm.company
    lead.title = norm.title
    lead.location = norm.location
    lead.work_mode = norm.work_mode
    lead.exp_min, lead.exp_max = norm.exp.exp_min, norm.exp.exp_max
    lead.ctc_min, lead.ctc_max = norm.ctc_min, norm.ctc_max
    lead.posted_at = norm.posted_at
    lead.jd_text = norm.description
    lead.role_family = norm.role_family
    lead.is_inbound = bool(lead.is_inbound or raw.is_inbound)
    lead.raw = raw.raw or {}


def ingest(
    session: Session,
    raw_jobs: list[RawJob],
    settings: Settings,
    *,
    now: datetime | None = None,
    cv_text: str | None = None,
) -> IngestResult:
    """Upsert `raw_jobs` as Lead rows by (source, source_ref). Commits once at the end.

    New rows get found_at=now, a dedupe group (joining an existing one when the same job is already stored),
    prefilter verdict and quick score. Known rows are refreshed in place: restored leads keep passing, the
    dedupe group and found_at never change.
    """
    now = as_utc(now) or utcnow()
    if cv_text is None:
        cv_text = read_default_cv()
    scorer = Scorer(settings, cv_text)
    index = DedupeIndex(session)
    result = IngestResult(fetched=len(raw_jobs))
    ids: dict[int, None] = {}

    for raw in raw_jobs:
        norm = normalize(raw, settings)
        lead = session.exec(
            select(Lead).where(Lead.source == raw.source, Lead.source_ref == raw.source_ref)
        ).first()
        is_new = lead is None
        if lead is None:
            lead = Lead(source=raw.source, source_ref=raw.source_ref, company=norm.company, title=norm.title,
                        found_at=now)
        else:
            _keep_known(norm, lead)

        verdict = prefilter(norm, settings, now)
        _fill(lead, raw, norm)
        lead.prefilter_reasons = verdict.reasons
        lead.prefilter_tags = verdict.tags
        lead.prefilter_pass = True if lead.restored else verdict.passed
        lead.quick_score = scorer.score(
            title=norm.title, skills=norm.skills, description=norm.description, role_family=norm.role_family,
            source=raw.source, is_inbound=lead.is_inbound, posted_at=norm.posted_at, found_at=lead.found_at,
            now=now, exp=norm.exp)

        if is_new:
            match = index.find(norm)
            if match is not None and match.group is None:  # legacy row without a group: start one
                match.group = f"d{match.id}"
                session.get(Lead, match.id).dedupe_group = match.group
            lead.dedupe_group = match.group if match else None
            session.add(lead)
            session.flush()  # assigns lead.id; also makes this row visible to the next lookup
            if match is None:
                lead.dedupe_group = f"d{lead.id}"
            result.new += 1
            result.duplicates += match is not None
            result.dropped += not lead.prefilter_pass
        else:
            if lead.dedupe_group is None:
                lead.dedupe_group = f"d{lead.id}"
            session.add(lead)
            result.updated += 1
        index.add(lead, norm)
        ids[lead.id] = None

    session.commit()
    result.lead_ids = list(ids)
    return result


def _stored_exp(lead: Lead) -> ExpInfo:
    """Experience as ingest saw it, rebuilt from the stored columns. The 'inferred' marker is not stored, so it is
    re-derived: a title-level guess that equals the stored numbers is still treated as a guess."""
    parsed = parse_experience(lead.title, lead.jd_text, None, None)
    inferred = parsed.inferred if parsed.inferred and parsed.exp_min == lead.exp_min else None
    return ExpInfo(exp_min=lead.exp_min, exp_max=lead.exp_max, flags=parsed.flags, inferred=inferred)


def _stored_skills(lead: Lead) -> list[str]:
    if lead.source != Source.naukri:
        return []
    skills = lead.raw.get("skills") or []
    if isinstance(skills, str):
        skills = [part.strip() for part in skills.split(",") if part.strip()]
    return [str(s) for s in skills]


def rescore(session: Session, settings: Settings, *, now: datetime | None = None, cv_text: str | None = None) -> int:
    """Recompute `quick_score` for every stored lead with the current scorer (after a scoring rule or settings
    change). Only the score moves: prefilter verdicts, dedupe groups and found_at stay. Returns rows changed."""
    now = as_utc(now) or utcnow()
    scorer = Scorer(settings, cv_text if cv_text is not None else read_default_cv())
    changed = 0
    for lead in session.exec(select(Lead)):
        value = scorer.score(
            title=lead.title, skills=_stored_skills(lead), description=lead.jd_text, role_family=lead.role_family,
            source=lead.source, is_inbound=lead.is_inbound, posted_at=as_utc(lead.posted_at),
            found_at=lead.found_at, now=now, exp=_stored_exp(lead))
        if abs(value - lead.quick_score) > 1e-9:
            lead.quick_score = value
            session.add(lead)
            changed += 1
    session.commit()
    return changed
