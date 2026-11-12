"""Insights: rule output with enough data, the "need more applies" fallback, and the min-sample guards."""

from datetime import UTC, datetime, timedelta

import pytest

from jobhunter import analytics, paths
from jobhunter.models import (
    Actor,
    Application,
    ApplyChannel,
    AppStatus,
    Event,
    Lead,
    ResumeVariant,
    Source,
)
from jobhunter.settings import load_defaults, save_settings

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
_n = iter(range(1, 100_000))


@pytest.fixture(autouse=True)
def settings(session):
    return save_settings(session, load_defaults(paths.CONFIG_EXAMPLE))


def apply(session, *, source=Source.naukri, channel=ApplyChannel.company_ats, variant=None, title="Java Developer",
          call=False, days_ago=3.0, response_days=None, **lead_kw):
    n = next(_n)
    lead = Lead(source=source, source_ref=f"r{n}", company=f"Co{n}", title=title, apply_channel=channel, **lead_kw)
    session.add(lead)
    session.commit()
    app = Application(lead_id=lead.id, status=AppStatus.applied, resume_variant=variant)
    session.add(app)
    session.commit()
    at = NOW - timedelta(days=days_ago)
    session.add(Event(application_id=app.id, to_status=AppStatus.applied, at=at, actor=Actor.owner))
    if call:
        session.add(Event(application_id=app.id, to_status=AppStatus.screening,
                          at=at + timedelta(days=response_days or 2), actor=Actor.owner))
    elif response_days:
        session.add(Event(application_id=app.id, to_status=AppStatus.rejected,
                          at=at + timedelta(days=response_days), actor=Actor.owner))
    session.commit()
    return app


def by_kind(items):
    return {i.kind: i for i in items}


def test_too_little_data_returns_one_info_insight(session):
    assert [i.severity for i in analytics.insights(session, now=NOW)] == ["info"]
    for _ in range(3):
        apply(session)
    (only,) = analytics.insights(session, now=NOW)
    assert only.severity == "info" and only.kind == "pace"
    assert "3 applies" in only.text and "2 more" in only.text and "5 are needed" in only.text


def test_applies_outside_the_window_do_not_count(session):
    for _ in range(6):
        apply(session, days_ago=45)
    (only,) = analytics.insights(session, now=NOW)
    assert "0 applies" in only.text and "5 more" in only.text
    (wider,) = analytics.insights(session, days=60, now=NOW)  # 6 applies now count: past the fallback
    assert wider.text.startswith("0 applies in the last 7 days")


def test_best_and_weak_source(session):
    for i in range(10):
        apply(session, source=Source.naukri, call=i < 3)
    for _ in range(6):
        apply(session, source=Source.linkedin)
    got = by_kind(analytics.insights(session, now=NOW))
    best, weak = got["best_source"], got["weak_source"]
    assert best.text == "Naukri: 3 calls from 10 applies (30%), best source in the last 30 days"
    assert best.severity == "good" and best.metric == pytest.approx(0.3)
    assert weak.text.startswith("Linkedin: 0 calls from 6 applies (0%)") and weak.severity == "warn"


def test_source_with_fewer_than_five_applies_is_ignored(session):
    for i in range(5):
        apply(session, source=Source.naukri, call=i < 2)
    for _ in range(4):
        apply(session, source=Source.linkedin)
    for _ in range(3):
        apply(session, source=Source.indeed, call=True)  # perfect rate, but only 3 applies
    got = by_kind(analytics.insights(session, now=NOW))
    assert "Naukri" in got["best_source"].text and "weak_source" not in got


def test_no_best_source_when_nobody_has_a_call(session):
    for _ in range(6):
        apply(session)
    kinds = {i.kind for i in analytics.insights(session, now=NOW)}
    assert "best_source" not in kinds and "weak_source" not in kinds and "pace" in kinds


def test_variant_comparison_needs_both_variants_with_five_applies(session):
    for i in range(6):
        apply(session, variant=ResumeVariant.a, call=i < 1)
    for i in range(6):
        apply(session, variant=ResumeVariant.b, call=i < 3)
    text = by_kind(analytics.insights(session, now=NOW))["variant"].text
    assert text == "CV B: 3 calls from 6 applies (50%) vs CV A: 1 call from 6 applies (17%)"


def test_variant_skipped_with_thin_or_equal_data(session):
    for _ in range(6):
        apply(session, variant=ResumeVariant.a)
    for _ in range(3):
        apply(session, variant=ResumeVariant.b, call=True)
    assert "variant" not in by_kind(analytics.insights(session, now=NOW))
    for _ in range(3):
        apply(session, variant=ResumeVariant.b)  # B now has 6 applies and 3 calls vs A 0 calls
    assert "variant" in by_kind(analytics.insights(session, now=NOW))


