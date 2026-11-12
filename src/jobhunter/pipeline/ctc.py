"""CTC parsing, always returned in LPA (lakh INR per annum).

Structured salary: INR yearly / 1e5, monthly x 12, weekly x 52, USD at `usd_inr`. Hourly and daily rates are
ignored (not clear enough). Two sanity repairs because boards mislabel intervals: an INR "yearly" value
under 1.5 lakh is really monthly; an INR "monthly" value over 10 lakh is really yearly. Yearly INR values under
1000 are already LPA.

Free text ("10-15 LPA", "₹12,00,000 - ₹18,00,000", "$120k - $150k", "50,000 - 80,000 per month"): LPA/lakh
phrases are trusted anywhere; rupee, dollar and crore amounts in a description need a salary word nearby
(ctc, salary, compensation, package, ...) so "raised $50M" or "₹500 Cr revenue" are not read as pay.
"""

from __future__ import annotations

import re

_NUM = r"(\d[\d,]*+(?:\.\d+)?+)"  # possessive: no backtracking into a shorter number
_DASH = r"(?:-|–|—|to)"
_CUR = r"(?:₹|rs\.?|inr)"

_LPA = re.compile(
    rf"(?:(?:{_CUR})\s*)?{_NUM}\s*(?:{_DASH}\s*(?:{_CUR}\s*)?{_NUM}\s*)?"
    r"(?:lpa|l\.p\.a\.?|lacs?|lakhs?|lakh|lac)\b(\s*\+)?", re.IGNORECASE)
_LPA_SHORT = re.compile(rf"₹\s*{_NUM}\s*l\b(?:\s*{_DASH}\s*₹?\s*{_NUM}\s*l\b)?", re.IGNORECASE)
_CRORE = re.compile(rf"{_NUM}\s*(?:{_DASH}\s*{_NUM}\s*)?(?:cr|crores?)\b", re.IGNORECASE)
_RUPEES = re.compile(
    rf"{_CUR}\s*{_NUM}\s*(k)?\s*(?:{_DASH}\s*(?:{_CUR}\s*)?{_NUM}\s*(k)?)?(?!\s*(?:cr|crores?|m|mn|million|b|bn|billion)\b)",
    re.IGNORECASE)
_USD = re.compile(
    rf"(?:\$|usd\s*){_NUM}\s*(k)?\s*(?:{_DASH}\s*(?:\$|usd\s*)?{_NUM}\s*(k)?)?(?!\s*(?:m|mn|million|b|bn|billion)\b)",
    re.IGNORECASE)
_INTERVAL = re.compile(
    r"(?:per|a|/|\bp\.?)\s*(month|mo|year|yr|annum|hour|hr|day|week)\b|\b(monthly|annual(?:ly)?|yearly|hourly|daily)\b|"
    r"\bp\.?a\.?\b|\bp\.?m\.?\b", re.IGNORECASE)
_CONTEXT = re.compile(r"ctc|salary|compensation|package|remuneration|\bpay\b|stipend|budget|offer|\blpa\b", re.IGNORECASE)
_UPTO = re.compile(r"(?:up\s*to|upto|max(?:imum)?|not exceeding|till)\s*[:\-]?\s*$", re.IGNORECASE)
_FROM = re.compile(r"(?:from|starting|minimum|min\.?|above|at least|starts? at)\s*[:\-]?\s*$", re.IGNORECASE)

Range = tuple[float | None, float | None]


def _f(s: str) -> float:
    return float(s.replace(",", ""))


def _round(v: float | None) -> float | None:
    return None if v is None else round(v, 2)


def _interval(text: str) -> str | None:
    m = _INTERVAL.search(text)
    if not m:
        return None
    word = (m.group(1) or m.group(2) or m.group(0)).lower().replace(".", "")
    for key, val in (("month", "monthly"), ("mo", "monthly"), ("pm", "monthly"), ("year", "yearly"),
                     ("yr", "yearly"), ("annum", "yearly"), ("annual", "yearly"), ("pa", "yearly"),
                     ("hour", "hourly"), ("hr", "hourly"), ("day", "daily"), ("daily", "daily"),
                     ("week", "weekly")):
        if word.startswith(key):
            return val
    return None


