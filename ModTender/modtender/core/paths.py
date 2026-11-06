"""Well-known Windows folders, resolved safely (works with OneDrive-redirected Documents)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

HOME = Path.home()
IS_WINDOWS = sys.platform == "win32"


def _env_path(var: str, fallback: Path) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else fallback


def _shell_folder(csidl: int, fallback: Path) -> Path:
    """A special folder as Windows reports it (OneDrive often moves Documents and Desktop)."""
    if IS_WINDOWS:
        try:
            import ctypes
            from ctypes import wintypes

            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0 and buf.value:
                return Path(buf.value)
        except Exception:
            pass
    return fallback


def desktop_dir() -> Path:
    return _shell_folder(0x10, HOME / "Desktop")  # CSIDL_DESKTOPDIRECTORY


def _documents_dir() -> Path:
    """The real Documents folder. On Windows this asks the shell, because
    OneDrive often moves Documents somewhere other than ~/Documents."""
    if IS_WINDOWS:
        try:
            import ctypes
            from ctypes import wintypes

            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            CSIDL_PERSONAL = 5
            if ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_PERSONAL, None, 0, buf) == 0 and buf.value:
                return Path(buf.value)
        except Exception:
            pass
    return HOME / "Documents"


APPDATA = _env_path("APPDATA", HOME / "AppData" / "Roaming")
LOCALAPPDATA = _env_path("LOCALAPPDATA", HOME / "AppData" / "Local")
LOCALLOW = HOME / "AppData" / "LocalLow"
DOCUMENTS = _documents_dir()

# Everything ModTender owns lives here. MODTENDER_DATA overrides it (used by tests).
DATA_DIR = _env_path("MODTENDER_DATA", LOCALAPPDATA / "ModTender")


def data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def disabled_dir(game_id: str) -> Path:
    """Where disabled mods are parked (outside the game's mod folder so the game ignores them)."""
    path = data_dir() / "disabled" / game_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_backup_dir() -> Path:
    return data_dir() / "backups"


def quarantine_dir(game_id: str) -> Path:
    """Where Fix moves damaged mods, replaced originals and stray files. Nothing is ever deleted."""
    path = data_dir() / "quarantine" / game_id
    path.mkdir(parents=True, exist_ok=True)
    return path
