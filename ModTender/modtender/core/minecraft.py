"""Minecraft: mods built for the wrong mod loader or the wrong Minecraft version.

Each mod .jar says which loader it's for (fabric.mod.json, quilt.mod.json, META-INF/mods.toml,
META-INF/neoforge.mods.toml) and which Minecraft versions it supports. Forge, NeoForge and Fabric
all refuse to start when a mod's Minecraft range doesn't match, and a mod for another loader is
either ignored or crashes the game."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

LOADER_NAMES = {"fabric": "Fabric", "quilt": "Quilt", "forge": "Forge", "neoforge": "NeoForge"}


# ---------------------------------------------------------------- reading the mod's requirements

def read_fabric(meta: dict, quilt: bool) -> tuple[str, str]:
    """(loader, minecraft requirement) from fabric.mod.json / quilt.mod.json."""
    req = ""
    if quilt:
        for dep in (meta.get("quilt_loader") or {}).get("depends") or []:
            if isinstance(dep, dict) and dep.get("id") == "minecraft":
                v = dep.get("versions", "*")
                req = "fabric:" + json.dumps(v if isinstance(v, (str, list)) else "*")
    else:
        v = (meta.get("depends") or {}).get("minecraft")
        if isinstance(v, (str, list)):
            req = "fabric:" + json.dumps(v)
    return ("quilt" if quilt else "fabric"), req


def read_toml(data: dict | None, text: str, neo_file: bool) -> tuple[str, str]:
    """(loader, minecraft requirement) from mods.toml / neoforge.mods.toml."""
    deps: list[dict] = []
    if isinstance(data, dict):
        raw = data.get("dependencies") or {}
        # Usually [[dependencies.modid]] (a table of lists), but some mods write a plain [[dependencies]] list.
        blocks = raw.values() if isinstance(raw, dict) else [raw] if isinstance(raw, list) else []
        for block in blocks:
            if isinstance(block, list):
                deps += [d for d in block if isinstance(d, dict)]
            elif isinstance(block, dict):
                deps.append(block)
    else:  # couldn't parse as TOML: pick out [[dependencies.x]] blocks by hand
        for block in re.split(r"^\s*\[\[", text, flags=re.M)[1:]:
            if block.startswith("dependencies"):
                d = dict(re.findall(r'^\s*(\w+)\s*=\s*"([^"]*)"', block, re.M))
                deps.append(d)
    ids = {str(d.get("modId", "")).lower() for d in deps}
    loader = "neoforge" if neo_file or "neoforge" in ids else "forge"
    req = ""
    for d in deps:
        if str(d.get("modId", "")).lower() == "minecraft":
            rng = str(d.get("versionRange", "") or "")
            if rng and "${" not in rng:
                req = "maven:" + rng
    return loader, req


def toml_missing_loader(parsed: dict | None, text: str) -> bool:
    """Forge/NeoForge refuse to start ("Missing ModLoader in file") when mods.toml has no modLoader key."""
    if isinstance(parsed, dict):
        return not parsed.get("modLoader")
    return not re.search(r"^\s*modLoader\s*=", text, re.M)


def jar_problem(path, loader: str) -> str:
    """Why this jar won't load with the given loader ('' when it looks fine). Used before swapping in an update."""
    import zipfile
    try:
        with zipfile.ZipFile(path) as zf:
            names = {n.lower(): n for n in zf.namelist()}
            if loader in ("forge", "neoforge"):
                toml = names.get("meta-inf/neoforge.mods.toml") if loader == "neoforge" else None
                toml = toml or names.get("meta-inf/mods.toml")
                if not toml:
                    return f"the new file isn't a {LOADER_NAMES[loader]} mod"
                text = zf.read(toml).decode("utf-8", errors="ignore")
                try:
                    import tomllib
                    parsed = tomllib.loads(text)
                except Exception:
                    parsed = None
                if toml_missing_loader(parsed, text):
                    return f"the new file isn't a valid {LOADER_NAMES[loader]} mod (no modLoader in its mods.toml)"
            elif loader in ("fabric", "quilt"):
                if "fabric.mod.json" not in names and "quilt.mod.json" not in names:
                    return f"the new file isn't a {LOADER_NAMES[loader]} mod"
    except (OSError, zipfile.BadZipFile):
        return "the download isn't a valid .jar"
    return ""


