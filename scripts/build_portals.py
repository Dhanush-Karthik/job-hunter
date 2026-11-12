#!/usr/bin/env python3
"""Discover and verify public ATS boards, then build career-ops portals.

The default build uses bounded, cached public requests. --dry-run is offline;
--refresh ignores cached probes. No applications or authenticated requests.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, quote, urljoin, urlparse

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "career-ops"
USER_AGENT = "job-hunter-portal-resolver/1.0 (public careers discovery; no applications)"
TITLE_FILTER = {
    "positive": ["Java", "Backend", "Back-end", "Spring", "Software Engineer", "SDE",
                 "Platform Engineer", "Microservices", "Identity", "Keycloak"],
    "negative": [],
}
REMOTE_BOARDS = [
    {"name": "Himalayas", "provider": "himalayas", "careers_url": "https://himalayas.app/jobs", "enabled": True},
    {"name": "RemoteOK", "provider": "remoteok", "careers_url": "https://remoteok.com/", "enabled": True},
    {"name": "Remotive", "provider": "remotive", "careers_url": "https://remotive.com/remote-jobs", "enabled": True},
    {"name": "We Work Remotely", "provider": "weworkremotely",
     "careers_url": "https://weworkremotely.com/", "enabled": True},
]
FAMILIES = {
    "greenhouse": ("greenhouse.io",), "lever": ("lever.co",), "ashby": ("ashbyhq.com",),
    "workable": ("workable.com",), "smartrecruiters": ("smartrecruiters.com",),
    "recruitee": ("recruitee.com",), "workday": ("myworkdayjobs.com", "myworkdaysite.com"),
    "darwinbox": ("darwinbox.in", "darwinbox.com"), "keka": ("keka.com",),
    "zoho-recruit": tuple("zohorecruit." + t for t in ("com", "in", "eu", "ca", "com.au", "jp", "sa", "com.cn")),
    "turbohire": ("turbohire.co",), "freshteam": ("freshteam.com",),
    "successfactors": ("successfactors.com", "successfactors.eu", "jobs2web.com"),
}
IDENTITY_PROVIDERS = {"greenhouse", "lever", "ashby", "workable", "smartrecruiters", "recruitee"}
GENERIC_SLUGS = {"talent", "careers", "career", "jobs", "job", "hiring", "team", "apply", "work", "join",
                 "boards", "board", "recruiting", "recruitment", "people", "opportunities", "www", "j"}
# Brand changes and product/legal names, never inferred from a guessed board token.
ALIASES = {
    "abnormalai": ["Abnormal Security", "Abnormal"], "messagebird": ["Bird"],
    "airflowastronomer": ["Astronomer"], "sentinelone": ["Sentinel Labs"],
    "vmwarebybroadcom": ["Broadcom"], "freshworks": ["Freshworks Inc."],
    "bosch": ["Bosch Group"], "rubrik": ["Rubrik Job Board"],
    "yugabyte": ["YugabyteDB"], "zoominfo": ["ZoomInfo Technologies"],
    "razorpay": ["Razorpay Software"],
}


def identity_name(value: str) -> str:
    suffixes = ("incorporated", "corporation", "limited", "private", "inc", "ltd", "llc", "plc", "corp", "pvt")
    words = re.findall(r"[a-z0-9]+", html.unescape(value).casefold())
    while len(words) > 1 and words[-1] in suffixes:
        words.pop()
    value = "".join(words)
    while suffix := next((s for s in suffixes if value.endswith(s) and len(value) - len(s) >= 4), None):
        value = value[:-len(suffix)]
    return value


def company_identities(company: dict) -> set[str]:
    return {identity_name(n) for n in [company["name"], *company.get("aliases", []),
                                      *ALIASES.get(identity_name(company["name"]), [])]}


def names_match(company: dict, name: str) -> bool:
    return bool(name) and identity_name(name) in company_identities(company)


def identity_signals(provider: str, payload) -> list[dict]:
    """Keep evidence returned by the API, never the URL we guessed ourselves."""
    signals = []

    def walk(value, depth=0):
        if depth > 5:
            return
        if isinstance(value, list):
            for row in value[:30]:
                walk(row, depth + 1)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key in {"company", "organization", "organisation", "employer", "account",
                           "companyName", "organizationName", "company_name"}:
                    name = item.get("name") if isinstance(item, dict) else item
                    if isinstance(name, str):
                        signals.append({"kind": "company_name", "value": name})
                elif key == "name" and depth == 0 and provider == "workable" and isinstance(item, str):
                    signals.append({"kind": "company_name", "value": item})
                if key in {"hostedUrl", "applyUrl", "jobUrl", "careers_url", "url", "shortlink", "applicationUrl"}:
                    if isinstance(item, str) and item.startswith("https://"):
                        signals.append({"kind": "posting_url", "value": item})
                elif key in {"description", "descriptionPlain", "descriptionHtml", "text", "content"} and isinstance(item, str):
                    signals.append({"kind": "posting_text", "value": re.sub("<[^>]+>", " ", item)[:12000]})
                if isinstance(item, (dict, list)):
                    walk(item, depth + 1)
    walk(payload)
    return signals[:120]


def matching_evidence(company: dict, signals: list[dict]) -> list[dict]:
    matched = []
    identities = company_identities(company)
    named = [s for s in signals if s["kind"] == "company_name"]
    if named and not any(names_match(company, s["value"]) for s in named):
        return []
    for signal in signals:
        value, kind = signal["value"], signal["kind"]
        if kind == "company_name":
            hit = names_match(company, value)
        elif kind == "posting_url":
            parsed = urlparse(value)
            host = parsed.hostname or ""
            family = detect_ats(value)
            if family in {"lever", "ashby", "greenhouse", "smartrecruiters", "workable"}:
                token = parsed.path.strip("/").split("/")[0]
                hit = token not in GENERIC_SLUGS and names_match(company, token)
            else:
                labels = host.split(".")
                multipart = {"co.in", "co.uk", "com.au", "co.jp", "co.nz", "com.br", "com.cn"}
                offset = 3 if ".".join(labels[-2:]) in multipart else 2
                domain = ".".join(labels[-offset:])
                source_host = urlparse(company.get("careers_url", "")).hostname or ""
                hit = (len(labels) >= offset and identity_name(labels[-offset]) in identities) or (
                    bool(source_host) and not detect_ats(company.get("careers_url", ""))
                    and (source_host == domain or source_host.endswith("." + domain)))
        else:
            # A product/dependency mentioned in a JD is not employer evidence.
            text = " ".join(html.unescape(value).casefold().split())
            aliases = [company["name"], *company.get("aliases", []),
                       *ALIASES.get(identity_name(company["name"]), [])]
            hit = any(re.search(r"\b(?:at|join|about|we are|welcome to)\s+" + re.escape(n.casefold()) + r"\b", text)
                      for n in aliases)
        if hit:
            matched.append({"kind": kind, "value": value[:500]})
    return matched[:5]


def detect_ats(url: str) -> str | None:
    """Identify a URL's ATS family, never a substring in its query/path."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
    except ValueError:
        return None
    if parsed.scheme not in {"https", "http"}:
        return None
    for provider, domains in FAMILIES.items():
        if any(host == d or host.endswith("." + d) for d in domains):
            return provider
    return None


