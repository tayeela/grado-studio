/* ГРАДО 2 · слои проекта как в QGIS: дерево с порядком прорисовки (перетаскивание), видимость,
   оформление (единое / категории / диапазоны / правила / знаки ЛГР), подписи, таблица атрибутов.
   Строка инструментов как в AutoCAD: рисование в текущий слой, вершины, перенос, удаление, замеры;
   правка выгрузок с возвратом к исходной.
   Данные слоя живут в DATA[key].fc (WGS84) — их же читает граф анализа. */

const CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"], OTHER = "#9aa1a8";
const RAMPS = { blue: ["#dcebfa", "#a8cbf1", "#6fa6e6", "#2a78d6", "#1a4f94", "#0f3363"], brick: ["#fbe4d8", "#f5b698", "#ec875b", "#cf5a2c", "#933717", "#5e200c"], green: ["#e1f2e3", "#b2dcb7", "#7ec188", "#3f9a4f", "#1f6e31", "#10461e"], grey: ["#f2f2f2", "#d4d4d4", "#aaaaaa", "#7a7a7a", "#4d4d4d", "#262626"] };
const PICK = [...CAT, "#1d1d1f", "#5f6368", "#9aa1a8", "#d4d4d4", "#ffffff", "#b3261e", "#1f7a4d", "#7a4b2a", ...RAMPS.blue.slice(0, 4), ...RAMPS.brick.slice(0, 4)];
const ramp = (n, k) => k === 1 ? [RAMPS[n][3]] : Array.from({ length: k }, (_, i) => RAMPS[n][Math.round(i * (RAMPS[n].length - 1) / Math.max(1, k - 1))]);
// цвет стиля из чужого файла проекта пишется в атрибуты разметки — только настоящий цвет, иначе значение по умолчанию
const HEX = /^#[0-9a-f]{3,8}$/i, okc = (c, d) => typeof c === "string" && HEX.test(c) ? c : d;
function cleanStyle(st) {
  st.fill = okc(st.fill, "#9aa1a8"); st.stroke = okc(st.stroke, "#5f6368");
  st.rules.elseFill = okc(st.rules.elseFill, "#dddddd"); (st.rules.list || []).forEach(r => { r.fill = okc(r.fill, "#9aa1a8"); });
  Object.keys(st.cat.colors || {}).forEach(k => { st.cat.colors[k] = okc(st.cat.colors[k], "#9aa1a8"); });
  return st;
}
const ST = o => cleanStyle(stDefaults(o));
const stDefaults = o => Object.assign({ mode: "single", fill: "#9aa1a8", stroke: "#5f6368", width: 1, opacity: .7, hatch: false, label: "", labelSize: 11,
  cat: { field: "", colors: {}, off: [] }, grad: { field: "", n: 5, ramp: "blue", method: "quantile" }, rules: { list: [], elseFill: "#dddddd", elseHide: false } }, o);
// порядок по умолчанию: сверху вниз (первый — самый верхний), как на опорном плане: линии и подписи, застройка,
// оси и точки транспорта, зоны ограничений (штриховка и контур — прозрачны), участки, покрытия (проезжая часть, вода,
// озеленение), внизу — площадные зоны планирования. Прежний порядок клал проезжую часть Яндекса под все зоны — её не было видно.
const PREFERRED = ["gisogd.red_lines", "gisogd.demolition", "egko.addresses", "egko.fences", "relief.contours",
  "egko.buildings", "nspd.buildings", "yandex.buildings", "osm.buildings",
  "yandex.transport", "yandex.parking", "osm.social", "yandex.roads", "osm.roads", "egko.paths", "yandex.road_edges",
  "gisogd.okn", "nspd.zouit", "gisogd.zouit", "gisogd.szz", "gisogd.vodookhr", "gisogd.ppt", "gisogd.pmt", "gisogd.agr", "gisogd.gpzu", "gisogd.krt",
  "nspd.parcels", "calc.uds_ya", "calc.uds_osm", "yandex.hd_roads", "egko.roads", "egko.water_labels", "egko.water", "osm.water", "yandex.water", "egko.green", "yandex.green",
  "gisogd.admin", "gisogd.pzz_zones", "gisogd.pzz_sub", "gisogd.func_zones", "gisogd.func_zones_tinao", "osm.landuse", "yandex.landuse"];
// застройка из разных источников — одна и та же: на холсте видна одна, по этому порядку (ЕГКО — самая полная)
const BUILDINGS = ["egko.buildings", "nspd.buildings", "yandex.buildings", "osm.buildings"];
// опорный план на холсте после сборки раздела: остальные выгруженные слои есть в дереве, но выключены
const CANVAS_BASE = ["gisogd.red_lines", "calc.uds_ya", "egko.roads", "egko.water", "egko.green", "nspd.parcels"];
/* «Упорядочить слои»: выгрузки встают по опорному порядку (свои слои и импорт — сверху, как были), из нескольких
   слоёв застройки остаётся видимым один. Ничего не удаляется. */
function tidyLayers(fresh) {
  const rank = k => { const i = PREFERRED.indexOf(k); return i < 0 ? -1 : i; };
  const order = LYR.map((l, i) => [l, i]).sort((a, b) => (rank(a[0].key) - rank(b[0].key)) || (a[1] - b[1])).map(x => x[0]);
  LYR.splice(0, LYR.length, ...order);
  if (fresh) LYR.forEach(l => { if (fresh.has(l.key)) l.visible = CANVAS_BASE.includes(l.key) || BUILDINGS.includes(l.key); });
  let hidden = [];
  const on = BUILDINGS.map(lyr).filter(l => l?.visible);
  on.slice(1).forEach(l => { l.visible = false; hidden.push(l.title); });
  normGroups(); dataRev++; applyOrder(); renderTree(); renderRight();
  return { buildings: on[0]?.title, hidden };
}
function defaultStyle(key, fc) {
  const zones = lib => { const colors = {}; fc.features.forEach(f => { const v = String(f.properties.naimfunkzony ?? f.properties.naimfunkzo ?? f.properties["Вид зоны"] ?? ""); const z = lib[v.toLowerCase()]; if (z) colors[v] = z.fill; }); return colors; };
  return ST(({
    "nspd.parcels": { fill: "#ffffff", stroke: "#7d8288", width: .8, opacity: 0 },
    "nspd.buildings": { fill: "#cbc6be", stroke: "#4d4d4d", width: .8, opacity: 1 },
    "nspd.zouit": { fill: "#7a4ab0", stroke: "#7a4ab0", hatch: true },
    "osm.roads": { mode: "cat", width: 1.6, cat: { field: "Тип дороги", colors: {}, off: [] } },
    "osm.buildings": { fill: "#dcd7ce", stroke: "#8a857c", width: .7, opacity: 1 },
    "osm.water": { fill: "#b9d6ec", stroke: "#6fa6e6", width: .8, opacity: 1 },
    "osm.landuse": { mode: "cat", opacity: .35, stroke: "#b8b2a3", width: .5, cat: { field: "Землепользование", colors: {}, off: [] } },
    "gisogd.func_zones": { mode: "cat", opacity: .8, stroke: "#3c3c3c", width: .5, cat: { field: "naimfunkzony", colors: zones(GPZ), off: [] } },
    "gisogd.func_zones_tinao": { mode: "cat", opacity: .8, stroke: "#3c3c3c", width: .5, cat: { field: "Вид зоны", colors: zones(NMZ), off: [] } },
    "gisogd.szz": { fill: "#4a3aa7", stroke: "#4a3aa7", hatch: true, width: 1.2 },
    "gisogd.vodookhr": { fill: "#2a78d6", stroke: "#2a78d6", hatch: true, width: 1.2 },
    // ЗОУИТ по СПРИТ: вид зоны — цветом штриховки знака Эталона ЛГР (береговые — синим контуром знака)
    "gisogd.zouit": { mode: "cat", hatch: true, width: 1.2, cat: { field: "Вид зоны", off: [], colors: {
      "Водоохранная зона": "#0669b2", "Прибрежная защитная полоса": "#3a86d4", "Береговая полоса": "#0018b8", "Зона затопления": "#5b8fd9",
      "Зона сильного подтопления": "#8f63a8", "Зона умеренного подтопления": "#6fa4e0", "Зона слабого подтопления": "#5fb89c",
      "Санитарно-защитная зона (ПЗЗ)": "#62a51b", "Зона охраняемого объекта": "#694720", "Зона военного объекта": "#e3007b",
      "Охранная зона радиотехнического объекта": "#eb880e", "Охранная зона ООПТ": "#b8a800", "Охранная зона объектов электроэнергетики": "#eb880e",
      "Охранная зона линий и сооружений связи": "#b8a800", "Охранная зона пунктов наблюдений": "#694720", "Охранная зона геодезических пунктов": "#694720",
      "Особо охраняемая зелёная территория": "#009f3c" } } },
    "gisogd.red_lines": { mode: "lgr", fill: "#d7191c", width: 1.3 },
    // ПЗЗ: подзоны окрашены по предельной плотности — она задана чаще высоты (серые — не установлена или «по факту»); зоны — контуром
    "gisogd.pzz_sub": { mode: "grad", opacity: .45, stroke: "#8a5a00", width: .6, grad: { field: "Плотность, тыс. м²/га", n: 5, ramp: "brick", method: "quantile" } },
    "gisogd.pzz_zones": { fill: "#ffffff", opacity: 0, stroke: "#6a3d9a", width: 1.4 },
    "gisogd.okn": { mode: "cat", hatch: true, width: 1.2, cat: { field: "Вид зоны", colors: {}, off: [] } },
    "gisogd.demolition": { fill: "#b3261e", stroke: "#b3261e", hatch: true, width: 1.4 },
    "relief.contours": { fill: "#a0663a", width: .8, label: "Высота, м", labelSize: 10 },
    // документация по планировке и административное деление (листы раздела «Существующее положение»)
    "gisogd.ppt": { mode: "cat", hatch: true, width: 1.2, hatchPat: "135", cat: { field: "Вид зоны", colors: {}, off: [] } },
    "gisogd.gpzu": { fill: "#35c2d6", stroke: "#1b8a99", width: .8, opacity: .35 },
    "egko.water_labels": { fill: "#1f8fe0", width: 1, label: "Подпись", labelSize: 11, marker: false, labelColor: "#1f8fe0" },
    "gisogd.pmt": { fill: "#2f9e44", stroke: "#2f9e44", width: 1.6, opacity: 0 },
    "gisogd.agr": { fill: "#d6336c", stroke: "#b3261e", hatch: true, hatchPat: "45", width: 1 },
    "gisogd.krt": { fill: "#e0892f", stroke: "#b35d00", hatch: true, hatchPat: "45", width: 1.2 },
    "gisogd.admin": { mode: "cat", opacity: 0, fill: "#ffffff", stroke: "#3c3c3c", width: 1, label: "Наименование", labelSize: 11, cat: { field: "Уровень", colors: { "округ": "#3c3c3c", "район": "#8a8a8a" }, off: [] } },
    // ЕГКО — картооснова: те же тона, что у зданий НСПД/OSM, улиц эскиза и воды OSM, чтобы подложка не спорила с проектом
    "egko.buildings": { fill: "#d6d1c7", stroke: "#6f6a62", width: .7, opacity: 1 },
    "egko.fences": { fill: "#5f5a52", width: .7 },
    "egko.addresses": { fill: "#6b6b6b", stroke: "#ffffff", width: .5, opacity: 1 },
    "egko.paths": { fill: "#b09b7a", width: .8 },
    "egko.roads": { fill: "#e4e1da", stroke: "#b7b2a8", width: .5, opacity: .9 },
    "egko.water": { fill: "#b9d6ec", stroke: "#6fa6e6", width: .8, opacity: 1 },
    "egko.green": { fill: "#cfe3b4", stroke: "#8fb573", width: .4, opacity: .7 },
    // Яндекс — подложка для анализа и эскиза, спокойные тона; куски тайлов склеены по стыкам, контур без швов
    "yandex.buildings": { fill: "#d8d3c9", stroke: "#8f897f", width: .6, opacity: 1 },
    // проезжая часть — холодный серый с кромкой: тёплые здания и светлый фон с ней не сливаются (прежний #e6e3dc был не виден)
    "yandex.hd_roads": { fill: "#d5dae0", stroke: "#9ea7b1", width: .6, opacity: 1 },
    // УДС полигонами (листы раздела): без контура — стыки проезжей части и проездов по осям не видны
    "calc.uds_ya": { fill: "#d5dae0", stroke: "#9ea7b1", width: 0, opacity: 1 },
    "calc.uds_osm": { fill: "#dfe2e6", stroke: "#a3a3a3", width: 0, opacity: 1 },
    "yandex.roads": { fill: "#8f887c", width: .9 },       // оси — одним тоном: классы Яндекса («4_link», «8») владельцу ничего не говорят
    "yandex.road_edges": { fill: "#9c968b", width: .6 },
    "yandex.landuse": { mode: "cat", opacity: .3, stroke: "#b8b2a3", width: 0, cat: { field: "ft_type_name", colors: {}, off: [] } },
    "yandex.green": { fill: "#cfe4b3", stroke: "#9cbf80", width: 0, opacity: .7 },
    "yandex.water": { fill: "#bcd8ee", stroke: "#78aee6", width: 0, opacity: 1 },
    "yandex.parking": { fill: "#5b7bb0", stroke: "#ffffff", width: .6, opacity: 1 },
    "yandex.transport": { fill: "#7a5c99", stroke: "#ffffff", width: .8, opacity: 1 },
  })[key] || (fc.features.some(f => f.properties._lt) ? { mode: "lgr" } : { fill: CAT[LYR.length % CAT.length], stroke: "#3d3d3d" }));
}

/* ---------- модель ---------- */
const LYR = [];                       // сверху вниз
const UNDO = [], REDO = [];           // отмена и возврат: записи правок объектов и стиля (pushUndo ниже)
const GROUPS = [];                    // группы слоёв как в QGIS: {id, title, visible, open}; слои группы идут в LYR подряд
let CUR = null;                       // текущий слой (выделен в дереве)
let SEL = [];                         // выбранные объекты [{key, f}] — из одного или нескольких слоёв
const BIG = 20000;                    // слой крупнее рисуется через WebGL: 100 000 объектов без задержек
const lyr = key => LYR.find(l => l.key === key);
const grp = id => GROUPS.find(g => g.id === id);
const shown = l => l.visible && (!l.group || grp(l.group)?.visible !== false);   // видимость слоя с учётом его группы
const isBig = l => l.style.mode !== "lgr" && (layerSrc[l.key]?.getFeatures().length || 0) > BIG;
const geomOf = fc => { const g = fc.features.find(f => f.geometry)?.geometry?.type || ""; return /Point/.test(g) ? "point" : /Line/.test(g) ? "line" : "poly"; };
// поля с русскими названиями (подписанные сервером) — первыми, служебные поля порталов — после
const SYMK = "gradosym";              // служебное: номер цвета объекта в крупном слое, в файл и таблицы не попадает
const hiddenField = k => k.startsWith("_") || k === SYMK || k === "geometry";
const fieldsOfKey = key => (DATA[key]?.fields || []).filter(k => !hiddenField(k)).sort((a, b) => (/[а-яё]/i.test(b) - /[а-яё]/i.test(a)));
function ensureLayer(key, title, geom) {
  let l = lyr(key);
  if (!l) {
    const fc = DATA[key]?.fc || { features: [] };
    l = { key, title: title || DATA[key]?.title || key, visible: true, layerOpacity: 1, open: false, group: null, geom: geom || geomOf(fc), style: defaultStyle(key, fc), cache: new Map() };
    if (l.style.mode === "cat") assignCats(l, true);
    const rank = k => { const i = PREFERRED.indexOf(k); return i < 0 ? -1 : i; };
    // свои слои и импорт — наверх; выгрузки — по привычному порядку (линии над застройкой, зоны внизу)
    const r = rank(key), at = r < 0 ? 0 : LYR.findIndex(x => rank(x.key) > r);
    LYR.splice(at < 0 ? LYR.length : at, 0, l);
    layerSrc[key] ||= new ol.source.Vector();
    ALLMAPS.forEach(m => attachLayer(m, l));
    if (!CUR) CUR = key;
  }
  normGroups(); applyOrder(); renderTree(); renderRight();
  return l;
}
/* Слой на карте — холст со стилем на каждый объект. У крупного слоя (больше BIG объектов) два представления
   одних и тех же объектов (замер на 100 000 полигонов: холст — 140 мс на кадр в обзоре и 15 мс вблизи,
   WebGL — 45 мс в любом масштабе):
   · издалека, где в кадре тысячи объектов, рисует видеокарта (WebGL): класс знака считается один раз
     в служебное свойство SYMK (без подчёркиваний — WebGL их не допускает), цвет берётся по таблице;
   · вблизи, где в кадре до ~15 000 объектов, — обычный холст со всем оформлением, подписями и правкой. */
