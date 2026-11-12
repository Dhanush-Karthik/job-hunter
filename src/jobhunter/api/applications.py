from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, PlainTextResponse

from jobhunter.api._stub import todo
from jobhunter.models import AppStatus
from jobhunter.schemas import ApplicationOut, ApplicationPatch, EventOut, TransitionRequest

router = APIRouter(prefix="/api/applications", tags=["applications"])


@router.get("", response_model=list[ApplicationOut], operation_id="listApplications")
def list_applications(
    status: list[AppStatus] | None = Query(None),
    q: str | None = None,
) -> list[ApplicationOut]:
    raise todo()


@router.get(
    "/export.csv",
    response_class=PlainTextResponse,
    responses={200: {"content": {"text/csv": {}}}},
    operation_id="exportApplicationsCsv",
)
def export_csv() -> str:
    raise todo()


@router.get("/{app_id}", response_model=ApplicationOut, operation_id="getApplication")
def get_application(app_id: int) -> ApplicationOut:
    raise todo()


@router.patch("/{app_id}", response_model=ApplicationOut, operation_id="patchApplication")
def patch_application(app_id: int, body: ApplicationPatch) -> ApplicationOut:
    raise todo()


@router.post(
    "/{app_id}/transition",
    response_model=ApplicationOut,
    responses={409: {"description": "transition not allowed"}},
    operation_id="transitionApplication",
)
def transition(app_id: int, body: TransitionRequest) -> ApplicationOut:
    raise todo()


@router.get("/{app_id}/events", response_model=list[EventOut], operation_id="applicationEvents")
def events(app_id: int) -> list[EventOut]:
    raise todo()


@router.get(
    "/{app_id}/cv.pdf",
    response_class=FileResponse,
    responses={200: {"content": {"application/pdf": {}}}},
    operation_id="applicationCvPdf",
)
def cv_pdf(app_id: int) -> FileResponse:
    raise todo()
