/* ГРАДО 2 · листы и альбом (этап Э6). Лист = вид карты (или текущая карта) в рамке А3/А1 с масштабом, легендой вида,
   таблицей ТЭП, стрелкой севера, масштабной линейкой и основной надписью по ГОСТ Р 21.101. Оформление объектов
   считает тот же код, что рисует слои на экране (symbolOf), поэтому лист не расходится с картой; в PDF его
   собирает рендер ядра (print_io.py): МСК, типы линий REDLN97, штриховки. Состав альбома хранится в проекте. */
const ALBUM = { meta: { object: "", code: "", stage: "ПП", org: "" }, sheets: [] };
const SCALES = [500, 1000, 2000, 2500, 3000, 4000, 5000, 7500, 10000, 15000, 20000, 25000, 50000, 100000, 200000, 500000, 1000000];
const FRAME_MM = { A3: [275, 224], A1: [636, 521] };   // размер карты на листе по ГОСТ (как layout() в print_io.py)
// слайды: 16:9 и альбомные А4, А3, А2 с одинаковым оформлением (SLIDES в print_io.py)
const SLIDE = { P: [338.67, 190.5], PA4: [297, 210], PA3: [420, 297], PA2: [594, 420] };
// лист без штампа (инструмент «Лист» на карте): карта на весь лист с полями 2 %, ориентация — sheet.orient ("P" книжная)
const PAPER = { BA4: [297, 210], BA3: [420, 297], BA2: [594, 420], BA1: [841, 594], BA0: [1189, 841] };
const SIZE_T = { BA4: "А4 без штампа", BA3: "А3 без штампа", BA2: "А2 без штампа", BA1: "А1 без штампа", BA0: "А0 без штампа",
  A3: "A3 (ГОСТ)", A1: "A1 (ГОСТ)", P: "слайд 16:9", PA4: "слайд А4", PA3: "слайд А3", PA2: "слайд А2" };
const isPaper = size => size in PAPER;
const paperMM = sheet => { const [a, b] = PAPER[sheet.size] || PAPER.BA3; return sheet.orient === "P" ? [b, a] : [a, b]; };
const isSlide = size => size in SLIDE;
// рамка карты в мм: как layout(), panel_rects() и photo_map_rect() в print_io.py
function frameMM(sheet) {
  if (sheet.rect) return [sheet.rect[2], sheet.rect[3]];                      // карта альбома по шаблону: своя рамка в мм листа
  if (isPaper(sheet.size)) return paperMM(sheet).map(v => v * .96);          // как PAPER_MARGIN в print_io.py
  if (!isSlide(sheet.size)) return FRAME_MM[sheet.size] || FRAME_MM.A3;
  const [w, h] = SLIDE[sheet.size], k = w / SLIDE.P[0], col = w < 500 ? 80 : 110, mw = w - 14 * k - col - 6, mh = h - 34 * k;
  if (sheet.part === "half") return [(mw - 6) / 2, mh - 11];
  if (sheet.kind === "photos" || sheet.part === "photo") return [mw * .47, mh];
  return [mw, mh];
}
const newSheet = () => ({ id: "s" + Date.now().toString(36) + Math.random().toString(36).slice(2, 4), title: VIEWS.find(v => v.id === VIEW_CUR)?.name || "Существующее положение", size: "A3", view: VIEW_CUR || "", scale: 0, legend: true, tep: false });

