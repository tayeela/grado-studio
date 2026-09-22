/* ГРАДО 2: одно рабочее поле — карта со слоями, строка инструментов и плавающие окна
   (данные, граф, эскиз, варианты, показатели, объём, сравнение, таблица). Порядок работы свободный.
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
function newMap(target, layers) { const m = new ol.Map({ target, layers: [basemap(), ...layers], view: sharedView, controls: [new ol.control.ScaleLine({ minWidth: 70 }), new ol.control.Attribution({ collapsible: false })], interactions: interactions() }); ALLMAPS.push(m); window.attachDataLayers?.(m); return m; }
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
const terrLayer = () => new ol.layer.Vector({ source: terrSrc, style: terrStyle, zIndex: 110 });

/* ================= данные территории ================= */
const mMain = newMap("mMain", [terrLayer()]);
function setTerritory(feature) {
  TERR = turf.feature(feature.geometry); TERR_M2 = turf.area(TERR);
  setFrame(turf.centroid(TERR).geometry.coordinates);
  terrSrc.clear(); terrSrc.addFeature(toOl(TERR));
  $("terrInfo").textContent = `Площадь ${fmt(TERR_M2 / 1e4, 2)} га. Загружается прямоугольник вокруг границы.`;
  $("bLoad").disabled = false; dataRev++; window.syncStatus?.(); window.syncStart?.(); window.markDirty?.(); if (!$("wData").hidden) renderSources();
  sharedView.fit(terrSrc.getExtent(), { padding: [40, 40, 40, 40], maxZoom: 17 });
}
$("bDraw").onclick = () => setTool("terr");
$("bExample").onclick = () => setTerritory(turf.polygon([[[37.5195, 55.7895], [37.5305, 55.7895], [37.5305, 55.7955], [37.5195, 55.7955], [37.5195, 55.7895]]]));
const GROUP = { fgistp: "ФГИС ТП (загруженные слои документов)", import: "Импорт файлов", nspd: "ЕГРН · НСПД", osm: "OpenStreetMap", gisogd: "ГИС ОГД Москвы (первая выгрузка слоя идёт целиком — до 200 МБ и пары минут; дальше из кэша)", terrain: "Рельеф" };
const CHECKED = new Set(["nspd.parcels", "nspd.buildings", "osm.roads", "osm.buildings", "osm.water", "osm.landuse", "gisogd.szz", "gisogd.vodookhr"]);
const histText = d => { const h = d.history || [], x = h[h.length - 1]; return h.length > 1 && x.added != null ? ` · выгрузок ${h.length}, в последней +${x.added} −${x.removed} ~${x.changed}` : ""; };
function renderSources() {
  const groups = {}; Object.entries(SOURCES).forEach(([k, s]) => (groups[s.kind] ||= []).push(k));
  $("srcList").innerHTML = Object.entries(groups).map(([g, ks]) => `<div class="src"><div class="srch"><i data-lucide="database"></i><b>${GROUP[g] || g}</b></div>` + ks.map(k => {
    const d = DATA[k], e = ERRORS[k];
    return `<label class="lr"><input type="checkbox" data-src="${k}" ${CHECKED.has(k) ? "checked" : ""}><span class="nm" title="${esc(d?.source || "")}">${esc(SOURCES[k].title)}</span><span class="c num">${d ? d.count : ""}</span></label>` + (e ? `<div class="err">${esc(e)}</div>` : "") + (d ? `<div class="err" style="color:var(--faint)">выгрузка ${d.fetched_at}${histText(d)}${d.notes?.length ? " · " + esc(d.notes[0]) : ""}</div>` : "");
  }).join("") + `</div>`).join("") + (Object.keys(DATA).length ? `<div class="sect">Существующее положение</div>${kv(existingSummary())}` : "")
    + `<div id="fgBox">${fgHTML()}</div>`
    + `<div class="note">Загруженные слои появляются в списке слоёв; их можно править, исходная выгрузка сохраняется (меню слоя → «Вернуть исходную выгрузку»). В графе анализа слои доступны узлом «Слой». Красные линии рисуются типами линий REDLN97 — <a href="linetypes.html" target="_blank">каталог типов</a>.</div>`;
  icons();
}
$("srcList").addEventListener("change", e => {
  const k = e.target.dataset.src; if (k) e.target.checked ? CHECKED.add(k) : CHECKED.delete(k);
  if (e.target.id === "fgDoc") fgPick(e.target.value);
  if (e.target.dataset.fgl) { e.target.checked ? FG.sel.add(e.target.dataset.fgl) : FG.sel.delete(e.target.dataset.fgl); $("fgLoad").disabled = !FG.sel.size; }
});
$("srcList").addEventListener("click", e => { if (e.target.closest("#fgFind")) fgFind(); if (e.target.closest("#fgLoad")) fgLoad(); });

