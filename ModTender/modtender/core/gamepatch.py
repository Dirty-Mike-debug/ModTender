"""Notice when Steam updates a game, and warn which mods usually break after a patch.

Steam keeps an appmanifest_<appid>.acf for every installed game, with a "buildid" that changes on
every update and StateFlags that say when an update is waiting. ModTender remembers the build it
last saw for each game (game_builds.json). When it changes, the Issues page warns about the mods
most likely to need an update (script extenders, BepInEx plugins, SMAPI, ...) until you dismiss it."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from . import paths
from .log import log

# Steam app ids for the games ModTender knows (GameDef only carries some of them).
APP_IDS = {
    "fs25": 2300320, "fs22": 1248130, "stardew": 413150, "skyrimse": 489830, "fallout4": 377160,
    "witcher3": 292030, "cyberpunk": 1091500, "bg3": 1086940, "valheim": 892970, "rimworld": 294100,
    "ets2": 227300, "ats": 270880, "sims4": 1222670, "cs2": 949230, "snowrunner": 1465360,
    "arma3": 107410, "reforger": 1874880, "deadlock": 1422450,
    "dayz": 221100, "warhammer3": 1142710, "planetzoo": 703080,
}

# What tends to break after a patch, per game: (what to look for, advice).
RISKS = {
    "skyrimse": ("SKSE plugins (.dll files in Data\\SKSE\\Plugins) and Address Library",
                 "Don't launch through SKSE until SKSE and your .dll plugins have updates for this game "
                 "version. Plugins (.esp/.esm) themselves usually keep working."),
    "fallout4": ("F4SE plugins (.dll files in Data\\F4SE\\Plugins) and Address Library",
                 "Wait for F4SE and your .dll plugins to update for this game version before launching "
                 "through F4SE."),
    "cyberpunk": ("Cyber Engine Tweaks, RED4ext, ArchiveXL, TweakXL and Codeware",
                  "These frameworks almost always need an update after a Cyberpunk patch. Check their "
                  "Nexus pages before launching; mods built on them won't work until they're updated."),
    "bg3": ("Script Extender and mods that need it",
            "Update the BG3 Script Extender first. The game may also reset your mod order, so check "
            "your mod manager's load order."),
    "valheim": ("BepInEx plugins (.dll mods)",
                "Code mods often break after Valheim updates. Check each mod's page (Thunderstore or "
                "Nexus) for an update before you join a world."),
    "stardew": ("SMAPI and code mods",
                "Big Stardew updates need a new SMAPI. Run the SMAPI installer again if the game won't "
                "start, and update any mod SMAPI says is out of date."),
    "witcher3": ("Script mods",
                 "Run Script Merger again after a patch: game updates can change the scripts your mods "
                 "are merged with."),
    "fs25": ("Script mods",
             "Most Farming Simulator mods keep working, but mods with scripts can break after a patch. "
             "Check ModHub for updates if something stops working."),
    "fs22": ("Script mods",
             "Most Farming Simulator mods keep working, but mods with scripts can break after a patch. "
             "Check ModHub for updates if something stops working."),
    "deadlock": ("Every mod, until gameinfo.gi is set up again",
                 "Deadlock updates put the original gameinfo.gi back, which switches all mods off. ModTender "
                 "flags it on the Issues page with a one-click fix. HUD and hero mods may also need updates "
                 "from GameBanana after big patches."),
    "arma3": ("Mods built on CBA_A3 and ACE, and mods with .dll extensions",
              "After a big Arma 3 update, wait for CBA_A3 and ACE to update first; most other mods depend on "
              "them. Servers usually update on their own schedule, so check your group's announcements."),
    "reforger": ("Almost every mod",
                 "Reforger updates often change things mods rely on. The Workshop menu shows which mods have "
                 "updates; servers won't let you join until your mods match theirs again."),
    "dayz": ("Almost every mod, starting with Community Framework (CF)",
             "After a DayZ update, wait for CF and Dabs Framework to update first. Servers won't let you join until "
             "your mods match theirs, and the DayZ Launcher re-downloads them when they do."),
    "warhammer3": ("Mods that change units, factions or scripts",
                   "Big Warhammer III patches break many mods until they're updated. Turn mods off in the launcher "
                   "before a campaign, and don't continue a modded campaign until its mods are updated."),
    "planetzoo": ("ACSE and new-species mods",
                  "After a Planet Zoo update, update ACSE first: most species mods need it. Remove mods that "
                  "haven't been updated if the game won't load."),
    "rimworld": ("Mods made for the previous version",
                 "After a major RimWorld version, mods need updating to the new version. The in-game mod "
                 "list marks the ones that aren't."),
    "ets2": ("Mods made for the previous version",
             "After a major update, map and truck mods often need new versions. The in-game mod manager "
             "marks mods made for older versions."),
    "ats": ("Mods made for the previous version",
            "After a major update, map and truck mods often need new versions. The in-game mod manager "
            "marks mods made for older versions."),
}
FRAMEWORK_HINTS = ("cyber_engine_tweaks", "red4ext", "archivexl", "tweakxl", "codeware", "skse", "f4se",
                   "address library", "addresslibrary", "bepinex", "jotunn", "smapi", "scriptextender")
UPDATE_REQUIRED = 2  # StateFlags bit: Steam has an update waiting


def _state_file() -> Path:
    return paths.data_dir() / "game_builds.json"


def _load() -> dict:
    try:
        return json.loads(_state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    try:
        _state_file().write_text(json.dumps(data, indent=1), encoding="utf-8")
    except OSError:
        pass


def app_id(game) -> int:
    return game.steam_appid or game.definition.steam_appid or APP_IDS.get(game.definition.id, 0)


def read_manifest(appid: int, libraries: list[Path] | None = None) -> dict | None:
    """buildid, LastUpdated and StateFlags from Steam's appmanifest for this game."""
    if not appid:
        return None
    if libraries is None:
        from .games import steam_libraries
        libraries = steam_libraries()
    for lib in libraries:
        acf = lib / "steamapps" / f"appmanifest_{appid}.acf"
        try:
            text = acf.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        values = dict(re.findall(r'^\s*"(buildid|LastUpdated|StateFlags|name|installdir)"\s+"([^"]*)"', text, re.M))
        if values.get("buildid"):
            return values
    return None


