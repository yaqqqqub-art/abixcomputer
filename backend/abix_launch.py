#!/usr/bin/env python3
"""ABIX launcher (V6 slice 1): the list of apps shown in the Start menu, their REAL install status, and a launch action.
Stdlib only. Imported by abix_api.py (root inside the container); apps always start as the desktop user, never as root.

Honest states (nothing is faked):
  installed       the program is on this computer (found on PATH)
  not_installed   the program is missing; `install_id` (when present) names the App Center entry that installs it
  web             a web app (WhatsApp, imo, Telegram): opens in a browser window; needs Chrome/Edge/Chromium or Firefox
  windows_only    a Windows program (Premiere Pro, After Effects): no Linux version. It becomes 'installed' only when a
                  verified Wine launcher is registered in ~/.config/abix/windows-apps.json
Launch commands are fixed argument lists from this file. The browser sends only an app id, never a command or a URL."""
import glob
import json
import os
import pwd
import shutil
import subprocess
import threading
import time

DESK_USER = os.environ.get("ABIX_DESKTOP_USER", "abix")
DESK_HOME = os.environ.get("ABIX_DESKTOP_HOME", "/home/abix")
SEARCH_PATH = os.environ.get("ABIX_LAUNCH_PATH", "/usr/local/bin:/usr/bin:/bin:/opt/google/chrome:/opt/microsoft/msedge")
CATEGORIES = ("Productivity", "Utilities & Tools", "Internet", "Social", "Creativity", "Development")
CHROMIUM = ("google-chrome-stable", "google-chrome", "microsoft-edge-stable", "chromium", "chromium-browser")
LAUNCH_GAP = 0.6          # seconds between two launches (stops a click-flood from starting dozens of programs)
_last = [0.0]
_lock = threading.Lock()


def _a(id, name, desc, category, kind, cmd=None, check=(), icon=None, install_id=None):
    return {"id": id, "name": name, "desc": desc, "category": category, "kind": kind, "cmd": cmd or [],
            "check": list(check), "icon": icon or (id + ".svg"), "install_id": install_id}


CATALOG = [
    _a("file-manager", "File Manager", "Browse, copy and organise files.", "Productivity", "native", ["thunar"], ["thunar"], "file-manager.png"),
    _a("notepad", "ABIX Notepad", "Simple text notes.", "Productivity", "native", ["mousepad"], ["mousepad"]),
    _a("calculator", "Calculator", "Basic and scientific calculator.", "Productivity", "native", ["gnome-calculator"], ["gnome-calculator"]),
    _a("archive", "Archive Manager", "Open and create ZIP and other archives.", "Productivity", "native", ["file-roller"], ["file-roller"]),
    _a("terminal", "Terminal", "Command line.", "Utilities & Tools", "native", ["xfce4-terminal"], ["xfce4-terminal"]),
    _a("task-manager", "Task Manager", "See running programs and stop one that hangs.", "Utilities & Tools", "native", ["xfce4-taskmanager"], ["xfce4-taskmanager"]),
    _a("system-monitor", "System Monitor", "CPU and memory in the terminal (htop).", "Utilities & Tools", "native", ["xfce4-terminal", "-e", "htop"], ["htop"], None, "htop"),
    _a("screenshot", "Screenshot Tool", "Capture the screen or a window.", "Utilities & Tools", "native", ["xfce4-screenshooter"], ["xfce4-screenshooter"], "screenshot.png", "screenshooter"),
    _a("settings", "Settings", "Look, wallpaper and desktop options.", "Utilities & Tools", "native", ["abix-personalize"], ["abix-personalize"]),
    _a("abix-browser", "ABIX Browser", "ABIX's own browser window with a separate profile (tabs, bookmarks, history, downloads).", "Internet", "native", ["abix-browser"],
       ["abix-browser"]),
    _a("chrome", "Google Chrome", "Google's web browser.", "Internet", "native", ["abix-chrome"], ["google-chrome-stable", "google-chrome"], None, "google-chrome"),
    _a("firefox", "Firefox", "Mozilla's web browser.", "Internet", "native", ["firefox"], ["firefox"]),
    _a("edge", "Microsoft Edge", "Microsoft's web browser.", "Internet", "native", ["abix-edge"], ["microsoft-edge-stable"]),
    _a("whatsapp", "WhatsApp", "WhatsApp Web in its own window.", "Social", "web", ["abix-webapp", "whatsapp"]),
    _a("imo", "imo", "imo web in its own window.", "Social", "web", ["abix-webapp", "imo"]),
    _a("telegram", "Telegram", "Telegram Web in its own window.", "Social", "web", ["abix-webapp", "telegram"]),
    _a("premiere", "Adobe Premiere Pro", "Windows-only video editor.", "Creativity", "windows"),
    _a("aftereffects", "Adobe After Effects", "Windows-only motion graphics.", "Creativity", "windows"),
    _a("gimp", "GIMP", "Photo and image editor.", "Creativity", "native", ["gimp"], ["gimp"], None, "gimp"),
    _a("inkscape", "Inkscape", "Vector graphics editor.", "Creativity", "native", ["inkscape"], ["inkscape"], None, "inkscape"),
    _a("krita", "Krita", "Digital painting.", "Creativity", "native", ["krita"], ["krita"], None, "krita"),
    _a("audacity", "Audacity", "Audio recorder and editor.", "Creativity", "native", ["audacity"], ["audacity"], None, "audacity"),
    _a("kdenlive", "Kdenlive", "Video editor (Linux).", "Creativity", "native", ["kdenlive"], ["kdenlive"], None, "kdenlive"),
    _a("vscode", "Visual Studio Code", "Code editor.", "Development", "native", ["code", "--no-sandbox"], ["code"], None, "vscode"),
]
WINDOWS_NOTE = ("Windows-only: there is no Linux version. ABIX can try to run a setup file you own through Wine "
                "(App Center > Windows program), but Adobe's current apps are not known to run properly under Wine. "
                "Treat this as unverified until it works for you.")


