#!/usr/bin/env python3
"""Build career-ops portals from curated search targets.

Use career-ops' own provider detectors first (a read-only Node subprocess), then
host matching when Node/dependencies are unavailable. Unrecognized branded
career pages are retained as explicit websearch entries for manual resolution.
Add --discover to probe unresolved names using discover-ats.mjs's public APIs;
these probes can take several minutes. --dry-run never writes.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "career-ops"
TITLE_FILTER = {
    "positive": ["Java", "Backend", "Back-end", "Spring", "Software Engineer", "SDE",
                 "Platform Engineer", "Microservices", "Identity", "Keycloak"],
    "negative": [],
}
REMOTE_BOARDS = [
    {"name": "Himalayas", "provider": "himalayas", "careers_url": "https://himalayas.app/jobs",
     "enabled": True},
    {"name": "RemoteOK", "provider": "remoteok", "careers_url": "https://remoteok.com/",
     "enabled": True},
    {"name": "Remotive", "provider": "remotive", "careers_url": "https://remotive.com/remote-jobs",
     "enabled": True},
    {"name": "We Work Remotely", "provider": "weworkremotely",
     "careers_url": "https://weworkremotely.com/", "enabled": True},
]


def detect_ats(url: str) -> str | None:
    """Offline host-based fallback; never classify a substring in a query/path."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
    except ValueError:
        return None
    if parsed.scheme not in {"https", "http"}:
        return None
    families = {
        "greenhouse": ("greenhouse.io",),
        "lever": ("lever.co",),
        "ashby": ("ashbyhq.com",),
        "workday": ("myworkdayjobs.com", "myworkdaysite.com"),
        "smartrecruiters": ("smartrecruiters.com",),
        "darwinbox": ("darwinbox.in", "darwinbox.com"),
        "keka": ("keka.com",),
        "zoho-recruit": ("zohorecruit.com", "zohorecruit.in", "zohorecruit.eu"),
        "successfactors": ("successfactors.com", "successfactors.eu", "jobs2web.com"),
    }
    for provider, domains in families.items():
        if any(host == domain or host.endswith("." + domain) for domain in domains):
            return provider
    return None


def vendor_detection(companies: list[dict], vendor: Path = VENDOR) -> list[str | None]:
    """Run the same detect() methods used by scan.mjs, in one bounded process.

    Unlike discover-ats.mjs's slug probing this makes no network requests and
    does not write user data or need all 150 companies to have live openings.
    """
    registry = (vendor / "providers" / "_registry.mjs").as_uri()
    code = """
import { readFileSync } from 'node:fs';
import { loadProviders, resolveProvider } from REGISTRY;
const providers = await loadProviders(PROVIDERS);
const rows = JSON.parse(readFileSync(0, 'utf8'));
console.log(JSON.stringify(rows.map(entry => {
  const hit = resolveProvider(entry, providers, {skipIds: ['local-parser']});
  return hit?.provider?.id || null;
})));
""".replace("REGISTRY", json.dumps(registry)).replace(
        "PROVIDERS", json.dumps(str(vendor / "providers")))
    try:
        result = subprocess.run(
            ["node", "--input-type=module", "--eval", code], input=json.dumps(companies),
            capture_output=True, text=True, check=True, timeout=45, cwd=ROOT,
        )
        detected = json.loads(result.stdout)
        if not isinstance(detected, list) or len(detected) != len(companies):
            raise ValueError("invalid detector output")
        if result.stderr.strip():
            print("career-ops detector warnings: " + result.stderr.strip(), file=sys.stderr)
        return detected
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"career-ops detection unavailable; using URL fallback: {exc}", file=sys.stderr)
        return [None] * len(companies)


def company_entries(seeds: list[dict], detected: list[str | None]) -> list[dict]:
    entries = []
    for seed, provider in zip(seeds, detected, strict=True):
        entry = copy.deepcopy(seed)
        name = str(entry["name"]).strip()
        entry["name"] = name
        url = entry.get("careers_url") or ""
        provider = provider or detect_ats(entry.get("api") or url)
        entry.setdefault("enabled", True)
        if provider:
            entry["provider"] = provider
        else:
            entry.setdefault("scan_method", "websearch")
            parsed = urlparse(url)
            scope = f"site:{parsed.netloc}{parsed.path} " if parsed.netloc else ""
            entry.setdefault("scan_query", f'{scope}"{name}" (Java OR backend OR "software engineer") India')
            entry.setdefault("notes", "ATS unresolved; websearch fallback, requires follow-up before API scanning.")
        entries.append(entry)
    return entries


