"""Normalize one RawJob into the fields a Lead stores plus the signals the prefilter needs.

Pure functions, no database. `normalize(raw, settings)` -> `Normalized`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import SplitResult, parse_qsl, urlencode, urlsplit

from jobhunter.intake.types import RawJob
from jobhunter.models import ApplyChannel, RoleFamily, Source, WorkMode
from jobhunter.pipeline import ctc as ctc_mod
from jobhunter.pipeline.experience import ExpInfo, parse_experience
from jobhunter.pipeline.location import LocationInfo, canonical_city, parse_location
from jobhunter.schemas import Settings

# ---------- URLs ----------

_TRACKING = {
    "refid", "trackingid", "tracking", "trk", "trkinfo", "src", "source", "from", "ref", "referrer", "referral",
    "campaign", "lipi", "midtoken", "midsig", "ebp", "cmpid", "gclid", "fbclid", "msclkid", "_ga", "sid", "ss",
    "pos", "position", "lever-source", "lever-origin", "vjk", "advn", "tk", "sk", "xpse", "alid", "bb", "fccid",
    "utm", "clickid", "jobsource", "jb_src",
}


def split_url(url: str) -> SplitResult:
    """urlsplit that treats an unparseable URL (e.g. 'http://[' -> Invalid IPv6 URL) as empty: no host, no path."""
    try:
        return urlsplit(url if "://" in url else "https://" + url)
    except ValueError:
        return SplitResult("", "", "", "", "")


def canonical_url(url: str | None) -> str | None:
    """https, lowercase host without 'www.', tracking params and fragment dropped, params sorted.
    LinkedIn collapses to /jobs/view/<id>, Indeed to /viewjob?jk=<id>."""
    if not url or not url.strip() or url.strip().lower().startswith("mailto:"):
        return None
    url = url.strip()
    parts = split_url(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    if not host:
        return None
    query = parse_qsl(parts.query, keep_blank_values=False)
    if host.endswith("linkedin.com"):
        m = re.search(r"/jobs/view/(?:[^/?#]*-)?(\d{6,})", parts.path) or re.search(r"currentJobId=(\d{6,})", url)
        if m:
            return f"https://linkedin.com/jobs/view/{m.group(1)}"
    if "indeed." in host:
        jk = dict(query).get("jk") or dict(query).get("vjk")
        if jk:
            return f"https://{host}/viewjob?jk={jk}"
    kept = sorted((k, v) for k, v in query
                  if k.lower() not in _TRACKING and not k.lower().startswith(("utm_", "mc_")))
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/")
    out = f"https://{host}{path}"
    return out + ("?" + urlencode(kept) if kept else "")


# ---------- apply channel ----------

ATS_HOSTS = (
    "greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com", "myworkdaysite.com", "workday.com",
    "smartrecruiters.com", "darwinbox.in", "darwinbox.com", "keka.com", "kekahire.com", "zohorecruit.com",
    "zohorecruit.in", "successfactors.com", "successfactors.eu", "icims.com", "taleo.net", "oraclecloud.com",
    "jobvite.com", "breezy.hr", "workable.com", "recruitee.com", "bamboohr.com", "teamtailor.com",
    "turbohire.co", "turbohire.in", "freshteam.com", "pinpointhq.com", "applytojob.com", "rippling.com",
    "personio.de", "personio.com", "eightfold.ai", "phenompeople.com", "avature.net", "hirecentric.com",
)
_QUICK_ALERTS = {"instahyre"}  # alert senders whose apply is a platform 1-click


def _host(url: str | None) -> str:
    if not url or not url.strip():
        return ""
    url = url.strip()
    return (split_url(url).hostname or "").lower()


def is_ats_url(url: str | None) -> bool:
    h = _host(url)
    return bool(h) and any(h == d or h.endswith("." + d) for d in ATS_HOSTS)


def apply_channel(raw: RawJob) -> ApplyChannel:
    if raw.easy_apply:
        return ApplyChannel.platform_quick
    if raw.source == Source.gmail_alert and (raw.source_detail or "").lower() in _QUICK_ALERTS:
        return ApplyChannel.platform_quick
    if any((u or "").strip().lower().startswith("mailto:") for u in (raw.apply_url, raw.job_url)):
        return ApplyChannel.email
    if raw.source == Source.gmail_inbound:
        return ApplyChannel.email
    if is_ats_url(raw.apply_url) or is_ats_url(raw.job_url):
        return ApplyChannel.company_ats
    return ApplyChannel.unknown


# ---------- work mode / remote scope ----------

_DESC_HYBRID = re.compile(r"\bhybrid\b(?!\s+(?:cloud|app|apps|mobile|search|ai|database|data|multi|infra))", re.IGNORECASE)
_DESC_REMOTE = re.compile(
    r"fully remote|100% remote|remote[\s-]first|work from home|work from anywhere|\bwfh\b|remote (?:position|role|"
    r"opportunity|job)|this is a remote|(?:location|work ?(?:mode|type|model)|mode of work)\s*[:\-]\s*remote",
    re.IGNORECASE)
_DESC_ONSITE = re.compile(r"work from office|\bwfo\b|\bon[\s-]?site\b|in[\s-]office|office[\s-]based|"
                          r"(?:work ?(?:mode|type|model)|mode of work)\s*[:\-]\s*(?:office|onsite)", re.IGNORECASE)

_US_ONLY = re.compile(
    r"\b(?:us|u\.s\.a?\.?|usa|united states)[\s-]*(?:only|based|residents?|citizens?)\b"
    r"|(?:must|should|need to)\s+(?:be\s+)?(?:located|based|residing|living)\s+in\s+(?:the\s+)?(?:us|u\.s\.|usa|united states)\b"
    r"|(?:authorized|authorised|eligible|legally entitled)\s+to\s+work\s+in\s+(?:the\s+)?(?:us|u\.s\.|usa|united states)\b"
    r"|remote\s*[\(\-–,:/]\s*(?:us|usa|u\.s\.|united states)\b|\b(?:us|usa)[\s-]remote\b"
    r"|within\s+the\s+(?:us|u\.s\.|united states)\b|\b(?:est|pst|cst)\s+(?:time\s*zone|hours)\b", re.IGNORECASE)
_EU_ONLY = re.compile(
    r"\b(?:eu|europe|european|emea|uk)[\s-]*(?:only|based|residents?|citizens?)\b"
    r"|(?:must|should|need to)\s+(?:be\s+)?(?:located|based|residing|living)\s+in\s+(?:the\s+)?(?:eu|europe|uk|united kingdom|emea)\b"
    r"|remote\s*[\(\-–,:/]\s*(?:eu|europe|emea|uk|united kingdom)\b|right to work in the (?:uk|eu)\b|\bcet\s+time\s*zone\b",
    re.IGNORECASE)
_INDIA_TEXT = re.compile(r"\bindia\b|\bpan[\s-]india\b|\bist\b", re.IGNORECASE)
_APAC_TEXT = re.compile(r"\b(?:apac|asia[\s-]pacific)\b", re.IGNORECASE)
_WORLD_TEXT = re.compile(r"\bworldwide\b|\bwork from anywhere\b|\bglobally\b|\bfully distributed\b", re.IGNORECASE)


def work_mode_of(raw: RawJob, loc: LocationInfo) -> WorkMode:
    desc = raw.description or ""
    if loc.hybrid or _HYBRID_IN.search(raw.title):
        return WorkMode.hybrid
    if raw.is_remote or loc.remote or _REMOTE_IN.search(raw.title):
        return WorkMode.remote
    if _DESC_HYBRID.search(desc):
        return WorkMode.hybrid
    if _DESC_REMOTE.search(desc):
        return WorkMode.remote
    if loc.onsite or _DESC_ONSITE.search(desc) or _ONSITE_IN.search(raw.title):
        return WorkMode.onsite
    return WorkMode.unknown


_HYBRID_IN = re.compile(r"\bhybrid\b", re.IGNORECASE)
_REMOTE_IN = re.compile(r"\bremote\b|\bwork from home\b|\bwfh\b", re.IGNORECASE)
_ONSITE_IN = re.compile(r"\bon[\s-]?site\b|\bwork from office\b", re.IGNORECASE)


def remote_scope(raw: RawJob, loc: LocationInfo) -> str | None:
    """india | apac | worldwide | us_only | eu_only | other_only | None (unknown). Location text is
    authoritative; title and description are searched for restrictions only when it is silent."""
    if loc.region == "india":
        return "india"
    if loc.region == "apac":
        return "apac"
    if loc.region in ("us", "eu", "other"):
        return {"us": "us_only", "eu": "eu_only", "other": "other_only"}[loc.region]
    if loc.region == "worldwide":
        text = f"{raw.title}\n{raw.description or ''}"
        return "us_only" if _US_ONLY.search(text) else "eu_only" if _EU_ONLY.search(text) else "worldwide"
    text = f"{raw.title}\n{raw.description or ''}"
    if _INDIA_TEXT.search(text):
        return "india"
    if _APAC_TEXT.search(text):
        return "apac"
    if _US_ONLY.search(text):
        return "us_only"
    if _EU_ONLY.search(text):
        return "eu_only"
    if _WORLD_TEXT.search(text):
        return "worldwide"
    return None


# ---------- role family ----------

_P1_TITLE = re.compile(r"\bjava\b|\bspring\b|\bquarkus\b|\bjvm\b|\bj2ee\b|back[\s-]?end|\bmicroservices?\b", re.IGNORECASE)
_P2_TITLE = re.compile(
    r"\bplatform\b|\bidentity\b|\biam\b|\bciam\b|\bkeycloak\b|\boauth\b|\boidc\b|security engineer|\bdevsecops\b|"
    r"application security|\bappsec\b|\bauth(?:entication|orization)?\b|\bllm\b|\bgenai\b|gen ai", re.IGNORECASE)
_AI = re.compile(r"\bai\b|\bllm\b|\bgenai\b|gen ai|machine learning|\bml\b", re.IGNORECASE)
_GENERIC_SDE = re.compile(
    r"\bsde\b|software (?:development )?engineer|software developer|application developer|"
    r"member of technical staff|\bmts\b|\bswe\b|full[\s-]?stack|programmer", re.IGNORECASE)
_NON_BACKEND_TITLE = re.compile(
    r"front[\s-]?end|\bui\b|\bux\b|\bios\b|android|flutter|react native|\bqa\b|\bsdet\b|quality assurance|"
    r"test engineer|\btester\b|data scientist|data analyst|\bsales\b|support engineer", re.IGNORECASE)
_JAVA_SIGNAL = re.compile(r"\bjava\b|spring|\bquarkus\b|\bjvm\b|j2ee|hibernate|back[\s-]?end", re.IGNORECASE)
_P2_SIGNAL = re.compile(r"\bkeycloak\b|\biam\b|\bciam\b|\boidc\b|\boauth\b|identity", re.IGNORECASE)


def role_family(title: str, skills: list[str], description: str | None) -> RoleFamily:
    t = title or ""
    if _NON_BACKEND_TITLE.search(t) and not re.search(r"\bjava\b|\bspring\b|back[\s-]?end|full[\s-]?stack", t, re.IGNORECASE):
        return RoleFamily.other
    if re.search(r"back[\s-]?end", t, re.IGNORECASE) and _AI.search(t):
        return RoleFamily.p2
    if re.search(r"\bkeycloak\b", t, re.IGNORECASE):
        return RoleFamily.p2
    if _P1_TITLE.search(t):
        return RoleFamily.p1
    if _P2_TITLE.search(t):
        return RoleFamily.p2
    if _GENERIC_SDE.search(t):
        blob = " ".join(skills) + " " + (description or "")[:2000]
        if _JAVA_SIGNAL.search(blob):
            return RoleFamily.p1
        if _P2_SIGNAL.search(blob):
            return RoleFamily.p2
    return RoleFamily.other


# ---------- orchestration ----------


@dataclass
class Normalized:
    company: str
    title: str
    skills: list[str]
    description: str | None
    loc: LocationInfo
    location: str | None  # what Lead.location stores: canonical city, "India" for pan-India, else as given
    work_mode: WorkMode
    remote_scope: str | None
    exp: ExpInfo
    ctc_min: float | None
    ctc_max: float | None
    role_family: RoleFamily
    apply_channel: ApplyChannel
    canonical_url: str | None
    apply_url: str | None
    posted_at: datetime | None
    extra_tags: list[str] = field(default_factory=list)


def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; models.py says to treat naive as UTC."""
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _clean(s: str | None) -> str:
    return " ".join((s or "").split())


