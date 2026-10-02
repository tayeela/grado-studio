/* ГРАДО 2: одно рабочее поле — карта со слоями, строка инструментов и плавающие окна
   (данные, граф, эскиз, варианты, показатели, объём, сравнение, таблица). Порядок работы свободный.
   Данные — реальные выгрузки сервера (/api/fetch), ТЭП — движок ядра (/api/tep).
   Геометрия в WGS84 (Turf.js); для посадки и объёма — локальная метрическая рамка вокруг территории. */

const $ = id => document.getElementById(id);
const fmt = (n, d = 0) => Number(n).toLocaleString("ru-RU", { minimumFractionDigits: d, maximumFractionDigits: d });
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const icons = () => lucide.createIcons({ attrs: { "stroke-width": 1.75 } });
// Совместный режим (hub.js ставит window.KEYGUARD): клавиша наблюдателя гасится здесь, в самом первом перехвате окна, —
// обработчики cad.js и layers.js стоят на том же перехвате и идут позже; в обычном режиме KEYGUARD нет и ничего не происходит
// макет листа (layout.js) открыт поверх всего — его клавиши тоже решаются здесь, раньше команд карты
addEventListener("keydown", e => { if (window.LAYKEYS?.(e) || window.KEYGUARD?.(e)) { e.preventDefault(); e.stopImmediatePropagation(); } }, true);
// сообщение внизу по центру; если там стоит окно — над картой сверху, чтобы не закрывать карточки и кнопки окна
let tT; function toast(t) {
  const el = $("toast"); el.textContent = t; el.classList.remove("top"); el.classList.add("on");
  // сообщение — над низом карты (над встроенными снизу окнами и командной строкой), по центру карты; поверх окна — вверху карты
  const m = $("mMain").getBoundingClientRect();
  // над командной строкой по её настоящей высоте (с пометкой она бывает в две строки), иначе — над низом карты
  const cl = document.querySelector(".cmdline:not([hidden])"), cr = cl && cl.offsetParent ? cl.getBoundingClientRect() : null;
  Object.assign(el.style, { left: (m.left + m.width / 2) + "px", bottom: (cr ? innerHeight - cr.top + 8 : innerHeight - m.bottom + 14) + "px", top: "" });
  const r = el.getBoundingClientRect(), hit = [...document.querySelectorAll(".win:not([hidden])")].some(w => { const b = w.getBoundingClientRect(); return b.left < r.right && b.right > r.left && b.top < r.bottom && b.bottom > r.top; });
  if (hit) { el.classList.add("top"); Object.assign(el.style, { top: (m.top + 10) + "px", bottom: "auto" }); }
  clearTimeout(tT); tT = setTimeout(() => el.classList.remove("on"), /^Восстановлена последняя работа/.test(t) ? 2500 : 4200);   // «Восстановлена…» не должна долго висеть над первой командой
}
let busyN = 0; function busy(on) { busyN += on ? 1 : -1; $("busy").hidden = busyN <= 0; }
async function api(path, body, signal) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal } : signal ? { signal } : {});
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
/* Площадь — в плоскости МСК, как её считают AutoCAD (площадь полилинии в координатах чертежа) и ЕГРН: формула
   площади многоугольника по координатам вершин в МСК. turf.area считает на шаре и под Москвой занижает площадь на
   ~0,46 % (КРТ 3141: 48,29 га вместо 48,5180 га по документу; владелец 30.09.2026: «считай так же точно, как в КАД»).
   Пересчёт вершин в МСК дороже, поэтому площадь запоминается у геометрии (геометрии в программе не меняются на месте). */
const M2C = new WeakMap();
function planarArea(g) {
  const ring = r => { let a = 0; const q = r.map(c => MSK.fromWgs(c)), x0 = q[0][0], y0 = q[0][1];
    for (let k = 0; k < q.length - 1; k++) a += (q[k][0] - x0) * (q[k + 1][1] - y0) - (q[k + 1][0] - x0) * (q[k][1] - y0);
    return Math.abs(a) / 2; };
  const poly = rs => rs.reduce((s, r, i) => s + (i ? -1 : 1) * ring(r), 0);
  return g.type === "Polygon" ? poly(g.coordinates) : g.type === "MultiPolygon" ? g.coordinates.reduce((s, p) => s + poly(p), 0)
    : g.type === "GeometryCollection" ? g.geometries.reduce((s, x) => s + planarArea(x), 0) : 0;
}
const m2 = f => {
  if (!f) return 0;
  if (f.type === "FeatureCollection") return f.features.reduce((s, x) => s + m2(x), 0);
  const g = f.geometry || f; if (!g?.type) return 0;
  if (!window.MSK) return turf.area(g);
  let v = M2C.get(g); if (v == null) { v = planarArea(g); M2C.set(g, v); }
  return v;
};
const safe = fn => { try { return fn(); } catch (e) { console.warn(e); return null; } };
/* булевы операции Turf (polygon-clipping) изредка падают на почти совпадающих рёбрах соседних зон
   («Unable to find segment … in SweepLine tree»). Тогда повтор с координатами, округлёнными до ~1 см,
   а затем с «раздутым» на 1 см вычитаемым — иначе пятно застройки молча пропадает целиком. */
const quiet = fn => { try { return { ok: true, v: fn() }; } catch { return { ok: false }; } };
const snap6 = f => turf.truncate(f, { precision: 7, coordinates: 2 });
function robust(op, a, b) {
  const tries = [() => op(a, b), () => op(snap6(a), snap6(b)), () => op(snap6(a), snap6(turf.buffer(b, .01, { units: "meters" }) || b))];
  for (const t of tries) { const r = quiet(t); if (r.ok) return r.v; }
  console.warn("геометрия: операция не удалась и после повторов"); return null;
}
function unionAll(fs) {
  fs = fs.filter(f => f && polys(f).length); if (!fs.length) return null; if (fs.length === 1) return fs[0];
  const all = quiet(() => turf.union(turf.featureCollection(fs))); if (all.ok) return all.v;
  const snapped = quiet(() => turf.union(turf.featureCollection(fs.map(snap6)))); if (snapped.ok) return snapped.v;
  return fs.reduce((a, b) => robust((x, y) => turf.union(turf.featureCollection([x, y])), a, b) || a);
}
const diff = (a, b) => !a ? null : !b ? a : robust((x, y) => turf.difference(turf.featureCollection([x, y])), a, b);
const inter = (a, b) => (a && b) ? robust((x, y) => turf.intersect(turf.featureCollection([x, y])), a, b) : null;
const buf = (a, d) => { if (!a) return null; if (!d) return a; const r = safe(() => turf.buffer(a, d, { units: "meters" })); return r?.geometry ? r : null; };
// ponytail: объединение линий дорог через буфер каждой — O(n) union, для района в сотни улиц хватает
const asArea = f => f && /Line/.test(f.geometry.type) ? buf(f, 0.5) : f;
function rot([x, y], a, c) { const s = Math.sin(a), k = Math.cos(a), dx = x - c[0], dy = y - c[1]; return [c[0] + dx * k - dy * s, c[1] + dx * s + dy * k]; }

