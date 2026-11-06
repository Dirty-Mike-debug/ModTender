"""'Where to get mods' database.

A copy ships with ModTender (assets/mod_sources.json). The latest version is also fetched from the
GitHub repository, so the list can be corrected or extended without releasing a new app version."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from .. import UPDATE_REPO, __version__
from . import paths
from .log import log

BUNDLED = Path(__file__).resolve().parents[1] / "assets" / "mod_sources.json"
REMOTE = "https://raw.githubusercontent.com/{repo}/main/ModTender/modtender/assets/mod_sources.json"


def _cache() -> Path:
    return paths.data_dir() / "mod_sources.json"


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data.get("games"), dict) else None
    except (OSError, ValueError, AttributeError):
        return None


def load_sources() -> dict:
    """The newest list available offline: the downloaded copy if it's newer than the bundled one."""
    bundled = _read(BUNDLED) or {"games": {}, "general_tips": [], "kinds": {}}
    cached = _read(_cache())
    if cached and str(cached.get("updated", "")) > str(bundled.get("updated", "")):
        return cached
    return bundled


def refresh_sources(repo: str = UPDATE_REPO, progress=None) -> dict:
    """Download the latest list from GitHub and cache it. Returns the list to show."""
    if repo:
        req = urllib.request.Request(REMOTE.format(repo=repo), headers={"User-Agent": f"ModTender/{__version__}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data.get("games"), dict):
                _cache().write_text(json.dumps(data, indent=1), encoding="utf-8")
        except Exception as exc:  # offline or GitHub unavailable: the offline copy is fine
            log.info("Couldn't refresh the mod sources list: %s", exc)
    return load_sources()


def for_game(data: dict, game_id: str) -> dict:
    games = data.get("games", {})
    return games.get(game_id) or games.get("custom") or {"sources": [], "tips": []}
