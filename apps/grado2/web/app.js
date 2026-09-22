/* ГРАДО 2: существующее положение → параметрический граф → эскиз.
   Данные — реальные выгрузки сервера (/api/fetch), ТЭП — движок ядра (/api/tep).
   Геометрия в WGS84 (Turf.js); для посадки и объёма — локальная метрическая рамка вокруг территории. */

const $ = id => document.getElementById(id);
const fmt = (n, d = 0) => Number(n).toLocaleString("ru-RU", { minimumFractionDigits: d, maximumFractionDigits: d });
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const icons = () => lucide.createIcons({ attrs: { "stroke-width": 1.75 } });
let tT; function toast(t) { const el = $("toast"); el.textContent = t; el.classList.add("on"); clearTimeout(tT); tT = setTimeout(() => el.classList.remove("on"), 4200); }
let busyN = 0; function busy(on) { busyN += on ? 1 : -1; $("busy").hidden = busyN <= 0; }
async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const j = await r.json(); if (!r.ok) throw new Error(j.error || r.status); return j;
}

/* ---------- геометрия ---------- */
let LON0 = 37.6, LAT0 = 55.75, KX = 111320 * Math.cos(LAT0 * Math.PI / 180), KY = 110540;
function setFrame([lon, lat]) { LON0 = lon; LAT0 = lat; KX = 111320 * Math.cos(lat * Math.PI / 180); }
const toLL = ([x, y]) => [LON0 + x / KX, LAT0 + y / KY], toXY = ([lo, la]) => [(lo - LON0) * KX, (la - LAT0) * KY];
const polyLL = ring => turf.polygon([[...ring.map(toLL), toLL(ring[0])]]);
const rect = (x0, y0, x1, y1) => [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
const bboxOf = r => { const xs = r.map(p => p[0]), ys = r.map(p => p[1]); return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]; };
const centroid = r => { let x = 0, y = 0; r.forEach(p => { x += p[0]; y += p[1]; }); return [x / r.length, y / r.length]; };
const polys = f => { const g = f?.geometry; return !g ? [] : g.type === "Polygon" ? [g.coordinates] : g.type === "MultiPolygon" ? g.coordinates : []; };
const ringsXY = f => polys(f).map(p => p[0].map(toXY));
const splitParts = f => polys(f).map(c => turf.polygon(c));
const m2 = f => f ? turf.area(f) : 0;
const safe = fn => { try { return fn(); } catch (e) { console.warn(e); return null; } };
function unionAll(fs) {
  fs = fs.filter(f => f && polys(f).length); if (!fs.length) return null; if (fs.length === 1) return fs[0];
  return safe(() => turf.union(turf.featureCollection(fs))) || fs.reduce((a, b) => safe(() => turf.union(turf.featureCollection([a, b]))) || a);
}
const diff = (a, b) => !a ? null : !b ? a : safe(() => turf.difference(turf.featureCollection([a, b])));
const inter = (a, b) => (a && b) ? safe(() => turf.intersect(turf.featureCollection([a, b]))) : null;
const buf = (a, d) => { if (!a) return null; if (!d) return a; const r = safe(() => turf.buffer(a, d, { units: "meters" })); return r?.geometry ? r : null; };
// ponytail: объединение линий дорог через буфер каждой — O(n) union, для района в сотни улиц хватает
const asArea = f => f && /Line/.test(f.geometry.type) ? buf(f, 0.5) : f;
function rot([x, y], a, c) { const s = Math.sin(a), k = Math.cos(a), dx = x - c[0], dy = y - c[1]; return [c[0] + dx * k - dy * s, c[1] + dx * s + dy * k]; }

/* ---------- карта (EPSG:3857, подложка OSM) ---------- */
const GJ = new ol.format.GeoJSON({ featureProjection: "EPSG:3857" });
const toOl = f => GJ.readFeature(f);
const sharedView = new ol.View({ center: ol.proj.fromLonLat([37.525, 55.7925]), zoom: 15 });
const interactions = () => (ol.interaction.defaults.defaults || ol.interaction.defaults)({ doubleClickZoom: false, altShiftDragRotate: false, pinchRotate: false });
const basemap = () => new ol.layer.Tile({ source: new ol.source.OSM(), className: "basemap", opacity: .55 });
const ALLMAPS = [];   // все карты проекта: слои из модели (layers.js) цепляются к каждой
function newMap(target, layers) { const m = new ol.Map({ target, layers: [basemap(), ...layers], view: sharedView, controls: [new ol.control.ScaleLine({ minWidth: 70 }), new ol.control.Attribution({ collapsible: true })], interactions: interactions() }); ALLMAPS.push(m); window.attachDataLayers?.(m); return m; }
const PAT = new Map();
function hatch(color) { if (PAT.has(color)) return PAT.get(color); const c = document.createElement("canvas"); c.width = c.height = 8; const x = c.getContext("2d"); x.fillStyle = color + "18"; x.fillRect(0, 0, 8, 8); x.strokeStyle = color; x.lineWidth = 1.1; x.beginPath(); x.moveTo(0, 8); x.lineTo(8, 0); x.moveTo(-4, 4); x.lineTo(4, -4); x.moveTo(4, 12); x.lineTo(12, 4); x.stroke(); const p = x.createPattern(c, "repeat"); PAT.set(color, p); return p; }
const S = (fill, stroke, w = 1) => new ol.style.Style({ fill: fill && new ol.style.Fill({ color: fill }), stroke: stroke && new ol.style.Stroke({ color: stroke, width: w }) });
const MAJOR = new Set(["motorway", "trunk", "primary", "secondary", "tertiary"]);

/* ---------- знаки: ЛГР (коды, цвета, штрих) и Генплан — из библиотек ядра ---------- */
const LGRC = {}, LGRD = {}, GPZ = {}, NMZ = {};
async function loadStyleLibs() {
  await Linetypes.load();
  const [lgr, gp] = await Promise.all(["/styles/moscow_lgr.json", "/styles/moscow_genplan.json"].map(u => fetch(u).then(r => r.json())));
  Object.values(lgr.styles).forEach(s => { if (s.lgr_code != null) { LGRC[+s.lgr_code] = s.stroke; if (s.dash_mm) LGRD[+s.lgr_code] = s.dash_mm.map(v => v * 2); } }); // мм на 1:2000 → метры
  Object.values(gp.styles).forEach(s => { if (s.gp_zone) GPZ[s.gp_zone.toLowerCase()] = s; if (s.nm_zone) NMZ[s.nm_zone.toLowerCase()] = s; });
}
const ltCode = n => { const m = /^L(\d\d)s(\d\d)/i.exec(n) || /^L(\d\d)[bt](\d\d)/i.exec(n); return m ? (/^L\d\ds/i.test(n) ? +m[2] : +m[1]) : null; };
/* красные линии ОГД: тип линии REDLN97 по LineCode (выбирает сервер), коды без типа — по библиотеке ЛГР */
const redLineStyle = f => new ol.style.Style({ renderer(coords, st) {
  const ctx = st.context, pr = st.pixelRatio, mpp = st.resolution * Math.cos(LAT0 * Math.PI / 180), k = pr / mpp, plain = mpp / 0.000264583 > 10000;
  const lines = typeof coords[0][0] === "number" ? [coords] : coords, lt = f.get("_lt") || [], miss = f.get("_miss") || [];
  for (const pts of lines) {
    lt.forEach(n => Linetypes.draw(ctx, pts, n, k, { color: LGRC[ltCode(n)] || "#d7191c", width: 1.3 * pr, plain }));
    miss.forEach(([c]) => { ctx.save(); ctx.strokeStyle = LGRC[c] || "#888"; ctx.lineWidth = 1.3 * pr; if (LGRD[c] && !plain) ctx.setLineDash(LGRD[c].map(v => v * k)); ctx.beginPath(); pts.forEach((p, i) => i ? ctx.lineTo(...p) : ctx.moveTo(...p)); ctx.stroke(); ctx.restore(); });
    if (!lt.length && !miss.length) { ctx.save(); ctx.strokeStyle = "#999"; ctx.lineWidth = pr; ctx.beginPath(); pts.forEach((p, i) => i ? ctx.lineTo(...p) : ctx.moveTo(...p)); ctx.stroke(); ctx.restore(); }
  }
} });