PLATFORM_IDS = {"minecraft", "java", "forge", "neoforge", "fabricloader", "quilt_loader", "fml", "javafml"}


def fabric_requires(meta: dict) -> list[str]:
    """Ids of the mods a Fabric/Quilt mod needs."""
    try:
        if "quilt_loader" in meta:
            deps = (meta["quilt_loader"] or {}).get("depends") or []
            ids = [d if isinstance(d, str) else d.get("id", "") for d in deps if isinstance(d, (str, dict))]
        else:
            ids = list((meta.get("depends") or {}).keys())
    except AttributeError:
        return []
    return [i for i in ids if i and i.lower() not in PLATFORM_IDS]


def toml_requires(data) -> list[str]:
    """Ids of the mods a Forge/NeoForge mod needs (required dependencies only)."""
    if not isinstance(data, dict):
        return []
    raw = data.get("dependencies") or {}
    blocks = raw.values() if isinstance(raw, dict) else [raw] if isinstance(raw, list) else []
    out = []
    for block in blocks:
        for d in block if isinstance(block, list) else [block]:
            if not isinstance(d, dict):
                continue
            needed = str(d.get("type", "")).lower() == "required" or d.get("mandatory") is True
            mid = str(d.get("modId", ""))
            if needed and mid and mid.lower() not in PLATFORM_IDS and mid not in out:
                out.append(mid)
    return out


# ---------------------------------------------------------------- version matching

def _ver(text: str) -> tuple[int, ...] | None:
    text = text.strip().rstrip("-")
    if re.match(r"^\d{2}w\d{2}", text):
        return None  # snapshot like 23w13a: can't compare with release versions
    m = re.match(r"^(\d+(?:\.\d+)*)", text)
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def _cmp(a: tuple, b: tuple) -> int:
    n = max(len(a), len(b))
    a, b = a + (0,) * (n - len(a)), b + (0,) * (n - len(b))
    return (a > b) - (a < b)


def _maven_ok(spec: str, mc: tuple) -> bool | None:
    spec = spec.strip()
    if not spec or spec == "*":
        return True
    ranges = re.findall(r"([\[(])\s*([^,\])]*?)\s*(?:(,)\s*([^\])]*?))?\s*([\])])", spec)
    if not ranges:
        return True  # a bare version is only a recommendation in Forge's format
    for lo_b, lo, comma, hi, hi_b in ranges:
        if not comma:  # [1.20.1] = exactly that version
            v = _ver(lo)
            if v is None:
                return None
            if _cmp(mc, v) == 0:
                return True
            continue
        ok = True
        if lo:
            v = _ver(lo)
            if v is None:
                return None
            c = _cmp(mc, v)
            ok &= c > 0 or (c == 0 and lo_b == "[")
        if hi:
            v = _ver(hi)
            if v is None:
                return None
            c = _cmp(mc, v)
            ok &= c < 0 or (c == 0 and hi_b == "]")
        if ok:
            return True
    return False


def _maven_line_ok(spec: str, mc: tuple) -> bool | None:
    """Forge/NeoForge in practice load mods built for any release of the same version line
    (a mod saying [1.21,1.21.1) runs on 1.21.1), so only flag ranges that miss the whole line."""
    if len(mc) < 2:
        return _maven_ok(spec, mc)
    line_lo, line_hi = mc[:2], (mc[0], mc[1] + 1)
    spec = spec.strip()
    if not spec or spec == "*":
        return True
    ranges = re.findall(r"([\[(])\s*([^,\])]*?)\s*(?:(,)\s*([^\])]*?))?\s*([\])])", spec)
    if not ranges:
        return True
    for lo_b, lo, comma, hi, hi_b in ranges:
        lo_v = _ver(lo) if lo else None
        hi_v = _ver(hi) if hi else (lo_v if not comma else None)
        if (lo and lo_v is None) or (hi and hi_v is None):
            return None
        if hi and re.match(r"^\d+(\.\d+)*[a-zA-Z]", hi):
            hi_v = hi_v + (10 ** 9,)  # "1.21z" is a trick meaning "any 1.21.x"
        below = hi_v is not None and (_cmp(hi_v, line_lo) < 0 or (_cmp(hi_v, line_lo) == 0 and (comma and hi_b == ")")))
        above = lo_v is not None and _cmp(lo_v, line_hi) >= 0
        if not below and not above:
            return True
    return False


