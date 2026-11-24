"""Career-ops contract checks using real subprocess transport and offline fake binaries."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlmodel import select

from jobhunter import careerops, paths
from jobhunter.careerops._parsing import envelope, machine_summary
from jobhunter.careerops._runtime import NODE_DIR, claude_text, run, scan_timeout
from jobhunter.careerops.smoke import main as smoke_main
from jobhunter.models import (
    Actor,
    Application,
    AppStatus,
    Evaluation,
    Event,
    Lead,
    Outreach,
    ResumeVariant,
    Run,
    RunKind,
    Source,
    SourceHealth,
)
from jobhunter.settings import load_defaults, save_settings

FIXTURES = Path(__file__).parent / "fixtures" / "careerops"
SETTINGS = load_defaults(paths.CONFIG_EXAMPLE)


@pytest.fixture()
def bridge_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    cops = data / "careerops"
    cv = data / "cv"
    cops.mkdir(parents=True)
    cv.mkdir()
    for variant in ("a", "b"):
        (cv / f"cv_{variant}.md").write_text("# Example Candidate\nJava backend engineer\n")
    monkeypatch.setattr(paths, "DATA", data)
    monkeypatch.setattr(paths, "CAREEROPS_DATA", cops)
    monkeypatch.setattr(paths, "CV_DIR", cv)
    binary = FIXTURES / "fake_binary.py"
    monkeypatch.setenv("JOBHUNTER_NODE_BIN", str(binary))
    monkeypatch.setenv("JOBHUNTER_CLAUDE_BIN", str(binary))
    monkeypatch.setenv("COPS_CAPTURE", str(tmp_path / "invocations.jsonl"))
    monkeypatch.setenv("COPS_PIDS", str(tmp_path / "pids"))
    monkeypatch.delenv("COPS_SCENARIO", raising=False)
    return tmp_path


@pytest.fixture()
def lead_run(session, bridge_env):
    lead = Lead(source=Source.manual, source_ref="java-42", canonical_url="https://jobs.example.test/java-42",
                company="Example Software", title="Java Backend Engineer", jd_text="Java Spring Boot, Chennai")
    session.add(lead)
    session.commit()
    session.refresh(lead)
    full = SETTINGS.model_copy(deep=True)
    full.evaluator.mode = "full"  # these tests pin the career-ops A-H path; lean mode has its own tests
    save_settings(session, full)
    run_row = Run(kind=RunKind.evaluate, lead_id=lead.id)
    session.add(run_row)
    session.commit()
    session.refresh(run_row)
    return lead, run_row


def records(directory):
    return [json.loads(line) for line in (directory / "invocations.jsonl").read_text().splitlines()]


def test_parse_real_spike():
    report = envelope((FIXTURES / "spike_report.txt").read_text(), "report-md")
    meta = machine_summary(report)
    assert meta["score"] == 3.7
    assert meta["grade"] is None
    assert meta["archetype"] == "Java Backend Engineer / SDE I-II"
    assert meta["legitimacy_tier"] == "Proceed with Caution"


@pytest.mark.parametrize("text", ["", "<<report-md>>\nmissing closer", "<</report-md>>\n<<report-md>>",
                                  "<<report-md>>\n<</report-md>>", "mentioned <<report-md>> inline"])
def test_invalid_envelope(text):
    with pytest.raises(careerops.BridgeError, match="envelope"):
        envelope(text, "report-md")


def test_reject_multiple_envelopes():
    text = "<<report-md>>\nreport\n<</report-md>>\n" * 2
    with pytest.raises(careerops.BridgeError):
        envelope(text, "report-md")


@pytest.mark.parametrize("score", ["0", "5.1", "nan", "true", "null", "'not a number'"])
def test_summary_rejects_bad_score(score):
    with pytest.raises(careerops.BridgeError, match="score"):
        machine_summary(f"## Machine Summary\n\n```yaml\nscore: {score}\n```\n")


def test_summary_grade_and_missing_summary():
    assert machine_summary("## Machine Summary\n```yaml\nscore: 4.2\ngrade: B\n```\n")["grade"] == "B"
    with pytest.raises(careerops.BridgeError, match="Machine Summary"):
        machine_summary("No machine block")


def test_evaluate(session, lead_run, bridge_env):
    lead, run_row = lead_run
    log = io.StringIO()
    result = careerops.evaluate(session, lead.id, run_id=run_row.id, log=log, should_cancel=lambda: False)
    assert result.score == 3.7
    assert result.run_id == run_row.id
    assert result.lead_id == lead.id
    assert result.report_path.startswith("reports/001-example-software-ltd-")
    assert "Machine Summary" in careerops.report_md(result)
    assert "Proceed with Caution" in log.getvalue()
    calls = records(bridge_env)
    assert calls[0]["payload"]["jd_text"] == lead.jd_text
    assert all(Path(call["cwd"]) == paths.CAREEROPS_DATA for call in calls)
    assert all(Path(call["data"]) == paths.CAREEROPS_DATA for call in calls)
    assert all(Path(call["tracker"]).is_relative_to(paths.CAREEROPS_DATA) for call in calls)
    args = calls[1]["args"]
    assert "--strict-mcp-config" in args
    assert set(args[args.index("--disallowedTools") + 1].split(",")) >= {"Write", "Edit", "Bash", "Task"}
    assert args[args.index("--add-dir") + 1] == str(paths.CAREEROPS_VENDOR)


def assert_claude_isolated(directory):
    calls = [call for call in records(directory) if call["args"][0] == "-p"]
    assert calls
    for call in calls:
        args = call["args"]
        assert "--safe-mode" in args
        assert args[args.index("--setting-sources") + 1] == ""
        assert "--strict-mcp-config" in args
        assert "--no-session-persistence" in args
        assert "--bare" not in args


@pytest.mark.parametrize("mode", ["evaluate", "cv", "contacts"])
def test_all_claude_modes_are_isolated(session, lead_run, bridge_env, mode):
    lead, run_row = lead_run
    kwargs = {"run_id": run_row.id, "log": io.StringIO(), "should_cancel": lambda: False}
    if mode == "cv":
        careerops.generate_cv(session, lead.id, ResumeVariant.a, **kwargs)
    elif mode == "contacts":
        careerops.find_contacts(session, lead.id, **kwargs)
    else:
        careerops.evaluate(session, lead.id, **kwargs)
    assert_claude_isolated(bridge_env)


@pytest.mark.parametrize("scenario", ["usage_limit", "usage_limit_zero", "usage_limit_result"])
def test_usage_limit_has_clear_error(session, lead_run, bridge_env, monkeypatch, scenario):
    lead, run_row = lead_run
    monkeypatch.setenv("COPS_SCENARIO", scenario)
    expected = "Claude usage limit reached; resets at "
    expected += "9:30pm" if scenario == "usage_limit_result" else "21:30 IST"
    with pytest.raises(careerops.BridgeError, match=expected):
        careerops.evaluate(session, lead.id, run_id=run_row.id, log=io.StringIO(), should_cancel=lambda: False)
    assert session.exec(select(Evaluation)).all() == []


def test_stream_usage_limit_precedes_generic_result_error():
    stream = json.dumps({"type": "rate_limit_event", "rate_limit_info": {
        "status": "rejected", "resetsAt": 1794499200,
    }}) + '\n' + json.dumps({"type": "result", "is_error": True, "result": ""})
    with pytest.raises(careerops.BridgeError, match="Claude usage limit reached; resets at 21:30 IST"):
        claude_text(stream)
    assert claude_text(json.dumps({"type": "rate_limit_event", "rate_limit_info": {
        "status": "allowed_warning", "resetsAt": 1794499200,
    }}) + '\n' + json.dumps({"type": "result", "result": "ok"})) == "ok"
    report = "The role requires building APIs with rate limiting and usage limits."
    assert claude_text(json.dumps({"type": "result", "result": report})) == report


def test_evaluate_url_fallback_and_unique_reports(session, lead_run, bridge_env):
    lead, run_row = lead_run
    lead.jd_text = None
    session.add(lead)
    session.commit()
    one = careerops.evaluate(session, lead.id, run_id=run_row.id, log=io.StringIO(), should_cancel=lambda: False)
    two = careerops.evaluate(session, lead.id, run_id=run_row.id, log=io.StringIO(), should_cancel=lambda: False)
    assert one.report_path != two.report_path
    assert records(bridge_env)[0]["payload"]["url"] == lead.canonical_url


@pytest.mark.parametrize("scenario,reason", [("malformed", "envelope"), ("nonzero", "Claude session"),
                                            ("claude_error", "could not complete")])
def test_evaluate_failure(session, lead_run, monkeypatch, scenario, reason):
    lead, run_row = lead_run
    monkeypatch.setenv("COPS_SCENARIO", scenario)
    log = io.StringIO()
    with pytest.raises(careerops.BridgeError, match=reason):
        careerops.evaluate(session, lead.id, run_id=run_row.id, log=log, should_cancel=lambda: False)
    assert session.exec(select(Evaluation)).all() == []
    assert not (paths.CAREEROPS_DATA / "reports").exists()
    assert "No report" in log.getvalue() if scenario == "malformed" else "Starting" in log.getvalue()


def test_cancel_kills_process_group(session, lead_run, bridge_env, monkeypatch):
    lead, run_row = lead_run
    monkeypatch.setenv("COPS_SCENARIO", "sleep")
    pids = bridge_env / "pids"
    start = time.monotonic()
    with pytest.raises(careerops.Cancelled):
        careerops.evaluate(session, lead.id, run_id=run_row.id, log=io.StringIO(),
                           should_cancel=pids.exists)
    assert time.monotonic() - start < 3
    parent, child = map(int, pids.read_text().split())
    with pytest.raises(ProcessLookupError):
        os.kill(parent, 0)
    # A killed child can briefly remain a zombie until init reaps it.
    status = subprocess.run(["ps", "-o", "stat=", "-p", str(child)], check=False, capture_output=True, text=True)
    assert not status.stdout.strip() or status.stdout.strip().startswith("Z")


def test_pre_cancel_starts_nothing(session, lead_run, bridge_env):
    lead, run_row = lead_run
    with pytest.raises(careerops.Cancelled):
        careerops.evaluate(session, lead.id, run_id=run_row.id, log=io.StringIO(), should_cancel=lambda: True)
    assert not (bridge_env / "invocations.jsonl").exists()


def test_scan_ingests_and_records_health(session, bridge_env):
    result = careerops.scan(session, SETTINGS, log=io.StringIO(), should_cancel=lambda: False)
    assert result.fetched == 5
    assert result.new == 5
    leads = session.exec(select(Lead)).all()
    assert {lead.source for lead in leads} == {
        Source.careerops_scan, Source.himalayas, Source.remoteok, Source.remotive, Source.weworkremotely,
    }
    assert all(lead.source_ref == lead.canonical_url for lead in leads)
    assert leads[0].posted_at is not None
    health = session.get(SourceHealth, "careerops_scan")
    assert health.last_count == 5
    assert health.last_ok_at is not None
    assert health.last_error is None
    assert health.consecutive_failures == 0
    assert session.get(SourceHealth, "himalayas").last_count == 1
    again = careerops.scan(session, SETTINGS, log=io.StringIO(), should_cancel=lambda: False)
    assert again.new == 0
    assert again.updated == 5


def test_scan_error_health_recovers(session, bridge_env, monkeypatch):
    monkeypatch.setenv("COPS_SCENARIO", "scan_error")
    with pytest.raises(careerops.BridgeError, match="unreachable"):
        careerops.scan(session, SETTINGS, log=io.StringIO(), should_cancel=lambda: False)
    health = session.get(SourceHealth, "careerops_scan")
    assert health.consecutive_failures == 1
    assert health.last_run_at is not None
    monkeypatch.delenv("COPS_SCENARIO")
    careerops.scan(session, SETTINGS, log=io.StringIO(), should_cancel=lambda: False)
    session.refresh(health)
    assert health.consecutive_failures == 0
    assert health.last_error is None


def test_partial_scan_tracks_failed_and_empty_boards(session, bridge_env, monkeypatch):
    monkeypatch.setenv("COPS_SCENARIO", "partial_scan")
    result = careerops.scan(session, SETTINGS, log=io.StringIO(), should_cancel=lambda: False)
    assert result.fetched == 1
    assert "upstream timeout" in session.get(SourceHealth, "careerops_scan").last_error
    failed = session.get(SourceHealth, "remoteok")
    assert failed.consecutive_failures == 1
    assert failed.last_ok_at is None
    empty = session.get(SourceHealth, "himalayas")
    assert empty.last_ok_at is not None
    assert empty.last_count == 0


def test_actual_provider_salary_and_epoch_mapping():
    raw = careerops._raw_job({
        "title": "Java Engineer", "company": "Example", "url": "https://jobs.example.test/java",
        "provider": "ashby", "postedAt": 1794412800000,
        "salary": {"min": 1500000, "max": 2200000, "currency": "INR"},
    })
    assert raw.salary_min == 1500000
    assert raw.salary_max == 2200000
    assert raw.currency == "INR"
    assert raw.salary_text is None
    assert raw.posted_at.year == 2026


@pytest.mark.parametrize("status", [None, AppStatus.new, AppStatus.shortlisted, AppStatus.applied])
def test_verify_closed(session, lead_run, monkeypatch, status):
    lead, run_row = lead_run
    if status:
        session.add(Application(lead_id=lead.id, status=status))
        session.commit()
    monkeypatch.setenv("COPS_SCENARIO", "closed")
    result = careerops.verify(session, lead.id, run_id=run_row.id, log=io.StringIO(), should_cancel=lambda: False)
    assert result.is_live is False
    assert result.live_verified_at is not None
    application = session.exec(select(Application)).one()
    events = session.exec(select(Event)).all()
    if status == AppStatus.applied:
        assert application.status == status
        assert events == []
    else:
        assert application.status == AppStatus.expired
        assert events[0].actor == Actor.system
        assert events[0].to_status == AppStatus.expired


def test_verify_updates_latest_and_unknown_does_not_expire(session, lead_run, monkeypatch):
    lead, run_row = lead_run
    old = Evaluation(lead_id=lead.id, score=2)
    latest = Evaluation(lead_id=lead.id, score=4)
    session.add_all([old, latest])
    session.commit()
    session.refresh(latest)
    monkeypatch.setenv("COPS_SCENARIO", "unknown")
    result = careerops.verify(session, lead.id, run_id=run_row.id, log=io.StringIO(), should_cancel=lambda: False)
    assert result.id == latest.id
    assert result.score == 4
    assert result.is_live is None
    assert session.exec(select(Application)).all() == []


@pytest.mark.parametrize("variant", [ResumeVariant.a, ResumeVariant.b])
def test_generate_cv(session, lead_run, bridge_env, variant):
    lead, run_row = lead_run
    result = careerops.generate_cv(session, lead.id, variant, run_id=run_row.id,
                                   log=io.StringIO(), should_cancel=lambda: False)
    assert result.status == AppStatus.shortlisted
    assert result.resume_variant == variant
    assert result.cv_approved is False
    assert (paths.DATA / result.cv_pdf_path).is_file()
    assert len(list((paths.CAREEROPS_DATA / "output").glob("*.md"))) == 1
    assert session.exec(select(Event)).one().to_status == AppStatus.shortlisted
    calls = records(bridge_env)
    checked = [call for call in calls if call["args"][0].endswith("facts.mjs")]
    assert len(checked) == 2
    assert all(Path(call["payload"]["source"]).name == f"cv_{variant.value.lower()}.md" for call in checked)


@pytest.mark.parametrize("scenario", ["facts_fail", "pdf_error"])
def test_cv_failure_leaves_no_pdf_or_application(session, lead_run, bridge_env, monkeypatch, scenario):
    lead, run_row = lead_run
    monkeypatch.setenv("COPS_SCENARIO", scenario)
    with pytest.raises(careerops.BridgeError):
        careerops.generate_cv(session, lead.id, ResumeVariant.a, run_id=run_row.id,
                              log=io.StringIO(), should_cancel=lambda: False)
    assert list((paths.CAREEROPS_DATA / "output").glob("*.pdf")) == []
    assert session.exec(select(Application)).all() == []
    if scenario == "facts_fail":
        assert not any(c["args"][0].endswith("render.mjs") for c in records(bridge_env))


def test_assist_fills_only_approved_cv(session, lead_run, bridge_env):
    lead, run_row = lead_run
    app = Application(lead_id=lead.id, cv_pdf_path="cv/out/approved.pdf", cv_approved=False)
    session.add(app)
    session.commit()
    careerops.assist_apply(session, lead.id, run_id=run_row.id, log=io.StringIO(), should_cancel=lambda: False)
    assert records(bridge_env)[0]["payload"]["pdf"] is None
    pdf = paths.DATA / app.cv_pdf_path
    pdf.parent.mkdir()
    pdf.write_bytes(b"%PDF")
    app.cv_approved = True
    session.add(app)
    session.commit()
    log = io.StringIO()
    careerops.assist_apply(session, lead.id, run_id=run_row.id, log=log, should_cancel=lambda: False)
    assert records(bridge_env)[-1]["payload"]["pdf"] == str(pdf)
    assert records(bridge_env)[-1]["payload"]["submit"] is False
    assert '"filled"' in log.getvalue()
    script = Path(careerops.__file__).parent.joinpath("node", "assist.mjs").read_text()
    assert "headless: false" in script
    assert ".click(" not in script
    assert ".submit(" not in script
    assert ".requestSubmit(" not in script
    assert ".press(" not in script
    assert 'route.abort()' in script


def test_contacts_are_unsent_outreach(session, lead_run):
    lead, run_row = lead_run
    app = Application(lead_id=lead.id, status=AppStatus.shortlisted)
    session.add(app)
    session.commit()
    session.refresh(app)
    rows = careerops.find_contacts(session, lead.id, run_id=run_row.id,
                                   log=io.StringIO(), should_cancel=lambda: False)
    assert len(rows) == 1
    assert rows[0].application_id == app.id
    assert rows[0].lead_id == lead.id
    assert rows[0].kind.value == "referral"
    assert rows[0].sent_at is None
    assert rows[0].contact.startswith("Alex Example — https://")
    assert "Java" in rows[0].draft
    assert len(session.exec(select(Outreach)).all()) == 1


def test_no_contacts(session, lead_run, monkeypatch):
    lead, run_row = lead_run
    monkeypatch.setenv("COPS_SCENARIO", "no_contacts")
    assert careerops.find_contacts(session, lead.id, run_id=run_row.id,
                                  log=io.StringIO(), should_cancel=lambda: False) == []


def test_report_path_is_contained(bridge_env):
    outside = paths.DATA / "private.md"
    outside.write_text("private")
    assert careerops.report_md(Evaluation(lead_id=1, report_path="../private.md")) is None
    assert careerops.report_md(Evaluation(lead_id=1)) is None


def test_stream_result_deduplication_and_delta_fallback():
    text = "<<report-md>>\nreport\n<</report-md>>"
    stream = json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    stream += "\n" + json.dumps({"type": "result", "result": text})
    assert claude_text(stream) == text
    assert claude_text(json.dumps({"type": "stream_event", "event": {"delta": {
        "type": "text_delta", "text": text,
    }}})) == text


def test_timeout_and_missing_binary(bridge_env):
    with pytest.raises(careerops.BridgeError, match="Could not start"):
        run(["/missing/jobhunter-binary"], log=io.StringIO(), should_cancel=lambda: False)
    with pytest.raises(careerops.BridgeError, match="timed out"):
        run([str(FIXTURES / "fake_binary.py"), "-p", '{"kind":"evaluate"}'],
            log=io.StringIO(), should_cancel=lambda: False, timeout=0)


def test_smoke_uses_temporary_database(bridge_env, monkeypatch, capsys):
    sentinel = paths.DATA / "jobhunter.sqlite"
    sentinel.write_bytes(b"Owner database must remain untouched")
    monkeypatch.setattr(sys, "argv", ["smoke", "--lead-url", "https://jobs.example.test/java"])
    assert smoke_main() == 0
    assert sentinel.read_bytes() == b"Owner database must remain untouched"
    assert "score=3.7" in capsys.readouterr().out


@pytest.fixture()
def scan_node(tmp_path):
    """Run our actual Node scanner with offline providers and a temporary data root."""
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("Node is required for scanner policy subprocess tests")
    vendor = tmp_path / "vendor"
    (vendor / "lib").mkdir(parents=True)
    (vendor / "providers").mkdir()
    shutil.copy(FIXTURES / "scan_provider.mjs", vendor / "providers" / "_registry.mjs")
    modules = {
        "lib/yaml-document.mjs": "export const loadYaml = JSON.parse;",
        "lib/entry-response-cap.mjs": "export const applyEntryResponseCap = () => {};",
        "lib/entry-timeout.mjs": "export const applyEntryTimeout = (ctx, e) => { ctx.timeoutMs = e.timeout_ms; };",
        "providers/_http.mjs": "export const makeHttpCtx = () => ({});",
        "providers/_connection-scope.mjs": "export const withConnectionScope = fn => fn();",
    }
    for name, text in modules.items():
        (vendor / name).write_text(text)

    def invoke(targets, **env):
        (tmp_path / "portals.yml").write_text(json.dumps({"tracked_companies": targets}))
        process_env = {key: value for key, value in os.environ.items() if not key.startswith("JOBHUNTER_SCAN_")}
        process_env.update({key: str(value) for key, value in env.items()})
        return subprocess.run(
            [node_bin, str(NODE_DIR / "scan.mjs"), str(vendor)], check=False, input="{}", capture_output=True,
            text=True, cwd=tmp_path, env=process_env, timeout=5,
        )
    return invoke


def test_node_scan_deadline_returns_completed_and_marks_running_and_queued(scan_node):
    result = scan_node([
        {"name": "Completed"}, {"name": "RemoteOK", "provider": "remoteok", "hang": True},
        {"name": "Running", "hang": True}, {"name": "Queued"},
    ], JOBHUNTER_SCAN_CONCURRENCY=2, JOBHUNTER_SCAN_DEADLINE_S=0.12)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert [job["company"] for job in value["postings"]] == ["Completed"]
    assert set(value["errors"]) == {"RemoteOK: deadline", "Running: deadline", "Queued: deadline"}
    assert value["sources"]["remoteok"] == {"count": 0, "error": "deadline"}
    assert "start:Queued" not in result.stderr
    assert "abort:RemoteOK" in result.stderr


def test_node_scan_entry_timeout_frees_worker_and_preserves_results(scan_node):
    result = scan_node([
        {"name": "Completed"}, {"name": "Slow tenant", "hang": True}, {"name": "After timeout"},
    ], JOBHUNTER_SCAN_CONCURRENCY=1, JOBHUNTER_SCAN_ENTRY_TIMEOUT_S=0.05)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert {job["company"] for job in value["postings"]} == {"Completed", "After timeout"}
    assert value["errors"] == ["Slow tenant: timeout after 0.05s"]
    assert "abort:Slow tenant" in result.stderr


@pytest.mark.parametrize("reason,env", [
    ("deadline", {"JOBHUNTER_SCAN_DEADLINE_S": 0.04}),
    ("timeout after 0.04s", {"JOBHUNTER_SCAN_ENTRY_TIMEOUT_S": 0.04}),
])
def test_node_scan_fails_only_when_zero_targets_succeeded(scan_node, reason, env):
    result = scan_node([{"name": "Slow", "hang": True}], **env)
    assert result.returncode != 0
    assert f"Slow: {reason}" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("concurrency", [None, 2])
def test_node_scan_default_and_overridden_concurrency(scan_node, concurrency):
    env = {} if concurrency is None else {"JOBHUNTER_SCAN_CONCURRENCY": concurrency}
    result = scan_node([{"name": str(i), "delayMs": 30} for i in range(10)], **env)
    assert result.returncode == 0, result.stderr
    starts_before_first_result = result.stderr.split("fetched", 1)[0].count("start:")
    assert starts_before_first_result == (8 if concurrency is None else concurrency)
    assert len(json.loads(result.stdout)["postings"]) == 10


def test_node_location_filter_recall_first_table(scan_node):
    keep = [None, "", "  ", "Unknown", "N/A", "TBD", "Not specified", "Multiple locations",
            "India", "Chennai, Tamil Nadu", "Bengaluru", "Bangalore, IN", "Hyderabad", "Pune",
            "Mumbai", "New Delhi", "Gurgaon", "Gurugram", "Noida", "Kochi", "Coimbatore",
            "Karnataka", "Tamil-Nadu", "Ahmedabad", "Kerala", "Telangana", "Maharashtra",
            "Remote", "London / Remote", "Anywhere", "Worldwide", "APAC", "Asia Pacific",
            "San Francisco; Chennai", "Asia", "Global", "Work from home"]
    drop = ["San Francisco, CA", "London, United Kingdom", "Berlin, Germany", "Singapore",
            "New York, USA (Onsite)", "Toronto, Canada", "Paris, France", "Sydney, Australia",
            "Indianapolis, Indiana", "Onsite - US", "EMEA"]
    jobs = [{"title": "Java Engineer", "url": f"https://jobs.test/{i}", "location": location}
            for i, location in enumerate(keep + drop)]
    result = scan_node([{"name": "Locations", "provider": "himalayas", "jobs": jobs}])
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert [job["location"] for job in value["postings"]] == keep
    assert value["sources"]["himalayas"] == {"count": len(keep), "error": None}
    assert f"{len(jobs)} fetched, {len(keep)} kept" in result.stderr


def test_node_scan_empty_success_and_disabled_entries(scan_node):
    result = scan_node([
        {"name": "Empty", "jobs": [], "provider": "himalayas"},
        {"name": "Skipped", "enabled": False, "hang": True},
        {"name": "Unresolved", "provider": "websearch"},
    ])
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["postings"] == []
    assert value["errors"] == ["Unresolved: no public API provider"]
    assert value["sources"]["himalayas"] == {"count": 0, "error": None}
    assert "Skipped" not in result.stderr


@pytest.mark.parametrize("value,expected", [(None, 1500), ("1800", 2100), ("bad", 1500),
                                            ("0", 1500), ("nan", 1500), ("inf", 1500)])
def test_scan_timeout_tracks_node_deadline(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("JOBHUNTER_SCAN_DEADLINE_S", raising=False)
    else:
        monkeypatch.setenv("JOBHUNTER_SCAN_DEADLINE_S", value)
    assert scan_timeout() == expected


def test_python_scan_passes_extended_timeout(session, bridge_env, monkeypatch):
    timeouts = []
    original = careerops.node

    def capture(helper, payload, **kwargs):
        timeouts.append(kwargs["timeout"])
        return original(helper, payload, **kwargs)

    monkeypatch.setenv("JOBHUNTER_SCAN_DEADLINE_S", "1800")
    monkeypatch.setattr(careerops, "node", capture)
    careerops.scan(session, SETTINGS, log=io.StringIO(), should_cancel=lambda: False)
    assert timeouts == [2100]