/* ---------- состояние проекта ---------- */
let SOURCES = {};                 // ключ → {title, kind}
const DATA = {};                  // ключ → {title, source, fetched_at, fc, count, fields}
let ERRORS = {};
let TERR = null, TERR_M2 = 0, dataRev = 0;
const terrSrc = new ol.source.Vector(), layerSrc = {};
const terrStyle = S(null, "#b3261e", 2); terrStyle.getStroke().setLineDash([12, 4, 2, 4]);
const terrLayer = () => new ol.layer.Vector({ source: terrSrc, style: terrStyle, zIndex: 60 });

/* ================= 1. Существующее положение ================= */
const mCollect = newMap("mCollect", [terrLayer()]);
function setTerritory(feature) {
  TERR = turf.feature(feature.geometry); TERR_M2 = turf.area(TERR);
  setFrame(turf.centroid(TERR).geometry.coordinates);
  terrSrc.clear(); terrSrc.addFeature(toOl(TERR));
  $("terrInfo").textContent = `Площадь ${fmt(TERR_M2 / 1e4, 2)} га. Загружается прямоугольник вокруг границы.`;
  $("bLoad").disabled = false; dataRev++;
  sharedView.fit(terrSrc.getExtent(), { padding: [40, 40, 40, 40], maxZoom: 17 });
}
let drawI = null;
$("bDraw").onclick = () => {
  if (drawI) mCollect.removeInteraction(drawI);
  drawI = new ol.interaction.Draw({ type: "Polygon", source: new ol.source.Vector() });
  drawI.on("drawend", e => { mCollect.removeInteraction(drawI); drawI = null; setTerritory(JSON.parse(new ol.format.GeoJSON().writeFeature(e.feature, { featureProjection: "EPSG:3857" }))); });
  mCollect.addInteraction(drawI); toast("Щёлкайте по углам границы, двойной щелчок завершает.");
};
$("bExample").onclick = () => setTerritory(turf.polygon([[[37.5195, 55.7895], [37.5305, 55.7895], [37.5305, 55.7955], [37.5195, 55.7955], [37.5195, 55.7895]]]));
const GROUP = { import: "Импорт чертежей", nspd: "ЕГРН · НСПД", osm: "OpenStreetMap", gisogd: "ГИС ОГД Москвы (красные линии: первая выгрузка — весь слой, около 100 МБ)" };
const CHECKED = new Set(["nspd.parcels", "nspd.buildings", "osm.roads", "osm.buildings", "osm.water", "osm.landuse", "gisogd.szz", "gisogd.vodookhr"]);
function renderSources() {
  const groups = {}; Object.entries(SOURCES).forEach(([k, s]) => (groups[s.kind] ||= []).push(k));
  $("srcList").innerHTML = Object.entries(groups).map(([g, ks]) => `<div class="src"><div class="srch"><i data-lucide="database"></i><b>${GROUP[g] || g}</b></div>` + ks.map(k => {
    const d = DATA[k], e = ERRORS[k];
    return `<label class="lr"><input type="checkbox" data-src="${k}" ${CHECKED.has(k) ? "checked" : ""}><span class="nm" title="${esc(d?.source || "")}">${esc(SOURCES[k].title)}</span><span class="c num">${d ? d.count : ""}</span></label>` + (e ? `<div class="err">${esc(e)}</div>` : "") + (d ? `<div class="err" style="color:var(--faint)">выгрузка ${d.fetched_at}${d.notes?.length ? " · " + esc(d.notes[0]) : ""}</div>` : "");
  }).join("") + `</div>`).join("") + (Object.keys(DATA).length ? `<div class="sect">Существующее положение</div>${kv(existingSummary())}` : "")
    + `<div class="note">Выгрузки не правятся: это доказательная база. В графе анализа они доступны узлом «Слой». Красные линии рисуются типами линий REDLN97 — <a href="linetypes.html" target="_blank">каталог типов</a>.</div>`;
  icons();
}
$("srcList").addEventListener("change", e => { const k = e.target.dataset.src; if (k) e.target.checked ? CHECKED.add(k) : CHECKED.delete(k); });
$("bLoad").onclick = async () => {
  if (!TERR) return;
  const keys = [...CHECKED];
  if (!keys.length) return toast("Отметьте источники.");
  const [w, s, e, n] = turf.bbox(buf(TERR, 60));
  $("bLoad").disabled = true; busy(true); toast("Выгрузка идёт: НСПД и OSM — секунды, ГИС ОГД в первый раз качает слой целиком.");
  try {
    const r = await api("/api/fetch", { bbox: [w, s, e, n], sources: keys });
    ERRORS = r.errors;
    for (const [k, v] of Object.entries(r.layers)) {
      const fields = [...new Set(v.features.features.slice(0, 200).flatMap(f => Object.keys(f.properties)))];
      DATA[k] = { ...v, fc: v.features, count: v.features.features.length, fields };
      layerSrc[k] ||= new ol.source.Vector(); setLayerData(k, v.features);
      const l = ensureLayer(k, v.title); assignCats(l, true); restyle(l);
    }
    dataRev++; renderSources();
    const ne = Object.keys(ERRORS).length; toast(`Загружено слоёв: ${Object.keys(r.layers).length}${ne ? `, с ошибкой: ${ne}` : ""}.`);
  } catch (err) { toast("Выгрузка не удалась: " + err.message); }
  finally { busy(false); $("bLoad").disabled = false; }
};
const EXIST_KEY = () => DATA["nspd.buildings"] ? "nspd.buildings" : DATA["osm.buildings"] ? "osm.buildings" : null;
const floorsOf = f => { const v = +(f.properties["Этажность"]); return v > 0 ? v : 1; };
function insideTerr(f) { return TERR && safe(() => turf.booleanPointInPolygon(turf.pointOnFeature(f), TERR)); }
function existingSummary() {
  const k = EXIST_KEY(), rows = [["Территория", fmt(TERR_M2 / 1e4, 2) + " га"]];
  if (k) { const B = DATA[k].fc.features.filter(insideTerr); const spp = B.reduce((s, f) => s + m2(f) * floorsOf(f), 0), fp = B.reduce((s, f) => s + m2(f), 0);
    rows.push(["Зданий в границе", B.length + (k === "osm.buildings" ? " (OSM)" : "")], ["СПП существующая", fmt(spp / 1000, 1) + " тыс. м²"], ["Плотность", fmt(spp / 1000 / (TERR_M2 / 1e4), 1) + " тыс. м²/га"], ["Застроенность", fmt(fp / TERR_M2 * 100, 1) + " %"]); }
  if (DATA["nspd.parcels"]) rows.push(["Участков ЕГРН", DATA["nspd.parcels"].fc.features.filter(insideTerr).length]);
  return rows;
}
function kv(rows) { return `<div class="kv">${rows.map(([k, v, cls]) => `<div>${esc(k)}</div><div class="${cls || ""}">${v}</div>`).join("")}</div>`; }