const kindOf = l => (isBig(l) ? "gl" : "cv") + (l.style.label ? "+t" : "");
function glSwitchRes(l) {                 // разрешение (м/пикс.), крупнее которого в кадре больше ~15 000 объектов слоя
  const ex = layerSrc[l.key].getExtent(), n = layerSrc[l.key].getFeatures().length, area = Math.max(1, ol.extent.getArea(ex));
  return Math.sqrt(15000 * area / n / (1600 * 900));
}
// видимость по масштабу (как в QGIS): слой виден только крупнее 1:maxDen; разрешение карты — через широту центра
const denToRes = den => den * 0.000264583 / Math.cos(ol.proj.toLonLat(sharedView.getCenter())[1] * Math.PI / 180);
const outOfScale = l => !!l.style.maxDen && scaleDen(sharedView.getResolution()) > l.style.maxDen;
function olLayersFor(l) {
  const src = layerSrc[l.key], out = [], mr = l.style.maxDen ? denToRes(l.style.maxDen) : Infinity;
  l._kind = kindOf(l); l.gl = l._kind.startsWith("gl"); l._maxDen = l.style.maxDen || 0;
  const cv = new ol.layer.Vector({ source: src, style: (f, res) => styleFor(l, f, res), declutter: !!l.style.label, maxResolution: mr });
  if (l.gl) {
    symAll(l, false); const r = glSwitchRes(l);
    out.push(new ol.layer.WebGLVector({ source: src, style: glStyle(l), minResolution: r, maxResolution: mr, disableHitDetection: true }));
    cv.setMaxResolution(Math.min(r, mr));
  }
  out.push(cv);
  out.forEach((x, i) => { x.set("key", l.key); x.set("sub", i); x.set("gl", x instanceof ol.layer.WebGLVector); });
  return out;
}
function attachLayer(map, l) {
  if (map.getLayers().getArray().some(x => x.get("key") === l.key)) return;
  olLayersFor(l).forEach(x => map.addLayer(x));
}
function rebuildLayer(l) {
  ALLMAPS.forEach(m => { m.getLayers().getArray().filter(x => x.get("key") === l.key).forEach(x => m.removeLayer(x)); attachLayer(m, l); });
  applyOrder();
}
const mainOl = (map, key) => map.getLayers().getArray().find(x => x.get("key") === key && !x.get("gl"));   // холст: выбор и правка
window.attachDataLayers = map => LYR.forEach(l => attachLayer(map, l));
function applyOrder() {
  window.markDirty?.();
  ALLMAPS.forEach(m => m.getLayers().forEach(ml => { const l = lyr(ml.get("key")); if (!l) return; ml.setZIndex(10 + LYR.length - LYR.indexOf(l)); ml.setVisible(shown(l)); ml.setOpacity(l.layerOpacity); }));
}
// слои одной группы держатся подряд на месте первого из них; пустые группы исчезают
function normGroups() {
  const seen = new Set(), out = [];
  LYR.forEach(l => { if (l.group && !grp(l.group)) l.group = null; if (!l.group) return out.push(l); if (seen.has(l.group)) return; seen.add(l.group); out.push(...LYR.filter(x => x.group === l.group)); });
  LYR.splice(0, LYR.length, ...out);
  for (let i = GROUPS.length - 1; i >= 0; i--) if (!seen.has(GROUPS[i].id)) GROUPS.splice(i, 1);
}
/* Данные слоя: источник правды — объекты на карте (layerSrc). DATA[key].fc (GeoJSON WGS84 для графа,
   сохранения и выгрузки) собирается из них лениво, при первом чтении после правки: на слое в 100 000
   объектов правка одного объекта не переписывает весь слой. */
let revSeq = 0;
// у объекта без атрибутов OpenLayers пишет properties: null — дальше код везде ждёт объект
function writeFC(fs) { const o = GJ.writeFeaturesObject(fs); o.features.forEach(f => { if (f.properties) delete f.properties[SYMK]; else f.properties = {}; }); return o; }
function bindFC(key) {
  const d = DATA[key]; if (d.stale) return;
  let cache = d.fc || null; delete d.fc;
  Object.defineProperty(d, "fc", { configurable: true, enumerable: true, get: () => cache ||= writeFC(layerSrc[key].getFeatures()), set: v => { cache = v; } });
  Object.defineProperty(d, "stale", { value: () => { cache = null; } });
}
function setLayerData(key, fc, keepUndo = false) {
  const d = DATA[key]; d.original ||= fc;              // исходная выгрузка — тот же объект: он больше не меняется
  // объекты слоя заменяются новыми: записи отмены по старым объектам больше не к чему применить (отмена вернула бы
  // старую копию рядом с новой — дубль в СПП и ТЭП). Отмена стиля слоя остаётся
  if (!keepUndo && layerSrc[key].getFeatures().length) {           // «Вернуть исходную выгрузку» сама ставит запись, возвращающую эти объекты
    const stale = u => u.kind === "feat" && u.items.some(i => i.key === key);
    if (UNDO.some(stale) || REDO.some(stale)) { UNDO.splice(0, UNDO.length, ...UNDO.filter(u => !stale(u))); REDO.splice(0, REDO.length, ...REDO.filter(u => !stale(u))); syncRibbon(); }
  }
  layerSrc[key].clear(true); layerSrc[key].addFeatures(GJ.readFeatures(fc));
  syncFromSource(key, false); d.fc = fc;
  if (SEL.some(x => x.key === key)) setSel(SEL);                  // выбор старых объектов слоя снимается: правка ушла бы в никуда
}
/* правка на карте → DATA, которым питается граф */
function syncFromSource(key, edited = true) {
  const d = DATA[key], fs = layerSrc[key].getFeatures(); bindFC(key); d.stale();
  d.count = fs.length; d.rev = ++revSeq;
  if (fs.length) d.fields = [...new Set(fs.slice(0, 500).flatMap(f => f.getKeys().filter(k => k !== "geometry" && k !== SYMK)))];
  d.edited = fs.reduce((n, f) => n + (f.get("_edited") ? 1 : 0), 0);
  if (edited) dataRev++;
  const l = lyr(key);
  if (l) { l.cache.clear(); l._br = null; if (kindOf(l) !== l._kind) rebuildLayer(l); else if (l.gl) { symAll(l, true);            // номера классов пересчитаны — таблица цветов GPU тоже
    ALLMAPS.forEach(m => m.getLayers().forEach(x => { if (x.get("key") === l.key && x.get("gl")) x.setStyle(glStyle(l)); })); } }
  renderTree(); renderTable();
  if (edited) window.onLayerEdited?.(key);
}

/* ---------- оформление ---------- */
const isNum = v => typeof v === "number" || (v !== "" && v != null && !isNaN(+v));
const numOf = v => v == null || v === "" ? NaN : +v;   // пустое значение — «нет данных», а не ноль
function catValues(key, field) { const m = new Map(); layerSrc[key]?.getFeatures().forEach(f => { const v = String(f.get(field) ?? ""); m.set(v, (m.get(v) || 0) + 1); }); return [...m.entries()].sort((a, b) => b[1] - a[1]); }
function numFields(key) { const fs = layerSrc[key]?.getFeatures() || []; return fieldsOfKey(key).filter(k => fs.length && fs.slice(0, 300).every(f => f.get(k) == null || isNum(f.get(k)))); }
function assignCats(l, keep) {
  // поле по умолчанию — текстовое с немногими значениями (2–30): у «Наименования» каждый объект был бы своим классом
  const st = l.style;
  if (!st.cat.field) { const fs = fieldsOfKey(l.key), txt = fs.filter(k => !numFields(l.key).includes(k)), feats = layerSrc[l.key]?.getFeatures() || [];
    const nv = k => new Set(feats.slice(0, 5000).map(f => String(f.get(k) ?? ""))).size;
    st.cat.field = txt.find(k => { const n = nv(k); return n >= 2 && n <= 30; }) || txt[0] || fs[0] || ""; }
  const c = keep ? { ...st.cat.colors } : {}; let k = Object.keys(c).length;
  catValues(l.key, st.cat.field).forEach(([v]) => { if (!c[v]) c[v] = k < CAT.length ? CAT[k++] : OTHER; });
  st.cat.colors = c; if (!keep) st.cat.off = [];
}
function breaks(l) {
  const g = l.style.grad, v = (layerSrc[l.key]?.getFeatures() || []).map(f => numOf(f.get(g.field))).filter(x => !isNaN(x)).sort((a, b) => a - b); if (!v.length) return [0, 0];
  const b = [v[0]]; for (let i = 1; i < g.n; i++) b.push(+(g.method === "equal" ? v[0] + (v[v.length - 1] - v[0]) * i / g.n : v[Math.floor(i * v.length / g.n)]).toFixed(2)); b.push(v[v.length - 1]);
  const u = [...new Set(b)]; return u.length > 1 ? u : [u[0], u[0]];   // совпавшие границы — один класс, а не «16–16» четыре раза
}
function testRule(r, f) {
  const v = f.get(r.field), t = r.val; if (v == null) return false;
  if (r.op === "содержит") return String(v).toLowerCase().includes(String(t).toLowerCase());
  const n = isNum(v) && isNum(t), a = n ? +v : String(v), b = n ? +t : String(t);
  return { "=": a == b, "≠": a != b, ">": a > b, "<": a < b, "≥": a >= b, "≤": a <= b }[r.op];
}
function symbolOf(l, f) {
  const st = l.style; let fill = st.fill, hatch = st.hatch, hide = false;
  if (st.mode === "cat") { const v = String(f.get(st.cat.field) ?? ""); fill = st.cat.colors[v] || OTHER; hide = st.cat.off.includes(v); }
  else if (st.mode === "grad") { const b = l._br || (l._br = breaks(l)), v = numOf(f.get(st.grad.field)), cols = ramp(st.grad.ramp, (l._br || (l._br = breaks(l))).length - 1); const i = b.findIndex((x, k) => k > 0 && v <= x); fill = isNaN(v) ? OTHER : cols[Math.max(0, i - 1)] ?? cols[cols.length - 1]; }
  else if (st.mode === "rules") { const r = st.rules.list.find(r => r.field && testRule(r, f)); if (r) { fill = r.fill; hatch = r.hatch; } else { fill = st.rules.elseFill; hatch = false; hide = st.rules.elseHide; } }
  return { fill, hatch, hide };
}
const rgba = (hex, a) => { const c = [...ol.color.asArray(hex)]; c[3] = a; return c; };
const css = (hex, a) => `rgba(${rgba(hex, a).join(",")})`;
// labelColor — цвет подписи (надписи ЛГР — цветом знака), labelAngle — поле угла подписи (ГИС ОГД: по часовой стрелке),
// marker: false — слой подписей без значка точки: подпись стоит на самой точке
const upright = a => { a = ((a % 360) + 360) % 360; return a > 90 && a <= 270 ? a - 180 : a > 270 ? a - 360 : a; };
// угол подписи в градусах против часовой стрелки: _angle — вдоль границы своей папки (сервер), иначе угол ГИС ОГД
// textangle (он по часовой); ol.style.Text поворачивает по часовой — знак меняется
const labelDeg = f => f.get("_angle") != null ? +f.get("_angle") : -(+f.get("textangle") || 0);
const labelStyle = (l, f) => { const st = l.style, t = f.get(st.label); if (t == null || t === "") return null;
  const ang = st.labelAngle ? -upright(labelDeg(f)) * Math.PI / 180 : 0, bare = st.marker === false;
  return new ol.style.Style({ text: new ol.style.Text({ text: String(t), font: `${st.labelSize}px system-ui, sans-serif`, fill: new ol.style.Fill({ color: st.labelColor || "#1d1d1f" }), stroke: new ol.style.Stroke({ color: "#fff", width: 3 }), placement: l.geom === "line" ? "line" : "point", rotation: ang, rotateWithView: !!st.labelAngle, offsetY: l.geom === "point" && !bare ? -(2 + st.width * 2 + 1 + st.labelSize * 0.6 + 5) : 0, overflow: false }) }); };   // у точки подпись над знаком с зазором: знак — помеха для разведения подписей, задетая рамкой подпись скрывалась
// крупный слой: номер цвета в таблице l.pal у каждого объекта (-1 — скрыт категорией или правилом)
function symAll(l, notify) {
  const idx = new Map(); l.pal = [];
  layerSrc[l.key].getFeatures().forEach(f => {
    const s = symbolOf(l, f); let i = -1;
    if (!s.hide) { i = idx.get(s.fill); if (i === undefined) { i = l.pal.length; idx.set(s.fill, i); l.pal.push(s.fill); } }
    if (f.get(SYMK) !== i) f.set(SYMK, i, !notify);
  });
}
function glStyle(l) {
  const st = l.style, pal = l.pal.length ? l.pal : [st.fill];
  const m = a => pal.length === 1 ? css(pal[0], a) : ["match", ["get", SYMK], ...pal.slice(0, -1).flatMap((c, i) => [i, css(c, a)]), css(pal[pal.length - 1], a)];
  const style = l.geom === "poly" ? { "fill-color": m(st.hatch ? .22 : st.opacity), "stroke-color": st.hatch ? m(1) : css(st.stroke, st.width > 0 ? 1 : 0), "stroke-width": Math.max(st.width, .01) }   // штриховку WebGL не рисует — полупрозрачная заливка того же цвета
    : l.geom === "line" ? { "stroke-color": m(1), "stroke-width": st.width }
    : { "circle-radius": 2 + st.width * 2, "circle-fill-color": m(1), "circle-stroke-color": css(st.stroke, 1), "circle-stroke-width": 1 };
  return [{ filter: [">=", ["get", SYMK], 0], style }];
}
/* Полигон, обрезанный по области выгрузки (ЕГКО): рёбра на рамке — след обрезки, их не обводим, иначе дорога или газон
   получают «бордюр» по краю области. Точки среза лежат ровно на рамке (clip.py), поэтому сравнение точное. */
function frameless(ft) {
  const g = ft.getGeometry(), b = ft.get("_clip"); if (!b || !g) return g;
  const rev = g.getRevision(); if (ft._fl?.rev === rev) return ft._fl.g;
  const [x0, y0] = ol.proj.fromLonLat([b[0], b[1]]), [x1, y1] = ol.proj.fromLonLat([b[2], b[3]]);
  const onFrame = (a, c) => a[0] === c[0] && (a[0] === x0 || a[0] === x1) || a[1] === c[1] && (a[1] === y0 || a[1] === y1);
  const lines = [], polys = g.getType() === "MultiPolygon" ? g.getCoordinates() : [g.getCoordinates()];
  for (const p of polys) for (const r of p) {
    let cur = [];
    for (let i = 1; i < r.length; i++) {
      if (onFrame(r[i - 1], r[i])) { if (cur.length > 1) lines.push(cur); cur = []; }
      else { if (!cur.length) cur.push(r[i - 1]); cur.push(r[i]); }
    }
    if (cur.length > 1) lines.push(cur);
  }
  ft._fl = { rev, g: new ol.geom.MultiLineString(lines) }; return ft._fl.g;
}
// число объектов под правилом: считается один раз на версию данных слоя и набор правил (панель перерисовывается часто)
function ruleCount(l, i) {
  const sig = (DATA[l.key]?.rev ?? 0) + "|" + JSON.stringify(l.style.rules.list);
  if (l._rc?.sig !== sig) { const fs = layerSrc[l.key]?.getFeatures() || []; l._rc = { sig, n: l.style.rules.list.map(r => fs.filter(f => testRule(r, f)).length) }; }
  return l._rc.n[i] ?? 0;
}
function styleFor(l, f, res) {
  const st = l.style;
  const out = [];
  if (st.mode === "lgr") { out.push(redLineStyle(f)); }
  else {
    const s = symbolOf(l, f); if (s.hide) return null;
    // слой со смешанной геометрией (вода, транспорт): точка — знаком точки; линия в слое точек — линией, в слое полигонов — цветом контура
    const ft = f.getGeometry()?.getType() || "", g = /Point/.test(ft) ? "point" : /Line/.test(ft) && l.geom !== "line" ? (l.geom === "poly" ? "pline" : "line") : l.geom;
    const clip = g === "poly" && st.width > 0 && !!f.get("_clip");
    const key = `${s.fill}|${s.hatch}|${g}|${clip}|${st.hatchPat || "45"}|${st.hatchStep || 8}`; let base = l.cache.get(key);
    // контур цветом знака при штриховке (Эталон ЛГР: граница — своим цветом, штриховка — своим) и штрих контура
    const edge = s.hatch && !st.strokeOwn ? s.fill : st.stroke, dash = st.dash?.length ? st.dash : undefined;
    if (!base) {
      if (g === "line") base = new ol.style.Style({ stroke: new ol.style.Stroke({ color: s.fill, width: st.width, lineCap: dash ? "butt" : "round", lineJoin: "round", lineDash: dash }) });
      else if (g === "pline") base = new ol.style.Style({ stroke: new ol.style.Stroke({ color: edge, width: Math.max(st.width, 1), lineCap: "round", lineJoin: "round", lineDash: dash }) });
      else if (g === "point" && st.marker === false) base = [];
      else if (g === "point") base = new ol.style.Style({ image: new ol.style.Circle({ declutterMode: "obstacle", radius: 2 + st.width * 2, fill: new ol.style.Fill({ color: s.fill }), stroke: new ol.style.Stroke({ color: st.stroke, width: 1 }) }) });
      else if (clip) base = [new ol.style.Style({ fill: new ol.style.Fill({ color: s.hatch ? hatch(s.fill, st.hatchPat, st.hatchStep) : rgba(s.fill, st.opacity) }) }),
        new ol.style.Style({ geometry: frameless, stroke: new ol.style.Stroke({ color: edge, width: st.width, lineDash: dash }) })];
      else base = new ol.style.Style({ fill: new ol.style.Fill({ color: s.hatch ? hatch(s.fill, st.hatchPat, st.hatchStep) : rgba(s.fill, st.opacity) }), stroke: st.width > 0 ? new ol.style.Stroke({ color: edge, width: st.width, lineDash: dash }) : undefined });   // толщина 0 — без контура (холст с 0 рисует прежней толщиной)
      l.cache.set(key, base);
    }
    Array.isArray(base) ? out.push(...base) : out.push(base);
  }
  if (st.label && res < 4) { const t = labelStyle(l, f); if (t) out.push(t); }
  return out;
}
/* слои портала ГИС ОГД (ключ «ogd.<код>», окно «Исходные данные») — в оформлении карты портала: сервер переводит
   CartoCSS слоя в стиль ГРАДО (заливка, контур, штриховка, подпись). Один раз на слой: отметка style.portal
   сохраняется с проектом, дальше оформление ваше. Линии с кодом линии ГИС ОГД — знаками ЛГР (REDLN97). */
