/* ГРАДО 2 · черчение как в AutoCAD в новом интерфейсе — перенос web/cad.js рабочей страницы: те же команды и псевдонимы
   (L, PL, C, A, REC, POL, PO, M, CO, RO, SC, MI, O, TR, EX, F, BR, J, X, E, DI, AA, BO и другие), динамический ввод у курсора
   (длина, длина<угол, @dx;dy, X;Y в МСК, буквы параметров), режимы ПРИВЯЗКА (F3), ОТСЛЕЖ (F11), ПОЛЯР (F10), ОРТО (F8),
   ДИН (F12), ТОПО, ручки на вершинах выбранного, история команд (F2). Размеры, углы и площади — в метрах МСК (web/cadcore.js).
   Связь с проектом другая, чем в рабочей странице: объекты слоёв — объекты карты окна «Карта» (maplayers.js, у каждого
   ссылка gj на запись в файле); правка пишет в слой новый fc, где новые записи только у изменённых объектов (writeBack),
   отмена — общая по снимкам (edit.js); выбор — features.js по `_uid`. Лента и строка состояния — Vue (App.vue, CadModes.vue)
   по `cad` (реактивное: идущая команда, режимы) и `cadApi` (запуск, отмена, переключение режимов).
   attachCad(map, {vec, sync, terrSrc}) вызывает MapPanel при создании карты; возвращает функцию отключения. */
import { reactive, watch } from "vue";
import Feature from "ol/Feature.js";
import Overlay from "ol/Overlay.js";
import * as extent from "ol/extent.js";
import { LineString, MultiLineString, MultiPolygon, Point, Polygon } from "ol/geom.js";
import Interaction from "ol/interaction/Interaction.js";
import VectorLayer from "ol/layer/Vector.js";
import VectorSource from "ol/source/Vector.js";
import { fromLonLat, toLonLat } from "ol/proj.js";
import { Circle, Fill, RegularShape, Stroke, Style, Text } from "ol/style.js";
import * as turf from "@turf/turf";
import * as cgModule from "../../web/cadcore.js";
import * as mskModule from "../../web/msk.js";
import { currentId, project, scale, shown } from "./store.js";
import { dataRev, lyr, newLayer, touchData } from "./edit.js";
import { fieldsOfFeatures, sel, setSel as setSelUid } from "./features.js";
import { diff, fmt, buf, inter, unionAll } from "./geom.js";
import { setTerritory, terrArea, terrTool } from "./data.js";
import { gjFormat } from "./maplayers.js";
import { notice } from "./project.js";
import { fullStyle, symbolOf } from "./symbology.js";
import icons from "./cadicons.svg?raw";

/* web/cadcore.js и web/msk.js — общие файлы с рабочей страницей: в сборке Vite они модули CommonJS (module.exports) */
const G = cgModule.default || cgModule, MSK = globalThis.MSK || mskModule.default || mskModule;
const ol = { Feature, Overlay, extent, geom: { LineString, MultiLineString, MultiPolygon, Point, Polygon }, interaction: { Interaction },
  layer: { Vector: VectorLayer }, source: { Vector: VectorSource }, proj: { fromLonLat, toLonLat }, style: { Circle, Fill, RegularShape, Stroke, Style, Text } };

/* Для ленты и строки состояния: cmd — идущая команда (id), st — копия режимов; ready — черчение подключено к карте. */
export const cad = reactive({ cmd: null, st: { modes: {} }, ready: false });
export const cadApi = {};              // start(id), cancel(), toggle(k), setOpt(k, v), setMode(k, v), CMDS, ALIAS, HELP, MODES — после attachCad
/* Группы ленты и меню — как в рабочей странице (web/cad.js fillRibbon). */
export const RIBBON = {
  draw: ["line", "pline", "circle", "arc", "ellipse", "rect", "polygon", "point"],
  anno: ["hatch", "dim", "text"],
  modify: ["move", "copy", "rotate", "mirror", "scale", "offset", "trim", "extend", "fillet", "array", "stretch"],
  more: ["chamfer", "break", "join", "explode", "lengthen", "arrayedit", "erase"],
  gis: ["split", "merge", "subtract", "delring", "buffer", "simplify", "reverse", "align", "matchprop", "divide", "measure", "similar", "qselect", "laymcur", "convert", "bpoly"],
  measure: ["dist", "area"], terr: ["terr"],
};
/* значки команд (символы ci-<команда>) — один раз в документ */
export function cadIcons() {
  if (document.getElementById("ci-line")) return;
  const box = document.createElement("div"); box.hidden = true; box.innerHTML = icons.replace(/<!--[\s\S]*?-->/, ""); document.body.prepend(box);
}

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const MOD = /Mac|iP(hone|ad)/.test(navigator.platform) ? "⌘" : "Ctrl";
const MEM = {};                        // последние числа команд (подобие, сопряжение, фаска, буфер…) за сеанс
const UIS = { tool: "select" };
const typing = e => e.composedPath().some(n => n instanceof HTMLElement && (n.matches("input, textarea, select, [contenteditable], wa-input, wa-select, wa-textarea, wa-dialog, wa-dropdown, [role=menu], [role=listbox], .tabulator") || n.classList.contains("graphp")));   // список слоёв и таблица — свои клавиши (#30)
const propsOf = f => { const p = { ...f.getProperties() }; delete p[f.getGeometryName()]; return p; };
const newUid = () => Array.from(crypto.getRandomValues(new Uint8Array(6)), b => b.toString(16).padStart(2, "0")).join("");
const fieldsAll = key => { const fs = project.data[key]?.fc?.features || []; return [...new Set(fs.slice(0, 500).flatMap(f => Object.keys(f.properties || {})))].filter(k => k !== "geometry"); };
const fieldsOfKey = key => fieldsOfFeatures((project.data[key]?.fc?.features || []).slice(0, 500));
const outOfScale = l => { const s = l.style || {}, den = scale.value; return !!den && ((!!s.maxDen && den > s.maxDen) || (!!s.minDen && den < s.minDen)); };
// скрытые категорией или правилом стиля объекты не выбираются (как web/layers.js visibleIn)
const visibleIn = (l, f) => !["cat", "rules"].includes(l.style?.mode) || !symbolOf(fullStyle(l.style), k => f.get(k), []).hide;
const setCurrentQuiet = key => { currentId.value = key; };
/* сообщения черчения — только в командной строке над картой (аудит 09.10.2026: строка состояния их не повторяет);
   пока черчение не подключено к карте — в строку состояния. cadSay заменяет attachCad. */
let cadSay = msg => { notice.value = msg; };
const toast = msg => cadSay(msg), syncStatus = () => { if (notice.value === "Esc — прервать") notice.value = ""; }, restyle = () => {};
let layerSwitch = null;                // слой рисования сменился сам (текущий другого вида): итог команды говорит об этом
const terrLocked = () => false;
const ANNO_TITLES = [["Надписи", "point"], ["Размеры", "line"], ["Штриховка", "poly"]];
const isAnno = l => ANNO_TITLES.some(([t, g]) => l.title === t && l.geom === g);
function createLayerQuiet(name, geom) { const key = newLayer(name, geom); return lyr(key); }
// слой для рисования: текущий, если геометрия подходит; иначе свой слой той же геометрии; иначе новый (web/layers.js targetLayer)
function targetLayer(geom) {
  const cur = lyr(currentId.value); if (cur?.geom === geom) return cur;
  const own = project.layers.find(l => l.geom === geom && l.key.startsWith("user:") && !isAnno(l));
  if (own) { layerSwitch = { from: cur, to: own.title }; setCurrentQuiet(own.key); return own; }
  const l = createLayerQuiet({ point: "Точки", line: "Линии", poly: "Полигоны" }[geom], geom);
  layerSwitch = { from: cur, to: l.title, made: true };
  toast(`Создан слой «${l.title}»: новые объекты попадут в него. Переименовать — двойной щелчок в списке слоёв.`); return l;
}
const DRAWS = new Set(["line", "pline", "circle", "arc", "ellipse", "rect", "polygon", "point"]);
function revealCurLayer(name) { const l = lyr(currentId.value); if (DRAWS.has(name) && l && !shown(l)) { l.visible = true; const g = project.groups.find(x => x.id === l.group); if (g) g.visible = true; } }
/* геометрия под слой другого вида (web/layers.js geomFor): полигон в слое линий — контуры замкнутыми линиями, замкнутая
   линия в слое полигонов — полигоном; точки только в слой точек; null — не переносится */
function geomFor(g, geom) {
  const t = g.getType(), closedRing = r => r.length > 3 && r[0][0] === r[r.length - 1][0] && r[0][1] === r[r.length - 1][1];
  if (geom === "point") return /Point/.test(t) ? g.clone() : null;
  if (/Point/.test(t)) return null;
  if (geom === "line") { if (/Line/.test(t)) return g.clone(); const rings = t === "Polygon" ? g.getCoordinates() : g.getCoordinates().flat();
    return rings.length === 1 ? new LineString(rings[0]) : new MultiLineString(rings); }
  if (/Polygon/.test(t)) return g.clone();
  const lines = (t === "LineString" ? [g.getCoordinates()] : g.getCoordinates()).filter(closedRing);
  return !lines.length ? null : lines.length === 1 ? new Polygon([lines[0]]) : new MultiPolygon(lines.map(r => [r]));
}

const toM = c => MSK.fromWgs(toLonLat(c)), fromM = w => fromLonLat(MSK.toWgs(w));