/* ---------- DXF: импорт чертежа и экспорт проекта (сервер, ezdxf) ---------- */
$("fDxf").onchange = async e => {
  const file = e.target.files[0]; if (!file) return; e.target.value = "";
  busy(true);
  try {
    const r = await fetch("/api/import/dxf", { method: "POST", body: await file.arrayBuffer() }); const j = await r.json(); if (!r.ok) throw new Error(j.error);
    const key = "import:" + file.name, fc = j.features;
    SOURCES[key] = { title: "DXF: " + file.name, kind: "import" }; CHECKED.add(key);
    DATA[key] = { title: "DXF: " + file.name, source: "файл " + file.name, fetched_at: new Date().toISOString().slice(0, 10), notes: j.notes, fc, count: fc.features.length, fields: [...new Set(fc.features.flatMap(f => Object.keys(f.properties)))] };
    layerSrc[key] ||= new ol.source.Vector(); setLayerData(key, fc); ensureLayer(key, DATA[key].title); dataRev++; renderSources();
    if (fc.features.length) sharedView.fit(layerSrc[key].getExtent(), { padding: [40, 40, 40, 40], maxZoom: 18 });
    toast(`DXF: объектов ${fc.features.length}. ${j.notes.join("; ")}`);
  } catch (err) { toast("DXF не прочитан: " + err.message); } finally { busy(false); }
};
$("bExport").onclick = async () => {
  const layers = Object.entries(DATA).map(([k, d]) => ({ name: d.title, features: d.fc, color: k === "gisogd.red_lines" ? "#d7191c" : "#808080" }));
  if (TERR) layers.push({ name: "Граница территории", features: turf.featureCollection([TERR]), color: "#b3261e" });
  if (RESULT.sketch?.length) layers.push({ name: "Эскиз застройки", features: turf.featureCollection(RESULT.sketch.map(b => turf.feature(b.f.geometry, { floors: b.floors }))), color: "#2a78d6", floors: true });
  if (!layers.length) return toast("Экспортировать нечего: загрузите данные или постройте эскиз.");
  busy(true);
  try {
    const r = await fetch("/api/export/dxf", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ layers }) });
    if (!r.ok) throw new Error((await r.json()).error);
    const a = document.createElement("a"); a.href = URL.createObjectURL(await r.blob()); a.download = "grado2-dxf.zip"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    toast("DXF готов: в архиве чертёж, red_lns.shx и REDLN97.LIN. Координаты — МГГТ, метры.");
  } catch (err) { toast("Экспорт не удался: " + err.message); } finally { busy(false); }
};

/* ================= 2. Граф анализа (litegraph.js) ================= */
Object.assign(LiteGraph, { NODE_DEFAULT_COLOR: "#d6dade", NODE_DEFAULT_BGCOLOR: "#f7f7f5", NODE_DEFAULT_BOXCOLOR: "#8a8d91", NODE_TITLE_COLOR: "#1d1d1f", NODE_SELECTED_TITLE_COLOR: "#000", NODE_TEXT_COLOR: "#333", NODE_TEXT_SIZE: 12, NODE_SUBTEXT_SIZE: 11,
  WIDGET_BGCOLOR: "#ffffff", WIDGET_OUTLINE_COLOR: "#b5b8bc", WIDGET_TEXT_COLOR: "#1d1d1f", WIDGET_SECONDARY_TEXT_COLOR: "#6b6f75", LINK_COLOR: "#7a7e84", CONNECTING_LINK_COLOR: "#2f6fc4", NODE_TITLE_HEIGHT: 24, NODE_SLOT_HEIGHT: 20, NODE_WIDGET_HEIGHT: 20 });
LGraphCanvas.link_type_colors = { geom: "#3f8f5a", num: "#b07a00", sketch: "#2f6fc4", tep: "#8a4ab0" };
const TITLE = { src: "#cfe3d4", op: "#d6dade", gen: "#cfdcf0", tep: "#e3d6ec", num: "#f0e3c8" };
const OPS = ["—", "=", "≠", ">", "<", "≥", "≤", "содержит", "один из"];
function testOp(v, op, t) {
  if (op === "—") return true; if (v == null) return false;
  if (op === "содержит") return String(v).toLowerCase().includes(String(t).toLowerCase());
  if (op === "один из") return String(t).split(",").map(s => s.trim().toLowerCase()).includes(String(v).toLowerCase());
  const n = !isNaN(+v) && !isNaN(+t) && t !== "", a = n ? +v : String(v), b = n ? +t : String(t);
  return { "=": a == b, "≠": a != b, ">": a > b, "<": a < b, "≥": a >= b, "≤": a <= b }[op];
}
function drawInfo(ctx) { if (this.flags.collapsed || !this.info) return; ctx.fillStyle = "#5f6368"; ctx.font = "11px system-ui, sans-serif"; ctx.fillText(this.info, 8, this.size[1] - 7); }
function finish(node, kind, w = 210) { node.color = TITLE[kind]; node.bgcolor = "#f7f7f5"; node.size = node.computeSize(); node.size[0] = Math.max(w, node.size[0]); node.size[1] += 16; node.onDrawForeground = drawInfo; }
const ha = f => f ? fmt(m2(f) / 1e4, 2) + " га" : "пусто";
const titleToKey = t => Object.keys(DATA).find(k => DATA[k].title === t) || Object.keys(SOURCES).find(k => SOURCES[k].title === t);

function NTerr() { this.addOutput("граница", "geom"); finish(this, "src", 170); }
NTerr.title = "Территория"; NTerr.prototype.onExecute = function () { this.setOutputData(0, TERR); this.info = TERR ? ha(TERR) : "граница не задана"; };
LiteGraph.registerNodeType("Данные/Территория", NTerr);

function NLayer() {
  this.addOutput("объекты", "geom");
  this.addWidget("combo", "слой", "", () => { }, { values: () => Object.keys(DATA).map(k => DATA[k].title) });
  this.addWidget("combo", "поле", "—", () => { }, { values: () => ["—", ...(DATA[titleToKey(this.widgets[0].value)]?.fields || [])] });
  this.addWidget("combo", "условие", "—", () => { }, { values: OPS });
  this.addWidget("text", "значение", "", () => { });
  finish(this, "src", 250);
}
NLayer.title = "Слой"; NLayer.prototype.onExecute = function () {
  const [lw, fw, ow, vw] = this.widgets, key = titleToKey(lw.value), d = DATA[key];
  if (!d) { this.setOutputData(0, null); this.info = lw.value ? "слой не загружен" : "выберите слой"; return; }
  if (this._cacheKey !== [dataRev, key, fw.value, ow.value, vw.value, !!TERR].join("|")) {
    this._cacheKey = [dataRev, key, fw.value, ow.value, vw.value, !!TERR].join("|");
    const list = d.fc.features.filter(f => fw.value === "—" || testOp(f.properties[fw.value], ow.value, vw.value));
    const u = unionAll(list.map(asArea)); if (u) u.properties = { _src: list };
    this._out = u; this._n = [list.length, d.count];
  }
  this.setOutputData(0, this._out);
  this.title = "Слой: " + d.title + (fw.value !== "—" && ow.value !== "—" ? ` [${fw.value} ${ow.value} ${vw.value}]` : "");
  this.info = `${this._n[0]} из ${this._n[1]} объектов`;
};
LiteGraph.registerNodeType("Данные/Слой", NLayer);

