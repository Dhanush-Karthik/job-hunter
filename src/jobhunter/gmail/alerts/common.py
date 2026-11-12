"""Shared card extraction primitives; platform modules select their own formats."""
from __future__ import annotations

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from jobhunter.gmail.message import Message, clean_url, html_tree, lines
from jobhunter.intake.types import RawJob
from jobhunter.models import Source


def make_job(message: Message, sender: str, title: str, company: str, context: str,
             url: str | None = None, location: str | None = None) -> RawJob:
    experience = re.search(r'\b\d+(?:\.\d+)?\s*(?:[-–]\s*\d+(?:\.\d+)?)?\s*(?:years?|yrs?)\b',
                           context, re.IGNORECASE)
    salary = re.search(r'(?:₹|INR|Rs\.?|\$)?\s*\d+(?:\.\d+)?\s*(?:[-–]\s*\d+(?:\.\d+)?)?\s*'
                       r'(?:LPA|lakhs?|USD|per annum)\b', context, re.IGNORECASE)
    posted = None
    date = re.search(r'Posted(?: on| at)?:?\s*([^\n|]+)', context, re.IGNORECASE)
    if date:
        try:
            parsed = datetime.fromisoformat(date[1].strip())
            posted = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
        except ValueError:
            try:
                posted = parsedate_to_datetime(date[1]).astimezone(UTC)
            except (ValueError, TypeError):
                pass
    return RawJob(source=Source.gmail_alert, source_ref='', source_detail=sender,
                  title=title.strip(), company=company.strip(), location=location,
                  job_url=clean_url(url) if url else None, experience_text=experience[0] if experience else None,
                  salary_text=salary[0].strip() if salary else None, posted_at=posted,
                  easy_apply=True if re.search(r'easy apply|apply with resume|one.click apply', context, re.IGNORECASE)
                  else None)


def finish(message: Message, jobs: list[RawJob]) -> list[RawJob]:
    unique = {}
    for job in jobs:
        if job.title and job.company:
            key = job.job_url or (job.title, job.company, job.location)
            unique.setdefault(key, job)
    for index, job in enumerate(unique.values()):
        job.source_ref = f'{message.message_id}#{index}'
    return list(unique.values())


def text_cards(message: Message, sender: str) -> list[RawJob]:
    """Numbered digest lines and explicit field-labelled cards."""
    jobs = []
    blocks = re.split(r'(?=^\s*\d+\.\s)|\n\s*\n|(?=^Title:)', message.text, flags=re.MULTILINE)
    for block in blocks:
        match = re.search(r'^\s*(?:\d+\.\s*)?(.+?)\s+at\s+(.+?)(?:\s*\|\s*(.+))?$', block, re.MULTILINE)
        if match:
            title, company, meta = match.groups()
            if len(title) > 140 or title.lower().startswith(('hi ', 'opportunity', 'exciting')):
                continue
            url = re.search(r'https?://[^\s<>\])]+', block)
            jobs.append(make_job(message, sender, title, company, block, url[0] if url else None,
                                 re.split(r'[•|]', meta)[0].strip() if meta else None))
        elif re.search(r'^Title:', block, re.MULTILINE):
            fields = dict(re.findall(r'^(Title|Company|Location|URL|Apply URL):\s*(.+)$', block, re.MULTILINE))
            if fields.get('Title') and fields.get('Company'):
                job = make_job(message, sender, fields['Title'], fields['Company'], block,
                               fields.get('URL'), fields.get('Location'))
                job.apply_url = clean_url(fields['Apply URL']) if fields.get('Apply URL') else None
                jobs.append(job)
    return jobs


def html_cards(message: Message, sender: str, url_pattern: str) -> list[RawJob]:
    jobs = []
    tree = html_tree(message.html)
    for anchor in tree.css('a[href]'):
        url = clean_url(anchor.attributes['href'])
        if not url or not re.search(url_pattern, url, re.IGNORECASE):
            continue
        node = anchor
        for _ in range(9):
            content = lines(node.text(separator='\n'))
            title = company = location = None
            if sender == 'linkedin' and len(content) >= 2 and '·' in content[1]:
                title = content[0]
                company, location = (x.strip() for x in content[1].split('·', 1))
            elif sender == 'instahyre' and len(content) >= 2:
                match = re.fullmatch(r'(.+?)\s*\(([^)]+)\)', content[0])
                if match:
                    company, location = match.groups()
                    title = content[1]
            elif sender == 'wellfound':
                for i, line in enumerate(content[1:], 1):
                    if re.search(r'/\s*[\d,-]+ Employees', line):
                        title, company = content[i - 1], line.split('/')[0].strip()
                        location = content[i + 1].strip(' |').split('|')[0].strip() if i + 1 < len(content) else None
                        break
            else:
                title_node = node.css_first('.job-title, .title, h2, h3')
                company_node = node.css_first('.company, .company-name')
                location_node = node.css_first('.location')
                if title_node and company_node:
                    title, company = title_node.text(strip=True), company_node.text(strip=True)
                    location = location_node.text(strip=True) if location_node else None
            if title and company:
                context = '\n'.join(content)
                job = make_job(message, sender, title, company, context, url, location)
                for link in node.css('a[href]'):
                    if 'apply' in link.text(strip=True).lower():
                        apply = clean_url(link.attributes['href'])
                        if apply != job.job_url:
                            job.apply_url = apply
                jobs.append(job)
                break
            node = node.parent
            if node is None or node.tag in {'body', 'html'}:
                break
    return jobs