// Оформление, которое владелец задал слою сам (земельные участки — синий контур), сервер отдаёт с номером правки rev:
// слой, оформленный по прежней правке, перекрашивается один раз заново
let portalRun = null;                  // один проход за раз: проект открывается и догружается почти одновременно
async function portalStyles() {
  if (portalRun) return portalRun;
  portalRun = (async () => { try { await portalStylesOnce(); await labelAngles(); } finally { portalRun = null; } })();
  return portalRun;
}
async function portalStylesOnce() {
  const all = LYR.filter(l => l.key.startsWith("ogd."));
  if (!all.length) return;
  // код знака ЛГР из атрибутов слоя (зоны — zonelineco, надписи — textlineco), если он там есть
  const field = l => { for (const f of DATA[l.key]?.fc.features.slice(0, 50) || []) { const p = f.properties, v = p.zonelineco ?? p.textlineco; if (v != null && v !== "" && +v) return v; } return null; };
  let r; try { r = await api("/api/ogd_all/styles", { layers: Object.fromEntries(all.map(l => [l.key.slice(4), [l.geom, field(l)]])) }); } catch { return; }
  const rev = l => r.rev?.[l.key.slice(4)] || 1, done = l => l.style.portal === true ? 1 : l.style.portal || 0;
  const todo = all.filter(l => done(l) < rev(l));
  if (!todo.length) return;
  todo.forEach(l => {
    const s = r.styles[l.key.slice(4)]; if (!s || !Object.keys(s).length) { l.style.portal = rev(l); return; }
    const lgr = l.geom === "line" && DATA[l.key]?.fc.features.some(f => f.properties._lt || f.properties._miss);
    l.style = ST({ ...s, ...(lgr ? { mode: "lgr" } : {}), portal: rev(l) });
    if (l.style.mode === "cat") assignCats(l, true);
    l.cache.clear(); restyle(l);
  });
  renderTree(); renderRight(); window.markDirty?.();
}
/* подписи слоёв надписей ГИС ОГД, загруженных до v0.63, — угол вдоль границы своей папки (сервер считает по кэшу) */
async function labelAngles() {
  for (const l of LYR.filter(l => l.key.startsWith("ogd.") && l.style.labelAngle && l.geom === "point")) {
    const d = DATA[l.key], fs = d?.fc.features || [];
    if (!fs.length || fs.some(f => f.properties._angle != null)) continue;
    let r; try { r = await api("/api/ogd_all/label_angles", { code: l.key.slice(4), points: fs.map(f => f.geometry?.type === "Point" ? f.geometry.coordinates : [0, 0]) }); } catch { continue; }
    if (!r.angles.some(a => a != null)) continue;
    const fc = { ...d.fc, features: fs.map((f, i) => r.angles[i] == null ? f : { ...f, properties: { ...f.properties, _angle: r.angles[i] } }) };
    if (d.original === d.fc) d.original = fc;
    d.fc = fc; setLayerData(l.key, fc, true); l.cache.clear(); restyle(l);
  }
}
window.portalStyles = portalStyles;
function restyle(l) {
  l.cache.clear(); l._br = null;
  if (kindOf(l) !== l._kind || (l.style.maxDen || 0) !== l._maxDen) rebuildLayer(l);
  else if (l.gl) { symAll(l, false); ALLMAPS.forEach(m => m.getLayers().forEach(x => { if (x.get("key") === l.key) x.get("gl") ? x.setStyle(glStyle(l)) : x.changed(); })); }
  else layerSrc[l.key]?.changed();
  renderTree(); window.markDirty?.();
}

/* ---------- дерево слоёв ---------- */
function symHTML(l, color) {
  const st = l.style;
  if (st.mode === "lgr" && !color) return `<span class="sym line" style="border-top-color:#d7191c"></span>`;
  const c = color || (st.mode === "single" ? st.fill : st.mode === "cat" ? (Object.values(st.cat.colors)[0] || OTHER) : st.mode === "grad" ? ramp(st.grad.ramp, 3)[1] : (st.rules.list[0]?.fill || st.rules.elseFill));
  const c0 = c; { const c = esc(c0);
  if (l.geom === "line") return `<span class="sym line" style="border-top-color:${c}"></span>`;
  if (l.geom === "point") return `<span class="sym pt" style="background:${c}"></span>`;
  return `<span class="sym" style="${st.hatch && !color ? `background:repeating-linear-gradient(135deg,${c} 0 1px,transparent 1px 4px);border-color:${c}` : st.mode === "single" && st.opacity === 0 && !color ? `background:transparent;border-color:${esc(st.stroke)}` : `background:${c}`}"></span>`; }
}
function legendItems(l) {
  const st = l.style;
  if (st.mode === "cat") return catValues(l.key, st.cat.field).map(([v, n]) => ({ v, n, c: st.cat.colors[v] || OTHER, off: st.cat.off.includes(v), check: true }));
  if (st.mode === "grad") { const b = l._br || (l._br = breaks(l)), none = (layerSrc[l.key]?.getFeatures() || []).filter(f => isNaN(numOf(f.get(st.grad.field)))).length;
    return ramp(st.grad.ramp, b.length - 1).map((c, i) => ({ v: `${fmt(b[i], 1)} – ${fmt(b[i + 1], 1)}`, c })).concat(none ? [{ v: "нет значения", c: OTHER, n: none }] : []); }
  if (st.mode === "rules") return st.rules.list.map(r => ({ v: `${r.field} ${r.op} ${r.val}`, c: r.fill })).concat(st.rules.elseHide ? [] : [{ v: "остальные", c: st.rules.elseFill }]);
  return [];
}
// строка слоя в дереве (и в режиме «По листам»: extra — кнопка «убрать с листа»)
function rowHTML(l, ind, drag, extra = "") {
  const d = DATA[l.key], items = l.open ? legendItems(l).slice(0, 60) : [];
  return `<div class="tn${ind} ${shown(l) ? "" : "off"}" draggable="${drag}" data-lk="${esc(l.key)}" aria-selected="${CUR === l.key}">
      <button class="tw" data-tw="${esc(l.key)}" aria-label="Легенда" ${["cat", "grad", "rules"].includes(l.style.mode) ? "" : 'style="visibility:hidden"'}><i data-lucide="${l.open ? "chevron-down" : "chevron-right"}"></i></button>
      <input type="checkbox" data-vis="${esc(l.key)}" ${l.visible ? "checked" : ""} aria-label="Видимость">${symHTML(l)}
      <span class="nm${outOfScale(l) ? " outscale" : ""}" title="${esc(l.title)}${d?.source ? " — " + esc(d.source) : ""}${d?.fetched_at ? ", " + d.fetched_at : ""}${l.style.maxDen ? `. Виден крупнее 1:${fmt(l.style.maxDen)}` : ""}">${esc(l.title)}</span>
      ${d?.edited && d.original ? `<span class="badge" title="Объектов выгрузки изменено вручную">изм. ${d.edited}</span>` : ""}
      ${l.gl ? `<span class="badge gl" title="Крупный слой рисуется видеокартой (WebGL). Штриховка показывается полупрозрачной заливкой, подписи — на крупном масштабе.">GPU</span>` : ""}
      <span class="meta num">${fmt(d?.count ?? 0)}</span>
      ${extra}<button class="tw more" data-more="${esc(l.key)}" aria-label="Меню слоя"><i data-lucide="more-horizontal"></i></button></div>`
      + items.map(it => `<div class="tn leg${ind} ${it.off ? "off" : ""}">${it.check ? `<input type="checkbox" data-catoff="${esc(l.key)}|${esc(it.v)}" ${it.off ? "" : "checked"} aria-label="Показывать">` : ""}${symHTML(l, it.c)}<span class="nm">${esc(it.v || "—")}</span>${it.n != null ? `<span class="meta num">${it.n}</span>` : ""}</div>`).join("");
}
/* Режим дерева «По листам»: папка на каждый лист альбома, в ней ровно слои этого листа — у листа раздела его набор,
   у листа с видом видимые слои вида, у листа «текущая карта» видимые слои карты. Слой, нужный нескольким листам,
   стоит в нескольких папках: это один и тот же слой, видимость и оформление у него общие. Добавить слой на лист
   и убрать с листа можно прямо в папке — меняется состав листа (набор листа раздела или его вид). */
let BY_SHEET = false;
const SHEET_SHUT = new Set();
function sheetKeys(sh) {
  if (sh.panels) return [...new Set(sh.panels.flatMap(p => p.keys || []))];
  if (sh.keys) return sh.keys.slice();
  const v = sh.view && VIEWS.find(x => x.id === sh.view);
  return v ? v.layers.filter(x => x.visible).map(x => x.key) : null;      // null — лист показывает текущую карту
}
const sheetView = sh => !sh.keys && !sh.panels && sh.view ? VIEWS.find(x => x.id === sh.view) : null;
const sheetEditable = sh => !sh.panels && !!(sh.keys || sheetView(sh));
const mapSheets = () => ALBUM.sheets.filter(s => s.kind !== "title" && s.kind !== "tep");
function sheetTreeHTML() {
  const used = new Set(), sheets = mapSheets();
  const folder = (id, name, n, tools, note) => `<div class="tn gr" data-shk="${esc(id)}">
      <button class="tw" data-shtw="${esc(id)}" aria-label="${SHEET_SHUT.has(id) ? "Развернуть" : "Свернуть"} папку листа"><i data-lucide="${SHEET_SHUT.has(id) ? "chevron-right" : "chevron-down"}"></i></button>
      <i data-lucide="${SHEET_SHUT.has(id) ? "folder" : "folder-open"}" class="gi"></i><span class="nm" title="${esc(note || name)}">${esc(name)}</span><span class="meta num">${n}</span>${tools}</div>`;
  let h = sheets.length ? "" : `<div class="note">Листов пока нет: нарисуйте лист инструментом «Лист» или соберите раздел в окне «Листы». Папки слоёв появятся по листам.</div>`;
  sheets.forEach(sh => {
    const ks = sheetKeys(sh), ls = ks ? LYR.filter(l => ks.includes(l.key)) : LYR.filter(l => l.visible), ed = sheetEditable(sh);
    ls.forEach(l => used.add(l.key));
    const tools = `${ks ? `<button class="tw" data-shshow="${esc(sh.id)}" title="Показать на карте только слои этого листа"><i data-lucide="eye"></i></button>` : ""}<button class="tw more" data-shmore="${esc(sh.id)}" aria-label="Меню папки листа"><i data-lucide="more-horizontal"></i></button>`;
    h += folder(sh.id, `${ALBUM.sheets.indexOf(sh) + 1}. ${sh.title}`, ls.length, tools,
      ks ? (ed ? "Слои листа. Добавить слой — меню «…» папки, убрать — крестик у слоя" : "Слои листа раздела заданы шаблоном раздела") : "Лист показывает текущую карту: здесь видимые слои. Меню «…» → «Закрепить состав листа»");
    if (SHEET_SHUT.has(sh.id)) return;
    ls.forEach(l => { h += rowHTML(l, " in", false, ed ? `<button class="tw" data-shrm="${esc(sh.id)}|${esc(l.key)}" title="Убрать слой с листа «${esc(sh.title)}» (слой остаётся в проекте)"><i data-lucide="x"></i></button>` : ""); });
  });
  const rest = LYR.filter(l => !used.has(l.key));
  if (rest.length) {
    h += folder("_rest", "Не на листах", rest.length, "", "Слои, которых нет ни на одном листе");
    if (!SHEET_SHUT.has("_rest")) rest.forEach(l => { h += rowHTML(l, " in", false); });
  }
  return h;
}
function showSheet(sh) {
  const v = sheetView(sh); if (v) return applyView(v);
  const ks = sheetKeys(sh); if (!ks) return;
  LYR.forEach(l => { l.visible = ks.includes(l.key); }); GROUPS.forEach(g => { g.visible = true; });
  dataRev++; applyOrder(); renderTree(); window.markDirty?.();
}
function sheetSet(sh, key, on) {
  if (sh.keys) sh.keys = on ? [key, ...sh.keys.filter(k => k !== key)] : sh.keys.filter(k => k !== key);
  else {
    const v = sheetView(sh), l = lyr(key); if (!v || !l) return;
    const x = v.layers.find(y => y.key === key);
    if (x) x.visible = on; else if (on) v.layers.push({ key, visible: true, style: JSON.parse(JSON.stringify(l.style)), layerOpacity: l.layerOpacity });
  }
  window.markDirty?.(); renderTree(); window.renderSheets?.();
}
function sheetMenu(anchor, id) {
  const sh = ALBUM.sheets.find(s => s.id === id); if (!sh) return;
  const ks = sheetKeys(sh);
  showMenu(anchor, [
    ks ? ["Показать только слои листа", () => showSheet(sh)] : null,
    sh.center ? ["Найти лист на карте", () => window.selectSheetFrame?.(sh, true)] : null,
    !ks ? ["Закрепить состав листа: видимые сейчас слои", () => { const v = captureView(sh.title, false); VIEWS.push(v); sh.view = v.id; window.markDirty?.(); renderViews(); renderTree(); window.renderSheets?.(); toast(`Состав листа «${sh.title}» закреплён: вид «${sh.title}». Теперь слои листа меняются в его папке.`); }] : null,
    ...(sheetEditable(sh) ? LYR.filter(l => !ks.includes(l.key)).map(l => [`Добавить на лист: ${l.title}`, () => sheetSet(sh, l.key, true)]) : []),
  ].filter(Boolean));
}
function setBySheet(on) {
  BY_SHEET = on; ALBUM.meta.treeBySheet = on || undefined; const b = $("bBySheet"); if (b) b.setAttribute("aria-pressed", on);
  renderTree();
}
window.setBySheet = setBySheet;
function renderTree() {
  const el = $("layerTree"); if (!el) return;
  if (BY_SHEET && LYR.length) { el.innerHTML = sheetTreeHTML(); syncCurSelect(); syncStart(); icons(); return; }
  const res = (RESULT.sketch.length || RESULT.site) && PREVIEW_WINS.some(id => !$(id).hidden) ? `<div class="tgrp" title="Как предпросмотр в Grasshopper: виден, пока открыты окна «Граф», «Эскиз», «Варианты», «Объём» или «Сравнение». В проект эскиз попадает кнопкой «Принять в проект».">Предпросмотр графа${PREVIEW_WINS.some(id => !$(id).hidden) ? "" : " · скрыт"}</div>` + RES.map(r => `<label class="tn"><span class="tw"></span><input type="checkbox" data-res="${r.id}" ${r.on !== false ? "checked" : ""} aria-label="Показывать в предпросмотре"><span class="sym" style="background:${r.color}"></span><span class="nm">${r.title}</span><span class="meta num">${r.layer.getSource().getFeatures().length || ""}</span></label>`).join("") : "";
  if (!LYR.length) { el.innerHTML = `<div class="note">Слоёв пока нет. Нажмите «+» над списком и рисуйте, выберите инструмент рисования на панели сверху (слой появится сам) или загрузите источники в окне «Данные».</div>` + res; icons(); syncStart(); syncCurSelect(); return; }
  let h = "", prevG = null;
  LYR.forEach(l => {
    const g = l.group && grp(l.group);
    if (g && l.group !== prevG) {
      const n = LYR.filter(x => x.group === g.id).length;
      h += `<div class="tn gr ${g.visible ? "" : "off"}" draggable="true" data-gk="${esc(g.id)}" title="Группа слоёв: перетаскивается целиком, двойной щелчок — переименовать">
        <button class="tw" data-gtw="${esc(g.id)}" aria-label="${g.open ? "Свернуть" : "Развернуть"} группу"><i data-lucide="${g.open ? "chevron-down" : "chevron-right"}"></i></button>
        <input type="checkbox" data-gvis="${esc(g.id)}" ${g.visible ? "checked" : ""} aria-label="Видимость группы"><i data-lucide="${g.open ? "folder-open" : "folder"}" class="gi"></i>
        <span class="nm">${esc(g.title)}</span><span class="meta num">${n}</span>
        <button class="tw more" data-gmore="${esc(g.id)}" aria-label="Меню группы"><i data-lucide="more-horizontal"></i></button></div>`;
    }
    prevG = l.group;
    if (g && !g.open) return;
    h += rowHTML(l, g ? " in" : "", true);
  });
  el.innerHTML = h + res;
  syncCurSelect(); syncStart();
  icons();
}
const tree = () => $("layerTree");
document.addEventListener("click", e => {
  const t = e.target;
  if (!tree()?.contains(t)) return;
  const shtw = t.closest("[data-shtw]"); if (shtw) { const id = shtw.dataset.shtw; SHEET_SHUT.has(id) ? SHEET_SHUT.delete(id) : SHEET_SHUT.add(id); renderTree(); return; }
  const shshow = t.closest("[data-shshow]"); if (shshow) { const sh = ALBUM.sheets.find(s => s.id === shshow.dataset.shshow); if (sh) showSheet(sh); return; }
  const shmore = t.closest("[data-shmore]"); if (shmore) { sheetMenu(shmore, shmore.dataset.shmore); return; }
  const shrm = t.closest("[data-shrm]"); if (shrm) { const [id, k] = shrm.dataset.shrm.split("|"); const sh = ALBUM.sheets.find(s => s.id === id); if (sh) sheetSet(sh, k, false); return; }
  const tw = t.closest("[data-tw]"); if (tw) { const l = lyr(tw.dataset.tw); l.open = !l.open; renderTree(); return; }
  const gtw = t.closest("[data-gtw]"); if (gtw) { const g = grp(gtw.dataset.gtw); g.open = !g.open; window.markDirty?.(); renderTree(); return; }
  const more = t.closest("[data-more]"); if (more) { layerMenu(more, more.dataset.more); return; }
  const gmore = t.closest("[data-gmore]"); if (gmore) { groupMenu(gmore, gmore.dataset.gmore); return; }
  if (t.matches("input")) return;
  const row = t.closest("[data-lk]"); if (row) setCurrent(row.dataset.lk);
});
document.addEventListener("dblclick", e => {
  if (e.target.closest?.("[data-tw],[data-more],[data-gtw],[data-gmore],input")) return;
  const row = e.target.closest?.("#layerTree [data-lk]"); if (row) return renameLayer(row.dataset.lk);
  const gr = e.target.closest?.("#layerTree [data-gk]"); if (gr) renameGroup(gr.dataset.gk);
});
document.addEventListener("change", e => {
  const t = e.target; if (!tree()?.contains(t)) return;
  if (t.dataset.vis) { lyr(t.dataset.vis).visible = t.checked; dataRev++; applyOrder(); renderTree(); }      // видимость слоёв ограничений читает граф
  if (t.dataset.gvis) { grp(t.dataset.gvis).visible = t.checked; dataRev++; applyOrder(); renderTree(); }
  if (t.dataset.res) { RES.find(r => r.id === t.dataset.res).on = t.checked; syncPreview(); }
  if (t.dataset.catoff) { const [k, v] = t.dataset.catoff.split("|"); const l = lyr(k), st = l.style; pushStyleUndo(l, "cat"); st.cat.off = t.checked ? st.cat.off.filter(x => x !== v) : [...st.cat.off, v]; restyle(l); renderRight(); }
});
/* перетаскивание = порядок прорисовки: верхний в списке рисуется поверх.
   Слой, брошенный на слой, попадает в его группу; на верх заголовка группы — над группой, на низ — в группу.
   Группа перетаскивается целиком. */