def which(name):
    return shutil.which(name, path=SEARCH_PATH)


def engine():
    """('chromium', binary) / ('firefox', binary) / (None, None): the browser a web app would open in."""
    for n in CHROMIUM:
        if which(n):
            return "chromium", n
    if which("firefox"):
        return "firefox", "firefox"
    return None, None


# ------------------------------------------------------------------ Windows (Wine) registry
def _inside_home(p):
    root = os.path.realpath(DESK_HOME)
    r = os.path.realpath(p)
    return r == root or r.startswith(root + os.sep)


def windows_registry():
    """{id: {"exe": ..., "prefix": ...}} - only entries whose files really exist inside the home folder."""
    out = {}
    try:
        with open(os.path.join(DESK_HOME, ".config", "abix", "windows-apps.json"), encoding="utf-8") as f:
            items = json.load(f).get("apps", [])
    except (OSError, ValueError, AttributeError):
        return out
    for e in items if isinstance(items, list) else []:
        try:
            exe, prefix, aid = e["exe"], e["prefix"], e["id"]
        except (KeyError, TypeError):
            continue
        if (isinstance(exe, str) and isinstance(prefix, str) and isinstance(aid, str)
                and exe.lower().endswith(".exe") and _inside_home(exe) and _inside_home(prefix)
                and os.path.isfile(exe) and os.path.isdir(prefix)):
            out[aid] = {"exe": os.path.realpath(exe), "prefix": os.path.realpath(prefix)}
    return out


# ------------------------------------------------------------------ status
def state(a):
    """Real, current status of one catalog entry."""
    s = {"id": a["id"], "name": a["name"], "desc": a["desc"], "category": a["category"], "kind": a["kind"],
         "icon": a["icon"], "install_id": a["install_id"], "state": "not_installed", "can_launch": False, "note": ""}
    if a["kind"] == "native":
        if any(which(c) for c in a["check"]):
            s.update(state="installed", can_launch=True)
        else:
            s["note"] = ("Not installed. Install it from the App Center." if a["install_id"] else "Not available in this image.")
    elif a["kind"] == "web":
        eng, _ = engine()
        if eng:
            s.update(state="web", can_launch=True, note="Opens as a web app in " + ("Chrome/Edge" if eng == "chromium" else "Firefox") + ".")
        else:
            s["note"] = "No browser is installed, so this web app cannot open."
    else:
        if a["id"] in windows_registry():
            s.update(state="installed", can_launch=True)
        else:
            s.update(state="windows_only", note=WINDOWS_NOTE)
    return s


