"""Plain-text diagnostic report, easy to paste into a forum post or Discord."""
from __future__ import annotations

import platform

from .. import __version__
from .issues import Issue, health_label, health_score
from .scanner import ScanResult


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def build_report(scan: ScanResult, issues: list[Issue]) -> str:
    score = health_score(issues)
    enabled = [m for m in scan.mods if m.enabled]
    lines = [
        f"ModTender {__version__} diagnostic report",
        "=" * 44,
        f"Game:        {scan.game.name}",
        f"Mod folder:  {scan.game.mods_dir}",
        f"Scanned:     {scan.scanned_at:%Y-%m-%d %H:%M}",
        f"System:      {platform.system()} {platform.release()}",
        f"Health:      {score}/100 ({health_label(score)})",
        f"Mods:        {len(enabled)} enabled, {len(scan.mods) - len(enabled)} disabled, "
        f"{human_size(sum(m.size for m in enabled))} total",
        "",
        f"ISSUES ({len(issues)})",
        "-" * 44,
    ]
    if not issues:
        lines.append("No problems found.")
    for n, issue in enumerate(issues, 1):
        lines += [f"{n}. [{issue.severity.upper()}] {issue.title}"]
        lines += [f"   {line}" for line in issue.detail.splitlines()]
        lines += [f"   Fix: {issue.fix}", ""]
    lines += ["", "ENABLED MODS", "-" * 44]
    for m in sorted(enabled, key=lambda m: m.name.lower()):
        ver = f" v{m.version}" if m.version else ""
        lines.append(f"{m.name}{ver}  ({human_size(m.size)})")
    disabled = [m for m in scan.mods if not m.enabled]
    if disabled:
        lines += ["", "DISABLED MODS", "-" * 44] + [m.name for m in disabled]
    return "\n".join(lines) + "\n"
