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
  labelFn: { "osm.roads": "street", "osm.landuse": "name2" }, labelMM: { "osm.roads": 3.8, "osm.landuse": 3.8, "egko.water_labels": 3.8 },   // кегль чуть меньше (владелец 30.09.2026)
  labelStyle: { "osm.roads": C_LBL, "osm.landuse": C_LBL, "egko.water_labels": { lf: "sans-bold", lh: .55 } } };
// реки и водоёмы — подписями ЕГКО, голубым с белой обводкой (владелец 29.09.2026)
const C_WATER = { "egko.water_labels": { mode: "single", fill: "#1f8fe0", width: 1, marker: false, label: "Подпись", labelColor: "#1f8fe0" },
  "egko.water": { mode: "single", fill: "#a9cfe5", stroke: "#a9cfe5", width: 0, opacity: 0, label: "" } };   // на снимке вода видна сама — контуры только для подписи
// на белых схемах вода закрашена, иначе подпись реки висит над пустым местом
const C_WATER_VIS = { "egko.water": { mode: "single", fill: "#bfe0f5", stroke: "#bfe0f5", width: 0, opacity: 1, label: "" } };
// дороги — полигонами: проезжая часть ЕГКО и УДС Яндекса (в ТиНАО картооснова ЕГКО почти пустая), без контура
const C_ROADS = fill => ({ "calc.uds_ya": { mode: "single", fill, stroke: fill, width: 0, opacity: 1 }, "egko.roads": { mode: "single", fill, stroke: fill, width: 0, opacity: 1 } });
const C_NAMES = { "osm.landuse": { mode: "single", fill: "#ffffff", stroke: "#ffffff", width: 0, opacity: 0, label: "Название" } };
const C_STREETS = (fill = C_ROAD) => ({ "osm.roads": { mode: "single", fill, width: 0, label: "Название", lineOff: true } });
const C_PLAN = { ...C_ROADS(C_ROAD), ...C_WATER, ...C_WATER_VIS, "egko.buildings": { mode: "single", fill: "#ffffff", stroke: "#8c8c8c", width: 1, opacity: 0 } };
const C_ONLY = { "osm.roads": { field: "Тип дороги", values: ["motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "living_street"] } };
const PPTKRT_C = [
  { ...C_BASE, concept: "ortho", title: "Ортофотоплан", basemap: "sat", bleed: true, rect: [0, 44, 420, 253], ctx: 2.2,
    keys: ["calc.uds_ya", "egko.roads", "osm.landuse", "osm.roads", "gisogd.admin", "egko.water", "egko.water_labels"],
    styles: { ...C_NAMES, ...C_STREETS("#f3d98c"), ...C_ROADS("#f3d98c"), ...C_WATER,
      "gisogd.admin": { mode: "single", opacity: 0, fill: "#e30613", stroke: "#e30613", width: 2, label: "" } },
    only: { ...C_ONLY, "gisogd.admin": { field: "Уровень", values: ["район"] } } },
  { ...C_BASE, concept: "photos", kind: "photos", title: "Материалы фотофиксации", rect: [7, 44, 198, 152], ctx: 1.3,
    keys: ["egko.water", "calc.uds_ya", "egko.roads", "egko.buildings", "osm.landuse", "osm.roads", "egko.water_labels"],
    styles: { ...C_NAMES, ...C_STREETS("#ffffff"), ...C_WATER, ...C_WATER_VIS, "calc.uds_ya": { mode: "single", fill: "#ffffff", stroke: "#a0a0a0", width: 1, opacity: 1 },
      "egko.roads": { mode: "single", fill: "#ffffff", stroke: "#a0a0a0", width: 1, opacity: 1 }, "egko.buildings": C_PLAN["egko.buildings"] }, only: C_ONLY },
  { ...C_BASE, concept: "use", title: "Схема существующего использования территорий с границами зон с особыми условиями использования территорий",
    // линии Сводного плана и ЗОУИТ ГИС ОГД — типами линий REDLN97 (оформление задаёт conceptSheet); проезжая часть — серая
    // заливка, территории автодорог (участки под дорогами) — белые, как в «ГК Царицыно»
    keys: ["egko.water", "calc.uds_ya", "egko.roads", "egko.buildings", "nspd.parcels", "gisogd.zouit", "gisogd.szz", "gisogd.vodookhr", "gisogd.red_lines", "gisogd.airfield", "osm.landuse", "osm.roads", "egko.water_labels"],
    styles: { ...C_NAMES, ...C_STREETS(), ...C_PLAN, "nspd.parcels": { mode: "single", fill: "#0000ff", stroke: "#0000ff", width: .7, opacity: 0, label: "" },   // тоньше (владелец 30.09.2026)
      ...C_ROADS("#e3e3e3"), "egko.water": { mode: "single", fill: "#336699", stroke: "#336699", width: 0, opacity: 1, label: "" },   // вода — класс 22 шаблона
      "gisogd.airfield": { mode: "single", fill: "#000000", stroke: "#000000", width: 0, opacity: 0, label: "" },   // только надпись под легендой
      ...Object.fromEntries(["gisogd.zouit", "gisogd.szz", "gisogd.vodookhr"].map(k => [k, { mode: "single", fill: "#ff0000", stroke: "#ff0000", width: 1, opacity: 0, label: "" }])) }, only: C_ONLY },
  { ...C_BASE, concept: "gp", legend: true, title: "Генеральный план города Москвы. Фрагмент схемы «Карта функциональных зон»",
    keys: ["gisogd.func_zones", "gisogd.func_zones_tinao", "egko.water", "calc.uds_ya", "egko.roads", "egko.buildings", "osm.landuse", "osm.roads", "egko.water_labels"], extra: "genplan",
    styles: { ...C_NAMES, ...C_STREETS(), ...C_WATER, ...C_WATER_VIS, "calc.uds_ya": { mode: "single", fill: "#b4b4b4", stroke: "#b4b4b4", width: 0, opacity: .55 },
      "egko.roads": { mode: "single", fill: "#b4b4b4", stroke: "#b4b4b4", width: 0, opacity: .55 },
      "egko.buildings": { mode: "single", fill: "#ffffff", stroke: "#5f5f73", width: 1, opacity: 0 } },
    labelFn: { ...C_BASE.labelFn, "gisogd.func_zones": "gp", "gisogd.func_zones_tinao": "gp" },
    labelMM: { ...C_BASE.labelMM, "gisogd.func_zones": 8.5, "gisogd.func_zones_tinao": 8.5 },
    labelStyle: { ...C_BASE.labelStyle, "gisogd.func_zones": { lfs: ["sans", "sans-bold"], lcol: "#ffffff", lh: .18, lhc: "#3a3a3a" },
      "gisogd.func_zones_tinao": { lfs: ["sans", "sans-bold"], lcol: "#ffffff", lh: .18, lhc: "#3a3a3a" } }, only: C_ONLY },
  { ...C_BASE, concept: "ppt", title: "Схема обеспеченности территории разработанной документацией ППТ и ПМТ",
    keys: ["egko.water", "calc.uds_ya", "egko.roads", "egko.buildings", "gisogd.ppt", "gisogd.pmt", "osm.landuse", "osm.roads", "egko.water_labels"],
    styles: { ...C_NAMES, ...C_STREETS(), ...C_PLAN, "gisogd.pmt": { mode: "single", fill: "#00d000", stroke: "#00d000", width: 4, opacity: 0 } }, only: C_ONLY },
  { ...C_BASE, concept: "gpzu", title: "Схема обеспеченности территории разработанной документацией ГПЗУ и АГР",
    keys: ["egko.water", "calc.uds_ya", "egko.roads", "egko.buildings", "gisogd.gpzu", "gisogd.agr", "osm.landuse", "osm.roads", "egko.water_labels"],
    styles: { ...C_NAMES, ...C_STREETS(), ...C_PLAN,
      "gisogd.gpzu": { mode: "single", fill: "#7b7bf2", stroke: "#7b7bf2", hatch: true, hatchPat: "45", width: 1, opacity: 1 },
      "gisogd.agr": { mode: "single", fill: "#ff3b3b", stroke: "#ff3b3b", hatch: true, hatchPat: "135", width: 1, opacity: 1 } }, only: C_ONLY },
  { ...C_BASE, concept: "parcels", title: "Схема существующих землепользователей разрабатываемой территории", basemap: "sat",
    keys: ["nspd.parcels", "osm.landuse", "osm.roads", "egko.water", "egko.water_labels"],
    styles: { ...C_NAMES, ...C_STREETS(), ...C_WATER, "nspd.parcels": { mode: "single", fill: "#c9c9ff", stroke: "#c9c9ff", width: 1, opacity: 0, label: "" } }, only: C_ONLY },
];

// деревни и улицы без названия в OSM — на всех листах обязательно (правила подписей): подписи и адреса картоосновы ЕГКО
const C_HIDDEN = { mode: "single", fill: "#141414", stroke: "#141414", width: 0, opacity: 0, marker: false, label: "" };
PPTKRT_C.forEach(sh => { sh.keys.push("egko.place_labels", "egko.addresses");
  sh.styles = { ...sh.styles, "egko.place_labels": { ...C_HIDDEN, label: "Подпись" }, "egko.addresses": C_HIDDEN }; });

// подписи улиц — как в образце: «ул. Промышленная», «Кавказский бульв.», «Тарный пр-д»
const W_ = w => new RegExp(`(^|\\s)${w}(?=\\s|$)`, "i");            // целое слово: \b в JS кириллицу не видит
const STREET_ABBR = [[W_("улица"), "ул."], [W_("проезд"), "пр-д"], [W_("бульвар"), "бульв."], [W_("шоссе"), "ш."], [W_("переулок"), "пер."],
  [W_("проспект"), "просп."], [W_("набережная"), "наб."], [W_("площадь"), "пл."], [W_("тупик"), "туп."]];
LABEL_FN.street = f => { let n = String(f.get("Название") || "").trim(); if (!n) return null;
  for (const [re, ab] of STREET_ABBR) if (re.test(n)) { n = n.replace(re, " ").replace(/\s+/g, " ").trim(); return ab === "ул." || ab === "пл." || ab === "просп." ? `${ab} ${n}` : `${n} ${ab}`; }
  return n; };
// длинное название — в две строки примерно равной длины (владелец 30.09.2026), не больше двух
LABEL_FN.name2 = f => { const n = String(f.get("Название") || "").trim().replace(/\s+/g, " "); if (!n) return null;
  const w = n.split(" "); if (n.length <= 14 || w.length < 2) return n;
  let best = 1, d = Infinity;
  for (let i = 1; i < w.length; i++) { const x = Math.abs(w.slice(0, i).join(" ").length - w.slice(i).join(" ").length); if (x < d) { d = x; best = i; } }
  return w.slice(0, best).join(" ") + "\n" + w.slice(best).join(" "); };

/* Виды разрешённого использования земельных участков — шаблон владельца «ВРИ земельных участков_RGB» (слой
   «plan_organiz_ex», 28 классов; docs/standards/albums/ВРИ земельных участков_RGB.dxf; владелец 30.09.2026: «крась по этому
   шаблону»). Класс участка: сначала код ВРИ в тексте (4.9.1.1 → 4.9.1 → 4.9), затем слова (VRI_WORDS, по порядку).
   Земля без участка и участок с непонятным ВРИ — по землепользованию OSM, остальное — «отсутствие хозяйственной деятельности». */
const VRI_T = {
  1: ["многофункционального назначения", "#c07c7e", []],
  2: ["торгово-бытового обслуживания", "#f4b598", ["2.4", "3.3", "4.2", "4.3", "4.4", "4.6", "4.7", "4.8", "4.8.1", "4.8.2"]],
  3: ["социального обслуживания", "#ccf1eb", ["3.2", "3.2.1", "3.2.2", "3.2.3", "3.2.4"]],
  4: ["здравоохранения", "#b0d9d5", ["3.4", "3.4.1", "3.4.2", "3.10", "3.10.1", "3.10.2"]],
  5: ["дошкольного, начального и среднего общего образования", "#cde1b7", ["3.5", "3.5.1"]],
  6: ["среднего и высшего профессионального образования", "#d5a9aa", ["3.5.2"]],
  7: ["культурного развития и религиозного использования", "#f99f9f", ["3.6", "3.6.1", "3.6.2", "3.6.3", "3.7", "3.7.1", "3.7.2", "4.10"]],
  8: ["административно-делового назначения", "#cbb2cc", ["3.1.2", "3.8", "3.8.1", "3.8.2", "3.9.2", "4.0", "4.1", "4.5"]],
  9: ["спорта", "#b9e592", ["5.1", "5.1.1", "5.1.2", "5.1.3", "5.1.4", "5.1.5", "5.1.6", "5.1.7"]],
  10: ["туристического обслуживания и санаторной деятельности", "#b3e5c2", ["5.2", "5.2.1", "5.3", "5.5", "9.2.1"]],
  11: ["средне- и многоэтажной жилой застройки", "#f9e79f", ["2.5", "2.6"]],
  12: ["индивидуальной жилой застройки и садоводства", "#e5e57f", ["2.0", "2.1", "2.1.1", "2.2", "2.3", "13.0", "13.2", "13.3"]],
  13: ["общественно-жилого назначения", "#ee8e62", ["2.7"]],
  14: ["производственной деятельности", "#cfd1eb", ["3.9.3", "6.0", "6.2", "6.2.1", "6.3", "6.3.1", "6.4", "6.5", "6.6", "6.7", "6.11", "6.12"]],
  15: ["специального назначения", "#c7d1c7", ["3.9.1", "6.1", "6.8", "6.10", "8.0", "8.1", "8.2", "8.3", "8.4", "10.1", "10.2", "10.4", "11.2", "11.3", "12.1", "12.2"]],
  16: ["коммунального обслуживания", "#d7c6c1", ["2.7.1", "3.1", "3.1.1"]],
  17: ["обслуживания автотранспорта, складов и трубопроводного транспорта", "#dcd5b6", ["4.9", "4.9.1", "4.9.1.1", "4.9.1.2", "4.9.1.3", "4.9.1.4", "6.9", "6.9.1", "7.2.3", "7.5"]],
  18: ["природно-рекреационного назначения", "#c0e3b5", ["5.0", "9.2", "11.1", "12.0.2"]],
  19: ["охраны природных территорий", "#597f47", ["9.0", "9.1"]],
  20: ["внешнего транспорта", "#ada4a0", ["5.4", "7.0", "7.1", "7.1.1", "7.1.2", "7.3", "7.4"]],
  21: ["территории улиц и дорог", "#ffffff", ["7.2", "7.2.1", "7.2.2", "12.0", "12.0.1"]],
  22: ["водные объекты", "#336699", ["11.0"]],
  23: ["историко-культурной деятельности", "#fed0d0", ["9.3"]],
  24: ["отсутствия хозяйственной деятельности", "#e9e9de", ["12.3"]],
  25: ["растениеводства, огородничества", "#e8f2c7", ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.17", "10.3", "13.1"]],
  26: ["животноводства", "#c0c000", ["1.7", "1.8", "1.9", "1.10", "1.11", "1.12", "1.13", "1.15", "1.16", "1.18"]],
  27: ["сельскохозяйственного производства", "#b8a47f", ["1.0"]],
  28: ["научного обеспечения сельского хозяйства", "#dcd5b6", ["1.14"]]};
// слова в тексте ВРИ → класс шаблона; порядок важен (частное раньше общего)
const VRI_WORDS = [[/многофункц/i, 1], [/физкультур|оздоровительн[а-яё]* комплекс|(^|[^а-яё])спорт/i, 9],
  [/выращивани|овощн|плодово|ягодн/i, 25], [/(^|[^а-яё])газ([^а-яё]|опровод)|(^|[^а-яё])азс([^а-яё]|$)/i, 17], [/мотел|гостиниц|хостел|общежит/i, 2], [/обслуживани[ея] жилой застройки|общественно-жил/i, 13],
  [/историко-культурн/i, 23], [/научн[а-яё]* обеспечени[ея] сельск/i, 28], [/полев[а-яё]* участк|животновод|скотовод|зверовод|птицевод|свиновод|пчеловод|рыбовод|переработк[а-яё]* сельскохоз|обеспечени[ея] сельскохоз/i, 26],
  [/сельскохозяйственн[а-яё]* производств/i, 27], [/огородн/i, 25],
  [/придорожн|автосервис|заправ|обслуживани[ея] автотранспорт|автомойк|шиномонт|стоянк|автодепо|парковк|склад|трубопровод/i, 17],
  [/гараж|коммунальн/i, 16], [/магазин|торгов|рын(о|к)|общественн[а-яё]* питан|бытов|развлеч|предпринимат/i, 2], [/социальн/i, 3],
  [/здравоохран|медицин|больниц|поликлиник|ветеринар/i, 4], [/высш|профессиональн|колледж|техникум|училищ|университет|академи/i, 6],
  [/образован|школ|детск[а-яё]* сад|дошкольн/i, 5], [/культур|религиоз|храм|церк|выставоч/i, 7],
  [/делов|административ|офис|управлени|банков|страхов|научн/i, 8], [/туризм|туристич|санатор|охот|рыбалк|гольф/i, 10],
  [/многоквартир|среднеэтаж|многоэтаж/i, 11], [/садов|дачн|подсобн|индивидуальн[а-яё]* жил|(^|[^а-яё])ижс([^а-яё]|$)|блокирован|малоэтажн|личного подсобного|жил/i, 12],
  [/связ[иь]|ритуальн|кладбищ|оборон|безопасност|недропольз|гидротехн|правопоряд|наказан|древесин|лесн[а-яё]* плантац|космич|гидрометео/i, 15],
  [/охран[а-яё]* природ|особ[а-яё]* охран|заповедн/i, 19], [/рекреац|природн|озелен|парк|сквер|бульвар|курорт/i, 18],
  [/железнодорож|водн[а-яё]* транспорт|воздушн|аэропорт|причал/i, 20], [/улично-дорожн|автомобильн[а-яё]* дорог|общего пользования/i, 21],
  [/водн[а-яё]* объект|пруд|водо[её]м/i, 22], [/отсутстви[ея] хозяйственн/i, 24],
  [/производств|промышлен|предприяти|технопарк|энергетик/i, 14], [/растениевод|зерновых|овощевод|питомник|сельскохоз|крестьян|фермер/i, 25]];
const LAND_USE = Object.entries(VRI_T).map(([n, [name, color]]) => [name, color, null, +n]);
const VRI_CLS = n => LAND_USE.find(u => u[3] === n);
const ROAD_USE = VRI_CLS(21), WATER_USE = VRI_CLS(22);
const CODE_CLS = new Map(Object.entries(VRI_T).flatMap(([n, [, , codes]]) => codes.map(c => [c, +n])));
const landUseOf = p => { const v = String(p["ВРИ"] || p["Разрешенное использование"] || "").replace(/[Cc](?=[а-яё])/g, "с"); if (!v) return null;   // латинская «C» в «Cадоводство»
  for (const m of v.match(/\b\d{1,2}(?:\.\d{1,2}){1,3}\b/g) || []) {      // код ВРИ в тексте: «(2.1)», «13.2», «4.9.1.1»
    for (let c = m; c; c = c.includes(".") ? c.slice(0, c.lastIndexOf(".")) : "") if (CODE_CLS.has(c)) return VRI_CLS(CODE_CLS.get(c)); }
  const w = VRI_WORDS.find(([re]) => re.test(v)); return w ? VRI_CLS(w[1]) : null; };
// земля без участка ЕГРН и участок с непонятным ВРИ — по землепользованию OSM (владелец 30.09.2026: белым только УДС)
const OSM_USE = [[/^(farmland|orchard|plant_nursery|greenhouse_horticulture|vineyard)$/, 25], [/^(farmyard|animal_keeping)$/, 26],
  [/^(forest|wood|scrub|grassland|heath|meadow|grass|park|garden|recreation_ground|village_green)$/, 18], [/^nature_reserve$/, 19],
  [/^(cemetery|quarry|landfill|military)$/, 15], [/^allotments$/, 12], [/^residential$/, 12],
  [/^industrial$/, 14], [/^(commercial|retail)$/, 2], [/^garages$/, 16], [/^(depot|storage)$/, 17], [/^railway$/, 20],
  [/^religious$/, 7], [/^education$/, 5], [/^(pitch|playground)$/, 9], [/^(brownfield|construction)$/, 14]];
const LAND_BASE = VRI_CLS(18)[0];                             // всё, что не закрыто ни участком, ни OSM: белых пятен и «отсутствия
                                                              // хозяйственной деятельности» быть не должно (владелец 30.09.2026)
const NATURE_USE = VRI_CLS(18);                               // береговая полоса — природно-рекреационная
const osmUseOf = p => { for (const v of [p["Землепользование"], p["Природа"], p["Отдых"]]) { const hit = v && OSM_USE.find(([re]) => re.test(v)); if (hit) return VRI_CLS(hit[1]); } return null; };
/* ЗОУИТ ГИС ОГД → код знака Эталона ЛГР (moscow_lgr.json); вид зоны без знака — красным пунктиром без штриховки */
const ZOUIT_LGR = { "Водоохранная зона": 16, "Прибрежная защитная полоса": 17, "Береговая полоса": 41, "Зона затопления": 22,
  "Зона сильного подтопления": 64, "Зона умеренного подтопления": 65, "Зона слабого подтопления": 66, "Санитарно-защитная зона (ПЗЗ)": 5,
  "Зона охраняемого объекта": 44, "Зона военного объекта": 30, "Охранная зона радиотехнического объекта": 31, "Охранная зона ООПТ": 19,
  "Охранная зона объектов электроэнергетики": 32, "Охранная зона линий и сооружений связи": 34, "Особо охраняемая зелёная территория": 47,
  "Охранная зона трубопровода": 35, "Зона минимальных расстояний до трубопроводов": 39 };
// «Водоохранные зоны» → «водоохранных зон», «СЗЗ (установленная)» → «санитарно-защитных зон (установленных)» — для «граница …»
// подписи линий в легенде, как в «ГК Царицыно»
const LGR_LEG = { 1: "красные линии, обозначающие границы территорий общего пользования улично-дорожной сети города Москвы" };
const ZONE_GEN = { 5: "санитарно-защитных зон (установленных)", 62: "санитарно-защитных зон (расчётных)", 63: "санитарно-защитных зон (ориентировочных)" };
const zoneGen = t => { const c = Object.entries(LGRT).find(([, v]) => v === t)?.[0]; if (ZONE_GEN[c]) return ZONE_GEN[c];
  return t.toLowerCase().split(/\s+/).map(w => w.replace(/(ые|ие)$/, "ых").replace(/зоны$/, "зон").replace(/полосы$/, "полос").replace(/ая$/, "ой").replace(/зона$/, "зоны").replace(/территории$/, "территорий")).join(" "); };
// зоны подтопления — знаками примера «Хатминки» (владелец 30.09.2026: «скопируй условные зон подтопления»); рисует печать
const FLOOD_C = "#038240", FLOOD_T = { 64: "сильное подтопление (0–0,3 м)", 65: "умеренное подтопление (0,3–2,0 м)", 66: "слабое подтопление (2,0–3,0 м)" };
// зоны подтопления в Эталоне различаются только штриховкой: без неё граница умеренного и слабого — типом линии сильного
// (с засечками) цветом штриховки своего знака, затемнённым (владелец 30.09.2026)
const ZONE_LINE = { 65: { lt: 64, color: "#2f7fd8" }, 66: { lt: 64, color: "#2e9e78" } };
const zouitCode = (key, p) => key === "gisogd.vodookhr" ? 16 : key === "gisogd.szz" ? (/расч/i.test(p["Вид зоны"] || "") ? 62 : /ориент/i.test(p["Вид зоны"] || "") ? 63 : 5) : ZOUIT_LGR[p["Вид зоны"]];

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

/* Подписи рек и водоёмов (владелец 29–30.09.2026): одна на название, на самом большом водоёме этой реки рядом с её
   подписями в ЕГКО (до 400 м; контур с другим названием не берётся, один контур — одно название). Пруд или озеро
   подписывается по центру вдоль своей длины (главная ось контура). Река — прямо на русле: центр подписи на средней
   линии русла (середина поперечного сечения контура), поворот — по направлению русла в этом месте; узкая река без
   контура — на линии тонкой реки ЕГКО. Общие слова («пр.», «ручей») не подписываются. */
const WATER_GENERIC = /^(пр\.?|ручей|пруд|р\.|кан\.?|оз\.?|вдхр\.?)$/i;
function waterLabels(out, bb) {
  const wl = out.layers.find(l => l.key === "egko.water_labels"); if (!wl) return;
  const box = turf.bboxPolygon(bb), inBox = c => c[0] >= bb[0] && c[0] <= bb[2] && c[1] >= bb[1] && c[1] <= bb[3];
  const water = (out.layers.find(l => l.key === "egko.water")?.features || []).filter(ft => safe(() => turf.booleanIntersects(ft.g, box)));
  const polys = water.filter(ft => /Polygon/.test(ft.g?.type))
    .map(ft => { const f = { type: "Feature", geometry: ft.g, properties: {} }, pr = ft.props || {};
      return { f, a: m2(f), v: turf.coordAll(f), b: turf.bbox(f), name: String(pr["Название"] || "").trim(), river: /река|ручей|канал/i.test(pr["Вид"] || "") }; });
  const lines = water.filter(ft => /LineString/.test(ft.g?.type))
    .flatMap(ft => turf.flatten({ type: "Feature", geometry: ft.g, properties: {} }).features.map(f => ({ f, v: f.geometry.coordinates, name: String(ft.props?.["Название"] || "").trim() })));
  const kx = Math.cos(bb[1] * Math.PI / 180), mx = 111320 * kx, my = 110540, k = (out.scale || 2000) / 1000;
  const norm = a => { if (a > 90) a -= 180; if (a <= -90) a += 180; return a; };
  const axis = pts => {                                        // главная ось облака точек: градусы против часовой от востока
    if (pts.length < 3) return 0;
    let cx = 0, cy = 0; pts.forEach(([x, y]) => { cx += x * kx; cy += y; }); cx /= pts.length; cy /= pts.length;
    let sxx = 0, syy = 0, sxy = 0; pts.forEach(([x, y]) => { const dx = x * kx - cx, dy = y - cy; sxx += dx * dx; syy += dy * dy; sxy += dx * dy; });
    return norm(.5 * Math.atan2(2 * sxy, sxx - syy) * 180 / Math.PI); };
  const dist = (pt, p) => safe(() => turf.booleanPointInPolygon(pt, p.f)) ? 0 : Math.min(...p.v.map(c => turf.distance(pt, c)));
  // середина русла у точки c: поперечное сечение контура перпендикуляром к направлению a, отрезок воды ближе всего к c
  const midChannel = (c, a, ps) => {
    const r = a * Math.PI / 180, nx = -Math.sin(r), ny = Math.cos(r), R = 300;
    const cut = turf.lineString([[c[0] - nx * R / mx, c[1] - ny * R / my], [c[0] + nx * R / mx, c[1] + ny * R / my]]);
    let best = null;
    ps.forEach(p => {
      const ts = (safe(() => turf.lineIntersect(cut, p.f).features) || []).map(q => ((q.geometry.coordinates[0] - c[0]) * mx * nx + (q.geometry.coordinates[1] - c[1]) * my * ny))
        .sort((x, y) => x - y);
      for (let i = 0; i + 1 < ts.length; i++) {
        const m = (ts[i] + ts[i + 1]) / 2, at = [c[0] + nx * m / mx, c[1] + ny * m / my];
        if (ts[i + 1] - ts[i] < .5 || !safe(() => turf.booleanPointInPolygon(at, p.f))) continue;
        const d = ts[i] <= 0 && ts[i + 1] >= 0 ? 0 : Math.min(Math.abs(ts[i]), Math.abs(ts[i + 1]));
        if (!best || d < best.d) best = { d, at };
      }
    });
    return best && best.d < 30 ? best.at : null; };
  const byName = new Map();
  wl.features.forEach(ft => { const t = String(ft.label || "").trim(); if (!t || WATER_GENERIC.test(t) || ft.g?.type !== "Point") return;
    (byName.get(t) || byName.set(t, []).get(t)).push(ft); });
  const tc = turf.centroid(TERR), used = new Set(), labels = [];
  const nearest = arr => arr.reduce((x, y) => turf.distance(y, tc) < turf.distance(x, tc) ? y : x);
  // место подписи: прямоугольник текста на местности (ширина по числу знаков, кегль из листа) целиком в рамке и не
  // поперёк дорог — дороги-полигоны листа (владелец 30.09.2026: «р. Вороновка» пересекала дороги)
  const roads = ["calc.uds_ya", "egko.roads"].flatMap(key => out.layers.find(l => l.key === key)?.features || [])
    .filter(ft => /Polygon/.test(ft.g?.type)).map(ft => ({ g: ft.g, b: turf.bbox(ft.g) }));
  turf.flatten(turf.polygonToLine(TERR)).features.forEach(l => roads.push({ g: l.geometry, b: turf.bbox(l) }));   // и границу территории
  const rect = (c, ang, text, ls) => {
    const L = text.length * .62 * ls * k / 2 + ls * k * .4, H = ls * .75 * k, a = ang * Math.PI / 180, ux = Math.cos(a), uy = Math.sin(a);
    const pts = [[-L, -H], [L, -H], [L, H], [-L, H]].map(([u, v]) => [c[0] + (u * ux - v * uy) / mx, c[1] + (u * uy + v * ux) / my]);
    return turf.polygon([[...pts, pts[0]]]); };
  // сколько дорог пересекает подпись (Infinity — не влезает в рамку)
  const hits = r => { const b = turf.bbox(r);
    if (b[0] < bb[0] || b[2] > bb[2] || b[1] < bb[1] || b[3] > bb[3]) return Infinity;
    return roads.filter(x => !(x.b[2] < b[0] || x.b[0] > b[2] || x.b[3] < b[1] || x.b[1] > b[3]) && safe(() => turf.booleanIntersects(x.g, r))).length; };
  // лучшее место на русле из списка мест [[x, y], угол]: меньше пересечений, при равенстве — ближе к территории
  const pick = (spots, t, ls) => { let bestHit = Infinity, at = null, ang = 0;
    spots.sort((x, y) => turf.distance(x[0], tc) - turf.distance(y[0], tc));
    for (const [c, a] of spots) { const n = hits(rect(c, a, t, ls)); if (n < bestHit) { bestHit = n; at = turf.point(c); ang = a; } if (n === 0) break; }
    return at && { at, ang }; };
  const thin = (c, ls) => ls.filter(l => l.v.some(q => turf.distance(c, q) < .15));
  byName.forEach((fts, t) => {
    const base = t.replace(/^(р\.|оз\.|пр\.)\s*/i, "").toLowerCase(), pts = fts.map(ft => turf.point(ft.g.coordinates)), ls = +fts[0].ls || 3.8;
    const inFrame = pts.filter(pt => inBox(pt.geometry.coordinates));
    const cand = polys.filter(p => !used.has(p) && (!p.name || p.name.toLowerCase() === base) && pts.some(pt => dist(pt, p) < .4));
    let res = null;
    if (cand.length) {
      const best = cand.reduce((x, y) => y.a > x.a ? y : x), part = safe(() => inter(best.f, box)) || best.f;
      used.add(best);
      if (!best.river) {                                       // пруд, озеро — по центру, вдоль длины
        const c = safe(() => turf.centerOfMass(part));
        res = { at: c && safe(() => turf.booleanPointInPolygon(c, part)) ? c : turf.pointOnFeature(part), ang: axis(turf.coordAll(part)) };
      } else {                                                 // река — на середине русла, вдоль него
        const ps = polys.filter(p => p.river && (p === best || (best.name && p.name === best.name)));
        const rv = ps.flatMap(p => p.v).filter(inBox), step = Math.max(1, Math.ceil(rv.length / 120)), spots = [];
        [...inFrame.map(pt => pt.geometry.coordinates), ...rv.filter((_, i) => i % step === 0)].forEach(c => {
          const a = axis(rv.filter(q => turf.distance(c, q) < .2)), m = midChannel(c, a, ps);
          if (m && inBox(m)) spots.push([m, a]); });
        res = pick(spots, t, ls);
      }
    }
    if (!res) {                                                // узкая река — на линии тонкой реки ЕГКО рядом с подписью
      const near = [...new Set(pts.flatMap(pt => thin(pt.geometry.coordinates, lines)))].filter(l => !l.name || l.name.toLowerCase() === base);
      const rv = near.flatMap(l => l.v).filter(inBox), step = Math.max(1, Math.ceil(rv.length / 120));
      res = pick(rv.filter((_, i) => i % step === 0).map(c => [c, axis(rv.filter(q => turf.distance(c, q) < .15))]), t, ls);
    }
    if (!res && inFrame.length) {                              // ни контура, ни линии — у подписи ЕГКО
      const at = nearest(inFrame); res = { at, ang: axis(polys.flatMap(p => p.v).filter(c => turf.distance(at, c) < .2)) };
    }
    if (!res) return;
    let ang = res.ang; if (ang < -60) ang += 180;              // почти вертикальная подпись читается снизу вверх
    labels.push({ ...fts[0], g: res.at.geometry, la: ang, nudge: false });
  });
  wl.features = labels;
}

/* Обязательные подписи (владелец 30.09.2026: «д. Безобразово и ул. Придорожная на всех листах»): деревни и посёлки —
   по пояснительным подписям ЕГКО, на своём месте; улицы, которых нет среди названий OSM на листе, — по адресам зданий
   ЕГКО («Придорожная улица 7»): вдоль ближайшей дороги OSM рядом со зданиями, иначе вдоль ряда зданий. Слой — первым:
   эти подписи ставятся раньше всех. */
const PLACE_RE = /^(д|дер|с|п|пос|рп|х|село|деревня)\.?\s+(.+)$/i;
const titleRu = t => t.toLowerCase().replace(/(^|[\s-])([а-яё])/g, (m, a, b) => a + b.toUpperCase());
function namedPlaces(out, bb) {
  const L = key => out.layers.find(l => l.key === key), inBox = c => c[0] >= bb[0] && c[0] <= bb[2] && c[1] >= bb[1] && c[1] <= bb[3];
  const feats = [], kx = Math.cos(bb[1] * Math.PI / 180);
  (L("egko.place_labels")?.features || []).forEach(ft => { const t = String(ft.props?.["Подпись"] || ft.label || "").trim(), m = PLACE_RE.exec(t);
    if (!m || ft.g?.type !== "Point" || !inBox(ft.g.coordinates)) return;
    const pre = /^(с|село)$/i.test(m[1]) ? "с." : /^(п|пос|рп)$/i.test(m[1]) ? "пос." : "д.";
    feats.push({ g: ft.g, nm: true, label: `${pre} ${titleRu(m[2].replace(/["«»]/g, ""))}`, ls: 4.6, lf: "sans-bold", lh: .55, lcol: "#141414", la: 0, nudge: true }); });
  // улицы из адресов: «Придорожная улица 7 соор.1» → «Придорожная улица»
  const known = new Set((L("osm.roads")?.features || []).map(ft => String(ft.props?.["Название"] || "").toLowerCase()).filter(Boolean));
  const streets = new Map();
  (L("egko.addresses")?.features || []).forEach(ft => { if (ft.g?.type !== "Point" || !inBox(ft.g.coordinates)) return;
    const m = /^(.*?(улица|переулок|проезд|шоссе|тупик|бульвар|площадь|набережная|проспект|аллея)(?:\s+[А-ЯЁа-яё-]+)?)[,\s]+\d/i.exec(String(ft.props?.["Адрес"] || ""));
    if (!m) return; const n = m[1].trim(); if (known.has(n.toLowerCase())) return;
    (streets.get(n) || streets.set(n, []).get(n)).push(ft.g.coordinates); });
  // название — на безымянные дороги OSM у домов этой улицы (вершина ближе 80 м к дому): дальше подпись ставит печать по
  // правилу улиц — на самом длинном прямом участке без перекрёстков, по его направлению (владелец 30.09.2026: подпись
  // «ул. Придорожная» шла криво). Обязательная: на коротком участке тоже ставится, строго вдоль него
  // дом голосует за ближайшую дорогу OSM (до 60 м); улица — дороги, набравшие голоса её домов. В деревне участок
  // названной в OSM дороги («Сипягинское шоссе») подписывается местным названием по адресам («ул. Придорожная»)
  const ways = (L("osm.roads")?.features || []).filter(ft => /Line/.test(ft.g?.type))
    .map(ft => ({ ft, parts: (ft.g.type === "LineString" ? [ft.g.coordinates] : ft.g.coordinates).filter(l => l.length > 1).map(l => turf.lineString(l)) }));
  const axis = pts => { let mx = 0, my = 0; pts.forEach(([x, y]) => { mx += x * kx; my += y; }); mx /= pts.length; my /= pts.length;
    let sxx = 0, syy = 0, sxy = 0; pts.forEach(([x, y]) => { const dx = x * kx - mx, dy = y - my; sxx += dx * dx; syy += dy * dy; sxy += dx * dy; });
    let a = .5 * Math.atan2(2 * sxy, sxx - syy) * 180 / Math.PI; if (a > 90) a -= 180; if (a <= -90) a += 180; return a; };
  streets.forEach((pts, n) => {
    const label = LABEL_FN.street({ get: () => n }), votes = new Map();
    pts.forEach(p => { let best = null;
      ways.forEach(w => w.parts.forEach(ls => { const d = safe(() => turf.pointToLineDistance(p, ls, { units: "meters" })) ?? Infinity;
        if (d < 60 && (!best || d < best.d)) best = { d, w }; }));
      if (best) votes.set(best.w, (votes.get(best.w) || 0) + 1); });
    const win = [...votes].filter(([, v]) => v >= Math.max(2, pts.length * .25)).map(([w]) => w);
    const mid = [pts.reduce((s, p) => s + p[0], 0) / pts.length, pts.reduce((s, p) => s + p[1], 0) / pts.length];
    if (win.length) { win.forEach(w => Object.assign(w.ft, { label, must: true, mustAt: mid })); return; }   // mustAt — у домов
    const c = [pts.reduce((s, p) => s + p[0], 0) / pts.length, pts.reduce((s, p) => s + p[1], 0) / pts.length];
    let a = pts.length >= 2 ? axis(pts) : 0; if (a < -60) a += 180;        // дороги в OSM нет — вдоль ряда домов
    feats.push({ g: { type: "Point", coordinates: c }, nm: true, label, ls: 3.8, lf: "sans-bold", lh: .55, lcol: "#141414", la: a, nudge: true }); });
  ["egko.place_labels", "egko.addresses"].forEach(k => { const l = L(k); if (l) l.features = []; });
  if (feats.length) out.layers.unshift({ title: "Населённые пункты и улицы", features: feats });
}

function conceptSheet(out, sheet, bb) {
  const ha = fmt(m2(TERR) / 1e4, 2), terr = { kind: "line", stroke: C_TERR, width: C_TW, dash: [C_TW, C_TW], label: `территории рассмотрения (${ha} га)` };
  out.look = "concept"; out.noFrame = true; out.callout = undefined; out.bleed = !!sheet.bleed;
  // полупрозрачная белая маска за границей территории — на схемах с белой основой, как в примере «Хатминки»; на снимке и
  // на фрагменте Генплана её нет (владелец 30.09.2026)
  out.terrMask = sheet.basemap !== "sat" && !["gp", "ortho"].includes(sheet.concept) ? .55 : undefined;
  out.terrStyle = { stroke: C_TERR, width: C_TW, dash: [C_TW, C_TW] };
  const L = key => out.layers.find(l => l.key === key), bounds = { title: "Границы", items: [terr] };
  const box = turf.bboxPolygon(bb), inFrame = ft => /Polygon|Line/.test(ft.g?.type) && safe(() => turf.booleanIntersects(ft.g, box));
  const k = sheet.concept;
  waterLabels(out, bb);
  // тонкие реки ЕГКО нужны только для подписей ручьёв: на снимке вода видна сама (владелец 30.09.2026: голубых линий
  // на листе 3 быть не должно)
  if (sheet.basemap === "sat") (out.layers.find(l => l.key === "egko.water")?.features || []).forEach(ft => { if (/Line/.test(ft.g?.type)) ft.nl = true; });
  namedPlaces(out, bb);
  if (k === "ortho") {
    // выноска как в «ГК Царицыно»: полупрозрачная белая плашка без рамки, серый текст в три строки, белый пунктир к точке
    // внутри территории; плашка — над территорией, а если до верхнего края листа меньше 35 мм — под ней (правила подписей)
    const [w, s, e, n] = turf.bbox(TERR), up = (bb[3] - n) * 110540 / ((out.scale || 2000) / 1000) >= 35;
    const edge = safe(() => inter(TERR, turf.bboxPolygon(up ? [w, n - (n - s) * .3, e, n] : [w, s, e, s + (n - s) * .3])));
    const tgt = (edge && safe(() => turf.pointOnFeature(edge))) || turf.pointOnFeature(TERR), [tx] = tgt.geometry.coordinates;
    out.layers.push({ title: "Выноска территории", features: [{ g: { type: "Point", coordinates: [tx, up ? n : s] }, nodot: true, lead: tgt.geometry.coordinates,
      label: `Территория\nрассмотрения\n(${ha} га)`, ls: 4.5, lf: "sans", lcol: "#4a4a4a", lbox: true, lboxAlpha: .75, ldy: up ? -22 : 16 }] });
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
    // снизу вверх: вся рамка — природные территории, поверх — землепользование OSM (крупные раньше мелких), поверх —
    // участки ЕГРН по ВРИ; УДС белые сверху. Белых пятен, кроме улиц и дорог, нет (владелец 30.09.2026)
    const pl = L("nspd.parcels"), use = [], seen = new Map(), base = LAND_USE.find(([n]) => n === LAND_BASE);
    const seeds = [];                                            // закрашенные участки и контуры OSM — для продолжения зон
    const put = (g, u, seed) => { use.push({ g, fill: u[1], stroke: null, w: 0, a: 1 }); seen.set(u[0], u[1]); if (seed) seeds.push({ g, u }); };
    put(turf.bboxPolygon(bb).geometry, base);
    (L("osm.landuse")?.features || []).filter(inFrame).map(ft => ({ ft, u: ft.props && osmUseOf(ft.props), a: m2({ type: "Feature", geometry: ft.g, properties: {} }) }))
      .filter(x => x.u && /Polygon/.test(x.ft.g.type)).sort((x, y) => y.a - x.a).forEach(x => put(x.ft.g, x.u, true));
    // участок без ВРИ («обособленный участок» единого землепользования — ВРИ в карточке родителя), больше чем на треть
    // под проезжей частью, — территория автодорог (владелец 30.09.2026: участки под дорогами должны быть белыми)
    const roadPolys = ["calc.uds_ya", "egko.roads"].flatMap(key => L(key)?.features || []).filter(inFrame)
      .map(ft => ({ f: { type: "Feature", geometry: ft.g, properties: {} }, b: turf.bbox(ft.g) }));
    // доля участка под проезжей частью; больше половины — территория автодорог при любом ВРИ (внутренние проезды СНТ
    // стоят на учёте как «для ведения садоводства»), без ВРИ — больше десятой доли (узкие полосы вдоль шоссе)
    const roadShare = ft => { const f = { type: "Feature", geometry: ft.g, properties: {} }, b = turf.bbox(f), a = m2(f); let r = 0;
      roadPolys.forEach(x => { if (x.b[2] < b[0] || x.b[0] > b[2] || x.b[3] < b[1] || x.b[1] > b[3]) return; const y = safe(() => inter(f, x.f)); if (y) r += m2(y); });
      return a > 0 ? r / a : 0; };
    const roadLots = [];                                          // территории дорог — поверх береговой полосы (ниже)
    (pl?.features || []).forEach(ft => { if (!inFrame(ft) || !ft.props) return;
      const sh = roadShare(ft), u = sh > .5 || (!ft.props["ВРИ"] && sh > .1) ? ROAD_USE : landUseOf(ft.props); if (!u) return;
      put(ft.g, u, u !== ROAD_USE && u !== WATER_USE); if (u === ROAD_USE) roadLots.push(ft.g); });
    // внутри береговой полосы — всё природные и озеленённые территории (владелец 30.09.2026), поверх участков
    (L("gisogd.zouit")?.features || []).forEach(ft => { if (ft.props?.["Вид зоны"] !== "Береговая полоса" || !/Polygon/.test(ft.g?.type)) return;
      const part = safe(() => inter({ type: "Feature", geometry: ft.g, properties: {} }, turf.bboxPolygon(bb))); if (part) put(part.geometry, NATURE_USE); });
    // участки, сформированные под дороги, — выше и в приоритете над зонами рек (владелец 30.09.2026); белым — только они,
    // без выдуманных полос вокруг проезжей части (владелец 30.09.2026: «убери обводку у всех дорог»)
    roadLots.forEach(g => put(g, ROAD_USE));
    // где ни участка, ни OSM — продолжение ближайших зон (владелец 30.09.2026: «экстраполировать ближайшие зоны»): точки по
    // границам закрашенных контуров → ячейки ближайшего соседа (Вороного) цветом своего контура, под всеми заливками
    const pts = [], seenPt = new Set(), per = seeds.reduce((a, x) => a + (safe(() => turf.length(turf.polygonToLine({ type: "Feature", geometry: x.g, properties: {} }), { units: "meters" })) || 0), 0);
    const step = Math.max(8, per / 6000);                         // не больше ~6000 точек на лист
    seeds.forEach(({ g, u }) => (g.type === "Polygon" ? [g.coordinates] : g.coordinates).forEach(poly => {
      const ring = turf.lineString(poly[0]), L0 = turf.length(ring, { units: "meters" });
      for (let d = 0; d < L0; d += step) { const c = turf.along(ring, d, { units: "meters" }).geometry.coordinates;
        if (c[0] < bb[0] || c[0] > bb[2] || c[1] < bb[1] || c[1] > bb[3]) continue;
        const key = c[0].toFixed(5) + "," + c[1].toFixed(5); if (seenPt.has(key)) continue; seenPt.add(key);   // ~1 м: совпадающие точки ломают ячейки
        pts.push(turf.point(c, { fill: u[1] })); } }));
    const dx = (bb[2] - bb[0]) * .02, dy = (bb[3] - bb[1]) * .02;          // рамка с запасом: точки на краю ломают ячейки
    const cells = pts.length > 2 ? safe(() => turf.voronoi(turf.featureCollection(pts), { bbox: [bb[0] - dx, bb[1] - dy, bb[2] + dx, bb[3] + dy] })) : null;
    if (cells) use.splice(1, 0, ...cells.features.map((c, i) => c && ({ g: c.geometry, fill: pts[i].properties.fill, stroke: pts[i].properties.fill, w: .6, a: 1 })).filter(Boolean));
    out.layers.unshift({ title: "Вид функционального использования", features: use });
    seen.set(ROAD_USE[0], ROAD_USE[1]);                         // территории улиц и дорог — белые, в легенде всегда
    if ((L("egko.water")?.features || []).some(inFrame)) seen.set(WATER_USE[0], WATER_USE[1]);   // вода — класс 22 шаблона
    // линии Сводного плана: код знака каждой линии; зона, у которой есть своя линия, по контуру второй раз не рисуется
    const lgr = new Map();
    (L("gisogd.red_lines")?.features || []).forEach(ft => { if (!inFrame(ft)) return;
      (ft.lt || []).forEach(n => { const c = ltCode(n); if (c != null && !lgr.has(c)) lgr.set(c, n); });
      (ft.miss || []).forEach(([c]) => { if (c != null && !lgr.has(+c)) lgr.set(+c, null); }); });
    // ЗОУИТ — как в «ГК Царицыно»: только граница зоны красным типом линии REDLN97 своего кода Эталона ЛГР, засечки
    // внутрь (кольцо против часовой — зона слева, вариант «t»); кода без типа линии — штрихом знака. Без штриховки
    const zk = new Map();
    // зоны одного вида сначала сливаются в одну фигуру (в пределах рамки с запасом): полосы подтопления ГИС ОГД идут
    // внахлёст, и на общей границе засечки смотрели в обе стороны (владелец 30.09.2026)
    const clip = turf.bboxPolygon([bb[0] - (bb[2] - bb[0]) * .05, bb[1] - (bb[3] - bb[1]) * .05, bb[2] + (bb[2] - bb[0]) * .05, bb[3] + (bb[3] - bb[1]) * .05]);
    const byCode = new Map();
    ["gisogd.zouit", "gisogd.szz", "gisogd.vodookhr"].forEach(key => { const l = L(key); if (!l) return;
      l.features.filter(inFrame).forEach(ft => { const c = zouitCode(key, ft.props || {});
        if (c != null && lgr.has(c)) return;                     // граница уже есть линией Сводного плана
        const part = safe(() => inter({ type: "Feature", geometry: ft.g, properties: {} }, clip)); if (!part) return;
        const k = c ?? "?"; byCode.set(k, [...(byCode.get(k) || []), part]); });
      l.features = []; });
    // подтопление вложено: слабое включает умеренное и сильное, умеренное — сильное; без этого граница слабого шла
    // по границе умеренного с засечками в другую сторону (владелец 30.09.2026)
    const nested = { 66: [65, 64], 65: [64] };
    Object.entries(nested).forEach(([k, inner]) => { if (byCode.has(+k)) byCode.set(+k, [...byCode.get(+k), ...inner.flatMap(c => byCode.get(c) || [])]); });
    const zoneFeats = [];
    byCode.forEach((parts, k) => {
      const c = k === "?" ? null : k, lt = c != null ? Linetypes.forCode(ZONE_LINE[c]?.lt ?? c, -1) : null;
      const one = parts.slice(1).reduce((acc, p) => safe(() => turf.union(turf.featureCollection([acc, p]))) || acc, parts[0]);
      const lines = safe(() => turf.polygonToLine(turf.rewind(one)));
      const g = lines && (lines.type === "FeatureCollection" ? { type: "MultiLineString", coordinates: lines.features.flatMap(f => f.geometry.type === "LineString" ? [f.geometry.coordinates] : f.geometry.coordinates) } : lines.geometry);
      if (!g) return;
      if (c != null && !zk.has(c) && !FLOOD_T[c]) zk.set(c, lt || null);
      const ml = g.type === "LineString" ? { type: "MultiLineString", coordinates: [g.coordinates] } : g;
      if (FLOOD_T[c]) { zoneFeats.push({ code: c, g: ml, flood: c, lc: FLOOD_C, w: 1.3 }); return; }   // подтопление — знаками «Хатминки»
      zoneFeats.push({ code: c, g: ml, lt: lt ? [lt] : [], miss: lt || c == null ? [] : [[c, ""]], lc: LGRC[c] || "#ff0000", w: 1.3,
        ll: lt || c == null ? undefined : LGRS[c]?.line_label }); });
    // контуры зон подтопления ГИС ОГД совпадают неточно: после слияния остаются щели, и граница слабого местами идёт
    // вдоль границы умеренного. Участки границы слабее, чем в 3 м от границы более сильной зоны, не рисуются
    const stronger = { 66: [65, 64], 65: [64] };
    const orig = new Map(zoneFeats.map(f => [f.code, f.g]));          // сравнение — с исходными границами, до обрезки
    zoneFeats.forEach(f => { const near = (stronger[f.code] || []).flatMap(c => orig.get(c)?.coordinates || []).filter(l => l.length > 1)
        .map(l => { const ls = turf.lineString(l); return { ls, b: turf.bbox(ls) }; });
      if (!near.length) return;
      const d = 3 / 111320;                                            // 3 м в градусах — запас габаритов
      const keep = [];
      f.g.coordinates.forEach(line => { let run = [];
        for (let i = 1; i < line.length; i++) {
          const mid = [(line[i - 1][0] + line[i][0]) / 2, (line[i - 1][1] + line[i][1]) / 2];
          const close = near.some(n => mid[0] > n.b[0] - 2 * d && mid[0] < n.b[2] + 2 * d && mid[1] > n.b[1] - d && mid[1] < n.b[3] + d
            && (safe(() => turf.pointToLineDistance(mid, n.ls, { units: "meters" })) ?? Infinity) < 3);
          if (close) { if (run.length > 1) keep.push(run); run = []; } else { if (!run.length) run.push(line[i - 1]); run.push(line[i]); }
        }
        if (run.length > 1) keep.push(run); });
      f.g = { type: "MultiLineString", coordinates: keep }; });
    if (L("gisogd.zouit")) L("gisogd.zouit").features = zoneFeats;
    else out.layers.push({ title: "ЗОУИТ и зоны ограничений (ОГД)", features: zoneFeats });
    out.cLegend = [{ title: "Границы", items: [terr, { kind: "line", stroke: "#0000ff", width: .35, label: "земельных участков, поставленных на кадастровый учёт" }] },
      { title: "Застройка", items: [{ kind: "fill", fill: "#ffffff", stroke: "#8c8c8c", label: "существующая" }] },
      ...(seen.size ? [{ title: "Виды разрешённого использования земельных участков, территорий",
        items: LAND_USE.filter(([n]) => seen.has(n)).map(([n, c]) => ({ kind: "fill", fill: c, stroke: "#7a7a7a", label: n })) }] : []),
      ...(lgr.size || zk.size ? [{ title: "Линии градостроительного регулирования, действующие",
        items: [...[...lgr].map(([c, n]) => [c, n, LGR_LEG[c] || "граница " + zoneGen(LGRT[c] || "")]), ...[...zk].filter(([c]) => !lgr.has(c)).map(([c, n]) => [c, n, "граница " + zoneGen(LGRT[c] || "")])]
          .sort((a, b) => a[0] - b[0]).map(([c, n, t]) => ({ kind: "lt", name: n || undefined, stroke: ZONE_LINE[c]?.color || LGRC[c] || "#ff0000", dash: n ? undefined : (LGRS[c]?.dash_mm || [3, 1]).map(v => v * .5),
            ll: n || (LGRS[c]?.line_label || "").length > 12 ? undefined : LGRS[c]?.line_label, label: t })) }] : [])];   // длинная надпись в знак 8 мм не входит
    // подтопление — своей группой, знаками и подписями примера «Хатминки»
    const fl = [64, 65, 66].filter(c => zoneFeats.some(f => f.flood === c && f.g.coordinates.length));
    if (fl.length) out.cLegend.push({ title: "Зона подтопления от паводка 1% обеспеченности (глубина залегания грунтовых вод)",
      items: fl.map(c => ({ kind: "flood", code: c, stroke: FLOOD_C, label: FLOOD_T[c] })) });
    // приаэродромная территория — надписью под легендой, как в «Хатминки»: подзоны, которые пересекают территорию
    const af = L("gisogd.airfield"), air = new Map();
    (af?.features || []).forEach(ft => { const [port, n] = String(ft.props?.["Вид зоны"] || "").split("|");
      if (port && n && safe(() => turf.booleanIntersects({ type: "Feature", geometry: ft.g, properties: {} }, TERR))) (air.get(port) || air.set(port, new Set()).get(port)).add(+n); });
    if (af) af.features = [];
    const ord = n => ({ 1: "1-й", 2: "2-й", 3: "3-ей", 4: "4-ой", 5: "5-ой", 6: "6-ой" })[n] || n + "-й";
    air.forEach((ns, port) => { const list = [...ns].sort((a, b) => a - b).map(ord);
      out.cLegend.push({ items: [{ kind: "note", label: `Территория находится в ${list.length > 1 ? list.slice(0, -1).join(", ") + " и " + list.at(-1) : list[0]} подзон${list.length > 1 ? "ах" : "е"} приаэродромной территории аэропорта «${port}»` + (port === "Внуково" ? ". Приказ Росавиации от 17.04.2020 № 394-П" : "") }] }); });
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
    // участки территории пронумерованы, как в примере «Хатминки», — номер в карточке, на карте не показывается
    // (владелец 30.09.2026: «пронумеруй, но не отображай»); порядок — от большего участка к меньшему
    cards.sort((a, b) => b.area - a.area);
    out.cCards = { title: "Сведения о земельных участках в границах территории рассмотрения", items: cards.map((c, i) => [["Участок", "№" + (i + 1)], ...c.rows]) };
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