def ats_links(body: str, base_url: str) -> list[str]:
    """Read links, iframes, script embeds and JSON-escaped URLs in page source."""
    body = html.unescape(body).replace(r"\/", "/").replace(r"\u002F", "/").replace(r"\u0026", "&")
    urls = [base_url]
    urls.extend(re.findall(r'''(?:https?:)?//[^\s<>"'`\\]+''', body))
    urls.extend(urljoin(base_url, u) for u in re.findall(r'''(?:href|src)\s*=\s*["']([^"']+)''', body, re.IGNORECASE))
    found = []
    for url in urls:
        url = urljoin(base_url, url).rstrip(");,")
        if detect_ats(url) and url not in found:
            found.append(url)
    return found


def board_entry(url: str) -> dict | None:
    """Map a discovered link to the fields the vendored provider actually reads."""
    provider = detect_ats(url)
    if not provider or provider == "freshteam":  # no freshteam plugin in this vendor revision
        return None
    parsed = urlparse(url)
    host = parsed.hostname or ""
    parts = parsed.path.strip("/").split("/")
    slug = parts[0]
    if provider == "greenhouse":
        if host == "boards-api.greenhouse.io" and len(parts) >= 4:
            slug = parts[2]
        if slug == "embed":
            slug = parse_qs(parsed.query).get("for", [""])[0]
        if not slug or slug == "embed":
            return None
        url = f"https://job-boards.greenhouse.io/{quote(slug, safe='')}"
        api = f"https://boards-api.greenhouse.io/v1/boards/{quote(slug, safe='')}/jobs"
    elif provider == "lever":
        if host.startswith("api.") and len(parts) >= 3:
            slug = parts[2]
        if not slug:
            return None
        region = "eu.lever.co" if host.endswith("eu.lever.co") else "lever.co"
        url = f"https://jobs.{region}/{quote(slug, safe='')}"
        api = f"https://api.{region}/v0/postings/{quote(slug, safe='')}?mode=json"
    elif provider == "ashby":
        if host == "api.ashbyhq.com" and len(parts) >= 3:
            slug = parts[2]
        if not slug:
            return None
        url = f"https://jobs.ashbyhq.com/{quote(slug, safe='')}"
        api = f"https://api.ashbyhq.com/posting-api/job-board/{quote(slug, safe='')}"
    elif provider == "smartrecruiters":
        if host == "api.smartrecruiters.com" and len(parts) >= 3:
            slug = parts[2]
        if not slug:
            return None
        url = f"https://careers.smartrecruiters.com/{quote(slug, safe='')}"
        # This provider reads a BOARD url from api, not the JSON endpoint.
        api = url
    elif provider == "workable":
        if host != "apply.workable.com" or not slug or slug in {"j", "api"}:
            return None
        url = f"https://apply.workable.com/{quote(slug, safe='')}/"
        api = f"https://apply.workable.com/api/v1/widget/accounts/{quote(slug, safe='')}?details=true"
    elif provider == "recruitee":
        url = f"https://{host}/"
        api = f"https://{host}/api/offers/"
    else:
        api = url
    return {"provider": provider, "careers_url": url, "api": api}


