"""Persistent settings with schema version + automatic migration."""
from __future__ import annotations

import copy
import datetime as _dt
import json
from dataclasses import dataclass, field

from metadata_writer_pro.app import SETTINGS_SCHEMA_VERSION
from metadata_writer_pro.app.services.logger import get_logger
from metadata_writer_pro.app.utils import paths as paths_mod

log = get_logger("settings")

DEFAULTS = {
    "settings_version": SETTINGS_SCHEMA_VERSION,
    "theme": "system",  # system | light | dark
    "language": "en",
    "rename_enabled": True,
    "create_backup": False,
    "continue_on_error": True,
    "overwrite_metadata": True,
    "preserve_existing": True,
    "default_rating": 5,
    "write_fields": ["title", "description", "keywords"],
    "auto_check_updates": True,
    "log_level": "INFO",
}


@dataclass
class Settings:
    data: dict = field(default_factory=lambda: copy.deepcopy(DEFAULTS))

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        self.data[key] = value

    def to_dict(self) -> dict:
        return copy.deepcopy(self.data)


def _stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def _migrate(data: dict) -> dict:
    """Migrate old settings dicts up to the current schema version."""
    version = int(data.get("settings_version", 1))
    merged = copy.deepcopy(DEFAULTS)
    merged.update(data)
    if version < 2:
        # v2 introduced write_fields / preserve_existing / language
        merged.setdefault("write_fields", list(DEFAULTS["write_fields"]))
        merged.setdefault("preserve_existing", True)
        merged.setdefault("language", "en")
    merged["settings_version"] = SETTINGS_SCHEMA_VERSION
    return merged


def load_settings() -> Settings:
    path = paths_mod.settings_path()
    if not path.is_file():
        return Settings()
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, dict):
            raise ValueError("settings root must be an object")
        return Settings(_migrate(raw))
    except Exception as exc:  # corrupt settings must never crash the app
        try:
            backup = path.with_name(f"settings.corrupt.{_stamp()}.bak")
            path.replace(backup)
            log.warning("Backed up unreadable settings to %s", backup.name)
        except Exception:
            pass
        log.warning("Could not load settings (%s); using defaults.", exc)
        return Settings()


def save_settings(settings: Settings) -> None:
    path = paths_mod.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(settings.to_dict(), fh, ensure_ascii=False, indent=2)
    tmp.replace(path)


# Convenience singleton used by the UI
_current: Settings | None = None


def get_settings() -> Settings:
    global _current
    if _current is None:
        _current = load_settings()
    return _current


def update_and_save(**kwargs) -> Settings:
    s = get_settings()
    for k, v in kwargs.items():
        s.set(k, v)
    save_settings(s)
    return s