def _to_lpa(value: float, currency: str, interval: str | None, usd_inr: float) -> float | None:
    cur = (currency or "INR").upper()
    if cur == "INR":
        if interval in ("hourly", "daily"):
            return None
        if interval == "weekly":
            value *= 52
        elif interval == "monthly":
            value = value * 12 if value <= 1_000_000 else value
        elif value < 1000:
            return value  # already LPA
        elif value < 150_000:
            value *= 12  # mislabelled yearly: really monthly
        return value / 1e5
    if cur == "USD":
        if interval in ("hourly", "daily"):
            return None
        if interval == "monthly":
            value *= 12
        elif interval == "weekly":
            value *= 52
        return value * usd_inr / 1e5
    return None  # other currencies: unknown rate, treat CTC as unknown


def from_structured(
    lo: float | None, hi: float | None, interval: str | None, currency: str | None, usd_inr: float
) -> Range:
    vals = [None if v is None else _to_lpa(v, currency or "INR", (interval or "yearly").lower(), usd_inr)
            for v in (lo, hi)]
    if all(v is None for v in vals):
        return None, None
    return _round(vals[0]), _round(vals[1] if vals[1] is not None else vals[0])


def _single_or_range(a: float, b: float | None, before: str, after: str = "") -> Range:
    if b is not None:
        return min(a, b), max(a, b)
    if _UPTO.search(before):
        return None, a
    if _FROM.search(before) or after.lstrip().startswith("+"):
        return a, None
    return a, a


def parse_text(text: str | None, usd_inr: float, *, strict: bool) -> Range:
    """`strict` (descriptions): only trust amounts that carry salary context or an explicit LPA unit."""
    if not text:
        return None, None
    for m in _LPA.finditer(text):
        a = _f(m.group(1))
        b = _f(m.group(2)) if m.group(2) else None
        if max(a, b or 0) > 500:
            continue
        return tuple(_round(v) for v in _single_or_range(a, b, text[: m.start()][-20:], m.group(3) or ""))  # type: ignore[return-value]
    for rx, mult in ((_LPA_SHORT, 1.0), (_CRORE, 100.0)):
        for m in rx.finditer(text):
            ctx = text[max(0, m.start() - 80): m.end() + 80]
            if (strict or mult != 1.0) and not _CONTEXT.search(ctx):
                continue
            a, b = _f(m.group(1)) * mult, (_f(m.group(2)) * mult if m.group(2) else None)
            if max(a, b or 0) <= 500:
                return tuple(_round(v) for v in _single_or_range(a, b, text[: m.start()][-20:]))  # type: ignore[return-value]
    for rx, cur in ((_RUPEES, "INR"), (_USD, "USD")):
        for m in rx.finditer(text):
            ctx = text[max(0, m.start() - 80): m.end() + 80]
            if strict and not _CONTEXT.search(ctx):
                continue
            a_raw, a_k, b_raw, b_k = m.group(1), m.group(2), m.group(3), m.group(4)
            a, b = _f(a_raw), (_f(b_raw) if b_raw else None)
            if a_k or b_k:  # "120k - 150k", "50 - 80k"
                a, b = a * 1000, (b * 1000 if b is not None else None)
            interval = _interval(text[m.end(): m.end() + 25]) or ("monthly" if cur == "INR" and max(a, b or 0) < 100_000
                                                                  and not a_k else None)
            vals = [_to_lpa(v, cur, interval or "yearly", usd_inr) if v is not None else None for v in (a, b)]
            if vals[0] is None:
                continue
            lo, hi = _single_or_range(vals[0], vals[1], text[: m.start()][-20:])
            return _round(lo), _round(hi)
    return None, None
