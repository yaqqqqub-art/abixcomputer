/* ABIX on-screen keyboard (Stage 3.1): full 104-key layout, RGB glow, click sound, key names.
   Keys are sent to the desktop by dispatching KeyboardEvents on the noVNC canvas (same origin iframe). */
(function () {
  "use strict";
  var NAMES = {
    "`": "Grave / Backtick (Tilde with Shift)", "~": "Tilde", "!": "Exclamation Mark", "@": "At Sign", "#": "Hash", "$": "Dollar", "%": "Percent", "^": "Caret",
    "&": "Ampersand", "*": "Asterisk", "(": "Left Parenthesis", ")": "Right Parenthesis", "-": "Hyphen (Underscore with Shift)", "_": "Underscore",
    "=": "Equals (Plus with Shift)", "+": "Plus", "[": "Left Bracket (Brace with Shift)", "]": "Right Bracket (Brace with Shift)", "{": "Left Brace", "}": "Right Brace",
    "\\": "Backslash (Vertical Bar with Shift)", "|": "Vertical Bar", ";": "Semicolon (Colon with Shift)", ":": "Colon", "'": "Apostrophe (Quotation Mark with Shift)", "\"": "Quotation Mark",
    ",": "Comma (Less-than with Shift)", ".": "Period (Greater-than with Shift)", "/": "Slash (Question Mark with Shift)", "?": "Question Mark", "<": "Less-than", ">": "Greater-than"
  };
  var rows = [];            // each row: array of items. item = key {code,key,label,shift,shiftLabel,name,w,loc,type} or spacer {sp:w}
  function K(code, key, label, o) { o = o || {}; return { code: code, key: key, label: label, shift: o.shift || null, shiftLabel: o.shiftLabel || null, name: o.name || label, w: o.w || 1, loc: o.loc || 0, type: o.type || "key" }; }
  function S(w) { return { sp: w }; }
  function mod(code, key, label, name, w, loc) { return K(code, key, label, { name: name, w: w, loc: loc, type: "mod" }); }
  function sym(code, a, b) { return K(code, a, a, { shift: b, shiftLabel: b, name: NAMES[a] || NAMES[b] || a }); }
  function letter(c) { return K("Key" + c, c.toLowerCase(), c, { shift: c, shiftLabel: c, name: "Letter " + c, type: "letter" }); }
  function digit(d, sh) { return K("Digit" + d, d, d, { shift: sh, shiftLabel: sh, name: "Number " + d + " (" + NAMES[sh] + " with Shift)" }); }
  function np(code, key, label, name) { return K(code, key, label, { name: "Keypad " + name, loc: 3, type: "num" }); }
  function spec(code, key, label, name, w) { return K(code, key, label, { name: name, w: w || 1, type: "spec" }); }

  var r0 = [K("Escape", "Escape", "Esc", { name: "Escape", type: "spec" }), S(1)];
  for (var f = 1; f <= 4; f++) { r0.push(spec("F" + f, "F" + f, "F" + f, "Function Key F" + f)); }
  r0.push(S(0.5)); for (f = 5; f <= 8; f++) { r0.push(spec("F" + f, "F" + f, "F" + f, "Function Key F" + f)); }
  r0.push(S(0.5)); for (f = 9; f <= 12; f++) { r0.push(spec("F" + f, "F" + f, "F" + f, "Function Key F" + f)); }
  r0.push(S(0.5), spec("PrintScreen", "PrintScreen", "PrtSc", "Print Screen"), spec("ScrollLock", "ScrollLock", "ScrLk", "Scroll Lock"), spec("Pause", "Pause", "Pause", "Pause / Break"), S(0.5 + 4));

  var NUMSH = [")", "!", "@", "#", "$", "%", "^", "&", "*", "("];
  var r1 = [K("Backquote", "`", "`", { shift: "~", shiftLabel: "~", name: NAMES["`"] })];
  for (var d = 1; d <= 9; d++) { r1.push(digit(String(d), NUMSH[d])); }
  r1.push(digit("0", ")"), sym("Minus", "-", "_"), sym("Equal", "=", "+"), spec("Backspace", "Backspace", "Backspace", "Backspace", 2), S(0.5),
    spec("Insert", "Insert", "Ins", "Insert"), spec("Home", "Home", "Home", "Home"), spec("PageUp", "PageUp", "PgUp", "Page Up"), S(0.5),
    K("NumLock", "NumLock", "Num", { name: "Num Lock", type: "lock" }), np("NumpadDivide", "/", "/", "Slash"), np("NumpadMultiply", "*", "*", "Asterisk"), np("NumpadSubtract", "-", "-", "Minus"));

  var r2 = [spec("Tab", "Tab", "Tab", "Tab", 1.5)];
  "QWERTYUIOP".split("").forEach(function (c) { r2.push(letter(c)); });
  r2.push(sym("BracketLeft", "[", "{"), sym("BracketRight", "]", "}"), K("Backslash", "\\", "\\", { shift: "|", shiftLabel: "|", name: NAMES["\\"], w: 1.5 }), S(0.5),
    spec("Delete", "Delete", "Del", "Delete"), spec("End", "End", "End", "End"), spec("PageDown", "PageDown", "PgDn", "Page Down"), S(0.5),
    np("Numpad7", "7", "7", "7"), np("Numpad8", "8", "8", "8"), np("Numpad9", "9", "9", "9"), np("NumpadAdd", "+", "+", "Plus"));

  var r3 = [K("CapsLock", "CapsLock", "Caps Lock", { name: "Caps Lock", w: 1.75, type: "lock" })];
  "ASDFGHJKL".split("").forEach(function (c) { r3.push(letter(c)); });
  r3.push(sym("Semicolon", ";", ":"), sym("Quote", "'", "\""), spec("Enter", "Enter", "Enter", "Enter", 2.25), S(0.5), S(3), S(0.5),
    np("Numpad4", "4", "4", "4"), np("Numpad5", "5", "5", "5"), np("Numpad6", "6", "6", "6"), S(1));

  var r4 = [mod("ShiftLeft", "Shift", "Shift", "Shift", 2.25, 1)];
  "ZXCVBNM".split("").forEach(function (c) { r4.push(letter(c)); });
  r4.push(sym("Comma", ",", "<"), sym("Period", ".", ">"), sym("Slash", "/", "?"), mod("ShiftRight", "Shift", "Shift", "Shift", 2.75, 2), S(0.5),
    S(1), spec("ArrowUp", "ArrowUp", "↑", "Up Arrow"), S(1), S(0.5),
    np("Numpad1", "1", "1", "1"), np("Numpad2", "2", "2", "2"), np("Numpad3", "3", "3", "3"), K("NumpadEnter", "Enter", "Enter", { name: "Keypad Enter", loc: 3, type: "num" }));

  var r5 = [mod("ControlLeft", "Control", "Ctrl", "Control", 1.25, 1), mod("MetaLeft", "Meta", "Win", "Windows Key", 1.25, 1), mod("AltLeft", "Alt", "Alt", "Alternate", 1.25, 1),
    K("Space", " ", "Space", { name: "Spacebar", w: 6.25, type: "spec" }), mod("AltRight", "Alt", "Alt", "Alternate", 1.25, 2), mod("MetaRight", "Meta", "Win", "Windows Key", 1.25, 2),
    spec("ContextMenu", "ContextMenu", "Menu", "Menu Key", 1.25), mod("ControlRight", "Control", "Ctrl", "Control", 1.25, 2), S(0.5),
    spec("ArrowLeft", "ArrowLeft", "←", "Left Arrow"), spec("ArrowDown", "ArrowDown", "↓", "Down Arrow"), spec("ArrowRight", "ArrowRight", "→", "Right Arrow"), S(0.5),
    K("Numpad0", "0", "0", { name: "Keypad 0", w: 2, loc: 3, type: "num" }), np("NumpadDecimal", ".", ".", "Decimal Point"), S(1)];
  rows = [r0, r1, r2, r3, r4, r5];

  var $ = function (id) { return document.getElementById(id); };
  var osk = typeof document !== "undefined" ? $("osk") : null;
  if (typeof window !== "undefined") { window.ABIX_KEYBOARD = { rows: rows }; }
  if (typeof module !== "undefined") { module.exports = { rows: rows }; }
  if (!osk) { return; }

  // ------------------------------------------------------------ state
  function store(k, v) { try { if (v === undefined) { return localStorage.getItem(k); } localStorage.setItem(k, v); } catch (e) { return null; } return null; }
  var state = { shift: false, caps: false, num: true, latched: {}, rgb: store("abix_krgb") !== "0", sound: store("abix_ksound") !== "0" };
  var els = {};            // code -> element
  var objs = {};           // code -> key object
  var ctx = null, idx = 0;

  function target() {
    try { var d = $("screen").contentDocument; var c = d && d.querySelector("canvas"); return c ? { win: $("screen").contentWindow, el: c } : null; } catch (e) { return null; }
  }
  function mods() {
    var l = state.latched;
    return { shiftKey: !!(l.ShiftLeft || l.ShiftRight), ctrlKey: !!(l.ControlLeft || l.ControlRight), altKey: !!(l.AltLeft || l.AltRight), metaKey: !!(l.MetaLeft || l.MetaRight) };
  }
  function fire(type, o, keyName) {
    var t = target(); if (!t) { return false; }
    var m = mods();
    t.el.dispatchEvent(new t.win.KeyboardEvent(type, { key: keyName, code: o.code, location: o.loc, bubbles: true, cancelable: true, shiftKey: m.shiftKey, ctrlKey: m.ctrlKey, altKey: m.altKey, metaKey: m.metaKey }));
    return true;
  }
  function effKey(o) { return (state.shift && o.shift) ? o.shift : o.key; }
  function say(txt) { $("osk-name").textContent = txt; }

  function click() {
    if (!state.sound) { return; }
    try {
      var AC = window.AudioContext || window.webkitAudioContext; if (!AC) { return; }
      ctx = ctx || new AC(); if (ctx.state === "suspended") { ctx.resume(); }
      var o = ctx.createOscillator(), g = ctx.createGain(), t = ctx.currentTime;
      o.type = "square"; o.frequency.setValueAtTime(1500, t); o.frequency.exponentialRampToValueAtTime(300, t + 0.03);
      g.gain.setValueAtTime(0.05, t); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.05);
      o.connect(g); g.connect(ctx.destination); o.start(t); o.stop(t + 0.06);
    } catch (e) { /* sound is optional */ }
  }

  function relabel() {
    var up = state.shift;
    Object.keys(els).forEach(function (code) {
      var o = objs[code], b = els[code];
      if (o.type === "letter") { b.textContent = (up !== state.caps) ? o.label.toUpperCase() : o.label.toLowerCase(); }
      else if (o.shift) { b.textContent = up ? o.shiftLabel : o.label; }
      if (o.type === "mod") { b.classList.toggle("on", !!state.latched[code]); }
      if (code === "CapsLock") { b.classList.toggle("on", state.caps); }
      if (code === "NumLock") { b.classList.toggle("on", state.num); }
    });
  }
  function releaseLatched() {
    var any = false;
    Object.keys(state.latched).forEach(function (c) { if (state.latched[c]) { state.latched[c] = false; fire("keyup", objs[c], objs[c].key); any = true; } });
    if (any) { state.shift = false; relabel(); }
  }

  function press(o) {
    click(); say(o.label + " — " + o.name);
    if (o.type === "mod") {
      var on = !state.latched[o.code];
      state.latched[o.code] = on; fire(on ? "keydown" : "keyup", o, o.key);   // flags: on at keydown, off at keyup (like a real keyboard)
      state.shift = !!(state.latched.ShiftLeft || state.latched.ShiftRight); relabel(); return;
    }
    if (!fire("keydown", o, effKey(o))) { say("Desktop is not ready yet"); return; }
    if (o.type === "lock") {
      fire("keyup", o, o.key);
      if (o.code === "CapsLock") { state.caps = !state.caps; } else { state.num = !state.num; }
      relabel();
    }
  }
  function release(o) {
    if (o.type === "mod" || o.type === "lock") { return; }
    fire("keyup", o, effKey(o));
    releaseLatched();
  }

  // ------------------------------------------------------------ build
  var host = $("osk-keys"); host.textContent = "";
  rows.forEach(function (row) {
    var line = document.createElement("div"); line.className = "osk-row";
    row.forEach(function (it) {
      if (it.sp !== undefined) { var s = document.createElement("span"); s.className = "osk-sp"; s.style.flex = it.sp + " " + it.sp + " 0"; line.appendChild(s); return; }
      var b = document.createElement("button"); b.type = "button"; b.className = "k k-" + it.type; b.textContent = it.label;
      b.title = it.label + " — " + it.name; b.setAttribute("aria-label", it.name);
      b.style.flex = it.w + " " + it.w + " 0"; b.style.animationDelay = (-(idx++) * 55) + "ms";
      els[it.code] = b; objs[it.code] = it;
      b.addEventListener("pointerdown", function (e) { e.preventDefault(); try { b.setPointerCapture(e.pointerId); } catch (x) {} b.classList.add("down"); press(it); });
      var up = function () { if (b.classList.contains("down")) { b.classList.remove("down"); release(it); } };
      b.addEventListener("pointerup", up); b.addEventListener("pointercancel", up); b.addEventListener("lostpointercapture", up);
      b.addEventListener("mouseenter", function () { say(it.label + " — " + it.name); });
      line.appendChild(b);
    });
    host.appendChild(line);
  });

  // The Power key opens the existing power menu (restart / sleep / sign out / shut down all ask for confirmation).
  var pw = document.createElement("button"); pw.type = "button"; pw.className = "k k-spec k-power"; pw.textContent = "⏻"; pw.title = "Power — opens the power menu"; pw.setAttribute("aria-label", "Power key");
  pw.addEventListener("click", function () { click(); say("Power — power menu opened"); $("b-power").click(); });
  $("osk-head-keys").appendChild(pw);

  // ------------------------------------------------------------ physical keyboard feedback (lights up the same key)
  function physical(e, down) {
    var b = els[e.code]; if (!b) { return; }
    b.classList.toggle("down", down);
    if (down) { click(); say(objs[e.code].label + " — " + objs[e.code].name); }
  }
  function hook(doc) { if (!doc) { return; } doc.addEventListener("keydown", function (e) { if (!osk.hidden && e.isTrusted) { physical(e, true); } }, true); doc.addEventListener("keyup", function (e) { if (!osk.hidden && e.isTrusted) { physical(e, false); } }, true); }
  hook(document);
  $("screen").addEventListener("load", function () { try { hook($("screen").contentDocument); } catch (e) {} });

  // ------------------------------------------------------------ toggles
  function look() { osk.classList.toggle("rgb", state.rgb); $("osk-rgb").setAttribute("aria-pressed", String(state.rgb)); $("osk-snd").setAttribute("aria-pressed", String(state.sound)); $("osk-rgb").classList.toggle("on", state.rgb); $("osk-snd").classList.toggle("on", state.sound); }
  $("osk-rgb").addEventListener("click", function () { state.rgb = !state.rgb; store("abix_krgb", state.rgb ? "1" : "0"); look(); });
  $("osk-snd").addEventListener("click", function () { state.sound = !state.sound; store("abix_ksound", state.sound ? "1" : "0"); look(); click(); });
  $("osk-close").addEventListener("click", function () { osk.hidden = true; });
  $("b-kbd").addEventListener("click", function () { osk.hidden = !osk.hidden; if (!osk.hidden) { say("Press a key to see its name"); click(); } });
  look(); relabel();
})();
