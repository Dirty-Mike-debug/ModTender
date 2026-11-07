"""Space saver: store identical mod files once, shared by every game or pack that uses them.

The same .jar often sits in several Minecraft packs (ATM10, ATM11, a test copy...). A hard link
makes two folder entries point at the same data on disk, so each pack keeps a normal-looking file
while the space is only used once. Launchers that update a mod delete the old file and write a new
one, which simply ends the sharing for that file; nothing else changes.

Safety rules:
  - only files that are byte-for-byte identical (same SHA-1 and size), on the same drive,
  - never inside OneDrive (it doesn't handle hard links) or Steam Workshop folders,
  - only mod files ModTender scanned (not configs or saves), 256 KB and up,
  - every link is recorded in space_saver.json, and Undo turns them back into separate copies."""
from __future__ import annotations

import json
import os
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import paths
from .log import log

MIN_SIZE = 256 * 1024


@dataclass
class SharedMod:
    title: str
    size: int
    files: list[Path]  # every copy, first one is kept as the original
    games: list[str]

    @property
    def saving(self) -> int:
        return self.size * (len(self.files) - 1)


@dataclass
class Plan:
    groups: list[SharedMod] = field(default_factory=list)
    already_shared: int = 0  # bytes already saved by earlier runs
    skipped_onedrive: int = 0

    @property
    def saving(self) -> int:
        return sum(g.saving for g in self.groups)


def _record_file() -> Path:
    return paths.data_dir() / "space_saver.json"


def _load_record() -> list[dict]:
    try:
        return json.loads(_record_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _save_record(entries: list[dict]) -> None:
    _record_file().write_text(json.dumps(entries, indent=1), encoding="utf-8")


def _excluded(path: Path) -> str:
    parts = [p.lower() for p in path.parts]
    if any(p.startswith("onedrive") for p in parts):
        return "onedrive"
    if "workshop" in parts and "content" in parts:
        return "workshop"
    return ""


def find_shared(scans: list) -> Plan:
    """Identical mod files across all scanned games and packs."""
    plan = Plan()
    by_content: dict[tuple, list] = defaultdict(list)
    for scan in scans:
        for m in scan.mods:
            if not m.sha1 or m.size < MIN_SIZE or not m.path.is_file() or m.workshop:
                continue
            why = _excluded(m.path)
            if why == "onedrive":
                plan.skipped_onedrive += 1
                continue
            if why:
                continue
            by_content[(m.sha1.lower(), m.size)].append((m, scan.game.name))
    for (sha, size), copies in by_content.items():
        if len(copies) < 2:
            continue
        by_drive: dict[int, list] = defaultdict(list)  # drive -> [(file id, mod, game)]
        for m, game_name in copies:
            try:
                st = m.path.stat()
            except OSError:
                continue
            by_drive[st.st_dev].append((st.st_ino, m, game_name))
        for entries in by_drive.values():
            distinct = {}
            for ino, m, game_name in entries:
                distinct.setdefault(ino, (m, game_name))
            plan.already_shared += (len(entries) - len(distinct)) * size
            if len(distinct) > 1:
                kept = list(distinct.values())
                plan.groups.append(SharedMod(kept[0][0].display_name, size, [m.path for m, _ in kept],
                                             sorted({g for _, g in kept})))
    plan.groups.sort(key=lambda g: -g.saving)
    return plan


def apply(plan: Plan, progress=None) -> tuple[int, list[str]]:
    """Replace duplicate copies with hard links to the first copy. Returns (bytes saved, problems)."""
    record = _load_record()
    saved, problems = 0, []
    for n, group in enumerate(plan.groups):
        if progress:
            progress(100 * n // max(1, len(plan.groups)), f"Sharing {group.title}…")
        original = group.files[0]
        for target in group.files[1:]:
            tmp = target.with_name(target.name + ".modtender-link")
            try:
                if target.stat().st_size != original.stat().st_size:
                    raise OSError("the file changed since the check")
                tmp.unlink(missing_ok=True)
                os.link(original, tmp)
                os.replace(tmp, target)
                record.append({"file": str(target), "original": str(original),
                               "date": datetime.now().isoformat(timespec="seconds")})
                saved += group.size
            except OSError as exc:
                tmp.unlink(missing_ok=True)
                problems.append(f"{target.name}: {exc}")
    _save_record(record)
    log.info("Space saver: shared %d bytes, %d problem(s)", saved, len(problems))
    return saved, problems


def undo(progress=None) -> tuple[int, list[str]]:
    """Turn every shared file back into its own separate copy."""
    record = _load_record()
    done, problems, keep = 0, [], []
    for n, entry in enumerate(record):
        if progress:
            progress(100 * n // max(1, len(record)), "Making separate copies…")
        target = Path(entry["file"])
        if not target.exists():
            continue  # removed or replaced since: nothing to undo
        tmp = target.with_name(target.name + ".modtender-copy")
        try:
            shutil.copyfile(target, tmp)  # a real copy: new data on disk
            shutil.copystat(target, tmp)
            os.replace(tmp, target)
            done += 1
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            problems.append(f"{target.name}: {exc}")
            keep.append(entry)
    _save_record(keep)
    log.info("Space saver undone for %d file(s), %d problem(s)", done, len(problems))
    return done, problems


def shared_count() -> int:
    return len(_load_record())
