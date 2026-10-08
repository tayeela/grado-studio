/* ГРАДО 2 · карта и печать для «Макета листа» (SheetPanel.vue → SheetEditor.vue, проп maps): берёт слои открытого
   проекта (store.js) в охвате блока карты, оформляет их так же, как окно «Карта» (styleOf), и просит сервер
   нарисовать карту блока (/api/print/map_svg — тот же рендер, что печатает альбом) или весь лист в PDF
   (/api/print/layout, apps/grado2/layout_io.py). Картинки карт кэшируются по месту, масштабу, размеру и слоям. */
import { project, styleOf, shown, mapView } from "../store.js";
import { blockBounds } from "../sheet/model.js";

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

/* Слои карты блока для печати: видимые, снизу вверх (как рисует карта), только объекты в охвате блока. */
export function mapLayers(b) {
  if (!b.center || !(b.scale > 0)) return [];
  const box = blockBounds(b), out = [];
  [...project.layers].reverse().forEach(l => {
    const fc = project.data[l.key]?.fc;
    if (!fc || !shown(l)) return;
    const s = styleOf(l), feats = [];
    indexed(fc).forEach(({ g, b: fb }) => {
      if (!meets(fb, box)) return;
      if (l.geom === "line") feats.push({ g, stroke: s.fill, w: s.width, a: 1 });          // у линии цвет — fill, как на карте
      else if (l.geom === "point") feats.push({ g, fill: s.fill, stroke: s.stroke, w: (2 + s.width * 2) * PX_PT });
      else feats.push({ g, fill: s.fill, stroke: s.width > 0 ? s.stroke : null, w: s.width, a: s.opacity });
    });
    if (feats.length) out.push({ title: l.title || l.key, features: feats });
  });
  return out;
}

/* Строки легенды из видимых слоёв проекта, сверху вниз, как в окне «Слои». */
export function legendItems() {
  return project.layers.filter(l => shown(l) && project.data[l.key]).map(l => {
    const s = styleOf(l), t = l.title || l.key;
    if (l.geom === "line") return { t, s: "line", c: s.fill };
    return { t, s: "fill", c: s.stroke, f: s.fill };
  });
}

/* ---------- картинки карт блоков ---------- */
const cache = new Map();                    // ключ → { state: "loading" | "ready" | "error", img, at }
const last = new Map();                     // id блока → последняя готовая картинка (показывается, пока грузится новая)
let dataTick = 0, lastData = null;
const sig = () => JSON.stringify([project.layers.map(l => [l.key, shown(l), l.style]), dataTick]);

function key(b) {
  if (project.data !== lastData) { lastData = project.data; dataTick++; }
  return JSON.stringify([b.w, b.h, b.center, b.scale, b.basemap || "none", sig()]);
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
  if (mapView.center) return { center: mapView.center, scale: mapView.scale };
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
