"""Dedupe: group postings of the same job. Precision first (target >= 99%), recall second.

Two postings are the same job when either
  1. they share a URL key: the canonical job URL, or a canonical apply URL that points at one specific
     company-ATS posting (a bare `boards.greenhouse.io/acme` listing page does not count), or
  2. company, title and place all agree under strict fuzzy rules:
       - company keys (legal and generic suffixes stripped) score >= 93 (RapidFuzz ratio),
       - title keys (level words/numbers, seniority words and years of experience normalised) score >= 92
         (token_sort_ratio) AND the level numbers (SDE 1 vs 2) and seniority words (senior, lead, ...) are
         identical,
       - places are compatible: same city, or a city and a state-level posting in that city's state
         ("Chennai" vs "TN, India"), or both remote, or both pan-India. Unknown places never match.

The group id is `d<id of the first lead in the group>`; the lowest lead id is the primary.
`DedupeIndex` holds light rows for every stored lead so a batch is matched without per-row queries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl

from rapidfuzz import fuzz, process
from sqlmodel import Session, select

from jobhunter.models import Lead, WorkMode
from jobhunter.pipeline.location import CITY_STATE, LocationInfo, parse_location
from jobhunter.pipeline.normalize import Normalized, canonical_url, is_ats_url, split_url

COMPANY_CUTOFF = 93
TITLE_CUTOFF = 92

_LEGAL = {"pvt", "private", "ltd", "limited", "inc", "incorporated", "llc", "llp", "corp", "corporation", "co",
          "gmbh", "plc", "pte", "company", "the"}
_GENERIC = {"technologies", "technology", "tech", "software", "softwares", "solutions", "systems", "services",
            "india", "global", "labs", "group", "digital", "infotech", "infosystems"}
_ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5"}
_LEVEL_WORDS = {"senior", "junior", "lead", "staff", "principal", "associate", "intern", "trainee", "architect",
                "manager", "head", "director"}
_TITLE_NOISE = re.compile(
    r"\(.*?\)|\[.*?\]|\b(?:remote|hybrid|onsite|on-site|wfh|work from home|urgent|urgently|hiring|opening|"
    r"openings|immediate|joiners?|walk[\s-]?in|full[\s-]?time|india|chennai|bengaluru|bangalore|hyderabad|pune|"
    r"mumbai|delhi|gurgaon|gurugram|noida|kolkata)\b|\d+(?:\.\d+)?\s*\+?\s*(?:-|to)?\s*\d*\s*(?:years?|yrs?)\b",
    re.IGNORECASE)


def company_keys(name: str) -> tuple[str, str]:
    """(core, full): full = legal suffixes stripped; core = generic words (technologies, india, ...) stripped too."""
    tokens = re.sub(r"[^a-z0-9]+", " ", name.lower()).split()
    tokens = [t for t in tokens if t not in _LEGAL] or tokens
    return " ".join([t for t in tokens if t not in _GENERIC] or tokens), " ".join(tokens)


def same_company(a_full: str, b_full: str) -> bool:
    """Candidates share a core key; this keeps them apart unless one name is a word-subset of the other
    ("Corvus Pay" / "Corvus Pay Technologies") or they are near-identical spellings. "Nimbus Labs" and
    "Nimbus Systems Group" are different companies."""
    a, b = set(a_full.split()), set(b_full.split())
    return a <= b or b <= a or fuzz.ratio(a_full, b_full) >= COMPANY_CUTOFF


def title_key(title: str) -> tuple[str, frozenset[str], frozenset[str]]:
    """(normalised title, level numbers, seniority words)."""
    t = _TITLE_NOISE.sub(" ", title.lower())
    t = re.sub(r"\bsr\b\.?", "senior", t)
    t = re.sub(r"\bjr\b\.?", "junior", t)
    tokens = [_ROMAN.get(tok, tok) for tok in re.sub(r"[^a-z0-9+#]+", " ", t).split() if tok not in {"at", "the", "a", "an"}]
    return " ".join(tokens), frozenset(tok for tok in tokens if tok.isdigit()), frozenset(tok for tok in tokens if tok in _LEVEL_WORDS)


def geo_key(loc: LocationInfo, work_mode: WorkMode) -> tuple[str, str] | None:
    if loc.city:
        return ("city", loc.city)
    if work_mode == WorkMode.remote:
        return ("remote", "")
    if loc.state:
        return ("state", loc.state)
    if loc.pan_india:
        return ("india", "")
    return None


def geo_compatible(a: tuple[str, str] | None, b: tuple[str, str] | None) -> bool:
    if a is None or b is None:
        return False
    if a == b:
        return True
    for x, y in ((a, b), (b, a)):
        if x[0] == "city" and y[0] == "state" and CITY_STATE.get(x[1]) == y[1]:
            return True
    return False


def url_keys(canon: str | None, apply_url: str | None) -> set[str]:
    """URLs that identify one posting. Listing pages (a bare company ATS board, a site root) are skipped:
    they are shared by many jobs."""
    keys = set()
    for url in (canon, apply_url if is_ats_url(apply_url) else None):
        c = canonical_url(url)
        if c and _identifies_posting(c):
            keys.add(c)
    return keys


def _identifies_posting(url: str) -> bool:
    p = split_url(url)
    if is_ats_url(url):
        return _specific(url)
    return bool(p.path.strip("/") or p.query)


def _specific(url: str) -> bool:
    """True when an ATS URL points at one posting, not a company's listing page."""
    p = split_url(url)
    if any(k.lower() in {"gh_jid", "jobid", "job_id", "jid", "id", "reqid", "requisitionid"} for k, _ in parse_qsl(p.query)):
        return True
    segs = [s for s in p.path.split("/") if s]
    return len(segs) >= 2 and any(ch.isdigit() for ch in segs[-1])


