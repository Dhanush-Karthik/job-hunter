"""Hirist technology job alert cards."""
from jobhunter.gmail.alerts.common import finish, html_cards, text_cards
from jobhunter.gmail.message import Message
from jobhunter.intake.types import RawJob


def parse(message: Message) -> list[RawJob]:
    return finish(message, html_cards(message, 'hirist', r'hirist\.(?:com|tech)/(?:j|job)/')
                  or text_cards(message, 'hirist'))