export function attachCad(mMain, host) {
const GJ = gjFormat, sharedView = mMain.getView(), terrSrc = host.terrSrc;
// слой, только что заведённый командой, появляется на карте сразу, а не при следующем обновлении окна «Карта»
const layerSrc = new Proxy({}, { get: (_, k) => { if (!host.vec[k] && lyr(k)) host.sync(); return host.vec[k]?.getSource(); } });
/* Запись слоя после правки: объекты карты, у которых правилась геометрия или поля (ревизия OpenLayers сменилась) или
   которых не было, становятся новыми записями fc; остальные записи — те же объекты. Удалённые из источника — уходят.
   Исходная выгрузка сохраняется при первой правке (как features.js editFeatures). */
function writeBack(key) {
  const d = project.data[key], src = layerSrc[key]; if (!d || !src) return;
  const seen = new Set(), features = src.getFeatures().map(f => {
    if (f.gj && f.gjRev === f.getRevision() && !seen.has(f.gj.properties?._uid)) { seen.add(f.gj.properties._uid); return f.gj; }
    let u = f.get("_uid"); if (!u || seen.has(u)) f.set("_uid", u = newUid(), true); seen.add(u);
    const gj = GJ.writeFeatureObject(f); f.gj = gj; f.gjRev = f.getRevision(); return gj;
  });
  const orig = typeof d.original === "object" && d.original ? { original: d.original } : d.original === "=fc" ? { original: d.fc } : {};
  project.data[key] = { ...d, fc: { ...d.fc, features }, ...orig };
  touchData();
}
/* выбор: в features.js — {key, uid}; здесь, как в рабочей странице, — {key, f} с объектом карты */
function olOf(key, uid) { const src = layerSrc[key]; if (!src) return null; for (const f of src.getFeatures()) if (f.gj?.properties?._uid === uid) return f; return null; }
const selNow = () => { const by = new Map(); return sel.map(s => {
  let m = by.get(s.key); if (!m) { m = new Map(); layerSrc[s.key]?.getFeatures().forEach(f => f.gj && m.set(f.gj.properties?._uid, f)); by.set(s.key, m); }
  const f = m.get(s.uid); return f ? { key: s.key, f } : null; }).filter(Boolean); };
function setSel(list) {
  setSelUid(list.map(({ key, f }) => { if (!f.gj) return null; return { key, uid: f.gj.properties?._uid }; }).filter(Boolean));
}
// щелчок выбирает только объекты текущего слоя (владелец 27.10.2026); нет текущего слоя — любой видимый
function hitAt(pixel) {
  let hit = null; const only = lyr(currentId.value) ? currentId.value : "";
  mMain.forEachFeatureAtPixel(pixel, (f, layer) => { const k = layer?.get("key"); if (!k || !lyr(k) || !f.gj) return; hit = { key: k, f }; return true; },
    { hitTolerance: 4, layerFilter: la => !!la.get("key") && la.getVisible() && (!only || la.get("key") === only) });
  return hit;
}
const mapReady = () => !!mMain.getSize()?.[0];
const measureSrc = new ol.source.Vector();
mMain.addLayer(new ol.layer.Vector({ source: measureSrc, zIndex: 120, style: f => [new Style({ fill: new Fill({ color: "rgba(224,138,0,.15)" }), stroke: new Stroke({ color: "#c46f00", width: 2 }) }),
  new Style({ text: new Text({ text: f.get("label") || "", font: "600 12px Onest, system-ui, sans-serif", fill: new Fill({ color: "#7a4200" }), stroke: new Stroke({ color: "#fff", width: 3 }), overflow: true, placement: "point" }) })] }));
const DEG = Math.PI / 180;

/* ---------- режимы ---------- */
const MODES = { end: "Конечная точка", mid: "Середина", cen: "Центр", quad: "Квадрант", int: "Пересечение", ext: "Продолжение", perp: "Нормаль", tan: "Касательная", par: "Параллельно", near: "Ближайшая" };
const ST = { topo: false, ortho: false, polar: true, polarInc: 45, polarRel: false, osnap: true, otrack: true, dyn: true, modes: { end: true, mid: true, cen: true, quad: false, int: true, ext: true, perp: true, tan: false, par: true, near: false } };
try { const s = JSON.parse(localStorage.getItem("grado2.cad") || "{}"); Object.assign(ST, { ...s, modes: { ...ST.modes, ...s.modes } }); } catch { }
const saveST = () => { try { localStorage.setItem("grado2.cad", JSON.stringify(ST)); } catch { } };

/* ---------- слой предпросмотра ---------- */
const prevSrc = new ol.source.Vector();
const ACC = "#1e6fd9", TRK = "#0b7a3d", MRK = "#e8590c";
const sRubber = new ol.style.Style({ stroke: new ol.style.Stroke({ color: ACC, width: 1.6 }), fill: new ol.style.Fill({ color: "rgba(30,111,217,0.08)" }) });
const sGhost = new ol.style.Style({ stroke: new ol.style.Stroke({ color: ACC, width: 1.4, lineDash: [6, 4] }), fill: new ol.style.Fill({ color: "rgba(30,111,217,0.05)" }), image: new ol.style.Circle({ radius: 4, stroke: new ol.style.Stroke({ color: ACC, width: 1.4 }) }) });
const sGone = new ol.style.Style({ stroke: new ol.style.Stroke({ color: "#b3261e", width: 2.5, lineDash: [5, 4] }) });
const sTrack = new ol.style.Style({ stroke: new ol.style.Stroke({ color: TRK, width: 1.1, lineDash: [2, 5] }) });
const sAcq = new ol.style.Style({ image: new ol.style.RegularShape({ points: 4, radius: 8, radius2: 0, stroke: new ol.style.Stroke({ color: TRK, width: 2.2 }) }) });
const sBase = new ol.style.Style({ image: new ol.style.Circle({ radius: 3, fill: new ol.style.Fill({ color: ACC }) }) });
const sPar = new ol.style.Style({ stroke: new ol.style.Stroke({ color: TRK, width: 3, lineDash: [3, 3] }) });
const MK = new ol.style.Stroke({ color: MRK, width: 2.2 });
const MARK = {
  end: new ol.style.RegularShape({ points: 4, radius: 10, angle: Math.PI / 4, stroke: MK }),
  mid: new ol.style.RegularShape({ points: 3, radius: 11, stroke: MK }),
  cen: new ol.style.Circle({ radius: 8, stroke: MK }),
  quad: new ol.style.RegularShape({ points: 4, radius: 10, stroke: MK }),
  int: new ol.style.RegularShape({ points: 4, radius: 11, radius2: 0, angle: Math.PI / 4, stroke: MK }),
  perp: new ol.style.RegularShape({ points: 4, radius: 9, angle: Math.PI / 4, stroke: MK, fill: new ol.style.Fill({ color: "rgba(232,89,12,0.25)" }) }),
  tan: new ol.style.Circle({ radius: 7, stroke: MK, fill: new ol.style.Fill({ color: "rgba(232,89,12,0.25)" }) }),
  near: new ol.style.RegularShape({ points: 4, radius: 9, radius2: 3, angle: Math.PI / 4, stroke: MK }),
  track: new ol.style.RegularShape({ points: 4, radius: 9, radius2: 0, angle: Math.PI / 4, stroke: new ol.style.Stroke({ color: TRK, width: 2.2 }) }) };
const KIND = { end: "конечная точка", mid: "середина", cen: "центр", quad: "квадрант", int: "пересечение", ext: "продолжение", perp: "нормаль", tan: "касательная", near: "ближайшая", track: "отслеживание", track2: "пересечение линий отслеживания", polar: "полярное", ortho: "орто", par: "параллельно" };
const prevLayer = new ol.layer.Vector({ source: prevSrc, zIndex: 140, updateWhileInteracting: true, updateWhileAnimating: true,
  style: f => ({ rubber: sRubber, ghost: sGhost, gone: sGone, track: sTrack, acq: sAcq, base: sBase, parseg: sPar })[f.get("k")] || new ol.style.Style({ image: MARK[f.get("k")] || MARK.end }) });
mMain.addLayer(prevLayer);
const fLine = (ws, k) => new ol.Feature({ geometry: new ol.geom.LineString(ws.map(fromM)), k });
const fPoly = (ring, k) => new ol.Feature({ geometry: new ol.geom.Polygon([ring.map(fromM)]), k });
const fPt = (w, k) => new ol.Feature({ geometry: new ol.geom.Point(fromM(w)), k });

/* ---------- ручки выбранных объектов, как в AutoCAD: квадраты на вершинах, треугольники на серединах сторон ---------- */
const gripSrc = new ol.source.Vector();
const GF = new ol.style.Fill({ color: ACC }), GS = new ol.style.Stroke({ color: "#ffffff", width: 1.2 });
const sGrip = new ol.style.Style({ image: new ol.style.RegularShape({ points: 4, radius: 6, angle: Math.PI / 4, fill: GF, stroke: GS }) });
const sGripMid = new ol.style.Style({ image: new ol.style.RegularShape({ points: 3, radius: 5.5, fill: GF, stroke: GS }) });
const sGripHover = new ol.style.Style({ image: new ol.style.RegularShape({ points: 4, radius: 7, angle: Math.PI / 4, fill: new ol.style.Fill({ color: "#e8590c" }), stroke: GS }) });
mMain.addLayer(new ol.layer.Vector({ source: gripSrc, zIndex: 136, style: f => f.get("hover") ? sGripHover : f.get("mid") ? sGripMid : sGrip }));
// обход координат геометрии с путями: путь — индексы в getCoordinates() до вершины
function vertices(g) {
  const out = [], walk = (c, path) => { if (typeof c[0] === "number") { out.push({ c, path }); return; } c.forEach((x, i) => walk(x, [...path, i])); };
  walk(g.getCoordinates(), []); return out;
}
const MAXGRIPS = 3000;
let gripCut = false;                  // выбор больше MAXGRIPS вершин: ручки не показаны, строка состояния говорит об этом
function syncGrips() {
  gripSrc.clear(true); gripCut = false;
  const terrF = null;                  // ручки границы — у инструмента «Изменить границу» окна «Данные»
  if (CMD || UIS.tool !== "select" || (!sel.length && !terrF)) return;
  const fs = [];
  for (const { key, f } of terrF ? [{ key: "@terr", f: terrF }] : selNow()) {
    const g = f.getGeometry(); if (!g) continue;
    const vs = vertices(g), byRing = new Map();
    vs.forEach(v => { const r = v.path.slice(0, -1).join(","); if (!byRing.has(r)) byRing.set(r, []); byRing.get(r).push(v); });
    for (const ring of byRing.values()) {
      const cl = ring.length > 2 && G.same(ring[0].c, ring[ring.length - 1].c, 1e-9), list = cl ? ring.slice(0, -1) : ring;
      list.forEach(v => fs.push(new ol.Feature({ geometry: new ol.geom.Point(v.c), key, f, path: v.path, closed: cl, n: list.length })));
      if (ring.length > 1 && !f.get("_cad")) for (let i = 0; i + 1 < ring.length; i++) { const a = ring[i].c, b = ring[i + 1].c; fs.push(new ol.Feature({ geometry: new ol.geom.Point([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]), key, f, path: ring[i + 1].path, mid: true })); }
    }
    if (fs.length > MAXGRIPS) { gripCut = true; return; }
  }
  gripSrc.addFeatures(fs);
}
function gripAt(px) {
  let best = null;
  gripSrc.forEachFeature(g => { const q = mMain.getPixelFromCoordinate(g.getGeometry().getCoordinates()), d = Math.hypot(q[0] - px[0], q[1] - px[1]); if (d <= 8 && (!best || d < best.d - 0.5 || (Math.abs(d - best.d) <= 0.5 && best.g.get("mid") && !g.get("mid")))) best = { g, d }; });
  return best?.g || null;
}
let hoverGrip = null;

/* ---------- кандидаты привязки у курсора ---------- */
function chainsOf(g) {
  const t = g.getType(), c = g.getCoordinates();
  return t === "Point" ? [[c]] : t === "MultiPoint" ? c.map(p => [p]) : t === "LineString" ? [c] : t === "MultiLineString" || t === "Polygon" ? c : t === "MultiPolygon" ? c.flat() : [];
}
const inSweep = (a, arc) => G.norm2pi(arc.sw >= 0 ? a - arc.a0 : arc.a0 - a) <= Math.abs(arc.sw) + 1e-9;
function gather(c, tolMap) {
  const ext = [c[0] - tolMap, c[1] - tolMap, c[0] + tolMap, c[1] + tolMap], memo = new Map();
  const M = p => { const k = p[0] + "," + p[1]; let v = memo.get(k); if (!v) { v = toM(p); memo.set(k, v); } return v; };
  const inExt = p => p[0] >= ext[0] && p[0] <= ext[2] && p[1] >= ext[1] && p[1] <= ext[3];
  const segBox = (a, b) => Math.max(a[0], b[0]) >= ext[0] && Math.min(a[0], b[0]) <= ext[2] && Math.max(a[1], b[1]) >= ext[1] && Math.min(a[1], b[1]) <= ext[3];
  const pts = [], segs = [], curves = [];
  const addChains = (chains, curve) => chains.forEach(ch => {
    const cl = ch.length > 2 && ch[0][0] === ch[ch.length - 1][0] && ch[0][1] === ch[ch.length - 1][1];
    ch.forEach((a, i) => {
      if (inExt(a) && (!curve || (!cl && (i === 0 || i === ch.length - 1)))) {
        const nb = ch.length > 1 && !cl ? (i === 0 ? ch[1] : i === ch.length - 1 ? ch[i - 1] : null) : null;
        pts.push({ w: M(a), k: "end", dir: nb ? G.unit(G.sub(M(a), M(nb))) : null });
      }
      const b = ch[i + 1]; if (!b || !segBox(a, b)) return;
      const A = M(a), B = M(b); segs.push({ a: A, b: B });
      if (!curve) pts.push({ w: [(A[0] + B[0]) / 2, (A[1] + B[1]) / 2], k: "mid" });
    });
  });
  let n = 0;
  for (const l of project.layers) {
    if (!shown(l) || outOfScale(l) || !layerSrc[l.key]) continue;
    layerSrc[l.key].forEachFeatureInExtent(ext, f => {
      if (++n > 300) return true;
      const cad = f.get("_cad");
      if (cad?.c) { curves.push(cad); pts.push({ w: cad.c, k: "cen" }); for (let q = 0; q < 4; q++) { const a = q * Math.PI / 2; if (cad.t === "circle" || inSweep(a, cad)) pts.push({ w: G.polar(cad.c, a, cad.r), k: "quad" }); } }
      addChains(chainsOf(f.getGeometry()), !!cad?.c);
    });
  }
  terrSrc.forEachFeatureInExtent(ext, f => addChains(chainsOf(f.getGeometry()), false));     // граница территории: вершины, середины и стороны
  if (CMD?.own) CMD.own().forEach(ch => { if (ch.length) addChains([ch.map(fromM)], false); });
  return { pts, segs, curves };
}

/* ---------- объектное отслеживание ---------- */
const ACQ = [];                       // захваченные точки {w, dir}: от них идут линии выравнивания и продолжения
let hover = null;
function acquireTick(s) {
  if (!ST.otrack || !["end", "mid", "cen", "int", "quad"].includes(s.k)) { hover = null; return; }
  if (hover && G.same(hover.w, s.w, 1e-6)) return;
  clearTimeout(hover?.timer); const h = { w: s.w, dir: s.dir }; hover = h; h.timer = setTimeout(() => acquire(h), 380);
}
function acquire(h) {
  if (hover !== h) return;
  const i = ACQ.findIndex(a => G.same(a.w, h.w, 1e-6));
  if (i >= 0) ACQ.splice(i, 1); else { ACQ.push({ w: h.w, dir: h.dir }); if (ACQ.length > 7) ACQ.shift(); }
  hover = null; refresh();
}
let PAR = null, parHover = null;          // захваченное направление для «Параллельно»: {a, b, d}
function parTick(seg) {
  if (!seg) { clearTimeout(parHover?.timer); parHover = null; return; }
  if (parHover && G.same(parHover.a, seg.a, 1e-6) && G.same(parHover.b, seg.b, 1e-6)) return;
  clearTimeout(parHover?.timer); const h = { a: seg.a, b: seg.b }; parHover = h;
  h.timer = setTimeout(() => { if (parHover !== h) return; const d = G.unit(G.sub(h.b, h.a)); PAR = PAR && G.same(PAR.a, h.a, 1e-6) ? null : { a: h.a, b: h.b, d }; parHover = null; refresh(); }, 400);
}
function trackLines(base, prev) {
  const out = [], angs = inc => { const a = []; for (let d = 0; d < 360; d += inc) a.push(d * DEG); return a; };
  if (ST.otrack) for (const a of ACQ) {
    for (const t of angs(ST.polar ? ST.polarInc : 90)) out.push({ o: a.w, d: [Math.cos(t), Math.sin(t)], k: "track", t });
    if (a.dir && ST.modes.ext) out.push({ o: a.w, d: a.dir, k: "ext" });
  }
  const rel = ST.polarRel && base && prev && G.dist(prev, base) > 1e-9 ? G.ang(prev, base) : 0;       // «от последнего отрезка», как в AutoCAD
  if (ST.polar && base) for (const t of angs(ST.polarInc)) out.push({ o: base, d: [Math.cos(t + rel), Math.sin(t + rel)], k: "polar", t });
  if (ST.osnap && ST.modes.par && PAR && base) out.push({ o: base, d: PAR.d, k: "par" }, { o: base, d: G.mul(PAR.d, -1), k: "par" });
  return out;
}

/* ---------- точка под курсором: привязка → отслеживание → ближайшая → орто ---------- */
let CUR = null;                       // {c: координаты карты под курсором, w: точка МСК, k: вид, dir, lines, mpp}
function resolve(c) {
  const res = sharedView.getResolution(), W = toM(c), mpp = G.dist(W, toM([c[0] + res * 20, c[1]])) / 20, tol = 10 * mpp;
  const base = CMD?.base?.() || null, pointMode = CMD?.need === "point", snapOn = ST.osnap && pointMode;
  let best = null, g = null;
  const cand = (w, k, pr, extra) => { const d = G.dist(w, W); if (d > tol) return; if (!best || pr < best.pr || (pr === best.pr && d < best.d)) best = { w, k, pr, d, ...extra }; };
  if (snapOn) {
    g = gather(c, 10 * res);
    for (const p of g.pts) if (ST.modes[p.k]) cand(p.w, p.k, p.k === "end" ? 1 : 2, { dir: p.dir });
    if (ST.modes.int) { const S = g.segs; for (let i = 0; i < S.length; i++) for (let j = i + 1; j < S.length; j++) { const x = G.inter(S[i].a, S[i].b, S[j].a, S[j].b); if (x && x.t > 1e-9 && x.t < 1 - 1e-9) cand(x.p, "int", 1); } }
    if (base) {
      if (ST.modes.perp) for (const s of g.segs) { const f = G.foot(base, s.a, s.b, false), d2 = G.dot(G.sub(s.b, s.a), G.sub(s.b, s.a)), t = d2 ? G.dot(G.sub(f, s.a), G.sub(s.b, s.a)) / d2 : -1; if (t >= -1e-9 && t <= 1 + 1e-9 && G.dist(f, base) > 1e-6) cand(f, "perp", 3); }
      if (ST.modes.tan) for (const cv of g.curves) for (const p of G.tangents(base, cv.c, cv.r)) if (cv.t === "circle" || inSweep(G.ang(cv.c, p), cv)) cand(p, "tan", 3);
    }
    if (best) acquireTick(best); else { clearTimeout(hover?.timer); hover = null; }
    // задержка курсора на отрезке — захват его направления для «Параллельно» (от последней точки)
    if (!best && base && ST.modes.par) { let seg = null, sd = tol * 0.6; for (const s of g.segs) { const d = G.dist(G.foot(W, s.a, s.b, true), W); if (d < sd) { sd = d; seg = s; } } parTick(seg); }
  }
  const lines = [];
  // орто: точка только на оси X или Y от последней точки; линия отслеживания может лишь указать, где на этой оси остановиться
  const ortho = ST.ortho && base && pointMode ? (() => { const v = G.sub(W, base), ax = Math.abs(v[0]) >= Math.abs(v[1]); return { d: ax ? [Math.sign(v[0]) || 1, 0] : [0, Math.sign(v[1]) || 1], p: ax ? [W[0], base[1]] : [base[0], W[1]] }; })() : null;
  if (!best && pointMode) {
    const near = [];
    for (const L of trackLines(base, CMD?.prev?.() || null)) {
      const v = G.sub(W, L.o), along = G.dot(v, L.d); if (along < -1e-9) continue;
      const off = Math.abs(G.cross(L.d, v)); if (off <= tol * 0.8) near.push({ ...L, p: G.add(L.o, G.mul(L.d, along)), off });
    }
    near.sort((a, b) => a.off - b.off);
    if (ortho) {
      for (const a of near) {
        if (Math.abs(G.cross(a.d, ortho.d)) < 1e-6) continue;
        const x = G.inter(base, G.add(base, ortho.d), a.o, G.add(a.o, a.d), true);
        if (x && x.t > 1e-9 && G.dist(x.p, ortho.p) <= tol * 1.5) { best = { w: x.p, k: "track", pr: 3.5, d: 0, dir: ortho.d }; lines.push(a); break; }
      }
    } else {
      for (let i = 0; i < near.length && !best; i++) for (let j = i + 1; j < near.length; j++) {        // две линии — точка их пересечения
        const a = near[i], b = near[j]; if (Math.abs(G.cross(a.d, b.d)) < 1e-6) continue;
        const x = G.inter(a.o, G.add(a.o, a.d), b.o, G.add(b.o, b.d), true);
        if (x && G.dist(x.p, W) <= tol * 1.5) { best = { w: x.p, k: "track2", pr: 3.5, d: 0 }; lines.push(a, b); break; }
      }
      if (!best && near.length) { const a = near[0]; best = { w: a.p, k: a.k, pr: 4, d: a.off, dir: a.k === "polar" || a.k === "par" ? a.d : null, t: a.t }; lines.push(a); }
    }
    if (!best && !ortho && snapOn && ST.modes.near) for (const s of g.segs) cand(G.foot(W, s.a, s.b, true), "near", 5);
  }
  let w = best ? best.w : W, k = best?.k || null, dir = best?.dir || null;
  if (!best && ortho) { w = ortho.p; k = "ortho"; dir = ortho.d; }
  if (base && !dir) { const v = G.sub(w, base); dir = G.len(v) > 1e-9 ? G.unit(v) : null; }
  return { c, w, k, dir, lines, mpp, t: best?.t };
}

/* ---------- предпросмотр ---------- */
function refresh() {
  prevSrc.clear(true);
  const fs = [];
  if (CUR && CMD) {
    const size = mMain.getSize() || [1000, 800], far = Math.hypot(size[0], size[1]) * CUR.mpp * 2;
    for (const L of CUR.lines) fs.push(fLine([L.o, G.add(CUR.w, G.mul(L.d, far))], "track"));
    ACQ.forEach(a => fs.push(fPt(a.w, "acq")));
    if (PAR && ST.modes.par && CMD.need === "point") fs.push(fLine([PAR.a, PAR.b], "parseg"));
    if (CMD.need === "point") {
      const pv = CMD.preview?.(CUR.w) || {};
      (pv.polys || []).forEach(r => r.length > 2 && fs.push(fPoly(r, "rubber")));
      (pv.lines || []).forEach(l => l.length > 1 && fs.push(fLine(l, "rubber")));
      (pv.ghosts || []).forEach(f => fs.push(f));
      (pv.pts || []).forEach(p => fs.push(fPt(p, "base")));
      if (CUR.k && CUR.k !== "ortho" && CUR.k !== "polar") fs.push(fPt(CUR.w, ["ext", "track", "track2", "par"].includes(CUR.k) ? "track" : CUR.k));
    } else if (CMD.need === "obj") (CMD.previewObj?.(CUR) || []).forEach(f => fs.push(f));
  }
  // неподвижный предпросмотр команды (массив): виден и без движения мыши, следует за набираемым числом
  if (CMD?.still) (CMD.still(typedNum()) || []).forEach(f => fs.push(f));
  prevSrc.addFeatures(fs);
  tip();
}

/* ---------- подсказка у курсора и динамический ввод ---------- */
const tipEl = document.createElement("div"); tipEl.className = "cadtip"; tipEl.hidden = true;
const tipOv = new ol.Overlay({ element: tipEl, offset: [18, 16], positioning: "top-left", stopEvent: false });
mMain.addOverlay(tipOv);
const f2 = n => fmt(n, 2), a1 = r => fmt(G.norm2pi(r) / DEG, 1);
function tip() {
  const lines = [];
  if (CMD && CUR && ST.dyn) {
    const base = CMD.base?.();
    if (CMD.need === "point" && base && G.dist(base, CUR.w) > 1e-9) lines.push(`${f2(G.dist(base, CUR.w))} м · ${a1(G.ang(base, CUR.w))}°`);
    (CMD.need === "point" ? CMD.tip?.(CUR.w) || [] : []).forEach(t => lines.push(t));
    if (CUR.k) lines.push(CUR.k === "polar" ? `полярное: ${fmt((CUR.t || 0) / DEG, 0)}°${ST.polarRel ? " к последнему отрезку" : ""}` : KIND[CUR.k]);
    if (!lines.length) lines.push(CMD.need === "obj" ? (CMD.objTip?.(CUR) || "выберите объект") : CMD.need === "sel" ? `выбрано: ${sel.length}` : CMD.need === "value" ? "введите значение" : "укажите точку");
  }
  tipEl.hidden = !lines.length || !CUR;
  if (!tipEl.hidden) { tipEl.innerHTML = lines.map(esc).join("<br>"); tipOv.setPosition(CUR.c); }
}
const inEl = document.createElement("input"); inEl.className = "cadin"; inEl.hidden = true; inEl.spellcheck = false; inEl.autocomplete = "off";
const acEl = document.createElement("div"); acEl.className = "cadac"; acEl.hidden = true;
mMain.getOverlayContainerStopEvent().append(inEl, acEl);
let inMode = null;                    // "cmd" — набирается команда, "val" — ввод для текущей команды
// русская раскладка: буквы по физической клавише (как набирают команды AutoCAD) и знаки ввода координат
const RU = "йцукенгшщзхъфывапролджэячсмитьбю", EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,.";
const toEn = s => [...s.toLowerCase()].map(ch => { const i = RU.indexOf(ch); return i >= 0 ? EN[i] : ch; }).join("");
const normNum = s => s.replace(/[жЖ]/g, ";").replace(/"/g, "@").replace(/Б/g, "<").replace(/\s*;\s*/g, ";").trim();
function openInput(mode, ch) {
  // мышь ещё не была над картой — поле у середины карты, а не в её левом верхнем углу
  const sz = mMain.getSize() || [160, 160];
  inMode = mode; const px = CUR ? mMain.getPixelFromCoordinate(CUR.c) : [sz[0] / 2 - 18, sz[1] / 2 - 16];
  const below = tipEl.hidden ? 16 : 16 + tipEl.offsetHeight + 4;
  inEl.style.left = `${Math.round(px[0] + 18)}px`; inEl.style.top = `${Math.round(px[1] + below)}px`;
  inEl.placeholder = mode === "cmd" ? "команда: L, PL, C, TR…" : CMD?.need === "point" ? "25 · 25<90 · X,Y · @dx,dy" : CMD?.need === "text" ? (CMD.placeholder?.() || "текст надписи, Enter") : "значение";
  inEl.hidden = false; inEl.value = ch || ""; inEl.classList.remove("bad"); inEl.focus(); autoc();
}
function closeInput() { inEl.hidden = true; inEl.value = ""; acEl.hidden = true; inMode = null; }
function autoc() {
  if (inMode !== "cmd") { acEl.hidden = true; return; }
  const q = inEl.value.trim().toUpperCase(), list = q ? Object.entries(ALIAS).filter(([a]) => a.startsWith(q)).sort((x, y) => x[0].length - y[0].length).slice(0, 6) : [];
  acEl.hidden = !list.length; if (!list.length) return;
  acEl.style.left = inEl.style.left; acEl.style.top = `${parseInt(inEl.style.top) + 30}px`;
  acEl.innerHTML = list.map(([a, n]) => `<div><b>${a}</b> ${esc(CMDS[n].title)}</div>`).join("");
}
inEl.addEventListener("keydown", e => {
  e.stopPropagation();
  if (inMode === "cmd" && /^Key[A-Z]$/.test(e.code) && !e.ctrlKey && !e.metaKey) { e.preventDefault(); const all = inEl.value && inEl.selectionStart === 0 && inEl.selectionEnd === inEl.value.length; inEl.value = (all ? "" : inEl.value) + e.code.slice(3); inEl.classList.remove("bad"); autoc(); return; }
  if (e.key === "Enter" || (e.key === " " && inMode === "cmd")) { e.preventDefault(); submit(); }
  else if (e.key === "Escape") { e.preventDefault(); closeInput(); }
});
inEl.addEventListener("input", () => { inEl.classList.remove("bad"); autoc(); if (CMD?.still) refresh(); });
// число, которое сейчас набирается в поле ввода команды (для живого предпросмотра), иначе null
// для точки «25,5» — координаты X,Y, а не длина 25,5 (как в parsePoint)
function typedNum() { if (inMode !== "val" || inEl.hidden) return null; const s = normNum(inEl.value.trim()); return new RegExp(`^${NUM}$`).test(s) && !(CMD?.need === "point" && s.includes(",")) ? num(s) : null; }
function bad(msg) { inEl.classList.add("bad"); inEl.select(); note(msg); }   // текст выделен целиком: следующий ввод заменяет его, а не клеится к нему
const PN = "(-?\\d+(?:\\.\\d+)?)", NUM = "(-?\\d+(?:[.,]\\d+)?)", num = s => +s.replace(",", ".");
function submit() {
  const raw = inEl.value.trim();
  if (inMode === "cmd") {
    if (!raw) { closeInput(); if (LAST) start(LAST); return; }
    const n = ALIAS[raw.toUpperCase()]; if (!n) return bad(`Команды «${raw}» нет. Например: L — отрезок, PL — полилиния, C — круг, TR — обрезать, ZE — показать всё, F1 — все.`);
    closeInput(); start(n); return;
  }
  if (!CMD) return closeInput();
  if (CMD.need === "text") { closeInput(); if (raw) CMD.text(raw); else enter(); after(); return; }
  if (!raw) { closeInput(); enter(); return; }
  const o = matchOpt(raw); if (o) { closeInput(); o.fn(); after(); return; }
  // команда ждёт ПЕРВУЮ точку (после «+» слой полигонов сам запускает «Полилинию»): набранный псевдоним — смена команды,
  // а не неверная точка. Когда точки уже есть, команды не принимаются: так же в AutoCAD.
  { const al = ALIAS[raw.toUpperCase()]; if (al && CMD.need === "point" && !CMD.base?.()) { closeInput(); start(al); return; } }
  const s = normNum(raw), plain = new RegExp(`^${NUM}$`).test(s);
  if (CMD.need === "value" || (plain && CMD.valueFirst?.())) { if (!plain) return bad("Нужно число."); closeInput(); CMD.value(num(s)); after(); return; }
  if (CMD.need === "point") { const p = parsePoint(s); if (typeof p === "string") return bad(p); closeInput(); CMD.point(p, { typed: true }); after(); return; }
  bad("Сейчас нужен щелчок по объекту или один из параметров в квадратных скобках.");
}
function matchOpt(raw) {
  const o = CMD?.opts?.(); if (!o) return null;
  const s = raw.toLowerCase(), e = toEn(s);
  return o.find(x => x.keys.includes(s)) || o.find(x => x.keys.includes(e)) || null;
}
function parsePoint(s) {
  const base = CMD.base?.(); let m;
  if ((m = s.match(new RegExp(`^@${NUM};${NUM}$`)))) return base ? G.add(base, [num(m[1]), num(m[2])]) : "Смещение @ считается от последней точки: сначала укажите первую.";
  if ((m = s.match(new RegExp(`^${NUM};${NUM}$`)))) return [num(m[1]), num(m[2])];
  // X,Y как в AutoCAD: «X,Y» — точка в МСК всегда (и после первой точки), «@dX,dY» — смещение от последней точки;
  // дробная часть — через точку (аудит 09.10.2026: в рабочей странице «x,y» после первой точки уходило в длину)
  if ((m = s.match(new RegExp(`^(@?)${PN},${PN}$`)))) {
    const xy = [+m[2], +m[3]];
    if (m[1]) return base ? G.add(base, xy) : "Смещение @ считается от последней точки: сначала укажите первую.";
    return xy;
  }
  if ((m = s.match(new RegExp(`^@?${NUM}\\s*<\\s*${NUM}$`)))) return base ? G.polar(base, num(m[2]) * DEG, num(m[1])) : "Длина и угол считаются от последней точки: сначала укажите первую.";
  if ((m = s.match(new RegExp(`^${NUM}$`)))) {
    if (!base) return "Одно число — длина от последней точки. Первую точку укажите щелчком или координатами X,Y.";
    if (!CUR?.dir) return "Покажите направление курсором и повторите ввод длины.";
    return G.add(base, G.mul(CUR.dir, num(m[1])));
  }
  return "Не понял ввод. Примеры: 25 (длина) · 25<90 (длина и угол) · 12345.6,6789.1 (точка X,Y в МСК) · @10,-5 (смещение).";
}

/* ---------- запуск команд ---------- */
let CMD = null, LAST = null;
const title = () => CMD ? CMDS[CMD.id].title.toUpperCase() : "";
function start(name, opts = {}) {
  cancel(true); closeInput(); lastNote = null; layerSwitch = null;
  // правка ручкой — не команда: Enter/Пробел после неё не повторяет её (у неё нет объекта) и её нет в истории F2
  if (name === "grip" && !opts?.g) return;
  terrTool.value = ""; UIS.tool = "cmd"; ACQ.length = 0; gripSrc.clear(true);
  CMD = CMDS[name].make(opts); CMD.id = name;
  downloadWarn(name);
  revealCurLayer(name);                   // рисование в скрытый текущий слой: слой включается
  if (CMDS[name].alias.length) { LAST = name; hist(`${CMDS[name].title.toUpperCase()} (${CMDS[name].alias[0]})`, true); }
  mMain.getTargetElement().style.cursor = "crosshair";
  if (CMD.done) return finish();
  after();
}
function cancel(silent) {
  if (!CMD) return; cadApi.lastEnd = performance.now(); CMD.cancel?.(); CMD = null; prevSrc.clear(); tipEl.hidden = true; ACQ.length = 0; closeInput(); setTimeout(() => { syncGrips(); showCmd(); }, 0);
  if (!silent) { UIS.tool = "select"; mMain.getTargetElement().style.cursor = ""; syncButtons(); syncStatus(); }
}
// итог команды («Соединено: 12 → 2», «Расстояние 25 м») остаётся в строке состояния после её завершения
function finish() { cadApi.lastEnd = performance.now(); setTimeout(() => { syncGrips(); showCmd(); }, 0); const t = title(), msg = doneMsg || lastNote || ""; CMD = null; prevSrc.clear(); tipEl.hidden = true; ACQ.length = 0; UIS.tool = "select"; mMain.getTargetElement().style.cursor = ""; syncButtons(); syncStatus(); if (msg && t && !msg.startsWith(t)) note(msg); }
let lastNote = null, noteTimer = 0;
/* итог действия в строке состояния (принцип 3: «каждый инструмент говорит, что делать дальше»); пока команда идёт, в строке состояния
   только короткая часть, полная подсказка — в командной строке над картой */
let doneMsg = null;
const MODK = () => MOD, UNDO_TAIL = () => ` ${MODK()}+Z — отменить.`;
const plural = (n, a, b, c) => { const m = n % 100, k = n % 10; return m > 10 && m < 20 ? c : k === 1 ? a : k > 1 && k < 5 ? b : c; };
function result(msg) { note(msg); doneMsg = msg; }
const DRAW_DONE = { "отрезок": ["Создан отрезок", "len"], "полилиния": ["Создана полилиния", "v"], "прямоугольник": ["Создан прямоугольник", "v"], "круг": ["Создан круг", "area"], "дуга": ["Создана дуга", "len"],
  "многоугольник": ["Создан многоугольник", "v"], "эллипс": ["Создан эллипс", "area"], "точка": ["Создана точка", ""] };
function drawSummary(items, label) {
  const d = DRAW_DONE[label]; if (!d || items.length !== 1) return;
  const { key, f } = items[0], g = f.getGeometry(), poly = g.getType() === "Polygon", ch = g.getType() === "Point" ? null : chainsOf(g)[0]?.map(toM), parts = [];
  if (ch) {
    const nv = ch.length > 2 && G.same(ch[0], ch[ch.length - 1], 1e-9) ? ch.length - 1 : ch.length;   // замкнутая линия — без повтора первой вершины
    if (d[1] === "v") parts.push(`${nv} ${plural(nv, "вершина", "вершины", "вершин")}`);
    if (poly && d[1] !== "len") parts.push(`${fmt(Math.abs(G.area(ch)), 1)} м²`); else if (!poly && d[1] !== "area") parts.push(`${f2(G.chainLen(ch))} м`);
  }
  // слой сменился сам: текущий слой другого вида — так и говорим, иначе объект «пропадает» в чужом слое (аудит 09.10.2026)
  const fr = layerSwitch?.from, sw = !layerSwitch ? "" : `${fr ? ` Слой «${fr.title}» — для ${{ poly: "полигонов", line: "линий", point: "точек" }[fr.geom] || "другой геометрии"}, поэтому` : ""} ${layerSwitch.made ? "создан новый" : "выбран"} слой «${layerSwitch.to}», теперь текущий — он.`;
  layerSwitch = null;
  result(`${poly && label === "полилиния" ? "Создан полигон" : d[0]} в слое «${lyr(key)?.title || "—"}»${parts.map(x => ", " + x).join("")}.${sw}${UNDO_TAIL()}`);
}
const EDIT_DONE = { "перенос": "Перемещено объектов", "копия": "Скопировано объектов", "поворот": "Повёрнуто объектов", "масштаб": "Масштабировано объектов", "зеркало": "Отражено объектов",
  "обрезка": "Обрезано объектов", "удлинение": "Удлинено объектов", "сопряжение": "Сопряжено объектов" };
function editSummary(changes, adds, label) {
  const n = changes.length || adds.length, w = /^удаление( \d+ об\.)?$/.test(label) ? "Удалено объектов" : EDIT_DONE[label];
  if (w && n) result(`${w}: ${n}.${UNDO_TAIL()}`);
}
// слой — выгрузка портала: объекты, нарисованные в нём, помечаются как правка выгрузки (бейдж «изм.» у слоя); рисованию это не мешает
const DL_SRC = { gisogd: "ГИС ОГД", ogd: "ГИС ОГД", egko: "ЕГКО", nspd: "НСПД", osm: "OpenStreetMap", yandex: "Яндекса" };
const DRAW_GEOM = { line: ["line"], arc: ["line"], pline: ["line", "poly"], rect: ["poly", "line"], circle: ["poly", "line"], polygon: ["poly", "line"], ellipse: ["poly", "line"], point: ["point"] };
function downloadWarn(name) {
  const l = DRAW_GEOM[name] && lyr(currentId.value), src = l && /^([a-z]+)\./.exec(l.key)?.[1];
  if (l && DL_SRC[src] && DRAW_GEOM[name].includes(l.geom)) note(`Слой — выгрузка ${DL_SRC[src]}: ваши объекты будут помечены как правка выгрузки.`);
}
function note(msg) { doneMsg = null; lastNote = msg; hist(msg); showCmd(); }
/* история команд, как текстовое окно AutoCAD (F2): запущенные команды и их сообщения за сеанс */
const HIST = [], histEl = document.createElement("div"); histEl.className = "cmdhist"; histEl.hidden = true; histEl.setAttribute("role", "log");
function hist(text, cmd) {
  if (!text || HIST[HIST.length - 1]?.text === text) return;
  HIST.push({ t: new Date(), text, cmd }); if (HIST.length > 200) HIST.shift(); if (!histEl.hidden) showHist();
}
function showHist() {
  histEl.innerHTML = `<div class="hh"><b>История команд</b><span>F2 — скрыть</span></div>` + (HIST.length ? HIST.slice(-60).map(h => `<div class="${h.cmd ? "hc" : ""}"><time>${h.t.toLocaleTimeString("ru-RU")}</time> ${esc(h.text)}</div>`).join("") : `<div class="empty">Команд в этом сеансе ещё не было.</div>`);
  histEl.scrollTop = histEl.scrollHeight;
}
function toggleHist() { histEl.hidden = !histEl.hidden; if (!histEl.hidden) { showHist(); placeHist(); } }
// история — над командной строкой, какой бы высоты та ни была (с сообщением она в две строки)
function placeHist() { if (!histEl.hidden) histEl.style.bottom = `${10 + cmdEl.offsetHeight + 6}px`; }
const cmdEl = document.createElement("div"); cmdEl.className = "cmdline"; cmdEl.hidden = true; cmdEl.setAttribute("role", "status");
mMain.getTargetElement().append(cmdEl, histEl);
cmdEl.addEventListener("click", e => { if (!CMD && !e.target.closest("button")) openInput("cmd"); });
function showCmd() {
  document.body.classList.toggle("cmdon", !!CMD);
  // без команды строка над картой не видна (владелец 09.10.2026, снимок: приглашение «Команда» на карте зачёркнуто; прежний ответ 2А —
  // «видна всегда» — заменён): команду набирают прямо на карте (L, PL, C… и Enter) или берут с ленты; сообщение команды — пока не прочитано
  // каждая строка — одна, длинный текст обрезается многоточием, целиком — в подсказке (title) и в истории F2 (аудит 09.10.2026)
  const nt = lastNote ? `<div class="nt" title="${esc(lastNote)}">${esc(lastNote)}</div>` : "";
  if (!CMD) {
    cmdEl.classList.add("idle");
    cmdEl.innerHTML = nt;
    cmdEl.hidden = !nt; placeHist();
    clearTimeout(noteTimer); if (nt) noteTimer = setTimeout(() => { if (!CMD) { lastNote = null; showCmd(); } }, 8000);   // итог команды — 8 с, история — F2
    return;
  }
  cmdEl.classList.remove("idle");
  const text = CMD.prompt().replace(/\s*\[[^\]]*\]/g, ""), ops = CMD.opts?.() || [];
  cmdEl.innerHTML = nt + `<div class="cl"><b title="${esc(title() + ": " + text)}">${esc(title())}</b><span class="tx">${esc(text)}</span>` + ops.map((o, i) => `<button class="op" data-op="${i}" title="Или наберите букву в скобках и Enter">${esc(o.label)}</button>`).join("") + `<span class="k">Esc — прервать</span></div>`;
  cmdEl.querySelectorAll("[data-op]").forEach(b => b.onclick = () => { const o = (CMD?.opts?.() || [])[+b.dataset.op]; if (o) { o.fn(); after(); } });
  cmdEl.hidden = false; placeHist();
}
function after() {
  if (!CMD) { showCmd(); return; } if (CMD.done) return finish();
  showCmd(); lastNote = null;
  if (CMD.need === "text" && inEl.hidden) openInput("val");            // текст надписи набирается сразу, без первой буквы-команды
  if (CUR) CUR = resolve(CUR.c); refresh(); syncButtons();
}
function enter() { if (!CMD) return; if (CMD.enter) CMD.enter(); else CMD.done = true; after(); }
function syncButtons() { cad.cmd = CMD?.id || null; }

let lastClick = null;
/* события карты: во время команды щелчок — ввод для команды, двойной щелчок не приближает, перетаскивание двигает карту */
const cadI = new ol.interaction.Interaction({ handleEvent: e => {
  if (!CMD && UIS.tool === "select" && gripSrc.getFeatures().length) {
    if (e.type === "pointermove") { const g = gripAt(e.pixel); if (g !== hoverGrip) { hoverGrip?.set("hover", false); hoverGrip = g; g?.set("hover", true); mMain.getTargetElement().style.cursor = g ? "pointer" : ""; } return true; }
    if (e.type === "pointerdown" && e.originalEvent.button === 0 && !e.originalEvent.shiftKey && !e.originalEvent.ctrlKey && !e.originalEvent.metaKey) {
      const g = gripAt(e.pixel); if (g) { hoverGrip = null; start("grip", { g, px: e.pixel.slice() }); return false; }
    }
  }
  if (!CMD) return true;
  if (e.type === "pointerdrag" && CMD.id === "grip") { CMD.moved = true; CUR = resolve(e.coordinate); refresh(); return false; }
  if (e.type === "pointerup" && CMD.id === "grip" && CMD.moved) { CUR = resolve(e.coordinate); CMD.point(CUR.w, { drag: true }); after(); return false; }
  if (e.type === "pointermove") { CUR = resolve(e.coordinate); refresh(); return true; }
  if (e.type === "click") {
    // свой двойной щелчок: два щелчка в одной точке быстрее 0,4 с (у OpenLayers двойным считаются любые два быстрых щелчка)
    const now = performance.now(), dbl = lastClick && now - lastClick.t < 400 && Math.hypot(lastClick.px[0] - e.pixel[0], lastClick.px[1] - e.pixel[1]) <= 6;
    lastClick = dbl ? null : { t: now, px: e.pixel.slice() };
    closeInput(); CUR = resolve(e.coordinate);
    if (dbl && CMD.need === "point" && CMD.dbl) CMD.dbl();
    else if (CMD.need === "point") CMD.point(CUR.w, { click: true });
    else if (CMD.need === "value" && CMD.clickPoint) { CMD.need = "point"; CMD.point(CUR.w, { click: true }); }   // щелчок вместо числа: число по умолчанию, щелчок — точка
    else if (CMD.need === "sel") { const h = hitAt(e.pixel); if (h) setSel(e.originalEvent.shiftKey ? selNow().filter(s => s.f !== h.f) : [...selNow(), h]); }
    else if (CMD.need === "obj") { const h = hitAt(e.pixel); if (!h) note(`${title()} · Под курсором нет объекта: щёлкните по линии или контуру.`); else CMD.pick(h, CUR); }
    after(); return false;
  }
  if (e.type === "dblclick") return false;                         // без приближения карты во время команды
  return true;
} });
cadI.set("gradoTop", true);                 // по метке лист (frames.js) встаёт сразу под перехватом команд
mMain.addInteraction(cadI);
mMain.getViewport().addEventListener("contextmenu", e => { if (CMD) { e.preventDefault(); enter(); } });   // правая кнопка — Enter, как в AutoCAD
// перехват держится последним, чтобы получать события раньше остальных взаимодействий карты
mMain.getInteractions().on("add", ev => { if (ev.element !== cadI) { const arr = mMain.getInteractions(); arr.remove(cadI); arr.push(cadI); } });

/* клавиатура: псевдонимы команд, динамический ввод, Enter/пробел, Esc, F-клавиши режимов */
const onKey = e => {
  if (e.target === inEl) return;
  if (typing(e)) return;      // клавиши дерева слоёв (стрелки, Пробел, F2, Delete) не уходят в команды карты; буквы и Esc — уходят; в открытом меню («Выгрузка», «Окна») Enter и пробел выбирают пункт, а не повторяют команду
  if (e.key === "F2") { e.preventDefault(); toggleHist(); return; }
  const F = { F3: "osnap", F8: "ortho", F10: "polar", F11: "otrack", F12: "dyn" }[e.key];
  if (F) { e.preventDefault(); toggle(F); return; }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === "Escape" && CMD) { e.preventDefault(); e.stopImmediatePropagation(); cancel(); return; }
  if (e.key === "Escape" && measureSrc.getFeatures().length) measureSrc.clear();
  // Enter и пробел на кнопке, ссылке, пункте меню нажимают её, а не повторяют команду (аудит 07.10.2026, #30: с клавиатуры кнопки не нажимались)
  if ((e.key === "Enter" || e.key === " ") && e.target.closest?.("button,a[href],summary,[role=button],[role=menuitem],[role=tab],[role=option]")) return;
  if ((e.key === "Enter" || e.key === " ") && (CMD || LAST)) { e.preventDefault(); e.stopImmediatePropagation(); CMD ? enter() : start(LAST); return; }
  if ((e.key === "Delete" || e.key === "Backspace") && CMD?.id === "grip") { e.preventDefault(); e.stopImmediatePropagation(); const o = CMD.opts()[0]; if (o) { o.fn(); after(); } return; }
  // во время команды Backspace убирает последнюю точку (если есть что убирать), но никогда не удаляет выбранное
  if ((e.key === "Backspace" || e.key === "Delete") && CMD) { e.preventDefault(); e.stopImmediatePropagation(); if (e.key === "Backspace" && CMD.back) { CMD.back(); after(); } return; }
  if (e.key.length !== 1 || e.key === "?" || e.key === "/") return;
  if (CMD && CMD.need !== "sel") { e.preventDefault(); e.stopImmediatePropagation(); openInput("val", e.key); }
  else if (/^Key[A-Z]$/.test(e.code) && mapReady()) { e.preventDefault(); e.stopImmediatePropagation(); openInput("cmd", e.code.slice(3)); }
};
addEventListener("keydown", onKey, true);

