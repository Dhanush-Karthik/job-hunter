"""Offline Gmail contract tests, using sanitized and explicitly synthetic MIME fixtures."""
from __future__ import annotations

import io
import re
from datetime import timedelta
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlmodel import select

from jobhunter import paths, secrets
from jobhunter.gmail import ALERT_SENDERS, GmailError, check_login, health, imap, run_intake
from jobhunter.gmail.alerts import parse
from jobhunter.gmail.classify import classify, sender_key
from jobhunter.gmail.conversations import duplicate_inbound, inbound_payload, normalized_subject
from jobhunter.gmail.inbound import parse as parse_inbound
from jobhunter.gmail.match import match_application
from jobhunter.gmail.message import Message, clean_url
from jobhunter.gmail.replies import template
from jobhunter.models import (
    Application,
    AppStatus,
    Event,
    Lead,
    Proposal,
    ProposalType,
    SettingRow,
    Source,
    SourceHealth,
)
from jobhunter.settings import load_defaults

FIXTURES = Path(__file__).parent / 'fixtures' / 'emails'
ALERTS = sorted(p for key in ALERT_SENDERS for p in (FIXTURES / key).glob('*.eml'))
MAILS = sorted(FIXTURES.rglob('*.eml'))


def message(path: Path, uid: int = 0) -> Message:
    return Message.from_bytes(path.read_bytes(), uid)


def fixture(folder: str, pattern: str = '*.eml') -> Path:
    return next(iter(sorted((FIXTURES / folder).glob(pattern))))


class FakeFolder:
    def __init__(self, mailbox):
        self.mailbox = mailbox

    def set(self, name, *, readonly=False):
        assert readonly is True, 'Writable folder selection forbidden'
        self.mailbox.selections.append(name)
        if name == '[Gmail]/All Mail' and self.mailbox.fallback:
            raise RuntimeError('Missing All Mail folder')

    def status(self, name, options):
        assert options == ['UIDVALIDITY']
        return {'UIDVALIDITY': self.mailbox.validity}


class FakeMailbox:
    """Only the permitted read calls exist; flag/send/delete/move would fail."""
    def __init__(self, files=(), *, validity=42, fail=False, fallback=False):
        self.files = list(files)
        self.validity = validity
        self.fail = fail
        self.fallback = fallback
        self.folder = FakeFolder(self)
        self.selections = []
        self.searches = []
        self.logouts = 0

    def login(self, address, password, *, initial_folder):
        assert initial_folder is None, 'Login must not select a writable INBOX'
        if self.fail:
            raise RuntimeError(f'AUTHENTICATIONFAILED {password} {address}')
        return self

    def fetch(self, criteria, *, mark_seen, reverse):
        assert mark_seen is False, 'Fetch must use BODY.PEEK'
        assert reverse is False
        self.searches.append(str(criteria))
        # Deliberately return everything: intake must guard the IMAP UID n:* edge case itself.
        for uid, path in enumerate(self.files, 1):
            yield SimpleNamespace(uid=str(uid), obj=BytesParser(policy=policy.compat32).parsebytes(path.read_bytes()))

    def logout(self):
        self.logouts += 1


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    mailbox = FakeMailbox()
    monkeypatch.setattr(imap, 'mailbox_factory', lambda host, port: mailbox)
    monkeypatch.setattr(secrets, 'get', lambda key: 'owner@example.com' if key == 'gmail_address' else 'secret-value')
    monkeypatch.setattr('jobhunter.pipeline.store.read_default_cv', lambda: '')
    return mailbox


@pytest.fixture
def settings():
    return load_defaults(paths.CONFIG_EXAMPLE)


def install(monkeypatch, mailbox):
    def factory(host, port):
        assert (host, port) == ('imap.gmail.com', 993)
        return mailbox
    monkeypatch.setattr(imap, 'mailbox_factory', factory)


@pytest.mark.parametrize('path', ALERTS, ids=lambda p: f'{p.parent.name}/{p.name}')
def test_every_alert_has_complete_cards(path):
    mail = message(path)
    assert classify(mail) == 'alert'
    assert sender_key(mail) == path.parent.name
    cards = parse(mail, path.parent.name)
    assert cards
    for index, card in enumerate(cards):
        assert card.title and card.company and card.job_url
        assert card.source == Source.gmail_alert
        assert card.source_detail == path.parent.name
        assert card.source_ref == f'{mail.message_id}#{index}'
    assert len({card.source_ref for card in cards}) == len(cards)


