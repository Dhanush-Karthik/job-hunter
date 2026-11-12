from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import or_
from sqlmodel import select

from jobhunter import paths
from jobhunter.api import convert, workflow
from jobhunter.api.deps import SessionDep, now_utc
from jobhunter.models import Actor, Application, AppStatus, Event, Lead
from jobhunter.schemas import ApplicationOut, ApplicationPatch, EventOut, TransitionRequest

router = APIRouter(prefix="/api/applications", tags=["applications"])

CSV_COLUMNS = [
    "application_id", "lead_id", "company", "title", "location", "source", "apply_channel", "apply_url",
    "status", "rejected_at_stage", "created_at", "applied_at", "next_follow_up_at", "resume_variant",
    "eval_score", "referral_contact", "recruiter", "notes",
]


def _query(status: list[AppStatus] | None, q: str | None):
    stmt = select(Application).join(Lead, Lead.id == Application.lead_id)
    if status:
        stmt = stmt.where(Application.status.in_(status))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Lead.company.ilike(like), Lead.title.ilike(like)))
    return stmt.order_by(Application.updated_at.desc(), Application.id.desc())


@router.get("", response_model=list[ApplicationOut], operation_id="listApplications")
def list_applications(
    session: SessionDep,
    status: list[AppStatus] | None = Query(None),
    q: str | None = None,
) -> list[ApplicationOut]:
    return convert.application_outs(session, list(session.exec(_query(status, q))))


def _cell(value) -> str:
    """One CSV cell; a leading = + - @ would run as a formula in Excel, so it gets a quote prefix."""
    if value is None:
        return ""
    text = value.value if hasattr(value, "value") else value.isoformat() if hasattr(value, "isoformat") else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


@router.get(
    "/export.csv",
    response_class=PlainTextResponse,
    responses={200: {"content": {"text/csv": {}}}},
    operation_id="exportApplicationsCsv",
)
def export_csv(session: SessionDep) -> str:
    apps = list(session.exec(_query(None, None)))
    leads = {lead.id: lead for lead in session.exec(select(Lead).where(Lead.id.in_({a.lead_id for a in apps})))}
    scores = {i: e.score for i, e in convert.latest_evaluations(session, list(leads)).items()}
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    for a in apps:
        lead = leads[a.lead_id]
        values = [
            a.id, lead.id, lead.company, lead.title, lead.location, lead.source, lead.apply_channel,
            lead.apply_url, a.status, a.rejected_at_stage, convert.as_utc(a.created_at),
            convert.as_utc(a.applied_at), convert.as_utc(a.next_follow_up_at), a.resume_variant,
            scores.get(lead.id), a.referral_contact, a.recruiter, a.notes,
        ]
        writer.writerow([_cell(v) for v in values])
    return Response(
        buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="applications.csv"'},
    )


@router.get("/{app_id}", response_model=ApplicationOut, operation_id="getApplication")
def get_application(app_id: int, session: SessionDep) -> ApplicationOut:
    return convert.application_out(session, workflow.get_application_or_404(session, app_id))


@router.patch("/{app_id}", response_model=ApplicationOut, operation_id="patchApplication")
def patch_application(app_id: int, body: ApplicationPatch, session: SessionDep) -> ApplicationOut:
    app = workflow.get_application_or_404(session, app_id)
    changes = body.model_dump(exclude_unset=True)
    for field in ("resume_variant", "referral_contact", "recruiter", "notes", "next_follow_up_at"):
        if field in changes:
            setattr(app, field, changes[field])
    if changes.get("cv_approved") is not None:
        app.cv_approved = changes["cv_approved"]
        if app.cv_approved and app.status == AppStatus.shortlisted:
            workflow.transition(session, app, AppStatus.ready, note="CV approved")
    app.updated_at = now_utc()
    session.add(app)
    session.commit()
    return convert.application_out(session, app)


@router.post(
    "/{app_id}/transition",
    response_model=ApplicationOut,
    responses={409: {"description": "transition not allowed"}},
    operation_id="transitionApplication",
)
def transition(app_id: int, body: TransitionRequest, session: SessionDep) -> ApplicationOut:
    app = workflow.get_application_or_404(session, app_id)
    workflow.transition(
        session, app, body.to_status, rejected_at_stage=body.rejected_at_stage, note=body.note, actor=Actor.owner
    )
    session.commit()
    return convert.application_out(session, app)


@router.get("/{app_id}/events", response_model=list[EventOut], operation_id="applicationEvents")
def events(app_id: int, session: SessionDep) -> list[EventOut]:
    workflow.get_application_or_404(session, app_id)
    rows = session.exec(select(Event).where(Event.application_id == app_id).order_by(Event.at, Event.id))
    return [convert.event_out(e) for e in rows]


@router.get(
    "/{app_id}/cv.pdf",
    response_class=FileResponse,
    responses={200: {"content": {"application/pdf": {}}}},
    operation_id="applicationCvPdf",
)
def cv_pdf(app_id: int, session: SessionDep) -> FileResponse:
    app = workflow.get_application_or_404(session, app_id)
    if not app.cv_pdf_path:
        raise HTTPException(404, "no CV generated yet")
    root = Path(paths.DATA).resolve()
    path = (root / app.cv_pdf_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():  # stored path must stay under data/
        raise HTTPException(404, "CV file missing")
    return FileResponse(path, media_type="application/pdf", filename=path.name)