def _risky_mods(game, mods: list) -> list:
    """Mods most likely to break: code mods (.dll) and the frameworks other mods sit on."""
    out = []
    for m in mods:
        if not m.enabled:
            continue
        name = f"{m.name} {m.title} {m.mod_id}".lower().replace(" ", "")
        code = m.name.lower().endswith(".dll") or any(f.lower().endswith(".dll") for f in m.root_files[:50])
        if code or any(h.replace(" ", "") in name for h in FRAMEWORK_HINTS):
            out.append(m)
    return out


def check(game, mods: list, libraries: list[Path] | None = None) -> list[dict]:
    """Issues about game updates. Records the current build the first time it sees a game."""
    appid = app_id(game)
    info = read_manifest(appid, libraries)
    if not info:
        return []
    key = game.definition.id if game.source != "workshop" else game.id
    state = _load()
    seen = state.get(key)
    build = info["buildid"]
    title = re.sub(r"\s*\(.*\)\s*$", "", game.definition.name)  # "Valheim (BepInEx)" -> "Valheim"
    out = []
    if seen is None:
        state[key] = {"buildid": build, "seen": datetime.now().isoformat(timespec="seconds")}
        _save(state)
    elif seen.get("buildid") != build:
        what, advice = RISKS.get(game.definition.id, ("Mods with code", "Mods that run code are the most likely "
                                                      "to break. Check their pages for updates if something "
                                                      "stops working."))
        when = ""
        try:
            when = datetime.fromtimestamp(int(info.get("LastUpdated", "0"))).strftime(" on %b %d")
        except (ValueError, OSError):
            pass
        risky = _risky_mods(game, mods)
        lines = "\n".join(f"  - {m.display_name}" for m in risky[:20]) + (
            f"\n  ...and {len(risky) - 20} more" if len(risky) > 20 else "")
        out.append({
            "severity": "warning",
            "title": f"{title} was updated",
            "detail": f"Steam updated {title}{when} (build {seen.get('buildid')} → {build}). "
                      f"What usually breaks after an update: {what}.\n\n{advice}"
                      + (f"\n\nYour mods most likely to be affected:\n{lines}" if risky else ""),
            "fix": "Check those mods for updates, then dismiss this. If the game crashes, Find broken mod on "
                   "the Dashboard narrows it down.",
            "mods": [m.name for m in risky],
            "action": "ack_game_update", "params": {"key": key, "build": build},
            "action_label": "Dismiss: I've checked my mods",
        })
    if int(info.get("StateFlags", "0") or 0) & UPDATE_REQUIRED:
        out.append({
            "severity": "info",
            "title": f"Steam has an update waiting for {title}",
            "detail": "Steam will install it the next time the game starts (or sooner, depending on your "
                      "settings). Updates can break mods, especially ones that run code.",
            "fix": "Make a backup now (Backups page) so you can roll back if mods stop working. In Steam, "
                   "Properties → Updates → 'Only update this game when I launch it' gives you more control.",
            "mods": [],
        })
    return out


def acknowledge(key: str, build: str) -> None:
    state = _load()
    state[key] = {"buildid": build, "seen": datetime.now().isoformat(timespec="seconds")}
    _save(state)
    log.info("Game update for %s acknowledged (build %s)", key, build)
