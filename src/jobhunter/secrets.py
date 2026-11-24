"""Owner secrets: the OS keychain (macOS Keychain, Windows Credential Locker, Linux Secret Service) via keyring.

Headless machines without a keychain can set `JOBHUNTER_GMAIL_ADDRESS` and `JOBHUNTER_GMAIL_APP_PASSWORD` instead;
the keychain wins when both exist. Values are never logged or returned by the API.

`start.sh doctor` looks items up with `security find-generic-password -s jobhunter -a <name>` on macOS, so the keyring
service and account names here must stay as they are.
"""

from __future__ import annotations

import os

import keyring
from keyring.errors import KeyringError

SERVICE = "jobhunter"
NAMES = ("gmail_address", "gmail_app_password")


def _env(name: str) -> str | None:
    return os.environ.get(f"JOBHUNTER_{name.upper()}", "").strip() or None


def get(name: str) -> str | None:
    try:
        value = keyring.get_password(SERVICE, name) or None
    except KeyringError:
        if _env(name) is None:
            raise
        value = None
    return value or _env(name)


def present(name: str) -> bool:
    return get(name) is not None


def put(name: str, value: str) -> None:
    keyring.set_password(SERVICE, name, value)
