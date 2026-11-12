"""Offline contract tests replaying one real five-row capture per board."""

import hashlib
import json
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from jobhunter import paths
from jobhunter.intake.boards import CURSOR_KEY, fetch_boards
from jobhunter.models import SettingRow, Source, SourceHealth
from jobhunter.settings import load_defaults

FIXTURES = Path(__file__).parent / "fixtures" / "boards"
NOW = datetime(2026, 11, 12, 8, tzinfo=UTC)


@pytest.fixture
def settings():
    return load_defaults(paths.CONFIG_EXAMPLE)


def one_query(settings, site):
    settings.query_matrix.sites = [Source(site)]
    settings.query_matrix.titles = ["Java Developer"]
    settings.query_matrix.locations = ["Chennai"]
    return settings


@pytest.mark.parametrize("site", ["linkedin", "naukri", "indeed", "glassdoor"])
def test_recorded_response_mapping(session, settings, site):
    one_query(settings, site)
    rows = json.loads((FIXTURES / f"{site}.json").read_text())
    calls = []

    def scrape(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame(rows)

    jobs = fetch_boards(session, settings, scrape=scrape, sleep=lambda _: None, now=NOW)
    assert len(jobs) == len(rows) == 5
    assert calls[0]["site_name"] == [site]
    assert calls[0]["results_wanted"] == settings.query_matrix.results_wanted
    assert calls[0]["hours_old"] == settings.query_matrix.hours_old
    assert calls[0]["location"] == "Chennai"
    assert calls[0]["verbose"] == 0
    if site in {"indeed", "glassdoor"}:
        assert calls[0]["country_indeed"] == "India"
    if site == "linkedin":
        assert calls[0]["linkedin_fetch_description"] is True
    if site == "naukri":
        assert calls[0]["fetch_description"] is True
    for job, row in zip(jobs, rows, strict=True):
        assert job.source == Source(site)
        assert job.source_ref == row["id"]
        assert job.title == row["title"]
        assert job.company == row["company"]
        assert job.location == row["location"]
        assert job.job_url == row["job_url"]
        assert job.apply_url == row["job_url_direct"]
        assert job.description == row["description"]
        assert job.is_remote == row["is_remote"]
        assert job.salary_min == row["min_amount"]
        assert job.salary_max == row["max_amount"]
        assert job.salary_interval == row["interval"]
        assert job.currency == row["currency"]
        assert job.job_level == row["job_level"]
        assert job.posted_at == datetime.fromisoformat(row["date_posted"]).replace(tzinfo=UTC)
        assert job.source_detail == "Java Developer @ Chennai"
        if site == "naukri":
            assert job.experience_text == row["experience_range"]
            assert job.skills == [skill.strip() for skill in row["skills"].split(",")]
        else:
            assert job.skills == []
        json.dumps(job.raw, allow_nan=False)
    health = session.get(SourceHealth, site)
    assert health.last_count == 5
    assert health.last_ok_at.replace(tzinfo=UTC) == NOW
    assert health.last_run_at.replace(tzinfo=UTC) == NOW
    assert health.last_error is None
    assert health.consecutive_failures == 0


def test_rotation_persists_advances_and_wraps(session, settings):
    settings.query_matrix.sites = [Source.linkedin, Source.naukri]
    settings.query_matrix.titles = ["Java", "Backend", "Spring"]
    settings.query_matrix.locations = ["Chennai", "Bengaluru"]
    calls = []

    def scrape(**kwargs):
        calls.append((kwargs["site_name"][0], kwargs["search_term"], kwargs["location"]))
        return pd.DataFrame()

    # Six daily runs -> one of six combinations per site per run.
    for index in range(6):
        fetch_boards(session, settings, scrape=scrape, sleep=lambda _: None, now=NOW)
        state = session.get(SettingRow, CURSOR_KEY).value
        assert state["offsets"] == {"linkedin": (index + 1) % 6, "naukri": (index + 1) % 6}
    assert len(calls) == 12
    assert len(set(calls)) == 12
    fetch_boards(session, settings, scrape=scrape, sleep=lambda _: None, now=NOW)
    assert calls[-2:] == calls[:2]


def test_default_matrix_finishes_daily_coverage(session, settings):
    seen = set()

    def scrape(**kwargs):
        seen.add((kwargs["site_name"][0], kwargs["search_term"], kwargs["location"],
                  kwargs.get("is_remote", False)))
        return pd.DataFrame()

    for _ in range(6):
        fetch_boards(session, settings, scrape=scrape, sleep=lambda _: None)
    assert len(seen) == len(settings.query_matrix.sites) * 27


def test_caps_apply_per_site_and_delays_between_all_calls(session, settings):
    settings.query_matrix.titles = [f"Java {i}" for i in range(100)]
    counts = Counter()
    delays = []

    def scrape(**kwargs):
        counts.update(kwargs["site_name"])
        return pd.DataFrame()

    fetch_boards(session, settings, scrape=scrape, sleep=delays.append)
    assert counts == {"linkedin": 6, "naukri": 10, "indeed": 10, "glassdoor": 10}
    assert len(delays) == sum(counts.values()) - 1
    assert all(2 <= delay <= 6 for delay in delays)


def test_global_cap_round_robins_without_starvation(session, settings):
    calls = []

    def scrape(**kwargs):
        calls.append(kwargs["site_name"][0])
        return pd.DataFrame()

    for _ in range(4):
        fetch_boards(session, settings, scrape=scrape, sleep=lambda _: None, max_queries=1)
    assert calls == ["linkedin", "naukri", "indeed", "glassdoor"]


@pytest.mark.parametrize("message", ["HTTP 429", "Too Many Requests", "request blocked"])
def test_rate_limit_retry_then_record_failure_and_continue_other_sites(session, settings, message):
    settings.query_matrix.sites = [Source.linkedin, Source.indeed]
    settings.query_matrix.titles = ["Java"]
    settings.query_matrix.locations = ["Chennai"]
    calls = []
    sleeps = []

    def scrape(**kwargs):
        site = kwargs["site_name"][0]
        calls.append(site)
        if site == "linkedin":
            raise RuntimeError(message)
        return pd.DataFrame([{"id": "indeed-1", "title": "Java", "company": "Acme"}])

    jobs = fetch_boards(session, settings, scrape=scrape, sleep=sleeps.append, now=NOW)
    assert calls == ["linkedin", "linkedin", "indeed"]
    assert len(jobs) == 1
    health = session.get(SourceHealth, "linkedin")
    assert health.last_error == message
    assert health.consecutive_failures == 1
    assert health.last_count == 0
    assert health.last_ok_at is None
    assert health.last_run_at.replace(tzinfo=UTC) == NOW
    assert 8 in sleeps
    assert session.get(SourceHealth, "indeed").last_count == 1


def test_auto_pause_skip_expire_and_recover(session, settings):
    one_query(settings, "linkedin")
    sleeps = []
    attempts = []

    def fail(**kwargs):
        attempts.append(kwargs)
        raise RuntimeError("429")

    for run in range(3):
        fetch_boards(session, settings, scrape=fail, sleep=sleeps.append,
                     now=NOW + timedelta(hours=run))
    health = session.get(SourceHealth, "linkedin")
    assert health.consecutive_failures == 3
    assert health.paused_until.replace(tzinfo=UTC) == NOW + timedelta(hours=8)
    assert len(attempts) == 6
    assert all(delay in sleeps for delay in (8, 16, 32))
    state = session.get(SettingRow, CURSOR_KEY).value
    fetch_boards(session, settings, scrape=fail, sleep=sleeps.append, now=NOW + timedelta(hours=3))
    assert len(attempts) == 6
    assert session.get(SettingRow, CURSOR_KEY).value == state
    assert health.last_run_at.replace(tzinfo=UTC) == NOW + timedelta(hours=2)
    fetch_boards(session, settings, scrape=lambda **_: pd.DataFrame(), sleep=sleeps.append,
                 now=NOW + timedelta(hours=8))
    assert health.consecutive_failures == 0
    assert health.paused_until is None
    assert health.last_error is None
    assert health.last_ok_at.replace(tzinfo=UTC) == NOW + timedelta(hours=8)


def test_disabled_sites_are_skipped(session, settings):
    one_query(settings, "naukri")
    session.add(SourceHealth(source="naukri", enabled=False))
    session.commit()

    def scrape(**kwargs):
        pytest.fail("Disabled source must not scrape")

    assert fetch_boards(session, settings, scrape=scrape) == []
    assert session.get(SourceHealth, "naukri").last_run_at is None


def test_remote_mapping_nan_dates_and_easy_apply(session, settings):
    one_query(settings, "naukri")
    settings.query_matrix.locations = ["Remote India"]
    calls = []
    row = {
        "id": np.nan, "job_url": "https://example.com/jobs/1", "title": "Backend",
        "company": "Acme", "job_url_direct": np.nan, "description": pd.NA,
        "is_remote": np.bool_(True), "date_posted": date(2026, 11, 10),
        "min_amount": np.float64(100000), "max_amount": float("inf"), "interval": "monthly",
        "currency": "INR", "skills": "Java, Spring Boot, , Kafka ", "experience_range": "2-4 Yrs",
        "easy_apply": "yes", "job_level": "Mid-Senior", "missing": pd.NaT,
        "nested": {"x": [np.nan, pd.Timestamp("2026-11-01", tz="UTC"), np.int64(4)]},
    }

    def scrape(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame([row])

    [job] = fetch_boards(session, settings, scrape=scrape, now=NOW)
    assert calls[0]["location"] == "India"
    assert calls[0]["is_remote"] is True
    assert job.source_detail == "Java Developer @ Remote India"
    assert job.source_ref == hashlib.sha1(row["job_url"].encode()).hexdigest()
    assert job.apply_url is None
    assert job.description is None
    assert job.salary_max is None
    assert job.salary_min == 100000
    assert job.salary_interval == "monthly"
    assert job.is_remote is True
    assert job.easy_apply is True
    assert job.posted_at == datetime(2026, 11, 10, tzinfo=UTC)
    assert job.skills == ["Java", "Spring Boot", "Kafka"]
    assert job.raw["nested"] == {"x": [None, "2026-11-01T00:00:00+00:00", 4]}
    assert job.raw["missing"] is None
    json.dumps(job.raw, allow_nan=False)


@pytest.mark.parametrize("site", ["linkedin", "naukri"])
def test_boolean_false_and_aware_timestamp(session, settings, site):
    one_query(settings, site)
    frame = pd.DataFrame([{"id": "test", "title": "Java", "company": "Acme",
                           "is_remote": "false", "is_easy_apply": False,
                           "date_posted": pd.Timestamp("2026-11-12T11:00:00+05:30")}])
    [job] = fetch_boards(session, settings, scrape=lambda **_: frame)
    assert job.easy_apply is False
    assert job.is_remote is False
    assert job.posted_at == datetime(2026, 11, 12, 5, 30, tzinfo=UTC)


def test_retry_success_resets_health(session, settings):
    one_query(settings, "linkedin")
    session.add(SourceHealth(source="linkedin", consecutive_failures=2, last_error="old failure"))
    session.commit()
    calls = []

    def scrape(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("blocked")
        return pd.DataFrame()

    fetch_boards(session, settings, scrape=scrape, sleep=lambda _: None, now=NOW)
    health = session.get(SourceHealth, "linkedin")
    assert len(calls) == 2
    assert health.consecutive_failures == 0
    assert health.last_error is None


def test_retry_consumes_site_cap(session, settings):
    one_query(settings, "linkedin")
    settings.query_matrix.titles = [f"Java {i}" for i in range(50)]
    calls = []

    def scrape(**kwargs):
        calls.append(kwargs)
        if len(calls) == 6:
            raise RuntimeError("429")
        return pd.DataFrame()

    fetch_boards(session, settings, scrape=scrape, sleep=lambda _: None)
    assert len(calls) == 6
    assert session.get(SourceHealth, "linkedin").consecutive_failures == 1


def test_no_retry_on_regular_error_and_global_budget_limits_retry(session, settings):
    one_query(settings, "linkedin")
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("connection reset")

    fetch_boards(session, settings, scrape=fail, sleep=lambda _: None)
    assert len(calls) == 1

    def rate_limit(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("429")

    fetch_boards(session, settings, scrape=rate_limit, sleep=lambda _: None, max_queries=1)
    assert len(calls) == 2


def test_google_supported_and_empty_is_success(session, settings):
    assert Source.google not in settings.query_matrix.sites
    one_query(settings, "google")
    assert fetch_boards(session, settings, scrape=lambda **_: pd.DataFrame()) == []
    assert session.get(SourceHealth, "google").consecutive_failures == 0
    assert session.get(SourceHealth, "google").last_ok_at is not None


@pytest.mark.parametrize("limit", [0, -1])
def test_zero_budget_does_not_advance(session, settings, limit):
    assert fetch_boards(session, settings, scrape=lambda **_: pytest.fail(), max_queries=limit) == []
    assert session.get(SettingRow, CURSOR_KEY) is None


def test_empty_matrix_does_not_call_scraper(session, settings):
    settings.query_matrix.titles = []
    assert fetch_boards(session, settings, scrape=lambda **_: pytest.fail()) == []
