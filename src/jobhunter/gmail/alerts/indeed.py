"""Indeed saved-search digests: linked title, company, location and job-specific jk URL."""
import re
from datetime import timedelta
from urllib.parse import urlsplit

from jobhunter.gmail.alerts.common import make_job
from jobhunter.gmail.message import Message, clean_url, html_tree, lines
from jobhunter.intake.types import RawJob


def _job_link(url: str) -> bool:
    parsed = urlsplit(url)
    return bool(parsed.hostname and (parsed.hostname == 'indeed.com' or parsed.hostname.endswith('.indeed.com'))
                and re.search(r'/(?:rc/clk/dl|pagead/clk/dl|viewjob|(?:company/[^/]+/)?jobs/)', parsed.path))


def parse(message: Message) -> list[RawJob]:
    jobs = []
    for anchor in html_tree(message.html).css('a[href]'):
        url = clean_url(anchor.attributes['href'])
        title = ' '.join(anchor.text(strip=True).split())
        if not url or not _job_link(url) or not title:
            continue
        node = anchor
        content = []
        for _ in range(11):
            current = lines(node.text(separator='\n'))
            links = {clean_url(link.attributes['href']) for link in node.css('a[href]')
                     if _job_link(link.attributes['href'])}
            if len(links) > 1:
                break
            if len(current) >= 3 and current[0] == title:
                content = current
            node = node.parent
            if node is None or node.tag in {'body', 'html'}:
                break
        if content:
            job = make_job(message, 'indeed', title, content[1], '\n'.join(content), url, content[2])
            _details(job, message, content)
            jobs.append(job)
    if not jobs:
        # Plain-text alternatives delimit each card with its job URL.
        content = lines(message.text)
        start = 0
        for index, line in enumerate(content):
            url = clean_url(line) if line.startswith('http') else None
            if not url or not _job_link(url):
                continue
            block = content[start:index]
            for i, value in enumerate(block):
                if i and ' - ' in value:
                    company, location = value.split(' - ', 1)
                    job = make_job(message, 'indeed', block[i - 1], company, '\n'.join(block), url, location)
                    _details(job, message, block)
                    jobs.append(job)
                    break
            start = index + 1
    # Sponsored redirect paths need not contain a jk; different cards may share the same URL.
    unique = {(job.job_url, job.title, job.company, job.location): job for job in jobs}
    for index, job in enumerate(unique.values()):
        job.source_ref = f'{message.message_id}#{index}'
    return list(unique.values())


def _details(job: RawJob, message: Message, content: list[str]) -> None:
    context = '\n'.join(content)
    if 'easily apply' in context.lower():
        job.easy_apply = True
    salary = next((line for line in content if re.match(r'[₹$£]|(?:INR|Rs)\b', line)), None)
    if salary:
        job.salary_text = salary
    if message.sent_at:
        age = re.search(r'\b(\d+) days? ago\b', context)
        if age or 'just posted' in context.lower():
            job.posted_at = message.sent_at - timedelta(days=int(age[1]) if age else 0)