function toggle(k) {
  ST[k] = !ST[k]; if (k === "ortho" && ST.ortho) ST.polar = false; if (k === "polar" && ST.polar) ST.ortho = false;
  if (k === "otrack" && !ST.otrack) ACQ.length = 0;
  saveST(); syncModes();
  note(`${({ osnap: "Объектная привязка", topo: "Топологическое редактирование", ortho: "Орто", polar: "Полярное отслеживание", otrack: "Объектное отслеживание", dyn: "Динамический ввод" })[k]} ${ST[k] ? "включено" : "выключено"} (${({ osnap: "F3", ortho: "F8", polar: "F10", otrack: "F11", dyn: "F12" })[k]}).`);
  if (CUR && CMD) { CUR = resolve(CUR.c); refresh(); }
}

/* ---------- запись в слои ---------- */
// открытая фигура — в слой линий, замкнутая — в полигоны (текущий слой линий — замкнутой линией), точка — в точки
function targetFor(kind, prefer) {
  const cur = lyr(currentId.value);
  if (kind === "point") return targetLayer("point");
  if (kind === "closed") return prefer === "line" || (!prefer && cur?.geom === "line") ? targetLayer("line") : targetLayer("poly");
  return targetLayer("line");
}
function newFeature(kind, w, prefer, props = {}) {
  const l = targetFor(kind, prefer), geom = kind === "point" ? new ol.geom.Point(fromM(w)) : l.geom === "poly" ? new ol.geom.Polygon([w.map(fromM)]) : new ol.geom.LineString(w.map(fromM));
  const f = new ol.Feature(geom); fieldsOfKey(l.key).forEach(k => f.set(k, "")); f.setProperties({ ...props, _edited: true, _new: true });
  return { key: l.key, f };
}
const copyFeat = (f, geom, extra = {}) => { const n = new ol.Feature(geom); const p = { ...propsOf(f), ...extra, _new: true, _edited: true }; delete p._key; delete p._uid; if (!extra._cad) delete p._cad; if (!extra._arr) delete p._arr; n.setProperties(p); return n; };
function addNew(items, label) {
  if (!items.length) return;
  const keys = new Set(); items.forEach(({ key, f }) => { layerSrc[key].addFeature(f); keys.add(key); });
  keys.forEach(k => writeBack(k));
  drawSummary(items, label); if (label === "подобие") result(`Подобие построено, объектов: ${items.length}.${UNDO_TAIL()}`);
}
// правка: changes [{key, f, geom?, cad?, remove?}] — прежнее состояние запоминается для отмены; adds [{key, f}] — новые объекты
function edit(changes, adds, label) {
  const keys = new Set();
  changes.forEach(c => { keys.add(c.key); if (c.remove) { layerSrc[c.key].removeFeature(c.f); return; } if (c.geom) c.f.setGeometry(c.geom); if (c.props) c.f.setProperties(c.props); if ("cad" in c) { if (c.cad) c.f.set("_cad", c.cad); else c.f.unset("_cad"); } c.f.set("_edited", true); });
  adds.forEach(a => { layerSrc[a.key].addFeature(a.f); keys.add(a.key); });
  keys.forEach(k => writeBack(k));
  editSummary(changes, adds, label);
}
const worldChains = f => chainsOf(f.getGeometry()).map(ch => ch.map(toM));
function xformGeom(g, fn) { const g2 = g.clone(); g2.applyTransform((inp, out, dim = 2) => { for (let i = 0; i < inp.length; i += dim) { const c = fromM(fn(toM([inp[i], inp[i + 1]]))); out[i] = c[0]; out[i + 1] = c[1]; } return out; }); return g2; }
function xformCad(cad, fn, k = 1, flip = false) {
  if (!cad?.c) return null;
  const c = fn(cad.c), out = { ...cad, c, r: cad.r * Math.abs(k) };
  if (cad.t === "arc") { out.a0 = G.ang(c, fn(G.polar(cad.c, cad.a0, cad.r))); out.sw = flip ? -cad.sw : cad.sw; }
  return out;
}
// предпросмотр преобразования: аффинная замена в координатах карты около опорной точки (точный пересчёт — при записи)
function affineOf(fn, baseW) {
  const b = fromM(baseW), s = 50, q0 = fromM(fn(baseW)), q1 = fromM(fn(toM([b[0] + s, b[1]]))), q2 = fromM(fn(toM([b[0], b[1] + s])));
  const ax = [(q1[0] - q0[0]) / s, (q1[1] - q0[1]) / s], ay = [(q2[0] - q0[0]) / s, (q2[1] - q0[1]) / s];
  return c => [q0[0] + ax[0] * (c[0] - b[0]) + ay[0] * (c[1] - b[1]), q0[1] + ax[1] * (c[0] - b[0]) + ay[1] * (c[1] - b[1])];
}
function ghosts(items, fn, baseW) {
  const A = affineOf(fn, baseW);
  return items.slice(0, 400).map(({ f }) => { const g = f.getGeometry().clone(); g.applyTransform((inp, out, dim = 2) => { for (let i = 0; i < inp.length; i += dim) { const c = A([inp[i], inp[i + 1]]); out[i] = c[0]; out[i + 1] = c[1]; } return out; }); return new ol.Feature({ geometry: g, k: "ghost" }); });
}

