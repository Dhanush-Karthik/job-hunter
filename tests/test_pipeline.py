"""Intake pipeline: parsers, prefilter rules, dedupe, upsert, restored leads, quick-score order."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select

from jobhunter import paths
from jobhunter.intake.types import RawJob
from jobhunter.models import ApplyChannel, Lead, RoleFamily, Source, WorkMode
from jobhunter.pipeline import ctc, ingest
from jobhunter.pipeline.experience import parse_experience
from jobhunter.pipeline.location import CITIES, cities_in_text, parse_location
from jobhunter.pipeline.normalize import canonical_url, normalize
from jobhunter.pipeline.prefilter import prefilter
from jobhunter.pipeline.score import Scorer
from jobhunter.settings import load_defaults

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
SETTINGS = load_defaults(paths.CONFIG_EXAMPLE)
TARGETS = frozenset({"Chennai", "Bengaluru"})


def raw(ref="1", **kw) -> RawJob:
    base = {"source": Source.naukri, "source_ref": ref, "title": "Java Developer", "company": "Acme",
            "location": "Chennai", "posted_at": NOW - timedelta(days=1), "experience_text": "2-5 Yrs"}
    return RawJob(**{**base, **kw})


def check(**kw):
    return prefilter(normalize(raw(**kw), SETTINGS), SETTINGS, NOW)


def stored(session) -> list[Lead]:
    return list(session.exec(select(Lead).order_by(Lead.id)))


# ---------- location ----------


@pytest.mark.parametrize("text,city,state", [
    ("Chennai, Tamil Nadu, India", "Chennai", None),
    ("Bangalore Urban, Karnataka", "Bengaluru", None),
    ("Greater Chennai Area", "Chennai", None),
    ("Pune, Maharashtra, India", "Pune", None),
    ("TN, India", None, "TN"),
    ("KA, India", None, "KA"),
    ("Tamil Nadu", None, "TN"),
])
def test_location_city_and_state(text, city, state):
    loc = parse_location(text, TARGETS)
    assert (loc.city, loc.state) == (city, state)


def test_location_multi_city_prefers_target():
    assert parse_location("Pune / Bengaluru / Delhi", TARGETS).city == "Bengaluru"


def test_city_mentions_share_location_aliases_and_boundaries():
    assert cities_in_text("Java - SECUNDERABAD / Bangalore / Bengaluru / Madras") == [
        "Hyderabad", "Bengaluru", "Chennai",
    ]
    assert cities_in_text("Java Developer at PuneTech and Bengalurux") == []
    for city, (_, aliases) in CITIES.items():
        assert cities_in_text(f"Java Developer ({city})") == [city]
        for alias in aliases:
            assert cities_in_text(f"Java Developer ({alias.upper()})") == [city]


@pytest.mark.parametrize("city", [city for city in CITIES if city not in TARGETS])
def test_title_non_target_city_overrides_board_location(city):
    result = check(title=f"Java Developer - Angular ({city})", location="Bengaluru")
    assert not result.passed
    assert f"location: title names {city}" in result.reasons


@pytest.mark.parametrize("city,alias", [(city, alias) for city, (_, aliases) in CITIES.items()
                                      if city not in TARGETS for alias in aliases if alias != city.lower()])
def test_title_non_target_city_alias_overrides_board_location(city, alias):
    result = check(title=f"Java Developer - Angular ({alias})", location="Bengaluru")
    assert not result.passed
    assert f"location: title names {city}" in result.reasons


@pytest.mark.parametrize("title", [
    "Java Developer- Angular (Hyderabad)", "Java Developer - Pune", "Java Developer (SECUNDERABAD)",
])
def test_title_location_conflict_drops_even_when_board_marks_remote(title):
    assert not check(title=title, location="Bengaluru", is_remote=True).passed


@pytest.mark.parametrize("title", [
    "Java Developer - Hyderabad / Chennai", "Java Developer - Pune / Bangalore",
    "Java Developer - Hyderabad (Remote)", "Java Developer - Pune - WFH",
    "Java Developer - Pune - Work from home", "Java Developer - Hyderabad - Work from anywhere",
    "Java Developer at PuneTech", "Java Developer",
])
def test_title_target_city_or_remote_keeps_recall(title):
    assert check(title=title, location="Bengaluru").passed


def test_title_location_uses_configured_targets():
    settings = SETTINGS.model_copy(deep=True)
    settings.prefilter.cities = ["Pune"]
    n = normalize(raw(title="Java Developer - Pune", location="Pune"), settings)
    assert prefilter(n, settings, NOW).passed


def test_title_remote_does_not_override_foreign_remote_restrictions():
    result = check(title="Java Developer - Hyderabad - Remote", location="US only", is_remote=True)
    assert not result.passed
    assert "location: remote US-only" in result.reasons


def test_location_pan_india_and_foreign():
    assert parse_location("Anywhere in India", TARGETS).pan_india
    assert parse_location("India", TARGETS).pan_india
    assert not parse_location("Chennai, India", TARGETS).pan_india
    assert parse_location("London, UK", TARGETS).foreign == "London"
    assert parse_location("Nashville, TN", TARGETS).state is None  # TN without India is Tennessee
    assert parse_location("Salem, OR, United States", TARGETS).city is None


def test_normalize_state_level_indeed_location_stays_city_unknown():
    n = normalize(raw(location="TN, India", source=Source.indeed), SETTINGS)
    assert n.loc.city is None and n.location == "TN, India"
    assert "city unknown: TN" in check(location="TN, India").tags


def test_work_mode_and_remote_scope():
    assert normalize(raw(is_remote=True, location="Worldwide"), SETTINGS).work_mode == WorkMode.remote
    assert normalize(raw(location="Chennai (Hybrid)"), SETTINGS).work_mode == WorkMode.hybrid
    assert normalize(raw(description="We run a hybrid cloud platform."), SETTINGS).work_mode == WorkMode.unknown
    assert normalize(raw(description="Work from office, 5 days."), SETTINGS).work_mode == WorkMode.onsite
    scope = lambda **kw: normalize(raw(is_remote=True, **kw), SETTINGS).remote_scope
    assert scope(location="Remote - India") == "india"
    assert scope(location="Worldwide") == "worldwide"
    assert scope(location="Remote", description="Must be based in the United States.") == "us_only"
    assert scope(location="Europe") == "eu_only"
    assert scope(location="Remote") is None


# ---------- experience ----------


@pytest.mark.parametrize("title,desc,exp_text,level,lo,hi", [
    ("Dev", None, "2-5 Yrs", None, 2, 5),
    ("Dev", None, "3+ Years", None, 3, None),
    ("Dev", None, "0-1 Yrs", None, 0, 1),
    ("Dev", "We want 3+ years of experience with Java.", None, None, 3, None),
    ("Dev", "Looking for 2 to 4 yrs experience", None, None, 2, 4),
    ("Dev", "Minimum 5 years in backend work", None, None, 5, None),
    ("Java Developer (3-5 years)", None, None, None, 3, 5),
    ("SDE II", None, None, None, 3, 5),
    ("Software Engineer I", None, None, None, 1, 3),
    ("Senior SDE II", None, None, None, 4, 7),
    ("Senior Java Developer", None, None, None, 5, 9),
    ("Developer", None, None, "Mid-Senior level", 3, 8),
    ("Java Developer 3 years", None, None, None, None, None),  # "3" is not an SDE level here
    ("Member of Technical Staff", None, None, None, None, None),
])
def test_experience_parsing(title, desc, exp_text, level, lo, hi):
    e = parse_experience(title, desc, exp_text, level)
    assert (e.exp_min, e.exp_max) == (lo, hi)
    assert not e.flags


def test_experience_flags():
    assert "intern" in parse_experience("Software Intern", None, None, None).flags
    assert "staff" in parse_experience("Staff Software Engineer", None, None, None).flags
    assert "principal" in parse_experience("Principal Engineer", None, None, None).flags
    assert "fresher" in parse_experience("Java Fresher", None, "0-1 Yrs", None).flags
    assert parse_experience("Dev", None, None, "Mid-Senior level").inferred


# ---------- CTC ----------


def test_ctc_structured():
    assert ctc.from_structured(1_200_000, 1_800_000, "yearly", "INR", 85) == (12.0, 18.0)
    assert ctc.from_structured(90_000, 120_000, "monthly", "INR", 85) == (10.8, 14.4)
    assert ctc.from_structured(100_000, 150_000, "yearly", "USD", 85) == (85.0, 127.5)
    assert ctc.from_structured(60_000, 80_000, "yearly", "INR", 85) == (7.2, 9.6)  # mislabelled monthly
    assert ctc.from_structured(50, 80, "hourly", "USD", 85) == (None, None)
    assert ctc.from_structured(None, None, None, None, 85) == (None, None)


@pytest.mark.parametrize("text,expected", [
    ("10-15 LPA", (10, 15)),
    ("18 LPA", (18, 18)),
    ("₹12,00,000 - ₹18,00,000", (12, 18)),
    ("Rs. 50,000 - 80,000 per month", (6, 9.6)),
    ("$120k - $150k", (102, 127.5)),
    ("up to 20 LPA", (None, 20)),
    ("12 LPA+", (12, None)),
    ("₹12L - ₹18L", (12, 18)),
    ("Not disclosed", (None, None)),
])
def test_ctc_text(text, expected):
    assert ctc.parse_text(text, 85, strict=False) == expected


def test_ctc_description_needs_context():
    assert ctc.parse_text("We raised $50M and have ₹500 Cr revenue.", 85, strict=True) == (None, None)
    assert ctc.parse_text("CTC: ₹14,00,000 - ₹20,00,000 per annum", 85, strict=True) == (14, 20)
    n = normalize(raw(description="Salary 20-28 LPA based on skills"), SETTINGS)
    assert (n.ctc_min, n.ctc_max) == (20, 28)


# ---------- role family, channel, urls ----------


@pytest.mark.parametrize("title,skills,desc,family", [
    ("Java Developer", [], None, RoleFamily.p1),
    ("Backend Engineer", [], None, RoleFamily.p1),
    ("Software Engineer II", ["Spring Boot"], None, RoleFamily.p1),
    ("Software Engineer II", [], "We use Keycloak for identity", RoleFamily.p2),
    ("Platform Engineer", [], None, RoleFamily.p2),
    ("Identity & Access Management Engineer", [], None, RoleFamily.p2),
    ("Keycloak Specialist", [], None, RoleFamily.p2),
    ("AI Backend Engineer", [], None, RoleFamily.p2),
    ("Frontend Developer", ["Java"], None, RoleFamily.other),
    ("Sales Manager", [], None, RoleFamily.other),
])
def test_role_family(title, skills, desc, family):
    assert normalize(raw(title=title, skills=skills, description=desc), SETTINGS).role_family == family


def test_apply_channel():
    ch = lambda **kw: normalize(raw(**kw), SETTINGS).apply_channel
    assert ch(easy_apply=True) == ApplyChannel.platform_quick
    assert ch(apply_url="https://boards.greenhouse.io/acme/jobs/123") == ApplyChannel.company_ats
    assert ch(apply_url="https://acme.wd5.myworkdayjobs.com/en-US/careers/job/Chennai/X_R1") == ApplyChannel.company_ats
    assert ch(apply_url="mailto:hr@acme.com") == ApplyChannel.email
    assert ch(source=Source.gmail_inbound) == ApplyChannel.email
    assert ch(apply_url="https://acme.com/careers") == ApplyChannel.unknown


def test_canonical_url():
    assert (canonical_url("HTTPS://WWW.Example.COM/jobs/1/?utm_source=x&refId=2&trackingId=3&id=9#frag")
            == "https://example.com/jobs/1?id=9")
    assert (canonical_url("https://in.linkedin.com/jobs/view/java-dev-at-acme-3912345678?refId=a&trk=b")
            == "https://linkedin.com/jobs/view/3912345678")
    assert canonical_url("https://in.indeed.com/viewjob?jk=abc&from=serp") == "https://in.indeed.com/viewjob?jk=abc"
    assert canonical_url("mailto:a@b.com") is None and canonical_url(None) is None


# ---------- prefilter rules ----------


def test_prefilter_passes_good_lead():
    r = check(skills=["Java"])
    assert r.passed and r.reasons == [] and "CTC unknown" in r.tags


@pytest.mark.parametrize("kw,reason", [
    ({"location": "Pune"}, "location: Pune"),
    ({"location": "MH, India", "source": Source.indeed}, "location: MH"),
    ({"location": "London, United Kingdom"}, "location: London"),
    ({"is_remote": True, "location": "USA Only"}, "location: remote US-only"),
    ({"is_remote": True, "location": "Europe"}, "location: remote EU/UK-only"),
    ({"experience_text": "8-12 Yrs"}, "experience: min 8 >= 6"),
    ({"experience_text": "0-1 Yrs"}, "experience: max 1 < 2"),
    ({"title": "Staff Software Engineer", "experience_text": None}, "experience: staff level"),
    ({"title": "Java Intern", "experience_text": None}, "experience: intern"),
    ({"salary_text": "4-6 LPA"}, "ctc: max 6.0 LPA < 10"),
    ({"title": "React Developer", "skills": ["React"]}, "stack: react developer"),
    ({"title": "Android Developer", "skills": ["Kotlin"]}, "stack: android"),
    ({"title": "PHP Developer", "skills": ["PHP"]}, "stack: php"),
    ({"posted_at": NOW - timedelta(days=41)}, "stale: 41 days"),
])
def test_prefilter_drop_reasons(kw, reason):
    r = check(**kw)
    assert not r.passed and reason in r.reasons


@pytest.mark.parametrize("kw,tag", [
    ({"location": "KA, India", "source": Source.indeed}, "city unknown: KA"),
    ({"location": "Some Place"}, "city unknown: Some Place"),
    ({"location": "India"}, "pan-India"),
    ({"is_remote": True, "location": "Remote"}, "remote scope unknown"),
    ({"experience_text": None}, "exp unknown"),
    ({"posted_at": None}, "posted date unknown"),
    ({"posted_at": NOW - timedelta(days=20)}, "aging: 20 days"),
])
def test_prefilter_unknowns_pass_with_tag(kw, tag):
    r = check(**kw)
    assert r.passed and tag in r.tags


def test_prefilter_recall_first_edges():
    assert check(experience_text="5-8 Yrs").passed  # min 5 is below the 6 cut
    assert check(title="Senior SDE II", experience_text=None).passed  # inferred ranges never drop
    assert check(title="Java Full Stack Developer (React + Java)", skills=["React", "Java"]).passed
    assert check(title="Full Stack Developer", skills=["React", "Node"]).passed
    assert check(is_remote=True, location="Worldwide").passed
    assert check(is_remote=True, location="Remote - India").passed
    assert check(location="Chennai / Pune").passed
    assert check(salary_text="12 LPA").passed
    assert check(title="Java Developer", experience_text="2-4 Yrs", location="Chennai, Tamil Nadu, India",
                 salary_min=85_000, salary_max=120_000, salary_interval="monthly", currency="INR").passed


# ---------- dedupe ----------


def test_dedupe_same_canonical_url(session):
    a = raw("a", source=Source.linkedin, job_url="https://www.linkedin.com/jobs/view/3912345678?trk=x")
    b = raw("b", source=Source.indeed, company="Totally Other", title="Other Title",
            job_url="https://in.linkedin.com/jobs/view/java-3912345678?refId=y")
    res = ingest(session, [a, b], SETTINGS, now=NOW, cv_text="")
    leads = stored(session)
    assert res.new == 2 and res.duplicates == 1
    assert leads[0].dedupe_group == leads[1].dedupe_group == f"d{leads[0].id}"


def test_dedupe_cross_source_fuzzy(session):
    rows = [
        raw("a", source=Source.linkedin, title="Software Engineer II", company="Nimbus Labs",
            location="Chennai, Tamil Nadu, India"),
        raw("b", source=Source.indeed, title="Software Engineer II", company="Nimbus Labs Pvt Ltd",
            location="TN, India"),
        raw("c", source=Source.naukri, title="Sr. Java Engineer", company="Corvus Pay", location="Bengaluru"),
        raw("d", source=Source.glassdoor, title="Senior Java Engineer", company="Corvus Pay Technologies",
            location="Bengaluru, Karnataka"),
    ]
    res = ingest(session, rows, SETTINGS, now=NOW, cv_text="")
    g = [ld.dedupe_group for ld in stored(session)]
    assert g[0] == g[1] and g[2] == g[3] and g[0] != g[2]
    assert res.duplicates == 2


def test_dedupe_precision_near_misses(session):
    rows = [
        raw("1", title="Software Engineer II", company="Nimbus Labs", location="Chennai"),
        raw("2", title="Software Engineer III", company="Nimbus Labs", location="Chennai"),  # other level
        raw("3", title="Software Engineer II", company="Nimbus Labs", location="Bengaluru"),  # other city
        raw("4", title="Senior Software Engineer II", company="Nimbus Labs", location="Chennai"),  # seniority
        raw("5", title="Software Engineer II", company="Nimbus Systems Group", location="Chennai"),  # same brand
        raw("6", title="Software Engineer II", company="Nova Labs", location="Chennai"),  # other company
        raw("7", title="Software Engineer II", company="Nimbus Labs", location=None),  # unknown place
        raw("8", title="Java Developer", company="Acme", location="Coimbatore, TN, India",
            source=Source.indeed),
        raw("9", title="Java Developer", company="Acme", location="KA, India", source=Source.indeed),
    ]
    ingest(session, rows, SETTINGS, now=NOW, cv_text="")
    groups = [ld.dedupe_group for ld in stored(session)]
    assert len(set(groups)) == len(groups)  # nothing merges
    assert groups[0] != groups[1] and groups[0] != groups[2] and groups[0] != groups[3]
    assert groups[0] != groups[5] and groups[0] != groups[6] and groups[7] != groups[8]


def test_dedupe_bare_ats_listing_url_does_not_group(session):
    rows = [raw("a", title="Java Developer", company="Acme", apply_url="https://boards.greenhouse.io/acme"),
            raw("b", title="Data Analyst", company="Other", apply_url="https://boards.greenhouse.io/acme",
                location="Chennai", source=Source.linkedin)]
    ingest(session, rows, SETTINGS, now=NOW, cv_text="")
    a, b = stored(session)
    assert a.dedupe_group != b.dedupe_group


def test_dedupe_joins_group_across_ingest_calls(session):
    ingest(session, [raw("a", source=Source.linkedin, company="Nimbus Labs", title="SDE 2")], SETTINGS, now=NOW,
           cv_text="")
    res = ingest(session, [raw("b", source=Source.naukri, company="Nimbus Labs Pvt Ltd", title="SDE II")], SETTINGS,
                 now=NOW, cv_text="")
    a, b = stored(session)
    assert res.duplicates == 1 and a.dedupe_group == b.dedupe_group


# ---------- upsert / store ----------


def test_upsert_is_idempotent_and_refreshes(session):
    first = raw("a", description=None, salary_text=None)
    res1 = ingest(session, [first], SETTINGS, now=NOW, cv_text="")
    lead = stored(session)[0]
    found, group = lead.found_at, lead.dedupe_group
    again = raw("a", description="Salary 20-28 LPA", title="Java Developer ")
    res2 = ingest(session, [again, again], SETTINGS, now=NOW + timedelta(hours=3), cv_text="")
    leads = stored(session)
    assert (res1.new, res1.updated) == (1, 0) and (res2.new, res2.updated) == (0, 2)
    assert len(leads) == 1 and res2.lead_ids == [lead.id]
    assert leads[0].dedupe_group == group and leads[0].found_at == found
    assert (leads[0].ctc_min, leads[0].ctc_max) == (20, 28) and leads[0].title == "Java Developer"


def test_refetch_without_fields_keeps_known_values(session):
    ingest(session, [raw("a", description="CTC 18-24 LPA. 3+ years of experience.", experience_text=None)],
           SETTINGS, now=NOW, cv_text="")
    ingest(session, [raw("a", description=None, experience_text=None, posted_at=None)], SETTINGS, now=NOW,
           cv_text="")
    lead = stored(session)[0]
    assert (lead.ctc_max, lead.exp_min) == (24, 3) and lead.jd_text and lead.posted_at is not None


def test_ingest_fills_all_fields_and_counts(session):
    rows = [
        raw("ok", skills=["Java", "Spring Boot"], salary_text="15-20 LPA", easy_apply=True,
            source_detail="java chennai"),
        raw("pune", location="Pune"),
        raw("dup", source=Source.indeed, location="TN, India", title="Java Developer", company="Acme"),
    ]
    res = ingest(session, rows, SETTINGS, now=NOW, cv_text="")
    assert (res.fetched, res.new, res.updated, res.duplicates, res.dropped) == (3, 3, 0, 1, 1)
    assert res.lead_ids == [ld.id for ld in stored(session)]
    ok, pune, dup = stored(session)
    assert ok.location == "Chennai" and ok.role_family == RoleFamily.p1 and ok.apply_channel == ApplyChannel.platform_quick
    assert (ok.ctc_min, ok.ctc_max, ok.exp_min, ok.exp_max) == (15, 20, 2, 5)
    assert ok.found_at.replace(tzinfo=UTC) == NOW and ok.source_detail == "java chennai" and ok.raw == {}
    assert ok.dedupe_group == dup.dedupe_group and pune.dedupe_group != ok.dedupe_group
    assert not pune.prefilter_pass and pune.prefilter_reasons == ["location: Pune"]
    assert dup.prefilter_tags[0] == "city unknown: TN" and dup.prefilter_pass


def test_restored_lead_keeps_passing_on_update(session):
    ingest(session, [raw("p", location="Pune")], SETTINGS, now=NOW, cv_text="")
    lead = stored(session)[0]
    assert not lead.prefilter_pass
    lead.restored = True
    session.add(lead)
    session.commit()
    res = ingest(session, [raw("p", location="Pune")], SETTINGS, now=NOW, cv_text="")
    lead = stored(session)[0]
    assert res.updated == 1 and lead.prefilter_pass and lead.restored
    assert lead.prefilter_reasons == ["location: Pune"]  # the audit trail stays


def test_update_can_flip_to_dropped_when_not_restored(session):
    ingest(session, [raw("x")], SETTINGS, now=NOW, cv_text="")
    assert stored(session)[0].prefilter_pass
    ingest(session, [raw("x", posted_at=NOW - timedelta(days=45))], SETTINGS, now=NOW, cv_text="")
    assert not stored(session)[0].prefilter_pass


def test_naive_datetimes_are_treated_as_utc(session):
    ingest(session, [raw("n", posted_at=datetime(2026, 11, 11, 12, 0))], SETTINGS, now=NOW, cv_text="")
    ingest(session, [raw("n", posted_at=None)], SETTINGS, now=NOW, cv_text="")  # reads naive value back from SQLite
    assert stored(session)[0].prefilter_pass


# ---------- quick score ----------


def score(scorer=None, **kw):
    n = normalize(raw(**kw), SETTINGS)
    r = raw(**kw)
    return (scorer or Scorer(SETTINGS, "")).score(
        title=n.title, skills=n.skills, description=n.description, role_family=n.role_family, source=r.source,
        is_inbound=r.is_inbound, posted_at=n.posted_at, found_at=NOW, now=NOW)


def test_score_is_deterministic_and_bounded():
    kw = {"skills": ["Java", "Spring Boot", "Kafka"], "title": "Java Backend Engineer"}
    assert score(**kw) == score(**kw)
    assert 0 <= score(**kw) <= 1


def test_score_ordering_sanity():
    java = {"title": "Java Backend Engineer", "skills": ["Java", "Spring Boot", "Kafka", "Microservices"]}
    fresh_p1 = score(**java)
    stale_p1 = score(**java, posted_at=NOW - timedelta(days=8))
    p2 = score(title="Platform Engineer", skills=["Kubernetes"])
    other = score(title="Accountant", skills=["Tally"], location="Chennai")
    assert fresh_p1 > stale_p1 > other
    assert fresh_p1 > p2 > other
    assert score(**java, posted_at=NOW - timedelta(hours=10)) > score(**java, posted_at=NOW - timedelta(hours=60))
    assert score(**java, posted_at=NOW - timedelta(days=30)) <= stale_p1


def test_score_source_weight_and_inbound_boost():
    kw = {"title": "Java Developer", "skills": ["Java"], "posted_at": NOW - timedelta(days=5)}
    assert score(source=Source.careerops_scan, **kw) > score(source=Source.linkedin, **kw) > score(
        source=Source.indeed, **kw)
    assert score(source=Source.gmail_inbound, is_inbound=True, **kw) > score(source=Source.gmail_alert, **kw) + 0.25


def test_score_uses_cv_vocabulary():
    cv = "Skills: Keycloak, OAuth2, OIDC, Java"
    cv_scorer = Scorer(SETTINGS, cv)
    iam = {"title": "Software Engineer", "skills": ["Keycloak", "OIDC"], "posted_at": NOW - timedelta(days=5)}
    kafka = {"title": "Software Engineer", "skills": ["Kafka", "Kubernetes"], "posted_at": NOW - timedelta(days=5)}
    assert score(cv_scorer, **iam) > score(cv_scorer, **kafka)


def test_keyword_overlap_keeps_resolution_above_nine_hits():
    scorer = Scorer(SETTINGS, "")
    nine = " ".join(scorer.vocab[:9])
    more = " ".join(scorer.vocab)
    assert 0 < scorer.keyword_overlap("Developer", [], nine) < scorer.keyword_overlap("Developer", [], more) < 1
    assert scorer.keyword_overlap("Developer", [], more) == scorer.keyword_overlap("Developer", [], more * 20)


def test_keyword_repetitions_and_skill_duplicates_do_not_add_score():
    scorer = Scorer(SETTINGS, "")
    assert scorer.keyword_overlap("Java Developer", ["Java"], "Java " * 100) == scorer.keyword_overlap(
        "Java Developer", ["Java", "Java"], "Java",
    )


@pytest.mark.parametrize("title", [
    "Java Developer", "Spring Boot Developer", "Java Backend Engineer", "Java Springboot Backend Engineer",
    "IAM Engineer", "Keycloak Developer", "Identity & Access Management Engineer",
])
def test_target_title_signals_outweigh_same_terms_in_jd(title):
    description = f"{title}. Java Spring Boot backend microservices Keycloak IAM. 2-4 years experience."
    assert score(title=title, description=description) > score(title="Software Engineer", description=description)


def test_java_title_does_not_match_javascript():
    assert score(title="Java Developer", description="Java") > score(title="JavaScript Developer", description="Java")


@pytest.mark.parametrize("level", ["Lead", "Senior Associate", "Staff", "Principal", "Architect", "Manager", "Senior", "Sr."])
def test_seniority_titles_rank_below_same_individual_contributor_role(level):
    common = {"description": "Java Spring Boot backend. 3 years of experience."}
    assert score(title=f"{level} Java Backend Engineer", **common) < score(title="Java Backend Engineer", **common)


@pytest.mark.parametrize("title", ["Java .NET Developer", "Java Angular Developer", "Java Full Stack Developer"])
def test_mixed_stack_titles_rank_below_java_role(title):
    common = {"description": "Java Spring Boot microservices. 2-4 years experience.", "skills": ["Java"]}
    assert score(title=title, **common) < score(title="Java Developer", **common)


def test_full_stack_with_backend_emphasis_avoids_full_stack_penalty():
    common = {"description": "Java Spring Boot backend. 2-4 years experience."}
    assert score(title="Java Backend Full Stack Developer", **common) == score(title="Java Backend Developer", **common)


def test_iam_adds_small_bonus_when_cv_vocabulary_does_not_include_it():
    scorer = Scorer(SETTINGS, "Java Spring Boot")
    common = {"title": "Java Developer"}
    assert score(scorer, description="Backend services using Keycloak", **common) > score(
        scorer, description="Backend services", **common,
    )


def test_stated_experience_fit_bonus_uses_owner_range():
    common = {"title": "Java Backend Developer"}
    unknown = score(description="Java Spring Boot backend", **common)
    assert score(description="Java Spring Boot backend. 2-4 years experience.", **common) > unknown
    assert score(description="Java Spring Boot backend. 3+ years experience.", **common) > unknown
    assert score(description="Java Spring Boot backend. 5+ years experience.", **common) < unknown
    assert score(description="Java Spring Boot backend. 0-1 years experience.", **common) == unknown
    settings = SETTINGS.model_copy(deep=True)
    settings.prefilter.exp_years = (5, 7)
    scorer = Scorer(settings, "")
    assert score(scorer, description="5-7 years experience.", **common) > score(
        scorer, description="2-4 years experience.", **common,
    )


def test_postings_asking_more_years_than_the_owner_has_rank_lower_the_more_they_ask():
    common = {"title": "Java Backend Developer"}
    by_min = {m: score(description=f"Java Spring Boot backend. {m}+ years experience.", **common) for m in (2, 3, 4, 5, 6, 7, 8, 12)}
    assert by_min[2] == by_min[3]  # inside the owner's 2-4 range: no penalty
    assert by_min[3] > by_min[4] > by_min[5] > by_min[6] > by_min[7] > 0  # then the penalty grows
    assert by_min[7] == by_min[8] == by_min[12]  # until the multiplier hits its 40% floor


def test_structured_experience_beats_what_the_description_says():
    scorer = Scorer(SETTINGS, "")
    kw = {"title": "Java Backend Developer", "skills": [], "description": "Java Spring Boot backend", "role_family": RoleFamily.p1,
              "source": Source.naukri, "is_inbound": False, "posted_at": NOW, "found_at": NOW, "now": NOW}
    fits = scorer.score(exp=parse_experience("x", None, "2-4 Yrs", None), **kw)
    stretch = scorer.score(exp=parse_experience("x", None, "5-9 Yrs", None), **kw)
    assert stretch < fits


def test_exp_fit_labels_against_owner_range():
    from jobhunter.pipeline.experience import exp_fit

    assert [exp_fit(m, None, (2, 4)) for m in (None, 2, 3, 4, 5, 8)] == ["unknown", "ok", "ok", "stretch", "above", "above"]
    assert exp_fit(None, 6, (2, 4)) == "ok"


def test_rescore_applies_the_current_rules_to_stored_leads(session):
    settings = SETTINGS.model_copy(deep=True)
    raw = [
        RawJob(source=Source.naukri, source_ref="n1", title="Java Backend Developer", company="A", location="Chennai",
               description="Java Spring Boot backend", experience_text="5-9 Yrs", posted_at=NOW),
        RawJob(source=Source.naukri, source_ref="n2", title="Java Backend Developer", company="B", location="Chennai",
               description="Java Spring Boot backend", experience_text="2-4 Yrs", posted_at=NOW),
    ]
    ingest(session, raw, settings, now=NOW, cv_text="")
    before = {lead.source_ref: lead.quick_score for lead in session.exec(select(Lead))}
    assert before["n1"] < before["n2"]
    from jobhunter.pipeline import rescore

    settings.prefilter.exp_years = (5, 9)  # the owner now wants senior roles
    assert rescore(session, settings, now=NOW, cv_text="") == 2
    after = {lead.source_ref: lead.quick_score for lead in session.exec(select(Lead))}
    assert after["n1"] > after["n2"]
    assert rescore(session, settings, now=NOW, cv_text="") == 0  # idempotent


def test_ctc_bonus_is_small_and_requires_salary_evidence():
    common = {"title": "Java Backend Developer"}
    unknown = score(description="Java Spring Boot backend", **common)
    paid = score(description="Java Spring Boot backend. Salary 12-18 LPA.", **common)
    assert 0 < paid - unknown <= 0.031
    assert score(description="Java Spring Boot backend. Salary 5-8 LPA.", **common) == unknown
    assert score(description="Java Spring Boot backend. We raised $50M and have ₹500 Cr revenue.", **common) == unknown


def test_inbound_adds_exact_same_boost_after_weighting():
    common = {"title": "Java Developer", "source": Source.gmail_alert, "posted_at": NOW - timedelta(days=8)}
    assert score(is_inbound=True, **common) == pytest.approx(score(is_inbound=False, **common) + .30, abs=.0001)


@pytest.mark.parametrize("weight", [-10, 0, 1, 10])
def test_score_clamps_even_with_extreme_source_weights(weight):
    settings = SETTINGS.model_copy(deep=True)
    settings.source_weights["naukri"] = weight
    scorer = Scorer(settings, "")
    value = score(scorer, title="Java Spring Boot Backend Engineer", description="2-4 years experience. Salary 12-18 LPA.")
    assert 0 <= value <= 1


def test_ingest_stores_title_location_conflict_and_respects_restore(session):
    posting = raw("conflict", title="Java Developer - Hyderabad", location="Bengaluru")
    result = ingest(session, [posting], SETTINGS, now=NOW, cv_text="")
    row = stored(session)[0]
    assert result.dropped == 1 and not row.prefilter_pass
    assert row.prefilter_reasons == ["location: title names Hyderabad"]
    row.restored = True
    session.add(row)
    session.commit()
    ingest(session, [posting], SETTINGS, now=NOW, cv_text="")
    assert stored(session)[0].prefilter_pass
    assert stored(session)[0].prefilter_reasons == ["location: title names Hyderabad"]


# ---------- unparseable URLs ----------

BAD_URLS = ["http://[", "https://[::1", "http://[abc", "ht tp://[x]/y"]


@pytest.mark.parametrize("url", BAD_URLS)
def test_unparseable_url_is_unusable_not_fatal(url):
    assert canonical_url(url) is None


def test_ingest_survives_malformed_urls(session):
    rows = [raw("bad1", job_url="http://[", apply_url="http://[", title="Java Developer"),
            raw("bad2", job_url="https://[::1", apply_url="http://[abc", title="Backend Engineer"),
            raw("ok", job_url="https://www.naukri.com/job-listings-java-123456")]
    res = ingest(session, rows, SETTINGS, now=NOW, cv_text="")
    assert res.new == 3 and res.fetched == 3
    leads = {lead.source_ref: lead for lead in stored(session)}
    assert set(leads) == {"bad1", "bad2", "ok"}
    assert leads["bad1"].canonical_url is None and leads["ok"].canonical_url is not None
    assert ingest(session, rows[:1], SETTINGS, now=NOW, cv_text="").updated == 1  # refetch is fine too
