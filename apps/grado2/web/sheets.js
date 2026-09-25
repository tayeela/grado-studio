/* ГРАДО 2 · листы и альбом (этап Э6). Лист = вид карты (или текущая карта) в рамке А3/А1 с масштабом, легендой вида,
   таблицей ТЭП, стрелкой севера, масштабной линейкой и основной надписью по ГОСТ Р 21.101. Оформление объектов
   считает тот же код, что рисует слои на экране (symbolOf), поэтому лист не расходится с картой; в PDF его
   собирает рендер ядра (print_io.py): МСК, типы линий REDLN97, штриховки. Состав альбома хранится в проекте. */
const ALBUM = { meta: { object: "", code: "", stage: "ПП", org: "" }, sheets: [] };
const SCALES = [500, 1000, 2000, 2500, 3000, 4000, 5000, 10000, 25000, 50000, 100000, 200000, 500000];
const FRAME_MM = { A3: [275, 224], A1: [636, 521], P: [238.67, 156.5] };   // размер карты на листе (как layout() в print_io.py)
const SIZE_T = { A3: "A3", A1: "A1", P: "16:9" };
const newSheet = () => ({ id: "s" + Date.now().toString(36) + Math.random().toString(36).slice(2, 4), title: VIEWS.find(v => v.id === VIEW_CUR)?.name || "Существующее положение", size: "A3", view: VIEW_CUR || "", scale: 0, legend: true, tep: false });

function autoScale(size, bb) {
  if (!TERR && !bb) return 2000;
  const [w, s, e, n] = bb || turf.bbox(TERR), mx = (e - w) * 111320 * Math.cos((s + n) / 2 * Math.PI / 180), my = (n - s) * 110540, [fw, fh] = FRAME_MM[size];
  const need = Math.max(mx / fw, my / fh) * 1000 * 1.08;
  return SCALES.find(v => v >= need) || SCALES[SCALES.length - 1];
}
// состояние слоя в виде (или как сейчас на карте)
function viewLayers(sheet) {
  // лист раздела: свой набор слоёв (снизу вверх) и своё оформление поверх стиля слоя
  if (sheet.keys) return sheet.keys.slice().reverse().map(k => lyr(k)).filter(Boolean).map(l => {
    const st = ST(JSON.parse(JSON.stringify({ ...l.style, ...(sheet.styles?.[l.key] || {}) })));
    return { key: l.key, title: l.title, geom: l.geom, style: st, visible: true, a: 1, _br: null, cache: new Map() }; });
  const v = VIEWS.find(x => x.id === sheet.view), by = v ? new Map(v.layers.map(x => [x.key, x])) : null, gv = v ? new Map(v.groups.map(x => [x.id, x.visible])) : null;
  // слой, которого не было при сохранении вида, в вид не входит — как при «Показать» (applyView)
  return LYR.map(l => { const x = by?.get(l.key); const st = x ? ST(JSON.parse(JSON.stringify(x.style))) : l.style, vis = v ? !!x?.visible : l.visible;
    const g = l.group ? (gv?.has(l.group) ? gv.get(l.group) : grp(l.group)?.visible !== false) : true;
    return { key: l.key, title: l.title, geom: l.geom, style: st, visible: vis && g, a: x ? x.layerOpacity ?? 1 : l.layerOpacity, _br: null, cache: new Map() }; }).filter(p => p.visible);
}
const sheetCenter = sheet => sheet.center || (sheet.fit && fitBox(sheet) ? [(fitBox(sheet)[0] + fitBox(sheet)[2]) / 2, (fitBox(sheet)[1] + fitBox(sheet)[3]) / 2]
  : TERR ? turf.centroid(TERR).geometry.coordinates : ol.proj.toLonLat(sharedView.getCenter()));
