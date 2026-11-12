"""Schemathesis against the app (in-memory DB, faked runner/scheduler/keyring): no 5xx, responses match the contract.

Runs every operation in the normal suite with a small example budget (< 60 s). Dig deeper locally: SCHEMATHESIS_EXAMPLES=300 uv run pytest tests/test_api_schema.py.
"""

import os
from datetime import timedelta

import pytest
import schemathesis
from apihelpers import make_app, make_eval, make_lead
from hypothesis import HealthCheck, settings
from schemathesis.checks import not_a_server_error
from schemathesis.specs.openapi.checks import content_type_conformance, response_schema_conformance

from jobhunter.models import (
    ApplyChannel,
    AppStatus,
    Event,
    Outreach,
    OutreachKind,
    Proposal,
    ProposalType,
    Run,
    RunKind,
    Source,
    utcnow,
)

pytest_plugins = ["apihelpers"]

MAX_EXAMPLES = int(os.environ.get("SCHEMATHESIS_EXAMPLES", "20"))
CHECKS = [not_a_server_error, response_schema_conformance, content_type_conformance]


@pytest.fixture()
def api_schema(app, db):
    """Schema bound to the app, with a little of every kind of row so the happy paths run too."""
    lead = make_lead(db, source=Source.linkedin, apply_channel=ApplyChannel.platform_quick, jd_text="java")
    make_eval(db, lead, 4.0)
    shortlisted = make_app(db, lead, AppStatus.shortlisted)
    applied = make_app(db, make_lead(db), AppStatus.applied)
    make_lead(db, prefilter_pass=False, prefilter_reasons=["exp"])
    db.add(Event(application_id=applied.id, to_status=AppStatus.applied, at=utcnow() - timedelta(days=2)))
    db.add(Event(application_id=applied.id, to_status=AppStatus.screening, at=utcnow()))
    db.add(Proposal(type=ProposalType.status_change, application_id=shortlisted.id, payload={"to_status": "Skipped"}))
    db.add(Outreach(kind=OutreachKind.referral, lead_id=lead.id, draft="hi", due_at=utcnow()))
    db.add(Run(kind=RunKind.evaluate, lead_id=lead.id))
    db.commit()
    return schemathesis.openapi.from_asgi("/api/openapi.json", app)


schema = schemathesis.pytest.from_fixture("api_schema")


@schema.parametrize()
@settings(max_examples=MAX_EXAMPLES, deadline=None, suppress_health_check=list(HealthCheck))
def test_api_conforms_to_contract(case):
    case.call_and_validate(checks=CHECKS)
