"""Install downloaded mod files into a game's mods folder.

ModTender works out what the download is and where its parts belong:
  - a file the game uses directly (.jar, .zip for Farming Simulator, .package, .pak...) is copied in,
  - a .zip is unpacked when the game wants folders (Stardew, RimWorld, Witcher 3) or loose files
    (Skyrim/Fallout Data, Valheim plugins, a Minecraft .jar inside a zip),
  - Cyberpunk downloads that mirror the game's folders (archive/, bin/, r6/...) go to the game folder,
  - Thunderstore packages (Valheim) put their plugins folder into BepInEx/plugins/<mod>.
Anything already there with the same name is moved to ModTender's quarantine first, never overwritten."""
from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .log import log

CYBERPUNK_ROOTS = {"archive", "bin", "r6", "red4ext", "mods", "engine"}
UNSUPPORTED_ARCHIVES = {".rar": "RAR", ".7z": "7-Zip"}


class InstallError(Exception):
    pass


@dataclass
class InstallResult:
    installed: list[str] = field(default_factory=list)  # what ended up in the game, in plain words
    replaced: list[str] = field(default_factory=list)  # older copies moved to quarantine
    problems: list[str] = field(default_factory=list)  # files that weren't installed, and why
    scanned: str = ""  # which antivirus checked the files, or why they couldn't be checked


def install(game, files: list[Path], scan: bool = True) -> InstallResult:
    result = InstallResult()
    if getattr(game, "workshop_only", False):
        result.problems.append(f"{game.name} only uses Steam Workshop mods. Subscribe to mods on Steam instead.")
        return result
    game.mods_dir.mkdir(parents=True, exist_ok=True)
    for src in files:
        if scan and Path(src).is_file():
            from . import virusscan
            verdict = virusscan.scan_file(Path(src))
            if verdict.flagged:
                result.problems.append(f"{Path(src).name}: {verdict.engine or 'your antivirus'} flagged it as "
                                       f"{verdict.threat or 'harmful'}, so it was NOT installed. Delete it from "
                                       "your Downloads.")
                log.warning("[%s] Blocked install of %s: %s", game.id, src, verdict.threat)
                continue
            if verdict.status == virusscan.CLEAN:
                result.scanned = f"Checked with {verdict.engine}: no threats found."
                import hashlib
                try:
                    virusscan.remember(hashlib.sha1(Path(src).read_bytes()).hexdigest(), verdict)
                except OSError:
                    pass
            elif not result.scanned:
                result.scanned = f"Couldn't check for viruses: {verdict.detail or 'no antivirus answered'}."
        try:
            _install_one(game, Path(src), result)
        except InstallError as exc:
            result.problems.append(f"{Path(src).name}: {exc}")
        except (OSError, zipfile.BadZipFile) as exc:
            result.problems.append(f"{Path(src).name}: couldn't install it ({exc})")
    log.info("[%s] Installed %d item(s), replaced %d, %d problem(s)", game.id, len(result.installed),
             len(result.replaced), len(result.problems))
    return result


# ---------------------------------------------------------------- deciding what to do

def _install_one(game, src: Path, result: InstallResult) -> None:
    gdef = game.definition
    exts = {e.lower() for e in gdef.extensions}
    ext = src.suffix.lower()
    if not src.is_file():
        if src.is_dir() and gdef.allow_folders:
            _place_tree(game, src, game.mods_dir / src.name, result)
            result.installed.append(f"{src.name} (folder)")
            return
        raise InstallError("drop the downloaded file, not a folder" if src.is_dir() else "file not found")
    if ext in UNSUPPORTED_ARCHIVES:
        raise InstallError(f"ModTender can't open {UNSUPPORTED_ARCHIVES[ext]} files yet. Extract it with "
                           "7-Zip or WinRAR, then drop what's inside.")
    if ext in exts or (not exts and ext != ".zip"):
        _copy(game, src, game.mods_dir / src.name, result)
        result.installed.append(src.name)
        return
    if ext != ".zip":
        raise InstallError(f"{game.name} doesn't use {ext or 'this kind of'} files.")
    with zipfile.ZipFile(src) as zf:
        members = _safe_members(zf)
        if not members:
            raise InstallError("the zip is empty")
        lower = [m.lower() for m in members]
        if any(m.endswith("fomod/moduleconfig.xml") for m in lower):
            raise InstallError("this mod has an installer with options (FOMOD). Install it with Vortex or "
                               "Mod Organizer 2 so you can pick the options.")
        if gdef.id == "cyberpunk":
            return _cyberpunk(game, src, zf, members, result)
        if gdef.id in ("skyrimse", "fallout4"):
            return _bethesda(game, src, zf, members, result)
        if gdef.id == "valheim":
            return _bepinex(game, src, zf, members, result)
        if gdef.allow_folders:
            return _folders(game, src, zf, members, result)
        # Loose files the game uses directly, packed in a zip (e.g. a Minecraft .jar or Sims .package).
        usable = [m for m in members if PurePosixPath(m).suffix.lower() in exts]
        if not usable:
            raise InstallError(f"nothing inside this zip is a file {game.name} uses.")
        for m in usable:
            _extract(game, zf, m, game.mods_dir / PurePosixPath(m).name, result)
            result.installed.append(PurePosixPath(m).name)


