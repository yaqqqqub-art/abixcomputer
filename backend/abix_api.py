#!/usr/bin/env python3
"""ABIX API (Stage 2) - login, session, lock, settings and power endpoints.

Python standard library only. Runs INSIDE the desktop container as root (so the desktop user
cannot read the secrets), listens on 0.0.0.0:8080 on the internal Docker network only, and is
reached only through Nginx (/api/). Desktop changes are made by running `abix-ctl` as the desktop
user - always as an argument list, never through a shell.

Config file (written by entrypoint.sh):  /home/abix/.config/abix/backend.json
  {"user": "admin", "hash": "pbkdf2:<iterations>:<salt hex>:<hash hex>", "secret": "<hex>", "vnc_password": "..."}
"""
import base64
import glob
import pwd
import shutil
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import abix_apps
import abix_launch
import abix_prefs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

CONF_PATH = os.environ.get("ABIX_BACKEND_CONF", "/etc/abix/backend.json")
CTL = os.environ.get("ABIX_CTL", "/usr/local/bin/abix-ctl")
DESK_USER = os.environ.get("ABIX_DESKTOP_USER", "abix")          # "" = do not drop privileges (tests)
DESK_HOME = os.environ.get("ABIX_DESKTOP_HOME", "/home/abix")
SYS_WALLS = os.environ.get("ABIX_SYS_WALLS", "/usr/share/backgrounds/abix")
USER_WALLS = os.path.join(DESK_HOME, "Pictures", "Wallpapers")
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
MAX_WALL_BYTES = 30 * 1024 * 1024
IDLE_SECONDS = int(float(os.environ.get("ABIX_SESSION_HOURS", "8")) * 3600)   # sliding idle timeout
ABS_SECONDS = 24 * 3600                                                        # hard limit
COOKIE = "abix_session"
COOKIE_SECURE = os.environ.get("ABIX_COOKIE_SECURE", "1") != "0"
MAX_BODY = 8192
FAIL_LIMIT, FAIL_WINDOW = 5, 300          # 5 wrong passwords per 5 minutes per address

THEMES = ("light", "dark")
ANIMS = ("off", "light", "full")
LOCK = threading.Lock()
SESSIONS = {}      # sid -> {"user","created","last","locked"}
FAILS = {}         # ip -> [timestamps]
CONF = {}


def log(event, **kw):
    kw["event"] = event
    kw["t"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    print("[abix-api] " + json.dumps(kw, ensure_ascii=False), flush=True)


# ------------------------------------------------------------------ passwords and cookies
def make_hash(password, iterations=200000):
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
    return "pbkdf2:%d:%s:%s" % (iterations, salt, dk)


def check_password(password, stored):
    try:
        kind, it, salt, want = stored.split(":")
        if kind != "pbkdf2":
            return False
        got = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(it)).hex()
        return hmac.compare_digest(got, want)
    except (ValueError, AttributeError):
        return False


def sign(sid):
    return hmac.new(CONF["secret"].encode(), sid.encode(), hashlib.sha256).hexdigest()[:40]


def cookie_value(sid):
    return sid + "." + sign(sid)


def sid_from_cookie(header):
    if not header:
        return None
    for part in header.split(";"):
        k, _, v = part.strip().partition("=")
        if k == COOKIE and "." in v:
            sid, _, sig = v.partition(".")
            if re.fullmatch(r"[0-9a-f]{32}", sid) and hmac.compare_digest(sig, sign(sid)):
                return sid
    return None


def get_session(sid, touch=True):
    """Return the live session or None (expired sessions are removed)."""
    if not sid:
        return None
    now = time.time()
    with LOCK:
        s = SESSIONS.get(sid)
        if not s:
            return None
        if now - s["last"] > IDLE_SECONDS or now - s["created"] > ABS_SECONDS:
            SESSIONS.pop(sid, None)
            return None
        if touch:
            s["last"] = now
        return dict(s)


# ------------------------------------------------------------------ throttle
def throttled(ip):
    now = time.time()
    with LOCK:
        FAILS[ip] = [t for t in FAILS.get(ip, []) if now - t < FAIL_WINDOW]
        return len(FAILS[ip]) >= FAIL_LIMIT


def record_fail(ip):
    with LOCK:
        FAILS.setdefault(ip, []).append(time.time())