def slug_candidates(entry: dict) -> list[str]:
    name = entry["name"].casefold()
    host = urlparse(entry.get("careers_url", "")).hostname or ""
    domain = host.removeprefix("www.").split(".")[0]
    words = re.sub(r"[^a-z0-9 ]", "", name).split()
    values = ["".join(words), "-".join(words), domain]
    if len(words) > 1 and words[-1] in {"labs", "technologies", "technology", "systems", "india", "software"}:
        values.append("".join(words[:-1]))
    return list(dict.fromkeys(v for v in values if v and v not in GENERIC_SLUGS))[:4]


def slug_boards(entry: dict) -> list[dict]:
    return [board_entry(pattern.format(slug)) for slug in slug_candidates(entry) for pattern in (
        "https://job-boards.greenhouse.io/{}", "https://jobs.lever.co/{}", "https://jobs.ashbyhq.com/{}",
        "https://apply.workable.com/{}/", "https://careers.smartrecruiters.com/{}",
    )]


def posting_count(provider: str, payload) -> int:
    """Reject 200 error envelopes, empty boards and malformed/sample postings."""
    key = {"greenhouse": "jobs", "ashby": "jobs", "workable": "jobs",
           "smartrecruiters": "content", "recruitee": "offers", "workday": "jobPostings"}.get(provider)
    rows = payload.get(key) if key and isinstance(payload, dict) else payload if provider == "lever" else None
    if not isinstance(rows, list):
        return 0
    title_key = "text" if provider == "lever" else "name" if provider == "smartrecruiters" else "title"
    identity = {"greenhouse": "id", "lever": "id", "ashby": "jobUrl", "workable": "shortlink",
                "smartrecruiters": "id", "recruitee": "careers_url", "workday": "externalPath"}[provider]
    return sum(1 for row in rows if isinstance(row, dict) and isinstance(row.get(title_key), str)
               and row[title_key].strip() and "(sample)" not in row[title_key].casefold()
               and (row.get(identity) or (row.get("url") if provider in {"workable", "recruitee"} else None)))