/* ---------- карта (EPSG:3857, подложка OSM) ---------- */
const GJ = new ol.format.GeoJSON({ featureProjection: "EPSG:3857" });
const toOl = f => GJ.readFeature(f);
const sharedView = new ol.View({ center: ol.proj.fromLonLat([37.525, 55.7925]), zoom: 15 });
const interactions = () => (ol.interaction.defaults.defaults || ol.interaction.defaults)({ doubleClickZoom: false, altShiftDragRotate: false, pinchRotate: false, shiftDragZoom: false });   // Shift+тянуть — рамка выбора
/* подложки: схема OSM (серая, приглушённая — чтобы читались знаки), спутник Esri, Sentinel-2 без облаков (EOX), без подложки */
const BASEMAPS = {
  osm: { title: "Схема OSM", layer: () => new ol.layer.Tile({ source: new ol.source.OSM(), className: "basemap", opacity: .55 }) },
  esri: { title: "Спутник (Esri)", layer: () => new ol.layer.Tile({ className: "basemap-sat", opacity: .9, source: new ol.source.XYZ({ url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", maxZoom: 19, attributions: "Снимки © Esri, Maxar, Earthstar Geographics" }) }) },
  s2: { title: "Sentinel-2 (EOX)", layer: () => new ol.layer.Tile({ className: "basemap-sat", opacity: .9, source: new ol.source.XYZ({ url: "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2021_3857/default/g/{z}/{y}/{x}.jpg", maxZoom: 15, attributions: "Sentinel-2 cloudless 2021 © EOX IT Services GmbH (содержит изменённые данные Copernicus Sentinel)" }) }) },
  none: { title: "Без подложки", layer: () => new ol.layer.Tile({ visible: false }) } };
let BASE = localStorage.getItem("grado2.base") || "osm"; if (!BASEMAPS[BASE]) BASE = "osm";
const basemap = () => { const l = BASEMAPS[BASE].layer(); l.set("basemap", true); return l; };
function setBasemap(id) {
  if (!BASEMAPS[id]) return; BASE = id; try { localStorage.setItem("grado2.base", id); } catch { }
  ALLMAPS.forEach(m => { const old = m.getLayers().getArray().find(x => x.get("basemap")); if (old) m.removeLayer(old); m.getLayers().insertAt(0, basemap()); });
  if ($("baseSel")) $("baseSel").value = id; window.markDirty?.();
}
const ALLMAPS = [];   // все карты проекта: слои из модели (layers.js) цепляются к каждой
// масштабная линейка по-русски: OpenLayers пишет «50 m» / «1 km»; текст правится сразу после каждого обновления линейки (масштаб, перемещение)
function ruScaleLine() {
  const sl = new ol.control.ScaleLine({ minWidth: 70 });
  new MutationObserver(() => sl.element.querySelectorAll(".ol-scale-line-inner").forEach(e => { const t = e.textContent.replace(/ (k?)m$/, (_, k) => k ? " км" : " м"); if (t !== e.textContent) e.textContent = t; }))
    .observe(sl.element, { childList: true, characterData: true, subtree: true });
  return sl;
}
function newMap(target, layers) { const m = new ol.Map({ target, layers: [basemap(), ...layers], view: sharedView, controls: [ruScaleLine(), new ol.control.Attribution({ collapsible: false })], interactions: interactions() }); ALLMAPS.push(m); window.attachDataLayers?.(m); return m; }
const PAT = new Map();
/* штриховка: узор (45, 135, 0 — горизонталь, 90 — вертикаль, x45 — косая сетка, x0 — прямая сетка, dots — точки) и шаг в пикселях */
const HATCHES = { "45": "косая ／", "135": "косая ＼", "0": "горизонтальная", "90": "вертикальная", "x45": "косая сетка", "x0": "прямая сетка", "dots": "точки" };
function hatch(color, pat = "45", step = 8) {
  const k = color + "|" + pat + "|" + step; if (PAT.has(k)) return PAT.get(k);
  const n = Math.max(4, Math.min(40, Math.round(step))), c = document.createElement("canvas"); c.width = c.height = n; const x = c.getContext("2d");
  x.fillStyle = color + "18"; x.fillRect(0, 0, n, n); x.strokeStyle = x.fillStyle = color; x.lineWidth = 1.1; x.beginPath();
  const d45 = () => { x.moveTo(0, n); x.lineTo(n, 0); x.moveTo(-n / 2, n / 2); x.lineTo(n / 2, -n / 2); x.moveTo(n / 2, n * 1.5); x.lineTo(n * 1.5, n / 2); };
  const d135 = () => { x.moveTo(0, 0); x.lineTo(n, n); x.moveTo(-n / 2, n / 2); x.lineTo(n / 2, n * 1.5); x.moveTo(n / 2, -n / 2); x.lineTo(n * 1.5, n / 2); };
  const h = () => { x.moveTo(0, n / 2); x.lineTo(n, n / 2); }, v = () => { x.moveTo(n / 2, 0); x.lineTo(n / 2, n); };
  if (pat === "dots") { x.arc(n / 2, n / 2, 1.2, 0, 2 * Math.PI); x.fill(); }
  else { ({ "45": [d45], "135": [d135], "0": [h], "90": [v], x45: [d45, d135], x0: [h, v] }[pat] || [d45]).forEach(f => f()); x.stroke(); }
  const p = x.createPattern(c, "repeat"); PAT.set(k, p); return p; }
const S = (fill, stroke, w = 1) => new ol.style.Style({ fill: fill && new ol.style.Fill({ color: fill }), stroke: stroke && new ol.style.Stroke({ color: stroke, width: w }) });
const MAJOR = new Set(["motorway", "trunk", "primary", "secondary", "tertiary"]);

/* ---------- знаки: ЛГР (коды, цвета, штрих) и Генплан — из библиотек ядра ---------- */
const LGRC = {}, LGRD = {}, LGRT = {}, LGRS = {}, GPZ = {}, NMZ = {};   // LGRS — знак Эталона целиком (штриховка, штрих в пикселях)
async function loadStyleLibs() {
  await Linetypes.load();
  const [lgr, gp] = await Promise.all(["/styles/moscow_lgr.json", "/styles/moscow_genplan.json"].map(u => fetch(u).then(r => r.json())));
  Object.values(lgr.styles).forEach(s => { if (s.lgr_code != null) { LGRS[+s.lgr_code] = s; LGRC[+s.lgr_code] = s.stroke; LGRT[+s.lgr_code] = s.title; if (s.dash_mm) LGRD[+s.lgr_code] = s.dash_mm.map(v => v * 2); } }); // мм на 1:2000 → метры
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
let TERR = null, TERR_M2 = 0, dataRev = 0, TERR_REV = 0;   // TERR_REV — номер версии границы: узлы графа пересчитываются при её перерисовке
const terrSrc = new ol.source.Vector(), layerSrc = {};
const terrStyle = S(null, "#b3261e", 2); terrStyle.getStroke().setLineDash([12, 4, 2, 4]);
const terrLayer = () => new ol.layer.Vector({ source: terrSrc, style: terrStyle, zIndex: 110 });

/* ================= данные территории ================= */
const mMain = newMap("mMain", [terrLayer()]);
function setTerritory(feature) {
  TERR = turf.feature(feature.geometry); TERR_M2 = m2(TERR); TERR_REV++;
  setFrame(turf.centroid(TERR).geometry.coordinates);
  terrSrc.clear(); terrSrc.addFeature(toOl(TERR));
  updateCover();
  $("bLoad").disabled = false; dataRev++; window.syncStatus?.(); window.syncStart?.(); window.markDirty?.(); if (!$("wData").hidden) renderSources(); if (!$("wSketch").hidden) renderParams(); if (!$("w3d").hidden) draw3d();
  sharedView.fit(terrSrc.getExtent(), { padding: [40, 40, 40, 40], maxZoom: 17 });
}
/* Область загрузки данных = рамки листов альбома (карты в своём формате и масштабе, со сдвигом), а не граница
   участка: всё, что попадёт на листы, должно быть загружено. Обзорные схемы (Москва, округ, район) и листы из двух карт
   грузят своё сами при сборке раздела. Листов нет — рамка листа А3 в автомасштабе вокруг территории.
   Пока открыто окно «Данные», область показана на карте синим пунктиром. */
const coverSrc = new ol.source.Vector();
const coverStyle = new ol.style.Style({ stroke: new ol.style.Stroke({ color: "#1a5fb4", width: 1.5, lineDash: [6, 5] }),
  text: new ol.style.Text({ text: "область загрузки данных", font: "12px system-ui, sans-serif", placement: "line", fill: new ol.style.Fill({ color: "#1a5fb4" }),
    stroke: new ol.style.Stroke({ color: "#fff", width: 3 }), textBaseline: "bottom", offsetY: -3 }) });
const coverLayer = new ol.layer.Vector({ source: coverSrc, style: coverStyle, zIndex: 105, visible: false });
mMain.addLayer(coverLayer);
function coverSheets() {
  const sh = (typeof ALBUM !== "undefined" ? ALBUM.sheets : []).filter(s => !["tep", "title", "photos"].includes(s.kind) && !s.fit && !s.panels);
  return sh.length ? sh : [newSheet()];
}
function coverBox() {
  const own = typeof ALBUM !== "undefined" && coverSheets()[0] && ALBUM.sheets.includes(coverSheets()[0]);
  const bs = [...(own || TERR ? coverSheets().map(frameBox) : []), ...(TERR ? [turf.bbox(buf(TERR, 60))] : [])];
  if (!bs.length) return null;
  return [Math.min(...bs.map(b => b[0])), Math.min(...bs.map(b => b[1])), Math.max(...bs.map(b => b[2])), Math.max(...bs.map(b => b[3]))];
}
function updateCover() {
  coverSrc.clear(); const b = coverBox(); $("bLoad").disabled = !b;
  if (!b) { $("terrInfo").textContent = "Нарисуйте лист (кнопка «Лист» на ленте) или границу территории — данные загружаются на них."; return; }
  const n = coverSheets(), own = ALBUM.sheets.includes(n[0]);
  coverSrc.addFeature(new ol.Feature(ol.geom.Polygon.fromExtent(b).transform("EPSG:4326", "EPSG:3857")));
  const km = (b[2] - b[0]) * 111.32 * Math.cos((b[1] + b[3]) / 2 * Math.PI / 180), kmy = (b[3] - b[1]) * 110.54;
  const what = own ? (n.length === 1 ? "рамку листа" : `рамки ${plural(n.length, ["листа", "листов", "листов"])}`) : "рамку листа А3 вокруг территории (листов пока нет — нарисуйте инструментом «Лист»)";
  $("terrInfo").textContent = `${TERR ? `Площадь ${fmt(TERR_M2 / 1e4, 2)} га. ` : ""}Данные загружаются на ${what}: ${fmt(km, 1)} × ${fmt(kmy, 1)} км, на карте — синий пунктир.`;
}
window.updateCover = updateCover;
new MutationObserver(() => {
  coverLayer.setVisible(!$("wData").hidden); if ($("wData").hidden) return; updateCover();
  // область целиком за краем экрана не видна — карта отдаляется, чтобы пунктир было видно весь
  const ex = coverSrc.getExtent(); if (coverSrc.getFeatures().length && !ol.extent.containsExtent(sharedView.calculateExtent(mMain.getSize()), ex))
    sharedView.fit(ex, { padding: [40, 40, 40, 40], duration: 250 });
}).observe($("wData"), { attributes: true, attributeFilter: ["hidden"] });
$("bDraw").onclick = () => setTool("terr");
/* Граница из файла (DXF, DWG, GeoJSON, KML/KMZ, Shapefile): самый большой полигон или замкнутая полилиния файла становится
   границей территории. Местные метры читаются в системе, выбранной в «Файлы в метрах» (по умолчанию МСК), как при импорте. */
function pickBoundary(then) {
  const inp = document.createElement("input"); inp.type = "file"; inp.multiple = true;
  inp.accept = ".dxf,.dwg,.geojson,.json,.kml,.kmz,.zip,.shp,.dbf,.shx,.prj,.cpg";
  inp.onchange = () => importBoundary([...inp.files]).then(ok => ok && then?.()); inp.click();
}
async function importBoundary(files) {
  if (!files.length) return false;
  busy(true);
  try {
    const body = { local: $("impLocal")?.value || "msk", files: await Promise.all(files.map(async f => ({ name: f.name, b64: b64(await f.arrayBuffer()) }))) };
    const r = await fetch("/api/import/files", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }), j = await r.json();
    if (!r.ok) throw new Error(j.error);
    const closed = c => c.length > 3 && turf.distance(c[0], c[c.length - 1]) * 1000 < .5;      // концы ближе 0,5 м — контур замкнут
    const polys = j.layers.flatMap(l => l.features.features).flatMap(f => {
      const g = f.geometry; if (!g) return [];
      if (g.type === "Polygon") return [turf.polygon(g.coordinates)];
      if (g.type === "MultiPolygon") return g.coordinates.map(c => turf.polygon(c));
      const ls = g.type === "LineString" ? [g.coordinates] : g.type === "MultiLineString" ? g.coordinates : [];
      return ls.filter(closed).map(c => safe(() => turf.polygon([[...c.slice(0, -1), c[0]]]))).filter(Boolean);
    });
    if (!polys.length) throw new Error("в файле нет замкнутых контуров");
    polys.sort((a, b) => turf.area(b) - turf.area(a));
    setTerritory(polys[0]);
    toast(`Граница из файла «${files[0].name}»: ${fmt(TERR_M2 / 1e4, 2)} га${polys.length > 1 ? `; взят самый большой из ${polys.length} контуров` : ""}.`);
    return true;
  } catch (e) { toast("Граница не прочитана: " + e.message); return false; } finally { busy(false); }
}
window.pickBoundary = pickBoundary;
$("bTerrFile").onclick = () => pickBoundary();
/* Граница по кадастровым номерам: территория — объединение участков НСПД (владелец 30.09.2026: границу КРТ 3141 —
   по участкам 50:27:0000000:126 и 77:22:0030223:315, 48,5180 га в документе заказчика). Номера вставляются как есть,
   из таблицы или письма: берутся все строки вида 00:00:0000000:000. */
{ const b = document.createElement("button"); b.className = "btn"; b.id = "bParcels"; b.title = "Граница территории — объединение земельных участков по кадастровым номерам";
  b.innerHTML = '<i data-lucide="grid-2x2"></i>По участкам'; $("bExample").before(b); window.lucide?.createIcons?.();
  b.onclick = async () => {
    const src = (DATA["nspd.parcels"]?.fc?.features || []).filter(f => /Polygon/.test(f.geometry?.type));
    const s = prompt("Кадастровые номера участков территории (через запятую, пробел или с новой строки):", "");
    const want = [...new Set(String(s || "").match(/\d+:\d+:\d+:\d+/g) || [])]; if (!want.length) return;
    if (!src.length) return boundaryByNumbers(want.join(", "));   // участков НСПД в проекте нет — берём их у портала по номерам
    const got = want.map(k => src.filter(f => String(f.properties?.["Кадастровый номер"] || "").trim() === k));
    const miss = want.filter((k, i) => !got[i].length);
    if (miss.length) { toast(`Нет среди загруженных участков: ${miss.join(", ")}. Граница не изменена.`); return; }
    const u = unionAll(got.flat()); if (!u) { toast("Участки не объединились — граница не изменена."); return; }
    setTerritory(u); toast(`Граница — по ${want.length} участкам: ${fmt(TERR_M2 / 1e4, 4)} га.`);
  }; }
/* ---------- поиск над картой: адрес (OpenStreetMap) и кадастровый номер (НСПД); сервер — /api/search ---------- */
const parcelsWord = n => plural(n, ["участок", "участка", "участков"]);
const haOf = f => { const a = m2(f) / 1e4; return fmt(a, a < 1 ? 4 : 2) + " га"; };
const srchErr = e => { const m = String(e?.message || e);
  return /busy/i.test(m) ? "Поиск занят другим запросом — повторите через минуту"
    : /NSPD/i.test(m) ? "Портал НСПД не ответил — повторите позже"
    : /Nominatim/i.test(m) ? "Сервис адресов OpenStreetMap не ответил — повторите позже"
    : /no valid cadastral/i.test(m) ? "Не похоже на кадастровый номер. Пример: 50:27:0000000:126"
    : /Failed to fetch|NetworkError|Load failed/i.test(m) ? "Нет связи с программой ГРАДО — повторите" : "Поиск не удался — повторите позже"; };
const searchApi = (kind, q, signal) => api(`/api/search${kind ? "/" + kind : ""}?q=${encodeURIComponent(q)}`, null, signal);
/* участки найденные по номерам попадают в слой «Земельные участки (ЕГРН)» как при обычной загрузке: уже стоящие там не дублируются */
/* один участок — один ключ, откуда бы он ни пришёл: поиск знает номер, выгрузка по области — id объекта портала, поэтому
   у участков с кадастровым номером ключом служит он (так же в mergeDownload) */
const cadOf = f => String(f?.properties?.["Кадастровый номер"] || "").trim();
const parcelKey = f => cadOf(f) || f?.properties?._key || "";
function addParcels(feats) {
  const k = "nspd.parcels", prev = DATA[k], have = prev?.fc?.features || [], seen = new Set(have.flatMap(f => [f.properties?._key, cadOf(f)]).filter(Boolean));
  const add = feats.filter(f => { const a = [f.properties?._key, cadOf(f)].filter(Boolean); if (a.some(x => seen.has(x))) return false; a.forEach(x => seen.add(x)); return true; }).map(f => cadOf(f) ? { ...f, properties: { ...f.properties, _key: cadOf(f) } } : f); if (!add.length && prev) return;
  const fc = { type: "FeatureCollection", features: [...have, ...add] }, title = prev?.title || SOURCES[k]?.title || "Земельные участки (ЕГРН)";
  SOURCES[k] ||= { title, kind: "nspd" };
  DATA[k] = { ...(prev || {}), title, source: prev?.source || "НСПД (nspd.gov.ru), поиск по кадастровому номеру", fetched_at: prev?.fetched_at || new Date().toISOString().slice(0, 10), fc, count: fc.features.length,
    fields: [...new Set(fc.features.slice(0, 200).flatMap(f => Object.keys(f.properties || {})))], original: { type: "FeatureCollection", features: [...(prev?.original?.features || []), ...add] }, history: prev?.history || [] };
  layerSrc[k] ||= new ol.source.Vector(); setLayerData(k, fc); const l = ensureLayer(k, title); assignCats(l, true); restyle(l);
  dataRev++; if (!$("wData").hidden) renderSources(); window.syncStatus?.(); window.markDirty?.();
}
/* граница по найденным участкам — тот же путь, что у «По участкам»: объединение участков → setTerritory */
function parcelsToTerritory(feats) {
  const polys = feats.filter(f => /Polygon/.test(f.geometry?.type)); if (!polys.length) { toast("У найденных участков нет контура — граница не изменена."); return false; }
  const u = unionAll(polys); if (!u) { toast("Участки не объединились — граница не изменена."); return false; }
  addParcels(polys); setTerritory(u); toast(`Граница по участкам: ${parcelsWord(polys.length)}, ${fmt(TERR_M2 / 1e4, 2)} га.`); return true;
}
async function boundaryByNumbers(q) {
  busy(true);
  try { const r = await searchApi("cadastral", q), feats = (r.features || []).filter(f => /Polygon/.test(f.geometry?.type));
    if (r.missing?.length) return toast(`Не найдено: ${r.missing.join(", ")}. Граница не изменена.`);
    if (!feats.length) return toast("Участки не найдены — граница не изменена.");
    parcelsToTerritory(feats);
  } catch (e) { toast(srchErr(e) + ". Граница не изменена."); } finally { busy(false); }
}
{ const inp = $("sq"), go = $("sqGo"), box = $("sres"), mk = new ol.source.Vector();
  mMain.addLayer(new ol.layer.Vector({ source: mk, zIndex: 120, style: f => f.getGeometry().getType() === "Point"
    ? [new ol.style.Style({ image: new ol.style.Circle({ radius: 9, stroke: new ol.style.Stroke({ color: "#1a5fb4", width: 2 }), fill: new ol.style.Fill({ color: "rgba(26,95,180,.12)" }) }) }), new ol.style.Style({ image: new ol.style.Circle({ radius: 2.5, fill: new ol.style.Fill({ color: "#1a5fb4" }) }) })]
    : new ol.style.Style({ stroke: new ol.style.Stroke({ color: "#1a5fb4", width: 2.5 }), fill: new ol.style.Fill({ color: "rgba(26,95,180,.10)" }) }) }));
  let R = null, act = -1, tok = 0, pend = false, ctl = null, tAsk = null;   // ctl — единственный запрос в полёте: новый поиск, закрытие и правка запроса отменяют прежний
  const dur = () => matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 250;
  const fitExt = ext => sharedView.fit(ext, { padding: [60, 60, 60, 60], maxZoom: 18, duration: dur() });
  const say = (t, bad) => { box.innerHTML = `<div class="srm${bad ? " bad" : ""}" role="status">${esc(t)}</div>`; box.hidden = false; R = null; act = -1; };
  const clearMark = () => mk.clear();
  const close = () => { tok++; ctl?.abort(); ctl = null; clearTimeout(tAsk); tAsk = null; box.hidden = true; box.innerHTML = ""; R = null; act = -1; clearMark(); pend = false; go.disabled = false; inp.removeAttribute("aria-busy"); };
  const marks = () => [...box.querySelectorAll(".sri")];
  const setAct = i => { const it = marks(); if (!it.length) return; act = (i + it.length) % it.length; it.forEach((el, j) => { el.classList.toggle("act", j === act); el.setAttribute("aria-selected", j === act); }); it[act].scrollIntoView({ block: "nearest" }); };
  function render() {
    const notes = (R.notes || []).filter(n => !/^Ничего не найдено/.test(n));
    if (R.type === "address") {
      box.innerHTML = R.list.map((x, i) => `<div class="sri" role="option" data-i="${i}"><b>${esc(x.name || x.display)}</b>${x.name && x.display ? `<span>${esc(x.display)}</span>` : ""}</div>`).join("")
        + notes.map(n => `<div class="srm">${esc(n)}</div>`).join("");
    } else {
      box.innerHTML = R.list.map((f, i) => `<div class="sri" role="option" data-i="${i}"><b>${esc(f.properties?.["Кадастровый номер"] || f.properties?._key || "")}</b><span>${haOf(f)}${f.properties?.["ВРИ"] ? " · " + esc(f.properties["ВРИ"]) : ""}</span></div>`).join("")
        + (R.missing.length ? `<div class="srm bad">Не найдено: ${esc(R.missing.join(", "))}</div>` : "") + notes.map(n => `<div class="srm">${esc(n)}</div>`).join("")
        + (R.list.length ? `<div class="sra"><button class="btn" data-a="show">Показать на карте</button><button class="btn" data-a="terr">Сделать границей территории</button></div>` : "");
    }
    clearTimeout(tAsk); tAsk = null; box.hidden = false; act = -1; window.lucide?.createIcons?.();
  }
  function pick(i) {
    const x = R?.list[i]; if (!x) return; clearMark();
    if (R.type === "address") {
      const [w, s, e, n] = x.bbox || [x.lon, x.lat, x.lon, x.lat], c = ol.proj.fromLonLat([x.lon, x.lat]);
      mk.addFeature(new ol.Feature(new ol.geom.Point(c)));
      if (w === e || s === n) sharedView.animate({ center: c, zoom: 17, duration: dur() }); else fitExt(ol.proj.transformExtent([w, s, e, n], "EPSG:4326", "EPSG:3857"));
    } else { const f = toOl(x); mk.addFeature(f); fitExt(f.getGeometry().getExtent()); }
  }
  async function run() {
    const q = inp.value.trim(); if (!q) return;
    ctl?.abort(); ctl = new AbortController(); const sig = ctl.signal;
    clearMark(); pend = true; go.disabled = true; inp.setAttribute("aria-busy", "true"); box.hidden = false; say("Ищу…"); const my = ++tok;
    try { const r = await searchApi("", q, sig); if (my !== tok || sig.aborted) return;
      if (r.type === "cadastral") { R = { type: "cadastral", list: (r.features || []), missing: r.missing || [], notes: r.notes || [] };
        if (!R.list.length && !R.missing.length) return say(R.notes[0] || "Ничего не нашлось", true); render(); }
      else { const list = r.results || []; if (!list.length) return say("Ничего не нашлось в Москве и области"); R = { type: "address", list, notes: r.notes || [] }; render(); }
    } catch (e) { if (my === tok) say(srchErr(e), true); }
    finally { if (my === tok) { ctl = null; pend = false; go.disabled = false; inp.removeAttribute("aria-busy"); } }
  }
  const tBack = b => { clearTimeout(tAsk); tAsk = null; if (b?.dataset.lb) { b.textContent = b.dataset.lb; delete b.dataset.lb; } };
  const act2 = (a, btn) => { if (!R || R.type !== "cadastral") return; clearMark();
    if (a === "terr") {      // чужую границу молча не заменяем: первый щелчок — вопрос на месте (как у «Пример»), второй за 5 с — замена
      if (TERR && !tAsk) { btn.dataset.lb = btn.textContent; btn.textContent = "Заменить вашу границу участками?"; tAsk = setTimeout(() => tBack(btn), 5000); return; }
      tBack(btn); if (parcelsToTerritory(R.list)) close(); return; }
    addParcels(R.list); const ex = ol.extent.createEmpty(); R.list.forEach(f => ol.extent.extend(ex, toOl(f).getGeometry().getExtent())); fitExt(ex); toast(`На карте: ${parcelsWord(R.list.length)} в слое «${DATA["nspd.parcels"]?.title || "Земельные участки (ЕГРН)"}».`); };
  go.onclick = run;
  inp.addEventListener("keydown", e => {
    if (e.isComposing) return;
    if (e.key === "Enter") { e.preventDefault(); if (act >= 0 && R) pick(act); else run(); }
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") { if (!box.hidden && marks().length) { e.preventDefault(); setAct(act < 0 ? (e.key === "ArrowDown" ? 0 : -1) : act + (e.key === "ArrowDown" ? 1 : -1)); } }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); inp.value = ""; close(); inp.blur(); mMain.getTargetElement()?.focus?.({ preventScroll: true }); }
  });
  inp.addEventListener("input", () => { if (R || !box.hidden || pend) close(); });   // правка запроса сбрасывает устаревший список; запрос уходит только по Enter или кнопке
  box.addEventListener("click", e => { const a = e.target.closest("[data-a]"); if (a) return act2(a.dataset.a, a); const it = e.target.closest(".sri"); if (it) pick(+it.dataset.i); });
  addEventListener("pointerdown", e => { if (!box.hidden && !$("msearch").contains(e.target)) close(); }, true);
  addEventListener("keydown", e => { if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.code === "KeyF") {
    if (!inp.offsetParent) return;                                                     // поле поиска не видно — Ctrl+F остаётся браузеру
    const t = e.target; if (t !== inp && t?.closest?.("input, textarea, select, [contenteditable]")) return;   // фильтр таблицы и другие поля ввода — свои
    e.preventDefault(); e.stopImmediatePropagation(); inp.focus(); inp.select(); } }, true);
}
/* «Пример» не заменяет границу пользователя молча: первый щелчок превращает кнопку в вопрос, второй в течение 5 с заменяет */
{ const b = $("bExample"); let ask = null; const back = () => { clearTimeout(ask); ask = null; if (b.dataset.lb) { b.innerHTML = b.dataset.lb; delete b.dataset.lb; window.lucide?.createIcons?.(); } };
  b.addEventListener("click", e => {
    if (!TERR || ask) { back(); return; }
    e.stopImmediatePropagation(); b.dataset.lb = b.innerHTML; b.textContent = "Заменить вашу границу примером?"; ask = setTimeout(back, 5000);
  }, true); }
$("bExample").onclick = () => setTerritory(turf.polygon([[[37.5195, 55.7895], [37.5305, 55.7895], [37.5305, 55.7955], [37.5195, 55.7955], [37.5195, 55.7895]]]));
/* «Выбрать и загрузить…» без границы и листа недоступна: подсказка говорит почему */
{ const b = $("bLoad"), t0 = b.title, off = "Сначала нарисуйте границу территории или лист — данные загружаются на них.";
  const sync = () => { const w = b.disabled ? (coverBox() ? "Сейчас идёт выгрузка — дождитесь конца." : off) : t0; if (b.title !== w) b.title = w; };
  new MutationObserver(sync).observe(b, { attributes: true, attributeFilter: ["disabled"] }); sync(); }
const GROUP = { gisogd_admin: "Административное деление Москвы (эталон)", fgistp: "ФГИС ТП (загруженные слои документов)", import: "Импорт файлов", nspd: "ЕГРН · НСПД", osm: "OpenStreetMap", gisogd: "ГИС ОГД Москвы (первая выгрузка слоя идёт целиком — до 200 МБ и пары минут; дальше из кэша)",
  egko: "ЕГКО Москвы — картооснова ГИС ОГД (первая выгрузка слоя идёт целиком по всей Москве — до 1,3 ГБ и нескольких минут; дальше из кэша)", terrain: "Рельеф",
  yandex: "Яндекс Карты, для анализа и эскиза; в сдаваемые материалы не включать (область до 40 км²; первая выгрузка 1 км² — около минуты, дальше с диска)" };
const CHECKED = new Set(["nspd.parcels", "nspd.buildings", "osm.roads", "osm.buildings", "osm.water", "osm.landuse", "gisogd.szz", "gisogd.vodookhr"]);
const histText = d => { const h = d.history || [], x = h[h.length - 1]; return h.length > 1 && x.added != null ? ` · выгрузок ${h.length}, в последней +${x.added} −${x.removed} ~${x.changed}` : ""; };
/* окно «Данные»: что уже в проекте — по группам источников, с числом объектов, датой и ошибкой выгрузки. Выбор
   источников — окно «Исходные данные» (ogdpick.js), кнопка «Выбрать и загрузить…» */
function renderSources() {
  Object.keys(DATA).filter(k => k.startsWith("ogd.") && !SOURCES[k]).forEach(k => { SOURCES[k] = { title: DATA[k].title, kind: "gisogd" }; });
  const groups = {}; Object.entries(SOURCES).filter(([k]) => DATA[k] || ERRORS[k]).forEach(([k, s]) => (groups[s.kind] ||= []).push(k));
  const stale = (window.STALE_OGD || []).filter(k => DATA[k] && !DATA[k].shp);
  $("srcList").innerHTML = (stale.length ? `<div class="note warn">${stale.map(k => "«" + esc(DATA[k].title) + "»").join(", ")} ${stale.length === 1 ? "выгружен" : "выгружены"} до v0.32 и ${stale.length === 1 ? "стоит" : "стоят"} на ~7,7 м в стороне (портал отдавал смещённый GeoJSON). Ваши правки объектов сохранятся. <button class="btn" id="bStale">Выгрузить заново</button></div>` : "")
    + Object.entries(groups).map(([g, ks]) => `<div class="src"><div class="srch"><i data-lucide="database"></i><b>${esc(GROUP[g] || g)}</b></div>` + ks.map(k => {
    const d = DATA[k], e = ERRORS[k];
    return `<div class="lr"><span class="nm" title="${esc(d?.source || "")}">${esc(SOURCES[k].title)}</span><span class="c num">${d ? d.count : ""}</span></div>` + (e ? `<div class="err">${esc(e)}</div>` : "") + (d ? `<div class="err" style="color:var(--faint)">выгрузка ${esc(d.fetched_at)}${esc(histText(d))}${d.notes?.length ? " · " + esc(d.notes[0]) : ""}</div>` : "");
  }).join("") + `</div>`).join("") + (Object.keys(groups).length ? "" : `<div class="note">В проекте пока нет загруженных данных. «Выбрать и загрузить…» — окно всех источников: ЕГРН, ГИС ОГД (все слои портала), ЕГКО, OpenStreetMap, Яндекс, рельеф.</div>`) + (Object.keys(DATA).length ? `<div class="sect">Существующее положение</div>${kv(existingSummary())}` : "")
    + `<div id="fgBox">${fgHTML()}</div>`
    + `<div class="note">Загруженные слои появляются в списке слоёв; их можно править, исходная выгрузка сохраняется (меню слоя → «Вернуть исходную выгрузку»). В схеме расчёта слои доступны блоком «Слой». Красные линии рисуются типами линий REDLN97 — <a href="linetypes.html" target="_blank">каталог типов</a>.</div>`;
  icons();
}
$("srcList").addEventListener("click", e => {
  if (e.target.closest("#bStale")) { const b = coverBox(); if (b) loadKeys((window.STALE_OGD || []).filter(k => DATA[k]), b); }
});
$("srcList").addEventListener("change", e => {
  const k = e.target.dataset.src; if (k) e.target.checked ? CHECKED.add(k) : CHECKED.delete(k);
  if (e.target.id === "fgDoc") fgPick(e.target.value);
  if (e.target.dataset.fgl) { e.target.checked ? FG.sel.add(e.target.dataset.fgl) : FG.sel.delete(e.target.dataset.fgl); $("fgLoad").disabled = !FG.sel.size; }
});
$("srcList").addEventListener("input", e => { if (e.target.id === "fgQ") { clearTimeout(fgQT); fgQT = setTimeout(() => fgSearch(e.target.value), 450); } });
$("srcList").addEventListener("click", e => { if (e.target.closest("#fgFind")) fgFind(); if (e.target.closest("#fgLoad")) fgLoad(); });

/* ---------- ФГИС ТП: документы терпланирования, чей охват накрывает территорию → их слои ---------- */
const FG = { docs: null, uin: "", layers: null, sel: new Set(), msg: "", q: "" };
const GEOMW = { "100": "полигоны", "010": "линии", "001": "точки" };
function fgHTML() {
  let h = `<div class="src"><div class="srch"><i data-lucide="landmark"></i><b>ФГИС ТП — документы территориального планирования</b><button class="btn" id="fgFind" ${TERR ? "" : "disabled"} title="Генпланы, схемы и их изменения, охват которых накрывает территорию (каталог Минэкономразвития)">Найти по территории</button></div>`;
  if (TERR) h += `<div class="lr" style="height:auto;padding:4px 8px"><input type="search" id="fgQ" value="${esc(FG.q || "")}" placeholder="Поиск по названию во всём каталоге, например «генеральный план москвы»" aria-label="Поиск документа ФГИС ТП по названию" style="width:100%"></div>`;
  if (FG.msg) h += `<div class="note">${esc(FG.msg)}</div>`;
  const inMoscow = TERR && (([x, y]) => x > 36.8 && x < 37.97 && y > 55.1 && y < 56.02)(turf.centroid(TERR).geometry.coordinates);
  if (inMoscow) h += `<div class="note">Генеральный план Москвы в ФГИС ТП не размещён (проверено по всему каталогу): его функциональные зоны — в группе «ГИС ОГД» выше. Здесь для Москвы есть схемы РФ и генплан Троицка.</div>`;
  if (FG.docs) h += `<div class="lr" style="height:auto;padding:4px 8px"><select id="fgDoc" style="width:100%"><option value="">— документ (${FG.docs.length}${FG.q ? ", найдено по названию" : ", по охвату территории"}) —</option>${FG.docs.map(d => `<option value="${esc(d.uin)}" ${d.uin === FG.uin ? "selected" : ""}>${esc(d.name.slice(0, 140))}${d.km ? ` · ${fmt(d.km)} км` : ""}</option>`).join("")}</select></div>`;
  if (FG.layers) h += FG.layers.map(l => `<label class="lr"><input type="checkbox" data-fgl="${esc(l.classid)}" ${FG.sel.has(l.classid) ? "checked" : ""}><span class="nm" title="${esc(l.class_name || "")}">${esc(l.class_title || l.class_name || l.classid)}</span><span class="c">${GEOMW[l.geom_type] || ""}</span></label>`).join("")
    + `<div class="lr" style="height:32px"><span class="sp" style="flex:1"></span><button class="btn primary" id="fgLoad" ${FG.sel.size ? "" : "disabled"}>Загрузить выбранные</button></div>`;
  return h + `</div>`;
}
// перерисовка не теряет набранное в поиске, пока ответ шёл
const fgRender = () => { const el = $("fgBox"); if (!el) return; const q = $("fgQ"), typed = q?.value, focus = q && document.activeElement === q;
  el.innerHTML = fgHTML(); icons(); const n = $("fgQ"); if (n && typed != null) { n.value = typed; if (focus) { n.focus(); n.setSelectionRange(typed.length, typed.length); } } };
async function fgFind() {
  FG.q = ""; const [w, s, e, n] = turf.bbox(TERR); FG.msg = "Каталог ФГИС ТП: первый раз около 10 МБ…"; fgRender(); busy(true);
  try { FG.docs = (await api(`/api/fgistp/docs?bbox=${[w, s, e, n].join(",")}`)).docs; FG.msg = FG.docs.length ? "Самые местные документы — сверху. Выберите документ, затем слои." : "Документов с охватом этой территории нет."; }
  catch (err) { FG.msg = "ФГИС ТП не ответила: " + err.message; } finally { busy(false); fgRender(); }
}
let fgQT;
async function fgSearch(q) {
  FG.q = q.trim(); if (!FG.q) return TERR ? fgFind() : fgRender();
  if (FG.q.length < 3) return;
  FG.msg = "Поиск в каталоге ФГИС ТП…"; busy(true);
  try { FG.docs = (await api(`/api/fgistp/docs?q=${encodeURIComponent(FG.q)}`)).docs; FG.uin = ""; FG.layers = null; FG.sel.clear();
    FG.msg = FG.docs.length ? `Найдено документов: ${FG.docs.length}${FG.docs.length === 100 ? " (первые 100 — уточните запрос)" : ""}. Самые местные — сверху.` : "По такому названию документов нет."; }
  catch (err) { FG.msg = "ФГИС ТП не ответила: " + err.message; } finally { busy(false); fgRender(); }
}
async function fgPick(uin) {
  FG.uin = uin; FG.layers = null; FG.sel.clear(); if (!uin) return fgRender();
  FG.msg = "Состав документа…"; fgRender(); busy(true);
  try { FG.layers = (await api(`/api/fgistp/layers?uin=${encodeURIComponent(uin)}`)).layers; FG.msg = `Слоёв в документе: ${FG.layers.length}. Отметьте нужные.`; }
  catch (err) { FG.msg = "Состав документа не получен: " + err.message; } finally { busy(false); fgRender(); }
}
async function fgLoad() {
  const [w, s, e, n] = coverBox(); FG.msg = "Загрузка слоёв документа: портал отдаёт документ целиком, может занять минуту…"; fgRender(); busy(true);
  try {
    const epoch = window.PROJ_EPOCH, r = await api("/api/fgistp/fetch", { uin: FG.uin, classids: [...FG.sel], bbox: [w, s, e, n] });
    if (epoch !== window.PROJ_EPOCH) { FG.msg = "Выгрузка для прежнего проекта отброшена."; return; }
    let n2 = 0; const reps = []; const empty = Object.values(r.layers).filter(v => !v.features.features.length).map(v => v.title.replace("ФГИС ТП: ", ""));
    for (const [k, v] of Object.entries(r.layers)) {
      if (!v.features.features.length) continue;                 // пустой в этой области слой не засоряет список
      SOURCES[k] = { title: v.title, kind: "fgistp" };
      // повторная загрузка слоя — как перевыгрузка: ваши правки, нарисованное и имя слоя сохраняются
      const prev = DATA[k], m = prev && layerSrc[k] ? mergeDownload(k, prev, v.features) : null;
      if (m) reps.push(`«${prev.title}»: ${m.text}`);
      DATA[k] = { ...v, title: prev?.title || v.title, fc: m ? m.fc : v.features, count: v.features.features.length, fields: [...new Set(v.features.features.slice(0, 200).flatMap(f => Object.keys(f.properties)))], original: v.features };
      layerSrc[k] ||= new ol.source.Vector(); setLayerData(k, DATA[k].fc); const l = ensureLayer(k, v.title); assignCats(l, true); restyle(l); n2 += DATA[k].count;
    }
    FG.msg = `Загружено слоёв: ${Object.keys(r.layers).length - empty.length}, объектов в области: ${n2}.${empty.length ? ` Нет объектов в области: ${empty.join(", ")}.` : ""}${reps.length ? " " + reps.join("; ") + "." : ""}`; dataRev++;
  } catch (err) { FG.msg = "Слои не загружены: " + err.message; } finally { busy(false); renderSources(); }
}
$("bLoad").onclick = () => window.openSources();
window.renderSources = renderSources;
/* выгрузка источников по прямоугольнику: кнопка «Загрузить» — граница + 60 м; листы раздела — вся площадь своих рамок */
async function loadKeys(keys, bb) {
  const [w, s, e, n] = bb;
  // OSM (Overpass) отвечает от секунд до минуты — отдельным запросом, чтобы остальные слои появились сразу
  // ЕГКО — тоже отдельно: первая выгрузка слоя всей Москвы идёт минутами
  // Яндекс — тоже отдельно: первая выгрузка тайлов идёт с паузами, до минуты на 1 км²
  const osm = keys.filter(k => k.startsWith("osm.")), egko = keys.filter(k => k.startsWith("egko.")), yandex = keys.filter(k => k.startsWith("yandex.")),
    rest = keys.filter(k => !/^(osm|egko|yandex)\./.test(k)), parts = [rest, osm, egko, yandex].filter(p => p.length);
  const pending = new Set(parts); let nLayers = 0; const reports = [], fresh = [], empty = [], same = [];
  ERRORS = {}; $("bLoad").disabled = true; busy(true);
  const epoch = window.PROJ_EPOCH; let dropped = false;
  const hint = () => window.setHint?.(`Выгрузка идёт${pending.size === 1 && pending.has(osm) ? ": ждём OpenStreetMap (Overpass отвечает до минуты, повтор той же области берётся с диска)" : ""}. Работать можно дальше.`);
  hint();
  // ГИС ОГД в первый раз качает слой целиком (ПЗЗ — 221 МБ), НСПД и OSM большую область берут по частям: сервер
  // сообщает ход, показываем его
  const mb = v => fmt(v / 1e6, v < 1e7 ? 1 : 0);
  const poll = setInterval(async () => {
    try { const pr = Object.values(await api("/api/progress")); if (!pr.length || !pending.size) return;
      const ya = pr.filter(x => x.stage === "tiles"), big = pr.filter(x => x.stage !== "tiles");
      window.setHint?.([big.length ? (big.every(x => x.stage === "cells") ? "Большая область, выгрузка по частям: " : "Первая выгрузка слоя целиком: ") + big.map(x => `«${x.title}» — ${x.stage === "cells" ? `часть ${x.got + 1} из ${x.total}` : x.stage === "parse" ? "разбор" : x.stage === "index" ? "раскладка по сетке" : !x.got ? "портал готовит файл (у крупных слоёв ЕГКО — до нескольких минут)" : x.total ? `${Math.round(x.got / x.total * 100)} % (${mb(x.got)} из ${mb(x.total)} МБ)` : `${mb(x.got)} МБ`}`).join("; ") : "",
        ya.length ? `Яндекс: тайлы ${ya[0].got} из ${ya[0].total}` : ""].filter(Boolean).join(". ") + ". Работать можно дальше."); } catch { }
  }, 800);
  await Promise.all(parts.map(async part => {
    try {
      const r = await api("/api/fetch", { bbox: [w, s, e, n], sources: part });
      // пока шла выгрузка, открыт или создан другой проект: результат относится к прежнему и в новый не пишется
      if (epoch !== window.PROJ_EPOCH) { dropped = true; return; }
      Object.assign(ERRORS, r.errors);
      for (const [k, v] of Object.entries(r.layers)) {
        // пустая первая выгрузка не заводит слой в списке: в области этого нет, сказано в итоге
        if (!DATA[k] && !v.features.features.length) { empty.push(v.title); continue; }
        const prev = DATA[k], fields = [...new Set(v.features.features.slice(0, 200).flatMap(f => Object.keys(f.properties)))];
        const m = prev && layerSrc[k] ? mergeDownload(k, prev, v.features, [w, s, e, n]) : null;
        const cover = prev?.bbox ? [Math.min(prev.bbox[0], w), Math.min(prev.bbox[1], s), Math.max(prev.bbox[2], e), Math.max(prev.bbox[3], n)] : [w, s, e, n];
        // имя, данное слою вами, переживает перевыгрузку: по нему слой находят узлы графа
        DATA[k] = { ...v, title: prev?.title || v.title, fc: m ? m.fc : v.features, count: (m ? m.fc : v.features).features.length, fields, original: m?.original || v.features, bbox: cover,
          history: [...(prev?.history || []), { date: v.fetched_at, n: v.features.features.length, ...(m?.counts || {}) }] };
        layerSrc[k] ||= new ol.source.Vector(); setLayerData(k, DATA[k].fc);
        const l = ensureLayer(k, v.title);
        // v0.33 рисовал площадные слои Яндекса без контура (швы тайлов); с v0.34 куски склеены — нетронутый стиль получает контур
        if ({ "yandex.buildings": "#d3cdc2", "yandex.hd_roads": "#e6e3dc" }[k] === l.style.fill && l.style.mode === "single" && l.style.width === 0)
          l.style.width = defaultStyle(k, DATA[k].fc).width;
        // v0.53: нетронутая проезжая часть прежнего бледного тона получает новый, видимый на холсте
        if (k === "yandex.hd_roads" && l.style.mode === "single" && l.style.fill === "#e6e3dc") Object.assign(l.style, { fill: "#d5dae0", stroke: "#9ea7b1", width: .6, opacity: 1 });
        assignCats(l, true); restyle(l); nLayers++;
        if (m) { if (m.counts.added || m.counts.removed || m.counts.changed || !/^\+0 новых, −0 исчезло, 0 изменились$/.test(m.text)) reports.push(`«${v.title}»: ${m.text}`); else same.push(v.title); fresh.push(...layerSrc[k].getFeatures().filter(f => m.mark.has(f.get("_key"))).map(f => ({ key: k, f }))); }
      }
    } catch (err) { if (epoch === window.PROJ_EPOCH) part.forEach(k => { ERRORS[k] = err.message; }); }
    pending.delete(part); dataRev++; renderSources(); if (pending.size) hint();
  }));
  if (poll) clearInterval(poll);
  busy(false); $("bLoad").disabled = false; window.syncStatus?.();
  portalStyles();
  if (dropped) return toast("Выгрузка для прежнего проекта отброшена: пока она шла, открыт другой проект.");
  const ne = Object.keys(ERRORS).length;
  if (fresh.length) setSel(fresh);          // новое и изменённое в источнике — подсвечено выбором
  const pzzMsg = DATA["gisogd.pzz_sub"] && keys.includes("gisogd.pzz_sub") && RESULT.tepNode?.widgets[1].value === 25 && !RESULT.tepNode.properties?.pzzTarget && takePzzTarget(true)
    ? ` Цель плотности эскиза взята по ПЗЗ: ${RESULT.tepNode.widgets[1].value} тыс. м²/га (окно «Показатели»).` : "";
  // причина видна сразу: «Земельные участки (ЕГРН): область 195 км² больше допустимых 150 км²…»
  const why = Object.entries(ERRORS).slice(0, 3).map(([k, m]) => `${SOURCES[k]?.title || k}: ${m}`).join("; ");
  toast(`Загружено слоёв: ${nLayers}${ne ? `, с ошибкой: ${ne} (${why})` : ""}.${empty.length ? ` Нет объектов в области: ${empty.join(", ")}.` : ""}${reports.length ? " Перевыгрузка — " + reports.join("; ") + (fresh.length ? ". Новое и изменённое выделено." : ".") : ""}${pzzMsg}${same.length ? ` Без изменений в источнике: ${same.length === 1 ? "«" + same[0] + "»" : plural(same.length, ["слой", "слоя", "слоёв"])}.` : ""}`);
};
/* Повторная выгрузка слоя: сравнение с прошлой по ключу объекта источника (_key) и слияние с ручной правкой,
   чтобы ничего не пропало молча: ваша правка объекта сильнее новой версии источника, удалённое вами остаётся
   удалённым, нарисованное вами остаётся. */
function mergeDownload(key, prev, fc, bb) {
  const clean = p => Object.fromEntries(Object.entries(p || {}).filter(([k]) => !k.startsWith("_")));
  // участки: найденные по номеру (_key = номер) и выгруженные по области (_key = id портала) — один и тот же объект
  const canon = list => key === "nspd.parcels" ? list.map(f => cadOf(f) && f.properties?._key !== cadOf(f) ? { ...f, properties: { ...f.properties, _key: cadOf(f) } } : f) : list;
  fc = { ...fc, features: canon(fc.features) }; if (prev.original) prev = { ...prev, original: { ...prev.original, features: canon(prev.original.features) } };
  const sig = f => JSON.stringify([f.geometry, clean(f.properties)]);
  const byKey = list => new Map(list.filter(f => f.properties?._key).map(f => [f.properties._key, f]));
  // выгрузка другой области: объекты прежней выгрузки вне новой рамки остаются как были (не «исчезли»), а объекты,
  // которых прежняя область не покрывала, — не «новые в источнике», а просто дальше по карте
  const fb = f => { try { return turf.bbox(f); } catch { return null; } };
  const hits = (f, r) => { const b = fb(f); return !!b && !(b[2] < r[0] || b[0] > r[2] || b[3] < r[1] || b[1] > r[3]); };
  const inNew = f => !bb || hits(f, bb), oldCover = prev.bbox || null;
  const keepOut = bb ? (prev.original?.features || []).filter(f => !inNew(f)) : [];
  const outKeys = new Set(keepOut.map(f => f.properties?._key).filter(Boolean));
  const oldF = (prev.original?.features || []).filter(f => !outKeys.has(f.properties?._key)), oldBy = byKey(oldF), newBy = byKey(fc.features);
  const cur = canon(writeFC(layerSrc[key].getFeatures()).features), curBy = byKey(cur);
  // пустая выгрузка с ключами идёт обычным путём: правленные вами объекты остаются с пометкой, счёт «−N исчезло» виден
  if (!byKey(prev.original?.features || []).size || (!newBy.size && fc.features.length)) {                               // без ключей источника (старый проект, горизонтали) сравнивать не с чем:
    const drawn = cur.filter(f => !f.properties?._key);            // слой заменяется, но нарисованное вами в нём остаётся
    return drawn.length ? { fc: { type: "FeatureCollection", features: fc.features.concat(drawn) }, text: `слой заменён новой выгрузкой, нарисованные вами объекты (${drawn.length}) сохранены`, mark: new Set(), counts: {} } : null;
  }
  const added = [...newBy.keys()].filter(k => !oldBy.has(k) && !outKeys.has(k) && (!oldCover || hits(newBy.get(k), oldCover))), removed = [...oldBy.keys()].filter(k => !newBy.has(k));
  const changed = [...newBy.keys()].filter(k => oldBy.has(k) && sig(oldBy.get(k)) !== sig(newBy.get(k)));
  const mine = cur.filter(f => f.properties?._edited && f.properties._key && newBy.has(f.properties._key));
  const gone = new Set([...oldBy.keys()].filter(k => !curBy.has(k)));
  const drawn = cur.filter(f => !f.properties?._key);
  // объекты прежней области вне новой рамки — в том виде, как сейчас на карте (с вашими правками); из новой выгрузки
  // такие же (на стыке рамок) не дублируются
  const outside = cur.filter(f => outKeys.has(f.properties?._key));
  fc = { ...fc, features: fc.features.filter(f => !outKeys.has(f.properties?._key)) };
  // поля, которых нет в источнике (добавлены вами, например «Решение» реестра), переносятся на новую версию объекта
  const srcFields = new Set(fc.features.slice(0, 500).flatMap(f => Object.keys(f.properties || {})));
  const own = [...new Set(cur.slice(0, 500).flatMap(f => Object.keys(f.properties || {})))].filter(k => !srcFields.has(k) && !k.startsWith("_"));
  // правленный вами объект, которого в источнике больше нет, не пропадает молча: остаётся с пометкой
  const orphan = cur.filter(f => f.properties?._edited && f.properties._key && !newBy.has(f.properties._key) && !outKeys.has(f.properties._key)).map(f => ({ ...f, properties: { ...f.properties, "Нет в источнике": "да" } }));
  const out = fc.features.filter(f => !gone.has(f.properties?._key)).map(f => { const c = curBy.get(f.properties?._key); if (c?.properties._edited) return c;
    if (!c || !own.length) return f; const p = { ...f.properties }; own.forEach(k => { if (c.properties[k] != null) p[k] = c.properties[k]; }); return { ...f, properties: p }; }).concat(outside, drawn, orphan);
  const conflict = mine.filter(f => changed.includes(f.properties._key)).length;
  const parts = [`+${added.length} новых`, `−${removed.length} исчезло`, `${changed.length} изменились`];
  if (mine.length) parts.push(`ваши правки (${mine.length}) сохранены${conflict ? `, из них ${conflict} изменились и в источнике — сверьте` : ""}`);
  if (gone.size) parts.push(`удалённые вами (${gone.size}) не вернулись`);
  if (orphan.length) parts.push(`правленные вами, но исчезнувшие из источника (${orphan.length}) оставлены с пометкой «Нет в источнике»`);
  if (outside.length) parts.push(`вне новой рамки оставлено как было: ${outside.length}`);
  return { fc: { type: "FeatureCollection", features: out }, original: { type: "FeatureCollection", features: fc.features.concat(keepOut) }, text: parts.join(", "), mark: new Set([...added, ...changed]),
    counts: { added: added.length, removed: removed.length, changed: changed.length } };
}
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

/* ---------- импорт файлов: DXF, GeoJSON, KML/KMZ, Shapefile — кнопкой или перетаскиванием на карту, как в QGIS ---------- */
const b64 = buf => { let s = ""; const u = new Uint8Array(buf); for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); };
async function importFiles(fileList) {
  const files = [...fileList]; if (!files.length) return;
  busy(true);
  try {
    const body = { local: $("impLocal")?.value || "msk", files: await Promise.all(files.map(async f => ({ name: f.name, b64: b64(await f.arrayBuffer()) }))) };
    const r = await fetch("/api/import/files", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); const j = await r.json();
    if (!r.ok) throw new Error(j.error);
    const ex = ol.extent.createEmpty(), msgs = [];
    for (const lay of j.layers) {
      // повторный импорт файла с тем же именем — новый слой рядом, а не замена прежнего вместе с правками
      let key = "import:" + lay.name + "." + lay.format.toLowerCase(), title = `${lay.name} (${lay.format})`, n = 2;
      while (DATA[key]) { key = `import:${lay.name} (${n}).${lay.format.toLowerCase()}`; title = `${lay.name} (${n}) (${lay.format})`; n++; }
      const fc = lay.features;
      SOURCES[key] = { title, kind: "import" }; CHECKED.add(key);
      DATA[key] = { title, source: "файл " + lay.name + "." + lay.format.toLowerCase(), fetched_at: new Date().toISOString().slice(0, 10), notes: lay.notes, fc, count: fc.features.length, fields: [...new Set(fc.features.slice(0, 500).flatMap(f => Object.keys(f.properties)))] };
      layerSrc[key] ||= new ol.source.Vector(); delete DATA[key].original; setLayerData(key, fc); ensureLayer(key, title);
      if (fc.features.length) ol.extent.extend(ex, layerSrc[key].getExtent());
      msgs.push(`${title}: ${fc.features.length} об. (${lay.notes.join("; ")})`);
    }
    dataRev++; renderSources();
    if (isFinite(ex[0])) sharedView.fit(ex, { padding: [40, 40, 40, 40], maxZoom: 18 });
    toast("Импорт: " + msgs.join(" · "));
  } catch (err) { toast("Файл не прочитан: " + err.message); } finally { busy(false); }
}
$("fDxf").onchange = e => { const fs = [...e.target.files]; e.target.value = ""; importFiles(fs); };
const mapDrop = $("mMain").parentElement;
mapDrop.addEventListener("dragover", e => { if ([...e.dataTransfer.types].includes("Files")) { e.preventDefault(); mapDrop.classList.add("dropfile"); } });
mapDrop.addEventListener("dragleave", e => { if (!mapDrop.contains(e.relatedTarget)) mapDrop.classList.remove("dropfile"); });
mapDrop.addEventListener("drop", e => { mapDrop.classList.remove("dropfile"); if (!e.dataTransfer.files.length) return; e.preventDefault();
  const fs = [...e.dataTransfer.files], proj = fs.find(f => /\.grado2$/i.test(f.name));
  if (proj) return window.openProjectFile?.(proj);          // файл проекта открывается как проект
  importFiles(fs); });
$("bExport").onclick = async () => {
  const layers = Object.entries(DATA).map(([k, d]) => ({ name: d.title, features: d.fc, color: k === "gisogd.red_lines" ? "#d7191c" : "#808080", floors: d.fc.features.some(f => f.properties?.["Этажность"]) }));
  if (TERR) layers.push({ name: "Граница территории", features: turf.featureCollection([TERR]), color: "#b3261e" });
  if (!layers.length) return toast("Экспортировать нечего: загрузите данные, нарисуйте объекты или примите эскиз в проект.");
  busy(true);
  try {
    const r = await fetch("/api/export/dxf", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ layers }) });
    if (!r.ok) throw new Error((await r.json()).error);
    const a = document.createElement("a"); a.href = URL.createObjectURL(await r.blob()); a.download = "grado2-dxf.zip"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    toast("DXF готов: в архиве чертёж, red_lns.shx и REDLN97.LIN. Координаты — МСК (как в QGIS), метры. Файл сохранён в папку загрузок браузера.");
  } catch (err) { toast("Экспорт не удался: " + err.message); } finally { busy(false); }
};

