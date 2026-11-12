"""Tracked companies for the career-ops scan (data/careerops/portals.yml, career-ops format)."""

from __future__ import annotations

from fastapi import APIRouter, Response

from jobhunter.api._stub import todo
from jobhunter.schemas import Company, CompanyIn, CompanyPatch

router = APIRouter(prefix="/api/companies", tags=["config"])


@router.get("", response_model=list[Company], operation_id="listCompanies")
def list_companies() -> list[Company]:
    """tracked_companies from portals.yml, in file order. Empty list if the file is missing."""
    raise todo()


@router.post("", response_model=Company, status_code=201, operation_id="addCompany")
def add_company(body: CompanyIn) -> Company:
    """Append (provider None, websearch scan). 409 if the name exists (case-insensitive)."""
    raise todo()


@router.patch("/{name}", response_model=Company, operation_id="patchCompany")
def patch_company(name: str, body: CompanyPatch) -> Company:
    raise todo()


@router.delete("/{name}", status_code=204, operation_id="deleteCompany")
def delete_company(name: str) -> Response:
    raise todo()
