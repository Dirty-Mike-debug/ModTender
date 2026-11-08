"""Read crash reports and game logs, and point at the mods most likely to blame.

Supported: Minecraft crash reports and latest.log (Forge, NeoForge, Fabric, Quilt), Stardew Valley's
SMAPI log, BepInEx's LogOutput.log (Valheim and other Unity games) and Farming Simulator's log.txt.
Any other log can be opened by hand; then the mod names found in its error lines are matched."""
from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import paths

NOT_MODS = {"minecraft", "forge", "neoforge", "fabric", "fabricloader", "fabric-api", "quilt_loader", "java",
            "mixin", "mixinextras", "smapi", "game", "bepinex", "unity", "unity log", "harmony", "fml", "mcp",
            "console", "stardew valley", "content patcher", "spongepowered", "minecraftforge", "neoforged",
            "javafml", "lowcodefml", "unknown"}
MAX_READ = 8_000_000


@dataclass
class Suspect:
    name: str  # what the log calls it
    reason: str
    mod_file: str = ""  # matching file in the mods folder, when found
    hits: int = 1


@dataclass
class CrashReport:
    path: Path
    kind: str  # crash | log
    when: datetime
    summary: str  # one-line description of what went wrong
    suspects: list[Suspect] = field(default_factory=list)
    excerpt: str = ""  # the key lines from the log

    @property
    def crashed(self) -> bool:
        return self.kind == "crash"


# ---------------------------------------------------------------- finding logs

