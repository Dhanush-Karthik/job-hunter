"""Classify by bounded sender domains and intent, never by a domain substring."""
import re

from jobhunter.gmail.message import Message
from jobhunter.gmail.replies import template

DOMAINS = {
    'linkedin': ('linkedin.com',), 'naukri': ('naukri.com',),
    'instahyre': ('instahyre.com',), 'hirist': ('hirist.com', 'hirist.tech'),
    'cutshort': ('cutshort.io',), 'foundit': ('foundit.in', 'foundit.com', 'monsterindia.com'),
    'wellfound': ('wellfound.com', 'angel.co'), 'uplers': ('uplers.com', 'uplers.in'),
}


def sender_key(message: Message) -> str | None:
    return next((key for key, domains in DOMAINS.items()
                 if any(message.domain == d or message.domain.endswith('.' + d) for d in domains)), None)


def classify(message: Message) -> str:
    text = (message.subject + '\n' + message.text).lower()
    subject = message.subject.lower()
    key = sender_key(message)
    if re.search(r'\b(?:otp|one.time (?:password|code)|verification code|bank statement)\b', subject):
        return 'other'
    # A platform can deliver personal outreach as well as automatic digests.
    if re.search(r'job invite from recruiter|invited to apply to this job|i.m reaching out|'
                 r'open to exploring|please share your (?:profile|resume)|'
                 r'let me know if we can take up a conversation', text):
        return 'inbound'
    if key and re.search(r'job alert|job digest|new jobs|job openings|jobs? (?:for you|matching)|'
                         r'companies are hiring|matched.{0,20}(?:jobs|roles)|hiring for|job recommendation', text):
        return 'alert'
    if key == 'instahyre' and 'job search preferences' in text:
        return 'other'
    if template(message):
        return 'reply'
    if re.search(r'\b(?:your application|application.{0,4}status|application status|re:.*application|interview|assessment)\b', subject):
        return 'reply'
    if re.search(r'(?:we are|we.re|i am|i.m) (?:hiring|recruiting)|'
                 r'opportunity (?:at|with)|share your (?:cv|resume)', text):
        return 'inbound'
    return 'other'
