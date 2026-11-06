"""Skyrim SE and Fallout 4 plugins (.esm/.esp/.esl): masters, load order and limits.

A plugin's header (the TES4 record at the start of the file) lists the 'masters' it needs.
If a master is missing or turned off, the game crashes on startup. If a master loads after a
plugin that needs it, things break in subtler ways."""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

LIGHT_FLAG = 0x200  # ESL flag in the TES4 record header
MASTER_FLAG = 0x1
FULL_LIMIT = 254  # .esm/.esp slots (0x00-0xFD)
LIGHT_LIMIT = 4096

# plugins.txt / the implicit base plugins per game
GAMES = {
    "skyrimse": {
        "plugins_txt": ["Skyrim Special Edition", "Skyrim Special Edition GOG", "Skyrim Special Edition MS"],
        "base": ["Skyrim.esm", "Update.esm", "Dawnguard.esm", "HearthFires.esm", "Dragonborn.esm"],
        "ccc": "Skyrim.ccc",
    },
    "fallout4": {
        "plugins_txt": ["Fallout4", "Fallout4 GOG"],
        "base": ["Fallout4.esm", "DLCRobot.esm", "DLCworkshop01.esm", "DLCCoast.esm", "DLCworkshop02.esm",
                 "DLCworkshop03.esm", "DLCNukaWorld.esm", "DLCUltraHighResolution.esm"],
        "ccc": "Fallout4.ccc",
    },
}


@dataclass
class PluginInfo:
    name: str
    masters: list[str] = field(default_factory=list)
    light: bool = False
    is_master: bool = False
    error: str = ""


def read_header(path: Path) -> PluginInfo:
    info = PluginInfo(path.name)
    ext = path.suffix.lower()
    info.light = ext == ".esl"
    info.is_master = ext in (".esm", ".esl")
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
            if len(head) < 24 or head[:4] != b"TES4":
                info.error = "Not a valid plugin file (it may be damaged or for another game)."
                return info
            size, flags = struct.unpack_from("<II", head, 4)
            data = fh.read(min(size, 1_000_000))
    except OSError as exc:
        info.error = f"Couldn't read the plugin: {exc}"
        return info
    info.light = info.light or bool(flags & LIGHT_FLAG)
    info.is_master = info.is_master or bool(flags & MASTER_FLAG)
    pos = 0
    while pos + 6 <= len(data):
        sub, length = struct.unpack_from("<4sH", data, pos)
        pos += 6
        if sub == b"XXXX":  # next subrecord is bigger than 65535 bytes
            (length,) = struct.unpack_from("<I", data, pos)
            pos += 4
            sub, _ = struct.unpack_from("<4sH", data, pos)
            pos += 6
        if sub == b"MAST":
            name = data[pos:pos + length].split(b"\0", 1)[0].decode("cp1252", errors="replace")
            if name:
                info.masters.append(name)
        pos += length
    return info


def find_plugins_txt(game_id: str) -> Path | None:
    for folder in GAMES.get(game_id, {}).get("plugins_txt", []):
        f = paths.LOCALAPPDATA / folder / "plugins.txt"
        if f.is_file():
            return f
    return None


