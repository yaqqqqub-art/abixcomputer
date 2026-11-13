#!/usr/bin/env python3
"""HTTP-level test of the V6 routes /api/launcher, /api/launcher/launch, /api/ui-prefs (auth, CSRF, locked, validation).
    python3 tests/unit/test_launch_api.py"""
import http.client, json, os, sys, tempfile, threading, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))
T = tempfile.mkdtemp()
BIN = os.path.join(T, "bin"); os.makedirs(BIN)
os.environ.update(ABIX_DESKTOP_USER="", ABIX_DESKTOP_HOME=T, ABIX_LAUNCH_PATH=BIN, ABIX_COOKIE_SECURE="1", ABIX_CTL="/bin/true")
import abix_api as A  # noqa: E402
import abix_launch as L  # noqa: E402
L.LAUNCH_GAP = 0
p = os.path.join(BIN, "handoff"); open(p, "w").write("#!/bin/bash\nexit 0\n"); os.chmod(p, 0o755)
L.CATALOG[:] = [L._a("t-hand", "Handoff", "d", "Internet", "native", ["handoff"], ["handoff"]),
                L._a("t-win", "Win", "d", "Creativity", "windows")]
A.CONF.update({"user": "admin", "hash": A.make_hash("pw-12345"), "secret": "x" * 40, "vnc_password": "v"})
SRV = A.make_server("127.0.0.1", 0); PORT = SRV.server_address[1]
threading.Thread(target=SRV.serve_forever, daemon=True).start()


def call(method, path, body=None, cookie=None, csrf=True):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
    h = {"Content-Type": "application/json"} if method == "POST" else {}
    if method == "POST" and csrf:
        h["X-Abix"] = "1"
    if cookie:
        h["Cookie"] = cookie
    c.request(method, path, json.dumps(body) if body is not None else None, h)
    r = c.getresponse(); d = r.read()
    try:
        return r.status, json.loads(d), r
    except ValueError:
        return r.status, None, r


def login():
    s, _, r = call("POST", "/api/login", {"username": "admin", "password": "pw-12345"})
    return r.getheader("Set-Cookie").split(";")[0]


class Api(unittest.TestCase):
    def test_requires_login(self):
        self.assertEqual(call("GET", "/api/launcher")[0], 401)
        self.assertEqual(call("GET", "/api/ui-prefs")[0], 401)
        self.assertEqual(call("POST", "/api/launcher/launch", {"id": "t-hand"})[0], 401)
        self.assertEqual(call("POST", "/api/ui-prefs", {"logo_anim": "off"})[0], 401)

    def test_list_and_launch(self):
        ck = login()
        s, j, _ = call("GET", "/api/launcher", cookie=ck)
        self.assertEqual(s, 200); self.assertEqual({i["id"]: i["state"] for i in j["items"]}, {"t-hand": "installed", "t-win": "windows_only"})
        self.assertNotIn("cmd", j["items"][0])          # commands never leave the server
        s, j, _ = call("POST", "/api/launcher/launch", {"id": "t-hand"}, cookie=ck)
        self.assertEqual((s, j["state"]), (200, "started"))
        self.assertEqual(call("POST", "/api/launcher/launch", {"id": "t-win"}, cookie=ck)[0], 409)       # Windows-only: honest refusal
        self.assertEqual(call("POST", "/api/launcher/launch", {"id": "../../bin/sh"}, cookie=ck)[0], 404)  # only catalog ids
        self.assertEqual(call("POST", "/api/launcher/launch", {"cmd": "rm -rf /"}, cookie=ck)[0], 404)

    def test_csrf_header_required(self):
        ck = login()
        self.assertEqual(call("POST", "/api/launcher/launch", {"id": "t-hand"}, cookie=ck, csrf=False)[0], 400)
        self.assertEqual(call("POST", "/api/ui-prefs", {"logo_anim": "off"}, cookie=ck, csrf=False)[0], 400)

    def test_prefs_roundtrip_and_validation(self):
        ck = login()
        s, j, _ = call("POST", "/api/ui-prefs", {"logo_style": "bloom", "logo_anim": "full"}, cookie=ck)
        self.assertEqual(s, 200)
        s, j, _ = call("GET", "/api/ui-prefs", cookie=ck)
        self.assertEqual((j["prefs"]["logo_style"], j["prefs"]["logo_anim"]), ("bloom", "full"))
        self.assertEqual(call("POST", "/api/ui-prefs", {"logo_style": "<script>"}, cookie=ck)[0], 400)
        self.assertEqual(call("POST", "/api/ui-prefs", {"evil": 1}, cookie=ck)[0], 400)

    def test_blocked_while_locked(self):
        ck = login()
        self.assertEqual(call("POST", "/api/lock", {}, cookie=ck)[0], 200)
        self.assertEqual(call("GET", "/api/launcher", cookie=ck)[0], 403)
        self.assertEqual(call("POST", "/api/launcher/launch", {"id": "t-hand"}, cookie=ck)[0], 403)
        self.assertEqual(call("POST", "/api/ui-prefs", {"logo_anim": "off"}, cookie=ck)[0], 403)


if __name__ == "__main__":
    unittest.main(verbosity=1)
