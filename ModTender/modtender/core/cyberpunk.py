"""Cyberpunk 2077: find .archive mods that replace the same game files.

Each .archive has an index listing a 64-bit hash for every file inside it. When two mods contain
the same file, the game uses the one from the archive that loads first:
  1. archive/pc/mod/*.archive, in modlist.txt order if that file exists, otherwise ASCII-alphabetical
     (so 'A.archive' beats 'a.archive' beats 'b.archive'),
  2. then REDmods (mods/<name>/archives/*.archive), by folder name.
The first one loaded wins; the others' versions of that file are ignored."""
from __future__ import annotations

import struct
from collections import defaultdict
from pathlib import Path

CONFLICT_CHECKER = "https://www.nexusmods.com/cyberpunk2077/mods/11126"
RECORD = struct.Struct("<QqIIIII20s")  # NameHash64, timestamp, inline, segs start/end, deps start/end, sha1


def read_hashes(path: Path) -> set[int] | None:
    """The file-name hashes inside an .archive, or None if it isn't a readable archive."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(44)
            if len(head) < 44 or head[:4] != b"RDAR":
                return None
            _magic, _ver, index_pos, index_size, *_ = struct.unpack("<4sIQIQIQI", head)
            fh.seek(index_pos)
            idx = fh.read(28)
            if len(idx) < 28:
                return None
            _off, _size, _crc, count, _segs, _deps = struct.unpack("<IIQIII", idx)
            if count > 2_000_000:
                return None
            raw = fh.read(count * RECORD.size)
    except OSError:
        return None
    if len(raw) < count * RECORD.size:
        return None
    return {RECORD.unpack_from(raw, i * RECORD.size)[0] for i in range(count)}


def load_order(mod_dir: Path) -> list[Path]:
    """Archives in the order the game loads them."""
    archives = sorted((p for p in mod_dir.glob("*.archive") if p.is_file()), key=lambda p: p.name.encode())
    modlist = mod_dir / "modlist.txt"
    if modlist.is_file():
        by_name = {p.name.lower(): p for p in archives}
        listed = []
        for line in modlist.read_text(encoding="utf-8", errors="ignore").splitlines():
            p = by_name.pop(line.strip().lower(), None)
            if p:
                listed.append(p)
        archives = listed + [p for p in archives if p.name.lower() in by_name]
    game_root = mod_dir.parent.parent.parent  # .../Cyberpunk 2077
    redmods = game_root / "mods"
    if redmods.is_dir():
        for folder in sorted((d for d in redmods.iterdir() if d.is_dir()), key=lambda d: d.name.encode()):
            archives += sorted((folder / "archives").glob("*.archive"), key=lambda p: p.name.encode())
    return archives


def analyze_cyberpunk(mod_dir: Path) -> list[dict]:
    if not mod_dir.is_dir():
        return []
    order = load_order(mod_dir)
    owner: dict[int, int] = {}  # file hash -> index of the archive that wins it
    lost: dict[tuple[int, int], int] = defaultdict(int)  # (winner, loser) -> files
    unreadable = []
    for i, archive in enumerate(order):
        hashes = read_hashes(archive)
        if hashes is None:
            unreadable.append(archive.name)
            continue
        for h in hashes:
            if h in owner:
                lost[(owner[h], i)] += 1
            else:
                owner[h] = i

    label = lambda p: p.name if p.parent == mod_dir else f"{p.parent.parent.name} (REDmod)"
    out = []
    by_loser: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for (w, l), n in lost.items():
        by_loser[l].append((w, n))
    for l, wins in sorted(by_loser.items()):
        loser = order[l]
        total = sum(n for _, n in wins)
        lines = "\n".join(f"  - {label(order[w])} ({n} file{'s' if n != 1 else ''})" for w, n in sorted(wins))
        out.append({
            "severity": "warning", "title": "Archive conflict: some of this mod's files are ignored",
            "detail": f"{label(loser)} contains {total} file{'s' if total != 1 else ''} that "
                      f"{'are' if total != 1 else 'is'} also in mods that load before it, so the game uses "
                      f"those versions instead:\n{lines}\n\n"
                      "If both mods change the same thing (for example the same outfit), that's expected: "
                      "pick the one you want. If one is a patch for the other, the patch should load first.",
            "fix": "To let this mod win, make it load first: add a modlist.txt in archive\\pc\\mod listing it "
                   "above the others, or rename it to start with an earlier character (like '#' or '0'). "
                   "The Archive Conflict Checker tool on Nexus shows which files clash.",
            "mods": [loser.name] + [order[w].name for w, _ in sorted(wins)],
            "url": CONFLICT_CHECKER,
        })
    if unreadable:
        out.append({"severity": "warning", "title": "Unreadable archive",
                    "detail": "These .archive files couldn't be read and may be damaged or incomplete:\n"
                              + "\n".join(f"  - {n}" for n in unreadable[:15]),
                    "fix": "Download the mod again.", "mods": unreadable})
    return out
