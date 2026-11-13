// Pointer engine test (no browser needed):  node tests/unit/test_pointer.js
const assert = require("assert"), path = require("path");
const { createEngine } = require(path.join(__dirname, "../../frontend/pointer.js"));

function make(mode) {
  const log = [], timers = []; let clicks = 0;
  const e = createEngine({
    emit: (type, x, y, b, dx, dy) => log.push({ type, x: Math.round(x), y: Math.round(y), b, dx, dy }),
    bounds: () => ({ l: 0, t: 0, r: 999, b: 599 }),
    later: (f, ms) => { timers.push({ f, ms, live: true }); return timers.length - 1; },
    cancelLater: h => { if (timers[h]) timers[h].live = false; },
    onClick: () => clicks++
  });
  e.setMode(mode || "touchpad"); e.center();
  const flush = () => { timers.forEach(t => { if (t.live && t.ms <= 100) { t.live = false; t.f(); } }); };
  const fire = ms => { timers.forEach(t => { if (t.live && t.ms === ms) { t.live = false; t.f(); } }); };
  const types = () => log.filter(l => l.type !== "move").map(l => l.type + (l.type === "wheel" ? "" : ":" + l.b));
  return { e, log, flush, fire, types, clicks: () => clicks, clear: () => { log.length = 0; } };
}

// 1) touchpad: a tap clicks left at the pointer position (no jump to the finger position)
{ const t = make(); const p0 = t.e.pos();
  t.e.down(1, 100, 100, 0); t.e.up(1, 80); t.flush();
  assert.deepStrictEqual(t.types(), ["down:0", "up:0"]); assert.strictEqual(t.clicks(), 1);
  assert.deepStrictEqual(t.e.pos(), p0, "a tap must not move the pointer"); }

// 2) touchpad: dragging moves the pointer RELATIVE, faster swipe = longer travel, and it never leaves the screen
{ const t = make(); const p0 = t.e.pos();
  t.e.down(1, 100, 100, 0); t.e.move(1, 120, 100, 16); t.e.up(1, 400); t.flush();
  const p1 = t.e.pos(); assert.ok(p1.x - p0.x >= 20, "moves at least the finger distance"); assert.strictEqual(t.types().length, 0, "a swipe is not a click");
  const slow = make(), fast = make();
  slow.e.down(1, 0, 0, 0); slow.e.move(1, 10, 0, 100); fast.e.down(1, 0, 0, 0); fast.e.move(1, 10, 0, 2);
  assert.ok(fast.e.pos().x - 500 > slow.e.pos().x - 500, "acceleration");
  t.e.down(2, 0, 0, 1000); t.e.move(2, 5000, 5000, 1001); assert.ok(t.e.pos().x <= 999 && t.e.pos().y <= 599, "clamped"); }

// 3) touchpad: tap then touch-and-drag = drag (button held while moving, released on lift)
{ const t = make();
  t.e.down(1, 50, 50, 0); t.e.up(1, 60); t.flush(); t.clear();
  t.e.down(2, 50, 50, 200); t.e.move(2, 90, 50, 216); t.e.move(2, 140, 60, 232);
  assert.ok(t.types().includes("down:0") && !t.types().includes("up:0"), "pressed, still held");
  t.e.up(2, 400); assert.deepStrictEqual(t.types(), ["down:0", "up:0"]); }

// 4) touchpad: two-finger tap = right click; two-finger drag = scroll (natural: fingers up -> page down)
{ const t = make();
  t.e.down(1, 100, 100, 0); t.e.down(2, 140, 100, 5); t.e.up(1, 90); t.e.up(2, 95); t.flush();
  assert.deepStrictEqual(t.types(), ["down:2", "up:2"], "right click");
  const s = make(); s.e.down(1, 100, 200, 0); s.e.down(2, 140, 200, 5);
  s.e.move(1, 100, 150, 20); s.e.move(2, 140, 150, 20); s.e.up(1, 100); s.e.up(2, 110); s.flush();
  const wheels = s.log.filter(l => l.type === "wheel"); assert.ok(wheels.length > 0 && wheels.every(w => w.dy > 0), "natural scroll: fingers up scroll down");
  assert.ok(!s.types().some(x => x.endsWith(":2")), "scrolling is not a right click");
  const n = make(); n.e.setNatural(false); n.e.down(1, 100, 200, 0); n.e.down(2, 140, 200, 5); n.e.move(1, 100, 150, 20); n.e.move(2, 140, 150, 20);
  assert.ok(n.log.filter(l => l.type === "wheel").every(w => w.dy < 0), "traditional scroll reversed"); }

// 5) direct touch: tap clicks exactly where touched; drag drags from the touch point; long press = right click
{ const t = make("direct");
  t.e.down(1, 300, 200, 0); t.e.up(1, 50); t.flush();
  assert.deepStrictEqual(t.log.filter(l => l.type === "down")[0], { type: "down", x: 300, y: 200, b: 0, dx: 0, dy: 0 });
  assert.deepStrictEqual(t.types(), ["down:0", "up:0"]);
  const d = make("direct"); d.e.down(1, 100, 100, 0); d.e.move(1, 160, 140, 30); d.e.move(1, 220, 180, 60);
  assert.deepStrictEqual(d.types(), ["down:0"]); d.e.up(1, 90); assert.deepStrictEqual(d.types(), ["down:0", "up:0"]);
  const l = make("direct"); l.e.down(1, 100, 100, 0); l.fire(550); l.flush(); l.e.up(1, 700);
  assert.deepStrictEqual(l.types(), ["down:2", "up:2"], "long press = right click only"); }

// 6) mouse pad buttons: hold keeps the button down (drag), release lets go; scroll strip scrolls
{ const t = make(); t.e.button(0, true); t.e.move(0, 0, 0, 0); t.e.button(0, false); assert.deepStrictEqual(t.types(), ["down:0", "up:0"]);
  t.clear(); t.e.scroll(0, 10); assert.strictEqual(t.log[0].type, "wheel"); assert.ok(t.log[0].dy < 0, "natural: strip drag down scrolls up"); }

// 7) switching mode releases anything held
{ const t = make(); t.e.button(0, true); t.e.setMode("direct"); assert.ok(t.types().includes("up:0")); }

console.log("pointer engine: all tests passed");
