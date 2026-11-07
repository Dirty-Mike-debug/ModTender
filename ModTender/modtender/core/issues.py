"""Find problems in a scanned mod folder, explain them, and describe the automatic fix (if any)."""
from __future__ import annotations

import re
import urllib.parse
from collections import defaultdict
from dataclasses import dataclass, field

from .scanner import Mod, ScanResult

CRITICAL, WARNING, INFO = "critical", "warning", "info"
SEVERITY_ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}

STRAY_HINTS = {
    ".rar": "The game can't read .rar files. Extract it, then add the mod inside.",
    ".7z": "The game can't read .7z files. Extract it, then add the mod inside.",
    ".zip": "The game can't read zipped mods. Extract it, then put the folder inside here.",
    ".txt": "A text file, usually a readme.",
    ".pdf": "A document, usually a readme.",
    ".png": "An image, probably a screenshot.",
    ".jpg": "An image, probably a screenshot.",
    ".tmp": "A leftover temporary file, often from an interrupted download.",
    ".crdownload": "An unfinished browser download. Finish or redo the download.",
    ".part": "An unfinished download. Finish or redo the download.",
}

# Order in which "Fix all" applies actions, so earlier fixes don't trip up later ones
# (e.g. remove an extra copy before renaming anything).
ACTION_ORDER = {"mkdir": 0, "quarantine_mod": 1, "dedupe": 2, "keep_newest": 3, "unpack": 4,
                "rezip": 5, "rename": 6, "quarantine_files": 7, "enable": 8, "disable": 9, "search": 10,
                "open_url": 11, "ack_game_update": 12, "deadlock_rename": 3, "deadlock_gameinfo": 13}

WORKSHOP_FIX = ("Steam manages Workshop mods, so ModTender doesn't move them. Open the item on Steam and "
                "unsubscribe to remove it, or unsubscribe and subscribe again to re-download it.")

# Search pages for mods ModTender can't find locally.
SEARCH_URLS = {
    "fs25": "https://www.farming-simulator.com/mods.php?title=fs2025&filter=latest&searchMod={q}",
    "fs22": "https://www.farming-simulator.com/mods.php?title=fs2022&filter=latest&searchMod={q}",
    "stardew": "https://www.nexusmods.com/stardewvalley/search/?gsearch={q}",
    "reforger": "https://reforger.armaplatform.com/workshop?search={q}",
}


@dataclass
class Issue:
    severity: str
    title: str
    detail: str
    fix: str  # human explanation of how to fix it
    mods: list[str] = field(default_factory=list)  # mod file names involved
    action: str = ""  # automatic fix ModTender can apply (see fixer.py); empty = manual only
    action_label: str = ""  # what the Fix button will do, in plain words
    params: dict = field(default_factory=dict)
    safe: bool = True  # included in "Fix all"

    @property
    def sort_key(self):
        return (SEVERITY_ORDER[self.severity], self.title.lower())

    @property
    def fixable(self) -> bool:
        return bool(self.action)


def _base_name(mod: Mod) -> str:
    """Normalise a mod's name so different versions of one mod match:
    'FS25_Cool-Mod_v1.2.0 (1).zip' -> 'fs25_cool_mod'."""
    stem = mod.name.rsplit(".", 1)[0] if mod.kind != "folder" else mod.name
    stem = stem.lower()
    stem = re.sub(r"\s*\(\d+\)$", "", stem)  # browser duplicate suffix " (1)"
    stem = re.sub(r"[-_ .]*v?\d+([._]\d+)+[a-z]?$", "", stem)  # trailing version
    stem = re.sub(r"[-_ .]*(copy|kopie)$", "", stem)
    return re.sub(r"[^a-z0-9]+", "_", stem).strip("_")