/* «DXF ГИС ОГД»: все слои ГИС ОГД внутри листа, нарисованного на карте (frames.js), — чертёж для передачи: МСК,
   слой портала на своём слое, лист бумаги с видовым экраном в масштабе. Кнопка в шапке берёт выбранный лист или
   последний; листа нет — включает инструмент «Лист». Выгрузка идёт на сервере фоном, повторное нажатие её останавливает. */
let ogdPoll = null;
function ogdSheet(fr) {
  const scale = Math.round(sheetScale(fr)), map = frameMM(fr), paper = isPaper(fr.size) ? paperMM(fr) : map, g = sheetMsk(fr);
  return { c: g.c, w: g.wh[0], h: g.wh[1], paper, map, scale, title: `${ALBUM.sheets.indexOf(fr) + 1}` };
}
window.ogdSheet = ogdSheet;
async function runOgd(fr, codes) {
  if (ogdPoll) { await api("/api/ogd_all/cancel", {}); window.setHint?.("Остановка: текущий слой дочитывается, потом выгрузка встанет."); return; }
  // лист бумаги в DXF: у листа без штампа — вся бумага, у ГОСТ и слайдов — только поле карты; видовой экран — поле карты
  const i = ALBUM.sheets.indexOf(fr), sheet = ogdSheet(fr), scale = sheet.scale;
  const where = `листу ${i + 1} «${fr.title}» (${SIZE_T[fr.size] || fr.size}, 1:${fmt(scale)})`;
  try { await api("/api/ogd_all/start", { sheet, codes, where, boundary: TERR?.geometry || null, name: `ОГД ${fr.title || `лист ${i + 1}`} 1-${scale}` }); }
  catch (err) {
    // выгрузка уже идёт (запущена раньше, из другой вкладки или до обновления страницы) — показываем её ход
    if (/уже идёт/.test(err.message)) { toast("Выгрузка ГИС ОГД уже идёт — показываю её ход на кнопке и в строке состояния. Новая начнётся, когда эта закончится."); return watchOgd(); }
    return toast("Выгрузка не началась: " + err.message);
  }
  toast(`Выгрузка всех слоёв ГИС ОГД по ${where}. Ход — на кнопке «DXF ГИС ОГД» и в строке состояния; работать можно дальше.`);
  watchOgd();
}
/* ход выгрузки: кнопка показывает «слой N из M», строка состояния — подробности; по окончании архив скачивается.
   Подключается и к выгрузке, начатой раньше (при открытии страницы и на повторное нажатие). */
function watchOgd() {
  const btn = $("bOgdAll"), lb = btn.lastChild, min = s => s < 90 ? `${Math.round(s)} с` : `${Math.round(s / 60)} мин`;
  clearInterval(ogdPoll);
  const tick = async () => {
    let st; try { st = await api("/api/ogd_all/status"); } catch { return; }
    const where = st.where || "листу";
    if (st.running) {
      const left = st.done ? (Date.now() / 1000 - st.started) / st.done * (st.total - st.done) : 0;
      lb.textContent = `ГИС ОГД ${st.done}/${st.total || "…"} · стоп`; btn.classList.add("busy");
      btn.title = `Идёт выгрузка ГИС ОГД по ${where}. Нажмите, чтобы остановить.`;
      window.setHint?.(`ГИС ОГД по ${where}: слой ${st.done} из ${st.total || "…"}${st.current ? ` — «${st.current}»` : ""}${st.message ? ` (${st.message})` : ""}. `
        + `С объектами на листе: ${st.found}.${left > 5 ? ` Осталось около ${min(left)}.` : ""} Работать можно дальше.`);
      return;
    }
    clearInterval(ogdPoll); ogdPoll = null; lb.textContent = "DXF ГИС ОГД"; btn.classList.remove("busy"); btn.title = btn.dataset.title || btn.title; window.setHint?.("");
    if (!st.file) return toast(st.message || "Выгрузка остановлена.");
    const a = document.createElement("a"); a.href = "/api/ogd_all/file"; a.download = st.file; a.click();
    const miss = st.errors.map(e => "«" + e.split(": ")[0] + "»");
    toast(`Готово по ${where}: ${plural(st.found, ["слой", "слоя", "слоёв"])}, ${plural(st.objects, ["объект", "объекта", "объектов"])}. `
      + `${st.dwg ? "В архиве DWG, DXF" : "В архиве DXF (в AutoCAD — вкладка листа с видовым экраном; в DWG — «Сохранить как»)"} и таблицы атрибутов.`
      + `${miss.length ? ` Портал не отдал: ${miss.slice(0, 2).join(", ")}${miss.length > 2 ? ` и ещё ${miss.length - 2}` : ""}.` : ""} Файл сохранён в папку загрузок браузера.`);
  };
  ogdPoll = setInterval(tick, 1500); tick();
}
$("bOgdAll").dataset.title = $("bOgdAll").title;
window.ogdResume = () => api("/api/ogd_all/status").then(st => { if (st.running) watchOgd(); }).catch(() => { });   // открыли страницу во время выгрузки; зовёт startApp, когда сервер готов принимать запросы (в совместном режиме — после входа)
window.ogdFrame = () => window.selectedFrame?.() || [...ALBUM.sheets].reverse().find(sh => window.sheetOnMap?.(sh));
window.runOgd = runOgd; window.exportOgd = fr => ogdPoll ? runOgd(null) : window.openOgdPicker(fr);   // сначала окно выбора слоёв (ogdpick.js)
$("bOgdAll").onclick = () => {
  if (ogdPoll) return runOgd(null);
  const fr = window.ogdFrame();
  if (fr) return window.exportOgd(fr);
  window.startFrame(); toast("Нарисуйте лист: тяните прямоугольник по карте. Потом «DXF ГИС ОГД» над листом.");
};

/* ================= граф анализа (litegraph.js) ================= */
Object.assign(LiteGraph, { NODE_DEFAULT_COLOR: "#d6dade", NODE_DEFAULT_BGCOLOR: "#f7f7f5", NODE_DEFAULT_BOXCOLOR: "#8a8d91", NODE_TITLE_COLOR: "#1d1d1f", NODE_SELECTED_TITLE_COLOR: "#000", NODE_TEXT_COLOR: "#333", NODE_TEXT_SIZE: 12, NODE_SUBTEXT_SIZE: 11,
  WIDGET_BGCOLOR: "#ffffff", WIDGET_OUTLINE_COLOR: "#b5b8bc", WIDGET_TEXT_COLOR: "#1d1d1f", WIDGET_SECONDARY_TEXT_COLOR: "#6b6f75", LINK_COLOR: "#7a7e84", CONNECTING_LINK_COLOR: "#2f6fc4", NODE_TITLE_HEIGHT: 24, NODE_SLOT_HEIGHT: 20, NODE_WIDGET_HEIGHT: 20 });
LGraphNode.prototype.serialize_widgets = true;   // значения полей узлов (слой, фильтр, ползунки) — в файл проекта
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
function drawInfo(ctx) { if (this.flags.collapsed || !this.info) return; ctx.fillStyle = "#5f6368"; ctx.font = "11px system-ui, sans-serif"; ctx.fillText(fitText(this.info, this.size[0] - 14, ctx.font), 8, this.size[1] - 7); }
function finish(node, kind, w = 210) { node.color = TITLE[kind]; node.bgcolor = "#f7f7f5"; node.size = node.computeSize(); node.size[0] = Math.max(w, node.size[0]); node.size[1] += 16; node.onDrawForeground = drawInfo; }
const ha = f => f ? fmt(m2(f) / 1e4, 2) + " га" : "пусто";
const titleToKey = t => Object.keys(DATA).find(k => DATA[k].title === t) || Object.keys(SOURCES).find(k => SOURCES[k].title === t);

function NTerr() { this.addOutput("граница", "geom"); finish(this, "src", 170); }
NTerr.title = "Территория"; NTerr.prototype.onExecute = function () { this.setOutputData(0, TERR); this.info = TERR ? ha(TERR) : "граница не задана"; };
LiteGraph.registerNodeType("Данные/Территория", NTerr);

/* Длинные имена в узле графа: litegraph рисует значение списка без обрезки, и оно наезжает на подпись.
   Если values — объект, он рисует values[значение], а в меню показывает ключи: ключ = полное имя, показ = обрезанное. */
const _mc = document.createElement("canvas").getContext("2d"), GFONT = { title: "600 12px system-ui, sans-serif", inner: "11px system-ui, sans-serif" };
function fitText(t, px, font) {
  _mc.font = font; t = String(t ?? "");
  if (_mc.measureText(t).width <= px) return t;
  let lo = 0, hi = t.length;
  while (lo < hi) { const m = (lo + hi + 1) >> 1; if (_mc.measureText(t.slice(0, m) + "…").width <= px) lo = m; else hi = m - 1; }
  return t.slice(0, lo) + "…";
}
const fitCombo = (node, name, list) => () => {
  const font = GFONT.inner; _mc.font = font;
  const room = node.size[0] - 50 - 35 - _mc.measureText(name).width - 14;            // от подписи до стрелки справа
  const fit = v => fitText(v === "" ? "—" : v, Math.max(24, room), font);
  // Proxy: значение, которого нет в списке (пустое, удалённый слой), тоже рисуется, а в меню не попадает
  return new Proxy(Object.fromEntries(list().map(v => [v, fit(v)])), { get: (o, k) => typeof k !== "string" || k in o ? o[k] : fit(k) });
};
function fitTitle(node, full) { node._fullTitle = full; node.title = fitText(full, node.size[0] - 34, GFONT.title); }
function NLayer() {
  this.addOutput("объекты", "geom");
  this.addWidget("combo", "слой", "", () => { }, { values: fitCombo(this, "слой", () => Object.keys(DATA).map(k => DATA[k].title)) });
  this.addWidget("combo", "поле", "—", () => { }, { values: fitCombo(this, "поле", () => ["—", ...(DATA[titleToKey(this.widgets[0].value)]?.fields || [])]) });
  this.addWidget("combo", "условие", "—", () => { }, { values: OPS });
  this.addWidget("text", "значение", "", () => { });
  finish(this, "src", 250);
}
NLayer.title = "Слой"; NLayer.prototype.onExecute = function () {
  const [lw, fw, ow, vw] = this.widgets;
  let key = titleToKey(lw.value), d = DATA[key];
  // здания ЕГРН не выгрузились (портал не ответил), а OSM есть — узел берёт здания OSM и говорит об этом,
  // иначе сохраняемых нет, эскиз садится на существующие дома, а ТЭП считает их все под снос
  const alt = !d && lw.value === "Здания (ЕГРН)" && DATA["osm.buildings"] ? "osm.buildings" : null;
  if (alt) { key = alt; d = DATA[alt]; }
  if (!d) { this.setOutputData(0, null); this.info = lw.value ? "слой не загружен" : "выберите слой"; return; }
  const ck = [d.rev, key, fw.value, ow.value, vw.value, TERR_REV].join("|");   // пересчёт — только при правке этого слоя
  if (this._cacheKey !== ck) {
    this._cacheKey = ck;
    const list = d.fc.features.filter(f => fw.value === "—" || testOp(f.properties[fw.value], ow.value, vw.value));
    // правка атрибута (адрес, этажность, «Решение» у несносимого) не меняет геометрию: объединение и все буферы после
    // него остаются, обновляется только список объектов для ТЭП. Объединение 3 000 зданий и буфер — полсекунды
    const gs = geomSig(list);
    if (this._out && gs === this._gsig && TERR_REV === this._terr) this._out.properties = { _src: list };
    else { let u = unionAll(list.map(asArea)); if (u) u = { ...u, properties: { _src: list } };   /* объединение одного объекта — он сам: копия, иначе его атрибуты затёрлись бы */ this._out = u; this._gsig = gs; this._terr = TERR_REV; }
    this._n = [list.length, d.count];
  }
  this.setOutputData(0, this._out);
  fitTitle(this, "Слой: " + d.title + (fw.value !== "—" && ow.value !== "—" ? ` [${fw.value} ${ow.value} ${vw.value}]` : ""));
  this.info = alt ? `${this._n[0]} зд. OSM: ЕГРН не выгружен` : `${this._n[0]} из ${this._n[1]} объектов`;
};
NLayer.prototype.onResize = function () { if (this._fullTitle) fitTitle(this, this._fullTitle); };
LiteGraph.registerNodeType("Данные/Слой", NLayer);

