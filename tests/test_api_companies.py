"""/api/companies on a temp portals.yml (paths.CAREEROPS_DATA is pointed at tmp_path by the engine fixture)."""

import threading
from urllib.parse import quote

import pytest
import yaml

from jobhunter import paths

pytest_plugins = ["apihelpers"]

PORTALS = """\
tracked_companies:
- name: Freshworks
  careers_url: https://careers.smartrecruiters.com/Freshworks
  enabled: true
  provider: smartrecruiters
- name: Zoho
  careers_url: https://www.zoho.com/careers/
  enabled: false
  scan_method: websearch
  scan_query: site:www.zoho.com/careers/ "Zoho" (Java OR backend OR "software engineer") India
  notes: ATS unresolved
title_filter:
  positive:
  - Java
  - Backend
location_filter:
  allow:
  - Chennai
job_boards:
  remotive: true
"""


@pytest.fixture()
def portals(engine):
    path = paths.CAREEROPS_DATA / "portals.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PORTALS)
    return path


def on_disk(portals):
    return yaml.safe_load(portals.read_text())


def test_list_in_file_order_with_defaults(client, portals):
    r = client.get("/api/companies")
    assert r.status_code == 200
    assert r.json() == [
        {"name": "Freshworks", "careers_url": "https://careers.smartrecruiters.com/Freshworks", "enabled": True,
         "provider": "smartrecruiters", "notes": None},
        {"name": "Zoho", "careers_url": "https://www.zoho.com/careers/", "enabled": False, "provider": None,
         "notes": "ATS unresolved"},
    ]


def test_list_is_empty_without_a_file(client, engine):
    assert not (paths.CAREEROPS_DATA / "portals.yml").exists()
    assert client.get("/api/companies").json() == []


def test_entries_without_a_name_are_skipped_but_kept(client, portals):
    portals.write_text("tracked_companies:\n- just a string\n- {careers_url: https://x.example/jobs}\n"
                       "- {name: Real, careers_url: 'https://real.example/careers'}\n")
    assert [c["name"] for c in client.get("/api/companies").json()] == ["Real"]
    client.patch("/api/companies/Real", json={"enabled": False})
    assert on_disk(portals)["tracked_companies"][:2] == ["just a string", {"careers_url": "https://x.example/jobs"}]


def test_add_appends_a_websearch_entry_and_keeps_everything_else(client, portals):
    before = on_disk(portals)
    r = client.post("/api/companies", json={"name": "  Acme Corp ", "careers_url": "https://acme.example/careers"})
    assert r.status_code == 201
    assert r.json() == {"name": "Acme Corp", "careers_url": "https://acme.example/careers", "enabled": True,
                        "provider": None, "notes": "Added from the dashboard."}
    after = on_disk(portals)
    assert after["tracked_companies"][:2] == before["tracked_companies"]  # order and unmodeled keys untouched
    entry = after["tracked_companies"][2]
    assert entry["scan_method"] == "websearch" and "provider" not in entry
    assert entry["scan_query"] == 'site:acme.example/careers "Acme Corp" (Java OR backend OR "software engineer") India'
    for key in ("title_filter", "location_filter", "job_boards"):
        assert after[key] == before[key]
    assert list(after) == list(before)  # top-level key order preserved
    assert [c["name"] for c in client.get("/api/companies").json()] == ["Freshworks", "Zoho", "Acme Corp"]


def test_add_creates_the_file_when_missing(client, engine):
    r = client.post("/api/companies", json={"name": "First", "careers_url": "https://first.example/jobs"})
    assert r.status_code == 201
    assert yaml.safe_load((paths.CAREEROPS_DATA / "portals.yml").read_text())["tracked_companies"][0]["name"] == "First"


@pytest.mark.parametrize("name", ["zoho", "ZOHO", " Zoho "])
def test_add_duplicate_name_is_409_case_insensitively(client, portals, name):
    r = client.post("/api/companies", json={"name": name, "careers_url": "https://zoho.example/careers"})
    assert r.status_code == 409
    assert len(on_disk(portals)["tracked_companies"]) == 2


