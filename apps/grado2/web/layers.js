/* ГРАДО 2 · слои проекта как в QGIS: дерево с порядком прорисовки (перетаскивание), видимость,
   оформление (единое / категории / диапазоны / правила / знаки ЛГР), подписи, таблица атрибутов.
   Строка инструментов как в AutoCAD: рисование в текущий слой, вершины, перенос, удаление, замеры;
   правка выгрузок с возвратом к исходной.
   Данные слоя живут в DATA[key].fc (WGS84) — их же читает граф анализа. */

const CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"], OTHER = "#9aa1a8";
const RAMPS = { blue: ["#dcebfa", "#a8cbf1", "#6fa6e6", "#2a78d6", "#1a4f94", "#0f3363"], brick: ["#fbe4d8", "#f5b698", "#ec875b", "#cf5a2c", "#933717", "#5e200c"], green: ["#e1f2e3", "#b2dcb7", "#7ec188", "#3f9a4f", "#1f6e31", "#10461e"], grey: ["#f2f2f2", "#d4d4d4", "#aaaaaa", "#7a7a7a", "#4d4d4d", "#262626"] };
const PICK = [...CAT, "#1d1d1f", "#5f6368", "#9aa1a8", "#d4d4d4", "#ffffff", "#b3261e", "#1f7a4d", "#7a4b2a", ...RAMPS.blue.slice(0, 4), ...RAMPS.brick.slice(0, 4)];
const ramp = (n, k) => k === 1 ? [RAMPS[n][3]] : Array.from({ length: k }, (_, i) => RAMPS[n][Math.round(i * (RAMPS[n].length - 1) / Math.max(1, k - 1))]);
const ST = o => Object.assign({ mode: "single", fill: "#9aa1a8", stroke: "#5f6368", width: 1, opacity: .7, hatch: false, label: "", labelSize: 11,
  cat: { field: "", colors: {}, off: [] }, grad: { field: "", n: 5, ramp: "blue", method: "quantile" }, rules: { list: [], elseFill: "#dddddd", elseHide: false } }, o);
// порядок по умолчанию: сверху вниз (первый — самый верхний)
const PREFERRED = ["gisogd.red_lines", "gisogd.demolition", "nspd.buildings", "osm.buildings", "gisogd.okn", "nspd.zouit", "gisogd.szz", "gisogd.vodookhr", "gisogd.pzz_zones", "osm.roads", "nspd.parcels", "gisogd.pzz_sub", "gisogd.func_zones", "gisogd.func_zones_tinao", "osm.water", "relief.contours", "osm.landuse"];
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
    "gisogd.red_lines": { mode: "lgr", fill: "#d7191c", width: 1.3 },
    // ПЗЗ: подзоны окрашены по предельной плотности — она задана чаще высоты (серые — не установлена или «по факту»); зоны — контуром
    "gisogd.pzz_sub": { mode: "grad", opacity: .45, stroke: "#8a5a00", width: .6, grad: { field: "Плотность, тыс. м²/га", n: 5, ramp: "brick", method: "quantile" } },
    "gisogd.pzz_zones": { fill: "#ffffff", opacity: 0, stroke: "#6a3d9a", width: 1.4 },
    "gisogd.okn": { mode: "cat", hatch: true, width: 1.2, cat: { field: "Вид зоны", colors: {}, off: [] } },
    "gisogd.demolition": { fill: "#b3261e", stroke: "#b3261e", hatch: true, width: 1.4 },
    "relief.contours": { fill: "#a0663a", width: .8, label: "Высота, м", labelSize: 10 },
  })[key] || (fc.features.some(f => f.properties._lt) ? { mode: "lgr" } : { fill: CAT[LYR.length % CAT.length], stroke: "#3d3d3d" }));
}