/* ---------- ФГИС ТП: документы терпланирования, чей охват накрывает территорию → их слои ---------- */
const FG = { docs: null, uin: "", layers: null, sel: new Set(), msg: "" };
const GEOMW = { "100": "полигоны", "010": "линии", "001": "точки" };
function fgHTML() {
  let h = `<div class="src"><div class="srch"><i data-lucide="landmark"></i><b>ФГИС ТП — документы территориального планирования</b><button class="btn" id="fgFind" ${TERR ? "" : "disabled"} title="Генпланы, схемы и их изменения, охват которых накрывает территорию (каталог Минэкономразвития)">Найти по территории</button></div>`;
  if (FG.msg) h += `<div class="note">${esc(FG.msg)}</div>`;
  if (FG.docs) h += `<div class="lr" style="height:auto;padding:4px 8px"><select id="fgDoc" style="width:100%"><option value="">— документ (${FG.docs.length}) —</option>${FG.docs.map(d => `<option value="${esc(d.uin)}" ${d.uin === FG.uin ? "selected" : ""}>${esc(d.name.slice(0, 140))}${d.km ? ` · ${fmt(d.km)} км` : ""}</option>`).join("")}</select></div>`;
  if (FG.layers) h += FG.layers.map(l => `<label class="lr"><input type="checkbox" data-fgl="${esc(l.classid)}" ${FG.sel.has(l.classid) ? "checked" : ""}><span class="nm" title="${esc(l.class_name || "")}">${esc(l.class_title || l.class_name || l.classid)}</span><span class="c">${GEOMW[l.geom_type] || ""}</span></label>`).join("")
    + `<div class="lr" style="height:32px"><span class="sp" style="flex:1"></span><button class="btn primary" id="fgLoad" ${FG.sel.size ? "" : "disabled"}>Загрузить выбранные</button></div>`;
  return h + `</div>`;
}
const fgRender = () => { const el = $("fgBox"); if (el) { el.innerHTML = fgHTML(); icons(); } };
async function fgFind() {
  const [w, s, e, n] = turf.bbox(TERR); FG.msg = "Каталог ФГИС ТП: первый раз около 10 МБ…"; fgRender(); busy(true);
  try { FG.docs = (await api(`/api/fgistp/docs?bbox=${[w, s, e, n].join(",")}`)).docs; FG.msg = FG.docs.length ? "Самые местные документы — сверху. Выберите документ, затем слои." : "Документов с охватом этой территории нет."; }
  catch (err) { FG.msg = "ФГИС ТП не ответила: " + err.message; } finally { busy(false); fgRender(); }
}
async function fgPick(uin) {
  FG.uin = uin; FG.layers = null; FG.sel.clear(); if (!uin) return fgRender();
  FG.msg = "Состав документа…"; fgRender(); busy(true);
  try { FG.layers = (await api(`/api/fgistp/layers?uin=${encodeURIComponent(uin)}`)).layers; FG.msg = `Слоёв в документе: ${FG.layers.length}. Отметьте нужные.`; }
  catch (err) { FG.msg = "Состав документа не получен: " + err.message; } finally { busy(false); fgRender(); }
}
async function fgLoad() {
  const [w, s, e, n] = turf.bbox(buf(TERR, 60)); FG.msg = "Загрузка слоёв документа: портал отдаёт документ целиком, может занять минуту…"; fgRender(); busy(true);
  try {
    const r = await api("/api/fgistp/fetch", { uin: FG.uin, classids: [...FG.sel], bbox: [w, s, e, n] });
    let n2 = 0; const empty = Object.values(r.layers).filter(v => !v.features.features.length).map(v => v.title.replace("ФГИС ТП: ", ""));
    for (const [k, v] of Object.entries(r.layers)) {
      if (!v.features.features.length) continue;                 // пустой в этой области слой не засоряет список
      SOURCES[k] = { title: v.title, kind: "fgistp" };
      DATA[k] = { ...v, fc: v.features, count: v.features.features.length, fields: [...new Set(v.features.features.slice(0, 200).flatMap(f => Object.keys(f.properties)))], original: v.features };
      layerSrc[k] ||= new ol.source.Vector(); setLayerData(k, v.features); const l = ensureLayer(k, v.title); assignCats(l, true); restyle(l); n2 += DATA[k].count;
    }
    FG.msg = `Загружено слоёв: ${Object.keys(r.layers).length - empty.length}, объектов в области: ${n2}.${empty.length ? ` Нет объектов в области: ${empty.join(", ")}.` : ""}`; dataRev++;
  } catch (err) { FG.msg = "Слои не загружены: " + err.message; } finally { busy(false); renderSources(); }
}
$("bLoad").onclick = async () => {
  if (!TERR) return;
  const keys = [...CHECKED];
  if (!keys.length) return toast("Отметьте источники.");
  const [w, s, e, n] = turf.bbox(buf(TERR, 60));
  $("bLoad").disabled = true; busy(true); window.setHint?.(`Выгрузка ${keys.length} источников идёт: порталы отвечают от секунд до минуты, ГИС ОГД в первый раз качает слой целиком. Работать можно дальше.`);
  try {
    const r = await api("/api/fetch", { bbox: [w, s, e, n], sources: keys });
    ERRORS = r.errors;
    const reports = [], fresh = [];
    for (const [k, v] of Object.entries(r.layers)) {
      const prev = DATA[k], fields = [...new Set(v.features.features.slice(0, 200).flatMap(f => Object.keys(f.properties)))];
      const m = prev && layerSrc[k] ? mergeDownload(k, prev, v.features) : null;
      DATA[k] = { ...v, fc: m ? m.fc : v.features, count: v.features.features.length, fields, original: v.features,
        history: [...(prev?.history || []), { date: v.fetched_at, n: v.features.features.length, ...(m?.counts || {}) }] };
      layerSrc[k] ||= new ol.source.Vector(); setLayerData(k, DATA[k].fc);
      const l = ensureLayer(k, v.title); assignCats(l, true); restyle(l);
      if (m) { reports.push(`«${v.title}»: ${m.text}`); fresh.push(...layerSrc[k].getFeatures().filter(f => m.mark.has(f.get("_key"))).map(f => ({ key: k, f }))); }
    }
    dataRev++; renderSources();
    const ne = Object.keys(ERRORS).length;
    if (fresh.length) setSel(fresh);          // новое и изменённое в источнике — подсвечено выбором
    toast(`Загружено слоёв: ${Object.keys(r.layers).length}${ne ? `, с ошибкой: ${ne}` : ""}.${reports.length ? " Перевыгрузка — " + reports.join("; ") + (fresh.length ? ". Новое и изменённое выделено." : ".") : ""}`);
  } catch (err) { toast("Выгрузка не удалась: " + err.message); }
  finally { busy(false); $("bLoad").disabled = false; window.syncStatus?.(); }
};
/* Повторная выгрузка слоя: сравнение с прошлой по ключу объекта источника (_key) и слияние с ручной правкой,
   чтобы ничего не пропало молча: ваша правка объекта сильнее новой версии источника, удалённое вами остаётся
   удалённым, нарисованное вами остаётся. */
