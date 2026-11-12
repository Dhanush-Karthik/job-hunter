"""Signals that distinguish personal recruiting from bulk marketing."""
import re

from jobhunter.gmail.message import Message, html_tree


def belongs_to(domain: str, parent: str) -> bool:
    return domain == parent or domain.endswith('.' + parent)


def is_marketing(message: Message) -> bool:
    text = (message.subject + '\n' + message.text).lower()
    if message.html:
        text += '\n' + html_tree(message.html).text(separator=' ').lower()
    if message.bulk:
        return True
    if re.search(r'\b(?:newsletter|employee reviews|product (?:updates|announcements)|'
                 r'this is a marketing email|company updates|read the blog|'
                 r'weekly (?:job.alert )?digest|supa update)\b', text):
        return True
    local = message.sender.partition('@')[0].lower()
    return bool(message.list_unsubscribe and (
        re.search(r'view (?:the )?web version|view (?:this email )?in (?:your )?browser|'
                  r'promotional|special offer|limited.time offer|discount|shop now|buy now', text)
        or re.match(r'(?:newsletter|marketing|digest|promotions)[-+@.]?', local)
    ))


def platform_outreach(message: Message) -> bool:
    text = (message.subject + '\n' + message.text).lower()
    local = message.sender.partition('@')[0].lower()
    if belongs_to(message.domain, 'linkedin.com'):
        return local in {'inmail-hit-reply', 'hit-reply'} and bool(
            re.search(r'\binmail\b|opportunity (?:at|with)|share your (?:profile|resume)|'
                      r'(?:take up|schedule) a conversation', text))
    if belongs_to(message.domain, 'naukri.com'):
        return bool(re.search(r'job invite from recruiter|invited to apply to this job|'
                              r'registered with naukri\.com as', text))
    return False


def personal_outreach(message: Message) -> bool:
    """Require an individual addressing the recipient, a named role and recruiting intent."""
    if platform_outreach(message):
        return True
    local = message.sender.partition('@')[0].lower()
    if re.match(r'(?:no.?reply|donotreply|newsletter|marketing|digest|updates|welcome)(?:\b|[-_.])', local):
        return False
    text = ' '.join((message.subject + '\n' + message.text).lower().split())
    addressed = bool(re.search(r'\b(?:hi|hello|hey|dear)[,!]?\s+[a-z][a-z ]{0,45}[,!]', text))
    targeted = bool(re.search(r'(?:i.m|i am|we.re|we are) (?:reaching out|recruiting|hiring)|'
                              r'your (?:profile|experience|background).{0,70}(?:fit|match|impress|interest)|'
                              r'please (?:share|send) (?:your|me your) (?:cv|resume)|'
                              r'would you be (?:open|interested)', text))
    role = bool(re.search(r'\b(?:engineer|developer|architect|analyst|consultant|manager|designer|'
                          r'recruiter|specialist|scientist)\b', text))
    return addressed and targeted and role
