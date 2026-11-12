"""Experience parsing: years of experience from structured text, title, description and seniority words.

Precedence: explicit numbers (experience_text, then title, then the earliest match in the description)
beat levels inferred from words (SDE I/II/III, Senior, LinkedIn job_level). Inferred ranges are tagged by the
caller and never cause a drop on their own; only the explicit flags (intern, fresher, staff, principal)
and explicit numbers do.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_N = r"(\d{1,2}(?:\.\d+)?)"
_DASH = r"(?:-|–|—|to)"
_YRS = r"(?:years?|yrs?)"

_RANGE = re.compile(rf"{_N}\s*\+?\s*{_DASH}\s*{_N}\s*\+?\s*{_YRS}\b", re.IGNORECASE)
_RANGE_BARE = re.compile(rf"^\s*{_N}\s*\+?\s*{_DASH}\s*{_N}\s*\+?\s*(?:{_YRS})?\s*$", re.IGNORECASE)
_PLUS = re.compile(rf"{_N}\s*\+\s*{_YRS}\b", re.IGNORECASE)
_MIN = re.compile(rf"(?:minimum|min\.?|at\s*least)\s*(?:of\s*)?{_N}\s*\+?\s*{_YRS}\b", re.IGNORECASE)
_YEARS_EXP = re.compile(
    rf"{_N}\s*{_YRS}['’]?\s*(?:of\s+)?(?:(?:relevant|hands[\s-]on|professional|industry|work|total|overall|"
    rf"software|backend|java|development)\s+){{0,3}}(?:experience|exp)\b", re.IGNORECASE)
_SINGLE = re.compile(rf"^\s*{_N}\s*(\+)?\s*(?:{_YRS})?\s*$", re.IGNORECASE)

_INTERN = re.compile(r"\bintern(?:ship)?s?\b", re.IGNORECASE)
_FRESHER = re.compile(r"\bfreshers?\b|\btrainee\b|\bgraduate engineer\b|\bcampus hire\b", re.IGNORECASE)
_STAFF = re.compile(r"(?<!technical\s)\bstaff\b", re.IGNORECASE)  # not "Member of Technical Staff"
_PRINCIPAL = re.compile(r"\b(principal|distinguished|director|vice president|vp|head of|fellow|chief)\b", re.IGNORECASE)
_SENIOR = re.compile(r"\b(senior|sr)\b\.?", re.IGNORECASE)
_JUNIOR = re.compile(r"\b(junior|jr)\b\.?", re.IGNORECASE)
_LEAD = re.compile(r"\b(lead|team lead|tech lead|technical lead)\b", re.IGNORECASE)
_ARCHITECT = re.compile(r"\barchitect\b", re.IGNORECASE)
_LEVEL = re.compile(
    r"\b(?:sde|sdet|swe|software (?:development )?engineer|software developer|developer|engineer|programmer|"
    r"analyst|member of technical staff|mts)\s*[-–]?\s*(iv|iii|ii|i|4|3|2|1)\b(?!\s*(?:\+|years?|yrs?|-\s*\d))", re.IGNORECASE)
_LEVELS = {"1": 1, "i": 1, "2": 2, "ii": 2, "3": 3, "iii": 3, "4": 4, "iv": 4}
_LEVEL_RANGE = {1: (1.0, 3.0), 2: (3.0, 5.0), 3: (5.0, 9.0), 4: (8.0, 12.0)}

_JOB_LEVEL = [  # LinkedIn style, first hit wins
    (re.compile(r"intern", re.IGNORECASE), "intern"),
    (re.compile(r"director|executive|vice president|vp\b|chief", re.IGNORECASE), "principal"),
    (re.compile(r"entry", re.IGNORECASE), (0.0, 2.0)),
    (re.compile(r"mid[\s-]*senior", re.IGNORECASE), (3.0, 8.0)),
    (re.compile(r"associate", re.IGNORECASE), (1.0, 3.0)),
    (re.compile(r"senior", re.IGNORECASE), (5.0, 9.0)),
]


@dataclass
class ExpInfo:
    exp_min: float | None = None
    exp_max: float | None = None
    flags: set[str] = field(default_factory=set)  # intern | fresher | staff | principal
    inferred: str | None = None  # why the numbers are a guess, e.g. "SDE II"; None when explicit/unknown


def _num(s: str) -> float:
    return float(s)


def _sane(lo: float, hi: float | None) -> bool:
    return 0 <= lo <= 40 and (hi is None or lo <= hi <= 40)


def parse_exp_text(text: str | None) -> tuple[float, float | None] | None:
    """Structured field like Naukri's '2-5 Yrs', '3+ Years', 'Fresher', '5 Yrs'."""
    if not text:
        return None
    if re.search(r"\bfreshers?\b", text, re.IGNORECASE):
        return 0.0, 1.0
    m = _RANGE_BARE.match(text) or _RANGE.search(text)
    if m and _sane(_num(m.group(1)), _num(m.group(2))):
        return _num(m.group(1)), _num(m.group(2))
    m = _SINGLE.match(text) or _PLUS.search(text)
    if m and _sane(_num(m.group(1)), None):
        return _num(m.group(1)), None
    return None


