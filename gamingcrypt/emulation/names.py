"""Which game a file is, chosen by hand - for files the automatic matching doesn't recognise
(renamed, translated or patched dumps: no cover, no genre, no year, so the filters miss them).

The choice is one of the official names libretro lists for the system ("Super Mario World (USA)");
covers (emulation/covers) and genres / years (emulation/rom_facts) are looked up by it then.
Kept on the drive: Emulation/config/names.json.
"""

from __future__ import annotations

import json

from gamingcrypt.emulation.covers import _title, wanted_regions, words
from gamingcrypt.emulation.library import EmulationPaths, RomGame


class Names:
    def __init__(self, paths: EmulationPaths):
        self.path = paths.config / "names.json"
        self._known: dict[str, str] | None = None

    @staticmethod
    def _key(game: RomGame) -> str:
        return f"{game.system.id}/{game.path.name}"

    def _load(self) -> dict[str, str]:
        if self._known is None:
            try:
                data = json.loads(self.path.read_text())
            except (OSError, ValueError):
                data = {}
            self._known = {k: v for k, v in data.items() if isinstance(v, str)} if isinstance(data, dict) else {}
        return self._known

    def get(self, game: RomGame) -> str | None:
        return self._load().get(self._key(game))

    def set(self, game: RomGame, name: str | None) -> None:
        """name None: back to the automatic matching."""
        known = self._load()
        if name:
            known[self._key(game)] = name
        else:
            known.pop(self._key(game), None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        part = self.path.with_suffix(".part")
        part.write_text(json.dumps(known, indent=1, sort_keys=True))
        part.replace(self.path)


def titles(game: RomGame, covers, facts) -> list[str] | None:
    """Every official name known for the game's system: the covers there are and the games with
    a genre or year. May ask the network (the covers' list); None: offline and nothing known."""
    names: set[str] = set()
    listed = covers.index(game) if covers is not None else None
    names.update(listed or [])
    table = facts.table(game.system.id) if facts is not None else None
    for field in ("genre", "releaseyear"):
        names.update((table or {}).get(field) or {})
    if not names and listed is None:
        return None
    return sorted(names)


def suggest(filename: str, names: list[str], text: str = "", limit: int = 60) -> list[str]:
    """The names to choose from: those with every typed word - or, with nothing typed, those that
    share a word with the file's name - the most alike first, the file's region before others."""
    own = set(words(_title(filename)))
    regions = wanted_regions(filename)
    typed = text.lower().split()

    def alike(name: str) -> tuple:
        title = set(words(_title(name)))
        tags = name[len(_title(name)):]
        region = next((len(regions) - i for i, r in enumerate(regions) if r in tags), 0)
        return -len(title & own), len(title - own), -region, name.lower()

    if typed:
        found = [n for n in names if all(word in n.lower() for word in typed)]
    else:
        found = [n for n in names if set(words(_title(n))) & own]
    return sorted(found, key=alike)[:limit]
