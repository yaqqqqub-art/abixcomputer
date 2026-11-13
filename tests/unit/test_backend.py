#!/usr/bin/env python3
"""Real HTTP test of backend/abix_api.py with a FAKE abix-ctl (no Docker, no desktop needed).
    python3 tests/unit/test_backend.py
"""
import http.client, json, os, stat, sys, tempfile, threading, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))
T = tempfile.mkdtemp()
FAKE = os.path.join(T, "abix-ctl")
with open(FAKE, "w") as f:
    f.write('#!/bin/bash\necho "$@" >> "%s/ctl.log"\n'
            'case "$1" in\n status) echo \'{"settings":{"THEME":"light","ANIMATION":"light","ACCENT":"#0067c0","WALLPAPER":"/x/abix-ocean.jpg"},'
            '"active":{"animation":{"effective":"picom-light"}},"detected":{"whisker_menu":true,"picom":true}}\';;\n'
            ' anim) echo \'{"effective":"picom-"\'$2\'}\';;\n *) echo \'{"ok":true}\';;\nesac\n' % T)
os.chmod(FAKE, 0o755)
WALLS = os.path.join(T, "walls"); os.makedirs(WALLS)
open(os.path.join(WALLS, "abix-ocean.jpg"), "wb").write(b"\xff\xd8JPEGDATA")
open(os.path.join(WALLS, "notes.txt"), "w").write("x")
os.environ.update(ABIX_CTL=FAKE, ABIX_DESKTOP_USER="", ABIX_DESKTOP_HOME=T, ABIX_SYS_WALLS=WALLS, ABIX_COOKIE_SECURE="1")
import abix_api as A  # noqa: E402
A.CONF.update({"user": "admin", "hash": A.make_hash("s3cret-pass"), "secret": "x" * 40, "vnc_password": "vncpw123"})
A.power = lambda a: a in ("restart-session", "restart-desktop")      # never kill real processes in a test
A.kick_viewers = lambda: open(os.path.join(T, "kicked"), "w").write("1")
SRV = A.make_server("127.0.0.1", 0)
PORT = SRV.server_address[1]
threading.Thread(target=SRV.serve_forever, daemon=True).start()
H = {"Content-Type": "application/json", "X-Abix": "1"}


