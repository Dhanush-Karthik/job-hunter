"""Offline resolver coverage: recorded response shapes and mocked HTTP only."""
import asyncio
import importlib.util
import json
import subprocess
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_portals.py"
spec = importlib.util.spec_from_file_location("build_portals", SCRIPT)
portals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(portals)
FIXTURES = Path(__file__).parent / "fixtures/portals"
PAYLOADS = json.loads((FIXTURES / "postings.json").read_text())


@pytest.mark.parametrize(("url", "provider"), [
    ("https://job-boards.greenhouse.io/acme", "greenhouse"),
    ("https://boards.eu.greenhouse.io/acme", "greenhouse"),
    ("https://boards-api.greenhouse.io/v1/boards/acme/jobs", "greenhouse"),
    ("https://jobs.eu.lever.co/acme", "lever"),
    ("https://jobs.ashbyhq.com/Acme", "ashby"),
    ("https://apply.workable.com/acme", "workable"),
    ("https://acme.wd3.myworkdayjobs.com/en-US/External", "workday"),
    ("https://wd3.myworkdaysite.com/recruiting/acme/External", "workday"),
    ("https://careers.smartrecruiters.com/Acme", "smartrecruiters"),
    ("https://acme.darwinbox.in/ms/candidate/careers", "darwinbox"),
    ("https://acme.keka.com/careers/", "keka"),
    ("https://acme.zohorecruit.in/jobs/Careers", "zoho-recruit"),
    ("https://acme.zohorecruit.com.au/jobs/Careers", "zoho-recruit"),
    ("https://acme.turbohire.co/", "turbohire"),
    ("https://acme.freshteam.com/jobs", "freshteam"),
    ("https://careers.acme.com/", None),
    ("https://evilgreenhouse.io/acme", None),
    ("https://greenhouse.io.evil.com/", None),
    ("https://example.com/?ats=lever.co", None),
    ("javascript://jobs.lever.co/acme", None),
    ("not a URL", None),
])
def test_detect_ats(url, provider):
    assert portals.detect_ats(url) == provider


def test_link_detection_all_ats_and_embeds():
    links = portals.ats_links((FIXTURES / "links.html").read_text(), "https://acme.example/careers")
    assert {portals.detect_ats(link) for link in links} == set(portals.FAMILIES)
    assert len(links) == 15
    assert portals.board_entry(links[0])["api"].endswith("/acme/jobs")
    assert any("jobs.ashbyhq.com/Acme/embed" in link for link in links)
    assert not any("evil" in link or "fake" in link for link in links)
    # Family recognition is separate from availability of a real vendor plugin.
    assert portals.board_entry("https://acme.freshteam.com/jobs") is None


@pytest.mark.parametrize(("url", "api", "careers"), [
    ("https://boards-api.greenhouse.io/v1/boards/acme/jobs", "https://boards-api.greenhouse.io/v1/boards/acme/jobs", "https://job-boards.greenhouse.io/acme"),
    ("https://boards.greenhouse.io/embed/job_board?for=acme", "https://boards-api.greenhouse.io/v1/boards/acme/jobs", "https://job-boards.greenhouse.io/acme"),
    ("https://jobs.eu.lever.co/acme/123", "https://api.eu.lever.co/v0/postings/acme?mode=json", "https://jobs.eu.lever.co/acme"),
    ("https://jobs.ashbyhq.com/Acme/embed", "https://api.ashbyhq.com/posting-api/job-board/Acme", "https://jobs.ashbyhq.com/Acme"),
    ("https://careers.smartrecruiters.com/Acme", "https://careers.smartrecruiters.com/Acme", "https://careers.smartrecruiters.com/Acme"),
    ("https://apply.workable.com/acme/j/123", "https://apply.workable.com/api/v1/widget/accounts/acme?details=true", "https://apply.workable.com/acme/"),
    ("https://acme.recruitee.com/o/backend", "https://acme.recruitee.com/api/offers/", "https://acme.recruitee.com/"),
])
def test_board_fields_match_vendor_contract(url, api, careers):
    board = portals.board_entry(url)
    assert board["api"] == api
    assert board["careers_url"] == careers


