/* ГРАДО 2 · совместная работа на карте нового интерфейса (как наложения web/hub.js): метки комментариев с номерами
   (выбранная — крупнее, решённые — серые, черновик — пунктиром), указатели и выбор других участников их цветом,
   указатель мыши — другим участникам. Щелчок по метке выбирает комментарий; в режиме «Комментарий на карте» щелчок
   ставит черновик. Подключает MapPanel: attachHub(map) → функция отключения; hubClick(e) — щелчок забрал комментарий. */
import { watch } from "vue";
import Feature from "ol/Feature.js";
import Point from "ol/geom/Point.js";
import VectorLayer from "ol/layer/Vector.js";
import VectorSource from "ol/source/Vector.js";
import { getCenter } from "ol/extent.js";
import { fromLonLat, toLonLat } from "ol/proj.js";
import { Circle, Fill, RegularShape, Stroke, Style, Text } from "ol/style.js";
import { hub, ink, pres, safeColor, sortedComments } from "./hub.js";
import { dataRev } from "./edit.js";
import { featureOf } from "./features.js";
import { gjFormat } from "./maplayers.js";
import { winApi } from "./store.js";

const rgba = (c, a) => { const n = parseInt(c.slice(1), 16); return `rgba(${n >> 16},${n >> 8 & 255},${n & 255},${a})`; };
const feat = (g, p) => { const f = new Feature(g); f.setProperties(p); return f; };
function geomPoint(g) {
  if (!g) return null; const t = g.getType();
  if (t === "Point") return g.getCoordinates().slice(0, 2);
  if (t === "Polygon") return g.getInteriorPoint().getCoordinates().slice(0, 2);
  return getCenter(g.getExtent());
}
/* объект слоя по `_uid` — геометрия в проекции карты */
function geomOf(layer, uid) { const gj = featureOf(layer, uid); if (!gj) return null; try { return gjFormat.readGeometry(gj.geometry); } catch { return null; } }
export function anchorPoint(a) {
  if (a?.lonlat) return fromLonLat(a.lonlat);
  if (a?.uid) return geomPoint(geomOf(a.layer, a.uid));
  return null;
}
const PSTY = new Map();
function pinStyle(f) {
  const draft = f.get("draft"), res = f.get("resolved"), sel = f.get("sel"), k = [draft, res, sel, f.get("n")].join();
  let s = PSTY.get(k); if (s) return s;
  const col = draft ? "#2f6fc4" : res ? "#8a8d91" : "#d9822b", z = sel || draft ? 3 : 2;
  s = [new Style({ image: new Circle({ radius: 3, fill: new Fill({ color: col }), stroke: new Stroke({ color: "#fff", width: 1 }) }), zIndex: z }),
    new Style({ image: new Circle({ radius: sel ? 13 : 11, displacement: [0, 14], fill: new Fill({ color: draft ? "rgba(47,111,196,.18)" : col }), stroke: new Stroke({ color: sel ? "#1d1d1f" : draft ? col : "#fff", width: 2, lineDash: draft ? [4, 3] : undefined }) }),
      text: draft ? undefined : new Text({ text: String(f.get("n")), offsetY: -14, font: "600 11px system-ui,sans-serif", fill: new Fill({ color: "#fff" }) }), zIndex: z })];
  PSTY.set(k, s); return s;
}
function presStyle(f) {
  const c = f.get("color");
  if (f.get("kind") === "cursor") return [new Style({ image: new RegularShape({ points: 3, radius: 8, displacement: [0, -8], fill: new Fill({ color: c }), stroke: new Stroke({ color: "#fff", width: 1.5 }) }),
    text: new Text({ text: f.get("name"), offsetX: 10, offsetY: 22, textAlign: "left", font: "600 11px system-ui,sans-serif", fill: new Fill({ color: ink(c) }), backgroundFill: new Fill({ color: c }), padding: [1, 4, 1, 4] }) })];
  const t = f.getGeometry().getType();
  if (/Point/.test(t)) return new Style({ image: new Circle({ radius: 10, stroke: new Stroke({ color: c, width: 3 }), fill: new Fill({ color: rgba(c, .15) }) }) });
  if (/Line/.test(t)) return new Style({ stroke: new Stroke({ color: c, width: 5 }) });
  return new Style({ stroke: new Stroke({ color: c, width: 3, lineDash: [8, 4] }), fill: new Fill({ color: rgba(c, .14) }) });
}