def catalog_view():
    return [state(a) for a in CATALOG]


def find(app_id):
    for a in CATALOG:
        if a["id"] == app_id:
            return a
    return None


# ------------------------------------------------------------------ launching
def session_env():
    """DISPLAY + DBUS of the running Xfce session (GUI programs need the session bus), read from xfce4-session."""
    env = {"PATH": SEARCH_PATH, "HOME": DESK_HOME, "DISPLAY": ":1", "XDG_RUNTIME_DIR": "/tmp/runtime-abix", "LANG": "C.UTF-8",
           "USER": DESK_USER or "abix"}
    try:
        uid = pwd.getpwnam(DESK_USER).pw_uid if DESK_USER else os.getuid()
    except KeyError:
        return env
    for p in glob.glob("/proc/[0-9]*"):
        try:
            if os.stat(p).st_uid != uid:
                continue
            with open(p + "/comm") as f:
                if f.read().strip() != "xfce4-session":
                    continue
            with open(p + "/environ", "rb") as f:
                for item in f.read().split(b"\0"):
                    k, _, v = item.partition(b"=")
                    if k in (b"DBUS_SESSION_BUS_ADDRESS", b"DISPLAY", b"XDG_RUNTIME_DIR"):
                        env[k.decode()] = v.decode()
            return env
        except OSError:
            continue
    return env


def _log_tail(path, n=300):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - n))
            return f.read().decode("utf-8", "replace").strip()
    except OSError:
        return ""


def launch(app_id, wait=1.5):
    """Start an app. Returns (http status, dict). Success is reported only if the process really started:
    still running after `wait` seconds = 'running'; exited 0 = 'started' (single-instance apps hand over to an
    already-running copy); exited with an error = failure with the program's own message."""
    a = find(app_id) if isinstance(app_id, str) else None
    if not a:
        return 404, {"error": "unknown app"}
    s = state(a)
    if not s["can_launch"]:
        return 409, {"error": s["note"] or "This app cannot be started.", "state": s["state"]}
    with _lock:
        now = time.time()
        if now - _last[0] < LAUNCH_GAP:
            return 429, {"error": "Wait a moment before starting another program."}
        _last[0] = now
    env = session_env()
    cmd = list(a["cmd"])
    if a["kind"] == "windows":
        w = windows_registry()[a["id"]]
        cmd = ["wine", "start", "/unix", w["exe"]]
        env["WINEPREFIX"] = w["prefix"]
    cache = os.path.join(DESK_HOME, ".cache")
    log = os.path.join(cache, "abix-launch.log")
    kw = {}
    if DESK_USER and os.geteuid() == 0:
        kw = {"user": DESK_USER, "group": DESK_USER, "extra_groups": []}
    try:
        os.makedirs(cache, exist_ok=True)
        out = open(log, "ab")
        try:
            if kw:
                u = pwd.getpwnam(DESK_USER)
                os.chown(cache, u.pw_uid, u.pw_gid)
                os.fchown(out.fileno(), u.pw_uid, u.pw_gid)
            out.write(("\n--- %s %s\n" % (time.strftime("%H:%M:%S"), a["id"])).encode())
            out.flush()
            p = subprocess.Popen(cmd, env=env, cwd=DESK_HOME, stdin=subprocess.DEVNULL, stdout=out, stderr=out,
                                 start_new_session=True, **kw)
        finally:
            out.close()
    except (OSError, KeyError) as e:
        return 500, {"error": "could not start %s: %s" % (a["name"], e)}
    deadline = time.time() + wait
    while time.time() < deadline and p.poll() is None:
        time.sleep(0.05)
    rc = p.poll()
    if rc is None:
        return 200, {"ok": True, "state": "running", "message": a["name"] + " is starting.", "pid": p.pid}
    if rc == 0:
        return 200, {"ok": True, "state": "started", "message": a["name"] + " was started (it may have opened in a window that was already running)."}
    return 500, {"error": "%s stopped right after starting (code %d). %s" % (a["name"], rc, _log_tail(log)), "state": "failed"}
