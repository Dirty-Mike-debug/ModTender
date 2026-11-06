"""Look up Steam Workshop item titles (items like Counter-Strike 2 maps carry no name on disk).

Uses Steam's public GetPublishedFileDetails endpoint (no API key needed). Titles are cached, so each
item is only looked up once; ModTender keeps working offline with the item numbers."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .. import __version__
from . import paths
from .log import log

API = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"


def _cache_file():
    return paths.data_dir() / "workshop_titles.json"


def load_cache() -> dict:
    try:
        return json.loads(_cache_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def apply_titles(mods, cache: dict | None = None) -> int:
    """Give untitled Workshop mods their cached title. Returns how many still have none."""
    cache = load_cache() if cache is None else cache
    missing = 0
    for m in mods:
        if m.workshop and not m.title:
            entry = cache.get(m.workshop_id)
            if entry and entry.get("title"):
                m.title = entry["title"]
            else:
                missing += 1
    return missing


def fetch_titles(ids: list[str], progress=None) -> dict:
    """Ask Steam for the titles of these items and add them to the cache. Returns the cache."""
    cache = load_cache()
    todo = [i for i in dict.fromkeys(ids) if i.isdigit() and i not in cache]
    for start in range(0, len(todo), 100):
        batch = todo[start:start + 100]
        form = {"itemcount": str(len(batch))}
        form.update({f"publishedfileids[{n}]": fid for n, fid in enumerate(batch)})
        req = urllib.request.Request(API, data=urllib.parse.urlencode(form).encode(),
                                     headers={"User-Agent": f"ModTender/{__version__}"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                details = json.loads(resp.read().decode("utf-8")).get("response", {}).get("publishedfiledetails", [])
        except Exception as exc:  # offline: keep the numbers for now
            log.info("Couldn't look up Workshop titles: %s", exc)
            break
        for d in details:
            fid = str(d.get("publishedfileid", ""))
            if fid:
                cache[fid] = {"title": d.get("title", ""), "updated": d.get("time_updated", 0)}
    try:
        _cache_file().write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass
    return cache
