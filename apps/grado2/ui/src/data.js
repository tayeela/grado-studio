/* ГРАДО 2 · данные проекта в новом интерфейсе: граница территории (нарисовать, из файла, по участкам, из выбранного,
   пример), область загрузки, выгрузка источников (ЕГРН, ГИС ОГД, ЕГКО, OSM, Яндекс, рельеф) и импорт файлов.
   Те же адреса сервера и те же правила, что у рабочей страницы (web/app.js loadKeys, mergeDownload, importFiles,
   importBoundary; web/layers.js ensureLayer, defaultStyle, portalStyles): повторная выгрузка сливается с ручной правкой,
   ваши правки, удалённое и нарисованное сохраняются; поля файла — title, source, fetched_at, notes, history, shp, bbox,
   fc, original. Портал: части большой области сервер берёт по очереди с паузами, клиент шлёт по одному запросу на группу.
   Ход выгрузки по слоям (job) показывает окно «Данные». */
import { markRaw, reactive, ref } from "vue";
import * as turf from "@turf/turf";
import "../../web/roles.js";
import { currentId, project } from "./store.js";
import { lyr, mapApi, normGroups, touchData } from "./edit.js";
import { busy, markDirty, notice } from "./project.js";
import { setSel, sizeOf } from "./features.js";
import { CAT, assignCats, fullStyle } from "./symbology.js";
import { plural } from "./geom.js";
import * as mskMod from "../../web/msk.js";
import { cornersM } from "./viewframes.js";

export const SOURCES = reactive({});   // ключ → {title, kind, code?}: /api/sources и импорт проекта
export const ERRORS = reactive({});    // ключ → текст ошибки последней выгрузки
export const coverOn = ref(false);     // окно «Данные» на виду: область загрузки — синей рамкой на карте
export const coverRev = ref(0);        // своя область загрузки задана или снята — карта и окно «Данные» перечитывают
export const terrTool = ref("");       // "draw" — рисуем границу, "edit" — правим её вершины
export const loading = ref("");        // строка хода выгрузки («Участки: 42 %…»), пусто — не идёт
/* Ход выгрузки по слоям — для окна «Данные» (владелец 09.10.2026: «невозможно отследить процесс выгрузки»):
   у каждого слоя состояние wait (в очереди) → run (идёт; detail — что сейчас, pct — доля) → done | empty | error; t0, t1 — начало и конец. */
export const job = reactive({ items: [], t0: 0, t1: 0 });

const today = () => new Date().toISOString().slice(0, 10);
const fmt = (v, d = 0) => Number(v).toLocaleString("ru-RU", { minimumFractionDigits: d, maximumFractionDigits: d });
const safe = fn => { try { return fn(); } catch (e) { console.warn(e); return null; } };

async function api(url, body) {
  const r = await fetch(url, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || String(r.status));
  return j;
}

export async function loadSources() {
  try { Object.assign(SOURCES, await api("/api/sources")); } catch { /* сервер без списка — останутся слои проекта */ }
  const imp = project.raw?.imports;
  if (imp && typeof imp === "object") Object.entries(imp).forEach(([k, s]) => { if (s && typeof s === "object") SOURCES[k] = { title: String(s.title ?? k), kind: String(s.kind ?? "import") }; });
  Object.keys(project.data).filter(k => k.startsWith("ogd.") && !SOURCES[k]).forEach(k => { SOURCES[k] = { title: project.data[k].title, kind: "gisogd" }; });
}

/* ---------- граница территории ---------- */
export const terrArea = () => project.territory ? sizeOf(project.territory)[1] : 0;   // м² в МСК, как площадь объектов

/* opt.keep — правка вершин: вид карты остаётся. Граница хранится в файле как GeoJSON Feature без свойств. */
export function setTerritory(feature, opt = {}) {
  if (!feature?.geometry) return;
  project.territory = markRaw({ type: "Feature", properties: {}, geometry: feature.geometry });
  if (!opt.keep) mapApi.fitExtent?.(turf.bbox(project.territory));
}

export const EXAMPLE = [[37.5195, 55.7895], [37.5305, 55.7895], [37.5305, 55.7955], [37.5195, 55.7955], [37.5195, 55.7895]];
export function exampleTerritory() {
  setTerritory(turf.polygon([EXAMPLE]));
  notice.value = `Граница-пример: ${fmt(terrArea() / 1e4, 2)} га`;
}

const polysOf = f => /Polygon/.test(f?.geometry?.type || "");
export function unionAll(fs) {
  fs = fs.filter(polysOf); if (!fs.length) return null; if (fs.length === 1) return fs[0];
  return safe(() => turf.union(turf.featureCollection(fs)))
    || safe(() => turf.union(turf.featureCollection(fs.map(f => turf.truncate(f, { precision: 7, coordinates: 2 })))));
}

/* Граница из выбранных на карте полигонов (участки, кварталы, зона ПЗЗ): их объединение. */
export function territoryFromSelection(items) {
  const u = unionAll(items.map(s => s.f));
  if (!u) { notice.value = "Среди выбранных нет площадных объектов — граница не изменена"; return false; }
  setTerritory(u); notice.value = `Граница — по выбранным объектам (${items.length}): ${fmt(terrArea() / 1e4, 2)} га`;
  return true;
}

