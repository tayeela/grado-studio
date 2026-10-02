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
    return { key: l.key, title: l.title, geom: l.geom, style: st, visible: vis && g, a: x ? okn(x.layerOpacity, 1) : l.layerOpacity, _br: null, cache: new Map() }; }).filter(p => p.visible);
}
const sheetCenter = sheet => sheet.center || (sheet.fit && fitBox(sheet) ? [(fitBox(sheet)[0] + fitBox(sheet)[2]) / 2, (fitBox(sheet)[1] + fitBox(sheet)[3]) / 2]
  : TERR ? turf.centroid(TERR).geometry.coordinates : ol.proj.toLonLat(sharedView.getCenter()));
const sheetScale = sheet => sheet.scale || autoScale(frameMM(sheet), sheet.fit ? fitBox(sheet) : null, !!sheet.adm);
// показатели ТЭП строками таблицы; на листе с картой — первые 30, на листе «Таблица ТЭП» — все
function tepRows(all) {
  const t = RESULT.tepNode?._tep; if (!t) return [];
  const ms = t.metrics.filter(m => m.value);
  return [["Территория", fmt(t.terr, 2) + " га"], ["СПП новая", fmt(t.sppNew / 1000, 1) + " тыс. м²"], ["СПП сохраняемая", fmt(t.sppKept / 1000, 1) + " тыс. м²"], ["Плотность", fmt(t.density, 1) + " тыс. м²/га"], ["Застроенность", fmt(t.cover * 100, 1) + " %"]]
    .concat(t.constantsChanged?.length ? [["Нормативы изменены вручную", String(t.constantsChanged.length)]] : [])      // правки в окне «Нормативы расчёта» видны и на листе
    .concat((all ? ms : ms.slice(0, 30)).map(m => [m.title, fmt(m.value, m.precision ?? 3) + " " + m.unit]));
}
function sheetSpec(sheet) {
  if (sheet.frozen) { const { id, frozen, view, ...ready } = sheet; return ready; }   // готовая вёрстка из файла: слои уже внутри листа (импорт «Из файла…»)
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
    const out = sheetSpec({ ...sheet, kind: "map", part: "photo" }), pts = sheet.look ? [] : (sheet.photos || []).map((ph, i) => ph.at ? { g: { type: "Point", coordinates: ph.at }, fill: "#2e8b3a", stroke: "#ffffff", w: 5, a: 1, label: String(i + 1) } : null).filter(Boolean);
    if (!sheet.look) out.layers.push({ title: "Точки съёмки", features: pts });   // у листа «Царицыно» — свои стрелки (conceptSheet)
    if (pts.length) out.legend.push({ title: "Точки съёмки", kind: "point", items: [{ label: "Точка съёмки и номер снимка", fill: "#2e8b3a" }] });
    return { ...out, kind: "photos", photos: (sheet.photos || []).map(ph => ({ data: ph.data, w: ph.w, h: ph.h })) };
  }
  const size = sheet.size, scale = sheetScale(sheet), [fw, fh] = frameMM(sheet);
  const center = sheetCenter(sheet);
  const half = [fw / 2 / 1000 * scale * 1.15, fh / 2 / 1000 * scale * 1.15], c3 = ol.proj.fromLonLat(center), stretch = 1 / Math.cos(center[1] * Math.PI / 180);
  const ext = [c3[0] - half[0] * stretch, c3[1] - half[1] * stretch, c3[0] + half[0] * stretch, c3[1] + half[1] * stretch];
  const tc = TERR ? turf.centroid(TERR) : null;
  // рамка листа в градусах (без запаса выборки): для списков документов и листов по образцу «ГК Царицыно»
  const frameLL = (() => { const [lo, la] = ol.proj.toLonLat([ext[0], ext[1]]), [hi, ha] = ol.proj.toLonLat([ext[2], ext[3]]), k = 1 / 1.15;
    return [center[0] - (center[0] - lo) * k, center[1] - (center[1] - la) * k, center[0] + (hi - center[0]) * k, center[1] + (ha - center[1]) * k]; })();
  const homeOkr = sheet.homeOkrug ? (h => h.okrug?.properties["Округ"] || h.okrug?.properties["Наименование"])(homeAdm()) : null;
  const vl = viewLayers(sheet).filter(pl => !(pl.style.maxDen && scale > pl.style.maxDen) && !(pl.style.minDen && scale < pl.style.minDen)), layers = [], legend = [];   // видимость по масштабу — и на листе, как в QGIS
  vl.slice().reverse().forEach(pl => {                                   // снизу вверх, как рисует карта
    const st = pl.style, feats = [];
    layerSrc[pl.key]?.forEachFeatureInExtent(ext, f => {
      const g = GJ.writeFeatureObject(f).geometry; if (!g) return;
      const only = sheet.only?.[pl.key]; if (only && !only.values.includes(f.get(only.field))) return;
      if (homeOkr && pl.key === "gisogd.admin" && f.get("Уровень") === "район" && f.get("Округ") !== homeOkr) return;   // «Районы …» — только своего округа
      const lab = sheet.labelFn?.[pl.key] ? LABEL_FN[sheet.labelFn[pl.key]](f) : st.label ? f.get(st.label) : null;
      // подсветка: округ и район, в которых лежит территория
      const hl = sheet.hilite?.[pl.key] && tc && /Polygon/.test(g.type) && safe(() => turf.booleanPointInPolygon(tc, g)) ? sheet.hilite[pl.key] : null;
      if (st.mode === "lgr") { const lt = f.get("_lt") || [], miss = f.get("_miss") || [];
        // код без типа линии REDLN97 (техзоны, береговые и др.) — штрих знака и надпись знака вдоль линии, по Эталону ЛГР
        const ll = miss.map(([c]) => LGRS[+c]?.line_label).find(Boolean);
        feats.push({ g, lt, miss, lc: LGRC[ltCode(lt[0] || "")] || LGRC[miss[0]?.[0]] || "#d7191c", w: st.width, label: lab, ll }); return; }
      const s = symbolOf(pl, f); if (s.hide) return;
      // как на карте: контур при штриховке — цветом штриховки, если у слоя нет своего цвета контура (Эталон ЛГР);
      // штрих контура и шаг штриховки — в пикселях карты; подписи надписей ГИС ОГД — своим цветом, под своим углом, без значка
      feats.push({ g, fill: hl || s.fill, stroke: pl.geom === "poly" ? (s.hatch && !st.strokeOwn ? s.fill : st.stroke) : s.fill, w: st.width, a: hl ? 1 : st.opacity * pl.a, hatch: s.hatch, hp: st.hatchPat || "45",
        hs: st.hatchStep, dash: st.dash?.length ? st.dash : undefined, nm: st.marker === false || undefined, lcol: st.labelColor, la: st.labelAngle ? upright(labelDeg(f)) : undefined,
        label: lab == null || lab === "" ? null : String(lab), ls: sheet.labelMM?.[pl.key], lc: pl.geom === "line" ? s.fill : undefined,
        nl: st.lineOff || undefined, props: sheet.look ? (({ geometry, ...p }) => p)(f.getProperties()) : undefined, ...(sheet.labelStyle?.[pl.key] || {}) });   // props — листам «Царицыно», в печать не уходят
    });
    layers.push({ key: pl.key, title: pl.title, features: feats });
  });
  if (sheet.legend) vl.forEach(pl => {
    const st = pl.style, items = st.mode === "lgr" ? [{ label: "красные линии и ЛГР (REDLN97)", fill: "#d7191c" }] : legendItems(pl).filter(it => !it.off).slice(0, 14).map(it => ({ label: it.v, fill: it.c, stroke: pl.geom === "poly" ? st.stroke : it.c, hatch: st.hatch, a: st.opacity }));
    // альбом по шаблону: в легенде без источника в скобках («Здания», а не «Здания (ЕГКО)»); свои названия — legendTitle
    const title = sheet.legendTitle?.[pl.key] || (sheet.style ? pl.title.replace(/\s*\((ОГД|ЕГКО|ЕГРН|OSM|НСПД|Яндекс)\)$/, "") : pl.title);
    legend.push({ title, kind: pl.geom, items: items.length ? items : [{ label: title, fill: st.fill, stroke: st.stroke, hatch: st.hatch, a: st.opacity }] });
  });
  const tep = sheet.tep ? tepRows(false) : [];
  const out = { title: sheet.title, size, orient: sheet.orient || "L", scale, center, layers, legend, tep, territory: TERR?.geometry || null, basemap: sheet.basemap || "",
    ...(sheet.rect ? { rect: sheet.rect } : {}), ...albumExtra(sheet) };
  if (isSlide(size)) out.terrStyle = ["okrug", "moscow"].includes(sheet.fit) ? { stroke: "#e0158c", width: .9, fill: "#e0158c" } : { stroke: "#e0158c", width: .9 };
  if (sheet.extra === "parcels") Object.assign(out, parcelsSheet(layers));
  if (sheet.extra === "radii") radiiSheet(out);
  if (sheet.extra === "genplan") genplanTable(out);
  if (sheet.docs && !sheet.look) docsSheet(out, sheet, frameLL);
  if (sheet.note) out.note = sheet.note;
  // выноска на карте района: «проектируемая территория» и район, где она лежит
  if (sheet.callout && tc) { const d = (DATA["gisogd.admin"]?.fc.features || []).find(x => x.properties["Уровень"] === "район" && safe(() => turf.booleanPointInPolygon(tc, x)));
    out.callout = sheet.style === "pptkrt" ? ["Рассматриваемая территория", `S\u00a0=\u00a0${fmt(m2(TERR) / 1e4, 2)}\u00a0га`]   // как в шаблоне ППТ КРТ
      : ["проектируемая территория"].concat(d ? ["район " + LABEL_FN.adm({ get: k => d.properties[k] })] : []); }
  if (isSlide(size) && sheet.legend) out.legend.unshift({ title: "Границы", kind: "line", items: [{ label: `${sheet.style === "pptkrt" ? "Граница территории рассмотрения" : "Граница разработки проекта планировки"} (S\u00a0=\u00a0${fmt(m2(TERR) / 1e4, 2)}\u00a0га)`, fill: "#e0158c" }] });   // площадь — до сотых гектара
  if (sheet.look === "concept") conceptSheet(out, sheet, frameLL);           // шапка ППТ КРТ, остальное — как в «ГК Царицыно» (albums.js)
  if (sheet.kind === "situation") situationExtras(sheet, out, frameLL);
  return out;
}
const albumSpec = list => ({ meta: { ...ALBUM.meta, short: ALBUM.meta.short || "", place: ALBUM.meta.place || placeText(), date: ALBUM.meta.date || monthYear() }, sheets: list.map(s => ({ ...sheetSpec(s), edits: s.edits || {}, items: s.items || [] })) });   // правки макета — в печать
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
// рамка содержания листа: территория с полями, район или округ территории (из слоя административного деления)
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
    rows: pl.map((f, i) => [String(i + 1), String(f.properties["Кадастровый номер"] || "—"), fmt(+f.properties["Площадь уточнённая, м²"] || +f.properties["Площадь участка, м²"] || Math.round(m2(f))), shortRight(f.properties["Вид права"] || f.properties["Форма собственности"] || "—")]) } };   // длинное печать ещё и ужмёт
}
const cut = (t, n) => { t = String(t); return t.length > n ? t.slice(0, n - 1) + "…" : t; };
// Генплан: функциональные зоны на территории — номер, индекс, наименование, суммарный поэтажный фонд
function genplanTable(out) {
  const z = ["gisogd.func_zones", "gisogd.func_zones_tinao"].flatMap(k => DATA[k]?.fc.features || []).filter(f => /Polygon/.test(f.geometry?.type) && safe(() => { const x = inter(f, TERR); return x && m2(x) > 20; }));
  if (!z.length) return;
  out.table = { title: "Функциональные зоны на территории", cols: [["№", .1, "left"], ["Индекс", .17, "left"], ["Наименование", .5, "left"], ["тыс. м²", .23, "right"]],
    rows: z.map(f => { const p = f.properties; return [gpNum(p) || "—", gpIdx(p) || "—", p.naimfunkzony || p["Вид зоны"] || p.name || "—", gpFund(p)]; }) };
}
// документы на листе (ППТ и ПМТ, ГПЗУ и АГР — как в «ГК Царицыно»): номер у документа на карте и нумерованный список
// «Название №… от … г.» в колонке листа; ближние к территории — первыми, нумерация сквозная по группам
const dateRu = d => /^\d{4}-\d{2}-\d{2}/.test(String(d || "")) ? String(d).slice(0, 10).split("-").reverse().join(".") : String(d || "");
function docsSheet(out, sheet, bb) {
  const c = TERR ? turf.centroid(TERR) : null, box = turf.bboxPolygon(bb), lists = [], pts = [];
  let no = 0;
  for (const d of sheet.docs) {
    const seen = new Map();
    (DATA[d.key]?.fc.features || []).filter(f => /Polygon/.test(f.geometry?.type) && safe(() => turf.booleanIntersects(f, box))).forEach(f => {
      const p = f.properties, id = p.document_n || p.document_g || p._key, part = safe(() => inter(f, box)) || f;
      const at = safe(() => turf.pointOnFeature(part)), dist = c && at ? turf.distance(c, at) : 0;
      if (at && (!seen.has(id) || dist < seen.get(id).dist)) seen.set(id, { f, at, dist });
    });
    const docs = [...seen.values()].sort((a, b) => a.dist - b.dist).slice(0, d.max || 12);
    if (!docs.length) continue;
    lists.push({ title: d.title, items: docs.map(({ f, at }) => {
      const p = f.properties, n = String(++no);
      pts.push({ g: at.geometry, nm: true, nudge: true, label: n, ls: 3.6, lf: "ui-bold", lh: .6, lcol: "#141414" });
      return `${n}. ${[d.pre || p.document_1 || "", p.document_n ? "№" + p.document_n : "", p.document_d ? `от ${dateRu(p.document_d)} г.` : ""].filter(Boolean).join(" ")}`; }) });
  }
  if (!pts.length) { out.note = [out.note, "В ГИС ОГД в пределах листа таких документов нет."].filter(Boolean).join(" "); return; }
  out.layers.push({ title: "Номера документов", features: pts });
  out.lists = lists;
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
const DERIVED = { "calc.uds_osm": ["osm.roads"], "calc.uds_ya": ["yandex.hd_roads", "yandex.roads"], "calc.uds_sit": ["sit.roads_hd", "sit.roads"] };
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
  if (DATA["sit.roads_hd"] || DATA["sit.roads"])
    udsLayer("calc.uds_sit", "Ситплан: УДС (Яндекс)", DATA["sit.roads_hd"]?.fc.features || [], DATA["sit.roads"]?.fc.features || [],
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
// административное деление всей Москвы (выгрузка до v0.65 знала районы только своего округа — берётся заново)
async function ensureAdmin() {
  const adm = DATA["gisogd.admin"]?.fc.features || [];
  if (adm.filter(f => f.properties["Уровень"] === "район").length < 100 || adm.some(f => f.properties["Уровень"] === "округ" && f.properties["Граница"] !== ADM_REV)) {
    toast("Административное деление Москвы…"); await loadKeys(["gisogd.admin"], [36.8, 55.1, 38.0, 56.1]); }
}
/* Ситуационный план: картинка на весь лист А4 без легенды, штампа и подписи — зелень, вода, дороги и дома Яндекса
   (тайлы z16), главные пути железной дороги, границы районов с названиями, названия улиц (OSM) и граница территории.
   Масштаб — авто по территории с окружением ~900 м, меняется в строке листа; рамку можно сдвинуть. */
const SIT = { kind: "situation", title: "Ситуационный план", size: "BA4", legend: false, tep: false, scale: 0, view: "", fit: "terr", pad: 900,
  keys: ["sit.green", "sit.water", "calc.uds_sit", "sit.buildings", "gisogd.admin", "sit.rail", "osm.roads"],
  only: { "gisogd.admin": { field: "Уровень", values: ["район"] }, "osm.roads": { field: "Тип дороги", values: ["motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "living_street"] } },
  styles: { "gisogd.admin": { mode: "single", fill: "#ffffff", opacity: 0, stroke: "#8a3fb0", width: 2.6, label: "", dash: [15, 4.6, 3, 4.6] },
    "sit.rail": { mode: "single", fill: "#1f1f1f", width: 3 }, "osm.roads": { mode: "single", fill: "#ffffff", width: 0, label: "Название", lineOff: true },
    ...Object.fromEntries(["sit.green", "sit.water", "calc.uds_sit", "sit.buildings"].map(k => [k, { minDen: 0 }])) },   // на листе — при любом масштабе
  labelMM: { "osm.roads": 2.2 } };
function situationExtras(sheet, out, frameLL) {
  // железная дорога — белые штрихи поверх чёрной линии, как на топоплане
  const rail = out.layers.find(l => l.key === "sit.rail");
  if (rail) out.layers.push({ key: "sit.rail.dash", title: "Железная дорога: штрихи", features: rail.features.map(f => ({ ...f, fill: "#ffffff", stroke: "#ffffff", lc: "#ffffff", w: 1.2, dash: [7.7, 7.7], label: null })) });
  // названия районов — на той части района, что попала на лист
  const box = turf.bboxPolygon(frameLL), pts = [];
  (DATA["gisogd.admin"]?.fc.features || []).filter(f => f.properties["Уровень"] === "район").forEach(f => {
    const x = inter(f, box); if (!x || turf.area(x) < 2e4) return;
    pts.push({ g: turf.pointOnFeature(x).geometry, nm: true, ls: 3.4, lcol: "#5b2a78", label: "РАЙОН " + LABEL_FN.adm({ get: k => f.properties[k] }).toUpperCase() }); });
  out.layers.push({ key: "sit.districts", title: "Районы: подписи", features: pts });
  out.kind = "situation"; out.legend = [];
}
const buildSituation = () => track(() => buildSituation0());
async function buildSituation0() {
  if (!TERR) { toast("Выберите файл границы (DXF, DWG, GeoJSON, KML, Shapefile) — лист строится вокруг неё."); return window.pickBoundary(buildSituation0); }
  const sh = { id: "sit_" + Date.now().toString(36), ...JSON.parse(JSON.stringify(SIT)) };
  await ensureAdmin();
  const bb = frameBox(sh), before = new Set(LYR.map(l => l.key));
  // OSM — только названия улиц: середины листа хватает
  const c = turf.centroid(TERR).geometry.coordinates, kx = 111.32 * Math.cos(c[1] * Math.PI / 180), ky = 110.54, a = (bb[2] - bb[0]) * kx * (bb[3] - bb[1]) * ky;
  const f = Math.min(1, Math.sqrt(24 / a)), ob = [c[0] - (bb[2] - bb[0]) * f / 2, c[1] - (bb[3] - bb[1]) * f / 2, c[0] + (bb[2] - bb[0]) * f / 2, c[1] + (bb[3] - bb[1]) * f / 2];
  toast("Ситуационный план: здания, дороги и зелень Яндекса, железная дорога, названия улиц…");
  await loadKeys(["sit.green", "sit.water", "sit.roads_hd", "sit.roads", "sit.buildings", "sit.rail"], bb);
  // вблизи территории — подробная основа Яндекса (z18): крупнее 1:7 500 обзорные слои не видны, их сменяет она
  const near = ["yandex.buildings", "yandex.hd_roads", "yandex.roads", "yandex.green", "yandex.water"].filter(k => !(DATA[k]?.bbox && turf.booleanWithin(turf.bboxPolygon(turf.bbox(buf(TERR, 150))), turf.bboxPolygon(DATA[k].bbox))));
  if (near.length) await loadKeys(near, turf.bbox(buf(TERR, 300)));
  const rb = DATA["osm.roads"]?.bbox; if (!rb || !(rb[0] <= ob[0] && rb[1] <= ob[1] && rb[2] >= ob[2] && rb[3] >= ob[3])) await loadKeys(["osm.roads"], ob);
  buildUds();
  // своя подробная застройка на территории (ЕГКО, ЕГРН) уже есть — здания Яндекса её не дублируют
  const ext = ol.proj.transformExtent(turf.bbox(TERR), "EPSG:4326", "EPSG:3857");
  const detailed = ["egko.buildings", "nspd.buildings"].some(k => lyr(k)?.visible && layerSrc[k]?.getFeaturesInExtent(ext).length);
  LYR.filter(l => !before.has(l.key) && /^(sit\.|calc\.uds_sit)/.test(l.key)).forEach(l => { l.visible = l.key !== "sit.roads" && l.key !== "sit.roads_hd" && !(detailed && l.key === "sit.buildings"); });
  // подробные слои Яндекса, заведённые здесь, — только крупнее 1:7 500: на обзоре их сменяет ситплан без наложения
  LYR.filter(l => !before.has(l.key) && /^yandex\./.test(l.key)).forEach(l => { l.visible = ["yandex.green", "yandex.water"].includes(l.key) || (l.key === "yandex.buildings" && !detailed);
    if (!l.style.maxDen) { l.style.maxDen = 7500; rebuildLayer(l); } });
  // названия улиц, УДС по осям OSM и районы нужны листу, а не холсту: заведённые здесь — выключены (есть в дереве)
  LYR.filter(l => !before.has(l.key) && ["osm.roads", "calc.uds_osm", "gisogd.admin"].includes(l.key)).forEach(l => { l.visible = false; });
  tidyLayers();
  ALBUM.sheets.push(sh); ALBUM.meta.builtAt = new Date().toISOString(); window.markDirty?.(); renderSheets(); previewSheet(ALBUM.sheets.length - 1);
  toast(`Ситуационный план А4, 1:${fmt(sheetScale(sh))}: масштаб меняется в строке листа, рамка сдвигается на карте, PDF одного листа — кнопкой в строке. Данные Яндекса — пользовательская карта, для работы.`);
}
/* Собрать набор листов по образцу (tpl): раздел 1 на слайдах 16:9 (SEC1) или альбомы по образцам владельца
   (albums.js): листы получают префикс id (prefix), старые листы того же набора заменяются. */
const buildSection = (...a) => track(() => buildSection0(...a));
async function buildSection0(tpl = SEC1, prefix = "sec1_", size = ALBUM.meta.slide || "P", name = "Раздел «Существующее положение»") {
  if (!TERR) return toast("Сначала задайте границу территории — от неё строятся рамки листов.");
  const before = new Set(LYR.map(l => l.key));
  const sheets = tpl.map((t, i) => ({ id: prefix + i, size, legend: t.kind !== "title", tep: false, scale: 0, view: "", ...JSON.parse(JSON.stringify(t)) }));
  // административное деление — для рамок «округ» и «район» его нужно получить первым; выгрузка до v0.65 знала районы
  // только своего округа — берётся заново: схема Москвы рисует все районы (их в Москве 132). Область выгрузки — вся
  // Москва: слой всегда городской, а перевыгрузка по малой рамке обновила бы только ближние районы
  await ensureAdmin();
  // остальные слои — по самой большой рамке листа, где слой нужен; одинаковые рамки — одной выгрузкой
  const need = new Map();
  sheets.flatMap(s => s.panels ? s.panels.map(p => ({ ...p, size: s.size, part: "half" })) : [s]).filter(s => s.keys).forEach(s => { const bb = frameBox(s); s.keys.flatMap(k => DERIVED[k] || [k]).filter(k => k !== "gisogd.admin" && SOURCES[k]).forEach(k => {
    const cur = need.get(k); need.set(k, cur ? [Math.min(cur[0], bb[0]), Math.min(cur[1], bb[1]), Math.max(cur[2], bb[2]), Math.max(cur[3], bb[3])] : bb); }); });
  // УДС Яндекса: вокруг территории (холст, анализ) и по рамкам листов, где дороги — полигоны Яндекса (альбом ППТ КРТ)
  ["yandex.hd_roads", "yandex.roads"].forEach(k => { const t = turf.bbox(buf(TERR, 400)), cur = need.get(k);
    need.set(k, cur ? [Math.min(cur[0], t[0]), Math.min(cur[1], t[1]), Math.max(cur[2], t[2]), Math.max(cur[3], t[3])] : t); });
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
  // пересборка раздела не теряет добавленные снимки и правки макета (надписи, свои тексты) — по листу с тем же видом и названием
  const old = new Map(ALBUM.sheets.filter(s => String(s.id).startsWith(prefix)).map(s => [(s.kind || "") + s.title, s]));
  sheets.forEach(s => { const o = old.get((s.kind || "") + s.title); if (s.kind === "photos") s.photos = o?.photos || [];
    if (o?.edits) s.edits = o.edits; if (o?.items) s.items = o.items; });
  ALBUM.sheets = ALBUM.sheets.filter(s => !String(s.id).startsWith(prefix)).concat(sheets);
  // холст — опорный план: тематические слои раздела (зоны, ПЗЗ, Генплан, документация, соцобъекты) выключены — они
  // нужны листам, а не холсту; включить любой можно в дереве. Застройка одна, порядок как на плане
  const used = sheets.flatMap(s => s.panels ? s.panels.flatMap(p => p.keys || []) : s.keys || []);
  tidyLayers(new Set(LYR.map(l => l.key).filter(k => !before.has(k) || used.includes(k) || need.has(k))));
  ALBUM.meta.builtAt = new Date().toISOString();
  window.markDirty?.(); renderSheets(); toast(`${lost.length ? `Не загрузились после повтора: ${lost.join("; ")} — слайды с ними неполные, повторите сборку позже. ` : ""}${name}: ${sheets.length} листов, формат «${SIZE_T[size] || size}». Холст приведён к опорному плану: тематические слои раздела выключены (включаются в дереве). «PDF альбома» — выгрузка; рамку любого листа можно сдвинуть.`);
}
// прямоугольник рамки листа в градусах (как frameGeom)
function frameBox(sh) { const g = frameGeom(sh).clone(); g.transform("EPSG:3857", "EPSG:4326"); return g.getExtent(); }

async function previewSheet(i) {
  if (ALBUM.sheets.length && i !== selIdx()) { SHI = i; renderSheets(); }
  busy(true);
  try {
    const r = await fetch("/api/print/svg", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...albumSpec([ALBUM.sheets[i]]), index: 0 }) });
    if (!r.ok) throw new Error((await r.json()).error);
    const url = URL.createObjectURL(await r.blob()), img = $("sheetPrev"); if (!img) return; if (img.dataset.url) URL.revokeObjectURL(img.dataset.url);
    img.src = url; img.dataset.url = url; img.dataset.i = i; img.hidden = false; img.title = "Двойной щелчок — макет: правка надписей листа";
  } catch (e) { toast("Лист не собран: " + e.message); } finally { busy(false); }
}
// альбом файлом: PDF для печати или PPTX — та же вёрстка редактируемой презентацией PowerPoint (подписи — текстом,
// карты — фигурами по слоям, снимки — рисунками)
const albumFile = (kind, only) => track(() => albumFile0(kind, only));
async function albumFile0(kind = "pdf", only = null) {
  if (!ALBUM.sheets.length) return toast("В альбоме нет листов: «Добавить лист».");
  const list = only ? [only] : ALBUM.sheets;
  busy(true);
  try {
    const r = await fetch("/api/print/" + kind, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(albumSpec(list)) });
    if (!r.ok) throw new Error((await r.json()).error);
    const a = document.createElement("a"); a.href = URL.createObjectURL(await r.blob()); a.download = (only ? only.title : ALBUM.meta.object || PROJ.name || "альбом") + "." + kind; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    if (!only) stampAlbum(kind === "pdf" ? "pdfAt" : "pptxAt");
    // листы «не готов»: что-то не поместилось, а мельчить и обрывать молча нельзя — пометка серым внизу листа
    const nr = r.headers.get("X-Grado-Not-Ready");
    toast((only ? `Лист «${only.title}» — PDF.` : kind === "pdf" ? `Альбом PDF: ${ALBUM.sheets.length} л. Координаты — МСК, красные линии — типами REDLN97.`
      : `Презентация PPTX: ${ALBUM.sheets.length} сл. Всё правится в PowerPoint: подписи — текст, карты — фигуры, сгруппированные по слоям.`)
      + (nr ? ` Не готовы листы ${nr.split(",").join(", ")}: не всё поместилось, что именно — серым внизу листа.` : "") + " Файл сохранён в папку загрузок браузера.");
  } catch (e) { toast((kind === "pdf" ? "PDF" : "PPTX") + " не собран: " + e.message); } finally { busy(false); }
}
// спутник Яндекса по рамке листа — для AutoCAD в МСК (как выгрузка снимка из QGIS). AutoCAD показывает снимок из DXF
// сразу, только если путь к нему полный: папку загрузок браузера программа спрашивает один раз, архив называется
// уникально (sputnik_<лист>_<время>), и двойной щелчок по нему в папке загрузок распаковывает его ровно туда
function dlDir(ask) {
  let d = ""; try { d = localStorage.getItem("grado2.dlDir") || ""; } catch { }
  if (!d || ask) {
    const v = prompt("Папка, куда браузер сохраняет скачанные файлы — полный путь (один раз). Например: /Users/имя/Downloads", d || "/Users/");
    if (!v) return null; d = v.trim().replace(/[\\/]+$/, ""); try { localStorage.setItem("grado2.dlDir", d); } catch { }
  }
  return d;
}
async function satFile(i, ask) {
  const sh = ALBUM.sheets[i], s = albumSpec([sh]).sheets[0], dir = dlDir(ask); if (!dir) return;
  const t = new Date(), p2 = n => String(n).padStart(2, "0");
  const stem = `sputnik_${i + 1}_${t.getFullYear()}${p2(t.getMonth() + 1)}${p2(t.getDate())}-${p2(t.getHours())}${p2(t.getMinutes())}${p2(t.getSeconds())}`;
  const req = { ...(s.rect && s.center ? { center: s.center, rect: s.rect, scale: s.scale } : { bbox: frameBox(sh) }), base: dir + "/" + stem };
  busy(true); window.setHint?.("Спутник Яндекса: скачиваются снимки рамки листа.");
  const poll = setInterval(async () => { try { const p = (await api("/api/progress")).sat; if (p) window.setHint?.(`Спутник Яндекса: снимки ${p.got} из ${p.total}. Первая выгрузка идёт минуты, повтор берётся с диска.`); } catch { } }, 1000);
  try {
    const r = await fetch("/api/export/sat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) });
    if (!r.ok) throw new Error((await r.json()).error);
    const a = document.createElement("a"); a.href = URL.createObjectURL(await r.blob()); a.download = stem + ".zip"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    toast(`Спутник Яндекса в МСК: ${stem}.zip. Распакуйте его двойным щелчком в папке загрузок (${dir}) и откройте sputnik_yandex.dxf — снимок уже на месте. Другая папка загрузок — Shift+щелчок по кнопке. Только для работы, в сдаваемые материалы не включать.`);
  } catch (e) { toast("Снимок не собран: " + (/too large|too many/.test(e.message) ? "рамка слишком велика — не больше 6 × 6 км" : e.message)); }
  finally { clearInterval(poll); busy(false); window.setHint?.(""); }
}
// строка состояния альбома: сколько листов, когда собран и когда в последний раз сохранены PDF и PPTX (время — в проекте, ALBUM.meta)
const stampAlbum = k => { ALBUM.meta[k] = new Date().toISOString(); window.markDirty?.(); syncAlbumStat(); };
const stampText = (iso, long) => { const d = new Date(iso); if (isNaN(d)) return ""; const p = n => String(n).padStart(2, "0"); return `${p(d.getDate())}.${p(d.getMonth() + 1)}${long ? "." + d.getFullYear() : ""} ${p(d.getHours())}:${p(d.getMinutes())}`; };
const BYTES = new WeakMap(), sheetBytes = x => { let n = BYTES.get(x); if (n == null) { n = JSON.stringify(x).length; BYTES.set(x, n); } return n; };   // размер листа в проекте считается один раз
const shWord = n => (n % 10 === 1 && n % 100 !== 11) ? "лист" : ([2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100)) ? "листа" : "листов";
function albumStatText() {
  const m = ALBUM.meta, n = ALBUM.sheets.length;
  if (!n) return "Альбом: листов нет";
  let t = `Альбом: ${n} ${shWord(n)}` + (m.builtAt ? ` · собран ${stampText(m.builtAt)}` : " · дата сборки не записана");
  const big = ALBUM.sheets.reduce((n, x) => n + (x.frozen ? sheetBytes(x) : 0), 0);
  if (big > 10 * 2**20) t += ` · готовая вёрстка, ${mb(big)} МБ — сохранение медленнее`;
  if (m.importedFrom) t += ` · импортирован из файла ${m.importedFrom}`;
  if (m.pdfAt) t += ` · PDF ${stampText(m.pdfAt)}`;
  if (m.pptxAt) t += ` · PPTX ${stampText(m.pptxAt)}`;
  const last = [m.editedAt, m.builtAt].filter(Boolean).sort().pop();       // правили листы после последнего файла
  if (last && m.pdfAt && last > m.pdfAt) t += " · изменён после PDF";
  else if (last && !m.pdfAt && m.pptxAt && last > m.pptxAt) t += " · изменён после PPTX";
  return t;
}
const syncAlbumStat = () => { const e = $("shStat"); if (e) { const t = SHBUILD > 0 ? "Собираю…" : albumStatText(); e.textContent = t; e.title = t; } };
/* Импорт альбома из файла: проект .grado2 (берётся его album) или голый альбом {meta, sheets}. Читается в браузере
   (FileReader), на сервер не уходит. Лист с готовой вёрсткой (слои с объектами внутри листа, как у описания печати)
   помечается frozen: он собирается без слоёв проекта. У листов по слоям недостающие слои — предупреждение, не сбой. */
let IMPORT = null;   // файл, ждущий выбора: { name, size, album } — «Заменить / Добавить»; { name, size, file } — предупреждение о размере
const IMPORT_WARN = 25 * 2**20, PROJECT_CAP = 400 * 2**20;   // предел тела записи проекта — MAX_PROJECT_BODY в server.py (и локально, и в совместном режиме)
const isViewer = () => document.body.classList.contains("hub-viewer") || window.Collab?.role === "viewer";
const mb = n => Math.max(1, Math.round(n / 2**20));
const isReadySheet = s => Array.isArray(s?.layers) && s.layers.every(l => Array.isArray(l?.features)) || !!s?.panels?.some?.(p => Array.isArray(p?.layers));
function albumOfJson(j) {
  if (!j || typeof j !== "object") throw new Error("это не альбом и не проект ГРАДО 2");
  if (j.format === "grado2") { const p = window.migrateProject ? window.migrateProject(j) : j; if (!p.album) throw new Error("в проекте нет альбома"); return p.album; }   // формат проекта — по миграциям project.js
  if (Array.isArray(j.sheets)) { const p = { format: "grado2", version: j.version ?? 2, album: j }; return (window.migrateProject ? window.migrateProject(p) : p).album; }   // голый альбом идёт теми же миграциями проекта (сейчас к альбому ни одна не применяется)
  throw new Error("в файле нет листов альбома");
}
function readAlbumFile(file, confirmed) {
  if (isViewer()) return toast("Только просмотр: импорт листов доступен тому, кто правит проект.");
  if (file.size > PROJECT_CAP) return toast(`Файл ${mb(file.size)} МБ больше предела проекта (${mb(PROJECT_CAP)} МБ): импорт отменён.`);
  if (!confirmed && file.size > IMPORT_WARN) { IMPORT = { name: file.name, size: file.size, file }; renderSheets(); return; }
  busy(true); const rd = new FileReader();
  rd.onerror = () => { busy(false); toast("Файл не прочитан: " + (rd.error?.message || "ошибка чтения")); };
  rd.onload = () => { try {
    const a = albumOfJson(JSON.parse(rd.result)), list = (a.sheets || []).filter(s => s && typeof s === "object");
    if (!list.length) throw new Error("в файле нет листов");
    IMPORT = { name: file.name, size: file.size, album: { meta: safeObj(a.meta), sheets: list } };
    if (!ALBUM.sheets.length) importAlbum("replace"); else { renderSheets(); toast(`Файл «${file.name}»: ${list.length} л. Выберите: заменить или добавить.`); }
  } catch (e) { toast("Файл не открыт: " + (e instanceof SyntaxError ? "это не JSON" : e.message)); } finally { busy(false); } };
  rd.readAsText(file);
}
function importBarHTML() {
  if (!IMPORT) return "";
  if (IMPORT.file) return `<div class="pad row shbar" style="flex-wrap:wrap" id="shImpBar"><span class="note" style="padding:0 6px 0 0">Файл ${mb(IMPORT.size)} МБ: проект станет большим, сохранение и совместная работа будут медленнее. Продолжить?</span><button class="btn primary" data-shimp="go">Продолжить</button><button class="btn" data-shimp="cancel">Отмена</button></div>`;
  const n = IMPORT.album.sheets.length, c = ALBUM.sheets.length;
  return `<div class="pad row shbar" style="flex-wrap:wrap" id="shImpBar"><span class="note" style="padding:0 6px 0 0">«${esc(IMPORT.name)}»: ${n} л.</span><button class="btn primary" data-shimp="replace">Заменить ${c} ${shWord(c)} текущего альбома на ${n} из файла</button><button class="btn" data-shimp="add">Добавить после текущих</button><button class="btn" data-shimp="cancel">Отмена</button></div>`;
}
function missingLayersText(list) {
  const have = new Set(LYR.map(l => l.key)), miss = new Set(); let ns = 0, nv = 0;
  list.forEach(s => { if (s.frozen) return;
    const ks = [...(s.keys || []), ...(s.panels || []).flatMap(p => p?.keys || [])].filter(k => !have.has(k)); ks.forEach(k => miss.add(k)); if (ks.length) ns++;
    if (s.view && !VIEWS.some(v => v.id === s.view)) nv++; });
  const t = []; if (ns) t.push(`в ${ns} л. нет слоёв: ${[...miss].slice(0, 6).join(", ")}${miss.size > 6 ? ` и ещё ${miss.size - 6}` : ""} — они будут пустыми, пока не загружены данные`);
  if (nv) t.push(`в ${nv} л. нет вида карты — берётся текущая карта`);
  return t.join("; ");
}
function importAlbum(mode) {
  const imp = IMPORT; IMPORT = null;
  if (!imp || mode === "cancel") { renderSheets(); return; }
  if (mode === "go") { readAlbumFile(imp.file, true); renderSheets(); return; }
  if (isViewer()) { renderSheets(); return toast("Только просмотр: импорт листов доступен тому, кто правит проект."); }
  // проект после импорта не должен перерасти предел записи (сам файл — верхняя оценка добавляемого альбома)
  const now = projectJSON().length;
  if (now + imp.size > PROJECT_CAP) { renderSheets(); return toast(`Проект станет ${mb(now + imp.size)} МБ, а сохранить можно не больше ${mb(PROJECT_CAP)} МБ: импорт отменён.`); }
  const list = imp.album.sheets.map(s => { const x = { ...s }; if (x.scale != null && !Array.isArray(x.scale)) x.scale = okn(x.scale, 0); if (x.view != null) x.view = safeId(x.view);
    if (x.photos != null && !Array.isArray(x.photos)) delete x.photos; if (isReadySheet(x)) x.frozen = true; return x; });
  const old = mode === "add" ? ALBUM.sheets.length : 0;
  // id всегда новые, «imp_…»: старые «sec1_», «pptkrt_» — префиксы наборов, по ним buildAlbum удаляет листы (ссылок листов друг на друга в файлах нет)
  const t = Date.now().toString(36), had = new Set(ALBUM.sheets.map(s => s.id)); let k = 0;
  list.forEach(s => { do { s.id = `imp_${t}_${k++}`; } while (had.has(s.id)); });
  const warn = missingLayersText(list), was = ALBUM.sheets.length;
  window.hideSheetFrame?.();
  if (mode === "add") ALBUM.sheets.push(...list); else ALBUM.sheets.splice(0, was, ...list);
  const m = ALBUM.meta, empty = v => v == null || v === "" || (Array.isArray(v) && !v.length);   // заполненное в проекте остаётся, пустое берётся из файла
  ["object", "code", "stage", "org", "short", "place", "date", "ogdCodes"].forEach(k => { if (empty(m[k]) && !empty(imp.album.meta[k])) m[k] = imp.album.meta[k]; });
  m.builtAt = new Date().toISOString(); m.importedFrom = imp.name;
  window.markDirty?.(); renderSheets(); previewSheet(old);
  toast(`${mode === "add" ? "Добавлено" : "Загружено"} ${list.length} л. из файла «${imp.name}»${mode === "add" ? `, всего ${ALBUM.sheets.length}` : ""}.${warn ? " Внимание: " + warn + "." : ""}`);
}
/* Окно «Листы и альбом»: сверху строка состояния и действия, «Штамп…», список листов в одну строку и свойства выбранного листа.
   Раскладка по ширине тела окна (container query в index.html), поэтому одинаково внизу, справа и в плавающем окне. */
let SHI = 0, STAMP_OPEN = false, SHBUILD = 0, SHOTHER = null;
const SHM = { open: null, btn: null };
const touch = () => { ALBUM.meta.editedAt = new Date().toISOString(); window.markDirty?.(); };
window.touchAlbum = touch;
const track = async fn => { SHBUILD++; syncBusy(); try { return await fn(); } finally { SHBUILD--; syncBusy(); } };
function syncBusy() {
  const w = $("sheetsBody")?.querySelector(".shw"); if (!w) return;
  w.classList.toggle("isbusy", SHBUILD > 0);
  w.querySelectorAll(".shact .btn").forEach(b => { b.disabled = SHBUILD > 0 || (/^shP/.test(b.id) && !ALBUM.sheets.length); });
  syncAlbumStat();
}
const selIdx = () => {
  const n = ALBUM.sheets.length; if (!n) return -1;
  const f = window.selectedFrame?.(), k = f ? ALBUM.sheets.indexOf(f) : -1; if (k >= 0) SHI = k;
  return SHI = Math.min(Math.max(SHI, 0), n - 1);
};
window.syncSheetBadge = () => { const b = $("shBadge"), n = ALBUM.sheets.length; if (b) { b.hidden = !n; b.textContent = n; } };
window.syncSheetSel = () => { if (!$("wSheets").hidden) renderSheets(); };   // рамку выбрали на карте — строка и свойства следуют за ней
const sizeShort = s => (SIZE_T[s.size] || s.size || "").replace(" без штампа", "").replace(" (ГОСТ)", "") + (isPaper(s.size) && s.orient === "P" ? " книжн." : "");
const scaleText = s => ["tep", "title", "photos"].includes(s.kind) ? "" : s.panels ? `${s.panels.length} карты` : "1:" + fmt(Math.round(sheetScale(s)));
const stampSum = () => { const m = ALBUM.meta, p = [m.object, m.code, m.stage].filter(Boolean); return p.length ? "Штамп: " + p.join(" · ") : "Штамп: не заполнен"; };
const mi = (id, ic, t, h, title) => `<button role="menuitem" id="${id}" title="${esc(title || h)}"><i data-lucide="${ic}"></i><span class="mi"><b>${t}</b><small>${h}</small></span></button>`;
function rowInner(s, i, on) {
  const ic = (cond, name, tip) => cond ? `<span title="${tip}"><i data-lucide="${name}"></i></span>` : "";
  const sc = scaleText(s);
  return `<span class="n">${i + 1}</span><span class="t" title="${esc(s.title)}">${esc(s.title) || "<i>без названия</i>"}</span>`
    + (s.frozen ? `<span class="rdy" title="Готовая вёрстка из файла: слои и оформление записаны в самом листе">готовая</span>` : "")
    + `<span class="fs">${esc(sizeShort(s))}${sc ? `<span class="sc"> · ${sc}</span>` : ""}</span>`
    + `<span class="ic">${ic(s.legend && s.kind !== "tep", "list", "Легенда вида")}${ic(s.tep || s.kind === "tep", "table", "Таблица ТЭП")}${ic(s.kind === "photos", "camera", "Фотофиксация")}</span>`
    + `<span class="ra"><button class="tb" data-shup="${i}" title="Выше" aria-label="Выше"><i data-lucide="arrow-up"></i></button><button class="tb" data-shdel="${i}" title="Удалить лист" aria-label="Удалить лист"><i data-lucide="trash-2"></i></button></span>`;
}
function detHTML(s, i) {
  const vopts = `<option value="" ${s.kind !== "tep" && !s.view ? "selected" : ""}>текущая карта</option>` + VIEWS.map(v => `<option value="${esc(v.id)}" ${s.kind !== "tep" && v.id === s.view ? "selected" : ""}>вид «${esc(v.name)}»</option>`).join("")
    + `<option value="__tep" ${s.kind === "tep" ? "selected" : ""}>таблица ТЭП (все показатели)</option>`;
  const tepS = s.kind === "tep" || s.frozen ? "disabled" : "";
  const note = s.frozen ? "Готовая вёрстка из файла: слои и оформление записаны в самом листе." : s.panels ? "Две карты: у каждой свой масштаб; слои, оформление и рамки заданы шаблоном раздела." : s.keys ? "Лист раздела: слои, оформление и рамка заданы шаблоном раздела." : "";
  const content = s.frozen ? `<select disabled aria-label="Содержание листа" title="Готовая вёрстка из файла: слои и оформление записаны в самом листе"><option>готовая вёрстка</option></select>`
    : s.keys || s.panels ? `<select disabled aria-label="Содержание листа" title="Лист раздела: слои, оформление и рамка заданы шаблоном раздела"><option>слои раздела</option></select>` : `<select data-sk="view" aria-label="Содержание листа">${vopts}</select>`;
  const scale = `<select data-sk="scale" aria-label="Масштаб" ${tepS} ${s.panels ? "disabled title=\"Две карты: у каждой свой масштаб\"" : ""}>${s.panels ? "<option>у каждой карты свой</option>" : s.frozen ? `<option>${+s.scale ? "1:" + fmt(Math.round(+s.scale)) : "—"}</option>` : ""}<option value="0" title="Масштаб подобран так, чтобы территория поместилась на лист">авто 1:${fmt(sheetScale({ ...s, scale: 0 }))}</option>${(+s.scale && !SCALES.includes(+s.scale) ? [+s.scale, ...SCALES] : SCALES).map(v => `<option value="${+v}" ${v === +s.scale ? "selected" : ""}>1:${fmt(Math.round(v))}</option>`).join("")}</select>`;
  const t = (a, ic, tip, extra = "") => `<button class="tb" ${a} ${extra} title="${tip}" aria-label="${tip.split(".")[0].split(":")[0]}"><i data-lucide="${ic}"></i></button>`;
  const tools = (s.kind === "photos" ? t(`data-shphoto="${i}"`, "camera", `Добавить снимки (${(s.photos || []).length} из 12). Точка съёмки на карте берётся из GPS снимка`) + ((s.photos || []).length ? t(`data-shphotox="${i}"`, "image-off", "Убрать все снимки со слайда") : "") : "")
    + (["tep", "title"].includes(s.kind) || s.panels || s.frozen ? "" : t(`data-shframe="${i}"`, "frame", `Рамка листа на карте: тяните её мышью, чтобы выбрать, что попадёт на лист${s.center ? ". Сейчас лист сдвинут — «Вернуть» центрирует его на территории" : ""}`, `aria-pressed="${FRAME?.i === i}"`))
    + (s.center && s.kind !== "tep" ? t(`data-shreset="${i}"`, "locate-fixed", "Вернуть лист в центр территории") : "")
    + (["tep", "title"].includes(s.kind) || s.panels ? "" : t(`data-shsat="${i}"`, "satellite", "Спутник Яндекса по рамке листа — в AutoCAD, в МСК, 0,3 м на пиксель: чертёж DXF со снимком на своём месте. Shift+щелчок — сменить папку загрузок"))
    + (s.kind === "situation" ? t(`data-shpdf="${i}"`, "file-down", "PDF только этого листа") : "")
    + t(`data-shprev="${i}"`, "eye", "Просмотр листа")
    + (s.kind === "tep" ? "" : t(`data-shlay="${i}"`, "pencil-ruler", "Макет: правка любой надписи листа — текст, шрифт, кегль, цвет, обводка, поворот, место; свои надписи"));
  return `<div class="shdet" data-sh="${i}">`
    + `<label class="f">Название<input type="text" data-sk="title" value="${esc(s.title)}" aria-label="Название листа"></label>`
    + `<div class="g2"><label class="f">Формат<select data-sk="size" aria-label="Формат" ${s.frozen ? "disabled" : ""}>${Object.keys(SIZE_T).map(v => `<option value="${esc(v)}" ${v === s.size ? "selected" : ""}>${esc(SIZE_T[v])}</option>`).join("")}</select></label><label class="f">Масштаб${scale}</label></div>`
    + `<label class="f">Содержание${content}</label>`
    + `<div class="flags"><label title="Легенда вида"><input type="checkbox" data-sk="legend" ${s.legend ? "checked" : ""} aria-label="Легенда" ${tepS}>Легенда</label><label title="Таблица ТЭП"><input type="checkbox" data-sk="tep" ${s.tep ? "checked" : ""} aria-label="ТЭП" ${tepS}>Таблица ТЭП</label></div>`
    + (note ? `<div class="snote">${note}</div>` : "") + `<div class="tools">${tools}</div>`
    + `<div class="sheetprev"><img id="sheetPrev" alt="Просмотр листа" hidden></div></div>`;
}
function emptyHTML() {
  const pk = ALBUM.meta.peak, d = pk?.at ? stampText(pk.at).slice(0, 5) : "", elsewhere = (SHOTHER?.list || []).filter(p => p.album_n > 0 && p.name !== PROJ.name).slice(0, 2);
  return `<div class="shempty"><div>Листов пока нет. Добавьте лист или соберите альбом ППТ КРТ</div>`
    + (pk?.n ? `<div class="snote">Раньше в проекте было ${pk.n} ${shWord(pk.n)}${d ? ` (${d})` : ""}. Они удалены или не сохранились — ${window.HUB_MODE ? "откройте «История» и вернитесь к версии с листами" : "откройте «Проекты» и выберите сохранённую версию"}.</div>` : "")
    + (elsewhere.length ? `<div class="snote" id="shOther">Альбомы лежат в других проектах: ${elsewhere.map(p => `<a data-shopen="${esc(p.name)}" role="button" tabindex="0" title="Открыть проект">«${esc(p.name)}»</a> — ${p.album_n} ${shWord(p.album_n)}`).join("; ")}.</div>` : "")
    + `<div class="row"><button class="btn" data-shact="add"><i data-lucide="file-plus"></i>Добавить лист</button><button class="btn primary" data-shact="pptkrt"><i data-lucide="presentation"></i>Собрать альбом ППТ КРТ</button></div></div>`;
}
// проекты с альбомом — для строки в пустом окне; один запрос на открытие окна, не чаще раза в 20 с, только в обычном режиме (в совместном проекты на сервере другого вида)
function loadOther() {
  if (window.HUB_MODE || (SHOTHER && Date.now() - SHOTHER.t < 20000)) return;
  SHOTHER = { t: Date.now(), list: [] };
  fetch("/api/projects").then(r => r.json()).then(r => { SHOTHER = { t: Date.now(), list: r.projects || [] }; if (!ALBUM.sheets.length && !$("wSheets").hidden) renderSheets(); }).catch(() => { });
}
function renderSheets() {
  window.redrawFrames?.(true);             // рамки листов на карте и область загрузки данных
  const el = $("sheetsBody"); if (!el) return;
  const m = ALBUM.meta, n = ALBUM.sheets.length, sel = selIdx(), focusRow = el.contains(document.activeElement) && document.activeElement.classList?.contains("shrow") ? sel : -1;
  const inp = (k, ph) => `<label>${ph}<input type="text" data-meta="${k}" value="${esc(m[k] || "")}" aria-label="${ph}"></label>`;
  SHM.open = null; window.syncSheetBadge();
  if (!n) loadOther();
  el.innerHTML = `<div class="shw">`
    + `<div class="shtop"><div class="shstat" id="shStat"></div><div class="shact">`
    + `<button class="btn dd" id="shAdd" aria-haspopup="menu" aria-expanded="false" aria-controls="shMenuAdd" title="Добавить в альбом новый лист: рамку и штамп можно настроить в свойствах листа"><i data-lucide="file-plus"></i>Добавить лист<i data-lucide="chevron-down" class="chev"></i></button>`
    + `<button class="btn dd" id="shBuild" aria-haspopup="menu" aria-expanded="false" aria-controls="shMenuBuild" title="Собрать набор листов по шаблону или взять листы из файла"><i data-lucide="layout-template"></i>Собрать<i data-lucide="chevron-down" class="chev"></i></button>`
    + `<button class="btn primary" id="shPdf" ${n ? "" : "disabled"} title="Все листы одним PDF: рамка, штамп, масштаб, легенда"><i data-lucide="file-down"></i>PDF</button>`
    + `<button class="btn" id="shPptx" ${n ? "" : "disabled"} title="Все листы редактируемой презентацией PowerPoint: подписи — текстом, карты — фигурами по слоям"><i data-lucide="presentation"></i>PPTX</button></div></div>`
    + `<div class="shstamp"><button id="shStampBtn" aria-expanded="${STAMP_OPEN}" aria-controls="shStampBox" title="Основная надпись листов: объект, шифр, стадия, организация"><i data-lucide="chevron-right"></i><span id="shStampSum">${esc(stampSum())}</span></button>`
    + `<div class="shstbox" id="shStampBox" ${STAMP_OPEN ? "" : "hidden"}>${inp("object", "Объект")}${inp("code", "Шифр")}${inp("stage", "Стадия: ПП, П, Р")}${inp("org", "Организация")}`
    + `<label>Формат слайдов раздела<select id="shSlide" title="Формат слайдов раздела: меняет и уже собранные слайды">${Object.keys(SLIDE).map(v => `<option value="${esc(v)}" ${v === (m.slide || "P") ? "selected" : ""}>${esc(SIZE_T[v])}</option>`).join("")}</select></label></div></div>`
    + importBarHTML()
    + (n ? `<div class="shmain"><div class="shlist" role="listbox" aria-label="Листы альбома">${ALBUM.sheets.map((s, i) => `<div class="shrow" role="option" data-sh="${i}" aria-selected="${i === sel}" tabindex="${i === sel ? 0 : -1}">${rowInner(s, i)}</div>`).join("")}</div>${detHTML(ALBUM.sheets[sel], sel)}</div>` : emptyHTML())
    + `</div>`
    + `<div class="menu shmenu" id="shMenuAdd" role="menu" hidden>${mi("shAddA3", "file-plus", "Лист A3 (ГОСТ)", "Рамка и штамп по ГОСТ, карта и легенда")}${mi("shAddA1", "file-plus", "Лист A1 (ГОСТ)", "Большой лист по ГОСТ")}${mi("shAddSlide", "presentation", "Слайд 16:9", "Для презентации PPTX")}</div>`
    + `<div class="menu shmenu" id="shMenuBuild" role="menu" hidden>${mi("shSec1", "layout-template", "Раздел 1: существующее положение", "Слайды по территории; заменит листы этого набора", "Слайды раздела «Существующее положение»: месторасположение, ортофотопланы, ограничения, землепользование, Генплан, ПЗЗ, документация, соцобъекты. Недостающие слои выгружаются на всю площадь листов. Заменит листы этого набора")}`
    + `${mi("shPptKrt", "presentation", "Альбом ППТ КРТ", "Шаблон с красной шапкой; заменит листы этого набора", "Альбом «План реализации ППТ КРТ» по шаблону (А3, красная шапка), состав — как в «ГК Царицыно»: титул, месторасположение, ортофотоплан, фотофиксация, существующее использование с ЗОУИТ, Генплан, ППТ и ПМТ, ГПЗУ и АГР, землепользователи. Заменит листы этого набора")}`
    + `${mi("shSit", "map", "Ситуационный план A4", "Окружение и граница территории, один лист", "Ситуационный план на весь лист А4 без штампа и легенды: зелень, вода, дома и дороги, железная дорога, районы, названия улиц, граница территории. Нет границы — сначала выбрать её файл")}<hr>`
    + `${mi("shImport", "folder-open", "Из файла…", "Листы из проекта .grado2 или готовой вёрстки", "Взять листы альбома из файла: проекта .grado2 или готовой вёрстки. Файл читается в браузере, на сервер не уходит")}</div>`
    + `<input type="file" id="shImpFile" accept=".grado2,.json,application/json" hidden>`;
  icons(); syncBusy();
  if (IMPORT) $("shImpBar")?.querySelector("button")?.focus();   // выбор по клавиатуре: фокус на первую кнопку строки
  else if (focusRow >= 0) el.querySelector(`.shrow[data-sh="${focusRow}"]`)?.focus();
}
function shMenu(id, on, btn) {
  const m = $(id); if (!m) return;
  if (SHM.open && SHM.open !== id) shMenu(SHM.open, false);
  if (on) {
    SHM.btn = btn || SHM.btn; m.hidden = false; m.style.left = "0px"; m.style.top = "0px";
    const r = SHM.btn.getBoundingClientRect(), mw = m.offsetWidth, mh = m.offsetHeight;
    let y = r.bottom + 4; if (y + mh > innerHeight - 8) y = Math.max(8, r.top - mh - 4);
    m.style.left = Math.round(Math.min(Math.max(8, r.left), innerWidth - mw - 8)) + "px"; m.style.top = Math.round(y) + "px";
    SHM.open = id; SHM.btn.setAttribute("aria-expanded", true); m.querySelector("button:not(:disabled)")?.focus();
  } else { m.hidden = true; if (SHM.open === id) SHM.open = null; SHM.btn?.setAttribute("aria-expanded", false); }
}
addEventListener("pointerdown", e => { if (SHM.open && !e.target.closest(".shmenu") && !e.target.closest("#shAdd,#shBuild")) shMenu(SHM.open, false); });
const shEl = () => $("sheetsBody");
shEl().addEventListener("keydown", e => {
  if (e.key === "Escape" && IMPORT) { e.preventDefault(); e.stopPropagation(); importAlbum("cancel"); return; }   // Esc в строке выбора — «Отмена»; Enter нажимает кнопку в фокусе сам
  const menu = e.target.closest?.(".shmenu"), trg = e.target.closest?.("#shAdd,#shBuild");
  if (trg && e.key === "ArrowDown") { e.preventDefault(); shMenu(trg.id === "shAdd" ? "shMenuAdd" : "shMenuBuild", true, trg); return; }
  if (menu) {
    const items = [...menu.querySelectorAll("button:not(:disabled)")], i = items.indexOf(document.activeElement);
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); const b = SHM.btn; shMenu(menu.id, false); b?.focus(); }
    else if (e.key === "Tab") shMenu(menu.id, false);
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); items[(i + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length]?.focus(); }
    else if (e.key === "Home" || e.key === "End") { e.preventDefault(); items[e.key === "Home" ? 0 : items.length - 1]?.focus(); }
    return;
  }
  const row = e.target.closest?.(".shrow");
  if (row && ["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
    e.preventDefault(); const k = e.key === "Home" ? 0 : e.key === "End" ? ALBUM.sheets.length - 1 : Math.min(Math.max(+row.dataset.sh + (e.key === "ArrowDown" ? 1 : -1), 0), ALBUM.sheets.length - 1);
    pickSheet(k);
  } else if (row && (e.key === "Enter" || e.key === " ") && !e.target.closest("button")) { e.preventDefault(); pickSheet(+row.dataset.sh); }
});
function pickSheet(i) { SHI = i; showFrame(i); renderSheets(); }
shEl().addEventListener("dblclick", e => { if (e.target.id === "sheetPrev" && e.target.dataset.i) openLayout(+e.target.dataset.i); });
const refreshRow = i => { const r = shEl().querySelector(`.shrow[data-sh="${i}"]`); if (r) { r.innerHTML = rowInner(ALBUM.sheets[i], i); icons(); } };
shEl().addEventListener("change", e => {
  const t = e.target, row = t.closest("[data-sh]");
  if (t.dataset.meta) { ALBUM.meta[t.dataset.meta] = t.value; touch(); const s = $("shStampSum"); if (s) s.textContent = stampSum(); return; }
  if (t.id === "shImpFile") { if (isViewer()) { t.value = ""; return toast("Только просмотр: импорт листов доступен тому, кто правит проект."); } const f = t.files?.[0]; t.value = ""; if (f) readAlbumFile(f); return; }
  // формат слайдов раздела: новый раздел строится в нём, собранные слайды переводятся сразу (масштаб — заново, по рамке)
  if (t.id === "shSlide") { ALBUM.meta.slide = t.value; ALBUM.sheets.filter(x => String(x.id).startsWith("sec1_")).forEach(x => { x.size = t.value; x.scale = 0; });
    touch(); if (FRAME) showFrame(FRAME.i); renderSheets(); return; }
  if (!row || !t.dataset.sk) return; const s = ALBUM.sheets[+row.dataset.sh], k = t.dataset.sk;
  if (k === "view") { s.kind = t.value === "__tep" ? "tep" : "map"; s.view = s.kind === "tep" ? "" : t.value; if (s.kind === "tep") { s.title = s.title === newSheet().title || !s.title ? "Технико-экономические показатели" : s.title; if (FRAME?.i === +row.dataset.sh) showFrame(null); } }
  else s[k] = t.type === "checkbox" ? t.checked : k === "scale" ? +t.value : t.value;
  touch(); if (["size", "view"].includes(k)) renderSheets(); else refreshRow(+row.dataset.sh);
  if (FRAME?.i === +row.dataset.sh && ["size", "scale", "title"].includes(k)) showFrame(FRAME.i);
});
const addSheet = size => { const s = newSheet(); if (size) s.size = size; ALBUM.sheets.push(s); SHI = ALBUM.sheets.length - 1; touch(); renderSheets(); previewSheet(SHI); };
shEl().addEventListener("click", e => {
  const a = e.target.closest("[data-shopen]"); if (a) return window.openProject?.(a.dataset.shopen);
  const b = e.target.closest("button"); if (!b) { const r = e.target.closest(".shrow"); if (r) pickSheet(+r.dataset.sh); return; }
  const menu = b.closest(".shmenu"); if (menu) shMenu(menu.id, false);
  if (b.id === "shAdd" || b.id === "shBuild") { const id = b.id === "shAdd" ? "shMenuAdd" : "shMenuBuild"; return shMenu(id, SHM.open !== id, b); }
  if (b.id === "shStampBtn") { STAMP_OPEN = !STAMP_OPEN; b.setAttribute("aria-expanded", STAMP_OPEN); $("shStampBox").hidden = !STAMP_OPEN; if (STAMP_OPEN) $("shStampBox").querySelector("input")?.focus(); return; }
  if (b.id === "shAddA3" || b.dataset.shact === "add") addSheet("A3");
  if (b.id === "shAddA1") addSheet("A1");
  if (b.id === "shAddSlide") addSheet("P");
  if (b.id === "shPdf") albumFile("pdf");
  if (b.id === "shPptx") albumFile("pptx");
  if (b.id === "shSec1") buildSection();
  if (b.id === "shPptKrt" || b.dataset.shact === "pptkrt") track(() => window.buildAlbum?.("pptkrt"));
  if (b.id === "shSit") buildSituation();
  if (b.id === "shImport") { if (isViewer()) return toast("Только просмотр: импорт листов доступен тому, кто правит проект."); $("shImpFile").click(); }
  if (b.dataset.shimp) importAlbum(b.dataset.shimp);
  if (b.dataset.shpdf) albumFile("pdf", ALBUM.sheets[+b.dataset.shpdf]);
  if (b.dataset.shprev) previewSheet(+b.dataset.shprev);
  if (b.dataset.shlay) openLayout(+b.dataset.shlay);
  if (b.dataset.shsat) satFile(+b.dataset.shsat, e.shiftKey);
  if (b.dataset.shphoto) addPhotos(+b.dataset.shphoto);
  if (b.dataset.shphotox) { const i = +b.dataset.shphotox; if (confirmInline(b, `Убрать ${ALBUM.sheets[i].photos.length} снимков со слайда?`)) { ALBUM.sheets[i].photos = []; touch(); renderSheets(); } }
  if (b.dataset.shframe) { const i = +b.dataset.shframe; SHI = i; showFrame(FRAME?.i === i ? null : i); renderSheets(); }
  if (b.dataset.shreset) { const i = +b.dataset.shreset; delete ALBUM.sheets[i].center; touch(); if (FRAME?.i === i) showFrame(i); renderSheets(); }
  if (b.dataset.shup || b.dataset.shdel) showFrame(null);
  if (b.dataset.shup) { const i = +b.dataset.shup; if (i > 0) { [ALBUM.sheets[i - 1], ALBUM.sheets[i]] = [ALBUM.sheets[i], ALBUM.sheets[i - 1]]; SHI = i - 1; touch(); renderSheets(); } }
  if (b.dataset.shdel) { const i = +b.dataset.shdel; if (confirmInline(b, `Удалить лист «${ALBUM.sheets[i].title}»?`)) { ALBUM.sheets.splice(i, 1); SHI = Math.max(0, Math.min(SHI, ALBUM.sheets.length - 1)); touch(); renderSheets(); } }
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
      const di = tag(gp, 0x11), dir = di == null ? null : (a => u32(a) / (u32(a + 4) || 1))(u32(di + 8));   // направление съёмки, градусы от севера
      if (!(lat || lon)) return null;
      const at = [lon, lat]; at.dir = dir; return at;
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
      const bm = await createImageBitmap(f), k = Math.min(1, 1600 / Math.max(bm.width, bm.height)), c = document.createElement("canvas"), dir = gps?.dir ?? null;
      c.width = Math.round(bm.width * k); c.height = Math.round(bm.height * k); c.getContext("2d").drawImage(bm, 0, 0, c.width, c.height);
      (sh.photos ||= []).push({ name: f.name, data: c.toDataURL("image/jpeg", .82).split(",")[1], w: c.width, h: c.height, at: gps ? [gps[0], gps[1]] : null, dir });
      if (gps) geo++;
    }
    touch(); renderSheets(); previewSheet(i);
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
window.previewSheet = previewSheet; window.renderSheets = renderSheets; window.albumFile = albumFile; window.hideSheetFrame = () => showFrame(null);
