"""Total War: Warhammer III checks.

Mods are .pack files. Local ones go in the game's data folder, next to Creative Assembly's own packs;
Workshop ones live in Steam's workshop folder. Every pack starts with a small header: "PFH5" for
Warhammer III (older games use PFH4 and earlier, which Warhammer III won't load), then the pack type.
Types 0-2 (boot, release, patch) are the game's own packs; mods are type 3 (mod) or 4 (movie)."""
from __future__ import annotations

import struct
from collections import defaultdict
from pathlib import Path

GAME_PACK_TYPES = {0, 1, 2}


def read_header(path: Path) -> tuple[str, int] | None:
    """(format, pack type) or None when the file isn't a Total War pack."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return None
    if len(head) < 8 or not head.startswith(b"PFH"):
        return None
    return head[:4].decode("ascii", errors="replace"), struct.unpack("<I", head[4:8])[0] & 0xF


def mark_packs(mods: list) -> None:
    """Protect the game's own packs and flag files that aren't packs at all."""
    for m in mods:
        if m.workshop or not m.path.is_file() or m.path.suffix.lower() != ".pack":
            continue
        head = read_header(m.path)
        if head is None:
            if not m.corrupt:
                m.corrupt = "This isn't a Total War pack file (the file is damaged or was renamed)."
            continue
        fmt, kind = head
        if kind in GAME_PACK_TYPES:
            m.protected = True
        m.version = m.version or fmt


def _workshop_packs(m) -> list[Path]:
    try:
        return [p for p in m.path.iterdir() if p.is_file() and p.suffix.lower() == ".pack"]
    except OSError:
        return []


def analyze_warhammer3(mods: list) -> list[dict]:
    out = []
    old = []
    for m in mods:
        packs = _workshop_packs(m) if m.workshop else ([m.path] if m.path.suffix.lower() == ".pack" else [])
        for p in packs:
            head = read_header(p)
            if head and head[0] != "PFH5" and head[1] not in GAME_PACK_TYPES:
                old.append((m, head[0]))
                break
    if old:
        lines = "\n".join(f"  - {m.display_name} ({fmt})" for m, fmt in old[:20])
        out.append({
            "severity": "warning",
            "title": "Mods made for an older Total War game",
            "detail": "These packs use an older pack format, so they were made for Warhammer II or an earlier "
                      f"game. Warhammer III won't load them:\n{lines}",
            "fix": "Look for a Warhammer III version of the mod on the Workshop or Nexus, and remove these.",
            "mods": [m.name for m, _ in old],
        })

    # The same pack both in the data folder and from the Workshop: the game loads it twice.
    owners: dict[str, list] = defaultdict(list)
    for m in mods:
        if not m.enabled:
            continue
        names = [p.name.lower() for p in _workshop_packs(m)] if m.workshop else [m.name.lower()]
        for n in names:
            if n.endswith(".pack"):
                owners[n].append(m)
    for pack, who in sorted(owners.items()):
        if len(who) > 1 and any(m.workshop for m in who) and any(not m.workshop for m in who):
            local = [m for m in who if not m.workshop]
            out.append({
                "severity": "warning",
                "title": "Mod installed twice",
                "detail": f"{pack} is in the game's data folder and also comes from the Steam Workshop. "
                          "The copy in the data folder wins, so Workshop updates to it won't show up in game.",
                "fix": "Keep the Workshop copy and turn off the one in the data folder (unless you put it there "
                       "on purpose to keep an older version).",
                "mods": [m.name for m in who],
                "action": "disable", "params": {"mods": [m.name for m in local]},
                "action_label": "Turn off the copy in the data folder", "safe": False,
            })
    return out
