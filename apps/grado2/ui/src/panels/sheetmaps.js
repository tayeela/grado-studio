/* ГРАДО 2 · карта и печать для «Макета листа» (SheetPanel.vue → SheetEditor.vue, проп maps): берёт слои открытого
   проекта (store.js) в охвате блока карты, оформляет их так же, как окно «Карта» (symbology.js), и просит сервер
   нарисовать карту блока (/api/print/map_svg — тот же рендер, что печатает альбом) или весь лист в PDF
   (/api/print/layout, apps/grado2/layout_io.py). Цвет объекта — как у карты (symbology.js symbolOf: единое, категории,
   диапазоны, правила; ЛГР — красной линией). Картинки карт кэшируются по месту, масштабу, размеру и слоям.
   Блок с видом (b.view, #119) берёт слои и оформление вида, а место и масштаб — из рамки вида (viewframes.js blockFromView;
   sync() правит блоки листа, frameTo() двигает рамку вида при «Сдвиге карты в рамке», frameScale() меняет её размер
   под масштаб, заданный числом, ownView() делает копию вида для одного листа; легенда с follow
   берёт строки из вида своей карты). */
import { project, shown, scale, viewNow } from "../store.js";
import { breaks, classStyle, edgeColor, floorsDenOf, fullStyle, legendItems as classesOf, lgrLinePrint, lgrPrintParts, swatchColor, symbolOf } from "../symbology.js";
import { blockBounds } from "../sheet/model.js";
import { blockFromView, frameForScale } from "../viewframes.js";

const PX_PT = 0.26 / 0.35;                  // радиус точки на экране (пикс.) → толщина w печати (print_io: r = w × 0,35 мм)
const boxes = new WeakMap();                // FeatureCollection → рамки объектов [запад, юг, восток, север]

function bboxOf(g) {
  const b = [Infinity, Infinity, -Infinity, -Infinity];
  const walk = c => { if (typeof c[0] === "number") { b[0] = Math.min(b[0], c[0]); b[1] = Math.min(b[1], c[1]); b[2] = Math.max(b[2], c[0]); b[3] = Math.max(b[3], c[1]); } else c.forEach(walk); };
  if (g?.type === "GeometryCollection") g.geometries.forEach(x => walk(x.coordinates || []));
  else if (g?.coordinates) walk(g.coordinates);
  return b;
}
function indexed(fc) {
  let v = boxes.get(fc);
  if (!v) { v = (fc.features || []).filter(f => f?.geometry).map(f => ({ g: f.geometry, b: bboxOf(f.geometry), p: f.properties || {} })); boxes.set(fc, v); }
  return v;
}
const meets = (a, b) => a[0] <= b[2] && b[0] <= a[2] && a[1] <= b[3] && b[1] <= a[3];

/* слои карты: без вида — как в окне «Карта»; с видом — видимость и оформление из вида (слоя нет в виде — скрыт, как
   при показе вида в ViewsPanel.vue) → [{ l, style }] снизу вверх не переставлены, порядок окна «Слои» */
const viewOf = id => id && project.views.find(v => v.id === id);
function layersOf(viewId) {
  const v = viewOf(viewId);
  if (!v) return project.layers.filter(shown).map(l => ({ l, style: l.style }));
  const by = new Map(v.layers.map(x => [x.key, x])), gOn = id => !id || (v.groups || []).find(g => g.id === id)?.visible !== false;
  return project.layers.filter(l => by.get(l.key)?.visible && gOn(l.group)).map(l => ({ l, style: by.get(l.key).style || l.style }));
}
/* Слои карты блока для печати: видимые (в виде блока или на карте), снизу вверх (как рисует карта), только объекты в охвате блока. */
export function mapLayers(b) {
  if (!b.center || !(b.scale > 0)) return [];
  const box = blockBounds(b), out = [];
  [...layersOf(b.view)].reverse().forEach(({ l, style }) => {
    const fc = project.data[l.key]?.fc;
    if (!fc) return;
    const s = fullStyle(style), feats = [], br = s.mode === "grad" ? breaks(s, fc) : null, effs = new Map();
    indexed(fc).forEach(({ g, b: fb, p }) => {
      if (!meets(fb, box)) return;
      // линии ЛГР — их знаками (зубцы, бергштрихи), как на карте, а не сплошной красной линией
      if (s.mode === "lgr") { lgrPrintParts(p._lt, p._miss).forEach(x => feats.push({ g, w: Math.max(s.width, 1), a: 1, ...x })); return; }
      const k = symbolOf(s, f => p[f], br);
      if (k.hide) return;
      let e = effs.get(k.id); if (!e) effs.set(k.id, e = classStyle(s, k.o));   // полный знак класса: контур, штрих, штриховка
      const f = printFeature(g, l.geom, e, k);
      // подпись — как на карте (symbology.js styleFunction): поле, размер (пикс. → мм листа), цвет; этажность — от своего
      // масштаба. Печать ставит подписи без наложений, не поместившиеся — в замечании листа (layout_io label_drop)
      if (e.label) {
        let t = p[e.label];
        const fd = e.label === "Этажность" ? floorsDenOf(l) : 0;
        if (t != null && t !== "" && (!fd || b.scale <= fd)) {
          if (e.label === "Этажность" && String(l.key).startsWith("user:")) t = t + " эт.";
          Object.assign(f, { label: String(t), ls: Math.round(e.labelSize * 0.26 * 100) / 100, ...(e.labelColor ? { lcol: e.labelColor } : {}) });
        }
      }
      feats.push(f);
    });
    if (feats.length) out.push({ title: l.title || l.key, features: feats });
  });
  return out;
}