@pytest.mark.parametrize("provider", PAYLOADS)
def test_postings_accept_and_reject(provider):
    assert portals.posting_count(provider, PAYLOADS[provider]) == 1
    for filename in ("rejected.json", "empty.json"):
        assert portals.posting_count(provider, json.loads((FIXTURES / filename).read_text())) == 0
    assert portals.posting_count(provider, {"jobs": [None, {}, "bad", {"title": "Oops"}]}) == 0
    assert portals.posting_count(provider, []) == 0


def test_recruitee_sample_not_live():
    assert portals.posting_count("recruitee", {"offers": [
        {"title": "Senior Marketer (Sample)", "careers_url": "https://acme.recruitee.com/o/sample"}]}) == 0


def test_recorded_public_responses_and_careers_html():
    recorded = json.loads((FIXTURES / "recorded.json").read_text())
    assert len(recorded["payloads"]) >= 5
    for provider, payload in recorded["payloads"].items():
        assert portals.posting_count(provider, payload) == 1
        assert recorded["sources"][provider].startswith("https://")
    links = portals.ats_links((FIXTURES / "temenos.html").read_text(), "https://www.temenos.com/careers/")
    assert links and all(portals.detect_ats(url) == "workday" for url in links)


@pytest.mark.parametrize("provider", ["greenhouse", "lever", "ashby", "workable", "smartrecruiters"])
def test_slug_probe_accepts_live_payload_and_caches(provider, tmp_path):
    async def scenario():
        requests = []
        def handle(request):
            requests.append(request)
            return httpx.Response(200, json=PAYLOADS[provider])
        cache = portals.ProbeCache(tmp_path / "probe.json")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            resolver = portals.Resolver(client, cache)
            board = next(b for b in portals.slug_boards({"name": "Acme"}) if b["provider"] == provider)
            assert await resolver.probe(board)
            assert await resolver.probe(board)
        cache.save()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: pytest.fail("cache miss"))) as client:
            assert await portals.Resolver(client, portals.ProbeCache(cache.path)).probe(board)
        assert len(requests) == 1
        if provider == "smartrecruiters":
            assert requests[0].url.host == "api.smartrecruiters.com"
            assert board["api"].startswith("https://careers.smartrecruiters.com/")
    asyncio.run(scenario())


@pytest.mark.parametrize("response", [httpx.Response(200, json={"error": "not found"}),
                                      httpx.Response(200, json={"jobs": []}),
                                      httpx.Response(404), httpx.Response(429),
                                      httpx.Response(200, text="<html>login</html>")])
def test_slug_probe_rejects_and_negative_cache(response, tmp_path):
    async def scenario():
        calls = []
        def handle(request):
            calls.append(request)
            return response
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            resolver = portals.Resolver(client, portals.ProbeCache(tmp_path / "cache.json"))
            board = portals.board_entry("https://job-boards.greenhouse.io/acme")
            assert not await resolver.probe(board)
            assert not await resolver.probe(board)
            assert len(calls) == 1
    asyncio.run(scenario())


def test_page_links_before_slug_guesses_upgrades_existing_fallback(tmp_path):
    async def scenario():
        requests = []
        def handle(request):
            requests.append(str(request.url))
            if request.url.host == "acme.example":
                return httpx.Response(200, text='<iframe src="https://boards.greenhouse.io/embed/job_board?for=real-board"></iframe>')
            assert "/real-board/jobs" in request.url.path
            return httpx.Response(200, json=PAYLOADS["greenhouse"])
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            resolver = portals.Resolver(client, portals.ProbeCache(tmp_path / "cache.json"))
            original = portals.fallback_entry({"name": "Acme", "careers_url": "https://acme.example/careers", "enabled": False})
            entry = await resolver.resolve(original)
            assert entry["provider"] == "greenhouse"
            assert entry["enabled"] is False
            assert "scan_method" not in entry and "scan_query" not in entry
            assert original["scan_method"] == "websearch"
            assert len(requests) == 2
    asyncio.run(scenario())