def parse_exp_free_text(text: str | None) -> tuple[float, float | None] | None:
    """Earliest experience statement in a title or description ('3+ years', '2 to 4 yrs', 'minimum 5 years')."""
    if not text:
        return None
    best: tuple[int, float, float | None] | None = None
    for rx, kind in ((_RANGE, "range"), (_PLUS, "min"), (_MIN, "min"), (_YEARS_EXP, "min")):
        for m in rx.finditer(text):
            lo = _num(m.group(1))
            hi = _num(m.group(2)) if kind == "range" else None
            if _sane(lo, hi) and (best is None or m.start() < best[0]):
                best = (m.start(), lo, hi)
            if _sane(lo, hi):
                break
    return (best[1], best[2]) if best else None


def _title_level(title: str) -> tuple[tuple[float, float], str] | None:
    senior = bool(_SENIOR.search(title))
    m = _LEVEL.search(title)
    level = _LEVELS[m.group(1).lower()] if m else None
    if senior and level:
        return (4.0, 7.0), f"senior level {level}"
    if level:
        return _LEVEL_RANGE[level], f"level {level}"
    if senior:
        return (5.0, 9.0), "senior"
    if _LEAD.search(title):
        return (5.0, 9.0), "lead"
    if _ARCHITECT.search(title):
        return (8.0, 15.0), "architect"
    if _JUNIOR.search(title):
        return (1.0, 3.0), "junior"
    return None


def parse_experience(
    title: str, description: str | None, experience_text: str | None, job_level: str | None
) -> ExpInfo:
    info = ExpInfo()
    if _INTERN.search(title):
        info.flags.add("intern")
    if _STAFF.search(title):
        info.flags.add("staff")
    if _PRINCIPAL.search(title):
        info.flags.add("principal")
    fresher = bool(_FRESHER.search(title)) or bool(experience_text and re.search(r"\bfreshers?\b", experience_text, re.IGNORECASE))

    explicit = parse_exp_text(experience_text) or parse_exp_free_text(title) or parse_exp_free_text(description)
    if explicit:
        info.exp_min, info.exp_max = explicit
        if fresher and info.exp_min < 1:
            info.flags.add("fresher")
        return info
    if "intern" in info.flags:
        info.exp_min, info.exp_max = 0.0, 0.0
        return info
    if fresher:
        info.flags.add("fresher")
        info.exp_min, info.exp_max = 0.0, 1.0
        return info
    if "staff" in info.flags:
        info.exp_min, info.exp_max, info.inferred = 8.0, 15.0, "staff"
        return info
    if "principal" in info.flags:
        info.exp_min, info.exp_max, info.inferred = 10.0, 20.0, "principal"
        return info
    lvl = _title_level(title)
    if lvl:
        (info.exp_min, info.exp_max), info.inferred = lvl[0], lvl[1]
        return info
    if job_level:
        for rx, val in _JOB_LEVEL:
            if rx.search(job_level):
                if val == "intern":
                    info.flags.add("intern")
                    info.exp_min, info.exp_max = 0.0, 0.0
                elif val == "principal":
                    info.flags.add("principal")
                    info.exp_min, info.exp_max, info.inferred = 10.0, 20.0, f"job level {job_level}"
                else:
                    (info.exp_min, info.exp_max), info.inferred = val, f"job level {job_level}"
                break
    return info
