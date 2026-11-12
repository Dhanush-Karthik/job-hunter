from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from jobhunter.api._stub import todo
from jobhunter.models import ApplyChannel, AppStatus, Source
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

router = APIRouter(prefix="/api/leads", tags=["leads"])


@router.get("", response_model=Page[LeadSummary], operation_id="listLeads")
def list_leads(
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
    raise todo()


@router.get("/quick-apply", response_model=list[LeadSummary], operation_id="listQuickApply")
def list_quick_apply(limit: int = Query(100, ge=1, le=500)) -> list[LeadSummary]:
    """Shortlisted/Ready leads on platform_quick channel, grouped client-side by source."""
    raise todo()


@router.post("", response_model=LeadDetail, status_code=201, operation_id="createManualLead")
def create_manual_lead(body: ManualLead) -> LeadDetail:
    raise todo()


@router.post("/bulk", response_model=BulkResult, operation_id="bulkLeads")
def bulk(body: BulkAction) -> BulkResult:
    raise todo()


@router.get("/{lead_id}", response_model=LeadDetail, operation_id="getLead")
def get_lead(lead_id: int) -> LeadDetail:
    raise todo()


@router.post("/{lead_id}/shortlist", response_model=LeadDetail, operation_id="shortlistLead")
def shortlist(lead_id: int) -> LeadDetail:
    raise todo()


@router.post("/{lead_id}/skip", response_model=LeadDetail, operation_id="skipLead")
def skip(lead_id: int, body: SkipRequest) -> LeadDetail:
    raise todo()


@router.post("/{lead_id}/restore", response_model=LeadDetail, operation_id="restoreLead")
def restore(lead_id: int) -> LeadDetail:
    """Undo a prefilter drop."""
    raise todo()


@router.post("/{lead_id}/evaluate", response_model=RunOut, status_code=202, operation_id="evaluateLead")
def evaluate(lead_id: int) -> RunOut:
    raise todo()


@router.post("/{lead_id}/verify", response_model=RunOut, status_code=202, operation_id="verifyLead")
def verify(lead_id: int) -> RunOut:
    raise todo()


@router.post("/{lead_id}/cv", response_model=RunOut, status_code=202, operation_id="generateCv")
def generate_cv(lead_id: int, body: CvRequest) -> RunOut:
    raise todo()


@router.post("/{lead_id}/assist-apply", response_model=RunOut, status_code=202, operation_id="assistApply")
def assist_apply(lead_id: int) -> RunOut:
    """Opens a pre-filled application form in a browser. Never submits."""
    raise todo()


@router.post("/{lead_id}/contacts", response_model=RunOut, status_code=202, operation_id="findContacts")
def find_contacts(lead_id: int) -> RunOut:
    raise todo()


@router.get("/{lead_id}/outreach", response_model=list[OutreachOut], operation_id="leadOutreach")
def lead_outreach(lead_id: int) -> list[OutreachOut]:
    raise todo()