@pytest.mark.parametrize('sender,count', [('linkedin', [6, 6, 8]), ('cutshort', [10]),
                                          ('instahyre', [1]), ('wellfound', [3])])
def test_real_alert_card_counts(sender, count):
    files = sorted(p for p in (FIXTURES / sender).glob('*.eml') if 'synthetic' not in p.name)
    assert [len(parse(message(path), sender)) for path in files] == count


@pytest.mark.parametrize('sender', ['naukri', 'hirist', 'foundit', 'uplers'])
def test_synthetic_platform_fields(sender):
    files = list((FIXTURES / sender).glob('*.eml'))
    assert len(files) >= 2
    for path in files:
        card = parse(message(path), sender)[0]
        assert card.company in {'Acme Systems', 'Example Labs'}
        assert card.title in {'Java Backend Developer', 'Software Engineer II'}
        assert card.location == 'Chennai'
        assert card.experience_text == '2-4 years'
        assert card.salary_text == '₹12-18 LPA'
        assert card.posted_at.date().isoformat() == '2026-11-11'
        assert card.easy_apply is True
        assert card.apply_url.startswith('https://careers.example.com/apply/')


def expected_template(path):
    headers = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    if headers.get('X-Jobhunter-Expected-Template'):
        return headers['X-Jobhunter-Expected-Template']
    if path.parent.name in {'ack', 'rejection'}:
        return None if 'amazon-rejection' in path.name else path.parent.name
    if path.parent.name == 'interview':
        return 'ack' if 'completed' in path.name else 'assessment' if 'assessment-invite' in path.name else 'interview'
    return None


def test_reply_template_precision_and_recall():
    predicted = correct = positives = recalled = 0
    counts = dict.fromkeys(['ack', 'rejection', 'interview', 'assessment'], 0)
    for path in MAILS:
        mail = message(path)
        expected = expected_template(path)
        actual = template(mail) if classify(mail) == 'reply' else None
        if actual is not None:
            predicted += 1
            correct += actual == expected
        if expected:
            counts[expected] += 1
            positives += 1
            recalled += actual == expected
    assert all(count >= 5 for count in counts.values()), counts
    assert predicted > 0 and correct / predicted >= 0.98
    assert recalled / positives >= 0.98


@pytest.mark.parametrize('path', sorted((FIXTURES / 'other').glob('*.eml')), ids=lambda p: p.name)
def test_other_mails_produce_nothing(path, session, settings, monkeypatch):
    mail = message(path)
    assert classify(mail) == 'other'
    assert template(mail) is None
    install(monkeypatch, FakeMailbox([path]))
    result = run_intake(session, settings)
    assert (result.cards, result.inbound, result.proposals, result.needs_eyes) == (0, 0, 0, 0)
    assert list(session.exec(select(Lead))) == []
    assert list(session.exec(select(Proposal))) == []


@pytest.mark.parametrize('path', sorted((FIXTURES / 'inbound').glob('*.eml')), ids=lambda p: p.name)
def test_real_inbound_fields(path):
    mail = message(path)
    assert classify(mail) == 'inbound'
    raw = parse_inbound(mail)
    assert raw.is_inbound and raw.source == Source.gmail_inbound
    assert raw.source_ref == mail.message_id
    assert raw.company in {'Yubi', 'Liquidnitro Games'}
    assert raw.title
    if 'yubi' in path.name:
        assert raw.title == 'Software Engineer' and raw.location == 'Chennai'


