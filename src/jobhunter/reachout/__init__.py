"""Direct reach-out emails to a job's HR mailbox (owner-triggered, never automatic).

From the job page: find the HR address (`finder`), auto-fill a short email from the Settings templates that lists the
job ID, attach the tailored CV or resume PDF, then send it over Gmail SMTP (or save it to Gmail Drafts). Nothing here
runs on a schedule: every send is one explicit owner click, behind a confirm flag, a per-address cool-down and a daily cap.
"""

from __future__ import annotations

import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Any

import yaml
from imap_tools import MailBox, MailMessageFlags

from jobhunter import paths
from jobhunter.models import Lead
from jobhunter.schemas import DEFAULT_BODY, DEFAULT_SUBJECT_MANY, DEFAULT_SUBJECT_ONE, ReachoutSettings

MAX_JOBS = 8  # hard upper bound on jobs listed in one email (the Settings value can only be lower)
MAX_RESUME_BYTES = 5 * 1024 * 1024
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
IMAP_HOST = "imap.gmail.com"
DRAFTS_FOLDER = "[Gmail]/Drafts"

EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$")

# Test seams: tests replace these, nothing else touches the network.
smtp_factory = smtplib.SMTP_SSL
mailbox_factory = MailBox


class ReachoutError(Exception):
    """A user-presentable failure (bad credentials, Gmail refused, no resume)."""


def resume_path() -> Path:
    return paths.CV_DIR / "resume.pdf"


def valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(value.strip()))


def job_id(lead: Lead) -> str:
    """The id a recruiter can look up: the job board's own number, else our lead id."""
    ref = lead.source_ref or ""
    head, sep, tail = ref.partition("-")
    if sep and tail and len(head) <= 3 and tail.isalnum():  # li-4493202067, gd-1010..., in-03a36ef7...
        return tail
    if ref and len(ref) <= 40 and re.fullmatch(r"[\w.\-]+", ref):
        return ref
    return f"JH-{lead.id}"


def _profile() -> dict[str, Any]:
    path = paths.CAREEROPS_DATA / "config" / "profile.yml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


@dataclass
class Candidate:
    name: str
    phone: str | None
    linkedin: str | None
    github: str | None
    headline: str | None
    location: str | None


def candidate(cfg: ReachoutSettings, fallback_email: str | None = None) -> Candidate:
    """Who is writing: Settings > CVs & email > "Who signs the email" first, then data/careerops/config/profile.yml."""
    data = _profile()
    c = data.get("candidate") if isinstance(data.get("candidate"), dict) else {}
    narrative = data.get("narrative") if isinstance(data.get("narrative"), dict) else {}
    me = cfg.me
    name = me.name.strip() or str(c.get("full_name") or "").strip() or (fallback_email or "").split("@")[0] or "Candidate"
    return Candidate(
        name=name, phone=me.phone.strip() or c.get("phone") or None, linkedin=me.linkedin.strip() or c.get("linkedin") or None,
        github=me.github.strip() or c.get("github") or None,
        headline=me.headline.strip() or narrative.get("headline") or None, location=c.get("location") or None,
    )


class _Fields(dict):
    """format_map source that leaves unknown {placeholders} as written instead of failing."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def fill(template: str, fallback: str, **fields: object) -> str:
    try:
        return template.format_map(_Fields(fields))
    except (ValueError, IndexError, KeyError, AttributeError):  # a stray "{" in a hand-edited template
        return fallback.format_map(_Fields(fields))


def _greeting(to_name: str | None) -> str:
    first = (to_name or "").strip().split(" ")[0]
    return f"Hi {first}," if first else "Hello,"


def _signature(me: Candidate) -> str:
    return "\n".join([me.name, *(x for x in (me.phone, me.linkedin, me.github) if x)])


def compose(company: str, to_name: str | None, jobs: list[tuple[Lead, str]], me: Candidate,
            cfg: ReachoutSettings | None = None) -> tuple[str, str]:
    """Subject and plain-text body from the Settings templates. `jobs` is (lead, job_id) pairs, best first.

    Deterministic: no model call. Placeholders: {greeting} {opening} {jobs} {role} {company} {title} {job_id}
    {count} {name} {phone} {linkedin} {github} {signature}.
    """
    cfg = cfg or ReachoutSettings()
    jobs = jobs[: max(1, min(cfg.max_jobs, MAX_JOBS))]
    first, first_id = jobs[0]
    if len(jobs) == 1:
        opening = f"I am writing to apply for the {first.title} role at {company} (Job ID {first_id})."
    else:
        opening = f"I would like to be considered for the following roles at {company}:"
    listing = []
    for lead, jid in jobs:
        where = f", {lead.location}" if lead.location else ""
        url = lead.apply_url or lead.canonical_url
        listing.append(f"  - {lead.title}{where} (Job ID {jid})" + (f"\n    {url}" if url else ""))
    fields = {
        "greeting": _greeting(to_name), "opening": opening, "jobs": "\n".join(listing), "company": company, "title": first.title,
        "job_id": first_id, "count": len(jobs), "name": me.name, "phone": me.phone or "", "linkedin": me.linkedin or "",
        "github": me.github or "", "signature": _signature(me), "role": (me.headline or "backend engineer").split("|")[0].strip(),
        "location": first.location or "", "url": first.apply_url or first.canonical_url or "",
    }
    subject = fill(cfg.subject_one if len(jobs) == 1 else cfg.subject_many,
                   DEFAULT_SUBJECT_ONE if len(jobs) == 1 else DEFAULT_SUBJECT_MANY, **fields)
    body = fill(cfg.body, DEFAULT_BODY, **fields)
    return " ".join(subject.split()), re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"


def build_message(sender: str, to_email: str, to_name: str | None, subject: str, body: str,
                  attachment: tuple[str, bytes] | None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = formataddr((to_name.replace("\r", " ").replace("\n", " "), to_email)) if to_name else to_email
    msg["Subject"] = subject.replace("\r", " ").replace("\n", " ")
    msg.set_content(body)
    if attachment is not None:
        name, data = attachment
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=name)
    return msg


def _clean(error: Exception, password: str) -> str:
    return str(error).replace(password, "***") if password else str(error)


def send(address: str, password: str, msg: EmailMessage) -> None:
    try:
        with smtp_factory(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context(), timeout=30) as smtp:
            smtp.login(address, password)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise ReachoutError("Gmail login failed. Check the Gmail address and app password in Settings.") from None
    except smtplib.SMTPRecipientsRefused:
        raise ReachoutError("Gmail refused the recipient address.") from None
    except (smtplib.SMTPException, OSError) as e:
        raise ReachoutError(f"Gmail could not send the email: {_clean(e, password)}") from None


def save_draft(address: str, password: str, msg: EmailMessage) -> None:
    """Put the message in Gmail's Drafts folder; the owner opens Gmail and presses Send."""
    try:
        box = mailbox_factory(IMAP_HOST, port=993)
        box.login(address, password, initial_folder=None)
        try:
            box.append(msg.as_bytes(), DRAFTS_FOLDER, flag_set=[MailMessageFlags.DRAFT])
        finally:
            box.logout()
    except Exception as e:  # noqa: BLE001 - imaplib/imap_tools raise several unrelated types
        raise ReachoutError(f"Gmail could not save the draft: {_clean(e, password)}") from None
