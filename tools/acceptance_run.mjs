// ГРАДО 2 · приёмочный прогон на настоящей территории (Хорошёво, ТиНАО) с настоящими порталами и замером времени каждого шага:
// граница из проекта или GeoJSON → выгрузка наборов «Существующее положение», «Ограничения», «Градостроительная документация» →
// «Рассчитать ограничения» → эскиз под цель плотности → варианты → альбом ППТ КРТ в PDF → DXF, GeoJSON, Excel. Всё — в новом
// интерфейсе (/next/), мышью, как у владельца; отдельный сервер на порту 8652 и временная папка проектов, проект владельца
// только читается (из него берётся граница). По умолчанию кэш пустой (временная домашняя папка, сертификаты НСПД копируются),
// --warm — с обычным кэшем ~/.grado2/cache (он не удаляется и не меняется местами).
// Запуск (Mac владельца): node tools/acceptance_run.mjs --project "~/Documents/ГРАДО 2/Хорошёво.grado2" --name Хорошёво
//   [--boundary граница.geojson] [--warm] [--headed] [--out DIR]; без --project и --boundary — граница «Пример».
// Итог: DIR/report.md (таблица шагов со временем, слои выгрузки, ошибки консоли), снимки экрана и файлы выгрузок;
// DIR по умолчанию — ~/Desktop/ГРАДО приёмка/<имя> <дата>. Описание — docs/ux/acceptance.md.
import { spawn } from "node:child_process";
import { copyFileSync, cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { homedir, tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const pw = createRequire(import.meta.url)("playwright-core");
const arg = (k, d) => { const i = process.argv.indexOf("--" + k); return i > 0 ? process.argv[i + 1] : d; };
const flag = k => process.argv.includes("--" + k);
const home = p => p && p.replace(/^~(?=\/|$)/, homedir());
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PY = process.env.PY || join(homedir(), ".grado2/venv/bin/python");
const NAME = arg("name", "Пример"), PORT = arg("port", "8652");
const stamp = new Date().toISOString().slice(0, 16).replace("T", " ").replace(":", "-");
const OUT = resolve(home(arg("out", join(homedir(), "Desktop", "ГРАДО приёмка", `${NAME} ${stamp}`))));
if (PORT === "8650") { console.error("Порт 8650 — рабочий сервер владельца, возьмите другой"); process.exit(2); }

// граница: из проекта (.grado2 — только поле territory) или из GeoJSON (первый полигон)
function boundary() {
  const p = home(arg("project")), g = home(arg("boundary"));
  if (p) { const t = JSON.parse(readFileSync(p, "utf-8")).territory; if (!t?.geometry) throw new Error("в проекте нет границы территории: " + p); return t; }
  if (g) { const j = JSON.parse(readFileSync(g, "utf-8")), f = j.type === "FeatureCollection" ? j.features.find(f => /Polygon/.test(f.geometry?.type)) : j.type === "Feature" ? j : { type: "Feature", geometry: j };
    if (!f?.geometry) throw new Error("в файле нет полигона: " + g); return { type: "Feature", properties: {}, geometry: f.geometry }; }
  return null;
}

const rows = [], errors = [];
let page;
async function step(title, fn, { shot = true } = {}) {
  const t0 = Date.now(); let ok = "да", note = "";
  process.stdout.write(`… ${title}\n`);
  try { note = (await fn()) || ""; } catch (e) { ok = "НЕТ"; note = e.message.split("\n")[0].slice(0, 300); }
  const s = ((Date.now() - t0) / 1000).toFixed(1);
  rows.push([title, ok, s, note]); console.log(`${ok === "да" ? "ok" : "НЕ ВЫШЛО"} — ${title}: ${s} с ${note}`);
  if (shot && page) await page.screenshot({ path: join(OUT, `${String(rows.length).padStart(2, "0")} ${title.replace(/[^\wа-яё ]+/gi, "")}.png`) }).catch(() => {});
}
const tab = t => page.locator(".dv-tab", { hasText: t }).first();
async function showWin(t) {
  if (!(await tab(t).count())) {
    await page.locator("header.top wa-button[slot=trigger]", { hasText: "Окна" }).click();
    await page.locator("header.top wa-dropdown-item[type=checkbox]", { hasText: t }).first().click(); await page.waitForTimeout(400);
  }
  await tab(t).click(); await page.waitForTimeout(300);
}
const winText = t => page.evaluate(t => { const b = [...document.querySelectorAll(".dv-tab")].find(x => x.textContent.trim() === t); return b ? b.closest(".dv-groupview").querySelector(".dv-content-container").innerText : ""; }, t);
const winButton = (t, label) => page.locator(".dv-groupview", { has: page.locator(".dv-tab.dv-active-tab", { hasText: t }) }).locator(".dv-content-container wa-button", { hasText: label }).first();
const wait = (fn, arg, ms) => page.waitForFunction(fn, arg, { timeout: ms, polling: 500 });
async function save(item, file) {
  const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 15 * 60000 }), (async () => {
    await page.locator("header.top wa-button[slot=trigger]", { hasText: "Выгрузка" }).click(); await page.locator(`header.top wa-dropdown-item[value=${item}]`).click(); })()]);
  await dl.saveAs(join(OUT, file)); return `${file}, ${Math.round(readFileSync(join(OUT, file)).length / 1024)} КБ`;
}

