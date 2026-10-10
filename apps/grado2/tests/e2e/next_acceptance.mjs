// ГРАДО 2 · сценарии приёмки C, D, E, G, H, N из docs/ux/grado2-ux.md в новом интерфейсе (/next/), без интернета: тестовый сервер
// на копии tests/fixtures/next_ui_project.grado2 с границей территории вокруг его зданий; мышь и клавиши — как у владельца.
// Запуск: CHROME=… node apps/grado2/tests/e2e/next_acceptance.mjs [--shots DIR]; нужны (cd tools && npm ci) и ~/.grado2/venv.
// Итог: строки «ok - …» и «FAILED …», SUMMARY; код выхода 1 при провале. Вызывают tests/test_e2e.py (GRADO2_E2E=1) и CI.
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { homedir, tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../../..");
const pw = createRequire(join(ROOT, "tools/package.json"))("playwright-core");
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PY = process.env.PY || join(homedir(), ".grado2/venv/bin/python");
const SHOTS = (i => i > 0 ? process.argv[i + 1] : "")(process.argv.indexOf("--shots"));
// граница вокруг 24 зданий образца (37.796–37.810, 55.823–55.829), чтобы эскиз, ТЭП и варианты считались без порталов
const TERR = { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[[37.7955, 55.8222], [37.8105, 55.8222], [37.8105, 55.8300], [37.7955, 55.8300], [37.7955, 55.8222]]] } };

function startServer() {
  const dir = mkdtempSync(join(tmpdir(), "grado-acc-"));
  const proj = JSON.parse(readFileSync(join(ROOT, "apps/grado2/tests/fixtures/next_ui_project.grado2"), "utf-8"));
  // соцобъекты образца — под ключом выгрузки OSM («Школы, детсады, поликлиники»), с полем «Вид», как их пишет сервер
  const soc = proj.data.social; delete proj.data.social;
  soc.fc.features.forEach((f, i) => { f.properties = { "Вид": i ? "школа" : "детский сад", "Название": `Соцобъект ${i + 1}` }; });
  proj.data["osm.social"] = soc;
  proj.layers.forEach(l => { if (l.key === "social") l.key = "osm.social"; });
  writeFileSync(join(dir, ".autosave.grado2"), JSON.stringify({ ...proj, territory: TERR }));
  const port = String(8950 + Math.floor(Math.random() * 40));
  const proc = spawn(PY, [join(ROOT, "apps/grado2/server.py"), port], {
    env: { ...process.env, GRADO2_PROJECTS: dir, GRADO2_NO_BROWSER: "1", PYTHONPATH: "", PYTHONUNBUFFERED: "1" }, stdio: ["ignore", "pipe", "pipe"],
  });
  return new Promise((ok, bad) => {
    let log = "";
    const on = b => { log += b; const m = log.match(/ГРАДО 2: (http:\/\/127\.0\.0\.1:\d+)/); if (m) ok({ url: m[1], stop: () => { proc.kill(); rmSync(dir, { recursive: true, force: true }); } }); };
    proc.stdout.on("data", on); proc.stderr.on("data", on);
    proc.on("exit", c => bad(new Error("сервер не запустился (" + c + "): " + log.slice(-500))));
    setTimeout(() => bad(new Error("сервер не ответил за 30 с: " + log.slice(-500))), 30000);
  });
}

let failed = 0, passed = 0;
const errors = [];
function check(cond, msg, detail = "") {
  if (cond) { passed++; console.log("ok -", msg); } else { failed++; console.log(`  FAILED #${failed} ${msg}${detail ? " — " + detail : ""}`); }
  return cond;
}
async function scenario(name, page, fn) {
  const before = errors.length;
  try { await fn(); } catch (e) { failed++; console.log(`STEP FAILED ${name}: ${e.message.split("\n").slice(0, 3).join(" ")}`); }
  if (SHOTS) await page.screenshot({ path: join(SHOTS, name.replace(/[^\wа-яё]+/gi, "_") + ".png") }).catch(() => {});
  check(errors.length === before, `${name}: консоль без ошибок`, errors.slice(before).join(" | ").slice(0, 400));
}

