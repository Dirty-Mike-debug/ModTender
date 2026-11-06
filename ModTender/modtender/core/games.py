"""Known games and automatic detection of their mod folders."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import paths

# A FS22/FS25 mod file name must be letters, digits and underscores, and not start
# with a digit, or the game silently ignores the mod.
FS_NAME_RULE = r"^[A-Za-z_][A-Za-z0-9_]*(\.zip)?$"


@dataclass(frozen=True)
class GameDef:
    id: str
    name: str
    mod_paths: tuple[str, ...]  # templates, first match wins
    extensions: tuple[str, ...] = ()  # allowed mod file types; empty = anything
    allow_folders: bool = True
    allows_dll: bool = False  # does this game legitimately load .dll mods?
    name_rule: str | None = None
    rule_hint: str = ""
    required_root_file: str | None = None  # file every archive mod must have at its root
    protected_rule: str | None = None  # base-game files that must never be disabled
    steam_appid: int = 0  # links the game to its Steam Workshop folder
    folders_only: bool = False  # mods must be folders; loose files (zips etc.) are ignored by the game
    name_prefix: str = ""  # mod names must start with this; Fix renames by adding it


KNOWN_GAMES: tuple[GameDef, ...] = (
    GameDef(
        "fs25", "Farming Simulator 25",
        ("{documents}/My Games/FarmingSimulator2025/mods",),
        extensions=(".zip",), name_rule=FS_NAME_RULE,
        rule_hint="Farming Simulator only loads mods whose names use letters, numbers and underscores, and don't start with a number.",
        required_root_file="modDesc.xml",
    ),
    GameDef(
        "fs22", "Farming Simulator 22",
        ("{documents}/My Games/FarmingSimulator2022/mods",),
        extensions=(".zip",), name_rule=FS_NAME_RULE,
        rule_hint="Farming Simulator only loads mods whose names use letters, numbers and underscores, and don't start with a number.",
        required_root_file="modDesc.xml",
    ),
    GameDef("minecraft", "Minecraft (Java)", ("{appdata}/.minecraft/mods",), extensions=(".jar",), allow_folders=False),
    GameDef("stardew", "Stardew Valley", ("{steam:Stardew Valley}/Mods",), allows_dll=True),
    GameDef("skyrimse", "Skyrim Special Edition", ("{steam:Skyrim Special Edition}/Data",),
            extensions=(".esp", ".esm", ".esl", ".bsa"), allow_folders=False,
            protected_rule=r"^(Skyrim|Update|Dawnguard|HearthFires|Dragonborn)\.esm$|^Skyrim - .*\.bsa$|^cc.*\.(esl|esm|bsa)$|^_ResourcePack\.(esl|bsa)$"),
    GameDef("fallout4", "Fallout 4", ("{steam:Fallout 4}/Data",),
            extensions=(".esp", ".esm", ".esl", ".ba2"), allow_folders=False,
            protected_rule=r"^(Fallout4|DLC\w+)\.esm$|^(Fallout4|DLC\w+) - .*\.ba2$|^cc.*\.(esl|esm|ba2)$"),
    GameDef("witcher3", "The Witcher 3: Wild Hunt",
            ("{steam:The Witcher 3}/mods",
             "C:/Program Files (x86)/GOG Galaxy/Games/The Witcher 3 Wild Hunt GOTY/mods",
             "C:/GOG Games/The Witcher 3 Wild Hunt GOTY/mods"),
            folders_only=True, name_prefix="mod", steam_appid=292030,
            rule_hint="The Witcher 3 only loads folders in 'mods' whose names start with 'mod'."),
    GameDef("cyberpunk", "Cyberpunk 2077", ("{steam:Cyberpunk 2077}/archive/pc/mod",), extensions=(".archive", ".xl")),
    GameDef("bg3", "Baldur's Gate 3", ("{localappdata}/Larian Studios/Baldur's Gate 3/Mods",), extensions=(".pak",)),
    GameDef("valheim", "Valheim (BepInEx)", ("{steam:Valheim}/BepInEx/plugins",), allows_dll=True),
    GameDef("rimworld", "RimWorld", ("{steam:RimWorld}/Mods",), steam_appid=294100),
    GameDef("ets2", "Euro Truck Simulator 2", ("{documents}/Euro Truck Simulator 2/mod",), extensions=(".scs", ".zip"),
            steam_appid=227300),
    GameDef("ats", "American Truck Simulator", ("{documents}/American Truck Simulator/mod",), extensions=(".scs", ".zip"),
            steam_appid=270880),
    GameDef("cs2", "Cities: Skylines II", ("{locallow}/Colossal Order/Cities Skylines II/Mods",), allows_dll=True),
    GameDef("snowrunner", "SnowRunner", ("{documents}/My Games/SnowRunner/base/Mods",)),
)

GAME_DEFS = {g.id: g for g in KNOWN_GAMES}
GENERIC = GameDef("custom", "Custom game", ())
WORKSHOP = GameDef("workshop", "Steam Workshop game", ())


@dataclass
class Game:
    id: str
    name: str
    mods_dir: Path
    definition: GameDef
    source: str = "detected"  # detected | steam | curseforge | custom | workshop
    workshop_dir: Path | None = None  # steamapps/workshop/content/<appid>, scanned as well
    steam_appid: int = 0

    @property
    def custom(self) -> bool:
        return self.source == "custom"

    @property
    def workshop_only(self) -> bool:
        """All of this game's mods are managed by Steam (nothing for ModTender to move or back up)."""
        return self.source == "workshop"


# ---------------------------------------------------------------- Steam

