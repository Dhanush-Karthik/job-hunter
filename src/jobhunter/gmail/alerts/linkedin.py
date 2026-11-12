"""LinkedIn job-alert cards in HTML and plain-text alternatives."""
import re

from jobhunter.gmail.alerts.common import finish, html_cards, make_job
from jobhunter.gmail.message import Message, lines
from jobhunter.intake.types import RawJob


def parse(message: Message) -> list[RawJob]:
    jobs = html_cards(message, 'linkedin', r'linkedin\.com/(?:comm/)?jobs/view/')
    if not jobs:
        for block in re.split(r'-{5,}', message.text):
            content = lines(block)
            for i, line in enumerate(content):
                if line.startswith('View job:') and i >= 3:
                    # Strip digest headings before the first actual title.
                    previous = content[:i]
                    while previous and (previous[-1].startswith(('This company', 'Apply with'))
                                        or re.match(r'\d+ (?:school|connection)', previous[-1])):
                        previous.pop()
                    if len(previous) >= 3:
                        title, company, location = previous[-3:]
                        jobs.append(make_job(message, 'linkedin', title, company, block,
                                             line.removeprefix('View job:').strip(), location))
    return finish(message, jobs)
