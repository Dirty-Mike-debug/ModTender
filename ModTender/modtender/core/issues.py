"""Find problems in a scanned mod folder and explain how to fix them."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from .scanner import Mod, ScanResult

CRITICAL, WARNING, INFO = "critical", "warning", "info"
SEVERITY_ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}

STRAY_HINTS = {
    ".rar": "The game can't read .rar files. Extract it, then add the mod inside.",
    ".7z": "The game can't read .7z files. Extract it, then add the mod inside.",
    ".txt": "A text file, usually a readme. Safe to delete or move elsewhere.",
    ".pdf": "A document, usually a readme. Safe to move elsewhere.",
    ".png": "An image, probably a screenshot. Safe to move elsewhere.",
    ".jpg": "An image, probably a screenshot. Safe to move elsewhere.",
    ".tmp": "A leftover temporary file, often from an interrupted download.",
    ".crdownload": "An unfinished browser download. Finish or redo the download.",
    ".part": "An unfinished download. Finish or redo the download.",
}


@dataclass
class Issue:
    severity: str
    title: str
    detail: str
    fix: str
    mods: list[str] = field(default_factory=list)  # mod file names involved

    @property
    def sort_key(self):
        return (SEVERITY_ORDER[self.severity], self.title.lower())


def _base_name(mod: Mod) -> str:
    """Normalise a mod's name so different versions of one mod match:
    'FS25_Cool-Mod_v1.2.0 (1).zip' -> 'fs25_cool_mod'."""
    stem = mod.name.rsplit(".", 1)[0] if mod.kind != "folder" else mod.name
    stem = stem.lower()
    stem = re.sub(r"\s*\(\d+\)$", "", stem)  # browser duplicate suffix " (1)"
    stem = re.sub(r"[-_ .]*v?\d+([._]\d+)+[a-z]?$", "", stem)  # trailing version
    stem = re.sub(r"[-_ .]*(copy|kopie)$", "", stem)
    return re.sub(r"[^a-z0-9]+", "_", stem).strip("_")


def analyze(scan: ScanResult) -> list[Issue]:
    gdef = scan.game.definition
    issues: list[Issue] = []
    enabled = [m for m in scan.mods if m.enabled]

    if scan.folder_missing:
        issues.append(Issue(
            WARNING, "Mod folder doesn't exist yet",
            f"ModTender expected this game's mods in:\n{scan.game.mods_dir}",
            "Launch the game once so it creates the folder, or add the game manually with the right folder.",
        ))

    for m in scan.mods:
        if m.corrupt:
            issues.append(Issue(
                CRITICAL, "Damaged or unreadable mod", m.corrupt,
                "Delete this file and download the mod again. Damaged mods are a common cause of crashes and failed loads.",
                [m.name],
            ))
        if m.risky_files and not m.protected:
            listing = "\n".join(f"  - {f}" for f in m.risky_files[:10])
            issues.append(Issue(
                WARNING, "Contains programs or scripts",
                f"This mod includes files that can run code on your PC:\n{listing}",
                "Game mods rarely need these. Only keep the mod if it came from a source you trust, "
                "and scan it with your antivirus. This doesn't mean it's malware.",
                [m.name],
            ))

    # Farming Simulator style checks
    if gdef.name_rule:
        rule = re.compile(gdef.name_rule)
        for m in enabled:
            if not rule.match(m.name):
                issues.append(Issue(
                    CRITICAL, "The game will ignore this mod (bad file name)",
                    f"'{m.name}' breaks the game's naming rule. {gdef.rule_hint}",
                    "Rename it, e.g. remove spaces, brackets like ' (1)' and dashes. "
                    "Renaming can break existing saves that use the mod, so check before you rename a mod you already use.",
                    [m.name],
                ))
    if gdef.required_root_file:
        need = gdef.required_root_file.lower()
        for m in enabled:
            if m.kind in ("archive", "folder") and not m.corrupt and need not in {f.lower() for f in m.root_files}:
                nested = [f for f in m.root_files if f.lower().endswith(".zip")]
                if nested:
                    detail = f"No {gdef.required_root_file} at the top of this mod, but it contains other zips ({', '.join(nested[:4])}). It's probably a mod pack."
                    fix = "Unzip it and put the zips inside into your mods folder."
                else:
                    detail = f"No {gdef.required_root_file} at the top of this mod, so the game can't load it."
                    fix = "It was probably zipped one folder too deep. Re-zip the contents, or download the mod again."
                issues.append(Issue(CRITICAL, f"Missing {gdef.required_root_file}", detail, fix, [m.name]))

    # Exact duplicates (same bytes, different names)
    by_hash: dict[str, list[Mod]] = defaultdict(list)
    for m in enabled:
        if m.sha1:
            by_hash[m.sha1].append(m)
    dup_names: set[str] = set()
    for group in by_hash.values():
        if len(group) > 1:
            names = [m.name for m in group]
            dup_names.update(names)
            issues.append(Issue(
                WARNING, "Same mod installed more than once",
                "These files are identical:\n" + "\n".join(f"  - {n}" for n in names),
                "Keep one and disable the rest. Duplicates can make the game load a mod twice or pick the wrong copy.",
                names,
            ))

    # Different versions of the same mod
    by_key: dict[str, list[Mod]] = defaultdict(list)
    for m in enabled:
        key = f"id:{m.mod_id.lower()}" if m.mod_id else f"name:{_base_name(m)}"
        if key not in ("name:", "id:"):
            by_key[key].append(m)
    for group in by_key.values():
        names = [m.name for m in group]
        if len(group) > 1 and not set(names) <= dup_names:
            lines = [f"  - {m.name}" + (f"  (version {m.version})" if m.version else "") for m in group]
            issues.append(Issue(
                WARNING, "Several versions of the same mod",
                "These look like copies of one mod:\n" + "\n".join(lines),
                "Keep the newest version and disable the others. Mixed versions are a classic cause of errors.",
                names,
            ))

    for stray in scan.strays:
        hint = STRAY_HINTS.get(stray.suffix.lower(), "The game doesn't use this file type, so it's ignored.")
        issues.append(Issue(INFO, "File the game can't use", f"'{stray.name}': {hint}",
                            "Move it out of the mods folder to keep things tidy.", [stray.name]))

    return sorted(issues, key=lambda i: i.sort_key)


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