def _steam_roots() -> list[Path]:
    roots: list[Path] = []
    if paths.IS_WINDOWS:
        try:
            import winreg

            for hive, key, value in (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath"),
            ):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        roots.append(Path(winreg.QueryValueEx(k, value)[0]))
                except OSError:
                    continue
        except ImportError:
            pass
    roots += [Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")]
    seen, unique = set(), []
    for r in roots:
        key = str(r).lower().replace("/", "\\")
        if key not in seen and r.exists():
            seen.add(key)
            unique.append(r)
    return unique


def steam_libraries() -> list[Path]:
    """Every Steam library folder (each has a steamapps/common inside)."""
    libs: list[Path] = []
    for root in _steam_roots():
        libs.append(root)
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            text = vdf.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            libs.append(Path(match.group(1).replace("\\\\", "\\")))
    seen, unique = set(), []
    for lib in libs:
        key = str(lib).lower()
        if key not in seen and (lib / "steamapps" / "common").exists():
            seen.add(key)
            unique.append(lib)
    return unique


def _resolve_template(template: str, libraries: list[Path]) -> list[Path]:
    m = re.match(r"\{steam:([^}]+)\}(.*)", template)
    if m:
        folder, rest = m.groups()
        return [Path(str(lib / "steamapps" / "common" / folder) + rest) for lib in libraries]
    expanded = template.format(
        documents=paths.DOCUMENTS, appdata=paths.APPDATA, localappdata=paths.LOCALAPPDATA,
        locallow=paths.LOCALLOW, home=paths.HOME,
    )
    return [Path(expanded)]


# ---------------------------------------------------------------- detection

def steam_workshops(libraries: list[Path]) -> dict[int, tuple[Path, str]]:
    """appid -> (workshop content folder, game name) for every Steam game with Workshop items."""
    found: dict[int, tuple[Path, str]] = {}
    for lib in libraries:
        content = lib / "steamapps" / "workshop" / "content"
        if not content.is_dir():
            continue
        for d in content.iterdir():
            if not (d.is_dir() and d.name.isdigit()):
                continue
            try:
                if not any(p.is_dir() for p in d.iterdir()):
                    continue  # no items subscribed
            except OSError:
                continue
            appid, name = int(d.name), ""
            for manifest_lib in libraries:  # the game may be installed in a different library
                acf = manifest_lib / "steamapps" / f"appmanifest_{appid}.acf"
                try:
                    m = re.search(r'"name"\s+"([^"]+)"', acf.read_text(encoding="utf-8", errors="ignore"))
                except OSError:
                    continue
                if m:
                    name = m.group(1)
                    break
            found.setdefault(appid, (d, name or f"Steam app {appid}"))
    return found


def detect_games(custom_games: list[dict] | None = None) -> list[Game]:
    libraries = steam_libraries()
    workshops = steam_workshops(libraries)
    games: list[Game] = []

    for gdef in KNOWN_GAMES:
        for template in gdef.mod_paths:
            hit = next((p for p in _resolve_template(template, libraries) if p.is_dir()), None)
            if hit is None:
                # Steam game installed but its mod folder doesn't exist yet: still list it.
                m = re.match(r"\{steam:([^}]+)\}", template)
                if m:
                    for lib in libraries:
                        if (lib / "steamapps" / "common" / m.group(1)).is_dir():
                            hit = _resolve_template(template, [lib])[0]
                            break
            if hit is not None:
                source = "steam" if template.startswith("{steam:") else "detected"
                ws = workshops.pop(gdef.steam_appid, (None, ""))[0] if gdef.steam_appid else None
                games.append(Game(gdef.id, gdef.name, hit, gdef, source, workshop_dir=ws, steam_appid=gdef.steam_appid))
                break
        else:
            if gdef.steam_appid and gdef.steam_appid in workshops:
                # Only Workshop mods (no local mod folder): still worth listing under the known game.
                ws, _ = workshops.pop(gdef.steam_appid)
                games.append(Game(gdef.id, gdef.name, ws, gdef, "workshop", workshop_dir=ws, steam_appid=gdef.steam_appid))

    # Every CurseForge Minecraft instance is its own "game" with its own mods folder.
    cf_root = paths.HOME / "curseforge" / "minecraft" / "Instances"
    if cf_root.is_dir():
        mc = GAME_DEFS["minecraft"]
        for inst in sorted(p for p in cf_root.iterdir() if p.is_dir()):
            mods = inst / "mods"
            if mods.is_dir():
                slug = re.sub(r"[^a-z0-9]+", "-", inst.name.lower()).strip("-")
                games.append(Game(f"cf-{slug}", f"Minecraft - {inst.name} (CurseForge)", mods, mc, "curseforge"))

    # Every other Steam game with Workshop mods gets its own entry.
    for appid, (ws, name) in sorted(workshops.items(), key=lambda kv: kv[1][1].lower()):
        games.append(Game(f"steam-{appid}", f"{name} (Steam Workshop)", ws, WORKSHOP, "workshop",
                          workshop_dir=ws, steam_appid=appid))

    for entry in custom_games or []:
        base = GAME_DEFS.get(entry.get("base", ""), GENERIC)
        games.append(Game(entry["id"], entry["name"], Path(entry["path"]), base, "custom"))

    return games


def make_custom_game_entry(name: str, folder: str, existing_ids: set[str]) -> dict:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "game"
    gid, n = f"custom-{slug}", 2
    while gid in existing_ids:
        gid, n = f"custom-{slug}-{n}", n + 1
    return {"id": gid, "name": name, "path": folder, "base": "custom"}
