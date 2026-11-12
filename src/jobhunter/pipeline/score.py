"""Quick score, deterministic, in [0, 1]. Orders every lead; the top N get the LLM evaluation.

    base  = 0.35 * kw + 0.25 * role + 0.20 * fresh + (0.10 if posted/found < 48 h else 0)
    score = clamp(base * source_weight)                  # settings.source_weights[source], default 1.0
    if is_inbound: score = clamp(score + 0.30)           # recruiter reached out: always near the top

  kw    CV keyword overlap. The CV vocabulary is every known tech term (TECH_TERMS plus
        settings.prefilter.stack_positive) that appears in `cv_text`; with no CV text it is just
        stack_positive. Each vocabulary term found in the job counts 2 in the title/skills and 1 in the
        description; kw = min(1, weighted_hits / (1.5 * min(len(vocabulary), 6))).
  role  P1 = 1.0, P2 = 0.6, other = 0.15.
  fresh 1.0 up to 48 h old, then linear decay to 0 at 9 days (about 7 days of decay). Age is measured from
        posted_at, or found_at when the posting has no date.

Same inputs and `now` always give the same score.
"""

from __future__ import annotations

import re
from datetime import datetime

from jobhunter import paths
from jobhunter.models import RoleFamily, Source
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
        self.target = max(1, min(len(self.vocab), 6))

    def keyword_overlap(self, title: str, skills: list[str], description: str | None) -> float:
        head = set(positive_terms(" ".join([title, *skills]), self.vocab))
        body = set(positive_terms(re.sub(r"\s+", " ", description or ""), self.vocab)) - head
        return min(1.0, (2 * len(head) + len(body)) / (1.5 * self.target))

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
        base = (0.35 * self.keyword_overlap(title, skills, description) + 0.25 * _ROLE_WEIGHT[role_family]
                + 0.20 * fresh + (0.10 if age_h < _FRESH_BOOST_HOURS else 0.0))
        value = min(1.0, base * self.weights.get(source.value, 1.0))
        if is_inbound:
            value = min(1.0, value + 0.30)
        return round(value, 4)