const cadOf = f => String(f?.properties?.["Кадастровый номер"] || "").trim();
/* Граница по кадастровым номерам: участки, уже загруженные из ЕГРН, иначе — поиск НСПД по номерам (/api/search/cadastral). */
export async function territoryByNumbers(text) {
  const want = [...new Set(String(text || "").match(/\d+:\d+:\d+:\d+/g) || [])];
  if (!want.length) { notice.value = "Номеров вида 77:01:0001001:123 не найдено"; return false; }
  const have = (project.data["nspd.parcels"]?.fc?.features || []).filter(polysOf);
  let feats;
  if (have.length) {
    const got = want.map(k => have.filter(f => cadOf(f) === k)), miss = want.filter((k, i) => !got[i].length);
    if (miss.length) { notice.value = `Нет среди загруженных участков: ${miss.join(", ")}. Граница не изменена`; return false; }
    feats = got.flat();
  } else {
    busy.value = true;
    try {
      const r = await api("/api/search/cadastral?q=" + encodeURIComponent(want.join(", ")));
      if (r.missing?.length) { notice.value = `Не найдено: ${r.missing.join(", ")}. Граница не изменена`; return false; }
      feats = (r.features || []).filter(polysOf);
      if (!feats.length) { notice.value = "Участки не найдены — граница не изменена"; return false; }
      addParcels(feats);
    } catch (e) { notice.value = (/[а-яё]/i.test(e.message) ? e.message.replace(/[.\s]+$/, "") : "Портал НСПД не ответил") + ". Граница не изменена"; return false; }
    finally { busy.value = false; }
  }
  const u = unionAll(feats); if (!u) { notice.value = "Участки не объединились — граница не изменена"; return false; }
  setTerritory(u); notice.value = `Граница — по участкам (${want.length}): ${fmt(terrArea() / 1e4, 4)} га`;
  return true;
}
/* участки, найденные по номерам, ложатся в слой «Земельные участки (ЕГРН)» без повторов (web/app.js addParcels) */
export function addParcels(feats) {
  const k = "nspd.parcels", prev = project.data[k], have = prev?.fc?.features || [];
  const seen = new Set(have.flatMap(f => [f.properties?._key, cadOf(f)]).filter(Boolean));
  const add = feats.filter(f => { const a = [f.properties?._key, cadOf(f)].filter(Boolean); if (a.some(x => seen.has(x))) return false; a.forEach(x => seen.add(x)); return true; })
    .map(f => cadOf(f) ? { ...f, properties: { ...f.properties, _key: cadOf(f) } } : f);
  if (!add.length && prev) return;
  const title = prev?.title || SOURCES[k]?.title || "Земельные участки (ЕГРН)";
  project.data[k] = { ...(prev || {}), title, source: prev?.source || "НСПД (nspd.gov.ru), поиск по кадастровому номеру", fetched_at: prev?.fetched_at || today(),
    fc: { type: "FeatureCollection", features: [...have, ...add] }, original: { type: "FeatureCollection", features: [...(prev?.original?.features || prev?.fc?.features || []), ...add] }, history: prev?.history || [] };
  ensureLayer(k, title); touchData();
}

const b64 = buf => { let s = ""; const u = new Uint8Array(buf); for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); };
export const localSys = ref("msk");    // в какой системе файлы в метрах: «МСК (как в QGIS)» или «ГИС ОГД»
const filesBody = async files => ({ local: localSys.value, files: await Promise.all(files.map(async f => ({ name: f.name, b64: b64(await f.arrayBuffer()) }))) });
export const FILE_ACCEPT = ".dxf,.dwg,.geojson,.json,.kml,.kmz,.zip,.shp,.dbf,.prj,.cpg,.shx";

/* Граница из файла: самый большой полигон или замкнутая (концы ближе 0,5 м) полилиния. */
export async function importBoundary(files) {
  if (!files.length) return false;
  busy.value = true;
  try {
    const j = await api("/api/import/files", await filesBody(files));
    const closed = c => c.length > 3 && turf.distance(c[0], c[c.length - 1]) * 1000 < 0.5;
    const polys = j.layers.flatMap(l => l.features.features).flatMap(f => {
      const g = f.geometry; if (!g) return [];
      if (g.type === "Polygon") return [safe(() => turf.polygon(g.coordinates))].filter(Boolean);
      if (g.type === "MultiPolygon") return g.coordinates.map(c => safe(() => turf.polygon(c))).filter(Boolean);
      const ls = g.type === "LineString" ? [g.coordinates] : g.type === "MultiLineString" ? g.coordinates : [];
      return ls.filter(closed).map(c => safe(() => turf.polygon([[...c.slice(0, -1), c[0]]]))).filter(Boolean);
    });
    if (!polys.length) throw new Error("в файле нет замкнутых контуров");
    polys.sort((a, b) => turf.area(b) - turf.area(a));
    setTerritory(polys[0]);
    notice.value = `Граница из файла «${files[0].name}»: ${fmt(terrArea() / 1e4, 2)} га${polys.length > 1 ? `; взят самый большой из ${polys.length} контуров` : ""}`;
    return true;
  } catch (e) { notice.value = "Граница не прочитана: " + e.message; return false; }
  finally { busy.value = false; }
}

