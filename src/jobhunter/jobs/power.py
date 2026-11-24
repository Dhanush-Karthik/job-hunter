"""Keep the Mac awake for the nightly run, and refuse to start it on a nearly empty battery.

`caffeinate -i -s -t N` holds idle- and system-sleep assertions for N seconds (-s only applies on AC power).
It cannot override a closed lid by itself; see docs/scoring-plan.md section 4.1b for the owner-side setting.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys

_logger = logging.getLogger(__name__)
MIN_BATTERY_PERCENT = 40


def hold_awake(seconds: int) -> bool:
    if sys.platform != "darwin" or not shutil.which("caffeinate"):
        return False
    try:
        subprocess.Popen(
            ["caffeinate", "-i", "-s", "-t", str(int(seconds))], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )
    except OSError:
        _logger.warning("caffeinate failed", exc_info=True)
        return False
    return True


def power_state() -> tuple[bool | None, int | None]:
    """(on AC power, battery percent); (None, None) when unknown (not macOS, no battery)."""
    if sys.platform != "darwin" or not shutil.which("pmset"):
        return None, None
    try:
        text = subprocess.run(["pmset", "-g", "batt"], check=False, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None, None
    on_ac = "AC Power" in text if "Power" in text else None
    match = re.search(r"(\d{1,3})%", text)
    return on_ac, int(match.group(1)) if match else None


def ok_to_run() -> tuple[bool, str]:
    on_ac, percent = power_state()
    if on_ac is False and percent is not None and percent < MIN_BATTERY_PERCENT:
        return False, f"on battery at {percent}% (needs AC or {MIN_BATTERY_PERCENT}%+)"
    return True, "AC power" if on_ac else f"battery {percent}%" if percent is not None else "power unknown"
