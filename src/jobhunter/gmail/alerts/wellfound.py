"""Wellfound role, company/employee count, and location cards."""
from jobhunter.gmail.alerts.common import finish, html_cards, text_cards
from jobhunter.gmail.message import Message
from jobhunter.intake.types import RawJob


def parse(message: Message) -> list[RawJob]:
    return finish(message, html_cards(message, 'wellfound', r'(?:wellfound\.com|angel\.co)/(?:.*(?:jobs|job)/|s/c/)')
                  or text_cards(message, 'wellfound'))
