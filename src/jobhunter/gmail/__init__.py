"""Gmail intake (Wave 3 contract, lead-owned signatures; codex_gmail implements the bodies).

Read-only IMAP (imap.gmail.com:993, app password from jobhunter.secrets). Never sends, moves, deletes or flags
mail: select folders read-only (`readonly=True` / EXAMINE) and fetch with BODY.PEEK so nothing is marked seen.

One run (`run_intake`) does, for every message newer than the cursor:
  1. classify the message: alert (a job-alert sender, see ALERT_SENDERS) / inbound (a recruiter reaching out) /
     reply (ack, rejection, interview invite, assessment) / other (ignored, nothing stored),
  2. alert -> parse every job card into RawJob(source=Source.gmail_alert, source_detail=<sender key>,
     source_ref="<message-id>#<card index>") and hand them all to pipeline.ingest,
  3. inbound -> one RawJob(source=Source.gmail_inbound, is_inbound=True, source_ref=<message-id>) via
     pipeline.ingest, then a Proposal(type=inbound, lead_id=<new lead>) with evidence = subject + short snippet,
  4. reply -> match an Application (sender domain / company name / title against leads with an application;
     RapidFuzz) and create a Proposal(type=status_change, payload {"to_status", "rejected_at_stage"?,
     "message_id"}) with confidence; no confident match or no confident template -> Proposal(type=needs_eyes).
Never writes Application/Event rows directly; status changes happen only when the owner accepts a proposal.
Proposals are idempotent per message-id (payload["message_id"]); re-running over the same mail adds nothing.
Evidence never stores full bodies (subject + <= 300 char snippet).

Cursor: SettingRow key "gmail_cursor" = {"uidvalidity": int, "last_uid": int} for "[Gmail]/All Mail"
(fallback INBOX). First run reads settings.followups.gmail_lookback_days back. SourceHealth rows "gmail_alert"
and "gmail_inbound" record last run, counts and errors (auth failure -> last_error, no crash).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TextIO

from sqlmodel import Session

from jobhunter.schemas import ServiceHealth, Settings

# sender key -> From-address domains/patterns. Parsers live in gmail/alerts/<key>.py.
ALERT_SENDERS = ("linkedin", "naukri", "instahyre", "hirist", "cutshort", "foundit", "wellfound", "uplers", "indeed")


class GmailError(Exception):
    """Login or IMAP failure with an owner-readable message (no secrets in it)."""


@dataclass
class GmailResult:
    messages: int = 0  # messages examined
    alerts: int = 0  # alert emails parsed
    cards: int = 0  # job cards extracted
    ingest: str = ""  # pipeline IngestResult.summary() for the alert + inbound RawJobs
    inbound: int = 0  # inbound proposals created
    proposals: int = 0  # status_change proposals created
    needs_eyes: int = 0
    parse_failures: list[str] = field(default_factory=list)  # "<sender>: <subject>" for alerts with 0 cards

    def summary(self) -> str:
        return (f"{self.messages} emails, {self.cards} job cards from {self.alerts} alerts, {self.inbound} inbound, "
                f"{self.proposals} reply proposals, {self.needs_eyes} need eyes; {self.ingest}")


def check_login(address: str, app_password: str) -> str | None:
    """Log in and EXAMINE INBOX, then log out. None on success, otherwise an owner-readable reason."""
    from jobhunter.gmail.service import check_login as implementation

    return implementation(address, app_password)


def run_intake(
    session: Session,
    settings: Settings,
    *,
    log: TextIO | None = None,
    should_cancel: Callable[[], bool] = lambda: False,
) -> GmailResult:
    """One Gmail intake run (module docstring). Raises GmailError when secrets are missing or login fails."""
    from jobhunter.gmail.service import run_intake as implementation

    return implementation(session, settings, log=log, should_cancel=should_cancel)


def health(session: Session) -> ServiceHealth:
    """ServiceHealth(name="gmail"): ok when secrets are present and the last run succeeded; detail = last run time
    and counts, or the last error, or "Gmail app password not set"."""
    from jobhunter.gmail.service import health as implementation

    return implementation(session)
