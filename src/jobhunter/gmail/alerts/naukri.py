"""Naukri title/company cards with experience, salary and apply links."""
from jobhunter.gmail.alerts.common import finish, html_cards, text_cards
from jobhunter.gmail.message import Message
from jobhunter.intake.types import RawJob


def parse(message: Message) -> list[RawJob]:
    return finish(message, html_cards(message, 'naukri', r'naukri\.com/(?:job-listings|job)/')
                  or text_cards(message, 'naukri'))