def test_intake_end_to_end_and_replay(session, settings, monkeypatch):
    lead = Lead(source=Source.manual, source_ref='existing', company='Acme', title='Java Developer')
    session.add(lead)
    session.commit()
    app = Application(lead_id=lead.id, status=AppStatus.applied)
    session.add(app)
    session.commit()
    event = Event(application_id=app.id, to_status=AppStatus.applied)
    session.add(event)
    session.commit()
    session.refresh(app)
    session.refresh(event)
    app_before, event_before = app.model_dump(), event.model_dump()
    files = [fixture('linkedin'), fixture('inbound', '*yubi*'), fixture('rejection', 'synthetic-1*'),
             fixture('interview', '*rocketlane*'), fixture('ack', 'synthetic-1*')]
    box = FakeMailbox(files)
    install(monkeypatch, box)
    result = run_intake(session, settings)
    assert result.messages == 5 and result.cards == 6
    assert result.inbound == 1 and result.proposals == 1 and result.needs_eyes == 1
    proposals = list(session.exec(select(Proposal)))
    assert len(proposals) == 3
    inbound = next(p for p in proposals if p.type == ProposalType.inbound)
    assert session.get(Lead, inbound.lead_id).is_inbound
    rejection = next(p for p in proposals if p.type == ProposalType.status_change)
    assert rejection.application_id == app.id
    assert rejection.payload['to_status'] == 'Rejected'
    assert rejection.payload['rejected_at_stage'] == 'Applied'
    for proposal in proposals:
        assert proposal.payload['message_id']
        assert len(proposal.evidence.split('\n', 1)[1]) <= 300
    cursor = session.get(SettingRow, 'gmail_cursor')
    assert cursor.value == {'uidvalidity': 42, 'last_uid': 5}
    lead_ids = [row.id for row in session.exec(select(Lead))]
    second = run_intake(session, settings)
    assert second.messages == 0
    assert [row.id for row in session.exec(select(Lead))] == lead_ids
    assert len(list(session.exec(select(Proposal)))) == 3
    # A UIDVALIDITY change requires replay; proposal identities still prevent duplicates.
    box.validity = 43
    third = run_intake(session, settings)
    assert third.messages == 5 and third.inbound == third.proposals == third.needs_eyes == 0
    assert len(list(session.exec(select(Proposal)))) == 3
    session.refresh(app)
    session.refresh(event)
    assert app.model_dump() == app_before
    assert event.model_dump() == event_before
    assert len(list(session.exec(select(Application)))) == len(list(session.exec(select(Event)))) == 1
    assert health(session).ok
    assert session.get(SourceHealth, 'gmail_alert').last_count == 6
    assert box.logouts == 3
    assert 'SINCE' in box.searches[0] and 'UID 6:*' in box.searches[1]


@pytest.mark.parametrize('kind', ['interview', 'assessment'])
def test_screening_proposals_never_update_application(kind, session, settings, monkeypatch):
    lead = Lead(source=Source.manual, source_ref='screening', company='Acme', title='Java Developer')
    session.add(lead)
    session.commit()
    app = Application(lead_id=lead.id, status=AppStatus.applied)
    session.add(app)
    session.commit()
    install(monkeypatch, FakeMailbox([fixture(kind, 'synthetic-1*')]))
    result = run_intake(session, settings)
    assert result.proposals == 1
    proposal = session.exec(select(Proposal)).one()
    assert proposal.payload['to_status'] == 'Screening'
    assert 'rejected_at_stage' not in proposal.payload
    session.refresh(app)
    assert app.status == AppStatus.applied
    assert not list(session.exec(select(Event)))


def test_unknown_reply_needs_eyes(session, settings, monkeypatch):
    install(monkeypatch, FakeMailbox([fixture('rejection', '*amazon-rejection*')]))
    result = run_intake(session, settings)
    assert result.needs_eyes == 1
    proposal = session.exec(select(Proposal)).one()
    assert proposal.type == ProposalType.needs_eyes and 'to_status' not in proposal.payload


def test_login_failure_health_and_secret_redaction(session, settings, monkeypatch):
    box = FakeMailbox(fail=True)
    install(monkeypatch, box)
    log = io.StringIO()
    with pytest.raises(GmailError) as raised:
        run_intake(session, settings, log=log)
    for source in ('gmail_alert', 'gmail_inbound'):
        row = session.get(SourceHealth, source)
        assert row.last_error and row.consecutive_failures == 1 and row.last_ok_at is None
        assert 'secret-value' not in row.last_error and 'owner@example.com' not in row.last_error
    assert 'secret-value' not in str(raised.value) + log.getvalue()
    reason = check_login('owner@example.com', 'sensitive-password')
    assert isinstance(reason, str) and 'sensitive-password' not in reason
    assert health(session).ok is False
    assert session.get(SettingRow, 'gmail_cursor') is None


