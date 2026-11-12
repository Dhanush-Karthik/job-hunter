"""macOS desktop notifications via osascript (Wave 3 contract, lead-owned signatures; builder implements).

Respects settings.notifications and settings.followups.quiet_hours (inside quiet hours -> skipped, not queued).
De-duplicated by `key`: SettingRow "notify_sent" maps key -> ISO time; a key fires at most once (prune > 30 days).
JOBHUNTER_NOTIFY=0 disables delivery (tests, CI); JOBHUNTER_NOTIFY_LOG=<path> appends one JSON line per
delivered notification instead of calling osascript (tests). Never raises: failures are logged.
"""

from __future__ import annotations

from sqlmodel import Session

from jobhunter.schemas import Settings


def notify(session: Session, settings: Settings, *, key: str, title: str, body: str) -> bool:
    """Deliver one notification. True if delivered now, False if disabled / quiet hours / already sent."""
    raise NotImplementedError


def notify_new_leads(session: Session, settings: Settings, lead_ids: list[int]) -> int:
    """After an intake run: notify for each new lead that is inbound, or fresh (<48 h) with quick_score >= 0.7
    or an evaluation score >= 4. Batches more than 3 into one "N hot leads" notification. Returns count sent."""
    raise NotImplementedError
