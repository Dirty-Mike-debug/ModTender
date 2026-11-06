"""Enable/disable mods by moving them in and out of the game's mod folder (always reversible)."""
from __future__ import annotations

import shutil
from pathlib import Path

from . import paths
from .games import Game
from .scanner import Mod


class ModActionError(Exception):
    pass


def _move(src: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if dest.exists():
        raise ModActionError(f"'{src.name}' already exists in {dest_dir}. Remove or rename one of them first.")
    shutil.move(str(src), str(dest))
    return dest


def disable_mod(game: Game, mod: Mod) -> Path:
    if mod.protected:
        raise ModActionError(f"'{mod.name}' is a base game file and can't be disabled.")
    if not mod.enabled:
        return mod.path
    return _move(mod.path, paths.disabled_dir(game.id))


def enable_mod(game: Game, mod: Mod) -> Path:
    if mod.enabled:
        return mod.path
    return _move(mod.path, game.mods_dir)