const sheetScale = sheet => sheet.scale || autoScale(sheet.size, sheet.fit ? fitBox(sheet) : null);
// показатели ТЭП строками таблицы; на листе с картой — первые 30, на листе «Таблица ТЭП» — все
function tepRows(all) {
  const t = RESULT.tepNode?._tep; if (!t) return [];
  const ms = t.metrics.filter(m => m.value);
  return [["Территория", fmt(t.terr, 2) + " га"], ["СПП новая", fmt(t.sppNew / 1000, 1) + " тыс. м²"], ["СПП сохраняемая", fmt(t.sppKept / 1000, 1) + " тыс. м²"], ["Плотность", fmt(t.density, 1) + " тыс. м²/га"], ["Застроенность", fmt(t.cover * 100, 1) + " %"]]
    .concat((all ? ms : ms.slice(0, 30)).map(m => [m.title, fmt(m.value, m.precision ?? 3) + " " + m.unit]));
}
function sheetSpec(sheet) {
  if (sheet.kind === "tep") return { title: sheet.title, size: sheet.size, kind: "tep", tep: tepRows(true) };
  if (sheet.kind === "title") return { title: sheet.title, size: sheet.size, kind: "title" };
  const size = sheet.size, scale = sheetScale(sheet), [fw, fh] = FRAME_MM[size];
  const center = sheetCenter(sheet);
  const half = [fw / 2 / 1000 * scale * 1.15, fh / 2 / 1000 * scale * 1.15], c3 = ol.proj.fromLonLat(center), stretch = 1 / Math.cos(center[1] * Math.PI / 180);
  const ext = [c3[0] - half[0] * stretch, c3[1] - half[1] * stretch, c3[0] + half[0] * stretch, c3[1] + half[1] * stretch];
  const vl = viewLayers(sheet).filter(pl => !(pl.style.maxDen && scale > pl.style.maxDen)), layers = [], legend = [];   // видимость по масштабу — и на листе, как в QGIS
  vl.slice().reverse().forEach(pl => {                                   // снизу вверх, как рисует карта
    const st = pl.style, feats = [];
    layerSrc[pl.key]?.forEachFeatureInExtent(ext, f => {
      const g = GJ.writeFeatureObject(f).geometry; if (!g) return;
      const only = sheet.only?.[pl.key]; if (only && !only.values.includes(f.get(only.field))) return;
      const lab = sheet.labelFn?.[pl.key] ? LABEL_FN[sheet.labelFn[pl.key]](f) : st.label ? f.get(st.label) : null;
      if (st.mode === "lgr") { const lt = f.get("_lt") || [], miss = f.get("_miss") || []; feats.push({ g, lt, miss, lc: LGRC[ltCode(lt[0] || "")] || LGRC[miss[0]?.[0]] || "#d7191c", w: st.width, label: lab }); return; }
      const s = symbolOf(pl, f); if (s.hide) return;
      feats.push({ g, fill: s.fill, stroke: pl.geom === "poly" ? st.stroke : s.fill, w: st.width, a: st.opacity * pl.a, hatch: s.hatch, hp: st.hatchPat || "45", label: lab == null || lab === "" ? null : String(lab), lc: pl.geom === "line" ? s.fill : undefined });
    });
    layers.push({ title: pl.title, features: feats });
  });
  if (sheet.legend) vl.forEach(pl => {
    const st = pl.style, items = st.mode === "lgr" ? [{ label: "красные линии и ЛГР (REDLN97)", fill: "#d7191c" }] : legendItems(pl).filter(it => !it.off).slice(0, 14).map(it => ({ label: it.v, fill: it.c, stroke: pl.geom === "poly" ? st.stroke : it.c, hatch: st.hatch, a: st.opacity }));
    legend.push({ title: pl.title, kind: pl.geom, items: items.length ? items : [{ label: pl.title, fill: st.fill, stroke: st.stroke, hatch: st.hatch, a: st.opacity }] });
  });
  const tep = sheet.tep ? tepRows(false) : [];
  const out = { title: sheet.title, size, scale, center, layers, legend, tep, territory: TERR?.geometry || null, basemap: sheet.basemap || "" };
  if (size === "P") out.terrStyle = sheet.fit === "okrug" ? { stroke: "#e0158c", width: .9, fill: "#e0158c" } : { stroke: "#e0158c", width: .9 };
  if (sheet.extra === "parcels") Object.assign(out, parcelsSheet(layers));
  if (sheet.extra === "radii") radiiSheet(out);
  if (sheet.note) out.note = sheet.note;
  if (size === "P" && sheet.legend) out.legend.unshift({ title: "Границы", kind: "poly", items: [{ label: "Граница разработки проекта планировки", fill: "#ffffff", stroke: "#e0158c", a: 0 }] });
  return out;
}
const albumSpec = list => ({ meta: { ...ALBUM.meta, short: ALBUM.meta.short || "", place: ALBUM.meta.place || placeText(), date: ALBUM.meta.date || monthYear() }, sheets: list.map(sheetSpec) });
const monthYear = () => { const d = new Date(); return ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"][d.getMonth()] + " " + d.getFullYear(); };
const OKR = { "Центральный": "ЦАО", "Северный": "САО", "Северо-Восточный": "СВАО", "Восточный": "ВАО", "Юго-Восточный": "ЮВАО", "Южный": "ЮАО", "Юго-Западный": "ЮЗАО",
  "Западный": "ЗАО", "Северо-Западный": "СЗАО", "Зеленоградский": "ЗелАО", "Новомосковский": "НАО", "Троицкий": "ТАО" };
const placeText = () => { const tp = RESULT.tepNode ? tepParams(RESULT.tepNode) : {}, o = String(tp.okrug || "").replace(/\s*административный округ/i, "").trim();
  return [OKR[o] || o, tp.district ? "район " + tp.district.replace(/^район\s+/i, "") : ""].filter(Boolean).join(", "); };
// подписи листов, собранные из нескольких полей: подзона ПЗЗ — «плотность / высота / застроенность», Ф — по факту
const LABEL_FN = { pzz: f => { const p = f.get("Плотность, тыс. м²/га"), h = f.get("Высота, м"), z = f.get("Застроенность, %");
  if (/не предусмотрено/.test(f.get("Регламент") || "")) return "0 / 0 / 0"; const v = x => x == null || x === "" ? "Ф" : String(x).replace(".", ","); return `${v(p)} / ${v(h)} / ${v(z)}`; } };
// рамка содержания листа: территория с полями, район или округ территории (из слоя административного деления ОГД)
function fitBox(sheet) {
  if (!TERR) return null;
  const c = turf.centroid(TERR).geometry.coordinates, adm = DATA["gisogd.admin"]?.fc.features || [];
  if (sheet.fit === "district" || sheet.fit === "okrug") {
    const lvl = sheet.fit === "district" ? "район" : "округ", f = adm.find(x => x.properties["Уровень"] === lvl && safe(() => turf.booleanPointInPolygon(c, x)));
    if (f) return turf.bbox(f);
    return turf.bbox(buf(TERR, sheet.fit === "district" ? 800 : 4000));
  }
  if (sheet.pad) return turf.bbox(buf(TERR, sheet.pad));
  const [w, s, e, n] = turf.bbox(TERR), k = (sheet.ctx || 1.4) / 2, cx = (w + e) / 2, cy = (s + n) / 2;
  return [cx - (e - w) * k, cy - (n - s) * k, cx + (e - w) * k, cy + (n - s) * k];
}
// землепользование: участки ЕГРН, задевающие территорию, пронумерованы по убыванию площади; таблица — справа
function parcelsSheet(layers) {
  const pl = (DATA["nspd.parcels"]?.fc.features || []).filter(f => { if (!/Polygon/.test(f.geometry?.type)) return false; const x = safe(() => inter(f, TERR)); return !!x && m2(x) > Math.min(50, m2(f) * .05); });
  pl.sort((a, b) => m2(b) - m2(a));
  const no = new Map(pl.map((f, i) => [f.properties["Кадастровый номер"] || i, i + 1]));
  layers.push({ title: "Номера участков", features: pl.map((f, i) => ({ g: turf.pointOnFeature(f).geometry, fill: "#ffffff", stroke: "#2b3cc4", w: 0, a: 0, label: String(i + 1) })) });
  return { table: { title: "Земельные участки в границах проекта", cols: [["№", .07, "left"], ["Кадастровый номер", .43, "left"], ["Площадь, м²", .2, "right"], ["Вид права", .3, "left"]],
    rows: pl.map((f, i) => [String(i + 1), String(f.properties["Кадастровый номер"] || "—"), fmt(+f.properties["Площадь участка, м²"] || Math.round(m2(f))), String(f.properties["Вид права"] || f.properties["Форма собственности"] || "—").slice(0, 28)]) } };
}
// социальная инфраструктура: объекты OSM и их радиусы обслуживания по нормам Москвы (2151-ПП) и СП 42.13330
function radiiSheet(out) {
  const ok = RESULT.tepNode ? tepParams(RESULT.tepNode).okrug : "", cao = /Централ/i.test(ok || "");
  const R = { "детский сад": cao ? 500 : 300, "школа": cao ? null : 1000, "поликлиника": 1000 }, col = { "детский сад": "#e0a100", "школа": "#1f5fbf", "поликлиника": "#2e8b3a" };
  const feats = [];
  (DATA["osm.social"]?.fc.features || []).filter(f => f.geometry?.type === "Point" && R[f.properties["Вид"]]).forEach(f => {
    const c = safe(() => turf.circle(f.geometry.coordinates, R[f.properties["Вид"]] / 1000, { steps: 64 }));
    if (c) feats.push({ g: c.geometry, fill: col[f.properties["Вид"]], stroke: col[f.properties["Вид"]], w: 1, a: .06, hatch: false, label: null }); });
  out.layers.unshift({ title: "Радиусы обслуживания", features: feats });
  out.legend.push({ title: "Радиусы обслуживания", kind: "poly", items: Object.entries(R).filter(([, r]) => r).map(([k, r]) => ({ label: `${k} — ${r} м`, fill: col[k], stroke: col[k], a: .15 })) });
}

/* Раздел 1 «Существующее положение» — слайды 16:9 по составу альбома ППТ: каждый лист знает свои слои, подложку,
   оформление и рамку содержания; «Собрать раздел» выгружает недостающие слои на всю площадь рамок и строит листы. */
const SEC1 = [
  { kind: "title", title: "Титульный слайд" },
  { title: "Месторасположение рассматриваемой территории", keys: ["gisogd.admin"], fit: "okrug" },
  { title: "Ортофотоплан", basemap: "sat", keys: ["gisogd.admin"], fit: "district", styles: { "gisogd.admin": { stroke: "#ffffff", labelSize: 13 } } },
  { title: "Ортофотоплан", basemap: "sat", keys: ["osm.roads"], fit: "terr", ctx: 3, styles: { "osm.roads": { mode: "single", fill: "#f5d58a", width: 1.4, label: "Название", labelSize: 11 } },
    only: { "osm.roads": { field: "Тип дороги", values: ["motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "living_street", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"] } } },
  { title: "Существующее состояние и использование территории с имеющимися ограничениями",
    // зоны ограничений — внизу бледной заливкой с контуром (альфы в PDF нет: сверху они закрыли бы здания), ОКН штриховкой
    // и красные линии — поверх
    keys: ["nspd.zouit", "gisogd.szz", "gisogd.vodookhr", "egko.green", "egko.water", "egko.roads", "nspd.parcels", "nspd.buildings", "gisogd.okn", "gisogd.red_lines"], fit: "terr", ctx: 1.6,
    styles: { "nspd.zouit": { hatch: false, opacity: .14, width: 1 }, "gisogd.szz": { hatch: false, opacity: .14, width: 1 }, "gisogd.vodookhr": { hatch: false, opacity: .14, width: 1 } } },
  { title: "Существующее использование территории с характеристикой по землепользованию", basemap: "sat", keys: ["nspd.parcels"], fit: "terr", ctx: 1.5, extra: "parcels",
    styles: { "nspd.parcels": { mode: "single", opacity: 0, stroke: "#2b3cc4", width: 1.6, label: "" } } },
  { title: "Фрагменты схем Генерального плана города Москвы", keys: ["gisogd.func_zones", "gisogd.func_zones_tinao"], fit: "terr", ctx: 1.6 },
  { title: "Фрагменты схем ПЗЗ: территориальные зоны и виды разрешённого использования", keys: ["gisogd.pzz_zones"], fit: "terr", ctx: 1.6, styles: { "gisogd.pzz_zones": { label: "ВРИ", labelSize: 9 } } },
  { title: "Фрагменты схем ПЗЗ: подзоны и предельные параметры", keys: ["gisogd.pzz_sub"], fit: "terr", ctx: 1.6, styles: { "gisogd.pzz_sub": { labelSize: 9 } }, labelFn: { "gisogd.pzz_sub": "pzz" },
    note: "Подписи подзон: плотность, тыс. м²/га / высота, м / застроенность, %; Ф — по фактическому использованию" },
  { title: "Схема об утверждённой и разрабатываемой документации", keys: ["egko.buildings", "gisogd.gpzu", "gisogd.krt", "gisogd.ppt"], fit: "terr", ctx: 2 },
  { title: "Объекты социальной инфраструктуры и радиусы обслуживания", keys: ["egko.buildings", "osm.social"], fit: "terr", pad: 700, extra: "radii" },
];
async function buildSection() {
  if (!TERR) return toast("Сначала задайте границу территории — от неё строятся рамки листов.");
  const sheets = SEC1.map((t, i) => ({ id: "sec1_" + i, size: "P", legend: t.kind !== "title", tep: false, scale: 0, view: "", ...JSON.parse(JSON.stringify(t)) }));
  // административное деление — для рамок «округ» и «район» его нужно получить первым
  if (!DATA["gisogd.admin"]) { toast("Раздел: административное деление Москвы (ГИС ОГД)…"); await loadKeys(["gisogd.admin"], turf.bbox(buf(TERR, 60))); }
  // остальные слои — по самой большой рамке листа, где слой нужен; одинаковые рамки — одной выгрузкой
  const need = new Map();
  sheets.filter(s => s.keys).forEach(s => { const bb = frameBox(s); s.keys.filter(k => k !== "gisogd.admin" && SOURCES[k]).forEach(k => {
    const cur = need.get(k); need.set(k, cur ? [Math.min(cur[0], bb[0]), Math.min(cur[1], bb[1]), Math.max(cur[2], bb[2]), Math.max(cur[3], bb[3])] : bb); }); });
  const groups = new Map(); need.forEach((bb, k) => { const g = bb.map(v => v.toFixed(5)).join(","); (groups.get(g) || groups.set(g, { bb, keys: [] }).get(g)).keys.push(k); });
  for (const { bb, keys } of groups.values()) { keys.forEach(k => CHECKED.add(k)); await loadKeys(keys, bb); }
  ALBUM.sheets = ALBUM.sheets.filter(s => !String(s.id).startsWith("sec1_")).concat(sheets);
  window.markDirty?.(); renderSheets(); toast(`Раздел «Существующее положение»: ${sheets.length} слайдов 16:9. «PDF альбома» — выгрузка; рамку любого листа можно сдвинуть.`);
}
// прямоугольник рамки листа в градусах (как frameGeom)
function frameBox(sh) { const g = frameGeom(sh).clone(); g.transform("EPSG:3857", "EPSG:4326"); return g.getExtent(); }

async function previewSheet(i) {
  busy(true);
  try {
    const r = await fetch("/api/print/svg", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...albumSpec([ALBUM.sheets[i]]), index: 0 }) });
    if (!r.ok) throw new Error((await r.json()).error);
    const url = URL.createObjectURL(await r.blob()), img = $("sheetPrev"); if (img.dataset.url) URL.revokeObjectURL(img.dataset.url);
    img.src = url; img.dataset.url = url; img.hidden = false;
  } catch (e) { toast("Лист не собран: " + e.message); } finally { busy(false); }
}
async function albumPdf() {
  if (!ALBUM.sheets.length) return toast("В альбоме нет листов: «Добавить лист».");
  busy(true);
  try {
    const r = await fetch("/api/print/pdf", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(albumSpec(ALBUM.sheets)) });
    if (!r.ok) throw new Error((await r.json()).error);
    const a = document.createElement("a"); a.href = URL.createObjectURL(await r.blob()); a.download = (ALBUM.meta.object || PROJ.name || "альбом") + ".pdf"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    toast(`Альбом PDF: ${ALBUM.sheets.length} л. Координаты — МСК, красные линии — типами REDLN97.`);
  } catch (e) { toast("PDF не собран: " + e.message); } finally { busy(false); }
}
function renderSheets() {
  const el = $("sheetsBody"); if (!el) return;
  const m = ALBUM.meta, inp = (k, ph) => `<input type="text" data-meta="${k}" value="${esc(m[k] || "")}" placeholder="${ph}" aria-label="${ph}">`;
  const vopts = s => `<option value="" ${s.kind !== "tep" && !s.view ? "selected" : ""}>текущая карта</option>` + VIEWS.map(v => `<option value="${v.id}" ${s.kind !== "tep" && v.id === s.view ? "selected" : ""}>вид «${esc(v.name)}»</option>`).join("")
    + `<option value="__tep" ${s.kind === "tep" ? "selected" : ""}>таблица ТЭП (все показатели)</option>`;
  const tepS = s => s.kind === "tep" ? "disabled" : "";
  el.innerHTML = `<div class="pad"><div class="note" style="padding:0 0 6px">Основная надпись</div><div class="meta4">${inp("object", "Объект")}${inp("code", "Шифр")}${inp("stage", "Стадия кратко: ПП, П, Р")}${inp("org", "Организация")}</div></div>`
    + `<div class="sect">Листы альбома</div>`
    + (ALBUM.sheets.length ? `<table class="at sheets"><colgroup><col style="width:26px"><col><col style="width:58px"><col style="width:20%"><col style="width:19%"><col style="width:36px"><col style="width:36px"><col style="width:148px"></colgroup><thead><tr><th>№</th><th>Название</th><th>Формат</th><th>Содержание</th><th>Масштаб</th><th title="Легенда вида">Лег.</th><th title="Таблица ТЭП">ТЭП</th><th></th></tr></thead><tbody>${ALBUM.sheets.map((s, i) => `<tr data-sh="${i}">
        <td class="num">${i + 1}</td><td><input type="text" data-sk="title" value="${esc(s.title)}" aria-label="Название листа"></td>
        <td><select data-sk="size" aria-label="Формат">${["A3", "A1", "P"].map(v => `<option value="${v}" ${v === s.size ? "selected" : ""}>${SIZE_T[v]}</option>`).join("")}</select></td>
        <td><select data-sk="view" aria-label="Содержание листа">${vopts(s)}</select></td>
        <td><select data-sk="scale" aria-label="Масштаб" ${tepS(s)}><option value="0" title="Масштаб подобран так, чтобы территория поместилась на лист">авто 1:${fmt(sheetScale({ ...s, scale: 0 }))}</option>${SCALES.map(v => `<option value="${v}" ${v === s.scale ? "selected" : ""}>1:${fmt(v)}</option>`).join("")}</select></td>
        <td><input type="checkbox" data-sk="legend" ${s.legend ? "checked" : ""} aria-label="Легенда" ${tepS(s)}></td><td><input type="checkbox" data-sk="tep" ${s.tep ? "checked" : ""} aria-label="ТЭП" ${tepS(s)}></td>
        <td class="acts">${s.kind === "tep" ? "" : `<button class="tb" data-shframe="${i}" aria-pressed="${FRAME?.i === i}" title="Рамка листа на карте: тяните её мышью, чтобы выбрать, что попадёт на лист${s.center ? ". Сейчас лист сдвинут — «Вернуть» центрирует его на территории" : ""}"><i data-lucide="frame"></i></button>`}${s.center && s.kind !== "tep" ? `<button class="tb" data-shreset="${i}" title="Вернуть лист в центр территории"><i data-lucide="locate-fixed"></i></button>` : ""}<button class="tb" data-shprev="${i}" title="Просмотр листа"><i data-lucide="eye"></i></button><button class="tb" data-shup="${i}" title="Выше"><i data-lucide="arrow-up"></i></button><button class="tb" data-shdel="${i}" title="Удалить лист"><i data-lucide="trash-2"></i></button></td></tr>`).join("")}</tbody></table>`
      : `<div class="note">Листов пока нет. Лист берёт вид карты (окно «Виды») или текущую карту, рамку А3/А1 по ГОСТ, легенду и ТЭП.</div>`)
    + `<div class="pad row"><button class="btn" id="shAdd"><i data-lucide="file-plus"></i>Добавить лист</button><button class="btn" id="shSec1" title="Слайды 16:9 раздела «Существующее положение»: месторасположение, ортофотопланы, ограничения, землепользование, Генплан, ПЗЗ, документация, соцобъекты. Недостающие слои выгружаются на всю площадь листов"><i data-lucide="layout-template"></i>Раздел 1: существующее положение</button><span class="sp" style="flex:1"></span><button class="btn primary" id="shPdf" title="Все листы одним PDF: рамка, штамп, масштаб, легенда"><i data-lucide="file-down"></i>PDF альбома</button></div>`
    + `<div class="sheetprev"><img id="sheetPrev" alt="Просмотр листа" hidden></div>`;
  icons();
}
const shEl = () => $("sheetsBody");
shEl().addEventListener("change", e => {
  const t = e.target, row = t.closest("[data-sh]");
  if (t.dataset.meta) { ALBUM.meta[t.dataset.meta] = t.value; window.markDirty?.(); return; }
  if (!row || !t.dataset.sk) return; const s = ALBUM.sheets[+row.dataset.sh], k = t.dataset.sk;
  if (k === "view") { s.kind = t.value === "__tep" ? "tep" : "map"; s.view = s.kind === "tep" ? "" : t.value; if (s.kind === "tep") { s.title = s.title === newSheet().title || !s.title ? "Технико-экономические показатели" : s.title; if (FRAME?.i === +row.dataset.sh) showFrame(null); } }
  else s[k] = t.type === "checkbox" ? t.checked : k === "scale" ? +t.value : t.value;
  window.markDirty?.(); if (["size", "view"].includes(k)) renderSheets();
  if (FRAME?.i === +row.dataset.sh && ["size", "scale", "title"].includes(k)) showFrame(FRAME.i);
});
shEl().addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.id === "shAdd") { ALBUM.sheets.push(newSheet()); window.markDirty?.(); renderSheets(); previewSheet(ALBUM.sheets.length - 1); }
  if (b.id === "shPdf") albumPdf();
  if (b.id === "shSec1") buildSection();
  if (b.dataset.shprev) previewSheet(+b.dataset.shprev);
  if (b.dataset.shframe) { const i = +b.dataset.shframe; showFrame(FRAME?.i === i ? null : i); renderSheets(); }
  if (b.dataset.shreset) { const i = +b.dataset.shreset; delete ALBUM.sheets[i].center; window.markDirty?.(); if (FRAME?.i === i) showFrame(i); renderSheets(); }
  if (b.dataset.shup || b.dataset.shdel) showFrame(null);
  if (b.dataset.shup) { const i = +b.dataset.shup; if (i > 0) { [ALBUM.sheets[i - 1], ALBUM.sheets[i]] = [ALBUM.sheets[i], ALBUM.sheets[i - 1]]; window.markDirty?.(); renderSheets(); } }
  if (b.dataset.shdel) { const i = +b.dataset.shdel; if (confirmInline(b, `Удалить лист «${ALBUM.sheets[i].title}»?`)) { ALBUM.sheets.splice(i, 1); window.markDirty?.(); renderSheets(); } }
});
/* Рамка листа на карте (как видовой экран листа в AutoCAD): размер = карта листа × масштаб, тянется мышью.
   Сдвиг запоминается в листе (center), без сдвига лист стоит по центру территории. */
