/* Станции рельсового каркаса на листах альбома (albums.js): метро, МЦК и МЦД — значок и название (правило 16
   label-rules.md, владелец 05.10.2026 и 06.10.2026). Чистые функции, без карты; проверки — tests/test_railstations_js.py.
   Источник — точки Яндекс Карт transport_p (слой yandex.stations), по одной на каждую линию станции:
     ft_type_name = transport-metro-station, closed ≠ 1 (закрытая станция не рисуется);
     network = moscow_metro, line = moscow_metro-14 (или p_name «Московское центральное кольцо») — МЦК;
     network = moscow_metro, прочие line = moscow_metro-N — метро (N — номер линии, в том числе БКЛ и Некрасовская);
     network = moscow_mcd, line = moscow_mcd-D1…D5 (или p_name «МЦД-N …») — МЦД, диаметр D1…D5.
   Метро и МЦК — один значок «М» и красное название; МЦД — параллелограмм своего диаметра и название его цветом. Станция
   метро и МЦД с одним названием рядом (до 700 м) — один подписанный объект с двумя значками, название красное. */
(function (root) {
  const METRO_COLOR = "#FF0013";
  const MCD_COLOR = { D1: "#F6A500", D2: "#E94282", D3: "#E95B0C", D4: "#41B384", D5: "#77B729" };
  const NEAR_M = 700;                                          // одна станция: то же название, точки не дальше 700 м
  const pick = (p, ...ks) => { for (const k of ks) { const v = p && (typeof p.get === "function" ? p.get(k) : p[k]); if (v != null && v !== "") return String(v); } return ""; };

  // вид станции по атрибутам точки: { kind: "metro" | "mck" | "mcd", d?: "D1".."D5", name } или null (не станция каркаса)
  function kindOf(p) {
    if (pick(p, "ft_type_name") !== "transport-metro-station") return null;
    if (pick(p, "closed") === "1") return null;
    const name = pick(p, "Название", "name").replace(/\s+/g, " ").trim(); if (!name || /\(закрыт/i.test(name)) return null;
    const net = pick(p, "network"), line = pick(p, "line"), pn = pick(p, "p_name");
    if (net === "moscow_mcd" || /^moscow_mcd-/i.test(line) || /^МЦД-\d/i.test(pn)) {
      const m = /^moscow_mcd-D([1-5])$/i.exec(line) || /^МЦД-([1-5])(?=\D|$)/i.exec(pn);
      return m ? { kind: "mcd", d: "D" + m[1], name } : null;     // диаметра нет среди пяти значков — не рисуем
    }
    if (net === "moscow_metro" || /^moscow_metro-/i.test(line)) {
      return { kind: line === "moscow_metro-14" || /^Московское центральное кольцо/i.test(pn) ? "mck" : "metro", name };
    }
    return null;
  }

  const dist = (a, b) => { const kx = Math.cos((a[1] + b[1]) / 2 * Math.PI / 180); return Math.hypot((a[0] - b[0]) * kx, a[1] - b[1]) * 111320; };

  // точки Яндекса → станции: [{ name, at: [lon, lat], icons: ["metro", "mcd-d2"], metro, mcd: ["D2"], color }]
  // items — [{ props, coord }]; значки: «metro» (метро или МЦК) первым, затем диаметры по порядку
  function stations(items) {
    const groups = [];
    for (const it of items) {
      const k = kindOf(it.props); if (!k || !it.coord) continue;
      let g = groups.find(x => x.name.toLowerCase() === k.name.toLowerCase() && x.pts.some(c => dist(c, it.coord) <= NEAR_M));
      if (!g) groups.push(g = { name: k.name, pts: [], metro: false, mck: false, mcd: new Set() });
      g.pts.push(it.coord);
      if (k.kind === "mcd") g.mcd.add(k.d); else { g.metro = g.metro || k.kind === "metro"; g.mck = g.mck || k.kind === "mck"; }
    }
    return groups.map(g => {
      const mcd = [...g.mcd].sort(), isMetro = g.metro || g.mck;
      const at = [g.pts.reduce((s, c) => s + c[0], 0) / g.pts.length, g.pts.reduce((s, c) => s + c[1], 0) / g.pts.length];
      return { name: g.name, at, icons: [...(isMetro ? ["metro"] : []), ...mcd.map(d => "mcd-" + d.toLowerCase())],
        metro: g.metro, mck: g.mck, mcd, color: isMetro ? METRO_COLOR : MCD_COLOR[mcd[0]] };
    });
  }

  // строки легенды для видимых значков (правило 7: только то, что есть на листе): [{ icon, label }]
  function legendItems(sts) {
    const out = [], m = sts.some(s => s.metro), c = sts.some(s => s.mck);
    if (m || c) out.push({ icon: "metro", label: m && c ? "станция метро и МЦК" : c ? "станция МЦК" : "станция метро" });
    [...new Set(sts.flatMap(s => s.mcd))].sort().forEach(d => out.push({ icon: "mcd-" + d.toLowerCase(), label: "станция МЦД " + d }));
    return out;
  }

  // название без приставки и регистра — для сравнения с подписями ЕГКО («ст. ж/д Перово» ↔ «Перово»)
  const bare = s => String(s || "").replace(/[\s ]+/g, " ").replace(/^(?:ж\/д\s+)?(?:ст\.?|станция)(?:\s+ж\/д)?\s+|^ж\/д\s+/i, "").trim().toLowerCase();

  const api = { METRO_COLOR, MCD_COLOR, NEAR_M, kindOf, stations, legendItems, bare, dist };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.RailStations = api;
})(typeof window !== "undefined" ? window : globalThis);
