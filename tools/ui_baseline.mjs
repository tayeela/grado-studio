// ГРАДО · замер скорости интерфейса — точка отсчёта плана 09.11.2026 (шаг И1): нынешний /next/ и новый /g3/ на одном
// проекте. Свой сервер на порту 8654 и временная папка проектов с копией образца tests/fixtures/next_ui_project.grado2 —
// проекты владельца не трогаются, порталы не нужны (данные лежат в файле). Замер: страница загружена, карта нарисована
// (первый холст карты), сколько окон открыто, сколько скачано своих файлов (скрипты, стили, WebAssembly), медиана из N прогонов.
// Запуск: node tools/ui_baseline.mjs [--runs 3] [--out файл.md]; браузер — $CHROME или встроенный Chromium Playwright.
import { spawn } from "node:child_process";
import { copyFileSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { homedir, tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const req = createRequire(import.meta.url);
const pw = (() => { try { return req("playwright-core"); } catch { return req("playwright"); } })();
const arg = (k, d) => { const i = process.argv.indexOf("--" + k); return i > 0 ? process.argv[i + 1] : d; };
const RUNS = Number(arg("runs", "3")), PORT = "8654", OUT = arg("out", "");
const PY = process.env.PY || join(homedir(), ".grado2/venv/bin/python");
const NAME = "Замер";

const dir = mkdtempSync(join(tmpdir(), "grado-baseline-"));
copyFileSync(join(ROOT, "apps/grado2/tests/fixtures/next_ui_project.grado2"), join(dir, NAME + ".grado2"));
const srv = spawn(PY, [join(ROOT, "apps/grado2/server.py"), PORT], { env: { ...process.env, GRADO2_PROJECTS: dir, GRADO2_NO_BROWSER: "1" }, stdio: "ignore" });
const stop = () => { srv.kill(); rmSync(dir, { recursive: true, force: true }); };
process.on("exit", stop);
for (let i = 0; i < 60; i++) {
  try { if ((await fetch(`http://127.0.0.1:${PORT}/api/health`)).ok) break; } catch { /* ещё стартует */ }
  await new Promise(r => setTimeout(r, 250));
}

const launch = process.env.CHROME ? { executablePath: process.env.CHROME } : {};
const browser = await pw.chromium.launch({ ...launch, args: ["--no-sandbox"] });
const med = a => [...a].sort((x, y) => x - y)[Math.floor(a.length / 2)];

async function once(path) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  let bytes = 0;
  page.on("response", async r => {
    const u = new URL(r.url());
    if (u.port === PORT && /\.(js|css|wasm)$/.test(u.pathname)) { try { bytes += (await r.body()).length; } catch { /* отменено */ } }
  });
  // карта: OpenLayers рисует слои на холсты внутри .ol-layer; ждём холст с размером, затем объекты проекта
  const t0 = Date.now();
  await page.goto(`http://127.0.0.1:${PORT}${path}?p=${encodeURIComponent(NAME)}`, { waitUntil: "domcontentloaded" });
  const dom = Date.now() - t0;
  await page.waitForFunction(() => [...document.querySelectorAll(".ol-layer canvas, .ol-viewport canvas")].some(c => c.width > 0), null, { timeout: 30000 });
  const map = Date.now() - t0;
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  const ready = Date.now() - t0;
  const tabs = await page.evaluate(() => document.querySelectorAll(".dv-tab").length);
  const heap = await page.evaluate(() => (performance.memory ? Math.round(performance.memory.usedJSHeapSize / 2 ** 20) : 0));
  await ctx.close();
  return { dom, map, ready, tabs, bytes, heap };
}

const rows = [];
for (const [title, path] of [["нынешний /next/", "/next/"], ["новый /g3/", "/g3/"]]) {
  const rs = [];
  for (let i = 0; i < RUNS; i++) rs.push(await once(path));
  rows.push({ title, dom: med(rs.map(r => r.dom)), map: med(rs.map(r => r.map)), ready: med(rs.map(r => r.ready)),
    tabs: med(rs.map(r => r.tabs)), mb: (med(rs.map(r => r.bytes)) / 2 ** 20).toFixed(2), heap: med(rs.map(r => r.heap)) });
}
await browser.close();

const md = [
  `Замер ${new Date().toISOString().slice(0, 16).replace("T", " ")} UTC, медиана из ${RUNS}, окно 1440 × 900, проект «${NAME}» (образец, 7 слоёв).`,
  "",
  "| интерфейс | страница, мс | карта, мс | всё загружено, мс | окон открыто | скачано своих файлов, МБ | память JS, МБ |",
  "|---|---|---|---|---|---|---|",
  ...rows.map(r => `| ${r.title} | ${r.dom} | ${r.map} | ${r.ready} | ${r.tabs} | ${r.mb.replace(".", ",")} | ${r.heap} |`),
].join("\n");
console.log(md);
if (OUT) writeFileSync(OUT, md + "\n");
stop();
process.exit(0);