# ------------------------------------------------------------------ desktop control
def run_as_desktop(args, timeout=40):
    """Run abix-ctl (or another fixed command) as the desktop user. Returns (rc, stdout, stderr)."""
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": DESK_HOME, "DISPLAY": ":1",
           "XDG_RUNTIME_DIR": os.path.join(DESK_HOME, ".runtime"), "LANG": "C.UTF-8"}
    kw = {}
    if DESK_USER and os.geteuid() == 0:
        kw = {"user": DESK_USER, "group": DESK_USER, "extra_groups": []}
    try:
        r = subprocess.run(args, env=env, capture_output=True, text=True, timeout=timeout, **kw)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, "", str(e)


def ctl_json(args):
    rc, out, err = run_as_desktop([CTL] + args)
    if rc != 0:
        return None, err or out or "abix-ctl failed"
    try:
        return json.loads(out), ""
    except ValueError:
        return {"raw": out}, ""


def list_wallpapers():
    items = []
    for kind, folder in (("sys", SYS_WALLS), ("user", USER_WALLS)):
        for p in sorted(glob.glob(os.path.join(folder, "*"))):
            n = os.path.basename(p)
            if n.lower().endswith(IMG_EXT) and os.path.isfile(p) and os.path.getsize(p) <= MAX_WALL_BYTES:
                items.append({"id": "%s-%s" % (kind, n), "name": os.path.splitext(n)[0].replace("-", " ").replace("_", " ")})
    return items


def wallpaper_path(wid):
    m = re.fullmatch(r"(sys|user)-([A-Za-z0-9._-]{1,120})", wid or "")
    if not m or ".." in m.group(2):
        return None
    folder = SYS_WALLS if m.group(1) == "sys" else USER_WALLS
    p = os.path.realpath(os.path.join(folder, m.group(2)))
    if os.path.dirname(p) != os.path.realpath(folder) or not p.lower().endswith(IMG_EXT):
        return None
    if not os.path.isfile(p) or os.path.getsize(p) > MAX_WALL_BYTES:
        return None
    return p


def apply_settings(body):
    """Validate every field against a fixed list, then call abix-ctl. Returns (result dict, http status)."""
    done, errors = {}, {}
    if "theme" in body:
        if body["theme"] in THEMES:
            r, e = ctl_json(["theme", body["theme"]])
            (done.__setitem__("theme", body["theme"]) if r is not None else errors.__setitem__("theme", e))
        else:
            errors["theme"] = "must be light or dark"
    if "animation" in body:
        if body["animation"] in ANIMS:
            r, e = ctl_json(["anim", body["animation"]])
            if r is not None:
                done["animation"] = r.get("effective", body["animation"]) if isinstance(r, dict) else body["animation"]
            else:
                errors["animation"] = e
        else:
            errors["animation"] = "must be off, light or full"
    if "accent" in body:
        if isinstance(body["accent"], str) and re.fullmatch(r"#[0-9a-fA-F]{6}", body["accent"]):
            r, e = ctl_json(["accent", body["accent"]])
            (done.__setitem__("accent", body["accent"]) if r is not None else errors.__setitem__("accent", e))
        else:
            errors["accent"] = "must look like #RRGGBB"
    if "wallpaper" in body:
        p = wallpaper_path(body["wallpaper"]) if isinstance(body["wallpaper"], str) else None
        if p:
            r, e = ctl_json(["wallpaper", p])
            (done.__setitem__("wallpaper", body["wallpaper"]) if r is not None else errors.__setitem__("wallpaper", e))
        else:
            errors["wallpaper"] = "unknown wallpaper"
    unknown = [k for k in body if k not in ("theme", "animation", "accent", "wallpaper")]
    for k in unknown:
        errors[k] = "unknown setting"
    if errors and not done:
        return {"ok": False, "errors": errors}, 400
    return {"ok": True, "applied": done, "errors": errors}, 200


def read_status():
    r, e = ctl_json(["status"])
    if r is None:
        return {"available": False, "error": e}
    s = r.get("settings", {})
    return {"available": True,
            "theme": s.get("THEME"), "animation": s.get("ANIMATION"), "accent": s.get("ACCENT"),
            "wallpaper": os.path.basename(s.get("WALLPAPER", "")),
            "active_animation": (r.get("active", {}).get("animation") or {}).get("effective")
            if isinstance(r.get("active", {}).get("animation"), dict) else r.get("active", {}).get("animation"),
            "start_menu": "whisker" if r.get("detected", {}).get("whisker_menu") else "xfce-menu",
            "picom": bool(r.get("detected", {}).get("picom"))}


