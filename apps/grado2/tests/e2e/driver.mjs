// ГРАДО 2 browser scenarios: headless Chrome over the DevTools protocol, no dependencies (node 22 has fetch and WebSocket).
// node driver.mjs <url> <steps.mjs>; Chrome path from env CHROME (default: macOS Google Chrome). Exit code 1 on a failed step
// or on any exception in the page console.
// steps.mjs: export default async (p) => { ... }  p.wheel(x,y,deltaY,{ctrl}) · p.ev(js) · p.click(x,y,{shift,meta,dbl}) · p.drag(x0,y0,x1,y1,{shift}) · p.key(key,code,mods) · p.shot(file) · p.sleep(ms) · p.log(...)
import { spawn } from "node:child_process";
import { writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const [url, stepsPath] = process.argv.slice(2);
const port = 9400 + Math.floor(Math.random() * 500);
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const profile = mkdtempSync(join(tmpdir(), "cdp-"));
const chrome = spawn(CHROME, [
  "--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  "--window-size=1440,900", "--no-first-run", "--no-default-browser-check", "--no-sandbox", "--enable-unsafe-swiftshader", "about:blank"], { stdio: "ignore" });
let failed = false;
const sleep = ms => new Promise(r => setTimeout(r, ms));
let ws, id = 0; const pending = new Map(), logs = [];
const send = (method, params = {}) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const mods = o => (o?.alt ? 1 : 0) | (o?.ctrl ? 2 : 0) | (o?.meta ? 4 : 0) | (o?.shift ? 8 : 0);
const p = {
  sleep, logs, raw: (m, a) => send(m, a),
  log: (...a) => console.log(...a),
  async ev(expr) { const r = await send("Runtime.evaluate", { expression: `(async () => { ${expr} })()`, awaitPromise: true, returnByValue: true }); if (r.result?.exceptionDetails) throw new Error("page: " + (r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text)); return r.result?.result?.value; },
  async move(x, y, o) { await send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y, modifiers: mods(o), button: o?.down ? "left" : "none", buttons: o?.down ? 1 : 0 }); },
  async click(x, y, o = {}) {
    await p.move(x, y, o);
    const n = o.dbl ? 2 : 1;
    for (let c = 1; c <= n; c++) { await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", buttons: 1, clickCount: c, modifiers: mods(o) }); await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", buttons: 0, clickCount: c, modifiers: mods(o) }); }
    await sleep(o.wait ?? 120);
  },
  async drag(x0, y0, x1, y1, o = {}) {
    await p.move(x0, y0, o); await send("Input.dispatchMouseEvent", { type: "mousePressed", x: x0, y: y0, button: "left", buttons: 1, clickCount: 1, modifiers: mods(o) });
    const n = 12; for (let i = 1; i <= n; i++) { await p.move(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n, { ...o, down: true }); await sleep(16); }
    await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: x1, y: y1, button: "left", buttons: 0, clickCount: 1, modifiers: mods(o) }); await sleep(o.wait ?? 150);
  },
  async key(key, code, o = {}) {
    const base = { key, code, modifiers: mods(o), windowsVirtualKeyCode: o.vk || (key.length === 1 ? key.toUpperCase().charCodeAt(0) : 0) };
    await send("Input.dispatchKeyEvent", { type: "keyDown", ...base, text: o.text }); await send("Input.dispatchKeyEvent", { type: "keyUp", ...base }); await sleep(o.wait ?? 80);
  },
  async wheel(x, y, dy, o = {}) { await send("Input.dispatchMouseEvent", { type: "mouseWheel", x, y, deltaX: 0, deltaY: dy, modifiers: mods(o) }); await sleep(o.wait ?? 40); },
  async type(text) { await send("Input.insertText", { text }); await sleep(60); },
  async shot(file) { const s = await send("Page.captureScreenshot", { format: "png" }); writeFileSync(file, Buffer.from(s.result.data, "base64")); },
};
try {
  let targets;
  for (let i = 0; i < 50; i++) { try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); break; } catch { await sleep(100); } }
  ws = new WebSocket(targets.find(t => t.type === "page").webSocketDebuggerUrl);
  await new Promise(r => ws.onopen = r);
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    if (m.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(m.params.type)) logs.push(m.params.type + ": " + m.params.args.map(a => a.value ?? a.description).join(" "));
    if (m.method === "Runtime.exceptionThrown") logs.push("EXCEPTION: " + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text)); };
  await send("Runtime.enable"); await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: +(process.env.W||1440), height: +(process.env.H||900), deviceScaleFactor: 1, mobile: false });
  await send("Page.navigate", { url }); await sleep(2500);
  const steps = (await import(resolve(stepsPath) + "?t=" + Date.now())).default;
  try { await steps(p); } catch (e) { console.log("STEP FAILED:", e.message); failed = true; }
  console.log(logs.length ? "CONSOLE:\n" + logs.slice(0, 40).join("\n") : "console clean");
  if (logs.some(l => l.startsWith("EXCEPTION"))) failed = true;
} finally {
  ws?.close(); chrome.kill(); process.exitCode = failed ? 1 : 0;
  // The temp profile is ~140 MB per run; remove it once Chrome has exited (5 s cap if it never reports exit).
  if (chrome.exitCode === null && chrome.signalCode === null)
    await new Promise(r => { const t = setTimeout(r, 5000); chrome.once("exit", () => { clearTimeout(t); r(); }); });
  rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}
