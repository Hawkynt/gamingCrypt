"""The console's language (Wii, Wii U, GameCube): the games show their text in it.

Set on the system's page (🌐 Language) for every game of it; without a choice it's the
device's own language (LANG), where the console has it - else English. Given to the core
as its option when a game starts (retroarch.launch).
"""

from __future__ import annotations

import os

from gamingcrypt.emulation.systems import System

ENGLISH = "English"
# the core's option, and each language as the core names it
CORES: dict[str, tuple[str, dict[str, str]]] = {
    "dolphin": ("dolphin_language", {"English": "1", "Japanese": "0", "German": "2", "French": "3",
                                     "Spanish": "4", "Italian": "5", "Dutch": "6",
                                     "Simplified Chinese": "7", "Traditional Chinese": "8", "Korean": "9"}),
    "cemu": ("cemu_console_language", {name: name for name in (
        "English", "Japanese", "French", "German", "Italian", "Spanish", "Chinese", "Korean", "Dutch",
        "Portuguese", "Russian", "Taiwanese")}),
}
# the device's language (LANG=de_DE.UTF-8 …) -> the console's name for it
LOCALES = {"en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian", "nl": "Dutch",
           "ja": "Japanese", "ko": "Korean", "pt": "Portuguese", "ru": "Russian"}
CHINESE = {"zh_tw": ("Traditional Chinese", "Taiwanese"), "zh_hk": ("Traditional Chinese", "Taiwanese"),
           "zh": ("Simplified Chinese", "Chinese")}


def core_of(system: System) -> str | None:
    """The core of the system that has a console language (its first such one)."""
    return next((core for core in system.cores if core in CORES), None)


def has_language(system: System) -> bool:
    return core_of(system) is not None


def languages(system: System) -> list[str]:
    core = core_of(system)
    return list(CORES[core][1]) if core else []


def chosen(config: dict, system_id: str) -> str | None:
    value = (config.get("console_language") or {}).get(system_id)
    return value if isinstance(value, str) else None


def set_chosen(config: dict, system_id: str, language: str | None) -> None:
    table = config.setdefault("console_language", {})
    if language:
        table[system_id] = language
    else:
        table.pop(system_id, None)


def device_language(system: System, environ=None) -> str:
    """The device's language as the console has it - English when the console hasn't it."""
    environ = os.environ if environ is None else environ
    locale = (environ.get("LC_ALL") or environ.get("LC_MESSAGES") or environ.get("LANG") or "").lower()
    offered = languages(system)
    code = locale.split(".")[0].replace("-", "_")
    for prefix, names in CHINESE.items():
        if code.startswith(prefix):
            return next((n for n in names if n in offered), ENGLISH)
    name = LOCALES.get(code[:2])
    return name if name in offered else ENGLISH


def for_system(config: dict, system: System, environ=None) -> str | None:
    """What its games start with: the choice, else the device's language (None: no such option)."""
    if not has_language(system):
        return None
    choice = chosen(config, system.id)
    return choice if choice in languages(system) else device_language(system, environ)


def core_options(core: str, language: str | None) -> dict[str, str]:
    """{option: value} for the core - nothing for a core without one, or no language."""
    if core not in CORES or not language:
        return {}
    key, values = CORES[core]
    return {key: values.get(language, values[ENGLISH])}
