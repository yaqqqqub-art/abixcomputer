#!/usr/bin/env python3
"""Tests for the Stage 5 App Center (backend/abix_apps.py + its API routes). No Docker, no internet.
    python3 tests/unit/test_apps.py
The network layer is replaced by a tiny local HTTP server; apt-get is replaced by a fake script."""
import http.client, http.server, json, os, sys, tempfile, threading, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))
T = tempfile.mkdtemp()
FAKE_APT = os.path.join(T, "apt-get")
with open(FAKE_APT, "w") as f:
    f.write('#!/bin/bash\necho "apt-get $@" >> "%s/apt.log"\nfor i in 1 2 3 4 5 6 7 8; do echo "line $i"; done\n[ -f "%s/apt-fail" ] && exit 100\nexit 0\n' % (T, T))
os.chmod(FAKE_APT, 0o755)
CAT = os.path.join(T, "catalog.json")
json.dump({"apps": [
    {"id": "good", "name": "Good", "kind": "apt", "packages": ["good"], "check": "sh", "remove": ["good"], "category": "Test"},
    {"id": "never", "name": "Never", "kind": "apt", "packages": ["never"], "check": "no-such-program-xyz", "category": "Test"},
    {"id": "arm-only", "name": "ArmOnly", "kind": "apt", "packages": ["x"], "check": "no-such-program-xyz", "arch": ["arm64-only-test"]},
    {"id": "BAD ID", "name": "x", "kind": "apt", "packages": ["x"]},
    {"id": "http-deb", "name": "x", "kind": "deb", "url": "http://insecure/x.deb"},
    {"id": "evil", "name": "x", "kind": "shell", "packages": ["x"]}]}, open(CAT, "w"))
HOME = os.path.join(T, "home"); os.makedirs(os.path.join(HOME, "Downloads"))
os.environ.update(ABIX_APT_GET=FAKE_APT, ABIX_APPS_CATALOG=CAT, ABIX_DESKTOP_USER="", ABIX_DESKTOP_HOME=HOME,
                  ABIX_APPS_CACHE=os.path.join(T, "cache"), ABIX_BACKEND_CONF="/nonexistent", ABIX_CTL="/bin/true",
                  ABIX_SYS_WALLS=T, ABIX_COOKIE_SECURE="1")
import abix_apps as P   # noqa: E402
import abix_api as A    # noqa: E402


def wait_done(jid, secs=10):
    t = time.time()
    while time.time() - t < secs:
        j = P.get_job(jid)
        if j and j["state"] != "running":
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


class Links(unittest.TestCase):
    def test_accepts_plain_https(self):
        self.assertEqual(P.check_url("https://example.com/a/setup.exe?x=1"), ("example.com", 443, "/a/setup.exe?x=1"))

    def test_rejects_bad_links(self):
        for u in ("http://example.com/a.exe", "ftp://example.com/a.exe", "file:///etc/passwd", "https://user:pw@example.com/a.exe",
                  "https://example.com:8443/a.exe", "https://example.com/a b.exe", "https://example.com/a\r\nHost: x", "", "javascript:alert(1)", None, 5, "https:///a.exe"):
            with self.assertRaises(P.BadLink, msg=repr(u)):
                P.check_url(u)

    def test_private_addresses_blocked(self):
        for h in ("localhost", "127.0.0.1", "10.0.0.5", "192.168.1.1", "172.17.0.2", "169.254.169.254", "0.0.0.0", "::1", "[::1]"):
            with self.assertRaises(P.BadLink, msg=h):
                P.public_ip(h.strip("[]"))

    def test_filenames(self):
        self.assertEqual(P.clean_filename("../../etc/passwd"), "passwd")
        self.assertEqual(P.clean_filename("set%20up.exe"), "set up.exe")
        self.assertEqual(P.clean_filename("a;b|c&d.exe"), "a_b_c_d.exe")
        self.assertEqual(P.clean_filename(""), "download")
        self.assertEqual(P.disposition_name('attachment; filename="Setup 1.exe"'), "Setup 1.exe")
        self.assertEqual(P.disposition_name("attachment; filename*=UTF-8''x.exe"), "x.exe")

    def test_sniff(self):
        p = os.path.join(T, "s.bin")
        for data, kind, want in ((b"MZ\x90\x00", ".exe", True), (b"PK\x03\x04", ".exe", False), (b"!<arch>\n", ".deb", True),
                                 (b"MZ", ".deb", False), (b"\xd0\xcf\x11\xe0xx", ".msi", True), (b"MZ", ".msi", False)):
            open(p, "wb").write(data)
            self.assertEqual(P.sniff(p, kind), want, (data, kind))


