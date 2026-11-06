"""Scan a game's mod folder: list mods, read their metadata, hash them."""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from . import paths
from .games import Game
from .log import log

ARCHIVE_EXTS = {".zip", ".jar", ".scs"}
RISKY_EXTS = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".scr", ".com", ".msi", ".pif", ".hta", ".wsf", ".lnk"}


@dataclass
class Mod:
    name: str  # file or folder name
    path: Path
    kind: str  # archive | file | folder
    size: int
    mtime: float
    enabled: bool
    protected: bool = False
    sha1: str | None = None
    title: str = ""
    version: str = ""
    mod_id: str = ""
    author: str = ""
    corrupt: str = ""  # empty when fine, otherwise the reason
    root_files: list[str] = field(default_factory=list)
    risky_files: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # FS mod names / Stardew UniqueIDs
    inner_zips: list[str] = field(default_factory=list)  # zips packed inside this zip (mod packs)
    nested_root: str = ""  # folder inside the archive that holds the real mod (zipped one level too deep)
    script_files: dict = field(default_factory=dict)  # Witcher 3: script path (lower) -> modified time
    origin: str = "local"  # local | workshop (managed by Steam)
    workshop_id: str = ""

    @property
    def display_name(self) -> str:
        return self.title or (f"Workshop item {self.workshop_id}" if self.workshop_id else self.name)

    @property
    def workshop(self) -> bool:
        return self.origin == "workshop"

    @property
    def workshop_url(self) -> str:
        return f"https://steamcommunity.com/sharedfiles/filedetails/?id={self.workshop_id}" if self.workshop_id else ""

    @property
    def modified(self) -> datetime:
        return datetime.fromtimestamp(self.mtime)


@dataclass
class ScanResult:
    game: Game
    mods: list[Mod]
    strays: list[Path]  # files in the mod folder the game can't use
    scanned_at: datetime
    folder_missing: bool = False


# ---------------------------------------------------------------- hashing (cached)

class HashCache:
    def __init__(self) -> None:
        self.file = paths.data_dir() / "hash_cache.json"
        try:
            self.data = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}
        self.dirty = False

    def sha1(self, path: Path, size: int, mtime: float) -> str:
        key = str(path).lower()
        hit = self.data.get(key)
        if hit and hit[0] == size and abs(hit[1] - mtime) < 1:
            return hit[2]
        h = hashlib.sha1()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        digest = h.hexdigest()
        self.data[key] = [size, mtime, digest]
        self.dirty = True
        return digest

    def save(self) -> None:
        if self.dirty:
            try:
                self.file.write_text(json.dumps(self.data), encoding="utf-8")
            except OSError:
                pass


# ---------------------------------------------------------------- metadata

def _xml_text(root, *tags: str) -> str:
    for tag in tags:
        node = root.find(tag)
        if node is not None:
            # FS titles look like <title><en>Name</en><de>...</de></title>
            en = node.find("en")
            text = (en.text if en is not None else node.text) or ""
            if text.strip():
                return text.strip()
    return ""


def _apply_moddesc(mod: Mod, data: bytes) -> None:
    try:
        root = ElementTree.fromstring(data)
        mod.title = mod.title or _xml_text(root, "title")
        mod.version = mod.version or _xml_text(root, "version")
        mod.author = mod.author or _xml_text(root, "author")
        for dep in root.iter("dependency"):
            name = (dep.text or "").strip()
            if name and name not in mod.dependencies:
                mod.dependencies.append(name)
    except ElementTree.ParseError:
        text = data.decode("utf-8", errors="ignore")
        m = re.search(r"<version>\s*([^<]+?)\s*</version>", text)
        if m:
            mod.version = mod.version or m.group(1)


def _apply_json_manifest(mod: Mod, data: bytes, kind: str) -> None:
    try:
        meta = json.loads(data.decode("utf-8-sig", errors="ignore"))
    except ValueError:
        return
    if kind == "fabric":  # fabric.mod.json / quilt.mod.json
        if "quilt_loader" in meta:
            meta = meta["quilt_loader"] | meta["quilt_loader"].get("metadata", {})
        mod.mod_id = mod.mod_id or str(meta.get("id", ""))
        mod.version = mod.version or str(meta.get("version", ""))
        mod.title = mod.title or str(meta.get("name", ""))
        authors = meta.get("authors") or meta.get("contributors") or []
        if isinstance(authors, list) and authors:
            first = authors[0]
            mod.author = mod.author or (first.get("name", "") if isinstance(first, dict) else str(first))
    else:  # Stardew SMAPI manifest.json
        mod.mod_id = mod.mod_id or str(meta.get("UniqueID", ""))
        mod.version = mod.version or str(meta.get("Version", ""))
        mod.title = mod.title or str(meta.get("Name", ""))
        mod.author = mod.author or str(meta.get("Author", ""))
        deps = list(meta.get("Dependencies") or [])
        if isinstance(meta.get("ContentPackFor"), dict):
            deps.append({**meta["ContentPackFor"], "IsRequired": True})
        for dep in deps:
            if isinstance(dep, dict) and dep.get("UniqueID") and dep.get("IsRequired", True) is not False:
                uid = str(dep["UniqueID"])
                if uid.lower() != "smapi" and uid not in mod.dependencies:
                    mod.dependencies.append(uid)