/* ---------- модель ---------- */
const LYR = [];                       // сверху вниз
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
function olLayersFor(l) {
  const src = layerSrc[l.key], out = [];
  l._kind = kindOf(l); l.gl = l._kind.startsWith("gl");
  const cv = new ol.layer.Vector({ source: src, style: (f, res) => styleFor(l, f, res), declutter: !!l.style.label });
  if (l.gl) {
    symAll(l, false); const r = glSwitchRes(l);
    out.push(new ol.layer.WebGLVector({ source: src, style: glStyle(l), minResolution: r, disableHitDetection: true }));
    cv.setMaxResolution(r);
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
function writeFC(fs) { const o = GJ.writeFeaturesObject(fs); o.features.forEach(f => { if (f.properties) delete f.properties[SYMK]; }); return o; }
function bindFC(key) {
  const d = DATA[key]; if (d.stale) return;
  let cache = d.fc || null; delete d.fc;
  Object.defineProperty(d, "fc", { configurable: true, enumerable: true, get: () => cache ||= writeFC(layerSrc[key].getFeatures()), set: v => { cache = v; } });
  Object.defineProperty(d, "stale", { value: () => { cache = null; } });
}
function setLayerData(key, fc) {
  const d = DATA[key]; d.original ||= fc;              // исходная выгрузка — тот же объект: он больше не меняется
  layerSrc[key].clear(true); layerSrc[key].addFeatures(GJ.readFeatures(fc));
  syncFromSource(key, false); d.fc = fc;
}
/* правка на карте → DATA, которым питается граф */
function syncFromSource(key, edited = true) {
  const d = DATA[key], fs = layerSrc[key].getFeatures(); bindFC(key); d.stale();
  d.count = fs.length; d.rev = ++revSeq;
  if (fs.length) d.fields = [...new Set(fs.slice(0, 500).flatMap(f => f.getKeys().filter(k => k !== "geometry" && k !== SYMK)))];
  d.edited = fs.reduce((n, f) => n + (f.get("_edited") ? 1 : 0), 0);
  if (edited) dataRev++;
  const l = lyr(key);
  if (l) { l.cache.clear(); l._br = null; if (kindOf(l) !== l._kind) rebuildLayer(l); else if (l.gl) symAll(l, true); }
  renderTree(); renderTable();
}

/* ---------- оформление ---------- */
const isNum = v => typeof v === "number" || (v !== "" && v != null && !isNaN(+v));
const numOf = v => v == null || v === "" ? NaN : +v;   // пустое значение — «нет данных», а не ноль
function catValues(key, field) { const m = new Map(); layerSrc[key]?.getFeatures().forEach(f => { const v = String(f.get(field) ?? ""); m.set(v, (m.get(v) || 0) + 1); }); return [...m.entries()].sort((a, b) => b[1] - a[1]); }
function numFields(key) { const fs = layerSrc[key]?.getFeatures() || []; return fieldsOfKey(key).filter(k => fs.length && fs.slice(0, 300).every(f => f.get(k) == null || isNum(f.get(k)))); }
function assignCats(l, keep) {
  const st = l.style; if (!st.cat.field) st.cat.field = fieldsOfKey(l.key).find(k => !numFields(l.key).includes(k)) || fieldsOfKey(l.key)[0] || "";
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
const labelStyle = (l, f) => { const st = l.style, t = f.get(st.label); return t == null || t === "" ? null : new ol.style.Style({ text: new ol.style.Text({ text: String(t), font: `${st.labelSize}px system-ui, sans-serif`, fill: new ol.style.Fill({ color: "#1d1d1f" }), stroke: new ol.style.Stroke({ color: "#fff", width: 3 }), placement: l.geom === "line" ? "line" : "point", offsetY: l.geom === "point" ? -(11 + st.width * 2) : 0, overflow: false }) }); };   // у точки подпись над знаком, иначе знак её закрывает
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
function styleFor(l, f, res) {
  const st = l.style;
  const out = [];
  if (st.mode === "lgr") { out.push(redLineStyle(f)); }
  else {
    const s = symbolOf(l, f); if (s.hide) return null;
    const key = `${s.fill}|${s.hatch}`; let base = l.cache.get(key);
    if (!base) {
      if (l.geom === "line") base = new ol.style.Style({ stroke: new ol.style.Stroke({ color: s.fill, width: st.width, lineCap: "round", lineJoin: "round" }) });
      else if (l.geom === "point") base = new ol.style.Style({ image: new ol.style.Circle({ declutterMode: "obstacle", radius: 2 + st.width * 2, fill: new ol.style.Fill({ color: s.fill }), stroke: new ol.style.Stroke({ color: st.stroke, width: 1 }) }) });
      else base = new ol.style.Style({ fill: new ol.style.Fill({ color: s.hatch ? hatch(s.fill) : rgba(s.fill, st.opacity) }), stroke: st.width > 0 ? new ol.style.Stroke({ color: s.hatch ? s.fill : st.stroke, width: st.width }) : undefined });   // толщина 0 — без контура (холст с 0 рисует прежней толщиной)
      l.cache.set(key, base);
    }
    out.push(base);
  }
  if (st.label && res < 4) { const t = labelStyle(l, f); if (t) out.push(t); }
  return out;
}
function restyle(l) {
  l.cache.clear(); l._br = null;
  if (kindOf(l) !== l._kind) rebuildLayer(l);
  else if (l.gl) { symAll(l, false); ALLMAPS.forEach(m => m.getLayers().forEach(x => { if (x.get("key") === l.key) x.get("gl") ? x.setStyle(glStyle(l)) : x.changed(); })); }
  else layerSrc[l.key]?.changed();
  renderTree(); window.markDirty?.();
}

/* ---------- дерево слоёв ---------- */
function symHTML(l, color) {
  const st = l.style;
  if (st.mode === "lgr" && !color) return `<span class="sym line" style="border-top-color:#d7191c"></span>`;
  const c = color || (st.mode === "single" ? st.fill : st.mode === "cat" ? (Object.values(st.cat.colors)[0] || OTHER) : st.mode === "grad" ? ramp(st.grad.ramp, 3)[1] : (st.rules.list[0]?.fill || st.rules.elseFill));
  if (l.geom === "line") return `<span class="sym line" style="border-top-color:${c}"></span>`;
  if (l.geom === "point") return `<span class="sym pt" style="background:${c}"></span>`;
  return `<span class="sym" style="${st.hatch && !color ? `background:repeating-linear-gradient(135deg,${c} 0 1px,transparent 1px 4px);border-color:${c}` : st.mode === "single" && st.opacity === 0 && !color ? `background:transparent;border-color:${st.stroke}` : `background:${c}`}"></span>`;
}
function legendItems(l) {
  const st = l.style;
  if (st.mode === "cat") return catValues(l.key, st.cat.field).map(([v, n]) => ({ v, n, c: st.cat.colors[v] || OTHER, off: st.cat.off.includes(v), check: true }));
  if (st.mode === "grad") { const b = l._br || (l._br = breaks(l)), none = (layerSrc[l.key]?.getFeatures() || []).filter(f => isNaN(numOf(f.get(st.grad.field)))).length;
    return ramp(st.grad.ramp, b.length - 1).map((c, i) => ({ v: `${fmt(b[i], 1)} – ${fmt(b[i + 1], 1)}`, c })).concat(none ? [{ v: "нет значения", c: OTHER, n: none }] : []); }
  if (st.mode === "rules") return st.rules.list.map(r => ({ v: `${r.field} ${r.op} ${r.val}`, c: r.fill })).concat(st.rules.elseHide ? [] : [{ v: "остальные", c: st.rules.elseFill }]);
  return [];
}
function renderTree() {
  const el = $("layerTree"); if (!el) return;
  const res = (RESULT.sketch.length || RESULT.site) && PREVIEW_WINS.some(id => !$(id).hidden) ? `<div class="tgrp" title="Как предпросмотр в Grasshopper: виден, пока открыты окна «Граф», «Эскиз», «Варианты», «Объём» или «Сравнение». В проект эскиз попадает кнопкой «Принять в проект».">Предпросмотр графа${PREVIEW_WINS.some(id => !$(id).hidden) ? "" : " · скрыт"}</div>` + RES.map(r => `<label class="tn"><span class="tw"></span><input type="checkbox" data-res="${r.id}" ${r.on !== false ? "checked" : ""} aria-label="Показывать в предпросмотре"><span class="sym" style="background:${r.color}"></span><span class="nm">${r.title}</span><span class="meta num">${r.layer.getSource().getFeatures().length || ""}</span></label>`).join("") : "";
  if (!LYR.length) { el.innerHTML = `<div class="note">Слоёв пока нет. Нажмите «+» над списком и рисуйте, выберите инструмент рисования на панели сверху (слой появится сам) или загрузите источники в окне «Данные».</div>` + res; icons(); syncStart(); return; }
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
    const d = DATA[l.key], items = l.open ? legendItems(l).slice(0, 60) : [], ind = g ? " in" : "";
    h += `<div class="tn${ind} ${shown(l) ? "" : "off"}" draggable="true" data-lk="${esc(l.key)}" aria-selected="${CUR === l.key}">
      <button class="tw" data-tw="${esc(l.key)}" aria-label="Легенда" ${["cat", "grad", "rules"].includes(l.style.mode) ? "" : 'style="visibility:hidden"'}><i data-lucide="${l.open ? "chevron-down" : "chevron-right"}"></i></button>
      <input type="checkbox" data-vis="${esc(l.key)}" ${l.visible ? "checked" : ""} aria-label="Видимость">${symHTML(l)}
      <span class="nm" title="${esc(l.title)}${d?.source ? " — " + esc(d.source) : ""}${d?.fetched_at ? ", " + d.fetched_at : ""}">${esc(l.title)}</span>
      ${d?.edited && d.original ? `<span class="badge" title="Объектов выгрузки изменено вручную">изм. ${d.edited}</span>` : ""}
      ${l.gl ? `<span class="badge gl" title="Крупный слой рисуется видеокартой (WebGL). Штриховка показывается полупрозрачной заливкой, подписи — на крупном масштабе.">GPU</span>` : ""}
      <span class="meta num">${fmt(d?.count ?? 0)}</span>
      <button class="tw more" data-more="${esc(l.key)}" aria-label="Меню слоя"><i data-lucide="more-horizontal"></i></button></div>`
      + items.map(it => `<div class="tn leg${ind} ${it.off ? "off" : ""}">${it.check ? `<input type="checkbox" data-catoff="${esc(l.key)}|${esc(it.v)}" ${it.off ? "" : "checked"} aria-label="Показывать">` : ""}${symHTML(l, it.c)}<span class="nm">${esc(it.v || "—")}</span>${it.n != null ? `<span class="meta num">${it.n}</span>` : ""}</div>`).join("");
  });
  el.innerHTML = h + res;
  syncCurSelect(); syncStart();
  icons();
}
const tree = () => $("layerTree");
document.addEventListener("click", e => {
  const t = e.target;
  if (!tree()?.contains(t)) return;
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
    d?.original ? ["Вернуть исходную выгрузку", () => { if (!confirmInline(anchor, "Отменить все правки слоя и вернуть выгрузку?")) return; pushUndo({ kind: "layer", key, label: `возврат выгрузки «${l.title}»`, fs: layerSrc[key].getFeatures() }); setLayerData(key, d.original); dataRev++; }] : null,
    ["Удалить слой из проекта", () => removeLayer(key)]]);
}
document.addEventListener("pointerdown", e => { if (menuEl && !menuEl.contains(e.target) && !e.target.closest("[data-more],[data-gmore]")) closeMenu(); });
// window.confirm в браузере-вьюере не работает: подтверждение — повторным выбором пункта в течение 4 с
let pendingConfirm = null;
function confirmInline(anchor, text) { const now = Date.now(); if (pendingConfirm && now - pendingConfirm < 4000) { pendingConfirm = null; return true; } pendingConfirm = now; toast(text + " Выберите пункт ещё раз, чтобы подтвердить."); return false; }
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
function afterRemove() { dataRev++; normGroups(); applyOrder(); renderTree(); renderRight(); renderTable(); renderSources?.(); setTool(UIS.tool); }
function removeLayer(key) {
  const l = lyr(key); if (!l) return;
  if (!confirmInline(tree(), `Удалить слой «${l.title}» из проекта?`)) return;
  dropLayer(key); afterRemove();
}
$("bNewLayer").onclick = () => {
  const box = $("newLayerBox"); box.hidden = !box.hidden; if (!box.hidden) $("nlName").focus();
};
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
const cbtn = (key, c) => `<button class="cbtn" data-color="${key}" aria-label="Выбрать цвет"><i style="background:${c}"></i></button>`;
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
  let h = `<div class="pad"><div class="ph">${symHTML(l)}<b>${esc(l.title)}</b></div><div class="modes">${modes.map(([m, t]) => `<button data-mode="${m}" aria-pressed="${st.mode === m}">${t}</button>`).join("")}</div>`;
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
      <div class="t">${cbtn("rule:" + i, r.fill)}${l.geom === "poly" ? `<label class="inl"><input type="checkbox" data-rule="${i}" data-rk="hatch" ${r.hatch ? "checked" : ""}> штриховка</label>` : ""}<span class="sp"></span><span class="num">${(layerSrc[l.key]?.getFeatures() || []).filter(f => testRule(r, f)).length} об.</span><button class="tb" data-delrule="${i}" title="Удалить правило"><i data-lucide="x"></i></button></div></div>`).join("");
    h += `<div class="row"><button class="btn" data-addrule><i data-lucide="plus"></i>Правило</button></div><div class="rule"><div class="t" style="margin:0">Остальные ${cbtn("else", st.rules.elseFill)}<label class="inl"><input type="checkbox" data-k="rules.elseHide" ${st.rules.elseHide ? "checked" : ""}> скрыть</label></div></div>`;
  }
  h += `<div class="sect" style="margin:8px -8px 8px">Контур, прозрачность, подписи</div>`;
  if (l.geom === "poly") h += `<div class="row"><label>Контур</label>${cbtn("stroke", st.stroke)}<input type="number" data-k="width" min="0" max="8" step=".1" value="${st.width}" style="width:64px" aria-label="Толщина контура"> пикс.</div>
    <div class="row"><label>Заливка, %</label><input type="range" data-k="opacity" min="0" max="1" step=".05" value="${st.opacity}" aria-label="Непрозрачность заливки"><span class="num">${Math.round(st.opacity * 100)}</span></div>`;
  else h += `<div class="row"><label>${l.geom === "point" ? "Размер" : "Толщина"}</label><input type="number" data-k="width" min=".3" max="10" step=".1" value="${st.width}" style="width:64px" aria-label="Толщина"> пикс.</div>`;
  h += `<div class="row"><label>Слой, %</label><input type="range" data-lop min="0" max="1" step=".05" value="${l.layerOpacity}" aria-label="Непрозрачность слоя"><span class="num">${Math.round(l.layerOpacity * 100)}</span></div>
    <div class="row"><label>Подпись</label><select data-k="label"><option value="">нет</option>${fields.map(k => `<option ${st.label === k ? "selected" : ""}>${esc(k)}</option>`).join("")}</select><input type="number" data-k="labelSize" min="7" max="24" value="${st.labelSize}" style="width:54px" aria-label="Кегль"></div></div>`;
  el.innerHTML = h;
}
const numOrText = v => isNum(v) && String(v).trim() !== "" && !/^0\d/.test(v) ? +v : v;
const sizeOf = f => { const g = f.getGeometry(), t = g?.getType() || "", w = GJ.writeFeatureObject(f); return /Polygon/.test(t) ? ["area", turf.area(w)] : /Line/.test(t) ? ["len", turf.length(w, { units: "kilometers" }) * 1000] : ["pt", 0]; };
const DECSHORT = { "сохраняем": "сохраняем", "реконструкция": "реконстр.", "сносим": "сносим" };
const decisionBar = () => SEL.some(s => fieldsOfKey(s.key).includes(DECISION)) ? `<div class="pad" style="padding-top:0"><div class="seg dec">${Object.keys(DECISIONS).map(v => `<button data-decide="${v}" title="Решение по выбранным зданиям: ${v}"><i style="background:${DECISIONS[v]}"></i>${DECSHORT[v]}</button>`).join("")}</div></div>` : "";
function renderObject(el) {
  if (!SEL.length) { el.innerHTML = `<div class="empty">Щёлкните объект на карте или строку таблицы.<br><br>Несколько объектов — Shift+щелчок или рамка с Shift. Все объекты слоя — ${MOD}+A.</div>`; return; }
  if (SEL.length === 1) {
    const { key, f } = SEL[0], l = lyr(key), [kind, v] = sizeOf(f);
    const keys = Object.keys(f.getProperties()).filter(k => !hiddenField(k));
    el.innerHTML = `<div class="pad"><div class="ph"><b>${esc(l.title)}</b></div><div class="note" style="padding:0 0 6px">${kind === "area" ? fmt(v, 1) + " м²" : kind === "len" ? fmt(v, 2) + " м" : ""}${f.get("_edited") ? " · изменён вручную" : ""}${f.get("_lt") ? " · " + esc(f.get("_lt").join(", ")) : ""}</div></div>${decisionBar()}
      <div class="pg">${keys.map(k => `<div class="ro" title="${esc(k)}">${esc(k)}</div><div><input type="text" data-attr="${esc(k)}" value="${esc(f.get(k))}"></div>`).join("")}</div>
      <div class="pad"><div class="row"><input type="text" id="newField" placeholder="Новое поле"><button class="btn" id="bAddField">Добавить</button></div></div>`;
    return;
  }
  // несколько объектов: сводка и, если они из одного слоя, общая правка атрибутов (как «Изменить атрибуты выбранных» в QGIS)
  const by = new Map(); SEL.forEach(s => (by.get(s.key) || by.set(s.key, []).get(s.key)).push(s.f));
  let area = 0, len = 0; if (SEL.length <= 5000) SEL.forEach(s => { const [k, v] = sizeOf(s.f); if (k === "area") area += v; if (k === "len") len += v; });
  const sum = [area ? `площадь ${fmt(area / 1e4, 3)} га` : "", len ? `длина ${fmt(len, 0)} м` : ""].filter(Boolean).join(" · ");
  let h = `<div class="pad"><div class="ph"><b>Выбрано объектов: ${fmt(SEL.length)}</b></div>${sum ? `<div class="note" style="padding:0 0 6px">${sum}</div>` : ""}</div>${decisionBar()}`;
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
  if (t.dataset.attr !== undefined) { if (e.type !== "change" || SEL.length !== 1) return; const { key, f } = SEL[0]; pushUndo(featRec(SEL, `атрибут «${t.dataset.attr}»`)); f.set(t.dataset.attr, numOrText(t.value)); f.set("_edited", true); syncFromSource(key); return; }
  if (t.dataset.battr !== undefined) {
    if (e.type !== "change" || !SEL.length) return; const k = t.dataset.battr, v = numOrText(t.value);
    pushUndo(featRec(SEL, `атрибут «${k}» у ${SEL.length} об.`)); SEL.forEach(s => { s.f.set(k, v); s.f.set("_edited", true); });
    syncFromSource(SEL[0].key); renderRight(); toast(`«${k}» = «${t.value}» у ${fmt(SEL.length)} объектов. Отменить — ${MOD}+Z.`); return;
  }
  const l = lyr(CUR); if (!l) return; const st = l.style;
  if (t.hasAttribute("data-lop")) { pushStyleUndo(l, "lop"); l.layerOpacity = +t.value; t.nextElementSibling.textContent = Math.round(l.layerOpacity * 100); applyOrder(); return; }
  if (t.dataset.k) {
    pushStyleUndo(l, "k:" + t.dataset.k);
    const p = t.dataset.k.split("."), v = t.type === "checkbox" ? t.checked : ["range", "number"].includes(t.type) || p[1] === "n" ? +t.value : t.value;
    let o = st; p.slice(0, -1).forEach(x => o = o[x]); o[p[p.length - 1]] = v;
    if (t.dataset.k === "cat.field") assignCats(l, false);
    if (t.type === "range") t.nextElementSibling.textContent = Math.round(v * 100);
    restyle(l); if (e.type === "change") renderRight(); return;
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
function renderTable() {
  if ($("wTable").hidden) return; const l = lyr(CUR), el = $("attrBody");
  const selSet = new Set(SEL.map(s => s.f)), nSel = SEL.filter(s => s.key === CUR).length;
  $("attrTitle").textContent = l ? `${l.title} · ${fmt(DATA[l.key]?.count ?? 0)} объектов${nSel ? ` · выбрано ${fmt(nSel)}` : ""} · двойной щелчок по ячейке — правка` : "Выберите слой в дереве";
  if (!l) { el.innerHTML = ""; return; }
  const cols = fieldsOfKey(l.key); let rows = UIS.selOnly ? SEL.filter(s => s.key === CUR).map(s => s.f) : layerSrc[l.key].getFeatures().slice();
  if (UIS.filter) { const q = UIS.filter.toLowerCase(); rows = rows.filter(f => cols.some(k => String(f.get(k) ?? "").toLowerCase().includes(q))); }
  if (UIS.sort && cols.includes(UIS.sort.k)) rows.sort((a, b) => { const x = a.get(UIS.sort.k), y = b.get(UIS.sort.k); return (isNum(x) && isNum(y) ? x - y : String(x ?? "").localeCompare(String(y ?? ""), "ru")) * UIS.sort.d; });
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
  renderRight(); renderTable(); syncRibbon(); syncStatus();
  if (UIS.tool === "move" || UIS.tool === "vertex") setTool(UIS.tool);      // перенос и вершины работают с выбором
}
function select(key, f) { setSel(f ? [{ key, f }] : []); }
function toggleSel(it) { setSel(SEL.some(s => s.f === it.f) ? SEL.filter(s => s.f !== it.f) : [...SEL, it]); }
function selectAll() { const l = lyr(CUR); if (!l) return toast("Выберите слой в списке."); if (!shown(l)) return toast(`Слой «${l.title}» скрыт — включите его видимость.`); setSel(layerSrc[l.key].getFeatures().map(f => ({ key: l.key, f }))); toast(`Выбраны все объекты слоя «${l.title}»: ${fmt(SEL.length)}.`); }
const keyOf = f => SEL.find(s => s.f === f)?.key || LYR.find(l => layerSrc[l.key]?.hasFeature(f))?.key;
// объект под курсором: холст отвечает сам; крупный слой в обзоре (видеокарта) — поиск по его данным
function hitAt(pixel) {
  let hit = null;
  mMain.forEachFeatureAtPixel(pixel, (f, layer) => { const k = layer?.get("key"); if (!k || !lyr(k)) return; hit = { key: k, f }; return true; }, { hitTolerance: 4, layerFilter: la => { const l = lyr(la.get("key")); return !!l && shown(l) && !la.get("gl"); } });
  if (hit) return hit;
  const c = mMain.getCoordinateFromPixel(pixel), res = sharedView.getResolution(), tol = 5 * res;
  for (const l of LYR) {
    if (!l.gl || !shown(l) || res < glSwitchRes(l)) continue;
    const src = layerSrc[l.key];
    if (l.geom === "poly") { const f = src.getFeaturesAtCoordinate(c).pop(); if (f && symVisible(f)) return { key: l.key, f }; }
    else { const f = src.getClosestFeatureToCoordinate(c, x => symVisible(x)); if (f && ol.coordinate.distance(c, f.getGeometry().getClosestPoint(c)) <= tol) return { key: l.key, f }; }
  }
  return null;
}
const symVisible = f => f.get(SYMK) !== -1;
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
const dragBox = new ol.interaction.DragBox({ condition: e => UIS.tool === "select" && (ol.events.condition.shiftKeyOnly(e) || ol.events.condition.platformModifierKeyOnly(e)), className: "ol-dragbox selbox" });
dragBox.on("boxstart", e => { boxFrom = e.coordinate; });
dragBox.on("boxdrag", e => { document.querySelector(".selbox")?.classList.toggle("cross", e.coordinate[0] < boxFrom[0]); });
dragBox.on("boxend", e => {
  const ex = dragBox.getGeometry().getExtent(), cross = e.coordinate[0] < boxFrom[0], add = e.mapBrowserEvent.originalEvent.shiftKey, found = [];
  LYR.filter(shown).forEach(l => layerSrc[l.key].forEachFeatureIntersectingExtent(ex, f => { if (symVisible(f) && (cross || ol.extent.containsExtent(ex, f.getGeometry().getExtent()))) found.push({ key: l.key, f }); }));
  setSel(add ? [...SEL, ...found] : found);
  setHint(`${cross ? "Секущая рамка (справа налево): всё, чего касается" : "Рамка (слева направо): только объекты целиком внутри"} — выбрано ${fmt(SEL.length)}.`);
});
mMain.addInteraction(dragBox);
function setCurrent(key) {
  if (!lyr(key)) return; CUR = key; renderTree(); renderRight(); renderTable();
  // инструмент рисования остаётся, если геометрия слоя подходит, иначе — инструмент под его геометрию
  const t = TOOLS[UIS.tool]; setTool(t.geom && t.geom !== lyr(key).geom ? GEOMTOOL[lyr(key).geom] : UIS.tool);
}
function syncCurSelect() {
  const s = $("curLayer"); if (!s) return;
  s.innerHTML = LYR.length ? LYR.map(l => `<option value="${esc(l.key)}" ${l.key === CUR ? "selected" : ""}>${esc(l.title)} · ${{ poly: "полигоны", line: "линии", point: "точки" }[l.geom]}</option>`).join("") : `<option>нет слоёв — появится при рисовании</option>`;
  s.disabled = !LYR.length;
}
$("curLayer").onchange = e => setCurrent(e.target.value);

/* ---------- строка инструментов ---------- */
const GEOMTOOL = { point: "point", line: "line", poly: "poly" };
const TOOLS = {
  select: { name: "Выбор", hint: "Выбор: щелчок — объект, Shift+щелчок — добавить или убрать, Shift+рамка — несколько. Del — удалить, Esc — снять выбор." },
  point: { name: "Точка", geom: "point", hint: "Точка: щелчок ставит точку в слой «%»." },
  line: { name: "Линия", geom: "line", hint: "Линия в слой «%»: щёлкайте вершины, двойной щелчок завершает, Backspace убирает последнюю вершину, Esc — отмена." },
  poly: { name: "Полигон", geom: "poly", hint: "Полигон в слой «%»: щёлкайте вершины, двойной щелчок завершает, Backspace убирает последнюю вершину, Esc — отмена." },
  rect: { name: "Прямоугольник", geom: "poly", hint: "Прямоугольник в слой «%»: щёлкните первый угол, затем противоположный." },
  vertex: { name: "Вершины", hint: "Вершины %: тяните вершину; щелчок по ребру добавляет вершину, Alt+щелчок удаляет." },
  move: { name: "Перенос", hint: "Перенос %: тяните объект." },
  mlen: { name: "Длина", hint: "Длина: щёлкайте точки, двойной щелчок завершает. Замеры остаются на карте, Esc стирает." },
  marea: { name: "Площадь", hint: "Площадь: щёлкайте вершины, двойной щелчок завершает. Замеры остаются на карте, Esc стирает." },
  terr: { name: "Граница территории", hint: "Граница территории: щёлкайте углы, двойной щелчок завершает." } };
const KEYS = { KeyV: "select", KeyP: "point", KeyL: "line", KeyG: "poly", KeyR: "rect", KeyE: "vertex", KeyM: "move", KeyD: "mlen", KeyA: "marea", KeyB: "terr" };
// слой для рисования: текущий, если геометрия подходит; иначе свой слой той же геометрии; иначе новый
function targetLayer(geom) {
  const cur = lyr(CUR); if (cur?.geom === geom) return cur;
  const own = LYR.find(l => l.geom === geom && l.key.startsWith("user:"));
  if (own) { setCurrentQuiet(own.key); return own; }
  const l = createLayerQuiet({ point: "Точки", line: "Линии", poly: "Полигоны" }[geom], geom);
  toast(`Создан слой «${l.title}»: новые объекты попадут в него. Переименовать — двойной щелчок в списке слоёв.`); return l;
}
const setCurrentQuiet = key => { CUR = key; renderTree(); renderRight(); renderTable(); };
function createLayerQuiet(name, geom) { const key = "user:" + Date.now().toString(36);
  DATA[key] = { title: name, source: "создан в проекте", fetched_at: new Date().toISOString().slice(0, 10), fc: { type: "FeatureCollection", features: [] }, count: 0, fields: ["Наименование", "Примечание"] };
  ensureLayer(key, name, geom); setCurrentQuiet(key); return lyr(key); }
const measureSrc = new ol.source.Vector();
mMain.addLayer(new ol.layer.Vector({ source: measureSrc, zIndex: 120, style: f => [S([224, 138, 0, .15], "#c46f00", 2), new ol.style.Style({ text: new ol.style.Text({ text: f.get("label") || "", font: "600 12px system-ui, sans-serif", fill: new ol.style.Fill({ color: "#7a4200" }), stroke: new ol.style.Stroke({ color: "#fff", width: 3 }), overflow: true, placement: "point" }) })] }));
const measureText = g => g.getType() === "Polygon" ? `${fmt(ol.sphere.getArea(g), 0)} м² · ${fmt(ol.sphere.getArea(g) / 1e4, 3)} га` : `${fmt(ol.sphere.getLength(g), 1)} м`;
/* крупный слой: вершины и привязка берут объекты текущего кадра (до 5 000), а не все 100 000 —
   индекс рёбер на весь слой строился бы секунды при каждом выборе инструмента */
function viewCollection(key, cleanup) {
  const coll = new ol.Collection(), src = layerSrc[key];
  const fill = () => { const res = sharedView.getResolution(), l = lyr(key); coll.clear(); if (res > glSwitchRes(l)) return; const out = []; src.forEachFeatureInExtent(mMain.getView().calculateExtent(mMain.getSize()), f => { out.push(f); return out.length >= 5000 || undefined; }); coll.extend(out); };
  fill(); const k = mMain.on("moveend", fill); cleanup.push(() => ol.Observable.unByKey(k)); return coll;
}
let toolI = [], toolClean = [], drawing = null;
function setTool(t) {
  if (!TOOLS[t]) t = "select";
  toolI.forEach(i => mMain.removeInteraction(i)); toolI = []; toolClean.forEach(fn => fn()); toolClean = []; drawing = null;
  let l = lyr(CUR);
  const geom = TOOLS[t].geom, selFs = SEL.map(s => s.f);
  if (geom) l = targetLayer(geom);
  else if ((t === "vertex" || t === "move") && !l && !SEL.length) { toast("Сначала выберите слой в списке или объекты на карте."); t = "select"; }
  UIS.tool = t;
  const src = l && layerSrc[l.key];
  const draw = opts => { const d = new ol.interaction.Draw(opts); d.on("drawstart", e => { drawing = d; if (opts.measure) e.feature.getGeometry().on("change", ev => setHint(measureText(ev.target))); });
    d.on("drawabort", () => { drawing = null; syncStatus(); }); toolI.push(d); return d; };
  const editedKeys = fs => { const ks = new Set(); fs.forEach(f => { f.set("_edited", true); const k = keyOf(f); if (k) ks.add(k); }); ks.forEach(k => syncFromSource(k)); };
  if (geom) {
    const d = draw({ source: src, type: t === "rect" ? "Circle" : { point: "Point", line: "LineString", poly: "Polygon" }[geom], geometryFunction: t === "rect" ? ol.interaction.Draw.createBox() : undefined });
    d.on("drawend", e => { drawing = null; pushUndo(featRec([{ key: l.key, f: e.feature }], `новый объект в «${l.title}»`)); e.feature.setProperties({ _edited: true, _new: true }); fieldsOfKey(l.key).forEach(k => e.feature.set(k, "")); setTimeout(() => { syncFromSource(l.key); select(l.key, e.feature); syncStatus(); }, 0); });
  } else if (t === "vertex") {
    // как ручки AutoCAD: при выборе — вершины выбранных объектов; без выбора — объекты текущего слоя
    const what = selFs.length ? { features: new ol.Collection(selFs) } : l.gl ? { features: viewCollection(l.key, toolClean) } : { source: src };
    const mo = new ol.interaction.Modify({ ...what, deleteCondition: e => ol.events.condition.altKeyOnly(e) && ol.events.condition.singleClick(e) });
    mo.on("modifystart", e => pushUndo(featRec(e.features.getArray().map(f => ({ key: keyOf(f), f })), "правка вершин")));
    mo.on("modifyend", e => { editedKeys(e.features.getArray()); if (SEL.length) renderRight(); }); toolI.push(mo);
  } else if (t === "move") {
    const tr = new ol.interaction.Translate(selFs.length ? { features: new ol.Collection(selFs) } : { layers: ALLMAPS.length ? [mainOl(mMain, l.key)] : [] });
    tr.on("translatestart", e => pushUndo(featRec(e.features.getArray().map(f => ({ key: keyOf(f), f })), selFs.length > 1 ? `перенос ${selFs.length} об.` : "перенос")));
    tr.on("translateend", e => editedKeys(e.features.getArray())); toolI.push(tr);
  } else if (t === "mlen" || t === "marea") {
    const d = draw({ source: measureSrc, type: t === "mlen" ? "LineString" : "Polygon", measure: true });
    d.on("drawend", e => { drawing = null; const g = e.feature.getGeometry(); e.feature.set("label", measureText(g)); setHint(measureText(g) + " — замер оставлен на карте, Esc стирает."); });
  } else if (t === "terr") {
    const d = draw({ source: new ol.source.Vector(), type: "Polygon" });
    d.on("drawend", e => { drawing = null; setTerritory(GJ.writeFeatureObject(e.feature)); setTool("select"); toast("Граница задана. Выгрузка источников — окно «Данные»."); });
  }
  if (["point", "line", "poly", "rect", "vertex", "move"].includes(t) && $("snapT").checked)
    LYR.filter(shown).forEach(x => toolI.push(new ol.interaction.Snap(x.gl ? { features: viewCollection(x.key, toolClean), pixelTolerance: 10 } : { source: layerSrc[x.key], pixelTolerance: 10 })));
  toolI.forEach(i => mMain.addInteraction(i));
  mMain.getTargetElement().style.cursor = t === "select" ? "" : t === "move" ? "move" : "crosshair";
  syncRibbon(); syncStatus();
}
function syncRibbon() {
  document.querySelectorAll("[data-tool]").forEach(b => b.setAttribute("aria-pressed", b.dataset.tool === UIS.tool));
  $("bDelFeat").disabled = !SEL.length; $("bUndo").disabled = !UNDO.length; $("bRedo").disabled = !REDO.length;
  $("bUndo").title = UNDO.length ? `Отменить: ${UNDO[UNDO.length - 1].label} (${MOD}+Z)` : `Отменить (${MOD}+Z)`;
  $("bRedo").title = REDO.length ? `Вернуть: ${REDO[REDO.length - 1].label} (${MOD}+Shift+Z)` : `Вернуть отменённое (${MOD}+Shift+Z)`;
}
let hintOverride = null;
const setHint = t => { hintOverride = t; $("stHint").textContent = t; };
function syncStatus() {
  hintOverride = null; const l = lyr(CUR), n = SEL.length;
  const what = n ? `выбранных объектов (${fmt(n)})` : `слоя «${l?.title || "—"}»`;
  $("stHint").textContent = !TERR && !LYR.length && UIS.tool === "select" ? "С чего начать: нарисуйте что угодно инструментами сверху, задайте границу территории (B) или откройте окно «Данные». Все клавиши — F1."
    : UIS.tool === "select" && n ? `Выбрано ${fmt(n)}: атрибуты справа, Del — удалить, M — перенести, E — вершины, Esc — снять выбор.`
    : TOOLS[UIS.tool].hint.replace("«%»", `«${l?.title || "—"}»`).replace("%", what);
  $("stLayer").innerHTML = l ? `слой <b>${esc(l.title)}</b>` : "";
}
window.syncStatus = syncStatus;
document.querySelectorAll("[data-tool]").forEach(b => b.onclick = () => setTool(b.dataset.tool));
$("snapT").onchange = () => setTool(UIS.tool);
$("bDelFeat").onclick = () => {
  if (!SEL.length) return toast("Выберите объект: инструмент «Выбор», щелчок по объекту.");
  const list = SEL, keys = new Set(list.map(s => s.key)); pushUndo(featRec(list, list.length > 1 ? `удаление ${list.length} об.` : "удаление"));
  list.forEach(s => layerSrc[s.key].removeFeature(s.f)); keys.forEach(k => syncFromSource(k)); setSel([]);
  if (list.length > 1) toast(`Удалено объектов: ${fmt(list.length)}. Вернуть — ${MOD}+Z.`);
};

/* ---------- отмена и возврат: правки объектов, стили, возврат выгрузки ----------
   Запись хранит прежнее состояние только затронутых объектов (а не копию всего слоя),
   поэтому отмена на слое в 100 000 объектов мгновенна. Обратная запись снимается в момент отмены. */
const UNDO = [], REDO = [];
const propsOf = f => { const p = { ...f.getProperties() }; delete p[f.getGeometryName()]; return p; };
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
  if (drawing) { if (from === UNDO) drawing.removeLastPoint(); return; }
  const rec = from.pop(); if (!rec) return toast(from === UNDO ? "Отменять нечего." : "Возвращать нечего.");
  if (rec.kind !== "feat" && !lyr(rec.key)) return stepHistory(from, to, verb);   // слой удалён
  const inv = capture(rec); applyRec(rec); to.push(inv);
  setSel(SEL); setHint(`${verb}: ${rec.label}.`); syncRibbon();
}
const undo = () => stepHistory(UNDO, REDO, "Отменено"), redo = () => stepHistory(REDO, UNDO, "Возвращено");
$("bUndo").onclick = undo; $("bRedo").onclick = redo;
addEventListener("keydown", e => {
  if (e.target.matches?.("input,select,textarea") || e.target.closest?.("#wGraph")) return;
  // e.code не зависит от раскладки (русская тоже работает); без code — по латинской букве
  const code = e.code || (/^[a-z]$/i.test(e.key) ? "Key" + e.key.toUpperCase() : "");
  const mod = e.metaKey || e.ctrlKey;
  if (mod && code === "KeyZ") { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
  if (mod && code === "KeyY") { e.preventDefault(); redo(); return; }
  if (mod && code === "KeyA") { e.preventDefault(); selectAll(); return; }
  if (e.key === "F1" || e.key === "?" || (e.shiftKey && code === "Slash")) { e.preventDefault(); winOpen("wKeys"); return; }
  if (mod || e.altKey) return;
  if (e.key === "Backspace" && drawing) { e.preventDefault(); drawing.removeLastPoint(); }
  else if ((e.key === "Delete" || e.key === "Backspace") && SEL.length) { e.preventDefault(); $("bDelFeat").click(); }
  else if (e.key === "Escape") { if (drawing) { drawing.abortDrawing(); return; } measureSrc.clear(); select(null, null); setTool("select"); }
  else if (KEYS[code]) { e.preventDefault(); setTool(KEYS[code]); }
});

/* ---------- окно «Клавиши»: собирается из тех же таблиц, что и обработчики, поэтому не расходится с ними ---------- */
const KEYNAME = c => c.replace(/^Key/, "");
function renderKeys() {
  const rows = (title, list) => `<div class="sect">${title}</div><table class="keys">${list.map(([k, v]) => `<tr><td><kbd>${k}</kbd></td><td>${v}</td></tr>`).join("")}</table>`;
  $("keysBody").innerHTML = rows("Инструменты", Object.entries(KEYS).map(([c, t]) => [KEYNAME(c), TOOLS[t].name]))
    + rows("Выбор", [["щелчок", "выбрать объект"], ["Shift+щелчок", "добавить к выбору или убрать из него"], ["Shift+тянуть", "рамка: добавить объекты к выбору"], [`${MOD}+тянуть`, "рамка: выбрать заново"], ["рамка слева направо", "только объекты целиком внутри (как в AutoCAD)"], ["рамка справа налево", "все объекты, которых рамка касается"], [`${MOD}+A`, "все объекты текущего слоя"], ["Esc", "снять выбор, вернуться к «Выбору»"]])
    + rows("Правка", [["Del, Backspace", "удалить выбранные объекты"], ["Backspace", "при рисовании — убрать последнюю вершину"], ["двойной щелчок", "завершить линию, полигон, замер"], ["Alt+щелчок", "в «Вершинах» — удалить вершину"], [`${MOD}+Z`, "отменить правку объектов или стиля"], [`${MOD}+Shift+Z, ${MOD}+Y`, "вернуть отменённое"]])
    + rows("Проект и окна", [[`${MOD}+S`, "сохранить проект"], ["F1, ?", "это окно"], ["двойной щелчок по заголовку окна", "окно во всю высоту у края карты"]])
    + rows("Карта", [["колесо, щипок", "масштаб"], ["тянуть", "сдвиг карты"]])
    + `<div class="note">Буквы работают в любой раскладке: нажимается клавиша, а не символ.</div>`;
}
$("bKeys").onclick = () => winOpen("wKeys");

/* ---------- пустой проект: с чего начать ---------- */
function syncStart() { const el = $("start"); if (el) el.hidden = !!(LYR.length || TERR); }
window.syncStart = syncStart;
$("start").addEventListener("click", e => {
  const b = e.target.closest("[data-go]"); if (!b) return;
  ({ example: () => { $("bExample").click(); winOpen("wData", true); toast("Пример границы задан. Отметьте источники в окне «Данные» и нажмите «Загрузить»."); },
    terr: () => setTool("terr"), draw: () => setTool("poly"), proj: () => $("bProj").click(), keys: () => winOpen("wKeys", true) })[b.dataset.go]();
});

// в подсказках Windows показывает Ctrl, macOS — ⌘
if (MOD === "⌘") document.querySelectorAll("[title*='Ctrl+']").forEach(b => b.title = b.title.replaceAll("Ctrl+", "⌘"));
mMain.on("pointermove", e => { const [lo, la] = ol.proj.toLonLat(e.coordinate); $("stXY").textContent = `${la.toFixed(5)}° с.ш. ${lo.toFixed(5)}° в.д.`; });
const syncScale = () => { const r = sharedView.getResolution(), la = ol.proj.toLonLat(sharedView.getCenter())[1]; $("stScale").textContent = "1:" + fmt(Math.round(r * Math.cos(la * Math.PI / 180) / 0.000264583 / 10) * 10); };
sharedView.on("change:resolution", syncScale); syncScale();

ALLMAPS.forEach(m => window.attachDataLayers(m));
renderTree(); renderRight(); setTool("select"); renderKeys();
