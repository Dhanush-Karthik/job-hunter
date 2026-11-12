"""Sources, settings, secrets, profiles, setup wizard."""

from __future__ import annotations

from fastapi import APIRouter, Response

from jobhunter.api._stub import todo
from jobhunter.schemas import (
    CvUpload,
    ProfileOut,
    ProfilePatch,
    SecretName,
    SecretPut,
    Settings,
    SetupStatus,
    SourceOut,
    SourcePatch,
)

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/sources", response_model=list[SourceOut], operation_id="listSources")
def list_sources() -> list[SourceOut]:
    raise todo()


@router.patch("/sources/{source}", response_model=SourceOut, operation_id="patchSource")
def patch_source(source: str, body: SourcePatch) -> SourceOut:
    raise todo()


@router.get("/settings", response_model=Settings, operation_id="getSettings")
def get_settings() -> Settings:
    raise todo()


@router.put("/settings", response_model=Settings, operation_id="putSettings")
def put_settings(body: Settings) -> Settings:
    raise todo()


@router.get("/secrets", response_model=list[SecretName], operation_id="listSecrets")
def list_secrets() -> list[SecretName]:
    """Presence only; values never leave the Keychain through the API."""
    raise todo()


@router.put("/secrets/{name}", status_code=204, operation_id="putSecret")
def put_secret(name: str, body: SecretPut) -> Response:
    raise todo()


@router.get("/profiles", response_model=list[ProfileOut], operation_id="listProfiles")
def list_profiles() -> list[ProfileOut]:
    raise todo()


@router.patch("/profiles/{platform}", response_model=ProfileOut, operation_id="patchProfile")
def patch_profile(platform: str, body: ProfilePatch) -> ProfileOut:
    raise todo()


@router.get("/setup", response_model=SetupStatus, operation_id="getSetup")
def setup_status() -> SetupStatus:
    raise todo()


@router.put("/setup/cv", response_model=SetupStatus, operation_id="putCv")
def put_cv(body: CvUpload) -> SetupStatus:
    raise todo()
