from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "start.sh"
LABEL = "com.jobhunter.server"

STUB = """#!/bin/sh
echo "$@" >> "$STUB_LOG"
case "$1" in
  print) [ -f "$STUB_STATE" ] ;;
  bootstrap) touch "$STUB_STATE" ;;
  bootout) rm -f "$STUB_STATE" ;;
esac
"""


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A copy of start.sh in its own directory: ROOT, data/ and the pidfile never touch the real server."""
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copy(SRC, root / "start.sh")
    return root


def run(repo: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    base = {**os.environ, "JOBHUNTER_NO_OPEN": "1"}
    return subprocess.run(
        ["bash", str(repo / "start.sh"), *args],
        check=False,
        capture_output=True,
        text=True,
        env={**base, **(env or {})},
        timeout=60,
    )


@pytest.fixture()
def launchd(tmp_path: Path) -> dict[str, str]:
    stub_dir = tmp_path / "stubbin"
    stub_dir.mkdir()
    (stub_dir / "launchctl").write_text(STUB)
    (stub_dir / "launchctl").chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    return {
        "HOME": str(home),
        "PATH": f"{stub_dir}{os.pathsep}/tmp/with&amp<odd>{os.pathsep}{os.environ['PATH']}",
        "STUB_LOG": str(tmp_path / "launchctl.log"),
        "STUB_STATE": str(tmp_path / "loaded"),
    }


def calls(env: dict[str, str]) -> list[str]:
    log = Path(env["STUB_LOG"])
    return log.read_text().splitlines() if log.exists() else []


def test_usage_lists_commands(repo: Path) -> None:
    result = run(repo, "help")
    assert result.returncode == 0
    for word in ("doctor", "up", "stop", "status", "logs", "foreground", "autostart on|off"):
        assert word in result.stdout


def test_unknown_command_exits_2(repo: Path) -> None:
    result = run(repo, "frobnicate")
    assert result.returncode == 2
    assert "usage:" in result.stdout


def test_doctor_exits_1_without_claude(repo: Path) -> None:
    result = run(repo, "doctor", env={"PATH": "/usr/bin:/bin"})
    assert result.returncode == 1
    assert "claude CLI not on PATH" in result.stdout
    assert "fix:" in result.stdout and "claude login" in result.stdout


def test_autostart_requires_known_argument(repo: Path, launchd: dict[str, str]) -> None:
    assert run(repo, "autostart", env=launchd).returncode == 2
    assert run(repo, "autostart", "maybe", env=launchd).returncode == 2
    assert calls(launchd) == []


def test_autostart_on_writes_plist_and_bootstraps(repo: Path, launchd: dict[str, str]) -> None:
    result = run(repo, "autostart", "on", env=launchd)
    assert result.returncode == 0, result.stderr
    plist_path = Path(launchd["HOME"]) / "Library/LaunchAgents" / f"{LABEL}.plist"
    plist = plistlib.loads(plist_path.read_bytes())
    assert plist["Label"] == LABEL
    assert plist["ProgramArguments"] == [str(repo / "start.sh"), "foreground"]
    assert plist["RunAtLoad"] is True and plist["KeepAlive"] is True
    assert plist["WorkingDirectory"] == str(repo)
    assert plist["EnvironmentVariables"]["PATH"] == launchd["PATH"]  # incl. characters that need XML escaping
    log = str(repo / "data/logs/server.log")
    assert plist["StandardOutPath"] == log and plist["StandardErrorPath"] == log
    assert f"bootstrap gui/{os.getuid()} {plist_path}" in calls(launchd)

    status = run(repo, "autostart", "status", env=launchd)
    assert status.returncode == 0 and "autostart on (loaded)" in status.stdout


def test_stop_boots_out_loaded_agent_first(repo: Path, launchd: dict[str, str]) -> None:
    run(repo, "autostart", "on", env=launchd)
    result = run(repo, "stop", env=launchd)
    assert result.returncode == 0
    assert f"bootout gui/{os.getuid()}/{LABEL}" in calls(launchd)
    assert not Path(launchd["STUB_STATE"]).exists()


def test_autostart_off_boots_out_and_removes_plist(repo: Path, launchd: dict[str, str]) -> None:
    run(repo, "autostart", "on", env=launchd)
    result = run(repo, "autostart", "off", env=launchd)
    assert result.returncode == 0
    assert f"bootout gui/{os.getuid()}/{LABEL}" in calls(launchd)
    assert not (Path(launchd["HOME"]) / "Library/LaunchAgents" / f"{LABEL}.plist").exists()
    status = run(repo, "autostart", "status", env=launchd)
    assert status.returncode == 1 and "autostart off" in status.stdout


def test_autostart_off_without_plist_is_harmless(repo: Path, launchd: dict[str, str]) -> None:
    assert run(repo, "autostart", "off", env=launchd).returncode == 0
    assert not any(c.startswith("bootout") for c in calls(launchd))
