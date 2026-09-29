/* ГРАДО 2 · альбомы по образцам владельца (26.09.2026): «План реализации ППТ КРТ» — по его шаблону PowerPoint
   (А3 альбомный, красная шапка; оформление листа — album_io.py) и «Градостроительная концепция» — по образцу
   «ГК Царицыно». Листы собираются той же сборкой, что раздел 1 (buildSection в sheets.js), со своим префиксом id.
   Состав листов — по «ГК Царицыно» (решение владельца 27.09.2026), оформление — шаблон ППТ КРТ. */

const OKR_FULL = { ЦАО: "Центральный", САО: "Северный", СВАО: "Северо-Восточный", ВАО: "Восточный", ЮВАО: "Юго-Восточный", ЮАО: "Южный",
  ЮЗАО: "Юго-Западный", ЗАО: "Западный", СЗАО: "Северо-Западный", ЗелАО: "Зеленоградский", НАО: "Новомосковский", ТАО: "Троицкий" };

/* Округа и районы — эталон владельца (27.09.2026): 132 района, каждый целиком в одном округе, округ — сумма его районов.
   Слой отдаёт сервер (run_admin); метка сборки та же, что ADMIN_REV в server.py: другая метка в проекте — слой берётся заново. */
const ADM_REV = "эталон 27.09.2026";

// округ и район, где лежит территория
function homeAdm() {
  const adm = DATA["gisogd.admin"]?.fc.features || [], c = TERR && turf.centroid(TERR);
  const at = lvl => c && adm.find(x => x.properties["Уровень"] === lvl && safe(() => turf.booleanPointInPolygon(c, x)));
  return { adm, okrug: at("округ"), district: at("район") };
}
const okrAbbr = f => f ? LABEL_FN.adm({ get: k => f.properties[k] }) : "";

/* Карта административного деления в шаблоне ППТ КРТ. adm: "moscow" — вся Москва: районы тонко серым, округа чёрным
   с подписями, свой округ красным с заливкой; "okrug" — свой округ: внутри цветная картооснова ЕГКО (рисует сервер
   по маске mask), снаружи белый фон, районы чёрным с названиями, контур округа жирно — как в шаблоне.
   Территория — точкой (terrPoint): в масштабе Москвы она меньше миллиметра. */
function admPanelSpec(p) {
  const { adm, okrug } = homeAdm(), abbr = okrAbbr(okrug), scale = sheetScale(p), center = sheetCenter(p);
  const poly = f => /Polygon/.test(f.geometry?.type);
  const lab = { lf: "sans-bold", lh: .6, lcol: "#141414" };
  let layers;
  if (p.adm === "moscow") {
    const okrs = adm.filter(f => poly(f) && f.properties["Уровень"] === "округ"), dists = adm.filter(f => poly(f) && f.properties["Уровень"] === "район");
    layers = [
      { title: "свой округ — заливка", features: okrug ? [{ g: okrug.geometry, fill: "#f7d4d4", stroke: "#e93939", w: 0, a: 1 }] : [] },
      { title: "районы", features: dists.map(f => ({ g: f.geometry, fill: null, stroke: "#a3a3a3", w: .45, a: 0 })) },
      { title: "округа", features: okrs.map(f => ({ g: f.geometry, fill: null, stroke: "#1a1a1a", w: 1.3, a: 0, label: okrAbbr(f), ls: 3.2, ...lab })) },
      { title: "свой округ", features: okrug ? [{ g: okrug.geometry, fill: null, stroke: "#e93939", w: 2.8, a: 0 }] : [] }];
  } else {
    const home = okrug?.properties["Округ"] || okrug?.properties["Наименование"];
    const dists = adm.filter(f => poly(f) && f.properties["Уровень"] === "район" && f.properties["Округ"] === home);
    layers = [
      { title: "районы", features: dists.map(f => ({ g: f.geometry, fill: null, stroke: "#111111", w: .9, a: 0, label: LABEL_FN.adm({ get: k => f.properties[k] }), ls: 2.5, ...lab })) },
      { title: "округ", features: okrug ? [{ g: okrug.geometry, fill: null, stroke: "#111111", w: 2.6, a: 0 }] : [] }];
  }
  return { title: "", size: p.size, scale, center, layers, legend: [], territory: TERR?.geometry || null, terrPoint: 1.0, noFrame: !!p.noFrame,
    basemap: p.basemap || "", rect: p.rect, ...(p.adm === "okrug" && okrug ? { mask: okrug.geometry } : {}), ...(p.okrugTitle && abbr ? { okrugTitle: `${OKR_FULL[abbr] || abbr} административный округ` } : {}) };
}

