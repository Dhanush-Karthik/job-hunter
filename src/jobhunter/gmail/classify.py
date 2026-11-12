"""Classify only clear application replies and targeted recruiting as proposal candidates."""
import re

from jobhunter.gmail.message import Message
from jobhunter.gmail.replies import template
from jobhunter.gmail.signals import belongs_to, is_marketing, personal_outreach, platform_outreach

DOMAINS = {
    'linkedin': ('linkedin.com',), 'naukri': ('naukri.com',),
    'instahyre': ('instahyre.com',), 'hirist': ('hirist.com', 'hirist.tech'),
    'cutshort': ('cutshort.io',), 'foundit': ('foundit.in', 'foundit.com', 'monsterindia.com'),
    'wellfound': ('wellfound.com', 'angel.co'), 'uplers': ('uplers.com', 'uplers.in'),
    'indeed': ('indeed.com', 'indeed.co.in'),
}
ATS_DOMAINS = ('myworkday.com', 'myworkdayjobs.com', 'greenhouse-mail.io', 'greenhouse.io',
               'lever.co', 'smartrecruiters.com', 'oracle.com', 'oraclecloud.com', 'amazon.jobs',
               'icims.com', 'ashbyhq.com', 'successfactors.com', 'workablemail.com')


def sender_key(message: Message) -> str | None:
    return next((key for key, domains in DOMAINS.items()
                 if any(belongs_to(message.domain, domain) for domain in domains)), None)


def classify(message: Message, *, application_thread: bool = False) -> str:
    text = ' '.join((message.subject + '\n' + message.text).lower().split())
    subject = message.subject.lower()
    key = sender_key(message)
    if re.search(r'\b(?:otp|one.time (?:password|code)|verification code|bank statement)\b', subject):
        return 'other'
    # Personal platform notifications include unsubscribe links too.
    personal_platform = platform_outreach(message)
    if not personal_platform and key and (
        re.search(r'job alert|job digest|new jobs|job openings|jobs? (?:for you|matching)|'
                  r'companies are hiring|matched.{0,20}(?:jobs|roles)|hiring for|job recommendation', text)
        or message.domain == 'jobalert.indeed.com'
    ):
        return 'alert'
    if is_marketing(message):
        return 'other'
    if key == 'instahyre' and 'job search preferences' in text:
        return 'other'
    if personal_platform and not application_thread:
        return 'inbound'
    kind = template(message)
    application_language = bool(re.search(r'\b(?:application|applying|candidacy|candidates?|position|'
                                          r'role|hiring|recruiting|interview|assessment|coding test)\b', text))
    if kind and (kind != 'rejection' or application_language):
        return 'reply'
    if application_thread or any(belongs_to(message.domain, domain) for domain in ATS_DOMAINS):
        return 'reply'
    if re.search(r'\b(?:your application|application.{0,4}status|application update|'
                 r'update on (?:the|your) application)\b', subject):
        return 'reply'
    if personal_outreach(message):
        return 'inbound'
    return 'other'