function NNum() { this.addOutput("число", "num"); this.addWidget("slider", "значение", 12, () => { }, { min: 1, max: 40, precision: 0, slider_color: "#e3b25a" }); finish(this, "num", 190); }
NNum.title = "Число"; NNum.prototype.onExecute = function () { this.setOutputData(0, Math.round(this.widgets[0].value)); };
LiteGraph.registerNodeType("Параметры/Число", NNum);

function cached(node, key, fn) { if (node._ck !== key) { node._ck = key; node._cv = fn(); } return node._cv; }
const gid = f => f ? (f._gid ||= Math.random().toString(36).slice(2)) : "-";
function NBuf() { this.addInput("объекты", "geom"); this.addInput("расстояние", "num"); this.addOutput("зона", "geom"); this.addWidget("slider", "расстояние, м", 10, () => { }, { min: -30, max: 60, precision: 0, slider_color: "#9fc0a8" }); finish(this, "op"); }
NBuf.title = "Буфер"; NBuf.prototype.onExecute = function () { const a = this.getInputData(0), d = this.getInputData(1) ?? Math.round(this.widgets[0].value); const r = cached(this, gid(a) + d, () => buf(a, d)); this.setOutputData(0, r); this.info = ha(r); };
LiteGraph.registerNodeType("Геометрия/Буфер", NBuf);
function NDiff() { this.addInput("из", "geom"); this.addInput("вычесть", "geom"); this.addOutput("остаток", "geom"); finish(this, "op", 170); }
NDiff.title = "Вычесть"; NDiff.prototype.onExecute = function () { const a = this.getInputData(0), b = this.getInputData(1); const r = cached(this, gid(a) + gid(b), () => diff(a, b)); this.setOutputData(0, r); this.info = ha(r); };
LiteGraph.registerNodeType("Геометрия/Вычесть", NDiff);
function NUnion() { this.addInput("A", "geom"); this.addInput("B", "geom"); this.addOutput("A ∪ B", "geom"); finish(this, "op", 150); }
NUnion.title = "Объединить"; NUnion.prototype.onExecute = function () { const a = this.getInputData(0), b = this.getInputData(1);
  const r = cached(this, gid(a) + gid(b), () => { const u = unionAll([a, b]); if (u) u.properties = { _src: [...(a?.properties?._src || []), ...(b?.properties?._src || [])] }; return u; }); this.setOutputData(0, r); this.info = ha(r); };
LiteGraph.registerNodeType("Геометрия/Объединить", NUnion);
function NInter() { this.addInput("A", "geom"); this.addInput("B", "geom"); this.addOutput("A ∩ B", "geom"); finish(this, "op", 150); }
NInter.title = "Пересечь"; NInter.prototype.onExecute = function () { const a = this.getInputData(0), b = this.getInputData(1); const r = cached(this, gid(a) + gid(b), () => inter(a, b)); this.setOutputData(0, r); this.info = ha(r); };
LiteGraph.registerNodeType("Геометрия/Пересечь", NInter);

function NPlace() {
  this.addInput("пятно", "geom"); this.addInput("этажность", "num"); this.addOutput("посадка", "sketch");
  this.addWidget("combo", "типология", "Секции", () => { }, { values: ["Секции", "Квартал", "Башни"] });
  this.addWidget("slider", "ширина корпуса, м", 16, () => { }, { min: 12, max: 24, precision: 0, slider_color: "#8fb3e0" });
  this.addWidget("slider", "этажность", 12, () => { }, { min: 3, max: 30, precision: 0, slider_color: "#8fb3e0" });
  this.addWidget("slider", "разрыв / высота", 1.0, () => { }, { min: .5, max: 2, precision: 2, slider_color: "#8fb3e0" });
  this.addWidget("slider", "ориентация, °", 0, () => { }, { min: 0, max: 90, precision: 0, slider_color: "#8fb3e0" });
  finish(this, "gen", 240);
}
NPlace.title = "Посадка застройки"; NPlace.prototype.onExecute = function () {
  const site = this.getInputData(0), p = placeParams(this);
  const r = cached(this, gid(site) + JSON.stringify(p), () => generate(site, p)); this.setOutputData(0, r);
  this.info = `${r.length} корпусов · ${fmt(r.reduce((s, b) => s + b.m2 * b.floors, 0) / 1000, 1)} тыс. м² СПП`;
};
LiteGraph.registerNodeType("Эскиз/Посадка застройки", NPlace);
function placeParams(n) { const w = n.widgets; return { typ: w[0].value, width: Math.round(w[1].value), floors: n.getInputData?.(1) ?? Math.round(w[2].value), gap: +w[3].value, angle: Math.round(w[4].value) }; }

function NTep() { this.addInput("посадка", "sketch"); this.addInput("сохраняемые", "geom"); this.addInput("ограничения", "geom"); this.addOutput("ТЭП", "tep");
  this.addWidget("slider", "доля жилья, %", 80, () => { }, { min: 0, max: 100, precision: 0, slider_color: "#c0a6d4" }); this.addWidget("slider", "цель, тыс. м²/га", 25, () => { }, { min: 5, max: 45, precision: 0, slider_color: "#c0a6d4" }); finish(this, "tep", 230); }
NTep.title = "ТЭП · методика КРТ Москвы"; NTep.prototype.onExecute = function () {
  const sk = this.getInputData(0) || [], kept = this.getInputData(1), lim = this.getInputData(2), share = this.widgets[0].value / 100, target = this.widgets[1].value;
  const key = [gid(sk), gid(kept), gid(lim), share, target, dataRev].join("|");
  if (this._key !== key) { this._key = key; const seq = this._seq = (this._seq || 0) + 1;
    tepRequest(sk, kept, lim, share, target).then(t => { if (seq === this._seq) { this._tep = t; this.setOutputData(0, t); this.info = `плотность ${fmt(t.density, 1)} · население ${fmt(t.m.population)}`; lgc.setDirty(true, true); if (ui.step === "sketch") renderTep(); } }).catch(e => { this.info = "ТЭП: " + e.message; }); }
  this.setOutputData(0, this._tep);
};
LiteGraph.registerNodeType("Показатели/ТЭП КРТ", NTep);

