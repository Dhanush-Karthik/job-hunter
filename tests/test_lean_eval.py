"""Lean evaluation: codex first, claude fallback, structured JSON, no tools, posting text only on stdin."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from jobhunter import careerops, paths
from jobhunter.careerops import BridgeError, lean
from jobhunter.models import Lead, Run, RunKind, Source
from jobhunter.settings import load_defaults, save_settings

FAKE = Path(__file__).parent / "fixtures" / "careerops" / "fake_engine.py"
SECRET_JD = "UNIQUE-POSTING-TEXT Java Spring Boot microservices, Chennai, 2-4 years"


@pytest.fixture()
def lean_env(session, tmp_path, monkeypatch):
    cops = tmp_path / "careerops"
    (cops / "modes").mkdir(parents=True)
    (cops / "cv.md").write_text("# CV\n**Email:** me@example.test\n**Phone:** +91 1\n## Summary\nJava backend engineer\n")
    (cops / "modes" / "_profile.md").write_text("# Profile\n## Your Target Roles\nJava\n## Your Negotiation Scripts\nsecret script\n")
    monkeypatch.setattr(paths, "CAREEROPS_DATA", cops)
    monkeypatch.setenv("JOBHUNTER_CODEX_BIN", str(FAKE))
    monkeypatch.setenv("JOBHUNTER_CLAUDE_BIN", str(FAKE))
    monkeypatch.setenv("FAKE_CAPTURE", str(tmp_path / "calls.jsonl"))
    monkeypatch.setattr(lean, "_cooldown", {})
    save_settings(session, load_defaults(paths.CONFIG_EXAMPLE))
    lead = Lead(source=Source.manual, source_ref="x", company="Acme", title="Java Backend Engineer", jd_text=SECRET_JD)
    session.add(lead)
    session.commit()
    run = Run(kind=RunKind.evaluate, lead_id=lead.id)
    session.add(run)
    session.commit()
    return lead, run, tmp_path / "calls.jsonl"


def _calls(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _evaluate(session, lead, run):
    return careerops.evaluate(session, lead.id, run_id=run.id, log=io.StringIO(), should_cancel=lambda: False)


def test_codex_first(session, lean_env):
    lead, run, capture = lean_env
    ev = _evaluate(session, lead, run)
    assert (ev.score, ev.grade, ev.call_chance, ev.engine) == (4.2, "B", "high", "codex:gpt-6.2-sol")
    assert ev.verdict.startswith("Strong Java backend")
    calls = _calls(capture)
    assert [c["engine"] for c in calls] == ["codex"]
    argv = calls[0]["argv"]
    assert {"--sandbox", "read-only", "--ignore-user-config", "--ephemeral"} <= set(argv)
    assert "model_reasoning_effort=low" in argv and "shell_tool" in argv
    assert not any("UNIQUE-POSTING-TEXT" in a for a in argv) and "UNIQUE-POSTING-TEXT" in calls[0]["stdin"]
    assert "me@example.test" not in calls[0]["stdin"] and "secret script" not in calls[0]["stdin"]
    report = careerops.report_md(ev)
    assert "Interview-call chance:** high" in report and "## Machine Summary" in report


@pytest.mark.parametrize("codex_mode", ["fail", "junk", "limit"])
def test_claude_fallback(session, lean_env, monkeypatch, codex_mode):
    lead, run, capture = lean_env
    monkeypatch.setenv("FAKE_CODEX", codex_mode)
    ev = _evaluate(session, lead, run)
    assert (ev.score, ev.engine) == (3.8, "claude:sonnet")
    calls = _calls(capture)
    assert [c["engine"] for c in calls] == ["codex", "claude"]
    claude = calls[1]["argv"]
    assert claude[claude.index("--tools") + 1] == "" and "--safe-mode" in claude
    assert claude[claude.index("--effort") + 1] == "low"
    assert not any("UNIQUE-POSTING-TEXT" in a for a in claude)


def test_usage_limit_skips_engine_for_rest_of_night(session, lean_env, monkeypatch):
    lead, run, capture = lean_env
    monkeypatch.setenv("FAKE_CODEX", "limit")
    _evaluate(session, lead, run)
    _evaluate(session, lead, run)
    assert [c["engine"] for c in _calls(capture)] == ["codex", "claude", "claude"]


def test_all_engines_fail(session, lean_env, monkeypatch):
    lead, run, _ = lean_env
    monkeypatch.setenv("FAKE_CODEX", "fail")
    monkeypatch.setenv("FAKE_CLAUDE", "limit")
    with pytest.raises(BridgeError, match="All evaluation engines failed"):
        _evaluate(session, lead, run)


@pytest.mark.parametrize(("raw", "error"), [
    ({"score": 9}, "out of range"), ({"call_chance": "high"}, "numeric score"), ([], "no JSON object"),
])
def test_validate_rejects(raw, error):
    with pytest.raises(lean.EngineError, match=error):
        lean.validate(raw)


def test_validate_normalises():
    out = lean.validate({"score": "3.66", "call_chance": "MAYBE", "verdict": " a \n b ", "strengths": list("abcd")})
    assert out["score"] == 3.7 and out["grade"] == "C" and out["call_chance"] == "medium"
    assert out["verdict"] == "a b" and out["strengths"] == ["a", "b", "c"]


def test_stated_minimum_above_owner_range_is_capped(session, lean_env):
    lead, run, _ = lean_env
    lead.exp_min, lead.exp_max = 4, 8
    session.add(lead)
    session.commit()
    ev = _evaluate(session, lead, run)  # the fake engine answers 4.2 / high regardless
    assert (ev.score, ev.call_chance, ev.grade) == (2.5, "low", "E")