def find_logs(game) -> list[Path]:
    """Crash reports and logs for this game, newest first."""
    gid, mods = game.definition.id, game.mods_dir
    found: list[Path] = []
    if gid == "minecraft":
        root = mods.parent
        found += (root / "crash-reports").glob("crash-*.txt")
        found += root.glob("hs_err_pid*.log")
        found.append(root / "logs" / "latest.log")
    elif gid == "stardew":
        logs = paths.APPDATA / "StardewValley" / "ErrorLogs"
        found += [logs / "SMAPI-crash.txt", logs / "SMAPI-latest.txt"]
    elif gid == "valheim":
        found += [mods.parent / "LogOutput.log", paths.LOCALLOW / "IronGate" / "Valheim" / "Player.log"]
    elif gid in ("fs25", "fs22"):
        found.append(mods.parent / "log.txt")
    elif gid == "arma3":
        found += (paths.LOCALAPPDATA / "Arma 3").glob("*.rpt")
    elif gid == "dayz":
        found += (paths.LOCALAPPDATA / "DayZ").glob("*.RPT")
        found += (paths.LOCALAPPDATA / "DayZ").glob("*.rpt")
        found += (paths.LOCALAPPDATA / "DayZ").glob("crash*.log")
    elif gid == "reforger":
        logs = paths.DOCUMENTS / "My Games" / "ArmaReforger" / "logs"
        try:
            newest = sorted((d for d in logs.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime)[-1:]
        except OSError:
            newest = []
        for d in newest:
            found += [d / "error.log", d / "console.log", d / "crash.log"]
    return sorted((p for p in found if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)


def latest_report(game, mods: list) -> CrashReport | None:
    """The most useful recent report: a crash beats a plain log. Only reports newer than the last
    change to the mods folder count, so a crash you've already dealt with stops showing up."""
    logs = find_logs(game)
    if not logs:
        return None
    changed = max([m.mtime for m in mods] + [_mtime(game.mods_dir)], default=0)
    reports = []
    for p in logs[:6]:
        mtime = _mtime(p)
        if mtime < changed or time.time() - mtime > 14 * 86400:
            continue
        r = analyze_log(p, mods)
        if r and (r.crashed or r.suspects):
            reports.append(r)
    reports.sort(key=lambda r: (r.crashed, r.when), reverse=True)
    return reports[0] if reports else None


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0


# ---------------------------------------------------------------- reading

def analyze_log(path: Path, mods: list) -> CrashReport | None:
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_READ)
    except OSError:
        return None
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
    when = datetime.fromtimestamp(_mtime(path))
    name = path.name.lower()
    if name.startswith("crash-") or "---- minecraft crash report ----" in text[:2000].lower():
        report = _minecraft_crash(path, text, when)
    elif name.startswith("hs_err_pid"):
        report = _java_crash(path, text, when)
    elif name.endswith(".rpt") or "requires addon" in text[:200000] or (name.startswith("crash") and "dayz" in text[:5000].lower()):
        report = _arma3(path, text, when)
    elif "[SMAPI]" in text[:20000] or name.startswith("smapi-"):
        report = _smapi(path, text, when)
    elif re.search(r"^\[(Info|Message|Error|Warning|Fatal|Debug)\s*:", text[:20000], re.M):
        report = _bepinex(path, text, when)
    elif re.search(r"(Farming Simulator|GIANTS Engine)", text[:5000]):
        report = _farming_sim(path, text, when)
    elif name == "latest.log" or re.search(r"\[main/(INFO|WARN|ERROR)\]", text[:20000]):
        report = _minecraft_log(path, text, when)
    else:
        report = _generic(path, text, when, mods)
    _match_mods(report, mods)
    return report


def _add(suspects: dict[str, Suspect], name: str, reason: str) -> None:
    key = name.strip().lower()
    if not key or key in NOT_MODS or len(key) < 3:
        return
    if key in suspects:
        suspects[key].hits += 1
    else:
        suspects[key] = Suspect(name.strip(), reason)


def _ranked(suspects: dict[str, Suspect], limit: int = 6) -> list[Suspect]:
    return sorted(suspects.values(), key=lambda s: -s.hits)[:limit]


def _minecraft_crash(path: Path, text: str, when: datetime) -> CrashReport:
    desc = re.search(r"^Description:\s*(.+)$", text, re.M)
    exc = re.search(r"^Description:.*\n\s*\n(.+)$", text, re.M)
    summary = (desc.group(1).strip() if desc else "Minecraft crashed")
    if exc:
        summary += f": {exc.group(1).strip()[:200]}"
    suspects: dict[str, Suspect] = {}
    # Forge/NeoForge name the suspects themselves.
    for block in re.findall(r"Suspected Mods?:\s*(.+?)(?:\n\S|\n\s*\n|\Z)", text, re.S):
        if block.strip().lower().startswith(("none", "unknown")):
            continue
        for m in re.finditer(r"^\s*([^\n(]+?)\s*\(([\w\-.]+)\)", block, re.M):
            _add(suspects, m.group(2), f"Minecraft's crash report names {m.group(1).strip()} as the suspect")
            if m.group(2).lower() in suspects:
                suspects[m.group(2).lower()].hits += 5
    for m in re.finditer(r"^\s*Mod File:\s*(.+\.jar)\s*$", text, re.M):
        _add(suspects, Path(m.group(1).replace("\\", "/")).name, "The crash happened while loading this mod file")
    _stack_suspects(text, suspects)
    return CrashReport(path, "crash", when, summary, _ranked(suspects), _excerpt(text, r"^(Description|Caused by|\S+Exception|\S+Error)"))


def _stack_suspects(text: str, suspects: dict[str, Suspect]) -> None:
    """Mixin handler names and '[in mixin config x, from mod y]' notes in the stack trace."""
    first = text.split("A detailed walkthrough of the error", 1)[0]
    for m in re.finditer(r"from mod ([\w\-.]+)\]", first):
        _add(suspects, m.group(1), "Its code appears in the crash's stack trace")
    for m in re.finditer(r"\$[a-z]{3}\d{3}\$([a-z][a-z0-9_]{2,})\$", first):  # handler$zbc000$modid$method
        _add(suspects, m.group(1), "Its code appears in the crash's stack trace")


def _java_crash(path: Path, text: str, when: datetime) -> CrashReport:
    lib = re.search(r"^# Problematic frame:\n#\s*(.+)$", text, re.M)
    summary = "Java itself crashed" + (f" in {lib.group(1).strip()}" if lib else "")
    hint = ""
    if lib and re.search(r"(nvoglv|atio6axx|ig\d+icd|amdvlk|lwjgl|opengl)", lib.group(1), re.I):
        hint = " This is usually the graphics driver: update it, or try removing shader / rendering mods."
    return CrashReport(path, "crash", when, summary + "." + hint, [], _excerpt(text, r"^# (Problematic|EXCEPTION|JRE)"))


def _minecraft_log(path: Path, text: str, when: datetime) -> CrashReport:
    suspects: dict[str, Suspect] = {}
    kind, summary = "log", "Errors in the last Minecraft session"
    # Fabric: "Mod 'Sodium' (sodium) 0.5.8 requires version 1.20.4 of 'Minecraft' ..."
    for m in re.finditer(r"- Mod '([^']+)' \(([\w\-.]+)\)[^\n]*?(requires|is incompatible with|conflicts with)([^\n]*)", text):
        _add(suspects, m.group(2), f"{m.group(1)} {m.group(3)}{m.group(4).split('!')[0]}")
        kind, summary = "crash", "Minecraft couldn't start because of a mod requirement"
    # NeoForge/Forge: "Mod ID: 'x', Requested by: 'y', Expected range: ..."
    for m in re.finditer(r"Mod ID: '([\w\-.]+)', Requested by: '([\w\-.]+)', Expected range: '([^']*)'(?:, Actual version: '([^']*)')?", text):
        need, by, rng, have = m.groups()
        from .minecraft import describe as describe_range
        reason = f"needs {need} {describe_range('maven:' + rng)}" + (
            f", but {have} is installed" if have and have != "[MISSING]" else f", but {need} isn't installed")
        _add(suspects, by, reason)
        kind, summary = "crash", "Minecraft couldn't start: a mod is missing something it needs"
    for m in re.finditer(r"(?:Failed to (?:create|load) mod|Exception (?:loading|caught during firing event) .*?) ([\w\-.]+)", text):
        _add(suspects, m.group(1), "Failed to load")
    if re.search(r"(Encountered an unexpected exception|Mod loading has failed|Incompatible mods? found)", text):
        kind = "crash"
        if summary.startswith("Errors"):
            summary = "Minecraft couldn't finish loading mods"
    _stack_suspects(text, suspects)
    return CrashReport(path, kind, when, summary, _ranked(suspects),
                       _excerpt(text, r"(/ERROR\]|/FATAL\]|Mod ID:|- Mod '|Incompatible mod)"))


def _smapi(path: Path, text: str, when: datetime) -> CrashReport:
    suspects: dict[str, Suspect] = {}
    for m in re.finditer(r"SMAPI\]\s+- (.+?) because (.+)$", text, re.M):
        name = re.sub(r"\s+\d[\w.\-]*$", "", m.group(1).strip())
        _add(suspects, name, f"SMAPI skipped it because {m.group(2).strip().rstrip('.')}")
        if name.lower() in suspects:
            suspects[name.lower()].hits += 3
    errors = Counter(m.group(1).strip() for m in re.finditer(r"^\[\d\d:\d\d:\d\d (?:ERROR|ALERT)\s+([^\]]+)\]", text, re.M))
    for source, n in errors.most_common():
        _add(suspects, source, f"logged {n} error{'s' if n != 1 else ''}")
        if source.strip().lower() in suspects:
            suspects[source.strip().lower()].hits = n
    crashed = path.name.lower() == "smapi-crash.txt" or "game has crashed" in text.lower()
    summary = "Stardew Valley crashed" if crashed else "Errors in the last Stardew Valley session"
    return CrashReport(path, "crash" if crashed else "log", when, summary, _ranked(suspects),
                       _excerpt(text, r"(ERROR|ALERT)\s"))


def _arma3(path: Path, text: str, when: datetime) -> CrashReport:
    suspects: dict[str, Suspect] = {}
    for m in re.finditer(r"Addon '([\w-]+)' requires addon '([\w-]+)'", text):
        needs, missing = m.groups()
        _add(suspects, needs.split("_")[0], f"its addon {needs} needs {missing}, which isn't loaded")
    for m in re.finditer(r"Cannot load (?:texture|model|sound|file) ([^\s.]+[\\/][^\s]+)", text, re.I):
        _add(suspects, re.split(r"[\\/]", m.group(1).lstrip("\\/"))[0], "a file it needs couldn't be loaded")
    crashed = bool(re.search(r"Exception code:|ACCESS_VIOLATION|STATUS_ACCESS", text)) or path.name.lower().startswith("crash")
    game = "DayZ" if "dayz" in (str(path).lower() + text[:3000].lower()) else "Arma 3"
    return CrashReport(path, "crash" if crashed else "log", when,
                       f"{game} crashed" if crashed else f"Errors in the last {game} session",
                       _ranked(suspects), _excerpt(text, r"(requires addon|Exception code|Cannot load|Error)"))


def _bepinex(path: Path, text: str, when: datetime) -> CrashReport:
    suspects: dict[str, Suspect] = {}
    errors = Counter(m.group(2).strip() for m in re.finditer(r"^\[(Error|Fatal)\s*:\s*([^\]]+)\]", text, re.M))
    for source, n in errors.most_common():
        _add(suspects, source, f"logged {n} error{'s' if n != 1 else ''}")
        if source.strip().lower() in suspects:
            suspects[source.strip().lower()].hits = n
    for m in re.finditer(r"Could not load \[([^\]]+?)(?: [\d.]+)?\] because (.+)", text):
        _add(suspects, m.group(1), f"BepInEx couldn't load it: {m.group(2).strip()}")
    return CrashReport(path, "log", when, "Errors in the last game session", _ranked(suspects),
                       _excerpt(text, r"^\[(Error|Fatal)|Could not load"))


def _farming_sim(path: Path, text: str, when: datetime) -> CrashReport:
    suspects: dict[str, Suspect] = {}
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if re.search(r"\bError\b", line):
            window = " ".join(lines[i:i + 4])
            for m in set(re.findall(r"mods[/\\]((?:FS2[25]_)?[\w\-]+)", window, re.I)):
                _add(suspects, m, "")
            for m in set(re.findall(r"\bmod '([\w\-]+)'", line, re.I)):
                _add(suspects, m, "")
    for s in suspects.values():
        s.reason = f"mentioned in {s.hits} error line{'s' if s.hits != 1 else ''}"
    crashed = "callstack" in text.lower() or "application crashed" in text.lower()
    return CrashReport(path, "crash" if crashed else "log", when,
                       "Farming Simulator crashed" if crashed else "Errors in the last Farming Simulator session",
                       _ranked(suspects), _excerpt(text, r"\bError\b"))


def _generic(path: Path, text: str, when: datetime, mods: list) -> CrashReport:
    suspects: dict[str, Suspect] = {}
    error_lines = [l for l in text.split("\n") if re.search(r"(error|exception|fatal|failed|crash)", l, re.I)]
    blob = "\n".join(error_lines).lower()
    for mod in mods:
        for key in {mod.mod_id.lower(), Path(mod.name).stem.lower()} - {""}:
            if len(key) >= 4 and key not in NOT_MODS and (n := blob.count(key)):
                _add(suspects, mod.name, f"mentioned in {n} error line{'s' if n != 1 else ''}")
                if mod.name.lower() in suspects:
                    suspects[mod.name.lower()].hits = n
                break
    return CrashReport(path, "log", when, f"{len(error_lines)} error line{'s' if len(error_lines) != 1 else ''} in this log",
                       _ranked(suspects), "\n".join(error_lines[:12]))


def _excerpt(text: str, pattern: str, limit: int = 12) -> str:
    lines = [l.rstrip() for l in text.split("\n") if re.search(pattern, l)]
    seen, out = set(), []
    for l in lines:
        key = re.sub(r"^\[[^\]]*\]\s*|^\S+ \S+\s+", "", l)[:160]
        if key not in seen:
            seen.add(key)
            out.append(l[:300])
        if len(out) >= limit:
            break
    return "\n".join(out)


def _match_mods(report: CrashReport, mods: list) -> None:
    """Link each suspect to a mod file, by id, file name or title."""
    index: dict[str, str] = {}
    for m in mods:
        for key in (m.mod_id, m.name, Path(m.name).stem, m.title):
            if key:
                index.setdefault(key.lower(), m.name)
                index.setdefault(re.sub(r"[^a-z0-9]", "", key.lower()), m.name)
    for s in report.suspects:
        key = s.name.lower()
        s.mod_file = s.mod_file or index.get(key) or index.get(re.sub(r"[^a-z0-9]", "", key), "")
    title = {m.name: m.display_name for m in mods}
    for s in report.suspects:
        if s.mod_file:
            s.name = title.get(s.mod_file, s.name)


def describe(report: CrashReport, limit: int = 5) -> str:
    when = report.when.strftime("%b %d at %I:%M %p").replace(" 0", " ")
    head = f"{report.summary}\n({report.path.name}, {when})"
    if not report.suspects:
        return head + "\n\nNo specific mod is named in this log. The key lines are below."
    lines = "\n".join(f"  {i}. {s.name}" + (f": {s.reason}" if s.reason else "")
                      for i, s in enumerate(report.suspects[:limit], 1))
    return f"{head}\n\nMost likely cause{'s' if len(report.suspects) > 1 else ''}:\n{lines}"


def as_issue_dict(report: CrashReport) -> dict:
    top = next((s for s in report.suspects if s.mod_file), None)
    d = {
        "severity": "warning" if report.crashed else "info",
        "title": "The game crashed recently" if report.crashed else "Mods showing errors in the last session",
        "detail": describe(report) + (f"\n\nFrom the log:\n{report.excerpt}" if report.excerpt else ""),
        "fix": ("Turn off the top suspect and start the game again. If it works, update or replace that mod. "
                "If it still crashes, turn it back on and try the next one.") if report.crashed else
               ("These mods hit errors while the game was running. That doesn't always cause problems, but if "
                "something isn't working, start with the mod at the top of the list."),
        "mods": [s.mod_file for s in report.suspects if s.mod_file],
    }
    if top:
        d.update(action="disable", params={"mods": [top.mod_file]},
                 action_label=f"Turn off {top.name} to test (you can turn it back on)")
    return d
