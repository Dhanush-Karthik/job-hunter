"""Find the HR / recruiter mailbox for a job, from the most to the least trustworthy place.

Sources, best first:
  job_post      an address written in the job description itself
  recruiter     the sender of the email that brought this lead (Gmail inbound), when it is a real mailbox
  posting_page  an address on the job's own web page (mailto links, Cloudflare-protected addresses, plain text)
  saved         a contact the owner saved for this company earlier
  company_site  an address on the company's careers / contact pages, at the company's own domain
  guess         careers@ / hr@ ... at the company domain. Never sent to unless the owner picks it.

Only the web lookups touch the network (`http_get` and `resolves` are test seams). Nothing here sends mail.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

import httpx
from selectolax.lexbor import LexborHTMLParser

Source = Literal["job_post", "recruiter", "posting_page", "saved", "company_site", "guess"]

MAX_PAGES = 5  # pages fetched per lookup
MAX_BYTES = 400_000
TIMEOUT = 8.0
MAX_RESULTS = 8

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
# "name [at] company [dot] com" and "name(at)company(dot)com"
_OBFUSCATED = re.compile(
    r"([A-Za-z0-9._%+\-]+)\s*[\[(]\s*at\s*[\])]\s*([A-Za-z0-9\-]+(?:\s*[\[(]\s*dot\s*[\])]\s*[A-Za-z0-9\-]+)+)", re.IGNORECASE)
_DOT = re.compile(r"\s*[\[(]\s*dot\s*[\])]\s*", re.IGNORECASE)

# Mailboxes that never read an application, or belong to someone else's job.
_JUNK_LOCAL = re.compile(
    r"no-?reply|do-?not-?reply|donotreply|mailer-daemon|postmaster|bounce|unsubscribe|notification|alerts?$|"
    r"abuse|privacy|legal|security|press|media|marketing|sales|support|billing|invoice|accounts?$|webmaster|"
    r"admin$|sentry|example|test$|dpo$|gdpr|compliance|investor", re.IGNORECASE)
_JUNK_DOMAIN = re.compile(
    r"(^|\.)(example|test|localhost|sentry|wixpress|sentry-next|godaddy|cloudflare|w3|schema|"
    r"googleusercontent|gstatic|amazonaws|cloudfront)\.", re.IGNORECASE)
_BAD_TLD = {"png", "jpg", "jpeg", "gif", "svg", "webp", "css", "js", "ico", "woff", "woff2", "pdf", "map"}
_HR_WORDS = re.compile(r"hr|career|job|talent|recruit|hiring|people|apply|resume|cv|join|staffing|ta$", re.IGNORECASE)

# Job boards and applicant-tracking systems: their domain says nothing about the employer's own mail domain.
_NOT_EMPLOYER = (
    "linkedin.com", "naukri.com", "indeed.com", "glassdoor.com", "glassdoor.co.in", "instahyre.com", "hirist.tech",
    "hirist.com", "cutshort.io", "foundit.in", "monsterindia.com", "wellfound.com", "angel.co", "uplers.com",
    "turing.com", "arc.dev", "google.com", "greenhouse.io", "lever.co", "ashbyhq.com", "workable.com",
    "smartrecruiters.com", "myworkdayjobs.com", "workday.com", "icims.com", "jobvite.com", "bamboohr.com",
    "recruitee.com", "breezy.hr", "zohorecruit.com", "zoho.com", "keka.com", "freshteam.com", "darwinbox.in",
    "darwinbox.com", "oraclecloud.com", "successfactors.com", "taleo.net", "eightfold.ai", "pinpointhq.com",
    "teamtailor.com", "jobs.lever.co", "apply.workable.com", "linktr.ee", "notion.site", "notion.so", "github.io",
    "facebook.com", "twitter.com", "x.com", "instagram.com", "youtube.com", "medium.com", "wa.me", "gmail.com",
)
_SECOND_LEVEL = {"co", "com", "org", "net", "gov", "ac", "edu"}  # co.in, com.au, co.uk ...
_PREFIXES = ("www", "careers", "career", "jobs", "job", "boards", "apply", "hire", "join", "work")

_WEIGHT: dict[str, int] = {"job_post": 100, "recruiter": 90, "posting_page": 80, "saved": 70, "company_site": 50, "guess": 10}
_LABEL: dict[str, str] = {
    "job_post": "Written in the job description",
    "recruiter": "Sent you this opportunity",
    "posting_page": "On the job's web page",
    "saved": "You saved this contact",
    "company_site": "On the company's website",
    "guess": "Common HR address (unverified guess)",
}

# Test seams.
http_get = None  # (url: str) -> str | None; None = real httpx
resolves = None  # (domain: str) -> bool; None = real DNS lookup


@dataclass
class Found:
    email: str
    source: Source
    label: str
    confidence: Literal["high", "medium", "low"]
    name: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _confidence(source: Source) -> Literal["high", "medium", "low"]:
    return "high" if source in ("job_post", "recruiter", "posting_page", "saved") else "medium" if source == "company_site" else "low"


def make(email: str, source: Source, name: str | None = None) -> Found:
    return Found(email=email, source=source, label=_LABEL[source], confidence=_confidence(source), name=name)


def usable(email: str) -> bool:
    """A mailbox a person could read: not a no-reply, an image file name, or a placeholder."""
    local, _, domain = email.lower().rpartition("@")
    if not local or not domain or len(email) > 254:
        return False
    if domain.rsplit(".", 1)[-1] in _BAD_TLD or _JUNK_DOMAIN.search("." + domain):
        return False
    return not _JUNK_LOCAL.search(local)


def emails_in(text: str) -> list[str]:
    """Distinct usable addresses in free text, in order of appearance (handles `name [at] x [dot] com`)."""
    if not text:
        return []
    flat = _OBFUSCATED.sub(lambda m: f"{m[1]}@{_DOT.sub('.', m[2])}".replace(" ", ""), text)
    seen: dict[str, None] = {}
    for m in EMAIL_RE.finditer(flat):
        email = m[0].strip(".-_").rstrip(".")
        if usable(email):
            seen.setdefault(email, None)
    return list(seen)


def _cf_decode(hex_str: str) -> str | None:
    """Cloudflare's email protection: first byte is the XOR key for the rest."""
    try:
        raw = bytes.fromhex(hex_str)
        return bytes(b ^ raw[0] for b in raw[1:]).decode("utf-8")
    except (ValueError, IndexError):
        return None


