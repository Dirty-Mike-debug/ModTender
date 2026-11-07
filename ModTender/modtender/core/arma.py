"""Arma 3 and Arma Reforger checks.

Arma 3 mods are folders (Steam Workshop items, or @Name folders in the game folder) holding
addons/*.pbo files and keys/*.bikey signing keys. Two mods that ship the same .pbo load it twice
(usually two copies of CBA or a mod bundled inside a pack), and mods without a .bikey get you
kicked from servers that check signatures.

Arma Reforger mods come from Bohemia's own workshop and live in Documents/My Games/ArmaReforger/
addons, one folder per mod with a ServerData.json (id, name, version, dependencies). The
dependency and "not fully downloaded" checks use that file (see scanner.py)."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path


def _sub(folder: Path, name: str) -> Path | None:
    """A subfolder by name, ignoring case (Addons / addons)."""
    try:
        return next((p for p in folder.iterdir() if p.is_dir() and p.name.lower() == name), None)
    except OSError:
        return None


def _files(folder: Path | None, ext: str) -> list[Path]:
    if folder is None:
        return []
    try:
        return [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ext]
    except OSError:
        return []


def analyze_arma3(mods: list) -> list[dict]:
    out = []
    owners: dict[str, list] = defaultdict(list)  # pbo name -> mods that ship it
    unsigned = []
    for m in mods:
        if not m.enabled or not m.path.is_dir():
            continue
        addons = _sub(m.path, "addons")
        pbos = _files(addons, ".pbo")
        for pbo in pbos:
            owners[pbo.name.lower()].append(m)
        if pbos and not _files(_sub(m.path, "keys"), ".bikey"):
            unsigned.append(m)

    clashes: dict[tuple, list[str]] = defaultdict(list)
    for pbo, who in owners.items():
        if len({id(m) for m in who}) > 1:
            clashes[tuple(sorted({m.name for m in who}))].append(pbo)
    by_name = {m.name: m for m in mods}
    for names, pbos in clashes.items():
        titles = [by_name[n].display_name for n in names]
        out.append({
            "severity": "warning",
            "title": "Two mods contain the same addon",
            "detail": f"{', '.join(titles)} both include {len(pbos)} of the same addon file"
                      f"{'s' if len(pbos) != 1 else ''} ({', '.join(sorted(pbos)[:5])}"
                      f"{'…' if len(pbos) > 5 else ''}). Loading both can cause errors on startup or odd "
                      "behaviour, and servers may reject the duplicate.",
            "fix": "Usually one of them bundles the other (for example a pack that includes CBA). Load only one "
                   "of them in the Arma 3 Launcher.",
            "mods": list(names),
        })
    if unsigned:
        lines = "\n".join(f"  - {m.display_name}" for m in unsigned[:20])
        out.append({
            "severity": "info",
            "title": "Mods without a signing key",
            "detail": "These mods have no .bikey in a keys folder. Servers that verify signatures will kick you "
                      f"when they're loaded:\n{lines}",
            "fix": "Fine for single player and unprotected servers. For a server, ask its admins which version "
                   "they run, or check the mod's Workshop page for a signed release.",
            "mods": [m.name for m in unsigned],
        })
    return out