def test_channel_insight_needs_a_real_gap(session):
    for i in range(6):
        apply(session, channel=ApplyChannel.platform_quick, call=i < 1)
    for i in range(6):
        apply(session, channel=ApplyChannel.company_ats, call=i < 4)
    text = by_kind(analytics.insights(session, now=NOW))["channel"].text
    assert text == "Company ats applies: 4 calls from 6 applies (67%) vs Platform quick: 1 call from 6 applies (17%)"


def test_title_insight(session):
    for i in range(5):
        apply(session, title="  Java   Developer ", call=i < 2)
    for _ in range(5):
        apply(session, title="Backend Engineer")
    text = by_kind(analytics.insights(session, now=NOW))["title"].text
    assert text == '"java developer" roles: 2 calls from 5 applies (40%), your best title so far'


def test_pace_against_targets(session, settings):
    settings.targets.applied_per_week = 10
    save_settings(session, settings)
    for _ in range(4):
        apply(session, days_ago=2)
    (fallback,) = analytics.insights(session, now=NOW)  # 4 applies: too few for the pace rule
    assert "1 more" in fallback.text
    for _ in range(2):
        apply(session, days_ago=1)
    warn = by_kind(analytics.insights(session, now=NOW))["pace"]
    assert warn.severity == "warn" and warn.text == "6 applies in the last 7 days, behind your target of 10"
    for _ in range(2):
        apply(session, days_ago=1)
    assert by_kind(analytics.insights(session, now=NOW))["pace"].severity == "info"  # 8 of 10 is close
    for _ in range(2):
        apply(session, days_ago=1)
    ok = by_kind(analytics.insights(session, now=NOW))["pace"]
    assert ok.severity == "good" and ok.metric == 10.0


def test_old_applies_do_not_count_towards_this_weeks_pace(session):
    for _ in range(8):
        apply(session, days_ago=20)
    pace = by_kind(analytics.insights(session, now=NOW))["pace"]
    assert pace.text.startswith("0 applies in the last 7 days") and pace.severity == "warn"


def test_response_time_needs_five_responses(session):
    for _ in range(4):
        apply(session, call=True, response_days=3)
    for _ in range(2):
        apply(session)
    assert "response_time" not in by_kind(analytics.insights(session, now=NOW))
    apply(session, response_days=5)  # a rejection also counts as a response
    got = by_kind(analytics.insights(session, now=NOW))["response_time"]
    assert got.text == "Companies take a median of 3.0 days to respond (5 responses)" and got.metric == 3.0


def test_top_prefilter_drop_needs_five_dropped_leads(session):
    for _ in range(6):
        apply(session)
    for i in range(4):
        session.add(Lead(source=Source.naukri, source_ref=f"d{i}", company="X", title="T", prefilter_pass=False,
                         prefilter_reasons=["city: Pune"], found_at=NOW - timedelta(days=1)))
    session.commit()
    assert "rejects" not in by_kind(analytics.insights(session, now=NOW))
    session.add(Lead(source=Source.naukri, source_ref="d9", company="X", title="T", prefilter_pass=False,
                     prefilter_reasons=["city: Pune", "exp too high"], found_at=NOW - timedelta(days=1)))
    session.commit()
    got = by_kind(analytics.insights(session, now=NOW))["rejects"]
    assert got.text.startswith('Top prefilter drop: "city: Pune" (5 of 5 dropped leads)') and got.metric == 5.0


def test_at_most_six_most_useful_first(session):
    for i in range(6):
        apply(session, source=Source.naukri, channel=ApplyChannel.platform_quick, variant=ResumeVariant.a,
              title="Java Developer", call=i < 3, response_days=2)
    for _ in range(6):
        apply(session, source=Source.linkedin, channel=ApplyChannel.company_ats, variant=ResumeVariant.b,
              title="Backend Engineer", response_days=2)
    for i in range(6):
        session.add(Lead(source=Source.indeed, source_ref=f"d{i}", company="X", title="T", prefilter_pass=False,
                         prefilter_reasons=["x"], found_at=NOW - timedelta(days=1)))
    session.commit()
    out = analytics.insights(session, now=NOW)
    assert len(out) == analytics.MAX_INSIGHTS == 6
    assert [i.kind for i in out][:3] == ["best_source", "weak_source", "variant"]
    assert all(i.text for i in out)


def test_naive_now_is_treated_as_utc(session):
    for i in range(6):
        apply(session, call=i < 2)
    assert analytics.insights(session, now=NOW.replace(tzinfo=None)) == analytics.insights(session, now=NOW)
