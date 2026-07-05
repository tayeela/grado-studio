// ГРАДО Студия — холст черчения. Мир: метры, ось Y вверх.

const VERSION = "0.28.0";

// любая ошибка интерфейса — на экран, а не молча в консоль
window.addEventListener("error", e => {
  if (/ResizeObserver loop/.test(e.message || "")) return; // безобидное предупреждение браузера
  const el = document.getElementById("errbar");
  if (el) {
    el.textContent = `Ошибка интерфейса (${VERSION}): ${e.message} — ${String(e.filename).split("/").pop()}:${e.lineno}`;
    el.style.display = "block";
  }
});

function on(id, event, fn) {
  const el = document.getElementById(id);
  if (!el) { console.warn("нет элемента #" + id); return; }
  el.addEventListener(event, fn);
}

const cv = document.getElementById("cv");
const ctx = cv.getContext("2d");

// Цвет отрисовки холста из палитры темы (canvas-theme.js). Fallback — если
// tokens/canvas-theme не загрузились (оффлайн-надёжность): прежние значения.
function cvColor(key, fallback) {
  const v = (window.CANVAS_THEME || {})[key];
  return v || fallback;
}

// ---------- модель v2: слои и стили (docs/fixes-geometry-layout.md, шаг 1) ----------
// Стиль — данные (JSON-совместимые): подпись задаётся именем поля, не функцией.
const STYLES_V2 = {
  "func_zone.fill":     { fill: "#faf0bf", stroke: "#b89e59", width: 1,   label_field: "zone_title" },
  "public_zone.fill":   { fill: "#f7c2c9", stroke: "#bf596b", width: 1.2, label_field: "purpose" },
  "restrict.hatch":     { fill: "rgba(245,219,219,.85)", stroke: "#bf5959", width: 1.2, dash: [8, 4], hatch: true },
  "parcel.line":        { stroke: "#8a7a5c", width: 0.8, label_field: "cad_num" },
  "building.fill":      { fill: "#f5c76b", stroke: "#8c6626", width: 1,   label_field: "floors" },
  "red.line.projected": { stroke: "#d91a1a", width: 2.5 },
  "boundary.line":      { stroke: "#1c1c1a", width: 2.5, dash: [14, 5, 4, 5] },
  "social.point":       { fill: "#2f6fde", stroke: "#1d4a9e", width: 1.2 },
  "dimension.line":     { stroke: "#44423c", width: 1 },
};

// Слой — главный объект управления (MODEL-01): id (идентичность) отделён
// от semantic_class (класс классификатора). Порядок массива = порядок
// отрисовки (первый — самый нижний). kind — транспорт схемы атрибутов до
// полного снятия. import_only — слой не выбирается инструментами и не
// перехватывает kind (объекты попадают в него только импортом по layer_id).
const LAYERS_V2 = [
  { id: "project.tp.func_zone", title: "Функциональная зона", kind: "zone",
    semantic_class: "tp.func_zone", geometry_type: "polygon",
    style_id: "func_zone.fill", topology: "coverage", stage: "existing",
    defaults: () => ({ zone_title: "Ж-" + (featuresOnLayer("project.tp.func_zone").length + 1) }) },
  { id: "source.fgistp.func_zones", title: "ФГИС ТП: функц. зоны", kind: "zone",
    semantic_class: "tp.func_zone", geometry_type: "polygon",
    style_id: "func_zone.fill", stage: "existing", source_kind: "fgistp",
    import_only: true, defaults: () => ({}) },
  { id: "project.apo.public_zones", title: "Зона нежилых ОКС", kind: "public",
    semantic_class: "pp.placement_zone", geometry_type: "polygon",
    style_id: "public_zone.fill", stage: "project",
    defaults: () => ({ purpose: "Общественный центр" }) },
  { id: "source.constraints.restrict", title: "Ограничение (ЗОУИТ)", kind: "restrict",
    semantic_class: "terr.restrict", geometry_type: "polygon",
    style_id: "restrict.hatch", stage: "existing",
    defaults: () => ({ kind: "охранная зона" }) },
  { id: "source.nspd.parcels", title: "Земельный участок (ЕГРН)", kind: "parcel",
    semantic_class: "cad.parcel", geometry_type: "polygon",
    style_id: "parcel.line", stage: "existing", source_kind: "nspd",
    defaults: () => ({}) },
  { id: "source.gisogd.func_zones", title: "ГИС ОГД: функц. зоны", kind: "zone",
    semantic_class: "tp.func_zone", geometry_type: "polygon",
    style_id: "func_zone.fill", stage: "existing", source_kind: "gisogd",
    import_only: true, defaults: () => ({}) },
  { id: "source.gisogd.red_lines", title: "ГИС ОГД: красные линии", kind: "redline",
    semantic_class: "pp.red_line", geometry_type: "polyline",
    style_id: "red.line.projected", stage: "existing", source_kind: "gisogd",
    import_only: true, defaults: () => ({}) },
  { id: "source.gisogd.restrict", title: "ГИС ОГД: зоны с особыми условиями", kind: "restrict",
    semantic_class: "terr.restrict", geometry_type: "polygon",
    style_id: "restrict.hatch", stage: "existing", source_kind: "gisogd",
    import_only: true, defaults: () => ({}) },
  { id: "project.apo.buildings", title: "Здание", kind: "building",
    semantic_class: "oks.building", geometry_type: "polygon",
    style_id: "building.fill", stage: "project", tool: "rect",
    defaults: () => ({ floors: 9, purpose: "МКД" }) },
  { id: "project.apo.red_lines", title: "Красная линия", kind: "redline",
    semantic_class: "pp.red_line", geometry_type: "polyline",
    style_id: "red.line.projected", stage: "project",
    defaults: () => ({ radius: 0 }) },
  { id: "project.territory.boundary", title: "Граница территории", kind: "boundary",
    semantic_class: "terr.boundary", geometry_type: "polygon",
    style_id: "boundary.line", stage: "base", defaults: () => ({}) },
  { id: "project.social.objects", title: "Объект социнфраструктуры", kind: "social",
    semantic_class: "social.object", geometry_type: "point",
    style_id: "social.point", stage: "project",
    defaults: () => ({ kind: "ОО+ДОО", capacity: 750 }) },
  { id: "annotation.dimensions", title: "Размер", kind: "dim",
    semantic_class: null, geometry_type: "polyline", style_id: "dimension.line",
    annotation: true, tool: "dim", defaults: () => ({}) },
];
const LAYER_BY_ID = {}, LAYER_BY_KIND = {};
for (const L of LAYERS_V2) {
  L.visible = true;
  LAYER_BY_ID[L.id] = L;
  // import-only слои не становятся дефолтом для kind (иначе нарисованная
  // вручную зона ушла бы в ФГИС-ТП-слой): первый не-import_only выигрывает
  if (!L.import_only && !(L.kind in LAYER_BY_KIND)) LAYER_BY_KIND[L.kind] = L;
}

// ---------- пользовательские слои («+ слой» в панели) ----------
// Типы, которые можно завести отдельным именованным слоем поверх встроенных
// (второй слой того же семантического класса — уже штатный сценарий с
// MODEL-01, см. source.fgistp/source.gisogd рядом с project.*). Границу
// территории и участки ЕГРН не даём дублировать: первая по смыслу
// единственная (сумма её площади — вход ТЭП terr_area), вторые — не
// hand-draw объект, а данные конкретного импорта.
const BASE_KINDS = [
  { kind: "zone", semantic_class: "tp.func_zone", geometry_type: "polygon",
    style_id: "func_zone.fill", label: "Функциональная зона / территория" },
  { kind: "restrict", semantic_class: "terr.restrict", geometry_type: "polygon",
    style_id: "restrict.hatch", label: "Ограничение (ЗОУИТ)" },
  { kind: "building", semantic_class: "oks.building", geometry_type: "polygon",
    style_id: "building.fill", label: "Здание" },
  { kind: "redline", semantic_class: "pp.red_line", geometry_type: "polyline",
    style_id: "red.line.projected", label: "Линия (красная/иная)" },
  { kind: "public", semantic_class: "pp.placement_zone", geometry_type: "polygon",
    style_id: "public_zone.fill", label: "Зона размещения ОКС" },
  { kind: "social", semantic_class: "social.object", geometry_type: "point",
    style_id: "social.point", label: "Точечный объект" },
];
const BASE_KIND_BY_KIND = Object.fromEntries(BASE_KINDS.map(b => [b.kind, b]));
// semantic_class → kind, для восстановления пользовательских слоёв с диска
// (манифест для бэкенда несёт code, не kind — см. userLayersManifest)
const KIND_BY_SEMANTIC_CLASS = Object.fromEntries(BASE_KINDS.map(b => [b.semantic_class, b.kind]));

// prop-дефолты нового объекта — та же логика, что у встроенных слоёв,
// но переиспользуемая (нужна и при создании слоя, и при восстановлении
// после перезагрузки, когда defaults() нельзя было сохранить как функцию)
function defaultsForKind(layerId, kind) {
  switch (kind) {
    case "zone": return { zone_title: "З-" + (featuresOnLayer(layerId).length + 1) };
    case "restrict": return { kind: "ограничение" };
    case "building": return { floors: 9, purpose: "МКД" };
    case "redline": return { radius: 0 };
    case "public": return { purpose: "Общественный центр" };
    case "social": return { kind: "ОО+ДОО", capacity: 750 };
    default: return {};
  }
}

const RU_TO_LAT = { а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e",
  ж: "zh", з: "z", и: "i", й: "y", к: "k", л: "l", м: "m", н: "n", о: "o",
  п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f", х: "h", ц: "c", ч: "ch",
  ш: "sh", щ: "sch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya" };
function slugify(s) {
  const translit = [...s.toLowerCase()].map(ch => RU_TO_LAT[ch] ?? ch).join("");
  return translit.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "sloi";
}
function uniqueLayerId(title) {
  const base = "user." + slugify(title);
  if (!LAYER_BY_ID[base]) return base;
  let n = 2;
  while (LAYER_BY_ID[`${base}-${n}`]) n++;
  return `${base}-${n}`;
}

// создаёт слой в LAYERS_V2/LAYER_BY_ID (id задаётся явно при восстановлении
// с диска — тогда он уже уникален и известен; при создании из UI — null)
function createUserLayer({ kind, title, styleId, id = null }) {
  const base = BASE_KIND_BY_KIND[kind];
  if (!base) throw new Error("неизвестный тип слоя: " + kind);
  const layerId = id || uniqueLayerId(title);
  const L = {
    id: layerId, title, kind: base.kind, semantic_class: base.semantic_class,
    geometry_type: base.geometry_type, style_id: styleId || base.style_id,
    stage: "project", user_created: true, visible: true,
    defaults: () => defaultsForKind(layerId, base.kind),
  };
  LAYERS_V2.push(L);
  LAYER_BY_ID[L.id] = L;
  return L;
}

// манифест пользовательских слоёв для бэкенда (маршрутизация build_project
// не знает layer_id, придуманный на холсте, без этого списка)
function userLayersManifest() {
  return LAYERS_V2.filter(L => L.user_created).map(L => ({
    layer_id: L.id, code: L.semantic_class, title: L.title,
    stage: L.stage, style_id: L.style_id,
  }));
}

function deleteLayer(layer) {
  if (!layer.user_created) {
    alert("Встроенный слой удалить нельзя — можно скрыть (чекбокс) или переименовать");
    return;
  }
  const count = featuresOnLayer(layer.id).length;
  if (count && !confirm(`В слое «${layer.title}» ${count} объект(ов). Удалить слой вместе с ними?`))
    return;
  snapshot();
  state.features = state.features.filter(f => layerOf(f) !== layer);
  LAYERS_V2.splice(LAYERS_V2.indexOf(layer), 1);
  delete LAYER_BY_ID[layer.id];
  if (state.activeLayerId === layer.id) {
    const fallback = LAYERS_V2.find(l => !l.annotation && !l.import_only);
    if (fallback) setActiveLayer(fallback.id);
  }
  if (selectedFeature() && layerOf(selectedFeature()) == null) state.selected = null;
  afterChange();
}

function renameLayer(layer) {
  const next = prompt("Новое имя слоя:", layer.title);
  if (next == null) return;                 // отмена
  const title = next.trim();
  if (!title) return;
  layer.title = title;
  renderLayers(); renderProps(); persist();
}

// Стили выше — встроенный fallback; на старте они переопределяются из
// /api/styles (единый источник styles/default.json — тот же, что PDF и DXF).
async function initStyles() {
  try {
    const r = await fetch("/api/styles");
    if (!r.ok) return;
    const lib = await r.json();
    for (const id of Object.keys(lib)) STYLES_V2[id] = lib[id];
    draw(); renderLayers();
  } catch (e) { /* сервер без /api/styles — холст на встроенных стилях */ }
}

function layerOf(f) { return LAYER_BY_ID[f.layer_id] || LAYER_BY_KIND[f.kind] || null; }
// Эффективный стиль слоя: базовый из библиотеки + пер-слойное переопределение
// оформления (layer.fmt) — как символика слоя в QGIS. Переопределение живёт
// на слое и сохраняется; на PDF/DXF (единый источник styles/default.json) не
// влияет — это оформление именно холста.
function layerStyle(L) {
  if (!L) return {};
  const base = STYLES_V2[L.style_id] || {};
  return L.fmt ? { ...base, ...L.fmt } : base;
}
function styleOf(f) {
  const L = layerOf(f);
  return (f.style_id && STYLES_V2[f.style_id]) || layerStyle(L) || {};
}
// ---------- инструменты: геометрия отдельно, слой отдельно (шаг 2) ----------
// Инструмент создаёт только геометрию; слой и стиль назначает активный слой.
const GEOM_OF_TOOL = { point: "point", polyline: "polyline",
                       polygon: "polygon", rect: "polygon" };
// какую геометрию собирает черчение (rect кликами = контур-полигон, dim — линия)
const TOOL_GEOM = { ...GEOM_OF_TOOL, dim: "polyline" };

function activeLayer() { return LAYER_BY_ID[state.activeLayerId] || null; }

function toolFitsLayer(tool, L) {
  const g = GEOM_OF_TOOL[tool];
  return !g || (!!L && !L.annotation && L.geometry_type === g);
}

function naturalToolFor(L) {
  return L.tool ||
    ({ point: "point", polyline: "polyline", polygon: "polygon" })[L.geometry_type];
}

