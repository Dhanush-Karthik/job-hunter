"""Quick score, deterministic, in [0, 1]. Orders every lead; the top N get the LLM evaluation.

    base = .28*kw + .20*role + .15*fresh + .05*hot + .20*title + .07*exp + .03*ctc + .02*iam
           - .06*seniority - .06*mixed
    score = clamp(base * source_weight)                 # settings.source_weights[source], default 1.0
    if is_inbound: score = clamp(score + 0.30)          # unchanged recruiter boost, after source weighting

  kw    CV keyword overlap. Vocabulary = known tech terms present in the CV, or stack_positive without a CV.
        A distinct term counts 2 in title/skills or 1 in the JD; repetitions never add hits. Use
        weighted_hits / (weighted_hits + vocabulary_size), so nine hits cannot saturate the score.
  title min(1, .35*Java + .30*Spring + .35*backend + .40*IAM/Keycloak/identity); title signals are independent
        of CV overlap. Springboot, back-end, CIAM and identity & access management aliases count.
  role  P1 = 1.0, P2 = 0.6, other = 0.15.
  fresh 1.0 up to 48 h old, then linear decay to 0 at 9 days (about 7 days of decay). Age is measured from
        posted_at, or found_at when the posting has no date. hot = 1 before 48 h, otherwise 0.
  exp   1 for stated experience overlapping settings.prefilter.exp_years (owner: 2-4), .5 for inferred title
        levels that overlap, 0 for unknown/outside that range. Uses the shared experience parser.
  ctc   1 when stated minimum pay is at least settings.prefilter.ctc_min_lpa; otherwise 0. Uses the shared
        salary parser with salary context required, so company revenue never adds a bonus.
  iam   1 when Keycloak/IAM/identity-access signals occur in title, skills or JD; otherwise 0.
  seniority 1 for lead, senior/sr (including senior associate), staff, principal, architect or manager titles.
  mixed 1 for .NET/Angular titles or full-stack titles without backend/Spring/microservices emphasis.

Experience and pay bonuses use title/JD evidence: the existing scorer caller does not pass structured fields.
All components are bounded; clamp means [0, 1], and rounding is to four decimals. No location bonus: the
prefilter already admits the owner's cities and remote roles, and uncertain locations remain recall-first.

Same inputs and `now` always give the same score.
"""

from __future__ import annotations

import re
from datetime import datetime

from jobhunter import paths
from jobhunter.models import RoleFamily, Source
from jobhunter.pipeline import ctc
from jobhunter.pipeline.experience import parse_experience
from jobhunter.pipeline.normalize import as_utc
from jobhunter.pipeline.prefilter import positive_terms
from jobhunter.schemas import Settings

TECH_TERMS = [
    "java", "spring", "spring boot", "spring cloud", "spring security", "hibernate", "jpa", "quarkus",
    "micronaut", "kotlin", "scala", "microservices", "rest api", "grpc", "graphql", "kafka", "rabbitmq",
    "redis", "elasticsearch", "postgresql", "mysql", "mongodb", "cassandra", "oracle", "sql", "nosql",
    "docker", "kubernetes", "openshift", "helm", "terraform", "ansible", "jenkins", "ci/cd", "gitlab",
    "aws", "azure", "gcp", "linux", "maven", "gradle", "junit", "mockito", "keycloak", "iam", "oauth", "oidc",
    "saml", "sso", "ldap", "jwt", "mfa", "identity", "nevis", "python", "go", "golang", "node.js", "typescript",
    "backend", "platform", "jvm", "api gateway", "design patterns", "system design", "agile", "llm", "rag",
]
_FRESH_BOOST_HOURS = 48
_FRESH_ZERO_DAYS = 9
_ROLE_WEIGHT = {RoleFamily.p1: 1.0, RoleFamily.p2: 0.6, RoleFamily.other: 0.15}
_JAVA = re.compile(r"\bjava\b|\bj2ee\b", re.IGNORECASE)
_SPRING = re.compile(r"\bspring(?:[\s-]*boot)?\b", re.IGNORECASE)
_BACKEND = re.compile(r"\bback[\s-]?end\b|\bmicroservices?\b", re.IGNORECASE)
_IAM = re.compile(r"\b(?:keycloak|ciam|iam)\b|\bidentity\s*(?:&|and)?\s*(?:access\s*)?management\b",
                  re.IGNORECASE)