/* ---------- область загрузки: рамки листов альбома и граница территории с запасом 60 м ---------- */
const SCALES = [500, 1000, 2000, 2500, 3000, 4000, 5000, 7500, 10000, 15000, 20000, 25000, 50000, 100000, 200000, 500000, 1000000];
const FRAME_MM = { A3: [275, 224], A1: [636, 521] };
const PAPER = { BA4: [297, 210], BA3: [420, 297], BA2: [594, 420], BA1: [841, 594], BA0: [1189, 841] };
const SLIDE = { P: [338.67, 190.5], PA4: [297, 210], PA3: [420, 297], PA2: [594, 420] };
/* рамка карты листа в мм — как frameMM в web/sheets.js */
function frameMM(s) {
  if (s.rect) return [s.rect[2], s.rect[3]];
  if (s.size in PAPER) { const [a, b] = PAPER[s.size]; return (s.orient === "P" ? [b, a] : [a, b]).map(v => v * 0.96); }
  if (!(s.size in SLIDE)) return FRAME_MM[s.size] || FRAME_MM.A3;
  const [w, h] = SLIDE[s.size], k = w / SLIDE.P[0], col = w < 500 ? 80 : 110, mw = w - 14 * k - col - 6, mh = h - 34 * k;
  if (s.part === "half") return [(mw - 6) / 2, mh - 11];
  if (s.kind === "photos" || s.part === "photo") return [mw * 0.47, mh];
  return [mw, mh];
}
function autoScale(frame, bb) {
  if (!bb) return 2000;
  const [w, s, e, n] = bb, mx = (e - w) * 111320 * Math.cos((s + n) / 2 * Math.PI / 180), my = (n - s) * 110540;
  const need = Math.max(mx / frame[0], my / frame[1]) * 1000 * 1.08;
  return SCALES.find(v => v >= need) || SCALES[SCALES.length - 1];
}
/* прямоугольник листа в долготе и широте: центр листа или центр границы, масштаб листа или подобранный по границе */
function frameBox(s, tb, tc) {
  const f = frameMM(s), c = s.center || tc; if (!c) return null;
  const sc = s.scale || autoScale(f, tb), k = 1 / Math.cos(c[1] * Math.PI / 180);
  const hx = f[0] / 2 / 1000 * sc, hy = f[1] / 2 / 1000 * sc;               // половина рамки на местности, м
  const dLon = hx / 111320 * k, dLat = hy / 110540;
  return [c[0] - dLon, c[1] - dLat, c[0] + dLon, c[1] + dLat];
}
const MSK = globalThis.MSK || mskMod.default || mskMod;
/* рамка (центр — долгота и широта, стороны w × h — метры МСК, как рамка вида) → прямоугольник в долготе и широте */
export function frameBbox(f) {
  const ll = cornersM(MSK.fromWgs(f.center), f.w, f.h).map(m => MSK.toWgs(m));
  return [Math.min(...ll.map(c => c[0])), Math.min(...ll.map(c => c[1])), Math.max(...ll.map(c => c[0])), Math.max(...ll.map(c => c[1]))];
}
/* прямоугольник в долготе и широте → рамка в метрах МСК */
export function bboxFrame(b) {
  const a = MSK.fromWgs([b[0], b[1]]), c = MSK.fromWgs([b[2], b[3]]);
  return { center: MSK.toWgs([(a[0] + c[0]) / 2, (a[1] + c[1]) / 2]).map(v => +v.toFixed(7)), w: Math.round(Math.abs(c[0] - a[0])), h: Math.round(Math.abs(c[1] - a[1])), aspect: "free" };
}
/* Область загрузки — рамка, как рамки видов (одна логика, как в QGIS: охват выгрузки задаётся той же рамкой, что и карта
   макета). Своя (project.raw.cover — рамка { center, w, h }) — её сдвинули или растянули на карте; иначе сама: граница
   с запасом 60 м, рамки видов и листы альбома с картой (не ТЭП, не титул, не фото, не готовая вёрстка); ни видов, ни
   листов — лист А3 вокруг границы. Рамка листа с подбором масштаба по схеме района считается здесь проще: по своему центру и масштабу. */
export const coverOwn = () => !!project.raw?.cover?.center;
export function autoCoverBox() {
  const t = project.territory, tb = t ? turf.bbox(t) : null, tc = t ? turf.centroid(t).geometry.coordinates : null;
  const own = (project.raw?.album?.sheets || []).filter(s => !["tep", "title", "photos"].includes(s.kind) && !s.fit && !s.panels && !s.frozen);
  const vs = project.views.filter(v => v.frame?.center).map(v => frameBbox(v.frame));
  const bs = [...(own.length || vs.length ? own : t ? [{ size: "A3" }] : []).map(s => frameBox(s, tb, tc)).filter(Boolean), ...vs, ...(t ? [turf.bbox(turf.buffer(t, 60, { units: "meters" }))] : [])];
  if (!bs.length) return null;
  return [Math.min(...bs.map(b => b[0])), Math.min(...bs.map(b => b[1])), Math.max(...bs.map(b => b[2])), Math.max(...bs.map(b => b[3]))];
}
export function coverBox() { return coverOwn() ? frameBbox(project.raw.cover) : autoCoverBox(); }
export const coverFrame = () => { if (coverOwn()) return project.raw.cover; const b = autoCoverBox(); return b ? bboxFrame(b) : null; };
/* своя область загрузки (рамка) или null — снова сама по границе, видам и листам */
export function setCover(f) {
  if (f) project.raw.cover = { center: f.center, w: f.w, h: f.h }; else delete project.raw.cover;
  coverRev.value++; markDirty();
}
export function coverText() {
  const b = coverBox(); if (!b) return "Нарисуйте границу территории — данные загружаются на неё, на рамки видов и листов.";
  const own = coverOwn(), sheets = (project.raw?.album?.sheets || []).length, views = project.views.some(v => v.frame?.center);
  const km = (b[2] - b[0]) * 111.32 * Math.cos((b[1] + b[3]) / 2 * Math.PI / 180), kmy = (b[3] - b[1]) * 110.54;
  const where = own ? "вашу рамку" : sheets || views ? "границу, рамки видов и листов" : "рамку листа А3 вокруг границы";
  const tail = own ? "Синюю рамку на карте можно сдвинуть и растянуть за углы." : "Синяя рамка на карте ставится сама; сдвиньте или растяните её — станет вашей.";
  return `${project.territory ? `Площадь ${fmt(terrArea() / 1e4, 2)}\u00a0га. ` : ""}Данные загружаются на ${where}: ${fmt(km, 1)}\u00a0×\u00a0${fmt(kmy, 1)}\u00a0км. ${tail}`;   // размер не рвётся на две строки (владелец 09.10.2026)
}

/* ---------- слои: место в списке и оформление по умолчанию (web/layers.js) ---------- */
const PREFERRED = ["gisogd.red_lines", "gisogd.demolition", "egko.addresses", "egko.fences", "relief.contours",
  "sit.rail", "egko.buildings", "nspd.buildings", "yandex.buildings", "osm.buildings", "sit.buildings",
  "yandex.transport", "yandex.parking", "osm.social", "yandex.roads", "osm.roads", "egko.paths", "yandex.road_edges",
  "gisogd.okn", "nspd.zouit", "gisogd.zouit", "gisogd.airfield", "gisogd.szz", "gisogd.vodookhr", "gisogd.ppt", "gisogd.pmt", "gisogd.agr", "gisogd.gpzu", "gisogd.krt",
  "nspd.parcels", "calc.uds_ya", "calc.uds_osm", "calc.uds_sit", "sit.roads_hd", "sit.roads", "sit.water", "sit.green", "yandex.hd_roads", "egko.roads", "egko.water_labels", "egko.place_labels", "egko.water", "osm.water", "yandex.water", "egko.green", "yandex.green",
  "gisogd.admin", "gisogd.pzz_zones", "gisogd.pzz_sub", "gisogd.func_zones", "gisogd.func_zones_tinao", "osm.landuse", "yandex.landuse"];