def kick_viewers():
    """Drop every open noVNC connection (websockify restarts by itself). Used when locking."""
    subprocess.run(["pkill", "-u", DESK_USER or "abix", "-f", "websockify"], capture_output=True)


def power(action):
    if action == "restart-session":
        run_as_desktop([CTL, "restart-session"])
        return True
    if action == "restart-desktop":
        subprocess.run(["pkill", "-u", DESK_USER or "abix", "Xtigervnc"], capture_output=True)
        return True
    return False



# ------------------------------------------------------------------ files (Stage 3): browse / download / upload inside the desktop home only
MAX_UPLOAD = int(os.environ.get("ABIX_MAX_UPLOAD_MB", "512")) * 1024 * 1024
BLOCKED_PARTS = (".vnc", ".ssh", ".gnupg")


def safe_path(rel, must_exist=True):
    """Map a user supplied relative path to a real path INSIDE the desktop home, or None.
    Rejects absolute paths, '..', blocked folders and symlinks that point outside the home."""
    if not isinstance(rel, str) or "\x00" in rel or len(rel) > 1024:
        return None
    rel = rel.strip().lstrip("/")
    parts = [x for x in rel.split("/") if x not in ("", ".")]
    if ".." in parts or any(x in BLOCKED_PARTS for x in parts):
        return None
    root = os.path.realpath(DESK_HOME)
    full = os.path.realpath(os.path.join(root, *parts))
    if full != root and not full.startswith(root + os.sep):
        return None
    if must_exist and not os.path.exists(full):
        return None
    return full


def rel_of(full):
    root = os.path.realpath(DESK_HOME)
    r = os.path.relpath(full, root)
    return "" if r == "." else r.replace(os.sep, "/")


def list_dir(rel):
    full = safe_path(rel)
    if not full or not os.path.isdir(full):
        return None
    items = []
    for name in sorted(os.listdir(full), key=str.lower):
        if name.startswith(".") and name in BLOCKED_PARTS:
            continue
        fp = os.path.join(full, name)
        try:
            st = os.stat(fp)
        except OSError:
            continue
        items.append({"name": name, "type": "dir" if os.path.isdir(fp) else "file",
                      "size": 0 if os.path.isdir(fp) else st.st_size, "mtime": int(st.st_mtime)})
    return {"path": rel_of(full), "items": items}


def give_to_desktop_user(path):
    if not DESK_USER:
        return
    try:
        u = pwd.getpwnam(DESK_USER)
        os.chown(path, u.pw_uid, u.pw_gid)
    except (KeyError, OSError):
        pass


def clean_name(name):
    if not isinstance(name, str):
        return None
    name = os.path.basename(name.replace("\\", "/")).strip()
    if not name or name in (".", "..") or "\x00" in name or len(name) > 200:
        return None
    return name