def version_key(text: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", text or "")[:5])


def stem(name: str) -> str:
    return name.rsplit(".", 1)[0] if "." in name else name


def fs_safe_name(name: str) -> str:
    """'FS25_Big Tractor (1).zip' -> 'FS25_Big_Tractor_1.zip' (letters, digits, underscores only)."""
    base, ext = (name.rsplit(".", 1) + [""])[:2]
    clean = re.sub(r"[^A-Za-z0-9_]+", "_", base)
    clean = re.sub(r"_+", "_", clean).strip("_") or "Mod"
    if clean[0].isdigit():
        clean = "Mod_" + clean
    return f"{clean}.{ext}" if ext else clean


def _pick_keeper(mods: list[Mod], name_rule: re.Pattern | None) -> Mod:
    """Which copy to keep among identical files: a valid name first, then the plainest name."""
    return sorted(mods, key=lambda m: (not (name_rule is None or name_rule.match(m.name)),
                                       "(" in m.name, len(m.name), m.mtime))[0]


def analyze(scan: ScanResult) -> list[Issue]:
    game = scan.game
    gdef = game.definition
    issues: list[Issue] = []
    enabled = [m for m in scan.mods if m.enabled]
    name_rule = re.compile(gdef.name_rule) if gdef.name_rule else None

    if scan.folder_missing:
        issues.append(Issue(
            WARNING, "Mod folder doesn't exist yet",
            f"ModTender expected this game's mods in:\n{game.mods_dir}",
            "Launch the game once so it creates the folder, or add the game manually with the right folder.",
            action="mkdir", action_label="Create the mods folder",
        ))

    for m in scan.mods:
        if m.corrupt and m.workshop:
            issues.append(Issue(
                CRITICAL, "Damaged or empty Workshop item", m.corrupt, WORKSHOP_FIX, [m.name],
                action="open_url", params={"url": m.workshop_url}, safe=False,
                action_label="Open this item's Steam Workshop page",
            ))
            continue
        if m.corrupt:
            issues.append(Issue(
                CRITICAL, "Damaged or unreadable mod", m.corrupt,
                "Download the mod again. Damaged mods are a common cause of crashes and failed loads.",
                [m.name], action="quarantine_mod", params={"mod": m.name},
                action_label="Move it out of the mods folder (into ModTender's quarantine folder)",
            ))
        if m.risky_files and not m.protected and m.enabled and m.workshop:
            listing = "\n".join(f"  - {f}" for f in m.risky_files[:10])
            issues.append(Issue(
                WARNING, "Workshop item contains programs or scripts",
                f"'{m.display_name}' includes files that can run code on your PC:\n{listing}",
                "Game mods rarely need these. Check the item's Workshop page and comments, and unsubscribe "
                "if you don't trust it. This doesn't mean it's malware.",
                [m.name], action="open_url", params={"url": m.workshop_url}, safe=False,
                action_label="Open this item's Steam Workshop page",
            ))
        elif m.risky_files and not m.protected and m.enabled:
            listing = "\n".join(f"  - {f}" for f in m.risky_files[:10])
            issues.append(Issue(
                WARNING, "Contains programs or scripts",
                f"This mod includes files that can run code on your PC:\n{listing}",
                "Game mods rarely need these. Only keep the mod if it came from a source you trust, "
                "and scan it with your antivirus. This doesn't mean it's malware.",
                [m.name], action="disable", params={"mods": [m.name]}, safe=False,
                action_label="Disable this mod (you can enable it again from the Mods page)",
            ))

    # Exact duplicates (same bytes, different names). Checked before naming so we drop extra copies
    # instead of renaming them.
    by_hash: dict[str, list[Mod]] = defaultdict(list)
    for m in enabled:
        if m.sha1 and not m.corrupt and not m.protected:  # never touch base-game files
            by_hash[m.sha1].append(m)
    extra_copies: set[str] = set()
    dup_names: set[str] = set()
    for group in by_hash.values():
        if len(group) > 1:
            keep = _pick_keeper(group, name_rule)
            ws = [m for m in group if m.workshop]
            if ws:
                keep = ws[0]  # Steam would re-download a removed Workshop item, so keep that one
            drop = [m.name for m in group if m is not keep and not m.workshop]
            if not drop:
                continue  # identical Workshop items only: nothing ModTender can or should change
            extra_copies.update(drop)
            dup_names.update(m.name for m in group)
            issues.append(Issue(
                WARNING, "Same mod installed more than once",
                "These files are identical:\n" + "\n".join(f"  - {m.name}" for m in group),
                "Keep one and disable the rest. Duplicates can make the game load a mod twice or pick the wrong copy.",
                [m.name for m in group], action="dedupe", params={"keep": keep.name, "keep_path": str(keep.path), "drop": drop},
                action_label=f"Keep {keep.name} and disable the other {len(drop)} cop{'y' if len(drop) == 1 else 'ies'}",
            ))

    # Different versions of the same mod
    by_key: dict[str, list[Mod]] = defaultdict(list)
    for m in enabled:
        if m.name in extra_copies or m.corrupt or m.protected:
            continue
        key = f"id:{m.mod_id.lower()}" if m.mod_id else f"name:{_base_name(m)}"
        if key not in ("name:", "id:"):
            by_key[key].append(m)
    for group in by_key.values():
        if len(group) < 2:
            continue
        newest = max(group, key=lambda m: (version_key(m.version), m.mtime))
        ws = [m for m in group if m.workshop]
        if ws:
            # A local copy alongside the Workshop version: keep the Workshop one (Steam keeps it updated).
            newest = max(ws, key=lambda m: (version_key(m.version), m.mtime))
        # Matching by the id inside the mod is reliable. Matching by file name is a guess, so outside
        # Farming Simulator (where file names are the mod's identity) it's left out of Fix all.
        by_id = all(m.mod_id for m in group)
        trusted = by_id or bool(gdef.name_rule)
        drop = [m.name for m in group if m is not newest and not m.workshop]
        label = lambda m: (f"{m.display_name} (Steam Workshop)" if m.workshop else m.name)
        lines = [f"  - {label(m)}" + (f"  (version {m.version})" if m.version else "") for m in group]
        if not drop:
            issues.append(Issue(
                WARNING, "Subscribed to the same mod twice on the Workshop",
                "These Workshop items look like the same mod:\n" + "\n".join(lines),
                "Unsubscribe from the one you don't want on Steam. Two copies of one mod usually conflict.",
                [m.name for m in group], action="open_url", params={"url": group[-1].workshop_url}, safe=False,
                action_label="Open one of them on the Steam Workshop",
            ))
            continue
        extra_ws = ("\n\nYou're also subscribed to more than one Workshop copy. Unsubscribe from the extra one on Steam."
                    if len(ws) > 1 else "")
        issues.append(Issue(
            WARNING, "Several versions of the same mod",
            "These look like copies of one mod:\n" + "\n".join(lines) + extra_ws,
            ("Keep the Steam Workshop version (Steam keeps it updated) and disable the local copies."
             if ws else "Keep the newest version and disable the others.") + " Mixed versions are a classic cause of errors.",
            [m.name for m in group], action="keep_newest",
            params={"keep": newest.name, "keep_path": str(newest.path), "drop": drop},
            safe=trusted,
            action_label=f"Keep {label(newest)}" + (f" (version {newest.version})" if newest.version else " (newest)")
                         + " and disable the other copies",
        ))

    # Farming Simulator style checks
    if name_rule:
        taken = {m.name.lower() for m in scan.mods}
        for m in enabled:
            if m.workshop or m.name in extra_copies or name_rule.match(m.name):
                continue
            new = fs_safe_name(m.name)
            n = 2
            while new.lower() in taken:
                new = fs_safe_name(f"{stem(m.name)}_{n}.{m.name.rsplit('.', 1)[-1]}")
                n += 1
            issues.append(Issue(
                CRITICAL, "The game will ignore this mod (bad file name)",
                f"'{m.name}' breaks the game's naming rule. {gdef.rule_hint}",
                f"Rename it to something like '{new}'. The game has never loaded it under its current name, "
                "so renaming it won't affect your saves.",
                [m.name], action="rename", params={"mod": m.name, "new": new},
                action_label=f"Rename it to {new}",
            ))
    if gdef.required_root_file:
        need = gdef.required_root_file.lower()
        for m in enabled:
            if m.workshop or m.kind not in ("archive", "folder") or m.corrupt or need in {f.lower() for f in m.root_files}:
                continue
            nested = [f.rsplit("/", 1)[-1] for f in m.inner_zips]
            if m.nested_root and m.kind == "archive":
                issues.append(Issue(
                    CRITICAL, f"Mod is zipped one folder too deep",
                    f"{gdef.required_root_file} is inside the folder '{m.nested_root}' instead of at the top of the zip, "
                    "so the game can't load it.",
                    "Re-zip the contents of that folder so the files sit at the top of the zip.",
                    [m.name], action="rezip", params={"mod": m.name, "inner": m.nested_root},
                    action_label="Rebuild the zip with the files at the top (the original is kept in quarantine)",
                ))
            elif nested and m.kind == "archive":
                issues.append(Issue(
                    CRITICAL, "Mod pack needs unpacking",
                    f"No {gdef.required_root_file} at the top of this zip, but it contains other mods: "
                    f"{', '.join(nested[:5])}{' …' if len(nested) > 5 else ''}.",
                    "Unzip it and put the zips inside into your mods folder.",
                    [m.name], action="unpack", params={"mod": m.name},
                    action_label=f"Extract the {len(nested)} mod(s) inside into your mods folder and quarantine the pack",
                ))
            else:
                issues.append(Issue(
                    CRITICAL, f"Missing {gdef.required_root_file}",
                    f"No {gdef.required_root_file} at the top of this mod, so the game can't load it.",
                    "The download is probably broken or isn't a mod for this game. Download it again.",
                    [m.name], action="quarantine_mod", params={"mod": m.name},
                    action_label="Move it out of the mods folder (into ModTender's quarantine folder)",
                ))

    if gdef.name_prefix:
        taken = {m.name.lower() for m in scan.mods}
        for m in enabled:
            if m.workshop or m.kind != "folder" or m.name in extra_copies or m.name.lower().startswith(gdef.name_prefix):
                continue
            new = gdef.name_prefix + m.name.replace(" ", "")
            if new.lower() in taken:
                new = f"{new}_2"
            issues.append(Issue(
                CRITICAL, "The game will ignore this mod (bad folder name)",
                f"'{m.name}' doesn't start with '{gdef.name_prefix}'. {gdef.rule_hint}",
                f"Rename the folder to '{new}'. Check the mod's instructions first: some mods ship a "
                "'dlc' folder that belongs in the game's dlc folder instead.",
                [m.name], action="rename", params={"mod": m.name, "new": new},
                action_label=f"Rename it to {new}",
            ))

    if gdef.script_conflicts:
        issues += _script_conflicts(scan, extra_copies)

    # Game-specific load-order checks
    found = []
    try:
        if gdef.id in ("skyrimse", "fallout4"):
            from .plugins import analyze_plugins
            found = analyze_plugins(gdef.id, game.mods_dir)
        elif gdef.id == "bg3":
            from .bg3 import analyze_bg3
            found = analyze_bg3(game.mods_dir)
        elif gdef.id == "cyberpunk":
            from .cyberpunk import analyze_cyberpunk
            found = analyze_cyberpunk(game.mods_dir)
        elif gdef.id == "deadlock":
            from .deadlock import analyze_deadlock
            found = analyze_deadlock(scan.mods, game.mods_dir)
        elif gdef.id == "arma3":
            from .arma import analyze_arma3
            found = analyze_arma3(scan.mods)
        elif gdef.id == "minecraft":
            from .minecraft import analyze_minecraft
            found = analyze_minecraft(scan.mods, game.mods_dir)
    except Exception as exc:  # never let one game's special check break the whole scan
        from .log import log
        log.warning("[%s] Load-order check failed: %s", game.id, exc)
    try:
        from .gamepatch import APP_IDS, check as check_game_update
        if gdef.id in APP_IDS:
            found += check_game_update(game, scan.mods)
    except Exception as exc:
        from .log import log
        log.warning("[%s] Game update check failed: %s", game.id, exc)
    try:
        from .crashlogs import latest_report, as_issue_dict
        report = latest_report(game, scan.mods)
        if report:
            found.append(as_issue_dict(report))
    except Exception as exc:
        from .log import log
        log.warning("[%s] Crash log check failed: %s", game.id, exc)
    for d in found:
        url = d.get("url", "")
        action = d.get("action") or ("open_url" if url else "")
        params = d.get("params") or ({"url": url} if url else {})
        label = d.get("action_label") or ("Open the Archive Conflict Checker on Nexus Mods" if url else "")
        issues.append(Issue(d["severity"], d["title"], d["detail"], d["fix"], d.get("mods", []),
                            action=action, params=params, safe=bool(d.get("safe", False)), action_label=label))

    try:
        from .virusscan import flagged_mods
        for m, r in flagged_mods(scan.mods):
            issues.append(Issue(
                CRITICAL, "Your antivirus flagged this mod",
                f"{r.engine or 'Your antivirus'} detected {r.threat or 'a threat'} in {m.display_name}"
                + (f" ({r.detail})" if r.detail else "") + ".\n\nIt could be a false alarm (some mod tools are "
                "flagged by mistake), but malware hidden in mods does happen.",
                "Move it to quarantine. If you trust where it came from, check the mod's page for reports first.",
                [m.name], action="quarantine_mod", params={"mod": m.name},
                action_label="Move it to ModTender's quarantine folder"))
    except Exception as exc:
        from .log import log
        log.warning("[%s] Virus scan results couldn't be read: %s", game.id, exc)

    issues += _dependency_issues(scan, extra_copies)

    strays = scan.strays
    if strays:
        lines = []
        for s in strays:
            lines.append(f"  - {s.name}: {STRAY_HINTS.get(s.suffix.lower(), 'The game does not use this file type.')}")
        issues.append(Issue(
            INFO, f"File{'s' if len(strays) > 1 else ''} the game can't use",
            "These files sit in the mods folder but the game ignores them:\n" + "\n".join(lines),
            "Move them out of the mods folder to keep things tidy.",
            [s.name for s in strays], action="quarantine_files", params={"files": [s.name for s in strays]},
            action_label=f"Move {len(strays)} file(s) to ModTender's quarantine folder",
        ))

    return sorted(issues, key=lambda i: i.sort_key)


MERGED = "mod0000_mergedfiles"
SCRIPT_MERGER_URL = "https://www.nexusmods.com/witcher3/search/?gsearch=Script%20Merger"


def _script_conflicts(scan: ScanResult, extra_copies: set[str]) -> list[Issue]:
    """The Witcher 3: when two mods ship the same script file, only one loads (the first in
    alphabetical order) unless Script Merger has combined them into mod0000_MergedFiles."""
    mods = [m for m in scan.mods if m.enabled and m.script_files and m.name not in extra_copies]
    merged = next((m for m in mods if m.name.lower() == MERGED), None)
    by_file: dict[str, list[Mod]] = defaultdict(list)
    for m in mods:
        if m is not merged:
            for path in m.script_files:
                by_file[path].append(m)

    unmerged: dict[tuple, list[str]] = defaultdict(list)  # (mods...) -> files
    stale: dict[str, list[str]] = defaultdict(list)  # mod updated after the merge -> files
    for path, group in by_file.items():
        if len(group) < 2:
            continue
        if merged and path in merged.script_files:
            merged_time = merged.script_files[path]
            for m in group:
                if m.script_files[path] > merged_time + 2:
                    stale[m.name].append(path)
            continue
        unmerged[tuple(sorted((m.name for m in group), key=str.lower))].append(path)

    issues = []
    for names, files in sorted(unmerged.items()):
        # Mods load in alphabetical order (by ASCII, so 'mod0…' and capitals come first); the first wins.
        winner = sorted(names)[0]
        shown = "\n".join(f"  - {f.replace('content/scripts/', '')}" for f in sorted(files)[:8])
        more = f"\n  …and {len(files) - 8} more" if len(files) > 8 else ""
        issues.append(Issue(
            WARNING, "Script conflict between mods",
            f"{len(names)} mods change the same script file{'s' if len(files) > 1 else ''}:\n{shown}{more}\n\n"
            f"Mods: {', '.join(names)}\n\nRight now only {winner}'s version is used, so the "
            f"other mod{'s' if len(names) > 2 else ''} may not work fully.",
            "Run Script Merger: it combines the changes into one mod (mod0000_MergedFiles). "
            "Run it again whenever you add, remove or update a script mod. "
            "If a mods.settings file sets custom priorities, the winner may differ.",
            list(names), action="open_url", params={"url": SCRIPT_MERGER_URL}, safe=False,
            action_label="Find Script Merger on Nexus Mods",
        ))
    if stale:
        lines = "\n".join(f"  - {n} ({len(f)} file{'s' if len(f) > 1 else ''})" for n, f in sorted(stale.items()))
        issues.append(Issue(
            WARNING, "Merged scripts are out of date",
            f"These mods were updated after you last ran Script Merger:\n{lines}\n\n"
            "The merged copy still has their old scripts, which can cause errors or undo the update.",
            "Open Script Merger, refresh, and merge again.",
            sorted(stale) + [merged.name], action="open_url", params={"url": SCRIPT_MERGER_URL}, safe=False,
            action_label="Find Script Merger on Nexus Mods",
        ))
    return issues


def _dependency_issues(scan: ScanResult, extra_copies: set[str]) -> list[Issue]:
    game = scan.game
    gdef = game.definition
    by_fs_name: dict[str, Mod] = {}
    by_id: dict[str, Mod] = {}
    for m in scan.mods:
        if m.name in extra_copies:
            continue
        prefer = lambda old: old is None or (m.enabled and not old.enabled)
        if prefer(by_fs_name.get(stem(m.name).lower())):
            by_fs_name[stem(m.name).lower()] = m
        if m.mod_id and prefer(by_id.get(m.mod_id.lower())):
            by_id[m.mod_id.lower()] = m

    missing: dict[str, list[str]] = defaultdict(list)  # dependency -> mods needing it
    disabled: dict[str, tuple[Mod, list[str]]] = {}
    for m in scan.mods:
        if not m.enabled or m.corrupt:
            continue
        for dep in m.dependencies:
            if dep.lower().startswith(("pdlc_", "ludeon.rimworld")):
                continue  # official DLC / the base game, not a mod
            found = by_id.get(dep.lower()) or by_fs_name.get(dep.lower())
            if found is None:
                missing[dep].append(m.name)
            elif not found.enabled:
                disabled.setdefault(dep, (found, []))[1].append(m.name)

    issues = []
    search = SEARCH_URLS.get(gdef.id)
    if not search and game.steam_appid and game.workshop_dir:
        search = f"https://steamcommunity.com/workshop/browse/?appid={game.steam_appid}&searchtext={{q}}"
    names = {m.name: m.display_name for m in scan.mods}
    dep_names = {k: v for m in scan.mods for k, v in m.dep_names.items()}
    for dep, needed_by in sorted(missing.items()):
        label = dep_names.get(dep, dep)
        if gdef.id == "reforger":
            url = f"https://reforger.armaplatform.com/workshop/{urllib.parse.quote(dep)}"
        else:
            url = search.format(q=urllib.parse.quote(label.replace("FS25_", "").replace("FS22_", "").split(".")[-1])) if search else ""
        issues.append(Issue(
            CRITICAL, "Missing required mod",
            f"'{label}' isn't installed, but these mods need it:\n" + "\n".join(f"  - {names.get(n, n)}" for n in needed_by),
            f"Download '{label}' and put it in your mods folder. Without it, the mods above won't load "
            "or will cause errors." if gdef.id != "reforger" else
            f"Download '{label}' from Arma Reforger's Workshop. Without it, the mods above won't load.",
            needed_by, action="search" if url else "", params={"url": url}, safe=False,
            action_label=f"Search online for {label}" if gdef.id != "reforger" else f"Open {label} on the Reforger Workshop",
        ))
    for dep, (mod, needed_by) in sorted(disabled.items()):
        if mod.workshop:
            continue
        issues.append(Issue(
            CRITICAL, "Required mod is disabled",
            f"'{mod.name}' is disabled, but these mods need it:\n" + "\n".join(f"  - {n}" for n in needed_by),
            "Enable it again.",
            [mod.name] + needed_by, action="enable", params={"mods": [mod.name]},
            action_label=f"Enable {mod.name}",
        ))
    return issues


def health_score(issues: list[Issue]) -> int:
    penalty = sum({CRITICAL: 20, WARNING: 6, INFO: 1}[i.severity] for i in issues)
    return max(0, 100 - penalty)


def health_label(score: int) -> str:
    if score >= 90:
        return "Healthy"
    if score >= 70:
        return "Needs attention"
    if score >= 40:
        return "Unhealthy"
    return "Critical"
