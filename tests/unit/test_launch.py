#!/usr/bin/env python3
"""Tests for backend/abix_launch.py and abix_prefs.py with REAL fake programs (no Docker, no desktop).
    python3 tests/unit/test_launch.py"""
import json, os, signal, stat, sys, tempfile, time, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "backend"))
T = tempfile.mkdtemp()
BIN = os.path.join(T, "bin"); HOME = os.path.join(T, "home")
os.makedirs(BIN); os.makedirs(HOME)
os.environ.update(ABIX_DESKTOP_USER="", ABIX_DESKTOP_HOME=HOME, ABIX_LAUNCH_PATH=BIN)
import abix_launch as L  # noqa: E402
import abix_prefs as P  # noqa: E402
L.LAUNCH_GAP = 0


def prog(name, body):
    p = os.path.join(BIN, name)
    open(p, "w").write("#!/bin/bash\n" + body + "\n"); os.chmod(p, 0o755)


prog("runner", "exec /bin/sleep 30")                       # stays running
prog("handoff", "exit 0")                             # single-instance app that hands over and exits
prog("crasher", 'echo "cannot open display" >&2; exit 3')
prog("firefox", "exec /bin/sleep 30")
REAL = list(L.CATALOG)
TEST = [L._a("t-run", "Runner", "d", "Internet", "native", ["runner"], ["runner"]),
        L._a("t-hand", "Handoff", "d", "Internet", "native", ["handoff"], ["handoff"]),
        L._a("t-bad", "Crasher", "d", "Internet", "native", ["crasher"], ["crasher"]),
        L._a("t-miss", "Missing", "d", "Internet", "native", ["nothere"], ["nothere"], None, "somepkg"),
        L._a("t-web", "Web", "d", "Social", "web", ["runner"]),
        L._a("t-win", "Win", "d", "Creativity", "windows")]


class Catalog(unittest.TestCase):
    def test_real_catalog_is_sound(self):
        ids = [a["id"] for a in REAL]
        self.assertEqual(len(ids), len(set(ids)))
        apps = {a["id"] for a in json.load(open(os.path.join(ROOT, "backend", "apps-catalog.json")))["apps"]}
        for a in REAL:
            self.assertIn(a["category"], L.CATEGORIES, a["id"])
            self.assertIn(a["kind"], ("native", "web", "windows"))
            self.assertTrue(all(isinstance(x, str) for x in a["cmd"]), a["id"])
            self.assertTrue(os.path.exists(os.path.join(ROOT, "frontend", "icons", a["icon"])), "missing icon " + a["icon"])
            if a["kind"] != "windows":
                self.assertTrue(a["cmd"], a["id"])
            if a["install_id"]:
                self.assertIn(a["install_id"], apps, "App Center has no entry " + a["install_id"])
        for must in ("file-manager", "notepad", "abix-browser", "whatsapp", "imo", "telegram", "premiere", "aftereffects"):
            self.assertIn(must, ids)

    def test_windows_apps_never_fake_installed(self):
        for a in REAL:
            if a["kind"] == "windows":
                s = L.state(a)
                self.assertEqual((s["state"], s["can_launch"]), ("windows_only", False))
                self.assertIn("Windows-only", s["note"])

    def test_launcher_scripts_exist(self):
        for f in ("abix-browser", "abix-webapp"):
            p = os.path.join(ROOT, "docker", "abix", f)
            self.assertTrue(os.access(p, os.X_OK), f)


class State(unittest.TestCase):
    def setUp(self): L.CATALOG[:] = TEST
    def tearDown(self): L.CATALOG[:] = REAL

    def test_installed_missing_web(self):
        v = {s["id"]: s for s in L.catalog_view()}
        self.assertEqual(v["t-run"]["state"], "installed")
        self.assertEqual((v["t-miss"]["state"], v["t-miss"]["can_launch"]), ("not_installed", False))
        self.assertIn("App Center", v["t-miss"]["note"])
        self.assertEqual(v["t-web"]["state"], "web")        # firefox exists in the fake PATH

    def test_web_without_any_browser(self):
        os.rename(os.path.join(BIN, "firefox"), os.path.join(BIN, "firefox.off"))
        try:
            s = L.state(L.find("t-web"))
            self.assertEqual((s["state"], s["can_launch"]), ("not_installed", False))
        finally:
            os.rename(os.path.join(BIN, "firefox.off"), os.path.join(BIN, "firefox"))