def _apply_mods_toml(mod: Mod, data: bytes) -> None:  # Forge / NeoForge
    """Read the mod's own entry from the [[mods]] table. The file also lists dependencies
    (each with its own modId), which must not be mistaken for this mod's id."""
    text = data.decode("utf-8", errors="ignore")
    entry: dict = {}
    try:
        import tomllib  # Python 3.11+
        mods = tomllib.loads(text).get("mods") or []
        entry = mods[0] if mods and isinstance(mods[0], dict) else {}
    except Exception:
        # Fallback: only look inside the first [[mods]] block.
        m = re.search(r"^\s*\[\[mods\]\]\s*$(.*?)(?=^\s*\[|\Z)", text, re.M | re.S)
        if m:
            for key in ("modId", "version", "displayName"):
                km = re.search(rf'^\s*{key}\s*=\s*"([^"]*)"', m.group(1), re.M)
                if km:
                    entry[key] = km.group(1)
    for attr, key in (("mod_id", "modId"), ("version", "version"), ("title", "displayName")):
        value = str(entry.get(key, "") or "")
        if value and "${" not in value and not getattr(mod, attr):
            setattr(mod, attr, value)


META_FILES = {
    "moddesc.xml": ("moddesc", None),
    "fabric.mod.json": ("json", "fabric"),
    "quilt.mod.json": ("json", "fabric"),
    "meta-inf/mods.toml": ("toml", None),
    "meta-inf/neoforge.mods.toml": ("toml", None),
    "manifest.json": ("json", "smapi"),
}


def _apply_meta(mod: Mod, member: str, data: bytes) -> None:
    kind, sub = META_FILES[member.lower()]
    if kind == "moddesc":
        _apply_moddesc(mod, data)
    elif kind == "json":
        _apply_json_manifest(mod, data, sub)
    else:
        _apply_mods_toml(mod, data)


def _inspect_archive(mod: Mod, deep: bool) -> None:
    try:
        with zipfile.ZipFile(mod.path) as zf:
            names = zf.namelist()
            if deep:
                bad = zf.testzip()
                if bad:
                    mod.corrupt = f"Damaged file inside the archive: {bad}"
            mod.root_files = sorted({n.split("/", 1)[0] for n in names if n})
            mod.risky_files = [n for n in names if Path(n).suffix.lower() in RISKY_EXTS][:20]
            mod.inner_zips = [n for n in names if n.lower().endswith(".zip")][:200]
            lower = {n.lower(): n for n in names}
            if "moddesc.xml" not in lower and len(mod.root_files) == 1:
                inner = f"{mod.root_files[0]}/moddesc.xml".lower()
                if inner in lower:  # e.g. FS25_Tractor.zip/FS25_Tractor/modDesc.xml
                    mod.nested_root = mod.root_files[0]
                    lower["moddesc.xml"] = lower[inner]
            for meta_name in META_FILES:
                if meta_name in lower:
                    try:
                        _apply_meta(mod, meta_name, zf.read(lower[meta_name])[:2_000_000])
                    except (KeyError, zipfile.BadZipFile, OSError, RuntimeError):
                        pass
    except zipfile.BadZipFile:
        mod.corrupt = "Not a valid archive. The download is probably incomplete or damaged."
    except (OSError, RuntimeError) as exc:
        mod.corrupt = f"Couldn't open the archive: {exc}"


def _apply_rimworld_about(mod: Mod, data: bytes) -> None:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return
    get = lambda tag: (root.findtext(tag) or "").strip()
    mod.title = mod.title or get("name")
    mod.author = mod.author or get("author")
    mod.mod_id = mod.mod_id or get("packageId").lower()
    mod.version = mod.version or get("modVersion")
    for li in root.iterfind("modDependencies/li"):
        pid = (li.findtext("packageId") or "").strip().lower()
        if pid and pid not in mod.dependencies:
            mod.dependencies.append(pid)


def _apply_scs_manifest(mod: Mod, data: bytes) -> None:  # Euro / American Truck Simulator
    text = data.decode("utf-8", errors="ignore")
    for attr, key in (("title", "display_name"), ("version", "package_version"), ("author", "author")):
        m = re.search(rf'^\s*{key}\s*:\s*"([^"]*)"', text, re.M)
        if m and not getattr(mod, attr):
            setattr(mod, attr, m.group(1))


