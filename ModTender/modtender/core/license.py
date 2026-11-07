"""ModTender Pro: a one-time purchase on Gumroad, unlocked with the license key Gumroad emails.

No server of ours is involved. Activating sends the key to Gumroad's own verification API
(api.gumroad.com/v2/licenses/verify), which says whether it's a real, unrefunded purchase of
ModTender Pro. The answer is remembered (license.json), so Pro keeps working offline. Every two
weeks ModTender checks again in the background; only an explicit "refunded" or "not a valid key"
from Gumroad turns Pro off, never a missing internet connection.

Until PRODUCT_ID is filled in, Pro isn't on sale yet and every feature stays unlocked."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from .. import __version__
from . import paths
from .log import log

# ---- fill these in once the Gumroad product exists --------------------------------------
PRODUCT_ID = os.environ.get("MODTENDER_GUMROAD_PRODUCT", "")  # goes live: "bCY5kByJT_3fJgK-p7Wecw=="  # Gumroad: product → Content → License key
CHECKOUT_URL = os.environ.get("MODTENDER_GUMROAD_URL", "")  # goes live: "https://pearce76.gumroad.com/l/modtender-pro"  # e.g. https://<name>.gumroad.com/l/modtender-pro
PRICE = os.environ.get("MODTENDER_PRO_PRICE", "")  # goes live: "$5 or more (you choose)"  # shown in the app, e.g. "$6"
# -------------------------------------------------------------------------------------------

VERIFY_URL = "https://api.gumroad.com/v2/licenses/verify"
RECHECK = timedelta(days=14)
MAX_PCS = 5  # one key works on up to this many PCs

PRO_FEATURES = [
    "Automatic backups (daily, weekly or after every change) and unlimited backup history",
    "Update all your Minecraft mods at once",
    "One-click fixes in Match mods: turn on, download missing and turn off extras",
    "Space saver: store identical mod files only once",
    "Custom colors and accent for any theme",
    "A Pro badge, and the warm feeling of supporting the developer",
]


class LicenseError(Exception):
    pass


def on_sale() -> bool:
    return bool(PRODUCT_ID)


def _file() -> Path:
    return paths.data_dir() / "license.json"


def _load() -> dict:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(state: dict) -> None:
    _file().write_text(json.dumps(state, indent=1), encoding="utf-8")


def is_pro() -> bool:
    if not on_sale():
        return True  # Pro isn't sold yet: nothing is locked
    return bool(_load().get("valid"))


def status() -> dict:
    """What Settings shows: email, a masked key, when it was activated."""
    st = _load()
    key = st.get("key", "")
    return {"pro": is_pro(), "on_sale": on_sale(), "email": st.get("email", ""),
            "key": (key[:8] + "…" + key[-4:]) if len(key) > 12 else key, "activated": st.get("activated", "")}


def _verify(key: str, count_use: bool) -> dict:
    data = urllib.parse.urlencode({"product_id": PRODUCT_ID, "license_key": key.strip(),
                                   "increment_uses_count": "true" if count_use else "false"}).encode()
    req = urllib.request.Request(VERIFY_URL, data=data, method="POST",
                                 headers={"User-Agent": f"ModTender/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # Gumroad answers 404 with a JSON body for unknown keys
        try:
            return json.loads(exc.read().decode("utf-8"))
        except ValueError:
            raise LicenseError(f"Gumroad answered with an error ({exc.code}). Try again in a minute.") from None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise LicenseError("Couldn't reach Gumroad. Check your internet connection and try again.") from exc


def _problem(answer: dict) -> str:
    """Why a verify answer doesn't count as a valid purchase ('' when it does)."""
    if not answer.get("success"):
        return answer.get("message") or "That isn't a valid ModTender Pro key."
    purchase = answer.get("purchase") or {}
    if purchase.get("refunded") or purchase.get("chargebacked") or purchase.get("disputed"):
        return "This purchase was refunded or disputed, so the key no longer unlocks Pro."
    return ""


def activate(key: str) -> str:
    """Check a key with Gumroad and unlock Pro. Returns the buyer's email. Raises LicenseError."""
    key = key.strip()
    if not key:
        raise LicenseError("Paste the license key from your Gumroad receipt email.")
    if not on_sale():
        raise LicenseError("ModTender Pro isn't on sale yet, and everything is already unlocked.")
    answer = _verify(key, count_use=True)
    why = _problem(answer)
    if why:
        raise LicenseError(why)
    uses = int(answer.get("uses") or 0)
    if uses > MAX_PCS:
        raise LicenseError(f"This key has already been activated on {uses - 1} PCs. One key works on up to "
                           f"{MAX_PCS}. If you've replaced a PC, contact the developer to reset it.")
    email = str((answer.get("purchase") or {}).get("email", ""))
    now = datetime.now().isoformat(timespec="seconds")
    _save({"key": key, "email": email, "valid": True, "activated": now, "checked": now})
    log.info("ModTender Pro activated (%s)", email or "no email")
    return email


def recheck_if_due() -> str:
    """Background check every two weeks. Returns a message only when Pro was switched off."""
    st = _load()
    if not on_sale() or not st.get("key") or not st.get("valid"):
        return ""
    try:
        if datetime.now() - datetime.fromisoformat(st.get("checked", "")) < RECHECK:
            return ""
    except ValueError:
        pass
    try:
        answer = _verify(st["key"], count_use=False)
    except LicenseError:
        return ""  # offline or Gumroad down: keep Pro, try again next time
    why = _problem(answer)
    st["checked"] = datetime.now().isoformat(timespec="seconds")
    if why:
        st["valid"] = False
        st["problem"] = why
        log.warning("ModTender Pro switched off: %s", why)
    _save(st)
    return why


def deactivate() -> None:
    _file().unlink(missing_ok=True)
    log.info("ModTender Pro key removed from this PC")
