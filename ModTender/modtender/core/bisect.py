"""Find the mod behind a crash or bug by turning mods off in halves.

Round 1 turns every mod off, to check the problem is caused by mods at all. After that, each round
keeps half of the remaining suspects on, plus anything they need, and turns the rest off. The
player starts the game and says whether the problem still happens; the suspects shrink to
whichever half must contain the cause. About log2(n) rounds: 9 for 500 mods.

Progress is saved after every step (data/bisect/<game>.json), so closing ModTender mid-search
loses nothing, and "Stop" always puts every mod back the way it was."""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import paths
from .log import log


@dataclass
class Hunt:
    game_id: str
    started: str
    original_on: list[str]  # every mod that was on when the search started
    suspects: list[str]  # mods that could still be the cause
    testing_off: list[str] = field(default_factory=list)  # mods turned off for the current round
    round: int = 1
    phase: str = "mods_at_all"  # mods_at_all | narrowing | confirm | found | not_mods | stuck
    titles: dict = field(default_factory=dict)  # file name -> readable name
    needs: dict = field(default_factory=dict)  # file name -> file names it requires

    @property
    def total_rounds(self) -> int:
        """Rough number of rounds for the whole search, counting the current one."""
        steps = (math.ceil(math.log2(len(self.suspects))) if len(self.suspects) > 1 else 0) + 1  # + confirm
        return 1 + steps if self.phase == "mods_at_all" else self.round - 1 + steps

    @property
    def finished(self) -> bool:
        return self.phase in ("found", "not_mods", "stuck")

    def name(self, file: str) -> str:
        return self.titles.get(file) or file


def _state_file(game_id: str) -> Path:
    folder = paths.data_dir() / "bisect"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', game_id)}.json"


def load(game_id: str) -> Hunt | None:
    try:
        data = json.loads(_state_file(game_id).read_text(encoding="utf-8"))
        return Hunt(**data)
    except (OSError, ValueError, TypeError):
        return None


def _save(hunt: Hunt) -> None:
    _state_file(hunt.game_id).write_text(json.dumps(asdict(hunt), indent=1), encoding="utf-8")


def _forget(game_id: str) -> None:
    _state_file(game_id).unlink(missing_ok=True)


# ---------------------------------------------------------------- dependencies

def _requirements(mods: list) -> dict[str, list[str]]:
    """file name -> file names of the mods it needs (only ones that are installed)."""
    index: dict[str, str] = {}
    for m in mods:
        for key in (m.mod_id, Path(m.name).stem, m.name):
            if key:
                index.setdefault(key.lower(), m.name)
    out = {}
    for m in mods:
        wanted = list(getattr(m, "requires", []) or []) + list(m.dependencies or [])
        found = sorted({index[w.lower()] for w in wanted if w and w.lower() in index} - {m.name})
        if found:
            out[m.name] = found
    return out


def _with_needs(keep: set[str], needs: dict, pool: set[str]) -> set[str]:  # used by tests
    """keep plus everything in pool that keep needs, directly or indirectly."""
    result, todo = set(keep), list(keep)
    while todo:
        for dep in needs.get(todo.pop(), []):
            if dep in pool and dep not in result:
                result.add(dep)
                todo.append(dep)
    return result


# ---------------------------------------------------------------- the search

def start(game, mods: list) -> Hunt:
    if load(game.id):
        raise ValueError("A search is already running for this game.")
    on = [m for m in mods if m.enabled and not m.workshop and not m.protected]
    if len(on) < 2:
        raise ValueError("There need to be at least two mods turned on to search through.")
    names = sorted(m.name for m in on)
    hunt = Hunt(game.id, datetime.now().isoformat(timespec="seconds"), names, list(names),
                testing_off=list(names), titles={m.name: m.display_name for m in on},
                needs=_requirements(on))
    _apply(game, hunt)
    _save(hunt)
    log.info("[%s] Broken-mod search started with %d mods", game.id, len(names))
    return hunt