const OWN = {
  "nspd.parcels": { fill: "#ffffff", stroke: "#7d8288", width: 0.8, opacity: 0 },
  "calc.uds_sit": { fill: "#d5dae0", stroke: "#9ea7b1", width: 0, opacity: 1, minDen: 7500 },
  "yandex.green": { fill: "#cfe4b3", stroke: "#9cbf80", width: 0, opacity: 0.7 },
  "yandex.water": { fill: "#bcd8ee", stroke: "#78aee6", width: 0, opacity: 1 },
  "yandex.parking": { fill: "#5b7bb0", stroke: "#ffffff", width: 0.6, opacity: 1 },
  "yandex.transport": { fill: "#7a5c99", stroke: "#ffffff", width: 0.8, opacity: 1 },
};
const geomOf = fc => { const g = fc?.features?.find(f => f.geometry)?.geometry?.type || ""; return /Point/.test(g) ? "point" : /Line/.test(g) ? "line" : "poly"; };
const defaultStyle = (key, fc) => fullStyle(OWN[key] || (fc.features.some(f => f.properties?._lt) ? { mode: "lgr" } : { fill: CAT[project.layers.length % CAT.length], stroke: "#3d3d3d" }));
const rank = k => { const i = PREFERRED.indexOf(k); return i < 0 ? -1 : i; };

/* «Упорядочить слои» (web/layers.js tidyLayers): выгрузки встают по опорному порядку (свои слои и импорт — сверху, как
   были), из нескольких слоёв застройки остаётся видимым один. Ничего не удаляется. */
const BUILDINGS = ["egko.buildings", "nspd.buildings", "yandex.buildings", "osm.buildings"];
export function tidyLayers() {
  const L = project.layers, order = L.map((l, i) => [l, i]).sort((a, b) => (rank(a[0].key) - rank(b[0].key)) || (a[1] - b[1])).map(x => x[0]);
  L.splice(0, L.length, ...order);
  const on = BUILDINGS.map(k => lyr(k)).filter(l => l?.visible), hidden = on.slice(1).map(l => { l.visible = false; return l.title; });
  normGroups(); markDirty();
  notice.value = `Слои упорядочены как на опорном плане.${hidden.length ? ` Застройка — «${on[0].title}»; выключены повторы: ${hidden.map(t => `«${t}»`).join(", ")}.` : ""}`;
}

/* Слой для данных: есть — тот же; нет — новый на своём месте: импорт и свои — наверх, выгрузки — по опорному порядку. */
export function ensureLayer(key, title) {
  let l = lyr(key); if (l) return l;
  const fc = project.data[key]?.fc || { features: [] };
  l = { key, title: title || project.data[key]?.title || key, geom: geomOf(fc), visible: true, layerOpacity: 1, open: false, group: null, style: defaultStyle(key, fc) };
  const r = rank(key), L = project.layers, at = r < 0 ? 0 : L.findIndex(x => rank(x.key) > r);
  L.splice(at < 0 ? L.length : at, 0, l);
  if (!currentId.value) currentId.value = key;
  normGroups();
  return lyr(key);
}

/* ---------- выгрузка источников ---------- */
const clean = p => Object.fromEntries(Object.entries(p || {}).filter(([k]) => !k.startsWith("_")));
const keepUid = (fresh, cur) => { const u = cur?.properties?._uid; return !u || fresh?.properties?._uid === u ? fresh : { ...fresh, properties: { ...(fresh.properties || {}), _uid: u } }; };
/* Повторная выгрузка: сравнение с прошлой по ключу объекта источника (_key) и слияние с ручной правкой — ваша правка
   сильнее новой версии источника, удалённое вами остаётся удалённым, нарисованное остаётся (web/app.js mergeDownload). */