let drag = null;                       // {key} слой или {gid} группа
const dropRow = e => e.target.closest?.("#layerTree [data-lk], #layerTree [data-gk]");
document.addEventListener("dragstart", e => {
  const row = dropRow(e); if (!row) return;
  drag = row.dataset.lk ? { key: row.dataset.lk } : { gid: row.dataset.gk };
  e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", ""); row.classList.add("dragging");
});
document.addEventListener("dragover", e => {
  const row = dropRow(e); if (!drag || !row) return; e.preventDefault();
  const r = row.getBoundingClientRect(); document.querySelectorAll("#layerTree .drop-a,#layerTree .drop-b").forEach(x => x.classList.remove("drop-a", "drop-b"));
  row.classList.add(e.clientY < r.top + r.height / 2 ? "drop-a" : "drop-b");
});
document.addEventListener("drop", e => {
  const row = dropRow(e); if (!drag || !row) return; e.preventDefault();
  const before = row.classList.contains("drop-a"), d = drag; drag = null;
  const moving = d.key ? [lyr(d.key)] : LYR.filter(l => l.group === d.gid);
  if (row.dataset.lk && moving.some(l => l.key === row.dataset.lk)) return renderTree();
  if (d.gid && row.dataset.gk === d.gid) return renderTree();
  moving.forEach(l => LYR.splice(LYR.indexOf(l), 1));
  let at, group = null;
  if (row.dataset.lk) {
    const t = lyr(row.dataset.lk); at = LYR.indexOf(t) + (before ? 0 : 1); group = t.group;
    if (d.gid && t.group) { const blk = LYR.filter(l => l.group === t.group); at = before ? LYR.indexOf(blk[0]) : LYR.indexOf(blk[blk.length - 1]) + 1; group = null; }  // группа в группу не вкладывается
  } else {
    const blk = LYR.filter(l => l.group === row.dataset.gk);
    if (before || d.gid) at = before ? LYR.indexOf(blk[0]) : LYR.indexOf(blk[blk.length - 1]) + 1;
    else { at = LYR.indexOf(blk[0]); group = row.dataset.gk; grp(group).open = true; }
  }
  LYR.splice(at, 0, ...moving);
  if (d.key) moving[0].group = group;
  normGroups(); applyOrder(); renderTree();
});
document.addEventListener("dragend", () => { drag = null; document.querySelectorAll("#layerTree .dragging,#layerTree .drop-a,#layerTree .drop-b").forEach(x => x.classList.remove("dragging", "drop-a", "drop-b")); });

/* ---------- реестр существующих зданий: решение по каждому зданию ----------
   Поле «Решение» (сохраняем / реконструкция / сносим) у всех объектов слоя, раскраска по нему; решения
   ставятся выбором зданий (щелчок, рамка) и кнопками в «Объекте». Узел графа, который подаёт «сохраняемые»
   в ТЭП и разрывы, начинает отбирать здания по этому полю: снесённые не мешают посадке и уходят в «Под снос». */
const DECISION = "Решение", DECISIONS = { "сохраняем": "#b9b4ab", "реконструкция": "#eda100", "сносим": "#b3261e" };
function makeRegister(key) {
  const l = lyr(key), fs = layerSrc[key].getFeatures();
  pushUndo(featRec(fs.map(f => ({ key, f })), `реестр зданий «${l.title}»`)); pushStyleUndo(l, "register");
  fs.forEach(f => { if (f.get(DECISION) == null) f.set(DECISION, "сохраняем", true); });
  syncFromSource(key); DATA[key].fields = [DECISION, ...DATA[key].fields.filter(k => k !== DECISION)];
  l.style = ST({ ...l.style, mode: "cat", opacity: .9, cat: { field: DECISION, colors: { ...DECISIONS }, off: [] } }); assignCats(l, true); restyle(l);
  // узел графа, подающий «сохраняемые» в ТЭП, — фильтр «Решение ≠ сносим»
  const tepN = graph._nodes.find(n => n.type === "Показатели/ТЭП КРТ"), link = tepN && graph.links[tepN.inputs[1]?.link], src = link && graph.getNodeById(link.origin_id);
  let hooked = false;
  if (src?.type === "Данные/Слой" && src.widgets[0].value === l.title) { src.widgets[1].value = DECISION; src.widgets[2].value = "≠"; src.widgets[3].value = "сносим"; hooked = true; }
  setCurrent(key); renderRight();
  toast(`Реестр: у ${fmt(fs.length)} зданий поле «Решение» = «сохраняем». Выберите здания (щелчок, Shift+рамка) и отметьте «сносим» кнопкой справа.${hooked ? " Граф берёт в «сохраняемые» только не снесённые." : ""}`);
}
function setDecision(v) {
  const list = SEL.filter(s => fieldsOfKey(s.key).includes(DECISION)); if (!list.length) return;
  pushUndo(featRec(list, `решение «${v}» у ${list.length} зд.`)); list.forEach(s => { s.f.set(DECISION, v); s.f.set("_edited", true); });
  new Set(list.map(s => s.key)).forEach(k => { syncFromSource(k); const l = lyr(k); if (l.style.mode === "cat" && l.style.cat.field === DECISION) { assignCats(l, true); restyle(l); } });
  renderRight(); setHint(`«${v}»: ${fmt(list.length)} зд. Отменить — ${MOD}+Z.`);
}

/* ---------- группы ---------- */
function newGroup(keys, title) {
  const id = "g" + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
  GROUPS.push({ id, title: title || `Группа ${GROUPS.length + 1}`, visible: true, open: true });
  keys.map(lyr).filter(Boolean).forEach(l => { l.group = id; });   // группа встаёт на место верхнего из слоёв
  normGroups(); applyOrder(); renderTree(); return id;
}
function groupMenu(anchor, id) {
  const g = grp(id), ls = LYR.filter(l => l.group === id);
  showMenu(anchor, [
    ["Приблизить к группе", () => { const ex = ol.extent.createEmpty(); ls.forEach(l => ol.extent.extend(ex, layerSrc[l.key].getExtent())); if (isFinite(ex[0])) sharedView.fit(ex, { padding: [40, 40, 40, 40], maxZoom: 18 }); }],
    ["Переименовать", () => renameGroup(id)],
    ["Разгруппировать", () => { ls.forEach(l => { l.group = null; }); normGroups(); applyOrder(); renderTree(); }],
    ["Удалить группу вместе со слоями", () => { if (!confirmInline(anchor, `Удалить группу «${g.title}» и ${ls.length} слоёв в ней?`)) return; ls.forEach(l => dropLayer(l.key)); normGroups(); afterRemove(); }]]);
}
function renameGroup(id) {
  const row = tree().querySelector(`[data-gk="${CSS.escape(id)}"] .nm`); if (!row) return; const g = grp(id);
  inlineEdit(row, g.title, v => { g.title = v; window.markDirty?.(); });
}

let menuEl = null, STYLE_CLIP = null;   // буфер стиля, как «Копировать/Вставить стиль» в QGIS
const closeMenu = () => { menuEl?.remove(); menuEl = null; };
function showMenu(anchor, items) {
  closeMenu(); items = items.filter(Boolean);
  menuEl = document.createElement("div"); menuEl.className = "menu"; menuEl.setAttribute("role", "menu");
  menuEl.innerHTML = items.map((it, i) => it === "-" ? `<hr>` : `<button data-i="${i}" role="menuitem">${esc(it[0])}</button>`).join("");
  document.body.appendChild(menuEl); const r = anchor.getBoundingClientRect(); menuEl.style.left = Math.min(r.left, innerWidth - 250) + "px"; menuEl.style.top = Math.max(8, Math.min(r.bottom + 2, innerHeight - menuEl.offsetHeight - 8)) + "px";
  menuEl.onclick = ev => { const b = ev.target.closest("[data-i]"); if (b) { closeMenu(); items[+b.dataset.i][1](); } };
}
function layerMenu(anchor, key) {
  const l = lyr(key), d = DATA[key], others = GROUPS.filter(g => g.id !== l.group);
  showMenu(anchor, [["Приблизить к слою", () => { const ex = layerSrc[key].getExtent(); if (isFinite(ex[0])) sharedView.fit(ex, { padding: [40, 40, 40, 40], maxZoom: 18 }); }],
    ["Таблица атрибутов", () => { setCurrent(key); openTable(true); }],
    ["Рисовать в этот слой", () => { setCurrent(key); setTool(GEOMTOOL[l.geom]); }],
    ["Выбрать все объекты слоя", () => { setCurrent(key); selectAll(); }],
    l.geom === "poly" && !fieldsOfKey(key).includes(DECISION) ? ["Реестр зданий: сохраняем / сносим", () => makeRegister(key)] : null,
    l.geom === "poly" && fieldsOfKey(key).includes("Этажность") && !key.startsWith("nspd.") && !key.startsWith("osm.") ? ["Проверить нормы (инсоляция, запреты, разрывы)", () => runCheck(key)] : null,
    "-",
    ["Копировать стиль", () => { STYLE_CLIP = { style: JSON.parse(JSON.stringify(l.style)), geom: l.geom, from: l.title }; toast(`Стиль «${l.title}» скопирован.`); }],
    STYLE_CLIP && STYLE_CLIP.from !== l.title ? [`Вставить стиль «${STYLE_CLIP.from}»`, () => { pushStyleUndo(l, "paste"); l.style = ST(JSON.parse(JSON.stringify(STYLE_CLIP.style))); if (l.style.mode === "cat") assignCats(l, true); restyle(l); renderRight(); if (STYLE_CLIP.geom !== l.geom) toast("Стиль вставлен; геометрия слоёв разная — проверьте толщину и заливку."); }] : null,
    "-",
    ["Переименовать", () => renameLayer(key)],
    ["Выше", () => moveLayer(key, -1)], ["Ниже", () => moveLayer(key, 1)],
    l.group ? ["Убрать из группы", () => { l.group = null; normGroups(); applyOrder(); renderTree(); }] : null,
    ...others.map(g => [`В группу «${g.title}»`, () => { l.group = g.id; LYR.splice(LYR.indexOf(l), 1); LYR.splice(LYR.findIndex(x => x.group === g.id), 0, l); normGroups(); applyOrder(); renderTree(); }]),
    ["В новую группу", () => { const id = newGroup([key]); setTimeout(() => renameGroup(id), 0); }],
    "-",
    d?.original ? ["Вернуть исходную выгрузку", () => { if (!confirmInline(anchor, "Отменить все правки слоя и вернуть выгрузку?")) return; pushUndo({ kind: "layer", key, label: `возврат выгрузки «${l.title}»`, fs: layerSrc[key].getFeatures() }); setLayerData(key, d.original, true); dataRev++; }] : null,
    ["Удалить слой из проекта", () => removeLayer(key)]]);
}
document.addEventListener("pointerdown", e => { if (menuEl && !menuEl.contains(e.target) && !e.target.closest("[data-more],[data-gmore]")) closeMenu(); });
// window.confirm в браузере-вьюере не работает: подтверждение — повторным выбором пункта в течение 4 с
let pendingConfirm = null;
function confirmInline(anchor, text) { const now = Date.now(); if (pendingConfirm && pendingConfirm.text === text && now - pendingConfirm.t < 4000) { pendingConfirm = null; return true; } pendingConfirm = { t: now, text }; toast(text + " Выберите пункт ещё раз, чтобы подтвердить."); return false; }
// «Выше/Ниже» — внутри своей группы или среди слоёв без группы; группы целиком — перетаскиванием
function moveLayer(key, d) {
  const l = lyr(key), peers = LYR.filter(x => x.group === l.group), i = peers.indexOf(l), j = i + d; if (j < 0 || j >= peers.length) return;
  const a = LYR.indexOf(l), b = LYR.indexOf(peers[j]); [LYR[a], LYR[b]] = [LYR[b], LYR[a]]; normGroups(); applyOrder(); renderTree();
}
function inlineEdit(el, old, apply) {
  el.innerHTML = `<input type="text" value="${esc(old)}" style="width:100%">`; const inp = el.querySelector("input"); inp.focus(); inp.select();
  let fired = false;
  const done = ok => { if (fired) return; fired = true; const v = inp.value.trim(); if (ok && v && v !== old) apply(v); renderTree(); };
  inp.onkeydown = e => { e.stopPropagation(); if (e.key === "Enter") done(true); if (e.key === "Escape") done(false); }; inp.onblur = () => done(true);
}
function renameLayer(key) {
  const row = tree().querySelector(`[data-lk="${CSS.escape(key)}"] .nm`); if (!row) return; const l = lyr(key), old = l.title;
  inlineEdit(row, old, v => { l.title = v; DATA[key].title = v; graph._nodes.forEach(n => n.widgets?.forEach(w => { if (w.name === "слой" && w.value === old) w.value = v; })); dataRev++; });
}
function dropLayer(key) {
  const i = LYR.findIndex(l => l.key === key); if (i < 0) return;
  LYR.splice(i, 1); ALLMAPS.forEach(m => m.getLayers().getArray().filter(x => x.get("key") === key).forEach(x => m.removeLayer(x)));
  delete DATA[key]; layerSrc[key]?.clear(); if (CUR === key) CUR = LYR[0]?.key || null;
  setSel(SEL.filter(s => s.key !== key)); UNDO.splice(0, UNDO.length, ...UNDO.filter(u => !undoKeys(u).includes(key))); REDO.length = 0;
}
function afterRemove() { dataRev++; normGroups(); applyOrder(); renderTree(); renderRight(); renderTable(); renderSources?.(); if (UIS.tool !== "cmd") setTool(UIS.tool); }
function removeLayer(key) {
  const l = lyr(key); if (!l) return;
  if (!confirmInline(tree(), `Удалить слой «${l.title}» из проекта?`)) return;
  dropLayer(key); afterRemove();
}
$("bNewLayer").onclick = () => {
  const box = $("newLayerBox"); box.hidden = !box.hidden; if (!box.hidden) $("nlName").focus();
};
$("bBySheet").onclick = () => setBySheet(!BY_SHEET);
$("bNewGroup").onclick = () => {
  if (!CUR) return toast("Группа собирается из слоёв: выберите слой в списке, затем «Новая группа». Слои переносятся в группу перетаскиванием.");
  const id = newGroup([CUR]); setTimeout(() => renameGroup(id), 0);
};
function createLayer(name, geom) {
  const key = "user:" + Date.now().toString(36);
  DATA[key] = { title: name, source: "создан в проекте", fetched_at: new Date().toISOString().slice(0, 10), fc: { type: "FeatureCollection", features: [] }, count: 0, fields: ["Наименование", "Примечание"] };
  ensureLayer(key, name, geom); setCurrent(key); return lyr(key);
}
$("nlOk").onclick = () => {
  const l = createLayer($("nlName").value.trim() || "Новый слой", $("nlGeom").value);
  $("newLayerBox").hidden = true; $("nlName").value = ""; document.activeElement.blur(); setTool(GEOMTOOL[l.geom]);
};
$("nlName").addEventListener("keydown", e => { if (e.key === "Enter") $("nlOk").click(); });

