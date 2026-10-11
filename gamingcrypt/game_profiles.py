"""Per-game settings that GamingCrypt applies while the game runs (power limit, FPS limit,
emulator options …), favorites, and when Windows / Linux games were played. Stored next to the
config: game-profiles.json is the admin's, game-profiles-<user id>.json each other user's own."""

from __future__ import annotations

import json
from pathlib import Path

FPS_CHOICES = [0, 30, 40, 45, 60]  # 0 = no limit


def default_path() -> Path:
    from gamingcrypt.config import config_dir

    return config_dir() / "game-profiles.json"


def path_for(user) -> Path:
    """The file of that user (users.User; None or the admin: the one there always was)."""
    if user is None or user.admin:
        return default_path()
    return default_path().with_name(f"game-profiles-{user.id}.json")


def for_user(user) -> "GameProfiles":
    return GameProfiles(path_for(user))


class GameProfiles:
    def __init__(self, path: Path | None = None):
        self.path = path or default_path()

    def _all(self) -> dict:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def get(self, appid: int) -> dict:
        profile = self._all().get(str(int(appid)), {})
        return profile if isinstance(profile, dict) else {}

    def set(self, appid: int, key: str, value) -> None:
        data = self._all()
        profile = data.setdefault(str(int(appid)), {})
        if value in (None, 0, ""):
            profile.pop(key, None)  # back to the default
        else:
            profile[key] = value
        if not profile:
            data.pop(str(int(appid)))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        tmp.replace(self.path)

    def favorites(self) -> list[int]:
        return sorted(int(appid) for appid, profile in self._all().items()
                      if isinstance(profile, dict) and profile.get("favorite"))

    def is_favorite(self, appid: int) -> bool:
        return bool(self.get(appid).get("favorite"))