function styleForDrawing() {
  if (state.tool === "dim") return STYLES_V2["dimension.line"];
  return layerStyle(activeLayer());
}
function labelOf(f) {
  const st = styleOf(f);
  return st.label_field ? f.props[st.label_field] : undefined;
}
function featuresOnLayer(id) {
  return state.features.filter(f => (layerOf(f) || {}).id === id);
}
// объект → формат v2: слой и тип геометрии явно; kind дописывается
// обратно для legacy-объектов (мигратор старых сцен и выгрузок ядра)
function upgradeFeature(f) {
  const L = layerOf(f);
  if (L) { f.layer_id = L.id; if (!f.kind) f.kind = L.kind; }
  f.geometry_type = f.point ? "point" : f.line ? "polyline" : "polygon";
  return f;
}

const state = {
  features: [], tool: "select", selected: null,
  drawing: null, drag: null, pan: null, edit: null, measure: null,
  snapHit: null, guides: [], typed: "", mouse: null,
  view: { k: 1.1, tx: 120, ty: 0 },
  undo: [], redo: [], nextId: 1,
  gridShow: true, gridSnap: true, osnap: true, gridMode: "auto",
  layers: LAYER_BY_ID, styles: STYLES_V2,   // модель v2 (видимость — layer.visible)
  activeLayerId: "project.territory.boundary",  // куда чертят геом-инструменты
  sources: [],                    // журнал источников (снимки НСПД/ФГИС ТП)
  _fitted: false, _ix: null,
};

function isHidden(f) { const L = layerOf(f); return L ? !L.visible : false; }

let shiftDown = false, spaceDown = false;

// ---------- координаты ----------
function w2s(x, y) { return [state.view.tx + x * state.view.k, state.view.ty - y * state.view.k]; }
function s2w(sx, sy) { return [(sx - state.view.tx) / state.view.k, (state.view.ty - sy) / state.view.k]; }
function featurePts(f) { return f.ring || f.line || [f.point]; }
function selectedFeature() { return state.features.find(x => x.id === state.selected); }
function vertexAt(f, wx, wy) {
  const tolW = 8 / state.view.k;
  const pts = featurePts(f);
  for (let i = 0; i < pts.length; i++)
    if (Math.hypot(pts[i][0] - wx, pts[i][1] - wy) < tolW) return i;
  return null;
}

// Совместное редактирование границ покрытия: вершины других зон,
// совпадающие с данной, двигаются вместе с ней — общая граница остаётся
// общей, дырки и нахлёсты не возникают (инвариант coverage ядра).
// Кто участвует — решает флаг слоя topology="coverage", не тип объекта.
function isCoverageFeature(f) {
  const L = layerOf(f);
  return !!L && L.topology === "coverage";
}
function sharedCompanions(f, vi) {
  if (!isCoverageFeature(f)) return [];
  const [x, y] = featurePts(f)[vi];
  const out = [];
  for (const other of state.features) {
    if (other.id === f.id || !isCoverageFeature(other) || isHidden(other)) continue;
    const pts = featurePts(other);
    for (let i = 0; i < pts.length; i++)
      if (Math.abs(pts[i][0] - x) < 1e-6 && Math.abs(pts[i][1] - y) < 1e-6)
        out.push({ f: other, vi: i });
  }
  return out;
}

function sharedVertexSet(f) {
  const shared = new Set();
  if (!isCoverageFeature(f)) return shared;
  const pts = featurePts(f);
  for (let i = 0; i < pts.length; i++)
    if (sharedCompanions(f, i).length) shared.add(i);
  return shared;
}

// Safari отмечен глюками ResizeObserver + <canvas>: назначение canvas.width
// сбрасывает битмап, и если наблюдатель перевызывает resize() синхронно
// в цикле (даже когда CSS-размер элемента фактически не изменился),
// холст может гаситься быстрее, чем успевает перерисоваться — экран
// «на секунду показывает точки сетки и белеет». Защита: (1) менять
// битмап только когда размер реально изменился; (2) события наблюдателя
// схлопывать через requestAnimationFrame, чтобы разорвать возможный
// синхронный цикл переисчисления layout.
let lastBufW = 0, lastBufH = 0;
function resize() {
  const dpr = window.devicePixelRatio || 1;
  const r = cv.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return;
  const w = Math.round(r.width * dpr), h = Math.round(r.height * dpr);
  if (w === lastBufW && h === lastBufH) { draw(); return; }
  lastBufW = w; lastBufH = h;
  cv.width = w; cv.height = h;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (state.features.length && !state._fitted) {
    state._fitted = true;
    fitView();
    return;
  }
  draw();
}
window.addEventListener("resize", resize);
let roPending = false;
new ResizeObserver(() => {
  if (roPending) return;
  roPending = true;
  requestAnimationFrame(() => { roPending = false; resize(); });
}).observe(cv);

// ---------- сетка ----------
function gridStep() {
  if (state.gridMode !== "auto") return +state.gridMode;
  for (const g of [1, 2, 5, 10, 20, 50, 100, 200, 500])
    if (g * state.view.k >= 22) return g;
  return 1000;
}

// ---------- подложка (тайлы XYZ) ----------
// Локальные метры холста → долгота/широта: приближение локальной
// касательной плоскости вокруг ORIGIN (см. crs.ORIGIN_LON/LAT в ядре).
// На масштабе территории (км, не сотни км) погрешность на два порядка
// меньше пиксела тайла — для фоновой подложки этого достаточно; точная
// проекция (обратный UTM) считается на сервере и используется только
// для получения самой точки ORIGIN.
const basemap = {
  on: false, opacity: 0.85, originLon: null, originLat: null, attribution: "",
  mPerDegLon: null, mPerDegLat: 111320,
  cache: new Map(),   // "z/x/y" -> {img, loaded, failed}
};

async function initBasemap() {
  try {
    const r = await fetch("/api/basemap-info");
    const d = await r.json();
    basemap.originLon = d.origin_lon;
    basemap.originLat = d.origin_lat;
    basemap.attribution = d.attribution;
    basemap.mPerDegLon = 111320 * Math.cos(d.origin_lat * Math.PI / 180);
  } catch (e) { /* сервер без /api/basemap-info — подложка недоступна */ }
}

function localToLonLat(x, y) {
  return [basemap.originLon + x / basemap.mPerDegLon,
          basemap.originLat + y / basemap.mPerDegLat];
}
function lonLatToLocal(lon, lat) {
  return [(lon - basemap.originLon) * basemap.mPerDegLon,
          (lat - basemap.originLat) * basemap.mPerDegLat];
}
function lonToTileX(lon, z) { return (lon + 180) / 360 * 2 ** z; }
function latToTileY(lat, z) {
  const r = lat * Math.PI / 180;
  return (1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * 2 ** z;
}
function tileXToLon(tx, z) { return tx / 2 ** z * 360 - 180; }
function tileYToLat(ty, z) {
  const n = Math.PI - 2 * Math.PI * ty / 2 ** z;
  return 180 / Math.PI * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
}

function tileImage(z, x, y) {
  const key = `${z}/${x}/${y}`;
  let e = basemap.cache.get(key);
  if (!e) {
    e = { img: new Image(), loaded: false, failed: false };
    e.img.onload = () => { e.loaded = true; draw(); };
    e.img.onerror = () => { e.failed = true; };
    e.img.src = `/api/tiles/${z}/${x}/${y}.png`;
    basemap.cache.set(key, e);
  }
  return e;
}

function drawBasemap(w, h) {
  if (!basemap.on || basemap.originLon == null) return;
  const [wx0, wy1] = s2w(0, 0), [wx1, wy0] = s2w(w, h);
  const [lon0, lat0] = localToLonLat(wx0, wy0);
  const [lon1, lat1] = localToLonLat(wx1, wy1);
  // подбор зума: метры на тайл-пиксель ≈ метры на экранный пиксель
  const mppTile0 = 156543.03392804097 * Math.cos(basemap.originLat * Math.PI / 180);
  let z = Math.round(Math.log2(mppTile0 * state.view.k));
  z = Math.max(1, Math.min(19, z));

  const txMin = Math.floor(lonToTileX(Math.min(lon0, lon1), z));
  const txMax = Math.floor(lonToTileX(Math.max(lon0, lon1), z));
  const tyMin = Math.floor(latToTileY(Math.max(lat0, lat1), z));
  const tyMax = Math.floor(latToTileY(Math.min(lat0, lat1), z));
  const maxTiles = 2 ** z;
  const budget = 300;  // защита от случайного запроса тысяч тайлов при рывке зума
  let drawn = 0;
  ctx.save();
  ctx.globalAlpha = basemap.opacity;
  for (let ty = tyMin; ty <= tyMax; ty++) {
    for (let tx = txMin; tx <= txMax; tx++) {
      if (++drawn > budget) break;
      const cx = ((tx % maxTiles) + maxTiles) % maxTiles;
      if (ty < 0 || ty >= maxTiles) continue;
      const e = tileImage(z, cx, ty);
      if (!e.loaded) continue;
      const nw = lonLatToLocal(tileXToLon(tx, z), tileYToLat(ty, z));
      const se = lonLatToLocal(tileXToLon(tx + 1, z), tileYToLat(ty + 1, z));
      const [sx0, sy0] = w2s(...nw), [sx1, sy1] = w2s(...se);
      // расширяем на 0.5px — прячет тонкие щели между соседними тайлами
      ctx.drawImage(e.img, sx0 - 0.5, sy0 - 0.5, sx1 - sx0 + 1, sy1 - sy0 + 1);
    }
  }
  ctx.restore();
  ctx.fillStyle = "rgba(255,255,255,.82)";
  ctx.fillRect(6, h - 18, ctx.measureText(basemap.attribution).width + 14, 14);
  ctx.fillStyle = "#5c5a54"; ctx.font = "10px sans-serif"; ctx.textAlign = "left";
  ctx.fillText(basemap.attribution, 10, h - 7);
}

// ---------- геометрия ----------
function ringArea(ring) {
  let s = 0;
  for (let i = 0; i < ring.length; i++) {
    const [x1, y1] = ring[i], [x2, y2] = ring[(i + 1) % ring.length];
    s += x1 * y2 - x2 * y1;
  }
  return Math.abs(s) / 2;
}
function lineLen(line) {
  let s = 0;
  for (let i = 0; i + 1 < line.length; i++)
    s += Math.hypot(line[i + 1][0] - line[i][0], line[i + 1][1] - line[i][1]);
  return s;
}
function pointInRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
function nearestOnSeg(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const l2 = dx * dx + dy * dy;
  const t = l2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2)) : 0;
  return [a[0] + dx * t, a[1] + dy * t];
}
function nearChain(x, y, chain, tolW) {
  for (let i = 0; i + 1 < chain.length; i++) {
    const q = nearestOnSeg([x, y], chain[i], chain[i + 1]);
    if (Math.hypot(x - q[0], y - q[1]) < tolW) return i;
  }
  return null;
}
function segIntersect(a0, a1, b0, b1) {
  const d0 = [a1[0] - a0[0], a1[1] - a0[1]], d1 = [b1[0] - b0[0], b1[1] - b0[1]];
  const det = d0[0] * d1[1] - d0[1] * d1[0];
  if (Math.abs(det) < 1e-12) return null;
  const t = ((b0[0] - a0[0]) * d1[1] - (b0[1] - a0[1]) * d1[0]) / det;
  const u = ((b0[0] - a0[0]) * d0[1] - (b0[1] - a0[1]) * d0[0]) / det;
  if (t < -1e-9 || t > 1 + 1e-9 || u < -1e-9 || u > 1 + 1e-9) return null;
  return [a0[0] + d0[0] * t, a0[1] + d0[1] * t];
}

function featureChains(f) {
  if (f.ring) return [[...f.ring, f.ring[0]]];
  if (f.line) return [f.line];
  return [];
}

// ---------- привязки (уровень CAD) ----------
const SNAP_PRIORITY = { "вершина": 0, "пересечение": 1, "середина": 2, "центр": 3 };

function _excludeSet(exclude) {
  if (exclude == null) return null;
  return exclude instanceof Set ? exclude : new Set([].concat(exclude));
}

function collectSnapPts(exclude) {
  const ex = _excludeSet(exclude);
  const out = [];
  for (const f of state.features) {
    if ((ex && ex.has(f.id)) || isHidden(f)) continue;
    if (f.point) { out.push({ p: f.point, kind: "вершина" }); continue; }
    for (const chain of featureChains(f)) {
      for (let i = 0; i + 1 < chain.length; i++) {
        out.push({ p: chain[i], kind: "вершина" });
        out.push({ p: [(chain[i][0] + chain[i + 1][0]) / 2,
                       (chain[i][1] + chain[i + 1][1]) / 2], kind: "середина" });
      }
    }
    if (f.ring) {
      const xs = f.ring.map(p => p[0]), ys = f.ring.map(p => p[1]);
      out.push({ p: [(Math.min(...xs) + Math.max(...xs)) / 2,
                     (Math.min(...ys) + Math.max(...ys)) / 2], kind: "центр" });
    }
  }
  return out;
}

function intersections() {
  if (state._ix) return state._ix;
  const segs = [];
  for (const f of state.features) {
    if (isHidden(f)) continue;
    for (const chain of featureChains(f))
      for (let i = 0; i + 1 < chain.length; i++)
        segs.push([chain[i], chain[i + 1]]);
  }
  const out = [];
  for (let i = 0; i < segs.length && i < 400; i++)
    for (let j = i + 1; j < segs.length && j < 400; j++) {
      const p = segIntersect(segs[i][0], segs[i][1], segs[j][0], segs[j][1]);
      if (p) out.push(p);
    }
  state._ix = out;
  return out;
}