// поля листа шаблона сверх обычной карты: стиль, выноска «рассматриваемая территория / Район …»
function albumExtra(sheet) {
  if (!sheet.style) return {};
  const out = { style: sheet.style };
  if (sheet.callout && TERR) {
    const { district } = homeAdm();
    out.callout = ["рассматриваемая территория", `Район ${district ? LABEL_FN.adm({ get: k => district.properties[k] }) : "—"}`];
    out.territory_lonlat = turf.centroid(TERR).geometry.coordinates;
  }
  // на картах листов — округ и район в углу, как в «ГК Царицыно»
  if (sheet.kind !== "title" && !sheet.panels && TERR) {
    const { okrug, district } = homeAdm(), abbr = okrAbbr(okrug);
    // «Троицкий» / «административный округ» — отдельными строками, ниже район (владелец 29.09.2026)
    out.mapNote = [okrug ? [OKR_FULL[abbr] || abbr, "административный округ"] : null, district ? ["район " + LABEL_FN.adm({ get: k => district.properties[k] })] : null].filter(Boolean);
  }
  return out;
}

/* ===== Листы 3–9: шапка ППТ КРТ, остальное — как в «ГК Царицыно» (решение владельца 27.09.2026) =====
   Карта слева без рамки (7, 44, 279 × 239 мм), справа колонка: «Условные обозначения», группы с подчёркнутым
   заголовком, списки документов в рамках, карточки участков (album_io.ConceptColumnFrame). Подписи — Century Gothic
   жирный с белым ореолом: улицы вдоль оси, названия территорий из OSM, округ и район в углу. Граница территории —
   пурпурный пунктир. Листы 5–9 — одна и та же рамка и масштаб, как в образце. */
const C_TERR = "#ff00ff", C_ROAD = "#a6a6a6", C_TW = 2.4;              // граница территории — жирный пунктир (владелец 29.09.2026)
const C_LBL = { lf: "sans-bold", lh: .55, lcol: "#141414" };
const C_BASE = { style: "pptkrt", look: "concept", fit: "terr", ctx: 1.25, rect: [7, 44, 279, 239], legend: false,
  labelFn: { "osm.roads": "street", "osm.landuse": "name2" }, labelMM: { "osm.roads": 4.3, "osm.landuse": 4.3, "egko.water_labels": 4.3 },
  labelStyle: { "osm.roads": C_LBL, "osm.landuse": C_LBL, "egko.water_labels": { lf: "sans-bold", lh: .55 } } };
// реки и водоёмы — подписями ЕГКО, голубым с белой обводкой (владелец 29.09.2026)
const C_WATER = { "egko.water_labels": { mode: "single", fill: "#1f8fe0", width: 1, marker: false, label: "Подпись", labelColor: "#1f8fe0" },
  "egko.water": { mode: "single", fill: "#a9cfe5", stroke: "#a9cfe5", width: 0, opacity: 0, label: "" } };   // контуры воды — только чтобы подпись легла вдоль реки