mkdirSync(OUT, { recursive: true });
const proj = mkdtempSync(join(tmpdir(), "grado-accept-"));
const env = { ...process.env, GRADO2_PROJECTS: join(proj, "projects"), GRADO2_NO_BROWSER: "1", PYTHONPATH: "", PYTHONUNBUFFERED: "1" };
mkdirSync(env.GRADO2_PROJECTS);
if (!flag("warm")) {                                         // пустой кэш: своя домашняя папка, сертификаты НСПД — копией
  env.HOME = join(proj, "home"); mkdirSync(join(env.HOME, ".grado2"), { recursive: true });
  const ca = join(homedir(), ".grado2", "ca"); if (existsSync(ca)) cpSync(ca, join(env.HOME, ".grado2", "ca"), { recursive: true });
}
const terr = boundary();
writeFileSync(join(env.GRADO2_PROJECTS, ".autosave.grado2"), JSON.stringify({ format: "grado2", version: 2, name: `Приёмка: ${NAME}`, layers: [], groups: [], data: {}, territory: terr }));

let srv;
const t00 = Date.now();
await step("Запуск программы", () => new Promise((ok, bad) => {
  srv = spawn(PY, [join(ROOT, "apps/grado2/server.py"), PORT], { env, stdio: ["ignore", "pipe", "pipe"] });
  let log = ""; const on = b => { log += b; if (/ГРАДО 2: http/.test(log)) ok(`порт ${PORT}, кэш ${flag("warm") ? "обычный" : "пустой"}`); };
  srv.stdout.on("data", on); srv.stderr.on("data", on); srv.on("exit", c => bad(new Error("сервер вышел: " + log.slice(-300))));
  setTimeout(() => bad(new Error("сервер не ответил за 60 с")), 60000);
}), { shot: false });

