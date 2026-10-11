/* ГРАДО 2 · карта и печать для «Макета листа» (SheetPanel.vue → SheetEditor.vue, проп maps): берёт слои открытого
   проекта (store.js) в охвате блока карты, оформляет их так же, как окно «Карта» (symbology.js), и просит сервер
   нарисовать карту блока (/api/print/map_svg — тот же рендер, что печатает альбом) или весь лист в PDF
   (/api/print/layout, apps/grado2/layout_io.py). Цвет объекта — как у карты (symbology.js symbolOf: единое, категории,
   диапазоны, правила; ЛГР — красной линией). Картинки карт кэшируются по месту, масштабу, размеру и слоям.
   Блок с видом (b.view, #119) берёт слои и оформление вида, а место и масштаб — из рамки вида (viewframes.js blockFromView;
   sync() правит блоки листа, frameTo() двигает рамку вида при «Сдвиге карты в рамке»). */
import { project, shown, scale, viewNow } from "../store.js";
import { breaks, fullStyle, legendItems as classesOf, swatchColor, symbolOf } from "../symbology.js";
import { blockBounds } from "../sheet/model.js";
import { blockFromView } from "../viewframes.js";

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
  if (!v) { v = (fc.features || []).filter(f => f?.geometry).map(f => ({ g: f.geometry, b: bboxOf(f.geometry) })); boxes.set(fc, v); }
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
    const s = fullStyle(style), feats = [], br = s.mode === "grad" ? breaks(s, fc) : null;
    indexed(fc).forEach(({ g, b: fb, p }) => {
      if (!meets(fb, box)) return;
      if (s.mode === "lgr") { feats.push({ g, stroke: "#d7191c", w: Math.max(s.width, 1), a: 1 }); return; }
      const k = symbolOf(s, f => p[f], br);
      if (k.hide) return;
      if (l.geom === "line") feats.push({ g, stroke: k.fill, w: s.width, a: 1 });          // у линии цвет — fill, как на карте
      else if (l.geom === "point") feats.push({ g, fill: k.fill, stroke: s.stroke, w: (2 + s.width * 2) * PX_PT });
      else feats.push({ g, fill: k.fill, stroke: s.width > 0 ? s.stroke : null, w: s.width, a: s.opacity });
    });
    if (feats.length) out.push({ title: l.title || l.key, features: feats });
  });
  return out;
}

/* Строки легенды из видимых слоёв проекта, сверху вниз, как в окне «Слои»; у слоя с категориями, диапазонами или
   правилами — строка на каждый класс. */
export function legendItems(viewId) {
  const out = [];
  layersOf(viewId).filter(({ l }) => project.data[l.key]).forEach(({ l, style }) => {
    const s = fullStyle(style), t = l.title || l.key, line = l.geom === "line" || s.mode === "lgr";
    const row = (title, c) => out.push(line ? { t: title, s: "line", c } : { t: title, s: "fill", c: s.stroke, f: c });
    const cls = s.mode === "single" || s.mode === "lgr" ? [] : classesOf(s, project.data[l.key].fc).filter(x => !x.off);
    if (cls.length) cls.forEach(x => row(`${t}: ${x.v === "" ? "без значения" : x.v}`, x.c));
    else row(t, swatchColor(s));
  });
  return out;
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
}

/* Лист — в PDF той же печатью, что и альбом; page — его номер в списке листов (для штампа). */
export function printPdf(sheet, meta, page) {
  return download({ sheet, meta, maps: mapsOf(sheet), page }, sheet.title);
}

/* Все листы макета — одним PDF, листы пронумерованы в штампе по порядку. */
export function printAll(sheets, meta, name) {
  return download({ meta, sheets: sheets.map(sheet => ({ sheet, maps: mapsOf(sheet) })) }, name);
}

/* ---------- вид блока (#119) ---------- */
// виды проекта для списка «Вид» в свойствах блока карты
export const views = () => project.views.map(v => ({ id: v.id, name: v.name, frame: v.frame || null }));
/* место и масштаб блоков с видом — по рамке вида; меняет лист на месте, → true, если что-то поменялось */
export function sync(sheet) {
  let changed = false;
  (sheet?.blocks || []).forEach(b => {
    if (b.kind !== "map" || !b.view) return;
    const r = blockFromView(b, viewOf(b.view)); if (!r) return;
    if (JSON.stringify(r.center) !== JSON.stringify(b.center) || r.scale !== b.scale) { Object.assign(b, r); changed = true; }
  });
  return changed;
}
// «Сдвиг карты в рамке» на блоке с видом двигает рамку вида: меняются все листы с этим видом
export function frameTo(viewId, center) {
  const v = viewOf(viewId); if (!v?.frame) return false;
  v.frame = { ...v.frame, center: center.map(x => +(+x).toFixed(7)) }; return true;
}
