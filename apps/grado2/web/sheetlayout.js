/* ГРАДО 2 · состав слоёв листа по ролям: sheet.layout (T86a, 06.10.2026, слово владельца: «единая логика для всех листов,
   группировка слоёв по листам и перетаскивание»). Чистые функции без карты: слои проекта и шаблон передаёт sheets.js / albums.js.
   layout = { groups: [{ id, title, role, items: [{ key, on, style?, only?, src? }] }] }. Порядок групп и элементов — порядок
   рисования (как у sheet.keys). style — оформление слоя на этом листе поверх стиля слоя проекта; only — отбор объектов
   { field, values }; src — очередь источников (только у дорог: кто первый, кто запасной).
   Переходный релиз: keys, styles и only у листа живут по-прежнему и заполняются как раньше. Лист читает layout, только пока
   он совпадает с keys (resolve): правка keys рукой (layers.js) не теряется. Листов без layout это не касается. Запуск проверок —
   tests/test_sheetlayout_js.py. */
(function (root) {
  // роль слоя — по ключу; порядок ролей — как «Слои и листы» будет показывать их в окне. Нет в таблице — «прочее»
  const ROLES = [
    { role: "parcels", title: "Участки", keys: ["nspd.parcels"] },
    { role: "zouit", title: "ЗОУИТ", keys: ["nspd.zouit", "gisogd.zouit", "gisogd.szz", "gisogd.vodookhr", "gisogd.airfield"] },
    { role: "redlines", title: "Красные линии", keys: ["gisogd.red_lines"] },
    { role: "buildings", title: "Здания", keys: ["egko.buildings"] },
    { role: "roads", title: "Дороги", keys: ["yandex.hd_roads", "egko.roads"] },
    { role: "rail", title: "Рельс и станции", keys: ["yandex.rail", "yandex.stations"] },
    { role: "water", title: "Вода", keys: ["egko.water"] },
    { role: "names", title: "Названия улиц и мест", keys: ["osm.landuse", "osm.roads", "egko.water_labels", "egko.place_labels", "egko.addresses"] },
    { role: "docs", title: "Генплан и документы", keys: ["gisogd.func_zones", "gisogd.func_zones_tinao", "gisogd.ppt", "gisogd.pmt", "gisogd.gpzu", "gisogd.agr"] },
    { role: "border", title: "Границы", keys: ["gisogd.admin"] },
  ];
  const OTHER = { role: "other", title: "Прочее" };
  const BY_KEY = new Map(ROLES.flatMap(r => r.keys.map(k => [k, r])));
  const roleOf = key => BY_KEY.get(key) || OTHER;
  const clone = x => x === undefined ? undefined : JSON.parse(JSON.stringify(x));
  // дороги: очередь источников полигонов — на векторной схеме ЕГКО первым, на снимке Яндекс (решение T84, roadsrc.js)
  const roadQueue = basemap => basemap === "sat" ? ["yandex.hd_roads", "egko.roads"] : ["egko.roads", "yandex.hd_roads"];

  // layout из упорядоченных ключей: подряд идущие слои одной роли — одна группа (порядок рисования не меняется, поэтому
  // роль может встретиться дважды: id «names», «names-2»)
  function build(keys, styles, only, basemap) {
    const groups = [], seen = new Set(), count = {};
    (keys || []).forEach(key => {
      if (seen.has(key)) return; seen.add(key);
      const r = roleOf(key), item = { key, on: true };
      if (styles?.[key] !== undefined) item.style = clone(styles[key]);
      if (only?.[key] !== undefined) item.only = clone(only[key]);
      if (key === "yandex.hd_roads") item.src = roadQueue(basemap);
      const last = groups[groups.length - 1];
      if (last && last.role === r.role) last.items.push(item);
      else { count[r.role] = (count[r.role] || 0) + 1; groups.push({ id: count[r.role] > 1 ? `${r.role}-${count[r.role]}` : r.role, title: r.title, role: r.role, items: [item] }); }
    });
    return { groups };
  }
  // начальный layout листа шаблона (PPTKRT_C): ровно те же слои, стили и отборы, что в keys/styles/only
  function seedLayout(tpl) { return Array.isArray(tpl?.keys) ? build(tpl.keys, tpl.styles, tpl.only, tpl.basemap) : null; }

  const flatten = layout => (layout?.groups || []).flatMap(g => (g.items || []).map(it => ({ ...it, group: g.id, role: g.role })));
  // ключи включённых элементов в порядке рисования — то, что раньше лежало в sheet.keys
  const layoutKeys = layout => flatten(layout).filter(it => it.on !== false).map(it => it.key);
  const layoutStyles = layout => Object.fromEntries(flatten(layout).filter(it => it.on !== false && it.style !== undefined).map(it => [it.key, it.style]));
  const layoutOnly = layout => Object.fromEntries(flatten(layout).filter(it => it.on !== false && it.only !== undefined).map(it => [it.key, it.only]));

  // layout, пока keys листа ему не противоречат (тот же набор в том же порядке); иначе лист живёт по keys/styles/only
  function matches(sheet) {
    if (!sheet?.layout || sheet.frozen) return false;
    const a = layoutKeys(sheet.layout), b = sheet.keys || [];
    return a.length === b.length && a.every((k, i) => k === b[i]);
  }
  // что читает сборка листа: ключи, стили и отборы — из layout, если он годен, иначе из полей листа
  function resolve(sheet) {
    return matches(sheet) ? { keys: layoutKeys(sheet.layout), styles: layoutStyles(sheet.layout), only: layoutOnly(sheet.layout), layout: true }
      : { keys: sheet.keys || null, styles: sheet.styles || {}, only: sheet.only || {}, layout: false };
  }
  // layout из того, что у листа уже есть: keys + styles + only, а у листа «по виду» — слои вида (view = { layers: [{ key, visible, style }] }).
  // Готовые листы (frozen) и листы без состава (текущая карта) layout не получают — null. Лист не меняется
  function migrate(sheet, view) {
    if (!sheet || sheet.frozen) return null;
    if (sheet.layout) return clone(sheet.layout);
    if (Array.isArray(sheet.keys)) return build(sheet.keys, sheet.styles, sheet.only, sheet.basemap);
    if (view && Array.isArray(view.layers)) {
      const l = build(view.layers.map(x => x.key), Object.fromEntries(view.layers.filter(x => x.style !== undefined).map(x => [x.key, x.style])), null, sheet.basemap);
      const vis = new Map(view.layers.map(x => [x.key, !!x.visible]));
      l.groups.forEach(g => g.items.forEach(it => { it.on = vis.get(it.key) !== false; }));
      return l;
    }
    return null;
  }
  const api = { ROLES, roleOf, seedLayout, build, flatten, layoutKeys, layoutStyles, layoutOnly, matches, resolve, migrate };
  if (typeof module === "object" && module.exports) module.exports = api;
  root.SheetLayout = api;
})(typeof window !== "undefined" ? window : globalThis);