function mergeDownload(key, prev, fc) {
  const clean = p => Object.fromEntries(Object.entries(p || {}).filter(([k]) => !k.startsWith("_")));
  const sig = f => JSON.stringify([f.geometry, clean(f.properties)]);
  const byKey = list => new Map(list.filter(f => f.properties?._key).map(f => [f.properties._key, f]));
  const oldF = prev.original?.features || [], oldBy = byKey(oldF), newBy = byKey(fc.features);
  if (!oldBy.size || !newBy.size) return null;                    // прежняя выгрузка без ключей (старый проект) — просто заменить
  const cur = writeFC(layerSrc[key].getFeatures()).features, curBy = byKey(cur);
  const added = [...newBy.keys()].filter(k => !oldBy.has(k)), removed = [...oldBy.keys()].filter(k => !newBy.has(k));
  const changed = [...newBy.keys()].filter(k => oldBy.has(k) && sig(oldBy.get(k)) !== sig(newBy.get(k)));
  const mine = cur.filter(f => f.properties?._edited && f.properties._key && newBy.has(f.properties._key));
  const gone = new Set([...oldBy.keys()].filter(k => !curBy.has(k)));
  const drawn = cur.filter(f => !f.properties?._key);
  // поля, которых нет в источнике (добавлены вами, например «Решение» реестра), переносятся на новую версию объекта
  const srcFields = new Set(fc.features.slice(0, 500).flatMap(f => Object.keys(f.properties || {})));
  const own = [...new Set(cur.slice(0, 500).flatMap(f => Object.keys(f.properties || {})))].filter(k => !srcFields.has(k) && !k.startsWith("_"));
  const out = fc.features.filter(f => !gone.has(f.properties?._key)).map(f => { const c = curBy.get(f.properties?._key); if (c?.properties._edited) return c;
    if (!c || !own.length) return f; const p = { ...f.properties }; own.forEach(k => { if (c.properties[k] != null) p[k] = c.properties[k]; }); return { ...f, properties: p }; }).concat(drawn);
  const conflict = mine.filter(f => changed.includes(f.properties._key)).length;
  const parts = [`+${added.length} новых`, `−${removed.length} исчезло`, `${changed.length} изменились`];
  if (mine.length) parts.push(`ваши правки (${mine.length}) сохранены${conflict ? `, из них ${conflict} изменились и в источнике — сверьте` : ""}`);
  if (gone.size) parts.push(`удалённые вами (${gone.size}) не вернулись`);
  return { fc: { type: "FeatureCollection", features: out }, text: parts.join(", "), mark: new Set([...added, ...changed]),
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
    const body = { files: await Promise.all(files.map(async f => ({ name: f.name, b64: b64(await f.arrayBuffer()) }))) };
    const r = await fetch("/api/import/files", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); const j = await r.json();
    if (!r.ok) throw new Error(j.error);
    const ex = ol.extent.createEmpty(), msgs = [];
    for (const lay of j.layers) {
      const key = "import:" + lay.name + "." + lay.format.toLowerCase(), title = `${lay.name} (${lay.format})`, fc = lay.features;
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
    toast("DXF готов: в архиве чертёж, red_lns.shx и REDLN97.LIN. Координаты — МГГТ, метры.");
  } catch (err) { toast("Экспорт не удался: " + err.message); } finally { busy(false); }
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
  const ck = [d.rev, key, fw.value, ow.value, vw.value, !!TERR].join("|");   // пересчёт — только при правке этого слоя
  if (this._cacheKey !== ck) {
    this._cacheKey = ck;
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
  this.addInput("пятно", "geom"); this.addInput("этажность", "num"); this.addInput("потолок", "cap"); this.addOutput("посадка", "sketch");
  this.addWidget("combo", "типология", "Секции", () => { }, { values: ["Секции", "Квартал", "Башни"] });
  this.addWidget("slider", "ширина корпуса, м", 16, () => { }, { min: 12, max: 24, precision: 0, slider_color: "#8fb3e0" });
  this.addWidget("slider", "этажность", 12, () => { }, { min: 3, max: 30, precision: 0, slider_color: "#8fb3e0" });
  this.addWidget("slider", "разрыв / высота", 1.0, () => { }, { min: .5, max: 2, precision: 2, slider_color: "#8fb3e0" });
  this.addWidget("slider", "поворот, °", 0, () => { }, { min: -45, max: 45, precision: 0, slider_color: "#8fb3e0" });
  this.properties = { run: false };        // как в TestFit: посадка строится только по команде «Построить эскиз»
  finish(this, "gen", 240);
}
NPlace.title = "Посадка застройки"; NPlace.prototype.onExecute = function () {
  if (!this.properties.run) { this.setOutputData(0, []); this.info = "не построена: «Построить эскиз» в окне «Эскиз»"; return; }
  const site = this.getInputData(0), p = placeParams(this);
  const r = cached(this, gid(site) + JSON.stringify(p) + (p.cap?._id || ""), () => generate(site, p)); this.setOutputData(0, r);
  const capped = r.filter(b => b.capped).length;
  this.info = `${r.length} корпусов · ${fmt(r.reduce((s, b) => s + b.m2 * b.floors, 0) / 1000, 1)} тыс. м² СПП${capped ? ` · ${capped} ниже по потолку` : ""}`;
};
LiteGraph.registerNodeType("Эскиз/Посадка застройки", NPlace);
function placeParams(n) { const w = n.widgets; return { typ: w[0].value, width: Math.round(w[1].value), floors: n.getInputData?.(1) ?? Math.round(w[2].value), gap: +w[3].value, angle: Math.round(w[4].value), cap: n.inputs?.[2] ? n.getInputData?.(2) || null : null }; }

function NTep() { this.addInput("посадка", "sketch"); this.addInput("сохраняемые", "geom"); this.addInput("ограничения", "geom"); this.addOutput("ТЭП", "tep");
  this.addWidget("slider", "доля жилья, %", 80, () => { }, { min: 0, max: 100, precision: 0, slider_color: "#c0a6d4" }); this.addWidget("slider", "цель, тыс. м²/га", 25, () => { }, { min: 5, max: 45, precision: 0, slider_color: "#c0a6d4" }); finish(this, "tep", 230); }
NTep.title = "ТЭП · методика КРТ Москвы"; NTep.prototype.onExecute = function () {
  const sk = this.getInputData(0) || [], kept = this.getInputData(1), lim = this.getInputData(2), share = this.widgets[0].value / 100, target = this.widgets[1].value;
  const key = [gid(sk), gid(kept), gid(lim), share, target, dataRev].join("|");
  if (this._key !== key) { this._key = key; const seq = this._seq = (this._seq || 0) + 1;
    tepRequest(sk, kept, lim, share, target).then(t => { if (seq === this._seq) { this._tep = t; this.setOutputData(0, t); this.info = `плотность ${fmt(t.density, 1)} · население ${fmt(t.m.population)}`; lgc.setDirty(true, true); renderTep(); } }).catch(e => { this.info = "ТЭП: " + e.message; }); }
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
  const out = place(site, p); if (!p.cap) return out;
  /* потолок (узел «Ограничения»): корпус не выше наименьшего потолка под ним — инсоляция соседей и высота по ПЗЗ;
     ниже двух этажей корпус не ставится. ponytail: разрывы между корпусами считаются от исходной этажности —
     после понижения они с запасом, а не впритык */
  const fh = typeof CONS !== "undefined" ? CONS.floorH : 3;
  return out.map(b => { const top = p.cap(b.f); if (top == null) return b; const fl = Math.min(b.floors, Math.floor(top / fh)); return fl >= 2 ? { ...b, floors: fl, capped: fl < b.floors } : null; }).filter(Boolean);
}
function place(site, p) {
  if (!site) return [];
  const out = [], extra = p.angle * Math.PI / 180;
  const fits = (part, ring) => { const f = polyLL(ring), ar = m2(f); return m2(inter(part, f)) >= ar * .985 ? f : null; };
  const push = (f, floors) => out.push({ f, floors, m2: m2(f) });
  for (const part of splitParts(site)) {
    if (m2(part) < 1500) continue;
    const { a, b } = partFrame(ringsXY(part)[0], extra), W = rp => rp.map(q => rot(q, a, [0, 0]));
    const span = (lo, hi, size, gap) => { const n = Math.max(0, Math.floor((hi - lo + gap) / (size + gap))); const s0 = lo + (hi - lo - (n * size + (n - 1) * gap)) / 2; return Array.from({ length: n }, (_, i) => s0 + i * (size + gap)); };
    if (p.typ === "Секции") {
      const H = p.floors * 3, gapLong = Math.max(p.gap * H, p.floors >= 4 ? 20 : 15), brk = 12;
      for (const v of span(b[1], b[3], p.width, gapLong)) {
        let u = b[0];
        while (u < b[2]) {                      // секция 60 м, у края — 40 м; не влезла — шаг дальше
          const L = [60, 40].find(len => u + len <= b[2] + .1 && fits(part, W(rect(u, v, u + len, v + p.width))));
          if (L) { push(polyLL(W(rect(u, v, u + L, v + p.width))), p.floors); u += L + brk; } else u += 5;
        }
      }
    } else if (p.typ === "Башни") {
      const s = p.width + 8, fl = Math.round(p.floors * 1.6), gap = Math.max(20, p.gap * fl * 3 * .6);
      for (const v of span(b[1], b[3], s, gap)) for (const u of span(b[0], b[2], s, gap)) { const f = fits(part, W(rect(u, v, u + s, v + s))); if (f) push(f, fl); }
    } else {                                    // квартал: периметр по краю участка с проездом во двор
      if (m2(part) < 2500) continue;
      const ring = diff(part, buf(part, -p.width)) || part, cx = (b[0] + b[2]) / 2;
      const r = diff(ring, polyLL(W(rect(cx - 7, b[1] - 5, cx + 7, b[3] + 5)))) || ring;
      splitParts(r).forEach(q => { if (m2(q) >= 150) push(q, Math.max(3, Math.round(p.floors * .7))); });
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
const nK = add("Данные/Слой", [20, 380], n => { setW(n, "слой", "Здания (ЕГРН)"); n.title = "Сохраняемые здания"; });   // по умолчанию сносить нечего; снос — условием в узле
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
  const s = Math.max(.6, Math.min(1.1, (box.width - 40) / (x1 - x0), (box.height - 60) / (y1 - y0))); // мельче 0,6 подписи узлов не читаются — дальше прокрутка lgc.ds.scale = s; lgc.ds.offset = [20 / s - x0, 50 / s - y0]; lgc.setDirty(true, true);
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
  const sig = signature(); if (!force && sig === lastSig) return; if (sig !== lastSig) window.markDirty?.(); lastSig = sig;
  safe(() => graph.runStep(1, true));
  const place = graph._nodes.find(n => n.type === "Эскиз/Посадка застройки"), tepN = graph._nodes.find(n => n.type === "Показатели/ТЭП КРТ");
  RESULT = { site: place?.getInputData(0) || null, sketch: place?.getOutputData(0) || [], tep: tepN?._tep || null, placeNode: place, tepNode: tepN };
  lgc.setDirty(true, true); updateAnalysisMap(); renderSketch();
  if (!recompute.once) { recompute.once = true; renderParams(); }
}
setInterval(() => recompute(false), 250);

/* ---------- результат графа на основной карте ---------- */
const prevSrc = new ol.source.Vector(), sketchSrc = new ol.source.Vector(), siteSrc = new ol.source.Vector(), keptSrc = new ol.source.Vector();
const shade = n => ["#dcebfa", "#a8cbf1", "#6fa6e6", "#2a78d6", "#1a4f94"][Math.min(4, Math.floor(n / 6))];
const sketchStyle = f => new ol.style.Style({ fill: new ol.style.Fill({ color: shade(f.get("floors")) }), stroke: new ol.style.Stroke({ color: "#1a4f94", width: 1 }), text: new ol.style.Text({ text: String(f.get("floors")), font: "11px Arial", fill: new ol.style.Fill({ color: f.get("floors") > 14 ? "#fff" : "#123" }) }) });
const siteLayer = () => new ol.layer.Vector({ source: siteSrc, zIndex: 20, style: new ol.style.Style({ fill: new ol.style.Fill({ color: hatch("#1f7a4d") }), stroke: new ol.style.Stroke({ color: "#1f7a4d", width: 1.4, lineDash: [5, 3] }) }) });
const keptLayer = () => new ol.layer.Vector({ source: keptSrc, zIndex: 35, style: S("#bdb8b0", "#4d4d4d", 1) });
const sketchLayer = () => new ol.layer.Vector({ source: sketchSrc, zIndex: 40, style: sketchStyle });
// результат графа — отдельные слои над данными; видимость переключается в дереве слоёв
const RES = [
  { id: "site", title: "Пятно застройки", color: "#1f7a4d", layer: siteLayer() },
  { id: "kept", title: "Сохраняемые здания", color: "#bdb8b0", layer: keptLayer() },
  { id: "sketch", title: "Эскиз застройки", color: "#6fa6e6", layer: sketchLayer() },
  { id: "prev", title: "Выход выбранного узла", color: "#e08a00", layer: new ol.layer.Vector({ source: prevSrc, style: S([224, 138, 0, .28], "#c46f00", 2) }) }];
RES.forEach((r, i) => { r.layer.setZIndex(100 + i); mMain.addLayer(r.layer); });
function fillGeom(src, f) { src.clear(); if (f) src.addFeature(toOl(f)); }
function fillSketch() { sketchSrc.clear(); sketchSrc.addFeatures(RESULT.sketch.map(b => { const f = toOl(b.f); f.set("floors", b.floors); return f; })); }
function updateAnalysisMap() {
  fillGeom(siteSrc, RESULT.site); fillSketch(); prevSrc.clear();
  let txt = TERR ? `Пятно застройки ${ha(RESULT.site)} · ${RESULT.sketch.length} корпусов` : "Сначала задайте территорию и загрузите данные (окно «Данные»)";
  if (selNode) { const out = selNode.getOutputData?.(0), t = selNode.outputs?.[0]?.type;
    if (t === "geom") { if (out) prevSrc.addFeature(toOl(out)); txt = `Выход узла «${selNode.title}»: ${ha(out)}`; }
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
  if (p) out.push({ n: p, w: "типология", type: "seg", opts: ["Секции", "Квартал", "Башни"], hint: "квартал — периметр с проходом, башни — ×1,6 к этажности" });
  if (num) out.push({ n: num, w: "значение", label: "Этажность", min: 3, max: 30, step: 1, hint: "узел «Число» в графе" }); else if (p) out.push({ n: p, w: "этажность", min: 3, max: 30, step: 1 });
  if (p) out.push({ n: p, w: "ширина корпуса, м", min: 12, max: 24, step: 1 }, { n: p, w: "разрыв / высота", min: .5, max: 2, step: .05, hint: "разрыв между длинными сторонами = коэф. × высота, но не меньше 15 м (2–3 эт.) и 20 м (4 эт. и выше), СП 42.13330 п. 7.1" }, { n: p, w: "поворот, °", label: "Поворот относительно длинной стороны участка, °", min: -45, max: 45, step: 1, hint: "0 — корпуса вдоль длинной стороны каждого участка" });
  graph._nodes.filter(n => n.type === "Геометрия/Буфер").forEach(n => out.push({ n, w: "расстояние, м", label: n.title + ", м", min: 0, max: 40, step: 1 }));
  if (t) out.push({ n: t, w: "доля жилья, %", min: 0, max: 100, step: 5 }, { n: t, w: "цель, тыс. м²/га", label: "Целевая плотность, тыс. м²/га", min: 5, max: 45, step: 1 });
  return out;
}
function renderParams() {
  const cs = publishedControls(), pn = RESULT.placeNode, on = !!pn?.properties.run;
  const head = !pn ? `<div class="note">В графе нет узла «Посадка застройки».</div>`
    : `<div class="ctl"><div class="row" style="margin:0">${on ? `<button class="btn" data-run="0" title="Остановить пересчёт посадки: правка параметров перестанет перестраивать эскиз"><i data-lucide="pause"></i>Остановить</button>` : `<button class="btn primary" data-run="1" title="Разместить корпуса на пятне застройки по заданной типологии"><i data-lucide="play"></i>Построить эскиз</button>`}<button class="btn" data-bake ${RESULT.sketch.length ? "" : "disabled"} title="Сделать эскиз обычным слоем проекта: править, стилизовать, выгружать"><i data-lucide="stamp"></i>Принять в проект</button></div>
      <small>${on ? `Эскиз перестраивается при каждой правке ниже. Корпусов: ${RESULT.sketch.length}. Пока эскиз не принят, он виден только при открытых окнах графа и эскиза.` : "Выберите типологию и параметры, затем «Построить эскиз». Сам по себе эскиз не строится."}</small></div>`;
  $("params").innerHTML = head + cs.map((c, i) => { const w = c.n.widgets.find(x => x.name === c.w), lbl = c.label || c.w[0].toUpperCase() + c.w.slice(1);
    if (c.type === "seg") return `<div class="ctl"><div class="t"><span>${lbl}</span></div><div class="seg">${c.opts.map(o => `<button data-seg="${i}" data-v="${o}" aria-pressed="${w.value === o}">${o}</button>`).join("")}</div>${c.hint ? `<small>${c.hint}</small>` : ""}</div>`;
    return `<div class="ctl"><div class="t"><label for="pc${i}">${esc(lbl)}</label><span id="pv${i}">${fmt(w.value, c.step < 1 ? 2 : 0)}</span></div><input type="range" id="pc${i}" data-pc="${i}" min="${c.min}" max="${c.max}" step="${c.step}" value="${w.value}">${c.hint ? `<small>${c.hint}</small>` : ""}</div>`; }).join("")
    + `<div class="note">Параметры узлов графа, вынесенные в панель: правка здесь меняет граф, и наоборот.</div>`;
  icons();
  $("params").oninput = e => { const i = e.target.dataset.pc; if (i == null) return; const c = cs[+i], w = c.n.widgets.find(x => x.name === c.w); w.value = +e.target.value; $("pv" + i).textContent = fmt(w.value, c.step < 1 ? 2 : 0); recompute(); };
  $("params").onclick = e => {
    const r = e.target.closest("[data-run]"); if (r) { pn.properties.run = r.dataset.run === "1"; pn._ck = null; recompute(true); renderParams(); syncPreview(); return; }
    if (e.target.closest("[data-bake]")) return bakeSketch();
    const b = e.target.closest("[data-seg]"); if (!b) return; const c = cs[+b.dataset.seg]; c.n.widgets.find(x => x.name === c.w).value = b.dataset.v; renderParams(); recompute(); };
}
/* «Принять в проект» (Bake в Grasshopper): снимок эскиза становится обычным слоем и больше не зависит от графа */
function bakeSketch() {
  const sk = RESULT.sketch; if (!sk.length) return toast("Эскиз пуст: сначала «Построить эскиз».");
  const typ = RESULT.placeNode.widgets[0].value, fl = [...new Set(sk.map(b => b.floors))].join("/"), key = "user:" + Date.now().toString(36), title = `Эскиз: ${typ.toLowerCase()}, ${fl} эт.`;
  const fc = turf.featureCollection(sk.map((b, i) => turf.feature(b.f.geometry, { "№": i + 1, "Типология": typ, "Этажность": b.floors, "Площадь застройки, м²": Math.round(b.m2), "СПП, м²": Math.round(b.m2 * b.floors) })));
  DATA[key] = { title, source: "эскиз из графа, принят " + new Date().toLocaleDateString("ru-RU"), fetched_at: new Date().toISOString().slice(0, 10), fc, count: 0, fields: [] };
  layerSrc[key] = new ol.source.Vector(); setLayerData(key, fc); delete DATA[key].original;
  const l = ensureLayer(key, title, "poly");
  const many = new Set(sk.map(b => b.floors)).size > 1;          // разная этажность — диапазоны, одна — единый цвет
  l.style = ST({ mode: many ? "grad" : "single", fill: "#6fa6e6", stroke: "#1a4f94", width: .8, opacity: .9, label: "Этажность", grad: { field: "Этажность", n: 4, ramp: "blue", method: "equal" } });
  restyle(l); setCurrent(key); dataRev++;
  toast(`Эскиз принят слоем «${title}»: ${sk.length} корпусов. Слой можно править, стилизовать и выгружать; граф на него больше не влияет.`);
}
// предпросмотр графа (Preview в Grasshopper): только пока открыты окна графа/эскиза, выход узла — только при открытом графе
const PREVIEW_WINS = ["wGraph", "wSketch", "wVars", "w3d", "wCmp"];
function syncPreview() {
  const open = id => !$(id).hidden, any = PREVIEW_WINS.some(open);
  RES.forEach(r => r.layer.setVisible(r.on !== false && (r.id === "prev" ? open("wGraph") : any)));
  if (typeof renderTree === "function") renderTree();
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
  renderTep();
  keptSrc.clear(); (RESULT.tepNode?._tep?.kept || []).forEach(f => keptSrc.addFeature(toOl(f)));
  if (!$("w3d").hidden) draw3d();
}
$("bRot").onclick = () => { rot3d = (rot3d + 1) % 4; draw3d(); };
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
new ResizeObserver(() => { if (!$("w3d").hidden) draw3d(); }).observe($("c3d").parentElement);

/* ---------- варианты ---------- */
let VARS = [], varSel = -1;
$("bGen").onclick = async () => {
  const p = RESULT.placeNode, t = RESULT.tepNode; if (!p || !RESULT.site) return toast("В графе нет пятна застройки или узла посадки.");
  const base = placeParams(p), share = t.widgets[0].value / 100, target = t.widgets[1].value, kept = t.getInputData(1), lim = t.getInputData(2);
  const combos = [["Секции", 9], ["Секции", 16], ["Квартал", 9], ["Квартал", 14], ["Башни", 12], ["Башни", 20]];
  busy(true);
  try { VARS = await Promise.all(combos.map(async ([typ, floors]) => { const sk = generate(RESULT.site, { ...base, typ, floors }); return { typ, floors, sk, tep: await tepRequest(sk, kept, lim, share, target) }; })); varSel = -1; renderVars(); }
  catch (e) { toast("Варианты не посчитались: " + e.message); } finally { busy(false); }
  if (!VARS.length) return;
};
function renderVars() {
  const tb = bboxOf(ringsXY(TERR)[0]), pad = 10, vb = `${tb[0] - pad} ${-tb[3] - pad} ${tb[2] - tb[0] + 2 * pad} ${tb[3] - tb[1] + 2 * pad}`;
  const pts = r => r.map(p => p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
  $("vlist").innerHTML = VARS.map((v, i) => { const cls = v.tep.density > v.tep.target * 1.05 ? "bad" : v.tep.density < v.tep.target * .8 ? "warn" : "good";
    const sw = Math.max(1, (tb[2] - tb[0]) / 180);
    return `<button class="vc" data-var="${i}" aria-pressed="${i === varSel}"><svg viewBox="${vb}" preserveAspectRatio="xMidYMid meet"><g transform="scale(1,-1)"><polygon points="${pts(ringsXY(TERR)[0])}" fill="#fff" stroke="#b3261e" stroke-width="${sw * 2}" stroke-dasharray="${sw * 8} ${sw * 4}"/>${v.tep.kept.flatMap(f => ringsXY(f)).map(r => `<polygon points="${pts(r)}" fill="#bdb8b0"/>`).join("")}${v.sk.flatMap(b => ringsXY(b.f)).map(r => `<polygon points="${pts(r)}" fill="#6fa6e6" stroke="#1a4f94" stroke-width="${sw}"/>`).join("")}</g></svg>
      <div class="vt">${v.typ} · ${v.floors} эт.</div><div class="vm"><span>плотность</span><b style="color:var(--${cls})">${fmt(v.tep.density, 1)}</b><span>СПП, тыс. м²</span><b>${fmt((v.tep.sppNew + v.tep.sppKept) / 1000, 1)}</b><span>население</span><b>${fmt(v.tep.m.population)}</b></div></button>`; }).join("");
}
$("bBakeVar").onclick = () => varSel < 0 ? toast("Выберите вариант в списке — щелчок по карточке.") : bakeSketch();
$("vlist").addEventListener("click", e => { const b = e.target.closest("[data-var]"); if (!b) return; varSel = +b.dataset.var; const v = VARS[varSel], p = RESULT.placeNode;
  p.widgets.find(w => w.name === "типология").value = v.typ;
  const num = graph._nodes.find(n => n.type === "Параметры/Число" && n.outputs[0].links?.some(id => graph.links[id]?.target_id === p.id));
  (num ? num.widgets[0] : p.widgets.find(w => w.name === "этажность")).value = v.floors; p.properties.run = true; syncPreview();
  recompute(); renderParams(); renderVars(); toast(`Вариант «${v.typ} · ${v.floors} эт.» перенесён в граф.`); });

/* ================= плавающие окна и панели ================= */
// окно = section.win: перетаскивание за шапку, размер — за угол, положение запоминается
const WINKEY = "grado2.win";
let WST = {}; try { WST = JSON.parse(localStorage.getItem(WINKEY)) || {}; } catch { }
const saveWins = () => { try { localStorage.setItem(WINKEY, JSON.stringify(WST)); } catch { } };
const W0 = () => { const w = innerWidth, h = innerHeight; return {
  wData: [300, 96, 340, Math.min(560, h - 150)], wGraph: [290, Math.round(h * .38), Math.max(560, w - 310), Math.round(h * .56)], wSketch: [w - 640, 96, 320, 470],
  wVars: [300, h - 300, Math.min(1180, w - 620), 260], wTep: [w - 640, 96, 330, Math.min(620, h - 150)], w3d: [360, 110, 620, 440],
  wCmp: [320, 100, Math.min(1000, w - 400), 520], wTable: [300, h - 330, Math.max(560, w - 620), 280], wProjects: [Math.round(w / 2 - 290), 90, 580, Math.min(480, h - 150)],
  wKeys: [Math.round(w / 2 - 230), 80, 460, Math.min(640, h - 140)], wCons: [650, 96, 340, Math.min(700, h - 150)] }; };
// рабочее поле карты: края боковых панелей, к которым прилипают окна
const mapBox = () => $("mMain").parentElement.getBoundingClientRect();
function placeWin(w) {
  const d = WST[w.id] || {}, [l, t, ww, hh] = W0()[w.id];
  if (d.anchor) return anchorWin(w);
  const W = Math.min(d.w || ww, innerWidth - 20), H = Math.min(d.h || hh, innerHeight - 90);
  Object.assign(w.style, { width: W + "px", height: H + "px", left: Math.max(4, Math.min(d.l ?? l, innerWidth - W - 4)) + "px", top: Math.max(40, Math.min(d.t ?? t, innerHeight - H - 26)) + "px" });
}
/* окно, прижатое к боковой панели, следует за ней при растягивании и скрытии панели;
   «во всю высоту» — двойной щелчок по заголовку, как у палитр AutoCAD */
function anchorWin(w) {
  const d = WST[w.id], m = mapBox(), W = Math.min(d.w || w.offsetWidth, m.width);
  const H = d.full ? m.height : Math.min(d.h || w.offsetHeight, m.height), T = d.full ? m.top : Math.max(m.top, Math.min(d.t ?? m.top, m.bottom - H));
  Object.assign(w.style, { width: W + "px", height: H + "px", top: T + "px", left: (d.anchor === "l" ? m.left : m.right - W) + "px" });
}
const reanchor = () => document.querySelectorAll(".win:not([hidden])").forEach(w => WST[w.id]?.anchor && anchorWin(w));
addEventListener("resize", reanchor);
const SNAP = 12;
function snapMove(w, x, y) {           // магнит к краям карты (боковым панелям), строке инструментов, строке состояния и другим окнам
  const m = mapBox(), W = w.offsetWidth, H = w.offsetHeight, xs = [m.left, m.right, 0, innerWidth], ys = [m.top, m.bottom, innerHeight];
  document.querySelectorAll(".win:not([hidden])").forEach(o => { if (o === w) return; const r = o.getBoundingClientRect(); xs.push(r.left, r.right); ys.push(r.top, r.bottom); });
  let sx = null, sy = null, best = SNAP;
  for (const t of xs) for (const e of [0, W]) { const d = Math.abs(x + e - t); if (d < best) { best = d; sx = t - e; } }
  best = SNAP; for (const t of ys) for (const e of [0, H]) { const d = Math.abs(y + e - t); if (d < best) { best = d; sy = t - e; } }
  const anchor = sx === m.left ? "l" : sx !== null && sx + W === m.right ? "r" : null;
  return { x: sx ?? x, y: sy ?? y, anchor, snapped: sx !== null || sy !== null };
}
function winFront(w) { document.querySelectorAll(".win.front").forEach(x => x.classList.remove("front")); w.classList.add("front"); }
const WIN_OPEN = {
  wGraph: () => { sizeGraph(); if (!go.fitted) { fitGraph(); go.fitted = true; } updateAnalysisMap(); },
  wSketch: () => renderParams(), wTep: () => renderTep(), w3d: () => draw3d(),
  wCmp: () => { if (!mBefore) { mBefore = newMap("mBefore", [terrLayer()]); mAfter = newMap("mAfter", [keptLayer(), sketchLayer(), terrLayer()]); } },
  wTable: () => window.renderTable?.(), wData: () => renderSources(), wCons: () => window.renderCons?.() };
const go = {};
function winOpen(id, on) {
  const w = $(id); on = on ?? w.hidden; w.hidden = !on;
  if (on) { placeWin(w); winFront(w); requestAnimationFrame(() => WIN_OPEN[id]?.()); }
  if (id === "wGraph") $("pv").hidden = !on;
  if (PREVIEW_WINS.includes(id)) syncPreview();
  (WST[id] ||= {}).open = on; saveWins(); syncWinButtons();
}
function syncWinButtons() {
  document.querySelectorAll("[data-win]").forEach(b => { const id = b.dataset.win;
    b.setAttribute("aria-pressed", id === "dockL" ? !$("work").classList.contains("noL") : id === "dockR" ? !$("work").classList.contains("noR") : !$(id).hidden); });
}
function toggleDock(side, on) {
  const cls = side === "L" ? "noL" : "noR"; $("work").classList.toggle(cls, on === undefined ? undefined : !on);
  WST["dock" + side] = !$("work").classList.contains(cls); saveWins(); syncWinButtons(); mMain.updateSize(); reanchor();
}
// боковые панели тянутся за разделитель, ширина запоминается
function setDockWidth(side, px) { $("work").style.setProperty(side === "l" ? "--wl" : "--wr", px + "px"); WST["w" + side] = px; }
document.querySelectorAll("[data-gut]").forEach(g => g.addEventListener("pointerdown", e => {
  const side = g.dataset.gut, x0 = e.clientX, w0 = side === "l" ? $("work").children[2].offsetWidth : $("work").querySelector(".side.r").offsetWidth;
  g.setPointerCapture(e.pointerId); g.classList.add("on");
  const mv = ev => { setDockWidth(side, Math.max(200, Math.min(620, w0 + (side === "l" ? ev.clientX - x0 : x0 - ev.clientX)))); reanchor(); };
  const up = () => { g.removeEventListener("pointermove", mv); g.removeEventListener("pointerup", up); g.classList.remove("on"); saveWins(); mMain.updateSize(); };
  g.addEventListener("pointermove", mv); g.addEventListener("pointerup", up);
}));
$("work").parentElement.querySelector(".wins").addEventListener("click", e => { const b = e.target.closest("[data-win]"); if (!b) return; const id = b.dataset.win;
  if (id === "dockL" || id === "dockR") toggleDock(id.slice(4)); else winOpen(id); });
document.querySelectorAll(".win").forEach(w => {
  w.addEventListener("pointerdown", () => winFront(w));
  w.querySelector("[data-close]").onclick = () => winOpen(w.id, false);
  const h = w.querySelector(".wh");
  h.addEventListener("pointerdown", e => {
    if (e.target.closest("button")) return;
    const r = w.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top; h.setPointerCapture(e.pointerId);
    let s = null;
    const mv = ev => { s = snapMove(w, Math.max(-r.width + 80, Math.min(ev.clientX - dx, innerWidth - 80)), Math.max(40, Math.min(ev.clientY - dy, innerHeight - 40)));
      w.style.left = s.x + "px"; w.style.top = s.y + "px"; w.classList.toggle("snap", s.snapped); };
    const up = () => { h.removeEventListener("pointermove", mv); h.removeEventListener("pointerup", up); w.classList.remove("snap");
      const d = WST[w.id] ||= {}; Object.assign(d, { l: parseInt(w.style.left), t: parseInt(w.style.top), anchor: s?.anchor ?? d.anchor ?? null }); if (s) d.full = false; saveWins(); };
    h.addEventListener("pointermove", mv); h.addEventListener("pointerup", up);
  });
  h.addEventListener("dblclick", e => {
    if (e.target.closest("button")) return; const d = WST[w.id] ||= {}, m = mapBox(), r = w.getBoundingClientRect();
    if (d.full) { d.full = false; d.h = d.hPrev || 400; } else { d.hPrev = r.height; d.full = true; d.anchor ||= r.left + r.width / 2 < m.left + m.width / 2 ? "l" : "r"; }
    anchorWin(w); saveWins();
  });
  // размер окна — за нижний правый угол (CSS resize); запоминаем и перерисовываем содержимое
  new ResizeObserver(() => { if (w.hidden) return; Object.assign(WST[w.id] ||= {}, { w: w.offsetWidth, h: w.offsetHeight }); saveWins(); }).observe(w);
});
$("baseSel").innerHTML = Object.entries(BASEMAPS).map(([k, b]) => `<option value="${k}">${b.title}</option>`).join(""); $("baseSel").value = BASE;
$("baseSel").onchange = e => setBasemap(e.target.value);
$("bTheme").onclick = () => { const d = matchMedia("(prefers-color-scheme: dark)").matches, c = document.documentElement.dataset.theme || (d ? "dark" : "light"); document.documentElement.dataset.theme = c === "dark" ? "light" : "dark"; };

(async () => {
  try { SOURCES = await api("/api/sources"); await loadStyleLibs(); } catch (e) { toast("Сервер ГРАДО не отвечает: " + e.message); }
  renderSources(); icons();
  if (WST.wl) setDockWidth("l", WST.wl); if (WST.wr) setDockWidth("r", WST.wr);
  if (WST.dockL === false) toggleDock("L", false); if (WST.dockR === false) toggleDock("R", false);
  Object.keys(W0()).forEach(id => { if (WST[id]?.open) winOpen(id, true); });   // первый запуск: вместо окон — «С чего начать» на карте
  syncWinButtons(); recompute(true);
  await window.projectStart?.(); syncPreview();
})();
