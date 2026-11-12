"""SQLite tables (lead-owned contract, plan section 6.2). Builders read these, never edit them.

Times are UTC (write aware datetimes; SQLite hands them back naive, treat naive as UTC). Money is LPA (lakh INR per annum) as float.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class Source(StrEnum):
    linkedin = "linkedin"
    naukri = "naukri"
    indeed = "indeed"
    glassdoor = "glassdoor"
    google = "google"
    careerops_scan = "careerops_scan"  # company career pages via career-ops scan
    remotive = "remotive"
    weworkremotely = "weworkremotely"
    yc = "yc"
    himalayas = "himalayas"
    remoteok = "remoteok"
    gmail_alert = "gmail_alert"  # job-alert emails (Hirist, Instahyre, ...); sender in Lead.source_detail
    gmail_inbound = "gmail_inbound"  # recruiter reached out
    manual = "manual"


class ApplyChannel(StrEnum):
    platform_quick = "platform_quick"  # Naukri / LinkedIn Easy Apply / Instahyre 1-click
    company_ats = "company_ats"  # Workday, Greenhouse, Lever, ... form
    email = "email"
    unknown = "unknown"


class WorkMode(StrEnum):
    onsite = "onsite"
    hybrid = "hybrid"
    remote = "remote"
    unknown = "unknown"


class RoleFamily(StrEnum):
    p1 = "P1"  # Java/Spring backend, IAM/Keycloak
    p2 = "P2"  # platform, general SDE with Java signal
    other = "other"


class AppStatus(StrEnum):
    new = "New"
    shortlisted = "Shortlisted"
    ready = "Ready"
    applied = "Applied"
    screening = "Screening"
    technical = "Technical"
    final = "Final"
    offer = "Offer"
    accepted = "Accepted"
    declined = "Declined"
    rejected = "Rejected"
    ghosted = "Ghosted"
    withdrawn = "Withdrawn"
    skipped = "Skipped"
    expired = "Expired"


# Allowed transitions (plan section 6.3). Entering Screening counts as an interview call.
TRANSITIONS: dict[AppStatus, set[AppStatus]] = {
    AppStatus.new: {AppStatus.shortlisted, AppStatus.skipped, AppStatus.expired},
    AppStatus.shortlisted: {AppStatus.ready, AppStatus.skipped},
    AppStatus.ready: {AppStatus.applied},
    AppStatus.applied: {AppStatus.screening, AppStatus.rejected, AppStatus.ghosted, AppStatus.withdrawn},
    AppStatus.screening: {AppStatus.technical, AppStatus.rejected, AppStatus.withdrawn},
    AppStatus.technical: {AppStatus.final, AppStatus.rejected, AppStatus.withdrawn},
    AppStatus.final: {AppStatus.offer, AppStatus.rejected},
    AppStatus.offer: {AppStatus.accepted, AppStatus.declined},
    AppStatus.ghosted: {AppStatus.screening},
    AppStatus.accepted: set(),
    AppStatus.declined: set(),
    AppStatus.rejected: set(),
    AppStatus.withdrawn: set(),
    AppStatus.skipped: set(),
    AppStatus.expired: set(),
}
TERMINAL: frozenset[AppStatus] = frozenset(s for s, nxt in TRANSITIONS.items() if not nxt)
INTERVIEW_CALL_STATUS = AppStatus.screening


class Actor(StrEnum):
    owner = "owner"
    system = "system"
    proposal = "proposal"


class ProposalType(StrEnum):
    status_change = "status_change"
    ghosted = "ghosted"
    inbound = "inbound"
    needs_eyes = "needs_eyes"


class ProposalState(StrEnum):
    pending = "pending"
    accepted = "accepted"
    dismissed = "dismissed"


class OutreachKind(StrEnum):
    referral = "referral"
    follow_up = "follow_up"
    recruiter_reply = "recruiter_reply"


class RunKind(StrEnum):
    intake_boards = "intake_boards"
    intake_remote = "intake_remote"
    intake_gmail = "intake_gmail"
    careerops_scan = "careerops_scan"
    evaluate = "evaluate"
    verify = "verify"
    cv = "cv"
    assist_apply = "assist_apply"
    contacts = "contacts"
    followups = "followups"


class RunState(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class ResumeVariant(StrEnum):
    a = "A"
    b = "B"


class Lead(SQLModel, table=True):
    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("source", "source_ref"),)

    id: int | None = Field(default=None, primary_key=True)
    source: Source = Field(index=True)
    source_ref: str  # site job id, email message-id + card index, ...
    source_detail: str | None = None  # e.g. alert sender "hirist", query that found it
    canonical_url: str | None = Field(default=None, index=True)
    apply_url: str | None = None
    apply_channel: ApplyChannel = ApplyChannel.unknown
    company: str = Field(index=True)
    title: str
    location: str | None = None
    work_mode: WorkMode = WorkMode.unknown
    exp_min: float | None = None
    exp_max: float | None = None
    ctc_min: float | None = None  # LPA
    ctc_max: float | None = None  # LPA
    posted_at: datetime | None = None
    found_at: datetime = Field(default_factory=utcnow, index=True)
    jd_text: str | None = None
    role_family: RoleFamily = RoleFamily.other
    prefilter_pass: bool = True
    prefilter_reasons: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    prefilter_tags: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    restored: bool = False  # owner overrode a prefilter drop
    quick_score: float = Field(default=0.0, index=True)
    is_inbound: bool = False
    dedupe_group: str | None = Field(default=None, index=True)  # same value = same job; lowest id is primary
    raw: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class Evaluation(SQLModel, table=True):
    __tablename__ = "evaluations"

    id: int | None = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="leads.id", index=True)
    score: float | None = None  # career-ops 0-5
    grade: str | None = None  # A-F
    report_path: str | None = None  # under data/careerops/
    is_live: bool | None = None
    live_verified_at: datetime | None = None
    run_id: int | None = Field(default=None, foreign_key="runs.id")
    created_at: datetime = Field(default_factory=utcnow)


class Application(SQLModel, table=True):
    __tablename__ = "applications"

    id: int | None = Field(default=None, primary_key=True)
    lead_id: int = Field(foreign_key="leads.id", unique=True)
    status: AppStatus = Field(default=AppStatus.new, index=True)
    resume_variant: ResumeVariant | None = None
    cv_pdf_path: str | None = None
    cv_approved: bool = False
    applied_at: datetime | None = None
    next_follow_up_at: datetime | None = Field(default=None, index=True)
    referral_contact: str | None = None
    recruiter: str | None = None
    notes: str | None = None
    rejected_at_stage: AppStatus | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: int | None = Field(default=None, primary_key=True)
    application_id: int = Field(foreign_key="applications.id", index=True)
    from_status: AppStatus | None = None
    to_status: AppStatus
    at: datetime = Field(default_factory=utcnow, index=True)
    actor: Actor = Actor.owner
    note: str | None = None


class Proposal(SQLModel, table=True):
    __tablename__ = "proposals"

    id: int | None = Field(default=None, primary_key=True)
    type: ProposalType
    application_id: int | None = Field(default=None, foreign_key="applications.id")
    lead_id: int | None = Field(default=None, foreign_key="leads.id")
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    evidence: str | None = None  # email subject + snippet, never full bodies
    confidence: float = 0.0
    state: ProposalState = Field(default=ProposalState.pending, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    decided_at: datetime | None = None


class Outreach(SQLModel, table=True):
    __tablename__ = "outreach"

    id: int | None = Field(default=None, primary_key=True)
    application_id: int | None = Field(default=None, foreign_key="applications.id", index=True)
    lead_id: int | None = Field(default=None, foreign_key="leads.id")
    kind: OutreachKind
    contact: str | None = None  # name + profile url
    draft: str | None = None
    due_at: datetime | None = None
    snoozed_until: datetime | None = None
    sent_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Profile(SQLModel, table=True):
    __tablename__ = "profiles"

    platform: str = Field(primary_key=True)  # naukri, linkedin, instahyre, ...
    edit_url: str | None = None
    last_refreshed_at: datetime | None = None
    refresh_every_days: int | None = None  # None = one-time checklist only
    checklist: dict[str, bool] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class Run(SQLModel, table=True):
    __tablename__ = "runs"

    id: int | None = Field(default=None, primary_key=True)
    kind: RunKind = Field(index=True)
    state: RunState = Field(default=RunState.queued, index=True)
    lead_id: int | None = Field(default=None, foreign_key="leads.id")
    params: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    log_path: str | None = None  # under data/logs/runs/
    summary: str | None = None  # e.g. "42 fetched, 7 new"
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow, index=True)


class SourceHealth(SQLModel, table=True):
    __tablename__ = "source_health"

    source: str = Field(primary_key=True)  # Source value, or "careerops:<company>"
    enabled: bool = True
    paused_until: datetime | None = None  # auto-pause after repeated failures
    last_run_at: datetime | None = None
    last_ok_at: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    last_count: int = 0  # leads fetched last run


class SettingRow(SQLModel, table=True):
    __tablename__ = "settings"

    key: str = Field(primary_key=True)
    value: Any = Field(sa_column=Column(JSON, nullable=True))


class SchemaVersion(SQLModel, table=True):
    __tablename__ = "schema_version"

    id: int = Field(default=1, primary_key=True)
    version: int
    applied_at: datetime = Field(default_factory=utcnow)
