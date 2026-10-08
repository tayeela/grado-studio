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
  // почему титул не готов: адреса нет; адрес взят из реестра ЕГКО сам — его сверяют с письмом ДГП (#56: в альбом ушло
  // «д. 8» из реестра вместо «вл. 8» по письму). Адрес, введённый или исправленный руками, — готов
  const addrWhy = meta => !String(meta?.address || meta?.object || "").trim() ? "нет адреса"
    : meta.address && meta.auto?.address ? "адрес из реестра — сверьте с письмом ДГП" : "";
  // Что не готово до выгрузки альбома (T74): строки для окна «Выгрузить всё равно / Отмена». st: { terr, meta, sheets: [{ i, title, why, photos (число снимков у листа «фотофиксация», иначе null), empty: [названия слоёв пустых в рамке] }], title (проверять шапку) }
  // Строка: { text, sheet? (номер листа с 0), stamp? }. «Нет адреса» у титула здесь не повторяется: его закрывает строка про шапку.
  function exportIssues(st) {
    const out = [], m = st.meta || {}, name = x => `лист ${x.i + 1} «${x.title || "без названия"}»`;
    if (!st.terr) out.push({ text: "Территория не задана: карты листов будут без границы" });
    const hd = [["short", "№ КРТ"], ["place", "округ/район"], ["address", "адрес"]].filter(([k]) => !String(m[k] || "").trim()).map(x => x[1]);
    if (st.title !== false && hd.length) out.push({ text: `В шапке не заполнено: ${hd.join(", ")}`, stamp: true });
    (st.sheets || []).forEach(x => {
      const why = [x.why && x.why !== "нет адреса" ? x.why : "", (x.empty || []).length ? `${x.empty.length > 1 ? "слои" : "слой"} ${x.empty.map(t => "«" + t + "»").join(", ")} в рамке листа пусты` : ""].filter(Boolean).join("; ");
      if (why) out.push({ text: `${name(x)}: ${why}`, sheet: x.i });
      if (x.photos === 0) out.push({ text: `${name(x)}: Фотофиксация: снимков нет`, sheet: x.i });
    });
    return out;
  }
  const api = { FIELDS, parseAddr, addressText, krtText, placeJoin, fillMeta, typed, addrWhy, exportIssues };
  if (typeof module === "object" && module.exports) module.exports = api;
  root.AlbumMeta = api;
})(typeof window !== "undefined" ? window : globalThis);
