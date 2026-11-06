"""Backups ("restore points") of a game's mods, and restoring them without ever destroying files.

Since 0.11 backups are snapshots: every mod file is stored once in a shared pool, named by its
SHA-1, and each backup is a small list of which files it contains. Backing up again only copies
mods that changed, so daily backups of a big mod folder cost almost no extra space.
Older .zip backups (0.2-0.10) are still listed and can still be restored.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import paths
from .games import Game
from .log import log

STAMP = "%Y%m%d-%H%M%S"
SNAP_SUFFIX = ".snap.json"


class BackupError(Exception):
    pass


@dataclass
class Backup:
    path: Path
    created: datetime
    mod_count: int
    total_size: int  # bytes of the mods in this backup
    note: str = ""  # Manual / Scheduled / Mods changed / Before Fix all …
    kind: str = "snapshot"  # snapshot | zip (older versions)
    pinned: bool = False  # "known good": never removed automatically
    new_bytes: int = 0  # space this backup added to the pool when it was made

    @property
    def file_size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0


@dataclass
class Changes:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    enabled: list[str] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.added) + len(self.removed) + len(self.updated) + len(self.enabled) + len(self.disabled)

    def summary(self) -> str:
        parts = []
        for label, items in (("added", self.added), ("removed", self.removed), ("updated", self.updated),
                             ("turned on", self.enabled), ("turned off", self.disabled)):
            if items:
                parts.append(f"{len(items)} {label}")
        return ", ".join(parts) or "no changes"


# ---------------------------------------------------------------- folders, pins

def _game_dir(root: Path, game: Game) -> Path:
    d = Path(root) / game.id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pool(root: Path, game: Game) -> Path:
    return _game_dir(root, game) / "pool"


def _pins_file(root: Path, game: Game) -> Path:
    return _game_dir(root, game) / "pins.json"


def _pins(root: Path, game: Game) -> set[str]:
    try:
        return set(json.loads(_pins_file(root, game).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def set_pinned(game: Game, root: Path, backup: Backup, pinned: bool) -> None:
    pins = _pins(root, game)
    (pins.add if pinned else pins.discard)(backup.path.name)
    _pins_file(root, game).write_text(json.dumps(sorted(pins)), encoding="utf-8")
    backup.pinned = pinned
    log.info("[%s] %s %s as a working setup", game.id, "Marked" if pinned else "Unmarked", backup.path.name)


def _collect(folder: Path, area: str) -> list[tuple[Path, str, str]]:
    out = []
    if folder.is_dir():
        for f in sorted(folder.rglob("*")):
            if f.is_file():
                out.append((f, area, f.relative_to(folder).as_posix()))
    return out


# ---------------------------------------------------------------- create

def create_backup(game: Game, root: Path, note: str = "Manual", progress=None) -> Backup:
    """Snapshot the enabled mods folder and ModTender's disabled-mods folder for this game."""
    from .scanner import HashCache

    if game.workshop_only:
        raise BackupError("All of this game's mods come from the Steam Workshop, so there's nothing to back up.")
    files = _collect(game.mods_dir, "enabled") + _collect(paths.disabled_dir(game.id), "disabled")
    pool = _pool(root, game)
    cache = HashCache()
    created = datetime.now()
    stats = [(f, f.stat()) for f, _, _ in files]
    total = sum(st.st_size for _, st in stats) or 1

    entries, done, new_bytes = [], 0, 0
    for (f, area, rel), (_, st) in zip(files, stats):
        if progress:
            progress(done * 100 / total, f"Backing up {f.name}")
        sha = cache.sha1(f, st.st_size, st.st_mtime)
        target = pool / sha[:2] / sha
        if not target.exists():
            free = shutil.disk_usage(pool.parent).free
            if free < st.st_size + 200 * 1024 * 1024:
                cache.save()
                raise BackupError(f"Not enough free space in {pool.parent.drive or pool.parent} for this backup. "
                                  "Free some space, or choose another backup folder in Settings.")
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".partial")
            shutil.copyfile(f, tmp)
            tmp.replace(target)
            new_bytes += st.st_size
        entries.append({"area": area, "rel": rel, "sha": sha, "size": st.st_size, "mtime": st.st_mtime})
        done += st.st_size
    cache.save()

    tops = {(e["area"], e["rel"].split("/", 1)[0]) for e in entries}
    manifest = {
        "app": "ModTender", "format": 2, "game_id": game.id, "game_name": game.name,
        "mods_dir": str(game.mods_dir), "created": created.isoformat(timespec="seconds"),
        "note": note, "mod_count": len(tops), "total_size": done, "new_bytes": new_bytes, "files": entries,
    }
    target = _game_dir(root, game) / f"{game.id}_{created.strftime(STAMP)}{SNAP_SUFFIX}"
    tmp = target.with_suffix(".partial")
    tmp.write_text(json.dumps(manifest), encoding="utf-8")
    tmp.replace(target)
    log.info("[%s] Backup created (%s): %s, %d items, %.1f MB new", game.id, note, target.name, len(tops),
             new_bytes / 1048576)
    if progress:
        progress(100, "Backup complete")
    return Backup(target, created, len(tops), done, note, "snapshot", False, new_bytes)


