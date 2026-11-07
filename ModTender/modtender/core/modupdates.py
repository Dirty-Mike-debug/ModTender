"""Check Modrinth for newer versions of Minecraft mods.

Each mod file is identified by its SHA-1, so this works no matter where it was downloaded from,
as long as the same file is also published on Modrinth. Two requests per check:
  POST /v2/version_files          -> the version each file currently is (to compare dates)
  POST /v2/version_files/update   -> the newest version for this loader and Minecraft version
Updating downloads the new file, checks its hash, and moves the old file to ModTender's
disabled-mods folder so it can be turned back on."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .. import UPDATE_REPO, __version__
from . import paths
from .log import log

API = "https://api.modrinth.com/v2"
USER_AGENT = f"{UPDATE_REPO}/{__version__} (github.com/{UPDATE_REPO})"
BATCH = 400


class UpdateCheckError(Exception):
    pass


@dataclass
class ModUpdate:
    mod_name: str  # file name in the mods folder
    title: str
    current: str
    new: str
    channel: str  # release | beta | alpha
    url: str
    filename: str
    sha1: str
    size: int
    project_id: str
    published: str

    @property
    def page(self) -> str:
        return f"https://modrinth.com/project/{self.project_id}"


@dataclass
class CheckResult:
    loader: str
    mc_version: str
    checked: int  # mod files looked up
    known: int  # of those, how many Modrinth recognised
    updates: list[ModUpdate]
    guessed_version: bool = False


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(f"{API}{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise UpdateCheckError("Modrinth is limiting requests right now. Try again in a minute.") from exc
        raise UpdateCheckError(f"Modrinth answered with an error ({exc.code}).") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise UpdateCheckError("Couldn't reach Modrinth. Check your internet connection.") from exc


def guess_mc_version(mods: list) -> str:
    """For folders without launcher info: the Minecraft version most mod file names mention."""
    found = Counter()
    for m in mods:
        hit = re.search(r"(?<![\d.])(1\.(?:1[6-9]|2\d)(?:\.\d{1,2})?)(?![\d])", m.name)
        if hit:
            found[hit.group(1)] += 1
    if not found:
        return ""
    version, n = found.most_common(1)[0]
    return version if n >= max(3, 0.3 * len(mods)) else ""


def check_updates(game, mods: list, progress=None) -> CheckResult:
    from .minecraft import LOADER_NAMES, instance_info
    loader, mc = instance_info(game.mods_dir)
    guessed = False
    jars = [m for m in mods if m.enabled and m.sha1 and m.name.lower().endswith(".jar")]
    if not loader:
        counts = Counter(l for m in jars for l in set(m.loaders))
        loader = counts.most_common(1)[0][0] if counts else ""
    if not mc:
        mc, guessed = guess_mc_version(jars), True
    if not loader or not mc:
        raise UpdateCheckError("ModTender couldn't tell which Minecraft version and mod loader this folder is "
                               "for, so it can't look for the right updates.")
    loaders = [loader] + (["fabric"] if loader == "quilt" else []) + \
              (["forge"] if loader == "neoforge" and mc.startswith("1.20.1") else [])
    by_hash = {m.sha1.lower(): m for m in jars}
    hashes = list(by_hash)
    current: dict = {}
    latest: dict = {}
    for i in range(0, len(hashes), BATCH):
        chunk = hashes[i:i + BATCH]
        if progress:
            progress(10 + 80 * i // max(1, len(hashes)), f"Asking Modrinth about {len(hashes)} mods…")
        current.update(_post("/version_files", {"hashes": chunk, "algorithm": "sha1"}))
        latest.update(_post("/version_files/update", {"hashes": chunk, "algorithm": "sha1",
                                                      "loaders": loaders, "game_versions": [mc]}))
    updates = []
    for h, new in latest.items():
        mod = by_hash.get(h.lower())
        if mod is None or not isinstance(new, dict):
            continue
        files = new.get("files") or []
        file = next((f for f in files if f.get("primary")), files[0] if files else None)
        if not file or (file.get("hashes") or {}).get("sha1", "").lower() == h.lower():
            continue  # already the newest
        cur = current.get(h) or {}
        if cur.get("date_published", "") >= new.get("date_published", "~"):
            continue  # the installed file is newer than anything matching (e.g. a beta)
        updates.append(ModUpdate(
            mod.name, mod.display_name, cur.get("version_number") or mod.version or "?",
            str(new.get("version_number", "")), str(new.get("version_type", "release")),
            str(file.get("url", "")), str(file.get("filename", "")),
            str((file.get("hashes") or {}).get("sha1", "")), int(file.get("size") or 0),
            str(new.get("project_id", "")), str(new.get("date_published", ""))[:10]))
    updates.sort(key=lambda u: u.title.lower())
    log.info("[%s] Mod update check: %d jars, %d known to Modrinth, %d updates (%s %s)", game.id, len(jars),
             len(current), len(updates), LOADER_NAMES.get(loader, loader), mc)
    return CheckResult(loader, mc, len(jars), len(current), updates, guessed)


def apply_updates(game, updates: list[ModUpdate], progress=None) -> tuple[list[str], list[str]]:
    """Download each update, verify it, and swap it in. Returns (done, problems)."""
    done, problems = [], []
    for n, u in enumerate(updates):
        if progress:
            progress(100 * n // max(1, len(updates)), f"Updating {u.title}…")
        if not u.url.startswith("https://") or not u.filename or "/" in u.filename or "\\" in u.filename:
            problems.append(f"{u.title}: Modrinth gave an unusable download")
            continue
        old = game.mods_dir / u.mod_name
        part = game.mods_dir / (u.filename + ".modtender-part")
        try:
            req = urllib.request.Request(u.url, headers={"User-Agent": USER_AGENT})
            h = hashlib.sha1()
            with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as out:
                while chunk := resp.read(1 << 16):
                    h.update(chunk)
                    out.write(chunk)
            if u.sha1 and h.hexdigest().lower() != u.sha1.lower():
                raise UpdateCheckError("the download didn't match Modrinth's checksum")
            from . import virusscan
            verdict = virusscan.scan_file(part)
            if verdict.flagged:
                raise OSError(f"{verdict.engine} flagged the download as {verdict.threat}, so it wasn't installed")
            if verdict.status == virusscan.CLEAN:
                virusscan.remember(h.hexdigest(), verdict)
            if old.exists():
                dest = paths.disabled_dir(game.id) / u.mod_name
                if dest.exists():
                    from .fixer import _quarantine
                    _quarantine(game, dest)
                shutil.move(str(old), str(dest))
            target = game.mods_dir / u.filename
            if target.exists():
                from .fixer import _quarantine
                _quarantine(game, target)
            part.replace(target)
            done.append(f"{u.title}: {u.current} → {u.new}")
        except (UpdateCheckError, urllib.error.URLError, OSError) as exc:
            problems.append(f"{u.title}: {exc}")
            part.unlink(missing_ok=True)
    log.info("[%s] Updated %d mod(s), %d failed", game.id, len(done), len(problems))
    return done, problems
