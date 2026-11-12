"""One parser per supported alert platform."""
from importlib import import_module

from jobhunter.gmail import ALERT_SENDERS
from jobhunter.gmail.message import Message
from jobhunter.intake.types import RawJob


def parse(message: Message, sender: str) -> list[RawJob]:
    if sender not in ALERT_SENDERS:
        return []
    return import_module(f'jobhunter.gmail.alerts.{sender}').parse(message)