const browser = await pw.chromium.launch({ executablePath: CHROME, headless: !flag("headed") });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
page = await ctx.newPage();
page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", e => errors.push(String(e)));
try {
  await step("Открыть новый интерфейс", async () => {
    await page.goto(`http://127.0.0.1:${PORT}/next/`); await page.waitForSelector(".dv-tab", { timeout: 60000 }); await page.waitForTimeout(1500);
    if (!terr) { await showWin("Данные"); await winButton("Данные", "Пример").click(); await page.waitForTimeout(1000); }
    await showWin("Данные"); return (await winText("Данные")).match(/Площадь [^.]*/)?.[0] || "";
  });
  await step("Выгрузка данных: существующее положение, ограничения, документация", async () => {
    await showWin("Данные"); await winButton("Данные", "Выбрать источники").click();
    await page.locator("wa-dialog.picker .presets wa-button").first().waitFor({ state: "visible", timeout: 30000 }); await page.waitForTimeout(1500);
    for (const p of ["Существующее положение", "Ограничения", "Градостроительная документация"]) {
      const b = page.locator("wa-dialog.picker .presets wa-button", { hasText: p }).first();
      if (await b.getAttribute("appearance") !== "filled") await b.click();
    }
    await page.locator("wa-dialog.picker wa-button[slot=footer]", { hasText: "Загрузить в проект" }).click();
    await wait(() => document.querySelector(".job.fin"), null, 40 * 60000);
    const items = await page.evaluate(() => [...document.querySelectorAll(".job .jl li")].map(li => [li.className, li.querySelector(".nm")?.textContent.trim(), li.querySelector(".dt")?.textContent.trim(), li.querySelector(".sub")?.textContent.trim() || ""]));
    rows.layers = items;
    const bad = items.filter(i => /error/.test(i[0])).length, empty = items.filter(i => /empty/.test(i[0])).length;
    return `слоёв ${items.length}: с объектами ${items.length - bad - empty}, пустых ${empty}, ошибок ${bad}`;
  });
  await step("Рассчитать ограничения", async () => {
    await showWin("Ограничения"); await winButton("Ограничения", "Рассчитать ограничения").click();
    await page.waitForTimeout(1000); await wait(() => !document.querySelector("wa-button[loading]"), null, 10 * 60000);
    return (await winText("Ограничения")).split("\n").filter(Boolean).slice(1, 3).join(" · ").slice(0, 200);
  });
  await step("Эскиз под цель плотности", async () => {
    await showWin("Эскиз");
    const d = page.locator(".dv-content-container wa-button", { hasText: "цели плотности" }).first(); if (await d.count()) await d.click();
    const b = winButton("Эскиз", "Построить эскиз"); if (await b.count()) await b.click();
    await showWin("Показатели (ТЭП)"); await wait(() => /СПП новая\s*[1-9]/.test(document.body.innerText), null, 10 * 60000);
    const t = await winText("Показатели (ТЭП)");
    return ["СПП новая", "Плотность", "Население"].map(k => (t.match(new RegExp(k + "\\s*([^\\n]+)")) || [])[0]).filter(Boolean).join(" · ");
  });
  await step("Подобрать варианты", async () => {
    await showWin("Варианты"); await winButton("Варианты", "Подобрать варианты").click();
    await wait(() => document.querySelectorAll(".dv-content-container button.vc").length >= 2 && !/Остановить/.test(document.querySelector(".dv-content-container")?.innerText || ""), null, 20 * 60000);
    await page.locator(".dv-content-container button.vc").first().click(); await page.waitForTimeout(2000);
    return `карточек ${await page.locator(".dv-content-container button.vc").count()}, выбран первый`;
  });
  await step("Альбом ППТ КРТ: собрать", async () => {
    await page.locator("header.top wa-button", { hasText: "Листы и альбом" }).click(); await page.waitForTimeout(2500);
    await page.locator("wa-button[slot=trigger]", { hasText: "Собрать" }).first().click();
    await page.locator("wa-dropdown-item[value=pptkrt]").first().click();
    await wait(() => !/Собираю|Собираю альбом/.test(document.body.innerText) && document.querySelectorAll(".album .sheet, .album li, .sheets li").length > 0, null, 15 * 60000).catch(() => {});
    await page.waitForTimeout(3000);
    return (await page.evaluate(() => document.body.innerText.match(/\d+ лист\S*/)?.[0])) || "";
  });
  await step("Альбом в PDF", async () => {
    const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 20 * 60000 }), (async () => {
      await page.locator(".dv-content-container wa-button", { hasText: /^\s*PDF\s*$/ }).first().click(); await page.waitForTimeout(1500);
      const go = page.locator("wa-button", { hasText: "Выгрузить всё равно" }).first(); if (await go.count()) await go.click(); })()]);
    await dl.saveAs(join(OUT, "альбом.pdf")); return `альбом.pdf, ${Math.round(readFileSync(join(OUT, "альбом.pdf")).length / 1024)} КБ`;
  });
  await step("Выгрузка DXF", () => save("dxf", "чертёж-dxf.zip"), { shot: false });
  await step("Выгрузка GeoJSON", () => save("geojson", "слои-geojson.zip"), { shot: false });
  await step("Выгрузка Excel (ТЭП и листы)", () => save("xlsx", "тэп.xlsx"), { shot: false });
} finally {
  const total = ((Date.now() - t00) / 1000 / 60).toFixed(1);
  const md = [`# Приёмка ГРАДО 2: ${NAME}`, "", `${new Date().toLocaleString("ru-RU")}; кэш ${flag("warm") ? "обычный" : "пустой"}; всего ${total} мин.`, "",
    "| шаг | вышло | время, с | что видно |", "|---|---|---|---|", ...rows.map(r => `| ${r.map(c => String(c).replace(/\|/g, "/")).join(" | ")} |`), "",
    "## Слои выгрузки", "", ...(rows.layers || []).map(([c, n, d, s]) => `- ${/error/.test(c) ? "ОШИБКА" : /empty/.test(c) ? "пусто" : "есть"} — ${n}: ${d}${s ? " (" + s + ")" : ""}`), "",
    `## Ошибки консоли браузера (${errors.length})`, "", ...errors.slice(0, 40).map(e => "- " + e.slice(0, 300).replace(/\n/g, " "))].join("\n");
  writeFileSync(join(OUT, "report.md"), md + "\n");
  console.log(`\nОтчёт: ${join(OUT, "report.md")}  (всего ${total} мин)`);
  await browser.close(); srv?.kill(); rmSync(proj, { recursive: true, force: true });
  process.exit(rows.some(r => r[1] !== "да") ? 1 : 0);
}
