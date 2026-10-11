"""Several codes for one volume: every user's code opens the same VeraCrypt volume.

The volume has one password (the admin's code through scrypt, as ever - see kdf.py). For more
users there's a random master key:

* the "vault" is the volume's password, encrypted with the master key;
* a "slot" per user is the master key, encrypted with a key made from that user's code (scrypt
  with a salt of its own).

A user's code opens their slot -> the master key -> the vault -> the volume's password. A wrong
code doesn't open the slot (the check value doesn't match), so VeraCrypt isn't even asked. The
admin changing their code changes the volume's password: only the vault is written anew - the
other users' slots stay as they are. Nothing here is secret by itself: it's all in config.json
(and next to a container file, see sidecar.py).

The volume is then as safe as the weakest of its codes: who has config.json can try a user's code
without the volume (each try costs the scrypt, ~256 MB and a second).

Encryption: a key stream from HMAC-SHA256 in counter mode, and an HMAC-SHA256 over nonce and
ciphertext as the check value (encrypt-then-MAC) - the standard library has no cipher, and this
needs none: what's encrypted is 32-64 bytes, under a key that's used once.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Callable

from gamingcrypt.unlock import kdf

MASTER_BYTES = 32
NONCE_BYTES = 16
VERSION = 1


def _keys(key: bytes) -> tuple[bytes, bytes]:
    """(for the key stream, for the check value) - never the same key for both."""
    return (hmac.new(key, b"gamingcrypt keyslot encrypt", hashlib.sha256).digest(),
            hmac.new(key, b"gamingcrypt keyslot check", hashlib.sha256).digest())


def _stream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks, counter = [], 0
    while sum(map(len, blocks)) < length:
        blocks.append(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    return b"".join(blocks)[:length]


def seal(key: bytes, data: bytes, rng: Callable[[int], bytes] = os.urandom) -> dict:
    """``data`` encrypted under ``key``: {"nonce", "data", "check"} (hex)."""
    stream_key, check_key = _keys(key)
    nonce = rng(NONCE_BYTES)
    sealed = bytes(a ^ b for a, b in zip(data, _stream(stream_key, nonce, len(data))))
    check = hmac.new(check_key, nonce + sealed, hashlib.sha256).hexdigest()
    return {"version": VERSION, "nonce": nonce.hex(), "data": sealed.hex(), "check": check}


def unseal(key: bytes, box: dict | None) -> bytes | None:
    """What was sealed - None with the wrong key (or a broken / changed box)."""
    try:
        nonce, sealed, check = bytes.fromhex(box["nonce"]), bytes.fromhex(box["data"]), str(box["check"])
    except (KeyError, TypeError, ValueError):
        return None
    stream_key, check_key = _keys(key)
    if not hmac.compare_digest(hmac.new(check_key, nonce + sealed, hashlib.sha256).hexdigest(), check):
        return None
    return bytes(a ^ b for a, b in zip(sealed, _stream(stream_key, nonce, len(sealed))))


def new_master(rng: Callable[[int], bytes] = os.urandom) -> bytes:
    return rng(MASTER_BYTES)


def new_slot(secret: str, master: bytes, params: dict | None = None) -> dict:
    """The master key under a user's code: {"kdf", "box"}."""
    params = params or kdf.new_params()
    return {"kdf": params, "box": seal(kdf.derive_key(secret, params), master)}


def open_slot(secret: str, slot: dict | None) -> bytes | None:
    """The master key - None: wrong code (or no usable slot)."""
    if not isinstance(slot, dict):
        return None
    try:
        key = kdf.derive_key(secret, slot.get("kdf"))
    except kdf.KDFError:
        return None
    master = unseal(key, slot.get("box"))
    return master if master is not None and len(master) == MASTER_BYTES else None


def new_vault(master: bytes, password: str) -> dict:
    """The volume's password under the master key."""
    return seal(master, password.encode("utf-8"))


def open_vault(master: bytes, vault: dict | None) -> str | None:
    data = unseal(master, vault)
    try:
        return data.decode("utf-8") if data is not None else None
    except UnicodeDecodeError:
        return None
