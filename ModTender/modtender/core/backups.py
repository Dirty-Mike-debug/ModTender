"""Snapshot a game's mods to a zip, and restore it without ever destroying current files."""
from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import paths
from .games import Game

STAMP = "%Y%m%d-%H%M%S"


@dataclass
class Backup:
    path: Path
    created: datetime
    mod_count: int
    total_size: int  # uncompressed bytes of the mods
    note: str = ""

    @property
    def file_size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0


def _game_backup_dir(root: Path, game: Game) -> Path:
    d = Path(root) / game.id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _collect(folder: Path, prefix: str) -> list[tuple[Path, str]]:
    out = []
    if folder.is_dir():
        for f in sorted(folder.rglob("*")):
            if f.is_file():
                out.append((f, f"{prefix}/{f.relative_to(folder).as_posix()}"))
    return out


def create_backup(game: Game, root: Path, note: str = "", progress=None) -> Backup:
    """Zip the enabled mods folder and ModTender's disabled-mods folder for this game.
    Files are stored without recompression: mods are already compressed, so this is fast."""
    files = _collect(game.mods_dir, "enabled") + _collect(paths.disabled_dir(game.id), "disabled")
    created = datetime.now()
    target = _game_backup_dir(root, game) / f"{game.id}_{created.strftime(STAMP)}.zip"
    partial = target.with_suffix(".zip.partial")
    total = sum(f.stat().st_size for f, _ in files) or 1
    done = 0
    try:
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
            for f, arc in files:
                if progress:
                    progress(done * 100 / total, f"Backing up {f.name}")
                zf.write(f, arc)
                done += f.stat().st_size
            top_level = {a.split("/")[1] for _, a in files if a.count("/") >= 1}
            manifest = {
                "app": "ModTender", "game_id": game.id, "game_name": game.name,
                "mods_dir": str(game.mods_dir), "created": created.isoformat(timespec="seconds"),
                "mod_count": len(top_level), "total_size": done, "note": note,
            }
            zf.writestr("modtender_backup.json", json.dumps(manifest, indent=2))
        partial.replace(target)  # only a finished backup gets the .zip name
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    if progress:
        progress(100, "Backup complete")
    return Backup(target, created, manifest["mod_count"], done, note)


def list_backups(game: Game, root: Path) -> list[Backup]:
    out = []
    for f in sorted(_game_backup_dir(root, game).glob("*.zip"), reverse=True):
        try:
            with zipfile.ZipFile(f) as zf:
                m = json.loads(zf.read("modtender_backup.json"))
            out.append(Backup(f, datetime.fromisoformat(m["created"]), m.get("mod_count", 0),
                              m.get("total_size", 0), m.get("note", "")))
        except (KeyError, ValueError, zipfile.BadZipFile, OSError):
            continue  # not one of ours, or damaged: leave it alone
    return out


def restore_backup(game: Game, backup: Backup, progress=None) -> Path:
    """Restore a backup. The current mods folder is renamed, not deleted, so a restore can be undone.
    Returns the path where the previous mods were kept."""
    stamp = datetime.now().strftime(STAMP)
    mods_dir = game.mods_dir
    staging = mods_dir.with_name(f"{mods_dir.name}.modtender-restoring")
    disabled_staging = paths.disabled_dir(game.id).with_name(f"{game.id}.restoring")
    for d in (staging, disabled_staging):
        if d.exists():
            shutil.rmtree(d)
    staging.mkdir(parents=True)
    disabled_staging.mkdir(parents=True)

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
                continue  # refuse paths that try to escape the folder
            if progress:
                progress(done * 100 / total, f"Restoring {Path(rel).name}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out, 1024 * 1024)
            done += info.file_size

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

    if progress:
        progress(100, "Restore complete")
    return kept


def prune_backups(game: Game, root: Path, keep: int) -> int:
    """Delete the oldest backups beyond `keep`. Returns how many were removed."""
    backups = list_backups(game, root)
    removed = 0
    for b in backups[keep:]:
        try:
            b.path.unlink()
            removed += 1
        except OSError:
            pass
    return removed
