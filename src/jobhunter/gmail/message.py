"""MIME decoding and URL handling, without retaining transport headers or attachments."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email import policy
from email.header import decode_header, make_header
from email.message import Message as EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from selectolax.lexbor import LexborHTMLParser


def decode_subject(value: str) -> str:
    """Decode compat32 headers too: imap-tools uses that legacy email policy."""
    try:
        result = str(make_header(decode_header(value)))
    except LookupError:
        result = ''.join(piece.decode('utf-8', errors='replace') if isinstance(piece, bytes) else piece
                         for piece, _ in decode_header(value))
    return ' '.join(result.split())


def clean_url(value: str) -> str | None:
    value = value.strip()
    for _ in range(3):
        decoded = unquote(value)
        if decoded == value:
            break
        value = decoded
    embedded = list(re.finditer(r'https?://', value, re.IGNORECASE))
    if embedded:
        value = value[embedded[-1].start():]
    try:
        parts = urlsplit(value)
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            return None
        path = re.split(r'/[012]/[0-9a-f]{12,}', parts.path, maxsplit=1)[0]
        query = urlencode([(k, v) for k, v in parse_qsl(parts.query)
                           if k.lower() in {'jobid', 'job_id', 'jk', 'gh_jid'}])
        return urlunsplit((parts.scheme, parts.netloc, path, query, ''))
    except ValueError:
        return None


def lines(text: str) -> list[str]:
    return [re.sub(r'\s+', ' ', line).strip(' |\t') for line in text.splitlines()
            if line.strip(' |\t\r\n')]


def html_tree(html: str) -> LexborHTMLParser:
    tree = LexborHTMLParser(html)
    for node in tree.css('head, style, script'):
        node.decompose()
    return tree


@dataclass(frozen=True)
class Message:
    message_id: str
    subject: str
    sender: str
    text: str
    html: str = ''
    uid: int = 0
    list_unsubscribe: bool = False
    bulk: bool = False
    thread_ids: tuple[str, ...] = ()
    sent_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, 'subject', decode_subject(self.subject))

    @property
    def domain(self) -> str:
        return self.sender.rsplit('@', 1)[-1].lower()

    @property
    def evidence(self) -> str:
        return self.subject + '\n' + ' '.join(self.text.split())[:300]

    @classmethod
    def from_bytes(cls, raw: bytes, uid: int = 0) -> Message:
        return cls.from_email(BytesParser(policy=policy.default).parsebytes(raw), uid)

    @classmethod
    def from_email(cls, mail: EmailMessage, uid: int = 0) -> Message:
        plain, html = [], []
        for part in mail.walk():
            if part.get_content_disposition() == 'attachment' or part.is_multipart():
                continue
            kind = part.get_content_type()
            if kind not in {'text/plain', 'text/html'}:
                continue
            payload = part.get_payload(decode=True) or b''
            try:
                content = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
            except LookupError:
                content = payload.decode('utf-8', errors='replace')
            (plain if kind == 'text/plain' else html).append(content)
        markup = '\n'.join(html)
        text = '\n'.join(plain)
        # Some reconstructed samples contain HTML in a text/plain part.
        if not text or re.search(r'<(?:div|p|table)\b', text, re.IGNORECASE):
            text = html_tree(markup or text).text(separator='\n')
        identity = str(mail.get('Message-ID', '')).strip()
        if not identity:
            identity = 'sha256:' + hashlib.sha256(mail.as_bytes()).hexdigest()
        sent_at = None
        if mail.get('Date'):
            try:
                sent_at = parsedate_to_datetime(str(mail['Date']))
                sent_at = sent_at.replace(tzinfo=UTC) if sent_at.tzinfo is None else sent_at.astimezone(UTC)
            except (ValueError, TypeError, OverflowError):
                pass
        references = ' '.join(str(mail.get(key, '')) for key in ('References', 'In-Reply-To'))
        return cls(identity, str(mail.get('Subject', '')), parseaddr(str(mail.get('From', '')))[1],
                   text, markup, uid, bool(mail.get('List-Unsubscribe') or mail.get('List-ID')),
                   str(mail.get('Precedence', '')).lower() in {'bulk', 'list', 'junk'},
                   tuple(dict.fromkeys(re.findall(r'<[^<>\s]+>', references))), sent_at)