def answer(game, hunt: Hunt, still_happens: bool) -> Hunt:
    """Record the result of the current round and set up the next one."""
    off = set(hunt.testing_off)
    if hunt.phase == "confirm":  # only the suspect was off
        hunt.phase = "stuck" if still_happens else "found"
        hunt.testing_off = []
        _apply(game, hunt)
        _save(hunt)
        log.info("[%s] Broken-mod search confirm: %s", game.id, hunt.phase)
        return hunt
    if hunt.phase == "mods_at_all":
        if still_happens:  # broken even with every mod off: not a mod problem
            hunt.phase = "not_mods"
        else:
            hunt.phase = "narrowing"
    elif still_happens:  # the cause is among the mods that were on
        hunt.suspects = [s for s in hunt.suspects if s not in off]
    else:  # turning those off fixed it: the cause is among them
        hunt.suspects = [s for s in hunt.suspects if s in off]
    if hunt.phase == "narrowing":
        if len(hunt.suspects) == 1:
            hunt.phase = "confirm"  # one more round with only this mod (and mods that need it) off
            hunt.testing_off = sorted(_dependents(hunt.suspects[0], hunt.needs, set(hunt.original_on)))
            hunt.round += 1
            _apply(game, hunt)
            _save(hunt)
            return hunt
        elif not hunt.suspects:
            hunt.phase = "stuck"
        else:
            if not _next_split(hunt):
                hunt.phase = "stuck"
            hunt.round += 1
    if hunt.finished:
        hunt.testing_off = []
    _apply(game, hunt)
    _save(hunt)
    log.info("[%s] Broken-mod search round %d: %s -> %s, %d suspect(s)", game.id, hunt.round,
             "still happens" if still_happens else "fixed", hunt.phase, len(hunt.suspects))
    return hunt


def _dependents(name: str, needs: dict, pool: set[str]) -> set[str]:
    """name plus every mod in pool that needs it, directly or indirectly."""
    result, changed = {name}, True
    while changed:
        changed = False
        for mod, deps in needs.items():
            if mod in pool and mod not in result and result & set(deps):
                result.add(mod)
                changed = True
    return result


def _next_split(hunt: Hunt) -> bool:
    """Choose which mods to turn off this round. False if the suspects can't be split any further.

    Turning a mod off also turns off every mod that needs it, so nothing that's on is ever missing
    a requirement. Mods already cleared may be among those: that's fine, they can't be the cause."""
    pool = set(hunt.suspects)
    everyone = set(hunt.original_on)
    ordered = sorted(pool, key=str.lower)  # related mods (mekanism-*, ae2-*) stay together
    half = len(ordered) // 2
    options = [ordered[:half], ordered[half:]] + [[s] for s in ordered]
    best = None
    for pick in options:
        off = set()
        for s in pick:
            off |= _dependents(s, hunt.needs, everyone)
        off_suspects = len(off & pool)
        if 0 < off_suspects < len(pool):
            balance = abs(len(pool) / 2 - off_suspects)
            if best is None or balance < best[0]:
                best = (balance, off)
            if balance <= 1:
                break
    if best is None:
        return False
    hunt.testing_off = sorted(best[1])
    return True


def _apply(game, hunt: Hunt) -> None:
    """Make the mods folder match the round: every original mod on, except testing_off."""
    from .fixer import _disable, _enable
    off = set(hunt.testing_off)
    disabled = paths.disabled_dir(game.id)
    for name in hunt.original_on:
        here = (game.mods_dir / name).exists()
        if name in off and here:
            _disable(game, name)
        elif name not in off and not here and (disabled / name).exists():
            _enable(game, name)


def stop(game, hunt: Hunt | None = None, keep_off: list[str] = ()) -> list[str]:
    """End the search and put mods back as they were (except keep_off). Returns problems."""
    hunt = hunt or load(game.id)
    if hunt is None:
        return []
    hunt.testing_off = list(keep_off)
    problems = []
    try:
        _apply(game, hunt)
    except Exception as exc:  # report, but never leave the state file pointing at nothing
        problems.append(str(exc))
    still_missing = [n for n in hunt.original_on
                     if n not in keep_off and not (game.mods_dir / n).exists()]
    if still_missing:
        problems.append("Couldn't turn these back on (check the Mods page): " + ", ".join(still_missing[:10]))
    _forget(game.id)
    log.info("[%s] Broken-mod search ended, %d kept off, %d problem(s)", game.id, len(keep_off), len(problems))
    return problems