def _fabric_pred_ok(pred: str, mc: tuple) -> bool | None:
    m = re.match(r"^(>=|<=|>|<|=|~|\^)?\s*(.+)$", pred.strip())
    if not m:
        return None
    op, value = m.group(1) or "", m.group(2)
    if value in ("*", "x", "X"):
        return True
    wild = re.match(r"^(\d+(?:\.\d+)*)\.[xX*]$", value)
    if wild and not op:
        prefix = tuple(int(x) for x in wild.group(1).split("."))
        return mc[:len(prefix)] == prefix
    v = _ver(value.replace(".x", "").replace(".X", "").replace(".*", ""))
    if v is None:
        return None
    c = _cmp(mc, v)
    if op == ">=":
        return c >= 0
    if op == "<=":
        return c <= 0
    if op == ">":
        return c > 0
    if op == "<":
        return c < 0
    if op == "~":
        upper = (v[0], v[1] + 1) if len(v) > 1 else (v[0] + 1,)
        return c >= 0 and _cmp(mc, upper) < 0
    if op == "^":
        return c >= 0 and _cmp(mc, (v[0] + 1,)) < 0
    return c == 0


def _fabric_ok(spec, mc: tuple) -> bool | None:
    options = spec if isinstance(spec, list) else [spec]
    unsure = False
    for option in options:
        results = [_fabric_pred_ok(p, mc) for p in str(option).split()]
        if None in results:
            unsure = True
        elif all(results):
            return True
    return None if unsure else False


def supports(req: str, mc_version: str) -> bool | None:
    """Does this requirement allow mc_version? None = can't tell (snapshots, odd formats)."""
    mc = _ver(mc_version)
    if not req or mc is None:
        return True
    kind, _, spec = req.partition(":")
    if kind == "maven":
        return _maven_line_ok(spec, mc)
    try:
        return _fabric_ok(json.loads(spec), mc)
    except ValueError:
        return None


def describe(req: str) -> str:
    """A requirement in plain words, like '1.20.1' or '1.20 to 1.20.6'."""
    kind, _, spec = req.partition(":")
    if kind == "fabric":
        try:
            value = json.loads(spec)
        except ValueError:
            return spec

        def one(p: str) -> str:
            p = p.strip()
            if p.startswith(">=") and " " not in p:
                return f"{p[2:].strip()} or newer"
            if p[:1] in "~^=" and " " not in p:
                return p[1:].strip()
            return p
        return " or ".join(one(str(p)) for p in (value if isinstance(value, list) else [value]))
    out = []
    for lo_b, lo, comma, hi, hi_b in re.findall(r"([\[(])\s*([^,\])]*?)\s*(?:(,)\s*([^\])]*?))?\s*([\])])", spec):
        if not comma:
            out.append(lo)
        elif lo and hi:
            out.append(f"{lo} to {hi}" if hi_b == "]" else f"{lo} up to (not including) {hi}")
        elif lo:
            out.append(f"{lo} or newer")
        elif hi:
            out.append(f"up to {hi}")
    return " or ".join(out) or spec


# ---------------------------------------------------------------- the instance

