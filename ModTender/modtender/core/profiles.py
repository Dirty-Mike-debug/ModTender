"""Mod profiles: named sets of turned-on mods, per game, that you can switch between in one click.

A profile remembers the file/folder names of the mods that were on. Switching turns on the profile's
mods and turns off the rest, the same way the Enable/Disable buttons do (by moving them in and out of
the game's mods folder), so it's always reversible. Before every switch the current setup is saved
as "Before switching", so a switch can be undone. Steam Workshop items and base-game files are left
alone: Steam decides which Workshop items are installed."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import manager, paths
from .log import log

UNDO_NAME = "Before switching"
FREE_PROFILES = 2

# Games whose own launcher or load-order file decides what loads: moving files would scramble it.
UNSUPPORTED = {
    "skyrimse": "Skyrim keeps its load order in plugins.txt, which switching would scramble",
    "fallout4": "Fallout 4 keeps its load order in plugins.txt, which switching would scramble",
    "bg3": "Baldur's Gate 3 would drop the missing mods from its mod list",
    "rimworld": "RimWorld would drop the missing mods from its active mod list",
    "arma3": "the Arma 3 Launcher already has presets for this",
    "dayz": "the DayZ Launcher picks the mods for each server",
    "reforger": "Arma Reforger picks the mods for each server itself",
    "warhammer3": "Total War's launcher keeps its own list of ticked mods (its playsets do this job)",
}


def unsupported_reason(game) -> str:
    if game is None:
        return "Pick a game first."
    if game.workshop_only:
        return (f"All of {game.name}'s mods come from the Steam Workshop, and Steam decides which ones are "
                "installed, so there's nothing for a profile to switch.")
    why = UNSUPPORTED.get(game.definition.id)
    return f"Profiles aren't available for {game.name}: {why}." if why else ""


def switchable(mods: list) -> list:
    return [m for m in mods if not m.workshop and not m.protected]


@dataclass
class Plan:
    turn_on: list = field(default_factory=list)
    turn_off: list = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # names in the profile that aren't installed any more

    @property
    def changes(self) -> int:
        return len(self.turn_on) + len(self.turn_off)


def _file(game_id: str) -> Path:
    folder = paths.data_dir() / "profiles"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', game_id)}.json"


def _load(game_id: str) -> dict:
    try:
        data = json.loads(_file(game_id).read_text(encoding="utf-8"))
        if isinstance(data.get("profiles"), dict):
            return data
    except (OSError, ValueError, AttributeError):
        pass
    return {"profiles": {}, "active": ""}


def _save(game_id: str, data: dict) -> None:
    _file(game_id).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def names(game_id: str) -> list[str]:
    """Profile names, the undo profile last."""
    profs = _load(game_id)["profiles"]
    return sorted((n for n in profs if n != UNDO_NAME), key=str.lower) + ([UNDO_NAME] if UNDO_NAME in profs else [])


def count(game_id: str) -> int:
    """How many profiles the user made (the automatic undo one doesn't count)."""
    return sum(n != UNDO_NAME for n in _load(game_id)["profiles"])


def active(game_id: str) -> str:
    return _load(game_id).get("active", "")


def get(game_id: str, name: str) -> dict | None:
    return _load(game_id)["profiles"].get(name)


def save(game_id: str, name: str, mods: list, make_active: bool = True) -> dict:
    """Remember which mods are on right now under this name (replacing a profile with the same name)."""
    name = name.strip()
    if not name:
        raise ValueError("Give the profile a name.")
    data = _load(game_id)
    on = sorted(m.name for m in switchable(mods) if m.enabled)
    data["profiles"][name] = {
        "mods": on,
        "titles": {m.name: m.display_name for m in switchable(mods) if m.enabled and m.display_name != m.name},
        "saved": datetime.now().isoformat(timespec="seconds"),
    }
    if make_active:
        data["active"] = name
    _save(game_id, data)
    log.info("[%s] Saved profile '%s' with %d mods", game_id, name, len(on))
    return data["profiles"][name]


def rename(game_id: str, old: str, new: str) -> None:
    new = new.strip()
    data = _load(game_id)
    if not new or old not in data["profiles"]:
        return
    if new in data["profiles"] and new != old:
        raise ValueError(f"There's already a profile called '{new}'.")
    data["profiles"][new] = data["profiles"].pop(old)
    if data.get("active") == old:
        data["active"] = new
    _save(game_id, data)


def delete(game_id: str, name: str) -> None:
    data = _load(game_id)
    data["profiles"].pop(name, None)
    if data.get("active") == name:
        data["active"] = ""
    _save(game_id, data)


def plan(game_id: str, name: str, mods: list) -> Plan:
    prof = get(game_id, name)
    if prof is None:
        raise ValueError(f"There's no profile called '{name}'.")
    want = set(prof["mods"])
    mods = switchable(mods)
    have = {m.name for m in mods}
    return Plan(
        turn_on=[m for m in mods if m.name in want and not m.enabled],
        turn_off=[m for m in mods if m.name not in want and m.enabled],
        missing=sorted(prof.get("titles", {}).get(n, n) for n in want - have),
    )


def matches(game_id: str, name: str, mods: list) -> bool:
    try:
        return plan(game_id, name, mods).changes == 0
    except ValueError:
        return False


def current_match(game_id: str, mods: list) -> str:
    """The profile that matches the mods that are on right now ('' if none)."""
    act = active(game_id)
    if act and matches(game_id, act, mods):
        return act
    return next((n for n in names(game_id) if n != UNDO_NAME and matches(game_id, n, mods)), "")


def switch(game, name: str, mods: list) -> tuple[Plan, list[str]]:
    """Turn on the profile's mods and turn off the rest. Returns the plan and any errors."""
    p = plan(game.id, name, mods)
    if name != UNDO_NAME and not current_match(game.id, mods):
        save(game.id, UNDO_NAME, mods, make_active=False)  # so the switch can be undone
    errors = []
    for m in p.turn_off:
        try:
            manager.disable_mod(game, m)
        except (manager.ModActionError, OSError) as exc:
            errors.append(f"{m.display_name}: {exc}")
    for m in p.turn_on:
        try:
            manager.enable_mod(game, m)
        except (manager.ModActionError, OSError) as exc:
            errors.append(f"{m.display_name}: {exc}")
    data = _load(game.id)
    data["active"] = name if name != UNDO_NAME else ""
    _save(game.id, data)
    log.info("[%s] Switched to profile '%s': %d on, %d off, %d missing, %d errors", game.id, name,
             len(p.turn_on), len(p.turn_off), len(p.missing), len(errors))
    return p, errors
