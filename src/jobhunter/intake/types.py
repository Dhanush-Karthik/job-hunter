"""Intake -> pipeline hand-off (lead-owned contract).

Every fetcher (JobSpy boards, career-ops scan import, Gmail alerts) emits RawJob; the pipeline
(`jobhunter.pipeline.ingest`) normalizes, dedupes, prefilters, scores and stores them as Lead rows.
Fetchers do no filtering beyond what the site query already does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from jobhunter.models import Source


@dataclass
class RawJob:
    source: Source
    source_ref: str  # stable per source: site job id, url hash, message-id#card-index
    title: str
    company: str
    location: str | None = None  # as given by the site, e.g. "Chennai, Tamil Nadu, India", "TN, India"
    job_url: str | None = None  # posting page
    apply_url: str | None = None  # direct/company apply link when different from job_url
    description: str | None = None  # markdown or plain text
    posted_at: datetime | None = None  # UTC
    is_remote: bool | None = None
    salary_min: float | None = None  # in `currency` per `salary_interval`, not yet converted to LPA
    salary_max: float | None = None
    salary_interval: str | None = None  # yearly | monthly | weekly | daily | hourly
    currency: str | None = None  # INR, USD, ...
    salary_text: str | None = None  # free text like "10-15 LPA" when no numbers are given
    experience_text: str | None = None  # e.g. Naukri "2-5 Yrs"
    skills: list[str] = field(default_factory=list)
    job_level: str | None = None  # e.g. LinkedIn "Mid-Senior level"
    easy_apply: bool | None = None  # platform 1-click apply (Naukri, LinkedIn Easy Apply, ...)
    source_detail: str | None = None  # query that found it, alert sender, provider name
    is_inbound: bool = False  # recruiter reached out (Gmail inbound)
    raw: dict[str, Any] = field(default_factory=dict)  # original row, JSON-serializable


@dataclass
class IngestResult:
    fetched: int = 0
    new: int = 0
    updated: int = 0  # already known (source, source_ref): fields refreshed
    duplicates: int = 0  # new rows that joined an existing dedupe group
    dropped: int = 0  # new rows with prefilter_pass = False
    lead_ids: list[int] = field(default_factory=list)  # ids of new + updated leads

    def summary(self) -> str:
        return (f"{self.fetched} fetched, {self.new} new, {self.updated} updated, "
                f"{self.duplicates} duplicates, {self.dropped} dropped")