let FRAME = null;
function frameGeom(sh) {
  const [fw, fh] = FRAME_MM[sh.size], scale = sheetScale(sh), c = sheetCenter(sh), c3 = ol.proj.fromLonLat(c), k = 1 / Math.cos(c[1] * Math.PI / 180);
  const hx = fw / 2 / 1000 * scale * k, hy = fh / 2 / 1000 * scale * k;
  return new ol.geom.Polygon([[[c3[0] - hx, c3[1] - hy], [c3[0] + hx, c3[1] - hy], [c3[0] + hx, c3[1] + hy], [c3[0] - hx, c3[1] + hy], [c3[0] - hx, c3[1] - hy]]]);
}
function showFrame(i) {
  if (FRAME) { mMain.removeLayer(FRAME.layer); mMain.removeInteraction(FRAME.tr); FRAME = null; }
  if (i == null || !ALBUM.sheets[i] || ["tep", "title"].includes(ALBUM.sheets[i].kind)) return;
  const sh = ALBUM.sheets[i], f = new ol.Feature(frameGeom(sh)), scale = sheetScale(sh);
  const layer = new ol.layer.Vector({ source: new ol.source.Vector({ features: [f] }), zIndex: 10000, style: new ol.style.Style({
    stroke: new ol.style.Stroke({ color: "#1a5fb4", width: 2.5 }), fill: new ol.style.Fill({ color: "rgba(26,95,180,.07)" }),
    text: new ol.style.Text({ text: `Лист ${i + 1} «${sh.title}», ${sh.size}, 1:${fmt(scale)}\nтяните рамку, чтобы сдвинуть`, font: "600 12px system-ui, sans-serif", fill: new ol.style.Fill({ color: "#1a5fb4" }),
      stroke: new ol.style.Stroke({ color: "#fff", width: 3 }), overflow: true }) }) });
  const tr = new ol.interaction.Translate({ layers: [layer] });
  tr.on("translateend", () => { sh.center = ol.proj.toLonLat(ol.extent.getCenter(f.getGeometry().getExtent())); window.markDirty?.(); renderSheets(); });
  mMain.addLayer(layer); mMain.addInteraction(tr); FRAME = { i, layer, tr };
  // рамку — в ту часть карты, которую не закрывает окно «Листы» (обычно оно полосой внизу)
  const m = mMain.getTargetElement().getBoundingClientRect(), w = $("wSheets").getBoundingClientRect(), pad = [24, 24, 24, 24];
  if (w.top > m.top + m.height * .3) pad[2] = Math.max(24, m.bottom - w.top + 16); else if (w.bottom < m.bottom - m.height * .3) pad[0] = Math.max(24, w.bottom - m.top + 16);
  mMain.getView().fit(f.getGeometry().getExtent(), { padding: pad, duration: 250 });
}
// окно «Листы» закрыто — рамка с карты уходит
new MutationObserver(() => { if ($("wSheets").hidden && FRAME) showFrame(null); }).observe($("wSheets"), { attributes: true, attributeFilter: ["hidden"] });
window.renderSheets = renderSheets; window.hideSheetFrame = () => showFrame(null);