let MAP = null;
const comSrc = new VectorSource(), presSrc = new VectorSource();
function paintPins() {
  const fs = [];
  sortedComments().forEach((c, i) => { const pt = anchorPoint(c.anchor); if (pt) fs.push(feat(new Point(pt), { cid: c.id, n: i + 1, resolved: !!c.resolved, sel: c.id === hub.cSel })); });
  const d = hub.draft && (hub.draft.pt || anchorPoint(hub.draft.anchor)); if (d) fs.push(feat(new Point(d), { draft: true }));
  comSrc.clear(true); comSrc.addFeatures(fs);
}
function paintPresence() {
  const fs = [];
  for (const u of hub.others) {
    const col = safeColor(u.color);
    if (Array.isArray(u.cursor) && isFinite(u.cursor[0]) && isFinite(u.cursor[1])) fs.push(feat(new Point(fromLonLat(u.cursor)), { kind: "cursor", color: col, name: u.name || u.login }));
    (u.sel || []).slice(0, 200).forEach(uid => { const g = geomOf(u.layer, uid); if (g) fs.push(feat(g, { kind: "sel", color: col })); });
  }
  presSrc.clear(true); presSrc.addFeatures(fs);
}
/* перейти к метке комментария */
export function flyTo(pt) {
  if (!MAP) return;
  if (!pt) { return false; }
  const v = MAP.getView(); v.animate({ center: pt, zoom: Math.max(v.getZoom() || 0, 17), duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 350 });
  return true;
}
/* щелчок по карте: метка — выбрать комментарий; режим «Комментарий на карте» — черновик в точке. true — щелчок забран */
export function hubClick(e) {
  if (!MAP || !hub.pid) return false;
  let cid = null;
  MAP.forEachFeatureAtPixel(e.pixel, f => { if (f.get("cid")) { cid = f.get("cid"); return true; } }, { layerFilter: l => !!l.get("hubPins"), hitTolerance: 6 });
  if (cid) { hub.cSel = cid; winApi.open("comments"); return true; }
  if (!hub.cMode) return false;
  hub.draft = { anchor: { lonlat: toLonLat(e.coordinate) }, pt: e.coordinate }; hub.cMode = false; winApi.open("comments");
  return true;
}
export function attachHub(map) {
  MAP = map;
  const p = new VectorLayer({ source: presSrc, zIndex: 910, style: presStyle, updateWhileInteracting: true, updateWhileAnimating: true });
  const c = new VectorLayer({ source: comSrc, zIndex: 920, style: pinStyle, updateWhileInteracting: true, updateWhileAnimating: true, properties: { hubPins: true } });
  map.addLayer(p); map.addLayer(c);
  const onMove = e => { const ll = toLonLat(e.coordinate); pres.cursor = [+ll[0].toFixed(6), +ll[1].toFixed(6)]; pres.dirty = true; };
  const onLeave = () => { pres.cursor = null; pres.dirty = true; };
  map.on("pointermove", onMove); map.getViewport().addEventListener("mouseleave", onLeave);
  const stop = [watch(() => [hub.comments, hub.cSel, hub.draft, dataRev.value], paintPins, { deep: true }), watch(() => [hub.others, dataRev.value], paintPresence, { deep: true }),
    watch(() => hub.cMode, on => map.getTargetElement()?.classList.toggle("cmode", on))];
  paintPins(); paintPresence();
  return () => { stop.forEach(s => s()); map.un("pointermove", onMove); map.getViewport().removeEventListener("mouseleave", onLeave); map.removeLayer(p); map.removeLayer(c); MAP = null; };
}
