"""Owner secrets in the OS keychain (macOS Keychain via keyring). Values are never logged or returned by the API.

`start.sh doctor` looks items up with `security find-generic-password -s jobhunter -a <name>`, so the keyring
service and account names here must stay as they are.
"""

from __future__ import annotations

import keyring

SERVICE = "jobhunter"
NAMES = ("gmail_address", "gmail_app_password")


def get(name: str) -> str | None:
    return keyring.get_password(SERVICE, name) or None


def present(name: str) -> bool:
    return get(name) is not None


def put(name: str, value: str) -> None:
    keyring.set_password(SERVICE, name, value)