/* Объект для печати (print_io.py: fill, stroke, w, a, dash, hatch, hp — узор, hs — шаг, hc — цвет штриховки, parts — слои знака) по стилю
   e (слой с полями класса) и знаку k — так же, как карта (symbology.js symbolStyle). */
export function printFeature(g, geom, e, k) {
  const f = printBase(g, geom, e, k);
  if (e.parts?.length && geom !== "point") f.parts = e.parts;     // слои знака поверх — print_io → symparts.py, как partStyles на карте
  return f;
}
function printBase(g, geom, e, k) {
  const dash = e.dash?.length ? e.dash : undefined;
  if (e.lgrLine && geom !== "point") {                    // знак ЛГР слоя: у полигона — контуром, знаки внутрь (print_io lsign)
    const z = lgrLinePrint(e.lgrLine), w = Math.max(1, e.width);
    if (geom === "line") return { g, w, a: 1, ...z };
    const f = { g, fill: k.fill, stroke: null, w, a: e.opacity, ...z };
    if (k.hatch) Object.assign(f, { hatch: true, hp: e.hatchPat || "45", hs: e.hatchStep, hc: e.hatchColor });
    return f;
  }
  if (geom === "line") return { g, stroke: k.fill, w: e.width, a: 1, dash };              // у линии цвет — fill, как на карте
  if (geom === "point") return { g, fill: k.fill, stroke: e.stroke, w: (2 + e.width * 2) * PX_PT };
  const f = { g, fill: k.fill, stroke: e.width > 0 ? edgeColor(e, k) : null, w: e.width, a: e.opacity, dash };
  if (k.hatch) Object.assign(f, { hatch: true, hp: e.hatchPat || "45", hs: e.hatchStep, hc: e.hatchColor });
  return f;
}

/* Строки легенды из видимых слоёв проекта, сверху вниз, как в окне «Слои»; у слоя с категориями, диапазонами или
   правилами — строка на каждый класс. */
export function legendItems(viewId) {
  const out = [];
  layersOf(viewId).filter(({ l }) => project.data[l.key]).forEach(({ l, style }) => {
    const s = fullStyle(style), t = l.title || l.key, line = l.geom === "line" || s.mode === "lgr";
    const row = (title, c, o, h) => out.push(legendRow(title, line, classStyle(s, o), { fill: c, hatch: !!h }));
    const cls = s.mode === "single" || s.mode === "lgr" ? [] : classesOf(s, project.data[l.key].fc).filter(x => !x.off);
    if (cls.length) cls.forEach(x => row(`${t}: ${x.v === "" ? "без значения" : x.v}`, x.c, x.o, x.h ?? (s.mode === "grad" && s.hatch)));
    else row(t, swatchColor(s), null, s.mode === "single" && s.hatch);
  });
  return out;
}

/* Строка легенды: знак как на карте — заливка с прозрачностью, контур своей толщины и штриха, штриховка (layout_io.py _legend,
   sheet/draw.js legendContent). */
export function legendRow(t, line, e, k) {
  const dash = e.dash?.length ? e.dash.map(v => +(v * 0.26).toFixed(2)) : undefined;   // штрих карты (пикс.) → мм листа, как print_io PX_MM
  if (line) return { t, s: "line", c: k.fill, ...(dash ? { dash } : {}) };
  const r = { t, s: "fill", c: edgeColor(e, k), f: k.fill };
  if (e.opacity < 1 && !k.hatch) r.a = e.opacity;
  if (e.width !== 1) r.w = e.width;
  if (dash) r.dash = dash;
  if (k.hatch) Object.assign(r, { h: e.hatchPat || "45", hc: e.hatchColor || k.fill, ...(e.hatchColor ? {} : { f: null }) });
  return r;
}