def call(method, path, body=None, cookie=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
    h = dict(H if method == "POST" else {})
    h.update(headers or {})
    if cookie:
        h["Cookie"] = cookie
    c.request(method, path, json.dumps(body) if body is not None else None, h)
    r = c.getresponse(); data = r.read()
    try:
        j = json.loads(data)
    except ValueError:
        j = None
    return r.status, j, r, data


def login(pw="s3cret-pass", ip="9.9.9.9"):
    s, j, r, _ = call("POST", "/api/login", {"username": "admin", "password": pw}, headers={"X-Real-IP": ip})
    ck = r.getheader("Set-Cookie")
    return s, (ck.split(";")[0] if ck else None), ck


class T1(unittest.TestCase):
    def test_01_health_and_unauthenticated(self):
        self.assertEqual(call("GET", "/api/health")[0], 200)
        self.assertEqual(call("GET", "/api/auth/check")[0], 401)
        self.assertEqual(call("GET", "/api/settings")[0], 401)
        self.assertEqual(call("GET", "/api/connect")[0], 401)
        self.assertEqual(call("GET", "/api/session")[1], {"authenticated": False})

    def test_02_csrf_header_required(self):
        c = http.client.HTTPConnection("127.0.0.1", PORT)
        c.request("POST", "/api/login", json.dumps({"username": "admin", "password": "s3cret-pass"}), {"Content-Type": "application/json"})
        self.assertEqual(c.getresponse().status, 400)
        c = http.client.HTTPConnection("127.0.0.1", PORT)
        c.request("POST", "/api/login", "u=a&p=b", {"X-Abix": "1", "Content-Type": "text/plain"})
        self.assertEqual(c.getresponse().status, 400)

    def test_03_wrong_password_and_throttle(self):
        for _ in range(5):
            self.assertEqual(login("bad", ip="1.2.3.4")[0], 401)
        self.assertEqual(login("s3cret-pass", ip="1.2.3.4")[0], 429)      # even the right password is blocked
        self.assertEqual(login("s3cret-pass", ip="5.6.7.8")[0], 200)      # other address unaffected

    def test_04_login_cookie_flags_and_forgery(self):
        s, ck, full = login()
        self.assertEqual(s, 200)
        for flag in ("HttpOnly", "Secure", "SameSite=Strict"):
            self.assertIn(flag, full)
        self.assertEqual(call("GET", "/api/auth/check", cookie=ck)[0], 200)
        sid = ck.split("=")[1].split(".")[0]
        self.assertEqual(call("GET", "/api/auth/check", cookie="abix_session=%s.%s" % (sid, "0" * 40))[0], 401)
        self.assertEqual(call("GET", "/api/auth/check", cookie="abix_session=%s.%s" % ("a" * 32, A.sign("a" * 32)))[0], 401)

    def test_05_settings_and_wallpapers(self):
        _, ck, _ = login()
        s, j, *_ = call("GET", "/api/settings", cookie=ck)
        self.assertEqual((s, j["theme"], j["start_menu"], j["active_animation"]), (200, "light", "whisker", "picom-light"))
        self.assertEqual(call("POST", "/api/settings", {"theme": "dark", "animation": "full", "accent": "#12ABef"}, cookie=ck)[0], 200)
        log = open(os.path.join(T, "ctl.log")).read()
        self.assertIn("theme dark", log); self.assertIn("anim full", log); self.assertIn("accent #12ABef", log)
        for bad in ({"theme": "pink"}, {"accent": "red;rm -rf /"}, {"accent": "#12345"}, {"animation": "x"},
                    {"wallpaper": "sys-../../etc/passwd"}, {"wallpaper": "sys-notes.txt"}, {"wallpaper": "user-nothere.jpg"}, {"hack": 1}):
            self.assertEqual(call("POST", "/api/settings", bad, cookie=ck)[0], 400, bad)
        self.assertNotIn("pink", open(os.path.join(T, "ctl.log")).read())
        items = call("GET", "/api/wallpapers", cookie=ck)[1]["items"]
        self.assertEqual([i["id"] for i in items], ["sys-abix-ocean.jpg"])
        self.assertEqual(call("POST", "/api/settings", {"wallpaper": "sys-abix-ocean.jpg"}, cookie=ck)[0], 200)
        self.assertIn("wallpaper " + os.path.join(WALLS, "abix-ocean.jpg"), open(os.path.join(T, "ctl.log")).read())
        s, _, r, data = call("GET", "/api/wallpaper/sys-abix-ocean.jpg", cookie=ck)
        self.assertEqual((s, r.getheader("Content-Type"), data[:2]), (200, "image/jpeg", b"\xff\xd8"))
        self.assertEqual(call("GET", "/api/wallpaper/sys-..%2f..%2fetc%2fpasswd", cookie=ck)[0], 404)

    def test_06_lock_unlock(self):
        _, ck, _ = login()
        self.assertEqual(call("GET", "/api/connect", cookie=ck)[1], {"password": "vncpw123"})
        self.assertEqual(call("POST", "/api/lock", {}, cookie=ck)[0], 200)
        self.assertTrue(os.path.exists(os.path.join(T, "kicked")))           # viewers were disconnected
        self.assertEqual(call("GET", "/api/auth/check", cookie=ck)[0], 403)   # Nginx would refuse /desktop/
        self.assertEqual(call("GET", "/api/connect", cookie=ck)[0], 403)      # no VNC password while locked
        self.assertEqual(call("GET", "/api/settings", cookie=ck)[0], 403)
        self.assertEqual(call("POST", "/api/settings", {"theme": "dark"}, cookie=ck)[0], 403)
        self.assertEqual(call("POST", "/api/power", {"action": "restart-session"}, cookie=ck)[0], 403)
        self.assertEqual(call("GET", "/api/session", cookie=ck)[1]["locked"], True)
        self.assertEqual(call("POST", "/api/unlock", {"password": "nope"}, cookie=ck, headers={"X-Real-IP": "7.7.7.7"})[0], 401)
        self.assertEqual(call("POST", "/api/unlock", {"password": "s3cret-pass"}, cookie=ck, headers={"X-Real-IP": "7.7.7.7"})[0], 200)
        self.assertEqual(call("GET", "/api/auth/check", cookie=ck)[0], 200)

    def test_07_power_and_logout(self):
        _, ck, _ = login()
        self.assertEqual(call("POST", "/api/power", {"action": "rm -rf /"}, cookie=ck)[0], 400)
        self.assertEqual(call("POST", "/api/power", {"action": "restart-session"}, cookie=ck)[0], 200)
        self.assertEqual(call("POST", "/api/power", {"action": "restart-desktop"}, cookie=ck)[0], 200)
        self.assertEqual(call("POST", "/api/logout", {}, cookie=ck)[0], 200)
        self.assertEqual(call("GET", "/api/auth/check", cookie=ck)[0], 401)   # session is really gone server-side

    def test_08_expiry_and_limits(self):
        _, ck, _ = login()
        sid = ck.split("=")[1].split(".")[0]
        A.SESSIONS[sid]["last"] -= A.IDLE_SECONDS + 5
        self.assertEqual(call("GET", "/api/auth/check", cookie=ck)[0], 401)
        c = http.client.HTTPConnection("127.0.0.1", PORT)
        c.request("POST", "/api/login", "x" * 20000, H)
        self.assertEqual(c.getresponse().status, 400)

    def test_09_hash_format(self):
        h = A.make_hash("pw")
        self.assertTrue(h.startswith("pbkdf2:") and "$" not in h)           # no "$": safe inside .env / compose
        self.assertTrue(A.check_password("pw", h)); self.assertFalse(A.check_password("pw2", h))
        self.assertFalse(A.check_password("pw", "garbage"))


class T2Files(unittest.TestCase):
    """Stage 3: file browse / download / upload must stay inside the desktop home."""
    @classmethod
    def setUpClass(cls):
        os.makedirs(os.path.join(T, "Downloads"), exist_ok=True)
        os.makedirs(os.path.join(T, ".ssh"), exist_ok=True)
        open(os.path.join(T, "Downloads", "hello.txt"), "w").write("hi there")
        open(os.path.join(T, ".ssh", "id_rsa"), "w").write("SECRET")
        outside = tempfile.mkdtemp(); open(os.path.join(outside, "pw.txt"), "w").write("OUTSIDE")
        try:
            os.symlink(outside, os.path.join(T, "Downloads", "escape"))
        except OSError:
            pass

    def raw(self, method, path, body=None, cookie=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
        h = {"Cookie": cookie} if cookie else {}
        h.update(headers or {})
        c.request(method, path, body, h)
        r = c.getresponse(); d = r.read()
        return r.status, d

    def test_10_requires_login(self):
        self.assertEqual(self.raw("GET", "/api/files?path=Downloads")[0], 401)
        self.assertEqual(self.raw("GET", "/api/files/download?path=Downloads/hello.txt")[0], 401)
        self.assertEqual(self.raw("POST", "/api/files/upload?path=Downloads&name=a.txt", b"x", None, {"X-Abix": "1"})[0], 401)

    def test_11_list_and_download(self):
        _, ck, _ = login(ip="8.8.1.1")
        st, d = self.raw("GET", "/api/files?path=Downloads", cookie=ck)
        self.assertEqual(st, 200)
        names = [i["name"] for i in json.loads(d)["items"]]
        self.assertIn("hello.txt", names)
        st, d = self.raw("GET", "/api/files/download?path=Downloads/hello.txt", cookie=ck)
        self.assertEqual((st, d), (200, b"hi there"))

    def test_12_traversal_blocked(self):
        _, ck, _ = login(ip="8.8.1.2")
        for bad in ("../etc/passwd", "Downloads/../../etc/passwd", "/etc/passwd", ".ssh/id_rsa", "Downloads/escape/pw.txt", "%2e%2e/x"):
            st, d = self.raw("GET", "/api/files/download?path=" + bad, cookie=ck)
            self.assertEqual(st, 404, bad)
            self.assertNotIn(b"SECRET", d); self.assertNotIn(b"OUTSIDE", d)
        self.assertEqual(self.raw("GET", "/api/files?path=../", cookie=ck)[0], 404)
        self.assertEqual(self.raw("GET", "/api/files?path=.ssh", cookie=ck)[0], 404)

    def test_13_upload(self):
        _, ck, _ = login(ip="8.8.1.3")
        hd = {"X-Abix": "1", "Content-Type": "application/octet-stream"}
        st, d = self.raw("POST", "/api/files/upload?path=Downloads&name=up.bin", b"A" * 5000, ck, hd)
        self.assertEqual(st, 200, d)
        self.assertEqual(open(os.path.join(T, "Downloads", "up.bin"), "rb").read(), b"A" * 5000)
        self.assertFalse(os.path.exists(os.path.join(T, "Downloads", "up.bin.abix-part")))
        # name tricks stay inside the folder
        st, d = self.raw("POST", "/api/files/upload?path=Downloads&name=../../evil.txt", b"x", ck, hd)
        self.assertEqual(st, 200)
        self.assertTrue(os.path.exists(os.path.join(T, "Downloads", "evil.txt")))
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(T), "evil.txt")))
        # no CSRF header -> rejected; outside folder -> rejected; too big -> rejected
        self.assertEqual(self.raw("POST", "/api/files/upload?path=Downloads&name=n.txt", b"x", ck, {})[0], 400)
        self.assertEqual(self.raw("POST", "/api/files/upload?path=../&name=n.txt", b"x", ck, hd)[0], 400)
        old = A.MAX_UPLOAD; A.MAX_UPLOAD = 10
        try:
            self.assertEqual(self.raw("POST", "/api/files/upload?path=Downloads&name=big.txt", b"x" * 50, ck, hd)[0], 413)
        finally:
            A.MAX_UPLOAD = old

    def test_14_mkdir_and_locked(self):
        _, ck, _ = login(ip="8.8.1.4")
        self.assertEqual(call("POST", "/api/files/mkdir", {"path": "Downloads", "name": "Games"}, cookie=ck)[0], 200)
        self.assertTrue(os.path.isdir(os.path.join(T, "Downloads", "Games")))
        self.assertEqual(call("POST", "/api/files/mkdir", {"path": "Downloads", "name": "../x"}, cookie=ck)[0], 200)  # basename only
        self.assertEqual(call("POST", "/api/files/mkdir", {"path": "../", "name": "x"}, cookie=ck)[0], 400)
        call("POST", "/api/lock", {}, cookie=ck)
        self.assertEqual(self.raw("GET", "/api/files?path=Downloads", cookie=ck)[0], 403)
        self.assertEqual(self.raw("POST", "/api/files/upload?path=Downloads&name=l.txt", b"x", ck, {"X-Abix": "1"})[0], 403)

    def test_15_shutdown_ends_session(self):
        _, ck, _ = login(ip="8.8.1.5")
        st, j, r, _ = call("POST", "/api/power", {"action": "shutdown"}, cookie=ck)
        self.assertEqual(st, 200)
        self.assertEqual(call("GET", "/api/auth/check", cookie=ck)[0], 401)


if __name__ == "__main__":
    unittest.main(verbosity=1)
