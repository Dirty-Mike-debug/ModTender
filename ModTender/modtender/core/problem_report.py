"""Bundle what's needed to look into a problem: ModTender's log, the current scan, and system info.

Nothing is sent anywhere. The zip is saved locally and a pre-filled GitHub issue page is opened,
so the person decides what to share."""
from __future__ import annotations

import platform
import sys
import urllib.parse
import zipfile
from datetime import datetime
from pathlib import Path

from .. import UPDATE_REPO, __version__
from .log import log, log_dir


def system_info(games=(), game=None) -> str:
    lines = [
        f"ModTender {__version__} ({'installed app' if getattr(sys, 'frozen', False) else 'script version'})",
        f"Windows: {platform.platform()}",
        f"Python {sys.version.split()[0]}",
        f"Selected game: {game.name} ({game.definition.id}, {game.source})" if game else "Selected game: none",
        f"Games found: {len(games)}",
    ]
    lines += [f"  - {g.name} ({g.definition.id})" for g in games]
    return "\n".join(lines)


def build_bundle(target: Path, description: str, games=(), game=None, scan=None, issues=()) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("what-happened.txt", description.strip() or "(no description)")
        zf.writestr("system.txt", system_info(games, game))
        if scan is not None:
            from .report import build_report
            try:
                zf.writestr("scan-report.txt", build_report(scan, list(issues)))
            except Exception as exc:  # a broken report shouldn't stop the bundle
                zf.writestr("scan-report.txt", f"Couldn't build the scan report: {exc}")
        for f in sorted(log_dir().glob("modtender.log*"))[:3]:
            try:
                zf.write(f, f"logs/{f.name}")
            except OSError:
                pass
    log.info("Problem report saved to %s", target)
    return target


def default_path() -> Path:
    from .paths import desktop_dir
    desktop = desktop_dir()
    folder = desktop if desktop.is_dir() else Path.home()
    return folder / f"ModTender problem report {datetime.now():%Y-%m-%d %H%M}.zip"


def issue_url(description: str, game=None) -> str:
    title = (description.strip().splitlines() or ["Problem report"])[0][:80]
    body = (f"**What happened**\n{description.strip() or '(describe it here)'}\n\n"
            f"**ModTender** {__version__}  \n**Game** {game.name if game else '-'}  \n"
            f"**Windows** {platform.release()}\n\n"
            "_Please attach the ModTender problem report .zip from your Desktop (drag it into this box)._")
    q = urllib.parse.urlencode({"title": title, "body": body[:6000]})
    return f"https://github.com/{UPDATE_REPO}/issues/new?{q}"
