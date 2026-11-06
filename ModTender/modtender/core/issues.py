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
                "rezip": 5, "rename": 6, "quarantine_files": 7, "enable": 8, "disable": 9, "search": 10}

# Search pages for mods ModTender can't find locally.
SEARCH_URLS = {
    "fs25": "https://www.farming-simulator.com/mods.php?title=fs2025&filter=latest&searchMod={q}",
    "fs22": "https://www.farming-simulator.com/mods.php?title=fs2022&filter=latest&searchMod={q}",
    "stardew": "https://www.nexusmods.com/stardewvalley/search/?gsearch={q}",
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
        if m.corrupt:
            issues.append(Issue(
                CRITICAL, "Damaged or unreadable mod", m.corrupt,
                "Download the mod again. Damaged mods are a common cause of crashes and failed loads.",
                [m.name], action="quarantine_mod", params={"mod": m.name},
                action_label="Move it out of the mods folder (into ModTender's quarantine folder)",
            ))
        if m.risky_files and not m.protected and m.enabled:
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
        if m.sha1 and not m.corrupt:
            by_hash[m.sha1].append(m)
    extra_copies: set[str] = set()
    dup_names: set[str] = set()
    for group in by_hash.values():
        if len(group) > 1:
            keep = _pick_keeper(group, name_rule)
            drop = [m.name for m in group if m is not keep]
            extra_copies.update(drop)
            dup_names.update(m.name for m in group)
            issues.append(Issue(
                WARNING, "Same mod installed more than once",
                "These files are identical:\n" + "\n".join(f"  - {m.name}" for m in group),
                "Keep one and disable the rest. Duplicates can make the game load a mod twice or pick the wrong copy.",
                [m.name for m in group], action="dedupe", params={"keep": keep.name, "drop": drop},
                action_label=f"Keep {keep.name} and disable the other {len(drop)} cop{'y' if len(drop) == 1 else 'ies'}",
            ))

    # Different versions of the same mod
    by_key: dict[str, list[Mod]] = defaultdict(list)
    for m in enabled:
        if m.name in extra_copies or m.corrupt:
            continue
        key = f"id:{m.mod_id.lower()}" if m.mod_id else f"name:{_base_name(m)}"
        if key not in ("name:", "id:"):
            by_key[key].append(m)
    for group in by_key.values():
        if len(group) < 2:
            continue
        newest = max(group, key=lambda m: (version_key(m.version), m.mtime))
        drop = [m.name for m in group if m is not newest]
        lines = [f"  - {m.name}" + (f"  (version {m.version})" if m.version else "") for m in group]
        issues.append(Issue(
            WARNING, "Several versions of the same mod",
            "These look like copies of one mod:\n" + "\n".join(lines),
            "Keep the newest version and disable the others. Mixed versions are a classic cause of errors.",
            [m.name for m in group], action="keep_newest", params={"keep": newest.name, "drop": drop},
            action_label=f"Keep {newest.name}" + (f" (version {newest.version})" if newest.version else " (newest)")
                         + " and disable the others",
        ))

    # Farming Simulator style checks
    if name_rule:
        taken = {m.name.lower() for m in scan.mods}
        for m in enabled:
            if m.name in extra_copies or name_rule.match(m.name):
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
            if m.kind not in ("archive", "folder") or m.corrupt or need in {f.lower() for f in m.root_files}:
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
            if dep.lower().startswith("pdlc_"):
                continue  # official DLC, not a mod file
            found = by_id.get(dep.lower()) or by_fs_name.get(dep.lower())
            if found is None:
                missing[dep].append(m.name)
            elif not found.enabled:
                disabled.setdefault(dep, (found, []))[1].append(m.name)

    issues = []
    search = SEARCH_URLS.get(gdef.id)
    for dep, needed_by in sorted(missing.items()):
        url = search.format(q=urllib.parse.quote(dep.replace("FS25_", "").replace("FS22_", ""))) if search else ""
        issues.append(Issue(
            CRITICAL, "Missing required mod",
            f"'{dep}' isn't installed, but these mods need it:\n" + "\n".join(f"  - {n}" for n in needed_by),
            f"Download '{dep}' and put it in your mods folder. Without it, the mods above won't load "
            "or will cause errors.",
            needed_by, action="search" if url else "", params={"url": url}, safe=False,
            action_label=f"Search online for {dep}" if url else "",
        ))
    for dep, (mod, needed_by) in sorted(disabled.items()):
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
