"""The people using the device: an admin - always there, called "admin" until renamed - and
the users the admin adds.

* Each has a code of their own (PIN, password, pattern …); every one of them unlocks the same
  volume (unlock/keyslots.py). The admin's code is the volume's own, exactly as before there
  were users - a config from before is simply "one admin".
* The admin manages the users, and is the only one who can delete games.
* A user can have an age: games rated for older ones aren't shown to them (ratings.py).
* Steam settings and emulator saves are each user's own (see steam_settings(), and
  emulation/library.EmulationPaths).

In config.json: "users" (a list: id, name, method, slot, age, steam), "admin" (name),
"unlock"."keyring" (the vault and the admin's slot, once there are users). Who is using the
device right now is "session"."user" - only in memory, never written.
"""

from __future__ import annotations

import copy
import re
import secrets as token_source
from dataclasses import dataclass

from gamingcrypt.unlock import kdf, keyslots
from gamingcrypt.unlock.secrets import METHODS

ADMIN = "admin"
MAX_NAME = 24
AGES = (0, 6, 12, 16, 18)  # the steps of the German ratings (FSK / USK)
LOCKABLE = ("Movies", "Shows", "Music", "Pictures")  # tabs the admin can lock for a user


class UserError(ValueError):
    pass


@dataclass(frozen=True)
class User:
    id: str
    name: str
    method: str
    admin: bool = False
    age: int | None = None  # None: no limit
    locked: tuple[str, ...] = ()  # tabs this user doesn't get (LOCKABLE)

    @property
    def can_delete_games(self) -> bool:
        return self.admin


def _records(config: dict) -> list[dict]:
    found = config.get("users")
    return [u for u in found if isinstance(u, dict) and u.get("id") and u.get("id") != ADMIN] \
        if isinstance(found, list) else []


def admin(config: dict) -> User:
    name = str((config.get("admin") or {}).get("name") or ADMIN)
    return User(ADMIN, name, config.get("unlock", {}).get("method", ""), admin=True)


def all_users(config: dict) -> list[User]:
    """The admin first, then the others as they were added."""
    found = [admin(config)]
    for record in _records(config):
        age = record.get("age")
        found.append(User(str(record["id"]), str(record.get("name") or record["id"]),
                          record.get("method") if record.get("method") in METHODS else "password",
                          age=int(age) if isinstance(age, int) and not isinstance(age, bool) else None,
                          locked=tuple(t for t in LOCKABLE if t in (record.get("locked") or ()))))
    return found


def get(config: dict, user_id: str | None) -> User:
    """That user - the admin for an id that isn't there (any more)."""
    return next((u for u in all_users(config) if u.id == user_id), admin(config))


def current(config: dict) -> User:
    return get(config, (config.get("session") or {}).get("user"))


def set_current(config: dict, user_id: str | None) -> User:
    user = get(config, user_id)
    config["session"] = {"user": user.id}
    return user


def _record(config: dict, user_id: str) -> dict:
    record = next((u for u in _records(config) if u["id"] == user_id), None)
    if record is None:
        raise UserError("No such user")
    return record


def check_name(config: dict, name: str, user_id: str | None = None) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        raise UserError("The name can't be empty")
    if len(name) > MAX_NAME:
        raise UserError(f"The name can have {MAX_NAME} characters at most")
    if any(u.name.lower() == name.lower() and u.id != user_id for u in all_users(config)):
        raise UserError(f"There's already a user called {name}")
    return name


def rename(config: dict, user_id: str, name: str) -> str:
    name = check_name(config, name, user_id)
    if user_id == ADMIN:
        config.setdefault("admin", {})["name"] = name
    else:
        _record(config, user_id)["name"] = name
    return name


def set_age(config: dict, user_id: str, age: int | None) -> None:
    if user_id == ADMIN:
        raise UserError("The admin has no age limit")
    _record(config, user_id)["age"] = None if age is None else max(0, int(age))


def set_locked(config: dict, user_id: str, tab: str, locked: bool) -> None:
    """Movies, Shows, Music or Pictures: not for this user (or again)."""
    if user_id == ADMIN:
        raise UserError("Nothing is locked for the admin")
    if tab not in LOCKABLE:
        raise UserError(f"{tab} can't be locked")
    record = _record(config, user_id)
    now = [t for t in LOCKABLE if (t in (record.get("locked") or ()) and t != tab) or (t == tab and locked)]
    record["locked"] = now


# --- codes -----------------------------------------------------------------------------------

