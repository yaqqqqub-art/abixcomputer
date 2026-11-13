/* ABIX App Center (Stage 5): install apps from the catalog and download Windows setup files (run in Wine). */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  if (typeof document === "undefined" || !$("apps")) { return; }
  var state = { items: [], wine: true, busy: false, timer: null };

  function api(method, path, body) {
    var opt = { method: method, credentials: "same-origin", headers: {} };
    if (method === "POST") { opt.headers["Content-Type"] = "application/json"; opt.headers["X-Abix"] = "1"; opt.body = JSON.stringify(body || {}); }
    return fetch(path, opt).then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return { status: r.status, data: d }; }); })
      .catch(function () { return { status: 0, data: { error: "no connection to the server" } }; });
  }
  function toast(t) { if (window.ABIX_APP) { window.ABIX_APP.toast(t); } }

  function render() {
    var box = $("a-list"), q = ($("a-search").value || "").toLowerCase().trim();
    box.textContent = "";
    var cats = {};
    state.items.forEach(function (a) {
      if (q && (a.name + " " + a.desc + " " + a.category).toLowerCase().indexOf(q) < 0) { return; }
      (cats[a.category] = cats[a.category] || []).push(a);
    });
    var names = Object.keys(cats).sort();
    if (!names.length) { var p = document.createElement("p"); p.className = "hint"; p.textContent = "No app found."; box.appendChild(p); return; }
    names.forEach(function (c) {
      var h = document.createElement("h4"); h.textContent = c; box.appendChild(h);
      cats[c].forEach(function (a) {
        var row = document.createElement("div"); row.className = "arow";
        var t = document.createElement("div"); t.className = "atext";
        var n = document.createElement("strong"); n.textContent = a.name;
        var d = document.createElement("span"); d.className = "hint"; d.textContent = a.note || a.desc;
        t.appendChild(n); t.appendChild(d);
        var b = document.createElement("button"); b.className = "btn" + (a.installed ? "" : " primary"); b.type = "button";
        b.textContent = a.installed ? "Remove" : "Install";
        b.disabled = !a.supported || state.busy;
        b.addEventListener("click", function () { run(a.installed ? "/api/apps/uninstall" : "/api/apps/install", { id: a.id }); });
        row.appendChild(t); row.appendChild(b); box.appendChild(row);
      });
    });
  }

  function load() {
    return api("GET", "/api/apps").then(function (r) {
      if (r.status !== 200) { return; }
      state.items = r.data.items || []; state.wine = !!r.data.wine;
      $("a-wine").textContent = state.wine ? "" : "Wine is not installed in this image, so Windows setup files can be downloaded but not run. Rebuild with ABIX_WINE=1.";
      var running = (r.data.jobs || []).filter(function (j) { return j.state === "running"; })[0];
      state.busy = !!running; render();
      if (running) { follow(running.id); }
    });
  }

  function show(j) {
    $("a-jobbox").hidden = false; $("a-jobtitle").textContent = j.title || "Working…";
    $("a-prog").value = j.percent || 0; $("a-msg").textContent = j.message || "";
    var lg = $("a-log"); lg.textContent = (j.log || []).join("\n"); lg.scrollTop = lg.scrollHeight;
  }
  function follow(id) {
    clearInterval(state.timer); state.busy = true; render();
    function tick() {
      api("GET", "/api/apps/job?id=" + encodeURIComponent(id)).then(function (r) {
        if (r.status !== 200) { clearInterval(state.timer); state.busy = false; render(); return; }
        show(r.data);
        if (r.data.state !== "running") {
          clearInterval(state.timer); state.busy = false; toast(r.data.message); load();
        }
      });
    }
    tick(); state.timer = setInterval(tick, 1200);
  }
  function run(path, body) {
    api("POST", path, body).then(function (r) {
      if (r.status === 202) { follow(r.data.job); }
      else { toast((r.data && r.data.error) || "Could not start (error " + r.status + ")"); $("a-msg").textContent = (r.data && r.data.error) || ""; }
    });
  }

  $("a-go").addEventListener("click", function () {
    var u = $("a-url").value.trim();
    if (!u) { toast("Paste a download link first."); return; }
    run("/api/apps/windows", { url: u });
  });
  $("a-url").addEventListener("keydown", function (e) { if (e.key === "Enter") { $("a-go").click(); } });
  $("a-search").addEventListener("input", render);
  $("a-close").addEventListener("click", function () { $("apps").hidden = true; });
  $("b-apps").addEventListener("click", function () {
    var open = $("apps").hidden;
    ["settings", "widgets", "files"].forEach(function (p) { $(p).hidden = true; });
    $("apps").hidden = !open;
    if (open) { load(); }
  });
  // opening another panel closes this one
  ["b-settings", "b-widgets", "b-files"].forEach(function (b) { $(b).addEventListener("click", function () { $("apps").hidden = true; }, true); });
})();
