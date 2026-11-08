"""Planet Zoo checks.

Mods are folders in Planet Zoo/win64/ovldata, next to Frontier's own content folders. Each mod
folder holds the game's .ovl files directly. The most common install mistake is a folder inside a
folder (ovldata/LeopardSeal/LeopardSeal/...), which the game silently ignores."""
from __future__ import annotations

from pathlib import Path


def _children(folder: Path) -> tuple[list[Path], list[Path]]:
    try:
        items = list(folder.iterdir())
    except OSError:
        return [], []
    return [p for p in items if p.is_file()], [p for p in items if p.is_dir()]


def _has_ovl(folder: Path) -> bool:
    files, _ = _children(folder)
    return any(p.suffix.lower() == ".ovl" for p in files)


def analyze_planetzoo(mods: list) -> list[dict]:
    out = []
    for m in mods:
        if m.workshop or m.protected or not m.enabled or not m.path.is_dir() or _has_ovl(m.path):
            continue
        files, dirs = _children(m.path)
        inner = [d for d in dirs if _has_ovl(d)]
        if len(inner) == 1 and not any(p.suffix.lower() == ".ovl" for p in files):
            out.append({
                "severity": "critical",
                "title": "Mod is a folder inside a folder",
                "detail": f"{m.display_name} has its files one folder too deep (in {m.name}\\{inner[0].name}). "
                          "Planet Zoo only looks one level into ovldata, so this mod won't load.",
                "fix": f"Move the folder {inner[0].name} out of {m.name} and straight into ovldata, then delete "
                       f"the empty {m.name} folder.",
                "mods": [m.name],
            })
    return out
