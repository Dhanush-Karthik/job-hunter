"""Extract one lead from a recruiter's outreach, with bounded supporting text."""
import re

from jobhunter.gmail.message import Message, clean_url, html_tree, lines
from jobhunter.intake.types import RawJob
from jobhunter.models import Source

_APPLY_TEXT = re.compile(r'\bapply\b|view (?:the )?(?:job|role|position|opening)|(?:see|job) details', re.IGNORECASE)
DESCRIPTION_CHARS = 1500


def _usable(url: str | None) -> str | None:
    """A link worth opening: not a bare site root, which is what stripping a tracking redirect can leave."""
    if not url:
        return None
    path = url.split('://', 1)[-1].partition('/')[2].split('?')[0]
    return url if path.strip('/') else None


def apply_link(message: Message) -> str | None:
    """Where the recruiter's email sends the candidate: the 'Apply' / 'View job' button first, then any job link."""
    if message.html:
        for anchor in html_tree(message.html).css('a[href]'):
            text = ' '.join(anchor.text().split())
            if text and _APPLY_TEXT.search(text) and (url := _usable(clean_url(anchor.attributes.get('href') or ''))):
                return url
    urls = re.findall(r'https?://[^\s<>\])]+', message.text)
    return next((url for value in urls if re.search(r'/job|/messaging/thread/', value)
                 and (url := _usable(clean_url(value)))), None)


def _excerpt(text: str) -> str:
    """The first DESCRIPTION_CHARS of the email, cut at a word so it never ends mid-word."""
    flat = ' '.join(text.split())
    if len(flat) <= DESCRIPTION_CHARS:
        return flat
    return flat[:DESCRIPTION_CHARS].rsplit(' ', 1)[0] + '…'


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
    if not title:
        invited = re.search(r'(?:apply for|application for|opening for|interest in)\s+(?:the\s+)?([^\n|]{3,80}?)\s+(?:role|position|job|opening)\b',
                            message.subject, re.IGNORECASE)
        title = invited[1].strip() if invited else None
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
    url = apply_link(message)
    return RawJob(source=Source.gmail_inbound, source_ref=message.message_id, title=title,
                  company=company, location=location, job_url=url,
                  is_inbound=True, description=_excerpt(message.text),
                  raw={'sender': message.sender})
