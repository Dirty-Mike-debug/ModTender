"""ModTender's log file: %LOCALAPPDATA%\\ModTender\\logs\\modtender.log (kept small, rotated)."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from . import paths

log = logging.getLogger("modtender")


def log_dir():
    d = paths.data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup() -> None:
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    try:
        handler = RotatingFileHandler(log_dir() / "modtender.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(handler)

    previous = sys.excepthook

    def crash(exc_type, exc, tb):
        log.critical("Unhandled error", exc_info=(exc_type, exc, tb))
        previous(exc_type, exc, tb)

    sys.excepthook = crash
