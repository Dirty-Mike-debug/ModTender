"""Start a game from ModTender, and watch for a crash while it runs.

Launching goes through Steam (steam://rungameid/<appid>) so overlays, cloud saves and DRM work as
usual. Minecraft is started from CurseForge or the Minecraft Launcher instead, so ModTender only
watches it. Watching doesn't need to know the game's process: ModTender looks at the game's crash
reports and logs (see crashlogs.py) and reacts when one written after launch says the game crashed."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .log import log

WATCH_HOURS = 8


def launch_url(game) -> str:
    from .gamepatch import app_id
    if game.definition.id == "minecraft" or game.definition.id == "custom":
        return ""
    appid = app_id(game)
    return f"steam://rungameid/{appid}" if appid else ""


def how_to_start(game) -> str:
    """What to tell the player when ModTender can't start the game itself."""
    if game.definition.id == "minecraft":
        if game.source == "curseforge":
            return "Start this pack from the CurseForge app as usual."
        return "Start Minecraft from the Minecraft Launcher as usual."
    return "Start the game the way you normally do."


@dataclass
class Watch:
    game: object
    mods: list
    started: float = field(default_factory=time.time)
    seen: dict = field(default_factory=dict)  # log path -> modified time already looked at
    reported: set = field(default_factory=set)

    @property
    def expired(self) -> bool:
        return time.time() - self.started > WATCH_HOURS * 3600

    def check(self):
        """A CrashReport if a crash happened since the game was started (each one reported once)."""
        from .crashlogs import analyze_log, find_logs
        for path in find_logs(self.game):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime < self.started - 5 or self.seen.get(str(path)) == mtime or str(path) in self.reported:
                continue
            self.seen[str(path)] = mtime
            report = analyze_log(path, self.mods)
            if report and report.crashed:
                self.reported.add(str(path))
                log.info("[%s] Crash spotted while watching: %s (%d suspect(s))", self.game.id, path.name,
                         len(report.suspects))
                return report
        return None
