"""Extract one lead from a recruiter's outreach, with bounded supporting text."""
import re

from jobhunter.gmail.message import Message, clean_url, lines
from jobhunter.intake.types import RawJob
from jobhunter.models import Source


def parse(message: Message) -> RawJob:
    content = '\n'.join(lines(message.text))
    company = None
    company_match = re.search(r'(?:opportunity|role|position) (?:at|with)\s+([^\n.!?]+)',
                              message.subject + '\n' + content, re.IGNORECASE)
    if company_match:
        company = company_match[1].strip(' …')
    title_match = re.search(r'(?:Job\s*\|\s*|Title:\s*)([^\n|]+?)(?:\s+in\s+([^\n|]+)|$)',
                            message.subject, re.IGNORECASE)
    title = title_match[1].strip() if title_match else None
    location = title_match[2].strip() if title_match and title_match[2] else None
    labelled = re.search(r'^Company:\s*(.+)$', content, re.MULTILINE | re.IGNORECASE)
    if labelled:
        company = labelled[1]
    registered = re.search(r'registered with Naukri.com as ([^(\n]+)', content, re.IGNORECASE)
    if registered:
        company = registered[1].strip()
    if not company:
        company = message.domain.split('.')[-2].title() if '.' in message.domain else 'Unknown company'
    if not title:
        labelled = re.search(r'^(?:Title|Role):\s*(.+)$', content, re.MULTILINE | re.IGNORECASE)
        title = labelled[1] if labelled else 'Software Engineer' if 'software engineer' in content.lower() else 'Recruiter opportunity'
    urls = re.findall(r'https?://[^\s<>\])]+', message.text)
    url = next((clean_url(value) for value in urls
                if re.search(r'/job|/messaging/thread/', value)), None)
    return RawJob(source=Source.gmail_inbound, source_ref=message.message_id, title=title,
                  company=company, location=location, job_url=url,
                  is_inbound=True, description=' '.join(message.text.split())[:300])
