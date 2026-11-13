#!/usr/bin/env python3
"""Real-browser test of the Stage 4 UI against a FAKE noVNC page (no Docker needed).
   pip install playwright && playwright install chromium   then:   python3 tests/ui/test_ui.py
It checks that touchpad / direct / mouse-pad modes and the Copy / Paste buttons really deliver mouse, wheel and key
events to the noVNC canvas. It does NOT prove noVNC itself accepts them: that is only visible in the real stack."""
import http.server, json, os, threading, sys, functools
from playwright.sync_api import sync_playwright

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend")
FAKE = """<!doctype html><body style="margin:0;background:#123"><textarea id="noVNC_clipboard_text"></textarea>
<canvas id="c" width="800" height="500" tabindex="0" style="width:100%;height:100%"></canvas>
<script>window.ev=[];window.boxchg=[];
const c=document.getElementById('c');
['mousedown','mouseup','mousemove'].forEach(t=>c.addEventListener(t,e=>ev.push([t,Math.round(e.clientX),Math.round(e.clientY),e.button,e.buttons])));
c.addEventListener('wheel',e=>ev.push(['wheel',e.deltaX,e.deltaY]));
['keydown','keyup'].forEach(t=>c.addEventListener(t,e=>ev.push([t,e.code,e.ctrlKey,e.shiftKey])));
document.getElementById('noVNC_clipboard_text').addEventListener('change',e=>boxchg.push(e.target.value));
</script></body>"""

class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def _j(self, code, obj): b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    POSTED = []
    PREFS = {"logo_style": "pulse", "logo_anim": "light", "boot_anim": True}
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0); body = json.loads(self.rfile.read(n) or b"{}")
        H.POSTED.append((self.path, body, self.headers.get("X-Abix")))
        if self.path == "/api/launcher/launch": return self._j(200, {"ok": True, "state": "running", "message": "%s is starting." % body.get("id")})
        if self.path == "/api/ui-prefs": H.PREFS.update(body); return self._j(200, {"ok": True, "prefs": H.PREFS})
        if self.path == "/api/power": return self._j(200, {"ok": True})
        return self._j(202, {"ok": True, "job": "j1"})
    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/api/session": return self._j(200, {"authenticated": True, "locked": False, "user": "t"})
        if p == "/api/connect": return self._j(200, {"password": "x"})
        if p == "/api/apps": return self._j(200, {"wine": True, "arch": "amd64", "jobs": [], "items": [
            {"id": "vlc", "name": "VLC media player", "desc": "Plays video", "category": "Media", "kind": "apt", "installed": False, "supported": True, "note": ""},
            {"id": "gimp", "name": "GIMP", "desc": "Photo editor", "category": "Graphics", "kind": "apt", "installed": True, "supported": True, "note": ""}]})
        if p == "/api/ui-prefs": return self._j(200, {"prefs": H.PREFS})
        if p == "/api/launcher": return self._j(200, {"categories": ["Productivity", "Utilities & Tools", "Social", "Creativity"], "items": [
            {"id": "file-manager", "name": "File Manager", "desc": "Browse files.", "category": "Productivity", "kind": "native", "icon": "file-manager.png", "install_id": None, "state": "installed", "can_launch": True, "note": ""},
            {"id": "screenshot", "name": "Screenshot Tool", "desc": "Capture.", "category": "Utilities & Tools", "kind": "native", "icon": "screenshot.png", "install_id": "screenshooter", "state": "not_installed", "can_launch": False, "note": "Not installed. Install it from the App Center."},
            {"id": "whatsapp", "name": "WhatsApp", "desc": "WhatsApp Web.", "category": "Social", "kind": "web", "icon": "whatsapp.svg", "install_id": None, "state": "web", "can_launch": True, "note": "Opens as a web app in Firefox."},
            {"id": "notepad", "name": "ABIX Notepad", "desc": "Notes.", "category": "Productivity", "kind": "native", "icon": "notepad.svg", "install_id": None, "state": "installed", "can_launch": True, "note": ""},
            {"id": "premiere", "name": "Adobe Premiere Pro", "desc": "Video.", "category": "Creativity", "kind": "windows", "icon": "premiere.svg", "install_id": None, "state": "windows_only", "can_launch": False, "note": "Windows-only: there is no Linux version."}]})
        if p == "/api/apps/job": return self._j(200, {"id": "j1", "title": "Install VLC", "state": "done", "percent": 100, "message": "VLC is installed.", "log": ["line 1", "line 2"]})
        if p.startswith("/api/"): return self._j(200, {"items": []})
        if p == "/desktop/vnc.html":
            b = FAKE.encode(); self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        return super().do_GET()