def _apply_folder_extras(mod: Mod) -> None:
    about = mod.path / "About" / "About.xml"
    if about.is_file():
        try:
            _apply_rimworld_about(mod, about.read_bytes()[:500_000])
        except OSError:
            pass
    manifests = [mod.path / "manifest.sii"] + list(mod.path.glob("*/manifest.sii"))[:3]
    for f in manifests:
        if f.is_file():
            try:
                _apply_scs_manifest(mod, f.read_bytes()[:200_000])
            except OSError:
                pass
            break


def _inspect_folder(mod: Mod) -> None:
    total = 0
    risky: list[str] = []
    try:
        mod.root_files = sorted(p.name for p in mod.path.iterdir())
        for f in mod.path.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    continue
                if f.suffix.lower() in RISKY_EXTS and len(risky) < 20:
                    risky.append(str(f.relative_to(mod.path)).replace("\\", "/"))
                if f.suffix.lower() == ".ws":
                    rel = str(f.relative_to(mod.path)).replace("\\", "/").lower()
                    i = rel.find("content/scripts/")
                    if i >= 0:
                        try:
                            mod.script_files[rel[i:]] = f.stat().st_mtime
                        except OSError:
                            pass
    except OSError:
        pass
    mod.size, mod.risky_files = total, risky
    # Metadata may sit at the top or one folder down (common for Stardew).
    for base in [mod.path] + [p for p in mod.path.iterdir() if p.is_dir()][:5] if mod.path.is_dir() else []:
        for meta_name in META_FILES:
            f = base / meta_name
            if f.is_file():
                try:
                    _apply_meta(mod, meta_name, f.read_bytes()[:2_000_000])
                except OSError:
                    pass
        if mod.title or mod.mod_id:
            break
    if not (mod.title or mod.mod_id) and mod.path.is_dir():
        _apply_folder_extras(mod)


# ---------------------------------------------------------------- scanning

def _entries(folder: Path) -> list[Path]:
    try:
        return sorted(folder.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return []


def scan_game(game: Game, deep: bool = False, progress=None) -> ScanResult:
    gdef = game.definition
    exts = {e.lower() for e in gdef.extensions}
    protected = re.compile(gdef.protected_rule, re.I) if gdef.protected_rule else None
    folder_missing = not game.mods_dir.is_dir()

    candidates: list[tuple[Path, bool, str]] = []
    if not game.workshop_only:
        candidates += [(p, True, "local") for p in _entries(game.mods_dir)]
        candidates += [(p, False, "local") for p in _entries(paths.disabled_dir(game.id))]
    if game.workshop_dir:
        candidates += [(p, True, "workshop") for p in _entries(game.workshop_dir) if p.is_dir()]
    mods: list[Mod] = []
    strays: list[Path] = []
    cache = HashCache()
    total = max(len(candidates), 1)

    for i, (entry, enabled, origin) in enumerate(candidates):
        if progress:
            progress(i * 100 / total, f"Checking {entry.name}")
        if entry.name.startswith(".") or entry.name.lower() in {"desktop.ini", "thumbs.db"}:
            continue
        try:
            st = entry.stat()
        except OSError:
            continue
        if origin == "workshop":
            mod = Mod(entry.name, entry, "folder", 0, st.st_mtime, True, origin="workshop", workshop_id=entry.name)
            _inspect_folder(mod)
            if mod.size == 0:
                mod.corrupt = "This Workshop item is empty. Steam may still be downloading it, or the download failed."
        elif entry.is_dir():
            if not gdef.allow_folders:
                continue  # e.g. Skyrim's Data/meshes - game content, not a mod entry
            mod = Mod(entry.name, entry, "folder", 0, st.st_mtime, enabled)
            _inspect_folder(mod)
        else:
            ext = entry.suffix.lower()
            if (exts and ext not in exts) or (gdef.folders_only and origin == "local"):
                if enabled and origin == "local":
                    strays.append(entry)
                continue
            kind = "archive" if ext in ARCHIVE_EXTS else "file"
            mod = Mod(entry.name, entry, kind, st.st_size, st.st_mtime, enabled)
            if ext in RISKY_EXTS:
                mod.risky_files = [entry.name]
            if st.st_size == 0:
                mod.corrupt = "The file is empty (0 bytes)."
            else:
                try:
                    mod.sha1 = cache.sha1(entry, st.st_size, st.st_mtime)
                except OSError as exc:
                    mod.corrupt = f"Couldn't read the file: {exc}"
                if kind == "archive" and not mod.corrupt:
                    _inspect_archive(mod, deep)
        mod.protected = bool(protected and protected.search(mod.name))
        mods.append(mod)

    cache.save()
    log.info("[%s] Scanned %s: %d mods (%d disabled, %d from Steam Workshop), %d stray files", game.id,
             game.mods_dir, len(mods), sum(not m.enabled for m in mods), sum(m.workshop for m in mods), len(strays))
    if progress:
        progress(100, "Scan complete")
    return ScanResult(game, mods, strays, datetime.now(), folder_missing)