class ProbeCache:
    """Versioned positive (7d), negative (1d), transport-error (15m) cache."""
    def __init__(self, path: Path, refresh: bool = False):
        self.path, self.refresh = path, refresh
        try:
            data = json.loads(path.read_text())
            self.records = data["records"] if data.get("version") == 1 else {}
        except (OSError, ValueError, KeyError, TypeError):
            self.records = {}

    def get(self, key):
        row = self.records.get(key)
        if self.refresh or not isinstance(row, dict):
            return None
        ttl = 900 if row.get("error") else 604800 if row.get("count", 0) else 86400
        if time.time() - row.get("at", 0) < ttl:
            return row
        return None

    def put(self, key, **values):
        self.records[key] = {"at": time.time(), **values}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps({"version": 1, "records": self.records}, indent=2))
        temp.replace(self.path)


# Complex providers keep their own HTML/token handling. Use their real parser,
# with bounded public HTTP calls, rather than treating an ATS-looking URL as proof.
NODE_PROBE = r"""
import { readFileSync } from 'node:fs';
import { loadProviders } from REGISTRY;
const providers = await loadProviders(PROVIDERS);
const entry = JSON.parse(readFileSync(0, 'utf8'));
let requests = 0;
async function request(url, opts = {}, json = false) {
  if (++requests > 4) throw Error('probe request cap');
  const {timeoutMs, maxBytes, ...rest} = opts;
  const r = await fetch(url, {...rest, headers: {...opts.headers, 'User-Agent': UA},
    signal: AbortSignal.timeout(10000)});
  if (!r.ok) throw Error(`HTTP ${r.status}`);
  return json ? r.json() : r.text();
}
try {
  const jobs = await providers.get(entry.provider).fetch(entry, {
    fetchJson: (u,o) => request(u,o,true), fetchText: (u,o) => request(u,o),
    maxPages: 1, includeUndated: true, sleep: async () => new Promise(r => setTimeout(r, 200)),
  });
  console.log(JSON.stringify({count: Array.isArray(jobs) ? jobs.filter(j => j.title && j.url).length : 0}));
} catch (e) { console.log(JSON.stringify({count: 0, error: e.message})); }
""".replace("REGISTRY", json.dumps((VENDOR / "providers/_registry.mjs").as_uri())).replace(
    "PROVIDERS", json.dumps(str(VENDOR / "providers"))).replace("UA", json.dumps(USER_AGENT))


