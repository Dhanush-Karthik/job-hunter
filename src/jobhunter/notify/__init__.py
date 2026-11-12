"""macOS desktop notifications via osascript.

Respects settings.notifications and settings.followups.quiet_hours (inside quiet hours -> skipped, not queued).
De-duplicated by `key`: SettingRow "notify_sent" maps key -> ISO time; a key fires at most once (prune > 30 days).
JOBHUNTER_NOTIFY=0 disables delivery (tests, CI) and wins over JOBHUNTER_NOTIFY_LOG=<path>, which appends one JSON
line per delivered notification instead of calling osascript (tests). Never raises: failures are logged.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from jobhunter.models import Evaluation, Lead, SettingRow
from jobhunter.schemas import Settings

log = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("Asia/Kolkata")
SENT_KEY = "notify_sent"
KEEP = timedelta(days=30)
FRESH = timedelta(hours=48)
HOT_QUICK_SCORE = 0.7
HOT_EVAL_SCORE = 4.0
BATCH_ABOVE = 3


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def in_quiet_hours(settings: Settings, now: datetime) -> bool:
    """[start, end) in local hours; the window may wrap midnight (23, 7). start == end means never quiet."""
    start, end = settings.followups.quiet_hours
    hour = _aware(now).astimezone(LOCAL_TZ).hour
    if start == end:
        return False
    return start <= hour < end if start < end else hour >= start or hour < end


def _escape(text: str) -> str:
    return " ".join(text.split()).replace("\\", "\\\\").replace('"', '\\"')


def _osascript(title: str, body: str) -> bool:
    script = f'display notification "{_escape(body)}" with title "{_escape(title)}"'
    done = subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10, check=False)
    if done.returncode != 0:
        log.warning("osascript failed (%s): %s", done.returncode, (done.stderr or b"").decode(errors="replace")[:200])
        return False
    return True


def _deliver(key: str, title: str, body: str, now: datetime) -> bool:
    path = os.environ.get("JOBHUNTER_NOTIFY_LOG")
    if path:
        line = json.dumps({"key": key, "title": title, "body": body, "at": now.isoformat()})
        with Path(path).open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        return True
    return _osascript(title, body)


def _load_sent(session: Session, now: datetime) -> dict[str, str]:
    row = session.get(SettingRow, SENT_KEY)
    sent = dict(row.value) if row is not None and isinstance(row.value, dict) else {}
    kept = {}
    for key, at in sent.items():
        try:
            if now - _aware(datetime.fromisoformat(at)) <= KEEP:
                kept[key] = at
        except (TypeError, ValueError):
            continue
    return kept


def _mark(session: Session, now: datetime, keys: list[str]) -> None:
    sent = _load_sent(session, now)
    for key in keys:
        sent[key] = now.isoformat()
    row = session.get(SettingRow, SENT_KEY) or SettingRow(key=SENT_KEY)
    row.value = sent  # new dict: JSON columns don't track in-place edits
    session.add(row)
    session.commit()


def notify(
    session: Session, settings: Settings, *, key: str, title: str, body: str, now: datetime | None = None
) -> bool:
    """Deliver one notification. True if delivered now, False if disabled / quiet hours / already sent.
    `now` is only for callers that run on an injected clock."""
    try:
        if not settings.notifications or os.environ.get("JOBHUNTER_NOTIFY") == "0":
            return False
        now = _aware(now) if now else datetime.now(UTC)
        if in_quiet_hours(settings, now) or key in _load_sent(session, now):
            return False
        if not _deliver(key, title, body, now):
            return False
        _mark(session, now, [key])
        return True
    except Exception:
        log.exception("notification %r failed", key)
        session.rollback()
        return False


def _hot(lead: Lead, best_eval: float | None, now: datetime) -> bool:
    if lead.is_inbound:
        return True
    if not lead.prefilter_pass or now - _aware(lead.posted_at or lead.found_at) >= FRESH:
        return False
    return lead.quick_score >= HOT_QUICK_SCORE or (best_eval is not None and best_eval >= HOT_EVAL_SCORE)


def notify_new_leads(
    session: Session, settings: Settings, lead_ids: list[int], *, now: datetime | None = None
) -> int:
    """After an intake run: notify for each new lead that is inbound, or fresh (<48 h) with quick_score >= 0.7
    or an evaluation score >= 4. Batches more than 3 into one "N hot leads" notification. Returns the number of
    notifications delivered (a batch counts once)."""
    try:
        if not lead_ids or not settings.notifications or os.environ.get("JOBHUNTER_NOTIFY") == "0":
            return 0
        now = _aware(now) if now else datetime.now(UTC)
        leads = session.exec(select(Lead).where(Lead.id.in_(lead_ids)).order_by(Lead.id)).all()
        scores: dict[int, float] = {}
        for ev in session.exec(select(Evaluation).where(Evaluation.lead_id.in_(lead_ids)).order_by(Evaluation.id)):
            if ev.score is not None:
                scores[ev.lead_id] = ev.score  # ascending id: the latest score wins
        sent = _load_sent(session, now)
        hot = [lead for lead in leads if f"lead:{lead.id}" not in sent and _hot(lead, scores.get(lead.id), now)]
        if len(hot) <= BATCH_ABOVE:
            return sum(
                notify(session, settings, key=f"lead:{lead.id}", now=now,
                       title=f"Recruiter reached out: {lead.company}" if lead.is_inbound else f"New lead: {lead.company}",
                       body=" · ".join(x for x in (lead.title, lead.location) if x))
                for lead in hot)
        names = "; ".join(f"{lead.company}: {lead.title}" for lead in hot[:3])
        batch_key = f"leads:{hot[0].id}-{hot[-1].id}-{len(hot)}"
        if notify(session, settings, key=batch_key, title=f"{len(hot)} hot leads", body=f"{names}; …", now=now):
            _mark(session, now, [f"lead:{lead.id}" for lead in hot])
            return 1
        return 0
    except Exception:
        log.exception("lead notifications failed")
        session.rollback()
        return 0
