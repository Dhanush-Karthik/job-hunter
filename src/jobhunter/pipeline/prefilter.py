"""India prefilter (plan section 4, recall first). Numbers come from `settings.prefilter`.

Drops need a stated, clear reason; unknowns pass and get a tag. Every drop reason is a short string such as
"location: Pune", "experience: min 8 >= 6", "ctc: max 6.0 LPA < 10", "stack: frontend only", "stale: 41 days".
Nothing is deleted here: the caller stores `passed=False` rows and the owner can restore them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from jobhunter.models import WorkMode
from jobhunter.pipeline.location import CITY_STATE
from jobhunter.pipeline.normalize import Normalized, as_utc, target_cities
from jobhunter.schemas import Settings

_REMOTE_DROP_REASON = {
    "us_only": "remote US-only",
    "eu_only": "remote EU/UK-only",
    "other_only": "remote outside India",
}
# settings stack_negative term -> title regex. Terms not listed match literally.
_NEG_PATTERNS = {
    "frontend only": r"front[\s-]?end|\bui\s+(?:developer|engineer)",
    "react developer": r"\breact(?:\.?js)?\s+(?:developer|engineer)",
    "angular developer": r"\bangular(?:\.?js)?\s+(?:developer|engineer)",
    "qa only": r"\bqa\b|quality assurance|\bsdet\b|\btest(?:ing)?\s+engineer|\btester\b",
    "manual testing": r"manual test",
    "sales": r"\bsales\b",
    "business development": r"business development|\bbdm?\b",
    "data entry": r"data entry",
    "sap abap": r"\bsap\b",
    "ios": r"\bios\b",
    "android": r"\bandroid\b",
    "php": r"\bphp\b",
    "wordpress": r"\bwordpress\b",
    "flutter": r"\bflutter\b",
}
_FULL_STACK = re.compile(r"full[\s-]?stack", re.IGNORECASE)


@dataclass
class PrefilterResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def _fmt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def _term_re(term: str) -> re.Pattern[str]:
    pat = _NEG_PATTERNS.get(term.lower())
    if pat is None:
        pat = r"(?<![\w])" + r"[\s-]*".join(re.escape(w) for w in term.lower().split()) + r"(?![\w])"
    return re.compile(pat, re.IGNORECASE)


def positive_terms(text: str, terms: list[str]) -> list[str]:
    low = text.lower()
    return [t for t in terms if re.search(r"(?<![\w+#])" + r"[\s-]*".join(re.escape(w) for w in t.lower().split())
                                          + r"(?![\w+#])", low)]


def _location(n: Normalized, settings: Settings, targets: frozenset[str], tags: list[str], reasons: list[str]) -> None:
    loc = n.loc
    pf = settings.prefilter
    if n.work_mode == WorkMode.remote:
        if not pf.remote_ok and not loc.city:
            reasons.append("location: remote")
            return
        if n.remote_scope in _REMOTE_DROP_REASON:
            reasons.append(f"location: {_REMOTE_DROP_REASON[n.remote_scope]}")
        elif n.remote_scope is None:
            tags.append("remote scope unknown")
        return
    if loc.city:
        if loc.city not in targets:
            reasons.append(f"location: {loc.city}")
        return
    if loc.foreign:
        reasons.append(f"location: {loc.foreign}")
        return
    if loc.pan_india:
        tags.append("pan-India")
        return
    if loc.state:
        if loc.state in {CITY_STATE[c] for c in targets if c in CITY_STATE}:
            tags.append(f"city unknown: {loc.state}")
        else:
            reasons.append(f"location: {loc.state}")
        return
    tags.append(f"city unknown: {loc.raw}" if loc.raw else "city unknown")


def _experience(n: Normalized, settings: Settings, tags: list[str], reasons: list[str]) -> None:
    e = n.exp
    lo_ok, _hi_ok = settings.prefilter.exp_years
    drop_min = settings.prefilter.exp_drop_min_at_least
    if "intern" in e.flags:
        reasons.append("experience: intern")
        return
    if "staff" in e.flags:
        reasons.append("experience: staff level")
        return
    if "principal" in e.flags:
        reasons.append("experience: principal level")
        return
    if "fresher" in e.flags:
        reasons.append("experience: fresher")
        return
    if e.exp_min is None and e.exp_max is None:
        tags.append("exp unknown")
        return
    if e.inferred:
        tags.append(f"exp inferred: {e.inferred}")
        return
    if e.exp_min is not None and e.exp_min >= drop_min:
        reasons.append(f"experience: min {_fmt(e.exp_min)} >= {_fmt(drop_min)}")
    elif e.exp_max is not None and e.exp_max < lo_ok:
        reasons.append(f"experience: max {_fmt(e.exp_max)} < {_fmt(lo_ok)}")


def _ctc(n: Normalized, settings: Settings, tags: list[str], reasons: list[str]) -> None:
    floor = settings.prefilter.ctc_min_lpa
    if n.ctc_max is None:
        tags.append("CTC unknown")
    elif n.ctc_max < floor:
        reasons.append(f"ctc: max {n.ctc_max:.1f} LPA < {_fmt(floor)}")


_MOBILE = {"ios", "android", "flutter"}
_WEAK_FOR_MOBILE = {"kotlin", "jvm"}  # Android developers list Kotlin; that is no backend signal


def _stack(n: Normalized, settings: Settings, tags: list[str], reasons: list[str]) -> None:
    pf = settings.prefilter
    head = " ".join([n.title, *n.skills])
    pos_head = positive_terms(head, pf.stack_positive)
    if not _FULL_STACK.search(n.title):
        for term in pf.stack_negative:
            if not _term_re(term).search(head):
                continue
            pos = [p for p in pos_head if term.lower() not in _MOBILE or p.lower() not in _WEAK_FOR_MOBILE]
            if not pos:
                reasons.append(f"stack: {term}")
                return
    if not pos_head and not positive_terms(n.description or "", pf.stack_positive):
        tags.append("stack unclear")


def _freshness(n: Normalized, settings: Settings, now: datetime, tags: list[str], reasons: list[str]) -> None:
    pf = settings.prefilter
    if n.posted_at is None:
        tags.append("posted date unknown")
        return
    age = max(0, (as_utc(now) - n.posted_at).days)
    if age > pf.max_age_days_drop:
        reasons.append(f"stale: {age} days")
    elif age > pf.max_age_days_pass:
        tags.append(f"aging: {age} days")


def prefilter(n: Normalized, settings: Settings, now: datetime) -> PrefilterResult:
    reasons: list[str] = []
    tags: list[str] = []
    targets = target_cities(settings)
    _location(n, settings, targets, tags, reasons)
    _experience(n, settings, tags, reasons)
    _ctc(n, settings, tags, reasons)
    _stack(n, settings, tags, reasons)
    _freshness(n, settings, now, tags, reasons)
    return PrefilterResult(passed=not reasons, reasons=reasons, tags=tags)