class FakeSite(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == "/redir":
            self.send_response(302); self.send_header("Location", "/setup.exe"); self.send_header("Content-Length", "0"); self.end_headers(); return
        if self.path == "/setup.exe":
            body = b"MZ" + b"\x00" * 5000
        elif self.path == "/fake.exe":
            body = b"<html>not an exe</html>"
        elif self.path == "/big.exe":
            body = b"MZ" + b"\x00" * 3 * 1048576
        elif self.path == "/archive.zip":
            body = b"PK"
        else:
            self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


class Downloads(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeSite)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        class Plain(http.client.HTTPConnection):          # same interface as PinnedHTTPS, no TLS, goes to the local site
            def __init__(s, host, ip, timeout=30): super().__init__("127.0.0.1", cls.port, timeout=timeout)
        cls.saved = (P.PinnedHTTPS, P.public_ip, P.check_url)
        P.PinnedHTTPS = Plain; P.public_ip = lambda h: "127.0.0.1"
        P.check_url = lambda u: ("site.test", 443, "/" + u.split("/", 3)[-1].split("?")[0] if "/" in u[8:] else "/")
        P.launch_wine = lambda path: (True, "launched %s" % os.path.basename(path))

    @classmethod
    def tearDownClass(cls):
        P.PinnedHTTPS, P.public_ip, P.check_url = cls.saved
        cls.srv.shutdown()

    def test_download_follows_redirect_and_saves(self):
        seen = []
        path = P.download("https://site.test/redir", os.path.join(T, "dl"), (".exe",), lambda d, t: seen.append(d))
        self.assertTrue(path.endswith("setup.exe")); self.assertEqual(os.path.getsize(path), 5002); self.assertTrue(seen)
        self.assertFalse([f for f in os.listdir(os.path.dirname(path)) if f.endswith(".abix-part")])

    def test_second_download_never_overwrites(self):
        a = P.download("https://site.test/setup.exe", os.path.join(T, "dl2"), (".exe",), lambda d, t: None)
        b = P.download("https://site.test/setup.exe", os.path.join(T, "dl2"), (".exe",), lambda d, t: None)
        self.assertNotEqual(a, b); self.assertTrue(os.path.exists(a) and os.path.exists(b))

    def test_wrong_extension_and_404_and_size(self):
        with self.assertRaises(P.BadLink): P.download("https://site.test/archive.zip", os.path.join(T, "dl3"), (".exe", ".msi"), lambda d, t: None)
        with self.assertRaises(P.BadLink): P.download("https://site.test/missing.exe", os.path.join(T, "dl3"), (".exe",), lambda d, t: None)
        with self.assertRaises(P.BadLink): P.download("https://site.test/big.exe", os.path.join(T, "dl3"), (".exe",), lambda d, t: None, max_bytes=1048576)
        self.assertFalse(os.path.exists(os.path.join(T, "dl3")) and os.listdir(os.path.join(T, "dl3")))

    def test_custom_job_runs_installer_and_rejects_fake(self):
        what, j = P.start_custom("https://site.test/setup.exe")
        self.assertEqual(what, "ok"); done = wait_done(j["id"])
        self.assertEqual(done["state"], "done", done); self.assertIn("launched setup", done["message"])
        self.assertTrue(os.path.exists(os.path.join(HOME, "Downloads", "setup.exe")))
        what, j = P.start_custom("https://site.test/fake.exe")
        done = wait_done(j["id"]); self.assertEqual(done["state"], "failed"); self.assertIn("not a real Windows installer", done["message"])
        self.assertFalse(os.path.exists(os.path.join(HOME, "Downloads", "fake.exe")))


class Catalog(unittest.TestCase):
    def test_invalid_entries_are_dropped(self):
        self.assertEqual(sorted(a["id"] for a in P.load_catalog()), ["arm-only", "good", "never"])

    def test_install_remove_and_failure(self):
        what, j = P.start_install("good"); self.assertEqual(what, "ok")
        done = wait_done(j["id"]); self.assertEqual(done["state"], "done", done); self.assertEqual(done["percent"], 100)
        log = open(os.path.join(T, "apt.log")).read()
        self.assertIn("apt-get update", log); self.assertIn("install -y --no-install-recommends good", log)
        self.assertIn("good", P.read_state())
        what, j = P.start_remove("good"); done = wait_done(j["id"]); self.assertEqual(done["state"], "done")
        self.assertNotIn("good", P.read_state()); self.assertIn("remove -y good", open(os.path.join(T, "apt.log")).read())
        open(os.path.join(T, "apt-fail"), "w").close()
        what, j = P.start_install("never"); done = wait_done(j["id"]); self.assertEqual(done["state"], "failed")
        self.assertTrue(done["log"]); os.remove(os.path.join(T, "apt-fail"))

    def test_unknown_and_wrong_cpu(self):
        self.assertEqual(P.start_install("nope")[0], "unknown"); self.assertEqual(P.start_install("good; rm -rf /")[0], "unknown")
        what, j = P.start_install("arm-only"); done = wait_done(j["id"]); self.assertEqual(done["state"], "failed"); self.assertIn("not available for this CPU", done["message"])

    def test_one_job_at_a_time(self):
        slow = P.new_job("slow", "install")
        self.assertEqual(P.start_install("good")[0], "busy"); self.assertEqual(P.start_custom("https://example.com/a.exe")[0], "busy")
        P.finish(slow, True, "ok")

    def test_custom_link_must_be_https(self):
        self.assertIn("https", P.start_custom("http://example.com/a.exe")[0])


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        A.CONF.update({"user": "admin", "hash": A.make_hash("pw-12345"), "secret": "x" * 40, "vnc_password": "v"})
        cls.srv = A.make_server("127.0.0.1", 0); cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        r = cls.call("POST", "/api/login", {"username": "admin", "password": "pw-12345"})
        cls.cookie = r[2].getheader("Set-Cookie").split(";")[0]

    @classmethod
    def call(cls, m, path, body=None, cookie=None, hdr=None):
        c = http.client.HTTPConnection("127.0.0.1", cls.port, timeout=10)
        h = {"Content-Type": "application/json", "X-Abix": "1"} if m == "POST" else {}
        h.update(hdr or {}); 
        if cookie: h["Cookie"] = cookie
        c.request(m, path, json.dumps(body) if body is not None else None, h)
        r = c.getresponse(); d = r.read()
        try: j = json.loads(d)
        except ValueError: j = None
        return r.status, j, r

    def test_requires_login_and_csrf(self):
        self.assertEqual(self.call("GET", "/api/apps")[0], 401)
        self.assertEqual(self.call("POST", "/api/apps/install", {"id": "good"})[0], 401)
        self.assertEqual(self.call("POST", "/api/apps/install", {"id": "good"}, cookie=self.cookie, hdr={"X-Abix": "0"})[0], 400)
        self.assertEqual(self.call("POST", "/api/apps/windows", {"url": "https://example.com/a.exe"}, cookie=self.cookie, hdr={"Content-Type": "text/plain"})[0], 400)

    def test_list_install_poll(self):
        s, j, _ = self.call("GET", "/api/apps", cookie=self.cookie)
        self.assertEqual(s, 200); ids = [a["id"] for a in j["items"]]; self.assertIn("good", ids); self.assertIn("wine", j)
        self.assertTrue(next(a for a in j["items"] if a["id"] == "good")["installed"])
        self.assertFalse(next(a for a in j["items"] if a["id"] == "arm-only")["supported"])
        s, j, _ = self.call("POST", "/api/apps/install", {"id": "never"}, cookie=self.cookie)
        self.assertEqual(s, 202); wait_done(j["job"])
        s, j2, _ = self.call("GET", "/api/apps/job?id=" + j["job"], cookie=self.cookie); self.assertEqual(s, 200); self.assertIn("log", j2)
        self.assertEqual(self.call("GET", "/api/apps/job?id=zzz", cookie=self.cookie)[0], 404)

    def test_bad_requests(self):
        self.assertEqual(self.call("POST", "/api/apps/install", {"id": "../../x"}, cookie=self.cookie)[0], 404)
        s, j, _ = self.call("POST", "/api/apps/windows", {"url": "http://example.com/a.exe"}, cookie=self.cookie)
        self.assertEqual(s, 400); self.assertIn("https", j["error"])
        self.assertEqual(self.call("POST", "/api/apps/windows", {"url": "https://localhost/a.exe"}, cookie=self.cookie)[0], 202)   # accepted, then the job fails safely
        time.sleep(0.5)
        s, j, _ = self.call("POST", "/api/apps/windows", {"url": 123}, cookie=self.cookie); self.assertEqual(s, 400)

    def test_locked_session_cannot_use_apps(self):
        s, j, r = self.call("POST", "/api/login", {"username": "admin", "password": "pw-12345"}); ck = r.getheader("Set-Cookie").split(";")[0]
        self.call("POST", "/api/lock", {}, cookie=ck)
        self.assertEqual(self.call("GET", "/api/apps", cookie=ck)[0], 403)
        self.assertEqual(self.call("POST", "/api/apps/install", {"id": "good"}, cookie=ck)[0], 403)


if __name__ == "__main__":
    A.kick_viewers = lambda: None
    unittest.main(verbosity=1)