def test_missing_secrets(session, settings, monkeypatch):
    monkeypatch.setattr(secrets, 'get', lambda key: None)
    with pytest.raises(GmailError, match='not set'):
        run_intake(session, settings)
    assert health(session).detail == 'Gmail app password not set'
    assert session.get(SourceHealth, 'gmail_alert').last_error


def test_inbox_fallback_and_login_check(session, settings, monkeypatch):
    box = FakeMailbox([fixture('linkedin')], fallback=True)
    install(monkeypatch, box)
    assert run_intake(session, settings).cards == 6
    assert box.selections == ['[Gmail]/All Mail', 'INBOX']
    assert check_login('owner@example.com', 'secret') is None
    assert box.selections[-1] == 'INBOX'
    assert check_login('', '')


def test_cancel_does_not_advance_cursor(session, settings, monkeypatch):
    box = FakeMailbox([fixture('linkedin')])
    install(monkeypatch, box)
    assert run_intake(session, settings, should_cancel=lambda: True).messages == 0
    assert session.get(SettingRow, 'gmail_cursor') is None
    assert not list(session.exec(select(Lead)))


def test_domain_and_ambiguous_application_matching(session):
    for index in range(2):
        lead = Lead(source=Source.manual, source_ref=str(index), company='Acme Systems',
                    title='Java Developer' if index == 0 else 'Platform Engineer')
        session.add(lead)
        session.flush()
        session.add(Application(lead_id=lead.id, status=AppStatus.applied))
    session.commit()
    ambiguous = Message('a', 'Application update', 'recruiter@acmesystems.example', 'Acme Systems is reviewing it.')
    assert match_application(session, ambiguous)[0] is None
    specific = Message('b', 'Interview invitation', 'recruiter@acmesystems.example',
                       'Java Developer interview at Acme Systems is scheduled.')
    matched, confidence = match_application(session, specific)
    assert matched and session.get(Lead, matched.lead_id).title == 'Java Developer'
    assert confidence >= 0.85
    unknown = Message('c', 'Application update', 'jobs@unknown.example', 'A Java Developer role at Unknown Corp.')
    assert match_application(session, unknown)[0] is None


def test_mime_html_only_and_message_id_fallback():
    raw = b'From: jobs@example.com\nSubject: HTML\nContent-Type: text/html; charset=utf-8\n\n<html><style>SECRET CSS</style><p>Hello world</p></html>'
    one, two = Message.from_bytes(raw), Message.from_bytes(raw)
    assert 'Hello world' in one.text and 'SECRET CSS' not in one.text
    assert one.message_id == two.message_id and one.message_id.startswith('sha256:')
    assert clean_url('https://click.instahyre.com/CL0/https:%2F%2Fwww.instahyre.com%2Fjob-123-developer%3Ftoken=secret/1/token') == 'https://www.instahyre.com/job-123-developer'


def test_sanitized_fixture_privacy():
    phone = re.compile(r'(?<![\w/])(?:\+?91[ -]?)?[6-9]\d{4}[ -]?\d{5}(?!\w)|\b1800[ -]\d{3}[ -]\d{4}\b')
    for path in MAILS:
        raw = path.read_text()
        assert not re.search(r'dhanush|karthik|@gmail\.com', raw, re.IGNORECASE), path
        assert not phone.search(raw), path
        assert not re.search(r'url_auth_token|emailunsub\?', raw, re.IGNORECASE), path
        assert not re.search(r'https://links\.wellfound\.com/s/[cu]/(?!sanitized-link-)[^\s]+', raw), path


def test_invitation_precedes_ack_boilerplate():
    interview = Message('interview', 'Next steps at Acme', 'jobs@acme.example',
                        'Thank you for applying. We invite you to an interview for Java Developer at Acme.')
    assessment = Message('assessment', 'Next steps at Acme', 'jobs@acme.example',
                         'Thank you for your application. Please complete our online assessment for Java Developer.')
    completed = Message('completed', 'Your assessment', 'jobs@acme.example',
                        'Thanks for completing the assessment. We will review your results.')
    assert template(interview) == 'interview'
    assert template(assessment) == 'assessment'
    assert template(completed) == 'ack'