/* ТЭП: геометрические части — здесь, нормативная часть — движок ядра на сервере */
function keptBuildings(kept) { const src = kept?.properties?._src || []; return src.filter(f => /Polygon/.test(f.geometry.type) && insideTerr(f)); }
async function tepRequest(sketch, kept, lim, share, target) {
  const keptList = keptBuildings(kept), keptSet = new Set(keptList);
  const sppNew = sketch.reduce((s, b) => s + b.m2 * b.floors, 0), fpNew = sketch.reduce((s, b) => s + b.m2, 0);
  const sppKept = keptList.reduce((s, f) => s + m2(f) * floorsOf(f), 0), fpKept = keptList.reduce((s, f) => s + m2(f), 0);
  const ek = EXIST_KEY(), demol = ek ? DATA[ek].fc.features.filter(f => /Polygon/.test(f.geometry.type) && insideTerr(f) && !keptSet.has(f)) : [];
  const restrict = m2(inter(TERR, lim)) / 1e4, terr = TERR_M2 / 1e4;
  const r = await api("/api/tep", { terr_ha: terr, restrict_ha: restrict, spp_new_m2: sppNew, share, spp_kept_m2: sppKept });
  const m = Object.fromEntries(r.metrics.map(x => [x.id, x.value]));
  return { m, metrics: r.metrics, density: r.density_total, target, terr, restrict, sppNew, sppKept, cover: (fpNew + fpKept) / TERR_M2, n: sketch.length, kept: keptList, demolN: demol.length, demolSpp: demol.reduce((s, f) => s + m2(f) * floorsOf(f), 0), existKey: ek };
}