export function mergeDownload(key, prev, fc, bb) {
  const canon = list => key === "nspd.parcels" ? list.map(f => cadOf(f) && f.properties?._key !== cadOf(f) ? { ...f, properties: { ...f.properties, _key: cadOf(f) } } : f) : list;
  fc = { ...fc, features: canon(fc.features) };
  const prevOrig = typeof prev.original === "object" && prev.original ? prev.original : prev.fc;
  const orig = { ...prevOrig, features: canon(prevOrig?.features || []) };
  const sig = f => JSON.stringify([f.geometry, clean(f.properties)]);
  const byKey = list => new Map(list.filter(f => f.properties?._key).map(f => [f.properties._key, f]));
  const fb = f => safe(() => turf.bbox(f));
  const hits = (f, r) => { const b = fb(f); return !!b && !(b[2] < r[0] || b[0] > r[2] || b[3] < r[1] || b[1] > r[3]); };
  const inNew = f => !bb || hits(f, bb), oldCover = prev.bbox || null;
  const keepOut = bb ? orig.features.filter(f => !inNew(f)) : [];
  const outKeys = new Set(keepOut.map(f => f.properties?._key).filter(Boolean));
  const oldF = orig.features.filter(f => !outKeys.has(f.properties?._key)), oldBy = byKey(oldF), newBy = byKey(fc.features);
  const cur = canon(prev.fc?.features || []), curBy = byKey(cur);
  if (!byKey(orig.features).size || (!newBy.size && fc.features.length)) {
    const drawn = cur.filter(f => !f.properties?._key);
    return drawn.length ? { fc: { type: "FeatureCollection", features: fc.features.concat(drawn) }, text: `слой заменён новой выгрузкой, нарисованные вами объекты (${drawn.length}) сохранены`, mark: new Set(), counts: {} } : null;
  }
  const added = [...newBy.keys()].filter(k => !oldBy.has(k) && !outKeys.has(k) && (!oldCover || hits(newBy.get(k), oldCover))), removed = [...oldBy.keys()].filter(k => !newBy.has(k));
  const changed = [...newBy.keys()].filter(k => oldBy.has(k) && sig(oldBy.get(k)) !== sig(newBy.get(k)));
  const mine = cur.filter(f => f.properties?._edited && f.properties._key && newBy.has(f.properties._key));
  const gone = new Set([...oldBy.keys()].filter(k => !curBy.has(k)));
  const drawn = cur.filter(f => !f.properties?._key);
  const outside = cur.filter(f => outKeys.has(f.properties?._key));
  fc = { ...fc, features: fc.features.filter(f => !outKeys.has(f.properties?._key)) };
  const srcFields = new Set(fc.features.slice(0, 500).flatMap(f => Object.keys(f.properties || {})));
  const own = [...new Set(cur.slice(0, 500).flatMap(f => Object.keys(f.properties || {})))].filter(k => !srcFields.has(k) && !k.startsWith("_"));
  const orphan = cur.filter(f => f.properties?._edited && f.properties._key && !newBy.has(f.properties._key) && !outKeys.has(f.properties._key)).map(f => ({ ...f, properties: { ...f.properties, "Нет в источнике": "да" } }));
  const out = fc.features.filter(f => !gone.has(f.properties?._key)).map(f => {
    const c = curBy.get(f.properties?._key); if (c?.properties._edited) return c;
    if (!c) return f; if (!own.length) return keepUid(f, c);
    const p = { ...f.properties }; own.forEach(k => { if (c.properties[k] != null) p[k] = c.properties[k]; }); return keepUid({ ...f, properties: p }, c);
  }).concat(outside, drawn, orphan);
  const conflict = mine.filter(f => changed.includes(f.properties._key)).length;
  const parts = [`+${added.length} новых`, `−${removed.length} исчезло`, `${changed.length} изменились`];
  if (mine.length) parts.push(`ваши правки (${mine.length}) сохранены${conflict ? `, из них ${conflict} изменились и в источнике — сверьте` : ""}`);
  if (gone.size) parts.push(`удалённые вами (${gone.size}) не вернулись`);
  if (orphan.length) parts.push(`правленные вами, но исчезнувшие из источника (${orphan.length}) оставлены с пометкой «Нет в источнике»`);
  if (outside.length) parts.push(`вне новой рамки оставлено как было: ${outside.length}`);
  return { fc: { type: "FeatureCollection", features: out }, original: { type: "FeatureCollection", features: fc.features.concat(keepOut) }, text: parts.join(", "), mark: new Set([...added, ...changed]),
    counts: { added: added.length, removed: removed.length, changed: changed.length } };
}

/* Один слой портала бывает под двумя ключами (подборка `gisogd.gpzu` и слой каталога `ogd.gpzu`): перевыгрузка идёт в тот,
   что уже в проекте. */
function sameLayerKey(k) {
  if (project.data[k]) return k;
  const code = k.startsWith("ogd.") ? k.slice(4) : SOURCES[k]?.code; if (!code) return k;
  return ["ogd." + code, ...Object.keys(SOURCES).filter(x => SOURCES[x].code === code)].find(x => x !== k && project.data[x]) || k;
}
function stepText(x) {
  const mb = v => fmt(v / 1e6, v < 1e7 ? 1 : 0);
  if (x.stage === "tiles") return { detail: `тайлы ${fmt(x.got)} из ${fmt(x.total)}`, pct: x.total ? x.got / x.total : null };
  if (x.stage === "cells") return { detail: `часть ${x.got + 1} из ${x.total}`, pct: x.total ? x.got / x.total : null };
  if (x.stage === "parse") return { detail: "разбор ответа", pct: null };
  if (x.stage === "index") return { detail: "раскладка по сетке", pct: null };
  if (!x.got) return { detail: "запрос к порталу", pct: null };
  return x.total ? { detail: `${mb(x.got)} из ${mb(x.total)} МБ`, pct: x.got / x.total } : { detail: `${mb(x.got)} МБ`, pct: null };
}
const jobItem = k => job.items.find(i => i.key === k);
function dlStatus(pr, names) {
  const mb = v => fmt(v / 1e6, v < 1e7 ? 1 : 0), ya = pr.filter(x => x.stage === "tiles"), big = pr.filter(x => x.stage !== "tiles");
  const what = x => x.stage === "cells" ? `часть ${x.got + 1} из ${x.total}` : x.stage === "parse" ? "разбор" : x.stage === "index" ? "раскладка по сетке"
    : !x.got ? "запрос к порталу" : x.total ? `${Math.round(x.got / x.total * 100)} % · ${mb(x.got)} МБ из ${mb(x.total)} МБ` : `${mb(x.got)} МБ`;
  const parts = big.map(x => `${x.of > 1 ? `${x.nth} из ${x.of}: ` : ""}${x.title}: ${what(x)}`);
  if (ya.length) parts.push(`Яндекс: тайлы ${ya[0].got} из ${ya[0].total}`);
  if (!parts.length && names.length) parts.push(`${names.slice(0, 3).join(", ")}${names.length > 3 ? ` и ещё ${names.length - 3}` : ""}: ждём ответ портала`);
  return parts.join("; ");
}

