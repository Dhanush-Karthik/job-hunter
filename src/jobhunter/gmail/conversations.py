"""Conversation identity for inbound deduplication and known application replies."""
import re
from datetime import UTC, datetime, timedelta
from email.utils import getaddresses

from sqlmodel import Session, select

from jobhunter.gmail.message import Message, decode_subject
from jobhunter.models import Application, Lead, Proposal, ProposalType, Source, utcnow


def normalized_subject(subject: str) -> str:
    subject = decode_subject(subject)
    while True:
        stripped = re.sub(r'^\s*(?:message replied|re|fwd?|aw)\s*:\s*', '', subject, flags=re.IGNORECASE)
        if stripped == subject:
            return ' '.join(subject.casefold().split())
        subject = stripped


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def inbound_payload(message: Message, company: str) -> dict:
    return {'message_id': message.message_id, 'conversation_subject': normalized_subject(message.subject),
            'sender_company': company.casefold().strip(),
            'received_at': (message.sent_at or utcnow()).isoformat(),
            'thread_ids': list(message.thread_ids)}


def duplicate_inbound(session: Session, message: Message, company: str) -> bool:
    subject = normalized_subject(message.subject)
    received = _utc(message.sent_at or utcnow())
    for proposal, lead in session.exec(select(Proposal, Lead).join(Lead, Proposal.lead_id == Lead.id).where(
        Proposal.type == ProposalType.inbound, Lead.source == Source.gmail_inbound
    )):
        payload = proposal.payload
        prior_ids = {payload.get('message_id'), *payload.get('thread_ids', [])}
        if message.message_id in prior_ids or set(message.thread_ids) & prior_ids:
            return True
        previous_subject = payload.get('conversation_subject') or normalized_subject(
            (proposal.evidence or '').split('\n', 1)[0])
        previous_company = payload.get('sender_company') or lead.company.casefold().strip()
        if subject != previous_subject or company.casefold().strip() != previous_company:
            continue
        try:
            prior_date = datetime.fromisoformat(payload['received_at']) if payload.get('received_at') else lead.found_at
        except (ValueError, TypeError):
            prior_date = lead.found_at
        if abs(received - _utc(prior_date)) <= timedelta(days=30):
            return True
    return False


def application_thread(session: Session, message: Message) -> bool:
    """Only persisted application correspondence or an exact known recruiter can anchor a thread."""
    if not message.thread_ids:
        return False
    references = set(message.thread_ids)
    for proposal in session.exec(select(Proposal)):
        if proposal.application_id is not None and references & {
            proposal.payload.get('message_id'), *proposal.payload.get('thread_ids', [])
        }:
            return True
    if normalized_subject(message.subject) == message.subject.casefold().strip():
        return False
    for application in session.exec(select(Application)):
        recruiters = {address.casefold() for _, address in getaddresses([application.recruiter or ''])}
        if message.sender and message.sender.casefold() in recruiters:
            lead = session.get(Lead, application.lead_id)
            if lead and lead.title.casefold() in message.subject.casefold():
                return True
    return False
