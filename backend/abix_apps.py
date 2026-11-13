#!/usr/bin/env python3
"""ABIX App Center (Stage 5): install / remove programs and download Windows setup files.

Python standard library only. Imported by abix_api.py (runs as root inside the container).

Three ways to get a program:
  kind "apt"  Ubuntu package from the catalog              -> apt-get install (root)
  kind "deb"  vendor .deb at a FIXED url from the catalog  -> download, apt-get install ./file.deb (root)
  custom url  a Windows setup .exe / .msi you paste        -> download to ~/Downloads, run in Wine as the
                                                             desktop user (never as root)
Custom links can NOT install .deb files: that would hand root to any web page you paste.
Download safety: https only, port 443 only, no user:pass in the link, every redirect is re-checked, the
host must resolve to PUBLIC addresses only (blocks 127.x, 10.x, 172.16.x, 192.168.x, 169.254.x, the Docker
network, ...) and the connection is pinned to the checked address (no DNS rebinding), size limit, time limit.
"""
import http.client
import ipaddress
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import threading
import time
import uuid
from urllib.parse import unquote, urljoin, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG_PATH = os.environ.get("ABIX_APPS_CATALOG", "/usr/local/share/abix/apps-catalog.json")
DESK_USER = os.environ.get("ABIX_DESKTOP_USER", "abix")
DESK_HOME = os.environ.get("ABIX_DESKTOP_HOME", "/home/abix")
APT = os.environ.get("ABIX_APT_GET", "apt-get")
CACHE_DIR = os.environ.get("ABIX_APPS_CACHE", "/var/cache/abix")
MAX_DOWNLOAD = int(float(os.environ.get("ABIX_MAX_DOWNLOAD_MB", "2048")) * 1048576)
DOWNLOAD_SECONDS = 30 * 60
CUSTOM_EXT = (".exe", ".msi")
STATE_REL = os.path.join(".config", "abix", "apps-installed.json")

JOBS = {}            # id -> job dict
JLOCK = threading.Lock()
BUSY = threading.Lock()   # one install at a time (apt cannot run twice)


def arch():
    try:
        return subprocess.run(["dpkg", "--print-architecture"], capture_output=True, text=True, timeout=5).stdout.strip() or "amd64"
    except (OSError, subprocess.TimeoutExpired):
        return "amd64"


# ------------------------------------------------------------------ catalog
def load_catalog(path=None):
    try:
        with open(path or CATALOG_PATH, encoding="utf-8") as f:
            items = json.load(f).get("apps", [])
    except (OSError, ValueError):
        return []
    good = []
    for a in items:
        if not isinstance(a, dict) or not re.fullmatch(r"[a-z0-9-]{1,40}", str(a.get("id", ""))):
            continue
        if a.get("kind") not in ("apt", "deb"):
            continue
        if a["kind"] == "apt" and not (isinstance(a.get("packages"), list) and a["packages"]):
            continue
        if a["kind"] == "deb" and not str(a.get("url", "")).startswith("https://"):
            continue
        good.append(a)
    return good


def find_app(app_id):
    for a in load_catalog():
        if a["id"] == app_id:
            return a
    return None


def is_installed(a):
    c = a.get("check")
    path = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/google/chrome:/usr/share/code/bin"
    return bool(c) and shutil.which(c, path=path) is not None


def app_view(a):
    arch_ok = (not a.get("arch")) or (arch() in a["arch"])
    return {"id": a["id"], "name": a.get("name", a["id"]), "desc": a.get("desc", ""), "category": a.get("category", "Other"),
            "kind": a["kind"], "installed": is_installed(a), "supported": arch_ok,
            "note": "" if arch_ok else "Not available for this CPU (%s)." % arch()}


def wine_available():
    return shutil.which("wine") is not None


# ------------------------------------------------------------------ remembered installs (survive container re-creation)
def state_path():
    return os.path.join(DESK_HOME, STATE_REL)


def read_state():
    try:
        with open(state_path(), encoding="utf-8") as f:
            v = json.load(f)
        return [x for x in v if isinstance(x, str)]
    except (OSError, ValueError):
        return []


def write_state(ids):
    p = state_path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(sorted(set(ids)), f)
        _own(p)
        _own(os.path.dirname(p))
    except OSError:
        pass


def _own(path):
    if not DESK_USER:
        return
    try:
        import pwd
        u = pwd.getpwnam(DESK_USER)
        os.chown(path, u.pw_uid, u.pw_gid)
    except (KeyError, OSError, ImportError):
        pass


