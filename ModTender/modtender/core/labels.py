"""Readable names ModTender remembers for mod files that had to be renamed (Deadlock's pakNN_dir.vpk)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import paths


def _file(game_id: str) -> Path:
    folder = paths.data_dir() / "labels"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', game_id)}.json"


def get(game_id: str) -> dict[str, str]:
    try:
        return json.loads(_file(game_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def set_label(game_id: str, file_name: str, label: str) -> None:
    data = get(game_id)
    data[file_name] = label
    try:
        _file(game_id).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