function NNum() { this.addOutput("число", "num"); this.addWidget("slider", "значение", 12, () => { }, { min: 1, max: 40, precision: 0, slider_color: "#e3b25a" }); finish(this, "num", 190); }
NNum.title = "Число"; NNum.prototype.onExecute = function () { this.setOutputData(0, Math.round(this.widgets[0].value)); };
LiteGraph.registerNodeType("Параметры/Число", NNum);

// отпечаток геометрии набора объектов (координаты до 1 см): равный — значит, геометрия та же. Порядок объектов не
// важен — источник карты после правки отдаёт их в другом порядке; порядок вершин внутри объекта важен
function geomSig(list) {
  let A = list.length, B = 0;
  for (const f of list) {
    if (!f.geometry) continue;
    let a = 7, b = 11;
    const walk = c => { if (typeof c[0] === "number") { a = (a * 31 + Math.round(c[0] * 1e7)) % 2147483647; b = (b * 37 + Math.round(c[1] * 1e7)) % 2147483629; } else for (const x of c) walk(x); };
    walk(f.geometry.coordinates); A = (A + a) % 9007199254740881; B = (B + b) % 9007199254740881;
  }
  return A + ":" + B;
}
// 1 дом, 2 дома, 5 домов, 21 дом, 1404 участка
function plural(n, [one, few, many]) { const a = Math.abs(n) % 100, b = a % 10; return `${fmt(n)} ${a > 10 && a < 20 ? many : b === 1 ? one : b >= 2 && b <= 4 ? few : many}`; }
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
  const r = cached(this, gid(a) + gid(b), () => { let u = unionAll([a, b]); if (u) u = { ...u, properties: { _src: [...(a?.properties?._src || []), ...(b?.properties?._src || [])] } }; return u; }); this.setOutputData(0, r); this.info = ha(r); };
LiteGraph.registerNodeType("Геометрия/Объединить", NUnion);
function NInter() { this.addInput("A", "geom"); this.addInput("B", "geom"); this.addOutput("A ∩ B", "geom"); finish(this, "op", 150); }
NInter.title = "Пересечь"; NInter.prototype.onExecute = function () { const a = this.getInputData(0), b = this.getInputData(1); const r = cached(this, gid(a) + gid(b), () => inter(a, b)); this.setOutputData(0, r); this.info = ha(r); };
LiteGraph.registerNodeType("Геометрия/Пересечь", NInter);

function NPlace() {
  this.addInput("пятно", "geom"); this.addInput("этажность", "num"); this.addInput("предельная высота", "cap"); this.addOutput("посадка", "sketch");
  this.addWidget("combo", "типология", "Секции", () => { }, { values: TYPOLOGIES });
  this.addWidget("slider", "ширина корпуса, м", 16, () => { }, { min: 12, max: 24, precision: 0, slider_color: "#8fb3e0" });
  this.addWidget("slider", "этажность", 12, () => { }, { min: 1, max: 30, precision: 0, slider_color: "#8fb3e0" });
  this.addWidget("slider", "разрыв / высота", 1.0, () => { }, { min: .5, max: 2, precision: 2, slider_color: "#8fb3e0" });
  this.addWidget("slider", "поворот, °", 0, () => { }, { min: -90, max: 90, precision: 0, slider_color: "#8fb3e0" });
  this.addWidget("combo", "этажность по", "заданной", () => { }, { values: FLOOR_MODES });
  this.addWidget("slider", "участок, соток", 10, () => { }, { min: 4, max: 20, precision: 0, slider_color: "#8fb3e0" });   // ИЖС
  this.addWidget("slider", "квартал, м", 110, () => { }, { min: 60, max: 200, precision: 0, slider_color: "#8fb3e0" });    // урбан-блоки
  this.properties = { run: false };        // как в TestFit: посадка строится только по команде «Построить эскиз»
  finish(this, "gen", 240);
}
NPlace.title = "Посадка застройки"; NPlace.prototype.onExecute = function () {
  if (!this.properties.run) { this.setOutputData(0, []); this.info = "не построена: «Построить эскиз» в окне «Эскиз»"; return; }
  if (!TERR) { this.setOutputData(0, []); this.info = "нет границы территории — эскиз не строится"; return; }
  const site = this.getInputData(0), p = placeParams(this);
  const r = cached(this, gid(site) + JSON.stringify(p) + (p.cap?._id || ""), () => generate(site, p)); this.setOutputData(0, r);
  const capped = r.filter(b => b.capped).length, avg = r.length ? r.reduce((s, b) => s + b.floors * b.m2, 0) / r.reduce((s, b) => s + b.m2, 0) : 0;
  const np = r.plots?.filter(g => /^участок/.test(g.kind)).length, ny = r.plots?.filter(g => g.kind === "двор" || g.kind === "свет соседям").length;
  const guest = (r.streets || []).filter(g => g.kind === "гостевая стоянка").reduce((s, g) => s + g["Мест"], 0);
  this.info = `${plural(r.length, LOWRISE.has(p.typ) ? ["дом", "дома", "домов"] : ["корпус", "корпуса", "корпусов"])}${np ? ` · ${plural(np, ["участок", "участка", "участков"])}` : ny ? ` · ${plural(ny, ["двор", "двора", "дворов"])}` : ""} · ${fmt(r.reduce((s, b) => s + b.m2 * b.floors, 0) / 1000, 1)} тыс. м² СПП · ср. ${fmt(avg, 1)} эт.${guest ? ` · гостевых мест ${guest} (945-ПП)` : ""}${capped ? ` · ${capped} ниже предельной высоты` : ""}${r.goal ? ` · ${r.goal}` : ""}${r.note ? ` · ${r.note}` : ""}`;
};
LiteGraph.registerNodeType("Эскиз/Посадка застройки", NPlace);
const TYPOLOGIES = ["Секции", "Квартал", "Башни", "Точка + секция", "Смешанная", "Урбан-блоки", "Блокированные", "ИЖС"], FLOOR_MODES = ["заданной", "цели плотности"];
const LOWRISE = new Set(["Блокированные", "ИЖС"]);        // не выше 3 этажей: ИЖС — ГрК РФ ст. 1 п. 39, дома блокированной застройки — ст. 49 ч. 2 п. 2
function placeParams(n) {
  const w = n.widgets, mode = FLOOR_MODES.includes(w[5]?.value) ? w[5].value : FLOOR_MODES[0];
  return { typ: TYPOLOGIES.includes(w[0].value) ? w[0].value : "Секции", width: Math.round(w[1].value), floors: n.getInputData?.(1) ?? Math.round(w[2].value), gap: +w[3].value, angle: Math.round(w[4].value),
    cap: n.inputs?.[2] ? n.getInputData?.(2) || null : null, goal: mode === FLOOR_MODES[1] ? densityGoal() : null,
    plot: Math.round(w[6]?.value ?? 10), block: Math.round(w[7]?.value ?? 110) };
}
/* цель плотности берётся из узла ТЭП графа: нужная СПП новой застройки = цель × территория − СПП сохраняемых */
function densityGoal() {
  const t = graph._nodes.find(n => n.type === "Показатели/ТЭП КРТ"); if (!t || !TERR) return null;
  const kept = keptBuildings(t.getInputData(1)), sppKept = kept.reduce((s, f) => s + m2(f) * floorsOf(f), 0);
  return { target: t.widgets[1].value, need: Math.max(0, t.widgets[1].value * 1000 * TERR_M2 / 1e4 - sppKept) };
}

function NTep() { this.addInput("посадка", "sketch"); this.addInput("сохраняемые", "geom"); this.addInput("ограничения", "geom"); this.addOutput("ТЭП", "tep");
  this.addWidget("slider", "доля жилья, %", 80, () => { }, { min: 0, max: 100, precision: 0, slider_color: "#c0a6d4" }); this.addWidget("slider", "цель, тыс. м²/га", 25, () => { }, { min: 5, max: 45, precision: 0, slider_color: "#c0a6d4" }); finish(this, "tep", 230); }
NTep.title = "ТЭП · Москва, «Калькулятор 2.0»"; NTep.prototype.onExecute = function () {
  // принятый в проект эскиз (и ваши правки в нём) считается вместо превью графа, пока его слой есть в проекте
  const bk = this.properties?.baked, bd = bk && DATA[bk];
  if (bk && !bd) this.properties.baked = null;
  const sk = bd ? bakedSketch(bd) : this.getInputData(0) || [], kept = this.getInputData(1), lim = this.getInputData(2), share = this.widgets[0].value / 100, target = this.widgets[1].value;
  const tp = tepParams(this); placeLookup(this);
  const key = [bd ? `${bk}:${bd.rev || 0}:${sk.length}` : gid(sk), gid(kept), gid(lim), share, target, dataRev, JSON.stringify(tp)].join("|");
  if (this._key !== key) { this._key = key; const seq = this._seq = (this._seq || 0) + 1;
    tepRequest(sk, kept, lim, share, target, tp).then(t => { if (seq === this._seq) { this._tep = t; this.setOutputData(0, t); this.info = `${bd ? "по сохранённому эскизу · " : ""}плотность ${fmt(t.density, 1)} · население ${fmt(t.m.population)}`; lgc.setDirty(true, true); renderTep(); } }).catch(e => { this.info = "ТЭП: " + e.message; }); }
  this.setOutputData(0, this._tep);
};
LiteGraph.registerNodeType("Показатели/ТЭП КРТ", NTep);
const bakedSketch = d => d.fc.features.filter(f => /Polygon/.test(f.geometry?.type)).map(f => ({ f, m2: m2(f), floors: +f.properties["Этажность"] > 0 ? +f.properties["Этажность"] : 1,
  maxF: /ИЖС|Блокированные/.test(f.properties["Типология"] || "") ? 3 : undefined }));

/* Территориальные параметры ТЭП (как маркер «Калькулятора 2.0»): район → образовательная зона (2151-ПП), K2 (945-ПП прил. 3,
   внутри ТТК 0,2), ТиНАО; K1 — по расстоянию до ближайшей станции. Определяются по центру территории, правятся руками
   в окне «Показатели» (тогда auto = false и повторно не перезаписываются). Хранятся в узле ТЭП — сохраняются в проекте. */
function tepParams(n) {
  n.properties ||= {};
  return n.properties.tp ||= { auto: true, district: "", zone: 1, k1: 1, k2: 0.9, tinao: 0, mode: 1, nonres: 6, unbuilt: 25, walk: null, rev: -1, notes: [] };
}
function placeLookup(n) {
  const tp = tepParams(n); if (!TERR || tp.rev === TERR_REV || n._placeBusy) return;
  n._placeBusy = true; const rev = TERR_REV, [lon, lat] = turf.centroid(TERR).geometry.coordinates;
  api("/api/place", { lon, lat }).then(r => {
    tp.rev = rev; tp.district = r.district; tp.okrug = r.okrug; tp.walk = r.rail_walk_m; tp.walkRoute = false; tp.station = ""; tp.notes = r.notes || []; tp.insideTtk = r.inside_ttk;
    if (tp.auto) Object.assign(tp, { zone: r.zone, k1: r.k1, k2: r.k2, tinao: r.tinao });
    recompute(true); renderTep();
    // K1 по улицам: маршрут по пешеходной сети OSM до входа или станции (первый раз — до пары минут, дальше с диска)
    tp.routing = r.rail_walk_m != null;
    if (tp.routing) api("/api/rail_route", { lon, lat }).then(q => {
      if (tp.rev !== rev) return;
      tp.routing = false;
      if (q?.route_m == null) return renderTep();
      tp.walk = q.route_m; tp.walkRoute = true; tp.station = q.station || "";
      if (tp.auto) tp.k1 = q.route_m < 1200 ? 0.75 : q.route_m <= 2200 ? 0.9 : 1.0;
      recompute(true); renderTep();
    }).catch(() => { if (tp.rev === rev) { tp.routing = false; renderTep(); } });
    // граница в нескольких районах: районы в точках внутри границы, кроме центра
    const bb = turf.bbox(TERR), c = [lon, lat], pts = [[bb[0], bb[1]], [bb[2], bb[1]], [bb[2], bb[3]], [bb[0], bb[3]]]
      .map(q => [c[0] + (q[0] - c[0]) * .7, c[1] + (q[1] - c[1]) * .7]).filter(q => turf.booleanPointInPolygon(q, TERR));
    Promise.all(pts.map(q => api("/api/place", { lon: q[0], lat: q[1] }).catch(() => null))).then(rs => {
      if (tp.rev !== rev) return;
      const other = [...new Set(rs.filter(Boolean).map(x => x.district).filter(d => d && d !== r.district))];
      if (other.length) { tp.notes = [...(tp.notes || []).filter(x => !/нескольких районах/.test(x)), `граница лежит в нескольких районах: ${[r.district, ...other].join(", ")} — зона, K2 и ТиНАО взяты по району центра («${r.district}»), проверьте`]; renderTep(); }
    });
  }).catch(e => { tp.rev = rev; tp.notes = ["район не определён: " + e.message + " — задайте зону и K1, K2 вручную"]; renderTep(); }).finally(() => { n._placeBusy = false; });
}
/* ТЭП: геометрические части — здесь, нормативная часть — движок ядра на сервере */
function keptBuildings(kept) { const src = kept?.properties?._src || []; return src.filter(f => /Polygon/.test(f.geometry.type) && insideTerr(f)); }
async function tepRequest(sketch, kept, lim, share, target, tp = {}) {
  const keptList = keptBuildings(kept), keptSet = new Set(keptList);
  const sppNew = sketch.reduce((s, b) => s + b.m2 * b.floors, 0), fpNew = sketch.reduce((s, b) => s + b.m2, 0);
  const sppKept = keptList.reduce((s, f) => s + m2(f) * floorsOf(f), 0), fpKept = keptList.reduce((s, f) => s + m2(f), 0);
  const ek = EXIST_KEY(), demol = ek ? DATA[ek].fc.features.filter(f => /Polygon/.test(f.geometry.type) && insideTerr(f) && !keptSet.has(f)) : [];
  // площадь сохранения и ограничений: ЗОУИТ и прочие запреты плюс пятна сохраняемых зданий (решение владельца 24.09.2026) —
  // новая СПП не раскладывается на землю, занятую домами, которые остаются
  const restrict = m2(inter(TERR, unionAll([lim, ...keptList].filter(Boolean)))) / 1e4, terr = TERR_M2 / 1e4;
  const sppLow = sketch.filter(b => b.maxF === 3).reduce((s, b) => s + b.m2 * b.floors, 0);        // ИЖС и блокированные: 50 м² квартир на жителя
  const r = await api("/api/tep", { terr_ha: terr, restrict_ha: restrict, spp_new_m2: sppNew, share, spp_kept_m2: sppKept, spp_low_m2: sppLow,
    nonres_part: tp.nonres ?? 6, education_zone: tp.zone ?? 1, k1: tp.k1 ?? 1, k2: tp.k2 ?? 0.9, tinao: tp.tinao ?? 0, territory_mode: tp.mode ?? 1, unbuilt_share: tp.unbuilt ?? 25 });
  const m = Object.fromEntries(r.metrics.map(x => [x.id, x.value]));
  return { m, metrics: r.metrics, density: r.density_total, target, terr, restrict, sppNew, sppKept, cover: (fpNew + fpKept) / TERR_M2, n: sketch.length, kept: keptList, demolN: demol.length, demolSpp: demol.reduce((s, f) => s + m2(f) * floorsOf(f), 0), existKey: ek };
}

/* ---------- генератор посадки (локальная рамка, метры) ---------- */
/* Посадка по логике TestFit: каждый участок пятна (между улицами) — отдельно, корпуса вдоль его длинной
   стороны (минимальный описанный прямоугольник), только целые корпуса, разрывы по нормам.
   Разрыв между длинными сторонами жилых домов — не меньше 15 м (2–3 эт.) и 20 м (4 эт. и выше),
   СП 42.13330.2016 п. 7.1; и не меньше «разрыв / высота» × высота — грубая замена расчёта инсоляции
   (СанПиН 1.2.3685-21: 2 ч непрерывно). ponytail: инсоляция и противопожарные разрывы (СП 4.13130)
   не считаются по-настоящему — только этим коэффициентом; честный расчёт — отдельный узел. */