def test_company_common_word_is_not_a_match(session):
    lead = Lead(source=Source.manual, source_ref='target', company='Target', title='Software Engineer')
    session.add(lead)
    session.flush()
    session.add(Application(lead_id=lead.id, status=AppStatus.applied))
    session.commit()
    mail = Message('rejection', 'Your application at Appian', 'jobs@greenhouse.example',
                   'Other candidates are a closer match to our target profile for Software Engineer at Appian.')
    assert match_application(session, mail)[0] is None


def test_same_message_id_at_multiple_uids_is_idempotent(session, settings, monkeypatch):
    inbound = fixture('inbound', '*yubi*')
    rejection = fixture('rejection', 'synthetic-1*')
    install(monkeypatch, FakeMailbox([inbound, inbound, rejection, rejection]))
    result = run_intake(session, settings)
    assert result.messages == 4 and result.inbound == 1 and result.needs_eyes == 1
    assert len(list(session.exec(select(Lead)))) == 1
    assert len(list(session.exec(select(Proposal)))) == 2


def test_fetch_failure_preserves_cursor_and_recovers(session, settings, monkeypatch):
    class InterruptedMailbox(FakeMailbox):
        def fetch(self, *args, **kwargs):
            yield from super().fetch(*args, **kwargs)
            raise OSError('Disconnected: secret-value')

    box = InterruptedMailbox([fixture('inbound', '*yubi*')])
    install(monkeypatch, box)
    with pytest.raises(GmailError) as error:
        run_intake(session, settings)
    assert 'secret-value' not in str(error.value)
    assert session.get(SettingRow, 'gmail_cursor').value['last_uid'] == 1
    assert len(list(session.exec(select(Proposal)))) == 1
    assert session.get(SourceHealth, 'gmail_inbound').consecutive_failures == 1
    install(monkeypatch, FakeMailbox(box.files))
    assert run_intake(session, settings).messages == 0
    assert health(session).ok
    assert session.get(SourceHealth, 'gmail_inbound').consecutive_failures == 0


def test_empty_mailbox_validity_reset_and_health(session, settings, monkeypatch):
    session.add(SettingRow(key='gmail_cursor', value={'uidvalidity': 41, 'last_uid': 999}))
    session.commit()
    install(monkeypatch, FakeMailbox(validity=42))
    run_intake(session, settings)
    assert session.get(SettingRow, 'gmail_cursor').value == {'uidvalidity': 42, 'last_uid': 0}
    assert health(session).ok


def test_unparsed_alert_records_health(session, settings, monkeypatch, tmp_path):
    path = tmp_path / 'unknown-format.eml'
    path.write_text('From: jobs@linkedin.com\nSubject: Your job alert\nMessage-ID: <bad-format@example.com>\n\nNew jobs match your preferences. Layout unknown.')
    install(monkeypatch, FakeMailbox([path]))
    result = run_intake(session, settings)
    assert result.parse_failures == ['linkedin: Your job alert']
    assert not health(session).ok
    assert session.get(SourceHealth, 'gmail_alert').last_error


REGRESSIONS = {
    'inbound-2': ('indeed', 'alert', 21),
    'inbound-6': ('indeed', 'alert', 27),
    'inbound-10': ('other', 'other', 0),
    'needs_eyes-1': ('other', 'other', 0),
    'needs_eyes-4': ('other', 'other', 0),
    'inbound-5': ('inbound', 'inbound', 0),
    'inbound-7': ('inbound', 'inbound', 0),
}


@pytest.mark.parametrize('name', REGRESSIONS)
def test_real_misclassification_regressions(name, session, settings, monkeypatch):
    folder, expected, count = REGRESSIONS[name]
    path = FIXTURES / folder / f'regression-{name}.eml'
    mail = message(path)
    assert classify(mail) == expected
    install(monkeypatch, FakeMailbox([path]))
    result = run_intake(session, settings)
    assert result.cards == count
    assert not result.parse_failures
    assert result.proposals == result.needs_eyes == 0
    assert result.inbound == (expected == 'inbound')
    proposals = list(session.exec(select(Proposal)))
    assert len(proposals) == (expected == 'inbound')
    if expected == 'alert':
        assert sender_key(mail) == 'indeed'
        leads = list(session.exec(select(Lead)))
        assert len(leads) == count
        assert all(lead.source == Source.gmail_alert and lead.source_detail == 'indeed' for lead in leads)


