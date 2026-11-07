"""Share a mod setup, and compare yours with someone else's (a friend, a server, a modpack).

Lists ModTender can read:
  - its own .modtender setup files (what "Share my mod list" saves),
  - Farming Simulator: a dedicated server's stats feed (dedicated-server-stats.xml, from a file or the
    server's link) and a savegame's careerSavegame.xml,
  - Minecraft: Modrinth modpacks (.mrpack / modrinth.index.json), which also say where to download,
  - Arma 3: Arma 3 Launcher presets (.html export, or .preset2 from the launcher's folder),
  - Arma Reforger: a server's config.json ("mods": [{"modId", "name", "version"}]),
  - plain text: one mod name or file name per line (for example copied from a server's mods page).
Mods are matched by file hash where both sides have one, then by mod id, then by name."""
from __future__ import annotations

import json
import re
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree

from .. import __version__

FORMAT = "modtender-setup"


@dataclass
class ListedMod:
    name: str  # file name or folder name, as the list gives it
    title: str = ""
    mod_id: str = ""
    version: str = ""
    sha1: str = ""
    download: str = ""  # direct download link, when the list has one (Modrinth packs)
    size: int = 0
    workshop_id: str = ""


@dataclass
class ModList:
    source: str  # what the list is, in plain words
    game_id: str = ""
    mods: list[ListedMod] = field(default_factory=list)
    mc_version: str = ""
    loader: str = ""


@dataclass
class Match:
    listed: ListedMod
    mod: object | None  # the installed Mod, or None


@dataclass
class Comparison:
    missing: list[ListedMod]  # in the list, not installed at all
    turned_off: list[Match]  # installed here but disabled
    other_version: list[Match]  # installed and on, but a different version
    same: list[Match]
    extra: list  # Mods on here that the list doesn't have

    @property
    def matches(self) -> bool:
        return not (self.missing or self.turned_off or self.other_version or self.extra)


# ---------------------------------------------------------------- sharing

def export_setup(game, mods: list, target: Path) -> Path:
    from .minecraft import instance_info
    data = {"format": FORMAT, "version": 1, "app": f"ModTender {__version__}",
            "created": datetime.now().isoformat(timespec="seconds"), "game_id": game.definition.id,
            "game_name": game.name, "mods": []}
    if game.definition.id == "minecraft":
        loader, mc = instance_info(game.mods_dir)
        data["minecraft"] = {"loader": loader, "version": mc}
    for m in sorted((m for m in mods if m.enabled), key=lambda m: m.name.lower()):
        data["mods"].append({k: v for k, v in {
            "name": m.name, "title": m.title, "mod_id": m.mod_id, "version": m.version, "sha1": m.sha1 or "",
            "size": m.size, "workshop_id": m.workshop_id}.items() if v})
    target.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return target


# ---------------------------------------------------------------- reading lists

class ListError(Exception):
    pass


def read_list(path_or_text: str | Path, from_text: bool = False) -> ModList:
    if from_text:
        text = str(path_or_text).strip()
        if re.match(r"^https?://", text) and "\n" not in text:
            return _from_url(text)
        return _parse_text(text, "the list you pasted")
    path = Path(path_or_text)
    if path.suffix.lower() == ".mrpack" or zipfile.is_zipfile(path):
        try:
            with zipfile.ZipFile(path) as zf:
                return _mrpack(json.loads(zf.read("modrinth.index.json").decode("utf-8")), path.name)
        except KeyError:
            raise ListError("That zip isn't a Modrinth modpack (it has no modrinth.index.json).") from None
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise ListError(f"Couldn't open that file: {exc}") from None
    return _parse_text(text, path.name)