function hull(pts) {                 // выпуклая оболочка (монотонная цепь)
  const P = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]), cr = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lo = [], up = [];
  for (const p of P) { while (lo.length > 1 && cr(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); }
  for (const p of P.reverse()) { while (up.length > 1 && cr(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop(); up.push(p); }
  return lo.slice(0, -1).concat(up.slice(0, -1));
}
function partFrame(ring, extra) {     // угол длинной оси участка и его габарит в повёрнутой системе
  const h = hull(ring), box = a => { const q = h.map(p => rot(p, -a, [0, 0])); return bboxOf(q); };
  let best = null;
  h.forEach((p, k) => { const q = h[(k + 1) % h.length], a = Math.atan2(q[1] - p[1], q[0] - p[0]), b = box(a), ar = (b[2] - b[0]) * (b[3] - b[1]); if (!best || ar < best.ar) best = { a, ar }; });
  let a = best.a, b = box(a); if (b[2] - b[0] < b[3] - b[1]) { a += Math.PI / 2; b = box(a); }
  a += extra; return { a, b: box(a) };
}
function generate(site, p) {
  let out = place(site, p);
  /* потолок (узел «Ограничения»): корпус не выше наименьшего потолка под ним — инсоляция соседей и высота по ПЗЗ;
     ниже двух этажей корпус не ставится. Разрывы между корпусами считаются от наибольшей этажности — после
     понижения они с запасом, а не впритык */
  const fh = typeof CONS !== "undefined" ? CONS.floorH : 3;
  const plots = out.plots, streets = out.streets, note = out.note;
  // малоэтажный дом (ИЖС, блокированный) может быть и одноэтажным; остальные корпуса ниже двух этажей не ставятся
  out = out.map(b => { const top = p.cap ? p.cap(b.f) : null, max = Math.min(b.maxF ?? Infinity, top == null ? b.floors : Math.min(b.floors, Math.floor(top / fh))); return max >= (b.minF ?? 2) ? { ...b, max, floors: max, capped: max < b.floors } : null; }).filter(Boolean);   // capped — потолок ниже задуманного
  // участок без дома (дом не поместился под потолком) остаётся свободным, а не пропадает
  out.plots = plots || []; out.streets = streets || []; out.note = note;
  if (!p.goal) return out;
  /* этажность под цель плотности («выращивание» внутри потолка): всем корпусам одна этажность, упёршиеся в свой
     потолок остаются на нём, недобор раздаётся остальным — пока не набрана нужная СПП или всем некуда расти */
  const need = p.goal.need;
  const fill = list => {
    let free = list.slice().sort((a, b) => a.max - b.max), fixed = 0;
    while (free.length) {
      const area = free.reduce((s, b) => s + b.m2, 0), f = Math.max(Math.min(...free.map(b => b.minF ?? 2)), Math.round((need - fixed) / area));
      const low = free.filter(b => b.max <= f);
      if (!low.length) { free.forEach(b => { b.floors = Math.min(b.max, f); }); break; }
      low.forEach(b => { b.floors = b.max; fixed += b.m2 * b.max; }); free = free.filter(b => b.max > f);
    }
    // одна общая этажность округляется вниз до полэтажа — при 5 этажах это до 10 % цели; добор по этажу корпусам с запасом
    let spp = list.reduce((s, b) => s + b.m2 * b.floors, 0);
    for (const b of list.slice().sort((a, b) => b.m2 - a.m2)) { if (spp >= need) break; if (b.floors < b.max) { b.floors++; spp += b.m2; } }
    return spp;
  };
  let spp = fill(out);
  /* цель набрана — корпуса под низкой предельной высотой (инсоляция соседей, ПЗЗ) убираются по одному, начиная с самого низкого, пока
     остальные добирают цель своей этажностью. Их пятна остаются дворами: там свет нужен соседям. Урбан-блоки, блокированные
     и ИЖС не прореживаются — у них корпус часть квартала, ряда или участка (grp). Решение владельца 23.09.2026 (Э10). */
  const dropped = [];
  if (spp >= need * .97) {
    const cand = out.filter(b => b.capped && b.grp == null).sort((a, b) => a.max - b.max || a.m2 - b.m2);
    let keep = out.slice();
    for (const b of cand) {
      const rest = keep.filter(x => x !== b);
      if (fill(rest) >= need * .97) { keep = rest; dropped.push(b); } else break;
    }
    if (dropped.length) {
      spp = fill(keep);
      const kept = new Set(keep), plots2 = out.plots, streets2 = out.streets, note2 = out.note;
      out = out.filter(b => kept.has(b)); out.plots = plots2; out.streets = streets2; out.note = note2;
      // пятна снятых корпусов, касающиеся друг друга, — одно пятно; вид свой, чтобы не читалось как пустой участок
      const u = unionAll(dropped.map(b => b.f)), parts = u ? polys(u).map(c => turf.polygon(c)) : dropped.map(b => b.f);
      parts.forEach(f => out.plots.push({ f, kind: "свет соседям", m2: m2(f), "Причина": "корпус снят: низкая предельная высота, соседям нужен свет" }));
    } else spp = fill(out);
  }
  out.dropped = dropped.length;
  out.goal = spp < need * .97 ? `цель не достигнута: не хватает ${fmt((need - spp) / 1000, 1)} тыс. м²` : `цель ${p.goal.target} тыс. м²/га${dropped.length ? ` · ${plural(dropped.length, ["корпус снят", "корпуса сняты", "корпусов снято"])}: свет соседям` : ""}`;
  return out;
}
function place(site, p) {
  if (!site) return [];
  const out = [], extra = p.angle * Math.PI / 180; out.plots = []; out.streets = [];
  const fits = (part, ring) => { const f = polyLL(ring), ar = m2(f); return m2(inter(part, f)) >= ar * .997 ? f : null; };   // корпус целиком на пятне (0,3 % — погрешность площади)
  const low = LOWRISE.has(p.typ), push = (f, floors, kind, extra = {}) => out.push({ f, floors: low ? Math.min(3, floors) : floors, m2: m2(f), kind, ...(low ? { maxF: 3, minF: 1 } : {}), ...extra });
  const plot = (f, kind, props = {}) => f && out.plots.push({ f, kind, m2: m2(f), ...props });
  let grp = 0;
  for (const part of splitParts(site)) {
    if (m2(part) < 1500) continue;
    const { a, b } = partFrame(ringsXY(part)[0], extra), W = rp => rp.map(q => rot(q, a, [0, 0]));
    const span = (lo, hi, size, gap) => { const n = Math.max(0, Math.floor((hi - lo + gap) / (size + gap))); const s0 = lo + (hi - lo - (n * size + (n - 1) * gap)) / 2; return Array.from({ length: n }, (_, i) => s0 + i * (size + gap)); };
    const H = p.floors * 3, gapLong = Math.max(p.gap * H, p.floors >= 4 ? 20 : 15), brk = 12;
    const tower = p.width + 8, tfl = Math.round(p.floors * 1.6);
    // ряд секций; withTowers — через одну вставляется точечный дом (башня), как в точечно-секционной застройке
    const row = (v, withTowers) => {
      let u = b[0], k = 0;
      while (u < b[2]) {
        if (withTowers && k % 2 === 1) { const f = fits(part, W(rect(u, v - (tower - p.width) / 2, u + tower, v - (tower - p.width) / 2 + tower))); if (f) { push(f, tfl, "башня"); u += tower + brk; k++; continue; } }
        const L = [60, 40].find(len => u + len <= b[2] + .1 && fits(part, W(rect(u, v, u + len, v + p.width))));
        if (L) { push(polyLL(W(rect(u, v, u + L, v + p.width))), p.floors, "секция"); u += L + brk; k++; } else u += 5;   // секция 60 м, у края — 40 м
      }
    };
    if (p.typ === "Секции" || p.typ === "Точка + секция") {
      for (const v of span(b[1], b[3], p.width, gapLong)) row(v, p.typ === "Точка + секция");
    } else if (p.typ === "Смешанная") {                 // секции по краям участка (вдоль улиц), внутри — башни
      const rows = span(b[1], b[3], p.width, gapLong);
      rows.forEach((v, i) => { if (i === 0 || i === rows.length - 1) row(v, false);
        else { const g = Math.max(20, p.gap * tfl * 3 * .6); for (const u of span(b[0], b[2], tower, g)) { const f = fits(part, W(rect(u, v - (tower - p.width) / 2, u + tower, v - (tower - p.width) / 2 + tower))); if (f) push(f, tfl, "башня"); } } });
    } else if (p.typ === "Башни") {
      const s = p.width + 8, fl = Math.round(p.floors * 1.6), gap = Math.max(20, p.gap * fl * 3 * .6);
      for (const v of span(b[1], b[3], s, gap)) for (const u of span(b[0], b[2], s, gap)) { const f = fits(part, W(rect(u, v, u + s, v + s))); if (f) push(f, fl, "башня"); }
    } else if (p.typ === "ИЖС" || p.typ === "Блокированные") {
      lowRise(part, a, b, W, span);
    } else if (p.typ === "Урбан-блоки") {
      urbanBlocks(part, a, b, W, span);
    } else {                                    // квартал: периметр по краю участка с проездом во двор
      if (m2(part) < 2500) continue;
      perimeter(part, b, W, Math.max(3, Math.round(p.floors * .7)), "квартал");
    }
  }
  if (p.typ === "Урбан-блоки" && !out.length) out.note ||= `квартал ${p.block} × ${Math.round(p.block * .8)} м не помещается в пятно — уменьшите «квартал, м»`;
  return out;

  function perimeter(part, b, W, floors, kind) {
    const ring = diff(part, buf(part, -p.width)) || part, cx = (b[0] + b[2]) / 2;
    const r = diff(ring, polyLL(W(rect(cx - 7, b[1] - 5, cx + 7, b[3] + 5)))) || ring;
    splitParts(r).forEach(q => { if (m2(q) >= 150) push(q, floors, kind); });
  }
  function pieces(f) { return f ? splitParts(f) : []; }
  // часть прямоугольника внутри пятна (одним куском), если её площадь не меньше доли share от прямоугольника
  function clipped(part, ring, share) { const f = polyLL(ring), full = m2(f); if (m2(inter(part, f)) >= full * .997) return f;
    const q = pieces(inter(part, f)).sort((x, y) => m2(y) - m2(x))[0]; return q && m2(q) >= full * share ? q : null; }
  function street(part, W, x0, y0, x1, y1, kind) { const f = inter(part, polyLL(W(rect(x0, y0, x1, y1)))); if (f && m2(f) > 50) out.streets.push({ f, kind, m2: m2(f) }); }

  /* ИЖС и блокированные дома — полосы «ряд участков — ряд участков — проезд»: участки двух рядов смыкаются задними
     границами, лицом выходят на свой проезд (у края пятна — на внешнюю улицу). Проезд 12 м в красных линиях.
     ИЖС (ГрК РФ ст. 1 п. 39: отдельно стоящий дом не выше 3 этажей): участок заданной площади, фронт ~ корень из
     площади / 1,6; дом до 12 × 12 м, 5 м от красной линии проезда и не ближе 3 м к границам соседних участков
     (СП 42.13330). Блокированные (ГрК РФ ст. 49 ч. 2 п. 2: не выше 3 этажей, не больше 10 домов в ряду): блок
     7 м по фасаду, глубина — «ширина корпуса» (10–14 м), 5 м палисадник и 12 м сад за домом — между длинными
     сторонами соседних рядов 24 м (не меньше 15 м для 2–3 этажей, СП 42.13330); в ряду до 6 блоков, между рядами
     домов по фасаду — 10 м проход. */
  function lowRise(part, a, b, W, span) {
    const S = 12, izs = p.typ === "ИЖС";
    const area = Math.max(400, p.plot * 100), F = Math.min(40, Math.max(18, Math.round(Math.sqrt(area / 1.6)))), Dz = Math.round(area / F);
    const uw = 7, hd = Math.max(10, Math.min(14, p.width)), G = 12, D = izs ? Dz : 5 + hd + G;
    const pitch = 2 * D + S, Hv = b[3] - b[1], m = Math.max(0, Math.floor((Hv + S) / pitch));
    const v0 = b[1] + (Hv - (m * pitch - S)) / 2;
    const front = new Array(Math.max(0, m - 1)).fill(0);        // домов лицом на каждый проезд — для гостевых мест
    // дома крайних рядов смотрят на внешнюю улицу, её в эскизе нет: их гостевые места — на ближайшем проезде
    let orphan = 0;
    const faces = (k, up, n) => { if (!front.length) { orphan += n; return; } front[Math.max(0, Math.min(front.length - 1, up ? k : k - 1))] += n; };
    for (let k = 0; k < m; k++) {
      const vs = v0 + k * pitch;
      if (k < m - 1) street(part, W, b[0] - 5, vs + 2 * D, b[2] + 5, vs + 2 * D + S, "проезд");
      for (const [r0, up] of [[vs, false], [vs + D, true]]) {        // up — ряд лицом к верхней границе полосы
        if (izs) {
          for (const u of span(b[0], b[2], F, 0)) {
            // у неровной границы участок подрезается ею, если осталось не меньше 70 % площади и дом помещается целиком
            const hw = Math.min(12, F - 8), hh = Math.min(12, D - 5 - 10), hu = u + (F - hw) / 2, hv = up ? r0 + D - 5 - hh : r0 + 5;
            const pl = clipped(part, W(rect(u, r0, u + F, r0 + D)), .7), house = pl && fits(part, W(rect(hu, hv, hu + hw, hv + hh))); if (!house) continue;
            plot(pl, "участок ИЖС", { "Площадь, сот.": Math.round(m2(pl) / 10) / 10 });
            push(house, p.floors, "дом ИЖС", { grp: ++grp }); faces(k, up, 1);
            // хозпостройка или гараж 4 × 6 м в глубине участка, 1 м от задней и боковой границ (СП 42.13330, п. 7.1):
            // в СПП не входит, показывается на участке — где дом и сарай стоят вместе, видно сразу
            const ov = up ? r0 + 1 : r0 + D - 1 - 6, out1 = polyLL(W(rect(u + 1, ov, u + 5, ov + 6)));
            if (Math.abs((up ? hv : hv + hh) - (up ? ov + 6 : ov)) >= 6 && m2(inter(pl, out1)) >= m2(out1) * .99)
              plot(out1, "хозпостройка", { "Площадь, м²": 24 });
          }
        } else {
          // ряды раскладываются от середины полосы: пробный проход слева даёт остаток на правом конце,
          // и начало сдвигается на половину остатка — полоса не «прижата» к одному краю
          const memo = new Map(), once = (k, fn) => memo.has(k) ? memo.get(k) : (memo.set(k, fn()), memo.get(k));
          const rowsFrom = (u0, dry) => { let u = u0, last = u0, count = 0;
            while (u + 3 * uw <= b[2] + .1) {
              const hv = up ? r0 + D - 5 - hd : r0 + 5;
              const units = []; for (let i = 0; i < 6; i++) { const x = u + i * uw, q = once("c" + x, () => clipped(part, W(rect(x, r0, x + uw, r0 + D)), .6)); if (!q) break; units.push(q); }
              let n = units.length; while (n >= 3 && !once("f" + u + ":" + n, () => fits(part, W(rect(u, hv, u + n * uw, hv + hd))))) n--;
              if (n < 3) { u += units.length ? uw : 5; continue; }
              count += n; last = u + n * uw;
              if (!dry) { grp++;
                for (let i = 0; i < n; i++) plot(units[i], "участок блока", { "Площадь, сот.": Math.round(m2(units[i]) / 10) / 10, "Блок": grp });
                push(polyLL(W(rect(u, hv, u + n * uw, hv + hd))), p.floors, "блокированный дом", { grp, "Блоков": n }); faces(k, up, n); }
              u += n * uw + 10;
            }
            return { count, slack: b[2] - last }; };
          const first = rowsFrom(b[0], true), shift = Math.max(0, first.slack / 2);
          const alt = shift > 1 ? rowsFrom(b[0] + shift, true) : null;
          rowsFrom(alt && alt.count >= first.count ? b[0] + shift : b[0], false);
        }
      }
    }
    /* Гостевые места по 945-ПП: постоянных мест жителей ИЖС и блокированных домов — 1,6 на дом (Прил. 5 п. 2, «C»; блок
       блокированного дома — дом), гостевых — 10 % от них (п. 6.2.3.2), с округлением вверх. Постоянные — на своих участках.
       Гостевые — плоскостные «карманы» 2,5 м вдоль проезда (улица местного значения: гостевые на прилегающей стороне
       допускаются, Прил. 7), по 6 м на место параллельно проезду; группами не реже чем через 400 м — до места не дальше
       200 м (п. 6.1.2.5.2). */
    if (orphan) out.note ||= `гостевых мест по 945-ПП нужно ${Math.ceil(orphan * .16 - 1e-9)}: внутренних проездов нет — разместите на внешней улице`;
    let short = 0;
    front.forEach((n, k) => {
      if (!n) return;
      const need = Math.ceil(n * 1.6 * .1 - 1e-9), L = b[2] - b[0], groups = Math.max(1, Math.ceil(L / 400)), per = Math.ceil(need / groups);
      const vs = v0 + k * pitch + 2 * D;                       // край проезда со стороны домов полосы k
      let left = need;
      for (let g = 0; g < groups && left > 0; g++) {
        const nn = Math.min(per, left), len = nn * 6, c = b[0] + L * (g + .5) / groups;
        for (const du of [0, -60, 60, -120, 120]) {            // у неровной границы карман сдвигается вдоль проезда
          const f = polyLL(W(rect(c - len / 2 + du, vs, c + len / 2 + du, vs + 2.5)));
          if (m2(inter(part, f)) >= m2(f) * .95) { out.streets.push({ f, kind: "гостевая стоянка", m2: m2(f), "Мест": nn }); left -= nn; break; }
        }
      }
      short += left;
    });
    if (short) out.note ||= `гостевых мест по 945-ПП не поместилось вдоль проездов: ${short} — разместите на внешней улице или парковке`;
  }

  /* урбан-блоки: сетка кварталов «квартал, м» × 0,8 с улицами 20 м между ними; по периметру квартала — секции
     глубиной «ширина корпуса» сплошным фронтом на улицу (первый этаж — нежилой), углы северной стороны — акценты ×1,4
     по этажности, сторона, обращённая на юг, — 0,6 от заданной (её углы — заданная), чтобы солнце попадало во двор; в торцевых сторонах — проход
     во двор 12 м. Квартал ставится только целиком внутри пятна. */
  function urbanBlocks(part, a, b, W, span) {
    const S = 20, Bu = p.block, Bv = Math.round(p.block * .8), d = p.width;
    if (Bu < 2 * d + 20 || Bv < 2 * d + 20) { out.note = `квартал ${Bu} × ${Bv} м меньше двух корпусов по ${d} м и двора 20 м — нужно от ${Math.ceil((2 * d + 20) / .8)} м`; return false; }
    const us = span(b[0], b[2], Bu, S), vs = span(b[1], b[3], Bv, S);
    let placed = 0;
    const side = (nx, ny) => { const c = Math.cos(a), s_ = Math.sin(a); return nx * s_ + ny * c; };        // северная составляющая наружной нормали стороны
    const south = [[0, -1], [0, 1], [-1, 0], [1, 0]].map(([nx, ny]) => side(nx, ny)), minN = Math.min(...south);
    const fl = { corner: Math.round(p.floors * 1.4), mid: p.floors, south: Math.max(2, Math.round(p.floors * .6)) };
    const at = new Set();                       // клетки сетки с кварталом: улицы — только между ними
    us.forEach((x0, i) => vs.forEach((y0, j) => {
      const x1 = x0 + Bu, y1 = y0 + Bv;
      if (!fits(part, W(rect(x0, y0, x1, y1)))) { if (cutBlock(part, W, x0, y0, x1, y1, d, Bu * Bv)) { placed++; at.add(i + ":" + j); } return; }
      placed++; grp++; at.add(i + ":" + j);
      const put = (r, floors, kind) => push(polyLL(W(r)), floors, kind, { grp, "1 этаж": "нежилой, на улицу" });
      const isS = k => south[k] === minN && minN < -.5;          // сторона смотрит на юг (отклонение не больше 60°)
      // нижняя и верхняя стороны — во всю длину с углами; боковые — между ними, с проходом во двор посередине
      [[y0, y0 + d, 0], [y1 - d, y1, 1]].forEach(([ya, yb, k]) => {
        // акценты — только на углах северной стороны: высокие южные углы затеняли дворовые фасады боковых секций
        const c = d + 10, L = Bu - 2 * c, cf = isS(k) ? fl.mid : fl.corner;
        if (L < 15) { const xm = (x0 + x1) / 2; put(rect(x0, ya, xm, yb), cf, "урбан-блок: угол"); put(rect(xm, ya, x1, yb), cf, "урбан-блок: угол"); return; }
        put(rect(x0, ya, x0 + c, yb), cf, "урбан-блок: угол"); put(rect(x1 - c, ya, x1, yb), cf, "урбан-блок: угол");
        const n = Math.max(1, Math.round(L / 45)), step = L / n;
        for (let i = 0; i < n; i++) put(rect(x0 + c + i * step, ya, x0 + c + (i + 1) * step, yb), isS(k) ? fl.south : fl.mid, isS(k) ? "урбан-блок: южная сторона" : "урбан-блок");
      });
      [[x0, x0 + d, 2], [x1 - d, x1, 3]].forEach(([xa, xb, k]) => {
        const ya = y0 + d, yb = y1 - d, ym = (ya + yb) / 2, f = isS(k) ? fl.south : fl.mid, kind = isS(k) ? "урбан-блок: южная сторона" : "урбан-блок";
        if (yb - ya >= 36) { put(rect(xa, ya, xb, ym - 6), f, kind); put(rect(xa, ym + 6, xb, yb), f, kind); } else put(rect(xa, ya, xb, yb), f, kind);
      });
      plot(polyLL(W(rect(x0 + d, y0 + d, x1 - d, y1 - d))), "двор", { "Блок": grp });
    }));
    if (!placed) return false;
    us.forEach((x0, i) => vs.forEach((y0, j) => {
      if (!at.has(i + ":" + j)) return;
      if (at.has(i + 1 + ":" + j)) street(part, W, x0 + Bu, y0, us[i + 1], y0 + Bv, "улица");
      if (at.has(i + ":" + (j + 1))) street(part, W, x0, y0 + Bv, x0 + Bu, vs[j + 1], "улица");
      if (at.has(i + 1 + ":" + j) && at.has(i + ":" + (j + 1)) && at.has(i + 1 + ":" + (j + 1))) street(part, W, x0 + Bu, y0 + Bv, us[i + 1], vs[j + 1], "улица");   // перекрёсток
    }));
    return true;
  }
  /* квартал у границы пятна (улица, отступ, существующие дома): часть клетки сетки внутри пятна, если это не меньше
     60 % квартала; секции идут по её наружному контуру (внутрь, вокруг сохраняемых домов, лент не будет), фронт режется
     на секции по 45 м; этажность — заданная */
  function cutBlock(part, W, x0, y0, x1, y1, d, full) {
    const cp = pieces(inter(part, polyLL(W(rect(x0, y0, x1, y1))))).sort((x, y) => m2(y) - m2(x))[0];
    if (!cp || m2(cp) < full * .6) return 0;
    // квартал без двора — не квартал: двор не меньше 20 % его площади и 600 м², иначе клетка остаётся пустой
    const outer = turf.polygon([cp.geometry.coordinates[0]]), core = buf(outer, -d), yard = core && inter(core, cp);
    if (!yard || m2(yard) < Math.max(600, m2(cp) * .2)) return 0;
    const ring = inter(diff(outer, core), cp); if (!ring) return 0;
    grp++; let n = 0;
    for (let tx = x0; tx < x1 - .1; tx += 45) for (let ty = y0; ty < y1 - .1; ty += 45)
      pieces(inter(ring, polyLL(W(rect(tx, ty, Math.min(tx + 45, x1), Math.min(ty + 45, y1))))))
        .forEach(q => { if (m2(q) >= 150) { push(q, p.floors, "урбан-блок", { grp, "1 этаж": "нежилой, на улицу" }); n++; } });
    plot(yard, "двор", { "Блок": grp });
    return n ? 1 : 0;
  }
}

/* ---------- граф по умолчанию ---------- */
const graph = new LGraph();
function add(type, pos, setup) { const n = LiteGraph.createNode(type); n.pos = pos; graph.add(n); setup?.(n); return n; }
const setW = (n, name, v) => { n.widgets.find(w => w.name === name).value = v; };
const nT = add("Данные/Территория", [20, 20]);
const nZ1 = add("Данные/Слой", [20, 100], n => setW(n, "слой", "Санитарно-защитные зоны (ОГД)"));
const nZ2 = add("Данные/Слой", [20, 280], n => setW(n, "слой", "Водоохранные зоны (ОГД)"));
const nK = add("Данные/Слой", [20, 460], n => { setW(n, "слой", "Здания (ЕГРН)"); n.title = "Сохраняемые здания"; });   // по умолчанию сносить нечего; снос — условием в узле
const nR = add("Данные/Слой", [20, 640], n => { setW(n, "слой", "Улично-дорожная сеть (OSM)"); setW(n, "поле", "Тип дороги"); setW(n, "условие", "один из"); setW(n, "значение", "trunk,primary,secondary,tertiary,residential,unclassified"); });
const nZ = add("Геометрия/Объединить", [300, 200], n => n.title = "ЗОУИТ");
const nBK = add("Геометрия/Буфер", [300, 470], n => { n.title = "Разрыв до сохраняемых"; setW(n, "расстояние, м", 12); });
const nBR = add("Геометрия/Буфер", [300, 650], n => { n.title = "Отступ от улиц"; setW(n, "расстояние, м", 12); });
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
Object.assign(lgc, { background_image: null, clear_background_color: "#e6e6e2", render_canvas_border: false, render_shadows: false, show_info: false, render_connection_arrows: false, title_text_font: GFONT.title, inner_text_font: GFONT.inner, links_render_mode: LiteGraph.SPLINE_LINK });
Object.defineProperty(lgc, "low_quality", { get: () => false, set() { } }); // подписи узлов при любом масштабе
let selNode = null;
lgc.onNodeSelected = n => { selNode = n; updateAnalysisMap(); };
lgc.onNodeDeselected = () => { selNode = null; updateAnalysisMap(); };
function fitGraph(min = .6) {
  const box = $("graphbox").getBoundingClientRect(), ns = graph._nodes; if (!ns.length || !box.width) return;
  const x0 = Math.min(...ns.map(n => n.pos[0])), y0 = Math.min(...ns.map(n => n.pos[1])) - 30, x1 = Math.max(...ns.map(n => n.pos[0] + n.size[0])), y1 = Math.max(...ns.map(n => n.pos[1] + n.size[1]));
  const s = Math.max(min, Math.min(1.1, (box.width - 40) / (x1 - x0), (box.height - 60) / (y1 - y0))); // мельче 0,6 подписи узлов не читаются — дальше прокрутка
  lgc.ds.scale = s; lgc.ds.offset = [20 / s - x0, 50 / s - y0]; lgc.setDirty(true, true);
}
function sizeGraph() { const b = $("graphbox").getBoundingClientRect(); if (b.width) { lgc.resize(Math.round(b.width), Math.round(b.height)); lgc.setDirty(true, true); } }
new ResizeObserver(sizeGraph).observe($("graphbox"));
$("bFitGraph").onclick = () => fitGraph();
$("bRunGraph").onclick = () => { graph._nodes.forEach(n => { n._ck = n._cacheKey = n._key = null; }); recompute(true); };
const LIB = { "Данные": ["Данные/Территория", "Данные/Слой"], "Параметры": ["Параметры/Число"], "Геометрия": ["Геометрия/Буфер", "Геометрия/Вычесть", "Геометрия/Объединить", "Геометрия/Пересечь"], "Эскиз": ["Эскиз/Посадка застройки"], "Показатели": ["Показатели/ТЭП КРТ"] };
const LIBICON = { "Данные": "database", "Параметры": "sliders-horizontal", "Геометрия": "shapes", "Эскиз": "building-2", "Показатели": "calculator" };
$("lib").innerHTML = Object.entries(LIB).map(([c, ts]) => `<div class="cat">${c}</div>` + ts.map(t => `<button data-add="${t}"><i data-lucide="${LIBICON[c]}"></i>${t.split("/")[1]}</button>`).join("")).join("");
$("lib").addEventListener("click", e => { const b = e.target.closest("[data-add]"); if (!b) return; add(b.dataset.add, lgc.convertCanvasToOffset([$("graphbox").clientWidth / 2 - 100, $("graphbox").clientHeight / 2 - 40])); lgc.setDirty(true, true); });

let lastSig = "", RESULT = { site: null, sketch: [], tep: null };
const signature = () => JSON.stringify([dataRev, Object.values(graph.links || {}).filter(Boolean).map(l => [l.origin_id, l.origin_slot, l.target_id, l.target_slot]), graph._nodes.map(n => [n.id, n.widgets?.map(w => w.value)])]);
function recompute(force) {
  const sig = signature(); if (!force && sig === lastSig) return; if (sig !== lastSig) window.markDirty?.(); lastSig = sig;
  safe(() => graph.runStep(1, true));
  const place = graph._nodes.find(n => n.type === "Эскиз/Посадка застройки"), tepN = graph._nodes.find(n => n.type === "Показатели/ТЭП КРТ");
  RESULT = { site: place?.getInputData(0) || null, sketch: place?.getOutputData(0) || [], tep: tepN?._tep || null, placeNode: place, tepNode: tepN };
  lgc.setDirty(true, true); updateAnalysisMap(); renderSketch();
  if (!recompute.once) { recompute.once = true; renderParams(); }
}
setInterval(() => { if (window.HUB_MODE === false || window.HUB_IN) recompute(false); }, 250);   // совместный режим: граф считается и ходит на сервер (/api/tep) только после входа

/* ---------- результат графа на основной карте ---------- */
const prevSrc = new ol.source.Vector(), sketchSrc = new ol.source.Vector(), siteSrc = new ol.source.Vector(), keptSrc = new ol.source.Vector();
const shade = n => ["#dcebfa", "#a8cbf1", "#6fa6e6", "#2a78d6", "#1a4f94"][Math.min(4, Math.floor(n / 6))];
const sketchStyle = f => new ol.style.Style({ fill: new ol.style.Fill({ color: shade(f.get("floors")) }), stroke: new ol.style.Stroke({ color: "#1a4f94", width: 1 }), text: new ol.style.Text({ text: String(f.get("floors")), font: "11px Arial", fill: new ol.style.Fill({ color: f.get("floors") > 14 ? "#fff" : "#123" }) }) });
const siteLayer = () => new ol.layer.Vector({ source: siteSrc, zIndex: 20, style: new ol.style.Style({ fill: new ol.style.Fill({ color: hatch("#1f7a4d") }), stroke: new ol.style.Stroke({ color: "#1f7a4d", width: 1.4, lineDash: [5, 3] }) }) });
const keptLayer = () => new ol.layer.Vector({ source: keptSrc, zIndex: 35, style: S("#bdb8b0", "#4d4d4d", 1) });
const sketchLayer = () => new ol.layer.Vector({ source: sketchSrc, zIndex: 40, style: sketchStyle });
// участки, дворы и улицы эскиза (ИЖС, блокированные, урбан-блоки) — под корпусами
const GROUND = { "улица": ["#e4e1da", "#b7b2a8"], "проезд": ["#e4e1da", "#b7b2a8"], "участок ИЖС": ["#eef5e4", "#7a9a5a"], "участок блока": ["#eef5e4", "#7a9a5a"], "двор": ["#f6f1dc", "#c9b77a"], "хозпостройка": ["#e9e2d6", "#8c7b62"], "гостевая стоянка": ["#c9d8ee", "#5577aa"], "свет соседям": ["#fdf0b8", "#d9a400"] };
const groundSrc = new ol.source.Vector(), groundStyle = f => { const [fill, stroke] = GROUND[f.get("kind")] || ["#eeeeee", "#999999"]; return S(fill, stroke, .8); };
// результат графа — отдельные слои над данными; видимость переключается в дереве слоёв
const RES = [
  { id: "site", title: "Пятно застройки", color: "#1f7a4d", layer: siteLayer() },
  { id: "kept", title: "Сохраняемые здания", color: "#bdb8b0", layer: keptLayer() },
  { id: "ground", title: "Участки и улицы эскиза", color: "#b7b2a8", layer: new ol.layer.Vector({ source: groundSrc, style: groundStyle }) },
  { id: "sketch", title: "Эскиз застройки", color: "#6fa6e6", layer: sketchLayer() },
  { id: "prev", title: "Выход выбранного узла", color: "#e08a00", layer: new ol.layer.Vector({ source: prevSrc, declutter: true, style: f => {
    const out = [S([224, 138, 0, .22], "#c46f00", 2)], t = f.get("Пояснение");            // узел объясняет результат словами прямо на карте
    if (t) out.push(new ol.style.Style({ text: new ol.style.Text({ text: String(t), font: "600 12px system-ui, sans-serif", fill: new ol.style.Fill({ color: "#6b3a00" }), stroke: new ol.style.Stroke({ color: "#fff", width: 3 }), overflow: false, placement: "point" }) }));
    return out; } }) }];
RES.forEach((r, i) => { r.layer.setZIndex(100 + i); mMain.addLayer(r.layer); });
function fillGeom(src, f) { src.clear(); if (f) src.addFeature(toOl(f)); }
function fillSketch() {
  sketchSrc.clear(); sketchSrc.addFeatures(RESULT.sketch.map(b => { const f = toOl(b.f); f.set("floors", b.floors); return f; }));
  groundSrc.clear(); groundSrc.addFeatures([...(RESULT.sketch.streets || []), ...(RESULT.sketch.plots || [])].map(g => { const f = toOl(g.f); f.set("kind", g.kind); return f; }));
}
function updateAnalysisMap() {
  fillGeom(siteSrc, RESULT.site); fillSketch(); prevSrc.clear();
  let txt = TERR ? `Пятно застройки ${ha(RESULT.site)} · ${RESULT.sketch.length} корпусов` : "Сначала задайте территорию и загрузите данные (окно «Данные»)";
  if (selNode) { const out = selNode.getOutputData?.(0), t = selNode.outputs?.[0]?.type;
    if (selNode._fc?.length) { prevSrc.addFeatures(selNode._fc.map(toOl)); txt = `«${selNode.title}»: ${selNode.info || ""}. «В слой» — сохранить результат с таблицей.`; }
    else if (t === "geom") { if (out) prevSrc.addFeature(toOl(out)); txt = `Выход узла «${selNode.title}»: ${ha(out)}`; }
    else if (t === "tep" && out) txt = `«${selNode.title}»: плотность ${fmt(out.density, 1)} тыс. м²/га, население ${fmt(out.m.population)} чел.`;
    else if (t === "num") txt = `«${selNode.title}»: ${out}`; }
  $("pv").textContent = txt; $("pv").hidden = $("wGraph").hidden;
  if (typeof renderTree === "function") renderTree();
}

/* ================= эскиз ================= */
let mBefore = null, mAfter = null, rot3d = 0;
function publishedControls() {
  const p = RESULT.placeNode, t = RESULT.tepNode, num = graph._nodes.find(n => n.type === "Параметры/Число" && n.outputs[0].links?.some(id => graph.links[id]?.target_id === p?.id));
  const out = [];
  const typ = p?.widgets[0].value;
  const TYP_HINT = { "Секции": "секции по 40–60 м рядами вдоль длинной стороны участка", "Квартал": "периметр каждого участка с проездом во двор, этажность 0,7 заданной",
    "Башни": "точечные дома сеткой, этажность ×1,6", "Точка + секция": "в рядах секций через одну — башня (×1,6)", "Смешанная": "секции по краям участка, башни внутри",
    "Урбан-блоки": "сетка кварталов с улицами 20 м, сплошной фронт, углы северной стороны выше, южная сторона ниже — солнце во дворе",
    "Блокированные": "ряды до 6 блоков по 7 м, у каждого блока участок; проезды 12 м; до 3 этажей", "ИЖС": "дом на своём участке, проезды 12 м между парами рядов; до 3 этажей" };
  if (p) out.push({ n: p, w: "типология", type: "seg", opts: TYPOLOGIES, hint: TYP_HINT[typ] || "" });
  if (p && p.widgets[5]) out.push({ n: p, w: "этажность по", label: "Этажность по", type: "seg", opts: FLOOR_MODES, hint: "цели плотности — этажность подбирается под «Целевую плотность» узла ТЭП, не выше предельной высоты; «Этажность» ниже — наибольшая" });
  const lowF = LOWRISE.has(typ), fr = lowF ? { min: 1, max: 3 } : { min: 3, max: 30 };
  if (num) out.push({ n: num, w: "значение", label: "Этажность", ...fr, step: 1, hint: lowF ? "до 3 этажей" : "блок «Число» в схеме" }); else if (p) out.push({ n: p, w: "этажность", ...fr, step: 1 });
  // параметры, которые выбранная типология не использует, в панели не показываются
  if (p && typ === "ИЖС") out.push({ n: p, w: "участок, соток", label: "Участок, соток", min: 4, max: 20, step: 1, hint: "дом до 12 × 12 м: 5 м от проезда, не ближе 3 м к соседним участкам; проезды 12 м между парами рядов" });
  // короче двух корпусов и двора 20 м квартал не бывает — ползунок ниже не опускается
  if (p && typ === "Урбан-блоки") out.push({ n: p, w: "квартал, м", label: "Квартал по длинной стороне, м", min: Math.ceil((2 * Math.round(p.widgets[1].value) + 20) / .8 / 5) * 5, max: 200, step: 5, hint: "квартал — длина × 0,8; между кварталами улицы 20 м; ставится только квартал, целиком помещающийся в пятно" });
  if (p && typ !== "ИЖС") out.push({ n: p, w: "ширина корпуса, м", label: typ === "Блокированные" ? "Глубина дома, м" : "Ширина корпуса, м", min: 12, max: 24, step: 1, hint: typ === "Блокированные" ? "берётся от 10 до 14 м; блок 7 м по фасаду, до 6 блоков в ряду, палисадник 5 м и сад 12 м" : "" });
  if (p && !LOWRISE.has(typ) && typ !== "Урбан-блоки") out.push({ n: p, w: "разрыв / высота", min: .5, max: 2, step: .05, hint: "разрыв между длинными сторонами = коэф. × высота, но не меньше 15 м (2–3 эт.) и 20 м (4 эт. и выше), СП 42.13330 п. 7.1" });
  if (p) out.push({ n: p, w: "поворот, °", label: "Поворот относительно длинной стороны участка, °", min: -90, max: 90, step: 1, hint: "0 — ряды (кварталы) вдоль длинной стороны каждого участка, 90 — поперёк" });
  graph._nodes.filter(n => n.type === "Геометрия/Буфер").forEach(n => out.push({ n, w: "расстояние, м", label: n.title + ", м", min: 0, max: 40, step: 1 }));
  if (t) out.push({ n: t, w: "доля жилья, %", min: 0, max: 100, step: 5 }, { n: t, w: "цель, тыс. м²/га", label: "Целевая плотность, тыс. м²/га", min: 5, max: 45, step: 1 });
  return out;
}
/* «Сравнение»: пока сравнивать нечего — строка-подсказка сверху */
function syncCmpHint() { const h = $("cmpHint"); if (h) h.hidden = !!(RESULT.sketch?.length && Object.keys(DATA).length); }
function renderParams() {
  syncCmpHint();
  const cs = publishedControls(), pn = RESULT.placeNode, on = !!pn?.properties.run;
  const head = !pn ? `<div class="note">В схеме расчёта нет блока «Посадка застройки».</div>`
    : `<div class="ctl"><div class="row" style="margin:0">${on ? `<button class="btn" data-run="0" title="Остановить пересчёт посадки: правка параметров перестанет перестраивать эскиз"><i data-lucide="pause"></i>Остановить</button>` : `<button class="btn primary" data-run="1" title="Разместить корпуса на пятне застройки по заданной типологии"><i data-lucide="play"></i>Построить эскиз</button>`}<button class="btn" data-bake ${RESULT.sketch.length ? "" : "disabled"} title="Сделать эскиз обычным слоем проекта: править, стилизовать, выгружать"><i data-lucide="stamp"></i>Сохранить слоем</button></div>
      <small>${on ? `Эскиз перестраивается при каждой правке ниже. ${LOWRISE.has(pn.widgets[0].value) ? "Домов" : "Корпусов"}: ${RESULT.sketch.length}.${RESULT.sketch.dropped ? ` Цель набрана и без ${plural(RESULT.sketch.dropped, ["корпуса", "корпусов", "корпусов"])} под низкой предельной высотой — на их месте пятна «свет соседям» (жёлтые): там нужен свет соседям.` : ""}${RESULT.sketch.goal && /не достигнута/.test(RESULT.sketch.goal) ? ` ${RESULT.sketch.goal[0].toUpperCase()}${RESULT.sketch.goal.slice(1)}.` : ""} Пока эскиз не сохранён, он виден только при открытых окнах схемы расчёта и эскиза.` : TERR ? "Выберите типологию и параметры, затем «Построить эскиз»: корпуса сами не появляются. Пока окно открыто, на карте виден предварительный просмотр — пятно застройки и сохраняемые здания; «Сохранить слоем» сохраняет построенный эскиз слоем." : "<b class=\"warnt\">Нет границы территории.</b> Эскиз строится только внутри неё: задайте границу командой BO или «Пример территории» в окне «Данные»."}</small></div>`;
  const chk = window.LASTCHECK, check = pn ? `<div class="ctl"><div class="row" style="margin:0"><button class="btn" data-check ${RESULT.sketch.length ? "" : "disabled"} title="Инсоляция новых домов и соседей, корпуса на запретах, разрывы между корпусами — слой «Проверка норм» с причиной у каждой точки"><i data-lucide="shield-check"></i>Проверить нормы</button></div>${chk ? `<small>${esc(chk.text)}; новые дома — норму получают ${chk.own} % фасадов; соседи, потерявшие норму: ${chk.lost}</small>` : ""}</div>` : "";
  $("params").innerHTML = head + check + cs.map((c, i) => { const w = c.n.widgets.find(x => x.name === c.w), lbl = c.label || c.w[0].toUpperCase() + c.w.slice(1);
    if (c.type === "seg") return `<div class="ctl"><div class="t"><span>${esc(lbl)}</span></div><div class="seg">${c.opts.map(o => `<button data-seg="${i}" data-v="${o}" title="${o}" aria-pressed="${w.value === o}">${o}</button>`).join("")}</div>${c.hint ? `<small>${c.hint}</small>` : ""}</div>`;
    return `<div class="ctl"><div class="t"><label for="pc${i}">${esc(lbl)}</label><span id="pv${i}">${fmt(w.value, c.step < 1 ? 2 : 0)}</span></div><input type="range" id="pc${i}" data-pc="${i}" min="${c.min}" max="${c.max}" step="${c.step}" value="${Number(w.value)}" title="${esc(lbl)}: от ${fmt(c.min, c.step < 1 ? 2 : 0)} до ${fmt(c.max, c.step < 1 ? 2 : 0)}; эскиз перестраивается сразу">${c.hint ? `<small>${c.hint}</small>` : ""}</div>`; }).join("")
    + `<div class="note">Параметры блоков схемы, вынесенные в панель: правка здесь меняет схему, и наоборот.</div>`;
  icons();
  $("params").oninput = e => { const i = e.target.dataset.pc; if (i == null) return; const c = cs[+i], w = c.n.widgets.find(x => x.name === c.w); w.value = +e.target.value; $("pv" + i).textContent = fmt(w.value, c.step < 1 ? 2 : 0); recompute(); };
  $("params").onclick = e => {
    const r = e.target.closest("[data-run]"); if (r) {
      if (r.dataset.run === "1" && !TERR) return toast("Эскиз строится внутри границы территории, а её нет. Задайте границу: команда BO (кнопка «Граница» на ленте) или «Пример территории» в окне «Данные».");
      if (r.dataset.run === "1" && !RESULT.site) return toast("Пятно застройки пусто: вся территория занята запретами или сохраняемыми зданиями. Проверьте окно «Ограничения».");
      pn.properties.run = r.dataset.run === "1"; pn._ck = null;
      if (pn.properties.run && RESULT.tepNode?.properties?.baked) RESULT.tepNode.properties.baked = null;   /* новый эскиз — показатели снова по графу */ recompute(true); renderParams(); syncPreview(); return; }
    if (e.target.closest("[data-bake]")) return bakeSketch();
    if (e.target.closest("[data-check]")) return window.runCheck?.(null);
    const b = e.target.closest("[data-seg]"); if (!b) return; const c = cs[+b.dataset.seg]; c.n.widgets.find(x => x.name === c.w).value = b.dataset.v;
    // переход между малоэтажной и многоэтажной типологией — этажность по умолчанию для неё (2 и 12), а не 12 этажей ИЖС
    if (c.w === "типология") { const fc = cs.find(x => x.w === "значение" || x.w === "этажность"), fw = fc?.n.widgets.find(x => x.name === fc.w);
      if (fw && LOWRISE.has(b.dataset.v) && fw.value > 3) fw.value = 2; else if (fw && !LOWRISE.has(b.dataset.v) && fw.value <= 3) fw.value = 12; }
    recompute(true); renderParams(); };            // сначала пересчёт — иначе панель покажет число корпусов прежней типологии
}
/* «Сохранить слоем» (Bake в Grasshopper): снимок эскиза становится обычным слоем и больше не зависит от графа */
function bakeSketch() {
  const sk = RESULT.sketch; if (!sk.length) return toast("Эскиз пуст: сначала «Построить эскиз».");
  const typ = RESULT.placeNode.widgets[0].value, fl = [...new Set(sk.map(b => b.floors))].join("/"), key = "user:" + Date.now().toString(36), title = `Эскиз: ${typ.toLowerCase()}, ${fl} эт.`;
  const fc = turf.featureCollection(sk.map((b, i) => turf.feature(b.f.geometry, { "№": i + 1, "Типология": typ, "Корпус": b.kind || "", "Этажность": b.floors, "Площадь застройки, м²": Math.round(b.m2), "СПП, м²": Math.round(b.m2 * b.floors),
    ...(b.grp ? { "Блок": b.grp } : {}), ...(b["Блоков"] ? { "Блоков": b["Блоков"] } : {}), ...(b["1 этаж"] ? { "1 этаж": b["1 этаж"] } : {}) })));
  DATA[key] = { title, source: "эскиз из схемы расчёта, сохранён " + new Date().toLocaleDateString("ru-RU"), fetched_at: new Date().toISOString().slice(0, 10), fc, count: 0, fields: [] };
  layerSrc[key] = new ol.source.Vector(); setLayerData(key, fc); delete DATA[key].original;
  const l = ensureLayer(key, title, "poly");
  if (RESULT.tepNode) { (RESULT.tepNode.properties ||= {}).baked = key; RESULT.tepNode._key = null; }   // «Показатели» — по принятому слою
  const many = new Set(sk.map(b => b.floors)).size > 1;          // разная этажность — диапазоны, одна — единый цвет
  l.style = ST({ mode: many ? "grad" : "single", fill: "#6fa6e6", stroke: "#1a4f94", width: .8, opacity: .9, label: "Этажность", grad: { field: "Этажность", n: 4, ramp: "blue", method: "equal" } });
  restyle(l);
  // участки, дворы и улицы — отдельными слоями рядом с корпусами, одной группой «Эскиз: …»
  const extra = [];
  const layerOf = (list, name, fields, style) => { if (!list?.length) return; const k = "user:" + Date.now().toString(36) + extra.length;
    const lfc = turf.featureCollection(list.map((g, i) => turf.feature(g.f.geometry, { "№": i + 1, "Вид": g.kind, "Площадь, м²": Math.round(g.m2), ...fields(g) })));
    DATA[k] = { title: name, source: "эскиз из схемы расчёта, сохранён " + new Date().toLocaleDateString("ru-RU"), fetched_at: new Date().toISOString().slice(0, 10), fc: lfc, count: 0, fields: [] };
    layerSrc[k] = new ol.source.Vector(); setLayerData(k, lfc); delete DATA[k].original;
    const x = ensureLayer(k, name, "poly"); x.style = ST(style); restyle(x); extra.push(k); };
  layerOf(sk.plots, `Эскиз: участки и дворы (${typ.toLowerCase()})`, g => ({ ...(g["Площадь, сот."] ? { "Площадь, сот.": g["Площадь, сот."] } : {}), ...(g["Блок"] ? { "Блок": g["Блок"] } : {}), ...(g["Причина"] ? { "Причина": g["Причина"] } : {}) }),
    { mode: "cat", width: .8, stroke: "#7a9a5a", opacity: .6, cat: { field: "Вид", colors: { "участок ИЖС": "#dfeccd", "участок блока": "#dfeccd", "двор": "#f3eac6", "свет соседям": "#fbe39a", "хозпостройка": "#d9cdb8" }, off: [] } });
  layerOf(sk.streets, `Эскиз: улицы и проезды (${typ.toLowerCase()})`, g => g["Мест"] ? { "Мест": g["Мест"], "Норма": "945-ПП п. 6.2.3.2: 10 % от 1,6 места на дом" } : {},
    { mode: "cat", fill: "#e4e1da", stroke: "#b7b2a8", width: .8, opacity: .9, cat: { field: "Вид", colors: { "проезд": "#e4e1da", "улица": "#e4e1da", "гостевая стоянка": "#9fb6d9" }, off: [] } });
  // порядок сверху вниз: корпуса, участки и дворы, улицы (новые слои встают наверх — поднимаем в обратном порядке)
  if (extra.length) { [...extra.slice(0, -1).reverse(), key].forEach(k => { const i = LYR.findIndex(x => x.key === k); LYR.unshift(LYR.splice(i, 1)[0]); });
    newGroup([key, ...extra], `Эскиз: ${typ.toLowerCase()}`); applyOrder(); }
  setCurrent(key); dataRev++;
  toast(`Эскиз сохранён слоем «${title}»: ${sk.length} корпусов${sk.plots?.length ? `, участков, дворов и хозпостроек ${sk.plots.length}` : ""}${sk.streets?.length ? `, улиц, проездов и гостевых стоянок ${sk.streets.length}` : ""}. Слои можно править, стилизовать и выгружать; схема на них больше не влияет.`);
}
// предпросмотр графа (Preview в Grasshopper): только пока открыты окна графа/эскиза, выход узла — только при открытом графе
const PREVIEW_WINS = ["wGraph", "wSketch", "wVars", "w3d", "wCmp"];
function syncPreview() {
  const open = id => !$(id).hidden, any = PREVIEW_WINS.some(open);
  RES.forEach(r => r.layer.setVisible(r.on !== false && (r.id === "prev" ? open("wGraph") : any)));
  if (typeof renderTree === "function") renderTree();
}
/* цель плотности по ПЗЗ: средняя предельная плотность подзон внутри границы, взвешенная по площади (0 — новое
   строительство не предусмотрено — тоже в счёт); подзоны без числа («-», «Ф») не участвуют, их доля показывается */
function pzzTarget() {
  const fs = DATA["gisogd.pzz_sub"]?.fc.features; if (!fs?.length || !TERR) return null;
  let a = 0, s = 0; const vals = new Set();
  for (const f of fs) { const v = f.properties["Плотность, тыс. м²/га"]; if (typeof v !== "number") continue; const x = inter(TERR, f); const m = x ? m2(x) : 0; if (m < 1) continue; a += m; s += m * v; vals.add(v); }
  return a ? { value: s / a, share: a / TERR_M2, vals: [...vals].sort((x, y) => x - y) } : { value: null, share: 0, vals: [] };
}
function takePzzTarget(silent) {
  const t = RESULT.tepNode, pz = pzzTarget(); if (!t || !pz?.value && pz?.value !== 0) return false;
  const v = Math.max(5, Math.min(45, Math.round(pz.value))); t.widgets[1].value = v; t.properties.pzzTarget = true;
  if (!silent) toast(`Цель плотности взята по ПЗЗ: ${fmt(pz.value, 1)} тыс. м²/га${v !== Math.round(pz.value) ? ` (ползунок держит ${v}: пределы 5–45)` : ""}; подзоны с числом покрывают ${Math.round(pz.share * 100)} % границы.`);
  window.markDirty?.(); recompute(true); return true;
}
window.takePzzTarget = takePzzTarget;
const GROUP_ORDER = ["Основные показатели", "СПП в ГНС", "Наземная площадь", "Единый показатель", "Баланс территории", "Социальные объекты", "Обслуживание", "Машино-места", "Элементы жилых территорий"];
const MODES = { 1: "преобразование", 2: "реконструкция", 3: "малоэтажный комплекс" };
function renderTep() {
  if (!TERR) { $("tep").innerHTML = `<div class="empty">Показатели появятся, когда будет граница территории: окно «Данные» → «Нарисовать границу» или «Пример».</div>`; return; }
  const t = RESULT.tepNode?._tep; if (!t) { $("tep").innerHTML = `<div class="empty">${TERR ? "Считаю…" : "Нет территории"}</div>`; return; }
  const tp = tepParams(RESULT.tepNode), sel = (k, opts, lab) => `<select data-tp="${k}" aria-label="${lab}">${opts.map(([v, l]) => `<option value="${v}" ${String(tp[k]) === String(v) ? "selected" : ""}>${l}</option>`).join("")}</select>`;
  const dCls = t.density > t.target * 1.05 ? "bad" : t.density < t.target * .8 ? "warn" : "good";
  const byGroup = {}; t.metrics.forEach(m => (byGroup[m.group || "Прочее"] ||= []).push(m));
  const place = `<div class="sect">Территория расчёта</div><div class="pad tepp">
      <div class="row"><label>Район</label><b>${esc(tp.district || "определяется…")}</b>${tp.insideTtk ? `<small>внутри ТТК</small>` : ""}</div>
      <div class="row"><label title="2151-ПП п. 1.3.2: нормы ДОО и школ">Образование</label>${sel("zone", [[1, "зона 1 — 44 / 90"], [2, "зона 2 — 63 / 124"]], "Образовательная зона")}</div>
      <div class="row"><label title="945-ПП прил. 6: пешая доступность входа в метро, МЦК, МЦД">K1</label>${sel("k1", [[0.75, "0,75 · до 1200 м"], [0.9, "0,9 · 1200–2200 м"], [1, "1,0 · дальше"]], "K1")}</div>
      ${tp.walk != null ? `<div class="row" style="margin:-2px 0 4px 140px"><small title="${tp.walkRoute ? "пешеходный маршрут по улицам и дорожкам OSM от центра территории" : "прямое расстояние до ближайшего входа или станции метро, МЦК, МЦД × 1,3 (маршрут по улицам считается)"}">${tp.walkRoute ? "" : "≈ "}${fmt(tp.walk)} м ${tp.walkRoute ? "пешком по улицам" : "до станции"}${tp.station ? ` · ${esc(tp.station)}` : ""}${tp.routing ? " · маршрут по улицам считается (первый раз до 2 минут)…" : ""}</small></div>` : ""}
      <div class="row"><label title="945-ПП прил. 3: деловая активность района">K2</label>${sel("k2", [[0.2, "0,2"], [0.5, "0,5"], [0.7, "0,7"], [0.9, "0,9"]], "K2")}<label class="inl" title="Отметьте, если территория в Троицком или Новомосковском округе: от этого зависит расчёт показателей"><input type="checkbox" data-tp="tinao" ${tp.tinao ? "checked" : ""}> ТиНАО</label></div>
      <div class="row"><label title="2152-ПП табл. 1.4.2">Жилые территории</label>${sel("mode", Object.entries(MODES), "Тип территории")}</div>
      <div class="row"><label title="Доля встроенно-пристроенных нежилых помещений в МКД; по умолчанию 94 / 6">Нежилое в МКД, %</label><input type="number" data-tp="nonres" min="0" max="100" value="${Number(tp.nonres)}" style="width:64px"></div>
      <div class="row"><label title="Незастраиваемая территория в составе жилой (баланс территории)">Незастраиваемая, %</label><input type="number" data-tp="unbuilt" min="0" max="90" value="${Number(tp.unbuilt)}" style="width:64px"></div>
      ${tp.auto ? "" : `<button class="btn" data-tp-auto title="Снова взять зону, K1, K2 и ТиНАО по району территории">по району</button>`}
      ${tp.mode !== 1 || tp.nonres !== 6 || tp.unbuilt !== 25 ? `<button class="btn" data-tp-reset title="Преобразование, нежилое 6 %, незастраиваемая 25 % — как в «Калькуляторе 2.0» по умолчанию">сбросить тип и проценты</button>` : ""}
      ${(() => { const pz = pzzTarget(); if (!pz) return ""; if (pz.value == null) return `<div class="row"><label>Цель по ПЗЗ</label><small>в подзонах внутри границы плотность не установлена числом («-», «Ф»)</small></div>`;
        return `<div class="row"><label title="Средняя предельная плотность подзон ПЗЗ внутри границы, взвешенная по площади">Цель по ПЗЗ</label><b>${fmt(pz.value, 1)}</b><small>тыс. м²/га · ${Math.round(pz.share * 100)} % границы${pz.vals.length > 1 ? ` · подзоны ${pz.vals.map(v => fmt(v, 1)).join(", ")}` : ""}</small>${Math.abs(t.target - pz.value) >= 0.5 ? `<button class="btn" data-tp-pzz title="Поставить цель плотности эскиза по ПЗЗ">взять цель</button>` : ""}</div>`; })()}
      ${(tp.notes || []).map(x => `<div class="note warn">${esc(x)}</div>`).join("")}</div>`;
  $("tep").innerHTML = place + `<div class="sect">Эскиз</div>` + kv([["Новые корпуса", t.n], ["СПП новая", fmt(t.sppNew / 1000, 2) + " тыс. м²"], ["СПП сохраняемая", fmt(t.sppKept / 1000, 2) + " тыс. м²"], ["Плотность итоговая", fmt(t.density, 2) + " тыс. м²/га", dCls], ["Цель", fmt(t.target) + " тыс. м²/га"], ["Застроенность", fmt(t.cover * 100, 1) + " %"], ["Сохраняется", t.kept.length + " зд."], ["Под снос", t.demolN + " зд. · " + fmt(t.demolSpp / 1000, 2) + " тыс. м²"]])
    + Object.entries(byGroup).sort((a, b) => (GROUP_ORDER.indexOf(a[0]) + 99) % 99 - (GROUP_ORDER.indexOf(b[0]) + 99) % 99).map(([g, ms]) => `<div class="sect">${esc(g)}</div>` + kv(ms.map(m => [m.title, fmt(m.value, m.precision ?? 3) + " " + esc(m.unit)]))).join("")
    + `<div class="note">Методика «Калькулятора 2.0» (Москва): 2151-ПП, 2150-ПП, 2152-ПП, 1557-ПП, 945-ПП — тексты и выписки в docs/standards/moscow-ngp. Население, соцобъекты и машино-места — от новой застройки; люди, места и машино-места округлены вверх, площади — математически (СПП — 2 знака, остальное — 3). K1 — по пешеходному маршруту по улицам OSM от центра территории до ближайшего входа или станции (пока маршрут считается — прямое расстояние × 1,3). ${t.existKey === "osm.buildings" ? "Существующие здания взяты из OSM: ЕГРН не загружен. " : ""}</div>`;
}
$("tep").addEventListener("change", e => {
  const k = e.target.dataset.tp; if (!k || !RESULT.tepNode) return; const tp = tepParams(RESULT.tepNode);
  tp[k] = e.target.type === "checkbox" ? (e.target.checked ? 1 : 0) : +e.target.value;
  if (["zone", "k1", "k2", "tinao"].includes(k)) tp.auto = false;
  window.markDirty?.(); recompute(true);
});
$("tep").addEventListener("click", e => {
  if (!RESULT.tepNode) return; const tp = tepParams(RESULT.tepNode);
  if (e.target.closest("[data-tp-auto]")) { tp.auto = true; tp.rev = -1; recompute(true); }
  if (e.target.closest("[data-tp-pzz]")) takePzzTarget();
  if (e.target.closest("[data-tp-reset]")) { Object.assign(tp, { mode: 1, nonres: 6, unbuilt: 25 }); window.markDirty?.(); recompute(true); }
});
function renderSketch() {
  renderTep();
  keptSrc.clear(); (RESULT.tepNode?._tep?.kept || []).forEach(f => keptSrc.addFeature(toOl(f)));
  if (!$("w3d").hidden) draw3d();
}
$("bRot").onclick = () => { rot3d = (rot3d + 1) % 4; draw3d(); };
$("sunDay").onchange = $("sunTime").oninput = () => draw3d();
/* аксонометрия: стены, крыши, порядок по глубине; дороги — земля */
function draw3d() {
  const cv = $("c3d"), r = cv.getBoundingClientRect(), dpr = devicePixelRatio || 1;
  const tm = +$("sunTime").value; $("sunInfo").textContent = `${String(Math.floor(tm)).padStart(2, "0")}:${String(Math.round(tm % 1 * 60)).padStart(2, "0")}`;
  $("e3d").hidden = !!TERR; if (!r.width || !TERR) { cv.getContext("2d").clearRect(0, 0, cv.width, cv.height); return; }
  cv.width = r.width * dpr; cv.height = r.height * dpr; const x = cv.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, r.width, r.height);
  const terr = ringsXY(TERR)[0], A = rot3d * Math.PI / 2, C = Math.cos(Math.PI / 6), Sn = Math.sin(Math.PI / 6), R = p => rot(p, A, [0, 0]);
  // новые — эскиз графа и принятые слои эскизов (видимые), серые — сохраняемые здания
  const baked = LYR.filter(l => shown(l) && /^эскиз/.test(DATA[l.key]?.source || "")).flatMap(l => DATA[l.key].fc.features.filter(f => f.properties["Этажность"] != null).map(f => ({ f, floors: +f.properties["Этажность"] || 1 })));
  const fh = typeof CONS !== "undefined" ? CONS.floorH : 3;
  const cKey = b => turf.centroid(b.f).geometry.coordinates.map(v => v.toFixed(6)).join(","), bakedAt = new Set(baked.map(cKey));
  const preview = RESULT.sketch.filter(b => !bakedAt.has(cKey(b)));          // принятый эскиз не рисуется второй раз из предпросмотра
  const items = [...preview.concat(baked).flatMap(b => ringsXY(b.f).map(ring => ({ ring, h: b.floors * fh, c: [222, 232, 246], e: [42, 90, 170] }))),
    ...(RESULT.tepNode?._tep?.kept || []).flatMap(f => ringsXY(f).map(ring => ({ ring, h: floorsOf(f) * fh, c: [214, 210, 202], e: [90, 90, 90] })))];
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
  // тени на земле для выбранной даты и времени (солнечное время): тень призмы — оболочка основания и его сдвига от солнца
  const sun = INSOL.sunAt(turf.centroid(TERR).geometry.coordinates[1], INSOL.declination(+$("sunDay").value), +$("sunTime").value);
  if (sun.alt > 0) {
    x.fillStyle = "rgba(40,40,60,.22)";
    // тень призмы = основание + по четырёхугольнику на каждое ребро (не выпуклая оболочка: двор и выемки не заливаются целиком);
    // все части одного обхода и одной заливкой по правилу nonzero — наложения не темнеют дважды
    const sa = q => q.reduce((acc, p, i) => { const n = q[(i + 1) % q.length]; return acc + p[0] * n[1] - n[0] * p[1]; }, 0);
    const add = q => { q = q.map(p => T(p)); if (sa(q) < 0) q.reverse(); q.forEach((p, i) => i ? x.lineTo(...p) : x.moveTo(...p)); x.closePath(); };
    x.beginPath();
    items.forEach(it => { const d = it.h / sun.tan, sh = p => [p[0] - sun.vx * d, p[1] - sun.vy * d]; add(it.ring);
      it.ring.forEach((a, i) => { const b = it.ring[(i + 1) % it.ring.length]; add([a, b, sh(b), sh(a)]); }); });
    x.fill("nonzero");
  }
  $("sunInfo").textContent = `${String(Math.floor(+$("sunTime").value)).padStart(2, "0")}:${String(Math.round(+$("sunTime").value % 1 * 60)).padStart(2, "0")} · солнце ${sun.alt > 0 ? Math.round(sun.alt * 180 / Math.PI) + "°" : "за горизонтом"}`;
  items.forEach(i => { i.d = R(centroid(i.ring)).reduce((a, b) => a + b, 0); }); items.sort((a, b) => b.d - a.d);
  for (const it of items) {
    let ring = it.ring; if (ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1]) ring = ring.slice(0, -1);
    const sa = ring.reduce((s, p, j) => { const q = ring[(j + 1) % ring.length]; return s + p[0] * q[1] - q[0] * p[1]; }, 0); if (sa < 0) ring = ring.slice().reverse();
    for (let j = 0; j < ring.length; j++) { const a = ring[j], b = ring[(j + 1) % ring.length], ra = R(a), rb = R(b), nx = rb[1] - ra[1], ny = -(rb[0] - ra[0]);
      if (nx + ny < 0) { const lum = nx < ny ? .8 : .66; poly([T(a), T(b), T(b, it.h), T(a, it.h)], `rgb(${it.c.map(v => Math.round(v * lum)).join(",")})`, `rgba(${it.e.join(",")},.6)`); } }
    poly(ring.map(p => T(p, it.h)), `rgb(${it.c.join(",")})`, `rgb(${it.e.join(",")})`);
  }
  x.fillStyle = "#555"; x.font = "11px system-ui, sans-serif"; x.fillText(`Объём: этаж ${fh} м. Серым — сохраняемые здания, тени — на земле, время солнечное.`, 10, r.height - 10);
}
new ResizeObserver(() => { if (!$("w3d").hidden) draw3d(); }).observe($("c3d").parentElement);