class Resolver:
    def __init__(self, client, cache: ProbeCache, concurrency: int = 6):
        self.client, self.cache = client, cache
        self.slots = asyncio.Semaphore(concurrency)
        self.host_locks = {}
        self.inflight = {}
        self.accepted = {}
        self.rejected = {}
        # Keep proven rejections visible after the bad URL has been removed
        # from portals.yml. Do not retain failed/empty metadata lookups as proof.
        for key, record in cache.records.items():
            if not key.startswith("probe:") or not record.get("count", 0):
                continue
            for decision in record.get("discoveries", {}).values():
                evidence = decision.get("identity_evidence", [])
                named = [s["value"] for s in evidence if s["kind"] in {"board_name", "unmatched_identity"}]
                now_matches = any(names_match({"name": decision["company"]}, n) for n in named)
                if decision.get("accepted") is False and not now_matches and any(s.get("value") for s in evidence):
                    self.rejected.setdefault(decision["company"], []).append({
                        "board": decision.get("board", key.split(":", 2)[-1]), "identity_evidence": evidence})

    @staticmethod
    def probe_key(entry):
        return "probe:" + entry["provider"] + ":" + entry.get("api", entry["careers_url"])

    async def request(self, url: str, **kwargs):
        host = urlparse(url).hostname
        lock = self.host_locks.setdefault(host, asyncio.Lock())
        async with lock, self.slots:
            await asyncio.sleep(0.2)
            async with asyncio.timeout(12):
                response = await self.client.request("POST" if "json" in kwargs else "GET", url, **kwargs)
                response.raise_for_status()
                if len(response.content) > 12_000_000:
                    raise ValueError("probe response too large")
                return response

    async def links(self, url: str) -> list[str]:
        key = "html:" + url
        cached = self.cache.get(key)
        if cached is not None:
            return cached.get("links", [])
        try:
            response = await self.request(url)
            links = ats_links(response.text, str(response.url))
            self.cache.put(key, links=links)
        except (httpx.HTTPError, ValueError, TimeoutError) as exc:
            links = []
            self.cache.put(key, links=[], error=type(exc).__name__)
        return links

    async def probe(self, entry: dict, *, identity_required: bool = False) -> bool:
        key = self.probe_key(entry)
        cached = self.cache.get(key)
        needs_signals = (identity_required and entry["provider"] != "greenhouse" and cached
                         and cached.get("count", 0) > 0 and cached.get("signals_version") != 1)
        if cached is not None and not needs_signals:
            return cached.get("count", 0) > 0
        if key not in self.inflight:
            self.inflight[key] = asyncio.create_task(self._probe(entry, key))
        try:
            return await self.inflight[key]
        finally:
            if self.inflight.get(key) and self.inflight[key].done():
                self.inflight.pop(key, None)

    async def _probe(self, entry: dict, key: str) -> bool:
        provider, url = entry["provider"], entry.get("api", entry["careers_url"])
        signals = []
        try:
            if provider in {"greenhouse", "lever", "ashby", "workable", "smartrecruiters", "recruitee"}:
                if provider == "smartrecruiters":
                    slug = urlparse(url).path.strip("/").split("/")[0]
                    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=10&status=PUBLIC"
                response = await self.request(url)
                payload = response.json()
                count = posting_count(provider, payload)
                signals = identity_signals(provider, payload)
            else:
                async with self.slots:
                    process = await asyncio.create_subprocess_exec(
                        "node", "--input-type=module", "--eval", NODE_PROBE,
                        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE, cwd=ROOT)
                    try:
                        out, _ = await asyncio.wait_for(process.communicate(json.dumps(entry).encode()), 35)
                    except (TimeoutError, asyncio.CancelledError):
                        process.kill()
                        await process.wait()
                        raise
                    result = json.loads(out)
                    count = result.get("count", 0)
                    if result.get("error"):
                        self.cache.put(key, count=0, error=result["error"])
                        return False
            self.cache.put(key, count=count, signals=signals, signals_version=1)
            return count > 0
        except (httpx.HTTPError, OSError, ValueError, TimeoutError) as exc:
            self.cache.put(key, count=0, error=type(exc).__name__)
            return False

    async def greenhouse_name(self, board: dict) -> str:
        canonical = board_entry(board.get("api") or board["careers_url"])
        if not canonical:
            return ""
        url = canonical["api"].removesuffix("/jobs")
        key = "identity:" + url
        cached = self.cache.get(key)
        if cached is not None:
            return cached.get("name", "")
        try:
            payload = (await self.request(url)).json()
            name = payload.get("name", "") if isinstance(payload, dict) else ""
            name = name if isinstance(name, str) else ""
            self.cache.put(key, name=name, count=bool(name))
            return name
        except (httpx.HTTPError, ValueError, TimeoutError) as exc:
            self.cache.put(key, name="", error=type(exc).__name__)
            return ""

    def record_discovery(self, company, board, found_by, evidence, accepted):
        record = self.cache.records.setdefault(self.probe_key(board), {"at": time.time()})
        record.setdefault("discoveries", {})[_name(company)] = {
            "company": company["name"], "found_by": found_by, "identity_evidence": evidence,
            "board": board["careers_url"], "accepted": accepted, "at": time.time(),
        }
        if accepted:
            self.accepted[_name(company)] = found_by
        else:
            self.rejected.setdefault(company["name"], []).append({
                "board": board["careers_url"], "identity_evidence": evidence})

    async def accept(self, company, board, found_by, source_url):
        if found_by == "slug":
            parsed = urlparse(board["careers_url"])
            token = ((parsed.hostname or "").split(".")[0] if board["provider"] == "recruitee"
                     else parsed.path.strip("/").split("/")[0]).casefold()
            if token in GENERIC_SLUGS:
                self.record_discovery(company, board, found_by, [{"kind": "generic_slug", "value": token}], False)
                return False
        if not await self.probe(board, identity_required=found_by == "slug"):
            return False
        if found_by == "link":
            evidence = [{"kind": "careers_page_link", "value": source_url}]
        elif board["provider"] == "greenhouse":
            name = await self.greenhouse_name(board)
            evidence = [{"kind": "board_name", "value": name}]
            if not names_match(company, name):
                self.record_discovery(company, board, found_by, evidence, False)
                return False
        else:
            signals = self.cache.records[self.probe_key(board)].get("signals", [])
            evidence = matching_evidence(company, signals)
            if not evidence:
                self.record_discovery(company, board, found_by,
                                      [{"kind": "unmatched_identity", "value": s["value"][:200]}
                                       for s in signals if s["kind"] == "company_name"]
                                      or [{"kind": "missing_identity", "value": "No matching company evidence"}], False)
                return False
        self.record_discovery(company, board, found_by, evidence, True)
        return True

    async def resolve(self, entry: dict, native: str | None = None, source: dict | None = None) -> dict:
        # The output's ATS URL is not proof of an own-site link. Re-establish
        # provenance from the seed (or persisted source), including legacy cache hits.
        original = copy.deepcopy(entry)
        original["careers_url"] = (source or {}).get("careers_url", entry.get("careers_source_url", entry.get("careers_url", "")))
        original.pop("api", None)
        original.pop("provider", None)
        if source and source.get("aliases"):
            original["aliases"] = source["aliases"]
        source_url = original["careers_url"]
        if not detect_ats(source_url):
            for link in await self.links(source_url):
                if (board := board_entry(link)) and await self.accept(original, board, "link", source_url):
                    return resolved_entry({**entry, "careers_source_url": source_url}, board)
        candidates = []
        if entry.get("provider") or native:
            candidates.append({**entry, "provider": entry.get("provider") or native})
        for url in (entry.get("api"), entry.get("careers_url"), source_url):
            if url and (board := board_entry(url)):
                candidates.append(board)
        for board in candidates:
            found_by = "slug" if board["provider"] in IDENTITY_PROVIDERS else "link"
            if await self.accept(original, board, found_by, source_url):
                return resolved_entry({**entry, "careers_source_url": source_url}, board)
        for board in slug_boards(original):
            if await self.accept(original, board, "slug", source_url):
                return resolved_entry({**entry, "careers_source_url": source_url}, board)
        return fallback_entry({**entry, "careers_url": source_url})