def admin_master(config: dict, admin_secret: str, verify=None) -> bytes:
    """The master key, by the admin's code. The first time (no users yet) it's made: then
    ``verify(secret) -> bool`` has to say that the code is right - there's nothing here to check
    it against, and a wrong one would lock every new user out.
    Raises UserError: wrong code."""
    unlock = config["unlock"]
    keyring = unlock.get("keyring")
    if isinstance(keyring, dict) and keyring.get("admin"):
        master = keyslots.open_slot(admin_secret, keyring.get("admin"))
        if master is None:
            raise UserError("That's not the admin's code")
        return master
    if verify is None or not verify(admin_secret):
        raise UserError("That's not the admin's code" if verify is not None
                        else "Lock the drive and unlock it once as admin, then try again")
    try:
        password = kdf.derive_password(admin_secret, unlock.get("kdf"))
    except kdf.KDFError as exc:
        raise UserError(str(exc)) from exc
    master = keyslots.new_master()
    unlock["keyring"] = {"vault": keyslots.new_vault(master, password),
                         "admin": keyslots.new_slot(admin_secret, master, _like(unlock.get("kdf")))}
    return master


def _like(params: dict | None) -> dict:
    """Fresh scrypt parameters as costly as the volume's own (a new salt)."""
    if not params:
        return kdf.new_params()
    return kdf.new_params(int(params.get("n", kdf.DEFAULT_N)), int(params.get("r", kdf.DEFAULT_R)),
                          int(params.get("p", kdf.DEFAULT_P)))


def add(config: dict, name: str, method: str, secret: str, master: bytes, age: int | None = None) -> User:
    name = check_name(config, name)
    if method not in METHODS:
        raise UserError("Unknown unlock method")
    taken = {u.id for u in all_users(config)}
    user_id = next(i for i in iter(lambda: "u" + token_source.token_hex(3), None) if i not in taken)
    record = {"id": user_id, "name": name, "method": method, "age": None,
              "slot": keyslots.new_slot(secret, master, _like(config["unlock"].get("kdf")))}
    if not isinstance(config.get("users"), list):
        config["users"] = []
    config["users"].append(record)
    if age is not None:
        set_age(config, user_id, age)
    return get(config, user_id)


def remove(config: dict, user_id: str) -> None:
    if user_id == ADMIN:
        raise UserError("The admin can't be deleted")
    record = _record(config, user_id)
    config["users"].remove(record)
    if (config.get("session") or {}).get("user") == user_id:
        config["session"] = {"user": ADMIN}


def user_master(config: dict, user_id: str, secret: str) -> bytes | None:
    """The master key by a user's own code - None: wrong code."""
    if user_id == ADMIN:
        keyring = config["unlock"].get("keyring")
        return keyslots.open_slot(secret, keyring.get("admin")) if isinstance(keyring, dict) else None
    try:
        return keyslots.open_slot(secret, _record(config, user_id).get("slot"))
    except UserError:
        return None


def set_code(config: dict, user_id: str, method: str, secret: str, master: bytes) -> None:
    """A new code for a user (not the admin: theirs is the volume's - Settings -> Security)."""
    if method not in METHODS:
        raise UserError("Unknown unlock method")
    record = _record(config, user_id)
    record["method"] = method
    record["slot"] = keyslots.new_slot(secret, master, _like(config["unlock"].get("kdf")))


def volume_password(config: dict, user_id: str, secret: str) -> str | None:
    """What VeraCrypt gets for this user's code - None: wrong code.
    (The admin's isn't checked here: VeraCrypt says whether it's right.)"""
    unlock = config["unlock"]
    if user_id == ADMIN or not any(u["id"] == user_id for u in _records(config)):
        return kdf.derive_password(secret, unlock.get("kdf"))
    master = user_master(config, user_id, secret)
    keyring = unlock.get("keyring")
    if master is None or not isinstance(keyring, dict):
        return None
    return keyslots.open_vault(master, keyring.get("vault"))


def admin_code_changed(config: dict, old_secret: str, new_secret: str) -> bool:
    """The admin's code - and with it the volume's password - changed (``unlock.kdf`` is the
    new one already): the vault and the admin's slot anew, so the others' codes still work.
    False: they don't any more (the master key couldn't be had) - each needs a new code."""
    unlock = config["unlock"]
    keyring = unlock.get("keyring")
    if not isinstance(keyring, dict):
        return True  # no users with codes
    master = keyslots.open_slot(old_secret, keyring.get("admin"))
    if master is None:
        forget_codes(config)
        return False
    unlock["keyring"] = {"vault": keyslots.new_vault(master, kdf.derive_password(new_secret, unlock.get("kdf"))),
                         "admin": keyslots.new_slot(new_secret, master, _like(unlock.get("kdf")))}
    return True