def instance_info(mods_dir: Path) -> tuple[str, str]:
    """(loader, Minecraft version) for a CurseForge instance; ('', '') when unknown."""
    try:
        data = json.loads((mods_dir.parent / "minecraftinstance.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return "", ""
    base = data.get("baseModLoader") or {}
    loader = str(base.get("name", "")).split("-")[0].lower()
    version = str(base.get("minecraftVersion") or data.get("gameVersion") or "")
    return (loader if loader in LOADER_NAMES else ""), version


def _compatible(instance: str, mc_version: str, mod_loaders: list[str], has_connector: bool) -> bool:
    ok = {instance}
    if instance == "quilt":
        ok.add("fabric")
    if instance == "neoforge":
        if mc_version.startswith("1.20.1"):
            ok.add("forge")  # NeoForge for 1.20.1 still loads Forge mods
        if has_connector:
            ok.add("fabric")  # Sinytra Connector runs Fabric mods on NeoForge
    if instance == "forge" and has_connector:
        ok.add("fabric")
    return bool(ok & set(mod_loaders))


def analyze_minecraft(mods: list, mods_dir: Path) -> list[dict]:
    active = [m for m in mods if m.enabled and m.loaders]
    if not active:
        return []
    loader, mc_version = instance_info(mods_dir)
    guessed = False
    if not loader:
        counts = Counter(l for m in active for l in set(m.loaders))
        top, n = counts.most_common(1)[0]
        if len(active) < 5 or n < 0.75 * len(active):
            return []  # too mixed to tell which loader this folder is meant for
        loader, guessed = top, True
    ids = {m.mod_id.lower() for m in active}
    connector = "connector" in ids
    name = LOADER_NAMES[loader]
    out = []

    wrong = [m for m in active if not _compatible(loader, mc_version, m.loaders, connector)]
    if wrong:
        lines = "\n".join(f"  - {m.display_name} ({' / '.join(LOADER_NAMES[l] for l in m.loaders)})"
                          for m in sorted(wrong, key=lambda m: m.display_name.lower())[:40])
        more = f"\n  ...and {len(wrong) - 40} more" if len(wrong) > 40 else ""
        where = f"Most of the mods here are for {name}" if guessed else f"This instance runs {name}"
        out.append({
            "severity": "warning" if guessed else "critical",
            "title": f"Mod{'s' if len(wrong) > 1 else ''} made for a different mod loader",
            "detail": f"{where}, but {'these are' if len(wrong) > 1 else 'this one is'} made for another "
                      f"loader. {name} can't load {'them' if len(wrong) > 1 else 'it'}, so the game either "
                      f"ignores {'them' if len(wrong) > 1 else 'it'} or won't start:\n{lines}{more}",
            "fix": f"Download the {name} version of each mod (most mod pages have one), or turn it off.",
            "mods": [m.name for m in wrong],
            "action": "disable", "params": {"mods": [m.name for m in wrong]},
            "action_label": f"Turn off {len(wrong)} mod{'s' if len(wrong) > 1 else ''} "
                            f"(you can turn {'them' if len(wrong) > 1 else 'it'} back on)",
        })

    if mc_version:
        skip = {m.name for m in wrong}
        bad = []
        for m in active:
            if m.name in skip:
                continue
            req = m.mc_req.get(loader) or next((m.mc_req[l] for l in m.loaders if l in m.mc_req), "")
            if req and supports(req, mc_version) is False:
                bad.append((m, req))
        if bad:
            lines = "\n".join(f"  - {m.display_name}: needs Minecraft {describe(r)}"
                              for m, r in sorted(bad, key=lambda b: b[0].display_name.lower())[:40])
            more = f"\n  ...and {len(bad) - 40} more" if len(bad) > 40 else ""
            out.append({
                "severity": "critical",
                "title": f"Mod{'s' if len(bad) > 1 else ''} made for a different Minecraft version",
                "detail": f"This instance is Minecraft {mc_version}, but "
                          f"{'these mods are' if len(bad) > 1 else 'this mod is'} built for "
                          f"another Minecraft version. {name} will refuse to start with "
                          f"{'them' if len(bad) > 1 else 'it'} installed:\n{lines}{more}",
                "fix": f"Download the version of each mod built for Minecraft {mc_version}, or turn it off.",
                "mods": [m.name for m, _ in bad],
                "action": "disable", "params": {"mods": [m.name for m, _ in bad]},
                "action_label": f"Turn off {len(bad)} mod{'s' if len(bad) > 1 else ''} "
                            f"(you can turn {'them' if len(bad) > 1 else 'it'} back on)",
            })
    return out