# ------------------------------------------------------------------ HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "abix-api"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    timeout = 15          # a stalled client cannot hold a thread forever

    def log_message(self, *a):   # access lines are not needed; events are logged explicitly
        pass

    # ---- helpers
    def ip(self):
        return self.headers.get("X-Real-IP") or self.client_address[0]

    def send(self, code, obj=None, cookie=None, raw=None, ctype="application/json", extra=None):
        data = raw if raw is not None else json.dumps(obj if obj is not None else {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if ctype == "application/json":
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def cookie_header(self, sid, clear=False):
        flags = "; Path=/; HttpOnly; SameSite=Strict" + ("; Secure" if COOKIE_SECURE else "")
        if clear:
            return "%s=; Max-Age=0%s" % (COOKIE, flags)
        return "%s=%s; Max-Age=%d%s" % (COOKIE, cookie_value(sid), IDLE_SECONDS, flags)

    def body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if n > MAX_BODY:
            self.close_connection = True
            return None
        if n == 0:
            return {}
        try:
            v = json.loads(self.rfile.read(n).decode("utf-8"))
            return v if isinstance(v, dict) else None
        except (ValueError, UnicodeDecodeError):
            return None

    def csrf_ok(self):
        # A custom header cannot be sent cross-site without CORS approval, and the cookie is SameSite=Strict.
        return self.headers.get("X-Abix") == "1" and "application/json" in (self.headers.get("Content-Type") or "")

    def session(self, touch=True):
        sid = sid_from_cookie(self.headers.get("Cookie"))
        return sid, get_session(sid, touch)

    # ---- routes
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.send(200, {"ok": True})
        if path == "/api/auth/check":           # used by Nginx auth_request: only 200/401/403 are meaningful
            sid, s = self.session(touch=False)
            if not s:
                return self.send(401, {"ok": False})
            if s["locked"]:
                return self.send(403, {"ok": False, "locked": True})
            return self.send(200, {"ok": True})
        if path == "/api/session":
            sid, s = self.session()
            if not s:
                return self.send(200, {"authenticated": False})
            return self.send(200, {"authenticated": True, "user": s["user"], "locked": s["locked"]})
        sid, s = self.session()
        if not s:
            return self.send(401, {"error": "login required"})
        if path == "/api/connect":              # VNC password for the embedded viewer (never when locked)
            if s["locked"]:
                return self.send(403, {"error": "locked"})
            return self.send(200, {"password": CONF.get("vnc_password", "")})
        if s["locked"]:
            return self.send(403, {"error": "locked"})
        if path in ("/api/files", "/api/files/download"):
            q = parse_qs(urlparse(self.path).query)
            rel = (q.get("path") or [""])[0]
            if path == "/api/files":
                res = list_dir(rel)
                return self.send(200, res) if res is not None else self.send(404, {"error": "folder not found"})
            full = safe_path(rel)
            if not full or not os.path.isfile(full):
                return self.send(404, {"error": "file not found"})
            size = os.path.getsize(full)
            fname = os.path.basename(full).replace('"', "_").replace("\r", "").replace("\n", "")
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size))
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % fname)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            log("download", ip=self.ip(), file=rel_of(full))
            with open(full, "rb") as f:
                shutil.copyfileobj(f, self.wfile, 1024 * 256)
            return
        if path == "/api/apps":
            return self.send(200, {"items": [abix_apps.app_view(a) for a in abix_apps.load_catalog()],
                                   "jobs": abix_apps.list_jobs(), "wine": abix_apps.wine_available(), "arch": abix_apps.arch()})
        if path == "/api/launcher":
            return self.send(200, {"items": abix_launch.catalog_view(), "categories": list(abix_launch.CATEGORIES)})
        if path == "/api/ui-prefs":
            return self.send(200, {"prefs": abix_prefs.load(), "styles": list(abix_prefs.STYLES), "levels": list(abix_prefs.LEVELS)})
        if path == "/api/apps/job":
            q = parse_qs(urlparse(self.path).query)
            j = abix_apps.get_job((q.get("id") or [""])[0])
            return self.send(200, j) if j else self.send(404, {"error": "unknown job"})
        if path == "/api/settings":
            return self.send(200, read_status())
        if path == "/api/wallpapers":
            return self.send(200, {"items": list_wallpapers()})
        if path.startswith("/api/wallpaper/"):
            p = wallpaper_path(path[len("/api/wallpaper/"):])
            if not p:
                return self.send(404, {"error": "not found"})
            ctype = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "bmp": "image/bmp"}[p.rsplit(".", 1)[1].lower()]
            with open(p, "rb") as f:
                return self.send(200, raw=f.read(), ctype=ctype, extra={"Cache-Control": "private, max-age=3600"})
        return self.send(404, {"error": "not found"})

    def do_upload(self):
        """POST /api/files/upload?path=Downloads&name=file.bin  - raw body, streamed to disk, never held in memory."""
        if self.headers.get("X-Abix") != "1":
            self.close_connection = True
            return self.send(400, {"error": "bad request"})
        sid, s = self.session()
        if not s:
            self.close_connection = True
            return self.send(401, {"error": "login required"})
        if s["locked"]:
            self.close_connection = True
            return self.send(403, {"error": "locked"})
        q = parse_qs(urlparse(self.path).query)
        folder = safe_path((q.get("path") or ["Downloads"])[0])
        name = clean_name((q.get("name") or [""])[0])
        try:
            n = int(self.headers.get("Content-Length") or -1)
        except ValueError:
            n = -1
        if not folder or not os.path.isdir(folder) or not name or n < 0:
            self.close_connection = True
            return self.send(400, {"error": "bad folder, name or length"})
        if n > MAX_UPLOAD:
            self.close_connection = True
            return self.send(413, {"error": "file too large (limit %d MB)" % (MAX_UPLOAD // 1048576)})
        dest = os.path.join(folder, name)
        if os.path.realpath(os.path.dirname(dest)) != os.path.realpath(folder) or os.path.islink(dest):
            return self.send(400, {"error": "bad name"})
        tmp = dest + ".abix-part"
        left = n
        try:
            with open(tmp, "wb") as f:
                while left > 0:
                    chunk = self.rfile.read(min(262144, left))
                    if not chunk:
                        raise IOError("connection closed early")
                    f.write(chunk)
                    left -= len(chunk)
            os.replace(tmp, dest)
            give_to_desktop_user(dest)
        except (IOError, OSError) as e:
            try:
                os.remove(tmp)
            except OSError:
                pass
            self.close_connection = True
            return self.send(500, {"error": "upload failed: %s" % e})
        log("upload", ip=self.ip(), file=rel_of(dest), bytes=n)
        return self.send(200, {"ok": True, "path": rel_of(dest), "size": n})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/files/upload":
            return self.do_upload()
        if not self.csrf_ok():
            return self.send(400, {"error": "bad request"})
        body = self.body()
        if body is None:
            return self.send(400, {"error": "bad json or too large"})
        ip = self.ip()

        if path == "/api/login":
            if throttled(ip):
                log("login_blocked", ip=ip)
                return self.send(429, {"error": "too many attempts, wait a few minutes"})
            u, p = body.get("username", ""), body.get("password", "")
            ok_user = isinstance(u, str) and hmac.compare_digest(u.encode(), CONF["user"].encode())
            ok_pass = isinstance(p, str) and len(p) <= 256 and check_password(p, CONF["hash"])
            if not (ok_user and ok_pass):
                record_fail(ip)
                time.sleep(0.4)
                log("login_failed", ip=ip)
                return self.send(401, {"error": "wrong username or password"})
            sid = secrets.token_hex(16)
            now = time.time()
            with LOCK:
                SESSIONS[sid] = {"user": CONF["user"], "created": now, "last": now, "locked": False}
                FAILS.pop(ip, None)
            log("login_ok", ip=ip)
            return self.send(200, {"ok": True, "user": CONF["user"]}, cookie=self.cookie_header(sid))

        sid, s = self.session()
        if path == "/api/logout":
            if s:
                with LOCK:
                    SESSIONS.pop(sid, None)
                log("logout", ip=ip)
            return self.send(200, {"ok": True}, cookie=self.cookie_header(None, clear=True))
        if not s:
            return self.send(401, {"error": "login required"})

        if path == "/api/lock":
            with LOCK:
                SESSIONS[sid]["locked"] = True
            kick_viewers()
            log("lock", ip=ip)
            return self.send(200, {"ok": True, "locked": True})
        if path == "/api/unlock":
            if not s["locked"]:
                return self.send(200, {"ok": True, "locked": False})
            if throttled(ip):
                return self.send(429, {"error": "too many attempts, wait a few minutes"})
            p = body.get("password", "")
            if not (isinstance(p, str) and len(p) <= 256 and check_password(p, CONF["hash"])):
                record_fail(ip)
                time.sleep(0.4)
                log("unlock_failed", ip=ip)
                return self.send(401, {"error": "wrong password"})
            with LOCK:
                SESSIONS[sid]["locked"] = False
                FAILS.pop(ip, None)
            log("unlock", ip=ip)
            return self.send(200, {"ok": True, "locked": False})

        if s["locked"]:
            return self.send(403, {"error": "locked"})
        if path == "/api/settings":
            res, code = apply_settings(body)
            log("settings", ip=ip, applied=res.get("applied"), errors=res.get("errors"))
            return self.send(code, res)
        if path in ("/api/apps/install", "/api/apps/uninstall", "/api/apps/windows"):
            if path == "/api/apps/windows":
                what, job = abix_apps.start_custom(body.get("url", ""))
            elif path == "/api/apps/install":
                what, job = abix_apps.start_install(str(body.get("id", "")))
            else:
                what, job = abix_apps.start_remove(str(body.get("id", "")))
            if what == "ok":
                log("apps", ip=ip, action=path.rsplit("/", 1)[1], job=job["title"])
                return self.send(202, {"ok": True, "job": job["id"]})
            if what == "busy":
                return self.send(409, {"error": "Another install is still running. Wait until it finishes."})
            if what == "unknown":
                return self.send(404, {"error": "unknown app"})
            return self.send(400, {"error": what})          # a readable reason, e.g. "Only https:// links are allowed."
        if path == "/api/launcher/launch":
            code, res = abix_launch.launch(body.get("id"))
            log("launch", ip=ip, app=str(body.get("id"))[:40], code=code)
            return self.send(code, res)
        if path == "/api/ui-prefs":
            res, code = abix_prefs.save(body)
            log("ui_prefs", ip=ip, ok=res.get("ok"))
            return self.send(code, res)
        if path == "/api/files/mkdir":
            parent = safe_path(body.get("path", ""))
            name = clean_name(body.get("name", ""))
            if not parent or not os.path.isdir(parent) or not name:
                return self.send(400, {"error": "bad folder or name"})
            d = os.path.join(parent, name)
            try:
                os.mkdir(d)
                give_to_desktop_user(d)
            except FileExistsError:
                return self.send(409, {"error": "already exists"})
            except OSError as e:
                return self.send(500, {"error": str(e)})
            log("mkdir", ip=ip, folder=rel_of(d))
            return self.send(200, {"ok": True, "path": rel_of(d)})
        if path == "/api/power":
            action = body.get("action")
            if action not in ("restart-session", "restart-desktop", "shutdown"):
                return self.send(400, {"error": "unknown action"})
            log("power", ip=ip, action=action)
            if action == "shutdown":       # "turn off" = end this web session; the container keeps running so files and downloads survive
                with LOCK:
                    SESSIONS.pop(sid, None)
                return self.send(200, {"ok": True, "action": action}, cookie=self.cookie_header(None, clear=True))
            power(action)
            return self.send(200, {"ok": True, "action": action})
        return self.send(404, {"error": "not found"})


def load_conf(path=CONF_PATH):
    # First use a config written by entrypoint.sh.
    if not os.path.isfile(path):
        candidates = ("/etc/abix/backend.json", "/home/abix/.config/abix/backend.json")
        fallback = next((p for p in candidates if os.path.isfile(p)), None)
        if fallback:
            log("config_path_fallback", requested=path, selected=fallback)
            path = fallback
        else:
            # Some managed hosts generate their own Dockerfile and may bypass the
            # repository ENTRYPOINT. Recover from injected environment variables
            # so the API can still start rather than leaving Nginx with a 502.
            user = (os.environ.get("ABIX_ADMIN_USER") or "abixone").strip()
            stored_hash = os.environ.get("ABIX_ADMIN_HASH", "")
            init_password = os.environ.get("ABIX_INIT_PASSWORD", "")
            if not stored_hash and init_password:
                if len(init_password) < 10 or len(init_password) > 256:
                    raise SystemExit("ABIX_INIT_PASSWORD must be 10-256 characters")
                stored_hash = make_hash(init_password)
            if not re.fullmatch(r"pbkdf2:[1-9][0-9]*:[0-9a-f]{32}:[0-9a-f]{64}", stored_hash):
                raise SystemExit("backend config missing; set ABIX_INIT_PASSWORD (10+ characters) or a valid ABIX_ADMIN_HASH")
            secret = os.environ.get("ABIX_SECRET", "")
            if not secret:
                secret_file = "/home/abix/.abix-secret"
                try:
                    os.makedirs(os.path.dirname(secret_file), exist_ok=True)
                    if os.path.isfile(secret_file):
                        with open(secret_file, encoding="utf-8") as f:
                            secret = f.read().strip()
                    else:
                        secret = secrets.token_hex(32)
                        fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        with os.fdopen(fd, "w", encoding="utf-8") as f:
                            f.write(secret)
                except FileExistsError:
                    with open(secret_file, encoding="utf-8") as f:
                        secret = f.read().strip()
                except OSError as e:
                    raise SystemExit("could not create session secret: %s" % e)
            vnc_password = os.environ.get("VNC_PASSWORD", "")
            if not user or len(secret) < 32 or not vnc_password:
                raise SystemExit("backend config missing required ABIX_ADMIN_USER, ABIX_SECRET (32+ chars), or VNC_PASSWORD")
            c = {"user": user, "hash": stored_hash, "secret": secret, "vnc_password": vnc_password}
            log("config_bootstrapped_from_environment", source="environment")
            return c
    with open(path, encoding="utf-8") as f:
        c = json.load(f)
    for k in ("user", "hash", "secret"):
        if not c.get(k):
            raise SystemExit("backend config is missing '%s'" % k)
    if len(c["secret"]) < 32:
        raise SystemExit("secret is too short (need 32+ characters)")
    return c


def make_server(host, port):
    return ThreadingHTTPServer((host, port), Handler)


def main():
    global CONF
    CONF = load_conf()
    port = int(os.environ.get("ABIX_PORT", "8080"))
    srv = make_server(os.environ.get("ABIX_BIND", "0.0.0.0"), port)
    log("started", port=port)
    abix_apps.restore_installed()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
