/* ГРАДО 2 · состав слоёв листа по ролям: sheet.layout (T86a, 06.10.2026, слово владельца: «единая логика для всех листов,
   группировка слоёв по листам и перетаскивание»). Чистые функции без карты: слои проекта и шаблон передаёт sheets.js / albums.js.
   layout = { groups: [{ id, title, role, items: [{ key, on, style?, only?, src? }] }] }. Порядок групп и элементов — порядок
   рисования (как у sheet.keys). style — оформление слоя на этом листе поверх стиля слоя проекта; only — отбор объектов
   { field, values }; src — очередь источников (только у дорог: кто первый, кто запасной).
   Переходный релиз: keys, styles и only у листа живут по-прежнему и заполняются как раньше. Лист читает layout, только пока
   он совпадает с keys (resolve; выключенные глазом элементы в keys остаются, но не рисуются): правка keys рукой (layers.js) не теряется. Листов без layout это не касается. Запуск проверок —
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

  // layout, пока keys листа ему не противоречат: тот же набор слоёв в том же порядке. Выключенный глазом элемент остаётся в keys
  // (on: false только прячет слой на листе), поэтому сравниваются все ключи, а не только включённые; иначе лист живёт по keys/styles/only
  function matches(sheet) {
    if (!sheet?.layout || sheet.frozen) return false;
    const a = flatten(sheet.layout).map(it => it.key), b = sheet.keys || [];
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

  /* ---- окно «Слои и листы» (T86b): чистые функции строк, покрытия и номеров листов; карты и страницы здесь нет ---- */
  const plural = (n, [a, b, c]) => { const m = Math.abs(n) % 100, d = m % 10; return `${n} ${m > 10 && m < 20 ? c : d === 1 ? a : d > 1 && d < 5 ? b : c}`; };
  const PROVIDERS = { gisogd: "ГИС ОГД", ogd: "ГИС ОГД", egko: "ЕГКО", nspd: "НСПД", yandex: "Яндекс", sit: "Яндекс", osm: "OSM", calc: "расчёт" };
  const providerName = key => PROVIDERS[String(key).split(".")[0]] || "файл";
  const roleTitle = role => (ROLES.find(r => r.role === role) || OTHER).title;
  // доля рамки (0…1), лежащая внутри выгруженной области; обе рамки — [запад, юг, восток, север] в градусах (отношение площадей
  // прямоугольников в градусах равно отношению в метрах: широта у обеих одна). Нет рамки или области — null
  function frameCover(frame, bbox) {
    if (!Array.isArray(frame) || !Array.isArray(bbox)) return null;
    const area = (w, s, e, n) => Math.max(0, e - w) * Math.max(0, n - s), A = area(...frame); if (!(A > 0)) return null;
    return Math.min(1, area(Math.max(frame[0], bbox[0]), Math.max(frame[1], bbox[1]), Math.min(frame[2], bbox[2]), Math.min(frame[3], bbox[3])) / A);
  }
  // бейдж состояния строки: { text, tone } или null. probe = { loaded, cover (0…1 | null), empty, error }
  function coverBadge(key, probe) {
    if (probe?.error) return { text: "не загрузился", tone: "bad" };
    if (!probe?.loaded) return { text: "не выгружен", tone: "warn" };
    const c = probe.cover;
    if (c !== null && c !== undefined && c < .005) return { text: "данные вне рамки", tone: "warn" };
    if (c !== null && c !== undefined && c < .995) return { text: providerName(key) === "Яндекс" ? "окно 40 км²" : `на ${Math.min(99, Math.max(1, Math.round((1 - c) * 100)))} % рамки нет`, tone: "warn" };
    return probe.empty ? { text: "в рамке нет", tone: "none" } : null;
  }
  // очередь источников роли: какой ключ берётся. picked — решение сборки (если известно), иначе первый с покрытием ≥ 90 %, иначе лучший
  function chooseSource(queue, probe, picked) {
    const q = queue || []; if (picked && q.includes(picked)) return picked;
    const cv = k => probe(k)?.cover ?? 0, ok = q.find(k => probe(k)?.loaded && cv(k) >= .9);
    return ok || q.slice().sort((a, b) => cv(b) - cv(a))[0] || null;
  }
  const queueRows = (queue, probe, chosen) => (queue || []).map((key, i) => {
    const p = probe(key) || {}; return { key, n: i + 1, provider: providerName(key), cover: p.cover ?? null, badge: coverBadge(key, p), used: key === chosen, loaded: !!p.loaded }; });
  // «ГИС ОГД · 3 слоя · ЕГКО» из ключей элементов
  function sourceText(keys) {
    const by = new Map(); keys.forEach(k => { const n = providerName(k); by.set(n, (by.get(n) || 0) + 1); });
    return [...by].map(([n, c]) => c > 1 ? `${n} · ${plural(c, ["слой", "слоя", "слоёв"])}` : n).join(" · ");
  }
  // строки ролей листа: одна строка на роль, на месте первого появления в layout (повторные группы той же роли сливаются:
  // роль может встретиться дважды из-за порядка рисования). probe(key) → { loaded, cover, empty }; opts.chosen(item) → ключ очереди src
  function roleRows(layout, probe, opts = {}) {
    const by = new Map();
    (layout?.groups || []).forEach(g => { const r = by.get(g.role); if (r) { r.ids.push(g.id); r.items.push(...(g.items || [])); } else by.set(g.role, { id: g.id, ids: [g.id], role: g.role, title: g.title || roleTitle(g.role), items: [...(g.items || [])] }); });
    return [...by.values()].map(g => {
      const items = g.items, head = items.find(it => Array.isArray(it.src) && it.src.length);
      // очередь — только те источники, что есть на листе среди слоёв роли: лист, собранный раньше, ЕГКО-дорог может не содержать
      const queue = head ? (head.src.filter(k => items.some(it => it.key === k)).length ? head.src.filter(k => items.some(it => it.key === k)) : head.src) : null;
      const chosen = head ? chooseSource(queue, probe, opts.chosen?.(head)) : null;
      const keys = head ? [chosen].filter(Boolean) : items.map(it => it.key), ps = keys.map(k => [k, probe(k) || {}]);
      const known = ps.filter(([, p]) => p.cover !== null && p.cover !== undefined), cover = known.length ? Math.min(...known.map(([, p]) => p.cover)) : null;
      const worst = ps.map(([k, p]) => ({ k, p, b: coverBadge(k, p) })).filter(x => x.b).sort((a, b) => (a.b.tone === "warn" ? 0 : 1) - (b.b.tone === "warn" ? 0 : 1))[0];
      const empty = ps.length > 0 && ps.every(([, p]) => p.loaded && p.empty);
      const on = items.some(it => it.on !== false);
      return { id: g.id, ids: g.ids, role: g.role, title: g.title, on, count: items.length, items: items.map(it => ({ key: it.key, on: it.on !== false })),
        source: sourceText(keys), cover, empty, badge: worst?.b || null, queue: head ? { head: head.key, keys: queue, chosen } : null };
    });
  }
  // лист → layout для показа. stored — состав уже лежит в листе и совпадает с keys; editable — глаз можно переключать (запись migrate безопасна).
  // viewOf(sheet) → вид листа ({layers}) для листа «по виду»; такой лист показывается, но глаз у него неактивен
  function layoutFor(sheet, viewOf) {
    const none = (why, kind) => ({ layout: null, stored: false, editable: false, why, kind: kind || "" });
    if (!sheet) return none("");
    if (sheet.frozen) return none("готовый лист: состав зашит в файл", "frozen");
    if (sheet.kind === "title") return none("", "title");
    if (sheet.kind === "tep") return none("", "tep");
    if (sheet.panels) return none("лист из двух карт: у каждой карты свой состав", "panels");
    if (matches(sheet)) return { layout: sheet.layout, stored: true, editable: true, why: "", kind: "map" };
    if (Array.isArray(sheet.keys)) { const l = migrate({ ...sheet, layout: undefined }, null), same = !!l && flatten(l).length === sheet.keys.length && flatten(l).every((it, i) => it.key === sheet.keys[i]);
      return { layout: l, stored: false, editable: same, why: same ? "" : "в списке слоёв листа есть повторы: глаз выключен", kind: "map" }; }
    const v = viewOf?.(sheet), l = v ? migrate({ ...sheet, layout: undefined }, v) : null;
    return l ? { layout: l, stored: false, editable: false, why: "состав листа задан видом карты: меняется в окне «Виды»", kind: "view" } : none("лист показывает текущую карту", "map");
  }
  // глаз на роли: включить или выключить все элементы группы (или нескольких групп одной роли — groupId массивом). Нет годного layout — сначала записывается migrate. true — лист изменён
  function setRole(sheet, groupId, on, viewOf) {
    const info = layoutFor(sheet, viewOf); if (!info.editable) return false;
    const ids = [].concat(groupId), gs = info.layout.groups.filter(x => ids.includes(x.id)); if (!gs.length) return false;
    if (!gs.some(g => g.items.some(it => (it.on !== false) !== !!on))) return false;
    if (!info.stored) sheet.layout = info.layout;
    sheet.layout.groups.filter(x => ids.includes(x.id)).forEach(g => g.items.forEach(it => { it.on = !!on; }));
    return true;
  }
  // при пересборке листа по шаблону скрытая роль остаётся скрытой: группа, выключенная целиком, выключается целиком (в шаблоне мог
  // появиться новый слой роли), остальное — по ключу элемента
  function carryOn(fresh, old) {
    if (!fresh?.layout || !old?.layout) return;
    const was = new Map(flatten(old.layout).map(it => [it.group + "|" + it.key, it.on !== false])), offGroup = new Set(old.layout.groups.filter(g => (g.items || []).length && g.items.every(it => it.on === false)).map(g => g.id));
    fresh.layout.groups.forEach(g => g.items.forEach(it => { if (offGroup.has(g.id) || was.get(g.id + "|" + it.key) === false) it.on = false; }));
  }
  // номера листов (с 1), где слой включён; viewKeys(sheet) → ключи видимых слоёв вида (или null)
  function sheetKeysOn(sheet, viewKeys) {
    if (!sheet || sheet.frozen || sheet.kind === "title" || sheet.kind === "tep") return [];
    if (sheet.panels) return [...new Set(sheet.panels.flatMap(p => p.keys || []))];
    return resolve(sheet).keys || viewKeys?.(sheet) || [];
  }
  const layerSheets = (sheets, key, viewKeys) => (sheets || []).map((s, i) => sheetKeysOn(s, viewKeys).includes(key) ? i + 1 : 0).filter(Boolean);
  // слои проекта по ролям: [{ role, title, items: [{ key, title, sheets }] }]; роли идут в порядке ROLES, «Прочее» — последним
  function bankGroups(layers, sheets, viewKeys) {
    const by = new Map();
    (layers || []).forEach(l => { const r = roleOf(l.key); if (!by.has(r.role)) by.set(r.role, { role: r.role, title: r.title, items: [] }); by.get(r.role).items.push({ key: l.key, title: l.title, sheets: layerSheets(sheets, l.key, viewKeys) }); });
    return [...ROLES, OTHER].map(r => by.get(r.role)).filter(Boolean);
  }
  // роли, которые есть на других листах альбома, а на этом по образцу нет (в порядке ROLES)
  function missingRoles(layouts, i) {
    const mine = new Set((layouts[i]?.groups || []).map(g => g.role)), all = new Set(layouts.flatMap(l => (l?.groups || []).map(g => g.role)));
    // границы территории и района есть на каждом листе (рисуются сами), в «нет по образцу» не попадают
    return [...ROLES, OTHER].filter(r => r.role !== "border" && all.has(r.role) && !mine.has(r.role)).map(r => r.title);
  }
  // вторая строка листа в колонке листов: основа и число ролей (или что лист такое)
  function sheetMeta(sheet, info) {
    if (info.kind === "frozen") return "готовая вёрстка из файла";
    if (info.kind === "title") return "шаблон, слоёв нет";
    if (info.kind === "tep") return "таблица показателей";
    if (info.kind === "panels") return "две карты на слайде";
    const base = sheet.basemap === "sat" ? "снимок" : "белая основа", n = new Set((info.layout?.groups || []).map(g => g.role)).size;
    return info.layout ? `${base} · ${plural(n, ["роль", "роли", "ролей"])}` : base;
  }
  /* ---- перетаскивание в окне «Слои и листы» (T86c): чистые функции правки состава листа; карты и страницы здесь нет ---- */
  const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
  const cap = t => t ? t[0].toUpperCase() + t.slice(1) : t;
  const TXT = { frozen: "Лист готов, замок — Alt при отпускании сделает рабочую копию", nomap: n => `У листа ${n} нет слоёв карты`,
    norole: (n, t) => `На листе ${n} нет роли «${t}» — по образцу её там не показывают`, border: n => `На листе ${n} границы не добавляются: территория и район рисуются сами`,
    have: (n, t) => `Слой «${t}» уже включён на листе ${n}`, haveRole: (n, t) => `Роль «${t}» уже полностью на листе ${n}`, here: (n, t) => `Роль «${t}» уже на листе ${n}`,
    wrongRow: (t, r, w) => `Слой «${t}» относится к роли «${r}», а не «${w}»` };
  // порядок ролей по образцу: первое появление роли в начальном layout шаблона листа (повторные группы той же роли — не в счёт)
  function refRank(tplLayout) { const m = new Map(); (tplLayout?.groups || []).forEach(g => { if (!m.has(g.role)) m.set(g.role, m.size); }); return m; }
  const rankOf = (role, ref) => ref.has(role) ? ref.get(role) : 1000 + ROLES.concat([OTHER]).findIndex(r => r.role === role);
  // допустимые роли листа: роли образца (начальный layout шаблона) + роли, которые лист уже имеет; в порядке образца, лишние — по ROLES
  function allowedRoles(layout, tplLayout) {
    const ref = refRank(tplLayout), have = new Set((layout?.groups || []).map(g => g.role)), all = new Set([...ref.keys(), ...have]);
    return [...all].sort((a, b) => rankOf(a, ref) - rankOf(b, ref));
  }
  // ключи и оформление листа повторяют layout (иначе resolve откатился бы к старым полям: matches сравнивает keys с layout)
  function syncFields(sheet) {
    const items = flatten(sheet.layout), st = {}, on = {};
    items.forEach(it => { if (it.style !== undefined) st[it.key] = clone(it.style); if (it.only !== undefined) on[it.key] = clone(it.only); });
    sheet.keys = items.map(it => it.key); sheet.styles = st; sheet.only = on;
  }
  // оформление нового элемента: как слой выглядит в образце этого листа, иначе на других листах альбома (ctx.tpl, ctx.others — layout'ы)
  function hintItem(key, ctx) { for (const l of [ctx?.tpl, ...(ctx?.others || [])]) { const it = flatten(l).find(x => x.key === key); if (it) return it; } return null; }
  function newItem(key, sheet, ctx) {
    const it = { key, on: true }, h = hintItem(key, ctx);
    if (h?.style !== undefined) it.style = clone(h.style); if (h?.only !== undefined) it.only = clone(h.only);
    if (key === "yandex.hd_roads") it.src = roadQueue(sheet.basemap);
    return it;
  }
  const uniqId = (layout, role) => { const ids = new Set(layout.groups.map(g => g.id)); let id = role, k = 1; while (ids.has(id)) id = role + "-" + (++k); return id; };
  // положить элемент в роль: в конец последней группы этой роли; если роли нет — новая группа на место по образцу
  function putItem(layout, role, item, ctx) {
    const gs = layout.groups.filter(g => g.role === role);
    if (gs.length) { gs[gs.length - 1].items.push(item); return gs[gs.length - 1].id; }
    const ref = refRank(ctx?.tpl), at = layout.groups.findIndex(g => rankOf(g.role, ref) > rankOf(role, ref)), g = { id: uniqId(layout, role), title: roleTitle(role), role, items: [item] };
    layout.groups.splice(at < 0 ? layout.groups.length : at, 0, g); return g.id;
  }
  // можно ли положить на лист роль role. o = { n: номер листа с 1, viewOf, tpl }. ok: true и info листа, иначе { code, tone, text }
  function targetCheck(sheet, role, o = {}) {
    const n = o.n, info = layoutFor(sheet, o.viewOf), bad = (code, text, tone = "bad") => ({ ok: false, code, tone, text });
    if (info.kind === "frozen") return bad("frozen", TXT.frozen, "frozen");
    if (info.kind === "title" || info.kind === "tep") return bad("nomap", TXT.nomap(n));
    if (!info.editable) return bad("noedit", cap(info.why || "лист не меняется") + ".");
    if (!allowedRoles(info.layout, o.tpl).includes(role)) return bad("norole", role === "border" ? TXT.border(n) : TXT.norole(n, roleTitle(role)));
    return { ok: true, info };
  }
  // слой банка → лист: включить. Лист не меняется при отказе. Результат { ok, changed, groupId } или { ok: false, code, tone, text }
  function addItem(sheet, key, ctx = {}) {
    const role = roleOf(key).role, t = targetCheck(sheet, role, ctx); if (!t.ok) return t;
    const title = ctx.title || key, hit = flatten(t.info.layout).find(it => it.key === key);
    if (hit && hit.on !== false) return { ok: false, code: "have", tone: "none", text: TXT.have(ctx.n, title) };
    if (!t.info.stored) sheet.layout = t.info.layout;
    let gid;
    if (hit) { sheet.layout.groups.forEach(g => g.items.forEach(it => { if (it.key === key) { it.on = true; gid = g.id; } })); }
    else gid = putItem(sheet.layout, role, newItem(key, sheet, ctx), ctx);
    syncFields(sheet); return { ok: true, changed: true, groupId: gid };
  }
  const roleItems = (layout, role) => (layout?.groups || []).filter(g => g.role === role).flatMap(g => g.items || []);
  // роль листа src → лист dst: перенос (с src роль убирается) или копия. Элементы, что уже есть на dst, не дублируются (выключенный включается)
  function moveRole(src, dst, role, ctx = {}, copy = false) {
    const title = roleTitle(role), s = layoutFor(src, ctx.viewOf);
    if (src === dst) return { ok: false, code: "same", tone: "none", text: TXT.here(ctx.n, title) };
    if (!s.editable || !s.layout) return { ok: false, code: "noedit", tone: "bad", text: cap(s.why || "лист не меняется") + "." };
    const items = roleItems(s.layout, role).map(clone); if (!items.length) return { ok: false, code: "norole", tone: "bad", text: TXT.norole(ctx.n, title) };
    const t = targetCheck(dst, role, ctx); if (!t.ok) return t;
    const L = t.info.stored ? dst.layout : t.info.layout, mine = new Map(flatten(L).map(it => [it.key, it])); let changed = false;
    const hasGroup = L.groups.some(g => g.role === role);
    items.forEach(it => {
      const x = mine.get(it.key);
      if (x) { if (x.on === false) { L.groups.forEach(g => g.items.forEach(y => { if (y.key === it.key) y.on = true; })); changed = true; } return; }
      it.on = true; putItem(L, role, it, ctx); changed = true;
    });
    if (!changed) return { ok: false, code: "have", tone: "none", text: TXT.haveRole(ctx.n, title) };
    dst.layout = L; syncFields(dst);
    if (!copy) { if (!s.stored) src.layout = s.layout; src.layout.groups = src.layout.groups.filter(g => g.role !== role); syncFields(src); }
    return { ok: true, changed: true, hasGroup };
  }
  // очередь источников роли: { head, queue } — как её строит roleRows (только источники, что есть на листе)
  function srcQueue(layout, role) {
    const items = roleItems(layout, role), head = items.find(it => Array.isArray(it.src) && it.src.length); if (!head) return null;
    const present = head.src.filter(k => items.some(it => it.key === k));
    return { head, queue: present.length ? present : head.src.slice() };
  }
  // порядок источников дорог: источник с индексом from встаёт на место to. Главный — первый. true — лист изменён
  function reorderSrc(sheet, role, from, to, viewOf) {
    const info = layoutFor(sheet, viewOf); if (!info.editable) return false;
    const q = srcQueue(info.layout, role); if (!q) return false;
    const a = q.queue.slice(); if (from === to || from < 0 || to < 0 || from >= a.length || to >= a.length) return false;
    a.splice(to, 0, a.splice(from, 1)[0]);
    if (!info.stored) sheet.layout = info.layout;
    const h = srcQueue(sheet.layout, role).head; h.src = a.concat(h.src.filter(k => !a.includes(k))); return true;
  }
  // порядок источников дорог, который владелец поменял (иначе null — сборка выбирает как раньше, по roadsrc.js)
  function roadOrder(sheet) {
    if (!matches(sheet)) return null;
    const q = srcQueue(sheet.layout, "roads"); if (!q || same(q.head.src, roadQueue(sheet.basemap))) return null;
    return q.queue;
  }
  // источник по порядку владельца: первый, у которого в рамке есть полигоны. ya, egko — площади
  function pickByOrder(order, { ya = 0, egko = 0 } = {}) {
    for (const k of order || []) { if (k === "yandex.hd_roads" && ya > 0) return "yandex"; if (k === "egko.roads" && egko > 0) return "egko"; }
    return "none";
  }
  // при пересборке листа по шаблону правленный состав переходит: ключи листа уже перенесены (carryHand), а layout — из шаблона, он им не
  // соответствует; берётся прежний layout (оформление слоёв из шаблона обновляется), если он годен и ключи те же
  function carryLayout(fresh, old) {
    if (!old?.layout || old.frozen || !fresh || (fresh.layout && matches(fresh)) || !matches(old) || !same(fresh.keys, old.keys)) return false;
    const l = clone(old.layout), tpl = new Map(flatten(fresh.layout || { groups: [] }).map(it => [it.key, it]));
    l.groups.forEach(g => g.items.forEach(it => { const t = tpl.get(it.key); if (t) { if (t.style !== undefined) it.style = clone(t.style); else delete it.style; if (t.only !== undefined) it.only = clone(t.only); else delete it.only; } }));
    fresh.layout = l; return true;
  }
  // что покажет цель перетаскивания: { ok, tone: ok | bad | frozen | none, text }. drag = { type: "layer", key, title } | { type: "role", from, role }.
  // o = { copy, n (лист с 1), viewOf, ctx(sheet) → { tpl, others }, row (роль строки под курсором), titleOf(key) }
  function dropCheck(sheets, i, drag, o = {}) {
    const sh = sheets[i], n = i + 1, ctx = { ...(o.ctx?.(sh) || {}), n, viewOf: o.viewOf };
    if (!sh) return { ok: false, tone: "none", text: "" };
    if (drag.type === "layer") {
      const role = roleOf(drag.key).role, title = drag.title || o.titleOf?.(drag.key) || drag.key;
      if (o.row && o.row !== role) return { ok: false, tone: "bad", text: TXT.wrongRow(title, roleOf(drag.key).title, roleTitle(o.row)) };
      const t = targetCheck(sh, role, ctx); if (!t.ok) return t;
      if (flatten(t.info.layout).some(it => it.key === drag.key && it.on !== false)) return { ok: false, tone: "none", text: TXT.have(n, title) };
      return { ok: true, tone: "ok", text: `Отпустите: включить «${title}» на листе ${n}` };
    }
    if (drag.type === "role") {
      const title = roleTitle(drag.role);
      if (sheets[drag.from] === sh) return { ok: false, tone: "none", text: TXT.here(n, title) };
      const t = targetCheck(sh, drag.role, ctx); if (!t.ok) return t;
      const sl = layoutFor(sheets[drag.from], o.viewOf); if (!sl.editable) return { ok: false, tone: "bad", code: "noedit", text: cap(sl.why || "лист не меняется") + "." };
      const mine = new Set(flatten(t.info.layout).filter(it => it.on !== false).map(it => it.key)), src = sl;
      if (roleItems(src.layout, drag.role).every(it => mine.has(it.key))) return { ok: false, tone: "none", text: TXT.haveRole(n, title) };
      return { ok: true, tone: "ok", text: `Отпустите: ${o.copy ? "скопировать" : "перенести"} роль «${title}» на лист ${n}` };
    }
    return { ok: false, tone: "none", text: "" };
  }
  const api = { ROLES, roleOf, seedLayout, build, flatten, layoutKeys, layoutStyles, layoutOnly, matches, resolve, migrate,
    plural, providerName, roleTitle, frameCover, coverBadge, chooseSource, queueRows, sourceText, roleRows, layoutFor, setRole, carryOn, sheetKeysOn, layerSheets, bankGroups, missingRoles, sheetMeta,
    allowedRoles, syncFields, addItem, moveRole, srcQueue, reorderSrc, roadOrder, pickByOrder, carryLayout, dropCheck, targetCheck, roadQueue };
  if (typeof module === "object" && module.exports) module.exports = api;
  root.SheetLayout = api;
})(typeof window !== "undefined" ? window : globalThis);