function snapPoint(wx, wy, exclude) {
  state.guides = [];
  const tolW = 10 / state.view.k;
  // 1. объектные привязки по приоритету
  if (state.osnap) {
    let best = null;
    for (const c of collectSnapPts(exclude)) {
      const d = Math.hypot(c.p[0] - wx, c.p[1] - wy);
      if (d > tolW) continue;
      const key = [SNAP_PRIORITY[c.kind], d];
      if (!best || key[0] < best.key[0] || (key[0] === best.key[0] && key[1] < best.key[1]))
        best = { p: [...c.p], kind: c.kind, key };
    }
    for (const p of intersections()) {
      const d = Math.hypot(p[0] - wx, p[1] - wy);
      if (d <= tolW && (!best || best.key[0] > 1 || (best.key[0] === 1 && d < best.key[1])))
        best = { p: [...p], kind: "пересечение", key: [1, d] };
    }
    if (best) return { p: best.p, kind: best.kind };
    // 2. направляющие выравнивания по вершинам
    let gx = null, gy = null;
    for (const c of collectSnapPts(exclude)) {
      if (c.kind !== "вершина") continue;
      if (Math.abs(c.p[0] - wx) < tolW && (!gx || Math.abs(c.p[0] - wx) < Math.abs(gx.p[0] - wx))) gx = c;
      if (Math.abs(c.p[1] - wy) < tolW && (!gy || Math.abs(c.p[1] - wy) < Math.abs(gy.p[1] - wy))) gy = c;
    }
    if (gx || gy) {
      const p = [gx ? gx.p[0] : wx, gy ? gy.p[1] : wy];
      if (gx) state.guides.push([gx.p, p]);
      if (gy) state.guides.push([gy.p, p]);
      return { p, kind: "выравнивание" };
    }
  }
  // (направляющие уже используют тот же exclude через collectSnapPts выше)
  // 3. сетка
  if (state.gridSnap) {
    const g = gridStep();
    return { p: [Math.round(wx / g) * g, Math.round(wy / g) * g], kind: "сетка" };
  }
  return { p: [wx, wy], kind: null };
}

function lastDrawingPt() {
  return state.drawing && state.drawing.pts.length
    ? state.drawing.pts[state.drawing.pts.length - 1] : null;
}

function orthoProject(base, wx, wy) {
  // фиксация направления на 0/45/90° (Shift)
  const dx = wx - base[0], dy = wy - base[1];
  const dist = Math.hypot(dx, dy);
  if (dist < 1e-9) return [wx, wy];
  const a = Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) * (Math.PI / 4);
  return [base[0] + dist * Math.cos(a), base[1] + dist * Math.sin(a)];
}

function cursorPoint(wx, wy) {
  const base = lastDrawingPt();
  if (shiftDown && base) {
    const [ox, oy] = orthoProject(base, wx, wy);
    if (state.gridSnap) {
      // выравниваем длину по шагу сетки вдоль зафиксированного направления
      const g = gridStep();
      const d = Math.round(Math.hypot(ox - base[0], oy - base[1]) / g) * g;
      const a = Math.atan2(oy - base[1], ox - base[0]);
      return { p: [base[0] + d * Math.cos(a), base[1] + d * Math.sin(a)], kind: "орто" };
    }
    return { p: [ox, oy], kind: "орто" };
  }
  return snapPoint(wx, wy, state.edit ? state.edit.f.id : undefined);
}

// ---------- отрисовка ----------
function drawChain(chain, close) {
  ctx.beginPath();
  ctx.moveTo(...w2s(...chain[0]));
  for (let i = 1; i < chain.length; i++) ctx.lineTo(...w2s(...chain[i]));
  if (close) ctx.closePath();
}

function drawGrid(w, h) {
  if (!state.gridShow) return;
  const g = gridStep();
  const [wx0, wy1] = s2w(0, 0), [wx1, wy0] = s2w(w, h);
  const px = g * state.view.k;
  // крупные линии каждые 5 шагов
  ctx.lineWidth = 1;
  const gridAxis = cvColor("label", "#d5d2ca"), gridLine = cvColor("grid", "#eceae5");
  for (let x = Math.floor(wx0 / (g * 5)) * g * 5; x <= wx1; x += g * 5) {
    ctx.strokeStyle = x === 0 ? gridAxis : gridLine;
    ctx.beginPath(); ctx.moveTo(...w2s(x, wy0)); ctx.lineTo(...w2s(x, wy1)); ctx.stroke();
  }
  for (let y = Math.floor(wy0 / (g * 5)) * g * 5; y <= wy1; y += g * 5) {
    ctx.strokeStyle = y === 0 ? gridAxis : gridLine;
    ctx.beginPath(); ctx.moveTo(...w2s(wx0, y)); ctx.lineTo(...w2s(wx1, y)); ctx.stroke();
  }
  // точки в узлах мелкого шага (как в Rayon)
  if (px >= 11) {
    ctx.fillStyle = cvColor("grid", "#c9c6bd");
    for (let x = Math.floor(wx0 / g) * g; x <= wx1; x += g)
      for (let y = Math.floor(wy0 / g) * g; y <= wy1; y += g) {
        const [sx, sy] = w2s(x, y);
        ctx.fillRect(sx - 0.75, sy - 0.75, 1.5, 1.5);
      }
  }
  document.getElementById("st-grid").textContent =
    `сетка ${g} м${state.gridSnap ? "" : " (без привязки)"}`;
}

function drawSnapMarker() {
  const s = state.snapHit;
  if (!s || !s.kind || state.tool === "select") return;
  const [sx, sy] = w2s(...s.p);
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = cvColor("shared", "#12a150");
  if (s.kind === "вершина") ctx.strokeRect(sx - 5, sy - 5, 10, 10);
  else if (s.kind === "середина") {
    ctx.beginPath(); ctx.moveTo(sx, sy - 6); ctx.lineTo(sx + 6, sy + 5); ctx.lineTo(sx - 6, sy + 5);
    ctx.closePath(); ctx.stroke();
  } else if (s.kind === "пересечение") {
    ctx.beginPath();
    ctx.moveTo(sx - 5, sy - 5); ctx.lineTo(sx + 5, sy + 5);
    ctx.moveTo(sx - 5, sy + 5); ctx.lineTo(sx + 5, sy - 5); ctx.stroke();
  } else if (s.kind === "центр") {
    ctx.beginPath(); ctx.arc(sx, sy, 5.5, 0, 7); ctx.stroke();
  } else if (s.kind === "выравнивание" || s.kind === "орто") {
    ctx.beginPath(); ctx.arc(sx, sy, 3, 0, 7); ctx.stroke();
  } else if (s.kind === "сетка") {
    ctx.strokeStyle = cvColor("label", "#9a978f");
    ctx.beginPath();
    ctx.moveTo(sx - 4, sy); ctx.lineTo(sx + 4, sy);
    ctx.moveTo(sx, sy - 4); ctx.lineTo(sx, sy + 4); ctx.stroke();
  }
}

