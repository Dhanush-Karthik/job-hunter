"""Fail-closed parsing of the inline artifacts returned by career-ops."""

from __future__ import annotations

import math
import re
from typing import Any

import yaml


def envelope(text: str, kind: str) -> str:
    from jobhunter.careerops import BridgeError

    text = text.replace("\r\n", "\n")
    opening = re.compile(rf"^<<{re.escape(kind)}(?:[ \t]+[^>\n]*)?>>[ \t]*$", re.MULTILINE)
    closing = re.compile(rf"^<</{re.escape(kind)}>>[ \t]*$", re.MULTILINE)
    starts, ends = list(opening.finditer(text)), list(closing.finditer(text))
    if len(starts) != 1 or len(ends) != 1 or starts[0].end() >= ends[0].start():
        raise BridgeError(f"Missing or malformed {kind} envelope; see run log")
    content = text[starts[0].end():ends[0].start()].strip()
    if not content:
        raise BridgeError(f"Empty {kind} envelope; see run log")
    return content + "\n"


def machine_summary(markdown: str) -> dict[str, Any]:
    from jobhunter.careerops import BridgeError

    section = re.search(r"^#{1,6}\s+Machine Summary[^\n]*\n", markdown, re.MULTILINE | re.IGNORECASE)
    if not section:
        raise BridgeError("Report has no Machine Summary; see run log")
    fence = re.match(r"\s*```(?:yaml|yml)\s*\n(.*?)\n```", markdown[section.end():], re.DOTALL)
    try:
        meta = yaml.safe_load(fence[1]) if fence else None
        if not isinstance(meta, dict) or isinstance(meta.get("score"), bool):
            raise TypeError
        score = float(str(meta["score"]).removesuffix("/5").strip())
        if not math.isfinite(score) or not 1 <= score <= 5:
            raise ValueError
    except (yaml.YAMLError, KeyError, TypeError, ValueError) as exc:
        raise BridgeError("Machine Summary has no valid score (1–5); see run log") from exc
    meta["score"] = score
    grade = meta.get("grade")
    if grade is None:
        match = re.search(r"^\*{0,2}Grade\*{0,2}:\*{0,2}\s*([A-H][+-]?)\b", markdown, re.MULTILINE)
        grade = match[1] if match else None
    if grade is not None and not re.fullmatch(r"[A-H][+-]?", str(grade).strip()):
        raise BridgeError("Machine Summary has an invalid grade; see run log")
    meta["grade"] = str(grade).strip() if grade else None
    return meta