def test_unresolved_keeps_websearch_despite_detectable_ats(tmp_path, monkeypatch):
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as client:
            resolver = portals.Resolver(client, portals.ProbeCache(tmp_path / "cache.json"))
            monkeypatch.setattr(portals, "slug_boards", lambda e: [])
            entry = await resolver.resolve({"name": "Acme", "careers_url": "https://jobs.lever.co/acme", "provider": "lever"})
            assert "provider" not in entry and "api" not in entry
            assert entry["scan_method"] == "websearch"
    asyncio.run(scenario())


def test_cache_expiry_refresh_and_corruption(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("{broken")
    cache = portals.ProbeCache(path)
    assert cache.get("missing") is None
    cache.put("yes", count=2)
    cache.put("no", count=0)
    cache.put("error", count=0, error="timeout")
    for key in ("yes", "no", "error"):
        assert cache.get(key) is not None
    cache.records["yes"]["at"] = time.time() - 604801
    cache.records["no"]["at"] = time.time() - 86401
    cache.records["error"]["at"] = time.time() - 901
    assert all(cache.get(k) is None for k in ("yes", "no", "error"))
    cache.put("yes", count=1)
    cache.save()
    assert portals.ProbeCache(path, refresh=True).get("yes") is None


def test_concurrent_identical_probes_share_one_request(tmp_path):
    async def scenario():
        calls = []
        def handle(request):
            calls.append(request)
            return httpx.Response(200, json=PAYLOADS["greenhouse"])
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            resolver = portals.Resolver(client, portals.ProbeCache(tmp_path / "cache.json"))
            board = portals.board_entry("https://job-boards.greenhouse.io/acme")
            assert await asyncio.gather(*(resolver.probe(board) for _ in range(10))) == [True] * 10
            assert len(calls) == 1
    asyncio.run(scenario())


def test_one_busy_host_does_not_hold_other_hosts_worker_slots(tmp_path):
    async def scenario():
        other_host_started = asyncio.Event()
        async def handle(request):
            if request.url.host == "busy.example":
                await other_host_started.wait()
            else:
                other_host_started.set()
            return httpx.Response(200, text="ok")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            resolver = portals.Resolver(client, portals.ProbeCache(tmp_path / "cache.json"), concurrency=2)
            await asyncio.wait_for(asyncio.gather(
                resolver.request("https://busy.example/1"),
                resolver.request("https://busy.example/2"),
                resolver.request("https://other.example/3")), timeout=2)
    asyncio.run(scenario())


@pytest.mark.parametrize("response", [{"count": 1}, {"count": 0, "error": "not a board"}])
def test_complex_ats_uses_real_vendor_parser_with_bounded_subprocess(tmp_path, monkeypatch, response):
    async def scenario():
        process = Mock()
        process.communicate = AsyncMock(return_value=(json.dumps(response).encode(), b""))
        spawn = AsyncMock(return_value=process)
        monkeypatch.setattr(portals.asyncio, "create_subprocess_exec", spawn)
        async with httpx.AsyncClient() as client:
            resolver = portals.Resolver(client, portals.ProbeCache(tmp_path / "cache.json"))
            board = portals.board_entry("https://acme.keka.com/careers")
            assert await resolver.probe(board) == (response["count"] > 0)
            assert await resolver.probe(board) == (response["count"] > 0)
            assert spawn.await_count == 1
            assert "maxPages: 1" in spawn.call_args.args[3]
            assert "AbortSignal.timeout(10000)" in spawn.call_args.args[3]
    asyncio.run(scenario())


def test_complex_ats_timeout_kills_child_and_caches_failure(tmp_path, monkeypatch):
    async def scenario():
        process = Mock()
        process.communicate = AsyncMock(side_effect=TimeoutError)
        process.wait = AsyncMock()
        monkeypatch.setattr(portals.asyncio, "create_subprocess_exec", AsyncMock(return_value=process))
        async with httpx.AsyncClient() as client:
            resolver = portals.Resolver(client, portals.ProbeCache(tmp_path / "cache.json"))
            assert not await resolver.probe(portals.board_entry("https://acme.turbohire.co/"))
            process.kill.assert_called_once()
            process.wait.assert_awaited_once()
    asyncio.run(scenario())


def test_merge_preserves_preferences_dedupes_and_is_idempotent():
    existing = {"title_filter": {"positive": ["Java"], "negative": ["Principal"]},
                "tracked_companies": [{"name": "Acme, Inc", "careers_url": "https://old.example/",
                                       "enabled": False, "notes": "keep this"}],
                "job_boards": [{"name": "My feed", "provider": "remotive", "enabled": False}],
                "custom_key": {"keep": True}}
    additions = [{"name": "ACME INC", "careers_url": "https://new.example"},
                 {"name": "Beta", "careers_url": "https://beta.example"},
                 {"name": "Beta alias", "careers_url": "https://beta.example/"}]
    result = portals.merge_portals(existing, additions)
    assert len(result["tracked_companies"]) == 2
    assert result["tracked_companies"][0] == existing["tracked_companies"][0]
    assert result["title_filter"] == existing["title_filter"]
    assert result["job_boards"][0] == existing["job_boards"][0]
    assert result["custom_key"] == existing["custom_key"]
    assert portals.merge_portals(result, additions) == result
    assert len(existing["tracked_companies"]) == 1


def test_vendor_detection_and_strict_validation(monkeypatch):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, '["greenhouse", null]', ""))
    monkeypatch.setattr(portals.subprocess, "run", run)
    assert portals.vendor_detection([{"name": "Acme"}, {"name": "Beta"}]) == ["greenhouse", None]
    assert "resolveProvider" in run.call_args.args[0][3]
    assert "writeFile" not in run.call_args.args[0][3]
    monkeypatch.setattr(portals.subprocess, "run", Mock(side_effect=FileNotFoundError("node")))
    assert portals.vendor_detection([{}]) == [None]
    with pytest.raises(RuntimeError, match="registry validation failed"):
        portals.vendor_detection([{}], strict=True)


