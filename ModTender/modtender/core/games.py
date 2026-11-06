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
    GameDef("cyberpunk", "Cyberpunk 2077", ("{steam:Cyberpunk 2077}/archive/pc/mod",), extensions=(".archive", ".xl")),
    GameDef("bg3", "Baldur's Gate 3", ("{localappdata}/Larian Studios/Baldur's Gate 3/Mods",), extensions=(".pak",)),
    GameDef("valheim", "Valheim (BepInEx)", ("{steam:Valheim}/BepInEx/plugins",), allows_dll=True),
    GameDef("rimworld", "RimWorld", ("{steam:RimWorld}/Mods",)),
    GameDef("ets2", "Euro Truck Simulator 2", ("{documents}/Euro Truck Simulator 2/mod",), extensions=(".scs", ".zip")),
    GameDef("ats", "American Truck Simulator", ("{documents}/American Truck Simulator/mod",), extensions=(".scs", ".zip")),
    GameDef("cs2", "Cities: Skylines II", ("{locallow}/Colossal Order/Cities Skylines II/Mods",), allows_dll=True),
    GameDef("snowrunner", "SnowRunner", ("{documents}/My Games/SnowRunner/base/Mods",)),
)

GAME_DEFS = {g.id: g for g in KNOWN_GAMES}
GENERIC = GameDef("custom", "Custom game", ())


@dataclass
class Game:
    id: str
    name: str
    mods_dir: Path
    definition: GameDef
    source: str = "detected"  # detected | steam | curseforge | custom

    @property
    def custom(self) -> bool:
        return self.source == "custom"


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

def detect_games(custom_games: list[dict] | None = None) -> list[Game]:
    libraries = steam_libraries()
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
                games.append(Game(gdef.id, gdef.name, hit, gdef, source))
                break

    # Every CurseForge Minecraft instance is its own "game" with its own mods folder.
    cf_root = paths.HOME / "curseforge" / "minecraft" / "Instances"
    if cf_root.is_dir():
        mc = GAME_DEFS["minecraft"]
        for inst in sorted(p for p in cf_root.iterdir() if p.is_dir()):
            mods = inst / "mods"
            if mods.is_dir():
                slug = re.sub(r"[^a-z0-9]+", "-", inst.name.lower()).strip("-")
                games.append(Game(f"cf-{slug}", f"Minecraft - {inst.name} (CurseForge)", mods, mc, "curseforge"))

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