def emails_in_html(html: str) -> list[str]:
    tree = LexborHTMLParser(html)
    found: dict[str, None] = {}
    for node in tree.css("a[href^='mailto:' i]"):
        target = (node.attributes.get("href") or "")[7:].split("?")[0]
        for part in target.replace("%40", "@").split(","):
            part = part.strip()
            if part and usable(part) and EMAIL_RE.fullmatch(part):
                found.setdefault(part, None)
    for node in tree.css("[data-cfemail]"):
        decoded = _cf_decode(node.attributes.get("data-cfemail") or "")
        if decoded and usable(decoded):
            found.setdefault(decoded, None)
    for tag in ("script", "style", "noscript"):
        for node in tree.css(tag):
            node.decompose()
    for email in emails_in(tree.text(separator=" ")):
        found.setdefault(email, None)
    return list(found)


def registrable(host: str) -> str | None:
    """`careers.acme.co.in` -> `acme.co.in`; None for job boards, ATSs and IPs."""
    host = host.lower().strip(".").split(":")[0]
    if not host or "." not in host:
        return None
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    labels = host.split(".")
    while len(labels) > 2 and labels[0] in _PREFIXES:
        labels = labels[1:]
    take = 3 if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL and len(labels[-1]) == 2 else 2
    domain = ".".join(labels[-take:])
    if any(domain == d or domain.endswith("." + d) or host == d or host.endswith("." + d) for d in _NOT_EMPLOYER):
        return None
    return domain


