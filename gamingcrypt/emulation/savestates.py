"""Save states of RetroArch games: nine slots, each with a picture of the moment it was saved.

RetroArch names a state after the game ("Game.state", "Game.state1" …) and writes its picture
next to it ("Game.state1.png"). It can load any slot (LOAD_STATE_SLOT), but saves only into
"the current one" - which GamingCrypt doesn't know. So a save goes: put the kept states aside,
let RetroArch save, and move what it wrote into the slot that was picked.
"""

from __future__ import annotations

import glob
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from gamingcrypt.emulation.library import EmulationPaths, RomGame

SLOTS = 9
SPARE = 99  # not one of the nine: the state a game comes back with after its speed was changed
SPARE_KEPT_S = 120
ASIDE = ".keep"  # a kept state while RetroArch saves


@dataclass
class State:
    slot: int
    path: Path | None = None
    picture: Path | None = None  # None: saved before there were pictures
    saved_at: float = 0.0

    @property
    def empty(self) -> bool:
        return self.path is None


def state_file(paths: EmulationPaths, game: RomGame, slot: int) -> Path:
    return paths.states / f"{game.path.stem}.state{slot or ''}"


def picture_of(state: Path) -> Path:
    return state.with_name(state.name + ".png")


def load_command(slot: int) -> str:
    return f"LOAD_STATE_SLOT {slot}"


def _age(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _written(paths: EmulationPaths, game: RomGame) -> list[tuple[Path, int]]:
    """(file, slot) of every state RetroArch wrote for the game - also in a folder per core
    below states/ (RetroArch's own "sort save states" setting, before GamingCrypt switched it off)."""
    name = re.compile(re.escape(game.path.stem) + r"\.state(\d*)$")
    try:
        files = [f for f in paths.states.rglob(glob.escape(game.path.stem) + ".state*") if f.is_file()]
    except OSError:
        return []
    return sorted((f, int(m.group(1) or 0)) for f in files if (m := name.match(f.name)))


def _move(state: Path, target: Path) -> None:
    """The state and its picture - a picture of what was there before must not stay."""
    os.replace(state, target)
    if picture_of(state).is_file():
        os.replace(picture_of(state), picture_of(target))
    else:
        picture_of(target).unlink(missing_ok=True)


def _delete(state: Path) -> None:
    for f in (state, picture_of(state)):
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass


def _put_aside(paths: EmulationPaths, game: RomGame) -> None:
    for state, _slot in _written(paths, game):
        for f in (state, picture_of(state)):
            if f.is_file():
                os.replace(f, f.with_name(f.name + ASIDE))


def _put_back(paths: EmulationPaths, game: RomGame) -> None:
    """The kept states again - except where a new one was saved meanwhile. Also after a crash
    in the middle of a save."""
    try:
        aside = [f for f in paths.states.rglob(glob.escape(game.path.stem) + ".state*" + ASIDE) if f.is_file()]
    except OSError:
        return
    back: set[Path] = set()
    for f in sorted(aside):  # "Game.state1.keep" before "Game.state1.png.keep"
        target = f.with_name(f.name[: -len(ASIDE)])
        picture = target.name.endswith(".png")
        state = target.with_name(target.name[: -len(".png")]) if picture else target
        try:
            if target.exists() or (picture and state.exists() and state not in back):
                f.unlink()  # replaced by a new save (a picture: with its state)
            else:
                os.replace(f, target)
                back.add(target)
        except OSError:
            pass


def tidy(paths: EmulationPaths, game: RomGame, clock: Callable[[], float] = time.time) -> None:
    """The nine newest states, in the slots 0-8 right in states/; the others are deleted.
    (More than nine, other slots, a folder per core: from before the nine slots.)"""
    _put_back(paths, game)
    found = []
    for state, slot in _written(paths, game):
        if slot == SPARE:
            if clock() - _age(state) > SPARE_KEPT_S:
                _delete(state)
            continue
        found.append((state, slot))
    found.sort(key=lambda item: _age(item[0]), reverse=True)
    for state, _slot in found[SLOTS:]:
        _delete(state)
    kept = sorted(found[:SLOTS], key=lambda item: item[1])
    home = {slot for state, slot in kept if slot < SLOTS and state == state_file(paths, game, slot)}
    free = [slot for slot in range(SLOTS) if slot not in home]
    for state, slot in kept:
        if slot in home and state == state_file(paths, game, slot):
            continue
        try:
            _move(state, state_file(paths, game, free.pop(0)))
        except OSError:
            pass


def slots(paths: EmulationPaths, game: RomGame) -> list[State]:
    """The nine slots, in order - tidied up first."""
    tidy(paths, game)
    found = []
    for slot in range(SLOTS):
        state = state_file(paths, game, slot)
        if state.is_file():
            picture = picture_of(state)
            found.append(State(slot, state, picture if picture.is_file() else None, _age(state)))
        else:
            found.append(State(slot))
    return found


def _wait_for_state(paths: EmulationPaths, game: RomGame, timeout: float, sleep, clock) -> Path | None:
    """What RetroArch saved, once it's written completely (the same size twice) - and its picture,
    which may take a moment longer."""
    deadline = clock() + timeout
    seen: tuple[Path, int] | None = None
    state = None
    while state is None and clock() < deadline:
        sleep(0.15)
        written = _written(paths, game)
        if written:
            now = (written[0][0], _size(written[0][0]))
            if now[1] and now == seen:
                state = now[0]
            seen = now
    if state is None:
        return None
    deadline, size = clock() + 3, -1
    while clock() < deadline:
        now = _size(picture_of(state))
        if now and now == size:
            break
        size = now
        sleep(0.15)
    return state


def capture(paths: EmulationPaths, game: RomGame, slot: int, send: Callable[[str], bool], timeout: float = 15.0,
            sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> bool:
    """Save the running game into the slot. False: RetroArch wrote nothing (a core without save
    states) - what was in the slot is still there then."""
    tidy(paths, game)
    _delete(state_file(paths, game, SPARE))
    _put_aside(paths, game)
    try:
        if not send("SAVE_STATE"):
            return False
        state = _wait_for_state(paths, game, timeout, sleep, clock)
        if state is None:
            return False
        target = state_file(paths, game, slot)
        if state != target:
            _move(state, target)
        return True
    except OSError:
        return False
    finally:
        _put_back(paths, game)


def rescue(paths: EmulationPaths, game: RomGame) -> int | None:
    """The spare state into a free slot (the game didn't come back with it by itself) - the slot,
    None when all nine are taken or there's no spare one."""
    spare = state_file(paths, game, SPARE)
    free = next((s.slot for s in slots(paths, game) if s.empty), None)
    if free is None or not spare.is_file():
        return None
    try:
        _move(spare, state_file(paths, game, free))
    except OSError:
        return None
    return free