/* ---------- варианты ---------- */
let VARS = [], varSel = -1;
/* Перебор вариантов (как «варианты» в TestFit/Forma, но внутри ограничений): типология × ширина корпуса × поворот
   (вдоль и поперёк длинной стороны участков), этажность — под цель плотности узла ТЭП, не выше предельной высоты.
   Оценка: отклонение плотности от цели и доля фасадов новых домов с нормой инсоляции. Все кандидаты — в таблице,
   шесть лучших — карточками; выбранный переносит параметры в граф, «Сохранить слоем» делает его слоем. */
let varRun = null;                 // идущий подбор: {stop}
const varProgress = (done, total, text) => { $("varProg").firstElementChild.style.width = (done / total * 100).toFixed(1) + "%"; $("varMsg").textContent = text; setHint(text); };
$("bStopVar").onclick = () => { if (varRun) { varRun.stop = true; $("bStopVar").disabled = true; $("varMsg").textContent = "Останавливаю: дорабатывает текущий вариант…"; } };
$("bGen").onclick = async () => {
  const p = RESULT.placeNode, t = RESULT.tepNode; if (!p || !RESULT.site) return toast("В схеме расчёта нет пятна застройки или блока посадки: задайте территорию и загрузите данные.");
  if (!t) return toast("В схеме расчёта нет блока «ТЭП КРТ»: варианты сравниваются по его целевой плотности. Добавьте его из группы «Показатели» и соедините с посадкой.");
  const base = placeParams(p), share = t.widgets[0].value / 100, target = t.widgets[1].value, kept = t.getInputData(1), lim = t.getInputData(2), goal = densityGoal();
  const sppKept = keptBuildings(kept).reduce((s, f) => s + m2(f) * floorsOf(f), 0), ha = TERR_M2 / 1e4;
  // малоэтажные типологии (ИЖС, блокированные) — только при цели до 10 тыс. м²/га: плотнее они не бывают
  const widthsOf = typ => typ === "ИЖС" ? [base.width] : typ === "Блокированные" ? [12, 14] : typ === "Квартал" ? [14, 18] : typ === "Урбан-блоки" ? [16] : [14, 17];
  const cands = []; for (const typ of TYPOLOGIES) { if (LOWRISE.has(typ) && target > 10) continue;
    for (const width of widthsOf(typ)) for (const angle of [0, 90]) for (const block of typ === "Урбан-блоки" ? [80, 110] : [base.block]) cands.push({ typ, width, angle, block }); }
  const NINS = 8, total = cands.length + NINS + 1, run = varRun = { stop: false }, epoch = window.PROJ_EPOCH, tick = () => new Promise(r => setTimeout(r, 0));
  busy(true); $("bGen").hidden = true; $("bStopVar").hidden = false; $("bStopVar").disabled = false; $("varProg").hidden = false; $("bBakeVar").disabled = true; VARS = [];
  $("vlist").innerHTML = `<div class="empty">Подбор идёт: сначала посадка всех ${cands.length} вариантов, потом инсоляция лучших ${NINS}. «Стоп» оставит уже посчитанное.</div>`;
  try {
    for (const [i, c] of cands.entries()) {
      if (run.stop) break;
      varProgress(i, total, `Посадка: вариант ${i + 1} из ${cands.length} — ${c.typ}, ${c.width} м, ${c.angle ? "поперёк" : "вдоль"}…`); await tick();
      const sk = generate(RESULT.site, { ...base, ...c, goal }); if (!sk.length) continue;
      const spp = sk.reduce((s, b) => s + b.m2 * b.floors, 0), fp = sk.reduce((s, b) => s + b.m2, 0);
      VARS.push({ ...c, sk, n: sk.length, spp, density: (spp + sppKept) / 1000 / ha, cover: fp / TERR_M2, avg: spp / fp, capped: sk.filter(b => b.capped).length });
    }
    VARS.forEach(v => { v.err = Math.abs(v.density - target) / target; });
    VARS.sort((a, b) => a.err - b.err);
    const ins = VARS.slice(0, NINS);
    for (const [i, v] of ins.entries()) {
      if (run.stop) break;
      varProgress(cands.length + i, total, `Инсоляция новых домов: вариант ${i + 1} из ${ins.length}…`); await tick(); v.own = window.ownInsolation?.(v.sk) ?? null;
    }
    VARS.forEach(v => { v.score = v.err + (v.own == null ? .3 : (100 - v.own) / 100 * .5); });   // недобор инсоляции весит как половина отклонения плотности
    VARS.sort((a, b) => a.score - b.score);
    varProgress(total - 1, total, "Показатели лучших вариантов…");
    await Promise.all(VARS.slice(0, 6).map(async v => { v.tep = await tepRequest(v.sk, kept, lim, share, target, tepParams(t)); }));
    if (epoch !== window.PROJ_EPOCH) { VARS = []; return toast("Подбор вариантов для прежнего проекта отброшен."); }
    varSel = -1; renderVars();
    if (!VARS.length) $("vlist").innerHTML = `<div class="empty">${run.stop ? "Подбор остановлен до первого варианта." : "Ни один вариант не поместился в пятно застройки: проверьте ограничения и цель плотности."}</div>`;
    const msg = run.stop ? `Подбор остановлен: вариантов ${VARS.length} из ${cands.length}${VARS.some(v => v.own == null) ? ", у части инсоляция не посчитана (—)" : ""}.` : `Вариантов: ${VARS.length}.`;
    $("varMsg").textContent = msg; setHint(msg + " Щелчок по карточке или строке таблицы переносит параметры в схему и на карту.");
  } catch (e) { console.error(e); toast("Варианты не посчитались: " + e.message); $("varMsg").textContent = "Подбор не удался: " + e.message; }
  finally { varRun = null; busy(false); $("bGen").hidden = false; $("bStopVar").hidden = true; $("varProg").hidden = true; $("bBakeVar").disabled = false; }
};
const vName = v => `${v.typ}${v.typ === "ИЖС" ? "" : v.typ === "Урбан-блоки" ? ` · квартал ${v.block} м` : ` · ${v.width} м`} · ${v.angle ? "поперёк" : "вдоль"}`;
function renderVars() {
  if (!VARS.length || !TERR) return;
  const tb = bboxOf(ringsXY(TERR)[0]), pad = 10, vb = `${tb[0] - pad} ${-tb[3] - pad} ${tb[2] - tb[0] + 2 * pad} ${tb[3] - tb[1] + 2 * pad}`;
  const pts = r => r.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" "), target = RESULT.tepNode?.widgets[1].value || 25;
  const dcls = d => d > target * 1.05 ? "bad" : d < target * .8 ? "warn" : "good", sw = Math.max(1, (tb[2] - tb[0]) / 180);
  const kept = keptBuildings(RESULT.tepNode?.getInputData(1)).flatMap(f => ringsXY(f));
  const cards = VARS.slice(0, 6).map((v, i) => `<button class="vc" data-var="${i}" aria-pressed="${i === varSel}"><svg viewBox="${vb}" preserveAspectRatio="xMidYMid meet"><g transform="scale(1,-1)"><polygon points="${pts(ringsXY(TERR)[0])}" fill="#fff" stroke="#b3261e" stroke-width="${sw * 2}" stroke-dasharray="${sw * 8} ${sw * 4}"/>${kept.map(r => `<polygon points="${pts(r)}" fill="#bdb8b0"/>`).join("")}${v.sk.flatMap(b => ringsXY(b.f)).map(r => `<polygon points="${pts(r)}" fill="#6fa6e6" stroke="#1a4f94" stroke-width="${sw}"/>`).join("")}</g></svg>
      <div class="vt">${i + 1}. ${esc(vName(v))}</div><div class="vm"><span>плотность</span><b style="color:var(--${dcls(v.density)})">${fmt(v.density, 1)}</b><span>ср. эт.</span><b>${fmt(v.avg, 1)}</b><span>инсоляция</span><b>${v.own == null ? "—" : v.own + " %"}</b><span>население</span><b>${v.tep ? fmt(v.tep.m.population) : "—"}</b></div></button>`).join("");
  const table = `<table class="at vt-table"><thead><tr><th>№</th><th>Вариант</th><th>Корпусов</th><th>Ср. эт.</th><th>СПП новая, тыс. м²</th><th>Плотность (цель ${fmt(target)})</th><th>Застроенность</th><th>Ниже предельной высоты</th><th title="Доля фасадов новых домов (без северных), получающих норму 22 апреля, предварительно">Инсоляция новых</th></tr></thead><tbody>${VARS.map((v, i) =>
    `<tr data-var="${i}" class="${i === varSel ? "sel" : ""}"><td class="num">${i + 1}</td><td>${esc(vName(v))}</td><td class="num">${v.n}</td><td class="num">${fmt(v.avg, 1)}</td><td class="num">${fmt(v.spp / 1000, 1)}</td><td class="num" style="color:var(--${dcls(v.density)})">${fmt(v.density, 1)}</td><td class="num">${fmt(v.cover * 100, 1)} %</td><td class="num">${v.capped || ""}</td><td class="num">${v.own == null ? "—" : v.own + " %"}</td></tr>`).join("")}</tbody></table>`;
  $("vlist").innerHTML = `<div class="vcards">${cards}</div><div class="note">Все варианты по оценке — лучшие сверху. Этажность подобрана под цель плотности и не выше предельной высоты ограничений. Инсоляция новых — предварительная оценка по 22 апреля (подробно — «Проверить нормы» в окне «Эскиз»).</div>${table}`;
}
$("bBakeVar").onclick = () => varSel < 0 ? toast("Выберите вариант в списке — щелчок по карточке.") : bakeSketch();
$("vlist").addEventListener("click", e => { const b = e.target.closest("[data-var]"); if (!b) return; varSel = +b.dataset.var; const v = VARS[varSel], p = RESULT.placeNode;
  const setWv = (name, val) => { const w = p.widgets.find(w => w.name === name); if (w) w.value = val; };
  setWv("типология", v.typ); setWv("ширина корпуса, м", v.width); setWv("поворот, °", v.angle); if (v.block) setWv("квартал, м", v.block); setWv("этажность по", FLOOR_MODES[1]);
  p.properties.run = true; p._ck = null; syncPreview(); recompute(true); renderParams(); renderVars(); toast(`Вариант «${vName(v)}» перенесён в схему: на карте эскиз этого варианта.`); });

