"""Check mods for viruses with the antivirus already on the PC.

1. Microsoft Defender's command-line scanner (MpCmdRun.exe), when Defender is on. It opens
   archives itself and names the threat.
2. Otherwise Windows' antimalware interface (AMSI), which hands the file to whichever antivirus is
   registered (Norton, Bitdefender, Defender...). Zips are opened and each file inside is checked.
Results are remembered by file hash in virus_scans.json, so a mod is only scanned again when it
changes or the result is more than 30 days old."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from . import paths
from .log import log

CLEAN, THREAT, ERROR, UNAVAILABLE = "clean", "threat", "error", "unavailable"
RESCAN_AFTER = timedelta(days=30)
AMSI_MAX = 128 * 1024 * 1024  # bigger single files are skipped by the AMSI route


@dataclass
class ScanResult:
    status: str  # clean | threat | error | unavailable
    threat: str = ""  # the antivirus's name for what it found
    engine: str = ""
    detail: str = ""
    date: str = ""

    @property
    def flagged(self) -> bool:
        return self.status == THREAT


# ---------------------------------------------------------------- remembered results

def _cache_file() -> Path:
    return paths.data_dir() / "virus_scans.json"


def _load_cache() -> dict:
    try:
        return json.loads(_cache_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def key_for(mod) -> str:
    """What a scan result is remembered by: the file hash, or for folders their name and date."""
    return (mod.sha1 or f"dir:{mod.name}:{int(mod.mtime)}").lower()


def remember(sha1: str, result: ScanResult) -> None:
    if not sha1 or result.status not in (CLEAN, THREAT):
        return
    cache = _load_cache()
    cache[sha1.lower()] = asdict(result) | {"date": result.date or datetime.now().isoformat(timespec="seconds")}
    try:
        _cache_file().write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass


def lookup(sha1: str | None) -> ScanResult | None:
    if not sha1:
        return None
    hit = _load_cache().get(sha1.lower())
    if not hit:
        return None
    try:
        return ScanResult(**hit)
    except TypeError:
        return None


def is_fresh(result: ScanResult | None) -> bool:
    if result is None:
        return False
    if result.flagged:
        return True  # a detection stays until the file changes
    try:
        return datetime.now() - datetime.fromisoformat(result.date) < RESCAN_AFTER
    except ValueError:
        return False


# ---------------------------------------------------------------- Microsoft Defender

_defender_ok: bool | None = None  # None = not tried yet this session


def defender_path() -> Path | None:
    if sys.platform != "win32":
        return None
    platform = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft" / "Windows Defender" / "Platform"
    try:
        versions = sorted((d for d in platform.iterdir() if (d / "MpCmdRun.exe").is_file()),
                          key=lambda d: [int(x) if x.isdigit() else 0 for x in re.split(r"[.-]", d.name)])
        if versions:
            return versions[-1] / "MpCmdRun.exe"
    except OSError:
        pass
    classic = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Windows Defender" / "MpCmdRun.exe"
    return classic if classic.is_file() else None


def _run_defender(target: Path) -> tuple[int, str]:
    exe = defender_path()
    if exe is None:
        return -1, "Microsoft Defender isn't installed"
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW: no console popping up
    try:
        proc = subprocess.run([str(exe), "-Scan", "-ScanType", "3", "-File", str(target), "-DisableRemediation"],
                              capture_output=True, text=True, timeout=1800, creationflags=flags)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, str(exc)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def parse_defender(code: int, output: str) -> tuple[str, list[tuple[str, str]]]:
    """(status, [(threat, file)]) from MpCmdRun's output. Exit code 2 means a threat OR a scan error,
    so the threat lines decide."""
    found: list[tuple[str, str]] = []
    threat = ""
    for line in output.splitlines():
        m = re.match(r"^\s*Threat\s*:\s*(.+?)\s*$", line)
        if m:
            threat = m.group(1)
            continue
        m = re.match(r"^\s*file\s*:\s*(.+?)\s*$", line, re.I)
        if m and threat:
            found.append((threat, m.group(1).split("->")[0].strip()))
    if threat and not found:
        found.append((threat, ""))
    if found:
        return THREAT, found
    if code == 0:
        return CLEAN, []
    return ERROR, []


# ---------------------------------------------------------------- AMSI (any registered antivirus)

class _Amsi:
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ct = ctypes
        self.dll = ctypes.WinDLL("amsi")
        self.ctx = ctypes.c_void_p()
        self.session = ctypes.c_void_p()
        self.dll.AmsiInitialize.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
        self.dll.AmsiOpenSession.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        self.dll.AmsiScanBuffer.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.ULONG, wintypes.LPCWSTR,
                                            ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        self.dll.AmsiCloseSession.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.dll.AmsiUninitialize.argtypes = [ctypes.c_void_p]
        if self.dll.AmsiInitialize("ModTender", ctypes.byref(self.ctx)) != 0:
            raise OSError("AMSI isn't available")
        self.dll.AmsiOpenSession(self.ctx, ctypes.byref(self.session))

    def detected(self, data: bytes, name: str) -> bool:
        result = self.ct.c_int(0)
        buf = self.ct.create_string_buffer(data, len(data))
        hr = self.dll.AmsiScanBuffer(self.ctx, buf, len(data), name, self.session, self.ct.byref(result))
        if hr != 0:
            raise OSError(f"AMSI scan failed ({hr & 0xFFFFFFFF:#x})")
        return result.value >= 32768  # AMSI_RESULT_DETECTED

    def close(self):
        try:
            self.dll.AmsiCloseSession(self.ctx, self.session)
            self.dll.AmsiUninitialize(self.ctx)
        except Exception:
            pass


def _amsi_scan(path: Path) -> ScanResult:
    if sys.platform != "win32":
        return ScanResult(UNAVAILABLE, detail="Virus scanning works on Windows only.")
    try:
        amsi = _Amsi()
    except Exception as exc:
        return ScanResult(UNAVAILABLE, detail=f"No antivirus could be reached: {exc}")
    engine = "your antivirus (through Windows)"
    try:
        parts: list[tuple[str, bytes]] = []
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as zf:
                for info in zf.infolist():
                    if not info.is_dir() and info.file_size <= AMSI_MAX:
                        parts.append((f"{path.name}/{info.filename}", zf.read(info)))
        elif path.stat().st_size <= AMSI_MAX:
            parts.append((path.name, path.read_bytes()))
        else:
            return ScanResult(ERROR, engine=engine, detail="Too big to check this way.")
        for name, data in parts:
            if data and amsi.detected(data, name):
                return ScanResult(THREAT, "Flagged by your antivirus", engine, name)
        return ScanResult(CLEAN, engine=engine)
    except Exception as exc:
        return ScanResult(ERROR, engine=engine, detail=str(exc))
    finally:
        amsi.close()


# ---------------------------------------------------------------- scanning

def scan_file(path: Path) -> ScanResult:
    """Check one file (or folder) before it goes into a game."""
    global _defender_ok
    path = Path(path)
    now = datetime.now().isoformat(timespec="seconds")
    if _defender_ok is not False:
        code, out = _run_defender(path)
        status, found = parse_defender(code, out)
        if status != ERROR:
            _defender_ok = True
            threat = found[0][0] if found else ""
            return ScanResult(status, threat, "Microsoft Defender", found[0][1] if found else "", now)
        if _defender_ok is None:
            _defender_ok = False  # Defender is off (another antivirus is in charge): use AMSI from now on
            log.info("Defender scan unavailable (%s), using AMSI", out.strip().splitlines()[-1:] or code)
    result = _amsi_scan(path) if not path.is_dir() else ScanResult(ERROR, detail="Folders are checked file by file.")
    result.date = now
    return result


def scan_mods(game, mods: list, progress=None, force: bool = False) -> dict[str, ScanResult]:
    """Scan every mod that hasn't been checked recently. Returns {mod file name: result}."""
    results: dict[str, ScanResult] = {}
    todo = []
    for m in mods:
        known = lookup(key_for(m))
        if not force and is_fresh(known):
            results[m.name] = known
        else:
            todo.append(m)
    for n, m in enumerate(todo):
        if progress:
            progress(5 + 90 * n // max(1, len(todo)), f"Checking {m.display_name} ({n + 1} of {len(todo)})…")
        if not m.path.exists():
            continue
        targets = [m.path] if m.path.is_file() else [p for p in m.path.rglob("*") if p.is_file()][:400]
        result = ScanResult(CLEAN, engine="", date=datetime.now().isoformat(timespec="seconds"))
        for target in targets:
            r = scan_file(target)
            result.engine = r.engine or result.engine
            if r.status == THREAT:
                result = r
                result.detail = result.detail or str(target.relative_to(m.path.parent))
                break
            if r.status in (ERROR, UNAVAILABLE):
                result = r
        results[m.name] = result
        remember(key_for(m), result)
    flagged = sum(r.flagged for r in results.values())
    log.info("[%s] Virus scan: %d mods, %d newly checked, %d flagged", game.id, len(mods), len(todo), flagged)
    return results


def flagged_mods(mods: list) -> list[tuple[object, ScanResult]]:
    out = []
    for m in mods:
        r = lookup(key_for(m))
        if r and r.flagged:
            out.append((m, r))
    return out