/* ---------- общие части команд ---------- */
const opt = (label, keys, fn) => ({ label, keys, fn });
const optStr = list => list.length ? ` [${list.map(o => o.label).join(" / ")}]` : "";
// команды редактирования работают с выбором: выбранное заранее берётся сразу (сначала объект, потом команда — как в AutoCAD)
function selection(then) {
  const st = { need: "sel" };
  st.prompt = () => `Выберите объекты: щелчок — добавить, Shift+щелчок — убрать, Shift+рамка — несколько (выбрано ${sel.length}). Enter — готово`;
  // после выбора команда продолжается своим состоянием: текущей командой становится объект, который вернул then
  st.enter = () => { if (!sel.length) { st.done = true; return; } const next = then(selNow().slice()); next.id = st.id; CMD = next; };
  if (sel.length) return then(selNow().slice());
  return st;
}
// объект под щелчком: цепочка (часть мульти-геометрии, ближайшая к щелчку) в координатах карты (space = "map") или МСК
function pickChain(h, pos, space = "world") {
  const t = h.f.getGeometry().getType(); if (/Point/.test(t)) return null;
  const chains = space === "map" ? chainsOf(h.f.getGeometry()) : worldChains(h.f), p = space === "map" ? pos.c : pos.w;
  let best = null;
  chains.forEach((ch, i) => { if (ch.length < 2) return; const q = G.nearest(ch, p); if (!best || q.d < best.q.d) best = { i, ch, q }; });
  return best && { ...best, t, key: h.key, f: h.f, space };
}
// геометрия после замены одной цепочки на несколько (обрезка, удлинение, сопряжение)
function replaced(p, chains) {
  const conv = c => p.space === "map" ? c : c.map(fromM);
  const all = chainsOf(p.f.getGeometry());
  if (p.t === "LineString") return chains.length === 1 ? new ol.geom.LineString(conv(chains[0])) : new ol.geom.MultiLineString(chains.map(conv));
  if (p.t === "MultiLineString") { all.splice(p.i, 1, ...chains.map(conv)); return new ol.geom.MultiLineString(all.filter(c => c.length >= 2)); }
  if (p.t === "Polygon") { all[p.i] = conv(chains[0]); return new ol.geom.Polygon(all); }
  if (p.t === "MultiPolygon") { const polys = p.f.getGeometry().getCoordinates(); let k = p.i; for (const poly of polys) { if (k < poly.length) { poly[k] = conv(chains[0]); break; } k -= poly.length; } return new ol.geom.MultiPolygon(polys); }
  return null;
}
// куски линии после обрезки и разрыва: первый остаётся тем же объектом, остальные — новые объекты с теми же атрибутами
function piecesEdit(p, pieces, label) {
  if (!pieces.length) return edit([{ key: p.key, f: p.f, remove: true }], [], label);
  if (p.t !== "LineString") return edit([{ key: p.key, f: p.f, geom: replaced(p, pieces), cad: null }], [], label);
  const conv = c => p.space === "map" ? c : c.map(fromM);
  edit([{ key: p.key, f: p.f, geom: new ol.geom.LineString(conv(pieces[0])), cad: null }], pieces.slice(1).map(c => ({ key: p.key, f: copyFeat(p.f, new ol.geom.LineString(conv(c))) })), label);
}
// границы для обрезки и удлинения — видимые объекты рядом, в координатах карты
function boundaries(except, around) {
  const ext = except.getGeometry().getExtent(), box = ol.extent.buffer(ext, around);
  const out = []; let n = 0;
  for (const l of project.layers) { if (!shown(l) || outOfScale(l)) continue; layerSrc[l.key].forEachFeatureIntersectingExtent(box, f => { if (++n > 4000) return true; if (f !== except) chainsOf(f.getGeometry()).forEach(c => c.length >= 2 && out.push(c)); }); }
  return out;
}
const CURKEY = () => currentId.value;
const ANNO = {
  text: { title: "Надписи", geom: "point", style: { fill: "#1d1d1f", stroke: "#ffffff", width: 0, opacity: 1, label: "Текст", labelSize: 13 } },
  dim: { title: "Размеры", geom: "line", style: { fill: "#2b4a7a", width: .8, label: "Размер", labelSize: 11 } },
  hatch: { title: "Штриховка", geom: "poly", style: { fill: "#5f6368", stroke: "#5f6368", width: .6, hatch: true, opacity: .7 } } };
function annoLayer(kind) {
  const a = ANNO[kind], have = project.layers.find(l => l.key.startsWith("user:") && l.title === a.title && l.geom === a.geom);
  if (have) return have;
  const cur = CURKEY(), l = createLayerQuiet(a.title, a.geom); Object.assign(l.style, a.style);
  if (cur && lyr(cur)) setCurrentQuiet(cur);
  toast(`Создан слой «${a.title}». Оформление слоя — в панели «Стиль».`); return l;
}


/* ---------- команды ---------- */
const CMDS = {};
const def = (id, title, alias, make) => { CMDS[id] = { title, alias, make }; };
const closeOpt = fn => opt("Замкнуть (З)", ["з", "замкнуть", "c", "close"], fn), undoOpt = fn => opt("Отменить (О)", ["о", "отменить", "u", "undo"], fn);

def("line", "Отрезок", ["L"], () => {                                     // каждый участок — отдельный объект
  const pts = [], made = [];
  const st = { need: "point", base: () => pts[pts.length - 1] || null, prev: () => pts[pts.length - 2] || null, own: () => [pts],
    prompt: () => pts.length ? `Следующая точка${optStr(st.opts())}, Enter — завершить` : "Первая точка",
    opts: () => [...(pts.length >= 3 ? [closeOpt(() => { st.point(pts[0]); st.done = true; })] : []), ...(made.length ? [undoOpt(() => st.back())] : [])],
    point: w => { if (pts.length && G.same(w, pts[pts.length - 1], 1e-6)) return; if (pts.length) { const it = newFeature("line", [pts[pts.length - 1], w]); addNew([it], "отрезок"); made.push(it); } pts.push(w); },
    back: () => { const it = made.pop(); if (it) { layerSrc[it.key].removeFeature(it.f); writeBack(it.key); } pts.pop(); },
    enter: () => { st.done = true; }, dbl: () => { st.done = true; },
    preview: w => ({ lines: pts.length ? [[pts[pts.length - 1], w]] : [] }) };
  return st;
});
def("pline", "Полилиния", ["PL"], o => {                                  // один объект; дуговые участки; в слое полигонов Enter замыкает контур
  const segs = [];                        // шаги построения: [точка] или точки дуги (у группы — свойство arc)
  let arcMode = false;
  const pts = () => segs.flat();
  const poly = () => (o.prefer || (lyr(CURKEY())?.geom === "poly" ? "poly" : "line")) === "poly";
  const endDir = () => { const P = pts(), last = segs[segs.length - 1]; if (last?.arc) return G.arcEndDir(last.arc); return P.length >= 2 ? G.unit(G.sub(P[P.length - 1], P[P.length - 2])) : [1, 0]; };
  const arcTo = w => { const P = pts(); return P.length ? G.tangentArc(P[P.length - 1], endDir(), w) : null; };
  const commit = close => {
    const P = pts(), p = P.filter((q, i) => !i || !G.same(q, P[i - 1], 1e-6));
    if ((close || poly()) && p.length > 3 && G.same(p[0], p[p.length - 1], 1e-6)) p.pop();   /* замыкание щелчком в начало — без двойной вершины */
    if (close || poly()) { if (p.length < 3) { note("Для замкнутого контура нужно не меньше трёх точек."); return false; } addNew([newFeature("closed", [...p, p[0]], o.prefer || null)], "полилиния"); }
    else { if (p.length < 2) { note("Для полилинии нужно не меньше двух точек."); return false; } addNew([newFeature("line", p)], "полилиния"); }
    return true;
  };
  const st = { need: "point", base: () => pts()[pts().length - 1] || null, prev: () => { const P = pts(); return P[P.length - 2] || null; }, own: () => [pts()],
    prompt: () => !segs.length ? "Начальная точка" : `${arcMode ? "Конечная точка дуги (касательной к предыдущему участку)" : "Следующая точка"}${optStr(st.opts())}, Enter — ${poly() ? "замкнуть контур" : "завершить"}`,
    opts: () => [...(segs.length ? [arcMode ? opt("Линейный (Л)", ["л", "линейный", "l", "line"], () => { arcMode = false; }) : opt("Дуга (Д)", ["д", "дуга", "a", "arc"], () => { arcMode = true; })] : []),
      ...(pts().length >= 3 ? [closeOpt(() => { if (commit(true)) st.done = true; })] : []), ...(segs.length ? [undoOpt(() => st.back())] : [])],
    point: w => {
      const P = pts(); if (P.length && G.same(w, P[P.length - 1], 1e-6)) return;
      const a = arcMode && P.length ? arcTo(w) : null;
      if (a) { const g = G.arcPts(a, 0.01).slice(1); g.arc = a; segs.push(g); } else segs.push([w]);
    },
    back: () => { segs.pop(); },
    enter: () => { if (!segs.length || commit(false)) st.done = true; }, dbl: () => { if (commit(false)) st.done = true; },
    tip: w => { const P = pts(), a = arcMode ? arcTo(w) : null, all = a ? [...P, ...G.arcPts(a, 0.05).slice(1)] : [...P, w];
      return [...(a ? [`дуга R ${f2(a.r)} м · ${f2(Math.abs(a.sw) * a.r)} м`] : []), ...(P.length >= 2 || a ? (poly() ? [`площадь ${fmt(Math.abs(G.area([...all, all[0]])), 1)} м²`] : [`всего ${f2(G.chainLen(all))} м`]) : [])]; },
    preview: w => { const P = pts(); if (!P.length) return {}; const a = arcMode ? arcTo(w) : null, all = a ? [...P, ...G.arcPts(a, 0.05).slice(1)] : [...P, w];
      return poly() && all.length >= 3 ? { polys: [[...all, all[0]]] } : { lines: [all] }; } };
  return st;
});
const RECC = { kind: null, r: 2, d1: 2, d2: 2 };                         // углы прямоугольника: null, "fillet", "chamfer"
def("rect", "Прямоугольник", ["REC"], o => {                              // по осям МСК или с поворотом; углы — фаской или сопряжением
  let a = null, rot = 0, ask = null;
  const box = b => { const u = [Math.cos(rot), Math.sin(rot)], v = [-u[1], u[0]], d = G.sub(b, a), x = G.dot(d, u), y = G.dot(d, v); return [a, G.add(a, G.mul(u, x)), G.add(G.add(a, G.mul(u, x)), G.mul(v, y)), G.add(a, G.mul(v, y)), a]; };
  const ring = b => { const r = box(b); if (RECC.kind === "fillet") { const q = G.filletAll(r, RECC.r, 0.01); return q.done === 4 ? q.pts : r; } if (RECC.kind === "chamfer") { const q = G.chamferAll(r, RECC.d1, RECC.d2); return q.done === 4 ? q.pts : r; } return r; };
  const cornerTxt = () => RECC.kind === "fillet" ? ` · углы: сопряжение R ${f2(RECC.r)} м` : RECC.kind === "chamfer" ? ` · углы: фаска ${f2(RECC.d1)} × ${f2(RECC.d2)} м` : "";
  const st = { need: "point", base: () => a,
    prompt: () => ask ? ask.p : a ? `Противоположный угол: щелчок или @ширина;высота${cornerTxt()}${optStr(st.opts())}` : `Первый угол${cornerTxt()}${optStr(st.opts())}`,
    opts: () => ask ? [] : a ? [opt("Поворот (П)", ["п", "поворот", "r", "rotation"], () => { ask = { p: "Угол поворота прямоугольника, °", k: "rot" }; st.need = "value"; })]
      : [opt("Сопряжение (С)", ["с", "сопряжение", "f", "fillet"], () => { ask = { p: `Радиус сопряжения углов <${f2(RECC.r)}>, 0 — без`, k: "r" }; st.need = "value"; }),
        opt("Фаска (Ф)", ["ф", "фаска", "c", "chamfer"], () => { ask = { p: `Первая длина фаски <${f2(RECC.d1)}>, 0 — без`, k: "d1" }; st.need = "value"; })],
    enter: () => { if (ask) { st.value(ask.k === "rot" ? 0 : RECC[ask.k] ?? 0); return; } st.done = true; },
    value: v => {
      const k = ask?.k; ask = null; st.need = "point";
      if (k === "rot" || !k) { rot = v * DEG; return; }
      if (v < 0) return note("Нужно число не меньше нуля.");
      if (k === "r") { RECC.kind = v > 0 ? "fillet" : null; if (v > 0) RECC.r = v; return; }
      if (k === "d1") { if (!v) { RECC.kind = null; return; } RECC.d1 = v; ask = { p: `Вторая длина фаски <${f2(RECC.d2 || v)}>`, k: "d2" }; st.need = "value"; return; }
      if (k === "d2") { RECC.d2 = v || RECC.d1; RECC.kind = "chamfer"; }
    },
    point: w => { if (!a) { a = w; return; } const r = ring(w); if (Math.abs(G.area(r)) < 1e-6) return; if (RECC.kind && r.length === 5) note("Углы не скруглены: стороны короче, чем нужно для фаски или сопряжения."); addNew([newFeature("closed", r, o.prefer)], "прямоугольник"); st.done = true; },
    tip: w => a ? (() => { const r = box(w); return [`${f2(G.dist(r[0], r[1]))} × ${f2(G.dist(r[1], r[2]))} м`, `площадь ${fmt(Math.abs(G.area(ring(w))), 1)} м²`]; })() : [],
    preview: w => a ? { polys: [ring(w)] } : {} };
  return st;
});
def("circle", "Круг", ["C"], o => {                                       // центр и радиус (диаметр) или три точки
  let c = null, three = null, dia = false;
  const make = (cc, r) => { if (r < 1e-6) return; addNew([newFeature("closed", G.circlePts(cc, r), o.prefer, { _cad: { t: "circle", c: cc, r } })], "круг"); st.done = true; };
  const st = { need: "point", base: () => three ? three[three.length - 1] || null : c,
    prompt: () => three ? `Точка ${three.length + 1} на окружности` : !c ? `Центр${optStr(st.opts())}` : `${dia ? "Диаметр" : "Радиус"}: число или точка${optStr(st.opts())}`,
    opts: () => three ? [] : !c ? [opt("3Т — по трём точкам", ["3", "3т", "3p"], () => { three = []; })] : [opt(dia ? "Радиус (Р)" : "Диаметр (Д)", dia ? ["р", "радиус", "r"] : ["д", "диаметр", "d"], () => { dia = !dia; })],
    valueFirst: () => !!c && !three, value: v => make(c, v / (dia ? 2 : 1)),
    point: w => {
      if (three) { three.push(w); if (three.length === 3) { const k = G.circle3(...three); if (!k) { three = []; return note("Точки на одной прямой — окружность не строится."); } make(k.c, k.r); } return; }
      if (!c) { c = w; return; } make(c, G.dist(c, w) / (dia ? 2 : 1));
    },
    tip: w => c && !three ? [`R ${f2(G.dist(c, w) / (dia ? 2 : 1))} м`] : [],
    preview: w => { if (three) { const k = three.length === 2 && G.circle3(three[0], three[1], w); return k ? { polys: [G.circlePts(k.c, k.r, 0.05)], pts: three } : { pts: three }; } return c ? { polys: [G.circlePts(c, G.dist(c, w) / (dia ? 2 : 1), 0.05)], lines: [[c, w]], pts: [c] } : {}; } };
  return st;
});
def("arc", "Дуга", ["A"], () => {                                         // три точки или центр–начало–конец
  const pts = []; let center = false;
  const arcOf = w => center ? (pts.length === 2 ? (() => { const c = pts[0], r = G.dist(c, pts[1]), a0 = G.ang(c, pts[1]); return { c, r, a0, sw: G.norm2pi(G.ang(c, w) - a0) || 2 * Math.PI }; })() : null) : pts.length === 2 ? G.arc3(pts[0], pts[1], w) : null;
  const st = { need: "point", base: () => pts[pts.length - 1] || null,
    prompt: () => center ? ["Центр дуги", "Начальная точка", "Конечная точка (дуга против часовой стрелки)"][pts.length] : [`Начальная точка${optStr(st.opts())}`, "Вторая точка дуги", "Конечная точка"][pts.length],
    opts: () => !pts.length && !center ? [opt("Центр (Ц)", ["ц", "центр", "c", "center"], () => { center = true; })] : [],
    point: w => { if (pts.length < 2) { pts.push(w); return; } const a = arcOf(w); if (!a) return note("Точки на одной прямой — дуга не строится."); addNew([newFeature("line", G.arcPts(a, 0.01), null, { _cad: { t: "arc", c: a.c, r: a.r, a0: a.a0, sw: a.sw } })], "дуга"); st.done = true; },
    tip: w => { const a = arcOf(w); return a ? [`R ${f2(a.r)} м · длина ${f2(Math.abs(a.sw) * a.r)} м`] : []; },
    preview: w => { const a = arcOf(w); return a ? { lines: [G.arcPts(a, 0.05)], pts } : { lines: pts.length ? [[...pts, w]] : [], pts }; } };
  return st;
});
let lastSides = 6;
def("polygon", "Многоугольник", ["POL"], o => {                           // правильный: число сторон, центр, радиус
  let n = lastSides, c = null, insc = true;
  const ring = w => G.regPoly(c, n, G.dist(c, w), G.ang(c, w), insc);
  const st = { need: "value", base: () => c,
    prompt: () => st.need === "value" ? `Число сторон <${n}> или щелчок — центр` : !c ? "Центр многоугольника" : `Радиус: ${insc ? "вершина" : "середина стороны"} — точка или число${optStr(st.opts())}`,
    value: v => { if (!c && st.need === "value") { if (v < 3 || v > 1024 || !Number.isInteger(v)) return note("Число сторон — целое от 3 до 1024."); n = lastSides = v; st.need = "point"; return; } if (v > 0) { addNew([newFeature("closed", G.regPoly(c, n, v, 0, insc), o.prefer)], "многоугольник"); st.done = true; } },
    valueFirst: () => !!c, clickPoint: true,
    enter: () => { if (st.need === "value") { st.need = "point"; return; } st.done = true; },
    opts: () => c ? [opt(insc ? "Описанный (О)" : "Вписанный (В)", insc ? ["о", "описанный", "c"] : ["в", "вписанный", "i"], () => { insc = !insc; })] : [],
    point: w => { if (!c) { c = w; return; } if (G.dist(c, w) < 1e-6) return; addNew([newFeature("closed", ring(w), o.prefer)], "многоугольник"); st.done = true; },
    tip: w => c ? [`R ${f2(G.dist(c, w))} м · сторона ${f2(G.dist(...ring(w).slice(0, 2)))} м`] : [],
    preview: w => c ? { polys: [ring(w)], lines: [[c, w]], pts: [c] } : {} };
  return st;
});
def("ellipse", "Эллипс", ["EL"], o => {                                  // центр, конец оси, вторая полуось
  let c = null, ax = null;
  const st = { need: "point", base: () => c,
    prompt: () => !c ? "Центр эллипса" : !ax ? "Конец первой оси: щелчок или длина по направлению курсора" : "Длина второй полуоси: число или точка",
    valueFirst: () => !!ax, value: v => { if (v > 0) make(v); },
    point: w => { if (!c) { c = w; return; } if (!ax) { if (G.dist(c, w) < 1e-6) return; ax = G.sub(w, c); return; } make(Math.abs(G.cross(G.unit(ax), G.sub(w, c)))); },
    tip: w => c && ax ? [`оси ${f2(2 * G.len(ax))} × ${f2(2 * Math.abs(G.cross(G.unit(ax), G.sub(w, c))))} м`] : c ? [`полуось ${f2(G.dist(c, w))} м`] : [],
    preview: w => !c ? {} : !ax ? { lines: [[c, w]], pts: [c] } : (() => { const b = Math.abs(G.cross(G.unit(ax), G.sub(w, c))); return b > 1e-6 ? { polys: [G.ellipsePts(c, ax, b, 0.05)], lines: [[c, G.add(c, ax)]], pts: [c] } : { lines: [[c, G.add(c, ax)]] }; })() };
  const make = b => { if (b < 1e-6) return; addNew([newFeature("closed", G.ellipsePts(c, ax, b, 0.01), o.prefer)], "эллипс"); st.done = true; };
  return st;
});
/* ШТРИХОВКА: щелчок внутри замкнутого контура — самый маленький контур вокруг точки копируется в слой «Штриховка»
   (стиль слоя — штриховка; сменить её вид можно в панели «Стиль»). Или выбрать контуры объектами. */