/* ---------- генератор посадки (локальная рамка, метры) ---------- */
function generate(site, p) {
  if (!site) return [];
  const H = p.floors * 3, out = [], a = p.angle * Math.PI / 180, rings = ringsXY(site); if (!rings.length) return [];
  const bb = bboxOf(rings.flat()), c = [(bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2], R = Math.hypot(bb[2] - bb[0], bb[3] - bb[1]) / 2 + 20;
  const push = (poly, floors) => { const ar = m2(poly); if (ar >= 150) out.push({ f: poly, floors, m2: ar }); };
  const clip = ring => inter(site, polyLL(ring));
  if (p.typ === "Секции") {
    const step = p.width + Math.max(15, p.gap * H), secLen = 60, brk = 12;
    for (let y = -R; y < R; y += step) for (let x = -R; x < R; x += secLen + brk) {
      const r = clip(rect(c[0] + x, c[1] + y, c[0] + x + secLen, c[1] + y + p.width).map(q => rot(q, a, c)));
      if (r && m2(r) > p.width * 24) splitParts(r).forEach(q => push(q, p.floors));
    }
  } else if (p.typ === "Башни") {
    const s = p.width + 8, step = s + Math.max(20, p.gap * H * .6);
    for (let y = -R; y < R; y += step) for (let x = -R; x < R; x += step) {
      const r = clip(rect(c[0] + x, c[1] + y, c[0] + x + s, c[1] + y + s).map(q => rot(q, a, c)));
      if (r && m2(r) > s * s * .97) push(r, Math.round(p.floors * 1.6));
    }
  } else {
    for (const part of splitParts(site)) {
      if (m2(part) < 2500) continue;
      const ring = diff(part, buf(part, -p.width)) || part, pb = bboxOf(ringsXY(part).flat()), cx = (pb[0] + pb[2]) / 2, cy = (pb[1] + pb[3]) / 2;
      const r = diff(ring, polyLL(rect(cx - 7, pb[1] - 5, cx + 7, pb[3] + 5).map(q => rot(q, a, [cx, cy])))) || ring;
      splitParts(r).forEach(q => push(q, Math.max(3, Math.round(p.floors * .7))));
    }
  }
  return out;
}

/* ---------- граф по умолчанию ---------- */
const graph = new LGraph();
function add(type, pos, setup) { const n = LiteGraph.createNode(type); n.pos = pos; graph.add(n); setup?.(n); return n; }
const setW = (n, name, v) => { n.widgets.find(w => w.name === name).value = v; };
const nT = add("Данные/Территория", [20, 20]);
const nZ1 = add("Данные/Слой", [20, 100], n => setW(n, "слой", "Санитарно-защитные зоны (ОГД)"));
const nZ2 = add("Данные/Слой", [20, 240], n => setW(n, "слой", "Водоохранные зоны (ОГД)"));
const nK = add("Данные/Слой", [20, 380], n => { setW(n, "слой", "Здания (ЕГРН)"); setW(n, "поле", "Этажность"); setW(n, "условие", "≥"); setW(n, "значение", "9"); });
const nR = add("Данные/Слой", [20, 540], n => { setW(n, "слой", "Улично-дорожная сеть (OSM)"); setW(n, "поле", "Тип дороги"); setW(n, "условие", "один из"); setW(n, "значение", "trunk,primary,secondary,tertiary,residential,unclassified"); });
const nZ = add("Геометрия/Объединить", [300, 170], n => n.title = "ЗОУИТ");
const nBK = add("Геометрия/Буфер", [300, 400], n => { n.title = "Разрыв до сохраняемых"; setW(n, "расстояние, м", 12); });
const nBR = add("Геометрия/Буфер", [300, 560], n => { n.title = "Отступ от улиц"; setW(n, "расстояние, м", 12); });
const nD1 = add("Геометрия/Вычесть", [520, 40], n => n.title = "Без ЗОУИТ");
const nD2 = add("Геометрия/Вычесть", [720, 110]);
const nD3 = add("Геометрия/Вычесть", [720, 250], n => n.title = "Пятно застройки");
const nNum = add("Параметры/Число", [720, 400], n => { n.title = "Этажность"; setW(n, "значение", 12); });
const nP = add("Эскиз/Посадка застройки", [960, 120]);
const nTep = add("Показатели/ТЭП КРТ", [1240, 150]);
nZ1.connect(0, nZ, 0); nZ2.connect(0, nZ, 1);
nT.connect(0, nD1, 0); nZ.connect(0, nD1, 1);
nK.connect(0, nBK, 0); nR.connect(0, nBR, 0);
nD1.connect(0, nD2, 0); nBK.connect(0, nD2, 1);
nD2.connect(0, nD3, 0); nBR.connect(0, nD3, 1);
nD3.connect(0, nP, 0); nNum.connect(0, nP, 1);
nP.connect(0, nTep, 0); nK.connect(0, nTep, 1); nZ.connect(0, nTep, 2);

const lgc = new LGraphCanvas($("gcv"), graph);
Object.assign(lgc, { background_image: null, clear_background_color: "#e6e6e2", render_canvas_border: false, render_shadows: false, show_info: false, render_connection_arrows: false, title_text_font: "600 12px system-ui, sans-serif", inner_text_font: "11px system-ui, sans-serif", links_render_mode: LiteGraph.SPLINE_LINK });
Object.defineProperty(lgc, "low_quality", { get: () => false, set() { } }); // подписи узлов при любом масштабе
let selNode = null;
lgc.onNodeSelected = n => { selNode = n; updateAnalysisMap(); };
lgc.onNodeDeselected = () => { selNode = null; updateAnalysisMap(); };
function fitGraph() {
  const box = $("graphbox").getBoundingClientRect(), ns = graph._nodes; if (!ns.length || !box.width) return;
  const x0 = Math.min(...ns.map(n => n.pos[0])), y0 = Math.min(...ns.map(n => n.pos[1])) - 30, x1 = Math.max(...ns.map(n => n.pos[0] + n.size[0])), y1 = Math.max(...ns.map(n => n.pos[1] + n.size[1]));
  const s = Math.min(1.1, (box.width - 40) / (x1 - x0), (box.height - 60) / (y1 - y0)); lgc.ds.scale = s; lgc.ds.offset = [20 / s - x0, 50 / s - y0]; lgc.setDirty(true, true);
}
function sizeGraph() { const b = $("graphbox").getBoundingClientRect(); if (b.width) { lgc.resize(Math.round(b.width), Math.round(b.height)); lgc.setDirty(true, true); } }
new ResizeObserver(sizeGraph).observe($("graphbox"));
$("bFitGraph").onclick = fitGraph;
$("bRunGraph").onclick = () => { graph._nodes.forEach(n => { n._ck = n._cacheKey = n._key = null; }); recompute(true); };
const LIB = { "Данные": ["Данные/Территория", "Данные/Слой"], "Параметры": ["Параметры/Число"], "Геометрия": ["Геометрия/Буфер", "Геометрия/Вычесть", "Геометрия/Объединить", "Геометрия/Пересечь"], "Эскиз": ["Эскиз/Посадка застройки"], "Показатели": ["Показатели/ТЭП КРТ"] };
const LIBICON = { "Данные": "database", "Параметры": "sliders-horizontal", "Геометрия": "shapes", "Эскиз": "building-2", "Показатели": "calculator" };
$("lib").innerHTML = Object.entries(LIB).map(([c, ts]) => `<div class="cat">${c}</div>` + ts.map(t => `<button data-add="${t}"><i data-lucide="${LIBICON[c]}"></i>${t.split("/")[1]}</button>`).join("")).join("");
$("lib").addEventListener("click", e => { const b = e.target.closest("[data-add]"); if (!b) return; add(b.dataset.add, lgc.convertCanvasToOffset([$("graphbox").clientWidth / 2 - 100, $("graphbox").clientHeight / 2 - 40])); lgc.setDirty(true, true); });

let lastSig = "", RESULT = { site: null, sketch: [], tep: null };
const signature = () => JSON.stringify([dataRev, Object.values(graph.links || {}).filter(Boolean).map(l => [l.origin_id, l.origin_slot, l.target_id, l.target_slot]), graph._nodes.map(n => [n.id, n.widgets?.map(w => w.value)])]);
function recompute(force) {
  const sig = signature(); if (!force && sig === lastSig) return; lastSig = sig;
  safe(() => graph.runStep(1, true));
  const place = graph._nodes.find(n => n.type === "Эскиз/Посадка застройки"), tepN = graph._nodes.find(n => n.type === "Показатели/ТЭП КРТ");
  RESULT = { site: place?.getInputData(0) || null, sketch: place?.getOutputData(0) || [], tep: tepN?._tep || null, placeNode: place, tepNode: tepN };
  lgc.setDirty(true, true); updateAnalysisMap(); if (ui.step === "sketch") renderSketch();
}
setInterval(() => { if (ui.step !== "collect") recompute(false); }, 250);

/* ---------- карта анализа ---------- */
const prevSrc = new ol.source.Vector(), sketchSrc = new ol.source.Vector(), siteSrc = new ol.source.Vector(), keptSrc = new ol.source.Vector();
const shade = n => ["#dcebfa", "#a8cbf1", "#6fa6e6", "#2a78d6", "#1a4f94"][Math.min(4, Math.floor(n / 6))];
const sketchStyle = f => new ol.style.Style({ fill: new ol.style.Fill({ color: shade(f.get("floors")) }), stroke: new ol.style.Stroke({ color: "#1a4f94", width: 1 }), text: new ol.style.Text({ text: String(f.get("floors")), font: "11px Arial", fill: new ol.style.Fill({ color: f.get("floors") > 14 ? "#fff" : "#123" }) }) });
const siteLayer = () => new ol.layer.Vector({ source: siteSrc, zIndex: 20, style: new ol.style.Style({ fill: new ol.style.Fill({ color: hatch("#1f7a4d") }), stroke: new ol.style.Stroke({ color: "#1f7a4d", width: 1.4, lineDash: [5, 3] }) }) });
const keptLayer = () => new ol.layer.Vector({ source: keptSrc, zIndex: 35, style: S("#bdb8b0", "#4d4d4d", 1) });
const sketchLayer = () => new ol.layer.Vector({ source: sketchSrc, zIndex: 40, style: sketchStyle });
const mAnalysis = newMap("mAnalysis", [siteLayer(), new ol.layer.Vector({ source: prevSrc, zIndex: 30, style: S([224, 138, 0, .28], "#c46f00", 2) }), sketchLayer(), terrLayer()]);
function fillGeom(src, f) { src.clear(); if (f) src.addFeature(toOl(f)); }
function fillSketch() { sketchSrc.clear(); sketchSrc.addFeatures(RESULT.sketch.map(b => { const f = toOl(b.f); f.set("floors", b.floors); return f; })); }
function updateAnalysisMap() {
  fillGeom(siteSrc, RESULT.site); fillSketch(); prevSrc.clear();
  let txt = TERR ? `Пятно застройки ${ha(RESULT.site)} · ${RESULT.sketch.length} корпусов` : "Сначала задайте территорию и загрузите данные (шаг 1)";
  if (selNode) { const out = selNode.getOutputData?.(0), t = selNode.outputs?.[0]?.type;
    if (t === "geom") { if (out) prevSrc.addFeature(toOl(out)); txt = `Выход узла «${selNode.title}»: ${ha(out)}`; }
    else if (t === "tep" && out) txt = `«${selNode.title}»: плотность ${fmt(out.density, 1)} тыс. м²/га, население ${fmt(out.m.population)} чел.`;
    else if (t === "num") txt = `«${selNode.title}»: ${out}`; }
  $("pv").textContent = txt;
}

/* ================= 3. Эскиз ================= */
const mSketch = newMap("mSketch", [siteLayer(), keptLayer(), sketchLayer(), terrLayer()]);
let mBefore = null, mAfter = null, view3d = "2d", rot3d = 0;
function publishedControls() {
  const p = RESULT.placeNode, t = RESULT.tepNode, num = graph._nodes.find(n => n.type === "Параметры/Число" && n.outputs[0].links?.some(id => graph.links[id]?.target_id === p?.id));
  const out = [];
  if (p) out.push({ n: p, w: "типология", type: "seg", opts: ["Секции", "Квартал", "Башни"], hint: "квартал — периметр с проходом, башни — ×1,6 к этажности" });
  if (num) out.push({ n: num, w: "значение", label: "Этажность", min: 3, max: 30, step: 1, hint: "узел «Число» в графе" }); else if (p) out.push({ n: p, w: "этажность", min: 3, max: 30, step: 1 });
  if (p) out.push({ n: p, w: "ширина корпуса, м", min: 12, max: 24, step: 1 }, { n: p, w: "разрыв / высота", min: .5, max: 2, step: .05, hint: "шаг между корпусами = коэф. × высота, не меньше 15 м" }, { n: p, w: "ориентация, °", min: 0, max: 90, step: 1 });
  graph._nodes.filter(n => n.type === "Геометрия/Буфер").forEach(n => out.push({ n, w: "расстояние, м", label: n.title + ", м", min: 0, max: 40, step: 1 }));
  if (t) out.push({ n: t, w: "доля жилья, %", min: 0, max: 100, step: 5 }, { n: t, w: "цель, тыс. м²/га", label: "Целевая плотность, тыс. м²/га", min: 5, max: 45, step: 1 });
  return out;
}
function renderParams() {
  const cs = publishedControls();
  $("params").innerHTML = cs.map((c, i) => { const w = c.n.widgets.find(x => x.name === c.w), lbl = c.label || c.w[0].toUpperCase() + c.w.slice(1);
    if (c.type === "seg") return `<div class="ctl"><div class="t"><span>${lbl}</span></div><div class="seg">${c.opts.map(o => `<button data-seg="${i}" data-v="${o}" aria-pressed="${w.value === o}">${o}</button>`).join("")}</div>${c.hint ? `<small>${c.hint}</small>` : ""}</div>`;
    return `<div class="ctl"><div class="t"><label for="pc${i}">${esc(lbl)}</label><span id="pv${i}">${fmt(w.value, c.step < 1 ? 2 : 0)}</span></div><input type="range" id="pc${i}" data-pc="${i}" min="${c.min}" max="${c.max}" step="${c.step}" value="${w.value}">${c.hint ? `<small>${c.hint}</small>` : ""}</div>`; }).join("")
    + `<div class="note">Параметры узлов графа, вынесенные в панель: правка здесь меняет граф, и наоборот.</div>`;
  $("params").oninput = e => { const i = e.target.dataset.pc; if (i == null) return; const c = cs[+i], w = c.n.widgets.find(x => x.name === c.w); w.value = +e.target.value; $("pv" + i).textContent = fmt(w.value, c.step < 1 ? 2 : 0); recompute(); };
  $("params").onclick = e => { const b = e.target.closest("[data-seg]"); if (!b) return; const c = cs[+b.dataset.seg]; c.n.widgets.find(x => x.name === c.w).value = b.dataset.v; renderParams(); recompute(); };
}
const GROUP_ORDER = ["Территория", "Застройка", "Население", "Социальная инфраструктура", "Обслуживание", "Благоустройство", "Транспорт"];
function renderTep() {
  const t = RESULT.tepNode?._tep; if (!t) { $("tep").innerHTML = `<div class="empty">${TERR ? "Считаю…" : "Нет территории"}</div>`; return; }
  const dCls = t.density > t.target * 1.05 ? "bad" : t.density < t.target * .8 ? "warn" : "good";
  const byGroup = {}; t.metrics.forEach(m => (byGroup[m.group || "Прочее"] ||= []).push(m));
  $("tep").innerHTML = `<div class="sect">Эскиз</div>` + kv([["Новые корпуса", t.n], ["СПП новая", fmt(t.sppNew / 1000, 1) + " тыс. м²"], ["СПП сохраняемая", fmt(t.sppKept / 1000, 1) + " тыс. м²"], ["Плотность итоговая", fmt(t.density, 1) + " тыс. м²/га", dCls], ["Цель", fmt(t.target) + " тыс. м²/га"], ["Застроенность", fmt(t.cover * 100, 1) + " %"], ["Сохраняется", t.kept.length + " зд."], ["Под снос", t.demolN + " зд. · " + fmt(t.demolSpp / 1000, 1) + " тыс. м²"]])
    + Object.entries(byGroup).sort((a, b) => (GROUP_ORDER.indexOf(a[0]) + 99) % 99 - (GROUP_ORDER.indexOf(b[0]) + 99) % 99).map(([g, ms]) => `<div class="sect">${esc(g)} · методика КРТ</div>` + kv(ms.map(m => [m.title, fmt(m.value, Number.isInteger(m.value) ? 0 : 2) + " " + esc(m.unit)]))).join("")
    + `<div class="note">Нормативная часть — движок ТЭП ядра ГРАДО (пресет КРТ Москвы) от СПП новой застройки: население, ДОО, школы, поликлиники, парковки. Ограничения — площадь ЗОУИТ внутри границы. ${t.existKey === "osm.buildings" ? "Существующие здания взяты из OSM: ЕГРН не загружен. " : ""}Перед документацией сверить с действующими нормативами.</div>`;
}
function renderSketch() {
  renderTep(); fillSketch(); fillGeom(siteSrc, RESULT.site);
  keptSrc.clear(); (RESULT.tepNode?._tep?.kept || []).forEach(f => keptSrc.addFeature(toOl(f)));
  if (view3d === "3d") draw3d();
}
document.querySelector(".mtools").addEventListener("click", e => {
  const b = e.target.closest("[data-view]"); if (b) { view3d = b.dataset.view; document.querySelectorAll("[data-view]").forEach(x => x.setAttribute("aria-pressed", x === b)); applyView(); }
  if (e.target.closest("#bRot")) { rot3d = (rot3d + 1) % 4; draw3d(); }
});
function applyView() {
  $("mSketch").hidden = view3d !== "2d"; $("c3d").hidden = view3d !== "3d"; $("splitBox").hidden = view3d !== "cmp"; $("bRot").hidden = view3d !== "3d";
  if (view3d === "cmp" && !mBefore) { mBefore = newMap("mBefore", [terrLayer()]); mAfter = newMap("mAfter", [keptLayer(), sketchLayer(), terrLayer()]); }
  requestAnimationFrame(() => { [mSketch, mBefore, mAfter].forEach(m => m?.updateSize()); if (view3d === "3d") draw3d(); });
}
/* аксонометрия: стены, крыши, порядок по глубине; дороги — земля */
function draw3d() {
  const cv = $("c3d"), r = cv.getBoundingClientRect(), dpr = devicePixelRatio || 1; if (!r.width || !TERR) return;
  cv.width = r.width * dpr; cv.height = r.height * dpr; const x = cv.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, r.width, r.height);
  const terr = ringsXY(TERR)[0], A = rot3d * Math.PI / 2, C = Math.cos(Math.PI / 6), Sn = Math.sin(Math.PI / 6), R = p => rot(p, A, [0, 0]);
  const items = [...RESULT.sketch.flatMap(b => ringsXY(b.f).map(ring => ({ ring, h: b.floors * 3, c: [222, 232, 246], e: [42, 90, 170] }))),
    ...(RESULT.tepNode?._tep?.kept || []).flatMap(f => ringsXY(f).map(ring => ({ ring, h: floorsOf(f) * 3, c: [214, 210, 202], e: [90, 90, 90] })))];
  const P = (p, z) => { const q = R(p); return [(q[0] - q[1]) * C, -(q[0] + q[1]) * Sn - z]; };
  const all = [...terr.map(p => P(p, 0)), ...items.map(i => P(i.ring[0], i.h))], xs = all.map(p => p[0]), ys = all.map(p => p[1]);
  const k = Math.min((r.width - 60) / (Math.max(...xs) - Math.min(...xs) || 1), (r.height - 60) / (Math.max(...ys) - Math.min(...ys) || 1));
  const ox = r.width / 2 - k * (Math.max(...xs) + Math.min(...xs)) / 2, oy = r.height / 2 - k * (Math.max(...ys) + Math.min(...ys)) / 2;
  const T = (p, z = 0) => { const s = P(p, z); return [ox + s[0] * k, oy + s[1] * k]; };
  const poly = (pts, fill, stroke, close = true) => { x.beginPath(); pts.forEach((p, i) => i ? x.lineTo(...p) : x.moveTo(...p)); if (close) x.closePath(); if (fill) { x.fillStyle = fill; x.fill(); } if (stroke) { x.strokeStyle = stroke; x.lineWidth = .7; x.stroke(); } };
  poly(terr.map(p => T(p)), "#f7f6f1", null);
  const roads = DATA["osm.roads"]?.fc.features || [];
  x.lineCap = "round"; roads.forEach(f => { const g = f.geometry; (g.type === "LineString" ? [g.coordinates] : g.type === "MultiLineString" ? g.coordinates : []).forEach(line => { x.beginPath(); line.map(toXY).forEach((p, i) => i ? x.lineTo(...T(p)) : x.moveTo(...T(p))); x.strokeStyle = "#d9d4c9"; x.lineWidth = MAJOR.has(f.properties["Тип дороги"]) ? 4 : 2; x.stroke(); }); });
  poly(terr.map(p => T(p)), null, "#b3261e");
  items.forEach(i => { i.d = R(centroid(i.ring)).reduce((a, b) => a + b, 0); }); items.sort((a, b) => b.d - a.d);
  for (const it of items) {
    let ring = it.ring; if (ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1]) ring = ring.slice(0, -1);
    const sa = ring.reduce((s, p, j) => { const q = ring[(j + 1) % ring.length]; return s + p[0] * q[1] - q[0] * p[1]; }, 0); if (sa < 0) ring = ring.slice().reverse();
    for (let j = 0; j < ring.length; j++) { const a = ring[j], b = ring[(j + 1) % ring.length], ra = R(a), rb = R(b), nx = rb[1] - ra[1], ny = -(rb[0] - ra[0]);
      if (nx + ny < 0) { const lum = nx < ny ? .8 : .66; poly([T(a), T(b), T(b, it.h), T(a, it.h)], `rgb(${it.c.map(v => Math.round(v * lum)).join(",")})`, `rgba(${it.e.join(",")},.6)`); } }
    poly(ring.map(p => T(p, it.h)), `rgb(${it.c.join(",")})`, `rgb(${it.e.join(",")})`);
  }
  x.fillStyle = "#555"; x.font = "11px system-ui, sans-serif"; x.fillText("Объём: этаж 3 м. Серым — сохраняемые здания.", 10, r.height - 10);
}
new ResizeObserver(() => { if (view3d === "3d" && ui.step === "sketch") draw3d(); }).observe($("sketchBox"));

