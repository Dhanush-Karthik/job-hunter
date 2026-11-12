"""Sources, settings, secrets, profiles, setup wizard."""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Response
from keyring.errors import KeyringError
from sqlmodel import select

from jobhunter import gmail, paths, secrets
from jobhunter import settings as app_settings
from jobhunter.api.deps import SessionDep, as_utc, now_utc
from jobhunter.jobs import scheduler
from jobhunter.models import Profile, Source, SourceHealth
from jobhunter.schemas import (
    CheckResult,
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

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["config"])

_ONE_TIME = {"created": False, "alerts_on": False, "cv_uploaded": False}
# (platform, edit_url, refresh_every_days): plan section 3 platforms
PROFILE_SEED: list[tuple[str, str | None, int | None]] = [
    ("naukri", "https://www.naukri.com/mnjuser/profile", 1),
    *((name, None, None) for name in (
        "linkedin", "instahyre", "hirist", "cutshort", "wellfound", "uplers", "foundit", "turing", "arc")),
]


# ---------- sources ----------


def _source_out(row: SourceHealth) -> SourceOut:
    return SourceOut(
        source=row.source, enabled=row.enabled, paused_until=as_utc(row.paused_until),
        last_run_at=as_utc(row.last_run_at), last_ok_at=as_utc(row.last_ok_at), last_error=row.last_error,
        consecutive_failures=row.consecutive_failures, last_count=row.last_count,
    )


def _ensure_sources(session: SessionDep) -> None:
    wanted = [s.value for s in app_settings.get_settings(session).query_matrix.sites] + [Source.careerops_scan.value]
    have = set(session.exec(select(SourceHealth.source)))
    for name in wanted:
        if name not in have:
            session.add(SourceHealth(source=name))
            have.add(name)
    session.commit()


@router.get("/sources", response_model=list[SourceOut], operation_id="listSources")
def list_sources(session: SessionDep) -> list[SourceOut]:
    _ensure_sources(session)
    rows = session.exec(select(SourceHealth).order_by(SourceHealth.source))
    # per-company rows ("careerops:<company>") are internal detail, not a toggle for the owner
    return [_source_out(r) for r in rows if not r.source.startswith("careerops:")]


@router.patch("/sources/{source}", response_model=SourceOut, operation_id="patchSource")
def patch_source(source: str, body: SourcePatch, session: SessionDep) -> SourceOut:
    _ensure_sources(session)
    row = session.get(SourceHealth, source)
    if row is None:
        raise HTTPException(404, "source not found")
    if body.enabled is not None:
        row.enabled = body.enabled
    if body.unpause:
        row.paused_until, row.consecutive_failures = None, 0
    session.add(row)
    session.commit()
    return _source_out(row)


# ---------- settings ----------


@router.get("/settings", response_model=Settings, operation_id="getSettings")
def get_settings(session: SessionDep) -> Settings:
    return app_settings.get_settings(session)


@router.put("/settings", response_model=Settings, operation_id="putSettings")
def put_settings(body: Settings, session: SessionDep) -> Settings:
    saved = app_settings.save_settings(session, body)
    try:
        scheduler.reload(saved)
    except Exception:
        log.exception("scheduler reload failed after settings change")
    return saved


# ---------- secrets ----------


def _keychain(fn, *args):
    try:
        return fn(*args)
    except KeyringError as e:
        log.warning("keychain unavailable: %s", type(e).__name__)  # never the secret value
        raise HTTPException(503, "keychain unavailable") from e


@router.get("/secrets", response_model=list[SecretName], operation_id="listSecrets")
def list_secrets() -> list[SecretName]:
    """Presence only; values never leave the Keychain through the API."""
    return [SecretName(name=name, present=_keychain(secrets.present, name)) for name in secrets.NAMES]


@router.put("/secrets/{name}", status_code=204, operation_id="putSecret")
def put_secret(name: str, body: SecretPut) -> Response:
    if name not in secrets.NAMES:
        raise HTTPException(404, "unknown secret")
    _keychain(secrets.put, name, body.value)
    return Response(status_code=204)


# ---------- profiles ----------


def profile_due(p: Profile, now) -> bool:
    if p.refresh_every_days is None:
        return False
    last = as_utc(p.last_refreshed_at)
    return last is None or now - last >= timedelta(days=p.refresh_every_days)