def _from_url(url: str) -> ModList:
    req = urllib.request.Request(url, headers={"User-Agent": f"ModTender/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read(5_000_000).decode("utf-8", errors="replace")
    except Exception as exc:
        raise ListError(f"Couldn't load that link: {exc}") from None
    return _parse_text(text, "the server")


def _parse_text(text: str, label: str) -> ModList:
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except ValueError:
            raise ListError("That looks like a JSON file, but it couldn't be read.") from None
        if data.get("format") == FORMAT:
            return _setup(data, label)
        if "files" in data and data.get("game") == "minecraft":
            return _mrpack(data, label)
        reforger = (data.get("game") or {}).get("mods") if isinstance(data.get("game"), dict) else data.get("mods")
        if isinstance(reforger, list) and any(isinstance(m, dict) and m.get("modId") for m in reforger):
            mods = [ListedMod(str(m.get("name") or m["modId"]), str(m.get("name") or ""), str(m["modId"]),
                              str(m.get("version") or "")) for m in reforger if isinstance(m, dict) and m.get("modId")]
            name = (data.get("game") or {}).get("name") if isinstance(data.get("game"), dict) else ""
            return ModList(f"{len(mods)} mods from the server config{f' {name}' if name else ''} ({label})",
                           "reforger", mods)
        raise ListError("ModTender doesn't recognise this JSON file. It reads ModTender setup files and "
                        "Modrinth modpacks.")
    if stripped.startswith("<") and 'data-type="ModContainer"' in stripped:
        return _arma_html(stripped, label)
    if stripped.startswith("<"):
        return _xml(stripped, label)
    names = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip().strip('"')
        if line and not line.startswith("#") and len(line) < 200:
            names.append(ListedMod(name=line))
    if not names:
        raise ListError("There are no mod names in that list.")
    return ModList(f"{len(names)} names from {label}", mods=names)


def _setup(data: dict, label: str) -> ModList:
    mc = data.get("minecraft") or {}
    mods = [ListedMod(**{k: v for k, v in m.items() if k in ListedMod.__dataclass_fields__})
            for m in data.get("mods", []) if isinstance(m, dict) and m.get("name")]
    return ModList(f"{data.get('game_name') or 'a ModTender setup'} ({label})", data.get("game_id", ""), mods,
                   mc.get("version", ""), mc.get("loader", ""))


def _mrpack(index: dict, label: str) -> ModList:
    mods = []
    for f in index.get("files", []):
        path = str(f.get("path", ""))
        if not path.startswith("mods/") or (f.get("env") or {}).get("client") == "unsupported":
            continue
        downloads = [u for u in f.get("downloads", []) if str(u).startswith("https://")]
        mods.append(ListedMod(name=Path(path).name, sha1=(f.get("hashes") or {}).get("sha1", ""),
                              download=downloads[0] if downloads else "", size=int(f.get("fileSize") or 0)))
    deps = index.get("dependencies") or {}
    loader = next((l.replace("-loader", "") for l in ("neoforge", "forge", "fabric-loader", "quilt-loader")
                   if l in deps), "")
    return ModList(f"{index.get('name') or 'Modrinth pack'} {index.get('versionId', '')} ({label})".replace("  ", " "),
                   "minecraft", mods, str(deps.get("minecraft", "")), loader)


def _arma_html(text: str, label: str) -> ModList:
    """An Arma 3 Launcher preset exported as HTML."""
    import html
    mods = []
    for row in re.findall(r'<tr[^>]*data-type="ModContainer"[^>]*>(.*?)</tr>', text, re.S | re.I):
        name = re.search(r'data-type="DisplayName"[^>]*>(.*?)</td>', row, re.S)
        link = re.search(r"filedetails/\?id=(\d+)", row)
        title = html.unescape(re.sub(r"<[^>]+>", "", name.group(1))).strip() if name else ""
        if title or link:
            mods.append(ListedMod(title or link.group(1), title, workshop_id=link.group(1) if link else ""))
    preset = re.search(r'<meta name="arma:PresetName" content="([^"]*)"', text)
    if not mods:
        raise ListError("That Arma 3 preset has no mods in it.")
    return ModList(f"{len(mods)} mods from the Arma 3 preset"
                   f"{f' {html.unescape(preset.group(1))}' if preset else ''} ({label})", "arma3", mods)


def _xml(text: str, label: str) -> ModList:
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        raise ListError("That XML file couldn't be read.") from None
    mods = []
    if root.tag.lower() == "addons-presets":  # Arma 3 Launcher .preset2 file
        for el in root.iter("id"):
            value = (el.text or "").strip()
            if value.startswith("steam:"):
                mods.append(ListedMod(value[6:], workshop_id=value[6:]))
            elif value.startswith("local:"):
                mods.append(ListedMod(Path(value[6:].rstrip("\\/").replace("\\", "/")).name))
        if mods:
            name = root.findtext("name") or ""
            return ModList(f"{len(mods)} mods from the Arma 3 preset{f' {name}' if name else ''} ({label})",
                           "arma3", mods)
    for el in root.iter():
        tag = el.tag.lower()
        if tag == "mod" and el.get("name"):  # dedicated-server-stats.xml: <Mod name="FS25_x" version="..">Title</Mod>
            mods.append(ListedMod(el.get("name"), (el.text or "").strip(), version=el.get("version", "")))
        elif tag == "mod" and el.get("modName"):  # careerSavegame.xml: <mod modName="FS25_x" title=".." version=".."/>
            if el.get("required", "true").lower() == "false":
                continue
            mods.append(ListedMod(el.get("modName"), el.get("title", ""), version=el.get("version", "")))
    if not mods:
        raise ListError("ModTender couldn't find a mod list in that XML file. It reads Farming Simulator "
                        "server stats (dedicated-server-stats.xml) and savegames (careerSavegame.xml).")
    kind = "the server" if root.tag.lower() == "server" else "the savegame" if "career" in root.tag.lower() else label
    name = root.get("name") or ""
    return ModList(f"{len(mods)} mods from {kind}{f' {name}' if name else ''}", "fs", mods)


# ---------------------------------------------------------------- comparing

def _norm(text: str) -> str:
    """'Sodium-Fabric-0.5.8+mc1.20.1.jar' -> 'sodiumfabric': drop extensions, versions and punctuation.
    Returns '' when too little is left to match safely."""
    t = text.lower().strip()
    t = re.sub(r"\.(jar|zip|pak|package|archive|disabled)$", "", t)
    t = re.sub(r"^fs\d\d_", "", t)  # FS25_Tractor -> tractor
    t = re.sub(r"[-_+ ]?(mc|fabric|forge|neoforge|quilt)?[-_ ]?1\.\d+(\.\d+)?(?=$|[-_+ ])", "", t)
    t = re.sub(r"([-_+ ]v?\d+(\.\d+)+([-+][a-z0-9.]+)?)+$", "", t)  # trailing version like -0.5.8 or _v1.2
    t = re.sub(r"[^a-z0-9]", "", t)
    return t if len(t) >= 4 else ""


def compare(mod_list: ModList, mods: list) -> Comparison:
    installed = [m for m in mods if not m.protected]
    by_sha = {m.sha1.lower(): m for m in installed if m.sha1}
    by_workshop = {m.workshop_id: m for m in installed if m.workshop_id}
    by_name = {m.name.lower(): m for m in installed}
    by_stem = {Path(m.name).stem.lower(): m for m in installed}
    by_id = {m.mod_id.lower(): m for m in installed if m.mod_id}
    by_title = {m.title.lower(): m for m in installed if m.title}
    by_norm: dict[str, object] = {}
    for m in installed:
        for key in (m.name, m.mod_id, m.title):
            if key and _norm(key):
                by_norm.setdefault(_norm(key), m)
    used = set()
    missing, off, other, same = [], [], [], []
    for item in mod_list.mods:
        mod = (by_workshop.get(item.workshop_id) if item.workshop_id else None) \
            or (by_sha.get(item.sha1.lower()) if item.sha1 else None) \
            or by_name.get(item.name.lower()) or by_stem.get(Path(item.name).stem.lower()) \
            or by_stem.get(item.name.lower()) \
            or (by_id.get(item.mod_id.lower()) if item.mod_id else None) \
            or (by_title.get(item.title.lower()) if item.title else None) \
            or by_title.get(item.name.lower()) \
            or by_norm.get(_norm(item.name) or "\0")
        if mod is None or id(mod) in used:
            missing.append(item)
            continue
        used.add(id(mod))
        match = Match(item, mod)
        if not mod.enabled:
            off.append(match)
        elif _different(item, mod):
            other.append(match)
        else:
            same.append(match)
    extra = [m for m in installed if m.enabled and id(m) not in used]
    return Comparison(missing, off, other, same, extra)


def _different(item: ListedMod, mod) -> bool:
    if item.sha1 and mod.sha1:
        return item.sha1.lower() != mod.sha1.lower()
    if item.version and mod.version:
        return item.version.strip().lower() != mod.version.strip().lower()
    return False


def summary(c: Comparison) -> str:
    if c.matches:
        return f"Your mods match: all {len(c.same)} are installed and turned on, with nothing extra."
    parts = []
    if c.missing:
        parts.append(f"{len(c.missing)} missing")
    if c.turned_off:
        parts.append(f"{len(c.turned_off)} turned off here")
    if c.other_version:
        parts.append(f"{len(c.other_version)} different version{'s' if len(c.other_version) != 1 else ''}")
    if c.extra:
        parts.append(f"{len(c.extra)} extra")
    return f"{len(c.same)} match. " + ", ".join(parts) + "."


def as_text(c: Comparison) -> str:
    """The comparison as plain text, to paste into a chat."""
    out = [summary(c)]
    for label, rows in (("Missing", [m.title or m.name for m in c.missing]),
                        ("Turned off", [m.mod.display_name for m in c.turned_off]),
                        ("Different version", [f"{m.mod.display_name}: you have {m.mod.version or m.mod.name}, "
                                               f"list has {m.listed.version or m.listed.name}" for m in c.other_version]),
                        ("Extra (not in the list)", [m.display_name for m in c.extra])):
        if rows:
            out.append(f"\n{label}:\n" + "\n".join(f"  - {r}" for r in rows))
    return "\n".join(out)


def download_missing(game, items: list[ListedMod], progress=None) -> tuple[list[str], list[str]]:
    """Download missing mods that have a direct link (Modrinth packs), checking each file's hash."""
    import hashlib
    done, problems = [], []
    for n, item in enumerate(items):
        if progress:
            progress(100 * n // max(1, len(items)), f"Downloading {item.name}…")
        if not item.download or "/" in item.name or "\\" in item.name:
            problems.append(f"{item.name}: no download link")
            continue
        target = game.mods_dir / item.name
        part = target.with_name(target.name + ".modtender-part")
        try:
            req = urllib.request.Request(item.download, headers={"User-Agent": f"ModTender/{__version__}"})
            h = hashlib.sha1()
            with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as out:
                while chunk := resp.read(1 << 16):
                    h.update(chunk)
                    out.write(chunk)
            if item.sha1 and h.hexdigest().lower() != item.sha1.lower():
                raise OSError("the download didn't match the pack's checksum")
            from . import virusscan
            verdict = virusscan.scan_file(part)
            if verdict.flagged:
                raise OSError(f"{verdict.engine} flagged the download as {verdict.threat}, so it wasn't installed")
            if verdict.status == virusscan.CLEAN:
                virusscan.remember(h.hexdigest(), verdict)
            if target.exists():
                raise OSError("a file with that name is already there")
            part.replace(target)
            done.append(item.name)
        except Exception as exc:
            part.unlink(missing_ok=True)
            problems.append(f"{item.name}: {exc}")
    return done, problems


def search_url(game, item: ListedMod) -> str:
    import urllib.parse
    from .issues import SEARCH_URLS
    if item.workshop_id:
        return f"https://steamcommunity.com/sharedfiles/filedetails/?id={item.workshop_id}"
    gid = game.definition.id
    if gid == "reforger" and item.mod_id:
        return f"https://reforger.armaplatform.com/workshop/{item.mod_id}"
    q = urllib.parse.quote(item.title or re.sub(r"^FS2\d_", "", Path(item.name).stem))
    if gid in SEARCH_URLS:
        return SEARCH_URLS[gid].format(q=q)
    if gid == "minecraft":
        return f"https://modrinth.com/mods?q={q}"
    return f"https://www.nexusmods.com/search?keyword={q}"