/* Выгрузка по прямоугольнику: OSM, ЕГКО и Яндекс — отдельными запросами (отвечают дольше), остальное — одним. */
export async function loadKeys(keys, bb) {
  if (!bb || !keys.length || loading.value) return;
  const [w, s, e, n] = bb; keys = [...new Set(keys.map(sameLayerKey))];
  const osm = keys.filter(k => k.startsWith("osm.")), egko = keys.filter(k => k.startsWith("egko.")), yandex = keys.filter(k => k.startsWith("yandex.")),
    rest = keys.filter(k => !/^(osm|egko|yandex)\./.test(k)), parts = [rest, osm, egko, yandex].filter(p => p.length);
  const pending = new Set(parts), reports = [], fresh = [], empty = [], same = [], my = project.raw;   // открыт другой проект — выгрузка не для него
  let nLayers = 0, dropped = false;
  Object.keys(ERRORS).forEach(k => delete ERRORS[k]);
  const names = () => [...pending].flat().map(k => SOURCES[k]?.title || project.data[k]?.title || k);
  loading.value = `Выгрузка: ${names().slice(0, 3).join(", ")}${names().length > 3 ? ` и ещё ${names().length - 3}` : ""}`;
  job.items = keys.map(k => ({ key: k, title: SOURCES[k]?.title || project.data[k]?.title || k, state: "run", detail: "запрос к порталу", pct: null, n: null }));
  job.t0 = Date.now(); job.t1 = 0;
  const poll = setInterval(async () => {
    try {
      const raw = await api("/api/progress"), pr = Object.values(raw);
      if (pending.size) loading.value = dlStatus(pr, names()) || loading.value;
      for (const [k, x] of Object.entries(raw)) { const it = jobItem(k); if (it?.state === "run") Object.assign(it, stepText(x)); }
    } catch { /* ход не пришёл — подождём */ }
  }, 800);
  const terr = project.territory ? turf.bbox(project.territory) : null;
  const ec = project.raw.emptyCover ||= {};
  await Promise.all(parts.map(async part => {
    try {
      const r = await api("/api/fetch", { bbox: [w, s, e, n], sources: part, ...(terr ? { territory: terr } : {}) });
      if (my !== project.raw) { dropped = true; return; }
      Object.assign(ERRORS, r.errors || {});
      for (const [k, v] of Object.entries(r.layers || {})) {
        if (!project.data[k] && !v.features.features.length) {           // пустая первая выгрузка слой не заводит
          Object.assign(jobItem(k) || {}, { state: "empty", detail: "нет объектов в области", pct: null });
          empty.push(v.title); const p0 = ec[k];
          ec[k] = p0 ? [Math.min(p0[0], w), Math.min(p0[1], s), Math.max(p0[2], e), Math.max(p0[3], n)] : [w, s, e, n]; continue;
        }
        const prev = project.data[k], m = prev?.fc ? mergeDownload(k, prev, v.features, [w, s, e, n]) : null;
        const pb = prev?.bbox || ec[k], cover = pb ? [Math.min(pb[0], w), Math.min(pb[1], s), Math.max(pb[2], e), Math.max(pb[3], n)] : [w, s, e, n];
        const { features, ...meta } = v;
        project.data[k] = { ...meta, title: prev?.title || v.title, fc: m ? m.fc : features, original: m?.original || features, bbox: cover,
          history: [...(prev?.history || []), { date: v.fetched_at, n: features.features.length, ...(m?.counts || {}) }] };
        SOURCES[k] ||= { title: v.title, kind: k.split(".")[0] };
        const l = ensureLayer(k, v.title);
        if (l.style.mode === "cat") { const st = JSON.parse(JSON.stringify(l.style)); assignCats(st, project.data[k].fc, true); l.style = fullStyle(st); }
        nLayers++;
        Object.assign(jobItem(k) || {}, { state: "done", n: project.data[k].fc.features.length, pct: null,
          detail: m ? (m.counts.added || m.counts.removed || m.counts.changed ? `+${m.counts.added} −${m.counts.removed} ~${m.counts.changed}` : "без изменений") : "" });
        if (m) {
          if (m.counts.added || m.counts.removed || m.counts.changed || !/^\+0 новых, −0 исчезло, 0 изменились$/.test(m.text)) reports.push(`«${v.title}»: ${m.text}`); else same.push(v.title);
          project.data[k].fc.features.forEach(f => { if (m.mark.has(f.properties?._key) && f.properties._uid) fresh.push({ key: k, uid: f.properties._uid }); });
        }
      }
    } catch (err) { if (my === project.raw) part.forEach(k => { ERRORS[k] = err.message; }); }
    part.forEach(k => {           // слой без ответа: ошибка портала или пусто
      const it = jobItem(k); if (!it || it.state !== "run") return;
      Object.assign(it, ERRORS[k] ? { state: "error", detail: ERRORS[k], pct: null } : { state: "empty", detail: "нет объектов в области", pct: null });
    });
    pending.delete(part); touchData();
  }));
  clearInterval(poll); loading.value = ""; job.t1 = Date.now();
  if (dropped) { notice.value = "Выгрузка для прежнего проекта отброшена: пока она шла, открыт другой проект"; return; }
  markDirty(); portalStyles();
  if (fresh.length) setSel(fresh);
  const ne = Object.keys(ERRORS).length, why = Object.entries(ERRORS).slice(0, 3).map(([k, m]) => `${SOURCES[k]?.title || k}: ${m}`).join("; ");
  notice.value = `Загружено слоёв: ${nLayers}${ne ? `, с ошибкой: ${ne} (${why})` : ""}.${empty.length ? ` Нет объектов в области: ${empty.join(", ")}.` : ""}`
    + `${reports.length ? " Перевыгрузка — " + reports.join("; ") + (fresh.length ? ". Новое и изменённое выделено." : ".") : ""}${same.length ? ` Без изменений в источнике: ${same.length}.` : ""}`;
}

/* Оформление слоёв портала ГИС ОГД — как на карте портала (/api/ogd_all/styles, как web/layers.js portalStyles). */
export async function portalStyles() {
  const all = project.layers.filter(l => l.key.startsWith("ogd."));
  if (!all.length) return;
  const field = l => { for (const f of project.data[l.key]?.fc?.features.slice(0, 50) || []) { const p = f.properties, v = p.zonelineco ?? p.textlineco; if (v != null && v !== "" && +v) return v; } return null; };
  let r; try { r = await api("/api/ogd_all/styles", { layers: Object.fromEntries(all.map(l => [l.key.slice(4), [l.geom, field(l)]])) }); } catch { return; }
  const rev = l => r.rev?.[l.key.slice(4)] || 1, done = l => l.style.portal === true ? 1 : l.style.portal || 0;
  all.filter(l => done(l) < rev(l)).forEach(l => {
    const s = r.styles?.[l.key.slice(4)]; if (!s || !Object.keys(s).length) { l.style = fullStyle({ ...l.style, portal: rev(l) }); return; }
    const lgr = l.geom === "line" && project.data[l.key]?.fc?.features.some(f => f.properties._lt || f.properties._miss);
    let st = fullStyle({ ...s, ...(lgr ? { mode: "lgr" } : {}), portal: rev(l) });
    if (st.mode === "cat") assignCats(st, project.data[l.key]?.fc, true);
    l.style = st;
  });
}

