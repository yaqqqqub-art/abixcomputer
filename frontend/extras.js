/* ABIX extras (Stage 4): click sounds, copy / paste between your device and the cloud PC. */
(function () {
  "use strict";
  var hasDoc = typeof document !== "undefined" && document.getElementById("clip-menu");
  var $ = function (id) { return document.getElementById(id); };
  var store = function (k, v) { try { if (v === undefined) { return localStorage.getItem(k); } localStorage.setItem(k, v); } catch (e) { return null; } return null; };

  // ------------------------------------------------------------------ click sounds (WebAudio, nothing to download)
  var ctx = null, soundOn = true;
  function blip(f0, f1, dur, vol, type) {
    if (!soundOn) { return; }
    try {
      var AC = window.AudioContext || window.webkitAudioContext; if (!AC) { return; }
      ctx = ctx || new AC(); if (ctx.state === "suspended") { ctx.resume(); }
      var o = ctx.createOscillator(), g = ctx.createGain(), t = ctx.currentTime;
      o.type = type || "sine"; o.frequency.setValueAtTime(f0, t); o.frequency.exponentialRampToValueAtTime(f1, t + dur);
      g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur + 0.02);
      o.connect(g); g.connect(ctx.destination); o.start(t); o.stop(t + dur + 0.03);
    } catch (e) { /* sound is optional */ }
  }
  var SND = { tick: function () { blip(1100, 600, 0.025, 0.05, "sine"); }, tap: function () { blip(260, 120, 0.045, 0.12, "sine"); } };
  if (typeof window !== "undefined") { window.ABIX_SOUND = SND; }
  if (typeof module !== "undefined") { module.exports = { SND: SND }; }
  if (!hasDoc) { return; }

  soundOn = store("abix_uisound") !== "0";
  $("s-sound").checked = soundOn;
  $("s-sound").addEventListener("change", function () { soundOn = $("s-sound").checked; store("abix_uisound", soundOn ? "1" : "0"); SND.tick(); });
  // Every button gets a soft tick. The on-screen keyboard keys have their own (louder) key sound.
  document.addEventListener("pointerdown", function (e) {
    var b = e.target.closest && e.target.closest("button,.btn,.sw,.wall");
    if (b && !b.closest("#osk-keys") && !b.closest("#mpad")) { SND.tick(); }
  }, true);

  // ------------------------------------------------------------------ copy / paste
  function say(t) { $("clip-msg").textContent = t; if (window.ABIX_APP) { window.ABIX_APP.toast(t); } }
  function remote() {
    try {
      var d = $("screen").contentDocument, c = d && d.querySelector("canvas");
      return c ? { win: $("screen").contentWindow, doc: d, el: c, box: d.getElementById("noVNC_clipboard_text") } : null;
    } catch (e) { return null; }
  }
  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  var MOD = { Control: "ControlLeft", Shift: "ShiftLeft" };
  // Sends a key combination, e.g. combo(["Control"], "KeyC", "c") = Ctrl+C
  function combo(mods, code, key) {
    var r = remote(); if (!r) { return false; }
    var down = {}, W = r.win;
    function ev(type, k, c, loc) {
      r.el.dispatchEvent(new W.KeyboardEvent(type, { key: k, code: c, location: loc, bubbles: true, cancelable: true, ctrlKey: !!down.Control, shiftKey: !!down.Shift }));
    }
    try { r.el.focus(); } catch (e) {}
    mods.forEach(function (m) { down[m] = true; ev("keydown", m, MOD[m], 1); });
    ev("keydown", key, code, 0); ev("keyup", key, code, 0);
    mods.slice().reverse().forEach(function (m) { ev("keyup", m, MOD[m], 1); delete down[m]; });
    return true;
  }
  function notReady() { say("The desktop is not connected yet."); }

  // device -> cloud PC: put the text into noVNC's clipboard box, then press the paste shortcut
  function readLocal() {
    var fb = $("clip-text").value;
    if (navigator.clipboard && navigator.clipboard.readText) {
      return navigator.clipboard.readText().then(function (t) { return t || fb; }, function () { return fb; });
    }
    return Promise.resolve(fb);
  }
  function paste(terminal) {
    var r = remote(); if (!r || !r.box) { notReady(); return; }
    readLocal().then(function (text) {
      if (!text) { say("Nothing to paste. Copy something on your device first, or type it in the box and press Paste."); return; }
      r.box.value = text; r.box.dispatchEvent(new r.win.Event("change", { bubbles: true }));
      return wait(180).then(function () {
        combo(terminal ? ["Control", "Shift"] : ["Control"], "KeyV", terminal ? "V" : "v");
        say("Pasted " + text.length + " characters.");
      });
    });
  }
  // cloud PC -> device: press copy, wait for the PC to send its clipboard back, then write it to your device
  function copy(cut, terminal) {
    var r = remote(); if (!r || !r.box) { notReady(); return; }
    var before = r.box.value;
    if (cut) { combo(["Control"], "KeyX", "x"); }
    else if (terminal) { combo(["Control", "Shift"], "KeyC", "C"); }
    else { combo(["Control"], "KeyC", "c"); }
    var tries = 0;
    (function poll() {
      tries++;
      var now = r.box.value;
      if (now && (now !== before || tries >= 6)) {
        $("clip-text").value = now;
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(now).then(function () { say("Copied " + now.length + " characters to your device."); },
            function () { say("Copied to the box in this menu. Your browser blocked the clipboard, so copy it from the box."); });
        } else { say("Copied to the box in this menu. Copy it from there."); }
        return;
      }
      if (tries >= 6) { say("Nothing was copied. Select some text on the desktop first."); return; }
      setTimeout(poll, 120);
    })();
  }
  function selectAll() { if (!combo(["Control"], "KeyA", "a")) { notReady(); } }

  $("c-copy").addEventListener("click", function () { copy(false, false); });
  $("c-cut").addEventListener("click", function () { copy(true, false); });
  $("c-paste").addEventListener("click", function () { paste(false); });
  $("c-all").addEventListener("click", selectAll);
  $("c-tcopy").addEventListener("click", function () { copy(false, true); });
  $("c-tpaste").addEventListener("click", function () { paste(true); });
  $("osk-copy").addEventListener("click", function () { copy(false, false); });
  $("osk-paste").addEventListener("click", function () { paste(false); });

  $("b-clip").addEventListener("click", function (e) { e.stopPropagation(); if (window.ABIX_CLOSE_MENUS) { window.ABIX_CLOSE_MENUS("clip-menu"); } $("clip-menu").hidden = !$("clip-menu").hidden; });
  $("clip-menu").addEventListener("click", function (e) { e.stopPropagation(); });
  document.addEventListener("click", function () { $("clip-menu").hidden = true; });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") { $("clip-menu").hidden = true; $("mouse-menu").hidden = true; } });
  // keep Power menu and the new menus from overlapping
  $("b-power").addEventListener("click", function () { if (window.ABIX_CLOSE_MENUS) { window.ABIX_CLOSE_MENUS("power-menu"); } });
})();
