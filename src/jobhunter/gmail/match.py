"""Match replies only when company/domain evidence identifies an application."""
import re
from urllib.parse import urlsplit

from rapidfuzz.fuzz import ratio, token_set_ratio
from sqlmodel import Session, select

from jobhunter.gmail.message import Message
from jobhunter.models import Application, Lead


def normalized(value: str) -> str:
    return ' '.join(re.findall(r'[a-z0-9]+', value.lower()))


def match_application(session: Session, message: Message) -> tuple[Application | None, float]:
    text = normalized(message.subject + ' ' + message.text)
    ranked = []
    for application, lead in session.exec(select(Application, Lead).join(Lead, Application.lead_id == Lead.id)):
        company = normalized(lead.company)
        tokens = company.split()
        while tokens and tokens[-1] in {'inc', 'limited', 'ltd', 'private', 'pvt', 'llc', 'corp'}:
            tokens.pop()
        company = ' '.join(tokens)
        company_match = bool(company and f' {company} ' in f' {text} ')
        if company in {'target', 'box', 'indeed', 'apple', 'wise', 'linear', 'stripe'}:
            company_match = bool(
                f' {company} ' in f' {normalized(message.subject)} '
                or re.search(rf'\b(?:at|with|from|join) {re.escape(company)}\b|'
                             rf'\b{re.escape(company)} (?:recruiting|recruitment|hiring|team)\b', text)
            )
        # Tolerate a typo in a multi-character company, but require a whole word/window match.
        if not company_match and len(company) >= 6 and company not in {'target', 'linear', 'stripe'}:
            words = text.split()
            company_match = any(ratio(company, ' '.join(words[i:i + len(tokens)])) >= 92
                                for i in range(len(words)))
        host = (urlsplit(lead.canonical_url or '').hostname or '').lower()
        domain = message.domain.removeprefix('mail.').removeprefix('recruiting.')
        domain_match = bool(host and domain and (host == domain or host.endswith('.' + domain)))
        if not domain_match and company:
            stem = normalized(domain.split('.')[0]).replace(' ', '')
            domain_match = stem == company.replace(' ', '') and len(stem) >= 4
        recruiter_match = bool(application.recruiter and message.sender.lower() in application.recruiter.lower())
        if not (company_match or domain_match or recruiter_match):
            continue
        title = normalized(lead.title)
        title_match = bool(title and f' {title} ' in f' {text} ')
        title_score = token_set_ratio(title, text) / 100 if title else 0
        score = min(0.99, (0.91 if domain_match or recruiter_match else 0.87)
                    + (0.10 if title_match else 0.02 * title_score))
        ranked.append((score, application))
    ranked.sort(key=lambda row: row[0], reverse=True)
    if not ranked:
        return None, 0.0
    score, application = ranked[0]
    if len(ranked) > 1 and score - ranked[1][0] < 0.06:
        return None, score
    return application, score
