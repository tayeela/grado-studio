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
// округ без далёких отдельных частей (владелец 05.10.2026: «северный анклав можно убрать», карта округа крупнее):
// остаются самая большая часть и части не дальше km от неё (у ВАО — пос. Восточный, ~1,5 км)
function okrugMainCalc(f, km) {
  if (f?.geometry?.type !== "MultiPolygon") return f;
  const parts = f.geometry.coordinates.map(c => turf.polygon(c)), big = parts.reduce((a, b) => m2(b) > m2(a) ? b : a);
  const edge = turf.lineString(big.geometry.coordinates[0]);
  const tc = TERR && turf.centroid(TERR);                    // часть, где лежит сама территория, остаётся всегда
  // крупная часть (≥ 2 % самой большой) — целые районы, например Крюково у ЗелАО: остаётся при любом расстоянии
  const bigA = m2(big);
  const keep = parts.filter(p => p === big || m2(p) >= bigA * .02 || (tc && safe(() => turf.booleanPointInPolygon(tc, p))) || turf.coordAll(p).filter((c, i, a) => i % Math.max(1, Math.floor(a.length / 50)) === 0).some(c => turf.pointToLineDistance(c, edge) < km));
  return { ...f, geometry: keep.length === 1 ? keep[0].geometry : { type: "MultiPolygon", coordinates: keep.map(p => p.geometry.coordinates) } };
}
// считается один раз на округ (по геометрии слоя), расстояние и центр территории: её часть остаётся всегда (T11, 06.10.2026)
const okrugMainMemo = AlbumGeo.memoByGeometry(okrugMainCalc);
const okrugMain = (f, km = 3) => okrugMainMemo(f, TERR ? turf.centroid(TERR).geometry.coordinates.join() : "", km);
window.okrugMain = okrugMain;
// район без частей в отброшенных частях округа: каждая часть остаётся, если её внутренняя точка — в основной части.
// Пересечение (turf.intersect) не годится: на сложных контурах оно падало, и район пропадал целиком (у САО оставалось 4 из 16)
function keepParts(f, main) {
  const g = f.geometry, ps = g?.type === "MultiPolygon" ? g.coordinates : g?.type === "Polygon" ? [g.coordinates] : [];
  const keep = ps.filter(c => safe(() => turf.booleanPointInPolygon(turf.pointOnFeature(turf.polygon(c)), main)));
  return { ...f, geometry: !keep.length ? null : keep.length === 1 ? { type: "Polygon", coordinates: keep[0] } : { type: "MultiPolygon", coordinates: keep } };
}

/* Полигоны схем округов и районов приводятся к масштабу листа (T71): рисовать контур точнее 0,5 пт на бумаге незачем, а
   полный слой — 111 тыс. вершин на панель — давал SVG в десятки мегабайт и минуты сборки. Упрощение — Дугласа–Пекера по общим
   рёбрам: вершина, у которой меняется набор объектов, содержащих её, — узел; дуга между узлами упрощается один раз и берётся
   всеми соседями одинаково, поэтому районы и округ не расходятся. Части площадью меньше 1 пт² отбрасываются (самая большая
   часть объекта остаётся, чтобы подпись не пропала). Граница территории и метка — не здесь, они идут как есть. */
const PT_M = 0.3528e-3;                                   // 1 пт на бумаге, м
function simplifyAdm(feats, scale, tolPt = .5, minPt2 = 1) {
  const tol = tolPt * PT_M * scale, minA = minPt2 * (PT_M * scale) ** 2, out = new Map();
  if (!feats.length) return out;
  const y0 = feats[0].geometry.type === "Polygon" ? feats[0].geometry.coordinates[0][0][1] : feats[0].geometry.coordinates[0][0][0][1];
  const kx = 111320 * Math.cos(y0 * Math.PI / 180), ky = 110574, key = c => c[0] + "," + c[1];
  const polysOf = g => g.type === "Polygon" ? [g.coordinates] : g.coordinates;
  const who = new Map();                                    // вершина → объекты, в которых она есть
  feats.forEach((f, i) => polysOf(f.geometry).forEach(po => po.forEach(r => r.forEach(c => { const k = key(c); (who.get(k) || who.set(k, new Set()).get(k)).add(i); }))));
  const sig = new Map(); const sg = c => { const k = key(c); return sig.get(k) || sig.set(k, [...who.get(k)].join(".")).get(k); };
  const dp = pts => {                                       // Дуглас–Пекер без рекурсии; концы остаются
    const n = pts.length, keep = new Uint8Array(n), st = [[0, n - 1]]; keep[0] = keep[n - 1] = 1;
    const P = pts.map(c => [c[0] * kx, c[1] * ky]);
    while (st.length) {
      const [a, b] = st.pop(); if (b - a < 2) continue;
      const [ax, ay] = P[a], dx = P[b][0] - ax, dy = P[b][1] - ay, L = Math.hypot(dx, dy); let m = -1, md = tol;
      for (let i = a + 1; i < b; i++) { const d = L ? Math.abs((P[i][0] - ax) * dy - (P[i][1] - ay) * dx) / L : Math.hypot(P[i][0] - ax, P[i][1] - ay); if (d > md) { md = d; m = i; } }
      if (m > 0) { keep[m] = 1; st.push([a, m], [m, b]); }
    }
    return pts.filter((_, i) => keep[i]);
  };
  const arcs = new Map();                                   // дуга (в канонической ориентации) → упрощённая
  const arc = pts => {
    const fwd = key(pts[0]) <= key(pts[pts.length - 1]), q = fwd ? pts : pts.slice().reverse(), id = key(q[0]) + "|" + key(q[q.length - 1]) + "|" + q.length;
    let r = arcs.get(id); if (!r) arcs.set(id, r = dp(q));
    return fwd ? r : r.slice().reverse();
  };
  const ring = r0 => {
    const r = r0.slice(0, -1), n = r.length, s = r.map(sg), nodes = [];
    for (let i = 0; i < n; i++) if (s[i] !== s[(i + n - 1) % n] || s[i] !== s[(i + 1) % n]) nodes.push(i);
    if (nodes.length < 2) {                                 // кольцо без соседей: узлы — первая и самая далёкая вершина
      let a = 0, far = 0, fd = -1; r.forEach((c, i) => { if (key(c) < key(r[a])) a = i; });   // от вершины с наименьшим ключом: одинаково для двух колец с одним контуром
      r.forEach((c, i) => { const d = Math.hypot((c[0] - r[a][0]) * kx, (c[1] - r[a][1]) * ky); if (d > fd) { fd = d; far = i; } });
      nodes.length = 0; nodes.push(...(a < far ? [a, far] : [far, a]));
    }
    const res = [];
    nodes.forEach((a, j) => { const b = nodes[(j + 1) % nodes.length], seg = []; for (let i = a; ; i = (i + 1) % n) { seg.push(r[i]); if (i === b) break; }
      res.push(...arc(seg).slice(0, -1)); });
    if (res.length < 3) return null;
    res.push(res[0]); return res;
  };
  const area = r => Math.abs(r.reduce((a, c, i) => i ? a + (r[i - 1][0] * kx) * (c[1] * ky) - (c[0] * kx) * (r[i - 1][1] * ky) : 0, 0)) / 2;
  feats.forEach((f, i) => {
    const parts = polysOf(f.geometry).map(po => { const rs = po.map(ring); return rs[0] ? { po: rs.filter(Boolean), a: area(rs[0]) } : null; }).filter(Boolean);
    if (!parts.length) return;
    const big = Math.max(...parts.map(x => x.a)), keep = parts.filter(x => x.a >= minA || x.a === big);
    out.set(f, keep.length === 1 ? { type: "Polygon", coordinates: keep[0].po } : { type: "MultiPolygon", coordinates: keep.map(x => x.po) });
  });
  return out;
}

/* Карта административного деления в шаблоне ППТ КРТ. adm: "moscow" — вся Москва: районы тонко серым, округа чёрным
   с подписями, свой округ красным с заливкой; "okrug" — свой округ: внутри цветная картооснова ЕГКО (рисует сервер
   по маске mask), снаружи белый фон, районы чёрным с названиями, контур округа жирно — как в шаблоне.
   Территория — точкой (terrPoint): в масштабе Москвы она меньше миллиметра. */