/* ---------- правая панель: оформление и объект ---------- */
const UIS = { rt: "style", tool: "select", sort: null, filter: "" };
const cbtn = (key, c) => `<button class="cbtn" data-color="${esc(key)}" aria-label="Выбрать цвет"><i style="background:${esc(c)}"></i></button>`;
const opts = (list, cur) => list.map(v => `<option ${String(v) === String(cur) ? "selected" : ""}>${esc(v)}</option>`).join("");
function renderRight() {
  document.querySelectorAll("[data-rtab]").forEach(b => b.setAttribute("aria-selected", b.dataset.rtab === UIS.rt));
  const el = $("rightPane"); if (!el) return;
  UIS.rt === "obj" ? renderObject(el) : renderStyle(el); icons();
}
function renderStyle(el) {
  const l = lyr(CUR); if (!l) { el.innerHTML = `<div class="empty">Выберите слой в дереве</div>`; return; }
  const st = l.style, fields = fieldsOfKey(l.key), nf = numFields(l.key), cf = fields.filter(k => !nf.includes(k));
  const modes = [["single", "Единый"], ["cat", "Категории"], ["grad", "Градуир."], ["rules", "Правила"]].concat(fields.includes("_lt") || st.mode === "lgr" || DATA[l.key]?.fc.features.some(f => f.properties._lt) ? [["lgr", "ЛГР"]] : []);
  let h = `<div class="pad"><div class="ph">${symHTML(l)}<b>${esc(l.title)}</b></div><div class="stmodes">${modes.map(([m, t]) => `<button data-mode="${m}" aria-pressed="${st.mode === m}">${t}</button>`).join("")}</div>`;
  const colorWord = l.geom === "line" ? "Цвет" : l.geom === "point" ? "Цвет" : "Заливка";
  if (st.mode === "lgr") h += `<div class="note" style="padding:0 0 8px">Знаки красных линий и ЛГР по стандарту REDLN97: тип линии выбирается по LineCode объекта. <a href="linetypes.html" target="_blank">Каталог типов</a>.</div>`;
  else if (st.mode === "single") h += `<div class="row"><label>${colorWord}</label>${cbtn("fill", st.fill)}${l.geom === "poly" ? `<label class="inl"><input type="checkbox" data-k="hatch" ${st.hatch ? "checked" : ""}>штриховка</label>` : ""}</div>`;
  else if (st.mode === "cat") {
    h += `<div class="row"><label>Поле</label><select data-k="cat.field">${opts(cf.length ? cf : fields, st.cat.field)}</select></div><div class="row"><label></label><button class="btn" data-recolor title="Как «Классифицировать» в QGIS: заново собрать значения поля и раздать цвета">Классифицировать</button></div>`;
    h += `<table class="cl">${catValues(l.key, st.cat.field).slice(0, 80).map(([v, n]) => `<tr class="${st.cat.off.includes(v) ? "off" : ""}"><td><input type="checkbox" data-catoff2="${esc(v)}" ${st.cat.off.includes(v) ? "" : "checked"} aria-label="Показывать"></td><td>${cbtn("cat:" + v, st.cat.colors[v] || OTHER)}</td><td>${esc(v || "—")}</td><td class="n num">${n}</td></tr>`).join("")}</table>`;
    if (l.geom === "poly") h += `<div class="row" style="margin-top:7px"><label></label><label class="inl"><input type="checkbox" data-k="hatch" ${st.hatch ? "checked" : ""}>штриховка вместо заливки</label></div>`;
  } else if (st.mode === "grad") {
    if (!nf.length) h += `<div class="empty">Нет числовых полей</div>`;
    else { if (!nf.includes(st.grad.field)) st.grad.field = nf[0]; const b = l._br || (l._br = breaks(l)), cols = ramp(st.grad.ramp, (l._br || (l._br = breaks(l))).length - 1);
      h += `<div class="row"><label>Поле</label><select data-k="grad.field">${opts(nf, st.grad.field)}</select></div><div class="row"><label>Классы</label><select data-k="grad.n">${opts([3, 4, 5, 6], st.grad.n)}</select><select data-k="grad.method"><option value="quantile" ${st.grad.method === "quantile" ? "selected" : ""}>Квантили</option><option value="equal" ${st.grad.method === "equal" ? "selected" : ""}>Равные интервалы</option></select></div>
      <div class="row"><label>Шкала</label><div class="ramps">${Object.keys(RAMPS).map(r => `<button class="ramp" data-ramp="${r}" aria-pressed="${st.grad.ramp === r}" aria-label="Шкала ${r}">${RAMPS[r].map(c => `<i style="background:${c}"></i>`).join("")}</button>`).join("")}</div></div>
      <table class="cl">${cols.map((c, i) => `<tr><td><span class="sym" style="background:${c}"></span></td><td class="num">${fmt(b[i], 1)} – ${fmt(b[i + 1], 1)}</td></tr>`).join("")}</table>`; }
  } else if (st.mode === "rules") {
    h += st.rules.list.map((r, i) => `<div class="rule"><div class="w"><select data-rule="${i}" data-rk="field" aria-label="Поле">${opts(fields, r.field)}</select><select data-rule="${i}" data-rk="op" aria-label="Условие">${opts(["=", "≠", ">", "<", "≥", "≤", "содержит"], r.op)}</select><input type="text" data-rule="${i}" data-rk="val" value="${esc(r.val)}" aria-label="Значение"></div>
      <div class="t">${cbtn("rule:" + i, r.fill)}${l.geom === "poly" ? `<label class="inl"><input type="checkbox" data-rule="${i}" data-rk="hatch" ${r.hatch ? "checked" : ""}> штриховка</label>` : ""}<span class="sp"></span><span class="num">${ruleCount(l, i)} об.</span><button class="tb" data-delrule="${i}" title="Удалить правило"><i data-lucide="x"></i></button></div></div>`).join("");
    h += `<div class="row"><button class="btn" data-addrule><i data-lucide="plus"></i>Правило</button></div><div class="rule"><div class="t" style="margin:0">Остальные ${cbtn("else", st.rules.elseFill)}<label class="inl"><input type="checkbox" data-k="rules.elseHide" ${st.rules.elseHide ? "checked" : ""}> скрыть</label></div></div>`;
  }
  h += `<div class="sect" style="margin:8px -8px 8px">Контур, прозрачность, подписи</div>`;
  if (l.geom === "poly") h += `<div class="row"><label>Контур</label>${cbtn("stroke", st.stroke)}<input type="number" data-k="width" min="0" max="8" step=".1" value="${st.width}" style="width:64px" aria-label="Толщина контура"> пикс.</div>
    <div class="row"><label>Заливка, %</label><input type="range" data-k="opacity" min="0" max="1" step=".05" value="${st.opacity}" aria-label="Непрозрачность заливки"><span class="num">${Math.round(st.opacity * 100)}</span></div>`;
  else h += `<div class="row"><label>${l.geom === "point" ? "Размер" : "Толщина"}</label><input type="number" data-k="width" min=".3" max="10" step=".1" value="${st.width}" style="width:64px" aria-label="Толщина"> пикс.</div>`;
  const DENS = [0, 1000, 2000, 2500, 5000, 10000, 25000];
  h += `<div class="row"><label>Виден</label><select data-k="maxDen" data-num aria-label="Видимость слоя по масштабу" title="Как «Видимость в зависимости от масштаба» в QGIS: на более мелком масштабе слой не рисуется ни на карте, ни на листе. На расчёты (граф, ограничения) не влияет">${DENS.map(d => `<option value="${d}" ${(st.maxDen || 0) === d ? "selected" : ""}>${d ? "крупнее 1:" + fmt(d) : "на любом масштабе"}</option>`).join("")}</select></div>`;
  h += `<div class="row"><label>Слой, %</label><input type="range" data-lop min="0" max="1" step=".05" value="${l.layerOpacity}" aria-label="Непрозрачность слоя"><span class="num">${Math.round(l.layerOpacity * 100)}</span></div>
    ${l.geom === "poly" && (st.hatch || st.rules.list.some(r => r.hatch)) ? `<div class="row"><label>Узор штриховки</label><select data-k="hatchPat">${Object.entries(HATCHES).map(([k, t]) => `<option value="${k}" ${(st.hatchPat || "45") === k ? "selected" : ""}>${t}</option>`).join("")}</select><input type="number" data-k="hatchStep" min="4" max="40" value="${st.hatchStep || 8}" title="шаг штриховки, пикс." style="width:52px"></div>` : ""}
    <div class="row"><label>Подпись</label><select data-k="label"><option value="">нет</option>${fields.map(k => `<option ${st.label === k ? "selected" : ""}>${esc(k)}</option>`).join("")}</select><input type="number" data-k="labelSize" min="7" max="24" value="${st.labelSize}" style="width:54px" aria-label="Кегль"></div>${l.gl ? `<div class="note" style="padding:2px 0 0">Слой крупный (${fmt(layerSrc[l.key]?.getFeatures().length || 0)} объектов): на обзоре его рисует видеокарта: штриховка там — полупрозрачной заливкой, подписей нет. Подписи появляются с масштаба крупнее 1:${fmt(scaleDen(glSwitchRes(l)))}.</div>` : ""}</div>`;
  el.innerHTML = h;
}
const numOrText = v => isNum(v) && String(v).trim() !== "" && !/^0\d/.test(v) ? +v : v;
// площадь и длина — в МСК, как их чертят, выгружают в DXF и печатают (эллипсоид дал бы 597,2 м² у прямоугольника 30 × 20 м)
const sizeOf = f => { const g = f.getGeometry(), t = g?.getType() || "";
  if (!window.CAD?.toM) { const w = GJ.writeFeatureObject(f); return /Polygon/.test(t) ? ["area", turf.area(w)] : /Line/.test(t) ? ["len", turf.length(w, { units: "kilometers" }) * 1000] : ["pt", 0]; }
  const ring = r => { const m = r.map(CAD.toM); let a = 0; for (let i = 0; i + 1 < m.length; i++) a += m[i][0] * m[i + 1][1] - m[i + 1][0] * m[i][1]; return Math.abs(a / 2); };
  const len = r => { const m = r.map(CAD.toM); let d = 0; for (let i = 0; i + 1 < m.length; i++) d += Math.hypot(m[i + 1][0] - m[i][0], m[i + 1][1] - m[i][1]); return d; };
  const c = g?.getCoordinates();
  if (t === "Polygon") return ["area", c.reduce((a, r, i) => a + (i ? -ring(r) : ring(r)), 0)];
  if (t === "MultiPolygon") return ["area", c.reduce((a, p) => a + p.reduce((b, r, i) => b + (i ? -ring(r) : ring(r)), 0), 0)];
  if (t === "LineString") return ["len", len(c)];
  if (t === "MultiLineString") return ["len", c.reduce((a, r) => a + len(r), 0)];
  return ["pt", 0]; };
const DECSHORT = { "сохраняем": "сохраняем", "реконструкция": "реконстр.", "сносим": "сносим" };
const decisionBar = () => SEL.some(s => fieldsOfKey(s.key).includes(DECISION)) ? `<div class="pad" style="padding-top:0"><div class="seg dec">${Object.keys(DECISIONS).map(v => `<button data-decide="${v}" title="Решение по выбранным зданиям: ${v}"><i style="background:${DECISIONS[v]}"></i>${DECSHORT[v]}</button>`).join("")}</div></div>` : "";
// этажность выбранных корпусов своего слоя (эскиз, свои слои): − / +, как ручки высоты в TestFit
const floorsBar = () => { const own = SEL.filter(s => fieldsOfKey(s.key).includes("Этажность") && !/^(nspd|osm|gisogd)\./.test(s.key)); if (!own.length) return "";
  const v = [...new Set(own.map(s => s.f.get("Этажность")))]; return `<div class="pad" style="padding-top:0"><div class="row" style="margin:0"><label>Этажность</label><button class="btn" data-fl="-1" title="На этаж ниже">−</button><b class="num" style="min-width:48px;text-align:center">${v.length === 1 ? v[0] : "разная"}</b><button class="btn" data-fl="1" title="На этаж выше">+</button></div></div>`; };
/* координаты вершин в МСК — правка числом (как «Редактор вершин» QGIS): изменение поля сдвигает вершину, замыкающая
   вершина контура идёт вместе с первой; до 300 вершин, у большего объекта таблица не строится */
const vPaths = g => { const t = g.getType(), c = g.getCoordinates();
  if (t === "Point") return [[[], c]]; if (t === "LineString") return c.map((q, i) => [[i], q]);
  if (t === "MultiLineString" || t === "Polygon") return c.flatMap((r, j) => r.map((q, i) => [[j, i], q]).slice(0, t === "Polygon" ? -1 : undefined));
  if (t === "MultiPolygon") return c.flatMap((p, k) => p.flatMap((r, j) => r.slice(0, -1).map((q, i) => [[k, j, i], q])));
  return []; };