/* ---------- картинки карт блоков ---------- */
const cache = new Map();                    // ключ → { state: "loading" | "ready" | "error", img, at }
const last = new Map();                     // id блока → последняя готовая картинка (показывается, пока грузится новая)
let dataTick = 0, lastData = null;
const sig = viewId => JSON.stringify([layersOf(viewId).map(({ l, style }) => [l.key, style]), dataTick]);

function key(b) {
  if (project.data !== lastData) { lastData = project.data; dataTick++; }
  return JSON.stringify([b.w, b.h, b.center, b.scale, b.basemap || "none", sig(b.view)]);
}

async function load(k, b, entry, redraw) {
  try {
    const r = await fetch("/api/print/map_svg", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ block: { w: b.w, h: b.h, center: b.center, scale: b.scale, basemap: b.basemap || "none" }, layers: mapLayers(b) }) });
    if (!r.ok) throw new Error(r.status);
    const svg = await r.text(), img = new Image();
    img.onload = () => { entry.state = "ready"; entry.img = img; last.set(b.id, entry); redraw?.(); };
    img.onerror = () => { entry.state = "error"; redraw?.(); };
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  } catch {
    entry.state = "error"; redraw?.();
  }
  if (cache.size > 40) cache.delete(cache.keys().next().value);
}

/* Картинка карты блока для draw.js: { state, img, from } — from — блок, для которого нарисована показанная картинка
   (пока новая грузится, показывается прежняя на своём месте). Нет места или масштаба — state "none". */
export function mapImage(b, redraw) {
  if (!b.center || !(b.scale > 0)) return { state: "none" };
  const k = key(b);
  let e = cache.get(k);
  if (!e) { e = { state: "loading", from: { center: b.center, scale: b.scale, w: b.w, h: b.h } }; cache.set(k, e); load(k, b, e, redraw); }
  if (e.state === "ready") return e;
  const prev = last.get(b.id);
  return prev ? { ...prev, state: e.state === "error" ? "error" : "loading" } : { state: e.state };
}

/* «Как на карте»: середина и масштаб окна «Карта»; окно ещё не открывалось — место проекта. */
export function here() {
  if (viewNow.center) return { center: viewNow.center.map(x => +x.toFixed(7)), scale: scale.value };
  const c = project.view?.center;
  return Array.isArray(c) && c.length === 2 ? { center: c.map(Number), scale: 0 } : null;
}

