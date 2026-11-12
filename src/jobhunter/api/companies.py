"""Tracked companies for the career-ops scan (data/careerops/portals.yml, career-ops format).

The file is career-ops' own: keys this API does not model (scan_method, scan_query, title_filter, job_boards, ...)
are kept as they are, order is preserved, and every write goes to a temp file that is renamed over portals.yml.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from fastapi import APIRouter, HTTPException, Response

from jobhunter import paths
from jobhunter.api.workflow import unprocessable
from jobhunter.schemas import Company, CompanyIn, CompanyPatch

router = APIRouter(prefix="/api/companies", tags=["config"])

_lock = threading.Lock()  # read-modify-write of portals.yml; route handlers run on a thread pool
_QUERY_TAIL = '(Java OR backend OR "software engineer") India'


def _file() -> Path:
    return paths.CAREEROPS_DATA / "portals.yml"


def _read() -> dict[str, Any]:
    path = _file()
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise HTTPException(500, "portals.yml is not valid YAML") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise HTTPException(500, "portals.yml must be a mapping")
    return data


def _entries(data: dict[str, Any]) -> list[Any]:
    entries = data.get("tracked_companies")
    if entries is None:
        entries = data["tracked_companies"] = []
    if not isinstance(entries, list):
        raise HTTPException(500, "portals.yml tracked_companies must be a list")
    return entries


def _write(data: dict[str, Any]) -> None:
    path = _file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _is_company(entry: Any) -> bool:
    return isinstance(entry, dict) and isinstance(entry.get("name"), str)


def _company(entry: dict[str, Any]) -> Company:
    return Company(
        name=entry["name"], careers_url=str(entry.get("careers_url") or ""), enabled=entry.get("enabled", True),
        provider=entry.get("provider"), notes=entry.get("notes"))


def _find(entries: list[Any], name: str) -> dict[str, Any]:
    wanted = name.strip().casefold()
    for entry in entries:
        if _is_company(entry) and entry["name"].strip().casefold() == wanted:
            return entry
    raise HTTPException(404, "company not found")


def _check_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise unprocessable("careers_url", "careers_url must be an http(s) URL")
    return url


def _site(url: str) -> str:
    parsed = urlparse(url)
    return f"site:{parsed.netloc}{parsed.path}"


@router.get("", response_model=list[Company], operation_id="listCompanies")
def list_companies() -> list[Company]:
    """tracked_companies from portals.yml, in file order. Empty list if the file is missing."""
    with _lock:
        return [_company(e) for e in _entries(_read()) if _is_company(e)]


@router.post("", response_model=Company, status_code=201, operation_id="addCompany")
def add_company(body: CompanyIn) -> Company:
    """Append (provider None, websearch scan). 409 if the name exists (case-insensitive)."""
    name, url = body.name.strip(), _check_url(body.careers_url)
    if not name:
        raise unprocessable("name", "name must not be blank")
    with _lock:
        data = _read()
        entries = _entries(data)
        if any(_is_company(e) and e["name"].strip().casefold() == name.casefold() for e in entries):
            raise HTTPException(409, f"{name} is already tracked")
        entry = {
            "name": name, "careers_url": url, "enabled": True, "scan_method": "websearch",
            "scan_query": f'{_site(url)} "{name}" {_QUERY_TAIL}', "notes": "Added from the dashboard.",
        }
        entries.append(entry)
        _write(data)
        return _company(entry)


@router.patch("/{name}", response_model=Company, operation_id="patchCompany")
def patch_company(name: str, body: CompanyPatch) -> Company:
    url = _check_url(body.careers_url) if body.careers_url is not None else None
    with _lock:
        data = _read()
        entry = _find(_entries(data), name)
        if body.enabled is not None:
            entry["enabled"] = body.enabled
        if url is not None:
            old_site = _site(str(entry.get("careers_url") or ""))
            entry["careers_url"] = url
            query = entry.get("scan_query")
            if isinstance(query, str) and query.startswith(old_site):  # keep the websearch scope in step
                entry["scan_query"] = _site(url) + query[len(old_site):]
        if body.enabled is not None or url is not None:
            _write(data)
        return _company(entry)


@router.delete("/{name}", status_code=204, operation_id="deleteCompany")
def delete_company(name: str) -> Response:
    with _lock:
        data = _read()
        entries = _entries(data)
        entries.remove(_find(entries, name))
        _write(data)
    return Response(status_code=204)