// Штриховка зоны по Эталону ЛГР: hatch = true (легаси 45° цветом обводки)
// или {angle: 0|45|90|135, cross, spacing_px, color}. Рисуется в клипе контура.
function drawHatch(ring, hatch, strokeColor) {
  const spec = hatch === true
    ? { angle: 45, spacing_px: 9, color: strokeColor }
    : hatch;
  ctx.save();
  drawChain(ring, true);
  ctx.clip();
  const ss = ring.map(p => w2s(...p));
  const xs = ss.map(p => p[0]), ys = ss.map(p => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y0 = Math.min(...ys), y1 = Math.max(...ys);
  ctx.strokeStyle = spec.color || strokeColor;
  ctx.lineWidth = 1.0;
  ctx.setLineDash([]);
  const step = Math.max(3, spec.spacing_px || 9);
  const angles = spec.cross ? [45, 135] : [spec.angle ?? 45];
  for (const a of angles) {
    ctx.beginPath();
    if (a === 0) {                       // горизонтальные
      for (let y = y0; y <= y1; y += step) { ctx.moveTo(x0, y); ctx.lineTo(x1, y); }
    } else if (a === 90) {               // вертикальные
      for (let x = x0; x <= x1; x += step) { ctx.moveTo(x, y0); ctx.lineTo(x, y1); }
    } else if (a === 45) {               // «///» (вверх слева направо на экране)
      const d = step * Math.SQRT2;
      for (let c = x0 - (y1 - y0); c < x1; c += d) {
        ctx.moveTo(c, y1); ctx.lineTo(c + (y1 - y0), y0);
      }
    } else {                             // 135°: «\\\»
      const d = step * Math.SQRT2;
      for (let c = x0 - (y1 - y0); c < x1; c += d) {
        ctx.moveTo(c + (y1 - y0), y1); ctx.lineTo(c, y0);
      }
    }
    ctx.stroke();
  }
  ctx.restore();
}

// Одна засечка в экранной точке (px,py): касательная (tx,ty), нормаль
// внутрь (nx,ny). Формы: tick ⊢, tee ⊥, corner Г, chevron ∨, chevron_dot ∨.,
// triangle ▼, dot ●, square ■, diamond ◇.
function drawMarkerGlyph(shape, px, py, tx, ty, nx, ny, s, period) {
  ctx.beginPath();
  switch (shape) {
    case "tee":
      ctx.moveTo(px, py); ctx.lineTo(px + nx * s, py + ny * s);
      ctx.moveTo(px - tx * s * 0.5, py - ty * s * 0.5);
      ctx.lineTo(px + tx * s * 0.5, py + ty * s * 0.5);
      ctx.stroke(); break;
    case "corner":
      ctx.moveTo(px, py); ctx.lineTo(px + nx * s, py + ny * s);
      ctx.lineTo(px + nx * s + tx * s, py + ny * s + ty * s);
      ctx.stroke(); break;
    case "chevron": case "chevron_dot": {
      // остриё внутрь зоны, плечи на линии (Эталон: зубец «▽» остриём в зону)
      const w2 = s * 0.5;
      ctx.moveTo(px - tx * w2, py - ty * w2);
      ctx.lineTo(px + nx * s, py + ny * s);
      ctx.lineTo(px + tx * w2, py + ty * w2);
      ctx.stroke();
      if (shape === "chevron_dot") {
        ctx.beginPath();
        ctx.arc(px + tx * period / 2 + nx * s * 0.5,
                py + ty * period / 2 + ny * s * 0.5, s * 0.15, 0, 7);
        ctx.fill();
      }
      break;
    }
    case "triangle": {
      // залитый «▼» остриём внутрь зоны, основание на линии (Эталон)
      const b = s * 0.5;
      ctx.moveTo(px - tx * b, py - ty * b);
      ctx.lineTo(px + tx * b, py + ty * b);
      ctx.lineTo(px + nx * s, py + ny * s);
      ctx.closePath(); ctx.fill(); break;
    }
    case "triangle2": {
      // два наложенных залитых треугольника остриём внутрь зоны (Эталон ООЗТ)
      const b = s * 0.5;
      for (const [base, apex] of [[0, s * 0.85], [s * 0.45, s * 1.3]]) {
        const bx = px + nx * base, by = py + ny * base;
        ctx.beginPath();
        ctx.moveTo(bx - tx * b, by - ty * b);
        ctx.lineTo(bx + tx * b, by + ty * b);
        ctx.lineTo(px + nx * apex, py + ny * apex);
        ctx.closePath(); ctx.fill();
      }
      break;
    }
    case "dot":
      ctx.arc(px, py, s / 2, 0, 7); ctx.fill(); break;
    case "square": {
      const b = s / 2;
      ctx.fillRect(px - b, py - b, s, s); break;
    }
    case "diamond": {
      const b = s / 2;
      ctx.moveTo(px - b, py); ctx.lineTo(px, py - b);
      ctx.lineTo(px + b, py); ctx.lineTo(px, py + b);
      ctx.closePath(); ctx.stroke(); break;
    }
    case "slashes": {
      // две параллельные косые засечки «⫽» поперёк линии (Эталон: зоны
      // затопления/подтопления). Наклон по (касательная − нормаль внутрь).
      const dx = tx - nx, dy = ty - ny, dl = Math.hypot(dx, dy) || 1;
      const ux = dx / dl, uy = dy / dl, h = s * 0.6, sep = s * 0.45;
      for (const o of [-sep / 2, sep / 2]) {
        const cx = px + tx * o, cy = py + ty * o;
        ctx.moveTo(cx - ux * h, cy - uy * h);
        ctx.lineTo(cx + ux * h, cy + uy * h);
      }
      ctx.stroke(); break;
    }
    default:  // tick
      ctx.moveTo(px, py); ctx.lineTo(px + nx * s, py + ny * s);
      ctx.stroke();
  }
}

// Засечки вдоль линии/контура. Размещение ПОСЕГМЕНТНОЕ: на каждом прямом
// ребре засечки распределяются равномерно с отступом от вершин, а не
// непрерывно по периметру — иначе на углах засечки соседних рёбер
// сходятся вплотную (в Эталоне углы свободны). mk={shape,period,size} px.
function drawLineMarkers(pts, mk, color, closed, inward) {
  const chain = closed ? [...pts, pts[0]] : pts;
  const scr = chain.map(p => w2s(...p));
  const period = mk.period || 40, s = mk.size || 4;
  ctx.save();
  ctx.setLineDash([]);
  ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1.2;
  for (let i = 1; i < scr.length; i++) {
    const [x1, y1] = scr[i - 1], [x2, y2] = scr[i];
    const d = Math.hypot(x2 - x1, y2 - y1);
    if (d < period * 0.5) continue;      // ребро короче половины периода
    const tx = (x2 - x1) / d, ty = (y2 - y1) / d;
    const nx = -ty * inward, ny = tx * inward;
    const n = Math.max(1, Math.round(d / period));
    const gap = d / n;
    for (let k = 0; k < n; k++) {
      const t = (gap * (k + 0.5)) / d;
      drawMarkerGlyph(mk.shape, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t,
                      tx, ty, nx, ny, s, period);
    }
  }
  ctx.restore();
}

// Знак засечки направлен внутрь зоны: выясняем сторону по центроиду кольца
function inwardSign(ring) {
  const [x1, y1] = ring[0], [x2, y2] = ring[1];
  const d = Math.hypot(x2 - x1, y2 - y1) || 1;
  // экранные нормали: w2s инвертирует y, поэтому знак согласован с canvas
  const [sx1, sy1] = w2s(x1, y1), [sx2, sy2] = w2s(x2, y2);
  const sd = Math.hypot(sx2 - sx1, sy2 - sy1) || 1;
  const nx = -(sy2 - sy1) / sd, ny = (sx2 - sx1) / sd;
  let cx = 0, cy = 0;
  for (const p of ring) { cx += p[0] / ring.length; cy += p[1] / ring.length; }
  const [scx, scy] = w2s(cx, cy);
  const mx = (sx1 + sx2) / 2, my = (sy1 + sy2) / 2;
  return (scx - mx) * nx + (scy - my) * ny > 0 ? 1 : -1;
}

// Двойная параллельная линия (защитные зоны ОКН): смещение по нормалям
function drawDoubleLine(pts, gap, closed) {
  const chain = closed ? [...pts, pts[0]] : pts;
  const scr = chain.map(p => w2s(...p));
  ctx.beginPath();
  for (let i = 0; i < scr.length; i++) {
    const prev = scr[Math.max(0, i - 1)], next = scr[Math.min(scr.length - 1, i + 1)];
    const dx = next[0] - prev[0], dy = next[1] - prev[1];
    const d = Math.hypot(dx, dy) || 1;
    const x = scr[i][0] - dy / d * gap, y = scr[i][1] + dx / d * gap;
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  ctx.stroke();
}

// Повторяющаяся подпись вдоль линии (условный знак ЛГР: «кл топ» и т.п.)
// Подпись линии (условный знак ЛГР: «кл топ», «водоохранная» и т.п.) —
// ОДНА на объект, на самом длинном отрезке контура/линии. Раньше подпись
// повторялась через каждые ~180px по всему периметру, что на компактных
// прямоугольниках сажало её на 3-4 стороны разом (в т.ч. вертикально на
// боковые рёбра) — нечитаемо и выглядело как баг. Один подписанный отрезок
// на самой длинной стороне — то, что реально нужно для типового объекта;
// для по-настоящему длинных линий (через весь чертёж) метки видно, пока
// видна сама протяжённая сторона.
function drawLineLabel(pts, text, color) {
  const scr = pts.map(p => w2s(...p));
  let best = null;
  for (let i = 1; i < scr.length; i++) {
    const [ax, ay] = scr[i - 1], [bx, by] = scr[i];
    const len = Math.hypot(bx - ax, by - ay);
    if (!best || len > best.len) best = { ax, ay, bx, by, len };
  }
  if (!best || best.len < 40) return;      // слишком коротко для подписи
  const x = (best.ax + best.bx) / 2, y = (best.ay + best.by) / 2;
  let ang = Math.atan2(best.by - best.ay, best.bx - best.ax);
  if (ang > Math.PI / 2 || ang < -Math.PI / 2) ang += Math.PI;  // не вверх ногами
  ctx.save();
  ctx.fillStyle = color; ctx.font = "600 10px sans-serif"; ctx.textAlign = "center";
  ctx.translate(x, y); ctx.rotate(ang);
  ctx.fillText(text, 0, -4);
  ctx.restore();
}

function draw() {
  const w = cv.clientWidth, h = cv.clientHeight;
  ctx.clearRect(0, 0, w, h);
  drawBasemap(w, h);
  drawGrid(w, h);

  for (const layer of LAYERS_V2) {
    if (!layer.visible) continue;
    for (const f of state.features) {
      if (layerOf(f) !== layer) continue;
      const st = styleOf(f);
      ctx.setLineDash(st.dash || []);
      ctx.lineWidth = st.width; ctx.strokeStyle = st.stroke || cvColor("boundary", "#000");
      if (layer.kind === "dim" && f.line) {
        // размерная линия: засечки 45° на концах + длина вдоль линии
        const [ax, ay] = w2s(...f.line[0]);
        const [bx, by] = w2s(...f.line[f.line.length - 1]);
        const ang = Math.atan2(by - ay, bx - ax);
        ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by);
        for (const [px, py] of [[ax, ay], [bx, by]]) {
          ctx.moveTo(px - 5 * Math.cos(ang + Math.PI / 4), py - 5 * Math.sin(ang + Math.PI / 4));
          ctx.lineTo(px + 5 * Math.cos(ang + Math.PI / 4), py + 5 * Math.sin(ang + Math.PI / 4));
        }
        ctx.stroke();
        const lenM = Math.hypot(f.line[1][0] - f.line[0][0], f.line[1][1] - f.line[0][1]);
        ctx.save();
        ctx.translate((ax + bx) / 2, (ay + by) / 2);
        let ta = ang;
        if (ta > Math.PI / 2 || ta < -Math.PI / 2) ta += Math.PI;  // текст не вверх ногами
        ctx.rotate(ta);
        ctx.fillStyle = st.stroke; ctx.font = "600 11px sans-serif"; ctx.textAlign = "center";
        ctx.fillText(lenM.toFixed(1) + " м", 0, -5);
        ctx.restore();
        ctx.setLineDash([]);
      } else if (f.point) {
        const [sx, sy] = w2s(...f.point);
        ctx.beginPath(); ctx.arc(sx, sy, 6, 0, 7); ctx.fillStyle = st.fill; ctx.fill(); ctx.stroke();
      } else {
        if (layer.kind === "redline" && (f.props.radius || 0) > 0 && f.line.length > 2) {
          ctx.beginPath();
          ctx.moveTo(...w2s(...f.line[0]));
          for (let i = 1; i < f.line.length - 1; i++)
            ctx.arcTo(...w2s(...f.line[i]), ...w2s(...f.line[i + 1]),
                      f.props.radius * state.view.k);
          ctx.lineTo(...w2s(...f.line[f.line.length - 1]));
        } else {
          drawChain(f.ring || f.line, !!f.ring);
        }
        if (st.fill && f.ring) { ctx.fillStyle = st.fill; ctx.fill(); }
        ctx.stroke();
        if (st.hatch && f.ring) drawHatch(f.ring, st.hatch, st.stroke);
        if (st.double) drawDoubleLine(f.ring || f.line, st.double, !!f.ring);
        if (st.line_marker && (f.ring || f.line)) {
          // направление засечки по знаку Эталона: по умолчанию остриём ВНУТРЬ
          // зоны, dir "out" — наружу (ООПТ/ПК/водоохранная/прибрежная/ландшафт)
          let inw = f.ring && f.ring.length > 2 ? inwardSign(f.ring) : 1;
          if (st.line_marker.dir === "out") inw = -inw;
          drawLineMarkers(f.ring || f.line, st.line_marker,
                          st.stroke || cvColor("redline", "#df0024"), !!f.ring, inw);
        }
        if (st.line_label) {
          const pts = f.ring ? [...f.ring, f.ring[0]] : f.line;
          drawLineLabel(pts, st.line_label, st.stroke || cvColor("redline", "#d91a1a"));
        }
      }
      ctx.setLineDash([]);
      if (st.label_field && f.ring) {
        const c = f.ring.reduce((a, p) => [a[0] + p[0] / f.ring.length, a[1] + p[1] / f.ring.length], [0, 0]);
        const v = labelOf(f);
        if (v !== undefined && v !== "" && v !== null) {
          ctx.fillStyle = cvColor("label", "#5c5a54"); ctx.font = "11px sans-serif"; ctx.textAlign = "center";
          ctx.fillText(String(v), ...w2s(...c));
        }
      }
      if (f.id === state.selected) {
        ctx.strokeStyle = cvColor("selection", "#2f6fde"); ctx.lineWidth = 1.5; ctx.setLineDash([4, 3]);
        if (f.point) { const [sx, sy] = w2s(...f.point); ctx.strokeRect(sx - 9, sy - 9, 18, 18); }
        else { drawChain(f.ring || f.line, !!f.ring); ctx.stroke(); }
        ctx.setLineDash([]);
        const shared = sharedVertexSet(f);
        const shFill = cvColor("shared", "#12a150"), vxStroke = cvColor("vertex", "#2f6fde");
        const handleBg = cvColor("bg", "#fff");
        featurePts(f).forEach((p, i) => {
          const [sx, sy] = w2s(...p);
          const isShared = shared.has(i);
          // зелёная ручка — вершина общая с соседней зоной, тянется совместно
          ctx.fillStyle = isShared ? shFill : handleBg;
          ctx.strokeStyle = isShared ? shFill : vxStroke;
          ctx.lineWidth = 1.2;
          ctx.fillRect(sx - 3, sy - 3, 6, 6); ctx.strokeRect(sx - 3, sy - 3, 6, 6);
        });
      }
    }
  }

  // пикетаж красных линий: засечки поперёк + подписи ПК
  for (const f of state.features) {
    if (f.kind !== "redline" || !(f.props.pk_step > 0) || !f.props._stations) continue;
    if (isHidden(f)) continue;
    ctx.strokeStyle = cvColor("redline", "#d91a1a"); ctx.lineWidth = 1;
    ctx.fillStyle = cvColor("redline", "#8c1414"); ctx.font = "600 10px sans-serif"; ctx.textAlign = "center";
    for (const st of f.props._stations) {
      const [sx, sy] = w2s(st.x, st.y);
      const nx = -Math.sin(st.a), ny = Math.cos(st.a);   // нормаль к касательной
      ctx.beginPath();
      ctx.moveTo(sx - nx * 5, sy + ny * 5);
      ctx.lineTo(sx + nx * 5, sy - ny * 5);
      ctx.stroke();
      const pk = `ПК${Math.floor(st.s / 100)}+${String(Math.round(st.s % 100)).padStart(2, "0")}`;
      ctx.fillText(pk, sx + nx * 16, sy - ny * 16 + 3);
    }
  }

  // направляющие выравнивания
  if (state.guides.length) {
    ctx.strokeStyle = cvColor("shared", "#12a150"); ctx.lineWidth = 0.8; ctx.setLineDash([4, 4]);
    for (const [a, b] of state.guides) { drawChain([a, b], false); ctx.stroke(); }
    ctx.setLineDash([]);
  }

  // черчение в процессе + живой размер
  if (state.drawing && state.drawing.pts.length) {
    const st = styleForDrawing();
    ctx.strokeStyle = st.stroke || cvColor("boundary", "#000"); ctx.lineWidth = st.width || 1; ctx.setLineDash([5, 4]);
    const pts = state.mouse ? [...state.drawing.pts, state.mouse] : state.drawing.pts;
    drawChain(pts, false); ctx.stroke(); ctx.setLineDash([]);
    const base = lastDrawingPt();
    if (base && state.mouse) {
      const len = Math.hypot(state.mouse[0] - base[0], state.mouse[1] - base[1]);
      const [mx, my] = w2s(...state.mouse);
      ctx.font = "600 12px sans-serif"; ctx.textAlign = "left";
      if (state.typed) {
        ctx.fillStyle = cvColor("selection", "#1c1c1a");
        ctx.fillRect(mx + 10, my - 24, ctx.measureText(state.typed + " м").width + 12, 18);
        ctx.fillStyle = "#fff";
        ctx.fillText(state.typed + " м", mx + 16, my - 11);
      } else {
        ctx.fillStyle = cvColor("label", "#8b8a85");
        ctx.fillText(len.toFixed(1) + " м", mx + 12, my - 10);
      }
    }
    // замыкание: подсветка первой точки
    if (TOOL_GEOM[state.tool] === "polygon" && state.drawing.pts.length > 2 && state.mouse) {
      const first = state.drawing.pts[0];
      if (Math.hypot(first[0] - state.mouse[0], first[1] - state.mouse[1]) < 12 / state.view.k) {
        const [fx, fy] = w2s(...first);
        ctx.strokeStyle = cvColor("shared", "#12a150"); ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(fx, fy, 8, 0, 7); ctx.stroke();
      }
    }
  }
  if (state.drag && state.drag.rect) {
    const { a, b } = state.drag;
    const [sx1, sy1] = w2s(...a), [sx2, sy2] = w2s(...b);
    const bst = styleForDrawing();
    ctx.strokeStyle = bst.stroke || cvColor("label", "#888");
    ctx.fillStyle = (bst.fill || cvColor("zoneB", "#cccccc")) + (bst.fill ? "88" : "");
    ctx.fillRect(Math.min(sx1, sx2), Math.min(sy1, sy2), Math.abs(sx2 - sx1), Math.abs(sy2 - sy1));
    ctx.strokeRect(Math.min(sx1, sx2), Math.min(sy1, sy2), Math.abs(sx2 - sx1), Math.abs(sy2 - sy1));
    ctx.fillStyle = cvColor("label", "#5c5a54"); ctx.font = "600 12px sans-serif"; ctx.textAlign = "left";
    ctx.fillText(`${Math.abs(b[0] - a[0]).toFixed(1)} × ${Math.abs(b[1] - a[1]).toFixed(1)} м`,
                 Math.max(sx1, sx2) + 8, Math.min(sy1, sy2) - 6);
  }
  // измерение
  if (state.measure) {
    const a = state.measure.a;
    const b = state.measure.b || state.mouse;
    if (b) {
      ctx.strokeStyle = cvColor("selection", "#2f6fde"); ctx.lineWidth = 1.2; ctx.setLineDash([6, 3]);
      drawChain([a, b], false); ctx.stroke(); ctx.setLineDash([]);
      const dist = Math.hypot(b[0] - a[0], b[1] - a[1]);
      const [mx, my] = w2s((a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
      ctx.fillStyle = cvColor("selection", "#2f6fde"); ctx.font = "600 12px sans-serif"; ctx.textAlign = "center";
      ctx.fillText(dist.toFixed(1) + " м", mx, my - 6);
    }
  }
  drawSnapMarker();
  updateOverlay();
}

// масштабная линейка + компас + онбординг поверх холста
function niceRound(x) {
  const p = Math.pow(10, Math.floor(Math.log10(x)));
  const f = x / p;
  return (f >= 5 ? 5 : f >= 2 ? 2 : 1) * p;
}
function updateOverlay() {
  const ob = document.getElementById("onboard");
  if (ob) ob.hidden = state.features.length !== 0;
  const bar = document.getElementById("cv-scale-bar");
  const lab = document.getElementById("cv-scale-label");
  if (!bar || !lab) return;
  const mpp = 1 / state.view.k;              // метров мира на экранный пиксель
  const bm = niceRound(90 * mpp);            // «круглая» длина ~90 px
  bar.style.width = Math.round(bm * state.view.k) + "px";
  const dist = bm >= 1000 ? (bm / 1000) + " км" : bm + " м";
  // ~1:N — приблизительно (экранный пиксель ≈ 1/96 дюйма), потому с тильдой
  const denom = Math.round(mpp * 3779.5);
  lab.textContent = `${dist} · ~1:${denom.toLocaleString("ru-RU")}`;
}

// ---------- вид ----------
function zoomBy(factor) {
  const w = cv.clientWidth, h = cv.clientHeight;
  const [wx, wy] = s2w(w / 2, h / 2);        // мировая точка под центром экрана
  state.view.k = Math.min(40, Math.max(0.05, state.view.k * factor));
  state.view.tx = w / 2 - wx * state.view.k;
  state.view.ty = h / 2 + wy * state.view.k;
  draw();
}
function fitPoints(pts, pad = 0.82) {
  if (!pts.length) return;
  const w = cv.clientWidth, h = cv.clientHeight;
  if (w < 2 || h < 2) return;
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const dx = Math.max(Math.max(...xs) - Math.min(...xs), 10);
  const dy = Math.max(Math.max(...ys) - Math.min(...ys), 10);
  state.view.k = Math.max(0.05, Math.min(40, Math.min(w / dx, h / dy) * pad));
  state.view.tx = w / 2 - (Math.min(...xs) + dx / 2) * state.view.k;
  state.view.ty = h / 2 + (Math.min(...ys) + dy / 2) * state.view.k;
  draw();
}
function fitView() {
  const pts = [];
  for (const f of state.features) for (const p of featurePts(f)) pts.push(p);
  fitPoints(pts);
}
function zoomToLayer(id) {
  const pts = [];
  for (const f of featuresOnLayer(id)) for (const p of featurePts(f)) pts.push(p);
  if (!pts.length) { toast("В слое нет объектов"); return; }
  fitPoints(pts, 0.6);
}
function zoomToFeature(f) { fitPoints(featurePts(f), 0.5); }

// ---------- история и сохранение ----------
function snapshot() {
  state.undo.push(JSON.stringify(state.features));
  if (state.undo.length > 100) state.undo.shift();
  state.redo = [];
}
function undo() {
  if (!state.undo.length) return;
  state.redo.push(JSON.stringify(state.features));
  state.features = JSON.parse(state.undo.pop());
  state.selected = null; afterChange();
}
function redo() {
  if (!state.redo.length) return;
  state.undo.push(JSON.stringify(state.features));
  state.features = JSON.parse(state.redo.pop());
  state.selected = null; afterChange();
}
let autosaveTimer = null;
function persist() {
  const payload = {
    features: state.features, nextId: state.nextId,
    name: document.getElementById("project-name").value,
    density: document.getElementById("p-density").value,
    ratio: document.getElementById("p-ratio").value,
    layersVisible: Object.fromEntries(LAYERS_V2.map(L => [L.id, L.visible])),
    layerOrder: LAYERS_V2.map(L => L.id),           // порядок отрисовки (QGIS-панель)
    layerFmt: Object.fromEntries(                    // пер-слойное оформление холста
      LAYERS_V2.filter(L => L.fmt).map(L => [L.id, L.fmt])),
    layerTitles: Object.fromEntries(LAYERS_V2.map(L => [L.id, L.title])),
    userLayers: userLayersManifest(),                // созданные в UI слои — пережить перезагрузку
    activeLayerId: state.activeLayerId,
    sources: state.sources,
  };
  try { localStorage.setItem("grado_studio_v1", JSON.stringify(payload)); }
  catch (e) { /* приватный режим — localStorage недоступен, но файловый автосейв ниже всё равно сработает */ }
  // файловый бэкап на диске сервера: переживает чистку данных сайта и смену
  // браузера, чего localStorage не гарантирует. Дебаунс — не пишем на диск
  // на каждое перемещение мыши при afterChange().
  clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(() => {
    fetch("/api/autosave", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload) }).catch(() => {});
  }, 1500);
}
// пикетаж: подтягиваем расчёт ядра, кэш по ключу геометрии
async function refreshStations(f) {
  const key = JSON.stringify(f.line) + "|" + (f.props.radius || 0) + "|" + f.props.pk_step;
  if (f.props._stations_key === key) return;
  try {
    const r = await fetch("/api/redline-stations", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ line: f.line, radius: f.props.radius || 0,
                             step: f.props.pk_step }) });
    if (!r.ok) return;
    const data = await r.json();
    f.props._stations = data.stations;
    f.props._stations_key = key;
    draw();
  } catch (e) { /* ядро недоступно — пикетаж просто не обновится */ }
}
function maybeRefreshStations() {
  for (const f of state.features)
    if (f.kind === "redline" && (f.props.pk_step || 0) > 0) refreshStations(f);
}

