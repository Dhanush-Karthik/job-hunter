"""Conservative reply templates. Acknowledgements never propose a transition."""
import re

from jobhunter.gmail.message import Message
from jobhunter.models import AppStatus

REJECTION = (
    r'not (?:be )?moving forward', r'move forward with other candidates',
    r'(?:pursue|pursuing|selected|select|chosen|chose|proceeding with) other candidates',
    r'application (?:wasn.t|was not|has not been) selected',
    r'unfortunately.{0,100}(?:not|unable|declin)', r'will not be (?:proceeding|progressing)',
    r'we (?:have )?decided not to', r'position has been filled',
)
ACK = (
    r'application (?:has been |was |is )?received', r'received your application',
    r'thank(?:s| you)(?: so much)? for (?:applying|your application)',
    r'currently processing your application', r'application (?:has been |was )?submitted',
    r'assessment completed', r'successfully submitted your assessment',
)
INTERVIEW = (
    r'\binterview\b.{0,80}\b(?:invit|schedul|confirm|round\b|availability\b)',
    r'(?:invit|schedul|confirm).{0,80}interview', r'interview - round',
    r'(?:please|can you).{0,50}(?:share|provide).{0,30}availability.{0,40}interview',
)
ASSESSMENT = (
    r'(?:invit|complete|take|start).{0,80}(?:assessment|coding (?:test|challenge))',
    r'(?:assessment|coding test).{0,60}(?:invit|action required|link)',
)


def template(message: Message) -> str | None:
    text = ' '.join((message.subject + '\n' + message.text).lower().split())
    # Ignore quoted history: a previous rejection must not become a new decision.
    text = re.split(r' on .{5,100} wrote:|-----original message-----', text)[0]
    # Interview and assessment invitations often start with “thanks for applying”.
    # A completion confirmation is the exception: it must stay an acknowledgement.
    if any(re.search(pattern, text) for pattern in REJECTION):
        return 'rejection'
    if re.search(r'assessment completed|successfully submitted your assessment|'
                 r'thank(?:s| you) for (?:completing|taking.{0,60}complete).{0,30}assessment', text):
        return 'ack'
    for kind, patterns in [('interview', INTERVIEW), ('assessment', ASSESSMENT), ('ack', ACK)]:
        if any(re.search(pattern, text) for pattern in patterns):
            return kind
    return None


def to_status(kind: str | None) -> AppStatus | None:
    if kind == 'rejection':
        return AppStatus.rejected
    if kind in {'interview', 'assessment'}:
        return AppStatus.screening
    return None
