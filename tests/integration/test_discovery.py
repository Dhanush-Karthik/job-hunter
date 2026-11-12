import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from sqlmodel import select

from jobhunter.intake.boards import fetch_boards
from jobhunter.models import Lead, RoleFamily, Source, SourceHealth
from jobhunter.pipeline import ingest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "boards"
NOW = datetime(2026, 11, 12, 12, tzinfo=UTC)
SITES = ("linkedin", "naukri", "indeed", "glassdoor")


@pytest.fixture()
def board_rows():
    return {site: json.loads((FIXTURES / f"{site}.json").read_text()) for site in SITES}


def fetch(session, settings, scrape, now=NOW):
    return fetch_boards(session, settings, scrape=scrape, sleep=lambda _: None, now=now)


def test_recorded_boards_to_db_and_idempotent_refetch(session, settings, board_rows):
    def scrape(**kwargs):
        return pd.DataFrame(board_rows[kwargs["site_name"][0]])

    raw = fetch(session, settings, scrape)
    expected = {(Source(site), row["id"]) for site, rows in board_rows.items() for row in rows}
    result = ingest(session, raw, settings, now=NOW, cv_text="")
    leads = list(session.exec(select(Lead)))
    assert result.fetched == result.new == len(expected) == 20
    assert len(leads) == len(expected)
    assert {(lead.source, lead.source_ref) for lead in leads} == expected
    found = {lead.id: lead.found_at for lead in leads}
    assert all(at.replace(tzinfo=UTC) == NOW for at in found.values())
    dropped = [lead for lead in leads if not lead.prefilter_pass]
    assert result.dropped == len(dropped) > 0
    assert all(lead.prefilter_reasons and all(lead.prefilter_reasons) for lead in dropped)
    for site in SITES:
        health = session.get(SourceHealth, site)
        assert health.last_count == 5
        assert health.last_ok_at.replace(tzinfo=UTC) == NOW
        assert health.last_run_at.replace(tzinfo=UTC) == NOW
        assert health.last_error is None
        assert health.consecutive_failures == 0

    later = NOW + timedelta(hours=3)
    again = ingest(session, fetch(session, settings, scrape, later), settings, now=later, cv_text="")
    session.expire_all()
    leads = list(session.exec(select(Lead)))
    assert again.new == 0
    assert again.updated == 20
    assert len(leads) == len(expected)
    assert {lead.id: lead.found_at for lead in leads} == found
    assert {(lead.source, lead.source_ref) for lead in leads} == expected
    for site in SITES:
        assert session.get(SourceHealth, site).last_ok_at.replace(tzinfo=UTC) == later


def test_cross_site_duplicate_and_role_ranking_through_fetch(session, settings, board_rows):
    # Recorded sites have no shared posting. Replay one recorded LinkedIn posting on Naukri too.
    duplicate = dict(board_rows["linkedin"][0], id="nk-cross-site")
    other = dict(duplicate, id="nk-other", company="Integration Other", title="Office Administrator",
                 description="Office administration", skills=None,
                 job_url="https://example.com/jobs/other", job_url_direct=None)
    settings.query_matrix.sites = [Source.linkedin, Source.naukri]

    def scrape(**kwargs):
        return pd.DataFrame([board_rows["linkedin"][0]] if kwargs["site_name"] == ["linkedin"]
                            else [duplicate, other])

    ingest(session, fetch(session, settings, scrape), settings, now=NOW, cv_text="")
    leads = {lead.source_ref: lead for lead in session.exec(select(Lead))}
    original = leads[board_rows["linkedin"][0]["id"]]
    assert original.dedupe_group
    assert original.dedupe_group == leads["nk-cross-site"].dedupe_group
    assert original.source != leads["nk-cross-site"].source
    assert leads["nk-other"].dedupe_group != original.dedupe_group
    assert original.role_family == RoleFamily.p1
    assert leads["nk-other"].role_family == RoleFamily.other
    assert original.quick_score > leads["nk-other"].quick_score
    assert leads["nk-cross-site"].quick_score > leads["nk-other"].quick_score


@pytest.mark.parametrize("failed_site", SITES)
def test_one_site_failure_does_not_block_other_sites(session, settings, board_rows, failed_site):
    def scrape(**kwargs):
        site = kwargs["site_name"][0]
        if site == failed_site:
            raise RuntimeError("integration: connection reset")
        return pd.DataFrame(board_rows[site])

    result = ingest(session, fetch(session, settings, scrape), settings, now=NOW, cv_text="")
    leads = list(session.exec(select(Lead)))
    assert result.new == len(leads) == 15
    assert {lead.source.value for lead in leads} == set(SITES) - {failed_site}
    failed = session.get(SourceHealth, failed_site)
    assert failed.last_error == "integration: connection reset"
    assert failed.consecutive_failures == 1
    assert failed.last_count == 0
    assert failed.last_ok_at is None
    assert failed.last_run_at.replace(tzinfo=UTC) == NOW
    for site in set(SITES) - {failed_site}:
        health = session.get(SourceHealth, site)
        assert health.last_count == 5
        assert health.last_error is None
        assert health.last_ok_at.replace(tzinfo=UTC) == NOW