function contourAt(w) {
  const c = fromM(w); let best = null;
  for (const l of project.layers) {
    if (!shown(l) || outOfScale(l) || !layerSrc[l.key] || l.title === ANNO.hatch.title) continue;
    // по габариту: замкнутая линия точку внутри не «пересекает», её находит только габарит
    layerSrc[l.key].forEachFeatureInExtent([c[0], c[1], c[0], c[1]], f => {
      const g = f.getGeometry(), t = g.getType(); let poly = null;
      if (t === "Polygon" || t === "MultiPolygon") poly = t === "Polygon" ? g : g.getPolygons().find(p => p.intersectsCoordinate(c));
      else if (t === "LineString") { const r = g.getCoordinates(); if (r.length > 3 && r[0][0] === r[r.length - 1][0] && r[0][1] === r[r.length - 1][1]) poly = new ol.geom.Polygon([r]); }
      if (!poly || !poly.intersectsCoordinate(c)) return;
      const a = poly.getArea(); if (!best || a < best.a) best = { a, poly };
    });
  }
  return best?.poly || regionAt(w);
}
/* Контур из линий вокруг точки (BOUNDARY AutoCAD): отрезки видимых линий и рёбер полигонов рядом с точкой режутся в
   местах пересечения, из них строится плоский граф, и обходится грань, в которой лежит точка (грань слева, на каждой
   вершине — ближайший поворот по часовой от обратного ребра). Окно поиска 150 → 1200 м, пока грань не замкнётся. */
function regionAt(w) {
  for (const R of [150, 400, 1200]) { const r = regionIn(w, R); if (r) return r; }
  return null;
}
function regionIn(w, R) {
  const c = fromM(w), k = 1 / Math.cos(ol.proj.toLonLat(c)[1] * Math.PI / 180), box = ol.extent.buffer([c[0], c[1], c[0], c[1]], R * k);
  const segs = []; let n = 0;
  for (const l of project.layers) { if (!shown(l) || outOfScale(l) || !layerSrc[l.key] || l.title === ANNO.hatch.title) continue;
    layerSrc[l.key].forEachFeatureIntersectingExtent(box, f => { if (++n > 3000) return true;
      chainsOf(f.getGeometry()).forEach(ch => { const m = ch.map(toM); for (let i = 0; i + 1 < m.length; i++) if (!G.same(m[i], m[i + 1], 1e-6)) segs.push([m[i], m[i + 1]]); }); }); }
  if (segs.length < 3 || segs.length > 20000) return null;
  // разрезы в пересечениях: сетка 50 м по габаритам отрезков
  const C = 50, grid = new Map(), cuts = segs.map(() => [0, 1]);
  segs.forEach(([a, b], i) => { for (let x = Math.floor(Math.min(a[0], b[0]) / C); x <= Math.floor(Math.max(a[0], b[0]) / C); x++) for (let y = Math.floor(Math.min(a[1], b[1]) / C); y <= Math.floor(Math.max(a[1], b[1]) / C); y++) { const kk = x + "," + y; (grid.get(kk) || grid.set(kk, []).get(kk)).push(i); } });
  const seen = new Set();
  grid.forEach(list => { for (let u = 0; u < list.length; u++) for (let v = u + 1; v < list.length; v++) { const i = list[u], j = list[v], kk = i < j ? i + ":" + j : j + ":" + i; if (seen.has(kk)) continue; seen.add(kk);
    const [a, b] = segs[i], [p, q] = segs[j], d = (b[0] - a[0]) * (q[1] - p[1]) - (b[1] - a[1]) * (q[0] - p[0]); if (Math.abs(d) < 1e-12) continue;
    const t = ((p[0] - a[0]) * (q[1] - p[1]) - (p[1] - a[1]) * (q[0] - p[0])) / d, s2 = ((p[0] - a[0]) * (b[1] - a[1]) - (p[1] - a[1]) * (b[0] - a[0])) / d;
    if (t >= -1e-9 && t <= 1 + 1e-9 && s2 >= -1e-9 && s2 <= 1 + 1e-9) { cuts[i].push(Math.min(1, Math.max(0, t))); cuts[j].push(Math.min(1, Math.max(0, s2))); } } });
  // вершины графа — с точностью 1 мм; рёбра — куски отрезков между разрезами
  const V = new Map(), vid = p => { const kk = Math.round(p[0] * 1000) + "," + Math.round(p[1] * 1000); if (!V.has(kk)) V.set(kk, { p, out: [] }); return kk; };
  const E = new Set();
  segs.forEach(([a, b], i) => { const ts = [...new Set(cuts[i].map(t => Math.round(t * 1e9) / 1e9))].sort((x, y) => x - y);
    for (let z = 0; z + 1 < ts.length; z++) { const p1 = G.add(a, G.mul(G.sub(b, a), ts[z])), p2 = G.add(a, G.mul(G.sub(b, a), ts[z + 1])), k1 = vid(p1), k2 = vid(p2);
      if (k1 === k2 || E.has(k1 + ">" + k2)) continue; E.add(k1 + ">" + k2); E.add(k2 + ">" + k1); V.get(k1).out.push(k2); V.get(k2).out.push(k1); } });
  const ang = (k1, k2) => { const a = V.get(k1).p, b = V.get(k2).p; return Math.atan2(b[1] - a[1], b[0] - a[0]); };
  V.forEach((v, kk) => v.out.sort((x, y) => ang(kk, x) - ang(kk, y)));
  // ребро, которое первым пересекает луч от точки на восток
  let hit = null;
  E.forEach(e => { const [k1, k2] = e.split(">"); if (k1 > k2) return; const a = V.get(k1).p, b = V.get(k2).p;
    if ((a[1] > w[1]) === (b[1] > w[1])) return; const x = a[0] + (w[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1]); if (x <= w[0]) return;
    if (!hit || x < hit.x) hit = { x, k1, k2 }; });
  if (!hit) return null;
  // точка должна быть слева от начального ребра: ребро, идущее на север при точке к западу от него
  let [from, to] = V.get(hit.k2).p[1] > V.get(hit.k1).p[1] ? [hit.k1, hit.k2] : [hit.k2, hit.k1];
  const start = from + ">" + to, ring = [V.get(from).p];
  for (let step = 0; step < 20000; step++) {
    ring.push(V.get(to).p);
    const out = V.get(to).out, back = out.indexOf(from), next = out[(back - 1 + out.length) % out.length];
    from = to; to = next; if (from + ">" + to === start) break;
    if (step === 19999) return null;
  }
  if (ring.length < 4) return null;
  const A = G.area(ring); if (A <= 0) return null;                 // обход по часовой — точка снаружи всех контуров
  return new ol.geom.Polygon([ring.map(fromM)]);
}
def("bpoly", "Контур по щелчку", ["BPOLY", "BOUNDARY"], () => {
  let n = 0;
  const st = { need: "point", base: () => null, prompt: () => `Щёлкните внутри области, ограниченной линиями или контурами (построено ${n}); Enter — завершить`,
    point: w => { const poly = contourAt(w); if (!poly) return note("Вокруг точки нет замкнутой области: линии не смыкаются или область больше 1,2 км.");
      const l = targetLayer("poly"), f = new ol.Feature(poly.clone()); fieldsOfKey(l.key).forEach(k => f.set(k, "")); f.setProperties({ _new: true, _edited: true });
      addNew([{ key: l.key, f }], "контур по щелчку"); n++; note(`Контур ${fmt(Math.abs(G.area(poly.getCoordinates()[0].map(toM))), 1)} м² в слое «${l.title}».`); },
    enter: () => { st.done = true; } };
  return st;
});
def("hatch", "Штриховка", ["H", "BH"], () => {
  const made = [];
  const st = { need: "point", base: () => null,
    prompt: () => `Точка внутри замкнутого контура (штриховок: ${made.length})${optStr(st.opts())}, Enter — завершить`,
    opts: () => [opt("Выбрать объекты (В)", ["в", "выбрать", "s", "select"], () => { CMD = selection(items => { const l = annoLayer("hatch"), adds = [];
      for (const it of items) { const g = it.f.getGeometry(), t = g.getType(); if (/Polygon/.test(t)) adds.push({ key: l.key, f: new ol.Feature(g.clone()) }); }
      if (adds.length) { adds.forEach(a => a.f.setProperties({ "Наименование": "", _new: true, _edited: true })); addNew(adds, "штриховка"); } note(adds.length ? `Штриховка: ${adds.length}.` : "Среди выбранного нет полигонов — штриховать нечего."); return { done: true }; }); CMD.id = "hatch"; })],
    point: w => { const poly = contourAt(w); if (!poly) return note("Точка не внутри замкнутого контура: щёлкните внутри полигона или замкнутой линии."); const l = annoLayer("hatch"), f = new ol.Feature(poly.clone()); f.setProperties({ "Наименование": "", _new: true, _edited: true }); addNew([{ key: l.key, f }], "штриховка"); made.push(f); },
    enter: () => { st.done = true; } };
  return st;
});
/* РАЗМЕР: две точки и положение размерной линии; параллельный отрезку (по умолчанию), горизонтальный или вертикальный.
   Объект — линия выносная–размерная–выносная в слое «Размеры», величина — поле «Размер» (подписью слоя). */
def("dim", "Размер", ["DIM", "DAL", "DLI"], () => {
  const pts = []; let mode = "al";
  const geom = q => { const [p1, p2] = pts; let d1, d2, v;
    if (mode === "h") { d1 = [p1[0], q[1]]; d2 = [p2[0], q[1]]; v = Math.abs(p2[0] - p1[0]); }
    else if (mode === "v") { d1 = [q[0], p1[1]]; d2 = [q[0], p2[1]]; v = Math.abs(p2[1] - p1[1]); }
    else { const u = G.unit(G.sub(p2, p1)), n = [-u[1], u[0]], off = G.dot(G.sub(q, p1), n); d1 = G.add(p1, G.mul(n, off)); d2 = G.add(p2, G.mul(n, off)); v = G.dist(p1, p2); }
    return { line: [p1, d1, d2, p2], v }; };
  const st = { need: "point", base: () => pts[pts.length - 1] || null,
    prompt: () => pts.length < 2 ? (pts.length ? "Вторая точка размера" : "Первая точка размера") : `Положение размерной линии${optStr(st.opts())}`,
    opts: () => pts.length === 2 ? [opt("Параллельный (П)", ["п", "параллельный", "a", "aligned"], () => { mode = "al"; }), opt("Горизонтальный (Г)", ["г", "горизонтальный", "h", "horizontal"], () => { mode = "h"; }), opt("Вертикальный (В)", ["в", "вертикальный", "v", "vertical"], () => { mode = "v"; })] : [],
    point: w => { if (pts.length < 2) { if (!pts.length || !G.same(w, pts[0], 1e-6)) pts.push(w); return; }
      const g = geom(w), l = annoLayer("dim"), f = new ol.Feature(new ol.geom.LineString(g.line.map(fromM)));
      f.setProperties({ "Размер": fmt(g.v, 2), _new: true, _edited: true }); addNew([{ key: l.key, f }], "размер"); note(`Размер ${fmt(g.v, 2)} м.`); st.done = true; },
    tip: w => pts.length === 2 ? [`${fmt(geom(w).v, 2)} м`] : pts.length ? [`${f2(G.dist(pts[0], w))} м`] : [],
    preview: w => pts.length === 2 ? { lines: [geom(w).line], pts } : { lines: pts.length ? [[pts[0], w]] : [], pts } };
  return st;
});
def("text", "Текст", ["T", "DT", "TEXT"], () => {                           // надпись: точка вставки и строка текста
  let at = null, n = 0;
  const st = { need: "point", base: () => null,
    prompt: () => st.need === "text" ? "Текст надписи, Enter — поставить (пустой Enter — завершить)" : `Точка вставки надписи${n ? ` (поставлено: ${n})` : ""}, Enter — завершить`,
    point: w => { at = w; st.need = "text"; },
    text: t => { const l = annoLayer("text"), f = new ol.Feature(new ol.geom.Point(fromM(at))); f.setProperties({ "Текст": t, _new: true, _edited: true }); addNew([{ key: l.key, f }], "надпись"); n++; at = null; st.need = "point"; },
    enter: () => { if (st.need === "text") { at = null; st.need = "point"; return; } st.done = true; } };
  return st;
});
// «Показать всё» (Z, ZE, ZOOM): карта вписывается во все видимые слои, границу территории и листы; без анимации
function zoomAll() {
  const ex = ol.extent.createEmpty(), add = e => { if (e && isFinite(e[0]) && e[2] >= e[0]) ol.extent.extend(ex, e); };
  project.layers.forEach(l => { if (shown(l) && layerSrc[l.key]?.getFeatures().length) add(layerSrc[l.key].getExtent()); });
  if (terrSrc.getFeatures().length) add(terrSrc.getExtent());
  if (!isFinite(ex[0])) return toast("Показывать нечего: на карте пока нет объектов.");
  sharedView.fit(ex, { padding: [40, 40, 40, 40], maxZoom: 18, duration: 0 });
  note("Показано всё. Колесо — масштаб, перетаскивание — сдвиг.");
}
def("zoomall", "Показать всё", ["Z", "ZE", "ZOOM"], () => { zoomAll(); return { done: true }; });
def("point", "Точка", ["PO"], () => { const st = { need: "point", base: () => null, prompt: () => "Укажите точку (X;Y в МСК — с клавиатуры), Enter — завершить", point: w => addNew([newFeature("point", w)], "точка"), enter: () => { st.done = true; } }; return st; });
function chainCmd(prompt0, promptN, finishFn, tipFn) {               // замеры и граница: точки по очереди, Enter — итог
  return () => {
    const pts = [];
    const st = { need: "point", base: () => pts[pts.length - 1] || null, own: () => [pts], prompt: () => pts.length ? promptN : prompt0,
      point: w => { if (!pts.length || !G.same(w, pts[pts.length - 1], 1e-6)) pts.push(w); }, back: () => pts.pop(),
      enter: () => { finishFn(pts); st.done = true; }, dbl: () => st.enter(), tip: w => tipFn(pts, w),
      preview: w => pts.length >= 2 && finishFn.closed ? { polys: [[...pts, w, pts[0]]] } : { lines: pts.length ? [[...pts, w]] : [] } };
    return st;
  };
}
const distFin = pts => { if (pts.length < 2) return; const f = fLine(pts); f.set("label", `${f2(G.chainLen(pts))} м`); measureSrc.addFeature(f); note(`Расстояние ${f2(G.chainLen(pts))} м. Замер оставлен на карте, Esc стирает.`); };
const areaFin = pts => { if (pts.length < 3) return; const r = [...pts, pts[0]], A = Math.abs(G.area(r)), f = fPoly(r); f.set("label", `${fmt(A, 1)} м² · ${fmt(A / 1e4, 3)} га`); measureSrc.addFeature(f); note(`Площадь ${fmt(A, 1)} м², периметр ${f2(G.chainLen(r))} м. Esc стирает замер.`); };
areaFin.closed = true;
const terrFin = pts => { if (pts.length < 3) return; setTerritory(GJ.writeFeatureObject(new ol.Feature(new ol.geom.Polygon([[...pts, pts[0]].map(fromM)])))); toast("Граница задана. Выгрузка источников — окно «Данные»."); };
terrFin.closed = true;
def("dist", "Расстояние", ["DI"], chainCmd("Первая точка", "Следующая точка, Enter — итог", distFin, (p, w) => p.length ? [`всего ${f2(G.chainLen([...p, w]))} м`] : []));
def("area", "Площадь", ["AA"], chainCmd("Первая вершина", "Следующая вершина, Enter — итог", areaFin, (p, w) => p.length >= 2 ? [`площадь ${fmt(Math.abs(G.area([...p, w, p[0]])), 1)} м²`] : []));
def("terr", "Граница территории", ["BO"], chainCmd("Первый угол границы территории", "Следующий угол, Enter — замкнуть границу", terrFin, (p, w) => p.length >= 2 ? [`${fmt(Math.abs(G.area([...p, w, p[0]])) / 1e4, 3)} га`] : []));

/* редактирование: перенос, копия, поворот, масштаб, зеркало — базовая точка, потом вторая, как в AutoCAD */
function transformCmd(kind) {
  return () => selection(items => {
    let base = null, p2 = null, copy = kind === "copy";
    const apply = (fn, k, flip, label, keep) => {
      const changes = [], adds = [];
      for (const { key, f } of items) {
        const g = xformGeom(f.getGeometry(), fn), cad = xformCad(f.get("_cad"), fn, k, flip);
        if (keep) adds.push({ key, f: copyFeat(f, g, cad ? { _cad: cad } : {}) }); else changes.push({ key, f, geom: g, cad });
      }
      edit(changes, adds, label); if (!keep) setSel(items);
    };
    const fnFor = w => kind === "move" || kind === "copy" ? G.T.move(G.sub(w, base)) : kind === "rotate" ? G.T.rotate(base, G.ang(base, w)) : kind === "scale" ? G.T.scale(base, G.dist(base, w)) : G.T.mirror(base, w);
    const st = { need: "point", base: () => base,
      prompt: () => !base ? (kind === "mirror" ? "Первая точка оси отражения" : "Базовая точка") :
        kind === "move" ? "Вторая точка: щелчок, @dx;dy или длина по направлению курсора" : kind === "copy" ? "Вторая точка копии (можно несколько), Enter — завершить" :
        kind === "rotate" ? `Угол поворота: число (°, против часовой) или точка${optStr(st.opts())}` : kind === "scale" ? `Масштаб: число или точка (расстояние = масштаб)${optStr(st.opts())}` : "Вторая точка оси отражения",
      opts: () => base && (kind === "rotate" || kind === "scale") ? [opt(copy ? "Без копии (К)" : "Копия (К)", ["к", "копия", "c", "copy"], () => { copy = !copy; }),
        ...(kind === "scale" ? [opt("Опорный отрезок (О)", ["о", "опорный", "r", "reference"], () => { st.ref = null; st.need = "value"; })] : [])] : [],
      valueFirst: () => !!base && (kind === "rotate" || kind === "scale"),
      value: v => {
        if (kind === "rotate") { apply(G.T.rotate(base, v * DEG), 1, false, "поворот", copy); st.done = true; return; }
        if (kind === "scale") {
          if (st.need === "value" && st.ref == null) { if (v <= 0) return note("Длина — больше нуля."); st.ref = v; return; }
          const k = st.ref != null ? v / st.ref : v; if (k <= 0) return note("Масштаб — положительное число."); apply(G.T.scale(base, k), k, false, "масштаб", copy); st.done = true;
        }
      },
      point: w => {
        if (!base) { base = w; return; }
        if (kind === "mirror") {
          if (G.dist(base, w) < 1e-6) return; p2 = w; st.need = "value";
          st.prompt = () => "Удалить исходные объекты? [Да (Д) / Нет (Н)] <Нет>";
          st.opts = () => [opt("Да", ["д", "да", "y", "yes"], () => { apply(G.T.mirror(base, p2), 1, true, "зеркало", false); st.done = true; }), opt("Нет", ["н", "нет", "n", "no"], () => { apply(G.T.mirror(base, p2), 1, true, "зеркало", true); st.done = true; })];
          st.enter = () => { apply(G.T.mirror(base, p2), 1, true, "зеркало", true); st.done = true; }; st.value = () => note("Ответьте Д или Н."); return;
        }
        if (kind === "rotate") { apply(G.T.rotate(base, G.ang(base, w)), 1, false, "поворот", copy); st.done = true; return; }
        if (kind === "scale") { const k = G.dist(base, w); if (k < 1e-9) return; apply(G.T.scale(base, k), k, false, "масштаб", copy); st.done = true; return; }
        apply(G.T.move(G.sub(w, base)), 1, false, copy ? "копия" : "перенос", copy); if (!copy) st.done = true;
      },
      enter: () => { st.done = true; },
      preview: w => base && G.dist(base, w) > 1e-9 ? { ghosts: ghosts(items, fnFor(w), base), lines: [[base, w]], pts: [base] } : {},
      tip: w => base ? kind === "rotate" ? [`поворот ${a1(G.ang(base, w))}°`] : kind === "scale" ? [`масштаб × ${fmt(G.dist(base, w), 3)}`] : [] : [] };
    const p0 = st.prompt; st.prompt = () => kind === "scale" && st.need === "value" ? (st.ref == null ? "Длина опорного отрезка, м" : "Новая длина, м") : p0();
    return st;
  });
}
def("move", "Перенести", ["M"], transformCmd("move"));
def("copy", "Копировать", ["CO", "CP"], transformCmd("copy"));
def("rotate", "Повернуть", ["RO"], transformCmd("rotate"));
def("scale", "Масштаб", ["SC"], transformCmd("scale"));
def("mirror", "Зеркало", ["MI"], transformCmd("mirror"));
def("erase", "Удалить", ["E"], () => selection(items => { edit(items.map(it => ({ ...it, remove: true })), [], items.length > 1 ? `удаление ${items.length} об.` : "удаление"); setSel([]); return { done: true }; }));

