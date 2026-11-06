"""Baldur's Gate 3: compare the .pak files in the Mods folder with the game's mod list (modsettings.lsx)."""
from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from . import paths

BASE_MODULES = {"gustav", "gustavdev", "gustavx", "goded", "honour", "honourx", "mainui", "modbrowser"}


def modsettings_path() -> Path:
    return paths.LOCALAPPDATA / "Larian Studios" / "Baldur's Gate 3" / "PlayerProfiles" / "Public" / "modsettings.lsx"


def read_modsettings(path: Path) -> list[dict] | None:
    try:
        root = ElementTree.parse(path).getroot()
    except (OSError, ElementTree.ParseError):
        return None
    mods = []
    for node in root.iter("node"):
        if node.get("id") != "ModuleShortDesc":
            continue
        attrs = {a.get("id"): a.get("value", "") for a in node.findall("attribute")}
        mods.append({"folder": attrs.get("Folder", ""), "name": attrs.get("Name", ""), "uuid": attrs.get("UUID", "")})
    return mods


def analyze_bg3(mods_dir: Path) -> list[dict]:
    settings = modsettings_path()
    listed = read_modsettings(settings) if settings.is_file() else None
    paks = sorted((p for p in mods_dir.glob("*.pak") if p.is_file()), key=lambda p: p.name.lower()) \
        if mods_dir.is_dir() else []
    if listed is None:
        if paks:
            return [{"severity": "info", "title": "Mod list not found",
                     "detail": "ModTender couldn't read modsettings.lsx, so it can't check which mods are turned on.",
                     "fix": "Start the game once (or open your mod manager), then scan again.", "mods": []}]
        return []
    entries = [m for m in listed if m["folder"].lower() not in BASE_MODULES and m["name"].lower() not in BASE_MODULES]
    keys = {k.lower() for m in entries for k in (m["folder"], m["name"]) if k}
    norm = lambda s: s.lower().replace(" ", "").replace("_", "").replace("-", "")
    nkeys = {norm(k) for k in keys}
    pak_keys = {norm(p.stem) for p in paks}

    out = []
    not_listed = [p.name for p in paks if p.stem.lower() not in keys and norm(p.stem) not in nkeys]
    if not_listed:
        out.append({"severity": "info", "title": "Mods installed but not in your mod list",
                    "detail": f"{len(not_listed)} .pak file(s) don't appear in the game's mod list, so they're "
                              "probably not turned on:\n" + "\n".join(f"  - {n}" for n in not_listed[:15])
                              + (" …" if len(not_listed) > 15 else "")
                              + "\n\n(Some mods use a different name inside the file, so this can be a false alarm.)",
                    "fix": "Turn them on in the in-game Mod Manager or BG3 Mod Manager. Some mods, like "
                           "frameworks and overrides, work without being in the list.",
                    "mods": not_listed})
    missing = [m["name"] or m["folder"] for m in entries
               if norm(m["folder"]) not in pak_keys and norm(m["name"]) not in pak_keys]
    if missing and paks:
        out.append({"severity": "warning", "title": "Mod list has mods with no file",
                    "detail": "These mods are in the game's mod list, but ModTender can't find a matching .pak:\n"
                              + "\n".join(f"  - {n}" for n in missing[:15]) + (" …" if len(missing) > 15 else "")
                              + "\n\n(Mods from the in-game browser may use a different file name, so check before "
                                "removing anything.)",
                    "fix": "If you deleted these mods, remove them from the mod list in your mod manager. "
                           "A mod listed without its file can stop saves from loading.",
                    "mods": missing})
    return out