function vertexTable(f) {
  const g = f.getGeometry(); if (!g || !window.CAD?.toM) return ""; const vs = vPaths(g); if (!vs.length || vs.length > 300) return vs.length ? `<div class="note">Вершин ${vs.length} — таблица координат строится до 300.</div>` : "";
  let prev = null;
  return `<div class="sect">Вершины, МСК</div><table class="vt"><tr><th>№</th><th>X</th><th>Y</th></tr>${vs.map(([p, q], n) => { const m = CAD.toM(q), ring = p.slice(0, -1).join(".");
    const head = ring !== prev && p.length > 1 ? `<tr><td colspan="3" class="vr">${p.length === 3 ? `часть ${p[0] + 1}, ` : ""}${p[p.length - 2] ? `дыра ${p[p.length - 2]}` : g.getType() === "MultiLineString" ? `линия ${p[0] + 1}` : "контур"}</td></tr>` : ""; prev = ring;
    return head + `<tr><td>${n + 1}</td><td><input type="text" class="num" data-vx="${p.join(",")}" value="${m[0].toFixed(3)}"></td><td><input type="text" class="num" data-vy="${p.join(",")}" value="${m[1].toFixed(3)}"></td></tr>`; }).join("")}</table>`;
}
function setVertex(f, path, axis, val) {
  const g = f.getGeometry(), coords = JSON.parse(JSON.stringify(g.getCoordinates()));
  let arr = coords; for (const i of path.slice(0, -1)) arr = arr[i];
  const last = path[path.length - 1], cur = path.length ? arr[last] : coords, m = CAD.toM(cur); m[axis] = val; const c = CAD.fromM(m);
  if (!path.length) { g.setCoordinates(c); return; }
  arr[last] = c; if (/Polygon/.test(g.getType()) && last === 0) arr[arr.length - 1] = c.slice();
  g.setCoordinates(coords);
}
function renderObject(el) {
  if (!SEL.length) { el.innerHTML = `<div class="empty">Щёлкните объект на карте или строку таблицы.<br><br>Несколько объектов — Shift+щелчок или рамка с Shift. Все объекты слоя — ${MOD}+A.</div>`; return; }
  if (SEL.length === 1) {
    const { key, f } = SEL[0], l = lyr(key), [kind, v] = sizeOf(f);
    const keys = Object.keys(f.getProperties()).filter(k => !hiddenField(k));
    el.innerHTML = `<div class="pad"><div class="ph"><b>${esc(l.title)}</b></div><div class="note" style="padding:0 0 6px">${kind === "area" ? fmt(v, 1) + " м²" : kind === "len" ? fmt(v, 2) + " м" : ""}${f.get("_edited") ? " · изменён вручную" : ""}${f.get("_lt") ? " · " + esc(f.get("_lt").join(", ")) : ""}</div></div>${decisionBar()}${floorsBar()}
      <div class="pg">${keys.map(k => `<div class="ro" title="${esc(k)}">${esc(k)}</div><div><input type="text" data-attr="${esc(k)}" value="${esc(f.get(k))}"></div>`).join("")}</div>
      <div class="pad"><div class="row"><input type="text" id="newField" placeholder="Новое поле"><button class="btn" id="bAddField">Добавить</button></div></div>${vertexTable(f)}`;
    return;
  }
  // несколько объектов: сводка и, если они из одного слоя, общая правка атрибутов (как «Изменить атрибуты выбранных» в QGIS)
  const by = new Map(); SEL.forEach(s => (by.get(s.key) || by.set(s.key, []).get(s.key)).push(s.f));
  let area = 0, len = 0; if (SEL.length <= 5000) SEL.forEach(s => { const [k, v] = sizeOf(s.f); if (k === "area") area += v; if (k === "len") len += v; });
  const sum = [area ? `площадь ${fmt(area / 1e4, 3)} га` : "", len ? `длина ${fmt(len, 0)} м` : ""].filter(Boolean).join(" · ");
  let h = `<div class="pad"><div class="ph"><b>Выбрано объектов: ${fmt(SEL.length)}</b></div>${sum ? `<div class="note" style="padding:0 0 6px">${sum}</div>` : ""}</div>${decisionBar()}${floorsBar()}`;
  if (by.size > 1) {
    h += `<table class="cl" style="margin:0 8px;width:calc(100% - 16px)">${[...by].map(([k, fs]) => `<tr><td>${symHTML(lyr(k))}</td><td>${esc(lyr(k).title)}</td><td class="n num">${fmt(fs.length)}</td><td><button class="btn" data-only="${esc(k)}" title="Оставить в выборе только объекты этого слоя">Только он</button></td></tr>`).join("")}</table>
      <div class="note">Атрибуты правятся у объектов одного слоя: оставьте в выборе один слой.</div>`;
  } else {
    const [key, fs] = [...by][0], l = lyr(key), keys = [...new Set(fs.slice(0, 2000).flatMap(f => Object.keys(f.getProperties())))].filter(k => !hiddenField(k));
    h += `<div class="note" style="padding:0 8px 6px">Слой «${esc(l.title)}». Значение, введённое в поле, получат все ${fmt(fs.length)} объектов; «разные» — у объектов разные значения, поле не меняется, пока его не заполнить.</div>
      <div class="pg">${keys.map(k => { const vals = new Set(fs.slice(0, 5000).map(f => String(f.get(k) ?? ""))); const same = vals.size === 1;
        return `<div class="ro" title="${esc(k)}">${esc(k)}</div><div><input type="text" data-battr="${esc(k)}" value="${same ? esc([...vals][0]) : ""}" placeholder="${same ? "" : `разные (${vals.size}${fs.length > 5000 ? "+" : ""})`}"></div>`; }).join("")}</div>
      <div class="pad"><div class="row"><input type="text" id="newField" placeholder="Новое поле для всех"><button class="btn" id="bAddField">Добавить</button></div></div>`;
  }
  el.innerHTML = h;
}
document.addEventListener("click", e => {
  const tab = e.target.closest?.("[data-rtab]"); if (tab) { UIS.rt = tab.dataset.rtab; renderRight(); return; }
  const pane = $("rightPane"); if (!pane?.contains(e.target)) return;
  const b = e.target.closest("button"); if (!b) return;
  if (b.id === "bAddField") {
    const n = $("newField").value.trim(); if (!n || !SEL.length || new Set(SEL.map(s => s.key)).size > 1) return;
    pushUndo(featRec(SEL, `новое поле «${n}»`)); SEL.forEach(s => { s.f.set(n, ""); s.f.set("_edited", true); }); syncFromSource(SEL[0].key); renderRight(); return;
  }
  if (b.dataset.only) { setSel(SEL.filter(s => s.key === b.dataset.only)); return; }
  if (b.dataset.decide) return setDecision(b.dataset.decide);
  if (b.dataset.fl) {
    // только свои слои (эскиз, нарисованное): этажность выгрузки ЕГРН/OSM — это факт, а не параметр проекта
    const own = SEL.filter(s => fieldsOfKey(s.key).includes("Этажность") && !/^(nspd|osm|gisogd)\./.test(s.key)), d = +b.dataset.fl; if (!own.length) return;
    pushUndo(featRec(own, `этажность ${d > 0 ? "+1" : "−1"} у ${own.length} корп.`));
    own.forEach(s => { const n = Math.max(1, (+s.f.get("Этажность") || 1) + d); s.f.set("Этажность", n); if (s.f.get("Площадь застройки, м²")) s.f.set("СПП, м²", Math.round(s.f.get("Площадь застройки, м²") * n)); s.f.set("_edited", true); });
    new Set(own.map(s => s.key)).forEach(k => { syncFromSource(k); const l = lyr(k); l._br = null; restyle(l); }); renderRight(); return;
  }
  const l = lyr(CUR); if (!l) return; const st = l.style;
  if (b.dataset.mode) { pushStyleUndo(l, "mode"); st.mode = b.dataset.mode; if (st.mode === "cat" && !Object.keys(st.cat.colors).length) assignCats(l); restyle(l); renderRight(); }
  else if (b.hasAttribute("data-recolor")) { pushStyleUndo(l, "recolor"); assignCats(l, false); restyle(l); renderRight(); }
  else if (b.dataset.ramp) { pushStyleUndo(l, "ramp"); st.grad.ramp = b.dataset.ramp; restyle(l); renderRight(); }
  else if (b.dataset.color) openPicker(b, b.dataset.color);
  else if (b.hasAttribute("data-addrule")) { pushStyleUndo(l, "addrule"); const f = fieldsOfKey(l.key)[0] || ""; st.rules.list.push({ field: f, op: "=", val: catValues(l.key, f)[0]?.[0] ?? "", fill: CAT[st.rules.list.length % 8], hatch: false }); restyle(l); renderRight(); }
  else if (b.dataset.delrule) { pushStyleUndo(l, "delrule"); st.rules.list.splice(+b.dataset.delrule, 1); restyle(l); renderRight(); }
});
function onPaneEdit(e) {
  const t = e.target, pane = $("rightPane"); if (!pane?.contains(t)) return;
  if ((t.dataset.vx !== undefined || t.dataset.vy !== undefined) && e.type === "change" && SEL.length === 1) {
    const v = +String(t.value).replace(",", ".").replace(/\s/g, ""); if (!isFinite(v)) { toast("Координата — число, например 7112,692."); return renderRight(); }
    const { key, f } = SEL[0], path = (t.dataset.vx ?? t.dataset.vy).split(",").filter(x => x !== "").map(Number);
    pushUndo(featRec(SEL, "координата вершины")); setVertex(f, path, t.dataset.vx !== undefined ? 0 : 1, v); f.set("_edited", true); f.unset?.("_cad"); syncFromSource(key); renderRight(); return;
  }
  if (t.dataset.attr !== undefined) { if (e.type !== "change" || SEL.length !== 1) return; const { key, f } = SEL[0]; pushUndo(featRec(SEL, `атрибут «${t.dataset.attr}»`)); f.set(t.dataset.attr, numOrText(t.value)); f.set("_edited", true); syncFromSource(key); return; }
  if (t.dataset.battr !== undefined) {
    if (e.type !== "change" || !SEL.length) return; const k = t.dataset.battr, v = numOrText(t.value);
    // без события на каждый объект: у 100 000 выбранных это 200 000 перерисовок; одно обновление слоя в конце
    pushUndo(featRec(SEL, `атрибут «${k}» у ${SEL.length} об.`)); SEL.forEach(s => { s.f.set(k, v, true); s.f.set("_edited", true, true); });
    new Set(SEL.map(s => s.key)).forEach(key => { layerSrc[key].changed(); syncFromSource(key); }); renderRight(); toast(`«${k}» = «${t.value}» у ${fmt(SEL.length)} объектов. Отменить — ${MOD}+Z.`); return;
  }
  const l = lyr(CUR); if (!l) return; const st = l.style;
  if (t.hasAttribute("data-lop")) { pushStyleUndo(l, "lop"); l.layerOpacity = +t.value; t.nextElementSibling.textContent = Math.round(l.layerOpacity * 100); applyOrder(); return; }
  if (t.dataset.k) {
    pushStyleUndo(l, "k:" + t.dataset.k);
    const p = t.dataset.k.split("."), v = t.type === "checkbox" ? t.checked : ["range", "number"].includes(t.type) || p[1] === "n" || t.dataset.num !== undefined ? +t.value : t.value;
    let o = st; p.slice(0, -1).forEach(x => o = o[x]); o[p[p.length - 1]] = v;
    if (t.dataset.k === "cat.field") assignCats(l, false);
    if (t.type === "range") t.nextElementSibling.textContent = Math.round(v * 100);
    // крупный слой видеокарта перестраивает целиком (~150 мс): при движении ползунка — не чаще раза в 120 мс
    if (l.gl && e.type === "input") { l._rsT ||= setTimeout(() => { l._rsT = null; restyle(l); }, 120); return; }
    clearTimeout(l._rsT); l._rsT = null; restyle(l); if (e.type === "change") renderRight(); return;
  }
  if (t.dataset.catoff2 !== undefined) { pushStyleUndo(l, "cat"); const v = t.dataset.catoff2; st.cat.off = t.checked ? st.cat.off.filter(x => x !== v) : [...st.cat.off, v]; restyle(l); renderRight(); return; }
  if (t.dataset.rule !== undefined) { pushStyleUndo(l, "rule" + t.dataset.rule + t.dataset.rk); const r = st.rules.list[+t.dataset.rule]; r[t.dataset.rk] = t.type === "checkbox" ? t.checked : t.value; restyle(l); if (e.type === "change") renderRight(); }
}
document.addEventListener("change", onPaneEdit);
// Enter в поле атрибута — как в AutoCAD: значение принято, клавиши снова управляют картой (иначе M или V попадут в поле)
$("rightPane").addEventListener("keydown", e => { if (e.key === "Enter" && e.target.matches("input[type=text]") && e.target.id !== "newField") e.target.blur(); });
document.addEventListener("input", e => { if (e.target.type === "range" || e.target.dataset?.rk === "val") onPaneEdit(e); });