def test_inbound_precision_on_all_fixtures():
    predicted = correct = positives = recalled = 0
    for path in MAILS:
        expected = path.parent.name == 'inbound'
        actual = classify(message(path)) == 'inbound'
        predicted += actual
        correct += actual and expected
        positives += expected
        recalled += actual and expected
    assert positives >= 5 and predicted > 0
    assert correct / predicted >= 0.98
    assert recalled / positives >= 0.98


def test_regression_mailbox_creates_one_inbound_conversation(session, settings, monkeypatch):
    files = [FIXTURES / folder / f'regression-{name}.eml' for name, (folder, _, _) in REGRESSIONS.items()]
    install(monkeypatch, FakeMailbox(files))
    result = run_intake(session, settings)
    assert result.messages == 7 and result.cards == 48
    assert result.inbound == 1 and result.needs_eyes == result.proposals == 0
    assert len(list(session.exec(select(Lead)))) == 49
    proposals = list(session.exec(select(Proposal)))
    assert len(proposals) == 1 and proposals[0].type == ProposalType.inbound
    assert not list(session.exec(select(Application)))
    assert not list(session.exec(select(Event)))


def test_inmail_followup_in_later_run_does_not_duplicate(session, settings, monkeypatch):
    box = FakeMailbox([fixture('inbound', 'regression-inbound-5.eml')])
    install(monkeypatch, box)
    assert run_intake(session, settings).inbound == 1
    box.files.append(fixture('inbound', 'regression-inbound-7.eml'))
    result = run_intake(session, settings)
    assert result.messages == 1 and result.inbound == result.needs_eyes == 0
    assert len(list(session.exec(select(Lead)))) == len(list(session.exec(select(Proposal)))) == 1
    assert session.get(SettingRow, 'gmail_cursor').value['last_uid'] == 2


@pytest.mark.parametrize('legacy', [False, True])
def test_conversation_identity_window_company_and_threads(session, legacy):
    initial = message(fixture('inbound', 'regression-inbound-5.eml'))
    lead = Lead(source=Source.gmail_inbound, source_ref=initial.message_id, title='Software Engineer',
                company='Liquidnitro Games', found_at=initial.sent_at)
    session.add(lead)
    session.flush()
    payload = {'message_id': initial.message_id} if legacy else inbound_payload(initial, lead.company)
    session.add(Proposal(type=ProposalType.inbound, lead_id=lead.id, payload=payload, evidence=initial.evidence))
    session.commit()
    for prefix in ['Message replied:', 'Re:', 'Fwd: Re: Message replied:']:
        followup = Message('followup', prefix + ' ' + initial.subject, 'hit-reply@linkedin.com',
                           'InMail: please share your profile.', sent_at=initial.sent_at + timedelta(days=30))
        assert duplicate_inbound(session, followup, lead.company)
        assert normalized_subject(followup.subject) == normalized_subject(initial.subject)
        assert not duplicate_inbound(session, followup, 'Another Company')
    expired = Message('expired', initial.subject, initial.sender, initial.text,
                      sent_at=initial.sent_at + timedelta(days=31))
    assert not duplicate_inbound(session, expired, lead.company)
    linked = Message('linked', 'A completely different subject', initial.sender, 'InMail',
                     thread_ids=(initial.message_id,), sent_at=expired.sent_at)
    assert duplicate_inbound(session, linked, lead.company)


def test_encoded_subject_is_decoded_for_matching_classification_and_evidence(session, settings, monkeypatch):
    path = fixture('rejection', 'synthetic-encoded-subject.eml')
    # Match the email policy used by imap-tools, which leaves encoded words undecoded.
    compat = BytesParser(policy=policy.compat32).parsebytes(path.read_bytes())
    assert '=?utf-8?' in compat['Subject'].lower()
    mail = Message.from_email(compat)
    assert mail.subject == 'Acme application decision – Java Developer'
    assert mail.evidence.startswith(mail.subject + '\n') and '=?' not in mail.evidence
    assert classify(mail) == 'reply'
    lead = Lead(source=Source.manual, source_ref='encoded', company='Acme', title='Java Developer')
    session.add(lead)
    session.flush()
    app = Application(lead_id=lead.id, status=AppStatus.applied)
    session.add(app)
    session.commit()
    install(monkeypatch, FakeMailbox([path]))
    assert run_intake(session, settings).proposals == 1
    proposal = session.exec(select(Proposal)).one()
    assert proposal.application_id == app.id and proposal.evidence.startswith(mail.subject + '\n')
    assert '=?' not in proposal.evidence