def _cyberpunk(game, src, zf, members, result) -> None:
    root = game.mods_dir.parents[2] if len(game.mods_dir.parents) > 2 else None
    tops = {PurePosixPath(m).parts[0].lower() for m in members}
    if root and tops & CYBERPUNK_ROOTS:
        for m in members:
            _extract(game, zf, m, root / m, result)
        result.installed.append(f"{src.stem} ({len(members)} files into the game folder)")
        return
    archives = [m for m in members if m.lower().endswith((".archive", ".xl"))]
    if not archives:
        raise InstallError("couldn't tell where this mod's files go. Check its install instructions.")
    for m in archives:
        _extract(game, zf, m, game.mods_dir / PurePosixPath(m).name, result)
        result.installed.append(PurePosixPath(m).name)


def _bethesda(game, src, zf, members, result) -> None:
    prefix = _common_prefix(members, "data")
    count = 0
    for m in members:
        rel = m[len(prefix):] if prefix else m
        if rel and not rel.lower().startswith(("readme", "fomod/")):
            _extract(game, zf, m, game.mods_dir / rel, result)
            count += 1
    result.installed.append(f"{src.stem} ({count} files into Data)")


def _bepinex(game, src, zf, members, result) -> None:
    def plugin_rel(m: str) -> str | None:
        parts = PurePosixPath(m).parts
        low = [p.lower() for p in parts]
        return "/".join(parts[low.index("plugins") + 1:]) if "plugins" in low[:-1] else None

    folder = game.mods_dir / src.stem
    plugin_files = [(m, plugin_rel(m)) for m in members if plugin_rel(m)]
    if plugin_files:  # Thunderstore package: manifest.json, icon.png, plugins/...
        _move_aside(game, folder, result)
        for m, rel in plugin_files:
            _extract(game, zf, m, folder / rel, result, aside=False)
        result.installed.append(f"{src.stem} (plugin folder)")
        return
    if not any(m.lower().endswith(".dll") for m in members):
        raise InstallError("there's no plugin (.dll) inside this zip.")
    prefix = _common_prefix(members)
    extras = ("manifest.json", "icon.png", "readme.md", "changelog.md")
    _move_aside(game, folder, result)
    for m in members:
        rel = m[len(prefix):]
        if rel.lower() not in extras:
            _extract(game, zf, m, folder / rel, result, aside=False)
    result.installed.append(f"{src.stem} (plugin folder)")


def _folders(game, src, zf, members, result) -> None:
    tops = {PurePosixPath(m).parts[0] for m in members}
    all_dirs = all(len(PurePosixPath(m).parts) > 1 for m in members)
    base = game.mods_dir if all_dirs else game.mods_dir / src.stem
    for top in (tops if all_dirs else {src.stem}):
        _move_aside(game, game.mods_dir / top, result)
    for m in members:
        _extract(game, zf, m, base / m, result, aside=False)
    names = sorted(tops) if all_dirs else [src.stem]
    result.installed.append(", ".join(f"{n} (folder)" for n in names))


# ---------------------------------------------------------------- file helpers

def _safe_members(zf: zipfile.ZipFile) -> list[str]:
    out = []
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        if info.is_dir() or not name.strip("/"):
            continue
        parts = PurePosixPath(name).parts
        if name.startswith("/") or ".." in parts or (parts and parts[0].endswith(":")):
            raise InstallError("the zip contains unsafe paths, so it wasn't installed")
        if parts[0] == "__MACOSX" or PurePosixPath(name).name in (".DS_Store", "Thumbs.db"):
            continue
        out.append(name)
    return out


def _common_prefix(members: list[str], only: str = "") -> str:
    """A single top folder every file sits in ('ModName/'), or '' if there isn't one."""
    tops = {m.split("/", 1)[0] for m in members}
    if len(tops) == 1 and all("/" in m for m in members):
        top = next(iter(tops))
        if not only or top.lower() == only:
            return top + "/"
    return ""


def _move_aside(game, target: Path, result: InstallResult) -> None:
    if target.exists():
        from .fixer import _quarantine
        _quarantine(game, target)
        result.replaced.append(target.name)


def _copy(game, src: Path, dest: Path, result: InstallResult) -> None:
    if src.resolve() == dest.resolve():
        raise InstallError("it's already in the mods folder")
    _move_aside(game, dest, result)
    shutil.copy2(src, dest)


def _extract(game, zf: zipfile.ZipFile, member: str, dest: Path, result: InstallResult, aside: bool = True) -> None:
    if aside:
        _move_aside(game, dest, result)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(member) as fin, open(dest, "wb") as fout:
        shutil.copyfileobj(fin, fout)


def _place_tree(game, src: Path, dest: Path, result: InstallResult) -> None:
    _move_aside(game, dest, result)
    shutil.copytree(src, dest)
