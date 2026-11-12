"""Pure portal generation and CLI tests; no network or real runtime writes."""

import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_portals.py"
spec = importlib.util.spec_from_file_location("build_portals", SCRIPT)
portals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(portals)


@pytest.mark.parametrize(("url", "provider"), [
    ("https://job-boards.greenhouse.io/acme", "greenhouse"),
    ("https://boards.eu.greenhouse.io/acme", "greenhouse"),
    ("https://boards-api.greenhouse.io/v1/boards/acme/jobs", "greenhouse"),
    ("https://jobs.lever.co/acme", "lever"),
    ("https://jobs.eu.lever.co/acme", "lever"),
    ("https://jobs.ashbyhq.com/Acme", "ashby"),
    ("https://acme.wd3.myworkdayjobs.com/en-US/External", "workday"),
    ("https://wd3.myworkdaysite.com/recruiting/acme/External", "workday"),
    ("https://careers.smartrecruiters.com/Acme", "smartrecruiters"),
    ("https://acme.darwinbox.in/ms/candidate/careers", "darwinbox"),
    ("https://acme.keka.com/careers/", "keka"),
    ("https://acme.zohorecruit.in/jobs/Careers", "zoho-recruit"),
    ("https://acme.zohorecruit.com/jobs/Careers", "zoho-recruit"),
    ("https://jobs.successfactors.eu/acme", "successfactors"),
    ("https://acme.jobs2web.com/careers", "successfactors"),
    ("https://careers.acme.com/", None),
    ("https://evilgreenhouse.io/acme", None),
    ("https://greenhouse.io.evil.com/", None),
    ("https://example.com/?ats=lever.co", None),
    ("javascript://jobs.lever.co/acme", None),
    ("not a URL", None),
])
def test_detect_ats(url, provider):
    assert portals.detect_ats(url) == provider


def test_native_detection_takes_priority_and_keeps_branded_url():
    seed = [{"name": "Acme", "careers_url": "https://acme.com/careers"}]
    [entry] = portals.company_entries(seed, ["phenom"])
    assert entry["provider"] == "phenom"
    assert entry["careers_url"] == seed[0]["careers_url"]
    assert "scan_method" not in entry


def test_unknown_ats_is_explicit_websearch_fallback():
    [entry] = portals.company_entries([{"name": "Acme", "careers_url": "https://acme.com/careers"}], [None])
    assert entry["scan_method"] == "websearch"
    assert "Acme" in entry["scan_query"]
    assert "Java OR backend" in entry["scan_query"]
    assert "unresolved" in entry["notes"]
    assert "provider" not in entry
    assert entry["scan_query"].startswith("site:acme.com/careers ")


def test_live_discovery_uses_vendor_preview_and_resolves_known_board(monkeypatch):
    original = [{"name": "Acme", "careers_url": "https://acme.com/careers"},
                {"name": "Beta", "careers_url": "https://beta.com/jobs"}]
    entries = portals.company_entries(original, [None, None])
    response = {"resolved": [{"name": "Acme", "vendor": "greenhouse",
                              "careers_url": "https://job-boards.greenhouse.io/acme",
                              "api": "https://boards-api.greenhouse.io/v1/boards/acme/jobs"}]}
    run = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(response), ""))
    monkeypatch.setattr(portals.subprocess, "run", run)
    result = portals.discover_entries(entries)
    command = run.call_args.args[0]
    assert command[0] == "node"
    assert command[1].endswith("discover-ats.mjs")
    assert "--write" not in command
    assert result[0]["provider"] == "greenhouse"
    assert result[0]["api"].endswith("/acme/jobs")
    assert "scan_method" not in result[0]
    assert "scan_query" not in result[0]
    assert result[1] == entries[1]
    assert entries[0]["scan_method"] == "websearch"


def test_live_discovery_failure_keeps_fallback(monkeypatch):
    entries = portals.company_entries([{"name": "Acme", "careers_url": "https://acme.com/careers"}], [None])
    monkeypatch.setattr(portals.subprocess, "run", Mock(side_effect=FileNotFoundError("node")))
    assert portals.discover_entries(entries) == entries


