"""Foundit (formerly Monster India) recommendation cards."""
from jobhunter.gmail.alerts.common import finish, html_cards, text_cards
from jobhunter.gmail.message import Message
from jobhunter.intake.types import RawJob


def parse(message: Message) -> list[RawJob]:
    return finish(message, html_cards(message, 'foundit', r'(?:foundit\.(?:in|com)|monsterindia\.com)/.*job')
                  or text_cards(message, 'foundit'))
