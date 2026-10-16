"""RetroArch cores downloaded automatically from the libretro buildbot.

A system that has games but no core gets its preferred core (the next one when that
isn't offered) - into the drive's cores/ folder, like an uploaded core. Downloads are
unzipped to a ".part" file and renamed when complete, and the same core is never
fetched twice at the same time.
"""

from __future__ import annotations

import io
import platform
import threading
import zipfile
from pathlib import Path
from typing import Callable

import requests

from gamingcrypt.emulation import retroarch
from gamingcrypt.emulation.library import EmulationPaths
from gamingcrypt.emulation.systems import System

BASE = "https://buildbot.libretro.com/nightly/linux/{arch}/latest/{core}_libretro.so.zip"
ARCHES = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}

# what a core needs in RetroArch's system folder (bios/), from the buildbot too - Dolphin's "Sys"
# (fonts, DSP, game settings), for GameCube and Wii: core -> (archive, what it unpacks to)
SYSTEM_FILES = {"dolphin": ("Dolphin.zip", "dolphin-emu/Sys")}
SYSTEM_BASE = "https://buildbot.libretro.com/assets/system/{name}"

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock(core: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(core, threading.Lock())


def url(core: str, machine: str | None = None) -> str | None:
    arch = ARCHES.get((machine or platform.machine()).lower())
    return BASE.format(arch=arch, core=core) if arch else None


def download(paths: EmulationPaths, core: str, get: Callable | None = None,
             machine: str | None = None) -> Path | None:
    """The core in cores/ (downloaded now, or already there); None: not offered or offline."""
    target = paths.cores / f"{core}_libretro.so"
    address = url(core, machine)
    if address is None:
        return None
    get = get or (lambda u: requests.get(u, timeout=120))
    with _lock(core):
        if target.exists():  # another thread was quicker
            return target
        try:
            response = get(address)
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                data = archive.read(target.name)
        except (zipfile.BadZipFile, KeyError):
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        part.write_bytes(data)
        part.replace(target)
        return target


def ensure(paths: EmulationPaths, system: System, wanted: str | None = None, get: Callable | None = None,
           machine: str | None = None) -> Path | None:
    """A core for the system: the installed one, else the first that can be downloaded."""
    found = retroarch.find_core(paths, system, wanted)
    if found is None:
        for core in ((wanted,) if wanted else ()) + tuple(c for c in system.cores if c != wanted):
            found = download(paths, core, get, machine)
            if found is not None:
                break
    if found is not None and needs_system_files(paths, found):
        download_system_files(paths, found, get)  # (tried again when a game starts)
    return found


def missing(paths: EmulationPaths, systems) -> list[System]:
    """Systems (with games) that have no core yet - or not its system files."""
    found = {s.id: retroarch.find_core(paths, s) for s in systems}
    return [s for s in systems if found[s.id] is None or needs_system_files(paths, found[s.id])]


def short_name(core: Path | str) -> str:
    return Path(core).name.removesuffix(".so").removesuffix("_libretro")


def needs_system_files(paths: EmulationPaths, core: Path | str | None) -> bool:
    """The core's system files aren't in bios/ yet."""
    wanted = SYSTEM_FILES.get(short_name(core)) if core else None
    return wanted is not None and not (paths.bios / wanted[1]).is_dir()


def download_system_files(paths: EmulationPaths, core: Path | str, get: Callable | None = None) -> Path | None:
    """The core's system files into bios/ (unpacked next to it, then moved in place) - the
    folder; None: not offered, offline, or a broken archive."""
    name = short_name(core)
    if name not in SYSTEM_FILES:
        return None
    archive_name, inside = SYSTEM_FILES[name]
    target = paths.bios / inside
    get = get or (lambda u: requests.get(u, timeout=300))
    with _lock("system:" + name):
        if target.is_dir():
            return target
        try:
            response = get(SYSTEM_BASE.format(name=archive_name))
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        part = paths.bios / (archive_name + ".part")
        import shutil

        shutil.rmtree(part, ignore_errors=True)
        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                for member in archive.infolist():
                    parts = Path(member.filename).parts
                    if not parts or member.filename.startswith("/") or ".." in parts:
                        continue  # (nothing outside its folder)
                    if not member.filename.startswith(inside.split("/")[0] + "/"):
                        continue
                    archive.extract(member, part)
        except (zipfile.BadZipFile, OSError):
            shutil.rmtree(part, ignore_errors=True)
            return None
        unpacked = part / inside
        if not unpacked.is_dir():
            shutil.rmtree(part, ignore_errors=True)
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        unpacked.replace(target)
        shutil.rmtree(part, ignore_errors=True)
        return target