def read_load_order(game_id: str, data_dir: Path) -> tuple[list[str], set[str], Path | None]:
    """(load order, active plugins (lowercase), plugins.txt path). Base game plugins come first."""
    cfg = GAMES[game_id]
    order: list[str] = [p for p in cfg["base"] if (data_dir / p).exists()]
    ccc = data_dir.parent / cfg["ccc"]  # Creation Club list lives next to the game's exe
    if ccc.is_file():
        for line in ccc.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and (data_dir / line).exists():
                order.append(line)
    active = {p.lower() for p in order}
    txt = find_plugins_txt(game_id)
    if txt:
        for line in txt.read_text(encoding="cp1252", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name = line.lstrip("*")
            if name.lower() not in {o.lower() for o in order}:
                order.append(name)
            if line.startswith("*"):
                active.add(name.lower())
    return order, active, txt


def analyze_plugins(game_id: str, data_dir: Path) -> list[dict]:
    """Problems as dicts (severity, title, detail, fix, mods) for issues.py to turn into Issues."""
    if game_id not in GAMES or not data_dir.is_dir():
        return []
    installed = {p.name.lower(): p for p in data_dir.iterdir()
                 if p.is_file() and p.suffix.lower() in (".esm", ".esp", ".esl")}
    order, active, txt = read_load_order(game_id, data_dir)
    position = {name.lower(): i for i, name in enumerate(order)}
    out = []

    if txt is None and len(installed) > len(GAMES[game_id]["base"]) + 5:
        out.append({"severity": "info", "title": "Load order not found",
                    "detail": "ModTender couldn't find plugins.txt, so it can't check which plugins are turned on. "
                              "If you use Mod Organizer 2, your mods live in MO2's own folders instead.",
                    "fix": "Launch the game (or your mod manager) once, then scan again.", "mods": []})
        return out

    infos = {k: read_header(p) for k, p in installed.items() if k in active}
    full = sum(1 for i in infos.values() if not i.light)
    light = sum(1 for i in infos.values() if i.light)

    for key, info in sorted(infos.items()):
        if info.error:
            out.append({"severity": "critical", "title": "Damaged plugin", "detail": f"{info.name}: {info.error}",
                        "fix": "Reinstall the mod this plugin came from.", "mods": [info.name]})
            continue
        missing = [m for m in info.masters if m.lower() not in installed]
        off = [m for m in info.masters if m.lower() in installed and m.lower() not in active]
        late = [m for m in info.masters if m.lower() in active and position.get(m.lower(), -1) > position.get(key, 10**6)]
        if missing:
            out.append({"severity": "critical", "title": "Plugin is missing a required master",
                        "detail": f"{info.name} needs these files, which aren't installed:\n"
                                  + "\n".join(f"  - {m}" for m in missing)
                                  + "\n\nThe game will crash on startup while this plugin is turned on.",
                        "fix": "Install the mods that provide these files (check the mod's Requirements on its "
                               "download page), or turn this plugin off.", "mods": [info.name] + missing})
        if off:
            out.append({"severity": "critical", "title": "Required master is turned off",
                        "detail": f"{info.name} needs these plugins, which are installed but turned off:\n"
                                  + "\n".join(f"  - {m}" for m in off)
                                  + "\n\nThe game will crash on startup.",
                        "fix": "Turn them on in your mod manager (or the game's Mods menu).", "mods": [info.name] + off})
        if late:
            out.append({"severity": "warning", "title": "Master loads after the plugin that needs it",
                        "detail": f"{info.name} loads before these masters it needs:\n"
                                  + "\n".join(f"  - {m}" for m in late),
                        "fix": "Move the masters above it in your load order (LOOT can sort this automatically).",
                        "mods": [info.name] + late})

    if full > FULL_LIMIT:
        out.append({"severity": "critical", "title": "Too many plugins",
                    "detail": f"{full} regular plugins are turned on, but the game can only load {FULL_LIMIT}.",
                    "fix": "Turn some off, or merge them / use ESL-flagged versions.", "mods": []})
    if light > LIGHT_LIMIT:
        out.append({"severity": "critical", "title": "Too many light plugins",
                    "detail": f"{light} light (.esl) plugins are turned on, but the game can only load {LIGHT_LIMIT}.",
                    "fix": "Turn some off.", "mods": []})

    base = {b.lower() for b in GAMES[game_id]["base"]}
    unused = sorted((p.name for k, p in installed.items()
                     if k not in active and k not in base and not re.match(r"^cc", k)), key=str.lower)
    if unused:
        out.append({"severity": "info", "title": "Plugins installed but turned off",
                    "detail": f"{len(unused)} plugin(s) are in the Data folder but not turned on:\n"
                              + "\n".join(f"  - {u}" for u in unused[:15]) + (" …" if len(unused) > 15 else ""),
                    "fix": "That's fine if you turned them off on purpose. Otherwise turn them on in your mod manager.",
                    "mods": unused})
    return out