// дороги — полигонами: проезжая часть ЕГКО и УДС Яндекса (в ТиНАО картооснова ЕГКО почти пустая), без контура
const C_ROADS = fill => ({ "calc.uds_ya": { mode: "single", fill, stroke: fill, width: 0, opacity: 1 }, "egko.roads": { mode: "single", fill, stroke: fill, width: 0, opacity: 1 } });
const C_NAMES = { "osm.landuse": { mode: "single", fill: "#ffffff", stroke: "#ffffff", width: 0, opacity: 0, label: "Название" } };
const C_STREETS = (fill = C_ROAD) => ({ "osm.roads": { mode: "single", fill, width: 0, label: "Название", lineOff: true } });
const C_PLAN = { ...C_ROADS(C_ROAD), ...C_WATER, "egko.buildings": { mode: "single", fill: "#ffffff", stroke: "#8c8c8c", width: 1, opacity: 0 } };
const C_ONLY = { "osm.roads": { field: "Тип дороги", values: ["motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "living_street"] } };
const PPTKRT_C = [
  { ...C_BASE, concept: "ortho", title: "Ортофотоплан", basemap: "sat", bleed: true, rect: [0, 44, 420, 253], ctx: 2.2,
    keys: ["calc.uds_ya", "egko.roads", "osm.landuse", "osm.roads", "gisogd.admin", "egko.water", "egko.water_labels"],
    styles: { ...C_NAMES, ...C_STREETS("#f3d98c"), ...C_ROADS("#f3d98c"), ...C_WATER,
      "gisogd.admin": { mode: "single", opacity: 0, fill: "#e30613", stroke: "#e30613", width: 2, label: "" } },
    only: { ...C_ONLY, "gisogd.admin": { field: "Уровень", values: ["район"] } } },
  { ...C_BASE, concept: "photos", kind: "photos", title: "Материалы фотофиксации", rect: [7, 44, 198, 152], ctx: 1.3,
    keys: ["calc.uds_ya", "egko.roads", "egko.buildings", "osm.landuse", "osm.roads", "egko.water", "egko.water_labels"],
    styles: { ...C_NAMES, ...C_STREETS("#ffffff"), ...C_WATER, "calc.uds_ya": { mode: "single", fill: "#ffffff", stroke: "#a0a0a0", width: 1, opacity: 1 },
      "egko.roads": { mode: "single", fill: "#ffffff", stroke: "#a0a0a0", width: 1, opacity: 1 }, "egko.buildings": C_PLAN["egko.buildings"] }, only: C_ONLY },
  { ...C_BASE, concept: "use", title: "Схема существующего использования территорий с границами зон с особыми условиями использования территорий",
    keys: ["calc.uds_ya", "egko.roads", "egko.buildings", "nspd.parcels", "gisogd.red_lines", "osm.landuse", "osm.roads", "egko.water", "egko.water_labels"],
    styles: { ...C_NAMES, ...C_STREETS(), ...C_PLAN, "nspd.parcels": { mode: "single", fill: "#0000ff", stroke: "#0000ff", width: 1, opacity: 0, label: "" } }, only: C_ONLY },
  { ...C_BASE, concept: "gp", legend: true, title: "Генеральный план города Москвы. Фрагмент схемы «Карта функциональных зон»",
    keys: ["gisogd.func_zones", "gisogd.func_zones_tinao", "calc.uds_ya", "egko.roads", "egko.buildings", "osm.landuse", "osm.roads", "egko.water", "egko.water_labels"], extra: "genplan",
    styles: { ...C_NAMES, ...C_STREETS(), ...C_WATER, "calc.uds_ya": { mode: "single", fill: "#b4b4b4", stroke: "#b4b4b4", width: 0, opacity: .55 },
      "egko.roads": { mode: "single", fill: "#b4b4b4", stroke: "#b4b4b4", width: 0, opacity: .55 },
      "egko.buildings": { mode: "single", fill: "#ffffff", stroke: "#5f5f73", width: 1, opacity: 0 } },
    labelFn: { ...C_BASE.labelFn, "gisogd.func_zones": "gp", "gisogd.func_zones_tinao": "gp" },
    labelMM: { ...C_BASE.labelMM, "gisogd.func_zones": 8.5, "gisogd.func_zones_tinao": 8.5 },
    labelStyle: { ...C_BASE.labelStyle, "gisogd.func_zones": { lfs: ["sans", "sans-bold"], lcol: "#ffffff", lh: .18, lhc: "#3a3a3a" },
      "gisogd.func_zones_tinao": { lfs: ["sans", "sans-bold"], lcol: "#ffffff", lh: .18, lhc: "#3a3a3a" } }, only: C_ONLY },
  { ...C_BASE, concept: "ppt", title: "Схема обеспеченности территории разработанной документацией ППТ и ПМТ",
    keys: ["calc.uds_ya", "egko.roads", "egko.buildings", "gisogd.ppt", "gisogd.pmt", "osm.landuse", "osm.roads", "egko.water", "egko.water_labels"],
    styles: { ...C_NAMES, ...C_STREETS(), ...C_PLAN, "gisogd.pmt": { mode: "single", fill: "#00d000", stroke: "#00d000", width: 4, opacity: 0 } }, only: C_ONLY },
  { ...C_BASE, concept: "gpzu", title: "Схема обеспеченности территории разработанной документацией ГПЗУ и АГР",
    keys: ["calc.uds_ya", "egko.roads", "egko.buildings", "gisogd.gpzu", "gisogd.agr", "osm.landuse", "osm.roads", "egko.water", "egko.water_labels"],
    styles: { ...C_NAMES, ...C_STREETS(), ...C_PLAN,
      "gisogd.gpzu": { mode: "single", fill: "#7b7bf2", stroke: "#7b7bf2", hatch: true, hatchPat: "45", width: 1, opacity: 1 },
      "gisogd.agr": { mode: "single", fill: "#ff3b3b", stroke: "#ff3b3b", hatch: true, hatchPat: "135", width: 1, opacity: 1 } }, only: C_ONLY },
  { ...C_BASE, concept: "parcels", title: "Схема существующих землепользователей разрабатываемой территории", basemap: "sat",
    keys: ["nspd.parcels", "osm.landuse", "osm.roads", "egko.water", "egko.water_labels"],
    styles: { ...C_NAMES, ...C_STREETS(), ...C_WATER, "nspd.parcels": { mode: "single", fill: "#c9c9ff", stroke: "#c9c9ff", width: 1, opacity: 0, label: "" } }, only: C_ONLY },
];

// подписи улиц — как в образце: «ул. Промышленная», «Кавказский бульв.», «Тарный пр-д»
const W_ = w => new RegExp(`(^|\\s)${w}(?=\\s|$)`, "i");            // целое слово: \b в JS кириллицу не видит
const STREET_ABBR = [[W_("улица"), "ул."], [W_("проезд"), "пр-д"], [W_("бульвар"), "бульв."], [W_("шоссе"), "ш."], [W_("переулок"), "пер."],
  [W_("проспект"), "просп."], [W_("набережная"), "наб."], [W_("площадь"), "пл."], [W_("тупик"), "туп."]];
LABEL_FN.street = f => { let n = String(f.get("Название") || "").trim(); if (!n) return null;
  for (const [re, ab] of STREET_ABBR) if (re.test(n)) { n = n.replace(re, " ").replace(/\s+/g, " ").trim(); return ab === "ул." || ab === "пл." || ab === "просп." ? `${ab} ${n}` : `${n} ${ab}`; }
  return n; };
LABEL_FN.name2 = f => { const n = String(f.get("Название") || "").trim(); if (!n) return null;
  const words = n.split(/\s+/), lines = [""]; words.forEach(w => { const l = lines.length - 1; if (lines[l] && (lines[l] + " " + w).length > 26) lines.push(w); else lines[l] = (lines[l] + " " + w).trim(); });
  return lines.slice(0, 3).join("\n"); };

/* Вид функционального использования участков — по ВРИ участков ЕГРН (классификатор видов функционального
   использования Москвы; цвета — как в легенде «ГК Царицыно»). Участок без понятного ВРИ не закрашивается. */
const LAND_USE = [
  ["территории автодорог, улиц, местных проездов", "#ffffff", /улично-дорожн|автомобильн[а-яё]* дорог|12\.0\.1|\b7\.2\b/i],
  ["территории внешнего транспорта", "#a59c98", /железнодорож|\b7\.[1345]\b|аэропорт|трубопровод/i],
  ["коммунально-складского вида", "#dcd6b4", /склад|\b6\.9\b|хранени/i],
  ["производственного вида", "#d0d0ec", /производств|промышлен|\b6\.\d\b|предприяти|недропольз/i],
  ["жилищно-коммунального вида", "#d6c2bd", /коммунальн|\b3\.1\b/i],
  ["торгово-бытового вида", "#f4b393", /магазин|торгов|рын(о|к)|общественн[а-яё]* питан|бытов|\b4\.[2346]\b|\b3\.3\b/i],
  ["административно-делового вида", "#c9adc9", /делов|административ|офис|\b4\.1\b|\b3\.8\b|управлени/i],
  ["культурно-просветительского вида", "#f29c9c", /культур|\b3\.6\b|религиоз|\b3\.7\b/i],
  ["учебно-воспитательного вида", "#f5c7dc", /образован|школ|детск[а-яё]* сад|дошкольн|\b3\.5/i],
  ["лечебно-оздоровительного вида", "#c9e3f2", /здравоохран|медицин|больниц|поликлиник|\b3\.4/i],
  ["спортивного вида", "#bfe0bf", /спорт|\b5\.1/i],
  ["жилых домов многоквартирного вида", "#f5e39a", /многоквартир|среднеэтаж|многоэтаж|\b2\.[56]\b|\b2\.1\.1\b/i],
  ["индивидуальной жилой застройки", "#fbe3c6", /индивидуальн[а-яё]* жил|(^|[^а-яё])ижс([^а-яё]|$)|блокирован|личного подсобного|\b2\.[123]\b/i],
  ["садоводческих и огороднических территорий", "#e3edc7", /садовод|огородн|дачн|\b13\.\d/i],
  ["сельскохозяйственного использования", "#eef2d6", /сельскохоз|крестьян|фермер|\b1\.\d{1,2}\b/i],
  ["природных и озеленённых территорий", "#cfe6c0", /рекреац|природн|озелен|лесн|парк|\b5\.0\b|\b9\.\d|12\.0\.2/i]];
const landUseOf = p => { const v = String(p["ВРИ"] || p["Разрешенное использование"] || ""); return v ? LAND_USE.find(([, , re]) => re.test(v)) : null; };

const C_PALETTE = ["#f5a623", "#00c8e0", "#7b2d8e", "#f0503c", "#ff3fb4", "#2e9d4f", "#1565c0", "#8d6e63", "#ff8f00", "#00897b"];
function conceptDocs(out, bb, groups) {
  // документы в рамке: номер на карте (жирный 10 мм с белым ореолом) и список в рамках цвета документа, ближние к
  // территории — первыми; groups: [{key, title, color (одна на группу) | palette, text(p) → строка списка}]
  const c = TERR ? turf.centroid(TERR) : null, box = turf.bboxPolygon(bb), lists = [], pts = [];
  let no = 0, pi = 0;
  for (const g of groups) {
    const layer = out.layers.find(l => l.key === g.key), seen = new Map();
    (layer?.features || []).forEach(ft => {
      const f = { type: "Feature", geometry: ft.g, properties: ft.props || {} }; if (!/Polygon/.test(ft.g?.type)) return;
      const part = safe(() => inter(f, box)); if (!part) return;
      const id = f.properties.document_n || f.properties.document_g || f.properties._key, at = safe(() => turf.pointOnFeature(part));
      const dist = c && at ? turf.distance(c, at) : 0;
      if (!seen.has(id)) seen.set(id, { f, at, dist, fts: [] });
      const cur = seen.get(id); cur.fts.push(ft); if (at && dist < cur.dist) Object.assign(cur, { at, dist });
    });
    const docs = [...seen.values()].filter(d => d.at).sort((a, b) => a.dist - b.dist).slice(0, g.max || 12);
    if (!docs.length) continue;
    const items = docs.map(d => {
      const n = String(++no), color = g.color || C_PALETTE[pi++ % C_PALETTE.length];
      d.fts.forEach(ft => { ft.fill = color; ft.stroke = color; });
      pts.push({ g: d.at.geometry, nm: true, nudge: true, label: n, ls: 10, lf: "sans-bold", lh: .8, lcol: "#141414" });
      return { text: `${n}. ${g.text(d.f.properties, d)}`, color };
    });
    lists.push({ title: g.title, items });
  }
  if (pts.length) out.layers.push({ title: "Номера документов", features: pts });
  return lists;
}
const docLine = p => [p.document_1 || "", p.document_n ? `№${p.document_n}` : "", p.document_d ? `от ${dateRu(p.document_d)} г.` : ""].filter(Boolean).join(" ");

/* Подписи рек и водоёмов (владелец 29.09.2026): одна на название, на самом большом водоёме этой реки рядом с её
   подписями в ЕГКО (до 400 м; контур с другим названием не берётся, один контур — одно название). Пруд или озеро
   подписывается по центру вдоль своей длины (главная ось контура), река — у подписи ЕГКО вдоль русла около неё.
   Общие слова («пр.», «ручей») не подписываются. */
const WATER_GENERIC = /^(пр\.?|ручей|пруд|р\.|кан\.?|оз\.?|вдхр\.?)$/i;
function waterLabels(out, bb) {
  const wl = out.layers.find(l => l.key === "egko.water_labels"); if (!wl) return;
  const box = turf.bboxPolygon(bb), inBox = c => c[0] >= bb[0] && c[0] <= bb[2] && c[1] >= bb[1] && c[1] <= bb[3];
  const polys = (out.layers.find(l => l.key === "egko.water")?.features || []).filter(ft => /Polygon/.test(ft.g?.type) && safe(() => turf.booleanIntersects(ft.g, box)))
    .map(ft => { const f = { type: "Feature", geometry: ft.g, properties: {} }, pr = ft.props || {};
      return { f, a: m2(f), v: turf.coordAll(f), name: String(pr["Название"] || "").trim(), river: /река|ручей|канал/i.test(pr["Вид"] || "") }; });
  const kx = Math.cos(bb[1] * Math.PI / 180);
  const axis = pts => {                                        // главная ось облака точек: градусы против часовой от востока
    if (pts.length < 3) return 0;
    let mx = 0, my = 0; pts.forEach(([x, y]) => { mx += x * kx; my += y; }); mx /= pts.length; my /= pts.length;
    let sxx = 0, syy = 0, sxy = 0; pts.forEach(([x, y]) => { const dx = x * kx - mx, dy = y - my; sxx += dx * dx; syy += dy * dy; sxy += dx * dy; });
    let a = .5 * Math.atan2(2 * sxy, sxx - syy) * 180 / Math.PI; if (a > 90) a -= 180; if (a <= -90) a += 180; return a; };
  const dist = (pt, p) => safe(() => turf.booleanPointInPolygon(pt, p.f)) ? 0 : Math.min(...p.v.map(c => turf.distance(pt, c)));
  const byName = new Map();
  wl.features.forEach(ft => { const t = String(ft.label || "").trim(); if (!t || WATER_GENERIC.test(t) || ft.g?.type !== "Point") return;
    (byName.get(t) || byName.set(t, []).get(t)).push(ft); });
  const tc = turf.centroid(TERR), used = new Set(), labels = [];
  const nearest = arr => arr.reduce((x, y) => turf.distance(y, tc) < turf.distance(x, tc) ? y : x);
  // место подписи: прямоугольник текста на местности (ширина по числу знаков, кегль из листа) целиком в рамке и не
  // поперёк дорог — дороги-полигоны листа (владелец 30.09.2026: «р. Вороновка» пересекала дороги)
  const roads = ["calc.uds_ya", "egko.roads"].flatMap(key => out.layers.find(l => l.key === key)?.features || [])
    .filter(ft => /Polygon/.test(ft.g?.type)).map(ft => ({ g: ft.g, b: turf.bbox(ft.g) }));
  const mx = 111320 * kx, my = 110540, k = (out.scale || 2000) / 1000;
  const rect = (c, ang, text, ls) => {
    const L = text.length * .62 * ls * k / 2 + ls * k * .4, H = ls * .75 * k, a = ang * Math.PI / 180, ux = Math.cos(a), uy = Math.sin(a);
    const pts = [[-L, -H], [L, -H], [L, H], [-L, H]].map(([u, v]) => [c[0] + (u * ux - v * uy) / mx, c[1] + (u * uy + v * ux) / my]);
    return turf.polygon([[...pts, pts[0]]]); };
  // сколько дорог пересекает подпись (Infinity — не влезает в рамку)
  const hits = r => { const b = turf.bbox(r);
    if (b[0] < bb[0] || b[2] > bb[2] || b[1] < bb[1] || b[3] > bb[3]) return Infinity;
    return roads.filter(x => !(x.b[2] < b[0] || x.b[0] > b[2] || x.b[3] < b[1] || x.b[1] > b[3]) && safe(() => turf.booleanIntersects(x.g, r))).length; };
  byName.forEach((fts, t) => {
    const base = t.replace(/^(р\.|оз\.|пр\.)\s*/i, "").toLowerCase(), pts = fts.map(ft => turf.point(ft.g.coordinates));
    const inFrame = pts.filter(pt => inBox(pt.geometry.coordinates));
    const cand = polys.filter(p => !used.has(p) && (!p.name || p.name.toLowerCase() === base) && pts.some(pt => dist(pt, p) < .4));
    let at = null, ang = 0;
    if (cand.length) {
      const best = cand.reduce((x, y) => y.a > x.a ? y : x), part = safe(() => inter(best.f, box)) || best.f;
      used.add(best);
      if (!best.river) {                                       // пруд, озеро — по центру, вдоль длины
        const c = safe(() => turf.centerOfMass(part)); at = c && safe(() => turf.booleanPointInPolygon(c, part)) ? c : turf.pointOnFeature(part);
        ang = axis(turf.coordAll(part));
      } else {                                                 // река — вдоль русла, ближе к территории, не поперёк дорог
        const rv = polys.filter(p => p.river && (p === best || (best.name && p.name === best.name))).flatMap(p => p.v).filter(inBox);
        const step = Math.max(1, Math.ceil(rv.length / 120));
        const spots = [...inFrame.filter(pt => dist(pt, best) < .15), ...rv.filter((_, i) => i % step === 0).map(c => turf.point(c))]
          .sort((x, y) => turf.distance(x, tc) - turf.distance(y, tc));
        const ls = +fts[0].ls || 4.3;
        let bestHit = Infinity;
        search: for (const pt of spots) {
          const a = axis(rv.filter(c => turf.distance(pt, c) < .2)), r = a * Math.PI / 180, [x0, y0] = pt.geometry.coordinates;
          for (const off of [0, 25, -25, 50, -50]) {           // вдоль русла, при нужде — чуть в сторону от него (м)
            const c = [x0 - Math.sin(r) * off / mx, y0 + Math.cos(r) * off / my], n = hits(rect(c, a, t, ls));
            if (n < bestHit) { bestHit = n; at = turf.point(c); ang = a; }
            if (n === 0) break search;
          }
        }
        if (!at) {                                             // места в рамке нет — у подписи ЕГКО
          const own = inFrame.filter(pt => dist(pt, best) < .15);
          at = own.length ? nearest(own) : turf.pointOnFeature(part);
          ang = axis(rv.filter(c => turf.distance(at, c) < .2));
        }
      }
    } else if (inFrame.length) {
      at = nearest(inFrame);
      ang = axis(polys.flatMap(p => p.v).filter(c => turf.distance(at, c) < .2));
    }
    if (ang < -60) ang += 180;                                 // почти вертикальная подпись читается снизу вверх
    if (at) labels.push({ ...fts[0], g: at.geometry, la: ang, nudge: true });
  });
  wl.features = labels;
}

function conceptSheet(out, sheet, bb) {
  const ha = fmt(m2(TERR) / 1e4, 2), terr = { kind: "line", stroke: C_TERR, width: C_TW, dash: [C_TW, C_TW], label: `территории рассмотрения (${ha} га)` };
  out.look = "concept"; out.noFrame = true; out.callout = undefined; out.bleed = !!sheet.bleed;
  out.terrStyle = { stroke: C_TERR, width: C_TW, dash: [C_TW, C_TW] };
  const L = key => out.layers.find(l => l.key === key), bounds = { title: "Границы", items: [terr] };
  const box = turf.bboxPolygon(bb), inFrame = ft => /Polygon|Line/.test(ft.g?.type) && safe(() => turf.booleanIntersects(ft.g, box));
  const k = sheet.concept;
  waterLabels(out, bb);
  if (k === "ortho") {
    // выноска как в «ГК Царицыно»: полупрозрачная белая плашка без рамки под территорией, серый текст в три строки,
    // белый пунктир от плашки к точке внутри территории у её южного края
    const [w, s, e, n] = turf.bbox(TERR), south = safe(() => inter(TERR, turf.bboxPolygon([w, s, e, s + (n - s) * .3])));
    const tgt = (south && safe(() => turf.pointOnFeature(south))) || turf.pointOnFeature(TERR), [tx] = tgt.geometry.coordinates;
    out.layers.push({ title: "Выноска территории", features: [{ g: { type: "Point", coordinates: [tx, s] }, nodot: true, lead: tgt.geometry.coordinates,
      label: `Территория\nрассмотрения\n(${ha} га)`, ls: 3.2, lf: "sans", lcol: "#4a4a4a", lbox: true, lboxAlpha: .75, ldy: 12 }] });
    // граница района — в легенде, только если она видна на листе
    const box = turf.bboxPolygon(bb), dist = (L("gisogd.admin")?.features || []).some(ft => /Polygon/.test(ft.g?.type)
      && safe(() => turf.flatten(turf.polygonToLine({ type: "Feature", geometry: ft.g, properties: {} })).features.some(l => turf.booleanIntersects(l, box))));
    out.cLegend = [{ items: [terr, ...(dist ? [{ kind: "line", stroke: "#e30613", width: .5, label: "района" }] : []),
      { kind: "fill", fill: "#f3d98c", stroke: "#f3d98c", label: "территории автодорог, улиц и местных проездов" }] }];
  }
  if (k === "photos") {
    const tc = turf.centroid(TERR);
    // точки съёмки — синие стрелки по направлению снимка (EXIF), без направления — в сторону территории
    out.layers.push({ title: "Точки съёмки", features: (sheet.photos || []).map((ph, i) => ph.at ? { g: { type: "Point", coordinates: ph.at }, mk: "view", fill: "#1f3fbf",
      dir: ph.dir ?? turf.bearing(turf.point(ph.at), tc), label: String(i + 1), ls: 5.4, lf: "sans-bold", lcol: "#1f3fbf", lh: .5 } : null).filter(Boolean) });
    out.legend = [];
  }
  if (k === "use") {
    const pl = L("nspd.parcels"), use = [], seen = new Map();
    (pl?.features || []).forEach(ft => { const u = ft.props && landUseOf(ft.props); if (!u || !inFrame(ft)) return;
      use.push({ g: ft.g, fill: u[1], stroke: null, w: 0, a: 1 }); seen.set(u[0], u[1]); });
    out.layers.unshift({ title: "Вид функционального использования", features: use });
    const lgr = new Map();
    (L("gisogd.red_lines")?.features || []).forEach(ft => { if (!inFrame(ft)) return; (ft.lt || []).forEach(n => { const c = ltCode(n); if (c != null && !lgr.has(c)) lgr.set(c, n); }); });
    out.cLegend = [{ title: "Границы", items: [terr, { kind: "line", stroke: "#0000ff", width: .35, label: "земельных участков, поставленных на кадастровый учёт" }] },
      { title: "Застройка", items: [{ kind: "fill", fill: "#ffffff", stroke: "#8c8c8c", label: "существующая" }] },
      ...(seen.size ? [{ title: "Вид функционального использования участков территории (по ВРИ участков ЕГРН)",
        items: LAND_USE.filter(([n]) => seen.has(n)).map(([n, c]) => ({ kind: "fill", fill: c, stroke: "#7a7a7a", label: n })) }] : []),
      ...(lgr.size ? [{ title: "Линии градостроительного регулирования, действующие",
        items: [...lgr].sort((a, b) => a[0] - b[0]).map(([c, n]) => ({ kind: "lt", name: n, stroke: LGRC[c] || "#ff0000", label: LGRT[c] || n })) }] : [])];
  }
  if (k === "gp") {
    // номер и индекс зоны — белые с тёмной обводкой, как в образце; на светлой зоне — тёмные с белой обводкой
    ["gisogd.func_zones", "gisogd.func_zones_tinao"].forEach(key => (L(key)?.features || []).forEach(ft => {
      const c = String(ft.fill || "#888888").replace("#", ""), [r, g, b] = [0, 2, 4].map(i => parseInt(c.slice(i, i + 2), 16) / 255);
      if (.3 * r + .59 * g + .11 * b > .62) Object.assign(ft, { lcol: "#3a3a3a", lhc: "#ffffff", lh: .45 }); }));
    const zones = out.legend.filter(g => /функц/i.test(g.title)).flatMap(g => g.items);
    out.cLegend = [bounds, { title: "Функциональные зоны", items: [...zones.map(it => ({ kind: "fill", fill: it.fill, stroke: it.stroke || it.fill, a: it.a ?? 1, label: String(it.label).toLowerCase() })),
      { kind: "text", sample: "10", family: "sans", underline: true, label: "номера функциональных зон" },
      { kind: "text", sample: "500", family: "sans-bold", label: "индексы функциональных зон" }] }];
    if (out.table?.rows?.length) out.gpTable = { title: "Функциональные зоны и их параметры",
      cols: ["Номер функц. зоны", "Индекс функц. зоны", "Тип функц. зоны", "Прогнозируемый фонд застройки функц. зоны, тыс. кв. м"],
      rows: out.table.rows.map(r => [r[0], r[1], String(r[2]).toLowerCase(), r[3]]) };
    out.table = undefined;
  }
  if (k === "ppt") {
    out.cLists = conceptDocs(out, bb, [{ key: "gisogd.ppt", title: "Проекты планировки территории", text: docLine },
      { key: "gisogd.pmt", title: "Проекты межевания территории", color: "#00d000", text: p => p.document_1 ? docLine(p) : ["Проект межевания территории", p.document_n ? `№${p.document_n}` : "", p.document_d ? `от ${dateRu(p.document_d)} г.` : ""].filter(Boolean).join(" ") }]);
    out.cLegend = [bounds, { title: "Разработанная документация", items: [{ kind: "fill", hatch: true, fill: "#222222", stroke: "#222222", angle: 135, label: "проекты планировки территории" },
      { kind: "fill", stroke: "#00d000", width: .5, label: "проекты межевания территории" }] }];
  }
  if (k === "gpzu") {
    // ГПЗУ с номером на карте; свидетельство АГР на том же участке — второй строкой того же пункта, как в образце
    const agr = (L("gisogd.agr")?.features || []).filter(inFrame).map(ft => ({ type: "Feature", geometry: ft.g, properties: ft.props || {} }));
    const used = new Set();
    const lists = conceptDocs(out, bb, [{ key: "gisogd.gpzu", title: "ГПЗУ и свидетельства об утверждении АГР", color: "#231f20", text: (p, d) => {
      const a = agr.find((x, i) => !used.has(i) && safe(() => { const y = inter(x, d.f); return y && m2(y) > m2(x) * .5; }));
      if (a) used.add(agr.indexOf(a));
      const q = a?.properties;
      return `ГПЗУ ${p.document_n ? "№" + p.document_n : ""} ${p.document_d ? `от ${dateRu(p.document_d)} г.` : ""}`.replace(/\s+/g, " ").trim()
        + (q ? `\nАГР ${q.document_n ? "№" + q.document_n : ""} ${q.document_d ? `от ${dateRu(q.document_d)} г.` : ""}`.replace(/\s+$/, "") : ""); } }]);
    (L("gisogd.gpzu")?.features || []).forEach(ft => { ft.fill = "#7b7bf2"; ft.stroke = "#7b7bf2"; });   // цвет ГПЗУ — общий, рамки списка — чёрные
    out.cLists = lists;
    out.cLegend = [bounds, { title: "Разработанная документация", items: [
      { kind: "fill", hatch: true, fill: "#ff3b3b", stroke: "#ff3b3b", angle: 135, label: "архитектурно-градостроительное решение" },
      { kind: "fill", hatch: true, fill: "#7b7bf2", stroke: "#7b7bf2", angle: 45, label: "градостроительный план земельного участка" }] }];
  }
  if (k === "parcels") {
    const pl = L("nspd.parcels"), cards = [], marks = [];
    (pl?.features || []).forEach(ft => {
      const f = { type: "Feature", geometry: ft.g, properties: ft.props || {} }, x = /Polygon/.test(ft.g?.type) && safe(() => inter(f, TERR));
      if (!x || m2(x) < Math.min(50, m2(f) * .05)) return;
      ft.stroke = "#0000ff"; ft.fill = "#0000ff"; ft.w = 2.6;
      const p = f.properties, kn = p["Кадастровый номер"] || "—";
      cards.push({ area: m2(f), rows: [["Кадастровый номер", kn], ["Адрес", p["Адрес"] || "—"],
        ["Площадь (га)", fmt((+p["Площадь участка, м²"] || m2(f)) / 1e4, 4)], ["Вид разрешённого использования", p["ВРИ"] || "—"],
        ["Форма собственности", String(p["Форма собственности"] || p["Вид права"] || "—").toLowerCase()]] });
      const at = safe(() => turf.pointOnFeature(x));
      if (at) marks.push({ g: at.geometry, nodot: true, label: `Кадастровый номер\n${kn}`, ls: 3.2, lf: "sans-bold", lcol: "#231f20", lbox: true });
    });
    pl && out.layers.push({ title: "Кадастровые номера", features: marks });
    cards.sort((a, b) => b.area - a.area);
    out.cCards = { title: "Сведения о земельных участках в границах территории рассмотрения", items: cards.map(c => c.rows) };
    out.cLegend = [{ title: "Границы", items: [terr,
      { kind: "line", stroke: "#c9c9ff", width: .35, label: "земельных участков вне границ территории рассмотрения, поставленных на кадастровый учёт" },
      { kind: "line", stroke: "#0000ff", width: .7, label: "земельных участков в границах территории рассмотрения, поставленных на кадастровый учёт" }] }];
  }
  out.layers.forEach(l => l.features.forEach(ft => { delete ft.props; }));   // свойства нужны были только здесь
  if (!out.cLegend && k !== "photos") out.cLegend = [bounds];
}
window.conceptSheet = conceptSheet;

/* План реализации ППТ КРТ: шапка и листы 1–2 — по шаблону владельца, листы 3–9 — как в «ГК Царицыно». */
const PPTKRT = [
  { kind: "title", style: "pptkrt", title: "Титульный лист" },
  { style: "pptkrt", title: "Месторасположение рассматриваемой территории", legend: false, callout: true, panels: [
    { keys: ["gisogd.admin"], adm: "moscow", fit: "moscow", rect: [25, 48, 174, 229], noFrame: true },
    { keys: ["gisogd.admin"], adm: "okrug", fit: "okrug", rect: [212, 48, 188, 229], okrugTitle: true, noFrame: true }] },   // за округом — белый фон (владелец)
  ...PPTKRT_C,
];

async function buildAlbum(kind) {
  if (kind === "pptkrt") return buildSection(PPTKRT, "pptkrt_", "PA3", "План реализации ППТ КРТ");
}
window.buildAlbum = buildAlbum;
