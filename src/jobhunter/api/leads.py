from __future__ import annotations

import hashlib
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import select

from jobhunter.api import convert, queries, workflow
from jobhunter.api.deps import SQLITE_MAX_INT, SessionDep
from jobhunter.intake.types import RawJob
from jobhunter.jobs import runner
from jobhunter.models import Application, ApplyChannel, AppStatus, Lead, RunKind, Source
from jobhunter.pipeline import ingest
from jobhunter.schemas import (
    BulkAction,
    BulkResult,
    CvRequest,
    LeadDetail,
    LeadSummary,
    ManualLead,
    OutreachOut,
    Page,
    RunOut,
    SkipRequest,
)
from jobhunter.settings import get_settings

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.get("", response_model=Page[LeadSummary], operation_id="listLeads")
def list_leads(
    session: SessionDep,
    q: str | None = Query(None, description="search company/title/jd"),
    status: list[AppStatus] | None = Query(None),
    source: list[Source] | None = Query(None),
    channel: list[ApplyChannel] | None = Query(None),
    min_score: float | None = None,
    fresh_only: bool = False,
    inbound_only: bool = False,
    include_rejected: bool = Query(False, description="include prefilter drops"),
    include_duplicates: bool = Query(False, description="include non-primary dedupe members"),
    sort: Literal["score", "found_at", "posted_at", "eval_score"] = "score",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Page[LeadSummary]:
    stmt = queries.lead_query(
        q=q, status=status, source=source, channel=channel, min_score=min_score, fresh_only=fresh_only,
        inbound_only=inbound_only, include_rejected=include_rejected, include_duplicates=include_duplicates,
        sort=sort,
    )
    total = queries.count(session, stmt)
    leads = session.exec(stmt.limit(limit).offset(min(offset, SQLITE_MAX_INT))).all()
    return Page(items=convert.lead_summaries(session, list(leads)), total=total, limit=limit, offset=offset)


@router.get("/quick-apply", response_model=list[LeadSummary], operation_id="listQuickApply")
def list_quick_apply(session: SessionDep, limit: int = Query(100, ge=1, le=500)) -> list[LeadSummary]:
    """Shortlisted/Ready leads on platform_quick channel, grouped client-side by source."""
    stmt = (
        select(Lead)
        .join(Application, Application.lead_id == Lead.id)
        .where(Application.status.in_([AppStatus.shortlisted, AppStatus.ready]))
        .where(Lead.apply_channel == ApplyChannel.platform_quick)
        .order_by(Lead.quick_score.desc(), Lead.id.desc())
        .limit(limit)
    )
    return convert.lead_summaries(session, list(session.exec(stmt)))


@router.post("", response_model=LeadDetail, status_code=201, operation_id="createManualLead")
def create_manual_lead(body: ManualLead, session: SessionDep) -> LeadDetail:
    basis = body.url.strip() if body.url and body.url.strip() else f"{body.company}|{body.title}".lower()
    raw = RawJob(
        source=Source.manual,
        source_ref=hashlib.sha1(basis.encode()).hexdigest(),
        title=body.title,
        company=body.company,
        location=body.location,
        job_url=body.url,
        description=body.jd_text,
        source_detail="manual",
    )
    ingest(session, [raw], get_settings(session))
    lead = session.exec(select(Lead).where(Lead.source == Source.manual, Lead.source_ref == raw.source_ref)).one()
    workflow.restore_lead(lead)  # the owner asked for this one: never dropped by the prefilter
    session.add(lead)
    session.commit()
    return convert.lead_detail(session, lead)


@router.post("/bulk", response_model=BulkResult, operation_id="bulkLeads")
def bulk(body: BulkAction, session: SessionDep) -> BulkResult:
    result = BulkResult(ok=[], failed={})
    reason = (body.reason or "").strip()
    for lead_id in dict.fromkeys(body.ids):
        try:
            lead = workflow.get_lead_or_404(session, lead_id)
            if body.action == "shortlist":
                workflow.shortlist_lead(session, lead)
            elif body.action == "skip":
                workflow.skip_lead(session, lead, reason)
            elif body.action == "restore":
                workflow.restore_lead(lead)
                session.add(lead)
            else:
                run = runner.submit(RunKind(body.action), lead_id=lead_id)
                if run.id not in result.run_ids:
                    result.run_ids.append(run.id)
            session.commit()
            result.ok.append(lead_id)
        except HTTPException as e:
            session.rollback()
            result.failed[lead_id] = workflow.detail_text(e)
        except Exception as e:  # noqa: BLE001  one bad id must not abort the batch
            session.rollback()
            result.failed[lead_id] = f"{type(e).__name__}: {e}"
    return result


@router.get("/{lead_id}", response_model=LeadDetail, operation_id="getLead")
def get_lead(lead_id: int, session: SessionDep) -> LeadDetail:
    return convert.lead_detail(session, workflow.get_lead_or_404(session, lead_id))


@router.post("/{lead_id}/shortlist", response_model=LeadDetail, operation_id="shortlistLead")
def shortlist(lead_id: int, session: SessionDep) -> LeadDetail:
    lead = workflow.get_lead_or_404(session, lead_id)
    workflow.shortlist_lead(session, lead)
    session.commit()
    return convert.lead_detail(session, lead)


@router.post("/{lead_id}/skip", response_model=LeadDetail, operation_id="skipLead")
def skip(lead_id: int, body: SkipRequest, session: SessionDep) -> LeadDetail:
    lead = workflow.get_lead_or_404(session, lead_id)
    workflow.skip_lead(session, lead, body.reason)
    session.commit()
    return convert.lead_detail(session, lead)


@router.post("/{lead_id}/restore", response_model=LeadDetail, operation_id="restoreLead")
def restore(lead_id: int, session: SessionDep) -> LeadDetail:
    """Undo a prefilter drop."""
    lead = workflow.get_lead_or_404(session, lead_id)
    workflow.restore_lead(lead)
    session.add(lead)
    session.commit()
    return convert.lead_detail(session, lead)


def _submit(session: SessionDep, lead_id: int, kind: RunKind, params: dict | None = None) -> RunOut:
    workflow.get_lead_or_404(session, lead_id)
    try:
        return runner.to_out(runner.submit(kind, lead_id=lead_id, params=params))
    except ValueError as e:  # lead vanished between the check and the insert
        raise HTTPException(404, str(e)) from e


@router.post("/{lead_id}/evaluate", response_model=RunOut, status_code=202, operation_id="evaluateLead")
def evaluate(lead_id: int, session: SessionDep) -> RunOut:
    return _submit(session, lead_id, RunKind.evaluate)


@router.post("/{lead_id}/verify", response_model=RunOut, status_code=202, operation_id="verifyLead")
def verify(lead_id: int, session: SessionDep) -> RunOut:
    return _submit(session, lead_id, RunKind.verify)


@router.post("/{lead_id}/cv", response_model=RunOut, status_code=202, operation_id="generateCv")
def generate_cv(lead_id: int, body: CvRequest, session: SessionDep) -> RunOut:
    return _submit(session, lead_id, RunKind.cv, {"variant": body.variant.value})


@router.post("/{lead_id}/assist-apply", response_model=RunOut, status_code=202, operation_id="assistApply")
def assist_apply(lead_id: int, session: SessionDep) -> RunOut:
    """Opens a pre-filled application form in a browser. Never submits."""
    return _submit(session, lead_id, RunKind.assist_apply)


@router.post("/{lead_id}/contacts", response_model=RunOut, status_code=202, operation_id="findContacts")
def find_contacts(lead_id: int, session: SessionDep) -> RunOut:
    return _submit(session, lead_id, RunKind.contacts)


@router.get("/{lead_id}/outreach", response_model=list[OutreachOut], operation_id="leadOutreach")
def lead_outreach(lead_id: int, session: SessionDep) -> list[OutreachOut]:
    workflow.get_lead_or_404(session, lead_id)
    app = session.exec(select(Application).where(Application.lead_id == lead_id)).first()
    return convert.outreach_outs(session, convert.lead_outreach_rows(session, lead_id, app.id if app else None))