def resolved_entry(entry: dict, board: dict) -> dict:
    result = copy.deepcopy(entry)
    result.update({k: v for k, v in board.items() if k in {"provider", "api", "careers_url"}})
    result.pop("scan_method", None)
    result.pop("scan_query", None)
    if "ATS unresolved" in result.get("notes", ""):
        result.pop("notes", None)
    return result


def fallback_entry(entry: dict) -> dict:
    entry = copy.deepcopy(entry)
    entry.pop("provider", None)
    entry.pop("api", None)
    entry["scan_method"] = "websearch"
    parsed = urlparse(entry.get("careers_url", ""))
    scope = f"site:{parsed.netloc}{parsed.path} " if parsed.netloc else ""
    entry.setdefault("scan_query", f'{scope}"{entry["name"]}" (Java OR backend OR "software engineer") India')
    entry.setdefault("notes", "ATS unresolved; websearch fallback, requires follow-up before API scanning.")
    return entry


def vendor_detection(companies: list[dict], vendor: Path = VENDOR, *, strict: bool = False) -> list[str | None]:
    registry = (vendor / "providers/_registry.mjs").as_uri()
    code = """
import { readFileSync } from 'node:fs';
import { loadProviders, resolveProvider } from REGISTRY;
const providers = await loadProviders(PROVIDERS);
const rows = JSON.parse(readFileSync(0, 'utf8'));
console.log(JSON.stringify(rows.map(entry => {
  const hit = resolveProvider(entry, providers, {skipIds: ['local-parser']});
  return hit?.provider?.id || null;
})));
""".replace("REGISTRY", json.dumps(registry)).replace("PROVIDERS", json.dumps(str(vendor / "providers")))
    try:
        result = subprocess.run(["node", "--input-type=module", "--eval", code], input=json.dumps(companies),
                                capture_output=True, text=True, check=True, timeout=45, cwd=ROOT)
        detected = json.loads(result.stdout)
        if not isinstance(detected, list) or len(detected) != len(companies):
            raise ValueError("invalid detector output")
        if result.stderr.strip():
            print(result.stderr.strip(), file=sys.stderr)
        return detected
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        if strict:
            raise RuntimeError(f"career-ops registry validation failed: {exc}") from exc
        print(f"career-ops detection unavailable: {exc}", file=sys.stderr)
        return [None] * len(companies)


