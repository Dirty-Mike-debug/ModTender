"""Deadlock: mods are .vpk files in Deadlock/game/citadel/addons.

Rules the game enforces:
  - only files named pak01_dir.vpk ... pak99_dir.vpk load (big mods also have pak01_000.vpk parts),
  - when two mods change the same file, the lower number wins,
  - nothing in addons loads unless game/citadel/gameinfo.gi has a "Game citadel/addons" search path,
    and every game update puts back the original gameinfo.gi.
ModTender reads each .vpk's file list to find mods that override each other."""
from __future__ import annotations

import re
import shutil
import stat
import struct
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .log import log

VALID = re.compile(r"^pak(\d{2})_dir\.vpk$", re.I)
PART = re.compile(r"^(.+)_(\d{3})\.vpk$", re.I)
ADDONS_LINE = re.compile(r"^\s*Game\s+citadel/addons\s*$", re.M | re.I)


# ---------------------------------------------------------------- gameinfo.gi

def gameinfo(mods_dir: Path) -> Path:
    return mods_dir.parent / "gameinfo.gi"  # addons -> citadel


def addons_enabled(mods_dir: Path) -> bool | None:
    """True/False, or None when gameinfo.gi can't be read."""
    try:
        text = gameinfo(mods_dir).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    uncommented = "\n".join(line.split("//")[0] for line in text.splitlines())
    return bool(ADDONS_LINE.search(uncommented))


def enable_addons(mods_dir: Path) -> str:
    """Add 'Game citadel/addons' to gameinfo.gi, keeping a backup of the original."""
    gi = gameinfo(mods_dir)
    text = gi.read_text(encoding="utf-8", errors="ignore")
    if addons_enabled(mods_dir):
        return "Deadlock was already set up to load mods"
    backup = gi.with_name(f"gameinfo.gi.modtender-backup-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(gi, backup)
    lines = text.splitlines(keepends=True)
    out, done, in_paths = [], False, False
    for line in lines:
        bare = line.split("//")[0].strip()
        if bare.lower() == "searchpaths":
            in_paths = True
        if in_paths and not done and re.match(r"^(Mod|Game|Write)\s+citadel\b", bare, re.I) \
                and not bare.lower().startswith("game_"):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f"{indent}Game\t\t\t\tcitadel/addons\n")
            done = True
        out.append(line)
    if not done:
        raise OSError("couldn't find where to add it in gameinfo.gi (the file may have changed format)")
    mode = gi.stat().st_mode
    if not mode & stat.S_IWRITE:
        gi.chmod(mode | stat.S_IWRITE)  # Deadlock Mod Manager sometimes leaves it read-only
    gi.write_text("".join(out), encoding="utf-8")
    log.info("Enabled addons in %s (backup %s)", gi, backup.name)
    return "Set up gameinfo.gi so Deadlock loads mods (the original was backed up)"


# ---------------------------------------------------------------- names

def number(name: str) -> int | None:
    m = VALID.match(name)
    return int(m.group(1)) if m else None


def used_numbers(mods_dir: Path) -> set[int]:
    try:
        return {n for p in mods_dir.iterdir() if (n := number(p.name)) is not None}
    except OSError:
        return set()


def next_free(taken: set[int]) -> int | None:
    return next((n for n in range(1, 100) if n not in taken), None)


def rename_plan(mods_dir: Path, names: list[str]) -> list[tuple[str, str]]:
    """New pakNN_dir.vpk names for misnamed mods (with their _000 parts), using free numbers."""
    taken = used_numbers(mods_dir)
    try:
        present = {p.name for p in mods_dir.iterdir()}
    except OSError:
        present = set()
    plan = []
    for name in names:
        n = next_free(taken)
        if n is None:
            break
        taken.add(n)
        base = re.sub(r"(_dir)?\.vpk$", "", name, flags=re.I)
        plan.append((name, f"pak{n:02d}_dir.vpk"))
        for other in sorted(present):
            m = PART.match(other)
            if m and m.group(1).lower() == base.lower():
                plan.append((other, f"pak{n:02d}_{m.group(2)}.vpk"))
    return plan


def _misnamed(mods: list) -> list:
    out = []
    for m in mods:
        if not m.enabled or not m.name.lower().endswith(".vpk") or VALID.match(m.name):
            continue
        part = PART.match(m.name)
        if part and part.group(1).lower().startswith("pak"):
            continue  # a data part of a correctly named mod (pak03_000.vpk)
        if part:
            continue  # data part of a misnamed mod: renamed together with its _dir file
        out.append(m)
    return out


# ---------------------------------------------------------------- reading a .vpk

