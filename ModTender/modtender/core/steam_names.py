"""Names for Steam games whose install manifest is missing (for example uninstalled games that
still have Workshop items). Looked up once from the Steam store and remembered."""
from __future__ import annotations

import json
import urllib.request

from .. import __version__
from . import paths
from .log import log


def _file():
    return paths.data_dir() / "steam_app_names.json"


def _load() -> dict:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def cached_name(appid: int) -> str:
    return _load().get(str(appid), "")


def fetch_names(appids: list[int], progress=None) -> dict:
    names = _load()
    for appid in appids:
        if str(appid) in names:
            continue
        req = urllib.request.Request(f"https://store.steampowered.com/api/appdetails?appids={appid}&filters=basic",
                                     headers={"User-Agent": f"ModTender/{__version__}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8")).get(str(appid), {})
            if data.get("success") and data.get("data", {}).get("name"):
                names[str(appid)] = data["data"]["name"]
        except Exception as exc:
            log.info("Couldn't look up the name of Steam app %s: %s", appid, exc)
            break
    try:
        _file().write_text(json.dumps(names), encoding="utf-8")
    except OSError:
        pass
    return names