def _name(entry: dict) -> str:
    return re.sub(r"[^\w]", "", str(entry.get("name", "")).casefold())


def merge_portals(existing: dict, additions: list[dict]) -> dict:
    """Dedupe by normalized name/board; preserve existing user preferences."""
    result = copy.deepcopy(existing)
    companies = []
    names, urls = set(), set()
    for row in [*result.get("tracked_companies", []), *additions]:
        row = copy.deepcopy(row)
        row["name"] = str(row["name"]).strip()
        row.setdefault("enabled", True)
        name = _name(row)
        url = row.get("careers_url", "").rstrip("/").casefold()
        if name in names or (url and url in urls):
            continue
        names.add(name)
        if url:
            urls.add(url)
        companies.append(row)
    result["tracked_companies"] = companies
    result.setdefault("title_filter", copy.deepcopy(TITLE_FILTER))
    result.setdefault("location_filter", {
        "allow": ["Chennai", "Tamil Nadu", "Bengaluru", "Bangalore", "Karnataka", "India", "Remote", "Worldwide", "APAC"],
        "block": [],
    })
    boards = result.setdefault("job_boards", [])
    for board in REMOTE_BOARDS:
        if not any(b.get("provider") == board["provider"] or _name(b) == _name(board) for b in boards):
            boards.append(copy.deepcopy(board))
    return result


async def discover_entries(entries: list[dict], cache: ProbeCache, concurrency: int = 6,
                           sources: dict | None = None) -> list[dict]:
    native = vendor_detection(entries)
    async with httpx.AsyncClient(timeout=10, follow_redirects=True, max_redirects=5,
                                 headers={"User-Agent": USER_AGENT},
                                 limits=httpx.Limits(max_connections=concurrency)) as client:
        resolver = Resolver(client, cache, concurrency)
        done = 0

        async def one(entry, provider):
            nonlocal done
            result = await resolver.resolve(entry, provider, (sources or {}).get(_name(entry)))
            done += 1
            print(f"[{done}/{len(entries)}] {entry['name']}: {result.get('provider', 'websearch')}", file=sys.stderr)
            if done % 10 == 0:
                cache.save()
            return result
        try:
            result = await asyncio.gather(*(one(e, p) for e, p in zip(entries, native, strict=True)))
            counts = Counter(resolver.accepted.values())
            print(f"Discovery: slug-accepted={counts['slug']}, link-accepted={counts['link']}")
            print("Rejected by identity (including cached decisions): " + (", ".join(sorted(resolver.rejected)) or "none"))
            for name, rejections in sorted(resolver.rejected.items()):
                unique = {json.dumps(r, sort_keys=True) for r in rejections}
                print(f"  {name}: " + "; ".join(sorted(unique)), file=sys.stderr)
            return result
        finally:
            cache.save()