/* ================= плавающие окна и панели ================= */
// окно = section.win: перетаскивание за шапку, размер — за угол, положение запоминается
const WINKEY = "grado2.win";
let WST = {}; try { WST = JSON.parse(localStorage.getItem(WINKEY)) || {}; } catch { }
const saveWins = () => { try { localStorage.setItem(WINKEY, JSON.stringify(WST)); } catch { } };
// начальные места окон — внутри поля карты, а не поверх боковых панелей
const W0 = () => { const w = innerWidth, h = innerHeight, m = $("mMain").getBoundingClientRect(), L = Math.round(m.left) + 12, R = Math.round(m.right) - 12, mw = Math.max(360, R - L); return {
  wData: [L, 96, 340, Math.min(560, h - 150)], wGraph: [L, Math.round(h * .38), Math.max(560, mw), Math.round(h * .56)], wSketch: [R - 320, 96, 320, 470],
  wVars: [L, h - 300, Math.min(1180, mw), 260], wTep: [R - 330, 96, 330, Math.min(620, h - 150)], w3d: [L + 40, 110, Math.min(620, mw), 440],
  wCmp: [L + 20, 100, Math.min(1000, mw), 520], wTable: [L, h - 330, Math.max(560, mw), 280], wProjects: [Math.round(w / 2 - 290), 90, 580, Math.min(480, h - 150)],
  wKeys: [Math.round(w / 2 - 290), 80, 580, Math.min(680, h - 140)], wCons: [R - 690, 96, 340, Math.min(700, h - 150)], wViews: [L + 350, 96, 380, Math.min(560, h - 150)], wSheets: [L, Math.max(120, h - 400), Math.min(820, mw), Math.min(370, h - 160)],
  // совместный режим (hub.js): по центру — проекты, доступ, пользователи; справа у карты — комментарии и история
  wHubProjects: [Math.round(w / 2 - 390), 90, 780, Math.min(520, h - 150)], wShare: [Math.round(w / 2 - 250), 90, 500, Math.min(440, h - 150)], wHubAdmin: [Math.round(w / 2 - 330), 90, 660, Math.min(560, h - 150)], wTeams: [Math.round(w / 2 - 320), 90, 640, Math.min(560, h - 150)],
  wComments: [R - 380, 104, 380, Math.min(580, h - 150)], wHistory: [R - 560, 104, 560, Math.min(540, h - 150)] }; };
// рабочее поле карты: края боковых панелей, к которым прилипают окна
const mapBox = () => $("mMain").parentElement.getBoundingClientRect();
function placeWin(w) {
  const d = WST[w.id] || {}, [l, t, ww, hh] = W0()[w.id];
  // окно не заходит на шапку и ленту: на узком экране лента в две строки, верх рабочего поля ниже
  const top = Math.round(mapBox().top) + 4, W = Math.min(d.w || ww, innerWidth - 20), H = Math.min(d.h || hh, innerHeight - top - 30);
  Object.assign(w.style, { width: W + "px", height: H + "px", left: Math.max(4, Math.min(d.l ?? l, innerWidth - W - 4)) + "px", top: Math.max(top, Math.min(d.t ?? t, innerHeight - H - 26)) + "px" });
}
const SNAP = 12;
function snapMove(w, x, y) {           // магнит плавающего окна к краям карты, строке состояния и другим окнам
  const m = mapBox(), W = w.offsetWidth, H = w.offsetHeight, xs = [m.left, m.right, 0, innerWidth], ys = [m.top, m.bottom, innerHeight];
  document.querySelectorAll(".win:not([hidden]):not(.docked)").forEach(o => { if (o === w) return; const r = o.getBoundingClientRect(); xs.push(r.left, r.right); ys.push(r.top, r.bottom); });
  let sx = null, sy = null, best = SNAP;
  for (const t of xs) for (const e of [0, W]) { const d = Math.abs(x + e - t); if (d < best) { best = d; sx = t - e; } }
  best = SNAP; for (const t of ys) for (const e of [0, H]) { const d = Math.abs(y + e - t); if (d < best) { best = d; sy = t - e; } }
  return { x: sx ?? x, y: sy ?? y, snapped: sx !== null || sy !== null };
}

/* Встраивание окон в рабочее поле (как панели QGIS и палитры AutoCAD): окно, брошенное на панель слоёв, на панель
   свойств или к нижнему краю карты, становится частью раскладки — карта ужимается, окна в одной зоне делят место;
   вытянутое за заголовок — снова плавает. Двойной щелчок по заголовку — встроить / сделать плавающим. */
const DZ = { l: $("dzL"), r: $("dzR"), b: $("dzB") };
const DOCK_DEFAULT = { wTable: "b", wVars: "b", wSheets: "b", wGraph: "b", wSketch: "r", wTep: "r", wCons: "r", wData: "l", wViews: "l" };
const narrow = () => innerWidth <= 1000;       // боковые панели — выезжающие поверх карты: окна боковых зон встают вкладками под карту
const dockPref = id => { const d = WST[id]; return d && "dock" in d ? d.dock : d?.anchor || DOCK_DEFAULT[id] || null; };   // anchor — прилипание прежних версий
const dockOf = id => { const z = dockPref(id); return z && z !== "b" && narrow() ? "b" : z; };
const layoutChanged = () => requestAnimationFrame(() => { syncZones(); mMain.updateSize(); window.CAD?.grips?.(); });
/* несколько окон в одной зоне — вкладки (как сгруппированные панели QGIS): боковая панель всегда, нижняя — когда окнам
   не хватает ширины (меньше 340 px на окно). Вкладку можно вытянуть мышью — окно поплывёт. */
