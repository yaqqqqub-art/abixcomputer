(function () {
  "use strict";
  // V6 slice 1: animated ABIX logo (style + level, saved on the server), Start menu with real install status.
  var $ = function (id) { return document.getElementById(id); };
  var A = window.ABIX_APP;
  var STYLES = ["pulse", "orbit", "draw", "bloom", "aurora"], LEVELS = ["off", "light", "full"];
  var P = { logo_style: "pulse", logo_anim: "light", boot_anim: true };
  var serial = 0;

  // ------------------------------------------------------------ preferences
  function merge(src) {
    if (!src) { return; }
    if (STYLES.indexOf(src.logo_style) > -1) { P.logo_style = src.logo_style; }
    if (LEVELS.indexOf(src.logo_anim) > -1) { P.logo_anim = src.logo_anim; }
    if (typeof src.boot_anim === "boolean") { P.boot_anim = src.boot_anim; }
  }
  try { merge(JSON.parse(localStorage.getItem("abix_ui") || "{}")); } catch (e) { /* first visit */ }   // quick start before login; the server copy wins later
  function cache() { try { localStorage.setItem("abix_ui", JSON.stringify(P)); } catch (e) { /* private mode */ } }
  function applyPrefs() {
    var h = document.documentElement;
    LEVELS.forEach(function (l) { h.classList.toggle("anim-" + l, P.logo_anim === l); });
    h.setAttribute("data-ls", P.logo_style);
    Array.prototype.forEach.call(document.querySelectorAll(".seg[data-ui]"), function (seg) {
      var key = seg.getAttribute("data-ui");
      Array.prototype.forEach.call(seg.querySelectorAll("button"), function (b) { b.classList.toggle("on", b.getAttribute("data-v") === P[key]); });
    });
    $("s-bootanim").checked = P.boot_anim;
    var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    $("s-logohint").textContent = reduced ? "This device asks for reduced motion, so animations stay off here." :
      (P.logo_anim === "off" ? "Animation is off: the logo stays still and startup screens are skipped." : "Saved on the server, so it stays after a restart.");
  }
  function loadPrefs() {
    return A.api("GET", "/api/ui-prefs").then(function (r) { if (r.status === 200) { merge(r.data.prefs); cache(); applyPrefs(); } });
  }
  function savePref(patch) {
    merge(patch); cache(); applyPrefs(); renderLogos(true);
    A.api("POST", "/api/ui-prefs", patch).then(function (r) {
      if (r.status !== 200) { A.toast("Could not save: " + ((r.data && (r.data.error || JSON.stringify(r.data.errors))) || r.status)); loadPrefs(); }
    });
  }

  // ------------------------------------------------------------ the animated logo (inline SVG, no inline styles: CSP safe)
  function logoSvg() {
    var n = ++serial;
    return '<svg class="alogo-svg" viewBox="-14 -14 92 92" aria-hidden="true"><defs><linearGradient id="alg' + n + '" x1="0" y1="0" x2="1" y2="1">' +
      '<stop offset="0" stop-color="#4cc2ff"/><stop offset="1" stop-color="#7a5cff"/></linearGradient></defs>' +
      '<circle class="ring r1" cx="32" cy="32" r="36" fill="none" stroke="#4cc2ff" stroke-width="1.6"/>' +
      '<circle class="ring r2" cx="32" cy="32" r="36" fill="none" stroke="#7a5cff" stroke-width="1.6"/>' +
      '<g class="dots"><circle class="dot" cx="32" cy="-9" r="2.8" fill="#4cc2ff"/><circle class="dot" cx="73" cy="32" r="2.8" fill="#7a5cff"/>' +
      '<circle class="dot" cx="32" cy="73" r="2.8" fill="#4cc2ff"/><circle class="dot" cx="-9" cy="32" r="2.8" fill="#7a5cff"/></g>' +
      '<g class="body"><rect class="tile" x="4" y="4" width="56" height="56" rx="14" fill="url(#alg' + n + ')"/>' +
      '<path class="glyph" pathLength="100" d="M20 44 32 18l12 26h-6l-2.4-5.6h-7.2L26 44z M30 34h4l-2-4.8z" fill="#fff" stroke="#fff" stroke-width="1" stroke-linejoin="round"/></g></svg>';
  }
  function renderLogos(replay) {
    Array.prototype.forEach.call(document.querySelectorAll(".alogo"), function (el) {
      if (replay || !el.firstChild) { el.innerHTML = logoSvg(); }
    });
  }

  // ------------------------------------------------------------ Start menu
  var items = [], cats = [];
  function chip(it) { return it.state === "not_installed" ? "Not installed" : it.state === "web" ? "Web app" : it.state === "windows_only" ? "Windows only" : ""; }
  function tile(it) {
    var b = document.createElement("button"); b.type = "button"; b.className = "app-tile" + (it.can_launch ? "" : " dim");
    b.title = it.desc + (it.note ? " - " + it.note : ""); b.setAttribute("data-id", it.id);
    var img = document.createElement("img"); img.alt = ""; img.loading = "lazy"; img.src = "icons/" + it.icon;
    img.addEventListener("error", function () { img.replaceWith(Object.assign(document.createElement("span"), { className: "fallback", textContent: it.name.charAt(0) })); });
    var nm = document.createElement("span"); nm.className = "nm"; nm.textContent = it.name;
    b.appendChild(img); b.appendChild(nm);
    if (chip(it)) { var c = document.createElement("span"); c.className = "chip"; c.textContent = chip(it); b.appendChild(c); }
    b.addEventListener("click", function () { open(it); });
    return b;
  }
  function render() {
    var q = $("st-search").value.trim().toLowerCase(), box = $("st-groups"); box.textContent = "";
    cats.forEach(function (cat) {
      var list = items.filter(function (it) { return it.category === cat && (!q || (it.name + " " + it.desc).toLowerCase().indexOf(q) > -1); });
      if (!list.length) { return; }
      var g = document.createElement("section"); g.className = "st-group";
      var h = document.createElement("h3"); h.textContent = cat; g.appendChild(h);
      var grid = document.createElement("div"); grid.className = "st-grid";
      list.forEach(function (it) { grid.appendChild(tile(it)); }); g.appendChild(grid); box.appendChild(g);
    });
    if (!box.firstChild) { var p = document.createElement("p"); p.className = "hint"; p.textContent = q ? "No app matches your search." : "Loading apps…"; box.appendChild(p); }
  }
  function load() {
    return A.api("GET", "/api/launcher").then(function (r) {
      if (r.status === 200) { items = r.data.items || []; cats = r.data.categories || []; render(); }
      else if (!items.length) { $("st-msg").textContent = "Could not load the app list."; }
    });
  }
  function open(it) {
    if (!it.can_launch) {
      $("st-msg").textContent = it.name + ": " + (it.note || "cannot be started.");
      if (it.install_id) { A.closePanels(); $("b-apps").click(); A.toast(it.name + " is not installed. Install it here."); }
      return;
    }
    $("st-msg").textContent = "Starting " + it.name + "…";
    A.api("POST", "/api/launcher/launch", { id: it.id }).then(function (r) {
      if (r.status === 200) { $("st-msg").textContent = ""; $("start").hidden = true; A.toast((r.data && r.data.message) || (it.name + " started")); }
      else { $("st-msg").textContent = (r.data && r.data.error) || ("Could not start " + it.name); }
    });
  }
  $("b-start").addEventListener("click", function (e) {
    e.stopPropagation();
    var show = $("start").hidden; A.closePanels(); $("start").hidden = !show;
    if (show) { $("st-msg").textContent = ""; $("st-search").value = ""; render(); load(); setTimeout(function () { $("st-search").focus(); }, 30); }
  });
  $("st-search").addEventListener("input", render);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") { $("start").hidden = true; } });
  Array.prototype.forEach.call(document.querySelectorAll("[data-pact]"), function (b) {
    b.addEventListener("click", function () { $("start").hidden = true; A.powerAct(b.getAttribute("data-pact")); });
  });

  // ------------------------------------------------------------ settings controls
  Array.prototype.forEach.call(document.querySelectorAll(".seg[data-ui]"), function (seg) {
    seg.addEventListener("click", function (e) {
      var v = e.target.getAttribute("data-v"); if (!v) { return; }
      var patch = {}; patch[seg.getAttribute("data-ui")] = v; savePref(patch);
    });
  });
  $("s-bootanim").addEventListener("change", function () { savePref({ boot_anim: $("s-bootanim").checked }); });
  $("s-preview").addEventListener("click", function () { renderLogos(true); });

  window.ABIX_UI = { get: function () { return P; }, onDesk: loadPrefs };
  applyPrefs(); renderLogos(false);
})();