function admPanelSpec(p) {
  const { adm, okrug } = homeAdm(), abbr = okrAbbr(okrug), scale = sheetScale(p), center = sheetCenter(p);
  const poly = f => /Polygon/.test(f.geometry?.type);
  const lab = { lf: "sans-bold", lh: .6, lcol: "#141414" };
  let layers, sg = new Map(), mainOk = null;
  const G = f => sg.get(f) || f.geometry;
  if (p.adm === "moscow") {
    const okrs = adm.filter(f => poly(f) && f.properties["Уровень"] === "округ"), dists = adm.filter(f => poly(f) && f.properties["Уровень"] === "район");
    sg = simplifyAdm([...okrs, ...dists], scale);
    layers = [
      { title: "свой округ — заливка", features: okrug ? [{ g: G(okrug), fill: "#f7d4d4", stroke: "#e93939", w: 0, a: 1 }] : [] },
      { title: "районы", features: dists.map(f => ({ g: G(f), fill: null, stroke: "#a3a3a3", w: .45, a: 0 })) },
      { title: "округа", features: okrs.map(f => ({ g: G(f), fill: null, stroke: "#1a1a1a", w: 1.3, a: 0, label: okrAbbr(f), ls: 3.2, ...lab })) },
      { title: "свой округ", features: okrug ? [{ g: G(okrug), fill: null, stroke: "#e93939", w: 2.8, a: 0 }] : [] }];
  } else {
    const home = okrug?.properties["Округ"] || okrug?.properties["Наименование"], main = okrugMain(okrug);
    // районы — только в пределах основной части округа (далёкие части не показываются)
    const dists = adm.filter(f => poly(f) && f.properties["Уровень"] === "район" && f.properties["Округ"] === home)
      .map(f => main === okrug ? f : keepParts(f, main)).filter(f => f.geometry);
    sg = simplifyAdm(main && poly(main) ? [main, ...dists] : dists, scale);
    layers = [
      { title: "районы", features: dists.map(f => ({ g: G(f), fill: null, stroke: "#111111", w: .9, a: 0, label: LABEL_FN.adm({ get: k => f.properties[k] }), ls: 2.5, ...lab })) },
      { title: "округ", features: main ? [{ g: G(main), fill: null, stroke: "#111111", w: 2.6, a: 0 }] : [] }];
    mainOk = main;
  }
  return { title: "", size: p.size, scale, center, layers, legend: [], territory: TERR?.geometry || null, terrPoint: 1.0, noFrame: !!p.noFrame,
    basemap: p.basemap || "", rect: p.rect, ...(p.adm === "okrug" && mainOk ? { mask: G(mainOk) } : {}), ...(p.okrugTitle && abbr ? { okrugTitle: `${OKR_FULL[abbr] || abbr} административный округ` } : {}) };
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
const C_TERR = "#ff00ff", C_TW = 2.4;                                  // граница территории — жирный пунктир (владелец 29.09.2026)
// проезжая часть на листах 5–8 — один серый, сплошной, без контура (владелец 01.10.2026: «Вариант 3: #B4B4B4»)
const C_ROAD = "#b4b4b4";
// толщина линии на бумаге в мм → ширина стиля: печать переводит ширину в мм множителем PX_MM = 0,26 (print_io.py)
const MM = mm => mm / .26;
const C_LBL = { lf: "sans-bold", lh: .55, lcol: "#141414" };
// отбор дорог — общий у всех листов (у ортофотоплана добавляется граница района)
const C_ONLY = { "osm.roads": { field: "Тип дороги", values: ["motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "living_street"] } };
const C_BASE = { style: "pptkrt", look: "concept", fit: "terr", ctx: 1.25, rect: [7, 44, 279, 239], legend: false, only: C_ONLY,
  labelFn: { "osm.roads": "street", "osm.landuse": "name2" }, labelMM: { "osm.roads": 3.8, "osm.landuse": 3.8, "egko.water_labels": 3.8 },   // кегль чуть меньше (владелец 30.09.2026)
  labelStyle: { "osm.roads": C_LBL, "osm.landuse": C_LBL, "egko.water_labels": { lf: "sans-bold", lh: .55 } } };
// реки и водоёмы — подписями ЕГКО, голубым с белой обводкой (владелец 29.09.2026)
const C_WATER = { "egko.water_labels": { mode: "single", fill: "#1f8fe0", width: 1, marker: false, label: "Подпись", labelColor: "#1f8fe0" },
  "egko.water": { mode: "single", fill: "#a9cfe5", stroke: "#a9cfe5", width: 0, opacity: 0, label: "" } };   // на снимке вода видна сама — контуры только для подписи
// на белых схемах вода закрашена, иначе подпись реки висит над пустым местом
const C_WATER_VIS = { "egko.water": { mode: "single", fill: "#bfe0f5", stroke: "#bfe0f5", width: 0, opacity: 1, label: "" } };
// дороги — полигонами: проезжая часть ЕГКО и УДС Яндекса (в ТиНАО картооснова ЕГКО почти пустая), без контура
// на всех схемах — только полигоны проезжей части Яндекса, без проездов по осям и дорог ЕГКО (владелец 05.10.2026)
const C_ROADS = fill => ({ "yandex.hd_roads": { mode: "single", fill, stroke: fill, width: 0, opacity: 1 } });
const C_NAMES = { "osm.landuse": { mode: "single", fill: "#ffffff", stroke: "#ffffff", width: 0, opacity: 0, label: "Название" } };
const C_STREETS = (fill = C_ROAD) => ({ "osm.roads": { mode: "single", fill, width: 0, label: "Название", lineOff: true } });
// застройка — белая с серым контуром на листах 4–8 (правило 3.28; владелец 01.10.2026)
const C_PLAN = { ...C_ROADS(C_ROAD), ...C_WATER, ...C_WATER_VIS, "egko.buildings": { mode: "single", fill: "#ffffff", stroke: "#8c8c8c", width: 1, opacity: 1 } };
// общие части листов 4–8: названия и улицы + дороги, вода и застройка (C_PLAN); листы задают только отличия
const C_VEC = { ...C_NAMES, ...C_STREETS(), ...C_PLAN };
const C_BODY = ["egko.water", "yandex.hd_roads", "egko.buildings", "yandex.rail"], C_TAIL = ["osm.landuse", "osm.roads", "egko.water_labels"];
// деревни и улицы без названия в OSM — на всех листах обязательно (правила подписей): подписи и адреса картоосновы ЕГКО
const C_HIDDEN = { mode: "single", fill: "#141414", stroke: "#141414", width: 0, opacity: 0, marker: false, label: "" };
// железная дорога на белых схемах (листы 4–8): чёрная линия, белые штрихи рисует conceptRail (владелец 05.10.2026)
const C_RAIL = { mode: "single", fill: "#1f1f1f", stroke: "#1f1f1f", width: 4, label: "" };
// что есть у каждого листа: источник дорог, железная дорога, подписи, станции метро (правило 16: точки Яндекса в тех же
// тайлах, что дороги; на листе — значок и название, railStations); затем состав листа по ролям (T86a): начальный layout
// шаблона повторяет keys/styles/only 1:1, сборка листа читает его (sheetlayout.js)
function cSheet(sh, opts = {}) {
  // полигоны ЕГКО добавлены в ключи и стили листов — слой режется из кэша слоя на диске (портал — только при первой выгрузке,
  // раз в срок кэша); на векторных схемах он первый, на снимке — запасной. Дороги по осям (calc.uds_*) не рисуются никогда
  const i = sh.keys.indexOf("yandex.hd_roads");
  if (i >= 0) { sh.keys.splice(i + 1, 0, "egko.roads"); sh.styles = { ...sh.styles, "egko.roads": sh.styles["yandex.hd_roads"] }; }
  if (sh.keys.includes("yandex.rail")) sh.styles = { ...sh.styles, "yandex.rail": { ...C_RAIL } };
  if (opts.places === false) { sh.keys.push("yandex.stations"); sh.styles = { ...sh.styles, "yandex.stations": C_HIDDEN }; }   // карта района: подписи деревень и адресов не нужны
  else {
    sh.keys.push("egko.place_labels", "egko.addresses", "yandex.stations");
    sh.styles = { ...sh.styles, "egko.place_labels": { ...C_HIDDEN, label: "Подпись" }, "egko.addresses": C_HIDDEN, "yandex.stations": C_HIDDEN };
  }
  sh.layout = SheetLayout.seedLayout(sh);
  return sh;
}
const PPTKRT_C = [
  { ...C_BASE, concept: "ortho", title: "Ортофотоплан", basemap: "sat", bleed: true, rect: [0, 44, 420, 253], ctx: 2.2,
    // дороги — только полигоны проезжей части Яндекса, без проездов по осям и дорог ЕГКО (владелец 05.10.2026)
    keys: ["yandex.hd_roads", "osm.landuse", "osm.roads", "gisogd.admin", "egko.water", "egko.water_labels"],
    styles: { ...C_NAMES, ...C_STREETS("#f3d98c"), "yandex.hd_roads": { mode: "single", fill: "#f3d98c", stroke: "#f3d98c", width: 0, opacity: 1 }, ...C_WATER,
      "gisogd.admin": { mode: "single", opacity: 0, fill: "#e30613", stroke: "#e30613", width: 2, label: "" } },
    only: { ...C_ONLY, "gisogd.admin": { field: "Уровень", values: ["район"] } } },
  { ...C_BASE, concept: "photos", kind: "photos", title: "Материалы фотофиксации", rect: [7, 44, 198, 152], ctx: 1.3,
    keys: [...C_BODY, ...C_TAIL],
    styles: { ...C_NAMES, ...C_STREETS("#ffffff"), ...C_WATER, ...C_WATER_VIS, "yandex.hd_roads": { mode: "single", fill: "#ffffff", stroke: "#a0a0a0", width: 1, opacity: 1 },
      "egko.buildings": C_PLAN["egko.buildings"] } },
  { ...C_BASE, concept: "use", title: "Схема существующего использования территорий с границами зон с особыми условиями использования территорий",
    // линии Сводного плана и ЗОУИТ ГИС ОГД — типами линий REDLN97 (оформление задаёт conceptSheet); проезжая часть — серая
    // заливка C_ROAD, как на листах 6–8, территории автодорог (участки под дорогами) — белые, как в «ГК Царицыно»
    keys: [...C_BODY, "nspd.parcels", "gisogd.zouit", "gisogd.szz", "gisogd.vodookhr", "gisogd.red_lines", "gisogd.airfield", ...C_TAIL],
    styles: { ...C_VEC, "nspd.parcels": { mode: "single", fill: "#0000ff", stroke: "#0000ff", width: MM(.2), opacity: 0, label: "" },   // 0,2 мм (владелец 30.09.2026: «чуть тоньше»)
      "egko.water": { mode: "single", fill: "#336699", stroke: "#336699", width: 0, opacity: 1, label: "" },   // вода — класс 22 шаблона
      "gisogd.airfield": { mode: "single", fill: "#000000", stroke: "#000000", width: 0, opacity: 0, label: "" },   // только надпись под легендой
      ...Object.fromEntries(["gisogd.zouit", "gisogd.szz", "gisogd.vodookhr"].map(k => [k, { mode: "single", fill: "#ff0000", stroke: "#ff0000", width: 1, opacity: 0, label: "" }])) } },
  { ...C_BASE, concept: "gp", legend: true, title: "Генеральный план города Москвы. Фрагмент схемы «Карта функциональных зон»",
    keys: ["gisogd.func_zones", "gisogd.func_zones_tinao", ...C_BODY, ...C_TAIL], extra: "genplan",
    styles: { ...C_NAMES, ...C_STREETS(), ...C_WATER, "egko.water": { mode: "single", fill: "#00689d", stroke: "#00689d", width: 0, opacity: 1, label: "" },   // вода — как в «Хатминки»
      ...C_ROADS(C_ROAD), "egko.buildings": { mode: "single", fill: "#ffffff", stroke: "#5f5f73", width: 1, opacity: 1 } },
    labelFn: { ...C_BASE.labelFn, "gisogd.func_zones": "gp", "gisogd.func_zones_tinao": "gp" },
    labelMM: { ...C_BASE.labelMM, "gisogd.func_zones": 5.2, "gisogd.func_zones_tinao": 5.2 },   // на треть мельче; индекс ×1,15 (правило 11)
    labelStyle: { ...C_BASE.labelStyle, "gisogd.func_zones": { lfs: ["sans-bold", "sans-bold"], lcol: "#141414", lh: .4, lhc: "#ffffff" },
      "gisogd.func_zones_tinao": { lfs: ["sans-bold", "sans-bold"], lcol: "#141414", lh: .4, lhc: "#ffffff" } } },
  { ...C_BASE, concept: "ppt", title: "Схема обеспеченности территории разработанной документацией ППТ и ПМТ",
    // документы — над всеми слоями карты (дорогами и застройкой), под границей территории (владелец 01.10.2026)
    keys: [...C_BODY, "gisogd.ppt", "gisogd.pmt", ...C_TAIL],
    styles: { ...C_VEC, "gisogd.pmt": { mode: "single", fill: "#00d000", stroke: "#00d000", width: 4, opacity: 0 } } },
  { ...C_BASE, concept: "gpzu", title: "Схема обеспеченности территории разработанной документацией ГПЗУ и АГР",
    // документы — над всеми слоями карты, АГР выше ГПЗУ; под границей территории (владелец 01.10.2026)
    keys: [...C_BODY, "gisogd.gpzu", "gisogd.agr", ...C_TAIL],
    styles: { ...C_VEC,
      "gisogd.gpzu": { mode: "single", fill: "#7b7bf2", stroke: "#7b7bf2", hatch: true, hatchPat: "45", width: 1, opacity: 1 },
      "gisogd.agr": { mode: "single", fill: "#ff3b3b", stroke: "#ff3b3b", hatch: true, hatchPat: "135", width: 1, opacity: 1 } } },
  { ...C_BASE, concept: "parcels", title: "Схема существующих землепользователей разрабатываемой территории", basemap: "sat",
    keys: ["nspd.parcels", "osm.landuse", "osm.roads", "egko.water", "egko.water_labels"],
    styles: { ...C_NAMES, ...C_STREETS(), ...C_WATER, "nspd.parcels": { mode: "single", fill: "#c9c9ff", stroke: "#c9c9ff", width: 1, opacity: 0, label: "" } } },
].map(sh => cSheet(sh));

/* Листы «в границах сит. плана» (владелец 07.10.2026, задача #37, docs/team/spec-37-sitplan-sheets.md): в конец альбома, листы 1–9 не
   трогаются. Лист 10 — п. 1: карта района — снимок Яндекса на весь лист, район территории целиком (fit "district"), дороги OSM жёлтыми
   линиями по классам, красная граница района, названия районов, главных дорог и станций метро, выноска территории */
const DOCS_TOTAL = 8;   // схема документации: номера у ближайших восьми документов (колонка листа 11)
const ROAD_YELLOW = "#f3d98c", D_ROADS = ["motorway", "trunk", "primary", "secondary", "tertiary", "motorway_link", "trunk_link", "primary_link"];
const PPTKRT_D = [
  { ...C_BASE, concept: "district", sit: true, title: "Фрагмент карты административно-планировочной структуры города Москвы", basemap: "sat", bleed: true, rect: [0, 44, 420, 253], fit: "district",
    keys: ["osm.roads", "gisogd.admin", "egko.water", "egko.water_labels"],
    styles: { "osm.roads": { mode: "single", fill: ROAD_YELLOW, width: MM(.7), label: "Название" }, ...C_WATER,
      "gisogd.admin": { mode: "single", opacity: 0, fill: "#b3392f", stroke: "#b3392f", width: MM(.6), label: "" } },   // тоньше (владелец 07.10.2026, #45)
    only: { "osm.roads": { field: "Тип дороги", values: D_ROADS }, "gisogd.admin": { field: "Уровень", values: ["район"] } },
    labelMM: { "osm.roads": 3.2, "egko.water_labels": 3.8 } },
].map(sh => cSheet(sh, { places: false })).concat(
  // лист 11 — п. 2, схема документации на светлой подложке (как ДПТ «Профсоюзная»): здания светло-серые без контура, дороги белые, границы
  // участков тонкими синими линиями, документы штриховкой; рамка «по границам выгрузки»
  [cSheet({ ...C_BASE, concept: "docs", sit: true, fit: "cover",
    // название владельца сокращено («градостроительных планов земельных участков» → «ГПЗУ»): в 176 знаков оно не помещается в две строки по 18 пт (правило 13)
    title: "Схема с отображением границ территорий с имеющимися территориальными и отраслевыми схемами, документацией по планировке территории и ГПЗУ",
    keys: ["egko.green", ...C_BODY, "nspd.parcels", "gisogd.krt", "gisogd.ppt", "gisogd.pmt", "gisogd.gpzu", "gisogd.agr", ...C_TAIL],
    styles: { ...C_VEC, "egko.green": { mode: "single", fill: "#e4efdb", stroke: "#e4efdb", width: 0, opacity: 1, label: "" },
      "egko.water": { mode: "single", fill: "#d9e8f3", stroke: "#d9e8f3", width: 0, opacity: 1, label: "" },
      "yandex.hd_roads": { mode: "single", fill: "#ffffff", stroke: "#ffffff", width: 0, opacity: 1 },
      "egko.buildings": { mode: "single", fill: "#e1e1e1", stroke: "#e1e1e1", width: 0, opacity: 1 },
      "nspd.parcels": { mode: "single", fill: "#1f3fbf", stroke: "#1f3fbf", width: MM(.15), opacity: 0, label: "" },
      "gisogd.krt": { mode: "single", fill: "#e0892f", stroke: "#b35d00", hatch: true, hatchPat: "45", width: 1, opacity: 1, label: "" },
      "gisogd.ppt": { mode: "single", fill: "#8c8c8c", stroke: "#8c8c8c", hatch: true, hatchPat: "135", width: 1, opacity: 1, label: "" },
      "gisogd.pmt": { mode: "single", fill: "#00d000", stroke: "#00d000", width: 4, opacity: 0, label: "" },
      "gisogd.gpzu": { mode: "single", fill: "#7b7bf2", stroke: "#7b7bf2", hatch: true, hatchPat: "45", width: 1, opacity: 1, label: "" },
      "gisogd.agr": { mode: "single", fill: "#ff3b3b", stroke: "#ff3b3b", hatch: true, hatchPat: "135", width: 1, opacity: 1, label: "" } } })].concat(
  // лист 12 — п. 3, Генплан: шаблон листа 6 с рамкой «по границам выгрузки» (sheets.js coverFrameBox); лист 13 — п. 3, ПЗЗ: границы
  // территориальных зон с кодами видов разрешённого использования на той же основе, что листы 7–8
  [{ ...JSON.parse(JSON.stringify(PPTKRT_C.find(s => s.concept === "gp"))), sit: true, fit: "cover", title: "Размещение территории в материалах территориального планирования (Генеральный план города Москвы)" },
    cSheet({ ...C_BASE, concept: "pzz", sit: true, fit: "cover", title: "Размещение территории в материалах градостроительного зонирования (ПЗЗ города Москвы)",
      keys: [...C_BODY, "gisogd.pzz_zones", ...C_TAIL],
      styles: { ...C_VEC, "gisogd.pzz_zones": { mode: "single", fill: "#ffffff", opacity: 0, stroke: "#6a3d9a", width: MM(.5), label: "ВРИ (коды)" } },
      labelFn: { ...C_BASE.labelFn, "gisogd.pzz_zones": "vri" }, labelMM: { ...C_BASE.labelMM, "gisogd.pzz_zones": 3.4 },
      labelStyle: { ...C_BASE.labelStyle, "gisogd.pzz_zones": { lf: "sans-bold", lh: .5, lcol: "#4b2a7a" } } })]));

// подписи улиц — как в образце: «ул. Промышленная», «Кавказский бульв.», «Тарный пр-д»
const W_ = w => new RegExp(`(^|\\s)${w}(?=\\s|$)`, "i");            // целое слово: \b в JS кириллицу не видит
const STREET_ABBR = [[W_("улица"), "ул."], [W_("проезд"), "пр-д"], [W_("бульвар"), "бульв."], [W_("шоссе"), "ш."], [W_("переулок"), "пер."],
  [W_("проспект"), "просп."], [W_("набережная"), "наб."], [W_("площадь"), "пл."], [W_("тупик"), "туп."]];
LABEL_FN.street = f => { let n = LabelFmt.guillemets(String(f.get("Название") || "").trim()); if (!n) return null;
  for (const [re, ab] of STREET_ABBR) if (re.test(n)) { n = n.replace(re, " ").replace(/\s+/g, " ").trim(); return ab === "ул." || ab === "пл." || ab === "просп." ? `${ab} ${n}` : `${n} ${ab}`; }
  return n; };
// длинное название — в две строки примерно равной длины (владелец 30.09.2026), не больше двух
// посёлок — «пос.», не «п.» и не полностью (владелец 01.10.2026)
// станция — «ст. ж/д Калошино» с неразрывными пробелами (правило 15, владелец 05.10.2026); кавычки — «ёлочки»
LABEL_FN.name2 = f => { let n = String(f.get("Название") || "").trim().replace(/\s+/g, " ").replace(/(^|\s)пос[её]лок(?=\s|$)/i, "$1пос."); if (!n) return null;
  n = LabelFmt.guillemets(LabelFmt.placeLabel(f, LabelFmt.complexLabel(n)));   // «ЖК «…»» (правило 17)
  return LabelFmt.splitLabel(n); };

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
const VRI_WORDS = [[/многофункц/i, 1], [/благоустройств/i, 18],   // благоустройство — природно-рекреационная, не сельское хозяйство (06.10.2026)
  [/завод|фабрик|комбинат|(^|[^а-яё])цех/i, 14],   // «эксплуатации зданий завода» — производственная (06.10.2026) [/физкультур|оздоровительн[а-яё]* комплекс|(^|[^а-яё])спорт/i, 9],
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
// названия и цвета в легенде сущпола — по образцу владельца (06.10.2026: «названия и цвета в легенде сущпола должны быть
// такими»): «Функциональные зоны специализированного назначения» и «Транспортная инфраструктура». Класс шаблона ВРИ (по коду
// и словам ВРИ, как раньше) → зона образца; несколько классов шаблона могут давать одну зону
const SPEC_ZONES = [["многофункционального", "#c07c7e", [1]], ["административно-делового", "#cbb2cc", [8]],
  ["культурно-просветительского", "#f99f9f", [7, 23]], ["торгово-бытового", "#f4b598", [2]], ["лечебно-оздоровительного", "#b0d9d5", [4, 3, 10]],
  ["спортивно-рекреационного", "#b9e592", [9]], ["учебно-воспитательного", "#cde1b7", [5]], ["учебно-образовательного", "#d5a9aa", [6]],
  ["общественно-жилого", "#ee8e62", [13]], ["многоквартирной жилой застройки", "#f9e79f", [11]], ["индивидуальной жилой застройки", "#e5e57f", [12]],
  ["сельскохозяйственного назначения", "#e8f2c7", [25]], ["общественно-производственного", "#ad84ae", []],
  ["сельскохозяйственно-производственного", "#b8a47f", [27, 28]], ["фермерско-производственного", "#c0c000", [26]], ["производственного", "#cfd1eb", [14]],
  ["коммунально-складского", "#dcd5b6", [17]], ["жилищно-коммунального", "#d7c6c1", [16]], ["специального", "#c7d1c7", [15]],
  ["природно-рекреационного", "#c0e3b5", [18]], ["природоохранного", "#597f47", [19]], ["водные поверхности", "#336699", [22]], ["прочие", "#f7faf5", [24]]];
const TRANSPORT_ZONES = [["территории железнодорожного транспорта", "#ada4a0", [20]], ["территории автодорог, улиц и местных проездов", "#ffffff", [21]]];
const ZONE_OF = new Map([...SPEC_ZONES, ...TRANSPORT_ZONES].flatMap(([name, color, ns]) => ns.map(n => [n, [name, color]])));
const LAND_USE = Object.keys(VRI_T).map(n => [...ZONE_OF.get(+n), null, +n]);
const VRI_CLS = n => LAND_USE.find(u => u[3] === n);
const ROAD_USE = VRI_CLS(21), WATER_USE = VRI_CLS(22);
const CODE_CLS = new Map(Object.entries(VRI_T).flatMap(([n, [, , codes]]) => codes.map(c => [c, +n])));
// сельскохозяйственные классы шаблона (растениеводство, животноводство, сельхозпроизводство, наука для сельского хозяйства)
const AGRI_CLS = new Set([25, 26, 27, 28]);
// территория в ТиНАО (Новомосковский или Троицкий округ): только там бывают сельскохозяйственные земли
const inNewMoscow = () => /Новомосковск|Троицк/.test(String(homeAdm().okrug?.properties?.["Округ"] || homeAdm().okrug?.properties?.["Наименование"] || ""));
// класс участка — по ВРИ (приоритет всегда у ВРИ, владелец 06.10.2026). Код ВРИ федерального классификатора: «(2.1)»,
// «4.9.1.1» → 4.9.1 → 4.9. Московские коды старого классификатора «1.2.9», «1.2.13» (склады, железная дорога) — не
// федеральные «1.2» (выращивание зерновых): трёхуровневый код раздела 1 не обрезается, класс — по словам ВРИ.
// В старой Москве сельскохозяйственных территорий нет (владелец 06.10.2026: «не может быть в старой москве территорий
// сельскохозяйственного назначения … если благоустройство, то это благоустройство»)
const landUseOf = p => { const v = String(p["ВРИ"] || p["Разрешенное использование"] || "").replace(/[Cc](?=[а-яё])/g, "с"); if (!v) return null;   // латинская «C» в «Cадоводство»
  const agriOk = safe(inNewMoscow);
  const ok = n => n != null && (agriOk || !AGRI_CLS.has(n));
  for (const m of v.match(/\b\d{1,2}(?:\.\d{1,2}){1,3}\b/g) || []) {      // код ВРИ в тексте: «(2.1)», «13.2», «4.9.1.1»
    if (/^1\.\d+\.\d+/.test(m) && !CODE_CLS.has(m)) continue;          // московский код «1.2.9» — не федеральный раздел 1
    for (let c = m; c; c = c.includes(".") ? c.slice(0, c.lastIndexOf(".")) : "") if (CODE_CLS.has(c) && ok(CODE_CLS.get(c))) return VRI_CLS(CODE_CLS.get(c)); }
  const w = VRI_WORDS.find(([re, n]) => re.test(v) && ok(n)); return w ? VRI_CLS(w[1]) : null; };
// земля без участка ЕГРН и участок с непонятным ВРИ — по землепользованию OSM (владелец 30.09.2026: белым только УДС)
const OSM_USE = [[/^(farmland|orchard|plant_nursery|greenhouse_horticulture|vineyard)$/, 25], [/^(farmyard|animal_keeping)$/, 26],
  [/^(forest|wood|scrub|grassland|heath|meadow|grass|park|garden|recreation_ground|village_green)$/, 18], [/^nature_reserve$/, 19],
  [/^(cemetery|quarry|landfill|military)$/, 15], [/^allotments$/, 12], [/^residential$/, 12],
  [/^industrial$/, 14], [/^retail$/, 2], [/^commercial$/, 8],   // commercial в OSM — офисы, не торговля (владелец 06.10.2026: «откуда торгово-бытовой?») [/^garages$/, 16], [/^(depot|storage)$/, 17], [/^railway$/, 20],
  [/^religious$/, 7], [/^education$/, 5], [/^(pitch|playground)$/, 9], [/^(brownfield|construction)$/, 14]];
const LAND_BASE = VRI_CLS(18)[0];                             // всё, что не закрыто ни участком, ни OSM: белых пятен и «отсутствия
                                                              // хозяйственной деятельности» быть не должно (владелец 30.09.2026)
const NATURE_USE = VRI_CLS(18);                               // береговая полоса — природно-рекреационная
const osmUseOf = p => { const agriOk = safe(inNewMoscow);   // в старой Москве сельского хозяйства нет и по OSM (06.10.2026)
  for (const v of [p["Землепользование"], p["Природа"], p["Отдых"]]) { const hit = v && OSM_USE.find(([re, n]) => re.test(v) && (agriOk || !AGRI_CLS.has(n))); if (hit) return VRI_CLS(hit[1]); } return null; };
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
// СЗЗ — условными знаками ГИС ОГД (владелец 05.10.2026: «рисуй, но возьми условные для СЗЗ как на ГИС ОГД»; стили
// слоёв портала virtual1743, virtual1745, virtual1746): только граница, без заливки; штрих 9/7 пикс. — у ориентировочных
// владелец 06.10.2026: «установленные СЗЗ — чёрный контур, ориентировочные — пунктир, чёрный контур» (расчётные — как на портале)
const SZZ_OGD = { 5: { color: "#000000" }, 62: { color: "#f3f707" }, 63: { color: "#000000", dash: [9, 7] } }, SZZ_W = 2.1;   // толще (владелец 06.10.2026: «все ЛГР потолще»)
// виды СЗЗ в легенде — друг за другом: установленные (5), затем расчётные (62) (владелец 05.10.2026)
const SZZ_ORD = c => c === 62 ? 5.5 : c === 63 ? 5.7 : c;
const zoneGen = t => { const c = Object.entries(LGRT).find(([, v]) => v === t)?.[0]; if (ZONE_GEN[c]) return ZONE_GEN[c];
  return t.toLowerCase().split(/\s+/).map(w => w.replace(/(ые|ие)$/, "ых").replace(/зоны$/, "зон").replace(/полосы$/, "полос").replace(/ая$/, "ой").replace(/зона$/, "зоны").replace(/территории$/, "территорий")
    .replace(/^(объект|режим)ы$/, "$1ов").replace(/^памятники$/, "памятников")).join(" "); };   // «граница объектов природного комплекса» (владелец 05.10.2026)
// зоны подтопления — знаками примера «Хатминки» (владелец 30.09.2026: «скопируй условные зон подтопления»); рисует печать
const FLOOD_C = "#038240", FLOOD_T = { 64: "сильное подтопление (0–0,3 м)", 65: "умеренное подтопление (0,3–2,0 м)", 66: "слабое подтопление (2,0–3,0 м)" };
// зоны подтопления в Эталоне различаются только штриховкой: без неё граница умеренного и слабого — типом линии сильного
// (с засечками) цветом штриховки своего знака, затемнённым (владелец 30.09.2026)
const ZONE_LINE = { 65: { lt: 64, color: "#2f7fd8" }, 66: { lt: 64, color: "#2e9e78" } };
// резерв угловой надписи листа (прямоугольник слева вверху рамки, 102 × 26 мм на бумаге — album_io.MapNoteFrame, слайд-правило 4.10)
// как полигон в градусах рамки bb [w, s, e, n]; scale — знаменатель масштаба листа
const cornerReserve = (bb, scale, w = 102, h = 26) => { const dx = w * scale / 1000 / (111320 * Math.cos((bb[1] + bb[3]) / 2 * Math.PI / 180)), dy = h * scale / 1000 / 111320;
  return turf.bboxPolygon([bb[0], bb[3] - dy, bb[0] + dx, bb[3]]); };
// текст надписи знака Эталона, который программа печатает вместо данных стиля (в стиле «охранная зона О электроэнергетики»: лишняя «О»)
const ZONE_LL = { 32: "охранная зона электроэнергетики" };
const zouitCode = (key, p) => key === "gisogd.vodookhr" ? 16 : key === "gisogd.szz" ? (/расч/i.test(p["Вид зоны"] || "") ? 62 : /ориент/i.test(p["Вид зоны"] || "") ? 63 : 5) : ZOUIT_LGR[p["Вид зоны"]];

const C_PALETTE = ["#f5a623", "#00c8e0", "#7b2d8e", "#f0503c", "#ff3fb4", "#2e9d4f", "#1565c0", "#8d6e63", "#ff8f00", "#00897b"];
// самая большая часть (мульти)полигона — кольца для печати: там ищется точка выноски номера
const bigRing = f => { const g = f?.geometry || f; if (!g) return undefined;
  const ps = g.type === "MultiPolygon" ? g.coordinates : g.type === "Polygon" ? [g.coordinates] : [];
  return ps.length ? ps.reduce((a, b) => m2(turf.polygon(b)) > m2(turf.polygon(a)) ? b : a) : undefined; };
function conceptDocs(out, bb, groups, opts = {}) {
  // документы в рамке: номер на карте (жирный 10 мм с белым ореолом) и список в рамках цвета документа, ближние к
  // территории — первыми; groups: [{key, title, color (одна на группу) | palette, text(p) → строка списка}]
  // opts.total — номера и списки только у ближайших документов всех групп вместе (схема документации в границах сит. плана, #37:
  // в колонку их помещается около восьми); остальные документы нарисованы без номера
  const c = TERR ? turf.centroid(TERR) : null, box = turf.bboxPolygon(bb), lists = [], pts = [], rsv = cornerReserve(bb, out.scale || 1000);
  let no = 0, pi = 0;
  const per = groups.map(g => {
    const layer = out.layers.find(l => l.key === g.key), seen = new Map();
    (layer?.features || []).forEach(ft => {
      const f = { type: "Feature", geometry: ft.g, properties: ft.props || {} }; if (!/Polygon/.test(ft.g?.type)) return;
      const part = safe(() => inter(f, box)); if (!part) return;
      // точка номера — вне резерва угловой надписи, если у документа есть часть за его пределами (F10: ⑥ стоял под надписью)
      const free = safe(() => turf.difference(turf.featureCollection([part, rsv]))), usable = free?.geometry && m2(free) >= 25 ? free : part;
      const id = f.properties.document_n || f.properties.document_g || f.properties._key, at = safe(() => turf.pointOnFeature(usable)), at0 = usable === part ? at : safe(() => turf.pointOnFeature(part));
      const dist = c && at0 ? turf.distance(c, at0) : 0;   // порядок номеров — по настоящему положению документа, а не по сдвинутой точке
      if (!seen.has(id)) seen.set(id, { f, at, dist, fts: [] });
      const cur = seen.get(id); cur.fts.push(ft); if (at && dist < cur.dist) Object.assign(cur, { at, dist });
    });
    return [...seen.values()].filter(d => d.at).sort((a, b) => a.dist - b.dist).slice(0, g.max || 12);
  });
  if (opts.total) { const keep = new Set(per.flat().sort((a, b) => a.dist - b.dist).slice(0, opts.total)); per.forEach((docs, i) => { per[i] = docs.filter(d => keep.has(d)); }); }
  groups.forEach((g, gi) => {
    const docs = per[gi]; if (!docs.length) return;
    const items = docs.map(d => {
      const n = String(++no), color = g.color || C_PALETTE[pi++ % C_PALETTE.length];
      d.fts.forEach(ft => { ft.fill = color; ft.stroke = color; });
      // номер — 5 мм; внутри документа, если помещается, иначе рядом с выноской к нему (владелец 30.09.2026: цифры огромные
      // и непонятно, к чему относятся)
      const k2 = 1000 / (out.scale || 2000), big = m2(safe(() => inter(d.f, box)) || d.f) * k2 * k2 > 120;   // кружок ~6 мм помещается
      pts.push({ g: d.at.geometry, nodot: true, leader: true, circle: true, inside: big, zone: bigRing(safe(() => inter(d.f, box)) || d.f),
        label: n, ls: 3.6, lf: "sans-bold", lcol: "#141414" });
      return { text: `${n}. ${g.text(d.f.properties, d)}`, color };
    });
    lists.push({ title: g.title, items });
  });
  if (pts.length) out.layers.push({ title: "Номера документов", features: pts });
  return lists;
}
// название документа — всегда полностью, как в ГИС ОГД (владелец 03.10.2026): без многоточия и обрезки; дефис между
// словами — тире (правило 11: «…от газорегулято №1218-ПП»)
const docTitle = t => LabelFmt.dotDigit(String(t || "").trim().replace(/\s+-\s+/g, " — "));
// «№» отделён от номера неразрывным пробелом (правило 2.26; владелец 01.10.2026)
const docLine = p => [docTitle(p.document_1), p.document_n ? `№\u00a0${p.document_n}` : "", p.document_d ? `от ${dateRu(p.document_d)} г.` : ""].filter(Boolean).join(" ");
// группы документов листов 7, 8 и схемы документации (лист 11): одни и те же списки и цвета
const PPT_GROUP = { key: "gisogd.ppt", title: "Проекты планировки территории", text: docLine };
const PMT_GROUP = { key: "gisogd.pmt", title: "Проекты межевания территории", color: "#00d000", text: p => p.document_1 ? docLine(p) : ["Проект межевания территории", p.document_n ? `№\u00a0${p.document_n}` : "", p.document_d ? `от ${dateRu(p.document_d)} г.` : ""].filter(Boolean).join(" ") };
// ГПЗУ с номером; свидетельство АГР на том же участке — второй строкой того же пункта, как в образце
const gpzuGroup = (agr, used) => ({ key: "gisogd.gpzu", title: "ГПЗУ и свидетельства об утверждении АГР", color: "#231f20", text: (p, d) => {
  const a = agr.find((x, i) => !used.has(i) && safe(() => { const y = inter(x, d.f); return y && m2(y) > m2(x) * .5; }));
  if (a) used.add(agr.indexOf(a));
  const q = a?.properties;
  return `ГПЗУ ${p.document_n ? "№\u00a0" + p.document_n : ""} ${p.document_d ? `от ${dateRu(p.document_d)} г.` : ""}`.replace(/ +/g, " ").trim()   // / +/: \s съел бы неразрывный пробел
    + (q ? `\nАГР ${q.document_n ? "№\u00a0" + q.document_n : ""} ${q.document_d ? `от ${dateRu(q.document_d)} г.` : ""}`.replace(/\s+$/, "") : ""); } });

/* Подписи рек и водоёмов (владелец 29–30.09.2026): одна на название, на самом большом водоёме этой реки рядом с её
   подписями в ЕГКО (до 400 м; контур с другим названием не берётся, один контур — одно название). Пруд или озеро
   подписывается по центру вдоль своей длины (главная ось контура). Река — прямо на русле: центр подписи на средней
   линии русла (середина поперечного сечения контура), поворот — по направлению русла в этом месте; узкая река без
   контура — на линии тонкой реки ЕГКО. Общие слова («пр.», «ручей») не подписываются. */
const WATER_GENERIC = /^(пр\.?|ручей|пруд|р\.|кан\.?|оз\.?|вдхр\.?)$/i;
// места подписей рек — одни для всех листов с той же рамкой и тем же масштабом (владелец 30.09.2026: «р. Моча на
// разных листах в разных местах, на одном листе нет»): считаются по данным проекта, а не по набору слоёв листа
const WL_MEMO = new Map();
// общий набор препятствий для подписей рек: проезжая часть из данных проекта в рамке — источник выбирает roadsrc по
// правилу векторных схем (ЕГКО первым), геометрия очищается как на листе (roadclean). Не зависит от слоёв листа
function sharedRoads(bb) {
  const polys = key => dataFts(key).filter(ft => /Polygon/.test(ft.g?.type));
  const ya = polys("yandex.hd_roads"), eg = polys("egko.roads");
  const area = g => safe(() => { const c = turf.bboxClip({ type: "Feature", geometry: g, properties: {} }, bb); return c?.geometry?.coordinates?.length ? turf.area(c) : 0; }) || 0;
  const sum = fts => fts.reduce((s, f) => s + area(f.g), 0);
  const src = LegendRules.obstacleSource({ ya: sum(ya), egko: sum(eg) }, RoadSrc.pickRoadSource);
  const fts = src === "egko" ? eg : src === "yandex" ? ya : [];
  const geoms = fts.map(f => f.g); if (src === "egko") geoms.push(...RoadClean.gapFill(turf, geoms, ya.map(f => f.g), bb));   // те же дороги, что на листе (F4)
  const g = fts.length ? RoadClean.clean(turf, geoms, bb) : null;
  return g ? [{ g, b: turf.bbox(g) }].filter(x => !(x.b[2] < bb[0] || x.b[0] > bb[2] || x.b[3] < bb[1] || x.b[1] > bb[3])) : [];
}
const dataFts = key => (DATA[key]?.fc?.features || []).map(f => ({ g: f.geometry, props: f.properties || {} }));
function waterLabels(out, bb) {
  const wl = out.layers.find(l => l.key === "egko.water_labels"); if (!wl) return;
  const mkey = [...bb.map(v => v.toFixed(6)), out.scale || 2000, dataRev, TERR_REV].join("|");
  if (WL_MEMO.has(mkey)) { wl.features = WL_MEMO.get(mkey).map(f => ({ ...f })); return; }
  const box = turf.bboxPolygon(bb), inBox = c => c[0] >= bb[0] && c[0] <= bb[2] && c[1] >= bb[1] && c[1] <= bb[3];
  const water = dataFts("egko.water").filter(ft => ft.g && safe(() => turf.booleanIntersects(ft.g, box)));
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
  // дороги — из данных проекта по правилам векторных схем, а не из слоёв листа (T85b, правило 0): на листе 9 дорог нет,
  // и подпись, посчитанная там первой, ложилась бы поперёк дорог на листах 5–8
  const roads = sharedRoads(bb);
  turf.flatten(turf.polygonToLine(TERR)).features.forEach(l => roads.push({ g: l.geometry, b: turf.bbox(l) }));   // и границу территории
  const rect = (c, ang, text, ls) => {
    const L = text.length * .62 * ls * k / 2 + ls * k * .4, H = ls * .75 * k, a = ang * Math.PI / 180, ux = Math.cos(a), uy = Math.sin(a);
    const pts = [[-L, -H], [L, -H], [L, H], [-L, H]].map(([u, v]) => [c[0] + (u * ux - v * uy) / mx, c[1] + (u * uy + v * ux) / my]);
    return turf.polygon([[...pts, pts[0]]]); };
  // сколько дорог пересекает подпись (Infinity — не влезает в рамку)
  const hits = r => { const b = turf.bbox(r);
    if (b[0] < bb[0] || b[2] > bb[2] || b[1] < bb[1] || b[3] > bb[3]) return Infinity;
    return roads.filter(x => !(x.b[2] < b[0] || x.b[0] > b[2] || x.b[3] < b[1] || x.b[1] > b[3]) && safe(() => turf.booleanIntersects(x.g, r))).length; };
  // доля оси подписи, лежащая на воде (11 точек по длине текста): на извилистой реке прямая подпись по среднему
  // направлению уходит с русла (владелец 30.09.2026: «р. Вороновка подписана криво»)
  const onWater = (c, ang, t, ls, wet) => { if (!wet) return 1;
    const L = t.length * .62 * ls * k / 2, a = ang * Math.PI / 180, ux = Math.cos(a), uy = Math.sin(a); let n = 0;
    for (let i = 0; i <= 10; i++) { const u = -L + 2 * L * i / 10; if (wet([c[0] + u * ux / mx, c[1] + u * uy / my])) n++; }
    return n / 11; };
  // лучшее место на русле из списка мест [[x, y], угол]: меньше пересечений с дорогами и границей, затем подпись
  // целиком на воде (направление уточняется поворотом до ±24°), при равенстве — ближе к территории
  const pick = (spots, t, ls, wet) => { let best = null;
    spots.sort((x, y) => turf.distance(x[0], tc) - turf.distance(y[0], tc));
    for (const [c, a0] of spots) for (const da of [0, -8, 8, -16, 16, -24, 24]) {
      const a = norm(a0 + da), n = hits(rect(c, a, t, ls)); if (n === Infinity) continue;
      const w = onWater(c, a, t, ls, wet), sc = n * 2 + (1 - w) + Math.abs(da) / 240;   // одна дорога весит как две длины подписи мимо воды
      if (!best || sc < best.sc - 1e-9) best = { sc, at: turf.point(c), ang: a };
      if (n === 0 && w === 1 && !da) break;
    }
    return best && { at: best.at, ang: best.ang }; };
  const thin = (c, ls) => ls.filter(l => l.v.some(q => turf.distance(c, q) < .15));
  byName.forEach((fts, t) => {
    const base = t.replace(/^(р\.|оз\.|пр\.)\s*/i, "").toLowerCase(), pts = fts.map(ft => turf.point(ft.g.coordinates)), ls = +fts[0].ls || 3.8;
    const inFrame = pts.filter(pt => inBox(pt.geometry.coordinates));
    const cand = polys.filter(p => !used.has(p) && (!p.name || p.name.toLowerCase() === base) && pts.some(pt => dist(pt, p) < .4));
    let res = null;
    if (cand.length) {
      const best = cand.reduce((x, y) => y.a > x.a ? y : x), part = safe(() => inter(best.f, box)) || best.f;
      used.add(best);
      // широкая вода (пруд, озеро, водохранилище на реке) — по центру вдоль длинной оси; ось — по точкам внутри
      // контура, а не по вершинам: у изрезанного берега вершины скучены и уводят ось (правило 11, «р. Поляница»)
      const inner = (() => { const [x0, y0, x1, y1] = turf.bbox(part), n = 28, pts = [];
        for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) { const q = [x0 + (x1 - x0) * (i + .5) / n, y0 + (y1 - y0) * (j + .5) / n];
          if (safe(() => turf.booleanPointInPolygon(q, part))) pts.push(q); }
        return pts; })();
      const lenM = inner.length > 2 ? (() => { const a = axis(inner) * Math.PI / 180, ux = Math.cos(a), uy = Math.sin(a);
        const us = inner.map(([x, y]) => x * mx * ux + y * my * uy); return Math.max(...us) - Math.min(...us); })() : 0;
      const wide = best.river && lenM > 0 && m2(part) / lenM > ls * k * 2.2;   // средняя ширина больше двух высот подписи
      if (!best.river || wide) {
        const c = safe(() => turf.centerOfMass(part));
        res = { lake: true, at: c && safe(() => turf.booleanPointInPolygon(c, part)) ? c : turf.pointOnFeature(part), ang: inner.length > 2 ? axis(inner) : axis(turf.coordAll(part)) };
      } else {                                                 // река — на середине русла, вдоль него
        const ps = polys.filter(p => p.river && (p === best || (best.name && p.name === best.name)));
        const rv = ps.flatMap(p => p.v).filter(inBox), step = Math.max(1, Math.ceil(rv.length / 120)), spots = [];
        [...inFrame.map(pt => pt.geometry.coordinates), ...rv.filter((_, i) => i % step === 0)].forEach(c => {
          const a = axis(rv.filter(q => turf.distance(c, q) < .2)), m = midChannel(c, a, ps);
          if (m && inBox(m)) spots.push([m, a]); });
        res = pick(spots, t, ls, q => ps.some(p => safe(() => turf.booleanPointInPolygon(q, p.f))));
      }
    }
    if (!res) {                                                // узкая река — на линии тонкой реки ЕГКО рядом с подписью
      const near = [...new Set(pts.flatMap(pt => thin(pt.geometry.coordinates, lines)))].filter(l => !l.name || l.name.toLowerCase() === base);
      const rv = near.flatMap(l => l.v).filter(inBox), step = Math.max(1, Math.ceil(rv.length / 120));
      const segs = near.flatMap(l => l.v.slice(1).map((q, i) => [l.v[i], q])), tol = ls * k * .35;   // на линии — в пределах полувысоты букв
      const onLine = q => segs.some(([u, v]) => { const ax = (v[0] - u[0]) * mx, ay = (v[1] - u[1]) * my, bx = (q[0] - u[0]) * mx, by = (q[1] - u[1]) * my,
        tt = Math.max(0, Math.min(1, (ax * bx + ay * by) / (ax * ax + ay * ay || 1))); return Math.hypot(bx - ax * tt, by - ay * tt) < tol; });
      res = pick(rv.filter((_, i) => i % step === 0).map(c => [c, axis(rv.filter(q => turf.distance(c, q) < .15))]), t, ls, onLine);
    }
    if (!res && inFrame.length) {                              // ни контура, ни линии — у подписи ЕГКО
      const at = nearest(inFrame); res = { at, ang: axis(polys.flatMap(p => p.v).filter(c => turf.distance(at, c) < .2)) };
    }
    if (!res) return;
    let ang = res.ang; if (ang < -60) ang += 180;              // почти вертикальная подпись читается снизу вверх
    if (res.lake && ang > 90) ang = 90;                        // озеро: не заваливать подпись назад — строго вертикально
    labels.push({ ...fts[0], g: res.at.geometry, la: ang, nudge: false });
  });
  wl.features = labels;
  WL_MEMO.set(mkey, labels.map(f => ({ ...f })));
  if (WL_MEMO.size > 40) WL_MEMO.delete(WL_MEMO.keys().next().value);
}

/* Станции метро, МЦК и МЦД (правило 16, владелец 05–06.10.2026): значок и название; признаки видов — railstations.js. Слой
   станций — первым: места под значки и названия занимаются раньше остальных подписей. Возвращает станции для namedPlaces
   (ЕГКО подписывает те же станции «ст. ж/д …» — дубль снимается) */
function railStations(out, bb) {
  const l = out.layers.find(x => x.key === "yandex.stations"); if (!l) return [];
  const sts = RailStations.stations(l.features.filter(ft => ft.g?.type === "Point").map(ft => ({ props: ft.props, coord: ft.g.coordinates })));
  l.features = [];
  const inBox = c => c[0] >= bb[0] && c[0] <= bb[2] && c[1] >= bb[1] && c[1] <= bb[3];
  const vis = sts.filter(s => inBox(s.at));
  if (vis.length) out.layers.unshift({ title: "Станции метро, МЦК и МЦД", features: vis.map(s => ({ g: { type: "Point", coordinates: s.at }, nm: true, label: s.name, ls: 4.4,
    lf: "sans-bold", lh: .55, lcol: s.color, la: 0, nudge: true, ic: s.icons })) });
  out._stations = vis;                                         // для легенды (conceptStations)
  return sts.map(s => ({ bare: RailStations.bare(s.name), at: s.at }));
}
// легенда: «Транспорт» — значки только тех станций, что видны на листе (правило 7)
function conceptStations(out, k) {
  const items = RailStations.legendItems(out._stations || []); delete out._stations;
  if (!items.length || k === "photos" || !out.cLegend) return;
  const row = items.map(it => ({ kind: "icon", icon: it.icon, label: it.label })), g = out.cLegend.find(x => x.title === "Транспорт");
  if (g) g.items.push(...row); else out.cLegend.push({ title: "Транспорт", items: row });
}

/* Обязательные подписи (владелец 30.09.2026: «д. Безобразово и ул. Придорожная на всех листах»): деревни и посёлки —
   по пояснительным подписям ЕГКО, на своём месте; улицы, которых нет среди названий OSM на листе, — по адресам зданий
   ЕГКО («Придорожная улица 7»): вдоль ближайшей дороги OSM рядом со зданиями, иначе вдоль ряда зданий. Слой — первым:
   эти подписи ставятся раньше всех. */
const PLACE_RE = /^(д|дер|с|п|пос|рп|х|село|деревня)\.?\s+(.+)$/i;
const titleRu = t => t.toLowerCase().replace(/(^|[\s-])([а-яё])/g, (m, a, b) => a + b.toUpperCase());
function namedPlaces(out, bb, rail = []) {
  const L = key => out.layers.find(l => l.key === key), inBox = c => c[0] >= bb[0] && c[0] <= bb[2] && c[1] >= bb[1] && c[1] <= bb[3];
  const feats = [], kx = Math.cos(bb[1] * Math.PI / 180);
  (L("egko.place_labels")?.features || []).forEach(ft => { const t = String(ft.props?.["Подпись"] || ft.label || "").trim(), m = PLACE_RE.exec(t);
    if (ft.g?.type === "Point" && /^(ст\.|станция)\s+\S/i.test(t) && rail.some(r => r.bare === RailStations.bare(t) && RailStations.dist(r.at, ft.g.coordinates) <= RailStations.NEAR_M)) return;   // это станция метро / МЦК / МЦД — подписана значком
    if (ft.g?.type === "Point" && inBox(ft.g.coordinates) && /^(ст\.|станция)\s+\S/i.test(t)) {   // станция ЕГКО — «ст. ж/д …» (правило 15); «СТ Ромашка» (садовое товарищество, без точки) — не станция
      feats.push({ g: ft.g, nm: true, label: LabelFmt.stationLabel(t), ls: 4.6, lf: "sans-bold", lh: .55, lcol: "#141414", la: 0, nudge: true }); return; }
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

// Дороги листа (владелец 06.10.2026, T84): на векторных схемах (основа не снимок: листы 4–8) — полигоны ЕГКО, Яндекс — только
// там, где у ЕГКО в рамке пусто или мало; на снимке (3, 9) — Яндекс, ЕГКО запасным (решение — roadsrc.js). Дорог по осям
// (calc.uds_*) на листах нет. Выбранные полигоны чистятся (roadclean.js: слияние без швов, без обрывков и островков) и
// переносятся в слой yandex.hd_roads: контур (casing), препятствия подписям, доля участка под дорогой и легенда видят один
// набор. Возвращает true, если в рамке есть полигоны дорог.
function roadSource(out, sheet, bb) {
  const hd = out.layers.find(l => l.key === "yandex.hd_roads"), eg = out.layers.find(l => l.key === "egko.roads");
  const area = g => /Polygon/.test(g?.type) ? (safe(() => { const c = turf.bboxClip({ type: "Feature", geometry: g, properties: {} }, bb); return c?.geometry?.coordinates?.length ? turf.area(c) : 0; }) || 0) : 0;
  const sum = fts => fts.reduce((s, f) => s + area(f.g), 0);
  const areas = { ya: sum(hd?.features || []), egko: sum(eg?.features || []) }, order = SheetLayout.roadOrder(sheet);
  // порядок источников, который владелец поменял в окне «Слои и листы» (T86c), главнее правила roadsrc.js; не менял — как раньше
  const src = order ? SheetLayout.pickByOrder(order, areas) : RoadSrc.pickRoadSource(areas, { vector: sheet.basemap !== "sat" });
  const chosen = src === "egko" ? eg : src === "yandex" ? hd : null;
  let layer = hd;
  if (src === "egko" && !hd) { eg.key = "yandex.hd_roads"; layer = eg; }
  if (layer) {
    const fts = (chosen?.features || []).filter(f => /Polygon/.test(f.g?.type)), geoms = fts.map(f => f.g);
    // дорога, которой нет у ЕГКО, но есть у Яндекса (лист 7–8, южнее НИКИЭТ), не теряется: Яндекс — только там, где у ЕГКО пусто (F4)
    if (src === "egko" && hd && layer !== eg) geoms.push(...RoadClean.gapFill(turf, geoms, hd.features.filter(f => /Polygon/.test(f.g?.type)).map(f => f.g), bb));
    const g = fts.length ? RoadClean.clean(turf, geoms, bb) : null;
    layer.features = g ? [{ ...fts[0], g, props: undefined, label: undefined }] : [];
  }
  if (eg && eg !== layer) eg.features = [];
  return src !== "none" && !!layer?.features.length;
}
const ROADS_WORD = "территории автодорог, улиц и местных проездов";   // как в образце владельца 06.10.2026 (было «…, улиц, местных…»)   // как в образце «ГК Царицыно», лист 5
function conceptSheet(out, sheet, bb) {
  const ha = fmt(m2(TERR) / 1e4, 2), terr = { kind: "line", stroke: C_TERR, width: C_TW, dash: [C_TW, C_TW], label: `территории рассмотрения (${ha} га)` };
  out.look = "concept"; out.noFrame = true; out.callout = undefined; out.bleed = !!sheet.bleed;
  // полупрозрачная белая маска за границей территории — на схемах с белой основой, как в примере «Хатминки»; на снимке и
  // на фрагменте Генплана её нет (владелец 30.09.2026)
  // листы документации (7, 8) — без маски: документы почти все снаружи (владелец 30.09.2026, как в образцах)
  out.terrMask = sheet.basemap !== "sat" && ["photos", "use"].includes(sheet.concept) ? .55 : undefined;
  out.terrStyle = { stroke: C_TERR, width: C_TW, dash: [C_TW, C_TW] };
  const L = key => out.layers.find(l => l.key === key), bounds = { title: "Границы", items: [terr] };
  const box = turf.bboxPolygon(bb), inFrame = ft => /Polygon|Line/.test(ft.g?.type) && safe(() => turf.booleanIntersects(ft.g, box));
  const k = sheet.concept, hasRoads = roadSource(out, sheet, bb);
  waterLabels(out, bb);
  // тонкие реки ЕГКО нужны только для подписей ручьёв: на снимке вода видна сама (владелец 30.09.2026: голубых линий
  // на листе 3 быть не должно)
  if (sheet.basemap === "sat") (out.layers.find(l => l.key === "egko.water")?.features || []).forEach(ft => { if (/Line/.test(ft.g?.type)) ft.nl = true; });
  namedPlaces(out, bb, railStations(out, bb));
  if (k === "ortho" || k === "district") {
    // выноска как в «ГК Царицыно»: полупрозрачная белая плашка без рамки, серый текст в три строки, белый пунктир к точке
    // внутри территории; плашка — над территорией, а если до верхнего края листа меньше 35 мм — под ней (правила подписей)
    const [w, s, e, n] = turf.bbox(TERR), up = (bb[3] - n) * 110540 / ((out.scale || 2000) / 1000) >= 35;
    const edge = safe(() => inter(TERR, turf.bboxPolygon(up ? [w, n - (n - s) * .3, e, n] : [w, s, e, s + (n - s) * .3])));
    const tgt = (edge && safe(() => turf.pointOnFeature(edge))) || turf.pointOnFeature(TERR), [tx] = tgt.geometry.coordinates;
    out.layers.push({ title: "Выноска территории", features: [{ g: { type: "Point", coordinates: [tx, up ? n : s] }, nodot: true, lead: tgt.geometry.coordinates,
      label: `Проектируемая территория – ${ha} га`, ls: 3.4, lf: "sans-bold", lcol: "#111111", lbox: C_TERR, lboxW: .7, lboxAlpha: 1, leadSolid: true, ldy: up ? -22 : 16 }] });   // владелец 07.10.2026 (#45): плашка в пурпурной рамке, чёрный текст в одну строку, белая линия к территории
    // маска района (владелец 07.10.2026, #45: «это маска от района, все кроме района светлое»): всё за границей района своей территории — под белой дымкой
    const home = homeAdm().district; if (home) { const part = safe(() => inter(home, turf.bboxPolygon(bb))); if (part?.geometry) out.distMask = { alpha: .45, geometry: part.geometry }; }
    // граница района — в легенде, только если она видна на листе
    const box = turf.bboxPolygon(bb), dist = (L("gisogd.admin")?.features || []).some(ft => /Polygon/.test(ft.g?.type)
      && safe(() => turf.flatten(turf.polygonToLine({ type: "Feature", geometry: ft.g, properties: {} })).features.some(l => turf.booleanIntersects(l, box))));
    // карта района (лист «в границах сит. плана»): дороги OSM — линии по классам, ширина на бумаге в мм; подписаны только магистрали и главные улицы
    const dRoads = k === "district" ? (L("osm.roads")?.features || []).filter(inFrame) : [];
    if (k === "district") {
      const W = { motorway: 2.2, trunk: 1.8, primary: 1.4, secondary: 1, tertiary: .7, motorway_link: .9, trunk_link: .9, primary_link: .8 }, NAMED = new Set(["motorway", "trunk", "primary"]);
      (L("osm.roads")?.features || []).forEach(ft => { const t = ft.props?.["Тип дороги"]; ft.w = MM(W[t] || .5); if (!NAMED.has(t)) ft.label = null; });
    }
    out.cLegend = [{ items: [terr, ...(dist ? [{ kind: "line", stroke: "#e30613", width: 1.2, label: "района" }] : []),
      ...(k === "district" ? (dRoads.length ? [{ kind: "line", stroke: ROAD_YELLOW, width: 1.2, label: "автомобильные дороги" }] : [])
        : hasRoads ? [{ kind: "fill", fill: "#f3d98c", stroke: "#f3d98c", label: ROADS_WORD }] : [])] }];   // правило 7: только то, что видно
  }
  if (k === "photos") {
    out.casing = ["yandex.hd_roads"];               // дороги контуром — один общий контур на все куски
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
    const roadPolys = ["yandex.hd_roads"].flatMap(key => L(key)?.features || []).filter(inFrame)
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
    const step = Math.max(2, per / 20000);                        // не больше ~20000 точек на лист: шаг 2 м — стык цветов без «пилы» (06.10.2026)
    seeds.forEach(({ g, u }) => (g.type === "Polygon" ? [g.coordinates] : g.coordinates).forEach(poly => {
      const ring = turf.lineString(poly[0]), L0 = turf.length(ring, { units: "meters" });
      for (let d = 0; d < L0; d += step) { const c = turf.along(ring, d, { units: "meters" }).geometry.coordinates;
        if (c[0] < bb[0] || c[0] > bb[2] || c[1] < bb[1] || c[1] > bb[3]) continue;
        const key = c[0].toFixed(5) + "," + c[1].toFixed(5); if (seenPt.has(key)) continue; seenPt.add(key);   // ~1 м: совпадающие точки ломают ячейки
        pts.push(turf.point(c, { fill: u[1] })); } }));
    const dx = (bb[2] - bb[0]) * .02, dy = (bb[3] - bb[1]) * .02;          // рамка с запасом: точки на краю ломают ячейки
    const cells = pts.length > 2 ? safe(() => turf.voronoi(turf.featureCollection(pts), { bbox: [bb[0] - dx, bb[1] - dy, bb[2] + dx, bb[3] + dy] })) : null;
    // ячейки одного цвета сливаются, стык двух цветов сглаживается: у соседей точки идут вперемешку, и граница ячеек
    // была «пилой» с зубцами в шаг точек (владелец 06.10.2026: «на сущполе странно покрашено треугольниками»)
    const merged = cells && safe(() => {
      const fc = turf.featureCollection(cells.features.map((c, i) => c && turf.feature(c.geometry, { fill: pts[i].properties.fill })).filter(Boolean));
      return turf.dissolve(fc, { propertyName: "fill" }).features.map(f => safe(() => turf.simplify(f, { tolerance: step * 1.2 / 111320, highQuality: false })) || f);
    });
    if (merged) use.splice(1, 0, ...merged.map(c => ({ g: c.geometry, fill: c.properties.fill, stroke: c.properties.fill, w: .6, a: 1 })));
    else if (cells) use.splice(1, 0, ...cells.features.map((c, i) => c && ({ g: c.geometry, fill: pts[i].properties.fill, stroke: pts[i].properties.fill, w: .6, a: 1 })).filter(Boolean));
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
    // СЗЗ (F1, 06.10.2026) — каждая зона отдельно, а не слитая фигура: зоны идут внахлёст, слитый контур целиком уходил за
    // рамку, и границ установленных СЗЗ на листе не было. szzFull — зоны целиком (для пояснения под легендой),
    // szzParts — их части в рамке с запасом (для границ)
    const byCode = new Map(), szzFull = new Map(), szzParts = new Map(), push = (m, k, v) => m.set(k, [...(m.get(k) || []), v]);
    ["gisogd.zouit", "gisogd.szz", "gisogd.vodookhr"].forEach(key => { const l = L(key); if (!l) return;
      l.features.filter(inFrame).forEach(ft => { const c = zouitCode(key, ft.props || {}), whole = { type: "Feature", geometry: ft.g, properties: {} };
        if (SZZ_OGD[c]) push(szzFull, c, whole);
        if (c != null && lgr.has(c)) return;                     // граница уже есть линией Сводного плана
        const part = safe(() => inter(whole, clip)); if (!part) return;
        if (SZZ_OGD[c]) { push(szzParts, c, part); return; }
        const k = c ?? "?"; push(byCode, k, part); });
      l.features = []; });
    // подтопление вложено: слабое включает умеренное и сильное, умеренное — сильное; без этого граница слабого шла
    // по границе умеренного с засечками в другую сторону (владелец 30.09.2026)
    const nested = { 66: [65, 64], 65: [64] };
    Object.entries(nested).forEach(([k, inner]) => { if (byCode.has(+k)) byCode.set(+k, [...byCode.get(+k), ...inner.flatMap(c => byCode.get(c) || [])]); });
    const zoneFeats = [], smoothZone = z => safe(() => { const r = buf(buf(z, 1.5), -3); const q = r && buf(r, 1.5); return q && turf.simplify(q, { tolerance: 1.5 / 111320, highQuality: false }); }) || z;
    byCode.forEach((parts, k) => {
      const c = k === "?" ? null : k, lt = c != null ? Linetypes.forCode(ZONE_LINE[c]?.lt ?? c, -1) : null;
      const one0 = parts.slice(1).reduce((acc, p) => safe(() => turf.union(turf.featureCollection([acc, p]))) || acc, parts[0]);
      // контур без шипов и петель: закрытие и открытие на 1,5 м и упрощение на 1,5 м — на листе это доли миллиметра,
      // а зигзаги исходной геометрии ГИС ОГД пропадают (правило 11, лист 5)
      const one = smoothZone(one0);
      const lines = safe(() => turf.polygonToLine(turf.rewind(one)));
      const g = lines && (lines.type === "FeatureCollection" ? { type: "MultiLineString", coordinates: lines.features.flatMap(f => f.geometry.type === "LineString" ? [f.geometry.coordinates] : f.geometry.coordinates) } : lines.geometry);
      if (!g) return;
      if (c != null && !zk.has(c) && !FLOOD_T[c]) zk.set(c, lt || null);
      const ml = g.type === "LineString" ? { type: "MultiLineString", coordinates: [g.coordinates] } : g;
      if (FLOOD_T[c]) { zoneFeats.push({ code: c, g: ml, flood: c, lc: FLOOD_C, w: 1.3 }); return; }   // подтопление — знаками «Хатминки»
      zoneFeats.push({ code: c, g: ml, lt: lt ? [lt] : [], miss: lt || c == null ? [] : [[c, ""]], lc: LGRC[c] || "#ff0000", w: 1.3,
        ll: lt || c == null ? undefined : LGRS[c]?.line_label }); });
    // границы СЗЗ: контур каждой зоны (без шипов), обрезанный по рамке с запасом 1 % — кромка запаса за рамкой не рисуется
    const mg = [(bb[2] - bb[0]) * .01, (bb[3] - bb[1]) * .01], lbb = [bb[0] - mg[0], bb[1] - mg[1], bb[2] + mg[0], bb[3] + mg[1]];
    szzParts.forEach((parts, c) => {
      const lines = parts.flatMap(p => { const one = smoothZone(p), ln = safe(() => turf.polygonToLine(turf.rewind(one))); if (!ln) return [];
        return (ln.type === "FeatureCollection" ? ln.features : [ln]).flatMap(f => (f.geometry.type === "LineString" ? [f.geometry.coordinates] : f.geometry.coordinates))
          .flatMap(co => { const k = safe(() => turf.bboxClip(turf.lineString(co), lbb))?.geometry; return !k ? [] : k.type === "LineString" ? [k.coordinates] : k.coordinates; }); })
        .filter(l => l.length > 1);
      if (!lines.length) return;
      zk.set(c, null);
      zoneFeats.push({ code: c, g: { type: "MultiLineString", coordinates: lines }, lt: [], miss: [], lc: SZZ_OGD[c].color, w: SZZ_W, dash: SZZ_OGD[c].dash }); });   // как на ГИС ОГД
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
    // пояснение под легендой (правило 14): в зонах каких видов лежит территория — по вложенности (доля территории под зонами
    // вида) и числу зон, а не по касанию (F1, AUD-norms 12). Знака в легенде у вида нет, если его границы в рамке не видны
    const szzKinds = [...szzFull].map(([c, fs]) => { const tm = Math.max(m2(TERR), 1);
      const hit = fs.filter(f => { const x = safe(() => inter(f, TERR)); return x && m2(x) >= 1; }), u = hit.reduce((a, f) => a ? safe(() => turf.union(turf.featureCollection([a, f]))) || a : f, null);
      const ux = u && safe(() => inter(u, TERR)); return { code: c, n: hit.length, share: ux ? Math.min(1, m2(ux) / tm) : 0 }; });
    const szzText = LegendRules.szzNote(szzKinds), szzNotes = szzText ? [szzText] : [];
    // надпись знака вдоль линии (правило 4.38): текст Эталона без лишней «О» (F2), и не в резерве угловой надписи (F2, 4.10) —
    // линии, задевающие резерв, рисуются без надписи; остальные подписываются с шагом печати, не дублями в углу
    const rsv = cornerReserve(bb, out.scale || 1000), noText = [];
    zoneFeats.forEach(f => { if (!f.ll) return; f.ll = ZONE_LL[f.code] || f.ll;
      const hit = f.g.coordinates.filter(l => safe(() => turf.booleanIntersects(turf.lineString(l), rsv)));
      if (!hit.length) return;
      f.g = { type: "MultiLineString", coordinates: f.g.coordinates.filter(l => !hit.includes(l)) };
      noText.push({ ...f, g: { type: "MultiLineString", coordinates: hit }, ll: undefined }); });
    zoneFeats.push(...noText.filter(f => f.g.coordinates.length));
    // СЗЗ — чёрным поверх белой дымки за территорией (владелец 06.10.2026: «установленные СЗЗ черный контур»; под дымкой
    // чёрный печатался серым)
    const szzOver = zoneFeats.filter(f => SZZ_OGD[f.code]), zoneRest = zoneFeats.filter(f => !SZZ_OGD[f.code]);
    if (L("gisogd.zouit")) L("gisogd.zouit").features = zoneRest;
    else out.layers.push({ title: "ЗОУИТ и зоны ограничений (ОГД)", features: zoneRest });
    if (szzOver.length) out.layers.push({ key: "gisogd.szz.lines", title: "Санитарно-защитные зоны", over: true, features: szzOver });
    // ЛГР и красные линии — поверх белой дымки за территорией, чёткими (владелец 06.10.2026: «красные линии и все лгр
    // потолще»: под дымкой толстые линии оставались бледными)
    ["gisogd.zouit", "gisogd.red_lines"].forEach(k => { if (L(k)) L(k).over = true; });
    // правило 7 (T85a): участки и застройка — знаком, только если есть в рамке
    const hasParcels = (L("nspd.parcels")?.features || []).some(inFrame), hasBuild = (L("egko.buildings")?.features || []).some(inFrame);
    out.cLegend = [{ title: "Границы", items: [terr, ...(hasParcels ? [{ kind: "line", stroke: "#0000ff", width: .35, label: "земельных участков, поставленных на кадастровый учёт" }] : [])] },
      ...(hasBuild ? [{ title: "Застройка", items: [{ kind: "fill", fill: "#ffffff", stroke: "#8c8c8c", label: "существующая" }] }] : []),
      // группы и порядок — как в образце владельца (06.10.2026); только зоны, которые есть на листе (правило 7)
      ...[["Функциональные зоны специализированного назначения", SPEC_ZONES], ["Транспортная инфраструктура", TRANSPORT_ZONES]]
        .map(([title, zs]) => ({ title, items: zs.filter(([n]) => seen.has(n)).map(([n, c]) => ({ kind: "fill", fill: c, stroke: "#7a7a7a", label: n })) }))
        .filter(g => g.items.length),
      ...(lgr.size || zk.size ? [{ title: "Линии градостроительного регулирования, действующие",
        items: [...[...lgr].map(([c, n]) => [c, n, LGR_LEG[c] || "граница " + zoneGen(LGRT[c] || "")]), ...[...zk].filter(([c]) => !lgr.has(c)).map(([c, n]) => [c, n, "граница " + zoneGen(LGRT[c] || "")])]
          .sort((a, b) => SZZ_ORD(a[0]) - SZZ_ORD(b[0])).map(([c, n, t]) => [c, n, String(t).replace(/(^|\s)мин\.\s/, "$1минимальных ")])   // слово полностью (правило 11)
          .map(([c, n, t]) => SZZ_OGD[c] ? { kind: "line", stroke: SZZ_OGD[c].color, width: SZZ_W * .26, dash: SZZ_OGD[c].dash?.map(v => v * .26), label: t }
            : ({ kind: "lt", name: n || undefined, stroke: ZONE_LINE[c]?.color || LGRC[c] || "#ff0000", dash: n ? undefined : (LGRS[c]?.dash_mm || [3, 1]).map(v => v * .5),
            ll: n || (LGRS[c]?.line_label || "").length > 20 ? undefined : LGRS[c]?.line_label, label: t })) }] : [])];   // длинная надпись в знак 13 мм не входит
    // подтопление — своей группой, знаками и подписями примера «Хатминки»
    const fl = [64, 65, 66].filter(c => zoneFeats.some(f => f.flood === c && f.g.coordinates.length));
    if (fl.length) out.cLegend.push({ title: "Зона подтопления от паводка 1% обеспеченности (глубина залегания грунтовых вод)",
      items: fl.map(c => ({ kind: "flood", code: c, stroke: FLOOD_C, label: FLOOD_T[c] })) });
    // пояснение «Территория расположена в границах … санитарно-защитных зон» не печатается (владелец 06.10.2026: «эту
    // сноску убери»)
    void szzNotes;
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
    // цвета всех зон — по таблице MapInfo функциональных зон ТиНАО владельца (ФункциональныеЗоны_ПрисоединенныеТер.TAB),
    // по индексу типа зоны (fz_type в ГИС ОГД = ФЗ_тип таблицы), без прозрачности; цвета «Хатминки» отменены
    // (владелец 01.10.2026: «Всё по таблице ТиНАО»). Зона без индекса — по названию, иначе палитра Эталона Генплана
    // таблица, названия и выбор цвета — в gpzones.js (чистые функции, тест test_gpzones_js.py); старая Москва несёт индекс
    // в fztip и имя в naimfunkzony, ТиНАО — fz_type и «Вид зоны»: цвет по индексу берётся из обоих слоёв
    const gpFill = (name, idx) => GpZones.fill(name, idx, nm => GPZ[nm]?.fill);
    const zoneEdges = [];
    ["gisogd.func_zones", "gisogd.func_zones_tinao"].forEach(key => (L(key)?.features || []).forEach(ft => {
      const f0 = gpFill(GpZones.zoneName(ft.props), GpZones.zoneIdx(ft.props)); if (f0) ft.fill = f0; ft.a = 1;
      if (/Polygon/.test(ft.g?.type)) zoneEdges.push(...safe(() => turf.flatten(turf.polygonToLine({ type: "Feature", geometry: ft.g, properties: {} })).features.map(l => l.geometry)) || []);
      ft.w = 0; Object.assign(ft, { lcol: "#141414", lhc: "#ffffff", lh: .4, ul0: true, lss: [1, 1.15] });   // номер и индекс — чёрные, номер подчёркнут, индекс крупнее
    }));
    // границы зон там, где они идут по границе территории (ближе 1 мм на бумаге), не рисуются: иначе чёрная линия
    // просвечивает сквозь пунктир территории (правило 11)
    const tLines = turf.flatten(turf.polygonToLine(TERR)).features, tol = (out.scale || 2000) / 1000;
    const nearT = c => tLines.some(l => (safe(() => turf.pointToLineDistance(c, l, { units: "meters" })) ?? 1e9) < tol);
    const cut = [];
    zoneEdges.forEach(g => { let run = [];
      g.coordinates.forEach((c, i) => { const next = g.coordinates[i + 1], mid = next && [(c[0] + next[0]) / 2, (c[1] + next[1]) / 2];
        run.push(c);
        if (!next || (nearT(c) && nearT(next) && nearT(mid))) { if (run.length > 1) cut.push({ type: "LineString", coordinates: run }); run = next ? [next] : []; } });
      if (run.length > 1) cut.push({ type: "LineString", coordinates: run }); });
    zoneEdges.length = 0; zoneEdges.push(...cut);
    // границы зон — чёрные, поверх дорог и застройки (владелец 30.09.2026: «границы зон должны быть выше»)
    out.layers.push({ title: "Границы функциональных зон", features: zoneEdges.map(g => ({ g, fill: "#000000", stroke: "#000000", w: MM(.35) })) });   // 0,35 мм
    // легенда — только зоны, видимые в рамке (больше 0,5 мм² на бумаге), в порядке образца «Хатминки» (правила 7, 11)
    const kk = (out.scale || 2000) / 1000, seenZ = [];
    ["gisogd.func_zones", "gisogd.func_zones_tinao"].forEach(key => (L(key)?.features || []).forEach(ft => {
      if (!/Polygon/.test(ft.g?.type)) return; const x = safe(() => inter({ type: "Feature", geometry: ft.g, properties: {} }, box));
      const a = x ? m2(x) / (kk * kk) : 0, name = GpZones.zoneName(ft.props), ix = GpZones.zoneIdx(ft.props);
      if (a > .5) seenZ.push({ name, idx: ix, fill: gpFill(name, ix), a, terr: !!safe(() => turf.booleanIntersects({ type: "Feature", geometry: ft.g, properties: {} }, TERR)) }); }));
    // знак — каждая зона, видимая в рамке; зоны одного цвета — одной строкой (F3); текст — название типа зоны как в слое
    const ORDER = ["общественно-жилая зона", "жилая зона", "природно-жилая зона", "природная зона", "общественно-производственно-жилая зона", "общественно-производственная зона"];
    const zones = GpZones.legendRows(seenZ, ORDER).map(r => ({ label: r.name, z: { idx: new Set(r.idx) } }));
    // индексы типа функционального назначения — только те, что на карте, с названием типа из тех же зон (как в образце)
    // индекс типа функционального назначения — цифрами в прямоугольнике знака своей зоны, без отдельного списка
    // (владелец 30.09.2026: «впиши цифры в прямоугольник условного обозначения… убрав дублирование»)
    // пояснения номера и индекса — только если зоны видны (правило 7, T85a)
    out.cLegend = [bounds, ...(zones.length ? [{ title: "Функциональные зоны", items: [...zones.map(({ label, z }) => { const ix = [...z.idx].sort();
        return { kind: "fill", fill: gpFill(label, ix[0]), stroke: "#3c3c3c", a: 1, num: ix.length ? ix.join(", ") : undefined, label: String(label).toLowerCase() }; }),
      { kind: "text", sample: "10", family: "sans-bold", underline: true, label: "номер функциональной зоны" },
      { kind: "text", sample: "500", family: "sans-bold", label: "индекс типа функционального назначения территории" }] }] : [])];
    if (out.table?.rows?.length) out.gpTable = { title: "Функциональные зоны и их параметры", widths: [.17, .17, .3, .36],
      // «функц. зоны» не разрывается (владелец 01.10.2026, правило 6.12)
      cols: ["Номер функц.\u00a0зоны", "Индекс функц.\u00a0зоны", "Тип функц.\u00a0зоны", "Прогнозируемый фонд застройки функц.\u00a0зоны, тыс.\u00a0кв.\u00a0м"],
      rows: out.table.rows.map(r => [r[0], r[1], String(r[2]).toLowerCase(), r[3]]) };
    out.table = undefined;
  }
  if (k === "docs") {
    // схема документации (#37, п. 2 владельца 07.10.2026): ППТ, ПМТ, ГПЗУ, АГР и КРТ на одной светлой подложке по аналогии с ДПТ «Профсоюзная»;
    // номера и списки — у ближайших документов (в колонку их помещается около восьми), остальные нарисованы без номера, как в аналоге
    const agr = (L("gisogd.agr")?.features || []).filter(inFrame).map(ft => ({ type: "Feature", geometry: ft.g, properties: ft.props || {} })), used = new Set();
    const lists = conceptDocs(out, bb, [PPT_GROUP, PMT_GROUP, gpzuGroup(agr, used)], { total: DOCS_TOTAL });
    (L("gisogd.gpzu")?.features || []).forEach(ft => { ft.fill = "#7b7bf2"; ft.stroke = "#7b7bf2"; });   // цвет ГПЗУ — общий, рамки списка — чёрные
    if (!agr.length) lists.forEach(l => { l.title = String(l.title).replace(/\s+и свидетельства об утверждении АГР$/, ""); });
    out.cLists = lists;
    // КРТ: решения о комплексном развитии соседних территорий — штриховкой; своё решение — это сама территория, поверх неё штриховки нет
    const kl = L("gisogd.krt");
    if (kl) kl.features = kl.features.filter(ft => { const f = { type: "Feature", geometry: ft.g, properties: {} }, x = /Polygon/.test(ft.g?.type) && safe(() => inter(f, TERR));
      return !(x && m2(x) > .8 * m2(TERR) && m2(f) < 1.5 * m2(TERR)); });
    const has = key => (L(key)?.features || []).some(inFrame);
    const hv = { ppt: has("gisogd.ppt"), pmt: has("gisogd.pmt"), gpzu: has("gisogd.gpzu"), agr: agr.length > 0, krt: has("gisogd.krt"), parcels: has("nspd.parcels") };
    out.cLegend = LegendRules.pruneGroups([
      { title: "Границы", items: [terr, ...(hv.parcels ? [{ kind: "line", stroke: "#1f3fbf", width: .35, label: "земельных участков, поставленных на кадастровый учёт" }] : [])] },
      { title: "Разработанная документация", items: [
        ...(hv.ppt ? [{ kind: "fill", hatch: true, fill: "#222222", stroke: "#222222", angle: 135, label: "проекты планировки территории" }] : []),
        ...(hv.pmt ? [{ kind: "fill", stroke: "#00d000", width: .5, label: "проекты межевания территории" }] : []),
        ...(hv.gpzu ? [{ kind: "fill", hatch: true, fill: "#7b7bf2", stroke: "#7b7bf2", angle: 45, label: "градостроительный план земельного участка" }] : []),
        ...(hv.agr ? [{ kind: "fill", hatch: true, fill: "#ff3b3b", stroke: "#ff3b3b", angle: 135, label: "архитектурно-градостроительное решение" }] : []),
        ...(hv.krt ? [{ kind: "fill", hatch: true, fill: "#e0892f", stroke: "#b35d00", angle: 45, label: "комплексное развитие территории" }] : [])] }]);
  }
  if (k === "pzz") {
    // выкопировка из ПЗЗ (#37): границы территориальных зон и коды видов разрешённого использования; в легенде — только видимое (правило 7)
    const zs = (L("gisogd.pzz_zones")?.features || []).filter(inFrame);
    out.cLegend = [{ title: "Границы", items: [terr, ...(zs.length ? [{ kind: "line", stroke: "#6a3d9a", width: .5, label: "территориальных зон" }] : [])] },
      ...(zs.some(ft => ft.label) ? [{ title: "Подписи", items: [{ kind: "text", sample: "4.9", family: "sans-bold", label: "коды видов разрешённого использования земельных участков и объектов капитального строительства" }] }] : [])];
  }
  if (k === "ppt") {
    out.cLists = conceptDocs(out, bb, [PPT_GROUP, PMT_GROUP]);
    // легенда и название листа — только то, что попало в рамку (правила 7, 11, 12)
    const has = key => (L(key)?.features || []).some(inFrame);
    // ничего нет — название не трогаем, группы «Разработанная документация» нет, лист «не готов» (conceptWhy)
    const hv = { ppt: has("gisogd.ppt"), pmt: has("gisogd.pmt") };
    out.title = LegendRules.docTitle("ppt", out.title || sheet.title || "", hv);
    out.cLegend = LegendRules.pruneGroups([bounds, { title: "Разработанная документация", items: [
      ...(hv.ppt ? [{ kind: "fill", hatch: true, fill: "#222222", stroke: "#222222", angle: 135, label: "проекты планировки территории" }] : []),
      ...(hv.pmt ? [{ kind: "fill", stroke: "#00d000", width: .5, label: "проекты межевания территории" }] : [])] }]);
  }
  if (k === "gpzu") {
    // ГПЗУ с номером на карте; свидетельство АГР на том же участке — второй строкой того же пункта, как в образце
    const agr = (L("gisogd.agr")?.features || []).filter(inFrame).map(ft => ({ type: "Feature", geometry: ft.g, properties: ft.props || {} }));
    const used = new Set();
    const lists = conceptDocs(out, bb, [gpzuGroup(agr, used)]);
    (L("gisogd.gpzu")?.features || []).forEach(ft => { ft.fill = "#7b7bf2"; ft.stroke = "#7b7bf2"; });   // цвет ГПЗУ — общий, рамки списка — чёрные
    out.cLists = lists;
    // название и знаки — по тому, что в рамке (правила 7, 12); ничего нет — группы нет, лист «не готов» (conceptWhy)
    const hv = { gpzu: (L("gisogd.gpzu")?.features || []).some(inFrame), agr: agr.length > 0 };
    out.title = LegendRules.docTitle("gpzu", out.title || sheet.title || "", hv);
    if (!agr.length) lists.forEach(l => { l.title = String(l.title).replace(/\s+и свидетельства об утверждении АГР$/, ""); });
    out.cLegend = LegendRules.pruneGroups([bounds, { title: "Разработанная документация", items: [
      ...(hv.agr ? [{ kind: "fill", hatch: true, fill: "#ff3b3b", stroke: "#ff3b3b", angle: 135, label: "архитектурно-градостроительное решение" }] : []),
      ...(hv.gpzu ? [{ kind: "fill", hatch: true, fill: "#7b7bf2", stroke: "#7b7bf2", angle: 45, label: "градостроительный план земельного участка" }] : [])] }]);
  }
  if (k === "parcels") {
    const pl = L("nspd.parcels"), cards = [], marks = [];
    (pl?.features || []).forEach(ft => {
      const f = { type: "Feature", geometry: ft.g, properties: ft.props || {} }, x = /Polygon/.test(ft.g?.type) && safe(() => inter(f, TERR));
      if (!x || m2(x) < Math.min(50, m2(f) * .05)) return;
      ft.stroke = "#0000ff"; ft.fill = "#0000ff"; ft.w = 1;   // толщина — как у участков за границей (владелец 30.09.2026)
      const p = f.properties, kn = p["Кадастровый номер"] || "—";
      cards.push({ feat: ft, area: m2(f), rows: [["Кадастровый номер", kn], ["Адрес", p["Адрес"] || "—"],
        // площадь — уточнённая по ЕГРН (она же площадь границы в МСК), затем площадь из записи, затем посчитанная;
        // форма собственности — как записана (правится в свойствах участка: «Общая долевая собственность», «Аренда с …»)
        ["Площадь (га)", fmt((+p["Площадь уточнённая, м²"] || +p["Площадь участка, м²"] || m2(f)) / 1e4, 4)], ["Вид разрешённого использования", p["ВРИ"] || "—"],
        ["Форма собственности", String(p["Форма собственности"] || p["Вид права"] || "—")]] });
      // номер — в глубине самой большой части участка (центр масс, если он внутри), а не на узком краю
      const big = x.geometry.type === "MultiPolygon" ? x.geometry.coordinates.map(c => turf.polygon(c)).reduce((a, b) => m2(b) > m2(a) ? b : a) : x;
      const cm = safe(() => turf.centerOfMass(big)), at = cm && safe(() => turf.booleanPointInPolygon(cm, big)) ? cm : safe(() => turf.pointOnFeature(big));
      cards[cards.length - 1].at = at && { g: at.geometry, inside: m2(x) * (1000 / (out.scale || 2000)) ** 2 > 120, zone: bigRing(big),
        zone2: bigRing(f) };                                    // весь участок — если в территории от него лишь узкая кромка
    });
    pl && out.layers.push({ title: "Кадастровые номера", features: marks });
    // участки территории пронумерованы, как в примере «Хатминки», — номер в карточке, на карте не показывается
    // (владелец 30.09.2026: «пронумеруй, но не отображай»); порядок — от большего участка к меньшему
    cards.sort((a, b) => b.area - a.area);
    // номер участка в синем кружке, как в «Хатминки»; сведения — в таблице по номеру (владелец 30.09.2026)
    cards.forEach((c, i) => c.at && marks.push({ g: c.at.g, nodot: true, leader: true, circle: true, inside: c.at.inside, zone: c.at.zone, zone2: c.at.zone2,
      label: String(i + 1), ls: 4.2, lf: "sans-bold", lcol: "#1f3fbf" }));
    // все участки — одной таблицей (карточки не помещались); номер — только в таблице, на схеме — кадастровый номер
    const val = (c, k) => (c.rows.find(r => r[0] === k) || [, "—"])[1];
    out.gpTable = { title: "Сведения о земельных участках в границах территории рассмотрения",
      cols: ["№", "Кадастровый номер", "Площадь, га", "Вид разрешённого использования", "Форма собственности"], widths: [.06, .27, .13, .33, .21], fs: 8,   // widths — запас, ниже пересчитывается
      rows: cards.map((c, i) => [String(i + 1), val(c, "Кадастровый номер"), val(c, "Площадь (га)"), LabelFmt.vri(val(c, "Вид разрешённого использования")),
        LabelFmt.tieShort(String(val(c, "Форма собственности")))]) };
    out.gpTable.widths = LabelFmt.colWidths(out.gpTable.cols, out.gpTable.rows);   // ширины — по содержимому, ВРИ самая широкая (F5)   // «с 02.05.2023» не разрывается (правило 11)
    out.veil = .15;                                             // белая дымка на снимке — границы участков не сливаются; слабее (владелец 06.10.2026: «спутник плохого качества»)
    // правило 7 (T85a): участки вне и в границах территории — каждый знак только если такие участки видны
    const outside = (pl?.features || []).some(ft => inFrame(ft) && !cards.some(c => c.feat === ft));
    out.cLegend = [{ title: "Границы", items: [terr,
      ...(outside ? [{ kind: "line", stroke: "#c9c9ff", width: .35, label: "земельных участков вне границ территории рассмотрения, поставленных на кадастровый учёт" }] : []),
      ...(cards.length ? [{ kind: "line", stroke: "#0000ff", width: .35, label: "земельных участков в границах территории рассмотрения, поставленных на кадастровый учёт" },
        { kind: "num", sample: "1", stroke: "#1f3fbf", label: "порядковый номер земельного участка в таблице" }] : [])] }];   // знак номера, как в «Хатминки» (правило 11)
  }
  out.layers.forEach(l => l.features.forEach(ft => { delete ft.props; }));   // свойства нужны были только здесь
  if (out.cLegend) out.cLegend = LegendRules.pruneGroups(out.cLegend);   // группа без знаков не печатается (T85a)
  if (!out.cLegend && k !== "photos") out.cLegend = [bounds];
  conceptRail(out, box, k);
  conceptStations(out, k);
  if (out.cLegend) out.cLegend = LegendRules.notesLast(out.cLegend);   // пояснения под легендой — после всех групп, включая «Транспорт» (слайд-правило 5.9)
  conceptDistricts(out, bb, k);
}
// железная дорога на белых схемах — главные пути знаком топоплана: чёрная линия, поверх белые штрихи (владелец
// 05.10.2026: «нет железной дороги в правильном обозначении»); в легенде — только если видна (правило 7)
function conceptRail(out, box, k) {
  const rail = out.layers.find(l => l.key === "yandex.rail"); if (!rail) return;
  rail.features = rail.features.filter(ft => /Line/.test(ft.g?.type) && safe(() => turf.booleanIntersects(ft.g, box)));
  if (!rail.features.length) return;
  rail.over = true;                                               // знак виден и за территорией, поверх белой маски
  out.layers.push({ key: "yandex.rail.dash", title: "Железная дорога: штрихи", over: true, features: rail.features.map(f => ({ ...f, fill: "#ffffff", stroke: "#ffffff", lc: "#ffffff", w: 1.6, dash: [7.7, 7.7], label: null })) });
  if (k !== "photos" && out.cLegend) out.cLegend.push({ title: "Транспорт", items: [{ kind: "rail", label: "железнодорожные пути" }] });
}
// соседние районы (владелец 05.10.2026: «на севере и юге другой район, а подписано только Гольяново»): если в рамку
// попадает другой район, на листах 3–9 видна граница района (красная, как на ортофотоплане) и каждый чужой район
// подписан на своей части листа; угловая надпись по-прежнему называет район территории
function conceptDistricts(out, bb, k) {
  const { adm, district } = homeAdm(); if (!district) return;
  const box = turf.bboxPolygon(bb), kk = (out.scale || 2000) / 1000;
  const near = adm.filter(f => f.properties["Уровень"] === "район" && /Polygon/.test(f.geometry?.type) && safe(() => turf.booleanIntersects(f, box)));
  const others = near.filter(f => f !== district).map(f => ({ f, part: safe(() => inter(f, box)) }))
    .filter(x => x.part && m2(x.part) / (kk * kk) > 400);          // больше 4 см² на бумаге — иначе подписи негде стоять
  if (!others.length && k !== "district") return;                  // на карте района свой район подписывается и без соседей
  if (k !== "ortho" && k !== "district") {                        // на ортофотоплане и карте района граница района уже есть (слой gisogd.admin)
    const g = safe(() => turf.polygonToLine(district));
    const lines = g && (g.type === "FeatureCollection" ? g.features : [g]);
    // поверх белой маски: под ней красная граница района бледнеет и сливается с красными линиями
    if (lines) out.layers.push({ title: "Граница района", over: true, features: lines.map(l => ({ g: l.geometry, fill: "#e30613", stroke: "#e30613", w: 4.6, a: 0 })) });   // жирная (владелец 06.10.2026)
    const gb = out.cLegend?.find(gr => gr.title === "Границы");
    if (gb && !gb.items.some(it => it.label === "района")) gb.items.splice(1, 0, { kind: "line", stroke: "#e30613", width: 1.2, label: "района" });
  }
  // районы по углам листа (владелец 05.10.2026: «в верхнем левом углу район Метрогородок, в правом нижнем Гольяново,
  // одинаковый кегль у подписей»): в левом верхнем углу — округ и район этого угла, в правом нижнем — район этого угла,
  // тем же кеглем; угловые надписи рисует album_io.MapNoteFrame
  // углы листа — по рамке в МСК (рамка в градусах по углам смещена: МСК повёрнута относительно меридианов; T11, 06.10.2026)
  const nm = f => "район " + LABEL_FN.adm({ get: q => f.properties[q] });
  const at = c => near.find(f => safe(() => turf.booleanPointInPolygon(c, f)));
  const cn = out.rect && out.center && out.scale ? AlbumGeo.cornerPoints(out.center, out.rect, out.scale, MSK)
    : { tl: [bb[0] + (bb[2] - bb[0]) * .03, bb[3] - (bb[3] - bb[1]) * .03], br: [bb[2] - (bb[2] - bb[0]) * .03, bb[1] + (bb[3] - bb[1]) * .03] };
  const tl = at(cn.tl), br = at(cn.br);
  const okrOf = f => { const a = f.properties["Округ"]; return [OKR_FULL[a] || a, "административный округ"]; };
  let named = new Set();
  if (tl && br && tl !== br) {
    out.mapNote = [okrOf(tl), [nm(tl)]];
    out.mapNoteBR = tl.properties["Округ"] === br.properties["Округ"] ? [[nm(br)]] : [okrOf(br), [nm(br)]];
    named = new Set([tl, br]);
  }
  // район без своего угла — подписью в глубине своей части листа, подальше от границы района, тем же кеглем (14,3 пт)
  const deep = part => { const [w, s, e, n] = turf.bbox(part), edge = turf.polygonToLine(part), ls = (edge.features || [edge]).map(x => x.geometry.type === "LineString" ? [x.geometry.coordinates] : x.geometry.coordinates).flat();
    let best = turf.pointOnFeature(part), bd = -1;
    for (let i = 1; i < 20; i++) for (let j = 1; j < 20; j++) { const pt = turf.point([w + (e - w) * i / 20, s + (n - s) * j / 20]);
      if (!safe(() => turf.booleanPointInPolygon(pt, part))) continue;
      const d = Math.min(...ls.map(l => turf.pointToLineDistance(pt, turf.lineString(l)))); if (d > bd) { bd = d; best = pt; } }
    return best; };
  const rest = others.filter(({ f }) => !named.has(f));
  const mine = k === "district" && !named.has(district) ? safe(() => inter(district, box)) : null;   // карта района: подписан и район территории
  if (mine) rest.push({ f: district, part: mine });
  if (rest.length) out.layers.push({ title: "Соседние районы: подписи", features: rest.map(({ f, part }) => ({ g: deep(part).geometry, nm: true, nudge: true,
    label: k === "ortho" || k === "district" ? nm(f).toUpperCase() : nm(f), ls: 14.3 * .3528, lf: "sans-bold", lh: .6, lcol: "#9e1717", la: 0,
    // снимок (владелец 07.10.2026, #45): ортофотоплан — тёмно-красные заглавные с белой обводкой, карта района — белые заглавные с тёмной обводкой
    ...(k === "ortho" ? { lcol: "#8b1a1a", lh: .9 } : k === "district" ? { lcol: "#ffffff", lh: .7, lhc: "#1a1a1a" } : {}) })) });
}
window.conceptSheet = conceptSheet;
// лист документации, у которого в рамке нет ни одного документа его вида, «не готов» с причиной (T85a, правило 7): считается
// по уже загруженным данным, без сборки листа. Слой, который не скачался, причиной не считается (это другая причина)
const DOC_KEYS = { ppt: { ppt: "gisogd.ppt", pmt: "gisogd.pmt" }, gpzu: { gpzu: "gisogd.gpzu", agr: "gisogd.agr" },
  docs: { ppt: "gisogd.ppt", pmt: "gisogd.pmt", gpzu: "gisogd.gpzu", agr: "gisogd.agr" } };
function conceptWhy(s) {
  const keys = DOC_KEYS[s?.concept]; if (!keys || s.frozen || !TERR) return "";
  const bb = safe(() => frameBox(s)); if (!bb) return "";
  const box = turf.bboxPolygon(bb), has = {};
  for (const [kind, key] of Object.entries(keys)) {
    if (ERRORS[key] || !CHECKED.has(key)) return "";
    has[kind] = (DATA[key]?.fc?.features || []).some(f => /Polygon|Line/.test(f.geometry?.type) && safe(() => turf.booleanIntersects(f, box)));
  }
  return LegendRules.docWhy(s.concept, s.concept === "gpzu" ? { gpzu: has.gpzu, agr: has.agr } : has);
}
window.conceptWhy = conceptWhy;   // sheets.js notReadyWhy: причина в значке листа и в окне выгрузки

/* План реализации ППТ КРТ: шапка и листы 1–2 — по шаблону владельца, листы 3–9 — как в «ГК Царицыно». */
const PPTKRT = [
  { kind: "title", style: "pptkrt", title: "Титульный лист" },
  { style: "pptkrt", title: "Месторасположение рассматриваемой территории", legend: false, callout: true, panels: [
    { keys: ["gisogd.admin"], adm: "moscow", fit: "moscow", rect: [25, 48, 174, 229], noFrame: true },
    { keys: ["gisogd.admin"], adm: "okrug", fit: "okrug", rect: [212, 48, 188, 229], okrugTitle: true, noFrame: true }] },   // за округом — белый фон (владелец)
  ...PPTKRT_C,
  ...PPTKRT_D,
];

TPL_SETS.pptkrt_ = { list: () => PPTKRT, size: () => "PA3" };       // обновление листов по шаблону (sheets.js, tplRefresh)

async function buildAlbum(kind) {
  if (kind === "pptkrt") return buildSection(PPTKRT, "pptkrt_", "PA3", "План реализации ППТ КРТ");
}
window.buildAlbum = buildAlbum;