# ------------------------------------------------------------------ download (SSRF-safe)
class BadLink(ValueError):
    pass


def check_url(url):
    """Return (host, port, path_with_query). Raises BadLink with a message a person can read."""
    if not isinstance(url, str) or len(url) > 2000 or any(c in url for c in "\r\n\x00 "):
        raise BadLink("That is not a valid link.")
    u = urlparse(url.strip())
    if u.scheme != "https":
        raise BadLink("Only https:// links are allowed.")
    if u.username or u.password:
        raise BadLink("Links with a user name or password are not allowed.")
    if not u.hostname:
        raise BadLink("The link has no host name.")
    if u.port not in (None, 443):
        raise BadLink("Only the normal https port (443) is allowed.")
    path = (u.path or "/") + ("?" + u.query if u.query else "")
    return u.hostname, 443, path


def public_ip(host):
    """Resolve host; every address must be public. Returns one address to connect to."""
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise BadLink("Cannot find the server '%s'." % host)
    addrs = []
    for fam, _, _, _, sa in infos:
        ip = ipaddress.ip_address(sa[0].split("%")[0])
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        if not ip.is_global:          # loopback, private, link-local, multicast, reserved, docker bridge ...
            raise BadLink("That address points to a private or internal network, which is not allowed.")
        addrs.append(str(ip))
    if not addrs:
        raise BadLink("Cannot find the server '%s'." % host)
    return addrs[0]


class PinnedHTTPS(http.client.HTTPSConnection):
    """HTTPS to a host name, but the TCP connection goes to the address we already checked."""
    def __init__(self, host, ip, timeout=30):
        super().__init__(host, 443, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, 443), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def clean_filename(name):
    name = unquote(name or "").replace("\\", "/").split("/")[-1].strip()
    name = re.sub(r"[^A-Za-z0-9._ ()+-]", "_", name).strip(" .")
    return name[:120] or "download"


def disposition_name(header):
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", header or "", re.I)
    return m.group(1) if m else None


def unique_path(folder, name):
    base, ext = os.path.splitext(name)
    p, n = os.path.join(folder, name), 1
    while os.path.exists(p):
        p = os.path.join(folder, "%s-%d%s" % (base, n, ext)); n += 1
    return p