def main():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(H, directory=ROOT))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/" % srv.server_address[1]
    fails = []
    def check(name, cond):
        print(("PASS  " if cond else "FAIL  ") + name)
        if not cond: fails.append(name)
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1000, "height": 700}, has_touch=True, permissions=["clipboard-read", "clipboard-write"])
        page = ctx.new_page(); errs = []
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.goto(url); page.wait_for_selector("#v-desk:not([hidden])"); page.wait_for_timeout(600)
        fr = page.frame_locator("#screen")
        def evs(): return page.frames[-1].evaluate("window.ev.splice(0)")
        def mode(m): page.click("#b-mouse"); page.click('#mouse-menu button[data-mode="%s"]' % m); page.wait_for_timeout(100)
        cdp = ctx.new_cdp_session(page)
        def touch(kind, pts): cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [{"x": x, "y": y, "id": i} for i, (x, y) in enumerate(pts)]})
        check("page loads without JS errors", not errs)
        # default on a touch device = touchpad: layer + cursor visible
        check("touch device defaults to touchpad (layer + pointer arrow shown)", page.is_visible("#pad-layer") and page.is_visible("#vcursor"))
        evs()
        # touchpad tap -> left click
        touch("touchStart", [(500, 400)]); page.wait_for_timeout(40); touch("touchEnd", []); page.wait_for_timeout(120)
        e = evs(); kinds = [x[0] for x in e]
        check("touchpad tap = mousedown + mouseup (left)", "mousedown" in kinds and "mouseup" in kinds and all(x[3] == 0 for x in e if x[0] in ("mousedown", "mouseup")))
        # touchpad swipe moves relative, no click (wait out the double-tap window first: tap + drag would be a drag)
        page.wait_for_timeout(450); evs(); touch("touchStart", [(300, 300)]); 
        for i in range(1, 8): touch("touchMove", [(300 + i * 12, 300)]); page.wait_for_timeout(16)
        touch("touchEnd", []); page.wait_for_timeout(100); e = evs()
        mv = [x for x in e if x[0] == "mousemove"]
        check("touchpad swipe moves the pointer to the right, without clicking", len(mv) >= 5 and mv[-1][1] > mv[0][1] and not any(x[0] == "mousedown" for x in e))
        # two finger tap -> right click
        evs(); touch("touchStart", [(400, 300), (440, 300)]); page.wait_for_timeout(50); touch("touchEnd", []); page.wait_for_timeout(120); e = evs()
        check("two-finger tap = right click", any(x[0] == "mousedown" and x[3] == 2 for x in e))
        # two finger scroll
        evs(); touch("touchStart", [(400, 400), (440, 400)])
        for i in range(1, 6): touch("touchMove", [(400, 400 - i * 15), (440, 400 - i * 15)]); page.wait_for_timeout(16)
        touch("touchEnd", []); page.wait_for_timeout(100); e = evs()
        w = [x for x in e if x[0] == "wheel"]
        check("two-finger drag up = wheel down (natural scrolling)", len(w) > 0 and all(x[2] > 0 for x in w))
        # direct touch
        mode("direct"); check("direct mode hides the pointer arrow", not page.is_visible("#vcursor")); evs()
        touch("touchStart", [(250, 250)]); page.wait_for_timeout(40); touch("touchEnd", []); page.wait_for_timeout(120); e = evs()
        d = [x for x in e if x[0] == "mousedown"]
        check("direct tap clicks at the touched point", len(d) == 1 and abs(d[0][1] - 250) <= 2 and abs(d[0][2] - 250 + 0) <= 120)
        # mouse pad
        mode("mousepad"); check("mouse pad panel is shown", page.is_visible("#mpad")); evs()
        box = page.locator("#mpad-l").bounding_box()
        touch("touchStart", [(box["x"] + 20, box["y"] + 20)]); page.wait_for_timeout(60); touch("touchEnd", []); page.wait_for_timeout(100); e = evs()
        check("mouse pad Left button = left click", any(x[0] == "mousedown" and x[3] == 0 for x in e) and any(x[0] == "mouseup" for x in e))
        pb = page.locator("#mpad-pad").bounding_box(); evs()
        touch("touchStart", [(pb["x"] + 30, pb["y"] + 60)])
        for i in range(1, 7): touch("touchMove", [(pb["x"] + 30 + i * 10, pb["y"] + 60)]); page.wait_for_timeout(16)
        touch("touchEnd", []); page.wait_for_timeout(80); e = evs()
        check("mouse pad moves the pointer", len([x for x in e if x[0] == "mousemove"]) >= 4)
        # normal mode: layer + pad hidden
        mode("normal"); check("normal mode shows no overlay", not page.is_visible("#pad-layer") and not page.is_visible("#mpad"))
        check("mode is remembered", page.evaluate("localStorage.getItem('abix_mouse')") == "normal")
        # clipboard: Copy sends Ctrl+C, then reads the box the PC fills
        page.frames[-1].evaluate("window.ev.length=0")
        page.click("#b-clip"); page.fill("#clip-text", "")
        page.frames[-1].evaluate("setTimeout(()=>{document.getElementById('noVNC_clipboard_text').value='hello from cloud'},150)")
        page.click("#c-copy"); page.wait_for_timeout(700); e = evs()
        check("Copy presses Ctrl+C on the desktop", any(x[0] == "keydown" and x[1] == "KeyC" and x[2] for x in e))
        check("Copy writes the cloud text to the device clipboard", page.evaluate("navigator.clipboard.readText()") == "hello from cloud")
        # Paste: device clipboard -> noVNC clipboard box -> Ctrl+V
        page.evaluate("navigator.clipboard.writeText('from my phone')")
        page.click("#c-paste"); page.wait_for_timeout(600); e = evs()
        check("Paste sends the device text to the desktop clipboard", page.frames[-1].evaluate("window.boxchg.includes('from my phone')"))
        check("Paste then presses Ctrl+V", any(x[0] == "keydown" and x[1] == "KeyV" and x[2] and not x[3] for x in e))
        page.click("#c-tpaste"); page.wait_for_timeout(500); e = evs()
        check("Terminal paste presses Ctrl+Shift+V", any(x[0] == "keydown" and x[1] == "KeyV" and x[2] and x[3] for x in e))
        # speed presets reload the screen with the right noVNC parameters
        page.click("#b-settings"); page.click('#perf-seg button[data-p="smooth"]'); page.wait_for_timeout(500)
        src = page.evaluate("document.getElementById('screen').src")
        check("Smooth preset puts quality/compression in the screen URL", "quality=5" in src and "compression=1" in src)
        page.click('#perf-seg button[data-p="turbo"]'); page.wait_for_timeout(500)
        src = page.evaluate("document.getElementById('screen').src")
        check("Turbo preset is the fastest (compression 0)", "quality=2" in src and "compression=0" in src)
        page.click('#perf-seg button[data-p="smooth"]'); page.wait_for_timeout(300)
        check("screen has no CSS filter at 100% brightness (stays on the fast path)", page.evaluate("document.getElementById('screen').style.filter") == "none")
        # ---- Stage 5: App Center
        page.click("#s-close")
        page.click("#b-apps"); page.wait_for_selector("#a-list .arow", timeout=3000)
        check("App Center opens and lists apps", page.locator("#a-list .arow").count() == 2 and not page.evaluate("document.getElementById('apps').hidden") is True)
        check("installed app shows Remove, other shows Install", page.locator("#a-list .arow", has_text="GIMP").locator("button").inner_text() == "Remove" and page.locator("#a-list .arow", has_text="VLC").locator("button").inner_text() == "Install")
        page.fill("#a-search", "gimp"); check("search filters the list", page.locator("#a-list .arow").count() == 1)
        page.fill("#a-search", "")
        page.locator("#a-list .arow", has_text="VLC").locator("button").click(); page.wait_for_timeout(700)
        check("Install posts the app id with the CSRF header", ("/api/apps/install", {"id": "vlc"}, "1") in H.POSTED)
        check("progress box shows the finished job", page.evaluate("!document.getElementById('a-jobbox').hidden") and "installed" in page.inner_text("#a-msg"))
        page.fill("#a-url", "https://example.com/setup.exe"); page.click("#a-go"); page.wait_for_timeout(500)
        check("Windows link is posted to /api/apps/windows", ("/api/apps/windows", {"url": "https://example.com/setup.exe"}, "1") in H.POSTED)
        page.click("#a-close"); check("close button hides the App Center", page.evaluate("document.getElementById('apps').hidden"))
        page.click("#b-settings"); check("Settings still opens afterwards", not page.evaluate("document.getElementById('settings').hidden"))
        page.click("#s-close")
        # ---- V6 slice 1: Start menu, launcher, animated logo, restart screen
        page.click("#b-start"); page.wait_for_selector("#start .app-tile", timeout=3000)
        check("Start menu opens with grouped app tiles", not page.evaluate("document.getElementById('start').hidden") and page.locator("#start .app-tile").count() == 5 and page.locator("#start .st-group").count() == 4)
        page.wait_for_function("Array.from(document.querySelectorAll('#start .app-tile img')).every(i => i.complete)", timeout=3000)
        check("every tile icon file really loads", page.evaluate("Array.from(document.querySelectorAll('#start .app-tile img')).every(i => i.complete && i.naturalWidth > 0)"))
        check("status chips are honest (not installed / web app / windows only)", page.locator("#start .app-tile", has_text="Premiere").locator(".chip").inner_text() == "Windows only" and page.locator("#start .app-tile", has_text="Screenshot").locator(".chip").inner_text() == "Not installed" and page.locator("#start .app-tile", has_text="WhatsApp").locator(".chip").inner_text() == "Web app" and page.locator("#start .app-tile", has_text="File Manager").locator(".chip").count() == 0)
        page.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "start-menu.png"))
        page.fill("#st-search", "whats"); check("Start search filters tiles", page.locator("#start .app-tile").count() == 1)
        page.fill("#st-search", "")
        n0 = len([x for x in H.POSTED if x[0] == "/api/launcher/launch"])
        page.locator("#start .app-tile", has_text="Premiere").click(); page.wait_for_timeout(200)
        check("Windows-only tile starts nothing and explains why", len([x for x in H.POSTED if x[0] == "/api/launcher/launch"]) == n0 and "Windows-only" in page.inner_text("#st-msg") and not page.evaluate("document.getElementById('start').hidden"))
        page.locator("#start .app-tile", has_text="Screenshot").click(); page.wait_for_timeout(200)
        check("not-installed tile with an App Center entry opens the App Center", not page.evaluate("document.getElementById('apps').hidden") and page.evaluate("document.getElementById('start').hidden"))
        page.click("#a-close")
        page.click("#b-start"); page.wait_for_selector("#start .app-tile")
        page.locator("#start .app-tile", has_text="File Manager").click(); page.wait_for_timeout(300)
        check("launching posts only the app id with the CSRF header", ("/api/launcher/launch", {"id": "file-manager"}, "1") in H.POSTED)
        check("Start menu closes after a successful launch", page.evaluate("document.getElementById('start').hidden"))
        # animation settings: Off / Light / Full and the five styles are really applied
        page.click("#b-settings")
        def anim(sel): return page.evaluate("getComputedStyle(document.querySelector('%s')).animationName" % sel)
        page.click('.seg[data-ui="logo_anim"] button[data-v="off"]'); page.wait_for_timeout(250)
        check("Off: class set, logo does not move, saved on the server", page.evaluate("document.documentElement.classList.contains('anim-off')") and anim("#s-logo-prev .body") == "none" and H.PREFS["logo_anim"] == "off")
        page.click('.seg[data-ui="logo_anim"] button[data-v="light"]'); page.wait_for_timeout(250)
        check("Light: gentle motion on the logo", anim("#s-logo-prev .body") == "al-breathe" and H.PREFS["logo_anim"] == "light")
        page.click('.seg[data-ui="logo_anim"] button[data-v="full"]'); page.click('.seg[data-ui="logo_style"] button[data-v="orbit"]'); page.wait_for_timeout(250)
        check("Full + Orbit: dots appear and spin", page.evaluate("getComputedStyle(document.querySelector('#s-logo-prev .dots')).opacity") == "1" and anim("#s-logo-prev .dots") == "al-spin" and H.PREFS["logo_style"] == "orbit")
        for st, want in (("pulse", "al-ripple"), ("draw", "al-draw"), ("bloom", "al-bloom"), ("aurora", "al-hue")):
            page.click('.seg[data-ui="logo_style"] button[data-v="%s"]' % st); page.wait_for_timeout(120)
            sel = "#s-logo-prev .glyph" if st == "draw" else ("#s-logo-prev .body" if st == "bloom" else ("#s-logo-prev .alogo-svg" if st == "aurora" else "#s-logo-prev .ring"))
            check("Full + %s style animates (%s)" % (st, want), anim(sel) == want)
        page.click('.seg[data-ui="logo_style"] button[data-v="bloom"]')
        page.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo-full-bloom.png"))
        page.click("#s-close")
        # a saved choice survives a page reload
        page.reload(); page.wait_for_selector("#v-desk:not([hidden])"); page.wait_for_timeout(500)
        check("saved animation choice survives a reload", page.evaluate("document.documentElement.classList.contains('anim-full') && document.documentElement.getAttribute('data-ls') === 'bloom'"))
        # restart screen with the animated logo (Full)
        page.click("#b-start"); page.click('#start [data-pact="restart-session"]'); page.wait_for_selector("#confirm:not([hidden])")
        check("Restart asks for confirmation first", "Restart desktop session" in page.inner_text("#c-title"))
        n1 = len([x for x in H.POSTED if x[0] == "/api/power"])
        page.click("#c-yes"); page.wait_for_timeout(500)
        check("Restart posts to /api/power and shows the ABIX restart screen", len([x for x in H.POSTED if x[0] == "/api/power"]) == n1 + 1 and not page.evaluate("document.getElementById('v-boot').hidden") and "Restarting" in page.inner_text("#boot-text") and page.locator("#v-boot .alogo svg").count() == 1)
        page.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "restart-screen.png"))
        page.wait_for_timeout(12200)
        check("after the restart wait the desktop comes back", page.evaluate("document.getElementById('v-boot').hidden") and not page.evaluate("document.getElementById('v-desk').hidden"))
        # animation Off = no startup screens
        page.click("#b-settings"); page.click('.seg[data-ui="logo_anim"] button[data-v="off"]'); page.click("#s-close"); page.wait_for_timeout(200)
        page.click("#b-power"); page.click('#power-menu [data-act="restart-session"]'); page.click("#c-yes"); page.wait_for_timeout(500)
        check("with animation Off the restart screen is skipped", page.evaluate("document.getElementById('v-boot').hidden") and not page.evaluate("document.getElementById('v-desk').hidden"))
        check("no JS errors at the end", not errs)
        page.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "last-run.png"))
        b.close()
    print("\nFailed: %d" % len(fails)); sys.exit(1 if fails else 0)
main()