# ---------------------------------------------------------------- list

def _read_snapshot(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def list_backups(game: Game, root: Path) -> list[Backup]:
    folder = _game_dir(root, game)
    pins = _pins(root, game)
    out = []
    for f in folder.glob(f"*{SNAP_SUFFIX}"):
        try:
            m = _read_snapshot(f)
            out.append(Backup(f, datetime.fromisoformat(m["created"]), m.get("mod_count", 0), m.get("total_size", 0),
                              m.get("note", ""), "snapshot", f.name in pins, m.get("new_bytes", 0)))
        except (KeyError, ValueError, OSError):
            continue
    for f in folder.glob("*.zip"):
        try:
            with zipfile.ZipFile(f) as zf:
                m = json.loads(zf.read("modtender_backup.json"))
            out.append(Backup(f, datetime.fromisoformat(m["created"]), m.get("mod_count", 0), m.get("total_size", 0),
                              m.get("note", "") or "Manual", "zip", f.name in pins, f.stat().st_size))
        except (KeyError, ValueError, zipfile.BadZipFile, OSError):
            continue  # not one of ours, or damaged: leave it alone
    return sorted(out, key=lambda b: b.created, reverse=True)


def last_working(backups: list[Backup]) -> Backup | None:
    return next((b for b in backups if b.pinned), None)


# ---------------------------------------------------------------- what changed

def _backup_mods(backup: Backup) -> dict[str, dict]:
    """name -> {"enabled", "size", "sha"} for each top-level mod in the backup."""
    mods: dict[str, dict] = {}
    if backup.kind == "snapshot":
        groups: dict[tuple, list] = {}
        for e in _read_snapshot(backup.path).get("files", []):
            top, _, rest = e["rel"].partition("/")
            groups.setdefault((e["area"], top, bool(rest)), []).append(e)
        for (area, top, is_folder), items in groups.items():
            sha = items[0]["sha"] if not is_folder else ""
            mods[top] = {"enabled": area == "enabled", "size": sum(i["size"] for i in items), "sha": sha}
    else:
        with zipfile.ZipFile(backup.path) as zf:
            for info in zf.infolist():
                area, _, rel = info.filename.partition("/")
                if area not in ("enabled", "disabled") or not rel or info.is_dir():
                    continue
                top = rel.split("/", 1)[0]
                entry = mods.setdefault(top, {"enabled": area == "enabled", "size": 0, "sha": ""})
                entry["size"] += info.file_size
    return mods


def changes_since(backup: Backup, scan) -> Changes:
    """Compare a backup with the mods as they are now (local mods only; Workshop items are Steam's)."""
    then = _backup_mods(backup)
    now = {m.name: m for m in scan.mods if not m.workshop}
    ch = Changes()
    for name, m in sorted(now.items(), key=lambda kv: kv[0].lower()):
        old = then.get(name)
        if old is None:
            ch.added.append(name)
            continue
        if old["sha"] and m.sha1:
            different = old["sha"] != m.sha1
        else:
            different = old["size"] != m.size
        if different:
            ch.updated.append(name)
        if old["enabled"] and not m.enabled:
            ch.disabled.append(name)
        elif not old["enabled"] and m.enabled:
            ch.enabled.append(name)
    ch.removed = sorted((n for n in then if n not in now), key=str.lower)
    return ch


# ---------------------------------------------------------------- restore

def _stage_snapshot(game: Game, root: Path, backup: Backup, staging: Path, disabled_staging: Path, progress) -> None:
    entries = _read_snapshot(backup.path).get("files", [])
    pool = _pool(root, game)
    missing = [e["rel"] for e in entries if not (pool / e["sha"][:2] / e["sha"]).exists()]
    if missing:
        raise BackupError(f"This backup is incomplete: {len(missing)} file(s) are missing from the backup folder "
                          f"(for example {missing[0]}). Nothing was changed.")
    total = sum(e["size"] for e in entries) or 1
    done = 0
    for e in entries:
        dest_root = staging if e["area"] == "enabled" else disabled_staging
        dest = (dest_root / e["rel"]).resolve()
        if dest_root.resolve() not in dest.parents:
            continue  # refuse paths that try to escape the folder
        if progress:
            progress(done * 100 / total, f"Restoring {Path(e['rel']).name}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pool / e["sha"][:2] / e["sha"], dest)
        done += e["size"]


def _stage_zip(backup: Backup, staging: Path, disabled_staging: Path, progress) -> None:
    with zipfile.ZipFile(backup.path) as zf:
        members = [i for i in zf.infolist() if not i.is_dir() and i.filename != "modtender_backup.json"]
        total = sum(i.file_size for i in members) or 1
        done = 0
        for info in members:
            top, _, rel = info.filename.partition("/")
            dest_root = staging if top == "enabled" else disabled_staging if top == "disabled" else None
            if dest_root is None or not rel:
                continue
            dest = (dest_root / rel).resolve()
            if dest_root.resolve() not in dest.parents:
                continue
            if progress:
                progress(done * 100 / total, f"Restoring {Path(rel).name}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out, 1024 * 1024)
            done += info.file_size


def restore_backup(game: Game, backup: Backup, progress=None, root: Path | None = None) -> Path:
    """Restore a backup. The current mods folder is renamed, not deleted, so a restore can be undone.
    Returns the path where the previous mods were kept."""
    if root is None:
        root = backup.path.parent.parent
    stamp = datetime.now().strftime(STAMP)
    mods_dir = game.mods_dir
    staging = mods_dir.with_name(f"{mods_dir.name}.modtender-restoring")
    disabled_staging = paths.disabled_dir(game.id).with_name(f"{game.id}.restoring")
    for d in (staging, disabled_staging):
        if d.exists():
            shutil.rmtree(d)
    staging.mkdir(parents=True)
    disabled_staging.mkdir(parents=True)
    try:
        if backup.kind == "snapshot":
            _stage_snapshot(game, root, backup, staging, disabled_staging, progress)
        else:
            _stage_zip(backup, staging, disabled_staging, progress)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(disabled_staging, ignore_errors=True)
        raise

    kept = mods_dir.with_name(f"{mods_dir.name}.before-restore-{stamp}")
    if mods_dir.exists():
        mods_dir.rename(kept)
    staging.rename(mods_dir)

    disabled = paths.disabled_dir(game.id)
    kept_disabled = disabled.with_name(f"{game.id}.before-restore-{stamp}")
    disabled.rename(kept_disabled)
    disabled_staging.rename(disabled)
    if not any(kept_disabled.iterdir()):
        kept_disabled.rmdir()

    log.info("[%s] Restored %s; previous mods kept in %s", game.id, backup.path.name, kept)
    if progress:
        progress(100, "Restore complete")
    return kept


# ---------------------------------------------------------------- delete, prune, clean up

def _collect_garbage(game: Game, root: Path) -> int:
    """Delete pool files no snapshot refers to any more. Returns bytes freed."""
    pool = _pool(root, game)
    if not pool.is_dir():
        return 0
    used = set()
    for f in _game_dir(root, game).glob(f"*{SNAP_SUFFIX}"):
        try:
            used.update(e["sha"] for e in _read_snapshot(f).get("files", []))
        except (ValueError, OSError, KeyError):
            return 0  # can't read a snapshot: don't risk deleting anything it needs
    freed = 0
    for f in pool.glob("*/*"):
        if f.is_file() and f.name not in used:
            try:
                freed += f.stat().st_size
                f.unlink()
            except OSError:
                pass
    return freed


def delete_backup(game: Game, root: Path, backup: Backup) -> int:
    backup.path.unlink()
    set_pinned(game, root, backup, False)
    freed = _collect_garbage(game, root)
    log.info("[%s] Deleted backup %s (%.1f MB freed)", game.id, backup.path.name,
             (freed + (backup.new_bytes if backup.kind == "zip" else 0)) / 1048576)
    return freed


def prune_backups(game: Game, root: Path, keep: int) -> int:
    """Delete the oldest backups beyond `keep`, never ones marked as working. Returns how many were removed."""
    removable = [b for b in list_backups(game, root) if not b.pinned]
    removed = 0
    for b in removable[keep:]:
        try:
            b.path.unlink()
            removed += 1
        except OSError:
            pass
    if removed:
        _collect_garbage(game, root)
    return removed


def storage_used(game: Game, root: Path) -> int:
    folder = _game_dir(root, game)
    return sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())


def is_due(backups: list[Backup], every: str, now: datetime | None = None) -> bool:
    """Is a scheduled backup due? `every` is 'daily' or 'weekly'."""
    days = {"daily": 1, "weekly": 7}.get(every)
    if not days:
        return False
    if not backups:
        return True
    now = now or datetime.now()
    return (now - backups[0].created).total_seconds() >= days * 86400 - 600


def fingerprint(scan) -> str:
    """Short hash of the local mods' state, to notice when mods changed between scans."""
    h = hashlib.sha1()
    for m in sorted((m for m in scan.mods if not m.workshop), key=lambda m: m.name.lower()):
        h.update(f"{m.name}|{m.enabled}|{m.size}|{m.sha1 or ''}\n".encode())
    return h.hexdigest()