def("offset", "Подобие", ["O"], () => {
  let d = MEM.__cadOffset || 5, pick = null;
  const offCh = w => { const cad = pick.f.get("_cad"); if (cad?.c) { const r = cad.r + (G.dist(w, cad.c) > cad.r ? d : -d); return r > 0 ? { ch: cad.t === "circle" ? G.circlePts(cad.c, r) : G.arcPts({ ...cad, r }, 0.01), cad: { ...cad, r } } : null; } const ch = G.offset(pick.ch, G.side(pick.ch, w) * d); return ch ? { ch } : null; };
  const st = { need: "value", base: () => null,
    prompt: () => st.need === "value" ? `Расстояние подобия, м <${fmt(d, 2)}>` : !pick ? "Выберите линию или контур, Enter — завершить" : "Укажите сторону, с которой строить подобие",
    value: v => { if (v <= 0) return note("Расстояние — больше нуля."); d = MEM.__cadOffset = v; st.need = "obj"; },
    enter: () => { if (st.need === "value") { st.need = "obj"; return; } st.done = true; },
    pick: (h, pos) => { const p = pickChain(h, pos); if (!p) return note("Подобие строится для линий и контуров."); pick = p; st.need = "point"; },
    point: w => {
      const r = offCh(w); if (!r) return note("Подобие на эту сторону не строится (радиус получается нулевым).");
      const g = /Polygon/.test(pick.t) ? new ol.geom.Polygon([r.ch.map(fromM)]) : new ol.geom.LineString(r.ch.map(fromM));
      addNew([{ key: pick.key, f: copyFeat(pick.f, g, r.cad ? { _cad: r.cad } : {}) }], "подобие"); pick = null; st.need = "obj";
    },
    preview: w => { const r = pick && offCh(w); return r ? { lines: [r.ch] } : {}; } };
  return st;
});
function trimInfo(pos) {
  const h = hitAt(mMain.getPixelFromCoordinate(pos.c)); if (!h) return null;
  const p = pickChain(h, pos, "map"); if (!p) return null;
  const cuts = G.cutsAlong(p.ch, boundaries(p.f, 300)), L = G.chainLen(p.ch);
  return { p, cuts, L };
}
def("trim", "Обрезать", ["TR"], () => {
  let memo = null;
  const info = pos => { const h = hitAt(mMain.getPixelFromCoordinate(pos.c)); if (!h) return null; if (memo?.f !== h.f) { const t = trimInfo(pos); memo = t && { f: h.f, ...t }; } if (!memo) return null; return { ...memo, p: { ...memo.p, q: G.nearest(memo.p.ch, pos.c) } }; };
  const st = { need: "obj", prompt: () => "Щёлкните по части линии, которую нужно отрезать (режущие кромки — все видимые объекты), Enter — завершить",
    objTip: () => prevSrc.getFeatures().some(f => f.get("k") === "gone") ? "щелчок — отрезать красное" : "наведите на отрезаемую часть",
    enter: () => { st.done = true; },
    pick: (h, pos) => {
      const t = info(pos); if (!t) return note("Обрезаются линии и контуры.");
      const { p, cuts } = t, pieces = G.trim(p.ch, p.q.s, cuts); memo = null;
      if (!pieces) return note("Здесь нечего отрезать: у этого участка нет пересечений с другими объектами.");
      if (/Polygon/.test(p.t)) {                                   // контур после обрезки не замкнут — уходит в слой линий
        const lk = targetLayer("line").key;
        // остальные кольца и части объекта (двор-дыра, второй участок мультиполигона) переходят в линии целиком
        const rest = chainsOf(p.f.getGeometry()).filter((c, i) => i !== p.i && c.length > 1);
        edit([{ key: p.key, f: p.f, remove: true }], [...pieces, ...rest].map(c => ({ key: lk, f: copyFeat(p.f, new ol.geom.LineString(c)) })), "обрезка");
        toast("Обрезанный контур больше не замкнут — он перенесён в слой линий."); return;
      }
      piecesEdit(p, pieces, "обрезка");
    },
    previewObj: pos => {
      const t = info(pos); if (!t) return [];
      const { p, cuts, L } = t, inner = cuts.filter(x => x > 1e-7 && x < L - 1e-7);
      if (!inner.length) return [];
      const line = (a, b) => new ol.Feature({ geometry: new ol.geom.LineString(G.sliceChain(p.ch, a, b)), k: "gone" });
      if (G.closed(p.ch)) {                                            // замкнутый контур — то же, что отрежет G.trim
        if (inner.length < 2) return [];
        const below = inner.filter(x => x < p.q.s), above = inner.filter(x => x > p.q.s);
        const a = below.length ? below[below.length - 1] : inner[inner.length - 1], b = above.length ? above[0] : inner[0];
        return a < b ? [line(a, b)] : [line(a, L), line(0, b)];
      }
      const s = p.q.s, lo = Math.max(0, ...inner.filter(x => x < s)), hi = Math.min(L, ...inner.filter(x => x > s));
      return [new ol.Feature({ geometry: new ol.geom.LineString(G.sliceChain(p.ch, lo, hi)), k: "gone" })];
    } };
  return st;
});
def("extend", "Удлинить", ["EX"], () => {
  const ext = pos => { const h = hitAt(mMain.getPixelFromCoordinate(pos.c)); if (!h) return null; const p = pickChain(h, pos, "map"); if (!p || G.closed(p.ch)) return null; const atStart = G.dist(pos.c, p.ch[0]) < G.dist(pos.c, p.ch[p.ch.length - 1]); return { p, ch: G.extend(p.ch, atStart, boundaries(p.f, 3000)), atStart }; };
  const st = { need: "obj", prompt: () => "Щёлкните у конца линии, которую нужно удлинить до ближайшего объекта, Enter — завершить",
    objTip: () => prevSrc.getFeatures().some(f => f.get("k") === "ghost") ? "щелчок — удлинить по пунктиру" : "наведите у конца линии",
    enter: () => { st.done = true; },
    pick: (h, pos) => { const r = ext(pos); if (!r) return note("Удлиняются незамкнутые линии."); if (!r.ch) return note("По направлению линии нет объекта, до которого её можно удлинить."); edit([{ key: r.p.key, f: r.p.f, geom: replaced(r.p, [r.ch]), cad: null }], [], "удлинение"); },
    previewObj: pos => { const r = ext(pos); if (!r?.ch) return []; const e = r.atStart ? [r.ch[0], r.p.ch[0]] : [r.p.ch[r.p.ch.length - 1], r.ch[r.ch.length - 1]]; return [new ol.Feature({ geometry: new ol.geom.LineString(e), k: "ghost" })]; } };
  return st;
});
def("break", "Разорвать", ["BR"], () => {
  let p = null;
  const st = { need: "obj", prompt: () => p ? "Вторая точка разрыва" : "Щёлкните по линии в первой точке разрыва",
    pick: (h, pos) => { p = pickChain(h, pos, "map"); if (!p || /Polygon/.test(p.t)) { p = null; return note("Разрываются линии (контур сначала расчлените: X)."); } st.need = "point"; },
    base: () => p ? toM(p.q.p) : null,
    point: w => { const q = G.nearest(p.ch, fromM(w)); piecesEdit(p, G.breakChain(p.ch, p.q.s, q.s), "разрыв"); st.done = true; },
    preview: w => { const q = G.nearest(p.ch, fromM(w)), a = Math.min(p.q.s, q.s), b = Math.max(p.q.s, q.s); return { ghosts: [new ol.Feature({ geometry: new ol.geom.LineString(G.sliceChain(p.ch, a, b)), k: "gone" })] }; } };
  return st;
});
def("fillet", "Сопряжение", ["F"], () => {
  let r = MEM.__cadFillet ?? 0, first = null, all = false;
  const st = { need: "obj",
    prompt: () => st.need === "value" ? `Радиус сопряжения, м <${fmt(r, 2)}>` : `${all ? "Выберите полилинию или контур — скруглить все углы" : first ? "Второй отрезок" : "Первый отрезок"} (радиус ${fmt(r, 2)} м)${optStr(st.opts())}`,
    opts: () => st.need === "value" ? [] : [opt("Радиус (Р)", ["р", "радиус", "r", "radius"], () => { st.need = "value"; }), opt("Полилиния (П)", ["п", "полилиния", "p", "polyline"], () => { all = true; first = null; })],
    value: v => { r = MEM.__cadFillet = Math.max(0, v); st.need = "obj"; },
    enter: () => { if (st.need === "value") { st.need = "obj"; return; } st.done = true; },
    pick: (h, pos) => {
      const p = pickChain(h, pos); if (!p) return note("Сопрягаются линии и контуры.");
      if (all) { if (r <= 0) return note("Для скругления всех углов задайте радиус: Р."); const res = G.filletAll(p.ch, r, 0.01); edit([{ key: p.key, f: p.f, geom: replaced(p, [res.pts]), cad: null }], [], "сопряжение"); note(`Скруглено углов: ${res.done}.`); st.done = true; return; }
      if (!first) { first = p; return; }
      const a = first, b = p; first = null;
      if (a.f === b.f && a.i === b.i) {                           // соседние отрезки одной полилинии — скругляется общая вершина
        const ch = a.ch, cl = G.closed(ch), n = cl ? ch.length - 1 : ch.length, i = a.q.i, j = b.q.i;
        const v = (i + 1) % n === j % n ? (i + 1) % n : (j + 1) % n === i % n ? (j + 1) % n : -1;
        if (v < 0 || (!cl && (v === 0 || v === n - 1))) return note("Выберите два соседних отрезка одной полилинии.");
        if (r === 0) return note("Угол полилинии уже острый: для скругления задайте радиус (Р).");
        const P = cl ? ch.slice(0, -1) : ch.slice(), f = G.filletCorner(P[(v - 1 + n) % n], P[v], P[(v + 1) % n], r);
        if (!f) return note("Радиус слишком велик для этих отрезков.");
        P.splice(v, 1, ...G.arcPts(f.arc, 0.01)); if (cl) P.push(P[0]);
        edit([{ key: a.key, f: a.f, geom: replaced(a, [P]), cad: null }], [], "сопряжение"); st.done = true; return;
      }
      if (a.f === b.f) return note("Выберите два разных объекта или два соседних отрезка одной полилинии.");
      if (G.closed(a.ch) || G.closed(b.ch)) return note("Для двух объектов выбирайте незамкнутые линии.");
      // два объекта: подрезать или продлить концевые отрезки до пересечения; при радиусе — дуга между ними
      const sa = [a.ch[a.q.i], a.ch[a.q.i + 1]], sb = [b.ch[b.q.i], b.ch[b.q.i + 1]], x = G.inter(sa[0], sa[1], sb[0], sb[1], true);
      if (!x) return note("Отрезки параллельны — сопряжение не строится.");
      // конец, который уходит к углу: щёлкнутая часть отрезка остаётся, как в AutoCAD
      const endOf = p => { const L = p.ch.length - 1, a0 = p.ch[p.q.i], d = G.sub(p.ch[p.q.i + 1], a0), sx = G.dot(G.sub(x.p, a0), d), sp = G.dot(G.sub(p.q.p, a0), d), toEnd = sx >= sp;
        if (toEnd && p.q.i === L - 1) return L; if (!toEnd && p.q.i === 0) return 0; return -1; };
      const ea = endOf(a), eb = endOf(b); if (ea < 0 || eb < 0) return note("Выбирайте концевые отрезки линий.");
      const far = (p, e) => p.ch[e === 0 ? 1 : p.ch.length - 2];
      let ta = x.p, tb = x.p, arc = null;
      if (r > 0) { const f = G.filletCorner(far(a, ea), x.p, far(b, eb), r); if (!f) return note("Радиус слишком велик для этих отрезков."); ta = f.t1; tb = f.t2; arc = f.arc; }
      const ca = a.ch.slice(), cb = b.ch.slice(); ca[ea] = ta; cb[eb] = tb;
      edit([{ key: a.key, f: a.f, geom: replaced(a, [ca]), cad: null }, { key: b.key, f: b.f, geom: replaced(b, [cb]), cad: null }], arc ? [newFeature("line", G.arcPts(arc, 0.01), null, { _cad: { t: "arc", ...arc } })] : [], "сопряжение");
      st.done = true;
    } };
  return st;
});
def("chamfer", "Фаска", ["CHA"], () => {
  let d1 = MEM.__cadCh1 ?? 1, d2 = MEM.__cadCh2 ?? 1, first = null, all = false, ask = 0;
  const st = { need: "obj",
    prompt: () => ask === 1 ? `Длина фаски на первом отрезке, м <${fmt(d1, 2)}>` : ask === 2 ? `Длина фаски на втором отрезке, м <${fmt(d2, 2)}>` : `${all ? "Выберите полилинию или контур — фаски на всех углах" : first ? "Второй отрезок" : "Первый отрезок"} (длины ${fmt(d1, 2)} и ${fmt(d2, 2)} м)${optStr(st.opts())}`,
    opts: () => ask ? [] : [opt("Длины (Д)", ["д", "длины", "d", "distance"], () => { ask = 1; st.need = "value"; }), opt("Полилиния (П)", ["п", "полилиния", "p", "polyline"], () => { all = true; first = null; })],
    value: v => { if (v < 0) return note("Длина — не меньше нуля."); if (ask === 1) { d1 = MEM.__cadCh1 = v; d2 = MEM.__cadCh2 = v; ask = 2; return; } d2 = MEM.__cadCh2 = v; ask = 0; st.need = "obj"; },
    enter: () => { if (ask === 1) { ask = 2; return; } if (ask === 2) { ask = 0; st.need = "obj"; return; } st.done = true; },
    pick: (h, pos) => {
      const p = pickChain(h, pos); if (!p) return note("Фаска строится на линиях и контурах.");
      if (all) { const r = G.chamferAll(p.ch, d1, d2); edit([{ key: p.key, f: p.f, geom: replaced(p, [r.pts]), cad: null }], [], "фаска"); note(`Фасок: ${r.done}.`); st.done = true; return; }
      if (!first) { first = p; return; }
      const a = first, b = p; first = null;
      if (a.f === b.f && a.i === b.i) {
        const ch = a.ch, cl = G.closed(ch), n = cl ? ch.length - 1 : ch.length, i = a.q.i, j = b.q.i;
        const v = (i + 1) % n === j % n ? (i + 1) % n : (j + 1) % n === i % n ? (j + 1) % n : -1;
        if (v < 0 || (!cl && (v === 0 || v === n - 1))) return note("Выберите два соседних отрезка одной полилинии.");
        const P = cl ? ch.slice(0, -1) : ch.slice(), first1 = (i + 1) % n === v, c = G.chamferCorner(P[(v - 1 + n) % n], P[v], P[(v + 1) % n], first1 ? d1 : d2, first1 ? d2 : d1);
        if (!c) return note("Длины фаски больше отрезков.");
        P.splice(v, 1, c.t1, c.t2); if (cl) P.push(P[0]);
        edit([{ key: a.key, f: a.f, geom: replaced(a, [P]), cad: null }], [], "фаска"); st.done = true; return;
      }
      if (a.f === b.f || G.closed(a.ch) || G.closed(b.ch)) return note("Выберите две незамкнутые линии или два соседних отрезка одной полилинии.");
      const x = G.inter(a.ch[a.q.i], a.ch[a.q.i + 1], b.ch[b.q.i], b.ch[b.q.i + 1], true); if (!x) return note("Отрезки параллельны — фаска не строится.");
      const endOf = p => { const L = p.ch.length - 1, a0 = p.ch[p.q.i], d = G.sub(p.ch[p.q.i + 1], a0), toEnd = G.dot(G.sub(x.p, a0), d) >= G.dot(G.sub(p.q.p, a0), d); if (toEnd && p.q.i === L - 1) return L; if (!toEnd && p.q.i === 0) return 0; return -1; };
      const ea = endOf(a), eb = endOf(b); if (ea < 0 || eb < 0) return note("Выбирайте концевые отрезки линий.");
      const far = (p, e) => p.ch[e === 0 ? 1 : p.ch.length - 2], c = G.chamferCorner(far(a, ea), x.p, far(b, eb), d1, d2);
      if (!c) return note("Длины фаски больше отрезков.");
      const ca = a.ch.slice(), cb = b.ch.slice(); ca[ea] = c.t1; cb[eb] = c.t2;
      edit([{ key: a.key, f: a.f, geom: replaced(a, [ca]), cad: null }, { key: b.key, f: b.f, geom: replaced(b, [cb]), cad: null }], G.dist(c.t1, c.t2) > 1e-6 ? [newFeature("line", [c.t1, c.t2])] : [], "фаска");
      st.done = true;
    } };
  return st;
});
// МАССИВ: прямоугольный (ряды × столбцы) или круговой (вокруг центра); копии — обычные объекты
def("array", "Массив", ["AR"], o => selection(items => {
  const ext = items.reduce((e, it) => ol.extent.extend(e, it.f.getGeometry().getExtent()), ol.extent.createEmpty());
  const lo = toM(ol.extent.getBottomLeft(ext)), hi = toM(ol.extent.getTopRight(ext)), w = Math.max(1, hi[0] - lo[0]), h = Math.max(1, hi[1] - lo[1]);
  const P = { kind: null, rows: 1, cols: 4, dr: +(h * 1.5).toFixed(2), dc: +(w * 1.5).toFixed(2), n: 6, fill: 360, rot: true, c: null, ...(o?.edit?.P || {}) };
  const arrId = o?.edit?.id || "a" + Date.now().toString(36);
  const steps = { rect: ["cols", "rows", "dc", "dr"], polar: ["n", "fill"] }, LBL = { cols: "Число столбцов", rows: "Число рядов", dc: "Расстояние между столбцами, м", dr: "Расстояние между рядами, м", n: "Число элементов", fill: "Угол заполнения, °" };
  let k = 0;
  const cen = toM(ol.extent.getCenter(ext));
  const fns = (Q = P) => {
    if (Q.kind === "rect") { const out = []; for (let r = 0; r < Q.rows; r++) for (let c = 0; c < Q.cols; c++) if (r || c) out.push({ fn: G.T.move([c * Q.dc, r * Q.dr]) }); return out; }
    const out = [], step = (Q.fill >= 360 ? 360 / Q.n : Q.fill / Math.max(1, Q.n - 1)) * DEG;
    for (let i = 1; i < Q.n; i++) { const a = step * i; out.push({ fn: Q.rot ? G.T.rotate(Q.c, a) : G.T.move(G.sub(G.T.rotate(Q.c, a)(cen), cen)) }); }
    return out;
  };
  // копии-призраки при текущих числах (и при числе, которое набирается), не больше 400 объектов
  const shadow = Q => {
    if (!Q.kind || (Q.kind === "polar" && !Q.c)) return [];
    const list = fns(Q), per = Math.max(1, Math.floor(400 / items.length)), out = [];
    for (const { fn } of list.slice(0, per)) out.push(...ghosts(items, fn, cen));
    return out;
  };
  const make = () => {
    const adds = [];
    const par = { id: arrId, kind: P.kind, rows: P.rows, cols: P.cols, dr: P.dr, dc: P.dc, n: P.n, fill: P.fill, rot: P.rot, c: P.c };
    const list = fns();
    if (list.length * items.length > 20000) return note("Больше 20 000 копий — уменьшите массив.");
    list.forEach(({ fn }, i) => { for (const { key, f } of items) { const cad = xformCad(f.get("_cad"), fn); adds.push({ key, f: copyFeat(f, xformGeom(f.getGeometry(), fn), { ...(cad ? { _cad: cad } : {}), _arr: { id: arrId, i: i + 1 } }) }); } });
    if (adds.length > 20000) return note("Больше 20 000 копий — уменьшите массив.");
    // массив остаётся массивом: исходные объекты помнят его параметры, копии — номер; AE меняет числа и пересобирает копии
    const old = (o?.edit?.copies || []).map(x => ({ ...x, remove: true }));
    edit([...old, ...items.map(({ key, f }) => ({ key, f, props: { _arr: { ...par, src: true } } }))], adds, o?.edit ? "правка массива" : "массив");
    note(`${o?.edit ? "Массив пересобран" : "Массив"}: ${adds.length} копий. Изменить числа потом — команда AE (правка массива).`); st.done = true;
  };
  const cur = () => steps[P.kind][k];
  const st = { need: "value",
    prompt: () => !P.kind ? "Тип массива [Прямоугольный (П) / Круговой (К)] <П>" : P.kind === "polar" && !P.c ? "Центр кругового массива" : k < steps[P.kind].length ? `${LBL[cur()]} <${fmt(P[cur()], cur() === "dr" || cur() === "dc" ? 2 : 0)}>` : `Поворачивать элементы? [Да (Д) / Нет (Н)] <Да>`,
    opts: () => !P.kind ? [opt("Прямоугольный (П)", ["п", "прямоугольный", "r", "rectangular"], () => { P.kind = "rect"; }), opt("Круговой (К)", ["к", "круговой", "p", "polar"], () => { P.kind = "polar"; st.need = "point"; })]
      : P.kind === "polar" && P.c && k >= steps.polar.length ? [opt("Да", ["д", "да", "y"], () => { P.rot = true; make(); }), opt("Нет", ["н", "нет", "n"], () => { P.rot = false; make(); })] : [],
    base: () => P.c,
    point: w => { P.c = w; st.need = "value"; },
    value: v => {
      if (!P.kind) return note("Выберите П или К.");
      const key = cur(); if (!key) return;
      if (["cols", "rows", "n"].includes(key) && (!Number.isInteger(v) || v < 1)) return note("Нужно целое число, не меньше 1.");
      P[key] = v; k++;
      if (P.kind === "rect" && k >= steps.rect.length) make();
    },
    enter: () => {
      if (!P.kind) { P.kind = "rect"; return; }
      if (P.kind === "polar" && !P.c) return;
      if (k < steps[P.kind].length) { k++; if (P.kind === "rect" && k >= steps.rect.length) make(); return; }
      make();
    },
    // до указания центра кругового массива копии разворачиваются вокруг курсора
    preview: w => P.kind === "polar" && !P.c ? { ghosts: shadow({ ...P, c: w }), pts: [w] } : {},
    still: tv => {
      if (P.kind === "polar" && !P.c) return [];
      const Q = { ...P }, key = P.kind && cur();
      if (key && tv != null && (["cols", "rows", "n"].includes(key) ? Number.isInteger(tv) && tv >= 1 : key === "fill" ? tv > 0 : tv !== 0)) Q[key] = tv;
      return shadow(Q);
    } };
  return st;
}));
// ПРАВКА МАССИВА (ARRAYEDIT): щелчок по любому элементу массива — те же вопросы с прежними числами, копии пересобираются
function arrayGroup(id) {
  const out = { src: [], copies: [] };
  for (const l of project.layers) layerSrc[l.key]?.getFeatures().forEach(f => { const a = f.get("_arr"); if (a?.id === id) (a.src ? out.src : out.copies).push({ key: l.key, f }); });
  return out;
}
def("arrayedit", "Правка массива", ["AE", "ARRAYEDIT"], () => ({ need: "obj",
  prompt: () => "Щёлкните по любому элементу массива",
  pick(h) {
    const a = h.f.get("_arr"); if (!a) return note("Это не элемент массива: массивы, построенные командой AR с этой версии, помнят свои числа.");
    const g = arrayGroup(a.id); if (!g.src.length) return note("Исходные объекты массива удалены — пересобрать нельзя.");
    const P = { ...g.src[0].f.get("_arr") }; delete P.src; delete P.id;
    setSel(g.src); const next = CMDS.array.make({ edit: { id: a.id, P, copies: g.copies } }); next.id = "array"; CMD = next;
    note(`Массив: ${g.src.length} исходных объектов, ${g.copies.length} копий. Enter — оставить число как было.`);
  } }));