function afterChange() {
  state._ix = null;
  draw(); renderProps(); renderLayers(); refreshTep(); persist();
  maybeRefreshStations();
}

// ---------- ТЭП ----------
let tepTimer = null;
function params() {
  return { density: +document.getElementById("p-density").value || 25,
           ratio_zh: +document.getElementById("p-ratio").value || 80 };
}
function refreshTep() {
  clearTimeout(tepTimer);
  document.getElementById("tep-status").textContent = "…";
  tepTimer = setTimeout(async () => {
    try {
      const r = await fetch("/api/tep", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ features: state.features, params: params() }) });
      const data = await r.json();
      renderTep(data);
      document.getElementById("tep-status").textContent = "";
      document.getElementById("st-core").textContent = `ядро: ок · v${VERSION}`;
    } catch (e) {
      document.getElementById("tep-status").textContent = "нет связи с ядром";
      document.getElementById("st-core").textContent = "ядро: НЕДОСТУПНО";
    }
  }, 250);
}
function renderTep(data) {
  const fact = document.getElementById("tep-fact");
  let zonesHtml = "";
  if (data.zones) {
    zonesHtml = data.zones.ok
      ? `<div class="tep-row" style="color:var(--success)"><span>Зонирование: покрытие корректно</span>
           <span class="v">${data.zones.total_ha} <small>га · общих границ ${data.zones.shared_edges}</small></span></div>`
      : `<div class="tep-row" style="color:var(--warning)"><span>Зонирование: ${data.zones.error}</span><span></span></div>`;
  }
  fact.innerHTML = `<div class="tep-row"><span>По посадке зданий</span><span></span></div>
    <div class="tep-row"><span>СПП факт</span><span class="v">${data.fact.spp} <small>тыс. м²</small></span></div>
    <div class="tep-row"><span>Плотность факт</span><span class="v">${data.fact.density} <small>тыс. м²/га</small></span></div>
    ${zonesHtml}`;
  const body = document.getElementById("tep-body");
  body.classList.remove("muted");
  let html = "", group = null;
  for (const r of data.results) {
    if (r.group !== group) { group = r.group; html += `<div class="tep-group">${group}</div>`; }
    html += `<div class="tep-row"><span>${r.title}</span><span class="v">${r.value} <small>${r.unit}</small></span></div>`;
  }
  body.innerHTML = html;
}

// ---------- свойства (UI-03: поля из схемы semantic_class слоя, не из kind) ----------
// Поле появляется потому, что у активного слоя такой semantic_class, а не
// потому, что где-то в коде проверяется f.kind === "building". Добавление
// атрибута новому слою — правка этой таблицы, а не новая ветка в renderProps.
const ATTR_FIELDS = {
  "oks.building": [
    { key: "floors", title: "Этажность", type: "number", min: 1, max: 75,
      cast: v => Math.max(1, parseInt(v) || 9) },
    { type: "computed",
      compute: f => `СПП: ${(ringArea(f.ring) * (f.props.floors || 1) / 1000).toFixed(1)} тыс. м²` },
  ],
  "pp.red_line": [
    { key: "radius", title: "Радиус сопряжения, м", type: "number", min: 0, max: 500, step: 5,
      cast: v => Math.max(0, parseFloat(v) || 0) },
    { key: "pk_step", title: "Пикетаж, шаг м (0 — выкл)", type: "number", min: 0, max: 500, step: 10,
      cast: v => Math.max(0, parseFloat(v) || 0) },
    { type: "offset" },
  ],
  "tp.func_zone": [
    { key: "zone_title", title: "Наименование зоны", type: "text" },
  ],
  "pp.placement_zone": [
    { key: "purpose", title: "Назначение", type: "text" },
  ],
};

function fieldHtml(field, f) {
  if (field.type === "offset") {
    return `<label>Офсет, м<input type="number" id="f-offdist" value="${f.props._offdist || 15}" min="0.5" max="200" step="0.5"></label>
      <div style="display:flex;gap:6px;margin-bottom:8px">
        <button id="f-offset-l" style="flex:1">⇐ влево</button>
        <button id="f-offset-r" style="flex:1">вправо ⇒</button>
      </div>`;
  }
  const val = f.props[field.key] ?? "";
  return `<label>${field.title}<input type="${field.type}" id="f-${field.key}" value="${val}"${
    field.min != null ? ` min="${field.min}"` : ""}${
    field.max != null ? ` max="${field.max}"` : ""}${
    field.step != null ? ` step="${field.step}"` : ""}></label>`;
}

async function runOffset(f, sign) {
  const dist = Math.abs(parseFloat(document.getElementById("f-offdist").value) || 15);
  f.props._offdist = dist;
  try {
    const r = await fetch("/api/redline-offset", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ line: f.line, radius: f.props.radius || 0,
                             dist: sign * dist }) });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      throw new Error(e.error || ("HTTP " + r.status));
    }
    const data = await r.json();
    snapshot();
    // сопряжение уже вшито в геометрию офсета — radius обнуляем;
    // офсет остаётся на слое исходной линии, а не «слое по умолчанию» —
    // иначе на пользовательском слое линий копия тихо ушла бы не туда
    const copy = upgradeFeature({ id: state.nextId++, layer_id: f.layer_id,
                                  line: data.line, props: { radius: 0 } });
    state.features.push(copy);
    state.selected = copy.id;
    afterChange();
  } catch (err) {
    alert("Офсет не построился: " + String(err).slice(0, 200) +
          "\n(обычно — радиус/офсет не помещается в геометрию)");
  }
}

function renderProps() {
  const el = document.getElementById("props-body");
  const f = selectedFeature();
  if (!f) { el.className = "muted"; el.textContent = "Ничего не выбрано"; return; }
  el.className = "";
  const L = layerOf(f);
  const fields = (L && ATTR_FIELDS[L.semantic_class]) || [];
  let metric = "";
  if (f.ring) metric = `площадь: ${(ringArea(f.ring) / 10000).toFixed(2)} га`;
  if (f.line) metric = `длина: ${lineLen(f.line).toFixed(0)} м`;
  for (const field of fields)
    if (field.type === "computed") metric += ` · ${field.compute(f)}`;
  const extra = fields.filter(fl => fl.type !== "computed").map(fl => fieldHtml(fl, f)).join("\n");
  const prov = f.prov
    ? `<div class="metric prov">источник: ${f.prov.source}${f.prov.source_date ? " · " + f.prov.source_date : ""}</div>`
    : "";
  // per-object стиль из системной библиотеки (default + Эталон ЛГР);
  // уезжает в .grado столбцом style_id и в PDF/DXF
  const stylePick = (L && !L.annotation)
    ? `<label>Стиль (библиотека)<select id="f-style">${stylePickerOptions(f.style_id)}</select></label>`
    : "";
  el.innerHTML = `<div class="kind">${(L || {}).title || f.kind}</div>
    <div class="metric">${metric}</div>${prov}${extra}${stylePick}
    <div class="metric" style="margin-top:6px">двойной клик по ребру — вершина,<br>Alt+клик по вершине — удалить,<br>R — поворот, ⌘D — дубликат</div>
    <button class="danger" id="f-del">Удалить (Del)</button>`;
  const styleSel = document.getElementById("f-style");
  if (styleSel) styleSel.addEventListener("change", () => {
    snapshot();
    if (styleSel.value) f.style_id = styleSel.value;
    else delete f.style_id;
    afterChange();
  });
  const bind = (id, key, cast) => {
    const inp = document.getElementById(id);
    if (inp) inp.addEventListener("change", () => {
      snapshot(); f.props[key] = cast ? cast(inp.value) : inp.value; afterChange();
    });
  };
  for (const field of fields) {
    if (field.type === "computed") continue;
    if (field.type === "offset") {
      const offL = document.getElementById("f-offset-l");
      const offR = document.getElementById("f-offset-r");
      if (offL) offL.onclick = () => runOffset(f, 1);
      if (offR) offR.onclick = () => runOffset(f, -1);
      continue;
    }
    bind(`f-${field.key}`, field.key, field.cast);
  }
  document.getElementById("f-del").onclick = deleteSelected;
}
// Порядок панели — как в QGIS: верхняя строка рисуется ПОВЕРХ. В draw()
// массив идёт снизу вверх (индекс 0 = низ), поэтому список = обратный массив.
function layerRowsTopFirst() {
  return [...LAYERS_V2].reverse()
    .filter(L => !(L.import_only && !featuresOnLayer(L.id).length));
}

// Перетаскивание строки src к строке target меняет порядок отрисовки.
// before=true — встать над target (рисоваться поверх него).
function reorderLayer(srcId, targetId, before) {
  if (srcId === targetId) return;
  const disp = [...LAYERS_V2].reverse();      // порядок показа (сверху вниз)
  const from = disp.findIndex(L => L.id === srcId);
  if (from < 0) return;
  const moved = disp.splice(from, 1)[0];
  let to = disp.findIndex(L => L.id === targetId);
  if (to < 0) return;
  if (!before) to += 1;
  disp.splice(to, 0, moved);
  LAYERS_V2.splice(0, LAYERS_V2.length, ...disp.reverse());  // обратно в порядок отрисовки
  renderLayers(); draw(); persist();
}

