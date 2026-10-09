// ГРАДО 2 · автоматическая проверка раскладки нового интерфейса (/next/) по своду docs/ux/ui-grid.md: запускает тестовый сервер
// на копии apps/grado2/tests/fixtures/next_ui_project.grado2, открывает каждое окно в Chrome (полосы прокрутки видны, как на Mac
// с мышью) на 1280 × 800 и 1920 × 1080 в светлой и тёмной теме и ищет то, на что жаловался владелец 09.10.2026: полосы прокрутки
// по ширине и вложенные, поля и кнопки за краем окна, текст, обрезанный без многоточия, поля не в одну колонку, прыжки шапки,
// ленты и строки состояния, мелкие цели для мыши, мелкий и моноширинный шрифт.
// Запуск: CHROME=… node tools/ui_layout_check.mjs [--out DIR] [--sizes 1280x800,1920x1080] [--themes light,dark] [--shots]
// Итог: DIR/report.md и DIR/report.json, снимки окон (--shots) в DIR; код выхода 1, если есть нарушения строгих правил (STRICT).
// Нужны (cd tools && npm ci) и ~/.grado2/venv; вызывает tools/gate.sh при E2E=1.
import { spawn } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { homedir, tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const arg = (k, d) => { const i = process.argv.indexOf("--" + k); return i > 0 ? process.argv[i + 1] : d; };
const OUT = resolve(arg("out", "/tmp/grado-ui-check"));
const SIZES = arg("sizes", "1280x800,1920x1080").split(",").map(s => s.split("x").map(Number));
const THEMES = arg("themes", "light,dark").split(",");
const SHOTS = process.argv.includes("--shots");
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PY = process.env.PY || join(homedir(), ".grado2/venv/bin/python");

// строгие правила: их нарушение валит проверку; остальное — в отчёт, правится по мере прохода окон
export const STRICT = new Set(["scroll-x", "scroll-nested", "outside", "jump", "mono", "drag", "hover"]);
const TITLE = {
  "scroll-x": "полоса прокрутки по ширине", "scroll-nested": "прокрутка внутри прокрутки", outside: "поле или кнопка за краем окна",
  cut: "текст обрезан без многоточия", align: "поля окна не в одну колонку", jump: "сдвинулась шапка, лента или строка состояния",
  shift: "раскладка прыгнула (CLS)", drag: "окно или граница не идёт за мышью", hover: "наведение мыши сдвигает соседей", target: "цель для мыши меньше 20 px", small: "шрифт мельче 11 px", mono: "моноширинный шрифт",
};

export function startServer() {
  const dir = mkdtempSync(join(tmpdir(), "grado-ui-"));
  copyFileSync(join(ROOT, "apps/grado2/tests/fixtures/next_ui_project.grado2"), join(dir, ".autosave.grado2"));
  const port = String(8700 + Math.floor(Math.random() * 250));     // свой порт: другой запуск проверки или тестовый сервер того же кода не мешают
  const proc = spawn(PY, [join(ROOT, "apps/grado2/server.py"), port], {
    env: { ...process.env, GRADO2_PROJECTS: dir, GRADO2_NO_BROWSER: "1", PYTHONPATH: "" }, stdio: ["ignore", "pipe", "pipe"],
  });
  return new Promise((ok, bad) => {
    let log = "";
    const on = b => { log += b; const m = log.match(/ГРАДО 2: (http:\/\/127\.0\.0\.1:\d+)/); if (m) ok({ url: m[1], stop: () => { proc.kill(); rmSync(dir, { recursive: true, force: true }); } }); };
    proc.stdout.on("data", on); proc.stderr.on("data", on);
    proc.on("exit", c => bad(new Error("сервер не запустился (" + c + "): " + log.slice(-500))));
    setTimeout(() => bad(new Error("сервер не ответил за 30 с: " + log.slice(-500))), 30000);
  });
}

/* Обход видимой страницы, включая теневые корни Web Awesome; возвращает нарушения. Выполняется в браузере. */
function measure() {
  const out = [];
  const all = [];
  (function walk(root) { for (const el of root.querySelectorAll("*")) { all.push(el); if (el.shadowRoot) walk(el.shadowRoot); } })(document);
  const host = el => el.getRootNode()?.host;
  const up = el => el.parentElement || host(el);
  const shown = el => { const r = el.getBoundingClientRect(); if (r.width < 1 || r.height < 1) return false; const s = getComputedStyle(el); return s.visibility !== "hidden" && s.display !== "none" && +s.opacity > 0; };
  const pane = el => { for (let e = el; e; e = up(e)) if (e.classList?.contains("dv-groupview")) return e; return null; };
  const where = el => {
    const g = pane(el);
    const tab = g?.querySelector(".dv-tab.dv-active-tab")?.textContent.trim();
    if (tab) return "окно «" + tab + "»";
    for (let e = el; e; e = up(e)) { if (e.matches?.("header.top")) return "шапка"; if (e.matches?.("nav.ribbon")) return "лента"; if (e.matches?.("footer.status")) return "строка состояния"; }
    return "страница";
  };
  const name = el => {
    let n = el.tagName.toLowerCase();
    const c = typeof el.className === "string" && el.className.trim().split(/\s+/).filter(x => !x.startsWith("data-v")).slice(0, 2).join(".");
    if (c) n += "." + c;
    const t = (el.getAttribute?.("label") || el.getAttribute?.("aria-label") || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 40);
    return t ? `${n} «${t}»` : n;
  };
  const add = (rule, el, detail = "") => out.push({ rule, where: where(el), what: name(el), detail });
  const scrolls = el => {
    const s = getComputedStyle(el);
    return { x: /auto|scroll/.test(s.overflowX) && el.scrollWidth > el.clientWidth + 1, y: /auto|scroll/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 1 };
  };
  for (const el of all) {
    if (!shown(el)) continue;
    const s = getComputedStyle(el);
    const sc = scrolls(el);
    if (sc.x && !el.closest?.(".ol-viewport, .tablewrap, .grid, canvas, .sheet-stage")) add("scroll-x", el, `${el.scrollWidth} > ${el.clientWidth}`);
    if (sc.y) for (let e = up(el); e; e = up(e)) if (shown(e) && scrolls(e).y) { add("scroll-nested", el, "внутри " + name(e)); break; }
    if (/mono/i.test(s.fontFamily) && el.childNodes.length && [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) add("mono", el, s.fontFamily);
    const fs = parseFloat(s.fontSize);
    if (fs < 11 && [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) add("small", el, fs + " px");
    if (s.overflowX === "hidden" && s.textOverflow !== "ellipsis" && el.scrollWidth > el.clientWidth + 1 && [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) && !el.matches?.("input,textarea"))
      add("cut", el, `${el.scrollWidth} > ${el.clientWidth}`);
  }
  // за краем окна: элемент управления выходит за видимую часть своего окна dockview
  for (const el of all) {
    if (!el.matches?.("wa-button, wa-input, wa-select, wa-number-input, wa-slider, wa-switch, wa-checkbox, button, input, select, textarea, label") || !shown(el)) continue;
    const g = pane(el); if (!g || el.closest(".gcanvas")) continue;   // холст схемы двигают мышью: блоки за краем — норма
    const body = g.querySelector(".dv-content-container") || g;
    const b = body.getBoundingClientRect(), r = el.getBoundingClientRect();
    if (r.right > b.right + 1 || r.left < b.left - 1) add("outside", el, `${Math.round(r.left)}–${Math.round(r.right)} при окне ${Math.round(b.left)}–${Math.round(b.right)}`);
  }
  // поля в одну колонку: у строк .f одного окна поле начинается с одной и той же x
  for (const p of document.querySelectorAll(".pane")) {
    if (!shown(p)) continue;
    const by = new Map();
    for (const f of p.querySelectorAll(".f")) {
      if (!shown(f) || f.parentElement.closest(".f") || f.children.length < 2) continue;
      const x = Math.round(f.children[1].getBoundingClientRect().left - f.getBoundingClientRect().left);
      const k = f.parentElement; if (!by.has(k)) by.set(k, new Set()); by.get(k).add(x);
    }
    for (const [k, xs] of by) if ([...xs].some(a => [...xs].some(b => Math.abs(a - b) > 2))) add("align", k, "отступы поля: " + [...xs].sort((a, b) => a - b).join(", ") + " px");
  }
  // мелкие цели: кнопки, поля, флажки и вкладки меньше 20 px по высоте или ширине
  for (const el of document.querySelectorAll("wa-button, button, wa-switch, wa-checkbox, select, input:not([type=hidden]), .dv-tab, [role=button]")) {
    if (!shown(el) || el.closest("wa-dropdown-item, .ol-attribution, .gcanvas")) continue;   // в схеме расчёта размер задаёт масштаб холста
    const r = el.getBoundingClientRect();
    if (r.height < 20 || r.width < 20) add("target", el, `${Math.round(r.width)} × ${Math.round(r.height)}`);
  }
  return out;
}

/* Движения мышью, на которые жаловался владелец: плавающее окно за полосу, его угол, граница между окнами, наведение.
   Окно и граница должны идти ровно за мышью (±3 px), наведение не должно двигать соседние элементы. */
async function interact(page, tag) {
  const out = [];
  const bad = (rule, where, what, detail) => out.push({ rule, where, what, detail, screen: tag, step: "мышь" });
  const box = async loc => (await loc.count()) ? loc.first().boundingBox() : null;
  const drag = async (x, y, dx, dy, probe) => {
    await page.mouse.move(x, y); await page.mouse.down();
    const seen = [];
    for (let i = 1; i <= 10; i++) { await page.mouse.move(x + dx * i / 10, y + dy * i / 10); await page.waitForTimeout(16); if (probe) seen.push(await probe()); }
    await page.mouse.up(); await page.waitForTimeout(250);
    return seen;
  };
  const near = (a, b) => Math.abs(a - b) <= 3;
  // 1. плавающее окно двигают за полосу над вкладками
  await page.mouse.click(640, 5); await page.keyboard.press("F1"); await page.waitForTimeout(500);   // «Справка» открывается плавающим окном
  const win = page.locator(".dv-resize-container", { has: page.locator(".dv-tab", { hasText: "Справка" }) });
  const bar = win.locator(".dv-floating-titlebar");
  const b0 = await box(win), h = await box(bar);
  if (!b0 || !h) bad("drag", "окно «Справка»", "плавающее окно", "не открылось плавающим или нет полосы для перетаскивания");
  else {
    const seen = await drag(h.x + h.width / 2, h.y + h.height / 2, -120, 60, () => box(win));
    const b1 = await box(win);
    const first = seen[0];
    if (first && (Math.abs(first.x - b0.x) > 15 || Math.abs(first.y - b0.y) > 9)) bad("drag", "окно «Справка»", "начало перетаскивания", `окно прыгнуло на ${Math.round(first.x - b0.x)}, ${Math.round(first.y - b0.y)} при сдвиге мыши −12, 6`);
    const dock = await box(page.locator(".grado-dock"));
    const ex = Math.max(-120, dock.x - b0.x), ey = Math.min(60, dock.y + dock.height - b0.y - b0.height);   // окно не уходит за край области окон
    if (!near(b1.x - b0.x, ex) || !near(b1.y - b0.y, ey)) bad("drag", "окно «Справка»", "перетаскивание за полосу", `мышь −120, 60 (можно ${Math.round(ex)}, ${Math.round(ey)}) — окно ${Math.round(b1.x - b0.x)}, ${Math.round(b1.y - b0.y)}`);
    if (!near(b1.width, b0.width) || !near(b1.height, b0.height)) bad("drag", "окно «Справка»", "перетаскивание за полосу", `размер изменился: ${Math.round(b0.width)}×${Math.round(b0.height)} → ${Math.round(b1.width)}×${Math.round(b1.height)}`);
    // 2. угол плавающего окна
    const c = await box(win.locator(".dv-resize-handle-bottomright"));
    if (c) {
      const a0 = await box(win), dock = await box(page.locator(".grado-dock"));
      await drag(c.x + c.width / 2, c.y + c.height / 2, 60, 40);
      const a1 = await box(win);
      const ew = Math.min(60, dock.x + dock.width - a0.x - a0.width), eh = Math.min(40, dock.y + dock.height - a0.y - a0.height);
      if (!near(a1.width - a0.width, ew) || !near(a1.height - a0.height, eh) || !near(a1.x, a0.x) || !near(a1.y, a0.y))
        bad("drag", "окно «Справка»", "угол окна", `мышь +60, +40 — ширина ${Math.round(a1.width - a0.width)}, высота ${Math.round(a1.height - a0.height)}, угол сдвинулся на ${Math.round(a1.x - a0.x)}, ${Math.round(a1.y - a0.y)}`);
    }
    // окно не уходит за край экрана, но и не прыгает назад, пока его тянут
    const e0 = await box(win), vw = page.viewportSize();
    const hb = await box(bar);
    await drag(hb.x + hb.width / 2, hb.y + hb.height / 2, vw.width, 0);
    const e1 = await box(win);
    if (e1.x + e1.width > vw.width + 1) bad("drag", "окно «Справка»", "у края экрана", "окно ушло за правый край экрана");
    await page.locator(".dv-tab", { hasText: "Справка" }).first().hover();
    await win.locator(".dv-tab.dv-active-tab .dv-default-tab-action").first().click({ force: true }).catch(() => {});
    await page.waitForTimeout(300);
    void e0;
  }
  // 3. граница между окнами «Слои» и «Карта»: тянем вправо на 40 px
  const left = page.locator(".dv-groupview", { has: page.locator(".dv-tab", { hasText: /^Слои$/ }) });
  const l0 = await box(left);
  if (l0) {
    const sx = l0.x + l0.width + 4, sy = l0.y + l0.height / 2;   // зазор 8 px между окнами — граница посередине
    const seen = await drag(sx, sy, 40, 0, () => box(left));
    const l1 = await box(left);
    if (!near(l1.width - l0.width, 40)) bad("drag", "граница «Слои» | «Карта»", "перетаскивание границы", `мышь +40 — окно шире на ${Math.round(l1.width - l0.width)}`);
    const steps = seen.map(b => Math.round(b.width - l0.width));
    if (steps.some((d, i) => i && d < steps[i - 1] - 1)) bad("drag", "граница «Слои» | «Карта»", "перетаскивание границы", "ширина шла назад: " + steps.join(", "));
    await drag(sx + 40, sy, -40, 0);
  }
  // 4. наведение: проводим мышью по кнопкам, вкладкам и строкам всех видимых окон и ленты — соседи не должны двигаться
  const targets = await page.evaluate(() => [...document.querySelectorAll(".dv-tab, .pane wa-button, .pane button, .pane .row, .pane li, .pane tr, nav.ribbon wa-button, footer.status button")]
    .map(el => { const r = el.getBoundingClientRect(); return r.width > 4 && r.height > 4 && r.top >= 0 && r.bottom <= innerHeight ? [r.x + r.width / 2, r.y + r.height / 2] : null; }).filter(Boolean).slice(0, 400));
  const snap = () => page.evaluate(() => [...document.querySelectorAll(".pane *, nav.ribbon *, footer.status *, .dv-tab")].filter(e => !e.closest("canvas, .ol-viewport, svg"))
    .map(e => { const r = e.getBoundingClientRect(); return r.width > 0 ? [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height), e.tagName + "." + (typeof e.className === "string" ? e.className.split(" ")[0] : "") + " «" + (e.textContent || "").trim().slice(0, 30) + "»"] : null; }));
  let moved = 0;
  for (const [x, y] of targets) {
    await page.mouse.move(5, 5); await page.waitForTimeout(30);
    const a = await snap();
    await page.mouse.move(x, y); await page.waitForTimeout(160);   // переходы оформления длятся до 120 мс
    const b = await snap();
    if (a.length !== b.length) continue;                            // появилась подсказка или меню — это не сдвиг
    for (let i = 0; i < a.length; i++) {
      if (!a[i] || !b[i] || a[i][4] !== b[i][4]) continue;
      if (Math.abs(a[i][0] - b[i][0]) > 1 || Math.abs(a[i][1] - b[i][1]) > 1) { bad("hover", "наведение", b[i][4], `сдвиг ${b[i][0] - a[i][0]}, ${b[i][1] - a[i][1]} px при мыши на ${Math.round(x)}, ${Math.round(y)}`); if (++moved > 20) break; break; }
    }
    if (moved > 20) break;
  }
  return out;
}

/* Положения постоянных частей экрана: шапка, лента, строка состояния. Сдвиг между двумя замерами — «прыжок». */
function chrome() {
  const r = {};
  document.querySelectorAll("header.top > *, nav.ribbon > *, footer.status > *").forEach((el, i) => {
    if (el.classList.contains("grow")) return;                     // распорка: её ширина и должна меняться
    const b = el.getBoundingClientRect(); if (b.width < 1) return;
    r[i + ":" + el.tagName + ":" + (el.className || "")] = [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height)];
  });
  return r;
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  let pw;
  try { pw = createRequire(join(ROOT, "tools/package.json"))("playwright-core"); } catch { console.error("нет playwright-core: (cd tools && npm ci)"); process.exit(2); }
  const srv = await startServer();
  const browser = await pw.chromium.launch({ executablePath: CHROME, headless: true, ignoreDefaultArgs: ["--hide-scrollbars"], args: ["--no-sandbox", "--enable-unsafe-swiftshader"] });
  const found = [];
  const errors = [];
  try {
    for (const [w, h] of SIZES) for (const theme of THEMES) {
      const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: theme });
      await ctx.addInitScript(t => {
        try { localStorage.setItem("grado-next-theme", t); localStorage.setItem("grado-next-seen", "[]"); } catch { /* нет */ }
        window.__shifts = [];
        new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__shifts.push({ v: e.value, src: (e.sources || []).map(s => s.node?.nodeName + "." + (s.node?.className || "")).slice(0, 3) }); })
          .observe({ type: "layout-shift", buffered: true });
      }, theme);
      const page = await ctx.newPage();
      page.on("pageerror", e => errors.push(`${w}×${h} ${theme}: ${e.message}`));
      await page.goto(srv.url + "/next/");
      await page.waitForSelector(".dv-tab", { timeout: 20000 });
      await page.waitForFunction(() => document.querySelector(".project")?.textContent.includes("Тест"), null, { timeout: 20000 }).catch(() => {});
      await page.waitForTimeout(1500);
      if (theme === "dark" && !(await page.evaluate(() => document.documentElement.classList.contains("wa-dark")))) {   // тема — кнопкой, как владелец
        await page.click("header.top wa-button[title='Тёмная тема']").catch(() => {});
        await page.waitForTimeout(400);
      }
      const tag = `${w}×${h} ${theme === "dark" ? "тёмная" : "светлая"}`;
      const titles = await page.evaluate(() => [...[...document.querySelectorAll("header.top wa-dropdown")].find(d => d.querySelector("wa-button[slot=trigger]")?.textContent.trim() === "Окна")
        .querySelectorAll("wa-dropdown-item[type=checkbox]")].map(i => i.textContent.trim()).filter(t => !["Карта", "Комментарии", "Макет листа"].includes(t)));
      const record = (list, win) => { for (const f of list) found.push({ ...f, screen: tag, step: win }); };
      record(await page.evaluate(measure), "открытие");
      if (SHOTS) await page.screenshot({ path: join(OUT, `${w}x${h}-${theme}-00-start.png`) });
      for (const [i, t] of titles.entries()) {
        const before = await page.evaluate(chrome);
        await page.evaluate(() => { window.__shifts = []; });
        const tab = page.locator(".dv-tab", { hasText: t }).first();
        if (await tab.count()) { for (const ev of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]) await tab.dispatchEvent(ev, { button: 0 }); }   // вкладку может закрывать плавающее окно
        else {
          await page.locator("header.top wa-button[slot=trigger]", { hasText: "Окна" }).click();
          await page.locator("header.top wa-dropdown-item[type=checkbox]", { hasText: t }).first().click();
          await page.keyboard.press("Escape");
        }
        await page.waitForTimeout(500);
        const after = await page.evaluate(chrome);
        for (const k of Object.keys(before)) if (after[k] && after[k].join() !== before[k].join())
          found.push({ rule: "jump", where: "постоянная часть экрана", what: k.split(":").slice(1).join(" "), detail: `${before[k]} → ${after[k]}`, screen: tag, step: "окно «" + t + "»" });
        const cls = await page.evaluate(() => window.__shifts);
        const sum = cls.reduce((a, e) => a + e.v, 0);
        if (sum > 0.02) found.push({ rule: "shift", where: "окно «" + t + "»", what: cls.flatMap(e => e.src).slice(0, 3).join(", "), detail: "CLS " + sum.toFixed(3), screen: tag, step: "окно «" + t + "»" });
        record(await page.evaluate(measure), "окно «" + t + "»");
        if (SHOTS) await page.screenshot({ path: join(OUT, `${w}x${h}-${theme}-${String(i + 1).padStart(2, "0")}.png`) });
      }
      await page.evaluate(() => { localStorage.removeItem("grado-next-layout"); localStorage.setItem("grado-next-seen", JSON.stringify(["norms", "vars", "cmp", "vol", "views", "help", "comments", "sheet", "cons", "sketch", "graph"])); });
      await page.reload(); await page.waitForSelector(".dv-tab"); await page.waitForTimeout(1200);
      found.push(...await interact(page, tag));
      if (SHOTS) await page.screenshot({ path: join(OUT, `${w}x${h}-${theme}-99-mouse.png`) });
      await ctx.close();
    }
  } finally { await browser.close(); srv.stop(); }

  // одно нарушение на каждом экране и окне встречается много раз — сводим по правилу, месту и элементу
  const key = f => [f.rule, f.where, f.what].join("|");
  const uniq = new Map();
  for (const f of found) { const k = key(f); if (!uniq.has(k)) uniq.set(k, { ...f, screens: new Set() }); uniq.get(k).screens.add(f.screen); }
  const list = [...uniq.values()].map(f => ({ ...f, screens: [...f.screens] })).sort((a, b) => (STRICT.has(b.rule) - STRICT.has(a.rule)) || a.rule.localeCompare(b.rule) || a.where.localeCompare(b.where));
  writeFileSync(join(OUT, "report.json"), JSON.stringify({ errors, issues: list }, null, 1));
  const md = ["# Проверка раскладки нового интерфейса", "", `Экраны: ${SIZES.map(s => s.join("×")).join(", ")}; темы: ${THEMES.join(", ")}.`, ""];
  for (const r of Object.keys(TITLE)) {
    const xs = list.filter(f => f.rule === r); if (!xs.length) continue;
    md.push(`## ${TITLE[r]}${STRICT.has(r) ? " (строгое)" : ""} — ${xs.length}`, "");
    for (const f of xs) md.push(`- ${f.where}: ${f.what}${f.detail ? " — " + f.detail : ""} (${f.screens.join("; ")})`);
    md.push("");
  }
  if (errors.length) md.push("## Ошибки страницы", "", ...errors.map(e => "- " + e), "");
  writeFileSync(join(OUT, "report.md"), md.join("\n"));
  const strict = list.filter(f => STRICT.has(f.rule)).length;
  console.log(`ui-layout: ${list.length} нарушений, строгих ${strict}, ошибок страницы ${errors.length} — ${join(OUT, "report.md")}`);
  for (const r of Object.keys(TITLE)) { const n = list.filter(f => f.rule === r).length; if (n) console.log(`  ${STRICT.has(r) ? "STRICT" : "      "} ${TITLE[r]}: ${n}`); }
  process.exit(strict || errors.length ? 1 : 0);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main().catch(e => { console.error(e); process.exit(2); });