// РАСТЯНУТЬ: вершины внутри секущей рамки двигаются, объекты целиком внутри — переносятся
def("stretch", "Растянуть", ["S"], () => {
  let c1 = null, box = null, base = null, hits = null;
  const inBox = w => w[0] >= box[0] && w[0] <= box[2] && w[1] >= box[1] && w[1] <= box[3];
  const collect = () => {
    const ext = ol.extent.boundingExtent([fromM([box[0], box[1]]), fromM([box[2], box[1]]), fromM([box[2], box[3]]), fromM([box[0], box[3]])]), out = [];
    for (const l of project.layers) { if (!shown(l) || outOfScale(l)) continue; layerSrc[l.key].forEachFeatureIntersectingExtent(ext, f => { if (out.length < 2000 && chainsOf(f.getGeometry()).some(ch => ch.some(c => inBox(toM(c))))) out.push({ key: l.key, f }); }); }
    return out;
  };
  const moved = (g, d) => { const g2 = g.clone(); g2.applyTransform((inp, out, dim = 2) => { for (let i = 0; i < inp.length; i += dim) { const w = toM([inp[i], inp[i + 1]]); const c = inBox(w) ? fromM(G.add(w, d)) : [inp[i], inp[i + 1]]; out[i] = c[0]; out[i + 1] = c[1]; } return out; }); return g2; };
  const st = { need: "point", base: () => base || c1,
    prompt: () => !c1 ? "Первый угол секущей рамки (захватите вершины, которые нужно сдвинуть)" : !box ? "Противоположный угол рамки" : !base ? `Базовая точка (захвачено объектов: ${hits.length})` : "Вторая точка: щелчок, @dx;dy или длина по направлению курсора",
    point: w => {
      if (!c1) { c1 = w; return; }
      if (!box) { box = [Math.min(c1[0], w[0]), Math.min(c1[1], w[1]), Math.max(c1[0], w[0]), Math.max(c1[1], w[1])]; hits = collect(); if (!hits.length) { c1 = box = null; note("В рамку не попала ни одна вершина — укажите рамку заново."); } return; }
      if (!base) { base = w; return; }
      const d = G.sub(w, base);
      edit(hits.map(({ key, f }) => { const all = chainsOf(f.getGeometry()).every(ch => ch.every(c => inBox(toM(c)))), cad = f.get("_cad"); return { key, f, geom: moved(f.getGeometry(), d), cad: all && cad ? xformCad(cad, G.T.move(d)) : null }; }), [], "растянуть");
      st.done = true;
    },
    preview: w => {
      if (c1 && !box) return { polys: [[c1, [w[0], c1[1]], w, [c1[0], w[1]], c1]] };
      if (base && hits) { const a = fromM(base), b = fromM(w), dm = [b[0] - a[0], b[1] - a[1]], bxM = [fromM([box[0], box[1]]), fromM([box[2], box[3]])];
        const inM = c => c[0] >= Math.min(bxM[0][0], bxM[1][0]) && c[0] <= Math.max(bxM[0][0], bxM[1][0]) && c[1] >= Math.min(bxM[0][1], bxM[1][1]) && c[1] <= Math.max(bxM[0][1], bxM[1][1]);
        return { ghosts: hits.slice(0, 400).map(({ f }) => { const g = f.getGeometry().clone(); g.applyTransform((inp, out, dim = 2) => { for (let i = 0; i < inp.length; i += dim) { const inside = inM([inp[i], inp[i + 1]]); out[i] = inp[i] + (inside ? dm[0] : 0); out[i + 1] = inp[i + 1] + (inside ? dm[1] : 0); } return out; }); return new ol.Feature({ geometry: g, k: "ghost" }); }), lines: [[base, w]], pts: [base] }; }
      return {};
    } };
  return st;
});
// УВЕЛИЧИТЬ: удлинить или укоротить конец линии на приращение или до полной длины
def("lengthen", "Увеличить", ["LEN"], () => {
  let delta = MEM.__cadLen ?? 1, total = null;
  const st = { need: "value",
    prompt: () => st.need === "value" ? (total != null ? `Полная длина, м <${fmt(total, 2)}>` : `Приращение, м (минус — укоротить) <${fmt(delta, 2)}>${optStr(st.opts())}`) : `Щёлкните у конца линии: ${total != null ? `полная длина ${fmt(total, 2)} м` : `приращение ${fmt(delta, 2)} м`}, Enter — завершить`,
    opts: () => st.need === "value" && total == null ? [opt("Всего (В)", ["в", "всего", "t", "total"], () => { total = 0; })] : [],
    value: v => { if (total != null) { if (v <= 0) return note("Длина — больше нуля."); total = v; } else delta = MEM.__cadLen = v; st.need = "obj"; },
    enter: () => { if (st.need === "value") { st.need = "obj"; return; } st.done = true; },
    pick: (h, pos) => {
      const p = pickChain(h, pos); if (!p || G.closed(p.ch)) return note("Увеличиваются незамкнутые линии.");
      const atStart = G.dist(pos.w, p.ch[0]) < G.dist(pos.w, p.ch[p.ch.length - 1]), d = total != null ? total - G.chainLen(p.ch) : delta;
      const ch = G.lengthen(p.ch, atStart, d); if (!ch) return note("Укоротить на столько нельзя: линия короче.");
      edit([{ key: p.key, f: p.f, geom: replaced(p, [ch]), cad: null }], [], "увеличить");
    } };
  return st;
});
// РУЧКА: щелчок по ручке, затем щелчок в новом месте (или перетаскивание); привязки, отслеживание, орто и ввод работают
/* правка границы территории: та же запись отмены, что у слоёв, но путь через setTerritory (площадь, версия, граф, сохранение, совместная работа) */
// допустима ли граница после правки: причина отказа простыми словами или null
function terrFault(gj) {
  const polys = gj.geometry.type === "Polygon" ? [gj.geometry.coordinates] : gj.geometry.type === "MultiPolygon" ? gj.geometry.coordinates : [];
  if (!polys.length || polys.flat(3).some(v => !Number.isFinite(v))) return "граница стала пустой";
  if (turf.kinks(gj).features.length) return "Граница не может пересекать сама себя";
  if (!(turf.area(gj) > 0.01)) return "Граница не может иметь нулевую площадь";
  for (const rings of polys) for (const hole of rings.slice(1)) if (hole.some(v => !turf.booleanPointInPolygon(v, turf.polygon([rings[0]])))) return "Дыра в границе должна лежать внутри контура";
  return null;
}
function terrEdit(geom, label) {
  if (!project.territory) return;
  if (terrLocked()) return result("Только просмотр: границу правит владелец или редактор проекта.");
  const gj = GJ.writeFeatureObject(new ol.Feature(geom)), bad = terrFault(gj);
  if (bad) return result(`${bad} — вершина возвращена на место.`);
  setTerritory(gj, { keep: true });
  result(`Граница территории: ${label}, площадь ${fmt(terrArea() / 1e4, 3)} га.${UNDO_TAIL()}`);
}
const put = (changes, label) => changes[0].key === "@terr" ? terrEdit(changes[0].geom, label) : edit(changes, [], label);
def("grip", "Ручка", [], o => {
  const g = o.g, f = g.get("f"), key = g.get("key"), path = g.get("path"), mid = !!g.get("mid"), closed = g.get("closed"), orig = f.getGeometry();
  const baseW = toM(g.getGeometry().getCoordinates());
  const build = (c, remove) => {
    const coords = JSON.parse(JSON.stringify(orig.getCoordinates())), last = path[path.length - 1];
    let arr = coords; for (const i of path.slice(0, -1)) arr = arr[i];
    if (mid) arr.splice(last, 0, c);
    else if (remove) { arr.splice(last, 1); if (closed && last === 0) arr[arr.length - 1] = arr[0].slice(); }
    else if (!path.length) return new ol.geom.Point(c);
    else { arr[last] = c; if (closed && last === 0) arr[arr.length - 1] = c.slice(); }
    const g2 = orig.clone(); g2.setCoordinates(coords); return g2;
  };
  let skip = true;
  /* ТОПО: та же вершина у соседних объектов (в пределах 1 мм на местности) переносится вместе — граница двух участков
     остаётся общей, без щели и нахлёста, как в топологическом редактировании QGIS */
  const oldC = fromM(baseW), tol = .001 / Math.cos(ol.proj.toLonLat(oldC)[1] * Math.PI / 180);
  const mates = mid || !path.length || !ST.topo || key === "@terr" ? [] : (() => { const out = [];
    for (const l of project.layers) { if (!shown(l) || outOfScale(l)) continue;
      layerSrc[l.key].forEachFeatureInExtent(ol.extent.buffer([oldC[0], oldC[1], oldC[0], oldC[1]], tol), o => { if (o === f || /Point/.test(o.getGeometry().getType())) return; out.push({ key: l.key, f: o }); }); }
    return out; })();
  const shared = c => mates.map(m => { const cc = JSON.parse(JSON.stringify(m.f.getGeometry().getCoordinates())); let hit = false;
    const walk = a => { if (typeof a[0] === "number") { if (Math.abs(a[0] - oldC[0]) <= tol && Math.abs(a[1] - oldC[1]) <= tol) { a[0] = c[0]; a[1] = c[1]; hit = true; } return; } a.forEach(walk); };
    walk(cc); if (!hit) return null; const g2 = m.f.getGeometry().clone(); g2.setCoordinates(cc); return { key: m.key, f: m.f, geom: g2, cad: null }; }).filter(Boolean);
  const st = { need: "point", base: () => baseW,
    prompt: () => mid ? "Новая вершина: щелчок, @dx;dy или X;Y (Esc — отмена)" : `Новое положение вершины: щелчок, @dx;dy или X;Y${optStr(st.opts())} (Esc — отмена)`,
    opts: () => mid || !path.length ? [] : [opt("Удалить вершину (У)", ["у", "удалить", "d", "delete"], () => {
      const n = g.get("n"), min = closed ? 3 : 2; if (n <= min) return note(`Удалить нельзя: у ${closed ? "контура" : "линии"} останется меньше ${min} вершин.`);
      put([{ key, f, geom: build(null, true), cad: null }], "удаление вершины"); st.done = true; })],
    point: (w, how) => { if (skip && how?.click && !st.moved) { skip = false; return; } put([{ key, f, geom: build(fromM(w)), cad: null }, ...shared(fromM(w))], mid ? "новая вершина" : "перенос вершины"); st.done = true; },
    enter: () => { st.done = true; },
    preview: w => ({ ghosts: [new ol.Feature({ geometry: build(fromM(w)), k: "ghost" }), ...shared(fromM(w)).map(x => new ol.Feature({ geometry: x.geom, k: "ghost" }))], lines: [[baseW, w]] }) };
  return st;
});
def("join", "Соединить", ["J"], () => selection(items => {
  const lines = items.filter(it => /LineString/.test(it.f.getGeometry().getType()));
  if (lines.length < 2) { note("Для соединения выберите две и больше линии с общими концами."); return { done: true }; }
  // соединяются только линии, у которых есть общий конец с другой выбранной; остальные остаются как были, со своими полями и слоем
  const ends = it => worldChains(it.f).flatMap(c => [c[0], c[c.length - 1]]);
  const part = lines.filter(a => lines.some(b => b !== a && ends(a).some(p => ends(b).some(q => G.same(p, q, 0.001)))));
  const chains = part.flatMap(it => worldChains(it.f)), merged = G.join(chains, 0.001);
  if (part.length < 2 || merged.length >= chains.length) { note("У выбранных линий нет общих концов (допуск 1 мм)."); return { done: true }; }
  const key = part[0].key, adds = merged.map(c => ({ key, f: copyFeat(part[0].f, new ol.geom.LineString(c.map(fromM))) }));
  edit(part.map(it => ({ ...it, remove: true })), adds, "соединение"); setSel(adds); note(`Соединено: ${chains.length} → ${merged.length}.`);
  return { done: true };
}));
def("explode", "Расчленить", ["X"], () => selection(items => {
  const adds = [], changes = [];
  for (const it of items) {
    const t = it.f.getGeometry().getType(); if (/Point/.test(t)) continue;
    const key = /Polygon/.test(t) ? targetLayer("line").key : it.key;
    chainsOf(it.f.getGeometry()).forEach(ch => { for (let i = 0; i + 1 < ch.length; i++) adds.push({ key, f: copyFeat(it.f, new ol.geom.LineString([ch[i], ch[i + 1]])) }); });
    changes.push({ ...it, remove: true });
  }
  if (changes.length) { edit(changes, adds, "расчленение"); setSel([]); note(`Получено отрезков: ${adds.length}.`); }
  return { done: true };
}));

/* ---------- работа с вектором, как в QGIS: разрезать, объединить, вычесть, буфер, свойства, деление, подобные ----------
   Геометрия — Turf в градусах (как в графе): площади и буферы в метрах на местности, стыки частей без зазоров. */
const gjOf = f => GJ.writeFeatureObject(f);
const polyParts = g => !g ? [] : g.geometry.type === "Polygon" ? [g.geometry.coordinates] : g.geometry.type === "MultiPolygon" ? g.geometry.coordinates : [];
const olPoly = c => GJ.readGeometry({ type: "Polygon", coordinates: c });
const polyItems = items => items.filter(it => /Polygon/.test(it.f.getGeometry().getType()));
const noteSkip = (all, used, what) => all.length > used.length ? ` Пропущено ${all.length - used.length}: ${what}.` : "";

def("split", "Разрезать", ["SPL", "SPLIT"], () => selection(items => {
  const polys = polyItems(items);
  if (!polys.length) { note("Разрезаются полигоны: выберите участки или зоны, потом проведите линию разреза."); return { done: true }; }
  const pts = [];
  const cut = () => {
    if (pts.length < 2) return note("Линия разреза — не меньше двух точек.");
    // сторона разреза — большой многоугольник слева от линии (концы продлены на 20 км): часть в нём и часть вне его
    const E = 20000, u0 = G.unit(G.sub(pts[0], pts[1])), u1 = G.unit(G.sub(pts[pts.length - 1], pts[pts.length - 2]));
    const a = G.add(pts[0], G.mul(u0, E)), b = G.add(pts[pts.length - 1], G.mul(u1, E)), d = G.unit(G.sub(b, a)), nrm = [-d[1], d[0]];
    const ring = [a, ...pts, b, G.add(b, G.mul(nrm, 2 * E)), G.add(a, G.mul(nrm, 2 * E)), a].map(w => ol.proj.toLonLat(fromM(w)));
    const side = turf.polygon([ring]);
    const changes = [], adds = []; let n = 0;
    for (const it of polys) {
      const f0 = gjOf(it.f), parts = [...polyParts(inter(f0, side)), ...polyParts(diff(f0, side))].filter(c => turf.area(turf.polygon(c)) > .01);
      if (parts.length < 2) continue;
      n++; changes.push({ key: it.key, f: it.f, geom: olPoly(parts[0]), cad: null });
      parts.slice(1).forEach(c => adds.push({ key: it.key, f: copyFeat(it.f, olPoly(c)) }));
    }
    if (!n) return note("Линия не пересекает выбранные полигоны насквозь — разрезать нечего.");
    edit(changes, adds, "разрез"); setSel([...changes, ...adds].map(x => ({ key: x.key, f: x.f })));
    note(`Разрезано полигонов: ${n}, частей стало ${changes.length + adds.length}. Атрибуты у всех частей — от исходного объекта.`);
  };
  const st = { need: "point", base: () => pts[pts.length - 1] || null, own: () => [pts],
    prompt: () => pts.length ? "Следующая точка линии разреза, Enter — разрезать" : `Первая точка линии разреза (полигонов выбрано ${polys.length}; линию ведите через контур насквозь)`,
    point: w => { if (!pts.length || !G.same(w, pts[pts.length - 1], 1e-6)) pts.push(w); }, back: () => pts.pop(),
    enter: () => { cut(); st.done = true; }, dbl: () => st.enter(),
    preview: w => ({ lines: pts.length ? [[...pts, w]] : [] }) };
  return st;
}));

def("merge", "Объединить", ["UNI", "MERGE"], () => selection(items => {
  const polys = polyItems(items), keys = new Set(polys.map(it => it.key));
  if (polys.length < 2) { note("Объединяются два и больше полигона одного слоя."); return { done: true }; }
  if (keys.size > 1) { note("Выбраны полигоны разных слоёв — объединяются только объекты одного слоя."); return { done: true }; }
  const u = unionAll(polys.map(it => gjOf(it.f)));
  if (!u) { note("Объединение не получилось: геометрия повреждена."); return { done: true }; }
  const parts = polyParts(u), g = parts.length === 1 ? olPoly(parts[0]) : GJ.readGeometry({ type: "MultiPolygon", coordinates: parts });
  edit([{ key: polys[0].key, f: polys[0].f, geom: g, cad: null }, ...polys.slice(1).map(it => ({ ...it, remove: true }))], [], "объединение");
  setSel([{ key: polys[0].key, f: polys[0].f }]);
  note(`Объединено ${polys.length} полигонов${parts.length > 1 ? ` (не касаются — один объект из ${parts.length} частей)` : ""}. Атрибуты — первого выбранного.${noteSkip(items, polys, "не полигоны")}`);
  return { done: true };
}));

def("subtract", "Вычесть", ["SU", "SUBTRACT"], () => selection(items => {
  const from = polyItems(items), cutters = [];
  if (!from.length) { note("Вычитание — из полигонов: выберите, из чего вычитать."); return { done: true }; }
  const st = { need: "obj", prompt: () => `Щёлкните полигоны, которые нужно вычесть (выбрано ${cutters.length}); Enter — вычесть`,
    pick: h => { if (!/Polygon/.test(h.f.getGeometry().getType())) return note("Вычитаемый объект — полигон.");
      if (from.some(it => it.f === h.f)) return note("Этот полигон — среди тех, из которых вычитают.");
      if (!cutters.includes(h.f)) cutters.push(h.f); },
    enter: () => {
      st.done = true; if (!cutters.length) return;
      const cutU = unionAll(cutters.map(gjOf)), changes = [];
      for (const it of from) {
        const r = diff(gjOf(it.f), cutU), parts = polyParts(r);
        if (!parts.length) { changes.push({ ...it, remove: true }); continue; }
        changes.push({ key: it.key, f: it.f, geom: parts.length === 1 ? olPoly(parts[0]) : GJ.readGeometry({ type: "MultiPolygon", coordinates: parts }), cad: null });
      }
      edit(changes, [], "вычитание"); note(`Вычтено из ${from.length} полигонов; вычитаемые объекты остались на месте (удалить — E).`);
    } };
  return st;
}));

def("buffer", "Буфер", ["BUF", "BUFFER"], () => selection(items => {
  let d = MEM.__cadBuf || 10;
  const run = () => {
    const l = targetLayer("poly"), adds = [];
    for (const it of items) { const r = buf(gjOf(it.f), d); polyParts(r).forEach(c => adds.push({ key: l.key, f: copyFeat(it.f, olPoly(c), { "Буфер, м": d }) })); }
    if (!adds.length) return note(d < 0 ? "Внутренний буфер съел объект целиком." : "Буфер не построен.");
    addNew(adds, "буфер"); note(`Буфер ${fmt(d, 2)} м: ${adds.length} полигонов в слое «${l.title}», атрибуты исходных объектов сохранены.`);
  };
  const st = { need: "value", prompt: () => `Ширина буфера, м (минус — внутрь полигона) <${fmt(d, 2)}>`,
    value: v => { if (!v) return note("Ширина буфера не может быть нулевой."); d = MEM.__cadBuf = v; run(); st.done = true; },
    enter: () => { run(); st.done = true; } };
  return st;
}));

