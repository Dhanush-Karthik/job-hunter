"""Gmail intake orchestration; only leads, proposals, health and cursor are written."""
from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import TextIO

from keyring.errors import KeyringError
from sqlmodel import Session, select

from jobhunter import secrets
from jobhunter.gmail import GmailError, GmailResult, imap
from jobhunter.gmail.alerts import parse as parse_alert
from jobhunter.gmail.classify import classify, sender_key
from jobhunter.gmail.inbound import parse as parse_inbound
from jobhunter.gmail.match import match_application
from jobhunter.gmail.replies import template, to_status
from jobhunter.intake.types import IngestResult
from jobhunter.models import Lead, Proposal, ProposalType, SettingRow, SourceHealth, utcnow
from jobhunter.pipeline.store import ingest
from jobhunter.schemas import ServiceHealth, Settings


def _credentials() -> tuple[str, str]:
    try:
        address, password = secrets.get('gmail_address'), secrets.get('gmail_app_password')
    except (KeyringError, OSError, RuntimeError):
        raise GmailError('Gmail credentials could not be read from the keychain.') from None
    if not address or not password:
        raise GmailError('Gmail app password not set')
    return address, password


def check_login(address: str, app_password: str) -> str | None:
    if not address or not app_password:
        return 'Gmail address and app password are required.'
    try:
        with imap.connect(address, app_password, inbox=True):
            pass
    except GmailError as error:
        return str(error)
    return None


def _record_health(session: Session, result: GmailResult, error: str | None = None) -> None:
    now = utcnow()
    for source, count in [('gmail_alert', result.cards), ('gmail_inbound', result.inbound)]:
        row = session.get(SourceHealth, source) or SourceHealth(source=source)
        row.last_run_at, row.last_error, row.last_count = now, error, count
        row.consecutive_failures = row.consecutive_failures + 1 if error else 0
        if not error:
            row.last_ok_at = now
        session.add(row)
    session.commit()


def run_intake(session: Session, settings: Settings, *, log: TextIO | None = None,
               should_cancel: Callable[[], bool] = lambda: False) -> GmailResult:
    result = GmailResult()
    total = IngestResult()
    existing = {p.payload.get('message_id') for p in session.exec(select(Proposal))}
    try:
        address, password = _credentials()
        with imap.connect(address, password) as (mailbox, folder):
            validity = int(mailbox.folder.status(folder, ['UIDVALIDITY'])['UIDVALIDITY'])
            cursor = session.get(SettingRow, 'gmail_cursor')
            value = cursor.value if cursor and isinstance(cursor.value, dict) else {}
            last_uid = int(value.get('last_uid', 0)) if value.get('uidvalidity') == validity else 0
            since = (utcnow() - timedelta(days=settings.followups.gmail_lookback_days)).date() if not last_uid else None
            for message in imap.messages(mailbox, last_uid, since):
                if should_cancel():
                    break
                result.messages += 1
                kind = classify(message)
                raw_jobs = []
                if kind == 'alert':
                    key = sender_key(message)
                    result.alerts += 1
                    raw_jobs = parse_alert(message, key)
                    result.cards += len(raw_jobs)
                    if not raw_jobs:
                        result.parse_failures.append(f'{key}: {message.subject}')
                elif kind == 'inbound' and message.message_id not in existing:
                    raw_jobs = [parse_inbound(message)]
                if raw_jobs:
                    ingested = ingest(session, raw_jobs, settings)
                    for field in ('fetched', 'new', 'updated', 'duplicates', 'dropped'):
                        setattr(total, field, getattr(total, field) + getattr(ingested, field))
                    if kind == 'inbound':
                        lead = session.exec(select(Lead).where(Lead.source == raw_jobs[0].source,
                                                              Lead.source_ref == message.message_id)).one()
                        session.add(Proposal(type=ProposalType.inbound, lead_id=lead.id,
                                             payload={'message_id': message.message_id},
                                             evidence=message.evidence, confidence=0.9))
                        result.inbound += 1
                        existing.add(message.message_id)
                elif kind == 'reply' and message.message_id not in existing:
                    reply = template(message)
                    if reply != 'ack':
                        application, confidence = match_application(session, message)
                        status = to_status(reply)
                        payload = {'message_id': message.message_id}
                        if application and status:
                            payload['to_status'] = status.value
                            if reply == 'rejection':
                                payload['rejected_at_stage'] = application.status.value
                            proposal_type = ProposalType.status_change
                            result.proposals += 1
                        else:
                            proposal_type = ProposalType.needs_eyes
                            result.needs_eyes += 1
                        session.add(Proposal(type=proposal_type,
                                             application_id=application.id if application else None,
                                             lead_id=application.lead_id if application else None,
                                             payload=payload, evidence=message.evidence,
                                             confidence=confidence if status else 0.0))
                        existing.add(message.message_id)
                # Persist after processing so a cancellation or transient failure resumes safely.
                last_uid = max(last_uid, message.uid)
                cursor = cursor or SettingRow(key='gmail_cursor', value={})
                cursor.value = {'uidvalidity': validity, 'last_uid': last_uid}
                session.add(cursor)
                session.commit()
            # Remember a UIDVALIDITY reset even for an empty mailbox.
            if not should_cancel():
                cursor = cursor or SettingRow(key='gmail_cursor', value={})
                cursor.value = {'uidvalidity': validity, 'last_uid': last_uid}
                session.add(cursor)
                session.commit()
    except GmailError as error:
        session.rollback()
        _record_health(session, result, str(error))
        if log:
            log.write(str(error) + '\n')
        raise
    result.ingest = total.summary()
    parse_error = 'Some Gmail job alerts could not be parsed.' if result.parse_failures else None
    _record_health(session, result, parse_error)
    if log:
        log.write(result.summary() + '\n')
    return result


def health(session: Session) -> ServiceHealth:
    try:
        _credentials()
    except GmailError as error:
        return ServiceHealth(name='gmail', ok=False, detail=str(error))
    rows = [session.get(SourceHealth, key) for key in ('gmail_alert', 'gmail_inbound')]
    error = next((row.last_error for row in rows if row and row.last_error), None)
    if error:
        return ServiceHealth(name='gmail', ok=False, detail=error)
    if any(row is None or row.last_ok_at is None for row in rows):
        return ServiceHealth(name='gmail', ok=False, detail='Gmail intake has not run yet')
    last = max(row.last_run_at for row in rows if row and row.last_run_at)
    count = sum(row.last_count for row in rows if row)
    return ServiceHealth(name='gmail', ok=True, detail=f'Last run {last.isoformat()}; {count} leads')