// окна: вкладка по названию, текст её содержимого, кнопка внутри окна по тексту
const tab = (page, t) => page.locator(".dv-tab", { hasText: t }).first();
async function showWin(page, t) {
  if (!(await tab(page, t).count())) {
    await page.locator("header.top wa-button[slot=trigger]", { hasText: "Окна" }).click();
    await page.locator("header.top wa-dropdown-item[type=checkbox]", { hasText: t }).first().click();
    await page.waitForTimeout(400);
  }
  await tab(page, t).click(); await page.waitForTimeout(300);
}
async function closeWin(page, t) {
  if (!(await tab(page, t).count())) return;
  await page.locator("header.top wa-button[slot=trigger]", { hasText: "Окна" }).click();
  await page.locator("header.top wa-dropdown-item[type=checkbox]", { hasText: t }).first().click();
  await page.waitForTimeout(400);
}
const winBody = (page, t) => page.evaluate(t => {
  const tb = [...document.querySelectorAll(".dv-tab")].find(x => x.textContent.trim() === t);
  return tb ? tb.closest(".dv-groupview").querySelector(".dv-content-container") : null;
}, t);
const winText = (page, t) => page.evaluate(t => {
  const tb = [...document.querySelectorAll(".dv-tab")].find(x => x.textContent.trim() === t);
  return tb ? tb.closest(".dv-groupview").querySelector(".dv-content-container").innerText : "";
}, t);
const winButton = (page, t, label) => page.locator(".dv-groupview", { has: page.locator(".dv-tab.dv-active-tab", { hasText: t }) })
  .locator(".dv-content-container wa-button", { hasText: label }).first();
async function until(page, fn, arg, what, ms = 20000) {
  try { await page.waitForFunction(fn, arg, { timeout: ms, polling: 200 }); return true; } catch { return check(false, what, "не дождался за " + ms / 1000 + " с"); }
}
const num = s => +String(s).replace(/\s| /g, "").replace(",", ".");

async function download(page, item) {
  const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 30000 }),
    (async () => { await page.locator("header.top wa-button[slot=trigger]", { hasText: "Выгрузка" }).click(); await page.locator(`header.top wa-dropdown-item[value=${item}]`).click(); })()]);
  return { name: dl.suggestedFilename(), body: readFileSync(await dl.path()) };
}