function syncZones() {
  for (const [k, z] of Object.entries(DZ)) {
    const ws = [...z.querySelectorAll(":scope>.win")].filter(w => !w.hidden);
    const width = k === "b" ? z.parentElement.clientWidth : 0, tabbed = ws.length > 1 && (k !== "b" || ws.length * 340 > width);
    let act = z.dataset.active; if (!ws.some(w => w.id === act)) act = ws[ws.length - 1]?.id || "";
    z.dataset.active = act; z.classList.toggle("tabbed", tabbed);
    ws.forEach(w => w.classList.toggle("dzoff", tabbed && w.id !== act));
    // нижняя зона без вкладок: окна рядом, ширины — перетаскиваемой границей между ними (WST[id].bw — доля)
    ws.forEach((w, i) => { w.classList.toggle("nfirst", k === "b" && !tabbed && i > 0); w.style.flexGrow = k === "b" && !tabbed ? (WST[w.id]?.bw || 1) : ""; });
    if (k !== "b" && WST["zh" + k]) z.style.setProperty("--dzh", WST["zh" + k] + "px");
    let bar = z.querySelector(":scope>.dztabs");
    if (!bar) { bar = document.createElement("div"); bar.className = "dztabs"; bar.setAttribute("role", "tablist"); z.insertBefore(bar, z.querySelector(":scope>.win")); bindTabs(bar); }
    bar.hidden = !tabbed;
    // вкладкам тесно — у неактивных остаются значок и крестик, подпись — в подсказке
    bar.classList.toggle("many", tabbed && ws.length * 120 > (k === "b" ? width : z.clientWidth || z.parentElement.clientWidth));
    if (tabbed) bar.innerHTML = ws.map(w => `<button role="tab" data-tab="${w.id}" aria-selected="${w.id === act}" title="${esc(w.getAttribute("aria-label"))}. Потяните вкладку, чтобы окно поплыло">${w.querySelector(".wh>svg, .wh>i")?.outerHTML || ""}<span>${esc(document.querySelector(`.wins [data-win="${w.id}"] .lb`)?.textContent || w.querySelector(".wh b")?.textContent || "")}</span><i class="x" data-tabclose="${w.id}" title="Закрыть">×</i></button>`).join("");
  }
}
function bindTabs(bar) {
  bar.addEventListener("pointerdown", e => {
    const t = e.target.closest("[data-tab]"); if (!t || e.button) return;
    if (e.target.closest("[data-tabclose]")) { winOpen(t.dataset.tab, false); return; }
    const w = $(t.dataset.tab); dragWin(w, e, () => { w.parentElement.dataset.active = w.id; syncZones(); requestAnimationFrame(() => WIN_OPEN[w.id]?.()); });
  });
}
function dockWin(w, side, keepPref) {
  const d = WST[w.id] ||= {}; if (!keepPref) d.dock = side; delete d.anchor; delete d.full;
  w.classList.add("docked"); w.classList.remove("front", "snap"); w.style.cssText = "";
  if (side !== "b") w.style.flexBasis = (d.dh || 300) + "px";
  if (w.parentElement !== DZ[side]) DZ[side].append(w);
  DZ[side].dataset.active = w.id;
  if (side === "l" && $("work").classList.contains("noL")) toggleDock("L", true);
  if (side === "r" && $("work").classList.contains("noR")) toggleDock("R", true);
  saveWins(); layoutChanged();
}
function floatWin(w, keepPref) {
  const d = WST[w.id] ||= {}; if (!keepPref) d.dock = null; w.classList.remove("docked", "dzoff"); w.style.flexBasis = "";
  document.body.append(w); saveWins(); layoutChanged();
}
// куда встанет окно, если отпустить его здесь: над панелью слоёв или у левого края карты — влево, и т. д.
function dropZone(x, y) {
  const m = mapBox(), inR = r => r.width && x >= r.left && x <= r.right && y >= r.top && y <= r.bottom, E = 36;
  const sl = document.querySelector(".work>.side:not(.r)").getBoundingClientRect(), sr = document.querySelector(".work>.side.r").getBoundingClientRect(), bb = DZ.b.getBoundingClientRect();
  if (!narrow() && (inR(sl) || (x >= m.left && x < m.left + E && y > m.top && y < m.bottom))) return "l";
  if (!narrow() && (inR(sr) || (x <= m.right && x > m.right - E && y > m.top && y < m.bottom))) return "r";
  if (inR(bb) || (y <= m.bottom && y > m.bottom - E && x > m.left && x < m.right)) return "b";
  return null;
}
function showDrop(z) {
  const el = $("dropInd"); el.hidden = !z; if (!z) return;
  const m = mapBox(), side = z === "l" ? document.querySelector(".work>.side:not(.r)") : document.querySelector(".work>.side.r");
  let r;
  if (z === "b") { const bb = DZ.b.getBoundingClientRect(), h = bb.height || Math.min(280, m.height * .4); r = { left: m.left, top: (bb.height ? bb.top : m.bottom - h), width: m.width, height: h }; }
  else { const sb = side.getBoundingClientRect(), w = sb.width || 290, left = sb.width ? sb.left : z === "l" ? m.left : m.right - w, top = m.top + m.height * .45; r = { left, top, width: w, height: m.bottom - top + (DZ.b.getBoundingClientRect().height || 0) }; }
  Object.assign(el.style, { left: r.left + "px", top: r.top + "px", width: r.width + "px", height: r.height + "px" });
  el.dataset.z = z;
}
// перетаскивание окна за заголовок или вкладку: встроенное вытягивается, плавающее двигается, у края зоны — встраивается;
// без движения (щелчок) — onTap
function dragWin(w, e, onTap) {
  const x0 = e.clientX, y0 = e.clientY, r = w.getBoundingClientRect(); let dx = x0 - r.left, dy = y0 - r.top, moving = !w.classList.contains("docked"), z = null, s = null, moved = false;
  // слушаем окно браузера, а не заголовок: перенос окна в другую зону страницы снимает захват указателя
  const pid = e.pointerId;
  const mv = ev => {
    if (ev.pointerId !== pid) return;
    if (!moved && Math.hypot(ev.clientX - x0, ev.clientY - y0) < 6) return;
    moved = true;
    if (!moving) {             // встроенное окно плывёт под указателем своим плавающим размером
      const d = WST[w.id] ||= {}, [, , ww, hh] = W0()[w.id], W = Math.min(d.w || ww, innerWidth - 20), H = Math.min(d.h || hh, innerHeight - 80);
      floatWin(w); Object.assign(w.style, { width: W + "px", height: H + "px" }); dx = Math.min(dx, W - 60); dy = Math.min(dy, 24); moving = true; winFront(w);
    }
    // заголовок окна всегда виден: не выше ленты и не ниже строки состояния
    const top0 = document.querySelector(".ribbon")?.getBoundingClientRect().bottom ?? 40, bot0 = (document.querySelector(".status")?.getBoundingClientRect().top ?? innerHeight) - 30;
    s = snapMove(w, Math.max(-w.offsetWidth + 80, Math.min(ev.clientX - dx, innerWidth - 80)), Math.max(top0, Math.min(ev.clientY - dy, bot0)));
    w.style.left = s.x + "px"; w.style.top = s.y + "px"; z = dropZone(ev.clientX, ev.clientY); showDrop(z); w.classList.toggle("snap", !z && s.snapped); w.classList.toggle("todock", !!z);
  };
  const up = ev => {
    if (ev.pointerId !== pid) return;
    removeEventListener("pointermove", mv); removeEventListener("pointerup", up); removeEventListener("pointercancel", up); showDrop(null); w.classList.remove("snap", "todock");
    if (!moved) { onTap?.(); return; }
    if (z) { dockWin(w, z); requestAnimationFrame(() => WIN_OPEN[w.id]?.()); return; }
    const d = WST[w.id] ||= {}; Object.assign(d, { l: parseInt(w.style.left), t: parseInt(w.style.top), dock: null }); saveWins();
  };
  addEventListener("pointermove", mv); addEventListener("pointerup", up); addEventListener("pointercancel", up); e.preventDefault();
}
function winFront(w) { document.querySelectorAll(".win.front").forEach(x => x.classList.remove("front")); w.classList.add("front"); }
const WIN_OPEN = {
  // при первом открытии граф вписывается читаемо (не мельче 0,8); «Вся схема» ужимает до 0,6
  wGraph: () => { sizeGraph(); const k = $("graphbox").clientWidth + "x" + $("graphbox").clientHeight; if (go.fitted !== k) { fitGraph(.8); go.fitted = k; } updateAnalysisMap(); },
  wSketch: () => renderParams(), wTep: () => renderTep(), w3d: () => draw3d(),
  wCmp: () => { syncCmpHint(); if (!mBefore) { mBefore = newMap("mBefore", [terrLayer()]); mAfter = newMap("mAfter", [keptLayer(), sketchLayer(), terrLayer()]); } },
  wTable: () => window.renderTable?.(), wData: () => renderSources(), wCons: () => window.renderCons?.(), wViews: () => window.renderViews?.(), wSheets: () => window.renderSheets?.() };
const go = {};
// лёгкое появление плавающего окна (прозрачность и масштаб, без смены размеров — раскладка не дёргается); не при
// восстановлении окон на старте и не при «уменьшении движения» в системе
let WIN_ANIM = false;
const winAppear = w => { if (!WIN_ANIM || !w.animate || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  w.animate([{ opacity: 0, transform: "scale(.98)" }, { opacity: 1, transform: "none" }], { duration: 150, easing: "cubic-bezier(0.23,1,0.32,1)" }); };
function winOpen(id, on) {
  const w = $(id); const was = w.hidden; on = on ?? w.hidden; w.hidden = !on;
  if (on) { const z = dockOf(id); if (z) dockWin(w, z, z !== dockPref(id)); else { if (w.classList.contains("docked")) floatWin(w); placeWin(w); winFront(w); if (was) winAppear(w); } requestAnimationFrame(() => WIN_OPEN[id]?.()); }
  if (w.classList.contains("docked")) layoutChanged();
  if (on && w.classList.contains("docked")) { w.parentElement.dataset.active = id; syncZones(); }
  if (id === "wGraph") $("pv").hidden = !on;
  if (PREVIEW_WINS.includes(id)) syncPreview();
  (WST[id] ||= {}).open = on; saveWins(); syncWinButtons();
}
function syncWinButtons() {
  document.querySelectorAll("[data-win]").forEach(b => { const id = b.dataset.win, on = id === "dockL" ? !$("work").classList.contains("noL") : id === "dockR" ? !$("work").classList.contains("noR") : !$(id).hidden;
    b.setAttribute(b.getAttribute("role") === "menuitemcheckbox" ? "aria-checked" : "aria-pressed", on); });
}
// меню «Окна ▾»: те же кнопки с подписями (видно ниже 1480 px, где значки без слов непонятны)
// ниже 1080 px в меню уходят и основные окна: значки без подписей непонятны
const WINITEMS = [...document.querySelectorAll(".wins .btn[data-win]")].map(b => `<button role="menuitemcheckbox" class="${b.classList.contains("opt") ? "" : "core"}" data-win="${b.dataset.win}" title="${esc(b.title)}">${b.querySelector("i, svg").outerHTML}${esc(b.querySelector(".lb").textContent)}</button>`).join("");
/* Раскладки окон под задачу (как рабочие пространства AutoCAD и профили панелей QGIS): какие окна открыты и где встроены.
   Готовые — под основные этапы; «Запомнить текущую» добавляет свою. Значение окна: "l" / "r" / "b" — зона, null — плавает. */
const LAYOUTS = {
  "Существующее положение": { wData: "l", wTable: "b" },
  "Ограничения и анализ": { wCons: "r", wGraph: "b", wTep: "r" },
  "Эскиз и варианты": { wSketch: "r", wTep: "r", wVars: "b" },
  "Листы и альбом": { wViews: "l", wSheets: "b" },
};
const userLayouts = () => WST.layouts ||= {};
function applyLayout(L) {
  // своя раскладка помнит и размеры окон в зонах: высоту в боковой, долю ширины внизу, высоту нижней зоны и вкладок
  const sz = L._sz;
  if (sz) { Object.entries(sz.w || {}).forEach(([id, v]) => Object.assign(WST[id] ||= {}, v)); ["hb", "zhl", "zhr"].forEach(k => { if (sz[k]) WST[k] = sz[k]; }); }
  Object.keys(W0()).forEach(id => { if (!(id in L) && !$(id).hidden) winOpen(id, false); });
  Object.entries(L).forEach(([id, z]) => { if (!$(id)) return; (WST[id] ||= {}).dock = z; if (!$(id).hidden) winOpen(id, false); winOpen(id, true); });
  saveWins(); layoutChanged();
}
function saveLayout() {
  const L = {}; Object.keys(W0()).forEach(id => { if (!$(id).hidden) L[id] = $(id).classList.contains("docked") ? dockPref(id) : null; });
  if (!Object.keys(L).length) return toast("Откройте нужные окна и расставьте их — тогда раскладку можно запомнить.");
  L._sz = { w: Object.fromEntries(Object.keys(L).map(id => [id, { dh: WST[id]?.dh, bw: WST[id]?.bw }])), hb: WST.hb, zhl: WST.zhl, zhr: WST.zhr };
  const U = userLayouts(); let n = 1; while (U["Моя раскладка " + n]) n++; U["Моя раскладка " + n] = L; saveWins(); toast(`Запомнено как «Моя раскладка ${n}» — она в меню «Окна», раздел «Раскладка окон».`);
}
function renderWinMenu() {
  const lay = (name, user) => `<button role="menuitem" class="lay" data-layout="${esc(name)}" data-user="${user ? 1 : ""}" title="Открыть окна этой раскладки и расставить их"><i data-lucide="layout-dashboard"></i>${esc(name)}${user ? `<i class="x" data-laydel="${esc(name)}" title="Удалить раскладку">×</i>` : ""}</button>`;
  $("winMenu").innerHTML = WINITEMS + `<div class="mh">Раскладка окон</div>` + Object.keys(LAYOUTS).map(n => lay(n)).join("") + Object.keys(userLayouts()).map(n => lay(n, true)).join("")
    + `<button role="menuitem" class="lay" data-laysave title="Запомнить, какие окна открыты и где встроены"><i data-lucide="bookmark-plus"></i>Запомнить текущую…</button>`;
  icons();
}
renderWinMenu();
$("winMenu").addEventListener("click", e => {
  const del = e.target.closest("[data-laydel]"); if (del) { e.stopImmediatePropagation(); delete userLayouts()[del.dataset.laydel]; saveWins(); renderWinMenu(); return; }
  const b = e.target.closest("[data-layout]"); if (b) { applyLayout(b.dataset.user ? userLayouts()[b.dataset.layout] : LAYOUTS[b.dataset.layout]); return; }
  if (e.target.closest("[data-laysave]")) saveLayout();
});
const winMenu = on => { if (on) renderWinMenu(); $("winMenu").hidden = !on; $("bMore").setAttribute("aria-expanded", on); if (on) { syncWinButtons(); [...$("winMenu").querySelectorAll("button")].find(b => b.offsetParent)?.focus(); } };
$("bMore").onclick = e => { e.stopPropagation(); winMenu($("winMenu").hidden); };
$("winMenu").addEventListener("click", () => winMenu(false));
$("winMenu").addEventListener("keydown", e => {
  const items = [...$("winMenu").querySelectorAll("button")].filter(b => b.offsetParent), i = items.indexOf(document.activeElement);
  if (e.key === "Escape") { e.stopPropagation(); winMenu(false); $("bMore").focus(); }
  if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); items[(i + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length].focus(); }
});
addEventListener("pointerdown", e => { if (!$("winMenu").hidden && !e.target.closest(".more")) winMenu(false); });
function toggleDock(side, on) {
  const cls = side === "L" ? "noL" : "noR"; $("work").classList.toggle(cls, on === undefined ? undefined : !on);
  // узкое окно: панели выезжают поверх карты — открыта только одна, иначе вдвоём они закрывают почти всю карту
  if (narrow() && !$("work").classList.contains(cls)) $("work").classList.add(side === "L" ? "noR" : "noL");
  WST["dock" + side] = !$("work").classList.contains(cls); saveWins(); syncWinButtons(); mMain.updateSize();
}
// боковые панели тянутся за разделитель, ширина запоминается
function setDockWidth(side, px) { $("work").style.setProperty(side === "l" ? "--wl" : "--wr", px + "px"); WST["w" + side] = px; }
document.querySelectorAll("[data-gut]").forEach(g => g.addEventListener("pointerdown", e => {
  const side = g.dataset.gut, x0 = e.clientX, w0 = side === "l" ? $("work").children[2].offsetWidth : $("work").querySelector(".side.r").offsetWidth;
  g.setPointerCapture(e.pointerId); g.classList.add("on");
  const mv = ev => { setDockWidth(side, Math.max(220, Math.min(620, w0 + (side === "l" ? ev.clientX - x0 : x0 - ev.clientX)))); mMain.updateSize(); };
  const up = () => { g.removeEventListener("pointermove", mv); g.removeEventListener("pointerup", up); g.classList.remove("on"); saveWins(); mMain.updateSize(); };
  g.addEventListener("pointermove", mv); g.addEventListener("pointerup", up);
}));
// кнопки окон — и в группе «Окна», и справа в шапке («Листы» стоит отдельно от группы: без этого она молчала)
document.querySelector("header.top").addEventListener("click", e => { const b = e.target.closest("[data-win]"); if (!b) return; const id = b.dataset.win;
  if (id === "dockL" || id === "dockR") toggleDock(id.slice(4)); else winOpen(id); });
document.querySelectorAll(".drawerx").forEach(b => b.onclick = () => toggleDock(b.dataset.dock, false));   // крестик выезжающей панели на узком окне
document.querySelectorAll(".win").forEach(w => {
  w.addEventListener("pointerdown", () => winFront(w));
  w.querySelector("[data-close]").onclick = () => winOpen(w.id, false);
  const h = w.querySelector(".wh");
  // с клавиатуры: заголовок окна достаётся Tab-ом, Alt+стрелка встраивает окно в зону, Alt+↑ делает плавающим
  h.tabIndex = 0; h.setAttribute("aria-keyshortcuts", "Alt+ArrowLeft Alt+ArrowRight Alt+ArrowDown Alt+ArrowUp");
  h.addEventListener("keydown", e => {
    if (!e.altKey || e.target !== h) return;
    const side = { ArrowLeft: "l", ArrowRight: "r", ArrowDown: "b" }[e.key];
    if (side) { e.preventDefault(); if (narrow() && side !== "b") { (WST[w.id] ||= {}).dock = side; dockWin(w, "b", true); } else dockWin(w, side); }
    else if (e.key === "ArrowUp" && w.classList.contains("docked")) { e.preventDefault(); floatWin(w); placeWin(w); winFront(w); }
    else return;
    h.focus();                                          // перенос окна в другую зону снимает фокус — клавиатура остаётся на заголовке
    requestAnimationFrame(() => WIN_OPEN[w.id]?.());
  });
  h.addEventListener("pointerdown", e => { if (!e.button && !e.target.closest("button,input,select")) dragWin(w, e); });
  h.addEventListener("dblclick", e => {
    if (e.target.closest("button,input,select")) return;
    if (w.classList.contains("docked")) { floatWin(w); placeWin(w); winFront(w); }
    else { const r = w.getBoundingClientRect(), m = mapBox(), side = r.left + r.width / 2 < m.left + m.width / 2 ? "l" : "r";
      // узкое окно: боковая панель не выезжает поверх карты — окно встаёт вкладкой под картой, сторона запоминается
      if (narrow()) { (WST[w.id] ||= {}).dock = side; dockWin(w, "b", true); } else dockWin(w, side); }
    requestAnimationFrame(() => WIN_OPEN[w.id]?.());
  });
  // высота встроенного окна в боковой панели — за верхнюю кромку
  const dres = document.createElement("div"); dres.className = "dres"; dres.title = "Потяните, чтобы изменить высоту"; w.append(dres);
  dres.addEventListener("pointerdown", e => {
    const y0 = e.clientY, h0 = w.offsetHeight, side = w.parentElement.closest(".side"); dres.setPointerCapture(e.pointerId);
    const z = w.parentElement, zk = Object.keys(DZ).find(k => DZ[k] === z), tab = z.classList.contains("tabbed"), zh0 = z.offsetHeight;
    // во вкладках высоту держит сама зона (одна на все вкладки), без вкладок — окно
    const mv = ev => { const lim = (side?.clientHeight || 600) - 150, px = Math.max(90, Math.min(lim, (tab ? zh0 : h0) - (ev.clientY - y0)));
      if (tab) { z.style.setProperty("--dzh", px + "px"); WST["zh" + zk] = px; } else { w.style.flexBasis = px + "px"; (WST[w.id] ||= {}).dh = px; } };
    const up = () => { dres.removeEventListener("pointermove", mv); dres.removeEventListener("pointerup", up); saveWins(); layoutChanged(); };
    dres.addEventListener("pointermove", mv); dres.addEventListener("pointerup", up);
  });
  // граница с соседом слева в нижней зоне: ширины двух окон меняются, сумма остаётся
  const dresv = document.createElement("div"); dresv.className = "dresv"; dresv.title = "Потяните, чтобы поделить ширину между окнами"; w.append(dresv);
  dresv.addEventListener("pointerdown", e => {
    let prev = w.previousElementSibling; while (prev && (!prev.classList.contains("win") || prev.hidden)) prev = prev.previousElementSibling;
    if (!prev) return;
    const x0 = e.clientX, pw0 = prev.offsetWidth, tot = pw0 + w.offsetWidth; dresv.setPointerCapture(e.pointerId);
    const mv = ev => { const pw = Math.max(200, Math.min(tot - 200, pw0 + ev.clientX - x0)); prev.style.flexGrow = pw; w.style.flexGrow = tot - pw; (WST[prev.id] ||= {}).bw = pw; (WST[w.id] ||= {}).bw = tot - pw; };
    const up = () => { dresv.removeEventListener("pointermove", mv); dresv.removeEventListener("pointerup", up); saveWins(); layoutChanged(); };
    dresv.addEventListener("pointermove", mv); dresv.addEventListener("pointerup", up);
  });
  // размер окна — за нижний правый угол (CSS resize); запоминаем и перерисовываем содержимое
  new ResizeObserver(() => { if (w.hidden || w.classList.contains("docked")) return; Object.assign(WST[w.id] ||= {}, { w: w.offsetWidth, h: w.offsetHeight }); saveWins(); }).observe(w);
});
// высота нижней зоны встроенных окон — за её верхнюю кромку
{ const g = document.createElement("div"); g.className = "dres b"; g.title = "Потяните, чтобы изменить высоту нижней панели"; DZ.b.prepend(g);
  g.addEventListener("pointerdown", e => {
    const y0 = e.clientY, h0 = DZ.b.offsetHeight, cap = DZ.b.parentElement.clientHeight; g.setPointerCapture(e.pointerId);
    const mv = ev => { const px = Math.max(120, Math.min(cap - 120, h0 - (ev.clientY - y0))); DZ.b.style.height = px + "px"; WST.hb = px; mMain.updateSize(); };
    const up = () => { g.removeEventListener("pointermove", mv); g.removeEventListener("pointerup", up); saveWins(); layoutChanged(); };
    g.addEventListener("pointermove", mv); g.addEventListener("pointerup", up);
  });
  DZ.b.style.height = (WST.hb || Math.max(260, Math.round(DZ.b.parentElement.clientHeight * .4))) + "px"; }
new ResizeObserver(() => mMain.updateSize()).observe($("mMain"));
// при сужении окна браузера плавающие окна остаются на экране; ниже 1000 px боковые встроенные окна плывут, шире — встают обратно
let wasNarrow = narrow();
addEventListener("resize", () => {
  const n = narrow();
  if (n !== wasNarrow) document.querySelectorAll(".win:not([hidden])").forEach(w => { const z = dockPref(w.id); if (z === "l" || z === "r") dockWin(w, n ? "b" : z, n); });
  wasNarrow = n;
  document.querySelectorAll(".win:not([hidden]):not(.docked)").forEach(placeWin); syncZones();
});
$("baseSel").innerHTML = Object.entries(BASEMAPS).map(([k, b]) => `<option value="${k}">${b.title}</option>`).join(""); $("baseSel").value = BASE;
$("baseSel").onchange = e => setBasemap(e.target.value);
$("bTheme").onclick = () => { const d = matchMedia("(prefers-color-scheme: dark)").matches, c = document.documentElement.dataset.theme || (d ? "dark" : "light"); document.documentElement.dataset.theme = c === "dark" ? "light" : "dark";
  try { localStorage.setItem("grado2.theme", document.documentElement.dataset.theme); } catch { } };
try { const t = localStorage.getItem("grado2.theme"); if (t) document.documentElement.dataset.theme = t; } catch { }

// старт — после того как выполнены все скрипты страницы: ответ сервера мог прийти раньше, чем браузер дочитал
// layers.js … project.js, и восстановление автосохранения падало на ещё не объявленных ALBUM, VIEWS
const startApp = async () => {
  await window.hubGate?.();                       // совместный режим: до первого запроса к серверу — вход (project.js, hub.js); в обычном режиме возвращается сразу
  window.ogdResume?.();
  try { SOURCES = await api("/api/sources"); await loadStyleLibs(); } catch (e) { toast("Сервер ГРАДО не отвечает: " + e.message); }
  try { window.APP_VERSION = (await api("/version.json")).version; document.querySelector(".brand").title = "ГРАДО 2, версия " + window.APP_VERSION; } catch { }
  renderSources(); icons();
  if (WST.wl) setDockWidth("l", WST.wl); if (WST.wr) setDockWidth("r", WST.wr);
  if (WST.dockL === false) toggleDock("L", false); if (WST.dockR === false) toggleDock("R", false);
  // узкое окно: панели поверх карты, при запуске закрыты — открываются из меню «Окна»
  if (innerWidth <= 1000) { $("work").classList.add("noL", "noR"); syncWinButtons(); }          // без записи: на широком окне панели вернутся
  Object.keys(W0()).forEach(id => { if (WST[id]?.open) winOpen(id, true); });   // первый запуск: вместо окон — «С чего начать» на карте
  requestAnimationFrame(() => { WIN_ANIM = true; });                                // окна, открытые дальше, появляются мягко
  syncWinButtons(); recompute(true);
  await window.projectStart?.(); syncPreview();
};
if (document.readyState === "loading") addEventListener("DOMContentLoaded", startApp); else startApp();
