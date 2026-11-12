"""Settings: defaults from config yml, live values in the settings table (key 'app')."""

from __future__ import annotations

from pathlib import Path

import yaml
from sqlmodel import Session

from jobhunter import paths
from jobhunter.models import SettingRow
from jobhunter.schemas import Settings

KEY = "app"


def load_defaults(path: Path | None = None) -> Settings:
    p = path or (paths.CONFIG_PATH if paths.CONFIG_PATH.exists() else paths.CONFIG_EXAMPLE)
    return Settings.model_validate(yaml.safe_load(p.read_text()))


def get_settings(s: Session) -> Settings:
    row = s.get(SettingRow, KEY)
    if row is None:
        settings = load_defaults()
        s.add(SettingRow(key=KEY, value=settings.model_dump(mode="json")))
        s.commit()
        return settings
    return Settings.model_validate(row.value)


def save_settings(s: Session, settings: Settings) -> Settings:
    row = s.get(SettingRow, KEY) or SettingRow(key=KEY)
    row.value = settings.model_dump(mode="json")
    s.add(row)
    s.commit()
    return settings
