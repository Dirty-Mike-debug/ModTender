"""Apply the automatic fixes described by issues.analyze().

Every fix is reversible: mods are disabled (moved to ModTender's disabled folder) or quarantined
(moved to ModTender's quarantine folder), never deleted. "Fix all" can also take a backup first."""
from __future__ import annotations

import shutil
import webbrowser
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import backups, paths
from .games import Game
from .issues import ACTION_ORDER, Issue
from .log import log


@dataclass
class FixResult:
    done: list[str] = field(default_factory=list)  # what was changed, in plain words
    skipped: list[str] = field(default_factory=list)  # fixes that couldn't run, with the reason
    backup: Path | None = None


class FixError(Exception):
    pass


def _unique(dest: Path) -> Path:
    if not dest.exists():
        return dest
    n = 2
    while True:
        candidate = dest.with_name(f"{dest.stem} ({n}){dest.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def _in_mods(game: Game, name: str) -> Path:
    path = game.mods_dir / name
    if not path.exists():
        raise FixError(f"'{name}' is no longer in the mods folder")
    return path


def _quarantine(game: Game, path: Path) -> Path:
    folder = paths.quarantine_dir(game.id) / datetime.now().strftime("%Y-%m-%d")
    folder.mkdir(parents=True, exist_ok=True)
    dest = _unique(folder / path.name)
    shutil.move(str(path), str(dest))
    return dest


def _disable(game: Game, name: str) -> str:
    src = _in_mods(game, name)
    dest = paths.disabled_dir(game.id) / name
    if dest.exists():
        # An older disabled copy with the same name: park that one in quarantine instead of failing.
        _quarantine(game, dest)
    shutil.move(str(src), str(dest))
    return f"Disabled {name}"


def _enable(game: Game, name: str) -> str:
    src = paths.disabled_dir(game.id) / name
    if not src.exists():
        raise FixError(f"'{name}' isn't in the disabled folder any more")
    dest = game.mods_dir / name
    if dest.exists():
        raise FixError(f"a file called '{name}' is already in the mods folder")
    shutil.move(str(src), str(dest))
    return f"Enabled {name}"


def _rename(game: Game, name: str, new: str) -> str:
    src = _in_mods(game, name)
    dest = game.mods_dir / new
    if dest.exists():
        raise FixError(f"'{new}' already exists")
    src.rename(dest)
    return f"Renamed {name} → {new}"


def _unpack(game: Game, name: str) -> str:
    src = _in_mods(game, name)
    extracted = []
    with zipfile.ZipFile(src) as zf:
        for info in zf.infolist():
            inner = Path(info.filename).name
            if info.is_dir() or not inner.lower().endswith(".zip"):
                continue
            dest = game.mods_dir / inner
            if dest.exists():
                continue  # already installed; keep the existing one
            with zf.open(info) as fin, open(dest, "wb") as fout:
                shutil.copyfileobj(fin, fout, 1024 * 1024)
            extracted.append(inner)
    _quarantine(game, src)
    return f"Unpacked {name}: added {len(extracted)} mod(s)" + (f" ({', '.join(extracted[:4])}" + (" …)" if len(extracted) > 4 else ")") if extracted else "")


def _rezip(game: Game, name: str, inner: str) -> str:
    src = _in_mods(game, name)
    prefix = inner.rstrip("/") + "/"
    tmp = game.mods_dir / f"{name}.modtender-tmp"
    try:
        with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                if not info.filename.startswith(prefix) or info.filename == prefix:
                    continue
                rel = info.filename[len(prefix):]
                if info.is_dir():
                    continue
                zout.writestr(zipfile.ZipInfo(rel, info.date_time), zin.read(info), zipfile.ZIP_DEFLATED)
        kept = _quarantine(game, src)
        tmp.rename(game.mods_dir / name)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return f"Rebuilt {name} with its files at the top (original kept in {kept.parent.name})"


def apply_fix(game: Game, issue: Issue) -> list[str]:
    """Apply one issue's fix. Returns plain-language lines describing what changed."""
    p, a = issue.params, issue.action
    if a == "mkdir":
        game.mods_dir.mkdir(parents=True, exist_ok=True)
        return [f"Created {game.mods_dir}"]
    if a == "deadlock_gameinfo":
        from .deadlock import enable_addons
        return [enable_addons(game.mods_dir)]
    if a == "deadlock_rename":
        from .deadlock import apply_renames
        return apply_renames(game, p["pairs"])
    if a == "ack_game_update":
        from .gamepatch import acknowledge
        acknowledge(p["key"], p["build"])
        return ["Dismissed the game update warning"]
    if a == "quarantine_mod":
        _quarantine(game, _in_mods(game, p["mod"]))
        return [f"Moved {p['mod']} to quarantine"]
    if a in ("dedupe", "keep_newest"):
        # never remove the others if the one we keep has gone
        if not (Path(p["keep_path"]).exists() if p.get("keep_path") else (game.mods_dir / p["keep"]).exists()):
            raise FixError(f"'{p['keep']}' is no longer there, so the other copies were left alone")
        return [_disable(game, n) for n in p["drop"] if (game.mods_dir / n).exists()]
    if a == "disable":
        return [_disable(game, n) for n in p["mods"]]
    if a == "enable":
        return [_enable(game, n) for n in p["mods"]]
    if a == "rename":
        return [_rename(game, p["mod"], p["new"])]
    if a == "unpack":
        return [_unpack(game, p["mod"])]
    if a == "rezip":
        return [_rezip(game, p["mod"], p["inner"])]
    if a == "quarantine_files":
        moved = []
        for n in p["files"]:
            f = game.mods_dir / n
            if f.exists():
                _quarantine(game, f)
                moved.append(n)
        return [f"Moved {len(moved)} file(s) to quarantine"] if moved else []
    if a in ("search", "open_url"):
        webbrowser.open(p["url"])
        return ["Opened the page in your browser"]
    raise FixError("there's no automatic fix for this issue")


def fix_issues(game: Game, issues: list[Issue], backup_root: Path | None = None, progress=None) -> FixResult:
    """Apply several fixes in a safe order. Optionally back up the mods folder first."""
    result = FixResult()
    todo = sorted((i for i in issues if i.fixable), key=lambda i: ACTION_ORDER.get(i.action, 99))
    if backup_root is not None and game.mods_dir.is_dir() and not game.workshop_only:
        if progress:
            progress(0, "Backing up before fixing…")
        log.info("[%s] Fix all: backing up first", game.id)
        result.backup = backups.create_backup(game, backup_root, note="Before Fix all",
                                              progress=lambda p, m: progress and progress(p * 0.8, m)).path
    for n, issue in enumerate(todo):
        if progress:
            progress(80 + 20 * n / max(len(todo), 1), f"Fixing: {issue.title}")
        try:
            lines = apply_fix(game, issue)
            result.done += lines
            for line in lines:
                log.info("[%s] Fix: %s", game.id, line)
        except (FixError, OSError, zipfile.BadZipFile) as exc:
            result.skipped.append(f"{issue.title} ({', '.join(issue.mods[:2])}): {exc}")
            log.warning("[%s] Fix skipped: %s (%s): %s", game.id, issue.title, ", ".join(issue.mods[:3]), exc)
    if progress:
        progress(100, "Fixes applied")
    return result
