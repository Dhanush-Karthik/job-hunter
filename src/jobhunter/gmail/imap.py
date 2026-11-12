"""Read-only IMAP connection seam. Tests replace mailbox_factory, never use the network."""
import imaplib
from contextlib import contextmanager
from datetime import date

from imap_tools import AND, MailBox
from imap_tools.errors import ImapToolsError

from jobhunter.gmail import GmailError
from jobhunter.gmail.message import Message

mailbox_factory = MailBox
LOGIN_ERROR = 'Gmail login failed. Check the Gmail address and app password.'
MAIL_ERRORS = (OSError, imaplib.IMAP4.error, ImapToolsError, RuntimeError)
IMAP_ERROR = 'Gmail could not read mail. Check the connection and try again.'


@contextmanager
def connect(address: str, password: str, *, inbox: bool = False):
    mailbox = None
    try:
        mailbox = mailbox_factory('imap.gmail.com', port=993)
        # MailBox.login defaults to a writable INBOX selection: explicitly disable it.
        mailbox.login(address, password, initial_folder=None)
    except MAIL_ERRORS:
        if mailbox is not None:
            try:
                mailbox.logout()
            except MAIL_ERRORS:
                pass
        raise GmailError(LOGIN_ERROR) from None
    try:
        folder = 'INBOX' if inbox else '[Gmail]/All Mail'
        try:
            mailbox.folder.set(folder, readonly=True)
        except MAIL_ERRORS:
            if inbox:
                raise
            folder = 'INBOX'
            mailbox.folder.set(folder, readonly=True)
        yield mailbox, folder
    except GmailError:
        raise
    except MAIL_ERRORS:
        raise GmailError(IMAP_ERROR) from None
    finally:
        try:
            # LOGOUT does not CLOSE/expunge the selected folder.
            mailbox.logout()
        except MAIL_ERRORS:
            pass


def messages(mailbox, last_uid: int, since: date | None):
    criteria = AND(uid=f'{last_uid + 1}:*') if last_uid else AND(date_gte=since) if since else 'ALL'
    for item in mailbox.fetch(criteria, mark_seen=False, reverse=False):
        uid = int(item.uid)
        # IMAP ranges containing '*' can include the current highest UID even when below the cursor.
        if uid <= last_uid:
            continue
        yield Message.from_email(item.obj, uid)
