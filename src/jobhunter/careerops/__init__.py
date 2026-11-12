"""career-ops bridge (Wave 2 contract, lead-owned signatures; codex_cops implements the bodies).

Every function is synchronous and blocking; `jobhunter.jobs.runner` calls it on a worker thread, owns the Run
row (state, timestamps, summary, error) and the concurrency cap. Functions here only:
  - write human-readable progress to `log` (the run's log file, already open),
  - poll `should_cancel()` while a subprocess runs and kill it (raise `Cancelled`) when it returns True,
  - write their domain rows (Evaluation, Application, Event, Outreach, Lead via pipeline.ingest) and commit,
  - raise `BridgeError` with a one-line, owner-readable message on failure.

Subprocesses: cwd = paths.CAREEROPS_DATA, env CAREER_OPS_DATA_DIR = paths.CAREEROPS_DATA, binaries from env
JOBHUNTER_CLAUDE_BIN (default "claude") and JOBHUNTER_NODE_BIN (default "node"), so tests and e2e can swap in fakes.
vendor/career-ops is never modified. Job-posting text is untrusted input (prompt-injection): claude -p runs with
the narrowest tool allowlist per mode, as career-ops' own web runner does (plan section 13).
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO
from uuid import uuid4

from sqlmodel import Session, select

from jobhunter import paths, pipeline
from jobhunter.intake.types import IngestResult, RawJob
from jobhunter.models import (
    Actor,
    Application,
    AppStatus,
    Evaluation,
    Event,
    Lead,
    Outreach,
    OutreachKind,
    ResumeVariant,
    Source,
    SourceHealth,
    utcnow,
)
from jobhunter.schemas import Settings

from ._parsing import envelope, machine_summary
from ._runtime import CLAUDE_ISOLATION_ARGS, claude_text, node, run, scan_timeout

ShouldCancel = Callable[[], bool]


class BridgeError(RuntimeError):
    """Owner-readable failure; becomes Run.error."""


class Cancelled(BridgeError):
    """should_cancel() returned True; the subprocess was killed."""


def scan(session: Session, settings: Settings, *, log: TextIO, should_cancel: ShouldCancel) -> IngestResult:
    """career-ops scan (company career pages from data/careerops/portals.yml + remote boards) -> RawJob ->
    pipeline.ingest. Updates SourceHealth rows "careerops_scan" (and per remote board source when known)."""
    health = session.get(SourceHealth, Source.careerops_scan.value) or SourceHealth(
        source=Source.careerops_scan.value
    )
    health.last_run_at = utcnow()
    session.add(health)
    session.commit()
    try:
        result = node("scan.mjs", {}, log=log, should_cancel=should_cancel, timeout=scan_timeout())
        postings = result["postings"]
        raws = [_raw_job(posting) for posting in postings]
        ingested = pipeline.ingest(session, raws, settings)
        now = utcnow()
        health.last_ok_at = now
        health.last_error = "; ".join(result.get("errors", []))[:500] or None
        health.consecutive_failures = 0
        health.last_count = len(raws)
        boards = {raw.source.value: {"count": sum(r.source == raw.source for r in raws), "error": None}
                  for raw in raws if raw.source != Source.careerops_scan}
        boards.update(result.get("sources", {}))
        for source, outcome in boards.items():
            board = session.get(SourceHealth, source) or SourceHealth(source=source)
            board.last_run_at = now
            board.last_error = outcome.get("error")
            if board.last_error:
                board.consecutive_failures += 1
            else:
                board.last_ok_at = now
                board.consecutive_failures = 0
            board.last_count = outcome.get("count", 0)
            session.add(board)
        session.add(health)
        session.commit()
        log.write(ingested.summary() + "\n")
        log.flush()
        return ingested
    except Exception as exc:
        session.rollback()
        health = session.get(SourceHealth, Source.careerops_scan.value)
        health.last_error = str(exc)[:500]
        health.consecutive_failures += 1
        health.last_count = 0
        session.add(health)
        session.commit()
        if isinstance(exc, BridgeError):
            raise
        raise BridgeError(f"Could not import career-ops scan: {str(exc)[:300]}") from exc


def evaluate(session: Session, lead_id: int, *, run_id: int, log: TextIO, should_cancel: ShouldCancel) -> Evaluation:
    """claude -p evaluate (read-only scope, JD pre-fetched from Lead.jd_text or fetched from the URL).
    Persists the report under data/careerops/reports/, parses its Machine Summary, inserts an Evaluation
    (score 1-5, grade letter, report_path relative to CAREEROPS_DATA, run_id) and returns it."""
    lead = _lead(session, lead_id)
    invocation = node(
        "prompt.mjs", _posting(lead) | {"kind": "evaluate"}, log=log, should_cancel=should_cancel
    )
    output = _claude(invocation["args"], log=log, should_cancel=should_cancel)
    markdown = envelope(output, "report-md")
    meta = machine_summary(markdown)
    reports = paths.CAREEROPS_DATA / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    slug = invocation.get("report_slug") or re.sub(r"[^a-z0-9]+", "-", lead.company.lower()).strip("-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)[:100] or "company"
    # career-ops' NNN-company.md convention; exclusive creation handles concurrent evaluations.
    number = max((int(p.name.split("-", 1)[0]) for p in reports.glob("[0-9]*-*.md")
                  if p.name.split("-", 1)[0].isdigit()), default=0) + 1
    while True:
        report = reports / f"{number:03d}-{slug}-{utcnow().date().isoformat()}.md"
        try:
            with report.open("x", encoding="utf-8") as handle:
                handle.write(markdown)
            break
        except FileExistsError:
            number += 1
    evaluation = Evaluation(
        lead_id=lead_id, run_id=run_id, score=meta["score"], grade=meta["grade"],
        report_path=report.relative_to(paths.CAREEROPS_DATA).as_posix(),
    )
    session.add(evaluation)
    session.commit()
    session.refresh(evaluation)
    log.write(f"Evaluation {evaluation.score}/5; archetype: {meta.get('archetype', 'unknown')}; "
              f"legitimacy: {meta.get('legitimacy_tier', 'unknown')}\n")
    log.flush()
    return evaluation


def verify(session: Session, lead_id: int, *, run_id: int, log: TextIO, should_cancel: ShouldCancel) -> Evaluation:
    """Is the posting still live (career-ops liveness, no LLM when possible)? Sets is_live + live_verified_at on
    the latest Evaluation (creates one without a score if none). Closed + application status New/Shortlisted ->
    status Expired with an Event (actor=system). Returns the Evaluation."""
    lead = _lead(session, lead_id)
    verdict = node("verify.mjs", {"url": _url(lead)}, log=log, should_cancel=should_cancel)
    evaluation = _latest_evaluation(session, lead_id) or Evaluation(lead_id=lead_id, run_id=run_id)
    is_live = verdict.get("is_live")
    if is_live is not None and not isinstance(is_live, bool):
        raise BridgeError("Invalid liveness result; see run log")
    evaluation.is_live = is_live
    evaluation.live_verified_at = utcnow()
    session.add(evaluation)
    if is_live is False:
        application = _application(session, lead_id)
        if application is None:
            application = Application(lead_id=lead_id)
            session.add(application)
            session.flush()
        if application.status in {AppStatus.new, AppStatus.shortlisted}:
            _transition(session, application, AppStatus.expired, verdict.get("reason", "Posting closed"))
    session.commit()
    session.refresh(evaluation)
    return evaluation


def generate_cv(
    session: Session, lead_id: int, variant: ResumeVariant, *, run_id: int, log: TextIO, should_cancel: ShouldCancel
) -> Application:
    """Tailored CV PDF from data/cv/cv_<a|b>.md for this lead, with career-ops fact-check (failure -> BridgeError,
    no PDF kept). Creates the Application (status Shortlisted + Event) if missing. Sets resume_variant,
    cv_pdf_path (relative to paths.DATA), cv_approved=False."""
    lead = _lead(session, lead_id)
    variant = ResumeVariant(variant)
    source = paths.CV_DIR / f"cv_{variant.value.lower()}.md"
    if not source.is_file():
        raise BridgeError(f"CV variant {variant.value} is missing: {source.name}")
    latest = _latest_evaluation(session, lead_id)
    invocation = node(
        "prompt.mjs", _posting(lead) | {
            "kind": "pdf", "variant_text": source.read_text(encoding="utf-8"),
            "report_file": latest.report_path if latest else None,
        }, log=log, should_cancel=should_cancel,
    )
    output = _claude(invocation["args"], log=log, should_cancel=should_cancel)
    markdown = envelope(output, "cv-md")
    html = envelope(output, "cv-html")
    directory = paths.CAREEROPS_DATA / "output"
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"cv-{lead_id}-{variant.value.lower()}-{run_id}-{uuid4().hex[:8]}"
    md_path, html_path, pdf_path = (directory / f"{stem}.{ext}" for ext in ("md", "html", "pdf"))
    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    try:
        for document in (md_path, html_path):
            checked = node(
                "facts.mjs", {"document": str(document.resolve()), "source": str(source.resolve())},
                log=log, should_cancel=should_cancel,
            )
            if checked.get("ok") is not True:
                raise BridgeError("CV fact-check failed; see run log")
        node("render.mjs", {
            "document": str(html_path.resolve()), "output": str(pdf_path.resolve()),
            "source": str(source.resolve()), "text": output,
        }, log=log, should_cancel=should_cancel)
        if not pdf_path.is_file() or not pdf_path.stat().st_size:
            raise BridgeError("PDF renderer produced no PDF; see run log")
        relative = pdf_path.resolve().relative_to(paths.DATA.resolve()).as_posix()
    except Exception:
        pdf_path.unlink(missing_ok=True)
        raise
    application = _application(session, lead_id)
    if application is None:
        application = Application(lead_id=lead_id)
        session.add(application)
        session.flush()
        _transition(session, application, AppStatus.shortlisted, "Tailored CV generated")
    application.resume_variant = variant
    application.cv_pdf_path = relative
    application.cv_approved = False
    application.updated_at = utcnow()
    session.add(application)
    session.commit()
    session.refresh(application)
    return application


def assist_apply(session: Session, lead_id: int, *, run_id: int, log: TextIO, should_cancel: ShouldCancel) -> None:
    """Open the apply URL in a headed Playwright browser and pre-fill the form (CV PDF if approved, profile data).
    NEVER clicks submit. Returns once the form is filled; the browser window stays open for the owner."""
    lead = _lead(session, lead_id)
    application = _application(session, lead_id)
    pdf = None
    if application and application.cv_approved and application.cv_pdf_path:
        pdf = _safe_path(paths.DATA, application.cv_pdf_path)
        if pdf is None or not pdf.is_file():
            raise BridgeError("Approved CV PDF is missing")
    node(
        "assist.mjs", {"url": _url(lead), "pdf": str(pdf) if pdf else None,
                       "headed": True, "submit": False, "run_id": run_id},
        log=log, should_cancel=should_cancel, owner_browser=True,
    )


def find_contacts(
    session: Session, lead_id: int, *, run_id: int, log: TextIO, should_cancel: ShouldCancel
) -> list[Outreach]:
    """Public referral contacts at the lead's company + a referral draft each -> Outreach rows (kind=referral,
    lead_id, application_id if any, contact "Name — profile url", draft). Never sends anything."""
    lead = _lead(session, lead_id)
    invocation = node(
        "prompt.mjs", _posting(lead) | {"kind": "contacts"}, log=log, should_cancel=should_cancel
    )
    output = _claude(invocation["args"], log=log, should_cancel=should_cancel)
    import json

    try:
        contacts = json.loads(envelope(output, "contacts-json"))
        if not isinstance(contacts, list):
            raise TypeError
        if any(not isinstance(c, dict) or not all(isinstance(c.get(k), str) and c[k].strip()
                   for k in ("name", "url", "draft")) for c in contacts):
            raise ValueError
        if any(not c["url"].startswith("https://") for c in contacts):
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise BridgeError("Invalid contacts or referral drafts; see run log") from exc
    application = _application(session, lead_id)
    rows = [Outreach(
        lead_id=lead_id, application_id=application.id if application else None,
        kind=OutreachKind.referral, contact=f"{contact['name']} — {contact['url']}", draft=contact["draft"],
    ) for contact in contacts]
    session.add_all(rows)
    session.commit()
    for row in rows:
        session.refresh(row)
    return rows


def report_md(evaluation: Evaluation) -> str | None:
    """Report markdown for the API (LeadDetail.evaluation.report_md); None if missing."""
    report = _safe_path(paths.CAREEROPS_DATA, evaluation.report_path)
    if report is None or not report.is_file():
        return None
    return report.read_text(encoding="utf-8")


def _safe_path(root: Path, relative: str | None) -> Path | None:
    if not relative:
        return None
    result = (root / relative).resolve()
    return result if result.is_relative_to(root.resolve()) else None


def _lead(session: Session, lead_id: int) -> Lead:
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise BridgeError(f"Lead {lead_id} does not exist")
    return lead


def _url(lead: Lead) -> str:
    url = lead.apply_url or lead.canonical_url
    if not url or not url.startswith(("https://", "http://")):
        raise BridgeError("Lead has no usable posting URL")
    return url


def _posting(lead: Lead) -> dict[str, Any]:
    return {"url": lead.canonical_url or lead.apply_url or "", "company": lead.company,
            "title": lead.title, "jd_text": lead.jd_text, "today": utcnow().date().isoformat()}


def _application(session: Session, lead_id: int) -> Application | None:
    return session.exec(select(Application).where(Application.lead_id == lead_id)).first()


def _latest_evaluation(session: Session, lead_id: int) -> Evaluation | None:
    return session.exec(select(Evaluation).where(Evaluation.lead_id == lead_id).order_by(
        Evaluation.created_at.desc(), Evaluation.id.desc()
    )).first()


def _transition(session: Session, application: Application, status: AppStatus, note: str) -> None:
    session.add(Event(application_id=application.id, from_status=application.status,
                      to_status=status, actor=Actor.system, note=note))
    application.status = status
    application.updated_at = utcnow()
    session.add(application)


def _claude(args: list[str], *, log: TextIO, should_cancel: ShouldCancel) -> str:
    return claude_text(run(
        [os.environ.get("JOBHUNTER_CLAUDE_BIN", "claude"), *args,
         *CLAUDE_ISOLATION_ARGS,
         "--add-dir", str(paths.CAREEROPS_VENDOR.resolve())], log=log, should_cancel=should_cancel,
    ))


def _raw_job(posting: dict[str, Any]) -> RawJob:
    provider = str(posting.get("provider", "")).removesuffix("-api").lower()
    provider = {"wwr": "weworkremotely", "remote-ok": "remoteok"}.get(provider, provider)
    source = Source(provider) if provider in {"remotive", "weworkremotely", "himalayas", "remoteok"} else (
        Source.careerops_scan
    )
    url = posting.get("url") or posting.get("job_url")
    reference = url or posting.get("id") or posting.get("externalId")
    if not reference or not posting.get("title") or not posting.get("company"):
        raise BridgeError("Scan posting is missing its identity, title or company")
    date = posting.get("postedAt") or posting.get("posted_at") or posting.get("date")
    try:
        if isinstance(date, (int, float)):
            posted_at = datetime.fromtimestamp(date / 1000 if date > 1e11 else date, UTC)
        else:
            posted_at = datetime.fromisoformat(str(date)) if date else None
    except (ValueError, OverflowError, OSError):
        posted_at = None
    salary = posting.get("salary")
    salary_values = salary if isinstance(salary, dict) else {}
    return RawJob(
        source=source, source_ref=str(reference), title=posting["title"], company=posting["company"],
        location=posting.get("location"), job_url=url,
        apply_url=posting.get("applyUrl") or posting.get("apply_url") or url,
        description=posting.get("description") or posting.get("jd_text"), posted_at=posted_at,
        is_remote=posting.get("remote") if isinstance(posting.get("remote"), bool) else None,
        salary_min=salary_values.get("min", posting.get("salaryMin", posting.get("salary_min"))),
        salary_max=salary_values.get("max", posting.get("salaryMax", posting.get("salary_max"))),
        currency=salary_values.get("currency") or posting.get("currency"), salary_interval="yearly",
        salary_text=salary if isinstance(salary, str) else None, source_detail=provider or None, raw=posting,
    )
