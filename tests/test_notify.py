"""Desktop notifications: quiet hours, dedupe, switches, log mode, osascript escaping, lead rules and batching."""

import json
import subprocess
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from jobhunter import notify, paths
from jobhunter.models import Evaluation, Lead, SettingRow, Source
from jobhunter.settings import load_defaults

IST = ZoneInfo("Asia/Kolkata")
NOON = datetime(2026, 11, 12, 12, 0, tzinfo=IST).astimezone(UTC)


@pytest.fixture()
def settings():
    return load_defaults(paths.CONFIG_EXAMPLE)


@pytest.fixture()
def osascript(monkeypatch):
    """Records argv instead of running osascript."""
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    monkeypatch.delenv("JOBHUNTER_NOTIFY", raising=False)
    monkeypatch.delenv("JOBHUNTER_NOTIFY_LOG", raising=False)
    monkeypatch.setattr(notify.subprocess, "run", run)
    return calls


def local(hour, minute=0):
    return datetime(2026, 11, 12, hour, minute, tzinfo=IST)


# ---------- quiet hours ----------


@pytest.mark.parametrize(
    ("window", "hour", "quiet"),
    [
        ((23, 7), 23, True), ((23, 7), 0, True), ((23, 7), 6, True), ((23, 7), 7, False),
        ((23, 7), 12, False), ((23, 7), 22, False),
        ((1, 5), 0, False), ((1, 5), 1, True), ((1, 5), 4, True), ((1, 5), 5, False),
        ((0, 0), 3, False), ((8, 8), 8, False),
    ],
)
def test_quiet_hours_window_including_midnight_wrap(settings, window, hour, quiet):
    settings.followups.quiet_hours = window
    assert notify.in_quiet_hours(settings, local(hour, 30)) is quiet


def test_quiet_hours_use_india_time_not_utc(settings):
    utc_evening = datetime(2026, 11, 12, 18, 0, tzinfo=UTC)  # 23:30 IST
    assert notify.in_quiet_hours(settings, utc_evening)
    assert not notify.in_quiet_hours(settings, datetime(2026, 11, 12, 6, 0, tzinfo=UTC))  # 11:30 IST


def test_quiet_hours_skip_without_recording_the_key(session, settings, osascript):
    assert not notify.notify(session, settings, key="k", title="t", body="b", now=local(2))
    assert osascript == [] and session.get(SettingRow, "notify_sent") is None
    assert notify.notify(session, settings, key="k", title="t", body="b", now=local(9))
    assert len(osascript) == 1


# ---------- delivery ----------


def test_osascript_gets_title_and_body(session, settings, osascript):
    assert notify.notify(session, settings, key="k", title="Follow-up due: Acme", body="Java Developer", now=NOON)
    (argv,) = osascript
    assert argv[:2] == ["osascript", "-e"]
    assert argv[2] == 'display notification "Java Developer" with title "Follow-up due: Acme"'


def test_osascript_escapes_quotes_backslashes_and_newlines(session, settings, osascript):
    notify.notify(session, settings, key="k", title='Say "hi" \\ there', body='line1\nline2 "q"', now=NOON)
    script = osascript[0][2]
    assert script == 'display notification "line1 line2 \\"q\\"" with title "Say \\"hi\\" \\\\ there"'
    # an injection attempt stays inside the string literal
    notify.notify(session, settings, key="k2", title="x", body='" & (do shell script "id") & "', now=NOON)
    assert osascript[1][2] == 'display notification "\\" & (do shell script \\"id\\") & \\"" with title "x"'


def test_failed_osascript_is_false_and_retried_later(session, settings, monkeypatch):
    monkeypatch.delenv("JOBHUNTER_NOTIFY", raising=False)
    monkeypatch.delenv("JOBHUNTER_NOTIFY_LOG", raising=False)
    monkeypatch.setattr(notify.subprocess, "run", lambda argv, **k: subprocess.CompletedProcess(argv, 1, b"", b"nope"))
    assert notify.notify(session, settings, key="k", title="t", body="b", now=NOON) is False
    assert session.get(SettingRow, "notify_sent") is None


@pytest.mark.parametrize("error", [FileNotFoundError("osascript"), subprocess.TimeoutExpired("osascript", 10),
                                   RuntimeError("boom")])
