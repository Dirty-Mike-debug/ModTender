"""User settings, stored as JSON in ModTender's data folder."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from . import paths


@dataclass
class Settings:
    backup_dir: str = ""
    keep_backups: int = 10
    deep_check: bool = False  # verify every byte of every archive (slow on big collections)
    custom_games: list[dict] = field(default_factory=list)
    hidden_games: list[str] = field(default_factory=list)
    last_game: str = ""

    @property
    def backup_root(self):
        from pathlib import Path
        return Path(self.backup_dir) if self.backup_dir else paths.default_backup_dir()


def _file():
    return paths.data_dir() / "settings.json"


def load_settings() -> Settings:
    try:
        raw = json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    known = Settings.__dataclass_fields__
    return Settings(**{k: v for k, v in raw.items() if k in known})


def save_settings(s: Settings) -> None:
    tmp = _file().with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(s), indent=2), encoding="utf-8")
    tmp.replace(_file())