/* ---------- импорт файлов: DXF, DWG, GeoJSON, KML/KMZ, Shapefile — кнопкой или перетаскиванием на карту ---------- */
export async function importFiles(files) {
  if (!files.length) return;
  busy.value = true;
  try {
    const j = await api("/api/import/files", await filesBody(files));
    const imports = project.raw.imports ||= {}, msgs = [], keys = [];
    for (const lay of j.layers) {
      let key = "import:" + lay.name + "." + lay.format.toLowerCase(), title = `${lay.name} (${lay.format})`, n = 2;
      while (project.data[key]) { key = `import:${lay.name} (${n}).${lay.format.toLowerCase()}`; title = `${lay.name} (${n}) (${lay.format})`; n++; }
      SOURCES[key] = imports[key] = { title, kind: "import" };
      project.data[key] = { title, source: "файл " + lay.name + "." + lay.format.toLowerCase(), fetched_at: today(), notes: lay.notes, fc: lay.features };
      ensureLayer(key, title); keys.push(key);
      msgs.push(`${title}: ${lay.features.features.length} об.${lay.notes?.length ? ` (${lay.notes.join("; ")})` : ""}`);
    }
    touchData(); markDirty();
    setTimeout(() => mapApi.zoomTo(keys), 50);
    notice.value = "Импорт: " + msgs.join(" · ");
  } catch (e) { notice.value = "Файл не прочитан: " + e.message; }
  finally { busy.value = false; }
}

/* ---------- сводка существующего положения в границе (web/app.js existingSummary) ---------- */
export function existingSummary() {
  const t = project.territory; if (!t) return [];
  const R = window.Roles; R?.use?.({ DATA: project.data, LYR: project.layers }); R?.load?.();
  const area = terrArea(), k = R?.existingBuildingsKey?.() ?? (project.data["nspd.buildings"] ? "nspd.buildings" : project.data["osm.buildings"] ? "osm.buildings" : null);
  const inside = f => safe(() => turf.booleanPointInPolygon(turf.pointOnFeature(f), t));
  const rows = [["Территория", fmt(area / 1e4, 2) + " га"]];
  if (k && project.data[k]?.fc) {
    const B = project.data[k].fc.features.filter(f => f.geometry && inside(f)), fl = f => { const v = +f.properties["Этажность"]; return v > 0 ? v : 1; };
    const a = f => safe(() => sizeOf(f)[1]) || 0, fp = B.reduce((s, f) => s + a(f), 0), spp = B.reduce((s, f) => s + a(f) * fl(f), 0);
    rows.push(["Зданий в границе", B.length + (k === "osm.buildings" ? " (OSM)" : "")], ["СПП существующая", fmt(spp / 1000, 1) + " тыс. м²"],
      ["Плотность", fmt(spp / 1000 / (area / 1e4), 1) + " тыс. м²/га"], ["Застроенность", fmt(fp / area * 100, 1) + " %"]);
  }
  if (project.data["nspd.parcels"]?.fc) rows.push(["Участков ЕГРН", project.data["nspd.parcels"].fc.features.filter(f => f.geometry && inside(f)).length]);
  return rows;
}

/* выбор источников проекта (поле checked файла): окно «Исходные данные» помнит отмеченное */
export const checked = () => new Set(project.raw?.checked || ["nspd.parcels", "nspd.buildings", "osm.roads", "osm.buildings", "osm.water", "osm.landuse", "gisogd.szz", "gisogd.vodookhr"]);
export function keepChecked(sel) { project.raw.checked = [...sel]; markDirty(); }

/* ---------- ФГИС ТП: документы территориального планирования, чей охват накрывает территорию → их слои (web/app.js fgFind,
   fgSearch, fgPick, fgLoad). Портал отдаёт документ целиком; пустой в области слой не заводится; повторная загрузка — как
   перевыгрузка (ваши правки, нарисованное и имя слоя сохраняются). ---------- */
export const FG = reactive({ docs: null, uin: "", layers: null, sel: new Set(), msg: "", q: "" });
export async function fgFind() {
  if (!project.territory) return;
  FG.q = ""; const [w, s, e, n] = turf.bbox(project.territory); FG.msg = "Каталог ФГИС ТП: первый раз около 10 МБ…"; busy.value = true;
  try { FG.docs = (await api(`/api/fgistp/docs?bbox=${[w, s, e, n].join(",")}`)).docs; FG.uin = ""; FG.layers = null; FG.sel = new Set();
    FG.msg = FG.docs.length ? "Самые местные документы — сверху. Выберите документ, затем слои." : "Документов с охватом этой территории нет."; }
  catch (err) { FG.msg = "ФГИС ТП не ответила: " + err.message; } finally { busy.value = false; }
}
export async function fgSearch(q) {
  FG.q = q.trim(); if (!FG.q) return project.territory ? fgFind() : undefined;
  if (FG.q.length < 3) return;
  FG.msg = "Поиск в каталоге ФГИС ТП…"; busy.value = true;
  try { FG.docs = (await api(`/api/fgistp/docs?q=${encodeURIComponent(FG.q)}`)).docs; FG.uin = ""; FG.layers = null; FG.sel = new Set();
    FG.msg = FG.docs.length ? `Найдено документов: ${FG.docs.length}${FG.docs.length === 100 ? " (первые 100 — уточните запрос)" : ""}. Самые местные — сверху.` : "По такому названию документов нет."; }
  catch (err) { FG.msg = "ФГИС ТП не ответила: " + err.message; } finally { busy.value = false; }
}
export async function fgPick(uin) {
  FG.uin = uin; FG.layers = null; FG.sel = new Set(); if (!uin) return;
  FG.msg = "Состав документа…"; busy.value = true;
  try { FG.layers = (await api(`/api/fgistp/layers?uin=${encodeURIComponent(uin)}`)).layers; FG.msg = `Слоёв в документе: ${FG.layers.length}. Отметьте нужные.`; }
  catch (err) { FG.msg = "Состав документа не получен: " + err.message; } finally { busy.value = false; }
}
export async function fgLoad() {
  const bb = coverBox(); if (!bb || !FG.uin || !FG.sel.size) return;
  FG.msg = "Загрузка слоёв документа: портал отдаёт документ целиком, может занять минуту…"; loading.value = "ФГИС ТП: загрузка слоёв документа"; const my = project.raw;
  try {
    const r = await api("/api/fgistp/fetch", { uin: FG.uin, classids: [...FG.sel], bbox: bb });
    if (my !== project.raw) { FG.msg = "Выгрузка для прежнего проекта отброшена."; return; }
    let n = 0; const reps = [], vals = Object.entries(r.layers || {}), empty = vals.filter(([, v]) => !v.features.features.length).map(([, v]) => v.title.replace("ФГИС ТП: ", ""));
    for (const [k, v] of vals) {
      if (!v.features.features.length) continue;                 // пустой в этой области слой не засоряет список
      SOURCES[k] = (project.raw.imports ||= {})[k] = { title: v.title, kind: "fgistp" };   // в файл — как у рабочей страницы (imports)
      const prev = project.data[k], m = prev?.fc ? mergeDownload(k, prev, v.features) : null;
      if (m) reps.push(`«${prev.title}»: ${m.text}`);
      const { features, ...meta } = v;
      project.data[k] = { ...meta, title: prev?.title || v.title, fc: m ? m.fc : features, original: m?.original || features, history: prev?.history || [] };
      const l = ensureLayer(k, v.title);
      if (l.style.mode === "cat") { const st = JSON.parse(JSON.stringify(l.style)); assignCats(st, project.data[k].fc, true); l.style = fullStyle(st); }
      n += project.data[k].fc.features.length;
    }
    touchData(); markDirty();
    FG.msg = `Загружено слоёв: ${vals.length - empty.length}, объектов в области: ${fmt(n)}.${empty.length ? ` Нет объектов в области: ${empty.join(", ")}.` : ""}${reps.length ? " " + reps.join("; ") + "." : ""}`;
  } catch (err) { FG.msg = "Слои не загружены: " + err.message; } finally { loading.value = ""; }
}

