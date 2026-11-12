"""Follow-ups: IST business days, idempotent run, second follow-up, ghosted proposals, profile refresh."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlmodel import select

from jobhunter import followups, notify, paths
from jobhunter.followups import holidays
from jobhunter.models import (
    Actor,
    Application,
    AppStatus,
    Event,
    Lead,
    Outreach,
    OutreachKind,
    Profile,
    Proposal,
    ProposalState,
    ProposalType,
    Source,
)
from jobhunter.settings import load_defaults

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 12, 10, 30, tzinfo=IST).astimezone(UTC)  # Thursday, inside notification hours
DAY = timedelta(days=1)


@pytest.fixture(autouse=True)
def notifications(tmp_path, monkeypatch):
    log = tmp_path / "notify.jsonl"
    monkeypatch.delenv("JOBHUNTER_NOTIFY", raising=False)
    monkeypatch.setenv("JOBHUNTER_NOTIFY_LOG", str(log))
    monkeypatch.setattr(notify.subprocess, "run", lambda *a, **k: pytest.fail("osascript must not run in tests"))
    return log


def sent_titles(log):
    import json

    return [json.loads(line)["title"] for line in log.read_text().splitlines()] if log.exists() else []


@pytest.fixture()
def settings():
    return load_defaults(paths.CONFIG_EXAMPLE)


_n = iter(range(1, 10_000))


def applied(session, *, company="Acme", applied_ago=6, due_ago=1, status=AppStatus.applied, event_ago=None):
    n = next(_n)
    lead = Lead(source=Source.manual, source_ref=f"r{n}", company=company, title="Java Developer")
    session.add(lead)
    session.commit()
    app = Application(
        lead_id=lead.id, status=status, applied_at=NOW - applied_ago * DAY,
        next_follow_up_at=None if due_ago is None else NOW - due_ago * DAY)
    session.add(app)
    session.commit()
    session.add(Event(application_id=app.id, to_status=AppStatus.applied, at=NOW - (event_ago or applied_ago) * DAY,
                      actor=Actor.owner))
    session.commit()
    return app


def outreach_of(session, app):
    session.expire_all()
    return list(session.exec(select(Outreach).where(Outreach.application_id == app.id).order_by(Outreach.id)))


# ---------- business days ----------


def test_holiday_list_covers_2026_and_2027():
    years = {d[:4] for d in holidays.HOLIDAYS}
    assert years == {"2026", "2027"}
    for text in holidays.HOLIDAYS:
        date.fromisoformat(text)  # every key is a real date
    for text in ("2026-01-26", "2026-08-15", "2026-10-02", "2026-12-25", "2027-01-26", "2027-04-14"):
        assert text in holidays.HOLIDAYS


def test_is_business_day_weekends_and_holidays():
    assert followups.is_business_day(date(2026, 11, 12))  # Thursday
    assert not followups.is_business_day(date(2026, 11, 14))  # Saturday
    assert not followups.is_business_day(date(2026, 11, 15))  # Sunday
    assert not followups.is_business_day(date(2026, 10, 2))  # Gandhi Jayanti, a Friday
    assert not followups.is_business_day(date(2027, 1, 26))  # Republic Day, a Tuesday


def test_extra_holidays_are_added_and_bad_entries_ignored():
    assert followups.is_business_day(date(2026, 11, 13))
    assert not followups.is_business_day(date(2026, 11, 13), ["2026-11-13"])
    assert followups.is_business_day(date(2026, 11, 13), ["not-a-date", ""])


def test_add_business_days_skips_weekend():
    start = datetime(2026, 11, 13, 10, 0, tzinfo=IST)  # Friday
    assert followups.add_business_days(start, 1) == datetime(2026, 11, 16, 10, 0, tzinfo=IST)
    assert followups.add_business_days(start, 5) == datetime(2026, 11, 20, 10, 0, tzinfo=IST)
    assert followups.add_business_days(start, 0) == start


def test_add_business_days_skips_holiday_and_keeps_time_of_day():
    start = datetime(2026, 10, 1, 9, 45, tzinfo=IST)  # Thursday; Fri 2 Oct is Gandhi Jayanti
    assert followups.add_business_days(start, 1) == datetime(2026, 10, 5, 9, 45, tzinfo=IST)
    assert followups.add_business_days(start, 1, ["2026-10-05"]) == datetime(2026, 10, 6, 9, 45, tzinfo=IST)
    # Thu 24 Dec + 1: Fri 25 Dec (Christmas) and the weekend are skipped
    assert followups.add_business_days(datetime(2026, 12, 24, 12, tzinfo=IST), 1) == datetime(
        2026, 12, 28, 12, tzinfo=IST)


def test_add_business_days_works_across_timezones_and_naive():
    utc = datetime(2026, 11, 13, 4, 30, tzinfo=UTC)  # Fri 10:00 IST
    got = followups.add_business_days(utc, 1)
    assert got == datetime(2026, 11, 16, 4, 30, tzinfo=UTC) and got.tzinfo is UTC
    assert followups.add_business_days(datetime(2026, 11, 13, 4, 30), 1) == datetime(2026, 11, 16, 4, 30, tzinfo=UTC)
    late = datetime(2026, 11, 13, 20, 0, tzinfo=UTC)  # Sat 01:30 IST: the local day is already a weekend
    assert followups.add_business_days(late, 1) == datetime(2026, 11, 15, 20, 0, tzinfo=UTC)  # Mon 01:30 IST


def test_draft_follow_up_mentions_role_company_and_date():
    first = followups.draft_follow_up("Acme", "Java Developer", datetime(2026, 11, 6, 5, tzinfo=UTC))
    assert "Java Developer" in first and "Acme" in first and "06 Nov 2026" in first
    assert "[recruiter name]" in first and "{" not in first
    second = followups.draft_follow_up("Acme", "Java Developer", None, second=True)
    assert "once more" in second and "recently" in second and second != first


# ---------- run ----------


def test_due_application_gets_one_follow_up_and_one_notification(session, settings, notifications):
    app = applied(session, company="Acme")
    first = followups.run(session, settings, now=NOW)
    assert (first.follow_ups_created, first.notifications) == (1, 1)
    (row,) = outreach_of(session, app)
    assert row.kind == OutreachKind.follow_up and row.sent_at is None
    assert row.lead_id == app.lead_id and row.due_at.replace(tzinfo=UTC) == NOW - DAY
    assert "Acme" in row.draft and "Java Developer" in row.draft
    assert sent_titles(notifications) == ["Follow-up due: Acme"]

    again = followups.run(session, settings, now=NOW + timedelta(hours=1))
    assert (again.follow_ups_created, again.ghosted_proposals, again.notifications) == (0, 0, 0)
    assert len(outreach_of(session, app)) == 1
    assert sent_titles(notifications) == ["Follow-up due: Acme"]


def test_not_due_closed_or_undated_applications_are_left_alone(session, settings):
    applied(session, due_ago=-2)  # due in two days
    applied(session, due_ago=None)
    applied(session, status=AppStatus.screening)
    applied(session, status=AppStatus.rejected)
    result = followups.run(session, settings, now=NOW)
    assert result.follow_ups_created == 0
    assert session.exec(select(Outreach)).all() == []


def test_quiet_hours_skip_the_notification_and_a_later_run_delivers_it(session, settings, notifications):
    app = applied(session)
    night = datetime(2026, 11, 12, 2, 0, tzinfo=IST).astimezone(UTC)
    first = followups.run(session, settings, now=night)
    assert (first.follow_ups_created, first.notifications) == (1, 0)
    assert sent_titles(notifications) == []
    morning = followups.run(session, settings, now=NOW)
    assert (morning.follow_ups_created, morning.notifications) == (0, 1)
    assert len(outreach_of(session, app)) == 1
    assert followups.run(session, settings, now=NOW + timedelta(hours=1)).notifications == 0


def test_snoozed_follow_up_is_not_renotified(session, settings, notifications):
    app = applied(session)
    night = datetime(2026, 11, 12, 2, 0, tzinfo=IST).astimezone(UTC)  # quiet hours: row created, nothing sent
    assert followups.run(session, settings, now=night).notifications == 0
    (row,) = outreach_of(session, app)
    row.snoozed_until = NOW + DAY
    session.add(row)
    session.commit()
    assert followups.run(session, settings, now=NOW).notifications == 0
    assert sent_titles(notifications) == []
    assert followups.run(session, settings, now=NOW + 2 * DAY).notifications == 1


def test_sent_follow_up_schedules_the_second_one_and_drafts_it_when_due(session, settings, notifications):
    app = applied(session)
    followups.run(session, settings, now=NOW)
    (first,) = outreach_of(session, app)
    first.sent_at = NOW  # Thursday 12 Nov 10:30 IST
    session.add(first)
    session.commit()

    result = followups.run(session, settings, now=NOW + timedelta(hours=2))
    assert result.follow_ups_created == 0
    session.expire_all()
    app = session.get(Application, app.id)
    expected = followups.add_business_days(NOW, settings.followups.second_follow_up_business_days)
    assert app.next_follow_up_at.replace(tzinfo=UTC) == expected
    assert expected.astimezone(IST).date() == date(2026, 11, 23)  # 7 business days, weekend skipped
    assert len(outreach_of(session, app)) == 1

    assert followups.run(session, settings, now=expected - timedelta(minutes=1)).follow_ups_created == 0
    second_run = followups.run(session, settings, now=expected + timedelta(hours=1))
    assert second_run.follow_ups_created == 1
    rows = outreach_of(session, app)
    assert len(rows) == 2 and rows[1].sent_at is None and "once more" in rows[1].draft
    assert rows[1].due_at.replace(tzinfo=UTC) == expected
    assert sent_titles(notifications) == ["Follow-up due: Acme", "Follow-up due: Acme"]


def test_there_is_never_a_third_follow_up(session, settings):
    app = applied(session)
    followups.run(session, settings, now=NOW)
    (first,) = outreach_of(session, app)
    first.sent_at = NOW
    session.add(first)
    session.commit()
    later = NOW + 20 * DAY
    followups.run(session, settings, now=later)
    first_after_second = outreach_of(session, app)
    assert len(first_after_second) == 2
    second = first_after_second[1]
    second.sent_at = later
    session.add(second)
    session.commit()
    for step in range(3):
        followups.run(session, settings, now=later + (step + 1) * 10 * DAY)
    assert len(outreach_of(session, app)) == 2
    session.expire_all()
    assert session.get(Application, app.id).next_follow_up_at is None


def test_second_follow_up_respects_extra_holidays(session, settings):
    settings.followups.second_follow_up_business_days = 1
    settings.followups.extra_holidays = ["2026-11-13"]
    app = applied(session)
    followups.run(session, settings, now=NOW)
    (first,) = outreach_of(session, app)
    first.sent_at = NOW  # Thu
    session.add(first)
    session.commit()
    followups.run(session, settings, now=NOW)
    session.expire_all()
    assert session.get(Application, app.id).next_follow_up_at.replace(tzinfo=UTC).astimezone(IST).date() == date(
        2026, 11, 16)  # Fri is a custom holiday, weekend skipped


def test_follow_up_leaves_moved_on_applications_alone(session, settings):
    app = applied(session)
    followups.run(session, settings, now=NOW)
    app.status = AppStatus.screening
    session.add(app)
    session.commit()
    result = followups.run(session, settings, now=NOW + 30 * DAY)
    assert result.follow_ups_created == 0 and result.ghosted_proposals == 0


# ---------- ghosted ----------


def ghost_proposals(session):
    session.expire_all()
    return list(session.exec(select(Proposal).where(Proposal.type == ProposalType.ghosted)))


def test_ghosted_proposal_after_threshold_once(session, settings):
    stale = applied(session, applied_ago=22, due_ago=None)
    applied(session, applied_ago=20, due_ago=None)  # inside 21 days
    result = followups.run(session, settings, now=NOW)
    assert result.ghosted_proposals == 1
    (proposal,) = ghost_proposals(session)
    assert proposal.application_id == stale.id and proposal.lead_id == stale.lead_id
    assert proposal.payload == {"to_status": "Ghosted"} and proposal.state == ProposalState.pending
    assert "22 days" in proposal.evidence
    assert followups.run(session, settings, now=NOW + timedelta(hours=1)).ghosted_proposals == 0
    assert len(ghost_proposals(session)) == 1


def test_any_recent_event_resets_the_ghost_clock(session, settings):
    app = applied(session, applied_ago=30, due_ago=None)
    session.add(Event(application_id=app.id, from_status=AppStatus.applied, to_status=AppStatus.applied,
                      at=NOW - 5 * DAY, actor=Actor.system))
    session.commit()
    assert followups.run(session, settings, now=NOW).ghosted_proposals == 0
    assert followups.run(session, settings, now=NOW + 17 * DAY).ghosted_proposals == 1


def test_dismissed_ghosted_proposal_is_not_recreated(session, settings):
    applied(session, applied_ago=40, due_ago=None)
    followups.run(session, settings, now=NOW)
    (proposal,) = ghost_proposals(session)
    proposal.state = ProposalState.dismissed
    session.add(proposal)
    session.commit()
    assert followups.run(session, settings, now=NOW + 5 * DAY).ghosted_proposals == 0
    assert len(ghost_proposals(session)) == 1


def test_ghost_threshold_comes_from_settings(session, settings):
    settings.followups.ghosted_after_days = 7
    applied(session, applied_ago=8, due_ago=None)
    assert followups.run(session, settings, now=NOW).ghosted_proposals == 1


def test_application_without_events_uses_applied_at(session, settings):
    app = applied(session, applied_ago=25, due_ago=None)
    for e in session.exec(select(Event)).all():
        session.delete(e)
    session.commit()
    assert followups.run(session, settings, now=NOW).ghosted_proposals == 1
    assert ghost_proposals(session)[0].application_id == app.id


# ---------- profile refresh ----------


def test_profile_refresh_notifies_once_per_local_day(session, settings, notifications):
    session.add(Profile(platform="naukri", refresh_every_days=1, last_refreshed_at=NOW - 2 * DAY))
    session.add(Profile(platform="linkedin", refresh_every_days=None))
    session.add(Profile(platform="instahyre", refresh_every_days=7, last_refreshed_at=NOW - DAY))
    session.commit()
    assert followups.run(session, settings, now=NOW).notifications == 1
    assert sent_titles(notifications) == ["Refresh your naukri profile"]
    assert followups.run(session, settings, now=NOW + timedelta(hours=3)).notifications == 0
    next_day = NOW + DAY
    assert followups.run(session, settings, now=next_day).notifications == 1
    assert sent_titles(notifications) == ["Refresh your naukri profile"] * 2


def test_profile_refreshed_today_is_quiet(session, settings, notifications):
    session.add(Profile(platform="naukri", refresh_every_days=1, last_refreshed_at=NOW - timedelta(hours=3)))
    session.commit()
    assert followups.run(session, settings, now=NOW).notifications == 0
    assert sent_titles(notifications) == []


def test_never_refreshed_profile_is_due(session, settings):
    session.add(Profile(platform="naukri", refresh_every_days=1))
    session.commit()
    assert followups.run(session, settings, now=NOW).notifications == 1


def test_notifications_off_still_creates_rows(session, settings, notifications):
    settings.notifications = False
    app = applied(session)
    result = followups.run(session, settings, now=NOW)
    assert (result.follow_ups_created, result.notifications) == (1, 0)
    assert len(outreach_of(session, app)) == 1 and sent_titles(notifications) == []


def test_summary_text():
    assert followups.FollowupResult(2, 1, 3).summary() == "2 follow-ups due, 1 ghosted proposals, 3 notifications"