function renderLayers() {
  const el = document.getElementById("layers-body");
  if (!el) return;
  el.innerHTML = "";
  for (const layer of layerRowsTopFirst()) {
    const count = featuresOnLayer(layer.id).length;
    const st = layerStyle(layer);
    // свотч: заливка, а для стилей ЛГР — мини-штриховка цветом зоны
    let swBg = st.fill || "transparent";
    if (!st.fill && st.hatch && st.hatch.color) {
      const a = st.hatch.cross ? 45 : (st.hatch.angle ?? 45);
      swBg = `repeating-linear-gradient(${90 - a}deg, ${st.hatch.color} 0 1px, transparent 1px 4px)`;
    }
    const row = document.createElement("div");
    row.className = "layer-row" + (layer.id === state.activeLayerId ? " active" : "");
    row.draggable = true;
    row.dataset.lid = layer.id;
    row.innerHTML = `<span class="grip" title="перетащить — порядок отрисовки"><svg class="ic"><use href="#ic-grip"/></svg></span>
      <input type="checkbox" title="видимость" ${layer.visible ? "checked" : ""}>
      <span class="sw" style="background:${swBg};border-color:${st.stroke || "#999"}"></span>
      <span class="nm" title="сделать активным (сюда чертят инструменты)">${layer.title}</span><span class="cnt">${count || ""}</span>
      <button class="lrow-menu" title="действия со слоем"><svg class="ic"><use href="#ic-menu-dots"/></svg></button>`;
    row.querySelector("input").addEventListener("change", ev => {
      layer.visible = ev.target.checked;
      const sel = selectedFeature();
      if (!layer.visible && sel && layerOf(sel) === layer) {
        state.selected = null;
        renderProps();
      }
      state._ix = null;
      persist();
      draw();
    });
    // клик по имени/образцу — активный слой (чекбокс отвечает только за видимость)
    row.querySelector(".nm").addEventListener("click", () => setActiveLayer(layer.id));
    row.querySelector(".sw").addEventListener("click", () => setActiveLayer(layer.id));
    const menuBtn = row.querySelector(".lrow-menu");
    menuBtn.addEventListener("click", ev => {
      ev.stopPropagation();
      const r = menuBtn.getBoundingClientRect();
      openLayerMenu(layer, r.right, r.bottom);
    });
    row.addEventListener("contextmenu", ev => {
      ev.preventDefault();
      openLayerMenu(layer, ev.clientX, ev.clientY);
    });
    // перетаскивание для смены порядка отрисовки
    row.addEventListener("dragstart", ev => {
      ev.dataTransfer.setData("text/plain", layer.id);
      ev.dataTransfer.effectAllowed = "move";
      row.classList.add("dragging");
    });
    row.addEventListener("dragend", () => {
      row.classList.remove("dragging");
      el.querySelectorAll(".layer-row").forEach(r =>
        r.classList.remove("drop-before", "drop-after"));
    });
    row.addEventListener("dragover", ev => {
      ev.preventDefault();
      const rect = row.getBoundingClientRect();
      const before = (ev.clientY - rect.top) < rect.height / 2;
      row.classList.toggle("drop-before", before);
      row.classList.toggle("drop-after", !before);
    });
    row.addEventListener("dragleave", () =>
      row.classList.remove("drop-before", "drop-after"));
    row.addEventListener("drop", ev => {
      ev.preventDefault();
      const src = ev.dataTransfer.getData("text/plain");
      const rect = row.getBoundingClientRect();
      const before = (ev.clientY - rect.top) < rect.height / 2;
      reorderLayer(src, layer.id, before);
    });
    el.appendChild(row);
  }
}

// ---------- контекстное меню слоя (логика QGIS) ----------
function closePopups() {
  document.querySelectorAll(".ctx-menu, .modal-overlay").forEach(n => n.remove());
}
function openLayerMenu(layer, x, y) {
  closePopups();
  const menu = document.createElement("div");
  menu.className = "ctx-menu";
  const items = [
    ["Сделать активным", () => setActiveLayer(layer.id)],
    ["Таблица атрибутов…", () => openAttributeTable(layer)],
    ["Форматирование…", () => openLayerFormat(layer)],
    ["Приблизить к слою", () => zoomToLayer(layer.id)],
    ["Переименовать…", () => renameLayer(layer)],
  ];
  for (const [label, fn] of items) {
    const it = document.createElement("div");
    it.className = "ctx-item";
    it.textContent = label;
    it.addEventListener("click", ev => { ev.stopPropagation(); closePopups(); fn(); });
    menu.appendChild(it);
  }
  if (layer.user_created) {
    const del = document.createElement("div");
    del.className = "ctx-item danger";
    del.textContent = "Удалить слой…";
    del.addEventListener("click", ev => { ev.stopPropagation(); closePopups(); deleteLayer(layer); });
    menu.appendChild(del);
  }
  document.body.appendChild(menu);
  // не вылезать за правый/нижний край
  const mw = menu.offsetWidth, mh = menu.offsetHeight;
  menu.style.left = Math.min(x, window.innerWidth - mw - 6) + "px";
  menu.style.top = Math.min(y, window.innerHeight - mh - 6) + "px";
  setTimeout(() => document.addEventListener("click", closePopups, { once: true }), 0);
}

// ---------- новый слой («+» в панели «Слои») ----------
function openNewLayerDialog() {
  closePopups();
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  const kindOptions = BASE_KINDS.map(b =>
    `<option value="${b.kind}">${b.label}</option>`).join("");
  overlay.innerHTML = `<div class="modal fmt-modal">
    <div class="modal-head">Новый слой</div>
    <label>Тип объектов<select id="nl-kind">${kindOptions}</select></label>
    <label>Название слоя<input type="text" id="nl-title" placeholder="напр. Озеленение" autofocus></label>
    <label>Стиль (библиотека)<select id="nl-style">${stylePickerOptions()}</select></label>
    <div class="modal-actions">
      <span class="spacer"></span>
      <button id="nl-cancel">Отмена</button>
      <button id="nl-create" class="primary">Создать</button>
    </div></div>`;
  document.body.appendChild(overlay);
  const $ = id => overlay.querySelector("#" + id);
  $("nl-title").focus();
  const create = () => {
    const kind = $("nl-kind").value;
    const title = $("nl-title").value.trim() ||
      BASE_KIND_BY_KIND[kind].label;
    const styleRef = $("nl-style").value || null;
    const L = createUserLayer({ kind, title, styleId: styleRef });
    closePopups();
    renderLayers();
    setActiveLayer(L.id);   // сразу готов чертить — не нужно искать слой в списке
    persist();
    toast(`Слой «${title}» создан и стал активным`);
  };
  $("nl-title").addEventListener("keydown", ev => { if (ev.key === "Enter") create(); });
  $("nl-create").addEventListener("click", create);
  $("nl-cancel").addEventListener("click", closePopups);
  overlay.addEventListener("click", ev => { if (ev.target === overlay) closePopups(); });
}

// ---------- выбор стиля из системной библиотеки (default + Эталон ЛГР) ----------
// Опции сгруппированы по group из библиотеки; value = style_id.
function stylePickerOptions(selectedId) {
  const groups = new Map();
  for (const [sid, s] of Object.entries(STYLES_V2)) {
    if (!s.title) continue;              // безымянные/служебные не предлагаем
    const g = s.group || "Базовые";
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push([sid, s.title]);
  }
  let html = `<option value=""${selectedId ? "" : " selected"}>— как у слоя —</option>`;
  for (const [g, items] of groups) {
    html += `<optgroup label="${g}">`;
    for (const [sid, title] of items.sort((a, b) => a[1].localeCompare(b[1], "ru")))
      html += `<option value="${sid}"${sid === selectedId ? " selected" : ""}>${title}</option>`;
    html += `</optgroup>`;
  }
  return html;
}

// ---------- форматирование слоя ----------
function toHexColor(c, fallback) {
  if (!c) return fallback;
  if (c[0] === "#") return c.slice(0, 7);
  const m = c.match(/rgba?\(([^)]+)\)/);
  if (m) {
    const [r, g, b] = m[1].split(",").map(x => parseInt(x.trim()));
    return "#" + [r, g, b].map(v => (v || 0).toString(16).padStart(2, "0")).join("");
  }
  return fallback;
}
function openLayerFormat(layer) {
  closePopups();
  const origFmt = layer.fmt ? { ...layer.fmt } : null;   // для отмены
  const cur = layerStyle(layer);
  const hasFill = cur.fill != null && cur.fill !== "transparent";
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `<div class="modal fmt-modal">
    <div class="modal-head">Форматирование · ${layer.title}</div>
    <label>Библиотечный стиль (Эталон ЛГР / базовые)
      <select id="fmt-preset">${stylePickerOptions(layer.fmt && layer.fmt.style_ref)}</select></label>
    <label class="chk"><input type="checkbox" id="fmt-hasfill" ${hasFill ? "checked" : ""}> заливка</label>
    <label>Цвет заливки<input type="color" id="fmt-fill" value="${toHexColor(cur.fill, "#faf0bf")}"></label>
    <label>Цвет обводки<input type="color" id="fmt-stroke" value="${toHexColor(cur.stroke, "#888888")}"></label>
    <label>Толщина обводки<input type="number" id="fmt-width" value="${cur.width ?? 1}" min="0.2" max="8" step="0.1"></label>
    <label class="chk"><input type="checkbox" id="fmt-dash" ${cur.dash ? "checked" : ""}> пунктир</label>
    <div class="modal-actions">
      <button id="fmt-reset">Сбросить</button>
      <span class="spacer"></span>
      <button id="fmt-cancel">Отмена</button>
      <button id="fmt-apply" class="primary">Применить</button>
    </div></div>`;
  document.body.appendChild(overlay);
  const $ = id => overlay.querySelector("#" + id);
  // fmt из полей модалки; выбранный пресет несёт hatch/line_label/dash целиком
  const collect = () => {
    const ref = $("fmt-preset").value;
    if (ref && STYLES_V2[ref]) {
      const p = STYLES_V2[ref];
      return { style_ref: ref, stroke: p.stroke, width: p.width,
               fill: p.fill || null, dash: p.dash || null,
               hatch: p.hatch || null, line_label: p.line_label || null,
               line_marker: p.line_marker || null, double: p.double || null };
    }
    return {
      stroke: $("fmt-stroke").value,
      width: Math.max(0.2, parseFloat($("fmt-width").value) || 1),
      fill: $("fmt-hasfill").checked ? $("fmt-fill").value : null,
      dash: $("fmt-dash").checked ? [6, 4] : null,
    };
  };
  // выбор пресета заполняет поля его значениями (дальше можно подстроить)
  $("fmt-preset").addEventListener("change", () => {
    const ref = $("fmt-preset").value;
    if (ref && STYLES_V2[ref]) {
      const p = STYLES_V2[ref];
      $("fmt-hasfill").checked = !!p.fill;
      if (p.fill) $("fmt-fill").value = toHexColor(p.fill, "#faf0bf");
      $("fmt-stroke").value = toHexColor(p.stroke, "#888888");
      $("fmt-width").value = p.width ?? 1;
      $("fmt-dash").checked = !!p.dash;
    }
    layer.fmt = collect(); draw();
  });
  // живой предпросмотр: правка любого поля = ручной режим (сброс пресета)
  overlay.querySelectorAll("input").forEach(inp =>
    inp.addEventListener("input", () => {
      $("fmt-preset").value = "";
      layer.fmt = collect(); draw();
    }));
  const restore = () => {                 // отмена/клик мимо — вернуть как было
    if (origFmt) layer.fmt = origFmt; else delete layer.fmt;
    closePopups(); renderLayers(); draw();
  };
  $("fmt-apply").addEventListener("click", () => {
    layer.fmt = collect();
    closePopups(); renderLayers(); draw(); persist();
  });
  $("fmt-cancel").addEventListener("click", restore);
  $("fmt-reset").addEventListener("click", () => {
    delete layer.fmt; closePopups(); renderLayers(); draw(); persist();
  });
  overlay.addEventListener("click", ev => { if (ev.target === overlay) restore(); });
}

