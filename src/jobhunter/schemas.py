"""API request/response shapes (lead-owned contract). contracts/openapi.json is generated from these.

Builders implement routes against these models; changing a shape is a lead decision.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

from jobhunter.models import (
    Actor,
    ApplyChannel,
    AppStatus,
    OutreachKind,
    ProposalState,
    ProposalType,
    ResumeVariant,
    RoleFamily,
    RunKind,
    RunState,
    Source,
    WorkMode,
)

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class Problem(BaseModel):
    detail: str


# ---------- leads ----------


class LeadSummary(BaseModel):
    id: int
    source: Source
    source_detail: str | None = None
    company: str
    title: str
    location: str | None = None
    work_mode: WorkMode
    apply_channel: ApplyChannel
    apply_url: str | None = None
    canonical_url: str | None = None
    exp_min: float | None = None
    exp_max: float | None = None
    ctc_min: float | None = None
    ctc_max: float | None = None
    posted_at: datetime | None = None
    found_at: datetime
    is_fresh: bool = Field(description="posted (or found, if unknown) within the last 48 h")
    role_family: RoleFamily
    quick_score: float
    eval_score: float | None = None
    eval_grade: str | None = None
    is_live: bool | None = None
    is_inbound: bool
    prefilter_pass: bool
    prefilter_reasons: list[str]
    prefilter_tags: list[str]
    restored: bool
    duplicates: int = Field(0, description="other leads in the same dedupe group")
    status: AppStatus = Field(description="application status, New if none yet")
    application_id: int | None = None


class Evaluation(BaseModel):
    id: int
    score: float | None = None
    grade: str | None = None
    report_md: str | None = None
    is_live: bool | None = None
    live_verified_at: datetime | None = None
    created_at: datetime


class EventOut(BaseModel):
    id: int
    application_id: int
    from_status: AppStatus | None = None
    to_status: AppStatus
    at: datetime
    actor: Actor
    note: str | None = None


class ApplicationOut(BaseModel):
    id: int
    lead_id: int
    company: str
    title: str
    status: AppStatus
    resume_variant: ResumeVariant | None = None
    has_cv_pdf: bool
    cv_approved: bool
    applied_at: datetime | None = None
    next_follow_up_at: datetime | None = None
    referral_contact: str | None = None
    recruiter: str | None = None
    notes: str | None = None
    rejected_at_stage: AppStatus | None = None
    source: Source
    apply_channel: ApplyChannel
    eval_score: float | None = None
    created_at: datetime
    updated_at: datetime


class OutreachOut(BaseModel):
    id: int
    application_id: int | None = None
    lead_id: int | None = None
    company: str | None = None
    title: str | None = None
    kind: OutreachKind
    contact: str | None = None
    draft: str | None = None
    due_at: datetime | None = None
    snoozed_until: datetime | None = None
    sent_at: datetime | None = None
    created_at: datetime


class LeadDetail(LeadSummary):
    jd_text: str | None = None
    evaluation: Evaluation | None = None
    application: ApplicationOut | None = None
    events: list[EventOut] = []
    outreach: list[OutreachOut] = []
    duplicate_ids: list[int] = []


class SkipRequest(BaseModel):
    reason: str


class BulkAction(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    action: Literal["shortlist", "skip", "evaluate", "verify", "restore"]
    reason: str | None = Field(None, description="required for skip")


class BulkResult(BaseModel):
    ok: list[int]
    failed: dict[int, str] = Field(default_factory=dict, description="lead id -> error")
    run_ids: list[int] = []


class CvRequest(BaseModel):
    variant: ResumeVariant


class ManualLead(BaseModel):
    company: str
    title: str
    url: str | None = None
    location: str | None = None
    jd_text: str | None = None


# ---------- applications ----------


class ApplicationPatch(BaseModel):
    resume_variant: ResumeVariant | None = None
    cv_approved: bool | None = None
    referral_contact: str | None = None
    recruiter: str | None = None
    notes: str | None = None
    next_follow_up_at: datetime | None = None


class TransitionRequest(BaseModel):
    to_status: AppStatus
    rejected_at_stage: AppStatus | None = Field(None, description="required when to_status=Rejected")
    note: str | None = None


# ---------- proposals ----------


class ProposalOut(BaseModel):
    id: int
    type: ProposalType
    application_id: int | None = None
    lead_id: int | None = None
    company: str | None = None
    title: str | None = None
    payload: dict[str, Any]
    evidence: str | None = None
    confidence: float
    state: ProposalState
    created_at: datetime


class ProposalAccept(BaseModel):
    payload: dict[str, Any] | None = Field(None, description="owner edits; replaces payload before applying")


# ---------- outreach ----------


class SnoozeRequest(BaseModel):
    days: int = Field(ge=1, le=30)


class OutreachPatch(BaseModel):
    contact: str | None = None
    draft: str | None = None


# ---------- runs ----------


class RunOut(BaseModel):
    id: int
    kind: RunKind
    state: RunState
    lead_id: int | None = None
    params: dict[str, Any]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    summary: str | None = None
    error: str | None = None
    created_at: datetime


class RunLog(BaseModel):
    run_id: int
    text: str
    truncated: bool


class IntakeRequest(BaseModel):
    sources: list[Source] | None = Field(None, description="None = all enabled sources")


# ---------- today / analytics ----------


class ActionItem(BaseModel):
    kind: Literal["inbound", "proposal", "follow_up", "quick_apply", "profile_refresh", "cv_review", "referral"]
    title: str
    subtitle: str | None = None
    lead_id: int | None = None
    application_id: int | None = None
    proposal_id: int | None = None
    outreach_id: int | None = None
    platform: str | None = None
    due_at: datetime | None = None


class ServiceHealth(BaseModel):
    name: str
    ok: bool
    detail: str | None = None


class TodaySummary(BaseModel):
    interview_calls_week: int
    interview_calls_prev_week: int
    applied_week: int
    applied_target: int
    referrals_week: int
    referrals_target: int
    fresh_hot_leads: list[LeadSummary]
    actions: list[ActionItem]
    health: list[ServiceHealth]


class FunnelStage(BaseModel):
    status: AppStatus
    count: int
    conversion_from_prev: float | None = None


class Funnel(BaseModel):
    stages: list[FunnelStage]
    date_from: datetime | None = None
    date_to: datetime | None = None


class BreakdownRow(BaseModel):
    key: str
    applied: int
    calls: int
    rate: float | None = None


class Breakdown(BaseModel):
    by: Literal["source", "channel", "title", "variant", "role_family"]
    rows: list[BreakdownRow]


class WeeklyPoint(BaseModel):
    week_start: datetime
    applied: int
    calls: int
    referrals: int
    applied_target: int
    referrals_target: int


class ResponseTimes(BaseModel):
    median_days_to_first_response: float | None = None
    p90_days_to_first_response: float | None = None
    samples: int


class RejectAuditRow(BaseModel):
    reason: str
    count: int
    sample_lead_ids: list[int]


class Insight(BaseModel):
    """One plain-English, rule-based observation for the Analytics page (no LLM)."""

    kind: Literal["best_source", "weak_source", "variant", "channel", "title", "pace", "response_time", "rejects"]
    text: str = Field(description='e.g. "Naukri: 3 calls from 12 applies (25%), best source this month"')
    severity: Literal["info", "good", "warn"] = "info"
    metric: float | None = None


# ---------- sources / settings / secrets / profiles ----------


class SourceOut(BaseModel):
    source: str
    enabled: bool
    paused_until: datetime | None = None
    last_run_at: datetime | None = None
    last_ok_at: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int
    last_count: int


class SourcePatch(BaseModel):
    enabled: bool | None = None
    unpause: bool | None = None


class QueryMatrix(BaseModel):
    titles: list[str]
    locations: list[str]
    sites: list[Source]
    hours_old: int = Field(72, ge=1, le=720)
    results_wanted: int = Field(50, ge=1, le=50)


class PrefilterRules(BaseModel):
    cities: list[str]
    remote_ok: bool = True
    exp_years: tuple[float, float] = (2, 4)
    exp_drop_min_at_least: float = 6
    ctc_min_lpa: float = 10
    usd_inr: float = 85.0
    max_age_days_pass: int = 14
    max_age_days_drop: int = 30
    stack_positive: list[str]
    stack_negative: list[str]


class Schedules(BaseModel):
    boards_every_hours: int = Field(3, ge=1, le=24)
    boards_window: tuple[int, int] = Field((7, 23), description="local hours [start, end)")
    careerops_scan_times: list[str] = Field(["08:00", "17:00"], description="HH:MM local")
    remote_boards_times: list[str] = ["08:30", "17:30"]
    gmail_every_minutes: int = Field(30, ge=5, le=240)


class Targets(BaseModel):
    applied_per_week: int = 60
    referrals_per_week: int = 15
    min_eval_score: float = 3.5


class FollowupRules(BaseModel):
    follow_up_business_days: int = Field(5, ge=1, le=20, description="after applied_at, IST business days")
    second_follow_up_business_days: int = Field(7, ge=1, le=30, description="after the first follow-up was sent")
    ghosted_after_days: int = Field(21, ge=7, le=90, description="Applied with no event since -> ghosted proposal")
    quiet_hours: tuple[int, int] = Field((23, 7), description="local hours [start, end) with no notifications")
    gmail_lookback_days: int = Field(14, ge=1, le=90, description="first Gmail run reads this far back")
    extra_holidays: list[str] = Field([], description="YYYY-MM-DD, added to the built-in IST holiday list")


class Settings(BaseModel):
    auto_evaluate_top_n: int = Field(10, ge=0, le=50)
    claude_concurrency: int = Field(2, ge=1, le=4)
    notifications: bool = True
    naukri_profile_bot: bool = Field(False, description="D6; off = reminder only")
    query_matrix: QueryMatrix
    prefilter: PrefilterRules
    schedules: Schedules
    targets: Targets
    followups: FollowupRules = FollowupRules()
    source_weights: dict[str, float] = {}


class SecretName(BaseModel):
    name: Literal["gmail_address", "gmail_app_password"]
    present: bool


class SecretPut(BaseModel):
    value: str = Field(min_length=1)


class ProfileOut(BaseModel):
    platform: str
    edit_url: str | None = None
    last_refreshed_at: datetime | None = None
    refresh_every_days: int | None = None
    refresh_due: bool
    checklist: dict[str, bool]


class ProfilePatch(BaseModel):
    checklist: dict[str, bool] | None = None
    refreshed_now: bool | None = None


class SetupStatus(BaseModel):
    cv_a: bool
    cv_b: bool
    gmail: bool
    claude_cli: bool
    careerops: bool
    playwright: bool
    complete: bool


class CheckResult(BaseModel):
    ok: bool
    detail: str


class Company(BaseModel):
    """One tracked company in data/careerops/portals.yml (career-ops format)."""

    name: str
    careers_url: str
    enabled: bool = True
    provider: str | None = Field(None, description="ATS provider career-ops scans via API; None = websearch")
    notes: str | None = None


class CompanyIn(BaseModel):
    name: str = Field(min_length=1)
    careers_url: str = Field(min_length=8)


class CompanyPatch(BaseModel):
    enabled: bool | None = None
    careers_url: str | None = None


class CvUpload(BaseModel):
    variant: ResumeVariant
    markdown: str = Field(min_length=50)


class Health(BaseModel):
    ok: bool
    version: str
    db: bool
    scheduler: bool
    services: list[ServiceHealth]
