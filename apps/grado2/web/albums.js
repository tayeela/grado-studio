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
  const lab = { lf: "ui-bold", lh: .6, lcol: "#141414" };
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
    out.mapNote = [okrug ? `${OKR_FULL[abbr] || abbr} административный округ` : "", district ? "район " + LABEL_FN.adm({ get: k => district.properties[k] }) : ""].filter(Boolean);
  }
  return out;
}

/* План реализации ППТ КРТ: оформление — шаблон владельца, состав листов — «ГК Царицыно» (9 листов). Рамки карт — в мм
   листа А3 (420 × 297): схемы Москвы и округа — как в шаблоне; карта остальных листов — рамка слайда 4 шаблона
   (album_io.MAP_RECT), справа колонка легенды и списков. Слои, подложка и оформление — как у слайдов раздела 1. */
const PK = { style: "pptkrt", rect: [24, 44, 263, 233], callout: true };
const PK_ROADS = ["motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "living_street"];
const PPTKRT = [
  { kind: "title", style: "pptkrt", title: "Титульный лист" },
  { style: "pptkrt", title: "Месторасположение рассматриваемой территории", legend: false, callout: true, panels: [
    { keys: ["gisogd.admin"], adm: "moscow", fit: "moscow", rect: [25, 48, 174, 229], noFrame: true },
    { keys: ["gisogd.admin"], adm: "okrug", fit: "okrug", rect: [212, 48, 188, 229], okrugTitle: true, noFrame: true }] },   // за округом — белый фон (владелец)
  { ...PK, title: "Ортофотоплан", basemap: "sat", keys: ["osm.roads", "gisogd.admin"], fit: "terr", ctx: 3,
    styles: { "osm.roads": { mode: "single", fill: "#f5d58a", width: 1.4, label: "Название", labelSize: 11 },
      "gisogd.admin": { mode: "single", opacity: 0, fill: "#e93939", stroke: "#e93939", width: 1.6, dash: [8, 4], label: "" } },
    labelMM: { "osm.roads": 2.8 }, legendTitle: { "gisogd.admin": "Граница района", "osm.roads": "Улицы, дороги и проезды" },
    only: { "osm.roads": { field: "Тип дороги", values: [...PK_ROADS, "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"] },
      "gisogd.admin": { field: "Уровень", values: ["район"] } } },
  { ...PK, kind: "photos", rect: [24, 44, 170, 233], callout: false, title: "Материалы фотофиксации", keys: ["calc.uds_osm", "egko.buildings", "osm.roads"], fit: "terr", ctx: 1.8,
    styles: { "osm.roads": { mode: "single", fill: "#d4d4d4", width: .3, label: "Название", labelSize: 9 } }, only: { "osm.roads": { field: "Тип дороги", values: PK_ROADS } } },
  { ...PK, title: "Схема существующего использования территорий с границами зон с особыми условиями использования территорий",
    keys: ["nspd.zouit", "gisogd.zouit", "gisogd.szz", "gisogd.vodookhr", "egko.green", "egko.water", "calc.uds_osm", "nspd.parcels", "egko.buildings", "gisogd.okn", "gisogd.red_lines"], fit: "terr", ctx: 1.6,
    styles: { "nspd.zouit": { hatch: false, opacity: .14, width: 1 }, "gisogd.szz": { hatch: false, opacity: .14, width: 1 }, "gisogd.vodookhr": { hatch: false, opacity: .14, width: 1 },
      "gisogd.zouit": { hatch: false, opacity: .14, width: 1 }, ...ROADS_WHITE } },
  { ...PK, title: "Генеральный план города Москвы. Фрагмент схемы «Карта функциональных зон»", keys: ["gisogd.func_zones", "gisogd.func_zones_tinao"], fit: "terr", ctx: 1.6,
    extra: "genplan", labelFn: { "gisogd.func_zones": "gp", "gisogd.func_zones_tinao": "gp" }, labelMM: { "gisogd.func_zones": 3.6, "gisogd.func_zones_tinao": 3.6 } },
  { ...PK, title: "Схема обеспеченности территории разработанной документацией ППТ и ПМТ", keys: ["calc.uds_osm", "egko.buildings", "gisogd.pmt", "gisogd.ppt"], fit: "terr", ctx: 2,
    styles: ROADS_WHITE, docs: [{ key: "gisogd.ppt", title: "Проекты планировки территории" }, { key: "gisogd.pmt", title: "Проекты межевания территории", pre: "Проект межевания территории" }] },
  { ...PK, title: "Схема обеспеченности территории разработанной документацией ГПЗУ и АГР", keys: ["calc.uds_osm", "egko.buildings", "gisogd.gpzu", "gisogd.agr"], fit: "terr", ctx: 2,
    styles: { ...ROADS_WHITE, "gisogd.gpzu": { fill: "#5c6bc0", stroke: "#3949ab", hatch: true, hatchPat: "135", width: .8, opacity: 1 } },
    docs: [{ key: "gisogd.gpzu", title: "Градостроительные планы земельных участков", pre: "ГПЗУ" }, { key: "gisogd.agr", title: "Свидетельства об утверждении АГР", pre: "АГР" }] },
  { ...PK, title: "Схема существующих землепользователей разрабатываемой территории", basemap: "sat", keys: ["nspd.parcels"], fit: "terr", ctx: 1.5, extra: "parcels",
    styles: { "nspd.parcels": { mode: "single", opacity: 0, stroke: "#2b3cc4", width: 1.6, label: "" } } },
];

async function buildAlbum(kind) {
  if (kind === "pptkrt") return buildSection(PPTKRT, "pptkrt_", "PA3", "План реализации ППТ КРТ");
}
window.buildAlbum = buildAlbum;
