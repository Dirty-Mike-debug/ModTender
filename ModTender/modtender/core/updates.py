"""Check GitHub Releases for a newer ModTender version."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from .. import UPDATE_REPO, __version__


class UpdateError(Exception):
    pass


@dataclass
class UpdateInfo:
    current: str
    latest: str
    newer: bool
    url: str  # release page to download from
    notes: str


def parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", text.split("-")[0])
    return tuple(int(n) for n in nums[:4]) or (0,)


def check_for_update(repo: str = UPDATE_REPO, progress=None) -> UpdateInfo:
    if not repo:
        raise UpdateError("Update checking isn't connected yet: ModTender doesn't have a release page to check.")
    if progress:
        progress(10, "Checking for updates…")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"ModTender/{__version__}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("No releases have been published yet.") from exc
        raise UpdateError(f"The update server answered with an error ({exc.code}). Try again later.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError("Couldn't reach the update server. Check your internet connection.") from exc
    except ValueError as exc:
        raise UpdateError("The update server sent an unreadable answer.") from exc

    latest = str(data.get("tag_name") or data.get("name") or "").lstrip("vV")
    if progress:
        progress(100, "Update check complete")
    return UpdateInfo(
        current=__version__,
        latest=latest or "?",
        newer=bool(latest) and parse_version(latest) > parse_version(__version__),
        url=data.get("html_url") or f"https://github.com/{repo}/releases",
        notes=(data.get("body") or "").strip()[:1500],
    )