def discover_entries(entries: list[dict], vendor: Path = VENDOR) -> list[dict]:
    """Optionally resolve unknown names live, without allowing vendor writes.

    Resolved ATS URLs come from the vendor's public API probes. Failed/empty
    probes retain the explicit fallback rather than inventing a board slug.
    """
    unknown = [entry["name"] for entry in entries if entry.get("scan_method") == "websearch"]
    if not unknown:
        return entries
    try:
        completed = subprocess.run(
            ["node", str(vendor / "discover-ats.mjs"),
             "--vendors", "gh,ashby,lever,smartrecruiters", *unknown],
            capture_output=True, text=True, check=True, timeout=300, cwd=ROOT,
        )
        resolved = json.loads(completed.stdout)["resolved"]
        matches = {_name(row): row for row in resolved}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as exc:
        print(f"Live ATS discovery unavailable ({type(exc).__name__}); "
              f"retaining {len(unknown)} unresolved targets.", file=sys.stderr)
        return entries
    result = copy.deepcopy(entries)
    for entry in result:
        match = matches.get(_name(entry))
        if not match:
            continue
        entry["careers_url"] = match["careers_url"]
        if match.get("api"):
            entry["api"] = match["api"]
        entry["provider"] = match.get("provider") or match["vendor"]
        entry.pop("scan_method", None)
        entry.pop("scan_query", None)
        entry["notes"] = "ATS board resolved by career-ops discover-ats.mjs public API probe."
    return result


def _name(entry: dict) -> str:
    return " ".join(str(entry.get("name", "")).casefold().split())


def merge_portals(existing: dict, additions: list[dict]) -> dict:
    """Keep existing entries and preferences intact; only append missing targets.

    Re-running produces the same document, including entries disabled by users.
    A board already present under another display name is matched by provider.
    """
    result = copy.deepcopy(existing)
    companies = result.setdefault("tracked_companies", [])
    names = {_name(row) for row in companies}
    urls = {row.get("careers_url", "").rstrip("/").casefold() for row in companies
            if row.get("careers_url")}
    for entry in additions:
        name = _name(entry)
        url = entry.get("careers_url", "").rstrip("/").casefold()
        if name in names or (url and url in urls):
            continue
        companies.append(copy.deepcopy(entry))
        names.add(name)
        if url:
            urls.add(url)
    result.setdefault("title_filter", copy.deepcopy(TITLE_FILTER))
    result.setdefault("location_filter", {
        "allow": ["Chennai", "Tamil Nadu", "Bengaluru", "Bangalore", "Karnataka",
                  "India", "Remote", "Worldwide", "APAC"],
        "block": [],
    })
    boards = result.setdefault("job_boards", [])
    providers = {row.get("provider") for row in boards}
    board_names = {_name(row) for row in boards}
    for board in REMOTE_BOARDS:
        if board["provider"] not in providers and _name(board) not in board_names:
            boards.append(copy.deepcopy(board))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=ROOT / "config" / "seed_companies.yml")
    default_data = Path(os.environ.get("CAREER_OPS_DATA_DIR", ROOT / "data" / "careerops"))
    parser.add_argument("--output", type=Path, default=default_data / "portals.yml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--discover", action="store_true",
                        help="Probe unresolved names against live ATS APIs (up to five minutes)")
    args = parser.parse_args(argv)
    seeds = yaml.safe_load(args.seed.read_text())["companies"]
    existing = (yaml.safe_load(args.output.read_text()) or {}) if args.output.exists() else {}
    entries = company_entries(seeds, vendor_detection(seeds))
    if args.discover:
        entries = discover_entries(entries)
    result = merge_portals(existing, entries)
    content = yaml.safe_dump(result, sort_keys=False, allow_unicode=True)
    if args.dry_run:
        print(content, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if not args.output.exists() or args.output.read_text() != content:
            temporary = args.output.with_suffix(".yml.tmp")
            temporary.write_text(content)
            temporary.replace(args.output)
        print(f"{args.output}: {len(result['tracked_companies'])} companies, "
              f"{len(result['job_boards'])} boards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
