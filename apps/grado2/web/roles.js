/* ГРАДО 2 · роли слоёв в расчётах. Ограничения, анализ и эскиз ищут данные по РОЛИ слоя, а не по фиксированному ключу:
   в проектах владельца каталожные слои лежат как `ogd.<код>` и `egko.*`, а не `gisogd.*`/`nspd.*`/`osm.*`.
   Роль слоя определяется так (по убыванию силы):
   а) вручную: поле `role` в описании слоя (роль из списка или "none" — слой не участвует в расчётах); нет поля = «авто»;
   б) по ключу источника (таблица SOURCE_ROLE: `nspd.zouit` → zouit, `egko.buildings` → buildings…);
   в) по коду каталога для `ogd.<код>` — таблица с сервера (GET /api/layer_roles, строится из SOURCES), грузится лениво:
      при загрузке скрипта запросов нет (в хабе тогда ещё нет сессии).
   Роль не ограничивает слой одним расчётом: слой «Зоны береговых полос» — zouit, и для ограничений, и для баланса.
   Слой с ручной ролью перестаёт играть автоматическую (ручная роль — единственная). */
(function (root) {
  const LABELS = {
    pzz_sub: "ПЗЗ: подзоны", pzz_zones: "ПЗЗ: территориальные зоны", func_zones: "Функциональные зоны Генплана",
    zouit: "ЗОУИТ и охранные зоны", szz: "Санитарно-защитные зоны", okn: "Объекты культурного наследия", red_lines: "Красные линии",
    buildings: "Здания", roads: "Дороги и улицы", water: "Водные объекты", green: "Зелень и озеленение", social: "Социальные объекты",
    parcels: "Земельные участки" };
  const NONE = "none";
  // ключ источника → роль; порядок записей = приоритет внутри роли (здания: ЕГРН, ЕГКО, OSM). Та же таблица на сервере
  // (server.py SOURCE_ROLES), сверяется тестом.
  const SOURCE_ROLE = {
    "gisogd.pzz_sub": "pzz_sub", "gisogd.pzz_zones": "pzz_zones", "gisogd.func_zones": "func_zones",
    "gisogd.func_zones_tinao": "func_zones", "nspd.zouit": "zouit", "gisogd.zouit": "zouit", "gisogd.vodookhr": "zouit",
    "gisogd.szz": "szz", "gisogd.okn": "okn", "gisogd.red_lines": "red_lines",
    "nspd.buildings": "buildings", "egko.buildings": "buildings", "osm.buildings": "buildings",
    "osm.roads": "roads", "egko.roads": "roads", "osm.water": "water", "egko.water": "water", "egko.green": "green",
    "osm.social": "social", "nspd.parcels": "parcels" };
  const SRC_KEYS = Object.keys(SOURCE_ROLE);
  let table = { codes: {}, titles: {} }, loading = null, env = null;
  const E = () => env || { DATA: typeof DATA !== "undefined" ? DATA : root.DATA || {}, LYR: typeof LYR !== "undefined" ? LYR : root.LYR || [] };
  const valid = r => r === NONE || Object.hasOwn(LABELS, r);
  const sane = r => valid(r) ? r : undefined;                     // роль из чужого файла проекта: только известная
  const codeOf = key => key.startsWith("ogd.") ? key.slice(4) : null;
  const layerOf = key => E().LYR.find(l => l.key === key);
  const auto = key => SOURCE_ROLE[key] || (codeOf(key) && Object.hasOwn(table.codes, codeOf(key)) ? table.codes[codeOf(key)] : null);
  const manual = key => { const r = layerOf(key)?.role; return valid(r) ? r : null; };
  /* роль слоя: {role, manual} — role null, если слой ни в одной роли (или помечен «не участвует») */
  function roleOf(key) { const m = manual(key); if (m) return { role: m === NONE ? null : m, manual: true }; return { role: auto(key) || null, manual: false }; }
  /* ключи слоёв роли: сначала ручные (в порядке слоёв), потом по таблице источников (приоритет), потом каталожные `ogd.*` */
  function keys(role) {
    load();                                                         // ленивая загрузка таблицы кодов; без неё `ogd.*` пока не распознаются
    const { DATA: D } = E(), out = [];
    Object.keys(D).forEach((k, i) => { if (!D[k]?.fc?.features) return; const r = roleOf(k); if (r.role !== role) return;
      out.push([r.manual ? 0 : SOURCE_ROLE[k] ? 1 + SRC_KEYS.indexOf(k) / 1000 : 2, i, k]); });
    return out.sort((a, b) => a[0] - b[0] || a[1] - b[1]).map(x => x[2]);
  }
  const features = role => keys(role).flatMap(k => E().DATA[k].fc.features);
  /* описание слоёв роли для журнала и подписей: ключ, заголовок слоя, название кода каталога, число объектов */
  const info = role => keys(role).map(k => { const d = E().DATA[k]; return { key: k, title: d.title || layerOf(k)?.title || k, codeTitle: table.titles[codeOf(k)] || null, count: d.fc.features.length, manual: manual(k) === role }; });
  const sig = role => keys(role).map(k => k + ":" + (E().DATA[k].rev ?? 0)).join(",");     // метка для кэша узлов графа
  const existingBuildingsKey = () => keys("buildings")[0] || null;
  function load() {
    if (loading || env || typeof fetch !== "function") return loading || Promise.resolve(true);
    loading = fetch("/api/layer_roles").then(r => r.ok ? r.json() : null).then(j => {
      if (j?.codes && typeof j.codes === "object") { table = { codes: j.codes, titles: j.titles || {} }; if (typeof dataRev !== "undefined") dataRev++; return true; }   // узлы графа перечитают слои
      loading = null; return false; }).catch(() => { loading = null; return false; });
    return loading;
  }
  const api = { LABELS, NONE, SOURCE_ROLE, valid, sane, roleOf, autoRole: auto, keys, features, info, sig, existingBuildingsKey, load,
    ready: () => load(),
    /* для проверок под node: подставить данные и таблицу кодов */
    use: o => { env = o.DATA || o.LYR ? { DATA: o.DATA || {}, LYR: o.LYR || [] } : env; if (o.table) table = { codes: o.table.codes || {}, titles: o.table.titles || {} }; } };
  if (typeof module === "object" && module.exports) module.exports = api;
  root.Roles = api;
})(typeof window !== "undefined" ? window : globalThis);