const mapsOf = sheet => Object.fromEntries(sheet.blocks.filter(b => b.kind === "map" && !b.hidden).map(b => [b.id, { layers: mapLayers(b) }]));
async function download(body, name) {
  const r = await fetch("/api/print/layout", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error("PDF не собрался: " + r.status);
  const url = URL.createObjectURL(await r.blob()), a = document.createElement("a");
  a.href = url; a.download = `${(name || "лист").replace(/[\\/:*?"<>|]/g, "_")}.pdf`; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
  // пластины карт на Rust (layout_io._plated): блоки карт без единого закрашенного места — лист не готов
  const empty = (r.headers.get("X-Empty-Maps") || "").split(",").filter(Boolean);
  const titleOf = id => body.sheets ? body.sheets.find(x => x.sheet.blocks?.some(b => b.id === id))?.sheet.title || "" : body.sheet?.title || "";
  // подписи карт налезают друг на друга (layout_io.label_clashes): «id:пар»
  // подписи карт: налезают друг на друга (layout_io.label_clashes) и не поместились (print_io dropped): «id:сколько»
  const counts = h => (r.headers.get(h) || "").split(",").filter(Boolean).map(x => { const i = x.lastIndexOf(":"); return { id: x.slice(0, i), n: +x.slice(i + 1) || 0, title: titleOf(x.slice(0, i)) }; });
  return { empty, titles: empty.map(titleOf), clash: counts("X-Label-Clash"), drop: counts("X-Label-Drop") };
}
/* текст для строки состояния: лист собран, но карта без объектов или подписи налезают — выгрузка не молчит */
export const emptyNote = res => {
  const out = [];
  if (res?.empty?.length) out.push(`карта пустая (${res.empty.length}): ${[...new Set(res.titles.filter(Boolean))].join(", ") || "проверьте охват и слои блока"}`);
  const sum = l => [l.reduce((a, c) => a + c.n, 0), [...new Set(l.map(c => c.title).filter(Boolean))]];
  if (res?.clash?.length) { const [n, t] = sum(res.clash); out.push(`подписи налезают друг на друга (${n}${n >= 50 ? "+" : ""}${t.length ? ": " + t.join(", ") : ""})`); }
  if (res?.drop?.length) { const [n, t] = sum(res.drop); out.push(`не поместились подписи (${n}${t.length ? ": " + t.join(", ") : ""})`); }
  if (res?.clash?.length || res?.drop?.length) out.push("крупнее масштаб, меньше подписей или мельче шрифт");
  return out.length ? `PDF собран, но ${out.join("; ")}` : "";
};

/* Лист — в PDF той же печатью, что и альбом; page — его номер в списке листов (для штампа). */
export function printPdf(sheet, meta, page) {
  return download({ sheet, meta, maps: mapsOf(sheet), page }, sheet.title);
}

/* Все листы макета — одним PDF, листы пронумерованы в штампе по порядку. */
export function printAll(sheets, meta, name) {
  return download({ meta, sheets: sheets.map(sheet => ({ sheet, maps: mapsOf(sheet) })) }, name);
}

/* ---------- вид блока (#119) ---------- */
// виды проекта для списка «Вид» в свойствах блока карты; on — сколько блоков карты на всех листах стоят на виде, где — листы
export function views() {
  const use = {};
  (project.layouts || []).forEach(s => (s.blocks || []).forEach(b => {
    if (b.kind !== "map" || !b.view) return;
    const u = use[b.view] ||= { on: 0, sheets: [] }; u.on++;
    const t = s.title || "без названия"; if (!u.sheets.includes(t)) u.sheets.push(t);
  }));
  return project.views.map(v => ({ id: v.id, name: v.name, frame: v.frame || null, on: use[v.id]?.on || 0, sheets: use[v.id]?.sheets || [] }));
}
/* место и масштаб блоков с видом — по рамке вида; легенда «следует за видом» (b.follow) — строки из слоёв вида своей
   карты (b.map). Меняет лист на месте, → true, если что-то поменялось */
export function sync(sheet) {
  let changed = false;
  const blocks = sheet?.blocks || [];
  blocks.forEach(b => {
    if (b.kind !== "map" || !b.view) return;
    // ячейка атласа (autosheets.js): своя середина в заданном масштабе вида, рамка вида — вся сетка
    const r = b.cell?.center && b.cell.scale > 0 ? { center: b.cell.center, scale: b.cell.scale } : blockFromView(b, viewOf(b.view)); if (!r) return;
    if (JSON.stringify(r.center) !== JSON.stringify(b.center) || r.scale !== b.scale) { Object.assign(b, r); changed = true; }
  });
  blocks.forEach(b => {
    if (b.kind !== "legend" || !b.follow) return;
    const m = blocks.find(x => x.kind === "map" && x.id === b.map) || blocks.find(x => x.kind === "map"), items = legendItems(m?.view);
    if (JSON.stringify(items) !== JSON.stringify(b.items)) { b.items = items; changed = true; }
  });
  return changed;
}
// «Сдвиг карты в рамке» на блоке с видом двигает рамку вида: меняются все листы с этим видом
export function frameTo(viewId, center) {
  const v = viewOf(viewId); if (!v?.frame) return false;
  v.frame = { ...v.frame, center: center.map(x => +(+x).toFixed(7)) }; return true;
}
// масштаб, заданный числом, на блоке с видом: рамка вида на карте меняет размер под блок (середина та же)
export function frameScale(viewId, b, scale) {
  const v = viewOf(viewId); if (!v?.frame) return false;
  v.frame = frameForScale(b, v.frame, scale); return true;
}
/* «Отдельный вид»: копия вида (слои, оформление, рамка) под одну карту листа — её рамку двигают, не трогая другие листы.
   → id новой копии */
export function ownView(viewId, sheetTitle) {
  const v = viewOf(viewId); if (!v) return "";
  const id = "v" + Date.now().toString(36) + Math.random().toString(36).slice(2, 5), base = `${v.name} · ${sheetTitle || "лист"}`;
  let name = base; for (let i = 2; project.views.some(x => x.name === name); i++) name = `${base} (${i})`;
  project.views.push({ ...JSON.parse(JSON.stringify(v)), id, name });
  return id;
}
/* Готовность листа к выгрузке (план 08.11, шаг 4): карта вида без рамки, в рамке нет ни одного объекта, легенда «за видом»
   пуста — замечание в строке листа (SheetEditor.vue, рядом с model.js problems), а не молча пустой лист */
export function ready(sheet) {
  const out = [], blocks = sheet?.blocks || [];
  blocks.forEach(b => {
    if (b.kind === "map" && b.view && !b.hidden) {
      const v = viewOf(b.view);
      if (!v) out.push({ id: b.id, text: "Карта: вида больше нет — выберите вид в свойствах" });
      else if (!v.frame) out.push({ id: b.id, text: `Карта: у вида «${v.name}» нет рамки на карте` });
      else if (b.center && b.scale > 0 && !mapLayers(b).length) out.push({ id: b.id, text: `Карта «${v.name}»: в рамке нет объектов — данные не загружены или слои вида скрыты` });
    }
    if (b.kind === "legend" && b.follow && !(b.items || []).length) out.push({ id: b.id, text: "Легенда пуста: в виде нет видимых слоёв с данными" });
  });
  return out;
}