let popEl = null;
const closePop = () => { popEl?.remove(); popEl = null; };
function openPicker(anchor, key) {
  closePop(); const l = lyr(CUR), st = l.style;
  const set = c => { pushStyleUndo(l, "color:" + key); if (key === "fill") st.fill = c; else if (key === "stroke") st.stroke = c; else if (key === "else") st.rules.elseFill = c; else if (key.startsWith("cat:")) st.cat.colors[key.slice(4)] = c; else st.rules.list[+key.slice(5)].fill = c; restyle(l); renderRight(); };
  popEl = document.createElement("div"); popEl.className = "pop";
  popEl.innerHTML = `<div class="g">${PICK.map(c => `<button style="background:${c}" data-c="${c}" aria-label="${c}" title="${c}"></button>`).join("")}</div><input type="text" placeholder="#RRGGBB" aria-label="Цвет HEX">`;
  document.body.appendChild(popEl); const r = anchor.getBoundingClientRect(); popEl.style.left = Math.min(r.left, innerWidth - 206) + "px"; popEl.style.top = Math.min(r.bottom + 4, innerHeight - 200) + "px";
  popEl.onclick = e => { const b = e.target.closest("[data-c]"); if (b) set(b.dataset.c); };
  popEl.querySelector("input").onchange = e => { if (/^#[0-9a-f]{6}$/i.test(e.target.value)) set(e.target.value.toLowerCase()); };
}
document.addEventListener("pointerdown", e => { if (popEl && !popEl.contains(e.target) && !e.target.closest("[data-color]")) closePop(); });

/* ---------- таблица атрибутов ---------- */
function openTable(on) { winOpen("wTable", on); }
const tableSort = { k: "", rows: [] };
function renderTable() {
  if ($("wTable").hidden) return; const l = lyr(CUR), el = $("attrBody");
  const selSet = new Set(SEL.map(s => s.f)), nSel = SEL.filter(s => s.key === CUR).length;
  $("attrTitle").textContent = l ? `${l.title} · ${fmt(DATA[l.key]?.count ?? 0)} объектов${nSel ? ` · выбрано ${fmt(nSel)}` : ""} · двойной щелчок по ячейке — правка` : "Выберите слой в дереве";
  if (!l) { el.innerHTML = ""; return; }
  const cols = fieldsOfKey(l.key); let rows = UIS.selOnly ? SEL.filter(s => s.key === CUR).map(s => s.f) : layerSrc[l.key].getFeatures().slice();
  if (UIS.filter) { const q = UIS.filter.toLowerCase(); rows = rows.filter(f => cols.some(k => String(f.get(k) ?? "").toLowerCase().includes(q))); }
  // сортировка — одна на версию слоя и колонку: выбор объекта и правка стиля таблицу заново не сортируют (256 мс на 100 000)
  if (UIS.sort && cols.includes(UIS.sort.k)) {
    const d = DATA[l.key], sk = [l.key, d?.rev, UIS.sort.k, UIS.sort.d, UIS.filter, UIS.selOnly ? SEL.length : 0].join("|");
    if (!UIS.selOnly && tableSort.k === sk) rows = tableSort.rows;
    else { const coll = new Intl.Collator("ru", { numeric: true }); rows.sort((a, b) => { const x = a.get(UIS.sort.k), y = b.get(UIS.sort.k); return (isNum(x) && isNum(y) ? x - y : coll.compare(String(x ?? ""), String(y ?? ""))) * UIS.sort.d; });
      if (!UIS.selOnly) Object.assign(tableSort, { k: sk, rows }); }
  }
  const vis = rows.slice(0, 1500);
  el.innerHTML = `<table class="at"><thead><tr><th></th>${cols.map(k => `<th data-sort="${esc(k)}">${esc(k)}${UIS.sort?.k === k ? (UIS.sort.d > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead><tbody>${vis.map((f, i) => `<tr data-uid="${ol.util.getUid(f)}" class="${selSet.has(f) ? "sel" : ""}"><td class="rn">${i + 1}${f.get("_edited") ? "*" : ""}</td>${cols.map(k => `<td data-cell="${esc(k)}">${esc(f.get(k) ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table>${rows.length > vis.length ? `<div class="note">Показаны первые ${fmt(vis.length)} из ${fmt(rows.length)}; уточните фильтр.</div>` : ""}`;
}
const featByUid = (key, uid) => layerSrc[key].getFeatures().find(f => String(ol.util.getUid(f)) === String(uid));
$("attrBody").addEventListener("click", e => {
  const th = e.target.closest("[data-sort]"); if (th) { const k = th.dataset.sort; UIS.sort = { k, d: UIS.sort?.k === k ? -UIS.sort.d : 1 }; renderTable(); return; }
  const tr = e.target.closest("[data-uid]"); if (!tr) return; const f = featByUid(CUR, tr.dataset.uid); if (!f) return;
  if (e.shiftKey || e.metaKey || e.ctrlKey) return toggleSel({ key: CUR, f });   // как в QGIS: строки добавляются к выбору
  select(CUR, f); sharedView.fit(f.getGeometry().getExtent(), { padding: [80, 80, 80, 80], maxZoom: 19, duration: 150 });
});
$("attrBody").addEventListener("dblclick", e => {
  const td = e.target.closest("[data-cell]"); if (!td) return;
  const f = featByUid(CUR, td.parentElement.dataset.uid), k = td.dataset.cell; td.innerHTML = `<input type="text" value="${esc(f.get(k) ?? "")}">`;
  const inp = td.querySelector("input"); inp.focus(); inp.select();
  const done = ok => { if (ok && inp.value !== String(f.get(k) ?? "")) { pushUndo(featRec([{ key: CUR, f }], `атрибут «${k}»`)); f.set(k, numOrText(inp.value)); f.set("_edited", true); syncFromSource(CUR); if (SEL.some(s => s.f === f)) renderRight(); } else renderTable(); };
  inp.onkeydown = ev => { if (ev.key === "Enter") done(true); if (ev.key === "Escape") done(false); }; inp.onblur = () => done(true);
});
$("attrFilter").oninput = e => { UIS.filter = e.target.value; renderTable(); };
$("attrSelOnly").onchange = e => { UIS.selOnly = e.target.checked; renderTable(); };
$("bTable").onclick = () => openTable();
$("bTidy").onclick = () => { const r = tidyLayers(); window.markDirty?.();
  toast(`Слои упорядочены как на опорном плане.${r.hidden.length ? ` Застройка — «${r.buildings}»; выключены повторы: ${r.hidden.map(t => `«${t}»`).join(", ")}.` : ""}`); };

/* ---------- выбор: щелчок, Shift+щелчок, рамка ---------- */
const MOD = /Mac/.test(navigator.platform) ? "⌘" : "Ctrl";
const selSrc = new ol.source.Vector();
const SELSTYLE = { poly: S([47, 111, 196, .15], "#2f6fc4", 3), line: S(null, "#2f6fc4", 4), point: new ol.style.Style({ image: new ol.style.Circle({ radius: 8, stroke: new ol.style.Stroke({ color: "#2f6fc4", width: 3 }) }) }) };
const gkind = f => { const t = f.getGeometry()?.getType() || ""; return /Point/.test(t) ? "point" : /Line/.test(t) ? "line" : "poly"; };
// подсветка выбора: до 5 000 объектов — холст, больше (выбрать всё в крупном слое) — видеокарта
const selCv = new ol.layer.Vector({ source: selSrc, zIndex: 108, style: f => SELSTYLE[gkind(f)] });
const selGl = new ol.layer.WebGLVector({ source: selSrc, zIndex: 108, visible: false, disableHitDetection: true, style: { "fill-color": "rgba(47,111,196,0.18)", "stroke-color": "#2f6fc4", "stroke-width": 2, "circle-radius": 6, "circle-fill-color": "rgba(47,111,196,0.25)", "circle-stroke-color": "#2f6fc4", "circle-stroke-width": 2 } });
mMain.addLayer(selCv); mMain.addLayer(selGl);
function setSel(list) {
  const seen = new Set(); SEL = list.filter(s => s.f && layerSrc[s.key]?.hasFeature(s.f) && !seen.has(s.f) && seen.add(s.f));
  const big = SEL.length > 5000; selCv.setVisible(!big); selGl.setVisible(big);
  selSrc.clear(true); selSrc.addFeatures(SEL.map(s => s.f));
  if (SEL.length) UIS.rt = "obj";
  CAD.grips?.();                                     // ручки AutoCAD на вершинах выбранных объектов (до строки состояния: она говорит, если ручек нет)
  renderRight(); renderTable(); syncRibbon(); syncStatus();
  if (UIS.tool === "vertex") setTool(UIS.tool);      // ручки работают с выбором
}
function select(key, f) { setSel(f ? [{ key, f }] : []); }
function toggleSel(it) { setSel(SEL.some(s => s.f === it.f) ? SEL.filter(s => s.f !== it.f) : [...SEL, it]); }
function selectAll() { const l = lyr(CUR); if (!l) return toast("Выберите слой в списке."); if (!shown(l)) return toast(`Слой «${l.title}» скрыт — включите его видимость.`);
  if (outOfScale(l)) return toast(`Слой «${l.title}» не виден на этом масштабе (крупнее 1:${fmt(l.style.maxDen)}).`); const all = layerSrc[l.key].getFeatures(), vis = all.filter(f => visibleIn(l, f)); setSel(vis.map(f => ({ key: l.key, f })));
  toast(`Выбраны все видимые объекты слоя «${l.title}»: ${fmt(SEL.length)}.${vis.length < all.length ? ` Скрытые стилем (${fmt(all.length - vis.length)}) не выбраны.` : ""}`); }
const keyOf = f => SEL.find(s => s.f === f)?.key || LYR.find(l => layerSrc[l.key]?.hasFeature(f))?.key;
// объект под курсором: холст отвечает сам; крупный слой в обзоре (видеокарта) — поиск по его данным
function hitAt(pixel) {
  let hit = null;
  mMain.forEachFeatureAtPixel(pixel, (f, layer) => { const k = layer?.get("key"); if (!k || !lyr(k)) return; hit = { key: k, f }; return true; }, { hitTolerance: 4, layerFilter: la => { const l = lyr(la.get("key")); return !!l && shown(l) && !la.get("gl"); } });
  if (hit) return hit;
  const c = mMain.getCoordinateFromPixel(pixel), res = sharedView.getResolution(), tol = 5 * res;
  for (const l of LYR) {
    if (!l.gl || !shown(l) || outOfScale(l) || res < glSwitchRes(l)) continue;
    const src = layerSrc[l.key];
    if (l.geom === "poly") { const f = src.getFeaturesAtCoordinate(c).pop(); if (f && symVisible(f)) return { key: l.key, f }; }
    else { const f = src.getClosestFeatureToCoordinate(c, x => symVisible(x)); if (f && ol.coordinate.distance(c, f.getGeometry().getClosestPoint(c)) <= tol) return { key: l.key, f }; }
  }
  return null;
}
const symVisible = f => f.get(SYMK) !== -1;
// объект виден на карте: скрытые категорией или правилом стиля не выбираются рамкой и «выбрать все» — Del их не заденет
const visibleIn = (l, f) => l.gl ? symVisible(f) : !symbolOf(l, f).hide;
mMain.on("click", e => {
  if (UIS.tool !== "select") return;
  const hit = hitAt(e.pixel);
  // как «Определить объекты» в QGIS: выбор не меняет текущий слой, иначе рисование уйдёт в чужую выгрузку
  if (e.originalEvent.shiftKey) { if (hit) toggleSel(hit); return; }
  select(hit?.key, hit?.f || null);
});
/* рамка: Shift+тянуть добавляет к выбору, Ctrl/⌘+тянуть выбирает заново.
   Как в AutoCAD: слева направо — только объекты целиком внутри рамки, справа налево — все, которых рамка касается. */
let boxFrom = null;
const dragBox = new ol.interaction.DragBox({ condition: e => (UIS.tool === "select" || CAD.selecting()) && (ol.events.condition.shiftKeyOnly(e) || ol.events.condition.platformModifierKeyOnly(e)), className: "ol-dragbox selbox" });
dragBox.on("boxstart", e => { boxFrom = e.coordinate; });
dragBox.on("boxdrag", e => { document.querySelector(".selbox")?.classList.toggle("cross", e.coordinate[0] < boxFrom[0]); });
dragBox.on("boxend", e => {
  const ex = dragBox.getGeometry().getExtent(), cross = e.coordinate[0] < boxFrom[0], add = e.mapBrowserEvent.originalEvent.shiftKey, found = [];
  LYR.filter(l => shown(l) && !outOfScale(l)).forEach(l => layerSrc[l.key].forEachFeatureIntersectingExtent(ex, f => { if (visibleIn(l, f) && (cross || ol.extent.containsExtent(ex, f.getGeometry().getExtent()))) found.push({ key: l.key, f }); }));
  setSel(add ? [...SEL, ...found] : found);
  setHint(`${cross ? "Секущая рамка (справа налево): всё, чего касается" : "Рамка (слева направо): только объекты целиком внутри"} — выбрано ${fmt(SEL.length)}.`);
});
mMain.addInteraction(dragBox);
function setCurrent(key) {
  if (!lyr(key)) return; CUR = key; renderTree(); renderRight(); renderTable(); window.syncStatus?.();
  // инструмент рисования остаётся, если геометрия слоя подходит, иначе — инструмент под его геометрию
  if (UIS.tool === "vertex") setTool("vertex");                    // команда черчения продолжается: новый объект попадёт в новый текущий слой
}
function syncCurSelect() {
  const s = $("curLayer"); if (!s) return;
  s.innerHTML = LYR.length ? LYR.map(l => `<option value="${esc(l.key)}" ${l.key === CUR ? "selected" : ""}>${esc(l.title)} · ${{ poly: "полигоны", line: "линии", point: "точки" }[l.geom]}</option>`).join("") : `<option>новый слой</option>`;
  s.title = LYR.length ? `Слой для новых объектов: ${lyr(CUR)?.title || ""}` : "Слоёв нет: первый появится сам, как только начнёте чертить";
  s.disabled = !LYR.length;
}
$("curLayer").onchange = e => setCurrent(e.target.value);

/* ---------- строка инструментов ---------- */
const GEOMTOOL = { point: "point", line: "line", poly: "poly" };
const TOOLS = {
  select: { name: "Выбор", hint: "Выбор: щелчок, Shift+рамка. Команды — на ленте или буквами и Enter: L, PL, C, M, TR… F1 — все." },
  vertex: { name: "Вершины", hint: "Вершины %: тяните вершину; щелчок по ребру добавляет вершину, Alt+щелчок удаляет." },
  cmd: { name: "Команда", hint: "" } };
// слой для рисования: текущий, если геометрия подходит; иначе свой слой той же геометрии; иначе новый
function targetLayer(geom) {
  const cur = lyr(CUR); if (cur?.geom === geom) return cur;
  const own = LYR.find(l => l.geom === geom && l.key.startsWith("user:") && !isAnno(l));
  if (own) { setCurrentQuiet(own.key); return own; }
  const l = createLayerQuiet({ point: "Точки", line: "Линии", poly: "Полигоны" }[geom], geom);
  toast(`Создан слой «${l.title}»: новые объекты попадут в него. Переименовать — двойной щелчок в списке слоёв.`); return l;
}
const setCurrentQuiet = key => { CUR = key; renderTree(); renderRight(); renderTable(); window.syncStatus?.(); };
// слои «Размеры», «Надписи», «Штриховка» заводят команды оформления; обычное черчение в них не попадает
const isAnno = l => typeof ANNO !== "undefined" && Object.values(ANNO).some(a => a.title === l.title && a.geom === l.geom);
function createLayerQuiet(name, geom) { const key = "user:" + Date.now().toString(36);
  DATA[key] = { title: name, source: "создан в проекте", fetched_at: new Date().toISOString().slice(0, 10), fc: { type: "FeatureCollection", features: [] }, count: 0, fields: ["Наименование", "Примечание"] };
  ensureLayer(key, name, geom); setCurrentQuiet(key); return lyr(key); }
const measureSrc = new ol.source.Vector();
mMain.addLayer(new ol.layer.Vector({ source: measureSrc, zIndex: 120, style: f => [S([224, 138, 0, .15], "#c46f00", 2), new ol.style.Style({ text: new ol.style.Text({ text: f.get("label") || "", font: "600 12px system-ui, sans-serif", fill: new ol.style.Fill({ color: "#7a4200" }), stroke: new ol.style.Stroke({ color: "#fff", width: 3 }), overflow: true, placement: "point" }) })] }));
/* крупный слой: вершины и привязка берут объекты текущего кадра (до 5 000), а не все 100 000 —
   индекс рёбер на весь слой строился бы секунды при каждом выборе инструмента */
function viewCollection(key, cleanup) {
  const coll = new ol.Collection(), src = layerSrc[key];
  const fill = () => { const res = sharedView.getResolution(), l = lyr(key); coll.clear(); if (res > glSwitchRes(l)) return; const out = []; src.forEachFeatureInExtent(mMain.getView().calculateExtent(mMain.getSize()), f => { out.push(f); return out.length >= 5000 || undefined; }); coll.extend(out); };
  fill(); const k = mMain.on("moveend", fill); cleanup.push(() => ol.Observable.unByKey(k)); return coll;
}
let toolI = [], toolClean = [];
/* привязка: индекс вершин слоя строится один раз и дальше сам следит за правками источника. OpenLayers пересобирает
   индекс при каждом добавлении привязки на карту, поэтому привязки слоёв стоят на карте постоянно и только
   включаются и выключаются, а инструменты вставляются перед ними (привязка должна стоять после рисования и правки).
   Прежде индекс строился заново при каждом переключении инструмента и каждом выборе в «Переносе» — 0,4–0,8 с на
   слоях в 15 000 объектов. Крупный слой (больше 5 000 объектов) привязывает только к видимым в кадре. */
const big = l => l.gl || layerSrc[l.key].getFeatures().length > 5000;
const SNAPS = new Map();
function snapFor(l) {
  let c = SNAPS.get(l.key);
  if (c && c.src !== layerSrc[l.key]) { mMain.removeInteraction(c.snap); SNAPS.delete(l.key); c = null; }
  if (!c) { const snap = new ol.interaction.Snap({ source: layerSrc[l.key], pixelTolerance: 10 }); snap.set("gradoSnap", true); mMain.addInteraction(snap); c = { src: layerSrc[l.key], snap }; SNAPS.set(l.key, c); }
  return c.snap;
}
function placeTools(list) {                  // инструменты — перед постоянными привязками, привязки к кадру крупных слоёв — в конце
  const coll = mMain.getInteractions(), arr = coll.getArray();
  let at = arr.findIndex(i => i.get("gradoSnap")); if (at < 0) at = arr.length;
  list.filter(i => !i.get("viewSnap")).forEach(i => coll.insertAt(at++, i));
  list.filter(i => i.get("viewSnap")).forEach(i => mMain.addInteraction(i));
}
// прежние имена инструментов — команды черчения (cad.js); «Вершины» — ручки OpenLayers
const CMD_OF = { point: "point", line: "pline", poly: "pline", rect: "rect", mlen: "dist", marea: "area", terr: "terr", move: "move" };
function clearTools() { toolI.forEach(i => { mMain.removeInteraction(i); i.dispose(); });   /* Modify держит подписки на объекты до dispose */ toolI = []; toolClean.forEach(fn => fn()); toolClean = []; SNAPS.forEach(c => c.snap.setActive(false)); }
window.clearTools = clearTools;
window.CURKEY = () => CUR;
function setTool(t) {
  if (CMD_OF[t]) { CAD.start(CMD_OF[t], { prefer: t === "poly" ? "poly" : t === "line" ? "line" : null }); return; }
  if (!TOOLS[t]) t = "select";
  CAD.cancel(true); clearTools();
  let l = lyr(CUR);
  const selFs = SEL.map(s => s.f);
  if (t === "vertex" && !l && !SEL.length) { toast("Сначала выберите слой в списке или объекты на карте."); t = "select"; }
  UIS.tool = t;
  const src = l && layerSrc[l.key];
  const editedKeys = fs => { const ks = new Set(); fs.forEach(f => { f.set("_edited", true); f.unset("_cad"); const k = keyOf(f); if (k) ks.add(k); }); ks.forEach(k => syncFromSource(k)); };
  if (t === "vertex") {
    // как ручки AutoCAD: при выборе — вершины выбранных объектов; без выбора — объекты текущего слоя
    const what = selFs.length ? { features: new ol.Collection(selFs) } : big(l) ? { features: viewCollection(l.key, toolClean) } : { source: src };
    const mo = new ol.interaction.Modify({ ...what, deleteCondition: e => ol.events.condition.altKeyOnly(e) && ol.events.condition.singleClick(e) });
    let dragging = null;
    mo.on("modifystart", e => { dragging = e.features.getArray(); pushUndo(featRec(dragging.map(f => ({ key: keyOf(f), f })), "правка вершин")); });
    mo.on("modifyend", e => { dragging = null; CAD.grip(null); editedKeys(e.features.getArray()); if (SEL.length) renderRight(); }); toolI.push(mo);
    // как ручки AutoCAD: пока тянете вершину — длины соседних отрезков и координаты МСК у курсора
    const k = mMain.on("pointermove", e => { if (dragging) CAD.grip(dragging, e.coordinate); }); toolClean.push(() => { ol.Observable.unByKey(k); CAD.grip(null); });
    const on = new Set();
    if (CAD.ST.osnap) LYR.filter(shown).forEach(x => { if (big(x)) { const v = new ol.interaction.Snap({ features: viewCollection(x.key, toolClean), pixelTolerance: 10 }); v.set("viewSnap", true); toolI.push(v); } else on.add(snapFor(x)); });
    SNAPS.forEach((c, k) => { if (!lyr(k)) { mMain.removeInteraction(c.snap); SNAPS.delete(k); } else c.snap.setActive(on.has(c.snap)); });
  }
  placeTools(toolI);
  mMain.getTargetElement().style.cursor = t === "select" ? "" : "crosshair";
  CAD.grips?.(); syncRibbon(); syncStatus();
}
function syncRibbon() {
  document.querySelectorAll("[data-tool]").forEach(b => b.setAttribute("aria-pressed", b.dataset.tool === UIS.tool));
  $("bDelFeat").disabled = !SEL.length; $("bUndo").disabled = !UNDO.length; $("bRedo").disabled = !REDO.length;
  $("bUndo").title = UNDO.length ? `Отменить: ${UNDO[UNDO.length - 1].label} (${MOD}+Z)` : `Отменить (${MOD}+Z)`;
  $("bRedo").title = REDO.length ? `Вернуть: ${REDO[REDO.length - 1].label} (${MOD}+Shift+Z)` : `Вернуть отменённое (${MOD}+Shift+Z)`;
}
let hintOverride = null;
const setHint = t => { hintOverride = t; $("stHint").textContent = t; };
window.setHint = setHint;                // ход выгрузки из окна «Данные» (app.js) пишется сюда же
function syncStatus() {
  hintOverride = null; const l = lyr(CUR), n = SEL.length;
  if (UIS.tool === "cmd" && CAD.active()) { $("stHint").textContent = CAD.prompt(); $("stLayer").innerHTML = l ? `слой <b>${esc(l.title)}</b>` : ""; return; }
  const what = n ? `выбранных объектов (${fmt(n)})` : `слоя «${l?.title || "—"}»`;
  $("stHint").textContent = !TERR && !LYR.length && UIS.tool === "select" ? "С чего начать: нарисуйте что угодно инструментами сверху, задайте границу территории (BO и Enter) или откройте окно «Данные». Все клавиши — F1."
    : UIS.tool === "select" && n && CAD.gripsCut?.() ? `Выбрано ${fmt(n)}: ручек было бы больше ${fmt(CAD.MAXGRIPS)}, поэтому они не показаны — выберите меньше объектов, чтобы править вершины. Команды (M, CO, RO) работают со всем выбором; Esc — снять выбор.`
    : UIS.tool === "select" && n ? `Выбрано ${fmt(n)}: атрибуты справа, Del — удалить; команды: M — перенести, CO — копировать, RO — повернуть, MI — зеркало (буквы и Enter); Esc — снять выбор.`
    : TOOLS[UIS.tool].hint.replace("«%»", `«${l?.title || "—"}»`).replace("%", what);
  $("stLayer").innerHTML = l ? `слой <b>${esc(l.title)}</b>` : ""; $("stLayer").title = l ? `Текущий слой: ${l.title}` : "";
  window.syncStart?.();
}
window.syncStatus = syncStatus;
document.querySelectorAll("[data-tool]").forEach(b => b.onclick = () => setTool(b.dataset.tool));

$("bDelFeat").onclick = () => {
  if (!SEL.length) return toast("Выберите объект: инструмент «Выбор», щелчок по объекту.");
  const list = SEL, keys = new Set(list.map(s => s.key)); pushUndo(featRec(list, list.length > 1 ? `удаление ${list.length} об.` : "удаление"));
  list.forEach(s => layerSrc[s.key].removeFeature(s.f)); keys.forEach(k => syncFromSource(k)); setSel([]);
  if (list.length > 1) toast(`Удалено объектов: ${fmt(list.length)}. Вернуть — ${MOD}+Z.`);
};

/* ---------- отмена и возврат: правки объектов, стили, возврат выгрузки ----------
   Запись хранит прежнее состояние только затронутых объектов (а не копию всего слоя),
   поэтому отмена на слое в 100 000 объектов мгновенна. Обратная запись снимается в момент отмены. */

const propsOf = f => { const p = { ...f.getProperties() }; delete p[f.getGeometryName()]; return p; };
/* геометрия под слой другого вида: полигон в слое линий — его контуры замкнутыми линиями, замкнутая линия в слое
   полигонов — полигоном; точки только в слой точек. null — не переносится */
function geomFor(g, geom) {
  const t = g.getType(), closedRing = r => r.length > 3 && r[0][0] === r[r.length - 1][0] && r[0][1] === r[r.length - 1][1];
  if (geom === "point") return /Point/.test(t) ? g.clone() : null;
  if (/Point/.test(t)) return null;
  if (geom === "line") { if (/Line/.test(t)) return g.clone(); const rings = t === "Polygon" ? g.getCoordinates() : g.getCoordinates().flat();
    return rings.length === 1 ? new ol.geom.LineString(rings[0]) : new ol.geom.MultiLineString(rings); }
  if (/Polygon/.test(t)) return g.clone();
  const lines = (t === "LineString" ? [g.getCoordinates()] : g.getCoordinates()).filter(closedRing);
  return !lines.length ? null : lines.length === 1 ? new ol.geom.Polygon([lines[0]]) : new ol.geom.MultiPolygon(lines.map(r => [r]));
}
// копия объектов в буфере обмена программы (как в QGIS: Ctrl+C, Ctrl+V — в текущий слой на то же место)
let CLIP = [];
function copySel() { if (!SEL.length) return toast("Выберите объекты, которые нужно скопировать.");
  CLIP = SEL.map(({ f }) => ({ g: f.getGeometry().clone(), p: propsOf(f) })); toast(`Скопировано объектов: ${CLIP.length}. ${MOD}+V — вставить в текущий слой на то же место.`); }
function pasteClip() {
  const l = lyr(CUR); if (!l) return toast("Выберите слой, в который вставить.");
  if (!CLIP.length) return toast(`Буфер пуст: сначала выберите объекты и нажмите ${MOD}+C.`);
  const items = [];
  CLIP.forEach(c => { const g = geomFor(c.g, l.geom); if (!g) return; const f = new ol.Feature(g); const p = { ...c.p }; delete p._key; delete p[SYMK];
    f.setProperties({ ...p, _new: true, _edited: true }); items.push({ key: l.key, f }); });
  if (!items.length) return toast(`В слой «${l.title}» (${{ poly: "полигоны", line: "линии", point: "точки" }[l.geom]}) эти объекты не встают: ${l.geom === "poly" ? "у линий нет замкнутого контура" : "другой вид геометрии"}.`);
  pushUndo(featRec(items, `вставка ${items.length} об.`)); items.forEach(({ f }) => layerSrc[l.key].addFeature(f)); syncFromSource(l.key); setSel(items);
  toast(`Вставлено в «${l.title}»: ${items.length}${items.length < CLIP.length ? `, не подошли по виду геометрии: ${CLIP.length - items.length}` : ""}.`);
}
const snapF = (key, f) => layerSrc[key]?.hasFeature(f) ? { g: f.getGeometry()?.clone(), p: propsOf(f) } : null;
const featRec = (items, label) => ({ kind: "feat", label, items: items.map(({ key, f }) => ({ key, f, s: snapF(key, f) })) });
const undoKeys = u => u.kind === "feat" ? u.items.map(i => i.key) : [u.key];
function pushUndo(rec) { UNDO.push(rec); if (UNDO.length > 80) UNDO.shift(); REDO.length = 0; syncRibbon(); }
// ползунок и ввод числа дают десятки событий — одна запись на серию правок одного поля в течение 1,5 с
function pushStyleUndo(l, tag) {
  const top = UNDO[UNDO.length - 1], now = Date.now();
  if (top?.kind === "style" && top.key === l.key && top.tag === tag && now - top.t < 1500) { top.t = now; return; }
  pushUndo({ kind: "style", key: l.key, tag, t: now, label: `стиль «${l.title}»`, style: JSON.stringify(l.style), lop: l.layerOpacity });
}
function capture(rec) {
  if (rec.kind === "feat") return { ...rec, items: rec.items.map(it => ({ ...it, s: snapF(it.key, it.f) })) };
  if (rec.kind === "layer") return { ...rec, fs: layerSrc[rec.key].getFeatures() };
  const l = lyr(rec.key); return { ...rec, t: 0, style: JSON.stringify(l.style), lop: l.layerOpacity };
}
function applyRec(rec) {
  if (rec.kind === "style") { const l = lyr(rec.key); l.style = ST(JSON.parse(rec.style)); l.layerOpacity = rec.lop; restyle(l); applyOrder(); UIS.rt = "style"; if (CUR !== l.key) setCurrentQuiet(l.key); renderRight(); return; }
  if (rec.kind === "layer") { const src = layerSrc[rec.key]; src.clear(true); src.addFeatures(rec.fs); syncFromSource(rec.key); return; }
  const keys = new Set();
  rec.items.forEach(({ key, f, s }) => {
    const src = layerSrc[key]; if (!src) return; keys.add(key);
    if (!s) { if (src.hasFeature(f)) src.removeFeature(f); return; }
    Object.keys(propsOf(f)).forEach(k => { if (!(k in s.p)) f.unset(k, true); });
    f.setProperties(s.p, true); f.setGeometry(s.g.clone());
    if (!src.hasFeature(f)) src.addFeature(f);
  });
  keys.forEach(k => syncFromSource(k));
}
function stepHistory(from, to, verb) {
  const rec = from.pop(); if (!rec) return toast(from === UNDO ? "Отменять нечего." : "Возвращать нечего.");
  if (rec.kind !== "feat" && !lyr(rec.key)) return stepHistory(from, to, verb);   // слой удалён
  const inv = capture(rec); applyRec(rec); to.push(inv);
  setSel(SEL); setHint(`${verb}: ${rec.label}.`); syncRibbon();
}
const undo = () => stepHistory(UNDO, REDO, "Отменено"), redo = () => stepHistory(REDO, UNDO, "Возвращено");
$("bUndo").onclick = undo; $("bRedo").onclick = redo;
// стрелки — в фазе перехвата: иначе карта OpenLayers сдвинула бы вид вместе с объектами
addEventListener("keydown", e => {
  if (e.target.matches?.("input,select,textarea") || e.target.closest?.("#wGraph") || e.metaKey || e.ctrlKey || e.altKey) return;
  // сдвиг выбранного стрелками по осям МСК: 0,1 м, с Shift — 1 м
  if (/^Arrow/.test(e.key) && SEL.length && !window.CAD?.active?.() && window.CAD?.toM) {
    e.preventDefault(); e.stopPropagation(); const d = e.shiftKey ? 1 : .1, [dx, dy] = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, d], ArrowDown: [0, -d] }[e.key];
    pushUndo(featRec(SEL, `сдвиг ${fmt(d, 1)} м`));
    SEL.forEach(({ f }) => { f.getGeometry().applyTransform((inp, out, dim = 2) => { for (let i = 0; i < inp.length; i += dim) { const m = CAD.toM([inp[i], inp[i + 1]]), c = CAD.fromM([m[0] + dx, m[1] + dy]); out[i] = c[0]; out[i + 1] = c[1]; } return out; }); f.set("_edited", true); f.unset("_cad"); });
    new Set(SEL.map(s => s.key)).forEach(k => syncFromSource(k)); window.CAD.grips?.(); setHint(`Сдвинуто на ${fmt(d, 1)} м (${{ ArrowLeft: "запад", ArrowRight: "восток", ArrowUp: "север", ArrowDown: "юг" }[e.key]} по МСК). ${MOD}+Z — отменить.`); return;
  }
}, true);
addEventListener("keydown", e => {
  if (e.target.matches?.("input,select,textarea") || e.target.closest?.("#wGraph")) return;
  // e.code не зависит от раскладки (русская тоже работает); без code — по латинской букве
  const code = e.code || (/^[a-z]$/i.test(e.key) ? "Key" + e.key.toUpperCase() : "");
  const mod = e.metaKey || e.ctrlKey;
  if (mod && code === "KeyZ") { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
  if (mod && code === "KeyY") { e.preventDefault(); redo(); return; }
  if (mod && code === "KeyA") { e.preventDefault(); selectAll(); return; }
  if (mod && code === "KeyC" && !e.shiftKey && !getSelection()?.toString()) { e.preventDefault(); copySel(); return; }
  if (mod && code === "KeyV" && !e.shiftKey) { e.preventDefault(); pasteClip(); return; }
  if (e.key === "F1" || e.key === "?" || (e.shiftKey && code === "Slash")) { e.preventDefault(); winOpen("wKeys"); return; }
  if (mod || e.altKey) return;
  if ((e.key === "Delete" || e.key === "Backspace") && SEL.length && !window.CAD?.active?.()) { e.preventDefault(); $("bDelFeat").click(); }
  else if (e.key === "Escape") {
    // Esc по очереди: открытое меню → подбор вариантов → выбор и инструмент → верхнее плавающее окно
    const menu = document.querySelector(".cadmenu"); if (menu) { menu.remove(); return; }
    if (varRun && !varRun.stop) { $("bStopVar").click(); return; }
    if (!SEL.length && UIS.tool === "select" && !measureSrc.getFeatures().length) { const w = document.querySelector(".win.front:not([hidden]):not(.docked)"); if (w) { winOpen(w.id, false); return; } if (!$("start").hidden) { closeStart(); return; } }
    measureSrc.clear(); select(null, null); setTool("select"); }
});

/* ---------- окно «Клавиши»: собирается из тех же таблиц, что и обработчики, поэтому не расходится с ними ---------- */
function renderKeys() {
  const rows = (title, list) => `<div class="sect">${title}</div><table class="keys">${list.map(([k, v]) => `<tr><td><kbd>${k}</kbd></td><td>${v}</td></tr>`).join("")}</table>`;
  const steps = [
    ["Территория", "«Данные» → «Нарисовать границу» или «Пример». Граница задаёт, что выгружать и где считать показатели."],
    ["Существующее положение", "Отметьте источники (ЕГРН, OSM, ГИС ОГД: ПЗЗ, ОКН, красные линии, рельеф) → «Загрузить». Свои файлы — «Файл…» или перетащите на карту. Повторная выгрузка покажет, что изменилось, и сохранит ваши правки."],
    ["Реестр зданий", "Меню слоя зданий → «Реестр зданий». Выберите дома (щелчок, Shift+рамка) и отметьте «сносим» справа."],
    ["Ограничения", "Окно «Ограничения» → «Рассчитать»: запреты (ЗОУИТ, отступ от красных линий, пожарные разрывы, ПЗЗ) и потолок высоты по инсоляции соседей. Выключенный слой группы «Ограничения» посадка не учитывает."],
    ["Эскиз", "«Эскиз» → типология, «Этажность по цели плотности» → «Построить эскиз». «Варианты» → «Подобрать варианты» сравнит типологии. «Принять в проект» делает эскиз обычным слоем."],
    ["Проверка", "«Проверить нормы»: инсоляция новых домов и соседей, корпуса на запретах, разрывы. После правки принятого эскиза проверка повторяется сама."],
    ["Анализ", "«Граф» → группа «Анализ»: радиусы школ и детсадов, пешая доступность, показатели кварталов, баланс территории. «В слой» сохраняет результат с таблицей."],
    ["Выпуск", "«Виды» — наборы слоёв с оформлением. «Листы» — листы А3/А1 из видов с рамкой и штампом, «PDF альбома». «DXF» — чертёж в МСК с типами линий красных линий."],
    ["Проект", "Сохраняется сам через 2 с после правки; Ctrl+S — сохранить под именем, окно «Проекты» — открыть, новый, копия."]];
  $("keysBody").innerHTML = `<div class="sect">Как работать</div><table class="keys">${steps.map(([k, v], i) => `<tr><td><b>${i + 1}. ${k}</b></td><td>${v}</td></tr>`).join("")}</table>`
    + `<div class="note" style="color:var(--warn)">Инсоляция в ГРАДО — предпроектная оценка по методам ГОСТ Р 57795-2017 (22 апреля и 22 августа). Для экспертизы нужен сертифицированный расчёт. Радиусы обслуживания — по СП 42.13330.2016; московские нормативы 2150-ПП и 2151-ПП сверяйте отдельно.</div>`
    + rows("Команды черчения (набрать и Enter или пробел, как в AutoCAD)", Object.entries(CAD.ALIAS).map(([a, id]) => [a, `${CAD.CMDS[id].title}: ${CAD.HELP[id]}`]))
    + rows("Во время команды", [["число, Enter", "следующая точка на этом расстоянии по направлению курсора или по пунктирной линии отслеживания, м"], ["длина<угол", "длина и угол; угол от направления на восток против часовой стрелки"], ["@dx;dy", "смещение от последней точки по X и Y, м"], ["X;Y", "точка в координатах МСК (X — на восток, Y — на север)"], ["буква параметра", "вариант из квадратных скобок в строке состояния: З — замкнуть, О — отменить, Р — радиус…"], ["Enter, пробел, правая кнопка", "завершить шаг или команду; без команды — повторить последнюю"], ["Backspace", "убрать последнюю точку"], ["Esc", "прервать команду"]])
    + rows("Режимы черчения (строка состояния)", [["F3", "объектная привязка: конточка, середина, центр, квадрант, пересечение, продолжение, нормаль, касательная, параллельно (задержите курсор на отрезке — потом ведите параллельно ему), ближайшая (▾ — набор)"], ["F11", "объектное отслеживание: задержите курсор на точке привязки до «+», дальше — пунктирные линии выравнивания и продолжения"], ["F10", "полярное отслеживание: пунктирный луч под углами, кратными шагу (▾ — 90, 45, 30, 15, 10, 5°)"], ["F8", "орто: только по осям X и Y МСК"], ["F12", "динамический ввод: размеры и поле ввода у курсора"], ["F2", "история команд за сеанс"]])
    + rows("Выбор", [["щелчок", "выбрать объект"], ["Shift+щелчок", "добавить к выбору или убрать из него"], ["Shift+тянуть", "рамка: добавить объекты к выбору"], [`${MOD}+тянуть`, "рамка: выбрать заново"], ["рамка слева направо", "только объекты целиком внутри (как в AutoCAD)"], ["рамка справа налево", "все объекты, которых рамка касается"], [`${MOD}+A`, "все объекты текущего слоя"], [`${MOD}+C, ${MOD}+V`, "копировать выбранное и вставить в текущий слой на то же место"], ["← → ↑ ↓, с Shift", "сдвинуть выбранное на 0,1 м, с Shift — на 1 м (оси МСК)"], ["Esc", "снять выбор, вернуться к «Выбору»"]])
    + rows("Правка", [["Del, Backspace", "удалить выбранные объекты"], ["двойной щелчок", "завершить полилинию, замер, границу"], ["Вершины", "ручки: тянуть вершину, щелчок по ребру — новая вершина, Alt+щелчок — удалить"], [`${MOD}+Z`, "отменить правку объектов или стиля"], [`${MOD}+Shift+Z, ${MOD}+Y`, "вернуть отменённое"]])
    + rows("Проект и окна", [[`${MOD}+S`, "сохранить проект"], ["F1, ?", "это окно"], ["двойной щелчок по заголовку окна", "встроить в панель / сделать плавающим"],
      ["Alt+← → ↓ на заголовке окна (Tab до него)", "встроить слева / справа / под картой; Alt+↑ — плавающее"]])
    + rows("Карта", [["колесо, щипок", "масштаб"], ["тянуть", "сдвиг карты"]])
    + `<div class="note">Команды набираются в любой раскладке: считается клавиша, а не буква. Объекты сначала можно выбрать, потом вызвать команду редактирования — или наоборот.</div>`;
}
$("bKeys").onclick = () => winOpen("wKeys");

/* ---------- пустой проект: с чего начать ---------- */
// закрытая панель больше не появляется сама (её содержимое есть в справке F1)
let startOff = false; try { startOff = localStorage.getItem("grado2.start") === "off"; } catch { }
// во время команды панель прячется: иначе щелчок по карте под ней попадал в её кнопки и сбрасывал черчение
function syncStart() { const el = $("start"); if (el) el.hidden = startOff || !!(LYR.length || TERR) || UIS.tool !== "select" || !!window.CAD?.active(); }
window.syncStart = syncStart;
function closeStart() { startOff = true; try { localStorage.setItem("grado2.start", "off"); } catch { } syncStart(); }
$("start").addEventListener("click", e => {
  if (e.target.closest("[data-close-start]")) return closeStart();
  const b = e.target.closest("[data-go]"); if (!b) return;
  ({ example: () => { $("bExample").click(); winOpen("wData", true); toast("Пример границы задан. Отметьте источники в окне «Данные» и нажмите «Загрузить»."); },
    terr: () => setTool("terr"), draw: () => setTool("poly"), proj: () => $("bProj").click(), keys: () => winOpen("wKeys", true) })[b.dataset.go]();
});

// в подсказках Windows показывает Ctrl, macOS — ⌘
if (MOD === "⌘") document.querySelectorAll("[title*='Ctrl+']").forEach(b => b.title = b.title.replaceAll("Ctrl+", "⌘"));
mMain.on("pointermove", e => { const ll = ol.proj.toLonLat(e.coordinate), [x, y] = MSK.fromWgs(ll);
  $("stXY").textContent = `${innerWidth > 1180 ? "МСК " : ""}X ${fmt(x, 2)}  Y ${fmt(y, 2)}`; $("stXY").title = `${ll[1].toFixed(6)}° с.ш. ${ll[0].toFixed(6)}° в.д. (WGS84). МСК — как пользовательская СК «МСК» в QGIS; X — на восток, Y — на север, как в DXF и на листах.`; });
function scaleDen(r) { const la = ol.proj.toLonLat(sharedView.getCenter())[1]; return Math.round(r * Math.cos(la * Math.PI / 180) / 0.000264583 / 10) * 10; }
const syncScale = () => { $("stScale").textContent = "1:" + fmt(scaleDen(sharedView.getResolution()));
  // имя слоя вне своего масштаба — серым курсивом, как в QGIS
  LYR.forEach(l => { if (l.style.maxDen) document.querySelector(`[data-lk="${CSS.escape(l.key)}"] .nm`)?.classList.toggle("outscale", outOfScale(l)); }); };
sharedView.on("change:resolution", syncScale); syncScale();

ALLMAPS.forEach(m => window.attachDataLayers(m));
renderTree(); renderRight(); setTool("select"); renderKeys();
