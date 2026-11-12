"""Proposals (replies, inbound, ghosted) and outreach (referrals, follow-ups)."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import or_
from sqlmodel import select

from jobhunter.api import convert as conv
from jobhunter.api import workflow
from jobhunter.api.deps import SessionDep, db_dt, fits, now_utc
from jobhunter.models import Actor, AppStatus, Outreach, OutreachKind, Proposal, ProposalState, ProposalType
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


def _proposal(session: SessionDep, proposal_id: int) -> Proposal:
    p = session.get(Proposal, proposal_id) if fits(proposal_id) else None
    if p is None:
        raise HTTPException(404, "proposal not found")
    return p


def _pending(p: Proposal) -> None:
    if p.state != ProposalState.pending:
        raise HTTPException(409, f"proposal already {p.state.value}")


def _status(value: object) -> AppStatus:
    try:
        return AppStatus(value)
    except ValueError as e:
        raise workflow.unprocessable("payload", f"unknown status {value!r} in proposal payload") from e


def _apply_status_change(session: SessionDep, p: Proposal) -> None:
    payload = p.payload or {}
    default = AppStatus.ghosted.value if p.type == ProposalType.ghosted else None
    to = _status(payload.get("to_status", default))
    stage = _status(payload["rejected_at_stage"]) if payload.get("rejected_at_stage") else None
    if p.application_id is not None:
        app = workflow.get_application_or_404(session, p.application_id)
    elif p.lead_id is not None:
        app = workflow.ensure_application(session, p.lead_id)
    else:
        raise workflow.unprocessable("proposal_id", "proposal has no application to change", "path")
    workflow.transition(session, app, to, rejected_at_stage=stage, note=f"proposal #{p.id}", actor=Actor.proposal)


@proposals.get("", response_model=list[ProposalOut], operation_id="listProposals")
def list_proposals(session: SessionDep, state: ProposalState = ProposalState.pending) -> list[ProposalOut]:
    rows = session.exec(
        select(Proposal).where(Proposal.state == state).order_by(Proposal.created_at.desc(), Proposal.id.desc())
    )
    return conv.proposal_outs(session, list(rows))


@proposals.post("/{proposal_id}/accept", response_model=ProposalOut, operation_id="acceptProposal")
def accept(proposal_id: int, body: ProposalAccept, session: SessionDep) -> ProposalOut:
    p = _proposal(session, proposal_id)
    _pending(p)
    if body.payload is not None:
        p.payload = body.payload
    if p.type in (ProposalType.status_change, ProposalType.ghosted):
        _apply_status_change(session, p)
    # inbound / needs_eyes: nothing to apply, accepting acknowledges it (convert makes the application)
    p.state, p.decided_at = ProposalState.accepted, now_utc()
    session.add(p)
    session.commit()
    return conv.proposal_outs(session, [p])[0]


@proposals.post("/{proposal_id}/dismiss", response_model=ProposalOut, operation_id="dismissProposal")
def dismiss(proposal_id: int, session: SessionDep) -> ProposalOut:
    p = _proposal(session, proposal_id)
    _pending(p)
    p.state, p.decided_at = ProposalState.dismissed, now_utc()
    session.add(p)
    session.commit()
    return conv.proposal_outs(session, [p])[0]


@proposals.post(
    "/{proposal_id}/convert", response_model=ApplicationOut, operation_id="convertInboundProposal"
)
def convert(proposal_id: int, session: SessionDep) -> ApplicationOut:
    """Inbound recruiter lead -> application (Shortlisted)."""
    p = _proposal(session, proposal_id)
    if p.type != ProposalType.inbound:
        raise HTTPException(409, "only inbound proposals can be converted")
    _pending(p)
    if p.lead_id is None:
        raise workflow.unprocessable("proposal_id", "inbound proposal has no lead", "path")
    app = workflow.ensure_application(session, p.lead_id)
    if app.status == AppStatus.new:
        workflow.transition(session, app, AppStatus.shortlisted, note="inbound recruiter")
    p.state, p.decided_at = ProposalState.accepted, now_utc()
    session.add(p)
    session.commit()
    return conv.application_out(session, app)


@outreach.get("", response_model=list[OutreachOut], operation_id="listOutreach")
def list_outreach(
    session: SessionDep,
    kind: OutreachKind | None = None,
    due_only: bool = Query(False, description="unsent, not snoozed, due_at <= now"),
    sent: bool | None = None,
) -> list[OutreachOut]:
    stmt = select(Outreach)
    if kind is not None:
        stmt = stmt.where(Outreach.kind == kind)
    if sent is not None:
        stmt = stmt.where(Outreach.sent_at.is_not(None) if sent else Outreach.sent_at.is_(None))
    if due_only:
        now = db_dt(now_utc())
        stmt = stmt.where(
            Outreach.sent_at.is_(None),
            Outreach.due_at.is_not(None),
            Outreach.due_at <= now,
            or_(Outreach.snoozed_until.is_(None), Outreach.snoozed_until <= now),
        )
    rows = session.exec(stmt.order_by(Outreach.due_at.asc().nulls_last(), Outreach.id))
    return conv.outreach_outs(session, list(rows))


def _outreach(session: SessionDep, outreach_id: int) -> Outreach:
    row = session.get(Outreach, outreach_id) if fits(outreach_id) else None
    if row is None:
        raise HTTPException(404, "outreach not found")
    return row


@outreach.patch("/{outreach_id}", response_model=OutreachOut, operation_id="patchOutreach")
def patch_outreach(outreach_id: int, body: OutreachPatch, session: SessionDep) -> OutreachOut:
    row = _outreach(session, outreach_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    session.add(row)
    session.commit()
    return conv.outreach_outs(session, [row])[0]


@outreach.post("/{outreach_id}/mark-sent", response_model=OutreachOut, operation_id="markOutreachSent")
def mark_sent(outreach_id: int, session: SessionDep) -> OutreachOut:
    """Owner sent it themselves; the app never sends."""
    row = _outreach(session, outreach_id)
    if row.sent_at is None:  # keep the first timestamp on a repeated click
        row.sent_at = now_utc()
    session.add(row)
    session.commit()
    return conv.outreach_outs(session, [row])[0]


@outreach.post("/{outreach_id}/snooze", response_model=OutreachOut, operation_id="snoozeOutreach")
def snooze(outreach_id: int, body: SnoozeRequest, session: SessionDep) -> OutreachOut:
    row = _outreach(session, outreach_id)
    row.snoozed_until = now_utc() + timedelta(days=body.days)
    session.add(row)
    session.commit()
    return conv.outreach_outs(session, [row])[0]