def test_summary_rejects_unknown_provider(monkeypatch):
    monkeypatch.setattr(portals, "vendor_detection", lambda rows, **kw: [None] * len(rows))
    with pytest.raises(RuntimeError, match="Unresolvable API entries: Acme"):
        portals.validate_and_summarize({"tracked_companies": [{"name": "Acme", "provider": "typo"}]})


def test_seed_unique_relevant_targets():
    rows = yaml.safe_load((portals.ROOT / "config/seed_companies.yml").read_text())["companies"]
    assert 280 <= len(rows) <= 350
    assert len({portals._name(r) for r in rows}) == len(rows)
    assert len({r["careers_url"].rstrip("/").casefold() for r in rows}) == len(rows)
    assert all(r["careers_url"].startswith("https://") for r in rows)


def test_cli_offline_preview_backup_and_idempotency(monkeypatch, tmp_path, capsys):
    output = tmp_path / "runtime/portals.yml"
    cache = tmp_path / "cache.json"
    seed = tmp_path / "seed.yml"
    seed.write_text("companies:\n- name: Acme\n  careers_url: https://acme.example/careers\n")
    async def discover(rows, *_):
        return [portals.resolved_entry(row, portals.board_entry("https://job-boards.greenhouse.io/acme")) for row in rows]
    monkeypatch.setattr(portals, "discover_entries", discover)
    monkeypatch.setattr(portals, "vendor_detection", lambda rows, **kw: [r.get("provider") for r in rows])
    args = ["--seed", str(seed), "--output", str(output), "--cache", str(cache)]
    assert portals.main([*args, "--dry-run"]) == 0
    assert len(yaml.safe_load(capsys.readouterr().out)["tracked_companies"]) == 1
    assert not output.parent.exists() and not cache.exists()
    output.parent.mkdir()
    original = "tracked_companies: []\n"
    output.write_text(original)
    assert portals.main(args) == 0
    assert "API-resolvable=1" in capsys.readouterr().out
    assert output.with_suffix(".yml.bak").read_text() == original
    before, mtime = output.read_bytes(), output.stat().st_mtime_ns
    assert portals.main(args) == 0
    assert output.read_bytes() == before and output.stat().st_mtime_ns == mtime
    assert output.with_suffix(".yml.bak").read_text() == original


