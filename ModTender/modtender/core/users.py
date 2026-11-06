"""Local user accounts: each person on this PC gets their own settings (theme, games, backups folder...).

An optional PIN keeps others from opening your profile by accident. It is not strong security:
anyone with access to the Windows account can read ModTender's files. Online accounts come later."""
from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass

from . import paths
from .log import log

ITERATIONS = 200_000


@dataclass
class User:
    id: str
    name: str
    pin_hash: str = ""
    salt: str = ""
    created: str = ""
    color: str = ""  # avatar color
    avatar: str = ""  # picture file name inside the user's folder, if they chose one

    @property
    def avatar_path(self):
        return (paths.data_dir() / "users" / self.id / self.avatar) if self.avatar else None

    @property
    def has_pin(self) -> bool:
        return bool(self.pin_hash)


AVATAR_COLORS = ["#3ecf8e", "#4f8cff", "#a371f7", "#ec6cb9", "#f0883e", "#2dd4bf", "#e3b341", "#f85149"]


def _file():
    return paths.data_dir() / "users.json"


def _read() -> dict:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"users": [], "last_user": "", "show_signin": False}


def _write(data: dict) -> None:
    tmp = _file().with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(_file())


def user_dir(user_id: str):
    d = paths.data_dir() / "users" / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_users() -> list[User]:
    return [User(**{k: v for k, v in u.items() if k in User.__dataclass_fields__}) for u in _read().get("users", [])]


def _hash(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), ITERATIONS).hex()


def _save_users(users: list[User], **extra) -> None:
    data = _read()
    data["users"] = [asdict(u) for u in users]
    data.update(extra)
    _write(data)


def _new_id(name: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "user"
    uid, n = base, 2
    while uid in taken:
        uid, n = f"{base}-{n}", n + 1
    return uid


def create_user(name: str, pin: str = "") -> User:
    users = list_users()
    name = name.strip()[:40] or "Player"
    user = User(_new_id(name, {u.id for u in users}), name, created=time.strftime("%Y-%m-%dT%H:%M:%S"),
                color=AVATAR_COLORS[len(users) % len(AVATAR_COLORS)])
    if pin:
        set_pin_on(user, pin)
    users.append(user)
    _save_users(users)
    user_dir(user.id)
    log.info("Created local user '%s'", user.name)
    return user


def set_pin_on(user: User, pin: str) -> None:
    if pin:
        user.salt = os.urandom(16).hex()
        user.pin_hash = _hash(pin, user.salt)
    else:
        user.salt = user.pin_hash = ""


def update_user(user: User) -> None:
    users = [user if u.id == user.id else u for u in list_users()]
    _save_users(users)


def delete_user(user: User) -> None:
    users = [u for u in list_users() if u.id != user.id]
    data = _read()
    _save_users(users, last_user="" if data.get("last_user") == user.id else data.get("last_user", ""))
    shutil.rmtree(paths.data_dir() / "users" / user.id, ignore_errors=True)
    log.info("Deleted local user '%s'", user.name)


def check_pin(user: User, pin: str) -> bool:
    if not user.has_pin:
        return True
    return hmac.compare_digest(_hash(pin, user.salt), user.pin_hash)


def last_user_id() -> str:
    return _read().get("last_user", "")


def set_last_user(user: User) -> None:
    data = _read()
    data["last_user"] = user.id
    _write(data)


def show_signin() -> bool:
    return bool(_read().get("show_signin", False))


def set_show_signin(value: bool) -> None:
    data = _read()
    data["show_signin"] = bool(value)
    _write(data)


def needs_signin() -> bool:
    """Skip the sign-in screen when there's one user, without a PIN, who hasn't asked to see it."""
    users = list_users()
    return len(users) > 1 or any(u.has_pin for u in users) or show_signin()


def ensure_first_user() -> User:
    """First run with user accounts: turn the existing settings into a user named after the Windows account."""
    users = list_users()
    if users:
        return next((u for u in users if u.id == last_user_id()), users[0])
    try:
        name = getpass.getuser() or "Player"
    except Exception:
        name = "Player"
    user = create_user(name.capitalize())
    old = paths.data_dir() / "settings.json"
    if old.exists():
        shutil.copy2(old, user_dir(user.id) / "settings.json")
        log.info("Moved existing settings into user '%s'", user.name)
    set_last_user(user)
    return user