function autoScale(frame, bb, exact = false) {
  if (!TERR && !bb) return 2000;
  const [w, s, e, n] = bb || turf.bbox(TERR), mx = (e - w) * 111320 * Math.cos((s + n) / 2 * Math.PI / 180), my = (n - s) * 110540, [fw, fh] = frame;
  const need = Math.max(mx / fw, my / fh) * 1000 * 1.08;
  if (exact) return Math.ceil(need / 1000) * 1000;           // схема (Москва, округ): заполняет рамку, стандартный масштаб не нужен
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
const sheetScale = sheet => sheet.scale || autoScale(frameMM(sheet), sheet.fit ? fitBox(sheet) : null, !!sheet.adm);
// показатели ТЭП строками таблицы; на листе с картой — первые 30, на листе «Таблица ТЭП» — все
function tepRows(all) {
  const t = RESULT.tepNode?._tep; if (!t) return [];
  const ms = t.metrics.filter(m => m.value);
  return [["Территория", fmt(t.terr, 2) + " га"], ["СПП новая", fmt(t.sppNew / 1000, 1) + " тыс. м²"], ["СПП сохраняемая", fmt(t.sppKept / 1000, 1) + " тыс. м²"], ["Плотность", fmt(t.density, 1) + " тыс. м²/га"], ["Застроенность", fmt(t.cover * 100, 1) + " %"]]
    .concat((all ? ms : ms.slice(0, 30)).map(m => [m.title, fmt(m.value, m.precision ?? 3) + " " + m.unit]));
}
function sheetSpec(sheet) {
  if (sheet.adm) return admPanelSpec(sheet);                               // схемы административного деления альбомов (albums.js)
  if (sheet.kind === "tep") return { title: sheet.title, size: sheet.size, kind: "tep", tep: tepRows(true) };
  if (sheet.kind === "title") return { title: sheet.title, size: sheet.size, kind: "title", ...albumExtra(sheet) };
  // две карты на слайде: у каждой свои слои, рамка и масштаб; легенда общая
  if (sheet.panels) {
    const subs = sheet.panels.map(p => sheetSpec({ ...p, size: sheet.size, part: "half", legend: sheet.legend })), legend = [];
    subs.forEach(x => x.legend.forEach(g => { if (!legend.some(y => y.title === g.title)) legend.push(g); }));
    const c = TERR && turf.centroid(TERR), okr = (DATA["gisogd.admin"]?.fc.features || []).find(x => x.properties["Уровень"] === "округ" && safe(() => turf.booleanPointInPolygon(c, x)));
    const on = okr ? LABEL_FN.adm({ get: k => okr.properties[k] }) : "административного округа";
    return { title: sheet.title, size: sheet.size, panels: subs.map((x, j) => ({ ...x, caption: (sheet.panels[j].caption || "").replace("{okr}", on) })), legend, note: sheet.note || "", ...albumExtra(sheet) };
  }
  if (sheet.kind === "photos") {
    const out = sheetSpec({ ...sheet, kind: "map", part: "photo" }), pts = (sheet.photos || []).map((ph, i) => ph.at ? { g: { type: "Point", coordinates: ph.at }, fill: "#2e8b3a", stroke: "#ffffff", w: 5, a: 1, label: String(i + 1) } : null).filter(Boolean);
    out.layers.push({ title: "Точки съёмки", features: pts });
    if (pts.length) out.legend.push({ title: "Точки съёмки", kind: "point", items: [{ label: "Точка съёмки и номер снимка", fill: "#2e8b3a" }] });
    return { ...out, kind: "photos", photos: (sheet.photos || []).map(ph => ({ data: ph.data, w: ph.w, h: ph.h })) };
  }
  const size = sheet.size, scale = sheetScale(sheet), [fw, fh] = frameMM(sheet);
  const center = sheetCenter(sheet);
  const half = [fw / 2 / 1000 * scale * 1.15, fh / 2 / 1000 * scale * 1.15], c3 = ol.proj.fromLonLat(center), stretch = 1 / Math.cos(center[1] * Math.PI / 180);
  const ext = [c3[0] - half[0] * stretch, c3[1] - half[1] * stretch, c3[0] + half[0] * stretch, c3[1] + half[1] * stretch];
  const tc = TERR ? turf.centroid(TERR) : null;
  const homeOkr = sheet.homeOkrug ? (h => h.okrug?.properties["Округ"] || h.okrug?.properties["Наименование"])(homeAdm()) : null;
  const vl = viewLayers(sheet).filter(pl => !(pl.style.maxDen && scale > pl.style.maxDen)), layers = [], legend = [];   // видимость по масштабу — и на листе, как в QGIS
  vl.slice().reverse().forEach(pl => {                                   // снизу вверх, как рисует карта
    const st = pl.style, feats = [];
    layerSrc[pl.key]?.forEachFeatureInExtent(ext, f => {
      const g = GJ.writeFeatureObject(f).geometry; if (!g) return;
      const only = sheet.only?.[pl.key]; if (only && !only.values.includes(f.get(only.field))) return;
      if (homeOkr && pl.key === "gisogd.admin" && f.get("Уровень") === "район" && f.get("Округ") !== homeOkr) return;   // «Районы …» — только своего округа
      const lab = sheet.labelFn?.[pl.key] ? LABEL_FN[sheet.labelFn[pl.key]](f) : st.label ? f.get(st.label) : null;
      // подсветка: округ и район, в которых лежит территория
      const hl = sheet.hilite?.[pl.key] && tc && /Polygon/.test(g.type) && safe(() => turf.booleanPointInPolygon(tc, g)) ? sheet.hilite[pl.key] : null;
      if (st.mode === "lgr") { const lt = f.get("_lt") || [], miss = f.get("_miss") || []; feats.push({ g, lt, miss, lc: LGRC[ltCode(lt[0] || "")] || LGRC[miss[0]?.[0]] || "#d7191c", w: st.width, label: lab }); return; }
      const s = symbolOf(pl, f); if (s.hide) return;
      // как на карте: контур при штриховке — цветом штриховки, если у слоя нет своего цвета контура (Эталон ЛГР);
      // штрих контура и шаг штриховки — в пикселях карты; подписи надписей ГИС ОГД — своим цветом, под своим углом, без значка
      feats.push({ g, fill: hl || s.fill, stroke: pl.geom === "poly" ? (s.hatch && !st.strokeOwn ? s.fill : st.stroke) : s.fill, w: st.width, a: hl ? 1 : st.opacity * pl.a, hatch: s.hatch, hp: st.hatchPat || "45",
        hs: st.hatchStep, dash: st.dash?.length ? st.dash : undefined, nm: st.marker === false || undefined, lcol: st.labelColor, la: st.labelAngle ? upright(labelDeg(f)) : undefined,
        label: lab == null || lab === "" ? null : String(lab), ls: sheet.labelMM?.[pl.key], lc: pl.geom === "line" ? s.fill : undefined });
    });
    layers.push({ title: pl.title, features: feats });
  });
  if (sheet.legend) vl.forEach(pl => {
    const st = pl.style, items = st.mode === "lgr" ? [{ label: "красные линии и ЛГР (REDLN97)", fill: "#d7191c" }] : legendItems(pl).filter(it => !it.off).slice(0, 14).map(it => ({ label: it.v, fill: it.c, stroke: pl.geom === "poly" ? st.stroke : it.c, hatch: st.hatch, a: st.opacity }));
    legend.push({ title: pl.title, kind: pl.geom, items: items.length ? items : [{ label: pl.title, fill: st.fill, stroke: st.stroke, hatch: st.hatch, a: st.opacity }] });
  });
  const tep = sheet.tep ? tepRows(false) : [];
  const out = { title: sheet.title, size, orient: sheet.orient || "L", scale, center, layers, legend, tep, territory: TERR?.geometry || null, basemap: sheet.basemap || "",
    ...(sheet.rect ? { rect: sheet.rect } : {}), ...albumExtra(sheet) };
  if (isSlide(size)) out.terrStyle = ["okrug", "moscow"].includes(sheet.fit) ? { stroke: "#e0158c", width: .9, fill: "#e0158c" } : { stroke: "#e0158c", width: .9 };
  if (sheet.extra === "parcels") Object.assign(out, parcelsSheet(layers));
  if (sheet.extra === "radii") radiiSheet(out);
  if (sheet.extra === "genplan") genplanTable(out);
  if (sheet.note) out.note = sheet.note;
  // выноска на карте района: «проектируемая территория» и район, где она лежит
  if (sheet.callout && tc) { const d = (DATA["gisogd.admin"]?.fc.features || []).find(x => x.properties["Уровень"] === "район" && safe(() => turf.booleanPointInPolygon(tc, x)));
    out.callout = ["проектируемая территория"].concat(d ? ["район " + LABEL_FN.adm({ get: k => d.properties[k] })] : []); }
  if (isSlide(size) && sheet.legend) out.legend.unshift({ title: "Границы", kind: "line", items: [{ label: `Граница разработки проекта планировки (S\u00a0=\u00a0${fmt(m2(TERR) / 1e4, 2)}\u00a0га)`, fill: "#e0158c" }] });   // площадь — до сотых гектара
  return out;
}
const albumSpec = list => ({ meta: { ...ALBUM.meta, short: ALBUM.meta.short || "", place: ALBUM.meta.place || placeText(), date: ALBUM.meta.date || monthYear() }, sheets: list.map(sheetSpec) });
const monthYear = () => { const d = new Date(); return ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"][d.getMonth()] + " " + d.getFullYear(); };
const OKR = { "Центральный": "ЦАО", "Северный": "САО", "Северо-Восточный": "СВАО", "Восточный": "ВАО", "Юго-Восточный": "ЮВАО", "Южный": "ЮАО", "Юго-Западный": "ЮЗАО",
  "Западный": "ЗАО", "Северо-Западный": "СЗАО", "Зеленоградский": "ЗелАО", "Новомосковский": "НАО", "Троицкий": "ТАО" };
const placeText = () => { const tp = RESULT.tepNode ? tepParams(RESULT.tepNode) : {}, o = String(tp.okrug || "").replace(/\s*административный округ/i, "").trim();
  return [OKR[o] || o, tp.district ? "район " + tp.district.replace(/^район\s+/i, "") : ""].filter(Boolean).join(", "); };
// подписи листов, собранные из нескольких полей: подзона ПЗЗ — «плотность / высота / застроенность», Ф — по факту
const codes = t => [...new Set(String(t || "").match(/\d{1,2}(\.\d{1,2}){1,3}/g) || [])];
const wrapLab = (parts, n) => parts.reduce((ls, p) => { const l = ls[ls.length - 1]; if (l && (l + ", " + p).length <= n) ls[ls.length - 1] = l + ", " + p; else ls.push(p); return ls; }, []).join("\n");
// Генплан: номер и индекс зоны. Старая Москва — n и fztip; ТиНАО — number_fz (ОО РР ННН: округ, район, номер зоны —
// на схеме подписывается номер в районе) и fz_type (тип зоны); фонд ТиНАО — интервал interval_fo, тыс. м²
const gpNum = p => p.n != null && p.n !== "" ? String(+p.n || p.n) : p.number_fz ? String(+String(p.number_fz).slice(-3) || p.number_fz) : "";
const gpIdx = p => p.fztip || (p.fz_type != null && p.fz_type !== "" ? String(p.fz_type) : "");
const gpFund = p => p.summfondpersp ? String(p.summfondpersp).replace(".", ",") : p.interval_fo && p.interval_fo !== "*" ? String(p.interval_fo).replace(/\s*-\s*/, "–") : "—";
const LABEL_FN = {
  // ПЗЗ, территориальные зоны: коды ВРИ, как на схеме 120-ПП (полные названия — в карточке объекта)
  vri: f => { const c = codes(f.get("ВРИ (коды)") || f.get("ВРИ")); return c.length ? wrapLab(c.length > 24 ? c.slice(0, 23).concat("…") : c, 26) : null; },
  // Генплан: номер функциональной зоны над индексом
  gp: f => { const n = gpNum(f.getProperties()), t = gpIdx(f.getProperties()); return n || t ? [n, t].filter(Boolean).join("\n") : null; },
  // административное деление: округ — сокращением (СВАО), район — названием
  adm: f => f.get("Уровень") === "округ" ? OKR[String(f.get("Наименование") || "").replace(/\s*административный округ/i, "").trim()] || f.get("Наименование") : String(f.get("Наименование") || "").replace(/^район\s+/i, ""),
  pzz: f => { const p = f.get("Плотность, тыс. м²/га"), h = f.get("Высота, м"), z = f.get("Застроенность, %");
  if (/не предусмотрено/.test(f.get("Регламент") || "")) return "0 / 0 / 0"; const v = x => x == null || x === "" ? "Ф" : String(x).replace(".", ",");
  return [p, h, z].every(x => x == null || x === "") ? "Ф" : `${v(p)} / ${v(h)} / ${v(z)}`; } };
// рамка содержания листа: территория с полями, район или округ территории (из слоя административного деления ОГД)
function fitBox(sheet) {
  if (!TERR) return null;
  const c = turf.centroid(TERR).geometry.coordinates, adm = DATA["gisogd.admin"]?.fc.features || [];
  if (sheet.fit === "moscow") { const o = adm.filter(x => x.properties["Уровень"] === "округ"); return o.length ? turf.bbox(turf.featureCollection(o)) : turf.bbox(buf(TERR, 20000)); }
  if (sheet.fit === "district" || sheet.fit === "okrug") {
    const lvl = sheet.fit === "district" ? "район" : "округ", f = adm.find(x => x.properties["Уровень"] === lvl && safe(() => turf.booleanPointInPolygon(c, x)));
    if (f) return turf.bbox(f);
    return turf.bbox(buf(TERR, sheet.fit === "district" ? 800 : 4000));
  }
  if (sheet.pad) return turf.bbox(buf(TERR, sheet.pad));
  const [w, s, e, n] = turf.bbox(TERR), k = (sheet.ctx || 1.4) / 2, cx = (w + e) / 2, cy = (s + n) / 2;
  return [cx - (e - w) * k, cy - (n - s) * k, cx + (e - w) * k, cy + (n - s) * k];
}
// вид права в таблице — привычными сокращениями, чтобы влезал в столбец без обрезки
const shortRight = t => String(t).length <= 20 ? String(t) : String(t).replace(/Российской Федерации/gi, "РФ").replace(/собственность/gi, "собств.").replace(/Государственная/g, "Гос.")
  .replace(/муниципальная/gi, "муницип.").replace(/\s+/g, " ").trim();
// землепользование: участки ЕГРН, задевающие территорию, пронумерованы по убыванию площади; таблица — справа
function parcelsSheet(layers) {
  const pl = (DATA["nspd.parcels"]?.fc.features || []).filter(f => { if (!/Polygon/.test(f.geometry?.type)) return false; const x = safe(() => inter(f, TERR)); return !!x && m2(x) > Math.min(50, m2(f) * .05); });
  pl.sort((a, b) => m2(b) - m2(a));
  const no = new Map(pl.map((f, i) => [f.properties["Кадастровый номер"] || i, i + 1]));
  layers.push({ title: "Номера участков", features: pl.map((f, i) => ({ g: turf.pointOnFeature(f).geometry, fill: "#ffffff", stroke: "#2b3cc4", w: 0, a: 0, label: String(i + 1) })) });
  return { table: { title: "Земельные участки в границах проекта", cols: [["№", .06, "left"], ["Кадастровый номер", .41, "left"], ["Площадь, м²", .22, "right"], ["Вид права", .31, "left"]],
    rows: pl.map((f, i) => [String(i + 1), String(f.properties["Кадастровый номер"] || "—"), fmt(+f.properties["Площадь участка, м²"] || Math.round(m2(f))), shortRight(f.properties["Вид права"] || f.properties["Форма собственности"] || "—")]) } };   // длинное печать ещё и ужмёт
}
const cut = (t, n) => { t = String(t); return t.length > n ? t.slice(0, n - 1) + "…" : t; };
// Генплан: функциональные зоны на территории — номер, индекс, наименование, суммарный поэтажный фонд
function genplanTable(out) {
  const z = ["gisogd.func_zones", "gisogd.func_zones_tinao"].flatMap(k => DATA[k]?.fc.features || []).filter(f => /Polygon/.test(f.geometry?.type) && safe(() => { const x = inter(f, TERR); return x && m2(x) > 20; }));
  if (!z.length) return;
  out.table = { title: "Функциональные зоны на территории", cols: [["№", .1, "left"], ["Индекс", .17, "left"], ["Наименование", .5, "left"], ["тыс. м²", .23, "right"]],
    rows: z.map(f => { const p = f.properties; return [gpNum(p) || "—", gpIdx(p) || "—", p.naimfunkzony || p["Вид зоны"] || p.name || "—", gpFund(p)]; }) };
}
// социальная инфраструктура: объекты OSM и их радиусы обслуживания по нормам Москвы (2151-ПП) и СП 42.13330
function radiiSheet(out) {
  const ok = RESULT.tepNode ? tepParams(RESULT.tepNode).okrug : "", cao = /Централ/i.test(ok || "");
  const R = { "детский сад": cao ? 500 : 300, "школа": cao ? null : 1000, "поликлиника": 1000 }, col = { "детский сад": "#e0a100", "школа": "#1f5fbf", "поликлиника": "#2e8b3a" };
  const feats = [];
  (DATA["osm.social"]?.fc.features || []).filter(f => f.geometry?.type === "Point" && R[f.properties["Вид"]]).forEach(f => {
    const c = safe(() => turf.circle(f.geometry.coordinates, R[f.properties["Вид"]] / 1000, { steps: 64 }));
    if (c) feats.push({ g: c.geometry, fill: col[f.properties["Вид"]], stroke: col[f.properties["Вид"]], w: 1, a: .06, hatch: false, label: null }); });
  if (!feats.length) {                    // пустые обозначения радиусов вводили бы в заблуждение: говорим прямо
    out.note = [out.note, "В OpenStreetMap в пределах листа нет школ, детских садов и поликлиник. Добавьте их точками в слой «Школы, детсады, поликлиники (OSM)» (поле «Вид»: школа, детский сад, поликлиника) — радиусы построятся сами."].filter(Boolean).join(" ");
    return;
  }
  out.layers.unshift({ title: "Радиусы обслуживания", features: feats });
  out.legend.push({ title: "Радиусы обслуживания", kind: "poly", items: Object.entries(R).filter(([, r]) => r).map(([k, r]) => ({ label: `${k} — ${r} м`, fill: col[k], stroke: col[k], a: .15 })) });
}

/* Раздел 1 «Существующее положение» — слайды 16:9 по составу альбома ППТ: каждый лист знает свои слои, подложку,
   оформление и рамку содержания; «Собрать раздел» выгружает недостающие слои на всю площадь рамок и строит листы. */
const ROADS_WHITE = { "calc.uds_osm": { mode: "single", fill: "#ffffff", stroke: "#a3a3a3", width: 0, opacity: 1 } };   // на цветных зонах
/* УДС полигонами. Холст — «УДС (Яндекс)»: проезжая часть HD, а где её нет (hd_covered = 0) — проезды по осям Яндекса с
   шириной по классу дороги. Листы — «УДС (OSM)»: оси OSM с шириной по типу дороги: Яндекс — пользовательская карта,
   в сдаваемые материалы её данные не включаются (yandex_vmap.py). Ширины — типовые полосы движения, не обмер. */
const UDS_YA_W = { 4: 14, 5: 12, 6: 10, 7: 7, 8: 6 };                       // класс дороги Яндекса (fc) → ширина, м
const UDS_OSM_W = { motorway: 24, trunk: 20, primary: 16, secondary: 14, tertiary: 12, unclassified: 7, residential: 8, living_street: 6, service: 5,
  motorway_link: 8, trunk_link: 8, primary_link: 7, secondary_link: 7, tertiary_link: 7 };
const DERIVED = { "calc.uds_osm": ["osm.roads"], "calc.uds_ya": ["yandex.hd_roads", "yandex.roads"] };
function udsLayer(key, title, polys, axes, widthOf, src) {
  const out = polys.filter(f => /Polygon/.test(f.geometry?.type)).map(f => ({ type: "Feature", geometry: f.geometry, properties: { "Вид": "проезжая часть", "Источник": src } }));
  axes.forEach(f => { const w = /LineString/.test(f.geometry?.type) && widthOf(f.properties || {}); if (!w) return;
    const b = safe(() => turf.buffer(f, w / 2000, { units: "kilometers", steps: 2 }));
    if (b?.geometry) out.push({ type: "Feature", geometry: b.geometry, properties: { "Вид": "по оси", "Ширина, м": w, "Источник": src } }); });
  if (!out.length) return;
  const fc = { type: "FeatureCollection", features: out };
  DATA[key] = { title, fc, count: out.length, fields: ["Вид", "Ширина, м", "Источник"], original: fc };
  layerSrc[key] ||= new ol.source.Vector(); setLayerData(key, fc); restyle(ensureLayer(key, title));
}
function buildUds() {
  if (DATA["yandex.hd_roads"] || DATA["yandex.roads"])
    udsLayer("calc.uds_ya", "УДС: проезжая часть и проезды (Яндекс)", DATA["yandex.hd_roads"]?.fc.features || [], DATA["yandex.roads"]?.fc.features || [],
      p => String(p.hd_covered) === "0" ? UDS_YA_W[+p.fc] : 0, "Яндекс Карты");
  if (DATA["osm.roads"]) udsLayer("calc.uds_osm", "УДС по осям (OSM)", [], DATA["osm.roads"].fc.features, p => UDS_OSM_W[p["Тип дороги"]], "OpenStreetMap");
}

const SEC1 = [
  { kind: "title", title: "Подготовка проекта планировки территории" },
  { title: "Месторасположение рассматриваемой территории", panels: [
    { keys: ["gisogd.admin"], fit: "moscow", caption: "Административные округа города Москвы", only: { "gisogd.admin": { field: "Уровень", values: ["округ"] } }, hilite: { "gisogd.admin": "#f6b3d6" }, labelFn: { "gisogd.admin": "adm" } },
    { keys: ["gisogd.admin"], fit: "okrug", caption: "Районы {okr}", callout: true, only: { "gisogd.admin": { field: "Уровень", values: ["район"] } }, homeOkrug: true, hilite: { "gisogd.admin": "#f6b3d6" }, labelFn: { "gisogd.admin": "adm" } }] },
  { title: "Ортофотоплан", basemap: "sat", keys: ["gisogd.admin"], fit: "district", styles: { "gisogd.admin": { stroke: "#ffffff", labelSize: 13 } }, labelFn: { "gisogd.admin": "adm" } },
  { title: "Ортофотоплан", basemap: "sat", keys: ["osm.roads"], fit: "terr", ctx: 3, styles: { "osm.roads": { mode: "single", fill: "#f5d58a", width: 1.4, label: "Название", labelSize: 11 } }, labelMM: { "osm.roads": 2.8 },
    only: { "osm.roads": { field: "Тип дороги", values: ["motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "living_street", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"] } } },
  { title: "Существующее состояние и использование территории с имеющимися ограничениями",
    // зоны ограничений — внизу бледной заливкой с контуром (альфы в PDF нет: сверху они закрыли бы здания), ОКН штриховкой
    // и красные линии — поверх
    // УДС — полигоны по осям OSM (белые с серой кромкой, поверх зон); застройка — одна, из ЕГКО
    keys: ["nspd.zouit", "gisogd.zouit", "gisogd.szz", "gisogd.vodookhr", "egko.green", "egko.water", "calc.uds_osm", "nspd.parcels", "egko.buildings", "gisogd.okn", "gisogd.red_lines"], fit: "terr", ctx: 1.6,
    styles: { "nspd.zouit": { hatch: false, opacity: .14, width: 1 }, "gisogd.szz": { hatch: false, opacity: .14, width: 1 }, "gisogd.vodookhr": { hatch: false, opacity: .14, width: 1 }, "gisogd.zouit": { hatch: false, opacity: .14, width: 1 }, ...ROADS_WHITE } },
  { title: "Существующее использование территории с характеристикой по землепользованию", basemap: "sat", keys: ["nspd.parcels"], fit: "terr", ctx: 1.5, extra: "parcels",
    styles: { "nspd.parcels": { mode: "single", opacity: 0, stroke: "#2b3cc4", width: 1.6, label: "" } } },
  // фотофиксация: снимки добавляет пользователь, точки съёмки берутся из GPS снимка
  { kind: "photos", title: "Материалы фотофиксации", keys: ["calc.uds_osm", "egko.buildings", "osm.roads"], fit: "terr", ctx: 1.8,
    styles: { "osm.roads": { mode: "single", fill: "#d4d4d4", width: .3, label: "Название", labelSize: 9 } },
    only: { "osm.roads": { field: "Тип дороги", values: ["motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "living_street"] } } },
  { title: "Фрагменты схем Генерального плана города Москвы", keys: ["gisogd.func_zones", "gisogd.func_zones_tinao"], fit: "terr", ctx: 1.6, extra: "genplan",
    labelFn: { "gisogd.func_zones": "gp", "gisogd.func_zones_tinao": "gp" }, labelMM: { "gisogd.func_zones": 3.6, "gisogd.func_zones_tinao": 3.6 } },
  { title: "Фрагменты схем правил землепользования и застройки города Москвы", panels: [
    { keys: ["gisogd.pzz_zones"], fit: "terr", ctx: 1.5, labelFn: { "gisogd.pzz_zones": "vri" }, styles: { "gisogd.pzz_zones": { labelSize: 9 } },
      caption: "Границы территориальных зон и виды разрешённого использования земельных участков и объектов капитального строительства" },
    { keys: ["gisogd.pzz_sub"], fit: "terr", ctx: 1.5, labelFn: { "gisogd.pzz_sub": "pzz" }, styles: { "gisogd.pzz_sub": { mode: "single", fill: "#ffffff", opacity: 0, stroke: "#8a5a2b", width: 1 } },
      caption: "Границы подзон территориальных зон и параметры разрешённого использования земельных участков и объектов капитального строительства" }],
    note: "Подписи зон — коды видов разрешённого использования. Подписи подзон: плотность, тыс. м²/га / высота, м / застроенность, %; Ф — по фактическому использованию" },
  { title: "Схема об утверждённой и разрабатываемой документации", keys: ["calc.uds_osm", "egko.buildings", "gisogd.gpzu", "gisogd.krt", "gisogd.ppt"], fit: "terr", ctx: 2 },
  { title: "Объекты социальной инфраструктуры и радиусы обслуживания", keys: ["egko.buildings", "osm.social"], fit: "terr", pad: 700, extra: "radii" },
];
/* Собрать набор листов по образцу (tpl): раздел 1 на слайдах 16:9 (SEC1) или альбомы по образцам владельца
   (albums.js): листы получают префикс id (prefix), старые листы того же набора заменяются. */
async function buildSection(tpl = SEC1, prefix = "sec1_", size = ALBUM.meta.slide || "P", name = "Раздел «Существующее положение»") {
  if (!TERR) return toast("Сначала задайте границу территории — от неё строятся рамки листов.");
  const before = new Set(LYR.map(l => l.key));
  const sheets = tpl.map((t, i) => ({ id: prefix + i, size, legend: t.kind !== "title", tep: false, scale: 0, view: "", ...JSON.parse(JSON.stringify(t)) }));
  // административное деление — для рамок «округ» и «район» его нужно получить первым; выгрузка до v0.65 знала районы
  // только своего округа — берётся заново: схема Москвы рисует все районы (их в Москве 137). Область выгрузки — вся
  // Москва: слой всегда городской, а перевыгрузка по малой рамке обновила бы только ближние районы
  const adm = DATA["gisogd.admin"]?.fc.features || [];
  if (adm.filter(f => f.properties["Уровень"] === "район").length < 100) {
    toast("Административное деление Москвы (ГИС ОГД)…"); await loadKeys(["gisogd.admin"], [36.8, 55.1, 38.0, 56.1]); }
  // остальные слои — по самой большой рамке листа, где слой нужен; одинаковые рамки — одной выгрузкой
  const need = new Map();
  sheets.flatMap(s => s.panels ? s.panels.map(p => ({ ...p, size: s.size, part: "half" })) : [s]).filter(s => s.keys).forEach(s => { const bb = frameBox(s); s.keys.flatMap(k => DERIVED[k] || [k]).filter(k => k !== "gisogd.admin" && SOURCES[k] && !k.startsWith("yandex.")).forEach(k => {
    const cur = need.get(k); need.set(k, cur ? [Math.min(cur[0], bb[0]), Math.min(cur[1], bb[1]), Math.max(cur[2], bb[2]), Math.max(cur[3], bb[3])] : bb); }); });
  // холст: УДС Яндекса — вокруг территории (для анализа; на листы не идёт)
  ["yandex.hd_roads", "yandex.roads"].forEach(k => need.set(k, turf.bbox(buf(TERR, 400))));
  // Яндекс — не больше 40 км² (первая выгрузка около минуты на 1 км²): рамку сжимаем к территории. НСПД большую
  // область сервер берёт по частям и склеивает
  const LIM = { yandex: 40 };
  need.forEach((bb, k) => { const lim = LIM[k.split(".")[0]]; if (!lim) return;
    const [w, s, e, n] = bb, c = turf.centroid(TERR).geometry.coordinates, kx = 111.32 * Math.cos(c[1] * Math.PI / 180), ky = 110.54, a = (e - w) * kx * (n - s) * ky;
    if (a <= lim * .97) return; const f = Math.sqrt(lim * .97 / a), hx = (e - w) * f / 2, hy = (n - s) * f / 2;
    need.set(k, [c[0] - hx, c[1] - hy, c[0] + hx, c[1] + hy]); });
  const groups = new Map(); need.forEach((bb, k) => { const g = bb.map(v => v.toFixed(5)).join(","); (groups.get(g) || groups.set(g, { bb, keys: [] }).get(g)).keys.push(k); });
  // ошибки каждой выгрузки (loadKeys начинает с чистого списка) копятся здесь; упавший слой повторяется один раз
  const failed = new Map();
  for (const { bb, keys } of groups.values()) {
    keys.forEach(k => CHECKED.add(k)); await loadKeys(keys, bb);
    keys.filter(k => ERRORS[k]).forEach(k => failed.set(k, { bb, why: ERRORS[k] }));
  }
  for (const [k, { bb }] of [...failed]) { await loadKeys([k], bb); if (!ERRORS[k]) failed.delete(k); else failed.get(k).why = ERRORS[k]; }
  const lost = [...failed].map(([k, x]) => `«${SOURCES[k]?.title || k}» (${x.why})`);
  buildUds();
  // пересборка раздела не теряет добавленные снимки
  const old = new Map(ALBUM.sheets.filter(s => s.photos).map(s => [s.kind + s.title, s.photos]));
  sheets.forEach(s => { if (s.kind === "photos") s.photos = old.get(s.kind + s.title) || []; });
  ALBUM.sheets = ALBUM.sheets.filter(s => !String(s.id).startsWith(prefix)).concat(sheets);
  // холст — опорный план: тематические слои раздела (зоны, ПЗЗ, Генплан, документация, соцобъекты) выключены — они
  // нужны листам, а не холсту; включить любой можно в дереве. Застройка одна, порядок как на плане
  const used = sheets.flatMap(s => s.panels ? s.panels.flatMap(p => p.keys || []) : s.keys || []);
  tidyLayers(new Set(LYR.map(l => l.key).filter(k => !before.has(k) || used.includes(k) || need.has(k))));
  window.markDirty?.(); renderSheets(); toast(`${lost.length ? `Не загрузились после повтора: ${lost.join("; ")} — слайды с ними неполные, повторите сборку позже. ` : ""}${name}: ${sheets.length} листов, формат «${SIZE_T[size] || size}». Холст приведён к опорному плану: тематические слои раздела выключены (включаются в дереве). «PDF альбома» — выгрузка; рамку любого листа можно сдвинуть.`);
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
  window.redrawFrames?.(true);             // рамки листов на карте и область загрузки данных
  const el = $("sheetsBody"); if (!el) return;
  const m = ALBUM.meta, inp = (k, ph) => `<input type="text" data-meta="${k}" value="${esc(m[k] || "")}" placeholder="${ph}" aria-label="${ph}">`;
  const vopts = s => `<option value="" ${s.kind !== "tep" && !s.view ? "selected" : ""}>текущая карта</option>` + VIEWS.map(v => `<option value="${v.id}" ${s.kind !== "tep" && v.id === s.view ? "selected" : ""}>вид «${esc(v.name)}»</option>`).join("")
    + `<option value="__tep" ${s.kind === "tep" ? "selected" : ""}>таблица ТЭП (все показатели)</option>`;
  const tepS = s => s.kind === "tep" ? "disabled" : "";
  el.innerHTML = `<div class="pad"><div class="note" style="padding:0 0 6px">Основная надпись</div><div class="meta4">${inp("object", "Объект")}${inp("code", "Шифр")}${inp("stage", "Стадия кратко: ПП, П, Р")}${inp("org", "Организация")}</div></div>`
    + `<div class="sect">Листы альбома</div>`
    + (ALBUM.sheets.length ? `<table class="at sheets"><colgroup><col style="width:26px"><col><col style="width:104px"><col style="width:20%"><col style="width:19%"><col style="width:36px"><col style="width:36px"><col style="width:176px"></colgroup><thead><tr><th>№</th><th>Название</th><th>Формат</th><th>Содержание</th><th>Масштаб</th><th title="Легенда вида">Лег.</th><th title="Таблица ТЭП">ТЭП</th><th></th></tr></thead><tbody>${ALBUM.sheets.map((s, i) => `<tr data-sh="${i}">
        <td class="num">${i + 1}</td><td><input type="text" data-sk="title" value="${esc(s.title)}" aria-label="Название листа"></td>
        <td><select data-sk="size" aria-label="Формат">${Object.keys(SIZE_T).map(v => `<option value="${v}" ${v === s.size ? "selected" : ""}>${SIZE_T[v]}</option>`).join("")}</select></td>
        <td>${s.keys || s.panels ? `<select disabled aria-label="Содержание листа" title="Лист раздела: слои, оформление и рамка заданы шаблоном раздела"><option>слои раздела</option></select>` : `<select data-sk="view" aria-label="Содержание листа">${vopts(s)}</select>`}</td>
        <td><select data-sk="scale" aria-label="Масштаб" ${tepS(s)} ${s.panels ? "disabled title=\"Две карты: у каждой свой масштаб\"" : ""}>${s.panels ? "<option>у каждой карты свой</option>" : ""}<option value="0" title="Масштаб подобран так, чтобы территория поместилась на лист">авто 1:${fmt(sheetScale({ ...s, scale: 0 }))}</option>${(s.scale && !SCALES.includes(s.scale) ? [s.scale, ...SCALES] : SCALES).map(v => `<option value="${v}" ${v === s.scale ? "selected" : ""}>1:${fmt(Math.round(v))}</option>`).join("")}</select></td>
        <td><input type="checkbox" data-sk="legend" ${s.legend ? "checked" : ""} aria-label="Легенда" ${tepS(s)}></td><td><input type="checkbox" data-sk="tep" ${s.tep ? "checked" : ""} aria-label="ТЭП" ${tepS(s)}></td>
        <td class="acts">${s.kind === "photos" ? `<button class="tb" data-shphoto="${i}" title="Добавить снимки (${(s.photos || []).length} из 12). Точка съёмки на карте берётся из GPS снимка"><i data-lucide="camera"></i></button>${(s.photos || []).length ? `<button class="tb" data-shphotox="${i}" title="Убрать все снимки со слайда"><i data-lucide="image-off"></i></button>` : ""}` : ""}${["tep", "title"].includes(s.kind) || s.panels ? "" : `<button class="tb" data-shframe="${i}" aria-pressed="${FRAME?.i === i}" title="Рамка листа на карте: тяните её мышью, чтобы выбрать, что попадёт на лист${s.center ? ". Сейчас лист сдвинут — «Вернуть» центрирует его на территории" : ""}"><i data-lucide="frame"></i></button>`}${s.center && s.kind !== "tep" ? `<button class="tb" data-shreset="${i}" title="Вернуть лист в центр территории"><i data-lucide="locate-fixed"></i></button>` : ""}<button class="tb" data-shprev="${i}" title="Просмотр листа"><i data-lucide="eye"></i></button><button class="tb" data-shup="${i}" title="Выше"><i data-lucide="arrow-up"></i></button><button class="tb" data-shdel="${i}" title="Удалить лист"><i data-lucide="trash-2"></i></button></td></tr>`).join("")}</tbody></table>`
      : `<div class="note">Листов пока нет. Лист берёт вид карты (окно «Виды») или текущую карту, рамку А3/А1 по ГОСТ, легенду и ТЭП.</div>`)
    + `<div class="pad row"><button class="btn" id="shAdd"><i data-lucide="file-plus"></i>Добавить лист</button><select id="shSlide" aria-label="Формат слайдов раздела" title="Формат слайдов раздела: меняет и уже собранные слайды">${Object.keys(SLIDE).map(v => `<option value="${v}" ${v === (ALBUM.meta.slide || "P") ? "selected" : ""}>${SIZE_T[v]}</option>`).join("")}</select><button class="btn" id="shSec1" title="Слайды раздела «Существующее положение»: месторасположение, ортофотопланы, ограничения, землепользование, Генплан, ПЗЗ, документация, соцобъекты. Недостающие слои выгружаются на всю площадь листов"><i data-lucide="layout-template"></i>Раздел 1: существующее положение</button><button class="btn" id="shPptKrt" title="Альбом «План реализации ППТ КРТ» по шаблону (А3, красная шапка): листы собираются по одному вместе с вами — сейчас титул и месторасположение"><i data-lucide="presentation"></i>Альбом ППТ КРТ</button><span class="sp" style="flex:1"></span><button class="btn primary" id="shPdf" title="Все листы одним PDF: рамка, штамп, масштаб, легенда"><i data-lucide="file-down"></i>PDF альбома</button></div>`
    + `<div class="sheetprev"><img id="sheetPrev" alt="Просмотр листа" hidden></div>`;
  icons();
}
const shEl = () => $("sheetsBody");
shEl().addEventListener("change", e => {
  const t = e.target, row = t.closest("[data-sh]");
  if (t.dataset.meta) { ALBUM.meta[t.dataset.meta] = t.value; window.markDirty?.(); return; }
  // формат слайдов раздела: новый раздел строится в нём, собранные слайды переводятся сразу (масштаб — заново, по рамке)
  if (t.id === "shSlide") { ALBUM.meta.slide = t.value; ALBUM.sheets.filter(x => String(x.id).startsWith("sec1_")).forEach(x => { x.size = t.value; x.scale = 0; });
    window.markDirty?.(); if (FRAME) showFrame(FRAME.i); renderSheets(); return; }
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
  if (b.id === "shPptKrt") window.buildAlbum?.("pptkrt");
  if (b.dataset.shprev) previewSheet(+b.dataset.shprev);
  if (b.dataset.shphoto) addPhotos(+b.dataset.shphoto);
  if (b.dataset.shphotox) { const i = +b.dataset.shphotox; if (confirmInline(b, `Убрать ${ALBUM.sheets[i].photos.length} снимков со слайда?`)) { ALBUM.sheets[i].photos = []; window.markDirty?.(); renderSheets(); } }
  if (b.dataset.shframe) { const i = +b.dataset.shframe; showFrame(FRAME?.i === i ? null : i); renderSheets(); }
  if (b.dataset.shreset) { const i = +b.dataset.shreset; delete ALBUM.sheets[i].center; window.markDirty?.(); if (FRAME?.i === i) showFrame(i); renderSheets(); }
  if (b.dataset.shup || b.dataset.shdel) showFrame(null);
  if (b.dataset.shup) { const i = +b.dataset.shup; if (i > 0) { [ALBUM.sheets[i - 1], ALBUM.sheets[i]] = [ALBUM.sheets[i], ALBUM.sheets[i - 1]]; window.markDirty?.(); renderSheets(); } }
  if (b.dataset.shdel) { const i = +b.dataset.shdel; if (confirmInline(b, `Удалить лист «${ALBUM.sheets[i].title}»?`)) { ALBUM.sheets.splice(i, 1); window.markDirty?.(); renderSheets(); } }
});
/* Фотофиксация: снимки уменьшаются до 1600 px по длинной стороне (JPEG) и хранятся в проекте; точка съёмки — из EXIF GPS. */
function exifGps(buf) {
  const v = new DataView(buf); if (v.byteLength < 4 || v.getUint16(0) !== 0xFFD8) return null;
  for (let o = 2; o + 10 < v.byteLength;) {
    const m = v.getUint16(o), len = v.getUint16(o + 2);
    if (m === 0xFFE1 && v.getUint32(o + 4) === 0x45786966) {
      const t = o + 10, le = v.getUint16(t) === 0x4949, u16 = p => v.getUint16(t + p, le), u32 = p => v.getUint32(t + p, le);
      const tag = (p, id) => { for (let i = 0, k = u16(p); i < k; i++) if (u16(p + 2 + i * 12) === id) return p + 2 + i * 12; return null; };
      const g = tag(u32(4), 0x8825); if (g == null) return null;
      const gp = u32(g + 8), deg = e => { const a = u32(e + 8); return [1, 60, 3600].reduce((s, d, k) => s + u32(a + k * 8) / (u32(a + k * 8 + 4) || 1) / d, 0); };
      const ref = id => { const e = tag(gp, id); return e == null ? "" : String.fromCharCode(v.getUint8(t + e + 8)); };
      const la = tag(gp, 2), lo = tag(gp, 4); if (la == null || lo == null) return null;
      const lat = deg(la) * (ref(1) === "S" ? -1 : 1), lon = deg(lo) * (ref(3) === "W" ? -1 : 1);
      return lat || lon ? [lon, lat] : null;
    }
    if ((m & 0xFF00) !== 0xFF00) break;
    o += 2 + len;
  }
  return null;
}
function addPhotos(i) {
  const inp = document.createElement("input");
  inp.type = "file"; inp.accept = "image/*"; inp.multiple = true;
  inp.onchange = () => addPhotoFiles(i, [...inp.files]);
  inp.click();
}
async function addPhotoFiles(i, list) {
  const sh = ALBUM.sheets[i], files = list.slice(0, 12 - (sh.photos || []).length);
  if (!files.length) return toast("На слайде уже 12 снимков — больше не поместится.");
  busy(true); let geo = 0;
  try {
    for (const f of files) {
      const buf = await f.arrayBuffer(), gps = (() => { try { return exifGps(buf); } catch { return null; } })();
      const bm = await createImageBitmap(f), k = Math.min(1, 1600 / Math.max(bm.width, bm.height)), c = document.createElement("canvas");
      c.width = Math.round(bm.width * k); c.height = Math.round(bm.height * k); c.getContext("2d").drawImage(bm, 0, 0, c.width, c.height);
      (sh.photos ||= []).push({ name: f.name, data: c.toDataURL("image/jpeg", .82).split(",")[1], w: c.width, h: c.height, at: gps });
      if (gps) geo++;
    }
    window.markDirty?.(); renderSheets(); previewSheet(i);
    toast(`Снимков добавлено: ${files.length}${geo < files.length ? `; без GPS — ${files.length - geo} (точки на карте нет, только снимок)` : ""}.`);
  } catch (e) { toast("Снимок не прочитан: " + e.message); } finally { busy(false); }
}
/* Рамки листов на карте рисует и правит frames.js (инструмент «Лист»): каждый лист-карта альбома — рамка с ручками.
   Кнопка рамки в строке листа выбирает его рамку и показывает её на карте. */
let FRAME = null;
function frameGeom(sh) {
  const [fw, fh] = frameMM(sh), scale = sheetScale(sh), c = sheetCenter(sh), c3 = ol.proj.fromLonLat(c), k = 1 / Math.cos(c[1] * Math.PI / 180);
  const hx = fw / 2 / 1000 * scale * k, hy = fh / 2 / 1000 * scale * k;
  return new ol.geom.Polygon([[[c3[0] - hx, c3[1] - hy], [c3[0] + hx, c3[1] - hy], [c3[0] + hx, c3[1] + hy], [c3[0] - hx, c3[1] + hy], [c3[0] - hx, c3[1] - hy]]]);
}
function showFrame(i) {
  const sh = i == null ? null : ALBUM.sheets[i];
  FRAME = sh && window.sheetOnMap?.(sh, true) ? { i } : null;
  window.selectSheetFrame?.(FRAME ? sh : null, true);
}
// окно «Листы» закрыто — листы раздела уходят с карты (свои листы остаются)
new MutationObserver(() => { if ($("wSheets").hidden && FRAME) showFrame(null); window.redrawFrames?.(); }).observe($("wSheets"), { attributes: true, attributeFilter: ["hidden"] });
window.previewSheet = previewSheet; window.renderSheets = renderSheets; window.hideSheetFrame = () => showFrame(null);