@pytest.mark.parametrize("case", json.loads((FIXTURES / "greenhouse-identity.json").read_text())["cases"])
def test_real_greenhouse_identities_revalidate_legacy_cache(case, tmp_path, monkeypatch):
    async def scenario():
        board = portals.board_entry("https://job-boards.greenhouse.io/" + case["slug"])
        source = {"name": case["company"], "careers_url": case["careers_url"]}
        legacy = portals.resolved_entry(source, board)
        cache = portals.ProbeCache(tmp_path / "cache.json")
        key = portals.Resolver.probe_key(board)
        cache.put(key, count=1)  # Old positive cache must not bypass identity.
        requests = []
        def handle(request):
            requests.append(str(request.url))
            if str(request.url) == board["api"].removesuffix("/jobs"):
                return httpx.Response(200, json=case["board"])
            if request.url.host == "boards-api.greenhouse.io" and request.url.path.endswith("/jobs"):
                return httpx.Response(200, json=PAYLOADS["greenhouse"])
            return httpx.Response(200, text="<html>No ATS link</html>")
        monkeypatch.setattr(portals, "slug_boards", lambda _: [board])
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            resolver = portals.Resolver(client, cache)
            for _ in range(2):
                result = await resolver.resolve(legacy, "greenhouse", source)
                assert (result.get("provider") == "greenhouse") == case["accepted"]
                if not case["accepted"]:
                    assert result["careers_url"] == source["careers_url"]
                    assert result["scan_method"] == "websearch"
                    assert case["company"] in resolver.rejected
            discovery = cache.records[key]["discoveries"][portals._name(source)]
            assert discovery["found_by"] == "slug"
            assert discovery["accepted"] == case["accepted"]
            assert discovery["identity_evidence"]
            if not case["accepted"]:
                assert case["company"] in portals.Resolver(client, cache).rejected
        if case["slug"] == "talent":
            assert not any("boards-api" in url for url in requests)  # Generic slugs never probed.
        else:
            assert requests.count(board["api"].removesuffix("/jobs")) == 1
    asyncio.run(scenario())


def test_correct_new_slug_match_and_evidence(tmp_path, monkeypatch):
    async def scenario():
        def handle(request):
            if request.url.path.endswith("/jobs"):
                return httpx.Response(200, json=PAYLOADS["greenhouse"])
            if request.url.host == "boards-api.greenhouse.io":
                return httpx.Response(200, json={"name": "Tenable"})
            return httpx.Response(200, text="<html></html>")
        board = portals.board_entry("https://job-boards.greenhouse.io/tenableinc")
        monkeypatch.setattr(portals, "slug_boards", lambda _: [board])
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            cache = portals.ProbeCache(tmp_path / "cache.json")
            resolver = portals.Resolver(client, cache)
            result = await resolver.resolve({"name": "Tenable", "careers_url": "https://www.tenable.com/careers"})
            assert result["provider"] == "greenhouse"
            evidence = cache.records[resolver.probe_key(board)]["discoveries"]["tenable"]
            assert evidence["identity_evidence"] == [{"kind": "board_name", "value": "Tenable"}]
            assert resolver.accepted == {"tenable": "slug"}
    asyncio.run(scenario())


