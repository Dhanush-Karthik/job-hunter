"""Proposals (replies, inbound, ghosted) and outreach (referrals, follow-ups)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from jobhunter.api._stub import todo
from jobhunter.models import OutreachKind, ProposalState
from jobhunter.schemas import (
    ApplicationOut,
    OutreachOut,
    OutreachPatch,
    ProposalAccept,
    ProposalOut,
    SnoozeRequest,
)

proposals = APIRouter(prefix="/api/proposals", tags=["proposals"])
outreach = APIRouter(prefix="/api/outreach", tags=["outreach"])


@proposals.get("", response_model=list[ProposalOut], operation_id="listProposals")
def list_proposals(state: ProposalState = ProposalState.pending) -> list[ProposalOut]:
    raise todo()


@proposals.post("/{proposal_id}/accept", response_model=ProposalOut, operation_id="acceptProposal")
def accept(proposal_id: int, body: ProposalAccept) -> ProposalOut:
    raise todo()


@proposals.post("/{proposal_id}/dismiss", response_model=ProposalOut, operation_id="dismissProposal")
def dismiss(proposal_id: int) -> ProposalOut:
    raise todo()


@proposals.post(
    "/{proposal_id}/convert", response_model=ApplicationOut, operation_id="convertInboundProposal"
)
def convert(proposal_id: int) -> ApplicationOut:
    """Inbound recruiter lead -> application (Shortlisted)."""
    raise todo()


@outreach.get("", response_model=list[OutreachOut], operation_id="listOutreach")
def list_outreach(
    kind: OutreachKind | None = None,
    due_only: bool = Query(False, description="unsent, not snoozed, due_at <= now"),
    sent: bool | None = None,
) -> list[OutreachOut]:
    raise todo()


@outreach.patch("/{outreach_id}", response_model=OutreachOut, operation_id="patchOutreach")
def patch_outreach(outreach_id: int, body: OutreachPatch) -> OutreachOut:
    raise todo()


@outreach.post("/{outreach_id}/mark-sent", response_model=OutreachOut, operation_id="markOutreachSent")
def mark_sent(outreach_id: int) -> OutreachOut:
    """Owner sent it themselves; the app never sends."""
    raise todo()


@outreach.post("/{outreach_id}/snooze", response_model=OutreachOut, operation_id="snoozeOutreach")
def snooze(outreach_id: int, body: SnoozeRequest) -> OutreachOut:
    raise todo()