def test_never_raises(session, settings, monkeypatch, error):
    monkeypatch.delenv("JOBHUNTER_NOTIFY", raising=False)
    monkeypatch.delenv("JOBHUNTER_NOTIFY_LOG", raising=False)

    def run(*args, **kwargs):
        raise error

    monkeypatch.setattr(notify.subprocess, "run", run)
    assert notify.notify(session, settings, key="k", title="t", body="b", now=NOON) is False


def test_never_raises_when_the_database_fails(session, settings, osascript, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("db gone")

    monkeypatch.setattr(session, "get", broken)
    assert notify.notify(session, settings, key="k", title="t", body="b", now=NOON) is False


# ---------- switches ----------


def test_settings_notifications_off(session, settings, osascript):
    settings.notifications = False
    assert not notify.notify(session, settings, key="k", title="t", body="b", now=NOON)
    assert osascript == []


def test_env_zero_disables_delivery_even_with_a_log(session, settings, osascript, monkeypatch, tmp_path):
    log = tmp_path / "n.jsonl"
    monkeypatch.setenv("JOBHUNTER_NOTIFY", "0")
    monkeypatch.setenv("JOBHUNTER_NOTIFY_LOG", str(log))
    assert not notify.notify(session, settings, key="k", title="t", body="b", now=NOON)
    assert osascript == [] and not log.exists()


def test_log_mode_appends_json_lines_instead_of_calling_osascript(session, settings, osascript, monkeypatch, tmp_path):
    log = tmp_path / "n.jsonl"
    monkeypatch.setenv("JOBHUNTER_NOTIFY_LOG", str(log))
    assert notify.notify(session, settings, key="a", title="One", body="first", now=NOON)
    assert notify.notify(session, settings, key="b", title="Two", body="second", now=NOON)
    assert osascript == []
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    assert [(x["key"], x["title"], x["body"]) for x in lines] == [("a", "One", "first"), ("b", "Two", "second")]
    assert all("at" in x for x in lines)


# ---------- dedupe ----------


def test_a_key_fires_once(session, settings, osascript):
    assert notify.notify(session, settings, key="k", title="t", body="b", now=NOON)
    assert not notify.notify(session, settings, key="k", title="t", body="b", now=NOON + timedelta(hours=1))
    assert notify.notify(session, settings, key="other", title="t", body="b", now=NOON)
    assert len(osascript) == 2
    assert set(session.get(SettingRow, "notify_sent").value) == {"k", "other"}


def test_old_keys_are_pruned_after_30_days(session, settings, osascript):
    notify.notify(session, settings, key="old", title="t", body="b", now=NOON)
    later = NOON + timedelta(days=29)
    assert not notify.notify(session, settings, key="old", title="t", body="b", now=later)
    much_later = NOON + timedelta(days=31)
    assert notify.notify(session, settings, key="fresh", title="t", body="b", now=much_later)
    assert set(session.get(SettingRow, "notify_sent").value) == {"fresh"}
    assert notify.notify(session, settings, key="old", title="t", body="b", now=much_later)


def test_garbage_in_the_sent_map_is_tolerated(session, settings, osascript):
    session.add(SettingRow(key="notify_sent", value={"bad": "yesterday-ish", "none": None}))
    session.commit()
    assert notify.notify(session, settings, key="k", title="t", body="b", now=NOON)
    assert set(session.get(SettingRow, "notify_sent").value) == {"k"}


# ---------- new leads ----------

_n = iter(range(1, 10_000))


def lead(session, *, score=0.8, age_hours=1, inbound=False, passed=True, company=None, title="Java Developer", **kw):
    n = next(_n)
    row = Lead(source=Source.naukri, source_ref=f"r{n}", company=company or f"Co{n}", title=title,
               quick_score=score, found_at=NOON - timedelta(hours=age_hours), is_inbound=inbound,
               prefilter_pass=passed, **kw)
    session.add(row)
    session.commit()
    return row


def titles(osascript):
    return [argv[2].split(' with title "')[1].rstrip('"') for argv in osascript]


def test_hot_fresh_lead_is_notified(session, settings, osascript):
    row = lead(session, company="Acme", location="Chennai")
    assert notify.notify_new_leads(session, settings, [row.id], now=NOON) == 1
    assert titles(osascript) == ["New lead: Acme"]
    assert "Java Developer · Chennai" in osascript[0][2]


def test_rules_inbound_stale_cold_dropped_and_evaluated(session, settings, osascript):
    inbound = lead(session, score=0.1, age_hours=500, inbound=True, company="Recruiter Co")
    cold = lead(session, score=0.69)
    stale = lead(session, score=0.95, age_hours=48)
    dropped = lead(session, score=0.95, passed=False)
    boundary = lead(session, score=0.70, age_hours=47, company="Boundary")
    rated = lead(session, score=0.2, company="Rated")
    low_rated = lead(session, score=0.2, company="LowRated")
    session.add(Evaluation(lead_id=rated.id, score=4.0))
    session.add(Evaluation(lead_id=low_rated.id, score=3.9))
    session.add(Evaluation(lead_id=stale.id, score=4.8))
    session.commit()
    ids = [x.id for x in (inbound, cold, stale, dropped, boundary, rated, low_rated)]
    assert notify.notify_new_leads(session, settings, ids, now=NOON) == 3
    assert sorted(titles(osascript)) == ["New lead: Boundary", "New lead: Rated", "Recruiter reached out: Recruiter Co"]


def test_latest_evaluation_score_decides(session, settings, osascript):
    row = lead(session, score=0.2)
    session.add(Evaluation(lead_id=row.id, score=4.5))
    session.add(Evaluation(lead_id=row.id, score=2.0))  # re-evaluated lower
    session.commit()
    assert notify.notify_new_leads(session, settings, [row.id], now=NOON) == 0


def test_posted_at_beats_found_at_for_freshness(session, settings, osascript):
    reposted = lead(session, posted_at=NOON - timedelta(days=10))
    assert notify.notify_new_leads(session, settings, [reposted.id], now=NOON) == 0


def test_each_lead_is_notified_once_across_runs(session, settings, osascript):
    row = lead(session)
    assert notify.notify_new_leads(session, settings, [row.id], now=NOON) == 1
    assert notify.notify_new_leads(session, settings, [row.id], now=NOON + timedelta(hours=3)) == 0
    assert len(osascript) == 1


def test_up_to_three_leads_are_sent_individually(session, settings, osascript):
    rows = [lead(session) for _ in range(3)]
    assert notify.notify_new_leads(session, settings, [r.id for r in rows], now=NOON) == 3
    assert len(osascript) == 3


def test_more_than_three_leads_batch_into_one(session, settings, osascript):
    rows = [lead(session, company=f"Batch{i}") for i in range(5)]
    assert notify.notify_new_leads(session, settings, [r.id for r in rows], now=NOON) == 1
    assert titles(osascript) == ["5 hot leads"]
    assert "Batch0" in osascript[0][2]
    # the batched leads count as notified: no individual alerts later
    assert notify.notify_new_leads(session, settings, [r.id for r in rows], now=NOON + timedelta(hours=1)) == 0
    assert len(osascript) == 1


def test_batch_skips_already_notified_leads_before_counting(session, settings, osascript):
    rows = [lead(session) for _ in range(5)]
    assert notify.notify_new_leads(session, settings, [r.id for r in rows[:2]], now=NOON) == 2
    assert notify.notify_new_leads(session, settings, [r.id for r in rows], now=NOON) == 3  # 3 left: individual
    assert len(osascript) == 5


def test_leads_in_quiet_hours_or_with_notifications_off_are_not_sent(session, settings, osascript):
    row = lead(session)
    assert notify.notify_new_leads(session, settings, [row.id], now=local(3)) == 0
    settings.notifications = False
    assert notify.notify_new_leads(session, settings, [row.id], now=NOON) == 0
    assert osascript == []


def test_empty_and_unknown_ids(session, settings, osascript):
    assert notify.notify_new_leads(session, settings, [], now=NOON) == 0
    assert notify.notify_new_leads(session, settings, [999], now=NOON) == 0


def test_notify_new_leads_never_raises(session, settings, osascript, monkeypatch):
    row = lead(session)

    def boom(*args, **kwargs):
        raise RuntimeError("db gone")

    monkeypatch.setattr(session, "exec", boom)
    assert notify.notify_new_leads(session, settings, [row.id], now=NOON) == 0
