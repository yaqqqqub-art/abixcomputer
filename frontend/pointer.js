/* ABIX pointer modes (Stage 4).
   normal   : the browser's own mouse/touch handling inside noVNC (default on a PC with a mouse)
   touchpad : the whole screen is a laptop trackpad. 1 finger = move, tap = click, tap+hold+drag = drag,
              2-finger tap = right click, 2-finger drag = scroll. A pointer arrow is drawn on top.
   mousepad : same trackpad logic, but on a small on-screen pad with Left/Right buttons and a scroll strip.
   direct   : tap where you want. Tap = click, long press = right click, drag = drag, 2-finger drag = scroll.
   The engine is plain logic (no DOM) so it can be tested with node: node tests/unit/test_pointer.js */
(function () {
  "use strict";

  // ------------------------------------------------------------------ engine
  // opt.emit(type, x, y, button, dx, dy)  type: "move" | "down" | "up" | "wheel"; button 0 = left, 2 = right
  // opt.bounds() -> {l, t, r, b} area the pointer may move in; opt.later(fn, ms); opt.onClick() optional (sound)
  function createEngine(opt) {
    var TAP_MS = 300, TAP_SLOP = 10, LONG_MS = 550, DRAG_SLOP = 8;
    var cfg = { speed: 1, natural: true, mode: "touchpad" };
    var cur = { x: 0, y: 0 }, held = {}, touches = {}, g = null, lastTap = null, longTimer = null;
    var later = opt.later || function (f, ms) { return setTimeout(f, ms); };
    var cancelLater = opt.cancelLater || function (h) { clearTimeout(h); };

    function box() { return opt.bounds ? opt.bounds() : { l: 0, t: 0, r: 1e9, b: 1e9 }; }
    function clamp() { var b = box(); cur.x = Math.min(b.r, Math.max(b.l, cur.x)); cur.y = Math.min(b.b, Math.max(b.t, cur.y)); }
    function count() { return Object.keys(touches).length; }
    function center() { var b = box(); cur.x = (b.l + b.r) / 2; cur.y = (b.t + b.b) / 2; }
    function emit(type, button, dx, dy) { opt.emit(type, cur.x, cur.y, button || 0, dx || 0, dy || 0); }
    function press(btn) { if (held[btn]) { return; } held[btn] = true; emit("move"); emit("down", btn); }
    function release(btn) { if (!held[btn]) { return; } held[btn] = false; emit("up", btn); }
    function click(btn) {
      emit("move"); emit("down", btn);
      if (opt.onClick) { opt.onClick(btn); }
      later(function () { emit("up", btn); }, 25);
    }
    function setAt(x, y) { cur.x = x; cur.y = y; clamp(); emit("move"); }
    function scrollBy(dx, dy) {                 // dx, dy = finger movement in px
      var k = cfg.natural ? -1 : 1; emit("wheel", 0, k * dx * 1.5, k * dy * 1.5);
    }
    function stopLong() { if (longTimer !== null) { cancelLater(longTimer); longTimer = null; } }
    function mid() { var ids = Object.keys(touches), a = touches[ids[0]], b = touches[ids[1]]; return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }; }

    function startTwo(t) {
      stopLong();
      if (g && g.drag) { release(0); }
      if (g && g.pressed) { release(0); }
      var m = mid(); g = { kind: "two", t0: t, cx: m.x, cy: m.y, total: 0, scrolled: false };
    }

    function down(id, x, y, t) {
      touches[id] = { x: x, y: y };
      var n = count();
      if (n === 2 && g && (g.kind === "one" || g.kind === "d1")) { startTwo(t); return; }
      if (n !== 1) { if (n > 2) { g = { kind: "ignore" }; } return; }
      if (cfg.mode === "direct") {
        setAt(x, y);
        g = { kind: "d1", id: id, t0: t, x0: x, y0: y, pressed: false, long: false };
        stopLong();
        longTimer = later(function () {
          longTimer = null;
          if (g && g.kind === "d1" && !g.pressed && count() === 1) { g.long = true; click(2); }
        }, LONG_MS);
      } else {
        var dbl = !!(lastTap && t - lastTap.t < TAP_MS);
        g = { kind: "one", id: id, t0: t, tprev: t, total: 0, drag: false, dragCandidate: dbl };
      }
    }

    function move(id, x, y, t) {
      var p = touches[id]; if (!p) { return; }
      var dx = x - p.x, dy = y - p.y; p.x = x; p.y = y;
      if (!g) { return; }
      if (g.kind === "one" && id === g.id) {
        g.total += Math.abs(dx) + Math.abs(dy);
        if (g.dragCandidate && !g.drag && g.total >= DRAG_SLOP) { g.drag = true; press(0); }
        var dt = Math.max(1, t - g.tprev); g.tprev = t;
        var v = Math.hypot(dx, dy) / dt;                    // px per ms
        var gain = cfg.speed * (1 + Math.min(v, 2.5) * 0.7);  // slow = precise, fast = covers the screen
        cur.x += dx * gain; cur.y += dy * gain; clamp(); emit("move");
      } else if (g.kind === "d1" && id === g.id) {
        if (!g.pressed && !g.long && Math.hypot(x - g.x0, y - g.y0) > DRAG_SLOP) {
          stopLong(); g.pressed = true; setAt(g.x0, g.y0); press(0);
        }
        if (g.pressed) { setAt(x, y); }
      } else if (g.kind === "two" && count() >= 2) {
        var m = mid(), mx = m.x - g.cx, my = m.y - g.cy; g.cx = m.x; g.cy = m.y;
        g.total += Math.abs(mx) + Math.abs(my);
        if (g.total > TAP_SLOP) { g.scrolled = true; }
        if (g.scrolled) { scrollBy(mx, my); }
      }
    }

    function up(id, t) {
      if (!touches[id]) { return; }
      var wasTwo = g && g.kind === "two";
      delete touches[id];
      if (!g) { return; }
      if (g.kind === "one" && id === g.id) {
        if (g.drag) { release(0); lastTap = null; }
        else if (g.total < TAP_SLOP && t - g.t0 < TAP_MS) {
          click(0);
          lastTap = g.dragCandidate ? null : { t: t };       // a third quick tap starts over
        } else { lastTap = null; }
        g = null;
      } else if (g.kind === "d1" && id === g.id) {
        stopLong();
        if (g.pressed) { release(0); }
        else if (!g.long) { setAt(g.x0, g.y0); click(0); }
        g = null;
      } else if (wasTwo) {
        if (!g.scrolled && t - g.t0 < 350) { click(2); }
        g = { kind: "ignore" };
      }
      if (count() === 0) { g = null; stopLong(); }
    }

    function cancel() { stopLong(); release(0); release(2); touches = {}; g = null; }

    return {
      cfg: cfg, pos: function () { return { x: cur.x, y: cur.y }; },
      setMode: function (m) { cancel(); cfg.mode = (m === "direct") ? "direct" : "touchpad"; },
      setSpeed: function (v) { cfg.speed = Math.max(0.3, Math.min(3, v)); },
      setNatural: function (b) { cfg.natural = !!b; },
      center: center, down: down, move: move, up: up, cancel: cancel,
      button: function (btn, isDown) { if (isDown) { press(btn); if (opt.onClick) { opt.onClick(btn); } } else { release(btn); } },
      scroll: scrollBy,
      // a real mouse on the overlay: send it straight through (position + button)
      mouse: function (type, x, y, btn) { cur.x = x; cur.y = y; clamp(); if (type === "down") { held[btn] = true; } if (type === "up") { held[btn] = false; } emit(type, btn); },
      wheel: function (dx, dy) { emit("wheel", 0, dx, dy); }
    };
  }

  if (typeof window !== "undefined") { window.ABIX_POINTER = { createEngine: createEngine }; }
  if (typeof module !== "undefined") { module.exports = { createEngine: createEngine }; }
  if (typeof document === "undefined" || !document.getElementById("pad-layer")) { return; }

  // ------------------------------------------------------------------ DOM wiring
  var $ = function (id) { return document.getElementById(id); };
  var store = function (k, v) { try { if (v === undefined) { return localStorage.getItem(k); } localStorage.setItem(k, v); } catch (e) { return null; } return null; };
  var layer = $("pad-layer"), cursor = $("vcursor"), mpad = $("mpad"), screen = $("screen");
  var mode = "normal", heldMask = 0, raf = 0;

  function target() {
    try { var d = screen.contentDocument, c = d && d.querySelector("canvas"); return c ? { win: screen.contentWindow, el: c } : null; } catch (e) { return null; }
  }
  function bounds() {
    var t = target(), st = $("stage").getBoundingClientRect();
    if (!t) { return { l: 0, t: 0, r: st.width, b: st.height }; }
    var r = t.el.getBoundingClientRect();
    return { l: Math.max(0, r.left), t: Math.max(0, r.top), r: Math.min(st.width, r.right) - 1, b: Math.min(st.height, r.bottom) - 1 };
  }
  var BTN = { 0: 1, 2: 2 };                        // MouseEvent.buttons bit for button 0 / 2
  function emit(type, x, y, button, dx, dy) {
    var t = target(); if (!t) { return; }
    var W = t.win, o = { bubbles: true, cancelable: true, view: W, clientX: x, clientY: y, screenX: x, screenY: y };
    if (type === "wheel") {
      o.deltaX = dx; o.deltaY = dy; o.deltaMode = 0; t.el.dispatchEvent(new W.WheelEvent("wheel", o)); return;
    }
    o.button = button;
    if (type === "down") { heldMask |= BTN[button] || 1; } else if (type === "up") { heldMask &= ~(BTN[button] || 1); }
    o.buttons = heldMask;
    t.el.dispatchEvent(new W.MouseEvent(type === "move" ? "mousemove" : type === "down" ? "mousedown" : "mouseup", o));
    if (type === "move") { place(x, y); }
  }
  function place(x, y) {
    if (raf) { return; }
    raf = requestAnimationFrame(function () { raf = 0; var p = engine.pos(); cursor.style.transform = "translate3d(" + p.x + "px," + p.y + "px,0)"; });
  }

  // soft tap sound for touchpad clicks (shared with extras.js)
  var engine = createEngine({
    emit: emit, bounds: bounds,
    later: function (f, ms) { return setTimeout(f, ms); }, cancelLater: function (h) { clearTimeout(h); },
    onClick: function () { if (window.ABIX_SOUND) { window.ABIX_SOUND.tap(); } }
  });

  function rel(e, el) { var r = el.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }

  // Generic pointer-event feeder: used for the full-screen layer and for the small pad.
  function feed(el, opts) {
    var downBtn = {};
    el.addEventListener("pointerdown", function (e) {
      e.preventDefault(); try { el.setPointerCapture(e.pointerId); } catch (x) {}
      var p = rel(e, opts.space || el);
      if (e.pointerType === "mouse" && opts.mouse) {                         // a real mouse on the layer behaves normally
        downBtn[e.pointerId] = e.button; engine.mouse("move", p.x, p.y, 0); engine.mouse("down", p.x, p.y, e.button === 2 ? 2 : 0); return;
      }
      engine.down(e.pointerId, p.x, p.y, e.timeStamp);
    });
    el.addEventListener("pointermove", function (e) {
      var p = rel(e, opts.space || el);
      if (e.pointerType === "mouse" && opts.mouse) { engine.mouse("move", p.x, p.y, 0); return; }
      engine.move(e.pointerId, p.x, p.y, e.timeStamp);
    });
    function end(e) {
      var p = rel(e, opts.space || el);
      if (e.pointerType === "mouse" && opts.mouse) { if (downBtn[e.pointerId] !== undefined) { engine.mouse("up", p.x, p.y, downBtn[e.pointerId] === 2 ? 2 : 0); delete downBtn[e.pointerId]; } return; }
      engine.up(e.pointerId, e.timeStamp);
    }
    el.addEventListener("pointerup", end); el.addEventListener("pointercancel", end);
    el.addEventListener("contextmenu", function (e) { e.preventDefault(); });
    if (opts.mouse) { el.addEventListener("wheel", function (e) { e.preventDefault(); var p = rel(e, el); engine.mouse("move", p.x, p.y, 0); engine.wheel(e.deltaX, e.deltaY); }, { passive: false }); }
  }
  // Full-screen layer: coordinates are relative to the stage (same origin as the noVNC iframe).
  feed(layer, { mouse: true, space: layer });
  // Small pad: only finger deltas matter, so any origin works.
  feed($("mpad-pad"), { mouse: false });

  // Left / Right buttons: hold = button held (so you can drag).
  [["mpad-l", 0], ["mpad-r", 2]].forEach(function (pair) {
    var b = $(pair[0]), btn = pair[1];
    b.addEventListener("pointerdown", function (e) { e.preventDefault(); try { b.setPointerCapture(e.pointerId); } catch (x) {} b.classList.add("down"); engine.button(btn, true); });
    var up = function () { if (b.classList.contains("down")) { b.classList.remove("down"); engine.button(btn, false); } };
    b.addEventListener("pointerup", up); b.addEventListener("pointercancel", up);
  });
  // Scroll strip
  (function () {
    var el = $("mpad-scroll"), lastY = null;
    el.addEventListener("pointerdown", function (e) { e.preventDefault(); try { el.setPointerCapture(e.pointerId); } catch (x) {} lastY = e.clientY; });
    el.addEventListener("pointermove", function (e) { if (lastY === null) { return; } engine.scroll(0, e.clientY - lastY); lastY = e.clientY; });
    var end = function () { lastY = null; }; el.addEventListener("pointerup", end); el.addEventListener("pointercancel", end);
  })();

  // ------------------------------------------------------------------ mode switching
  var HELP = {
    normal: "Normal: use your mouse, or noVNC's own touch handling.",
    touchpad: "Touchpad: drag = move the pointer. Tap = click. Tap, then touch and drag = drag. Two-finger tap = right click. Two fingers up/down = scroll.",
    mousepad: "Mouse pad: use the pad at the bottom like a laptop trackpad, with Left / Right buttons and the scroll strip.",
    direct: "Direct touch: tap where you want to click. Long press = right click. Drag to drag. Two fingers up/down = scroll."
  };
  function setMode(m, quiet) {
    if (!HELP[m]) { m = "normal"; }
    mode = m; store("abix_mouse", m); engine.cancel();
    engine.setMode(m === "direct" ? "direct" : "touchpad");
    layer.hidden = !(m === "touchpad" || m === "direct");
    mpad.hidden = (m !== "mousepad");
    cursor.hidden = !(m === "touchpad" || m === "mousepad");
    if (!cursor.hidden) { engine.center(); engine.pos(); place(engine.pos().x, engine.pos().y); }
    Array.prototype.forEach.call(document.querySelectorAll("#mouse-menu button"), function (b) { b.classList.toggle("on", b.getAttribute("data-mode") === m); });
    $("mouse-help").textContent = HELP[m];
    $("b-mouse").classList.toggle("on", m !== "normal");
    if (!quiet && window.ABIX_APP) { window.ABIX_APP.toast(HELP[m]); }
  }
  $("b-mouse").addEventListener("click", function (e) { e.stopPropagation(); closeMenus("mouse-menu"); $("mouse-menu").hidden = !$("mouse-menu").hidden; });
  $("mouse-menu").addEventListener("click", function (e) { e.stopPropagation(); var m = e.target.getAttribute("data-mode"); if (m) { setMode(m); $("mouse-menu").hidden = true; } });
  function closeMenus(except) { ["mouse-menu", "clip-menu", "power-menu"].forEach(function (id) { if (id !== except && $(id)) { $(id).hidden = true; } }); }
  window.ABIX_CLOSE_MENUS = closeMenus;
  document.addEventListener("click", function (e) { if (!e.target.closest || !e.target.closest("#mouse-menu")) { $("mouse-menu").hidden = true; } });

  // speed + scrolling preference
  function applyPrefs() {
    var sp = parseInt(store("abix_speed") || "100", 10); if (isNaN(sp) || sp < 50 || sp > 250) { sp = 100; }
    var nat = store("abix_natural") !== "0";
    engine.setSpeed(sp / 100); engine.setNatural(nat);
    $("s-speed").value = sp; $("s-natural").checked = nat;
  }
  $("s-speed").addEventListener("input", function () { store("abix_speed", $("s-speed").value); applyPrefs(); });
  $("s-natural").addEventListener("change", function () { store("abix_natural", $("s-natural").checked ? "1" : "0"); applyPrefs(); });

  // After a reconnect / resize the pointer must stay inside the picture.
  window.addEventListener("resize", function () { if (mode === "touchpad" || mode === "mousepad") { engine.center(); place(engine.pos().x, engine.pos().y); } });
  var saved = store("abix_mouse");
  if (!saved) { saved = (window.matchMedia && window.matchMedia("(pointer:coarse)").matches) ? "touchpad" : "normal"; }
  screen.addEventListener("load", function () { if (mode === "touchpad" || mode === "mousepad") { engine.center(); place(0, 0); } });
  applyPrefs(); setMode(saved, true);
})();
