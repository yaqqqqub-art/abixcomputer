(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var VIEWS = ["v-boot", "v-off", "v-login", "v-desk", "v-lock"];
  var ACCENTS = ["#0067c0", "#7a5cff", "#0f9d58", "#e8710a", "#d93025", "#c2185b"];
  var timers = { beat: null, clock: null, toast: null };
  var wallsLoaded = false;

  function show(id) { VIEWS.forEach(function (v) { $(v).hidden = (v !== id); }); }
  function toast(msg) {
    var t = $("toast"); t.textContent = msg; t.classList.add("show");
    clearTimeout(timers.toast); timers.toast = setTimeout(function () { t.classList.remove("show"); }, 3200);
  }

  function api(method, path, body) {
    var opt = { method: method, credentials: "same-origin", headers: {} };
    if (method === "POST") { opt.headers["Content-Type"] = "application/json"; opt.headers["X-Abix"] = "1"; opt.body = JSON.stringify(body || {}); }
    return fetch(path, opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (r.status === 401 && path !== "/api/login" && path !== "/api/unlock") { toLogin(); }
        else if (r.status === 403 && d.error === "locked") { toLock(); }
        return { status: r.status, data: d };
      });
    }).catch(function () { return { status: 0, data: { error: "no connection to the server" } }; });
  }

  // ---------------------------------------------------------------- views
  function stopBeat() { clearInterval(timers.beat); clearInterval(timers.clock); }
  function toLogin() {
    stopBeat(); $("screen").src = "about:blank"; show("v-login");
    $("l-pass").value = ""; $("settings").hidden = true;
  }
  function tickClock() {
    var d = new Date(); $("clock").textContent = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  function toLock(user) {
    stopBeat(); $("screen").src = "about:blank"; show("v-lock");
    if (user) { $("lock-user").textContent = user; }
    $("k-pass").value = ""; $("k-err").textContent = ""; tickClock();
    timers.clock = setInterval(tickClock, 15000);
    setTimeout(function () { $("k-pass").focus(); }, 50);
  }
  // Stage 4: speed presets = noVNC image quality (0-9) and compression (0-9). Balanced = noVNC defaults.
  // Stage 5: low compression = little CPU work per frame = less lag. Smooth is the default now. Turbo is for very slow links.
  var PERF = { turbo: "&quality=2&compression=0", smooth: "&quality=5&compression=1", balanced: "&quality=6&compression=2", sharp: "&quality=9&compression=4" };
  function perfName() { var p = store("abix_perf"); return PERF[p] ? p : "smooth"; }
  function perfParams() { return PERF[perfName()]; }
  function markPerf() { Array.prototype.forEach.call(document.querySelectorAll("#perf-seg button"), function (b) { b.classList.toggle("on", b.getAttribute("data-p") === perfName()); }); }
  $("perf-seg").addEventListener("click", function (e) {
    var p = e.target.getAttribute("data-p"); if (!p || !PERF[p]) { return; }
    store("abix_perf", p); markPerf(); toast("Speed: " + p + " (reconnecting the screen…)"); loadScreen();
  });
  function loadScreen() {
    $("conn").textContent = "connecting…"; $("conn").classList.remove("ok");
    return api("GET", "/api/connect").then(function (r) {
      if (r.status !== 200) { return; }
      var q = "path=desktop/websockify&autoconnect=1&resize=scale&reconnect=1&reconnect_delay=2000" + perfParams() + "&password=" + encodeURIComponent(r.data.password || "");
      $("screen").src = "/desktop/vnc.html?" + q;
    });
  }
  function toDesk() {
    show("v-desk"); loadScreen(); applyLook();
    if (window.ABIX_UI) { window.ABIX_UI.onDesk(); }
    stopBeat();
    timers.beat = setInterval(function () {
      api("GET", "/api/session").then(function (r) {
        if (r.data && r.data.authenticated === false) { toLogin(); }
        else if (r.data && r.data.locked) { toLock(r.data.user); }
      });
    }, 20000);
  }
  $("screen").addEventListener("load", function () {
    if ($("screen").src.indexOf("/desktop/") > -1) { $("conn").textContent = "online"; $("conn").classList.add("ok"); }
  });

  // ---------------------------------------------------------------- login / lock
  $("login-form").addEventListener("submit", function (e) {
    e.preventDefault(); $("l-err").textContent = "";
    api("POST", "/api/login", { username: $("l-user").value, password: $("l-pass").value }).then(function (r) {
      if (r.status === 200) { $("l-pass").value = ""; bootThen("Starting ABIX…", 1300, toDesk); }
      else {
        var message = r.data && r.data.error;
        if (!message) {
          if (r.status === 401) { message = "Username or password does not match the configured ABIX account."; }
          else if (r.status === 429 || r.status === 503) { message = "Login rate limit reached. Wait 5 minutes, then try once."; }
          else if (r.status === 0 || r.status >= 500) { message = "Login service is unavailable. Check Blitz Logs for the ABIX API error."; }
          else { message = "Login request failed (HTTP " + r.status + "). Check the Blitz deployment."; }
        }
        $("l-err").textContent = message; $("l-pass").select();
      }
    });
  });
  $("b-lock").addEventListener("click", function () {
    api("POST", "/api/lock").then(function (r) { if (r.status === 200) { toLock(); } else { toast("Could not lock"); } });
  });
  $("lock-form").addEventListener("submit", function (e) {
    e.preventDefault(); $("k-err").textContent = "";
    api("POST", "/api/unlock", { password: $("k-pass").value }).then(function (r) {
      if (r.status === 200) { $("k-pass").value = ""; toDesk(); }
      else { $("k-err").textContent = r.data.error || "could not unlock"; $("k-pass").select(); }
    });
  });
  $("k-out").addEventListener("click", logout);
  function animOn() { var p = (window.ABIX_UI && window.ABIX_UI.get()) || {}; return p.logo_anim !== "off" && p.boot_anim !== false; }
  // Shows the animated ABIX logo screen for `ms`, then runs fn. With animation Off (or boot animation disabled) fn runs at once.
  function bootThen(text, ms, fn) {
    if (!animOn()) { fn(); return; }
    closePanels(); $("boot-text").textContent = text; show("v-boot"); setTimeout(fn, ms);
  }
  function logout() {
    if (!$("v-desk").hidden) { bootThen("Signing out…", 900, function () { api("POST", "/api/logout").then(toLogin); }); }
    else { api("POST", "/api/logout").then(toLogin); }
  }

  // ---------------------------------------------------------------- toolbar
  $("b-hide").addEventListener("click", function () { $("bar").hidden = true; $("b-show").hidden = false; $("settings").hidden = true; });
  $("b-show").addEventListener("click", function () { $("bar").hidden = false; $("b-show").hidden = true; });
  $("b-full").addEventListener("click", function () {
    var el = document.documentElement;
    if (document.fullscreenElement) { document.exitFullscreen(); }
    else if (el.requestFullscreen) { el.requestFullscreen().catch(function () { toast("Full screen is not allowed here"); }); }
    else { toast("This browser has no full screen. On iPhone/iPad use Share > Add to Home Screen."); }
  });
  $("b-power").addEventListener("click", function (e) { e.stopPropagation(); $("power-menu").hidden = !$("power-menu").hidden; });
  document.addEventListener("click", function () { $("power-menu").hidden = true; });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") { $("power-menu").hidden = true; $("confirm").hidden = true; } });

  var pending = null;
  function ask(title, text, fn) { $("c-title").textContent = title; $("c-text").textContent = text; pending = fn; $("confirm").hidden = false; $("c-yes").focus(); }
  $("c-no").addEventListener("click", function () { $("confirm").hidden = true; pending = null; });
  $("c-yes").addEventListener("click", function () { $("confirm").hidden = true; var f = pending; pending = null; if (f) { f(); } });
  function doPower(action, wait) {
    api("POST", "/api/power", { action: action }).then(function (r) {
      if (r.status !== 200) { toast("Failed: " + (r.data.error || r.status)); return; }
      var anim = animOn();
      $("screen").src = "about:blank"; $("conn").textContent = "restarting…"; $("conn").classList.remove("ok");
      if (anim) { closePanels(); $("boot-text").textContent = action === "restart-desktop" ? "ABIX is restarting…" : "Restarting your desktop session…"; show("v-boot"); }
      else { toast("Restarting… reconnecting in a few seconds"); }
      setTimeout(function () { if (anim && !$("v-boot").hidden) { show("v-desk"); } loadScreen(); }, wait);
    });
  }
  function handlePower(a) {
    if (a === "logout") { logout(); }
    else if (a === "sleep") { api("POST", "/api/lock").then(function (r) { if (r.status === 200) { toLock(); } else { toast("Could not lock"); } }); }
    else if (a === "shutdown") { ask("Shut down ABIX Computer?", "You will be signed out and the screen turns off. Your files stay saved; press the power button to turn it on again.", shutDown); }
    else if (a === "restart-session") { ask("Restart desktop session?", "Open windows are closed; files in your home folder are kept.", function () { doPower(a, 12000); }); }
    else if (a === "restart-desktop") { ask("Restart whole desktop?", "The screen server and the session restart. Unsaved work in open apps is lost.", function () { doPower(a, 15000); }); }
  }
  $("power-menu").addEventListener("click", function (e) { var a = e.target.getAttribute("data-act"); if (a) { handlePower(a); } });

  // ---------------------------------------------------------------- settings
  function mark(group, value) {
    Array.prototype.forEach.call(document.querySelectorAll('.seg[data-key="' + group + '"] button'), function (b) { b.classList.toggle("on", b.getAttribute("data-v") === value); });
  }
  function renderStatus(s) {
    if (!s || s.available === false) { $("s-msg").textContent = "Desktop settings are not available yet: " + ((s && s.error) || "desktop still starting"); return; }
    mark("theme", s.theme); mark("animation", s.animation);
    $("s-anim").textContent = "Really active: " + (s.active_animation || "unknown") + (s.picom ? "" : " (picom not installed)");
    $("s-start").textContent = "Start menu: " + (s.start_menu === "whisker" ? "Whisker menu" : "standard Xfce menu");
    Array.prototype.forEach.call(document.querySelectorAll(".sw"), function (b) { b.classList.toggle("on", (s.accent || "").toLowerCase() === b.getAttribute("data-c")); });
    Array.prototype.forEach.call(document.querySelectorAll(".wall"), function (b) { b.classList.toggle("on", b.getAttribute("data-file") === s.wallpaper); });
  }
  function refreshSettings() { return api("GET", "/api/settings").then(function (r) { if (r.status === 200) { renderStatus(r.data); } }); }
  function change(patch, label) {
    $("s-msg").textContent = "Applying…";
    api("POST", "/api/settings", patch).then(function (r) {
      var errs = r.data && r.data.errors && Object.keys(r.data.errors).length;
      $("s-msg").textContent = r.status === 200 && !errs ? label + " applied" : "Not applied: " + JSON.stringify(r.data.errors || r.data.error || r.status);
      refreshSettings();
    });
  }
  function buildSettings() {
    var sw = $("accents"); sw.textContent = "";
    ACCENTS.forEach(function (c) {
      var b = document.createElement("button"); b.className = "sw"; b.style.background = c; b.setAttribute("data-c", c); b.setAttribute("aria-label", "Accent " + c);
      b.addEventListener("click", function () { change({ accent: c }, "Accent colour"); }); sw.appendChild(b);
    });
    api("GET", "/api/wallpapers").then(function (r) {
      var box = $("walls"); box.textContent = "";
      ((r.data && r.data.items) || []).forEach(function (w) {
        var b = document.createElement("button"); b.className = "wall"; b.setAttribute("data-file", w.id.replace(/^(sys|user)-/, ""));
        var img = document.createElement("img"); img.loading = "lazy"; img.alt = ""; img.src = "/api/wallpaper/" + encodeURIComponent(w.id);
        var sp = document.createElement("span"); sp.textContent = w.name;
        b.appendChild(img); b.appendChild(sp);
        b.addEventListener("click", function () { change({ wallpaper: w.id }, "Wallpaper"); }); box.appendChild(b);
      });
      wallsLoaded = true; refreshSettings();
    });
  }
  Array.prototype.forEach.call(document.querySelectorAll(".seg[data-key]"), function (seg) {
    seg.addEventListener("click", function (e) {
      var v = e.target.getAttribute("data-v"); if (!v) { return; }
      var patch = {}; patch[seg.getAttribute("data-key")] = v; change(patch, seg.getAttribute("data-key") === "theme" ? "Mode" : "Animation");
    });
  });
  $("b-settings").addEventListener("click", function () {
    var open = $("settings").hidden; $("settings").hidden = !open;
    if (open) { if (!wallsLoaded) { buildSettings(); } else { refreshSettings(); } }
  });
  $("s-close").addEventListener("click", function () { $("settings").hidden = true; });

  // ---------------------------------------------------------------- Stage 3: power on / off
  function store(k, v) { try { if (v === undefined) { return localStorage.getItem(k); } localStorage.setItem(k, v); } catch (e) { return null; } return null; }
  function closePanels() { ["settings", "widgets", "files", "apps", "start"].forEach(function (p) { $(p).hidden = true; }); }
  function shutDown() {
    closePanels(); $("boot-text").textContent = "Shutting down…"; show("v-boot");
    api("POST", "/api/power", { action: "shutdown" }).then(function () {
      stopBeat(); $("screen").src = "about:blank"; store("abix_off", "1");
      setTimeout(function () { show("v-off"); }, 1800);
    });
  }
  function powerOn() {
    store("abix_off", "0"); $("boot-text").textContent = "Starting ABIX Computer…"; show("v-boot");
    setTimeout(startUp, 2200);
  }
  $("b-on").addEventListener("click", powerOn);

  // ---------------------------------------------------------------- Stage 3: brightness + night light (this browser only)
  function applyLook() {
    var b = parseInt(store("abix_bright") || "100", 10); if (isNaN(b) || b < 30 || b > 100) { b = 100; }
    var n = store("abix_night") === "1";
    $("screen").style.filter = b < 100 ? "brightness(" + (b / 100) + ")" : "none";   // no filter at 100%: keeps the screen on the fast path
    $("night").style.opacity = n ? "0.25" : "0"; $("night").style.display = n ? "block" : "none";
    $("s-bright").value = b; $("s-night").checked = n; markPerf();
  }
  $("s-bright").addEventListener("input", function () { store("abix_bright", $("s-bright").value); applyLook(); });
  $("s-night").addEventListener("change", function () { store("abix_night", $("s-night").checked ? "1" : "0"); applyLook(); });

  // ---------------------------------------------------------------- Stage 3: widgets
  var wtimer = null;
  function tickWidgets() {
    var d = new Date();
    $("w-time").textContent = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    $("w-date").textContent = d.toLocaleDateString([], { weekday: "long", year: "numeric", month: "long", day: "numeric" });
  }
  $("b-widgets").addEventListener("click", function () {
    var open = $("widgets").hidden; closePanels(); $("widgets").hidden = !open;
    clearInterval(wtimer);
    if (open) {
      tickWidgets(); wtimer = setInterval(tickWidgets, 15000);
      $("w-notes").value = store("abix_notes") || "";
      $("w-info").textContent = "abix-computer · " + ($("conn").textContent || "") + " · brightness " + ($("s-bright").value) + "%";
    }
  });
  $("w-close").addEventListener("click", function () { $("widgets").hidden = true; clearInterval(wtimer); });
  $("w-notes").addEventListener("input", function () { store("abix_notes", $("w-notes").value); });

  // ---------------------------------------------------------------- Stage 3: files (browse / download / upload)
  var cwd = "";
  function fmtSize(n) { if (n < 1024) { return n + " B"; } if (n < 1048576) { return (n / 1024).toFixed(1) + " KB"; } if (n < 1073741824) { return (n / 1048576).toFixed(1) + " MB"; } return (n / 1073741824).toFixed(2) + " GB"; }
  function loadDir(rel) {
    return api("GET", "/api/files?path=" + encodeURIComponent(rel)).then(function (r) {
      if (r.status !== 200) { $("f-msg").textContent = "Cannot open folder: " + ((r.data && r.data.error) || r.status); return; }
      cwd = r.data.path; $("f-path").textContent = "/" + cwd; $("f-msg").textContent = "";
      var ul = $("f-list"); ul.textContent = "";
      if (!r.data.items.length) { var e = document.createElement("li"); e.className = "hint"; e.textContent = "This folder is empty."; ul.appendChild(e); }
      r.data.items.forEach(function (it) {
        var li = document.createElement("li"), nm = document.createElement("button"), sz = document.createElement("span");
        nm.className = "nm"; nm.textContent = (it.type === "dir" ? "📁 " : "📄 ") + it.name;
        sz.className = "sz"; sz.textContent = it.type === "dir" ? "" : fmtSize(it.size);
        li.appendChild(nm); li.appendChild(sz);
        var next = (cwd ? cwd + "/" : "") + it.name;
        if (it.type === "dir") { nm.addEventListener("click", function () { loadDir(next); }); }
        else {
          nm.disabled = true;
          var a = document.createElement("a"); a.className = "dl"; a.textContent = "⬇"; a.title = "Download to your computer";
          a.href = "/api/files/download?path=" + encodeURIComponent(next); a.setAttribute("download", it.name);
          li.appendChild(a);
        }
        ul.appendChild(li);
      });
    });
  }
  $("b-files").addEventListener("click", function () {
    var open = $("files").hidden; closePanels(); $("files").hidden = !open;
    if (open) { loadDir(cwd || "Downloads"); }
  });
  $("f-close").addEventListener("click", function () { $("files").hidden = true; });
  $("f-home").addEventListener("click", function () { loadDir(""); });
  $("f-dl").addEventListener("click", function () { loadDir("Downloads"); });
  $("f-up-dir").addEventListener("click", function () { loadDir(cwd.indexOf("/") > -1 ? cwd.slice(0, cwd.lastIndexOf("/")) : ""); });
  $("f-new").addEventListener("click", function () {
    var name = window.prompt("New folder name:"); if (!name) { return; }
    api("POST", "/api/files/mkdir", { path: cwd, name: name }).then(function (r) {
      if (r.status === 200) { loadDir(cwd); } else { $("f-msg").textContent = "Could not create folder: " + ((r.data && r.data.error) || r.status); }
    });
  });
  function uploadOne(file) {
    return new Promise(function (resolve) {
      var x = new XMLHttpRequest();
      x.open("POST", "/api/files/upload?path=" + encodeURIComponent(cwd) + "&name=" + encodeURIComponent(file.name));
      x.setRequestHeader("X-Abix", "1"); x.setRequestHeader("Content-Type", "application/octet-stream");
      x.upload.onprogress = function (e) { if (e.lengthComputable) { $("f-prog").value = Math.round(e.loaded * 100 / e.total); } };
      x.onload = function () { var d = {}; try { d = JSON.parse(x.responseText); } catch (e) {} resolve(x.status === 200 ? null : (d.error || ("error " + x.status))); };
      x.onerror = function () { resolve("no connection"); };
      x.send(file);
    });
  }
  function uploadList(files) {
    if (!files.length) { return; }
    $("f-prog").hidden = false; var errs = [], i = 0;
    (function next() {
      if (i >= files.length) { $("f-prog").hidden = true; $("f-msg").textContent = errs.length ? "Failed: " + errs.join("; ") : "Uploaded " + files.length + " file(s)."; loadDir(cwd); return; }
      var f = files[i++]; $("f-msg").textContent = "Uploading " + f.name + "…"; $("f-prog").value = 0;
      uploadOne(f).then(function (e) { if (e) { errs.push(f.name + " (" + e + ")"); } next(); });
    })();
  }
  $("f-pick").addEventListener("change", function () { var files = Array.prototype.slice.call($("f-pick").files); $("f-pick").value = ""; uploadList(files); });
  // Stage 4: drag files from your PC onto the Files panel
  ["dragenter", "dragover"].forEach(function (t) { $("files").addEventListener(t, function (e) { e.preventDefault(); $("files").classList.add("drop"); }); });
  ["dragleave", "drop"].forEach(function (t) { $("files").addEventListener(t, function (e) { e.preventDefault(); $("files").classList.remove("drop"); }); });
  $("files").addEventListener("drop", function (e) { uploadList(Array.prototype.slice.call((e.dataTransfer && e.dataTransfer.files) || [])); });

  // ---------------------------------------------------------------- start
  function startUp() {
    api("GET", "/api/session").then(function (r) {
      var d = r.data || {};
      if (!d.authenticated) { show("v-login"); $("l-user").focus(); }
      else if (d.locked) { toLock(d.user); }
      else { toDesk(); }
    });
  }
  window.ABIX_APP = { toast: toast, store: store, api: api, powerAct: handlePower, closePanels: closePanels };
  applyLook();
  if (store("abix_off") === "1") { show("v-off"); } else { startUp(); }
})();