// ---------- таблица атрибутов слоя (логика QGIS) ----------
function openAttributeTable(layer) {
  closePopups();
  const feats = featuresOnLayer(layer.id);
  const keys = [];
  for (const f of feats)
    for (const k of Object.keys(f.props || {}))
      if (!k.startsWith("_") && !keys.includes(k)) keys.push(k);
  const metric = f => {
    if (f.ring) return (ringArea(f.ring) / 10000).toFixed(2) + " га";
    if (f.line) return lineLen(f.line).toFixed(0) + " м";
    return "точка";
  };
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  const head = `<tr><th>#</th>${keys.map(k => `<th>${k}</th>`).join("")}<th>геометрия</th></tr>`;
  const rows = feats.map((f, i) => {
    const cells = keys.map(k => `<td>${f.props[k] ?? ""}</td>`).join("");
    return `<tr data-fid="${f.id}"><td>${i + 1}</td>${cells}<td>${metric(f)}</td></tr>`;
  }).join("");
  overlay.innerHTML = `<div class="modal attr-modal">
    <div class="modal-head">Таблица атрибутов · ${layer.title} <span class="muted">(${feats.length})</span>
      <button class="modal-x" title="Закрыть"><svg class="ic"><use href="#ic-close"/></svg></button></div>
    <div class="attr-scroll">${feats.length
      ? `<table class="attr-table"><thead>${head}</thead><tbody>${rows}</tbody></table>`
      : `<div class="muted" style="padding:14px">В слое нет объектов</div>`}</div>
    <div class="modal-actions"><span class="muted">клик по строке — выделить и приблизить</span></div>
  </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector(".modal-x").addEventListener("click", closePopups);
  overlay.addEventListener("click", ev => { if (ev.target === overlay) closePopups(); });
  overlay.querySelectorAll("tbody tr").forEach(tr =>
    tr.addEventListener("click", () => {
      const f = state.features.find(x => x.id === +tr.dataset.fid);
      if (!f) return;
      state.selected = f.id;
      if (!layer.visible) { layer.visible = true; renderLayers(); }
      closePopups();
      zoomToFeature(f);
      renderProps();
    }));
}

// ---------- журнал источников (снимки НСПД/ФГИС ТП, шаг 6) ----------
function renderSources() {
  const el = document.getElementById("sources-body");
  if (!el) return;
  if (!state.sources.length) {
    el.className = "muted"; el.textContent = "Пока не импортировано"; return;
  }
  el.className = "";
  el.innerHTML = state.sources.map(s => {
    const sha = s.sha8 || (s.sha256 || "").slice(0, 8);
    const date = (s.fetched_at || "").slice(0, 10);
    return `<div class="src-row" title="снимок ${s.id}">
      <span class="src-name">${s.source}</span>
      <span class="src-meta">${date} · ${s.count} об. · ${sha}</span></div>`;
  }).join("");
}

// снимок из ответа импорта → журнал; diff → тост «источник изменился»
function recordSource(snapshot, diff) {
  if (!snapshot) return;
  if (!state.sources.some(s => s.id === snapshot.id)) {
    state.sources.unshift(snapshot);
    if (state.sources.length > 50) state.sources.pop();
  }
  renderSources(); persist();
  if (diff && (diff.added.length || diff.removed.length || diff.changed.length))
    toast(`Источник изменился: +${diff.added.length} −${diff.removed.length} ~${diff.changed.length}`);
}

// журнал снимков сервера — источник истины (сливаем с локальным)
async function fetchSources() {
  try {
    const r = await fetch("/api/sources");
    if (!r.ok) return;
    const list = await r.json();
    const byId = new Map(state.sources.map(s => [s.id, s]));
    for (const s of list) byId.set(s.id, s);
    state.sources = [...byId.values()]
      .sort((a, b) => (b.fetched_at || "").localeCompare(a.fetched_at || ""));
    renderSources();
  } catch (e) { /* сервер без /api/sources — журнал только локальный */ }
}

function deleteSelected() {
  if (state.selected == null) return;
  snapshot();
  state.features = state.features.filter(f => f.id !== state.selected);
  state.selected = null; afterChange();
}

// ---------- добавление и правка фигур ----------
// layerId (не kind!) — иначе при двух слоях одного вида (built-in + созданный
// в панели) объект всегда падал бы в первый слой этого kind, игнорируя
// реально активный слой (тот же класс бага, что был в MODEL-01 на бэкенде).
function addFeature(layerId, geom) {
  snapshot();
  const L = LAYER_BY_ID[layerId];
  const f = { id: state.nextId++, layer_id: layerId,
             props: L ? L.defaults() : {}, ...geom };
  upgradeFeature(f);
  state.features.push(f);
  state.selected = f.id;
  afterChange();
  return f;
}
function finishDrawing() {
  const d = state.drawing;
  const L = activeLayer();
  if (!d || !L) { state.drawing = null; return; }
  const geom = TOOL_GEOM[state.tool];
  if (geom === "polygon" && d.pts.length >= 3) addFeature(L.id, { ring: d.pts });
  else if (geom === "polyline" && state.tool !== "dim" && d.pts.length >= 2)
    addFeature(L.id, { line: d.pts });
  state.drawing = null; state.typed = "";
  draw();
}
function rotateSelected() {
  const f = selectedFeature();
  if (!f || f.point) return;
  snapshot();
  const pts = featurePts(f);
  const cx = pts.reduce((a, p) => a + p[0], 0) / pts.length;
  const cy = pts.reduce((a, p) => a + p[1], 0) / pts.length;
  for (const p of pts) {
    const dx = p[0] - cx, dy = p[1] - cy;
    p[0] = cx - dy; p[1] = cy + dx;   // 90° против часовой
  }
  afterChange();
}
function duplicateSelected() {
  const f = selectedFeature();
  if (!f) return;
  const g = gridStep();
  const copy = JSON.parse(JSON.stringify(f));
  copy.id = state.nextId++;
  for (const p of featurePts(copy)) { p[0] += g; p[1] -= g; }
  snapshot();
  state.features.push(copy);
  state.selected = copy.id;
  afterChange();
}
function nudgeSelected(dx, dy) {
  const f = selectedFeature();
  if (!f) return;
  snapshot();
  for (const p of featurePts(f)) { p[0] += dx; p[1] += dy; }
  afterChange();
}
function placeTypedPoint() {
  const base = lastDrawingPt();
  const dist = parseFloat(state.typed.replace(",", "."));
  if (!base || !state.mouse || !isFinite(dist) || dist <= 0) { state.typed = ""; return; }
  const a = Math.atan2(state.mouse[1] - base[1], state.mouse[0] - base[0]);
  state.drawing.pts.push([base[0] + dist * Math.cos(a), base[1] + dist * Math.sin(a)]);
  state.typed = "";
  draw();
}

// ---------- хит-тест ----------
function hitTest(wx, wy) {
  const tolW = 7 / state.view.k;
  for (const layer of [...LAYERS_V2].reverse()) {
    if (!layer.visible) continue;
    for (let i = state.features.length - 1; i >= 0; i--) {
      const f = state.features[i];
      if (layerOf(f) !== layer) continue;
      if (f.point && Math.hypot(f.point[0] - wx, f.point[1] - wy) < tolW + 4 / state.view.k) return f;
      if (f.line && nearChain(wx, wy, f.line, tolW) !== null) return f;
      if (f.ring && (layer.kind === "boundary" ? nearChain(wx, wy, [...f.ring, f.ring[0]], tolW) !== null
                                               : pointInRing(wx, wy, f.ring))) return f;
    }
  }
  return null;
}

// ---------- события мыши ----------
cv.addEventListener("contextmenu", e => e.preventDefault());
cv.addEventListener("mousedown", e => {
  const [wxr, wyr] = s2w(e.offsetX, e.offsetY);
  if (e.button === 2 || e.button === 1 || (e.button === 0 && spaceDown)) {
    state.pan = { sx: e.offsetX, sy: e.offsetY, tx: state.view.tx, ty: state.view.ty };
    return;
  }
  if (e.button !== 0) return;
  const s = cursorPoint(wxr, wyr);
  if (state.tool === "select") {
    const cur = selectedFeature();
    if (cur) {
      const vi = vertexAt(cur, wxr, wyr);
      if (vi != null) {
        if (e.altKey) {   // Alt+клик — удалить вершину
          const pts = featurePts(cur);
          const min = cur.ring ? 3 : 2;
          if (!cur.point && pts.length > min) {
            snapshot(); pts.splice(vi, 1); afterChange();
          }
          return;
        }
        state.edit = { f: cur, vi, moved: false,
                       companions: sharedCompanions(cur, vi) };
        return;
      }
    }
    const f = hitTest(wxr, wyr);
    state.selected = f ? f.id : null;
    if (f) state.edit = { f, vi: "body", last: [wxr, wyr], moved: false };
    draw(); renderProps();
  } else if (state.tool === "measure") {
    if (!state.measure || state.measure.b) state.measure = { a: s.p, b: null };
    else state.measure.b = s.p;
    draw();
  } else if (state.tool === "point") {
    const L = activeLayer();
    if (L && L.geometry_type === "point") addFeature(L.id, { point: s.p });
  } else if (state.tool === "rect" && !state.drawing) {
    // протягивание — прямоугольник; одиночный клик — контур по точкам
    state.drag = { a: s.p, b: s.p, rect: true, moved: false };
  } else if (state.tool === "dim" || TOOL_GEOM[state.tool]) {
    if (!state.drawing) { state.drawing = { pts: [] }; state.typed = ""; }
    if (state.tool === "dim") {
      state.drawing.pts.push(s.p);
      if (state.drawing.pts.length === 2) {
        const pts = state.drawing.pts;
        state.drawing = null;
        addFeature(LAYER_BY_KIND["dim"].id, { line: pts });
      } else draw();
      return;
    }
    const first = state.drawing.pts[0];
    if (first && TOOL_GEOM[state.tool] === "polygon" && state.drawing.pts.length > 2 &&
        Math.hypot(first[0] - s.p[0], first[1] - s.p[1]) < 12 / state.view.k) {
      finishDrawing();
    } else {
      state.drawing.pts.push(s.p);
      state.typed = "";
      draw();
    }
  }
});
cv.addEventListener("mousemove", e => {
  const [wx, wy] = s2w(e.offsetX, e.offsetY);
  document.getElementById("st-coords").textContent = `x: ${wx.toFixed(1)}  y: ${wy.toFixed(1)} м`;
  if (state.pan) {
    state.view.tx = state.pan.tx + (e.offsetX - state.pan.sx);
    state.view.ty = state.pan.ty + (e.offsetY - state.pan.sy);
    draw(); return;
  }
  if (state.edit) {
    const ed = state.edit;
    if (!ed.moved) { snapshot(); ed.moved = true; }
    if (ed.vi === "body") {
      const dx = wx - ed.last[0], dy = wy - ed.last[1];
      ed.last = [wx, wy];
      for (const p of featurePts(ed.f)) { p[0] += dx; p[1] += dy; }
    } else {
      // исключаем из привязок свою фигуру и всех компаньонов общей вершины
      const ex = new Set([ed.f.id]);
      for (const c of (ed.companions || [])) ex.add(c.f.id);
      const s = snapPoint(wx, wy, ex);
      state.snapHit = s;
      const pts = featurePts(ed.f);
      pts[ed.vi][0] = s.p[0]; pts[ed.vi][1] = s.p[1];
      for (const c of (ed.companions || [])) {
        const cpts = featurePts(c.f);
        cpts[c.vi][0] = s.p[0]; cpts[c.vi][1] = s.p[1];
      }
    }
    state._ix = null;
    draw(); return;
  }
  const s = cursorPoint(wx, wy);
  state.snapHit = s;
  state.mouse = s.p;
  document.getElementById("st-snap").textContent = s.kind ? `привязка: ${s.kind}` : "";
  if (state.drag && state.drag.rect) {
    state.drag.b = s.p;
    if (Math.hypot(s.p[0] - state.drag.a[0], s.p[1] - state.drag.a[1]) * state.view.k > 4)
      state.drag.moved = true;
    draw(); return;
  }
  if (state.tool === "select") {
    const cur = selectedFeature();
    cv.style.cursor = (cur && vertexAt(cur, wx, wy) != null) ? "move"
      : hitTest(wx, wy) ? "pointer" : "default";
    if (state.guides.length) draw();
  }
  if (state.drawing || state.tool !== "select") draw();
});
// Слушаем на window, а не на #cv: если отпустить кнопку за пределами
// холста (над панелью/тулбаром), локальный слушатель #cv это событие
// не увидит — pan/edit/drag «залипнут», и вид будет произвольно
// скакать при следующем движении мыши, создавая впечатление, что
// холст не реагирует на клики.
window.addEventListener("mouseup", e => {
  if (state.pan) { state.pan = null; return; }
  if (state.edit) {
    const moved = state.edit.moved;
    state.edit = null;
    if (moved) afterChange();
    return;
  }
  if (state.drag && state.drag.rect) {
    const { a, b, moved } = state.drag;
    state.drag = null;
    const L = activeLayer();
    if (moved && Math.abs(a[0] - b[0]) > 1 && Math.abs(a[1] - b[1]) > 1) {
      if (L && L.geometry_type === "polygon")
        addFeature(L.id, { ring: [[a[0], a[1]], [b[0], a[1]], [b[0], b[1]], [a[0], b[1]]] });
    } else if (!moved) {
      // клик без протягивания — произвольный контур по точкам
      state.drawing = { pts: [a] };
      state.typed = "";
      draw();
    } else draw();
  }
});
// потеря фокуса окна (alt-tab, системный диалог) посреди жеста —
// та же защита, чтобы состояние не осталось залипшим
window.addEventListener("blur", () => {
  state.pan = null;
  if (state.edit) { state.edit = null; }
  if (state.drag) { state.drag = null; draw(); }
});
cv.addEventListener("dblclick", e => {
  e.preventDefault();
  if (state.drawing) { finishDrawing(); return; }
  // двойной клик по ребру выбранной фигуры — вставка вершины
  if (state.tool === "select") {
    const f = selectedFeature();
    if (!f || f.point) return;
    const [wx, wy] = s2w(e.offsetX, e.offsetY);
    const chain = f.ring ? [...f.ring, f.ring[0]] : f.line;
    const i = nearChain(wx, wy, chain, 7 / state.view.k);
    if (i !== null) {
      snapshot();
      const q = nearestOnSeg([wx, wy], chain[i], chain[i + 1]);
      featurePts(f).splice(i + 1, 0, q);
      afterChange();
    }
  }
});
cv.addEventListener("wheel", e => {
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
  const [wx, wy] = s2w(e.offsetX, e.offsetY);
  state.view.k = Math.min(40, Math.max(0.05, state.view.k * factor));
  state.view.tx = e.offsetX - wx * state.view.k;
  state.view.ty = e.offsetY + wy * state.view.k;
  draw();
}, { passive: false });

// ---------- клавиатура (по кодам клавиш — не зависит от раскладки) ----------
const TOOL_CODES = { KeyV: "select", KeyM: "measure", KeyD: "dim" };
// старые предметные клавиши живут как пресеты: слой + естественный инструмент
const PRESET_CODES = {
  KeyG: "project.territory.boundary", KeyZ: "project.tp.func_zone",
  KeyO: "source.constraints.restrict", KeyB: "project.apo.buildings",
  KeyP: "project.apo.public_zones", KeyL: "project.apo.red_lines",
  KeyS: "project.social.objects",
};
document.addEventListener("keydown", e => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
  if (e.key === "Shift") { shiftDown = true; if (state.drawing) draw(); return; }
  if (e.code === "Space") { spaceDown = true; e.preventDefault(); return; }
  if ((e.metaKey || e.ctrlKey) && e.code === "KeyZ") {
    e.preventDefault(); e.shiftKey ? redo() : undo(); return;
  }
  if ((e.metaKey || e.ctrlKey) && e.code === "KeyD") {
    e.preventDefault(); duplicateSelected(); return;
  }
  // набор длины цифрами при рисовании
  if (state.drawing && /^[0-9.,]$/.test(e.key)) { state.typed += e.key; draw(); return; }
  if (state.drawing && e.key === "Backspace") {
    state.typed = state.typed.slice(0, -1); draw(); return;
  }
  if (e.key === "Enter") {
    if (state.drawing && state.typed) placeTypedPoint();
    else finishDrawing();
    return;
  }
  if (e.key === "Escape") {
    if (state.typed) { state.typed = ""; draw(); return; }
    if (state.drawing) { state.drawing = null; draw(); return; }
    if (state.measure) { state.measure = null; draw(); return; }
    state.selected = null; draw(); renderProps(); return;
  }
  if (e.key === "Delete" || e.key === "Backspace") { deleteSelected(); return; }
  if (e.key.startsWith("Arrow")) {
    const step = e.shiftKey ? 1 : gridStep();
    const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0],
                ArrowUp: [0, step], ArrowDown: [0, -step] }[e.key];
    if (d && state.selected != null) { e.preventDefault(); nudgeSelected(...d); }
    return;
  }
  if (e.code === "KeyX") { setOsnap(!state.osnap); return; }
  if (e.code === "KeyC" && !e.metaKey && !e.ctrlKey) { setGridSnap(!state.gridSnap); return; }
  if (e.code === "KeyF") { fitView(); return; }
  if (e.code === "KeyR") { rotateSelected(); return; }
  const tool = TOOL_CODES[e.code];
  if (tool) { setTool(tool); return; }
  const preset = PRESET_CODES[e.code];
  if (preset) applyPreset(preset);
});
document.addEventListener("keyup", e => {
  if (e.key === "Shift") { shiftDown = false; if (state.drawing) draw(); }
  if (e.code === "Space") spaceDown = false;
});

// ---------- инструменты, сетка, кнопки ----------
function updateLayerStatus() {
  const el = document.getElementById("st-layer");
  const L = activeLayer();
  if (el) el.textContent = L ? `слой: ${L.title}` : "";
}
function setTool(tool, opts = {}) {
  state.tool = tool; state.drawing = null; state.drag = null;
  state.edit = null; state.typed = "";
  if (tool !== "measure") state.measure = null;
  // геом-инструмент против несовместимого слоя — слой переключается сам
  if (!opts.keepLayer && GEOM_OF_TOOL[tool] && !toolFitsLayer(tool, activeLayer())) {
    const fit = LAYERS_V2.find(l => !l.annotation &&
                                    l.geometry_type === GEOM_OF_TOOL[tool]);
    if (fit) { state.activeLayerId = fit.id; renderLayers(); }
  }
  updateLayerStatus();
  document.querySelectorAll("#toolbar button[data-tool]").forEach(
    b => b.classList.toggle("active", b.dataset.tool === tool));
  cv.style.cursor = tool === "select" ? "default" : "crosshair";
  draw();
}
function setActiveLayer(id) {
  const L = LAYER_BY_ID[id];
  if (!L) return;
  // import-only (источник) и аннотационные слои — не цели рисования: иначе
  // объект молча уходил бы в проектный слой (LAYER_BY_KIND по kind)
  if (L.import_only || L.annotation) {
    toast(`Слой «${L.title}» заполняется только импортом — рисовать в него нельзя`);
    return;
  }
  state.activeLayerId = id;
  state.drawing = null; state.typed = "";
  // несовместимый инструмент — переключается на естественный для слоя
  if (GEOM_OF_TOOL[state.tool] && !toolFitsLayer(state.tool, L))
    setTool(naturalToolFor(L), { keepLayer: true });
  renderLayers(); updateLayerStatus(); persist(); draw();
}
// быстрый пресет: слой + его естественный инструмент (клавиши G Z O B P L S)
function applyPreset(layerId) {
  const L = LAYER_BY_ID[layerId];
  if (!L) return;
  state.activeLayerId = layerId;
  setTool(naturalToolFor(L), { keepLayer: true });
  renderLayers();
}
document.querySelectorAll("#toolbar button[data-tool]").forEach(
  b => b.addEventListener("click", () => setTool(b.dataset.tool)));

function setOsnap(v) {
  state.osnap = v;
  document.getElementById("btn-snap").classList.toggle("active", v);
  const chk = document.getElementById("obj-snap");
  if (chk) chk.checked = v;
}
function setGridSnap(v) {
  state.gridSnap = v;
  const chk = document.getElementById("grid-snap");
  if (chk) chk.checked = v;
  draw();
}
on("basemap-show", "change", e => {
  basemap.on = e.target.checked;
  if (basemap.on && basemap.originLon == null) initBasemap().then(draw);
  draw();
});
on("basemap-opacity", "input", e => {
  basemap.opacity = +e.target.value / 100;
  draw();
});
on("btn-snap", "click", () => setOsnap(!state.osnap));
on("btn-zoom-in", "click", () => zoomBy(1.25));
on("btn-zoom-out", "click", () => zoomBy(0.8));
on("btn-zoom-fit", "click", fitView);
on("obj-snap", "change", e => setOsnap(e.target.checked));
on("grid-snap", "change", e => setGridSnap(e.target.checked));
on("grid-show", "change", e => { state.gridShow = e.target.checked; draw(); });
on("grid-step", "change", e => { state.gridMode = e.target.value; draw(); });
on("btn-undo", "click", undo);
on("btn-redo", "click", redo);
on("btn-clear", "click", () => {
  snapshot(); state.features = []; state.selected = null; afterChange();
});
on("p-density", "change", refreshTep);
on("p-ratio", "change", refreshTep);

async function download(url, filename) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ features: state.features, params: params(),
                           basemap: basemap.on,  // подложка включена → ортофото в альбоме и на печати
                           name: document.getElementById("project-name").value,
                           layers: userLayersManifest() }) });
  if (!r.ok) { alert("Ошибка сборки: " + (await r.text()).slice(0, 200)); return; }
  const blob = await r.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  if (filename.endsWith(".pdf")) window.open(a.href, "_blank");
  a.download = filename; a.click();
}
on("btn-album", "click", () => download("/api/album", "grado_agk_album.pdf"));
on("btn-grado", "click", () => download("/api/grado", "project.grado"));
on("btn-dxf", "click", () => download("/api/dxf", "project.dxf"));
on("btn-print", "click", () => download("/api/print", "chertezh.pdf"));

// открытие проекта .grado (round-trip с QGIS)
on("btn-open", "click", () => document.getElementById("grado-file").click());
on("grado-file", "change", async e => {
  const file = e.target.files[0];
  if (!file) return;
  e.target.value = "";
  try {
    const r = await fetch("/api/open-grado", { method: "POST",
      headers: { "Content-Type": "application/octet-stream" }, body: file });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    snapshot();
    state.features = data.features.map(f => upgradeFeature({ id: state.nextId++, ...f }));
    if (data.name) document.getElementById("project-name").value = data.name;
    state.selected = null;
    afterChange();
    fitView();
    toast(`Открыт проект: ${data.features.length} объектов`);
  } catch (err) {
    alert("Не удалось открыть проект: " + String(err).slice(0, 200));
  }
});

// мост браузерного расширения: опрос входящих выгрузок
let toastTimer = null;
function toast(msg) {
  const el = document.getElementById("st-toast");
  el.textContent = msg;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.textContent = ""; }, 5000);
}
let serverDown = false;
async function pollInbox() {
  try {
    const r = await fetch("/api/inbox");
    const data = await r.json();
    if (serverDown) {
      // сервер был недоступен (перезапуск/сон) и снова ответил — досасываем
      // то, что могло устареть за это время, без ручного F5
      serverDown = false;
      initStyles(); fetchSources(); refreshTep();
      toast("Связь с сервером восстановлена");
    }
    document.getElementById("st-bridge").textContent =
      data.bridge ? "мост 8081: вкл" : "мост 8081: занят (QGIS)";
    let added = 0;
    for (const item of data.items) {
      if (!item.features.length) continue;
      if (!added) snapshot();
      for (const f of item.features)
        state.features.push(upgradeFeature({ id: state.nextId++, ...f }));
      added += item.features.length;
      recordSource(item.snapshot, item.diff);   // снимок моста → журнал
    }
    if (added) {
      afterChange();
      fitView();
      const src = data.items[0].source === "fgis_tp" ? "ФГИС ТП" : "НСПД";
      toast(`Мост: +${added} объектов (${src})`);
    }
  } catch (e) {
    if (!serverDown) {
      serverDown = true;
      document.getElementById("st-core").textContent = "сервер недоступен — переподключение…";
    }
  }
}
setInterval(pollInbox, 2500);
pollInbox();

// импорт захвата НСПД (JSON браузерного моста GRADO)
on("btn-nspd", "click", () => document.getElementById("nspd-file").click());
on("nspd-file", "change", async e => {
  const file = e.target.files[0];
  if (!file) return;
  e.target.value = "";
  try {
    const payload = JSON.parse(await file.text());
    const r = await fetch("/api/import-nspd", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ payload }) });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    if (!data.features.length) { alert("В захвате нет полигонов НСПД"); return; }
    snapshot();
    for (const f of data.features)
      state.features.push(upgradeFeature({ id: state.nextId++, ...f }));
    state.selected = null;
    recordSource(data.snapshot, data.diff);   // снимок импорта → журнал
    afterChange();
    fitView();
  } catch (err) {
    alert("Не удалось импортировать захват: " + String(err).slice(0, 200));
  }
});

// импорт выгрузки ГИС ОГД (ZIP с портала, произвольный набор слоёв)
on("btn-gisogd", "click", () => document.getElementById("gisogd-file").click());
on("gisogd-file", "change", async e => {
  const file = e.target.files[0];
  if (!file) return;
  e.target.value = "";
  try {
    const r = await fetch("/api/import-gisogd", { method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: await file.arrayBuffer() });
    if (!r.ok) throw new Error(await r.text());
    const data = await r.json();
    if (data.features.length) {
      snapshot();
      for (const f of data.features)
        state.features.push(upgradeFeature({ id: state.nextId++, ...f }));
      state.selected = null;
      recordSource(data.snapshot, data.diff);
      afterChange();
      fitView();
    }
    if (data.notes && data.notes.length)
      toast(`ОГД: +${data.features.length} объектов · ${data.notes.join("; ")}`);
    else if (data.features.length)
      toast(`ОГД: +${data.features.length} объектов`);
    else
      alert("В архиве не нашлось распознанных слоёв");
  } catch (err) {
    alert("Не удалось импортировать выгрузку ОГД: " + String(err).slice(0, 200));
  }
});

// ---------- демо-наполнение ----------
on("btn-demo", "click", () => {
  snapshot();
  const B = [[0, 0], [650, 0], [650, 180], [520, 180], [520, 420], [300, 420],
             [300, 560], [60, 560], [60, 300], [0, 300]];
  state.features = [];
  state.nextId = 1;
  const add = (kind, geom, props = {}) => {
    const L = LAYER_BY_KIND[kind];
    state.features.push(upgradeFeature(
      { id: state.nextId++, kind, props: { ...(L ? L.defaults() : {}), ...props }, ...geom }));
  };
  add("boundary", { ring: B });
  add("zone", { ring: [[60, 180], [520, 180], [520, 420], [60, 420]] }, { zone_title: "Ж-1" });
  // вершина [60,180] делает границу с Ж-1 повершинно общей (покрытие)
  add("zone", { ring: [[0, 0], [520, 0], [520, 180], [60, 180], [0, 180]] }, { zone_title: "О-1" });
  add("restrict", { ring: [[520, 0], [650, 0], [650, 180], [520, 180]] });
  for (let r = 0; r < 3; r++) for (let c = 0; c < 5; c++)
    add("building", { ring: [[90 + c * 82, 215 + r * 62], [120 + c * 82, 215 + r * 62],
                             [120 + c * 82, 232 + r * 62], [90 + c * 82, 232 + r * 62]] },
        { floors: [9, 12, 14, 12, 9][c] });
  add("public", { ring: [[90, 40], [220, 40], [220, 130], [90, 130]] });
  add("redline", { line: [[-30, 190], [400, 190], [400, 590]] }, { radius: 60 });
  add("social", { point: [470, 350] });
  state.selected = null;
  afterChange();
  fitView();
});

// ---------- старт ----------
function applyRestoredState(d) {
  // пользовательские слои — ДО остального восстановления: layersVisible/
  // layerOrder/layerFmt/activeLayerId ссылаются на их id по значению
  if (Array.isArray(d.userLayers)) {
    for (const spec of d.userLayers) {
      if (LAYER_BY_ID[spec.layer_id]) continue;  // уже есть (повторный restore)
      const kind = KIND_BY_SEMANTIC_CLASS[spec.code];
      if (!kind) continue;  // неизвестный класс (снимок из будущей версии) — пропускаем не роняя
      createUserLayer({ kind, title: spec.title, styleId: spec.style_id,
                       id: spec.layer_id });
    }
  }
  state.features = (d.features || []).map(upgradeFeature);  // legacy kind → слой v2
  state.nextId = d.nextId || 1;
  if (d.layerTitles) {
    for (const [id, title] of Object.entries(d.layerTitles))
      if (LAYER_BY_ID[id]) LAYER_BY_ID[id].title = title;
  }
  if (d.layersVisible) {
    for (const [id, vis] of Object.entries(d.layersVisible))
      if (LAYER_BY_ID[id]) LAYER_BY_ID[id].visible = !!vis;
  } else if (d.hidden) {
    // сохранение старого формата: hidden было по kind
    for (const [kind, hid] of Object.entries(d.hidden))
      if (LAYER_BY_KIND[kind]) LAYER_BY_KIND[kind].visible = !hid;
  }
  if (Array.isArray(d.layerOrder)) {
    // восстановить порядок отрисовки; неизвестные (добавленные позже) — в конец
    const pos = new Map(d.layerOrder.map((id, i) => [id, i]));
    LAYERS_V2.sort((a, b) =>
      (pos.has(a.id) ? pos.get(a.id) : 1e9) - (pos.has(b.id) ? pos.get(b.id) : 1e9));
  }
  if (d.layerFmt) {
    for (const [id, fmt] of Object.entries(d.layerFmt))
      if (LAYER_BY_ID[id]) LAYER_BY_ID[id].fmt = fmt;
  }
  if (d.activeLayerId && LAYER_BY_ID[d.activeLayerId])
    state.activeLayerId = d.activeLayerId;
  if (Array.isArray(d.sources)) state.sources = d.sources;
  if (d.name) document.getElementById("project-name").value = d.name;
  if (d.density) document.getElementById("p-density").value = d.density;
  if (d.ratio) document.getElementById("p-ratio").value = d.ratio;
}
(function restore() {
  try {
    const raw = localStorage.getItem("grado_studio_v1");
    if (raw) { applyRestoredState(JSON.parse(raw)); return; }
  } catch (e) { /* повреждённое сохранение игнорируем, пробуем файловый автосейв ниже */ }
  // localStorage пуст (новый браузер/профиль, приватный режим, чистка данных
  // сайта) — пробуем резервную копию на диске сервера
  fetch("/api/autosave").then(r => r.ok ? r.json() : null).then(d => {
    if (!d || !d.features) return;
    applyRestoredState(d);
    draw(); renderProps(); renderLayers(); renderSources(); refreshTep(); fitView();
    toast("Восстановлено из файлового автосохранения");
  }).catch(() => {});
})();
on("project-name", "change", persist);
window.studio = { state, addFeature, refreshTep, fitView, snapPoint, gridStep,
                  layerOf, styleOf, layerStyle, upgradeFeature, LAYERS_V2, STYLES_V2,
                  setTool, setActiveLayer, applyPreset, activeLayer,
                  reorderLayer, openLayerMenu, openAttributeTable, openLayerFormat,
                  zoomToLayer, renderLayers };
on("btn-refresh-src", "click", fetchSources);
on("btn-new-layer", "click", openNewLayerDialog);
// переключатель темы (canvas-theme.js): смена темы → перечитать палитру
// холста и перерисовать. Тема на <html> уже выставлена до загрузки app.js.
on("btn-theme", "click", () => { if (window.toggleTheme) window.toggleTheme(); });
window.onThemeChange = () => { draw(); renderLayers(); };
setTool("select");
renderLayers();
renderSources();
requestAnimationFrame(resize);
refreshTep();
initStyles();
fetchSources();