/* ---------- «ГИС ОГД в DXF»: все отмеченные слои портала по рамке листа альбома (как кнопка «ГИС ОГД в DXF» рабочей страницы, app.js runOgd) ----------
   Выгрузка идёт на сервере фоном (/api/ogd_all/start, status, cancel, file): ход — здесь (окно «Данные» и строка состояния), по
   окончании архив DXF (и DWG, если есть конвертер) скачивается сам. req — запрос от albumhost.js ogdDxf: лист (sheet для сервера,
   bbox для подсчёта объектов), где он («листу 3 «…» (A3, 1:2 000)»), имя архива, граница территории, прежний выбор слоёв. */
export const ogd = reactive({ req: null, running: false, done: 0, total: 0, current: "", found: 0, where: "", left: "", msg: "" });
let ogdT = null;
const minText = s => s < 90 ? `${Math.round(s)} с` : `${Math.round(s / 60)} мин`;
async function ogdTick() {
  let st; try { st = await api("/api/ogd_all/status"); } catch { return; }
  if (st.running) {
    const left = st.done ? (Date.now() / 1000 - st.started) / st.done * (st.total - st.done) : 0;
    Object.assign(ogd, { running: true, done: st.done || 0, total: st.total || 0, current: st.current || "", found: st.found || 0, where: st.where || ogd.where || "листу",
      left: left > 5 ? minText(left) : "", msg: st.message || "" });
    return;
  }
  clearInterval(ogdT); ogdT = null;
  const was = ogd.running; ogd.running = false;
  if (!was) return;                                                     // ничего не шло — молчим (проверка при открытии)
  if (!st.file) { notice.value = st.message || "Выгрузка ГИС ОГД остановлена."; return; }
  const a = document.createElement("a"); a.href = "/api/ogd_all/file"; a.download = st.file; document.body.appendChild(a); a.click(); a.remove();
  const miss = (st.errors || []).map(e => "«" + String(e).split(": ")[0] + "»");
  notice.value = `ГИС ОГД готово по ${st.where || ogd.where}: ${plural(st.found || 0, ["слой", "слоя", "слоёв"])}, ${plural(st.objects || 0, ["объект", "объекта", "объектов"])}. `
    + (st.dwg ? "В архиве DWG, DXF" : "В архиве DXF (в AutoCAD — вкладка листа с видовым экраном)") + " и таблицы атрибутов."
    + (miss.length ? ` Портал не отдал: ${miss.slice(0, 2).join(", ")}${miss.length > 2 ? ` и ещё ${miss.length - 2}` : ""}.` : "") + " Файл — в папке загрузок браузера.";
}
export function watchOgd() { clearInterval(ogdT); ogd.running = true; ogdT = setInterval(ogdTick, 1500); ogdTick(); }
/* запуск: codes — коды слоёв портала; занятый сервер («уже идёт») — показываем ход той выгрузки */
export async function startOgd(req, codes) {
  ogd.where = req.where;
  try { await api("/api/ogd_all/start", { sheet: req.sheet, codes, where: req.where, boundary: req.boundary || null, name: req.name }); }
  catch (e) {
    if (/уже идёт|already/i.test(e.message)) { notice.value = "Выгрузка ГИС ОГД уже идёт — показываю её ход. Новая начнётся, когда эта закончится."; watchOgd(); return false; }
    notice.value = "Выгрузка ГИС ОГД не началась: " + e.message; return false;
  }
  notice.value = `Выгрузка всех отмеченных слоёв ГИС ОГД по ${req.where}. Ход — в окне «Данные»; работать можно дальше.`;
  watchOgd(); return true;
}
export async function stopOgd() {
  try { await api("/api/ogd_all/cancel", {}); notice.value = "Остановка: текущий слой дочитывается, потом выгрузка ГИС ОГД встанет."; } catch (e) { notice.value = "Не остановлено: " + e.message; }
}
/* открыли программу во время выгрузки (начатой раньше или в другой вкладке) — показываем её ход */
export function ogdResume() { api("/api/ogd_all/status").then(st => { if (st.running) watchOgd(); }).catch(() => { }); }