@pytest.mark.parametrize("body", [
    {"name": "", "careers_url": "https://acme.example/careers"},
    {"name": "Acme", "careers_url": "short"},
    {"name": "Acme", "careers_url": "ftp://acme.example/careers"},
    {"name": "Acme", "careers_url": "https:///nohost"},
    {"name": "   ", "careers_url": "https://acme.example/careers"},
])
def test_add_validation(client, portals, body):
    assert client.post("/api/companies", json=body).status_code == 422
    assert portals.read_text() == PORTALS


def test_patch_enabled_and_url_case_insensitive_name(client, portals):
    r = client.patch("/api/companies/zoho", json={"enabled": True, "careers_url": "https://zoho.example/jobs"})
    assert r.status_code == 200
    assert r.json()["enabled"] is True and r.json()["careers_url"] == "https://zoho.example/jobs"
    zoho = on_disk(portals)["tracked_companies"][1]
    assert zoho["enabled"] is True and zoho["notes"] == "ATS unresolved"
    assert zoho["scan_query"].startswith('site:zoho.example/jobs "Zoho"')  # websearch scope follows the URL
    assert on_disk(portals)["tracked_companies"][0]["name"] == "Freshworks"


def test_patch_empty_body_changes_nothing(client, portals):
    r = client.patch("/api/companies/Zoho", json={})
    assert r.status_code == 200 and r.json()["name"] == "Zoho"
    assert portals.read_text() == PORTALS


def test_patch_handles_url_encoded_names(client, portals):
    client.post("/api/companies", json={"name": "Two Words & Co", "careers_url": "https://two.example/careers"})
    r = client.patch(f"/api/companies/{quote('two words & co')}", json={"enabled": False})
    assert r.status_code == 200 and r.json()["enabled"] is False


def test_patch_bad_url_is_422_and_unknown_is_404(client, portals):
    assert client.patch("/api/companies/Zoho", json={"careers_url": "not a url"}).status_code == 422
    assert client.patch("/api/companies/Nobody", json={"enabled": False}).status_code == 404
    assert portals.read_text() == PORTALS


def test_delete(client, portals):
    r = client.delete("/api/companies/FRESHWORKS")
    assert r.status_code == 204 and r.content == b""
    assert [c["name"] for c in on_disk(portals)["tracked_companies"]] == ["Zoho"]
    assert client.delete("/api/companies/Freshworks").status_code == 404
    assert on_disk(portals)["job_boards"] == {"remotive": True}


def test_delete_missing_file_is_404(client, engine):
    assert client.delete("/api/companies/Zoho").status_code == 404


def test_writes_are_atomic_and_leave_no_temp_files(client, portals, monkeypatch):
    client.post("/api/companies", json={"name": "Acme", "careers_url": "https://acme.example/careers"})
    assert sorted(p.name for p in portals.parent.iterdir()) == ["portals.yml"]
    original = portals.read_text()

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr("jobhunter.api.companies.os.replace", boom)
    with pytest.raises(OSError):
        client.post("/api/companies", json={"name": "Other", "careers_url": "https://other.example/careers"})
    assert portals.read_text() == original  # the real file was never half-written
    assert sorted(p.name for p in portals.parent.iterdir()) == ["portals.yml"]


def test_concurrent_adds_do_not_lose_entries(client, portals):
    def add(i):
        assert client.post("/api/companies", json={
            "name": f"Co{i}", "careers_url": f"https://co{i}.example/careers"}).status_code == 201

    threads = [threading.Thread(target=add, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    names = [c["name"] for c in on_disk(portals)["tracked_companies"]]
    assert sorted(names[2:]) == sorted(f"Co{i}" for i in range(8)) and len(names) == 10


def test_invalid_yaml_is_500_not_a_crash(client, portals):
    portals.write_text("tracked_companies: [unclosed\n")
    r = client.get("/api/companies")
    assert r.status_code == 500 and "portals.yml" in r.json()["detail"]
    portals.write_text("- a list\n- not a mapping\n")
    assert client.get("/api/companies").status_code == 500