def forget_codes(config: dict) -> None:
    """Another volume, or a password set without the old one: the users stay, their codes don't
    open anything any more - the admin gives each a new one."""
    config["unlock"].pop("keyring", None)
    for record in _records(config):
        record.pop("slot", None)


def has_code(config: dict, user_id: str) -> bool:
    """Can this user unlock? (The admin always; another one once they have a code that fits.)"""
    if user_id == ADMIN:
        return True
    try:
        return isinstance(_record(config, user_id).get("slot"), dict) \
            and isinstance(config["unlock"].get("keyring"), dict)
    except UserError:
        return False


# --- what's each user's own -------------------------------------------------------------------

OWN_STEAM = ("api_key", "steam_id", "account", "country", "language")  # the rest is the device's


def steam_settings(config: dict, user: User) -> dict:
    """The Steam settings to work with while this user is using the device."""
    if user.admin:
        return config["steam"]
    record = _record(config, user.id)
    own = record.setdefault("steam", {})
    merged = copy.deepcopy(config["steam"])
    for key in OWN_STEAM:
        merged[key] = own.get(key, "")
    return merged


def persistable(config: dict) -> dict:
    """What's written to config.json: without the session - and with the Steam settings where
    they belong (the admin's as ever under "steam", a user's with the user)."""
    out = {k: v for k, v in config.items() if k not in ("session", "_admin_steam")}
    user = current(config)
    if not user.admin and "_admin_steam" in config:
        out = copy.deepcopy(out)
        record = next(u for u in out["users"] if isinstance(u, dict) and u.get("id") == user.id)
        record["steam"] = {key: config["steam"].get(key, "") for key in OWN_STEAM}
        device = copy.deepcopy(config["steam"])  # what isn't a user's own counts for everybody
        for key in OWN_STEAM:
            device[key] = config["_admin_steam"].get(key, "")
        out["steam"] = device
    return out


def enter(config: dict, user_id: str | None) -> User:
    """This user is using the device from now on: ``config["steam"]`` is theirs."""
    leave(config)
    user = set_current(config, user_id)
    if not user.admin:
        config["_admin_steam"] = config["steam"]
        config["steam"] = steam_settings(config, user)
    return user


def leave(config: dict) -> None:
    """Back to nobody (the lock screen): ``config["steam"]`` is the admin's again."""
    user = current(config)
    if not user.admin and "_admin_steam" in config:
        try:
            record = _record(config, user.id)
            record["steam"] = {key: config["steam"].get(key, "") for key in OWN_STEAM}
        except UserError:
            pass
        device = config["steam"]
        for key in OWN_STEAM:
            device[key] = config["_admin_steam"].get(key, "")
        config["steam"] = device
    config.pop("_admin_steam", None)
    config.pop("session", None)


def write_sidecar(config: dict) -> bool:
    """Next to a container file: who can unlock it (a lost config.json doesn't lock the users out)."""
    from gamingcrypt.unlock import sidecar

    written = persistable(config)
    return sidecar.write_sidecar(config["unlock"].get("volume", ""), written["unlock"], written.get("users"),
                                 written.get("admin"))


def adopt(config: dict, found: dict) -> None:
    """A container found by its sidecar (sidecar.find_container): its unlock settings - and its
    users, where this config has none."""
    found = dict(found)
    listed, admin_record = found.pop("users", None), found.pop("admin", None)
    config["unlock"].update(found)
    if listed and not _records(config):
        config["users"] = listed
    if admin_record and not config.get("admin"):
        config["admin"] = admin_record


class UserUnlocker:
    """Unlocks the volume with a user's own code (the admin's goes straight to VeraCrypt, as ever)."""

    def __init__(self, config: dict, user: User, unlocker_factory):
        self.config, self.user = config, user
        self.base = unlocker_factory(dict(config["unlock"], kdf=None))  # gets the volume's password itself

    @property
    def configured(self) -> bool:
        return self.base.configured

    def unlock(self, secret: str):
        from gamingcrypt.unlock.veracrypt import UnlockResult

        if not has_code(self.config, self.user.id):
            return UnlockResult(False, f"{self.user.name} has no code that fits this drive - the admin can set one")
        try:
            password = volume_password(self.config, self.user.id, secret)
        except kdf.KDFError as exc:
            return UnlockResult(False, str(exc))
        if password is None:
            return UnlockResult(False, "Wrong code")
        return self.base.unlock(password)


def unlocker_for(config: dict, user: User, unlocker_factory):
    return unlocker_factory(config["unlock"]) if user.admin else UserUnlocker(config, user, unlocker_factory)
