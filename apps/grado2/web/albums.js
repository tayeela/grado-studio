/* ГРАДО 2 · альбомы по образцам владельца (26.09.2026): «План реализации ППТ КРТ» — по его шаблону PowerPoint
   (А3 альбомный, красная шапка; оформление листа — album_io.py) и «Градостроительная концепция» — по образцу
   «ГК Царицыно». Листы собираются той же сборкой, что раздел 1 (buildSection в sheets.js), со своим префиксом id.
   Состав наращивается по листам вместе с владельцем: сейчас титул и месторасположение. */

const OKR_FULL = { ЦАО: "Центральный", САО: "Северный", СВАО: "Северо-Восточный", ВАО: "Восточный", ЮВАО: "Юго-Восточный", ЮАО: "Южный",
  ЮЗАО: "Юго-Западный", ЗАО: "Западный", СЗАО: "Северо-Западный", ЗелАО: "Зеленоградский", НАО: "Новомосковский", ТАО: "Троицкий" };

/* Округа и районы по эталону (решения владельца 26.09.2026). Слои округов ГИС ОГД (prefect_*, ЕГКО «Границы
   административных округов») собраны из старых 21 поселения ТиНАО; новые районы ТиНАО (слои virtualterr_*) делят его
   иначе, но нарисованы схематично — прямыми через местность, с заходами на старую Москву и щелью у Солнцева.
   Сборка:
   · ТиНАО целиком — точные поселения ЕГКО «Границы районов» (уровень «поселение», сервер) и старые районы,
     целиком (≥ 90 %) лежащие в новых районах ТиНАО (ЗАО «Внуково» → НАО);
   · ТАО = ТиНАО ∩ новые районы ТАО, НАО = ТиНАО − ТАО: внешний контур и стык со старой Москвой точные, граница
     ТАО/НАО внутри — по новым районам (другой нет);
   · новые районы обрезаются по своему округу, старые — как в ГИС ОГД; округа старой Москвы — объединение их районов.
   Обрезки меньше 1 га и дыры меньше 0,5 км² отбрасываются. Поселения после сборки из слоя уходят. */
const ADM_REV = "эталон 4";                       // метка сборки: другая — административное деление берётся заново
const isPoly = f => /Polygon/.test(f?.geometry?.type);
const isNewD = f => String(f.properties._key || "").startsWith("virtualterr_");
function geoClean(g, holes = 5e5) {
  if (!g) return null;
  const polys = (g.geometry.type === "Polygon" ? [g.geometry.coordinates] : g.geometry.coordinates)
    .map(p => [p[0], ...p.slice(1).filter(r => safe(() => turf.area(turf.polygon([r]))) > holes)])
    .filter(p => safe(() => turf.area(turf.polygon(p))) > 1e4);
  if (!polys.length) return null;
  return polys.length === 1 ? { type: "Polygon", coordinates: polys[0] } : { type: "MultiPolygon", coordinates: polys };
}
const geoFeat = g => g && { type: "Feature", properties: {}, geometry: g.geometry || g };
function geoUnite(fs) { fs = fs.filter(Boolean); if (!fs.length) return null; if (fs.length === 1) return geoFeat(fs[0]);
  try { return turf.union(turf.featureCollection(fs.map(geoFeat))); } catch { return null; } }
function geoCut(a, b, op) { if (!a || !b) return op === "difference" ? a : null;
  try { return turf[op](turf.featureCollection([geoFeat(a), geoFeat(b)])); } catch { return op === "difference" ? a : null; } }

function okrugsByDistricts(fc) {
  const all = fc.features || [], lvl = (f, l) => f.properties["Уровень"] === l && isPoly(f);
  const settl = all.filter(f => lvl(f, "поселение")), newD = all.filter(f => lvl(f, "район") && isNewD(f));
  const oldD = all.filter(f => lvl(f, "район") && !isNewD(f));
  const newU = geoUnite(newD);
  const moved = new Set(newU ? oldD.filter(d => { const x = geoCut(d, newU, "intersect"); return x && turf.area(x) >= .9 * turf.area(d); }) : []);
  const geomOf = {};                                       // округ → точная геометрия
  if (settl.length && newD.length) {
    const tinao = geoUnite([...settl, ...moved]);
    const tao = geoCut(tinao, geoUnite(newD.filter(d => d.properties["Округ"] === "ТАО")), "intersect");
    geomOf["ТАО"] = geoClean(tao); geomOf["НАО"] = geoClean(geoCut(tinao, tao, "difference"));
  }
  const districts = [];
  for (const d of oldD) if (!moved.has(d)) districts.push(d);
  for (const d of newD) {                                  // новый район — в границах своего (точного) округа
    const og = geomOf[d.properties["Округ"]];
    const g = og ? geoClean(geoCut(d, { geometry: og }, "intersect")) : d.geometry;
    if (g) districts.push({ ...d, geometry: g });
  }
  const out = [];
  for (const f of all) {
    if (f.properties["Уровень"] !== "округ") continue;
    const name = f.properties["Наименование"];
    const g = geomOf[name] || geoClean(geoUnite(districts.filter(d => d.properties["Округ"] === name)));
    out.push(g ? { ...f, geometry: g, properties: { ...f.properties, "Граница": ADM_REV } } : f);
  }
  return { ...fc, features: [...out, ...districts, ...all.filter(f => !["округ", "район", "поселение"].includes(f.properties["Уровень"]))] };
}
window.okrugsByDistricts = okrugsByDistricts;

// округ и район, где лежит территория (административное деление ГИС ОГД)
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
  return out;
}

/* План реализации ППТ КРТ (шаблон владельца). Рамки карт — в мм листа А3 (420 × 297), как в шаблоне. */
const PPTKRT = [
  { kind: "title", style: "pptkrt", title: "Титульный лист" },
  { style: "pptkrt", title: "Месторасположение рассматриваемой территории", legend: false, callout: true, panels: [
    { keys: ["gisogd.admin"], adm: "moscow", fit: "moscow", rect: [25, 48, 174, 229], noFrame: true },
    { keys: ["gisogd.admin"], adm: "okrug", fit: "okrug", rect: [212, 48, 188, 229], okrugTitle: true, noFrame: true }] },   // за округом — белый фон (владелец)
];

async function buildAlbum(kind) {
  if (kind === "pptkrt") return buildSection(PPTKRT, "pptkrt_", "PA3", "План реализации ППТ КРТ");
}
window.buildAlbum = buildAlbum;
