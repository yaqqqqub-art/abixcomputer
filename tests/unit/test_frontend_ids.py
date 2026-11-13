#!/usr/bin/env python3
"""Static frontend check: every element id used by app.js exists in index.html, no duplicate ids,
and the page keeps the inline-script/style-free shape required by Nginx's Content-Security-Policy.
    python3 tests/unit/test_frontend_ids.py"""
import os, re, unittest
F = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend")
html = open(os.path.join(F, "index.html"), encoding="utf-8").read()
js = open(os.path.join(F, "app.js"), encoding="utf-8").read()
osk = open(os.path.join(F, "osk.js"), encoding="utf-8").read()
ptr = open(os.path.join(F, "pointer.js"), encoding="utf-8").read()
extra = open(os.path.join(F, "extras.js"), encoding="utf-8").read()
start = open(os.path.join(F, "start.js"), encoding="utf-8").read()
ids = re.findall(r'\bid="([^"]+)"', html)

class T(unittest.TestCase):
    def test_js_ids_exist(self):
        used = set(re.findall(r'\$\("([A-Za-z0-9_-]+)"\)', js)) | set(re.findall(r'VIEWS = \[([^\]]+)\]', js) and re.findall(r'"(v-[a-z]+)"', re.search(r'VIEWS = \[([^\]]+)\]', js).group(1)))
        used |= set(re.findall(r'closePanels.*?\[([^\]]+)\]', js)[0].replace('"', '').replace(' ', '').split(","))
        missing = sorted(u for u in used if u not in ids)
        self.assertEqual(missing, [])
    def test_osk_ids_exist(self):
        used = set(re.findall(r'\$\("([A-Za-z0-9_-]+)"\)', osk))
        self.assertEqual(sorted(u for u in used if u not in ids), [])
        self.assertIn('<script src="osk.js"></script>', html)
    def test_stage4_ids_exist(self):
        for name, src in (("pointer.js", ptr), ("extras.js", extra)):
            used = set(re.findall(r'\$\("([A-Za-z0-9_-]+)"\)', src))
            self.assertEqual(sorted(u for u in used if u not in ids), [], name)
        for i in ("stage", "pad-layer", "vcursor", "mpad", "b-mouse", "mouse-menu", "b-clip", "clip-menu", "c-copy", "c-paste", "osk-copy", "osk-paste", "perf-seg", "s-speed", "s-natural", "s-sound"):
            self.assertIn(i, ids)
        for m in ("normal", "touchpad", "mousepad", "direct"):
            self.assertIn('data-mode="%s"' % m, html)
        for f in ("pointer.js", "extras.js", "cursor.svg"):
            self.assertTrue(os.path.exists(os.path.join(F, f)), f)
        self.assertLess(html.index('src="osk.js"'), html.index('src="pointer.js"'))
        self.assertLess(html.index('src="pointer.js"'), html.index('src="extras.js"'))
    def test_v6_start_menu_ids_and_icons(self):
        used = set(re.findall(r'\$\(\"([A-Za-z0-9_-]+)\"\)', start))
        self.assertEqual(sorted(u for u in used if u not in ids), [])
        self.assertIn('<script src="start.js"></script>', html)
        for act in ("sleep", "restart-session", "restart-desktop", "shutdown", "logout"):
            self.assertIn('data-pact="%s"' % act, html)
        for key, vals in (("logo_anim", ("off", "light", "full")), ("logo_style", ("pulse", "orbit", "draw", "bloom", "aurora"))):
            seg = re.search(r'data-ui="%s">(.*?)</div>' % key, html, re.S).group(1)
            self.assertEqual(re.findall(r'data-v="([a-z]+)"', seg), list(vals))
        self.assertEqual(html.count('class="alogo'), 5)          # boot, login, lock, start footer, settings preview
    def test_no_duplicate_ids(self):
        self.assertEqual(sorted({i for i in ids if ids.count(i) > 1}), [])
    def test_csp_friendly(self):
        self.assertNotRegex(html, r'<script(?![^>]*\bsrc=)[^>]*>')      # no inline scripts
        self.assertNotIn("<style", html); self.assertNotRegex(html, r'\sstyle="')
        self.assertNotRegex(html, r'\son[a-z]+="')                        # no inline handlers
    def test_stage3_features_present(self):
        for i in ("v-boot", "v-off", "b-on", "widgets", "files", "s-bright", "s-night", "night", "pcname", "osk", "b-kbd", "osk-keys"):
            self.assertIn(i, ids)
        for act in ("shutdown", "sleep"):
            self.assertIn('data-act="%s"' % act, html)
if __name__ == "__main__":
    unittest.main(verbosity=1)