const srv = await startServer();
const browser = await pw.chromium.launch({ executablePath: CHROME, headless: true, args: ["--no-sandbox", "--enable-unsafe-swiftshader"] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
const page = await ctx.newPage();
page.on("console", m => { if (m.type() === "error" && !/Failed to load resource|tile|ERR_/.test(m.text())) errors.push(m.text()); });
page.on("pageerror", e => errors.push(String(e)));
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
const t0 = Date.now();
try {
  await page.goto(srv.url + "/next/");
  await page.waitForSelector(".dv-tab", { timeout: 30000 });
  await until(page, () => document.querySelector(".project")?.textContent.includes("Тест"), null, "образец проекта открылся");

  // C. Существующее положение: граница и данные есть, «Данные» показывает их; слой перетаскивается выше — рисуется поверх
  await scenario("C существующее положение", page, async () => {
    await showWin(page, "Данные");
    const t = await winText(page, "Данные");
    check(/га/.test(t) && /слоёв/.test(t), "«Данные»: площадь границы и сводка слоёв проекта", t.slice(0, 160));
    await showWin(page, "Слои");
    const names = () => page.evaluate(() => [...document.querySelectorAll(".pane.layers .row[data-key]")].map(e => e.textContent.trim()));
    const before = await names();
    check(before.includes("Здания (ЕГКО)") && before.includes("Улицы (OSM)"), "в дереве слоёв есть здания и улицы", before.join(", "));
    const src = page.locator(".pane.layers .row[data-key]", { hasText: "Улицы (OSM)" }), dst = page.locator(".pane.layers .row[data-key]", { hasText: "Социальные объекты" });
    await src.dragTo(dst); await page.waitForTimeout(600);
    const after = await names();
    check(after.indexOf("Улицы (OSM)") < before.indexOf("Улицы (OSM)"), "«Улицы (OSM)» перетащен выше в дереве", after.join(", "));
  });

  // D. Анализ: эскиз внутри границы, ТЭП считается; изменение параметра эскиза («Ширина корпуса») меняет ТЭП
  const spp = async () => { const m = (await winText(page, "Показатели (ТЭП)")).match(/СПП новая\s*([\d\s\u00a0]+(?:,\d+)?)\s*тыс/); return m ? num(m[1]) : NaN; };
  await scenario("D анализ и ТЭП", page, async () => {
    await showWin(page, "Эскиз");
    await winButton(page, "Эскиз", "Построить эскиз").click();
    await showWin(page, "Показатели (ТЭП)");
    await until(page, () => /СПП новая\s*[1-9]/.test(document.body.innerText), null, "«Показатели» показывают СПП новую больше нуля", 30000);
    const t = await winText(page, "Показатели (ТЭП)"), a = await spp();
    check(/Территория/i.test(t) && a > 0, "ТЭП: территория и СПП новая больше нуля", `СПП ${a}; ` + t.slice(0, 120));
    await showWin(page, "Эскиз");
    const w = page.locator(".dv-content-container input[type=range][aria-label^='Ширина корпуса']").first();
    await w.focus(); for (let i = 0; i < 4; i++) await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(2500);
    await showWin(page, "Показатели (ТЭП)");
    await until(page, a => { const m = document.body.innerText.match(/СПП новая\s*([\d\s\u00a0]+(?:,\d+)?)\s*тыс/); return m && +m[1].replace(/\s|\u00a0/g, "").replace(",", ".") !== a; }, a,
      "после смены ширины корпуса ТЭП пересчитался", 30000);
    const b = await spp();
    check(b > 0 && b !== a, "СПП новая изменилась вслед за параметром эскиза", `${a} → ${b}`);
  });

  // E. Варианты: подбор, выбор варианта меняет эскиз; «Объём» открывается и рисует
  await scenario("E варианты и объём", page, async () => {
    await showWin(page, "Варианты");
    await winButton(page, "Варианты", "Подобрать варианты").click();
    await until(page, () => document.querySelectorAll(".dv-content-container button.vc").length >= 2, null, "появились карточки вариантов", 120000);
    const n = await page.locator(".dv-content-container button.vc").count();
    check(n >= 2, "вариантов больше одного", String(n));
    const sppBefore = await (async () => { await showWin(page, "Показатели (ТЭП)"); return spp(); })();
    await showWin(page, "Варианты");
    const cards = page.locator(".dv-content-container button.vc");
    await cards.nth(n - 1).click(); await page.waitForTimeout(2500);
    check(await cards.nth(n - 1).getAttribute("aria-pressed") === "true", "выбранная карточка отмечена");
    await showWin(page, "Показатели (ТЭП)");
    const sppAfter = await spp();
    check(sppAfter > 0 && sppAfter !== sppBefore, "выбранный вариант перенёсся в эскиз и ТЭП", `${sppBefore} → ${sppAfter}`);
    await showWin(page, "Объём");
    await page.waitForTimeout(1500);
    const canvas = await page.evaluate(() => { const tb = [...document.querySelectorAll(".dv-tab")].find(x => x.textContent.trim() === "Объём"); const c = tb?.closest(".dv-groupview").querySelector("canvas"); const r = c?.getBoundingClientRect(); return r ? [r.width, r.height] : null; });
    check(canvas && canvas[0] > 100 && canvas[1] > 100, "«Объём» рисует сцену", JSON.stringify(canvas));
    await closeWin(page, "Объём");
  });

  // G. Выгрузка: DXF — архив с чертежом, red_lns.shx и REDLN97.LIN; GeoJSON по слою; Excel с ТЭП
  await scenario("G выгрузка", page, async () => {
    const dxf = await download(page, "dxf");
    check(dxf.name === "grado2-dxf.zip" && ["grado2.dxf", "red_lns.shx", "REDLN97.LIN"].every(n => dxf.body.includes(n)), "DXF: zip с чертежом, red_lns.shx и REDLN97.LIN", dxf.name);
    const gj = await download(page, "geojson");
    check(gj.body.includes("README.txt") && gj.body.includes(".geojson") && gj.body.includes(Buffer.from("Граница территории".replace(/ /g, "_"))) || gj.body.includes(Buffer.from("Граница")), "GeoJSON: по файлу на слой и граница", gj.name);
    const xl = await download(page, "xlsx");
    check(xl.name === "grado2-tep.xlsx" && xl.body.slice(0, 2).toString() === "PK", "Excel: файл ТЭП", xl.name);
  });

  // H. Окна: открыть «Виды» рядом, сдвинуть границу, перезагрузить — раскладка та же
  await scenario("H раскладка окон после перезагрузки", page, async () => {
    const layout = () => page.evaluate(() => [...document.querySelectorAll(".dv-groupview")].map(g => [...g.querySelectorAll(".dv-tab")].map(t => t.textContent.trim()).join("|") + "@" + Math.round(g.getBoundingClientRect().width)).sort());
    // вертикальная граница между окном «Слои» и картой: её ведём мышью на 60 px вправо
    const left = () => page.evaluate(() => Math.round([...document.querySelectorAll(".dv-tab")].find(x => x.textContent.trim() === "Слои").closest(".dv-groupview").getBoundingClientRect().width));
    const b = await page.evaluate(() => {
      const r = [...document.querySelectorAll(".dv-tab")].find(x => x.textContent.trim() === "Слои").closest(".dv-groupview").getBoundingClientRect();
      const s = [...document.querySelectorAll(".dv-sash")].map(e => e.getBoundingClientRect()).filter(q => q.height > 200 && q.width < 20)
        .sort((p, q) => Math.abs(p.left - r.right) - Math.abs(q.left - r.right))[0];
      return s ? { x: s.left + s.width / 2, y: s.top + s.height / 2 } : null;
    });
    const w0 = await left();
    if (b) { await page.mouse.move(b.x, b.y); await page.mouse.down(); await page.mouse.move(b.x + 60, b.y, { steps: 10 }); await page.mouse.up(); }
    await page.waitForTimeout(500);
    const w1 = await left();
    check(Math.abs(w1 - w0 - 60) <= 4, "граница окна «Слои» идёт за мышью на 60 px", `${w0} → ${w1}`);
    const before = await layout();
    await page.reload(); await page.waitForSelector(".dv-tab"); await page.waitForTimeout(2000);
    const after = await layout();
    const same = before.length === after.length && before.every((g, i) => { const [a, wa] = g.split("@"), [b, wb] = after[i].split("@"); return a === b && Math.abs(wa - wb) <= 4; });
    check(same, "окна, вкладки и размеры вернулись после перезагрузки", JSON.stringify(before) + " → " + JSON.stringify(after));
  });

  // N. Анализ и виды: блок «Радиусы обслуживания» по соцобъектам пишет «вне радиуса … га», «В слой» сохраняет его слоем;
  // виды: сохранить «Существующее», скрыть слой, сохранить «Анализ», переключиться — видимость слоёв следует за видом
  await scenario("N анализ радиусов", page, async () => {
    await showWin(page, "Схема расчёта");
    const rows = await page.locator(".pane.layers .row[data-key]").count();
    await page.locator(".dv-content-container button[title^='Добавить блок «Радиусы обслуживания»']").click();
    await until(page, () => /Радиусы обслуживания»: \d+ объект.*вне радиуса/.test(document.body.innerText), null, "блок радиусов пишет «вне радиуса … га»", 20000);
    const t = await winText(page, "Схема расчёта");
    check(/вне радиуса [\d,]+\s*га/.test(t), "радиусы обслуживания посчитаны по соцобъектам", (t.match(/Радиусы обслуживания»:[^\n]*/) || [""])[0]);
    await winButton(page, "Схема расчёта", "В слой").click(); await page.waitForTimeout(800);
    await showWin(page, "Слои");
    check(await page.locator(".pane.layers .row[data-key]").count() === rows + 1, "«В слой» добавил слой с результатом", `${rows} → ${await page.locator(".pane.layers .row[data-key]").count()}`);
  });
  await scenario("N виды", page, async () => {
    const save = async name => {
      await showWin(page, "Виды");
      const inp = page.locator(".views .bar wa-input").first();
      await inp.click(); await page.keyboard.press("Control+A"); await page.keyboard.type(name);
      await winButton(page, "Виды", "Сохранить вид").click(); await page.waitForTimeout(400);
    };
    const shown = () => page.evaluate(() => { const r = [...document.querySelectorAll(".pane.layers .row[data-key]")].find(e => e.textContent.includes("Здания (ЕГКО)")); return r?.querySelector("button.eye")?.title; });
    await save("Существующее");
    await showWin(page, "Слои");
    await page.locator(".pane.layers .row[data-key]", { hasText: "Здания (ЕГКО)" }).locator("button.eye").click(); await page.waitForTimeout(300);
    check(await shown() === "Показать слой", "здания скрыты глазом");
    await save("Анализ");
    const t = await winText(page, "Виды");
    check(/Существующее/.test(t) && /Анализ/.test(t), "в «Видах» оба вида", t.slice(0, 200));
    await page.locator(".dv-content-container td.nm", { hasText: "Существующее" }).click(); await page.waitForTimeout(600);
    await showWin(page, "Слои");
    check(await shown() === "Скрыть слой", "вид «Существующее» вернул здания на карту", String(await shown()));
    await showWin(page, "Виды");
    await page.locator(".dv-content-container td.nm", { hasText: "Анализ" }).click(); await page.waitForTimeout(600);
    await showWin(page, "Слои");
    check(await shown() === "Показать слой", "вид «Анализ» снова их скрыл", String(await shown()));
  });
} catch (e) {
  failed++; console.log("STEP FAILED запуск: " + e.message.split("\n")[0]);
} finally {
  console.log(`SUMMARY: ${passed} ok, ${failed} failed, ${((Date.now() - t0) / 1000).toFixed(0)} s`);
  await browser.close(); srv.stop();
  process.exit(failed ? 1 : 0);
}
