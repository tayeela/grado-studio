/* ГРАДО 2 · шапка альбома: «№ КРТ», «Округ, район», «Адрес» заполняются сами из слоёв (T73, 05.10.2026).
   Чистые функции без обращения к карте: слои и проверка «внутри территории» передаёт sheets.js. Запуск проверок — tests/test_albummeta_js.py.
   Правило: введённое владельцем не затирается; сам заполненный текст помечен в meta.auto[поле] и обновляется при пересборке. */
(function (root) {
  const FIELDS = ["short", "place", "address"];
  const HOUSE = /(?<![\d\-])\d+[а-яё]?(?:\/\d+)?(?![\d\-])/i;   // «8», «12а», «12/1»; «1-й», «2-я» — порядковые, не дом
  // «1-й Иртышский проезд 8 стр.1» → { street: "1-й Иртышский проезд", house: "8" }
  function parseAddr(s) {
    let t = String(s || "").replace(/\s+/g, " ").trim().replace(/^(г\.?|город)\s*Москва\s*,?\s*/i, "");
    const m = HOUSE.exec(t); if (!m) return null;
    const street = t.slice(0, m.index).replace(/[\s,]+$/, "").replace(/(^|[\s,])(д\.?|дом|вл\.?|владение)$/i, "").replace(/[\s,]+$/, "");
    return street.length > 2 ? { street, house: m[0] } : null;
  }
  // адреса точек внутри территории → «г. Москва, 1-й Иртышский проезд, д. 8»; улиц несколько — та, где точек больше;
  // дома разные — только улица (номер не выдумываем)
  function addressText(list) {
    const by = new Map();
    list.map(parseAddr).filter(Boolean).forEach(a => { const e = by.get(a.street) || by.set(a.street, { n: 0, houses: new Set() }).get(a.street); e.n++; e.houses.add(a.house); });
    let best = null; by.forEach((e, st) => { if (!best || e.n > best.e.n) best = { st, e }; });
    if (!best) return "";
    return "г. Москва, " + best.st + (best.e.houses.size === 1 ? ", д. " + [...best.e.houses][0] : "");
  }
  // КРТ, в который попало больше всего территории: areaOf(f) — площадь пересечения; номер — поле num_krt
  function krtText(features, areaOf) {
    let best = null;
    (features || []).forEach(f => { const n = String(f.properties?.num_krt ?? "").trim(); if (!n) return; const a = areaOf(f); if (a > 0 && (!best || a > best.a)) best = { a, n }; });
    return best ? "№ " + best.n.replace(/^№\s*/, "") : "";
  }
  const placeJoin = (abbr, district) => [abbr, district ? "район " + String(district).replace(/^район\s+/i, "") : ""].filter(Boolean).join(", ");
  // vals — найденные значения; пустое найденное ничего не стирает. Возвращает список заполненных полей
  function fillMeta(meta, vals) {
    const done = []; meta.auto = { ...(meta.auto || {}) };
    FIELDS.forEach(k => { const v = vals[k]; if (!v) return;
      if (!meta[k] || meta.auto[k]) { if (meta[k] !== v) done.push(k); meta[k] = v; meta.auto[k] = true; } });
    return done;
  }
  const typed = (meta, k) => { if (meta.auto) delete meta.auto[k]; };   // владелец правит поле — оно больше не «автоматическое»
  const api = { FIELDS, parseAddr, addressText, krtText, placeJoin, fillMeta, typed };
  if (typeof module === "object" && module.exports) module.exports = api;
  root.AlbumMeta = api;
})(typeof window !== "undefined" ? window : globalThis);
