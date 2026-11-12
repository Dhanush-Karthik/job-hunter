"""Cutshort numbered digests and HTML job cards."""
from jobhunter.gmail.alerts.common import finish, html_cards, text_cards
from jobhunter.gmail.message import Message
from jobhunter.intake.types import RawJob


def parse(message: Message) -> list[RawJob]:
    return finish(message, text_cards(message, 'cutshort')
                  or html_cards(message, 'cutshort', r'cutshort\.io/job/'))
