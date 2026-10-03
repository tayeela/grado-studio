// ГРАДО 2 browser scenarios: headless Chrome over the DevTools protocol, no dependencies (node 22 has fetch and WebSocket).
// node driver.mjs <url> <steps.mjs>; Chrome path from env CHROME (default: macOS Google Chrome).
// steps.mjs: export default async (p) => { ... }  p.wheel(x,y,deltaY,{ctrl}) · p.ev(js) · p.click(x,y,{shift,meta,dbl}) · p.drag(x0,y0,x1,y1,{shift}) · p.key(key,code,mods) · p.shot(file) · p.sleep(ms) · p.log(...)
//
// Failures (T51). By default a failed check() does NOT stop the run: it prints "STEP FAILED: <message>" and goes on; a page
// exception inside p.ev is recorded the same way (p.ev then returns undefined, so the check around it fails or the next line
// throws). An exception that escapes the scenario (or a group) ends that scenario (or group) only. At the end:
//   SUMMARY: N ok, M failed   +   one "  FAILED #k [group] <name>" line per failed step.   Exit code 1 if anything failed
//   or the page console shows an exception. E2E_STOP=1 restores stop-at-first-failure (check() throws, p.ev throws).
// check(): scenarios.mjs defines its own `const check = ... throw ...`; while loading steps.mjs the driver swaps that one line
//   for the driver's check (module hook, the file on disk is untouched). A file without that line keeps its own check (stop at first).
// Groups (tags): in steps.mjs call  group("tep", async () => { ... })  or  group(["tep", "album"], async () => { ... })
//   (also p.group and globalThis.group). Names are free-form tags; failures are printed with their group.
//   E2E_ONLY=tep,album runs only groups with one of these tags; code outside any group always runs (keep shared set-up there).
//   Steps of a group depend on the state left by earlier ones: skipping a group that sets up state for another gives failures there.
//   An exception that escapes a group aborts that group; the run continues with the next group.
// Env: CHROME, W/H (viewport), E2E_STOP, E2E_ONLY. Debug port: a free TCP port picked by the OS. Start-up waits (cap 20 s) for
//   document.readyState=="complete" and the app globals (LYR, mMain) or window.ready===true instead of a fixed sleep.
import { spawn } from "node:child_process";
import { writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import net from "node:net";
import * as nodeModule from "node:module";
import { pathToFileURL } from "node:url";
import { join, resolve } from "node:path";

const [url, stepsPath] = process.argv.slice(2);
const STOP = process.env.E2E_STOP === "1";
const ONLY = (process.env.E2E_ONLY || "").split(",").map(x => x.trim()).filter(Boolean);
const freePort = () => new Promise((res, rej) => { const s = net.createServer(); s.once("error", rej); s.listen(0, "127.0.0.1", () => { const { port } = s.address(); s.close(() => res(port)); }); });
const port = await freePort();
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const profile = mkdtempSync(join(tmpdir(), "cdp-"));
const chrome = spawn(CHROME, [
  "--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  "--window-size=1440,900", "--no-first-run", "--no-default-browser-check", "--no-sandbox", "--enable-unsafe-swiftshader", "about:blank"], { stdio: "ignore" });
let failed = false, curGroup = "", nOk = 0;
const failures = [];
const fail = name => { failures.push({ group: curGroup, name }); console.log("STEP FAILED:", (curGroup ? `[${curGroup}] ` : "") + name); };
const check = (cond, msg) => { if (cond) { nOk++; console.log("ok -", msg); } else if (STOP) throw new Error("не выполнено: " + msg); else fail("не выполнено: " + msg); };
async function group(tags, fn) {
  const t = (Array.isArray(tags) ? tags : String(tags).split(",")).map(x => x.trim()).filter(Boolean);
  if (ONLY.length && !t.some(x => ONLY.includes(x))) { console.log("skip group", t.join(",")); return; }
  const prev = curGroup; curGroup = t.join(",");
  try { await fn(); } catch (e) { if (STOP) throw e; fail("group aborted by exception: " + (e?.message || e)); }
  finally { curGroup = prev; }
}
globalThis.group = group; globalThis.__e2e = { check, group };
const sleep = ms => new Promise(r => setTimeout(r, ms));
let ws, id = 0; const pending = new Map(), logs = [];
const send = (method, params = {}) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const mods = o => (o?.alt ? 1 : 0) | (o?.ctrl ? 2 : 0) | (o?.meta ? 4 : 0) | (o?.shift ? 8 : 0);
const p = {
  sleep, logs, check, group, raw: (m, a) => send(m, a),
  log: (...a) => console.log(...a),
  async ev(expr) {
    const r = await send("Runtime.evaluate", { expression: `(async () => { ${expr} })()`, awaitPromise: true, returnByValue: true });
    if (r.result?.exceptionDetails) {
      const msg = "page: " + (r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text);
      if (STOP) throw new Error(msg);
      fail("p.ev exception: " + msg.split("\n")[0].slice(0, 300) + "  | code: " + expr.replace(/\s+/g, " ").slice(0, 120)); return undefined;
    }
    return r.result?.result?.value;
  },
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
  await send("Page.navigate", { url });
  let ready = false;
  for (let t0 = Date.now(); Date.now() - t0 < 20000 && !ready; ) {
    const r = await send("Runtime.evaluate", { expression: `document.readyState==="complete" && (window.ready===true || (typeof LYR!=="undefined" && typeof mMain!=="undefined"))`, returnByValue: true });
    ready = r.result?.result?.value === true; if (!ready) await sleep(100);
  }
  if (!ready) fail("start-up: page not ready after 20 s (document.readyState/LYR/mMain)");
  // scenarios.mjs keeps its own `const check = ... throw`; swap that line for the driver's check so a failed check does not stop the run.
  if (!STOP && nodeModule.registerHooks) nodeModule.registerHooks({ load(u, ctx, next) {
    const r = next(u, ctx);
    if (u.split("?")[0] === pathToFileURL(resolve(stepsPath)).href && r.source != null) {
      const src = String(r.source), out = src.replace(/^const check = \(cond, msg\) => \{[^\n]*\};[ \t]*$/m, "const check = globalThis.__e2e.check;");
      return { ...r, source: out };
    }
    return r;
  } });
  const steps = (await import(pathToFileURL(resolve(stepsPath)).href + "?t=" + Date.now())).default;
  try { await steps(p); } catch (e) { if (STOP) { console.log("STEP FAILED:", e.message); failed = true; } else fail("scenario aborted by exception: " + (e?.message || e)); }
  console.log(logs.length ? "CONSOLE:\n" + logs.slice(0, 40).join("\n") : "console clean");
  if (logs.some(l => l.startsWith("EXCEPTION"))) failed = true;
  if (failures.length) failed = true;
  console.log(`SUMMARY: ${nOk} ok, ${failures.length} failed`);
  failures.forEach((f, i) => console.log(`  FAILED #${i + 1}${f.group ? ` [${f.group}]` : ""} ${f.name}`));
} finally {
  ws?.close(); chrome.kill(); process.exitCode = failed ? 1 : 0;
  // The temp profile is ~140 MB per run; remove it once Chrome has exited (5 s cap if it never reports exit).
  if (chrome.exitCode === null && chrome.signalCode === null)
    await new Promise(r => { const t = setTimeout(r, 5000); chrome.once("exit", () => { clearTimeout(t); r(); }); });
  rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}