def read_paths(path: Path) -> set[str] | None:
    """Every file path inside a VPK (version 1 or 2) directory file."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(12)
            if len(head) < 12:
                return None
            sig, version, tree_size = struct.unpack("<III", head)
            if sig != 0x55AA1234 or version not in (1, 2):
                return None
            if version == 2:
                fh.read(16)
            tree = fh.read(min(tree_size, 64_000_000))
    except OSError:
        return None
    out, pos = set(), 0

    def string() -> str:
        nonlocal pos
        end = tree.find(b"\0", pos)
        if end < 0:
            raise ValueError
        s, pos = tree[pos:end].decode("utf-8", "replace"), end + 1
        return s

    try:
        while True:
            ext = string()
            if not ext:
                break
            while True:
                folder = string()
                if not folder:
                    break
                while True:
                    name = string()
                    if not name:
                        break
                    preload = struct.unpack_from("<IHHIIH", tree, pos)[1]
                    pos += 18 + preload
                    out.add(f"{'' if folder == ' ' else folder + '/'}{name}.{ext}".lower())
    except (ValueError, struct.error):
        pass  # truncated tree: use what was read
    return out


# ---------------------------------------------------------------- checks

def analyze_deadlock(mods: list, mods_dir: Path) -> list[dict]:
    out = []
    vpks = [m for m in mods if m.enabled and m.name.lower().endswith(".vpk")]
    if not vpks:
        return out
    if addons_enabled(mods_dir) is False:
        out.append({
            "severity": "critical",
            "title": "Deadlock isn't set up to load mods",
            "detail": "Deadlock only loads mods when its gameinfo.gi file has a 'Game citadel/addons' line, and "
                      "every game update puts the original file back. Right now it's missing, so none of your "
                      f"{len(vpks)} mod{'s' if len(vpks) != 1 else ''} will load.",
            "fix": "If you use Deadlock Mod Manager, just start the game with its Launch Modded button. Otherwise "
                   "ModTender can add the line for you (the original file is backed up next to it).",
            "mods": [],
            "action": "deadlock_gameinfo", "params": {}, "action_label": "Set up gameinfo.gi to load mods",
            "safe": False,  # Deadlock Mod Manager also manages this file: let the player choose
        })
    bad = _misnamed(mods)
    if bad:
        plan = rename_plan(mods_dir, [m.name for m in bad])
        lines = "\n".join(f"  - {old} → {new}" for old, new in plan if old in {m.name for m in bad})
        out.append({
            "severity": "warning",
            "title": f"Deadlock won't load {'these mods' if len(bad) > 1 else 'this mod'}: wrong file name",
            "detail": "Deadlock only loads mods named pak01_dir.vpk to pak99_dir.vpk. ModTender can rename "
                      f"{'them' if len(bad) > 1 else 'it'} to free numbers and remember the original names:\n{lines}",
            "fix": "Rename to a free pakNN_dir.vpk number. Lower numbers win when mods change the same thing.",
            "mods": [m.name for m in bad],
            "action": "deadlock_rename", "params": {"pairs": plan},
            "action_label": f"Rename {len(bad)} mod{'s' if len(bad) != 1 else ''} so Deadlock loads them",
            "safe": True,
        })
    # Overrides: the lowest number wins each file.
    ordered = sorted((m for m in vpks if number(m.name) is not None), key=lambda m: number(m.name))
    owner: dict[str, object] = {}
    lost: dict[tuple, int] = defaultdict(int)
    for m in ordered:
        for f in read_paths(m.path) or set():
            if f in owner:
                lost[(owner[f].name, m.name)] += 1
            else:
                owner[f] = m
    by_name = {m.name: m for m in mods}
    for (winner, loser), n in sorted(lost.items()):
        w, l = by_name[winner], by_name[loser]
        out.append({
            "severity": "info",
            "title": "Two mods change the same files",
            "detail": f"{_who(l)} and {_who(w)} both change {n} "
                      f"file{'s' if n != 1 else ''}. Deadlock uses {w.display_name}'s version, because lower "
                      "numbers win.",
            "fix": f"That's fine if you meant it (for example two skins for the same hero). To use "
                   f"{l.display_name}'s version instead, give it a lower number than {winner}.",
            "mods": [loser, winner],
        })
    return out


def _who(m) -> str:
    return m.name if m.display_name == m.name else f"{m.display_name} ({m.name})"


def apply_renames(game, pairs: list) -> list[str]:
    from . import labels
    done = []
    for old, new in pairs:
        src, dest = game.mods_dir / old, game.mods_dir / new
        if not src.exists() or dest.exists():
            continue
        src.rename(dest)
        if VALID.match(new):
            labels.set_label(game.id, new, labels.get(game.id).get(old) or re.sub(r"(_dir)?\.vpk$", "", old, flags=re.I))
            done.append(f"Renamed {old} to {new}")
    return done
