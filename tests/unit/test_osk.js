// On-screen keyboard test with a tiny fake DOM:  node tests/unit/test_osk.js
const fs = require("fs"), vm = require("vm"), path = require("path"), assert = require("assert");
const src = fs.readFileSync(path.join(__dirname, "../../frontend/osk.js"), "utf8");

// ---- 1) pure layout check (no DOM) ----
{
  const ctx = { window: {}, document: undefined };
  vm.runInNewContext(src, ctx);
  const keys = ctx.window.ABIX_KEYBOARD.rows.flat().filter(k => k.sp === undefined);
  assert.strictEqual(keys.length, 104, "standard 104-key layout, got " + keys.length);
  const codes = keys.map(k => k.code);
  assert.strictEqual(new Set(codes).size, codes.length, "duplicate key codes");
  const need = [..."ABCDEFGHIJKLMNOPQRSTUVWXYZ"].map(c => "Key" + c)
    .concat([..."0123456789"].map(d => "Digit" + d), [...Array(12)].map((_, i) => "F" + (i + 1)),
      ["Escape","Tab","CapsLock","ShiftLeft","ShiftRight","ControlLeft","ControlRight","AltLeft","AltRight","MetaLeft","MetaRight","ContextMenu",
       "Enter","Space","Backspace","Delete","Home","End","Insert","PageUp","PageDown","ArrowUp","ArrowDown","ArrowLeft","ArrowRight",
       "NumLock","NumpadDivide","NumpadMultiply","NumpadSubtract","NumpadAdd","NumpadEnter","NumpadDecimal","Numpad0","Numpad1","Numpad2","Numpad3","Numpad4","Numpad5","Numpad6","Numpad7","Numpad8","Numpad9",
       "Backquote","Minus","Equal","BracketLeft","BracketRight","Backslash","Semicolon","Quote","Comma","Period","Slash","PrintScreen","ScrollLock","Pause"]);
  const missing = need.filter(c => !codes.includes(c));
  assert.deepStrictEqual(missing, [], "missing keys");
  // every symbol from the user's list is reachable (base or shifted)
  const chars = new Set(keys.flatMap(k => [k.key, k.shift]).filter(Boolean));
  for (const ch of "~!@#$%^&*()-_+=[]{}:;'\",./?\\|<>`") assert.ok(chars.has(ch), "symbol missing: " + ch);
  for (const k of keys) assert.ok(k.name && k.label, "key without name: " + k.code);
  // each row adds up to the same width (clean rectangle)
  const widths = ctx.window.ABIX_KEYBOARD.rows.map(r => r.reduce((s, i) => s + (i.sp !== undefined ? i.sp : i.w), 0));
  assert.ok(widths.every(w => Math.abs(w - 23) < 1e-9), "row widths " + widths);
}

// ---- 2) behaviour with a fake DOM ----
const log = [];
function el(id) {
  const o = { id, hidden: true, children: [], style: {}, _h: {}, textContent: "", attrs: {},
    classList: { s: new Set(), add(c) { this.s.add(c); }, remove(c) { this.s.delete(c); }, contains(c) { return this.s.has(c); }, toggle(c, f) { (f === undefined ? !this.s.has(c) : f) ? this.s.add(c) : this.s.delete(c); } },
    addEventListener(t, f) { (this._h[t] = this._h[t] || []).push(f); },
    appendChild(c) { this.children.push(c); return c; }, setAttribute(k, v) { this.attrs[k] = v; }, setPointerCapture() {},
    click() { (this._h.click || []).forEach(f => f({})); },
    fire(t, e) { (this._h[t] || []).forEach(f => f(Object.assign({ preventDefault() {}, pointerId: 1 }, e))); } };
  return o;
}
const ids = {}; ["osk","osk-keys","osk-name","osk-head-keys","osk-rgb","osk-snd","osk-close","b-kbd","b-power","screen"].forEach(i => ids[i] = el(i));
const canvas = { dispatchEvent(e) { log.push(e); return true; } };
ids.screen.contentDocument = { querySelector: () => canvas, addEventListener() {} };
ids.screen.contentWindow = { KeyboardEvent: class { constructor(type, o) { this.type = type; Object.assign(this, o); } } };
const doc = { getElementById: i => ids[i], createElement: () => el("x"), addEventListener() {} };
const sandbox = { window: { AudioContext: undefined }, document: doc, localStorage: { getItem: () => null, setItem() {} } };
vm.runInNewContext(src, sandbox);

const buttons = {}; ids["osk-keys"].children.forEach(row => row.children.forEach(b => { if (b.attrs["aria-label"]) buttons[b.attrs["aria-label"]] = b; }));
function tap(label) { const b = buttons[label]; b.fire("pointerdown", {}); b.fire("pointerup", {}); }
const seq = () => log.splice(0).map(e => e.type + ":" + e.key + (e.shiftKey ? "+S" : "") + (e.ctrlKey ? "+C" : ""));

tap("Letter A");
assert.deepStrictEqual(seq(), ["keydown:a", "keyup:a"]);
tap("Shift"); tap("Letter A");   // first "Shift" button = left shift
assert.deepStrictEqual(seq(), ["keydown:Shift+S", "keydown:A+S", "keyup:A+S", "keyup:Shift"], "shift then A, shift released after");
tap("Shift"); tap("Number 1 (Exclamation Mark with Shift)");
assert.deepStrictEqual(seq(), ["keydown:Shift+S", "keydown:!+S", "keyup:!+S", "keyup:Shift"]);
tap("Control"); tap("Letter C");
assert.deepStrictEqual(seq(), ["keydown:Control+C", "keydown:c+C", "keyup:c+C", "keyup:Control"], "Ctrl+C");
tap("Caps Lock");
assert.deepStrictEqual(seq(), ["keydown:CapsLock", "keyup:CapsLock"]);
assert.ok(buttons["Caps Lock"].classList.contains("on"));
assert.strictEqual(buttons["Letter A"].textContent, "A", "caps lock shows capitals");
tap("Spacebar"); assert.deepStrictEqual(seq(), ["keydown: ", "keyup: "]);
tap("Keypad 7"); const e7 = log.splice(0); assert.strictEqual(e7[0].location, 3);
tap("Print Screen"); assert.deepStrictEqual(seq(), ["keydown:PrintScreen", "keyup:PrintScreen"]);
// held key: down on press, up only on release
buttons["Letter B"].fire("pointerdown", {}); assert.deepStrictEqual(seq(), ["keydown:b"]); buttons["Letter B"].fire("pointerup", {}); assert.deepStrictEqual(seq(), ["keyup:b"]);
// shows the key name
tap("Escape"); assert.ok(ids["osk-name"].textContent.includes("Escape"));
// toggle open/close
ids["b-kbd"].click(); assert.strictEqual(ids.osk.hidden, false);
ids["osk-close"].click(); assert.strictEqual(ids.osk.hidden, true);
// no canvas -> no crash, user told
ids.screen.contentDocument = { querySelector: () => null, addEventListener() {} };
tap("Letter A"); assert.ok(ids["osk-name"].textContent.includes("not ready"));
// power key opens the power menu
let opened = 0; ids["b-power"]._h.click = [() => opened++]; ids["osk-head-keys"].children.slice(-1)[0].fire("click", {}); assert.strictEqual(opened, 1);
console.log("OSK tests passed: 104-key layout + press/latch/caps/numpad/name/toggle behaviour");