@dataclass
class Row:
    id: int
    group: str | None
    company: str  # core key
    company_full: str
    title: str
    nums: frozenset[str]  # level numbers in the title
    levels: frozenset[str]
    geo: tuple[str, str] | None
    urls: set[str]


def _row(id_: int, group: str | None, company: str, title: str, geo, urls: set[str]) -> Row:
    tkey, nums, levels = title_key(title)
    core, full = company_keys(company)
    return Row(id_, group, core, full, tkey, nums, levels, geo, urls)


class DedupeIndex:
    def __init__(self, session: Session | None = None):
        self._by_id: dict[int, Row] = {}
        self._by_company: dict[str, list[Row]] = {}
        self._by_url: dict[str, list[Row]] = {}
        if session is not None:
            cols = select(Lead.id, Lead.dedupe_group, Lead.company, Lead.title, Lead.location, Lead.work_mode,
                          Lead.canonical_url, Lead.apply_url)
            for id_, group, company, title, location, mode, canon, apply_url in session.exec(cols):
                self._put(_row(id_, group, company, title, geo_key(parse_location(location), mode),
                               url_keys(canon, apply_url)))

    def _put(self, row: Row) -> None:
        old = self._by_id.get(row.id)
        if old:
            self._by_company[old.company].remove(old)
            for u in old.urls:
                self._by_url[u].remove(old)
        self._by_id[row.id] = row
        self._by_company.setdefault(row.company, []).append(row)
        for u in row.urls:
            self._by_url.setdefault(u, []).append(row)

    def add(self, lead: Lead, norm: Normalized) -> None:
        """(Re)register a stored lead (after insert or update)."""
        self._put(_row(lead.id, lead.dedupe_group, lead.company, lead.title, geo_key(norm.loc, norm.work_mode),
                       url_keys(lead.canonical_url, lead.apply_url)))

    def find(self, norm: Normalized, *, exclude_id: int | None = None) -> Row | None:
        """Lowest-id stored lead that is the same job as `norm`, or None."""
        hits: dict[int, Row] = {}
        for u in url_keys(norm.canonical_url, norm.apply_url):
            for row in self._by_url.get(u, []):
                hits[row.id] = row
        tkey, nums, levels = title_key(norm.title)
        geo = geo_key(norm.loc, norm.work_mode)
        ckey, cfull = company_keys(norm.company)
        if ckey and tkey and geo is not None:
            if ckey in self._by_company:
                keys = [ckey]
            else:
                keys = [k for k, _, _ in process.extract(ckey, self._by_company.keys(), scorer=fuzz.ratio,
                                                          score_cutoff=COMPANY_CUTOFF, limit=None)]
            for k in keys:
                for row in self._by_company[k]:
                    if (same_company(row.company_full, cfull) and row.nums == nums and row.levels == levels and geo_compatible(row.geo, geo)
                            and fuzz.token_sort_ratio(row.title, tkey) >= TITLE_CUTOFF):
                        hits[row.id] = row
        hits.pop(exclude_id, None)
        return hits[min(hits)] if hits else None