def test_own_page_link_remains_trusted_even_for_different_board_name(tmp_path):
    async def scenario():
        calls = []
        def handle(request):
            calls.append(str(request.url))
            if request.url.host == "acme.example":
                return httpx.Response(200, text='<a href="https://job-boards.greenhouse.io/talent">Jobs</a>')
            return httpx.Response(200, json=PAYLOADS["greenhouse"])
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            resolver = portals.Resolver(client, portals.ProbeCache(tmp_path / "cache.json"))
            result = await resolver.resolve({"name": "Acme", "careers_url": "https://acme.example/careers"})
            assert result["provider"] == "greenhouse"
            assert resolver.accepted == {"acme": "link"}
            decision = next(iter(resolver.cache.records[resolver.probe_key(portals.board_entry(
                "https://job-boards.greenhouse.io/talent"))]["discoveries"].values()))
            assert decision["found_by"] == "link" and decision["identity_evidence"]
            assert len(calls) == 2  # No slug identity check for an own-page link.
    asyncio.run(scenario())


@pytest.mark.parametrize(("provider", "payload"), [
    ("lever", [{"hostedUrl": "https://jobs.lever.co/acme/id"}]),
    ("ashby", {"jobs": [{"jobUrl": "https://jobs.ashbyhq.com/acme/id"}]}),
    ("workable", {"name": "Acme, Inc.", "jobs": []}),
    ("smartrecruiters", {"content": [{"company": {"name": "Acme"}}]}),
    ("recruitee", {"offers": [{"careers_url": "https://careers.acme.com/o/backend"}]}),
    ("lever", [{"descriptionPlain": "Join Acme and build identity infrastructure"}]),
])
def test_other_ats_identity_evidence(provider, payload):
    evidence = portals.matching_evidence({"name": "Acme"}, portals.identity_signals(provider, payload))
    assert evidence


def test_missing_identity_and_contradictory_company_are_rejected():
    company = {"name": "Acme"}
    assert not portals.matching_evidence(company, portals.identity_signals("workable", PAYLOADS["workable"]))
    assert not portals.matching_evidence(company, portals.identity_signals("lever", [
        {"company": "Wrong Company", "hostedUrl": "https://jobs.lever.co/acme/1"}]))
    assert not portals.matching_evidence(company, [{"kind": "posting_text", "value": "We integrate Acme software"}])
    assert not portals.matching_evidence(company, [{"kind": "posting_url", "value": "https://notacme.com/1"}])
    assert not portals.matching_evidence(company, [{"kind": "posting_url", "value": "https://acme.evil.com/1"}])


def test_generic_slug_candidates_are_excluded():
    for generic in portals.GENERIC_SLUGS:
        candidates = portals.slug_candidates({"name": "Some Employer", "careers_url": f"https://{generic}.example.com"})
        assert generic not in candidates


@pytest.mark.parametrize(("company", "name", "matches"), [
    ("Wiz", "Wiz, Inc.", True), ("Zinc", "Zinc", True), ("Tenable", "tenableinc", True),
    ("Abnormal AI", "Abnormal", True), ("Bosch", "Bosch Group", True),
    ("Rubrik", "Rubrik Job Board", True), ("Yugabyte", "YugabyteDB", True),
    ("ZoomInfo", "ZoomInfo Technologies LLC", True),
    ("Clear", "CLEAR - Corporate", False), ("Pine Labs", "Pine", False),
    ("Remote", "General Assembly Remote Jobs", False), ("TCS", "Thornbury Community Services", False),
])
def test_curated_aliases_do_not_accept_unrelated_prefix_matches(company, name, matches):
    assert portals.names_match({"name": company}, name) == matches


def test_cached_postings_without_identity_are_refetched(tmp_path):
    async def scenario():
        calls = []
        def handle(request):
            calls.append(request)
            return httpx.Response(200, json=PAYLOADS["lever"])
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            cache = portals.ProbeCache(tmp_path / "cache.json")
            resolver = portals.Resolver(client, cache)
            board = portals.board_entry("https://jobs.lever.co/acme")
            cache.put(resolver.probe_key(board), count=1)
            assert await resolver.accept({"name": "Acme"}, board, "slug", "https://acme.example")
            assert len(calls) == 1
            assert await resolver.accept({"name": "Acme"}, board, "slug", "https://acme.example")
            assert len(calls) == 1
    asyncio.run(scenario())