def test_merge_keeps_existing_entries_and_is_idempotent():
    existing = {
        "title_filter": {"positive": ["Java"], "negative": ["Principal"]},
        "tracked_companies": [{"name": " ACME ", "careers_url": "https://old.example/",
                               "enabled": False, "notes": "keep this"}],
        "job_boards": [{"name": "My remote feed", "provider": "remotive", "enabled": False}],
        "custom_key": {"keep": True},
    }
    additions = [
        {"name": "Acme", "careers_url": "https://new.example", "enabled": True},
        {"name": "Beta", "careers_url": "https://beta.example"},
        {"name": "Beta alias", "careers_url": "https://beta.example/"},
    ]
    result = portals.merge_portals(existing, additions)
    assert len(result["tracked_companies"]) == 2
    assert result["tracked_companies"][0] == existing["tracked_companies"][0]
    assert result["job_boards"][0] == existing["job_boards"][0]
    assert len(result["job_boards"]) == 4
    assert result["title_filter"] == existing["title_filter"]
    assert result["custom_key"] == existing["custom_key"]
    assert portals.merge_portals(result, additions) == result
    assert len(existing["tracked_companies"]) == 1  # no mutation of the caller's dict


def test_vendor_detection_uses_native_registry_without_write(monkeypatch):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, '["greenhouse", null]', ""))
    monkeypatch.setattr(portals.subprocess, "run", run)
    assert portals.vendor_detection([{"name": "Acme"}, {"name": "Beta"}]) == ["greenhouse", None]
    args, kwargs = run.call_args
    assert args[0][:3] == ["node", "--input-type=module", "--eval"]
    assert "resolveProvider" in args[0][3]
    assert "writeFile" not in args[0][3]
    assert json.loads(kwargs["input"]) == [{"name": "Acme"}, {"name": "Beta"}]
    assert kwargs["timeout"] == 45


@pytest.mark.parametrize("failure", [FileNotFoundError("node"), subprocess.TimeoutExpired("node", 45),
                                     subprocess.CalledProcessError(1, "node")])
def test_vendor_unavailable_falls_back(monkeypatch, failure):
    monkeypatch.setattr(portals.subprocess, "run", Mock(side_effect=failure))
    assert portals.vendor_detection([{"name": "Acme"}]) == [None]
    [entry] = portals.company_entries([{"name": "Acme", "careers_url": "https://jobs.lever.co/acme"}], [None])
    assert entry["provider"] == "lever"


def test_seed_has_at_least_150_unique_companies():
    seed = yaml.safe_load((portals.ROOT / "config" / "seed_companies.yml").read_text())["companies"]
    assert len(seed) >= 150
    assert len({row["name"].casefold() for row in seed}) == len(seed)
    assert all(row["careers_url"].startswith("https://") for row in seed)


def test_cli_dry_run_and_idempotent_write(monkeypatch, tmp_path, capsys):
    output = tmp_path / "runtime" / "portals.yml"
    monkeypatch.setenv("CAREER_OPS_DATA_DIR", str(output.parent))
    monkeypatch.setattr(portals, "vendor_detection", lambda rows: [None] * len(rows))
    assert portals.main(["--dry-run"]) == 0
    result = yaml.safe_load(capsys.readouterr().out)
    assert len(result["tracked_companies"]) >= 150
    assert not output.parent.exists()
    assert {row["provider"] for row in result["job_boards"]} == {
        "himalayas", "remoteok", "remotive", "weworkremotely",
    }
    assert all(row["enabled"] for row in result["job_boards"])
    assert "Java" in result["title_filter"]["positive"]
    assert portals.main([]) == 0
    before = output.read_bytes()
    mtime = output.stat().st_mtime_ns
    assert portals.main([]) == 0
    assert output.read_bytes() == before
    assert output.stat().st_mtime_ns == mtime