class Launch(unittest.TestCase):
    def setUp(self): L.CATALOG[:] = TEST
    def tearDown(self): L.CATALOG[:] = REAL

    def test_running_started_failed(self):
        code, r = L.launch("t-run", wait=0.4)
        self.assertEqual((code, r["state"]), (200, "running"))
        os.killpg(r["pid"], signal.SIGKILL)
        code, r = L.launch("t-hand", wait=1.5)
        self.assertEqual((code, r["state"]), (200, "started"))
        code, r = L.launch("t-bad", wait=1.5)
        self.assertEqual(code, 500); self.assertIn("cannot open display", r["error"])    # the program's own message, never 'success'

    def test_refusals(self):
        self.assertEqual(L.launch("nope")[0], 404)
        self.assertEqual(L.launch(["x"])[0], 404)
        self.assertEqual(L.launch("t-miss")[0], 409)
        self.assertEqual(L.launch("t-win")[0], 409)

    def test_rate_limit(self):
        L.LAUNCH_GAP = 5
        try:
            L._last[0] = time.time()
            self.assertEqual(L.launch("t-hand", wait=0.2)[0], 429)
        finally:
            L.LAUNCH_GAP = 0


class WineRegistry(unittest.TestCase):
    def reg(self, apps):
        d = os.path.join(HOME, ".config", "abix"); os.makedirs(d, exist_ok=True)
        json.dump({"apps": apps}, open(os.path.join(d, "windows-apps.json"), "w"))

    def test_only_verified_entries_count(self):
        pre = os.path.join(HOME, "wine1"); os.makedirs(pre)
        exe = os.path.join(pre, "pr.exe"); open(exe, "wb").write(b"MZ")
        outside = os.path.join(T, "evil.exe"); open(outside, "wb").write(b"MZ")
        self.reg([{"id": "premiere", "exe": exe, "prefix": pre},
                  {"id": "aftereffects", "exe": outside, "prefix": pre},          # exe outside the home: refused
                  {"id": "x", "exe": os.path.join(pre, "gone.exe"), "prefix": pre},  # file missing: refused
                  {"id": "y", "exe": exe.replace("pr.exe", "pr.txt"), "prefix": pre}, "junk", {"id": 5}])
        self.assertEqual(sorted(L.windows_registry()), ["premiere"])
        self.assertEqual(L.state(L.find("premiere"))["state"], "installed")
        self.assertEqual(L.state(L.find("aftereffects"))["state"], "windows_only")

    def test_damaged_file(self):
        d = os.path.join(HOME, ".config", "abix"); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "windows-apps.json"), "w").write("{not json")
        self.assertEqual(L.windows_registry(), {})


class Prefs(unittest.TestCase):
    def setUp(self):
        if os.path.exists(P.path()):
            os.remove(P.path())          # every test starts from a clean saved state

    def test_defaults_save_and_reload(self):
        self.assertEqual(P.load(), P.DEFAULTS)
        res, code = P.save({"logo_style": "orbit", "logo_anim": "full"})
        self.assertEqual(code, 200)
        self.assertEqual(P.load()["logo_style"], "orbit"); self.assertTrue(P.load()["boot_anim"])
        res, code = P.save({"boot_anim": False})
        self.assertEqual((P.load()["logo_style"], P.load()["boot_anim"]), ("orbit", False))      # earlier values kept

    def test_rejects_bad_input(self):
        before = P.load()
        for bad in ({"logo_style": "x"}, {"logo_anim": "max"}, {"boot_anim": "yes"}, {"colour": "red"}, {}, [], "s"):
            self.assertEqual(P.save(bad)[1], 400, bad)
        self.assertEqual(P.load(), before)

    def test_damaged_file_falls_back(self):
        os.makedirs(os.path.dirname(P.path()), exist_ok=True)
        open(P.path(), "w").write("{broken")
        self.assertEqual(P.load(), P.DEFAULTS)
        open(P.path(), "w").write(json.dumps({"logo_style": "nope", "logo_anim": "full"}))
        self.assertEqual((P.load()["logo_style"], P.load()["logo_anim"]), ("pulse", "full"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