def _profile_out(p: Profile, now) -> ProfileOut:
    return ProfileOut(
        platform=p.platform, edit_url=p.edit_url, last_refreshed_at=as_utc(p.last_refreshed_at),
        refresh_every_days=p.refresh_every_days, refresh_due=profile_due(p, now), checklist=p.checklist,
    )


def ensure_profiles(session: SessionDep) -> list[Profile]:
    """Profiles in seed order (then any others); seeds the table when it is empty."""
    rows = list(session.exec(select(Profile)))
    if not rows:
        rows = [
            Profile(platform=name, edit_url=url, refresh_every_days=days, checklist=dict(_ONE_TIME))
            for name, url, days in PROFILE_SEED
        ]
        session.add_all(rows)
        session.commit()
    order = {name: i for i, (name, _, _) in enumerate(PROFILE_SEED)}
    return sorted(rows, key=lambda p: (order.get(p.platform, len(order)), p.platform))


@router.get("/profiles", response_model=list[ProfileOut], operation_id="listProfiles")
def list_profiles(session: SessionDep) -> list[ProfileOut]:
    now = now_utc()
    return [_profile_out(p, now) for p in ensure_profiles(session)]


@router.patch("/profiles/{platform}", response_model=ProfileOut, operation_id="patchProfile")
def patch_profile(platform: str, body: ProfilePatch, session: SessionDep) -> ProfileOut:
    ensure_profiles(session)
    p = session.get(Profile, platform)
    if p is None:
        raise HTTPException(404, "profile not found")
    if body.checklist is not None:
        p.checklist = {**p.checklist, **body.checklist}  # new dict: JSON columns don't track in-place edits
    if body.refreshed_now:
        p.last_refreshed_at = now_utc()
    session.add(p)
    session.commit()
    return _profile_out(p, now_utc())


# ---------- setup ----------


def _service_ok(services, needle: str) -> bool:
    return any(needle in s.name.lower() and s.ok for s in services)


def _safe_present(name: str) -> bool:
    try:
        return secrets.present(name)
    except KeyringError:
        return False


def _setup_status() -> SetupStatus:
    try:
        services = scheduler.services()
    except Exception:
        log.warning("scheduler probe failed", exc_info=True)
        services = []
    cv_a, cv_b = (paths.CV_DIR / "cv_a.md").is_file(), (paths.CV_DIR / "cv_b.md").is_file()
    gmail = all(_safe_present(n) for n in secrets.NAMES)
    claude, careerops = _service_ok(services, "claude"), _service_ok(services, "career")
    return SetupStatus(
        cv_a=cv_a, cv_b=cv_b, gmail=gmail, claude_cli=claude, careerops=careerops,
        playwright=_service_ok(services, "playwright"), complete=cv_a and claude and careerops,
    )


@router.get("/setup", response_model=SetupStatus, operation_id="getSetup")
def setup_status() -> SetupStatus:
    return _setup_status()


@router.put("/setup/cv", response_model=SetupStatus, operation_id="putCv")
def put_cv(body: CvUpload) -> SetupStatus:
    paths.CV_DIR.mkdir(parents=True, exist_ok=True)
    (paths.CV_DIR / f"cv_{body.variant.value.lower()}.md").write_text(body.markdown)
    master = paths.CAREEROPS_DATA / "cv.md"
    if body.variant.value == "A" and not master.exists():  # career-ops master CV; never overwrite the owner's
        master.parent.mkdir(parents=True, exist_ok=True)
        master.write_text(body.markdown)
    return _setup_status()


@router.post("/setup/gmail-test", response_model=CheckResult, operation_id="testGmail")
def test_gmail() -> CheckResult:
    """Log in to Gmail IMAP with the Keychain secrets (read-only, no mail fetched); ok=False + reason on failure."""
    address, password = _keychain(secrets.get, "gmail_address"), _keychain(secrets.get, "gmail_app_password")
    missing = [label for label, value in (("address", address), ("app password", password)) if not value]
    if missing:
        return CheckResult(ok=False, detail=f"Gmail {' and '.join(missing)} not set")
    try:
        reason = gmail.check_login(address, password)
    except Exception as exc:  # noqa: BLE001 - any failure is a result for the setup wizard, not a 500
        log.warning("gmail login check crashed: %s", type(exc).__name__)
        return CheckResult(ok=False, detail=f"Gmail login check failed ({type(exc).__name__})")
    if reason is not None:
        return CheckResult(ok=False, detail=reason.replace(password, "***"))
    return CheckResult(ok=True, detail=f"Logged in to Gmail as {address} (read-only)")