def download(url, folder, allowed_ext, progress, max_bytes=None, forced_name=None):
    """Download url into folder. Returns the file path. progress(done, total) is called now and then."""
    max_bytes = max_bytes or MAX_DOWNLOAD
    t0 = time.time()
    for _hop in range(6):
        host, _port, path = check_url(url)
        conn = PinnedHTTPS(host, public_ip(host))
        try:
            conn.request("GET", path, headers={"Host": host, "User-Agent": "ABIX-AppCenter/5", "Accept": "*/*"})
            r = conn.getresponse()
            if r.status in (301, 302, 303, 307, 308):
                loc = r.getheader("Location")
                if not loc:
                    raise BadLink("The server sent a broken redirect.")
                url = urljoin(url, loc)
                continue
            if r.status != 200:
                raise BadLink("The server answered %d %s." % (r.status, r.reason))
            total = int(r.getheader("Content-Length") or 0)
            if total and total > max_bytes:
                raise BadLink("The file is too large (limit %d MB)." % (max_bytes // 1048576))
            name = forced_name or clean_filename(disposition_name(r.getheader("Content-Disposition")) or urlparse(url).path)
            if allowed_ext and not name.lower().endswith(allowed_ext):
                raise BadLink("Only %s files can be installed this way (this link gives '%s')." % (" / ".join(allowed_ext), name))
            os.makedirs(folder, exist_ok=True)
            dest = unique_path(folder, name)
            tmp = dest + ".abix-part"
            done = 0
            try:
                with open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(262144)
                        if not chunk:
                            break
                        done += len(chunk)
                        if done > max_bytes:
                            raise BadLink("The file is too large (limit %d MB)." % (max_bytes // 1048576))
                        if time.time() - t0 > DOWNLOAD_SECONDS:
                            raise BadLink("The download took too long and was stopped.")
                        f.write(chunk)
                        progress(done, total)
                os.replace(tmp, dest)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
            return dest
        finally:
            conn.close()
    raise BadLink("Too many redirects.")


def sniff(path, kind):
    """Cheap check that the file really is what the link claimed."""
    with open(path, "rb") as f:
        head = f.read(8)
    if kind == ".exe":
        return head[:2] == b"MZ"
    if kind == ".msi":
        return head[:4] == b"\xd0\xcf\x11\xe0"
    if kind == ".deb":
        return head[:7] == b"!<arch>"
    return False


# ------------------------------------------------------------------ jobs
def new_job(title, kind):
    j = {"id": uuid.uuid4().hex[:12], "title": title, "kind": kind, "state": "running", "percent": 0,
         "message": "Starting…", "log": [], "started": int(time.time()), "finished": None}
    with JLOCK:
        JOBS[j["id"]] = j
        for old in sorted(JOBS.values(), key=lambda x: x["started"])[:-12]:     # keep the last 12
            JOBS.pop(old["id"], None)
    return j


def upd(j, **kw):
    with JLOCK:
        j.update(kw)


def logline(j, line):
    line = line.rstrip()[:300]
    if line:
        with JLOCK:
            j["log"] = (j["log"] + [line])[-40:]


def finish(j, ok, message):
    upd(j, state="done" if ok else "failed", message=message, percent=100 if ok else j["percent"], finished=int(time.time()))


def job_view(j, with_log=True):
    with JLOCK:
        d = {k: j[k] for k in ("id", "title", "kind", "state", "percent", "message", "started", "finished")}
        if with_log:
            d["log"] = list(j["log"])
        return d


def list_jobs():
    with JLOCK:
        return [job_view_nolock(j) for j in sorted(JOBS.values(), key=lambda x: -x["started"])[:6]]


def job_view_nolock(j):
    return {k: j[k] for k in ("id", "title", "kind", "state", "percent", "message", "started", "finished")}


def get_job(jid):
    with JLOCK:
        j = JOBS.get(jid)
    return job_view(j) if j else None


def run_cmd(j, args, step_from, step_to):
    """Run a root command, stream its output into the job log, move the progress bar slowly forward."""
    env = {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "DEBIAN_FRONTEND": "noninteractive", "LANG": "C.UTF-8"}
    try:
        p = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    except OSError as e:
        logline(j, str(e)); return 127
    pct, n = step_from, 0
    for line in p.stdout:
        logline(j, line)
        n += 1
        if n % 6 == 0 and pct < step_to - 1:
            pct += 1; upd(j, percent=pct)
    return p.wait()


def apt_update(j):
    upd(j, message="Updating the package list…", percent=5)
    return run_cmd(j, [APT, "update"], 5, 18)


def work_install_catalog(j, a):
    try:
        with BUSY:
            if not (not a.get("arch") or arch() in a["arch"]):
                return finish(j, False, "%s is not available for this CPU (%s)." % (a["name"], arch()))
            if apt_update(j) != 0:
                logline(j, "apt-get update failed (no internet?). Trying to install anyway.")
            if a["kind"] == "apt":
                upd(j, message="Installing %s…" % a["name"], percent=20)
                rc = run_cmd(j, [APT, "install", "-y", "--no-install-recommends"] + list(a["packages"]), 20, 95)
            else:
                os.makedirs(CACHE_DIR, mode=0o755, exist_ok=True)
                os.chmod(CACHE_DIR, 0o755)
                upd(j, message="Downloading %s…" % a["name"], percent=20)

                def prog(done, total):
                    if total:
                        upd(j, percent=20 + int(done * 40 / total), message="Downloading %s… %d MB" % (a["name"], done // 1048576))
                path = download(a["url"], CACHE_DIR, (".deb",), prog, forced_name="%s.deb" % a["id"])
                os.chmod(path, 0o644)
                if not sniff(path, ".deb"):
                    os.remove(path)
                    return finish(j, False, "The download is not a .deb package.")
                upd(j, message="Installing %s…" % a["name"], percent=62)
                rc = run_cmd(j, [APT, "install", "-y", "--no-install-recommends", path], 62, 95)
                try:
                    os.remove(path)
                except OSError:
                    pass
            if rc == 0 and is_installed(a):
                write_state(read_state() + [a["id"]])
                return finish(j, True, "%s is installed. Find it in the Start menu." % a["name"])
            finish(j, False, "Installing %s failed. See the details below." % a["name"])
    except BadLink as e:
        finish(j, False, str(e))
    except Exception as e:                      # a job thread must never die silently
        logline(j, repr(e)); finish(j, False, "Unexpected error: %s" % e)


def work_remove_catalog(j, a):
    try:
        with BUSY:
            upd(j, message="Removing %s…" % a["name"], percent=10)
            pk = a.get("remove") or a.get("packages") or []
            rc = run_cmd(j, [APT, "remove", "-y"] + list(pk), 10, 90)
            if rc == 0:
                write_state([x for x in read_state() if x != a["id"]])
                return finish(j, True, "%s was removed." % a["name"])
            finish(j, False, "Removing %s failed. See the details below." % a["name"])
    except Exception as e:
        logline(j, repr(e)); finish(j, False, "Unexpected error: %s" % e)


def launch_wine(path):
    """Start a Windows installer in Wine as the desktop user (never root). Returns (ok, message)."""
    if not wine_available():
        return False, "Wine is not installed in this image (build with ABIX_WINE=1). The file is saved in Downloads."
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": DESK_HOME, "DISPLAY": ":1", "XDG_RUNTIME_DIR": "/tmp/runtime-abix",
           "LANG": "C.UTF-8", "WINEDEBUG": "-all", "WINEDLLOVERRIDES": "winemenubuilder.exe=d;mscoree,mshtml="}
    cmd = ["wine", "msiexec", "/i", path] if path.lower().endswith(".msi") else ["wine", "start", "/unix", path]
    kw = {}
    if DESK_USER and os.geteuid() == 0:
        kw = {"user": DESK_USER, "group": DESK_USER, "extra_groups": []}
    try:
        log = open(os.path.join(DESK_HOME, ".cache", "abix-wine.log"), "ab") if os.path.isdir(os.path.join(DESK_HOME, ".cache")) else subprocess.DEVNULL
        subprocess.Popen(cmd, env=env, cwd=os.path.dirname(path), stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True, **kw)
    except OSError as e:
        return False, "Could not start Wine: %s" % e
    return True, "The installer is opening on your desktop (the first start of Wine can take a minute). Windows programs run in Wine; simple ones work, many games and anti-cheat programs do not."


def work_custom_exe(j, url):
    try:
        folder = os.path.join(DESK_HOME, "Downloads")
        upd(j, message="Checking the link…", percent=3)

        def prog(done, total):
            upd(j, percent=5 + (int(done * 85 / total) if total else min(80, done // 5242880)), message="Downloading… %d MB" % (done // 1048576))
        path = download(url, folder, CUSTOM_EXT, prog)
        _own(path)
        ext = os.path.splitext(path)[1].lower()
        if not sniff(path, ext):
            os.remove(path)
            return finish(j, False, "The download is not a real Windows installer (wrong file type). It was deleted.")
        logline(j, "Saved: Downloads/" + os.path.basename(path))
        upd(j, message="Starting the installer in Wine…", percent=94)
        ok, msg = launch_wine(path)
        finish(j, ok, ("Downloaded %s. " % os.path.basename(path)) + msg)
    except BadLink as e:
        finish(j, False, str(e))
    except Exception as e:
        logline(j, repr(e)); finish(j, False, "Unexpected error: %s" % e)


def start(target, *args, title="", kind=""):
    """Create a job and run target(job, *args) in a thread. Returns the job, or None if one is already running."""
    with JLOCK:
        if any(x["state"] == "running" for x in JOBS.values()):
            return None
    j = new_job(title, kind)
    threading.Thread(target=target, args=(j,) + args, daemon=True).start()
    return j


def start_install(app_id):
    a = find_app(app_id)
    if not a:
        return "unknown", None
    j = start(work_install_catalog, a, title="Install " + a["name"], kind="install")
    return ("busy", None) if j is None else ("ok", j)


def start_remove(app_id):
    a = find_app(app_id)
    if not a:
        return "unknown", None
    j = start(work_remove_catalog, a, title="Remove " + a["name"], kind="remove")
    return ("busy", None) if j is None else ("ok", j)


def start_custom(url):
    try:
        host, _, _ = check_url(url)
    except BadLink as e:
        return str(e), None
    j = start(work_custom_exe, url, title="Windows setup from " + host, kind="windows")
    return ("busy", None) if j is None else ("ok", j)


def restore_installed():
    """At start-up: catalog apps that were installed before but are gone (container was re-created) come back."""
    if os.environ.get("ABIX_APPS_RESTORE", "1") == "0":
        return
    def run():
        time.sleep(40)                     # let the desktop and the network come up first
        for app_id in read_state():
            a = find_app(app_id)
            if a and not is_installed(a):
                j = new_job("Restore " + a["name"], "restore")
                work_install_catalog(j, a)
    threading.Thread(target=run, daemon=True).start()