def company_domain(*urls: str | None) -> str | None:
    """The employer's own domain, from the first URL that is not a job board or ATS."""
    for url in urls:
        if url:
            domain = registrable(urlparse(url if "//" in url else "//" + url).hostname or "")
            if domain:
                return domain
    return None


def _public_http(url: str) -> bool:
    """Only http(s) pages on the public internet: never localhost, private ranges or file://."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or not host or host == "localhost" or host.endswith((".local", ".internal")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


def fetch(url: str) -> str | None:
    if not _public_http(url):
        return None
    if http_get is not None:
        return http_get(url)
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; job-hunter/1.0)", "Accept": "text/html,text/plain;q=0.9"}
        with httpx.stream("GET", url, headers=headers, timeout=TIMEOUT, follow_redirects=True) as r:
            if r.status_code >= 400 or not _public_http(str(r.url)):
                return None
            if "html" not in r.headers.get("content-type", "html") and "text" not in r.headers.get("content-type", ""):
                return None
            data = b""
            for chunk in r.iter_bytes():
                data += chunk
                if len(data) >= MAX_BYTES:
                    break
        return data.decode(r.encoding or "utf-8", errors="replace")
    except (httpx.HTTPError, OSError, ValueError):
        return None


def domain_resolves(domain: str) -> bool:
    if resolves is not None:
        return resolves(domain)
    try:
        socket.getaddrinfo(domain, None)
        return True
    except OSError:
        return False


def _on_domain(email: str, domain: str) -> bool:
    host = email.rsplit("@", 1)[-1].lower()
    return host == domain or host.endswith("." + domain)


def _hr_like(email: str) -> bool:
    return bool(_HR_WORDS.search(email.split("@", 1)[0]))


def from_text(jd_text: str | None) -> list[Found]:
    return [make(e, "job_post") for e in emails_in(jd_text or "")]


def from_sender(sender: str | None, name: str | None = None) -> list[Found]:
    return [make(sender, "recruiter", name)] if sender and usable(sender) and EMAIL_RE.fullmatch(sender.strip()) else []


def rank(found: list[Found], limit: int = MAX_RESULTS) -> list[Found]:
    """One entry per address (best source wins); role mailboxes (careers@, hr@) above personal ones; guesses last."""
    best: dict[str, Found] = {}
    for f in found:
        key = f.email.casefold()
        if key not in best or _WEIGHT[f.source] > _WEIGHT[best[key].source]:
            best[key] = f
    order = sorted(best.values(), key=lambda f: (-(_WEIGHT[f.source] + (8 if _hr_like(f.email) else 0)), f.email.casefold()))
    return order[:limit]


def lookup(*, jd_text: str | None, sender: str | None, job_urls: list[str | None], careers_url: str | None,
           guess: bool, guess_prefixes: list[str], pages: bool = True) -> list[Found]:
    """The full search. Network is used only when `pages` is true (posting page, company pages, DNS for guesses)."""
    out: list[Found] = [*from_text(jd_text), *from_sender(sender)]
    domain = company_domain(careers_url, *job_urls)
    if pages:
        seen: set[str] = set()
        budget = MAX_PAGES

        def read(url: str) -> str | None:
            nonlocal budget
            if budget <= 0 or url in seen:
                return None
            seen.add(url)
            budget -= 1
            return fetch(url)

        for url in dict.fromkeys(u for u in job_urls if u):
            html = read(url)
            if html:
                out += [make(e, "posting_page") for e in emails_in_html(html)]
        if domain:
            start = careers_url if careers_url and company_domain(careers_url) == domain else f"https://{domain}/"
            pages_to_try = [start]
            for path in ("/contact", "/contact-us", "/careers"):
                pages_to_try.append(urljoin(start if start.endswith("/") else start + "/", path.lstrip("/")))
            for url in dict.fromkeys(pages_to_try):
                html = read(url)
                if html:
                    out += [make(e, "company_site") for e in emails_in_html(html) if _on_domain(e, domain)]
    if guess and domain and (not pages or domain_resolves(domain)):
        out += [make(f"{p}@{domain}", "guess") for p in guess_prefixes if p.strip()]
    return rank(out)