/* ---------- варианты ---------- */
let VARS = [], varSel = -1;
$("bGen").onclick = async () => {
  const p = RESULT.placeNode, t = RESULT.tepNode; if (!p || !RESULT.site) return toast("В графе нет пятна застройки или узла посадки.");
  const base = placeParams(p), share = t.widgets[0].value / 100, target = t.widgets[1].value, kept = t.getInputData(1), lim = t.getInputData(2);
  const combos = [["Секции", 9], ["Секции", 16], ["Квартал", 9], ["Квартал", 14], ["Башни", 12], ["Башни", 20]];
  busy(true);
  try { VARS = await Promise.all(combos.map(async ([typ, floors]) => { const sk = generate(RESULT.site, { ...base, typ, floors }); return { typ, floors, sk, tep: await tepRequest(sk, kept, lim, share, target) }; })); varSel = -1; renderVars(); }
  catch (e) { toast("Варианты не посчитались: " + e.message); } finally { busy(false); }
};
function renderVars() {
  const tb = bboxOf(ringsXY(TERR)[0]), pad = 10, vb = `${tb[0] - pad} ${-tb[3] - pad} ${tb[2] - tb[0] + 2 * pad} ${tb[3] - tb[1] + 2 * pad}`;
  const pts = r => r.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
  $("vlist").innerHTML = VARS.map((v, i) => { const cls = v.tep.density > v.tep.target * 1.05 ? "bad" : v.tep.density < v.tep.target * .8 ? "warn" : "good";
    const sw = Math.max(1, (tb[2] - tb[0]) / 180);
    return `<button class="vc" data-var="${i}" aria-pressed="${i === varSel}"><svg viewBox="${vb}" preserveAspectRatio="xMidYMid meet"><g transform="scale(1,-1)"><polygon points="${pts(ringsXY(TERR)[0])}" fill="#fff" stroke="#b3261e" stroke-width="${sw * 2}" stroke-dasharray="${sw * 8} ${sw * 4}"/>${v.tep.kept.flatMap(f => ringsXY(f)).map(r => `<polygon points="${pts(r)}" fill="#bdb8b0"/>`).join("")}${v.sk.flatMap(b => ringsXY(b.f)).map(r => `<polygon points="${pts(r)}" fill="#6fa6e6" stroke="#1a4f94" stroke-width="${sw}"/>`).join("")}</g></svg>
      <div class="vt">${v.typ} · ${v.floors} эт.</div><div class="vm"><span>плотность</span><b style="color:var(--${cls})">${fmt(v.tep.density, 1)}</b><span>СПП, тыс. м²</span><b>${fmt((v.tep.sppNew + v.tep.sppKept) / 1000, 1)}</b><span>население</span><b>${fmt(v.tep.m.population)}</b></div></button>`; }).join("");
}
$("vlist").addEventListener("click", e => { const b = e.target.closest("[data-var]"); if (!b) return; varSel = +b.dataset.var; const v = VARS[varSel], p = RESULT.placeNode;
  p.widgets.find(w => w.name === "типология").value = v.typ;
  const num = graph._nodes.find(n => n.type === "Параметры/Число" && n.outputs[0].links?.some(id => graph.links[id]?.target_id === p.id));
  (num ? num.widgets[0] : p.widgets.find(w => w.name === "этажность")).value = v.floors;
  recompute(); renderParams(); renderVars(); toast(`Вариант «${v.typ} · ${v.floors} эт.» перенесён в граф.`); });

