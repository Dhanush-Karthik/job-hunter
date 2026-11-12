"""Uplers matched role cards and direct application links."""
from jobhunter.gmail.alerts.common import finish, html_cards, text_cards
from jobhunter.gmail.message import Message
from jobhunter.intake.types import RawJob


def parse(message: Message) -> list[RawJob]:
    return finish(message, html_cards(message, 'uplers', r'uplers\.(?:com|in)/.*(?:job|talent)')
                  or text_cards(message, 'uplers'))