def target_cities(settings: Settings) -> frozenset[str]:
    return frozenset(canonical_city(c) for c in settings.prefilter.cities)


def normalize(raw: RawJob, settings: Settings) -> Normalized:
    loc = parse_location(raw.location, target_cities(settings))
    mode = work_mode_of(raw, loc)
    if loc.city:
        location = loc.city
    elif loc.pan_india and not loc.remote:
        location = "India"
    else:
        location = _clean(raw.location) or ("Remote" if mode == WorkMode.remote else None)

    exp = parse_experience(raw.title, raw.description, raw.experience_text, raw.job_level)

    usd_inr = settings.prefilter.usd_inr
    lo, hi = ctc_mod.from_structured(raw.salary_min, raw.salary_max, raw.salary_interval, raw.currency, usd_inr)
    if lo is None and hi is None:
        lo, hi = ctc_mod.parse_text(raw.salary_text, usd_inr, strict=False)
    if lo is None and hi is None:
        lo, hi = ctc_mod.parse_text(raw.description, usd_inr, strict=True)

    canon = canonical_url(raw.job_url) or canonical_url(raw.apply_url)
    return Normalized(
        company=_clean(raw.company),
        title=_clean(raw.title),
        skills=[_clean(s) for s in raw.skills if s and s.strip()],
        description=raw.description,
        loc=loc,
        location=location,
        work_mode=mode,
        remote_scope=remote_scope(raw, loc) if mode == WorkMode.remote else None,
        exp=exp,
        ctc_min=lo,
        ctc_max=hi,
        role_family=role_family(raw.title, raw.skills, raw.description),
        apply_channel=apply_channel(raw),
        canonical_url=canon,
        apply_url=(raw.apply_url or "").strip() or None,
        posted_at=as_utc(raw.posted_at),
    )
