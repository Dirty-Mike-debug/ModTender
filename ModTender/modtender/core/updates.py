"""Check GitHub Releases for a newer ModTender version."""
from __future__ import annotations

import json
import re
import sys
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
    asset_url: str = ""  # direct link to the release zip, used for in-app updating
    asset_size: int = 0


def parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", text.split("-")[0])
    return tuple(int(n) for n in nums[:4]) or (0,)


def _plain(markdown: str) -> str:
    """Release notes are Markdown; show them as plain text in the update dialog."""
    text = markdown.split("\n---")[0]  # drop the 'new install' footer
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"^\s*-\s+", "•  ", text, flags=re.M)
    return text.strip()


def is_app_build() -> bool:
    """True when running as the installed ModTender.exe (PyInstaller), not from Python source."""
    return bool(getattr(sys, "frozen", False))


def pick_asset(assets: list[dict]) -> dict:
    """The installer for the app build; the source zip for the script version."""
    named = [(str(a.get("name", "")).lower(), a) for a in assets]
    if sys.platform != "win32":
        return next((a for n, a in named if "linux" in n), {})  # Linux: shown as a download, not installed
    if is_app_build():
        return next((a for n, a in named if n.endswith(".exe") and "setup" in n), {})
    return next((a for n, a in named if n.endswith(".zip") and "portable" not in n), {})


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
    asset = pick_asset(data.get("assets") or [])
    if progress:
        progress(100, "Update check complete")
    return UpdateInfo(
        current=__version__,
        latest=latest or "?",
        newer=bool(latest) and parse_version(latest) > parse_version(__version__),
        url=data.get("html_url") or f"https://github.com/{repo}/releases",
        notes=_plain(data.get("body") or "")[:1500],
        asset_url=asset.get("browser_download_url", ""),
        asset_size=int(asset.get("size") or 0),
    )
