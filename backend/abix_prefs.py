#!/usr/bin/env python3
"""ABIX UI preferences (V6 slice 1): logo animation style / level, saved permanently in the persistent home volume.
Stdlib only. Whitelist only: unknown keys and bad values are rejected, nothing is ever passed to a shell."""
import json
import os
import pwd

DESK_USER = os.environ.get("ABIX_DESKTOP_USER", "abix")
DESK_HOME = os.environ.get("ABIX_DESKTOP_HOME", "/home/abix")
STYLES = ("pulse", "orbit", "draw", "bloom", "aurora")
LEVELS = ("off", "light", "full")
DEFAULTS = {"logo_style": "pulse", "logo_anim": "light", "boot_anim": True}


def path():
    return os.path.join(DESK_HOME, ".config", "abix", "ui.json")


def load():
    """Saved values merged over the defaults. A missing or damaged file gives the defaults (never an error)."""
    out = dict(DEFAULTS)
    try:
        with open(path(), encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            if saved.get("logo_style") in STYLES:
                out["logo_style"] = saved["logo_style"]
            if saved.get("logo_anim") in LEVELS:
                out["logo_anim"] = saved["logo_anim"]
            if isinstance(saved.get("boot_anim"), bool):
                out["boot_anim"] = saved["boot_anim"]
    except (OSError, ValueError):
        pass
    return out


def _own(p):
    if DESK_USER and os.geteuid() == 0:
        try:
            u = pwd.getpwnam(DESK_USER)
            os.chown(p, u.pw_uid, u.pw_gid)
        except (KeyError, OSError):
            pass


def save(patch):
    """Validate a patch, merge it into the saved file. Returns (result dict, http status)."""
    if not isinstance(patch, dict) or not patch:
        return {"ok": False, "error": "nothing to save"}, 400
    errors = {}
    for k, v in patch.items():
        if k == "logo_style" and v not in STYLES:
            errors[k] = "must be one of: " + ", ".join(STYLES)
        elif k == "logo_anim" and v not in LEVELS:
            errors[k] = "must be one of: " + ", ".join(LEVELS)
        elif k == "boot_anim" and not isinstance(v, bool):
            errors[k] = "must be true or false"
        elif k not in DEFAULTS:
            errors[k] = "unknown setting"
    if errors:
        return {"ok": False, "errors": errors}, 400
    cur = load()
    cur.update(patch)
    p = path()
    try:
        d = os.path.dirname(p)
        os.makedirs(d, exist_ok=True)
        tmp = p + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cur, f)
        os.replace(tmp, p)
        _own(d)
        _own(p)
    except OSError as e:
        return {"ok": False, "error": "could not save: %s" % e}, 500
    return {"ok": True, "prefs": cur}, 200
