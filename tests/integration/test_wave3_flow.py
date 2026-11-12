"""Wave 3 through the real API, runner and SQLite; external services stay offline."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from email import policy
from email.parser import BytesParser
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import yaml
from sqlmodel import Session, select

from jobhunter import gmail, paths, secrets
from jobhunter.db import get_engine
from jobhunter.followups import add_business_days, is_business_day
from jobhunter.gmail import imap
from jobhunter.jobs import runner
from jobhunter.models import Application, Event, RunKind

from .test_wave2_flow import ROOT, real_client, response_json, wait_run  # noqa: F401

EMAILS = ROOT / 'tests/fixtures/emails'


class ReadOnlyMailbox:
    """Expose only read operations; preserve UIDs when more fixtures arrive."""
    def __init__(self):
        self.files = []
        self.folder = self

    def login(self, address, password, *, initial_folder):
        assert address == 'owner@example.com' and password == 'offline-password'
        assert initial_folder is None
        return self

    def set(self, name, *, readonly):
        assert readonly is True

    def status(self, name, options):
        assert options == ['UIDVALIDITY']
        return {'UIDVALIDITY': 42}

    def fetch(self, criteria, *, mark_seen, reverse):
        assert mark_seen is False and reverse is False
        for uid, path in enumerate(self.files, 1):
            yield SimpleNamespace(uid=str(uid), obj=BytesParser(policy=policy.default).parsebytes(path.read_bytes()))

    def logout(self):
        pass


@pytest.fixture()
def wave3(request, monkeypatch, tmp_path):
    box = ReadOnlyMailbox()
    monkeypatch.setattr(imap, 'mailbox_factory', lambda host, port: box)
    stored = {'gmail_address': 'owner@example.com', 'gmail_app_password': 'offline-password'}
    monkeypatch.setattr(secrets.keyring, 'get_password', lambda service, name: stored.get(name))
    monkeypatch.setattr(secrets.keyring, 'set_password', lambda service, name, value: stored.update({name: value}))
    monkeypatch.setenv('JOBHUNTER_NOTIFY_LOG', str(tmp_path / 'notify.jsonl'))
    monkeypatch.delenv('JOBHUNTER_NOTIFY', raising=False)
    client = request.getfixturevalue("real_client")
    settings = response_json(client.get('/api/settings'))
    settings['notifications'] = True
    settings['followups']['quiet_hours'] = [0, 0]
    response_json(client.put('/api/settings', json=settings))
    return client, box, tmp_path / 'notify.jsonl'


def intake(client):
    runs = response_json(client.post('/api/intake/run', json={'sources': ['gmail_inbound']}), 202)
    assert len(runs) == 1 and runs[0]['kind'] == 'intake_gmail'
    return wait_run(client, runs[0]['id'])


def applied(client, company):
    lead = response_json(client.post('/api/leads', json={
        'company': company, 'title': 'Java Developer', 'location': 'Chennai',
        'url': f'https://{company.lower()}.example/jobs/java', 'jd_text': 'Java Spring Boot backend',
    }), 201)
    detail = response_json(client.post(f"/api/leads/{lead['id']}/shortlist"))
    app_id = detail['application']['id']
    app = response_json(client.post(f'/api/applications/{app_id}/transition', json={'to_status': 'Applied'}))
    assert app['status'] == 'Applied'
    assert [e['to_status'] for e in response_json(client.get(f'/api/applications/{app_id}/events'))] == [
        'Shortlisted', 'Ready', 'Applied']
    return app_id


def test_inbound_notification_convert_and_alert_replay(wave3):
    client, box, log = wave3
    box.files.append(next((EMAILS / 'inbound').glob('*yubi*')))
    intake(client)
    proposal, = response_json(client.get('/api/proposals'))
    assert proposal['type'] == 'inbound'
    lead = response_json(client.get(f"/api/leads/{proposal['lead_id']}"))
    assert lead['is_inbound'] and lead['source'] == 'gmail_inbound'
    app = response_json(client.post(f"/api/proposals/{proposal['id']}/convert"))
    assert app['status'] == 'Shortlisted' and app['lead_id'] == lead['id']
    notifications = [json.loads(line) for line in log.read_text().splitlines()]
    assert any(lead['company'] in n['title'] and n['key'] == f"lead:{lead['id']}" for n in notifications)
    box.files.append(min((EMAILS / 'linkedin').glob('*.eml')))
    intake(client)
    alerts = response_json(client.get('/api/leads', params={'source': 'gmail_alert'}))['items']
    assert alerts and all(lead['source'] == 'gmail_alert' for lead in alerts)
    before = {lead['id'] for lead in alerts}
    log_before_replay = log.read_text()
    intake(client)
    assert {lead['id'] for lead in response_json(client.get('/api/leads', params={'source': 'gmail_alert'}))['items']} == before
    assert len(response_json(client.get('/api/proposals', params={'state': 'accepted'}))) == 1
    assert log.read_text() == log_before_replay


def test_replies_acceptance_counts_calls_and_rejection_stage(wave3):
    client, box, _ = wave3
    rejected = applied(client, 'Acme')
    screening = applied(client, 'Rocketlane')
    before = response_json(client.get('/api/today'))['interview_calls_week']
    box.files.extend([EMAILS / 'rejection/synthetic-1.eml',
                      EMAILS / 'interview/2025-10-07_rocketlane-interview-round1.eml'])
    intake(client)
    proposals = response_json(client.get('/api/proposals'))
    assert len(proposals) == 2 and all(p['type'] == 'status_change' for p in proposals)
    for p in proposals:
        assert response_json(client.get(f"/api/applications/{p['application_id']}"))['status'] == 'Applied'
        response_json(client.post(f"/api/proposals/{p['id']}/accept", json={}))
    app = response_json(client.get(f'/api/applications/{rejected}'))
    assert app['status'] == 'Rejected' and app['rejected_at_stage'] == 'Applied'
    assert response_json(client.get(f'/api/applications/{screening}'))['status'] == 'Screening'
    assert response_json(client.get('/api/today'))['interview_calls_week'] == before + 1
    rows = response_json(client.get('/api/analytics/breakdown?by=source'))['rows']
    assert next(row for row in rows if row['key'] == 'manual') == {
        'key': 'manual', 'applied': 2, 'calls': 1, 'rate': 0.5}
    intake(client)
    assert response_json(client.get('/api/proposals')) == []


def test_followups_sent_and_ghosted_are_idempotent_without_events(wave3):
    client, _, _ = wave3
    app_id = applied(client, 'FollowupCo')
    ghost_id = applied(client, 'SilentCo')
    now = datetime.now(UTC)
    old = now
    remaining = 8
    while remaining:
        old -= timedelta(days=1)
        if is_business_day(old.astimezone(ZoneInfo('Asia/Kolkata')).date()):
            remaining -= 1
    with Session(get_engine()) as session:
        app = session.get(Application, app_id)
        app.applied_at = old
        app.next_follow_up_at = add_business_days(old, 5)
        session.add(app)
        ghost = session.get(Application, ghost_id)
        ghost.applied_at = now - timedelta(days=22)
        ghost.next_follow_up_at = now + timedelta(days=1)
        session.add(ghost)
        for event in session.exec(select(Event).where(Event.application_id == ghost_id)):
            event.at = now - timedelta(days=22)
            session.add(event)
        session.commit()
        events_before = [e.model_dump() for e in session.exec(select(Event).order_by(Event.id))]
    wait_run(client, runner.submit(RunKind.followups).id)
    outreach, = response_json(client.get('/api/outreach?kind=follow_up&due_only=true'))
    assert outreach['application_id'] == app_id and 'FollowupCo' in outreach['draft']
    sent = response_json(client.post(f"/api/outreach/{outreach['id']}/mark-sent"))
    assert sent['sent_at']
    wait_run(client, runner.submit(RunKind.followups).id)
    assert response_json(client.get('/api/outreach?kind=follow_up&due_only=true')) == []
    assert len(response_json(client.get('/api/outreach?kind=follow_up'))) == 1
    ghosted = [p for p in response_json(client.get('/api/proposals')) if p['type'] == 'ghosted']
    assert len(ghosted) == 1 and ghosted[0]['application_id'] == ghost_id
    with Session(get_engine()) as session:
        assert [e.model_dump() for e in session.exec(select(Event).order_by(Event.id))] == events_before


def test_companies_setup_gmail_and_insights(wave3, monkeypatch):
    client, _, _ = wave3
    portal = paths.CAREEROPS_DATA / 'portals.yml'
    portal.write_text('job_boards: [remotive]\ntracked_companies: []\n')
    assert response_json(client.get('/api/companies')) == []
    company = response_json(client.post('/api/companies', json={
        'name': 'OfflineCo', 'careers_url': 'https://offline.example/careers'}), 201)
    assert company['enabled'] is True
    changed = response_json(client.patch('/api/companies/OfflineCo', json={
        'enabled': False, 'careers_url': 'https://offline.example/jobs'}))
    assert changed['enabled'] is False and changed['careers_url'].endswith('/jobs')
    assert response_json(client.get('/api/companies')) == [changed]
    assert yaml.safe_load(portal.read_text())['job_boards'] == ['remotive']
    assert client.delete('/api/companies/OfflineCo').status_code == 204
    assert response_json(client.get('/api/companies')) == []
    calls = []
    def check(address, password):
        calls.append((address, password))
    monkeypatch.setattr(gmail, 'check_login', check)
    assert response_json(client.post('/api/setup/gmail-test'))['ok'] is True
    assert calls == [('owner@example.com', 'offline-password')]
    monkeypatch.setattr(gmail, 'check_login', lambda *args: 'Authentication failed: offline-password')
    failed = response_json(client.post('/api/setup/gmail-test'))
    assert failed['ok'] is False and 'Authentication failed' in failed['detail']
    assert 'offline-password' not in failed['detail']
    assert isinstance(response_json(client.get('/api/analytics/insights')), list)