@pytest.mark.parametrize('subject,body,sender,bulk', [
    ('Hiring this month', 'We are hiring Software Engineers. Browse all roles.', 'updates@example.com', False),
    ('Interview tips', 'Prepare for interview questions with our community.', 'newsletter@example.com', False),
    ('Display problem', 'Unfortunately, your email client cannot display HTML.', 'mail@example.com', False),
    ('Product updates', 'Hi Test Owner, I am reaching out about a Software Engineer role.', 'person@example.com', False),
    ('Your application', 'This is a marketing email. Buy now.', 'mail@myworkday.com', True),
    ('Role opportunity', 'Hi Test Owner, we are hiring a Java Developer. Please share your resume.', 'person@example.com', True),
])
def test_low_confidence_and_bulk_never_create_proposal_candidates(subject, body, sender, bulk):
    mail = Message('negative', subject, sender, body, bulk=bulk, list_unsubscribe=True)
    assert classify(mail) == 'other'


def test_personal_consultancy_outreach_requires_targeted_role():
    mail = Message('consultancy', 'Java Developer opportunity', 'alex@consultancy.example',
                   'Hi Test Owner, I am recruiting a Java Developer for Acme. Please share your resume.')
    assert classify(mail) == 'inbound'
    unknown = Message('unknown', 'Opportunity', 'alex@example.com', 'We are hiring across all departments.')
    assert classify(unknown) == 'other'


def test_known_application_thread_can_need_eyes(session, settings, monkeypatch, tmp_path):
    lead = Lead(source=Source.manual, source_ref='thread', company='Acme', title='Java Developer')
    session.add(lead)
    session.flush()
    session.add(Application(lead_id=lead.id, status=AppStatus.applied, recruiter='alex@acme.example'))
    session.commit()
    mail = EmailMessage()
    mail['From'] = 'Test Recruiter <alex@acme.example>'
    mail['Subject'] = 'Re: Java Developer'
    mail['Message-ID'] = '<thread-response@example.com>'
    mail['In-Reply-To'] = '<owner-application@example.com>'
    mail.set_content('Could you let me know about Tuesday?')
    path = tmp_path / 'thread.eml'
    path.write_bytes(mail.as_bytes())
    install(monkeypatch, FakeMailbox([path]))
    result = run_intake(session, settings)
    assert result.needs_eyes == 1 and result.inbound == 0
    assert session.exec(select(Proposal)).one().application_id is not None


def test_inbound_apply_link_prefers_the_apply_button_and_skips_site_roots():
    from jobhunter.gmail.inbound import apply_link
    from jobhunter.gmail.message import Message

    html = ('<a href="https://www.linkedin.com/">Home</a>'
            '<a href="https://www.linkedin.com/comm/jobs/view/123456/?trackingId=abc">Apply now</a>')
    mail = Message(message_id='<m@x>', subject='s', sender='r@linkedin.com', text='hello', html=html)
    assert apply_link(mail) == 'https://www.linkedin.com/comm/jobs/view/123456/'
    bare = Message(message_id='<m@x>', subject='s', sender='r@linkedin.com', text='t',
                   html='<a href="https://click.linkedin.com/?x=1">Apply now</a>')
    assert apply_link(bare) is None  # a tracking redirect that strips down to a site root is no apply link


def test_inbound_title_from_invitation_subject_and_untruncated_description():
    from jobhunter.gmail.message import Message

    text = 'This role is a great match! ' + 'Java Spring Boot Microservices AWS Docker ' * 20
    mail = Message(message_id='<m@x>', subject="You're invited to apply for the Java Software Engineer role at Aditi Tech",
                   sender='r@linkedin.com', text=text)
    raw = parse_inbound(mail)
    assert raw.title == 'Java Software Engineer' and raw.company == 'Aditi Tech'
    assert len(raw.description) > 300 and not raw.description.endswith('Docke')