def("matchprop", "Копировать свойства", ["MA", "MATCHPROP"], () => {
  let src = null;
  const own = p => Object.fromEntries(Object.entries(p).filter(([k]) => !k.startsWith("_") && k !== "gradosym"));
  const st = { need: "obj", prompt: () => src ? "Щёлкните объекты, которым передать атрибуты; Enter — завершить" : "Щёлкните объект-образец",
    pick: h => { if (!src) { src = own(propsOf(h.f)); return note(`Образец: полей ${Object.keys(src).length}. Теперь объекты-получатели.`); }
      edit([{ key: h.key, f: h.f, props: { ...src, _edited: true } }], [], "копирование свойств"); },
    enter: () => { st.done = true; } };
  return st;
});

// деление линии на N равных частей и разметка через шаг — точки в слой точек, как DIVIDE и MEASURE в AutoCAD
function markCmd(kind) {
  return () => { let v = kind === "div" ? MEM.__cadDiv || 5 : MEM.__cadMeas || 10, ask = true;
    const st = { need: "value", prompt: () => ask ? (kind === "div" ? `Число частей <${v}>` : `Шаг разметки, м <${fmt(v, 2)}>`) : "Щёлкните линию или контур; Enter — завершить",
      value: x => { if (kind === "div" ? !(x >= 2 && x <= 1000 && Number.isInteger(x)) : !(x > 0)) return note(kind === "div" ? "Число частей — целое от 2 до 1000." : "Шаг — больше нуля.");
        v = x; if (kind === "div") MEM.__cadDiv = x; else MEM.__cadMeas = x; ask = false; st.need = "obj"; },
      enter: () => { if (ask) { ask = false; st.need = "obj"; return; } st.done = true; },
      pick: (h, pos) => { const p = pickChain(h, pos); if (!p) return note("Делится линия или контур.");
        const L = G.chainLen(p.ch), step = kind === "div" ? L / v : v, n = kind === "div" ? (G.closed(p.ch) ? v : v - 1) : Math.floor(L / step + 1e-9);
        if (n > 5000) return note("Больше 5 000 точек — увеличьте шаг.");
        const cur0 = CURKEY(), l = targetLayer("point"), adds = [];
        if (cur0 && lyr(cur0)) setCurrentQuiet(cur0);             // точки разметки — в слой точек, текущий слой не меняется
        for (let i = 1; i <= n; i++) { const s = i * step; if (s >= L - 1e-6 && !G.closed(p.ch)) break; const q = G.sliceChain(p.ch, 0, s); adds.push({ key: l.key, f: newPoint(l, q[q.length - 1], i) }); }
        addNew(adds, kind === "div" ? "деление" : "разметка"); note(`Точек: ${adds.length} в слое «${l.title}» (длина ${f2(L)} м, шаг ${f2(step)} м).`); } };
    return st; };
}
function newPoint(l, w, i) { const f = new ol.Feature(new ol.geom.Point(fromM(w))); fieldsOfKey(l.key).forEach(k => f.set(k, "")); f.setProperties({ "№": i, _new: true, _edited: true }); return f; }
def("divide", "Поделить", ["DIV", "DIVIDE"], markCmd("div"));
def("measure", "Разметить", ["ME", "MEASURE"], markCmd("meas"));

// выбрать подобные: объекты того же слоя с тем же классом стиля (значение поля категорий / правило), как SELECTSIMILAR
def("similar", "Выбрать подобные", ["SS", "SELECTSIMILAR"], () => selection(items => {
  const out = [];
  const keyOf = (l, f) => l.style.mode === "cat" && l.style.cat.field ? "c:" + f.get(l.style.cat.field) : l.style.mode === "lgr" ? "t:" + JSON.stringify(f.get("_lt")) : "*";
  new Set(items.map(it => it.key)).forEach(k => { const l = lyr(k); if (!l) return; const want = new Set(items.filter(it => it.key === k).map(it => keyOf(l, it.f)));
    layerSrc[k].getFeatures().forEach(f => { if (visibleIn(l, f) && want.has(keyOf(l, f))) out.push({ key: k, f }); }); });
  setSel(out); note(`Выбрано подобных: ${out.length} (тот же слой${items.some(it => lyr(it.key)?.style.mode === "cat") ? " и то же значение поля категорий" : ""}).`);
  return { done: true };
}));

// развернуть направление линии: у красных линий REDLN97 сторона засечек задана направлением («+» — объект справа),
// поэтому вместе с вершинами меняется сторона в типе линии (…b ↔ …t) и знаки кодов LineCode
const flipLt = n => /^L\d\ds\d\d[bt]$/i.test(n) ? n.slice(0, -1) + ({ b: "t", t: "b", B: "T", T: "B" })[n.slice(-1)]
  : /^L\d\d[bt]\d\d[bt]$/i.test(n) ? n.replace(/[bt]/gi, c => ({ b: "t", t: "b", B: "T", T: "B" })[c]) : n;
const flipCode = c => String(c).split(",").map(x => x.trim().startsWith("-") ? x.trim().slice(1) : "-" + x.trim()).join(",");
def("reverse", "Развернуть", ["REV", "REVERSE"], () => selection(items => {
  const changes = [];
  for (const it of items) {
    const g = it.f.getGeometry(), t = g.getType(); if (!/Line/.test(t)) continue;
    const c = g.getCoordinates(), g2 = t === "LineString" ? new ol.geom.LineString(c.slice().reverse()) : new ol.geom.MultiLineString(c.map(r => r.slice().reverse()));
    const lt = it.f.get("_lt"), lc = it.f.get("LineCode"), props = {};
    if (Array.isArray(lt) && lt.length) props._lt = lt.map(flipLt);
    if (lc != null && lc !== "") props.LineCode = flipCode(lc);
    if (it.f.get("Тип линии")) props["Тип линии"] = flipLt(it.f.get("Тип линии"));
    changes.push({ key: it.key, f: it.f, geom: g2, cad: null, props });
  }
  if (!changes.length) { note("Разворачиваются линии."); return { done: true }; }
  edit(changes, [], "разворот"); note(`Развёрнуто линий: ${changes.length}${changes.some(c => c.props._lt) ? "; засечки красных линий перешли на другую сторону" : ""}.`);
  return { done: true };
}));

def("simplify", "Упростить", ["SIMP", "SIMPLIFY"], () => selection(items => {
  let d = MEM.__cadSimp || 0.5;
  const run = () => {
    const changes = []; let before = 0, after = 0;
    for (const it of items) {
      const g = it.f.getGeometry(); if (/Point/.test(g.getType())) continue;
      const n0 = chainsOf(g).reduce((s, c) => s + c.length, 0);
      // допуск в метрах местности: Дуглас–Пекер в координатах карты с поправкой масштаба Меркатора на широте объекта
      const k = 1 / Math.cos(ol.proj.toLonLat(ol.extent.getCenter(g.getExtent()))[1] * Math.PI / 180), s2 = g.simplify(d * k);
      const n1 = chainsOf(s2).reduce((s, c) => s + c.length, 0); if (n1 >= n0) continue;
      before += n0; after += n1; changes.push({ key: it.key, f: it.f, geom: s2, cad: null });
    }
    if (!changes.length) return note(`С допуском ${fmt(d, 2)} м упрощать нечего.`);
    edit(changes, [], "упрощение"); note(`Упрощено объектов: ${changes.length}, вершин ${before} → ${after} (допуск ${fmt(d, 2)} м).`);
  };
  const st = { need: "value", prompt: () => `Допуск упрощения, м — отклонение от исходной линии не больше <${fmt(d, 2)}>`,
    value: v => { if (!(v > 0)) return note("Допуск — больше нуля."); d = MEM.__cadSimp = v; run(); st.done = true; },
    enter: () => { run(); st.done = true; } };
  return st;
}));

def("delring", "Удалить дыру", ["DR", "DELRING"], () => ({ need: "point",
  prompt: () => "Щёлкните внутри дыры полигона, которую нужно закрыть; Esc — завершить", base: () => null, own: () => [],
  point: w => {
    const c = fromM(w);
    for (const l of project.layers) { if (!shown(l) || l.geom !== "poly") continue;
      // точка в дыре геометрии не принадлежит — ищем по габариту полигона
      const all = []; layerSrc[l.key].forEachFeatureInExtent([c[0], c[1], c[0], c[1]], f => { all.push(f); });
      for (const f of all) {
        const g = f.getGeometry(), polys = g.getType() === "Polygon" ? [g.getCoordinates()] : g.getType() === "MultiPolygon" ? g.getCoordinates() : [];
        const inRing = r => { let o = false; for (let i = 0, j = r.length - 1; i < r.length; j = i++) { const a = r[i], b = r[j]; if ((a[1] > c[1]) !== (b[1] > c[1]) && c[0] < (b[0] - a[0]) * (c[1] - a[1]) / (b[1] - a[1]) + a[0]) o = !o; } return o; };
        for (const p of polys) { const k = p.findIndex((r, i) => i > 0 && inRing(r)); if (k > 0 && inRing(p[0])) {
          p.splice(k, 1); const g2 = g.getType() === "Polygon" ? new ol.geom.Polygon(polys[0]) : new ol.geom.MultiPolygon(polys);
          edit([{ key: l.key, f, geom: g2, cad: null }], [], "удаление дыры"); return note("Дыра закрыта."); } }
      } }
    note("Здесь нет дыры полигона.");
  } }));

/* выбор по условию на атрибуты (как QSELECT AutoCAD и «Выбрать по выражению» QGIS): «Этажность > 9», «Решение = сносим»,
   «Наименование ~ школ» (содержит), «Адрес пусто»; условия соединяются «и» / «или». Слой — текущий, «Все» — все видимые. */
const normTxt = v => String(v ?? "").toLowerCase().replace(/ё/g, "е").trim();
function condOf(text, fields) {
  const one = c => { const m = c.match(/^(.+?)\s*(>=|<=|!=|≠|=|>|<|~|не пусто|пусто)\s*(.*)$/i); if (!m) return null;
    const want = normTxt(m[1]), f = fields.find(x => normTxt(x) === want) || fields.find(x => normTxt(x).startsWith(want)); if (!f) return { bad: m[1] };
    const op = m[2].toLowerCase(), v = m[3].trim().replace(/^["«']|["»']$/g, ""), nv = +v.replace(",", ".");
    return { f, test: p => { const x = p[f], nx = typeof x === "number" ? x : +String(x ?? "").replace(",", "."), num = v !== "" && isFinite(nv) && x !== "" && x != null && isFinite(nx);
      switch (op) { case "пусто": return x == null || x === ""; case "не пусто": return !(x == null || x === "");
        case "~": return normTxt(x).includes(normTxt(v)); case "=": return num ? nx === nv : normTxt(x) === normTxt(v); case "!=": case "≠": return num ? nx !== nv : normTxt(x) !== normTxt(v);
        case ">": return num && nx > nv; case "<": return num && nx < nv; case ">=": return num && nx >= nv; case "<=": return num && nx <= nv; } return false; } }; };
  const ors = text.split(/\s+или\s+/i).map(g => g.split(/\s+и\s+/i).map(one));
  const bad = ors.flat().find(c => !c || c.bad); if (bad !== undefined) return { error: bad ? `нет поля «${bad.bad}»` : "не понял условие" };
  return { test: p => ors.some(g => g.every(c => c.test(p))) };
}
def("qselect", "Выбрать по условию", ["QS", "QSELECT"], () => {
  let all = false;
  const st = { need: "text", placeholder: () => "Этажность > 9 и Решение = сносим · Наименование ~ школ · Адрес пусто",
    prompt: () => `Условие выбора (${all ? "все видимые слои" : `слой «${lyr(CURKEY())?.title || "—"}»`}): поле, знак (= ≠ > < >= <= ~ пусто), значение; «и», «или»${optStr(st.opts())}`,
    opts: () => [opt(all ? "Текущий слой (Т)" : "Все слои (В)", all ? ["т", "текущий", "c", "current"] : ["в", "все", "a", "all"], () => { all = !all; })],
    text: t => {
      const layers = all ? project.layers.filter(l => shown(l) && !outOfScale(l)) : [lyr(CURKEY())].filter(Boolean);
      if (!layers.length) return note("Нет текущего слоя: выберите слой в списке.");
      const out = []; let err = null;
      layers.forEach(l => { const c = condOf(t, fieldsAll(l.key)); if (c.error) { err ||= `${c.error} в слое «${l.title}» (поля: ${(fieldsAll(l.key)).slice(0, 12).join(", ")})`; return; }
        layerSrc[l.key].getFeatures().forEach(f => { if (visibleIn(l, f) && c.test(f.getProperties())) out.push({ key: l.key, f }); }); });
      if (!out.length && err) return note(err);
      setSel(out); note(`Выбрано по условию «${t}»: ${out.length}${err && all ? ` (${err})` : ""}.`); st.done = true; },
    enter: () => { st.done = true; } };
  return st;
});

/* выравнивание по двум парам точек (ALIGN): первая пара переносит, вторая поворачивает; масштаб — по желанию */
def("align", "Выровнять", ["AL", "ALIGN"], () => selection(items => {
  const P = [], names = ["Первая исходная точка", "Первая точка назначения", "Вторая исходная точка (Enter — только перенос)", "Вторая точка назначения"];
  const fnOf = scale => { const [s1, d1, s2, d2] = P; if (!s2) return w => G.add(d1, G.sub(w, s1));
    const a = G.ang(d1, d2) - G.ang(s1, s2), k = scale ? G.dist(d1, d2) / (G.dist(s1, s2) || 1) : 1, c = Math.cos(a), sn = Math.sin(a);
    return w => { const v = G.mul(G.sub(w, s1), k); return G.add(d1, [v[0] * c - v[1] * sn, v[0] * sn + v[1] * c]); }; };
  const apply = scale => { const fn = fnOf(scale), k = P[2] && scale ? G.dist(P[1], P[3]) / (G.dist(P[0], P[2]) || 1) : 1;
    edit(items.map(({ key, f }) => ({ key, f, geom: xformGeom(f.getGeometry(), fn), cad: xformCad(f.get("_cad"), fn, k) })), [], "выравнивание");
    setSel(items); note(`Выровнено объектов: ${items.length}${scale && k !== 1 ? `, масштаб ${fmt(k, 4)}` : ""}.`); st.done = true; };
  const st = { need: "point", base: () => P.length % 2 ? P[P.length - 1] : null,
    prompt: () => P.length < 4 ? names[P.length] : `Масштабировать по точкам выравнивания?${optStr(st.opts())} Enter — нет`,
    opts: () => P.length === 4 ? [opt("Да (Д)", ["д", "да", "y", "yes"], () => apply(true)), opt("Нет (Н)", ["н", "нет", "n", "no"], () => apply(false))] : [],
    point: w => { if (P.length < 4) P.push(w); if (P.length === 4) st.need = "point"; },
    enter: () => { if (P.length === 2) return apply(false); if (P.length === 4) return apply(false); st.done = true; },
    preview: w => { if (P.length === 1 || P.length === 3) return { lines: [[P[P.length - 1], w]] }; return {}; } };
  return st;
}));

// перенести выбранные объекты в текущий слой (LAYMCUR): атрибуты сохраняются, вид геометрии подстраивается под слой
def("laymcur", "В текущий слой", ["LMC", "LAYMCUR"], () => selection(items => {
  const l = lyr(CURKEY()); if (!l) { note("Выберите слой в списке — он станет слоем назначения."); return { done: true }; }
  const changes = [], adds = []; let skip = 0;
  for (const it of items) { if (it.key === l.key) continue; const g = geomFor(it.f.getGeometry(), l.geom); if (!g) { skip++; continue; }
    changes.push({ ...it, remove: true }); adds.push({ key: l.key, f: copyFeat(it.f, g) }); }
  if (!adds.length) { note(skip ? `Эти объекты не встают в слой «${l.title}» по виду геометрии.` : "Выбранное уже в текущем слое."); return { done: true }; }
  edit(changes, adds, "в текущий слой"); setSel(adds); note(`Перенесено в «${l.title}»: ${adds.length}${skip ? `, не подошли по виду геометрии: ${skip}` : ""}.`);
  return { done: true };
}));
// замкнутая линия ↔ полигон: объект уходит в слой другого вида (свой слой полигонов или линий), атрибуты сохраняются
def("convert", "Линия ↔ полигон", ["CONV", "CONVERT"], () => selection(items => {
  const changes = [], adds = []; let skip = 0;
  for (const it of items) { const t = it.f.getGeometry().getType(); if (/Point/.test(t)) { skip++; continue; }
    const to = /Polygon/.test(t) ? "line" : "poly", g = geomFor(it.f.getGeometry(), to); if (!g) { skip++; continue; }
    const l = targetLayer(to); changes.push({ ...it, remove: true }); adds.push({ key: l.key, f: copyFeat(it.f, g) }); }
  if (!adds.length) { note("Преобразуются полигоны в линии и замкнутые линии в полигоны."); return { done: true }; }
  edit(changes, adds, "линия ↔ полигон"); setSel(adds); note(`Преобразовано: ${adds.length}${skip ? `, пропущено (точки или незамкнутые линии): ${skip}` : ""}.`);
  return { done: true };
}));

const ALIAS = {}; Object.entries(CMDS).forEach(([id, c]) => c.alias.forEach(a => { ALIAS[a] = id; }));

/* ---------- лента и строка состояния ---------- */
const HELP = { line: "отдельные отрезки", pline: "одна ломаная; в слое полигонов Enter замыкает контур", circle: "центр и радиус или три точки", arc: "по трём точкам или центр, начало, конец", rect: "по двум углам, по осям МСК; углы — фаской или сопряжением", ellipse: "центр, конец оси, вторая полуось", hatch: "щелчок внутри контура или выбор объектов — в слой «Штриховка»", dim: "две точки и положение размерной линии — в слой «Размеры»", text: "точка и строка — в слой «Надписи»", arrayedit: "изменить числа массива и пересобрать копии", polygon: "правильный, по числу сторон", point: "точки щелчком или по координатам",
  move: "базовая точка, затем вторая", copy: "несколько копий подряд", rotate: "вокруг базовой точки на угол", mirror: "по оси из двух точек", scale: "от базовой точки, в том числе по опорному отрезку", offset: "параллельная копия на расстоянии", trim: "по пересечениям с другими объектами", extend: "до ближайшего объекта", fillet: "радиусом; все углы полилинии", break: "между двумя точками", join: "линии с общими концами — в одну", explode: "полилинию и контур — на отрезки", erase: "выбранные объекты",
  chamfer: "срез угла двумя длинами; на всех углах полилинии", array: "прямоугольный: ряды и столбцы; круговой: вокруг центра", stretch: "вершины внутри секущей рамки сдвигаются", lengthen: "конец линии на приращение или до полной длины",
  split: "полигон — линией разреза на части, атрибуты у всех частей", merge: "полигоны одного слоя — в один", subtract: "из выбранных полигонов вырезать другие",
  buffer: "полигоны на заданном расстоянии вокруг объектов (минус — внутрь)", matchprop: "атрибуты образца — другим объектам",
  bpoly: "полигон из области, ограниченной линиями, — щелчком внутри (как BOUNDARY)", laymcur: "перенести выбранное в текущий слой, атрибуты сохраняются", convert: "замкнутую линию — в полигон, полигон — в замкнутые линии",
  delring: "закрыть дыру полигона щелчком внутри неё", align: "перенос и поворот по двум парам точек, масштаб по желанию",
  qselect: "выбрать объекты по условию на атрибуты: Этажность > 9 и Решение = сносим", simplify: "меньше вершин с допуском в метрах", reverse: "направление линии; у красных линий — и сторона засечек",
  divide: "точки, делящие линию на N равных частей", measure: "точки вдоль линии через заданный шаг", similar: "все объекты слоя того же класса стиля",
  dist: "расстояние по точкам", area: "площадь и периметр по точкам", terr: "граница территории разработки", zoomall: "вписать карту во все видимые слои, границу и листы" };
function syncModes() { Object.assign(cad.st, JSON.parse(JSON.stringify(ST))); }
syncModes();

Object.assign(cadApi, { MODES, start, cancel: silent => cancel(silent), toggle, active: () => !!CMD, selecting: () => CMD?.need === "sel",
  grips: () => syncGrips(), gripsCut: () => gripCut, MAXGRIPS, cur: () => CUR, acq: () => ACQ.slice(), toM, fromM, ST, CMDS, ALIAS, HELP,
  setOpt: (k, v) => { ST[k] = v; saveST(); syncModes(); }, setMode: (k, v) => { ST.modes[k] = v; saveST(); syncModes(); },
  ghosts: () => prevSrc.getFeatures().filter(f => f.get("k") === "ghost").map(f => toM(f.getGeometry().getFirstCoordinate())),
  gripList: () => gripSrc.getFeatures().map(g => ({ w: toM(g.getGeometry().getCoordinates()), mid: !!g.get("mid") })) });
showCmd();
cadSay = note;
cad.ready = true;
const stopW = watch([sel, dataRev], () => setTimeout(syncGrips, 0));
return () => { stopW(); removeEventListener("keydown", onKey, true); cancel(true); cadSay = msg => { notice.value = msg; }; cad.ready = false; cad.cmd = null; mMain.removeInteraction(cadI); };
}