/* ================= навигация ================= */
const ui = { step: "collect" };
function go(step) {
  if (step !== "collect" && !Object.keys(DATA).length) toast("Данных пока нет: задайте территорию и загрузите источники на шаге 1.");
  ui.step = step; document.querySelectorAll("[data-step]").forEach(b => b.setAttribute("aria-current", b.dataset.step === step));
  ["collect", "analysis", "sketch"].forEach(s => $("st-" + s).hidden = s !== step);
  requestAnimationFrame(() => {
    [mCollect, mAnalysis, mSketch, mBefore, mAfter].forEach(m => m?.updateSize());
    if (step === "analysis") { sizeGraph(); if (!go.fitted) { fitGraph(); go.fitted = true; } }
    if (step !== "collect") recompute(true);
    if (step === "sketch") { renderParams(); renderSketch(); applyView(); }
  });
}
$("steps").addEventListener("click", e => { const b = e.target.closest("[data-step]"); if (b) go(b.dataset.step); });
$("bTheme").onclick = () => { const d = matchMedia("(prefers-color-scheme: dark)").matches, c = document.documentElement.dataset.theme || (d ? "dark" : "light"); document.documentElement.dataset.theme = c === "dark" ? "light" : "dark"; };
document.querySelector(".proj").textContent = "Новый проект · реальные данные";

(async () => {
  try { SOURCES = await api("/api/sources"); await loadStyleLibs(); } catch (e) { toast("Сервер ГРАДО не отвечает: " + e.message); }
  renderSources(); icons(); go("collect");
})();