_SENIORITY = re.compile(r"\b(?:lead|senior|sr|staff|principal|architect|manager)\b", re.IGNORECASE)
_MIXED = re.compile(r"(?<!\w)\.?net\b|\bangular(?:\.?js)?\b", re.IGNORECASE)
_FULL_STACK = re.compile(r"\bfull[\s-]?stack\b", re.IGNORECASE)


def read_default_cv() -> str | None:
    p = paths.CV_DIR / "cv_a.md"
    return p.read_text(errors="replace") if p.exists() else None


class Scorer:
    def __init__(self, settings: Settings, cv_text: str | None = None):
        self.weights = settings.source_weights
        stack = list(settings.prefilter.stack_positive)
        vocab = list(dict.fromkeys([*stack, *TECH_TERMS]))
        cv_terms = positive_terms(cv_text, vocab) if cv_text and cv_text.strip() else []
        self.vocab = cv_terms or stack
        self.target = max(1, len(self.vocab))
        self.exp_years = settings.prefilter.exp_years
        self.ctc_floor = settings.prefilter.ctc_min_lpa
        self.usd_inr = settings.prefilter.usd_inr

    def keyword_overlap(self, title: str, skills: list[str], description: str | None) -> float:
        head = set(positive_terms(" ".join([title, *skills]), self.vocab))
        body = set(positive_terms(re.sub(r"\s+", " ", description or ""), self.vocab)) - head
        hits = 2 * len(head) + len(body)
        return hits / (hits + self.target)

    def _experience_fit(self, title: str, description: str | None) -> float:
        exp = parse_experience(title, description, None, None)
        low, high = self.exp_years
        if exp.flags or exp.exp_min is None or exp.exp_min > high:
            return 0.0
        if exp.exp_max is not None and exp.exp_max < low:
            return 0.0
        return 0.5 if exp.inferred else 1.0

    def score(
        self,
        *,
        title: str,
        skills: list[str],
        description: str | None,
        role_family: RoleFamily,
        source: Source,
        is_inbound: bool,
        posted_at: datetime | None,
        found_at: datetime,
        now: datetime,
    ) -> float:
        ref = as_utc(posted_at) or as_utc(found_at)
        age_h = max(0.0, (as_utc(now) - ref).total_seconds() / 3600)
        if age_h < _FRESH_BOOST_HOURS:
            fresh = 1.0
        else:
            fresh = max(0.0, 1 - (age_h / 24 - 2) / (_FRESH_ZERO_DAYS - 2))
        title_fit = min(1.0, .35 * bool(_JAVA.search(title)) + .30 * bool(_SPRING.search(title))
                        + .35 * bool(_BACKEND.search(title)) + .40 * bool(_IAM.search(title)))
        seniority = bool(_SENIORITY.search(title))
        backend_emphasis = bool(_BACKEND.search(title) or _SPRING.search(title))
        mixed = bool(_MIXED.search(title) or (_FULL_STACK.search(title) and not backend_emphasis))
        salary_min, _ = ctc.parse_text(f"{title}\n{description or ''}", self.usd_inr, strict=True)
        ctc_fit = salary_min is not None and salary_min >= self.ctc_floor
        iam_fit = bool(_IAM.search(" ".join([title, *skills, description or ""])))
        base = (.28 * self.keyword_overlap(title, skills, description) + .20 * _ROLE_WEIGHT[role_family]
                + .15 * fresh + (.05 if age_h < _FRESH_BOOST_HOURS else 0.0) + .20 * title_fit
                + .07 * self._experience_fit(title, description) + .03 * ctc_fit + .02 * iam_fit
                - .06 * seniority - .06 * mixed)
        value = max(0.0, min(1.0, base * self.weights.get(source.value, 1.0)))
        if is_inbound:
            value = min(1.0, value + 0.30)
        return round(value, 4)