async def audit_greenhouse(entries: list[dict], cache: ProbeCache) -> int:
    async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        resolver = Resolver(client, cache)
        boards = [e for e in entries if e.get("provider") == "greenhouse"]
        async def check(entry):
            name = await resolver.greenhouse_name(entry)
            return None if names_match(entry, name) else f"{entry['name']} -> {name or '(unavailable)'}"
        failures = [r for r in await asyncio.gather(*(check(e) for e in boards)) if r]
        cache.save()
        for failure in failures:
            print("Greenhouse mismatch: " + failure)
        print(f"Greenhouse board-name audit: checked={len(boards)}, matched={len(boards) - len(failures)}, mismatched={len(failures)}")
        return int(bool(failures))


def validate_and_summarize(result: dict) -> str:
    entries = result["tracked_companies"]
    api_entries = [e for e in entries if e.get("provider")]
    detected = vendor_detection(api_entries, strict=True)
    invalid = [e["name"] for e, p in zip(api_entries, detected, strict=True) if p != e["provider"]]
    if invalid:
        raise RuntimeError("Unresolvable API entries: " + ", ".join(invalid))
    counts = Counter(detected)
    providers = ", ".join(f"{p}={n}" for p, n in sorted(counts.items()))
    return (f"total={len(entries)}, API-resolvable={len(api_entries)}, "
            f"websearch={len(entries) - len(api_entries)}; {providers}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=ROOT / "config/seed_companies.yml")
    parser.add_argument("--output", type=Path,
                        default=Path(os.environ.get("CAREER_OPS_DATA_DIR", ROOT / "data/careerops")) / "portals.yml")
    parser.add_argument("--cache", type=Path, default=ROOT / "data/run/portals_probe.json")
    parser.add_argument("--concurrency", type=int, choices=range(1, 9), default=6)
    parser.add_argument("--dry-run", action="store_true", help="Offline preview; no probes or writes")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--discover", action="store_true", help="Compatibility flag; discovery is now the default")
    parser.add_argument("--audit-greenhouse", action="store_true", help="Check every configured Greenhouse board name")
    args = parser.parse_args(argv)
    seeds = yaml.safe_load(args.seed.read_text())["companies"]
    existing = (yaml.safe_load(args.output.read_text()) or {}) if args.output.exists() else {}
    if args.audit_greenhouse:
        return asyncio.run(audit_greenhouse(existing.get("tracked_companies", []), ProbeCache(args.cache, args.refresh)))
    result = merge_portals(existing, seeds)
    if args.dry_run:
        print(yaml.safe_dump(result, sort_keys=False, allow_unicode=True), end="")
        return 0
    result["tracked_companies"] = asyncio.run(discover_entries(
        result["tracked_companies"], ProbeCache(args.cache, args.refresh), args.concurrency,
        {_name(row): row for row in seeds}))
    # Discovery can reveal that two branded pages point at the same board.
    result = merge_portals(result, [])
    summary = validate_and_summarize(result)
    content = yaml.safe_dump(result, sort_keys=False, allow_unicode=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    backup = args.output.with_suffix(args.output.suffix + ".bak")
    if args.output.exists() and not backup.exists():
        shutil.copy2(args.output, backup)
    if not args.output.exists() or args.output.read_text() != content:
        temporary = args.output.with_suffix(".yml.tmp")
        temporary.write_text(content)
        temporary.replace(args.output)
    print(f"{args.output}: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
