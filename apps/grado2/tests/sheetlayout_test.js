// sheetlayout.js: состав слоёв листа по ролям (запуск — tests/test_sheetlayout_js.py). T86a, 06.10.2026.
const assert = require("assert");
const L = require("../web/sheetlayout.js");
let n = 0; const eq = (a, b, msg) => { assert.deepStrictEqual(a, b, "FAIL: " + msg); n++; };
// лист 5 шаблона ППТ КРТ (ключи в порядке рисования)
const KEYS5 = ["egko.water", "yandex.hd_roads", "egko.roads", "egko.buildings", "yandex.rail", "nspd.parcels", "gisogd.zouit", "gisogd.szz", "gisogd.vodookhr",
  "gisogd.red_lines", "gisogd.airfield", "osm.landuse", "osm.roads", "egko.water_labels", "egko.place_labels", "egko.addresses", "yandex.stations"];
const ST = { "egko.water": { fill: "#336699" }, "yandex.hd_roads": { fill: "#ccc" }, "nspd.parcels": { opacity: 0 } }, ONLY = { "osm.roads": { field: "Тип дороги", values: ["primary"] } };
const tpl = { keys: KEYS5, styles: ST, only: ONLY, basemap: undefined };
const lay = L.seedLayout(tpl);
// порядок рисования сохраняется целиком, стили и отборы — те же
eq(L.layoutKeys(lay), KEYS5, "ключи в том же порядке");
eq(L.layoutStyles(lay), ST, "стили те же");
eq(L.layoutOnly(lay), ONLY, "отборы те же");
eq(L.flatten(lay).length, KEYS5.length, "все слои — элементы");
// группы по ролям, подряд идущие слои одной роли — одна группа, повтор роли — id с номером
eq(lay.groups.map(g => g.id), ["water", "roads", "buildings", "rail", "parcels", "zouit", "redlines", "zouit-2", "names", "rail-2"], "группы листа 5");
eq(lay.groups[1], { id: "roads", title: "Дороги", role: "roads", items: [
  { key: "yandex.hd_roads", on: true, style: { fill: "#ccc" }, src: ["egko.roads", "yandex.hd_roads"] }, { key: "egko.roads", on: true }] }, "группа дорог");
eq(L.seedLayout({ keys: ["yandex.hd_roads", "egko.roads"], basemap: "sat" }).groups[0].items[0].src, ["yandex.hd_roads", "egko.roads"], "на снимке Яндекс первым");
eq(L.seedLayout({ keys: ["x.unknown"] }).groups[0].role, "other", "слой без роли — прочее");
eq(L.seedLayout({ keys: ["a", "a"] }).groups[0].items.length, 1, "повтор ключа не дублируется");
eq(L.seedLayout({}), null, "лист без keys — без layout");
eq(L.seedLayout(null), null, "нет шаблона");
// seed не делит объекты с шаблоном
lay.groups[0].items[0].style.fill = "#000"; eq(ST["egko.water"].fill, "#336699", "стиль склонирован");
// выключенный элемент не попадает в ключи
const l2 = L.seedLayout(tpl); l2.groups[1].items[1].on = false;
eq(L.layoutKeys(l2).includes("egko.roads"), false, "on: false убирает слой");
// resolve: layout, пока совпадает с keys; иначе — поля листа
const sh = { keys: KEYS5.slice(), styles: ST, only: ONLY, layout: L.seedLayout(tpl) };
eq(L.resolve(sh).layout, true, "layout годен");
eq(L.resolve(sh).keys, KEYS5, "resolve.keys");
eq(L.resolve(sh).only, ONLY, "resolve.only");
sh.keys = ["nspd.parcels", ...KEYS5.filter(k => k !== "nspd.parcels")];       // слой добавили рукой (layers.js sheetSet)
eq(L.resolve(sh).layout, false, "keys правлены рукой — layout не читается");
eq(L.resolve(sh).keys, sh.keys, "лист живёт по keys");
eq(L.resolve({ keys: ["a"] }).keys, ["a"], "нет layout — старое поведение");
eq(L.resolve({ view: "v" }).keys, null, "лист по виду — без keys");
eq(L.resolve({ keys: KEYS5, layout: lay, frozen: true }).layout, false, "готовый лист layout не читает");
// миграция из keys и из вида
eq(L.migrate({ keys: KEYS5, styles: ST, only: ONLY }), L.seedLayout(tpl), "migrate из keys = seed");
eq(L.migrate({ keys: ["a"], frozen: true }), null, "готовый лист — нет");
eq(L.migrate({ view: "v" }), null, "текущая карта — нет");
const mv = L.migrate({ view: "v" }, { layers: [{ key: "egko.water", visible: true, style: { fill: "#1" } }, { key: "egko.buildings", visible: false }] });
eq(L.layoutKeys(mv), ["egko.water"], "из вида: только видимые включены");
eq(L.flatten(mv).map(i => [i.key, i.on]), [["egko.water", true], ["egko.buildings", false]], "из вида: порядок и on");
const had = { keys: ["a"], layout: { groups: [{ id: "x", title: "X", role: "other", items: [{ key: "b", on: true }] }] } };
eq(L.migrate(had), had.layout, "готовый layout не пересчитывается");
eq(L.migrate(had) !== had.layout, true, "копия, не тот же объект");

// ---- T86b: глаз, покрытие, строки ролей, номера листов ----
// глаз: выключенный элемент остаётся в keys, layout годен, но слой не рисуется
const e1 = { keys: KEYS5.slice(), styles: ST, only: ONLY, layout: L.seedLayout(tpl) };
eq(L.setRole(e1, "water", false), true, "глаз выключил воду");
eq(L.matches(e1), true, "после глаза layout совпадает с keys");
eq(L.resolve(e1).keys.includes("egko.water"), false, "выключенная вода не в resolve");
eq(L.resolve(e1).keys.length, KEYS5.length - 1, "остальные слои на месте");
eq(e1.keys.includes("egko.water"), true, "в keys слой остаётся");
eq(L.setRole(e1, "water", false), false, "повторное выключение ничего не меняет");
eq(L.setRole(e1, "water", true), true, "включили обратно");
eq(L.resolve(e1).keys, KEYS5, "всё включено — как раньше");
eq(L.setRole(e1, "roads", false), true, "дороги: оба слоя группы"); eq(L.layoutKeys(e1.layout).filter(k => /roads$/.test(k) && k !== "osm.roads").length, 0, "оба слоя дорог выключены");
e1.keys.push("x.new"); eq(L.matches(e1), false, "keys правлены рукой — layout не читается");
// у листа без layout сначала записывается migrate
const e2 = { keys: ["egko.water", "egko.buildings"], styles: {} };
eq(L.setRole(e2, "water", false), true, "лист без layout: глаз пишет migrate"); eq(L.resolve(e2).keys, ["egko.buildings"], "вода скрыта"); eq(Array.isArray(e2.layout.groups), true, "layout записан");
// неактивный глаз: готовый лист, лист по виду, повторы в keys, неизвестная группа
const fz = { frozen: true, layers: [], keys: ["a"] }; eq(L.setRole(fz, "x", false), false, "готовый лист не меняется"); eq(fz.layout, undefined, "и layout не пишется");
eq(L.layoutFor({ view: "v" }, () => ({ layers: [{ key: "egko.water", visible: true }] })).editable, false, "по виду глаз неактивен");
eq(L.layoutFor({ view: "v" }, () => ({ layers: [{ key: "egko.water", visible: true }] })).layout.groups.length, 1, "по виду состав показан");
eq(L.layoutFor({ keys: ["a", "a"] }).editable, false, "повтор ключа: глаз выключен");
eq(L.layoutFor({ kind: "title" }).kind, "title", "титул"); eq(L.layoutFor({ panels: [] }).kind, "panels", "две карты"); eq(L.layoutFor({ view: "" }).layout, null, "текущая карта — без состава");
eq(L.setRole(e2, "нет-такой", false), false, "неизвестная группа");
// переход глаза при пересборке по шаблону
const old = { keys: KEYS5.slice(), layout: L.seedLayout(tpl) }, fr = { layout: L.seedLayout(tpl) };
L.setRole(old, "buildings", false); L.carryOn(fr, old);
eq(L.flatten(fr.layout).filter(i => !i.on).map(i => i.key), ["egko.buildings"], "carryOn: выключенное переходит"); L.carryOn({}, old); L.carryOn(fr, {});
const old2 = { keys: ["yandex.hd_roads", "egko.water"], layout: L.migrate({ keys: ["yandex.hd_roads", "egko.water"] }) }, fr2 = { layout: L.seedLayout({ keys: ["yandex.hd_roads", "egko.roads", "egko.water"] }) };
L.setRole(old2, "roads", false); L.carryOn(fr2, old2); eq(L.layoutKeys(fr2.layout), ["egko.water"], "роль скрыта целиком — новый слой роли тоже скрыт");
// покрытие рамки областью выгрузки
eq(L.frameCover([0, 0, 2, 2], [0, 0, 2, 2]), 1, "полностью"); eq(L.frameCover([0, 0, 2, 2], [-5, -5, 5, 5]), 1, "область больше рамки");
eq(L.frameCover([0, 0, 2, 2], [1, 0, 3, 2]), .5, "половина"); eq(L.frameCover([0, 0, 2, 2], [5, 5, 6, 6]), 0, "вне рамки");
eq(L.frameCover([0, 0, 2, 2], null), null, "нет области"); eq(L.frameCover([0, 0, 0, 2], [0, 0, 1, 1]), null, "вырожденная рамка");
// бейджи
eq(L.coverBadge("egko.buildings", { loaded: true, cover: .88 }), { text: "на 12 % рамки нет", tone: "warn" }, "на 12 %");
eq(L.coverBadge("yandex.rail", { loaded: true, cover: .6 }), { text: "окно 40 км²", tone: "warn" }, "окно Яндекса");
eq(L.coverBadge("egko.water", { loaded: true, cover: 1, empty: true }), { text: "в рамке нет", tone: "none" }, "пусто в рамке");
eq(L.coverBadge("egko.water", { loaded: true, cover: 1, empty: false }), null, "всё хорошо — без бейджа");
eq(L.coverBadge("egko.water", { loaded: false }), { text: "не выгружен", tone: "warn" }, "не выгружен");
eq(L.coverBadge("egko.water", { loaded: false, error: true }), { text: "не загрузился", tone: "bad" }, "ошибка выгрузки");
eq(L.coverBadge("egko.water", { loaded: true, cover: 0 }), { text: "данные вне рамки", tone: "warn" }, "вне рамки");
eq(L.coverBadge("egko.water", { loaded: true, cover: .999 }), null, "99,9 % — без бейджа");
eq(L.coverBadge("egko.water", { loaded: true, cover: .996 }), null, "99,6 % — без бейджа");
eq(L.coverBadge("egko.water", { loaded: true, cover: .994 }).text, "на 1 % рамки нет", "99,4 % — на 1 %");
// очередь источников и строки ролей
const P = { "egko.roads": { loaded: true, cover: .93 }, "yandex.hd_roads": { loaded: true, cover: .61 }, "osm.roads": { loaded: true, cover: 1 } };
const probe = k => P[k] || { loaded: true, cover: 1, empty: false };
eq(L.chooseSource(["egko.roads", "yandex.hd_roads"], probe), "egko.roads", "первый с покрытием ≥ 90 %");
eq(L.chooseSource(["yandex.hd_roads", "egko.roads"], probe), "egko.roads", "главный не дотянул — запасной");
eq(L.chooseSource(["yandex.hd_roads", "osm.roads"], k => k === "osm.roads" ? { loaded: true, cover: .5 } : { loaded: true, cover: .2 }), "osm.roads", "никто не дотянул — лучший");
eq(L.chooseSource(["a", "b"], () => ({}), "b"), "b", "решение сборки главнее"); eq(L.chooseSource([], probe), null, "очереди нет");
eq(L.queueRows(["egko.roads", "yandex.hd_roads"], probe, "egko.roads").map(r => [r.n, r.provider, r.used, r.badge?.text || ""]), [[1, "ЕГКО", true, "на 7 % рамки нет"], [2, "Яндекс", false, "окно 40 км²"]], "строки очереди");
eq(L.sourceText(["gisogd.zouit", "gisogd.szz", "gisogd.vodookhr"]), "ГИС ОГД · 3 слоя", "три слоя одного портала");
eq(L.sourceText(["osm.roads", "egko.water_labels", "osm.landuse"]), "OSM · 2 слоя · ЕГКО", "два портала"); eq(L.sourceText(["x.y"]), "файл", "свой слой");
const rr = L.roleRows(lay, probe), by = Object.fromEntries(rr.map(r => [r.id, r]));
eq(rr.map(r => r.id), ["water", "roads", "buildings", "rail", "parcels", "zouit", "redlines", "names"], "одна строка на роль, на месте первого появления");
eq(by.zouit.ids, ["zouit", "zouit-2"], "группы одной роли слиты"); eq(by.zouit.count, 4, "число слоёв роли"); eq(by.rail.count, 2, "рельс: 2 слоя"); eq(by.roads.source, "ЕГКО", "дороги: выбранный источник"); eq(by.roads.cover, .93, "покрытие выбранного");
eq(by.roads.queue.keys, ["egko.roads", "yandex.hd_roads"], "очередь у дорог");
const oldRoads = L.roleRows(L.seedLayout({ keys: ["yandex.hd_roads"] }), probe)[0]; eq(oldRoads.queue.keys, ["yandex.hd_roads"], "лист без ЕГКО-дорог: очередь только из того, что на листе"); eq(oldRoads.source, "Яндекс", "и источник — Яндекс"); eq(by.zouit.source, "ГИС ОГД · 4 слоя", "ЗОУИТ"); eq(by.zouit.queue, null, "очереди нет");
const pe = k => k === "gisogd.airfield" ? { loaded: true, cover: 1, empty: true } : probe(k);
eq(L.roleRows(L.seedLayout({ keys: ["gisogd.airfield"] }), pe)[0].badge, { text: "в рамке нет", tone: "none" }, "пустая роль");
eq(L.roleRows(L.seedLayout({ keys: ["gisogd.airfield"] }), pe)[0].empty, true, "empty у строки");
const rn = L.roleRows(L.seedLayout({ keys: ["nspd.parcels"] }), () => ({})); eq(rn[0].cover, null, "покрытие неизвестно"); eq(rn[0].badge.text, "не выгружен", "нет данных — не выгружен");
const off = L.seedLayout(tpl); L.setRole({ layout: off, keys: KEYS5 }, "water", false); eq(L.roleRows(off, probe)[0].on, false, "строка выключена");
// слои проекта: номера листов
const shs = [{ kind: "title" }, { frozen: true, keys: ["egko.water"] }, { keys: ["egko.water", "egko.buildings"] }, { keys: ["egko.water"], layout: null }, { view: "v" }, { panels: [{ keys: ["egko.water"] }] }, { kind: "tep" }];
eq(L.layerSheets(shs, "egko.water", s => s.view === "v" ? ["egko.water"] : null), [3, 4, 5, 6], "листы со слоем (титул, готовый, ТЭП — нет)");
const s3 = { keys: ["egko.water", "egko.buildings"], layout: L.migrate({ keys: ["egko.water", "egko.buildings"] }) }; L.setRole(s3, "water", false);
eq(L.layerSheets([s3], "egko.water"), [], "выключенный глазом слой не в номерах"); eq(L.layerSheets([s3], "egko.buildings"), [1], "включённый — в номерах");
const bg = L.bankGroups([{ key: "egko.buildings", title: "Здания" }, { key: "my.layer", title: "Мой" }, { key: "egko.water", title: "Вода" }, { key: "nspd.parcels", title: "Участки" }], shs);
eq(bg.map(g => g.role), ["parcels", "buildings", "water", "other"], "роли банка в порядке ROLES, прочее — последним"); eq(bg[2].items[0].sheets, [3, 4, 6], "номера у слоя банка");
// роли, которых на листе нет
const lays = [L.seedLayout({ keys: ["egko.water", "nspd.parcels"] }), L.seedLayout({ keys: ["egko.water"] }), null];
eq(L.missingRoles(lays, 1), ["Участки"], "на листе 2 нет участков"); eq(L.missingRoles(lays, 0), [], "на листе 1 есть всё"); eq(L.missingRoles(lays, 2), ["Участки", "Вода"], "лист без состава");
eq(L.missingRoles([L.seedLayout({ keys: ["gisogd.admin", "egko.water"] }), L.seedLayout({ keys: ["egko.water"] })], 1), [], "границы не считаются отсутствующей ролью");
const mg = { keys: KEYS5.slice(), layout: L.seedLayout(tpl) }; eq(L.setRole(mg, ["zouit", "zouit-2"], false), true, "глаз сразу у двух групп роли"); eq(L.layoutKeys(mg.layout).filter(k => /zouit|szz|vodookhr|airfield/.test(k)).length, 0, "обе группы ЗОУИТ скрыты");
// подписи
eq(L.sheetMeta({ basemap: "sat" }, { layout: lay, kind: "map" }), "снимок · " + L.plural(new Set(lay.groups.map(g => g.role)).size, ["роль", "роли", "ролей"]), "основа и роли");
eq(L.sheetMeta({}, { kind: "frozen" }), "готовая вёрстка из файла", "готовый"); eq(L.sheetMeta({}, { kind: "title" }), "шаблон, слоёв нет", "титул");
eq([1, 2, 5, 11, 12, 21, 25].map(k => L.plural(k, ["роль", "роли", "ролей"])), ["1 роль", "2 роли", "5 ролей", "11 ролей", "12 ролей", "21 роль", "25 ролей"], "склонение");
eq(L.providerName("gisogd.zouit"), "ГИС ОГД", "портал"); eq(L.roleTitle("roads"), "Дороги", "роль");
// ---- T86c: перетаскивание ----
const mk = keys => { const sh = { id: "s" + Math.random(), keys: keys.slice(), basemap: undefined }; sh.layout = L.seedLayout({ keys }); return sh; };
const T9 = L.seedLayout({ keys: ["nspd.parcels", "osm.landuse", "osm.roads", "egko.water", "egko.water_labels", "yandex.stations"] });      // образец листа 9
const T5 = L.seedLayout(tpl);
eq(L.allowedRoles(T9, T9), ["parcels", "names", "water", "rail"], "допустимые роли: образец листа 9");
eq(L.allowedRoles(T5, T5), ["water", "roads", "buildings", "rail", "parcels", "zouit", "redlines", "names"], "допустимые роли: образец листа 5");
eq(L.allowedRoles(L.seedLayout({ keys: ["egko.buildings"] }), T9), ["parcels", "names", "water", "rail", "buildings"], "роль, что лист уже имеет, допустима (в конце)");
eq(L.allowedRoles(null, null), [], "нет ни образца, ни состава");
// слой банка → лист: роль есть
const a1 = mk(["egko.water", "yandex.hd_roads", "egko.roads", "egko.buildings"]), c1 = { tpl: T5, n: 5, title: "Здания (ЕГКО)" };
let r = L.addItem(a1, "egko.buildings", c1); eq([r.ok, r.code, r.tone], [false, "have", "none"], "слой уже включён — отказ-подсказка");
L.setRole(a1, "buildings", false); r = L.addItem(a1, "egko.buildings", c1); eq([r.ok, r.changed, r.groupId], [true, true, "buildings"], "выключенный включается");
eq(L.layoutKeys(a1.layout), a1.keys, "после включения keys = layout");
// роль есть, слоя нет: в конец группы
const a2 = mk(["egko.water", "yandex.rail", "egko.buildings"]); r = L.addItem(a2, "yandex.stations", { ...c1, tpl: T5 });
eq(a2.layout.groups.map(g => g.id + ":" + g.items.map(i => i.key).join("+")), ["water:egko.water", "rail:yandex.rail+yandex.stations", "buildings:egko.buildings"], "слой встал в конец группы своей роли");
eq(a2.keys, ["egko.water", "yandex.rail", "yandex.stations", "egko.buildings"], "keys следуют за layout"); eq(L.matches(a2), true, "layout годен");
// роли нет, по образцу допустима: группа на место по образцу
const a3 = mk(["egko.water", "egko.buildings", "osm.roads"]); r = L.addItem(a3, "yandex.rail", { tpl: T5, n: 3, title: "Железная дорога" });
eq(a3.layout.groups.map(g => g.id), ["water", "buildings", "rail", "names"], "роль рельс — после зданий, перед названиями (порядок образца, не курсор)");
eq(a3.keys, ["egko.water", "egko.buildings", "yandex.rail", "osm.roads"], "порядок рисования сохранён");
const a3b = mk(["osm.roads", "egko.buildings"]); L.addItem(a3b, "egko.water", { tpl: T5, n: 1 }); eq(a3b.layout.groups.map(g => g.role), ["water", "names", "buildings"], "вода — в самое начало образца");
// оформление нового слоя — из образца, затем из других листов
const T5s = L.seedLayout({ keys: ["yandex.rail"], styles: { "yandex.rail": { fill: "#111" } } }), a4 = mk(["egko.water"]);
L.addItem(a4, "yandex.rail", { tpl: T5s, n: 2 }); eq(a4.styles, { "yandex.rail": { fill: "#111" } }, "стиль из образца"); eq(a4.layout.groups[0].items[0].style, { fill: "#111" }, "и в layout");
const a4b = mk(["egko.water"]); L.addItem(a4b, "yandex.rail", { tpl: L.seedLayout({ keys: ["egko.water", "yandex.rail"] }), others: [L.seedLayout({ keys: ["yandex.rail"], styles: { "yandex.rail": { fill: "#222" } } })], n: 2 });
eq(a4b.styles["yandex.rail"], undefined, "образец главнее других листов (в нём стиля нет)");
const a4c = mk(["egko.water"]); L.addItem(a4c, "yandex.rail", { tpl: L.seedLayout({ keys: ["egko.water", "yandex.stations"] }), others: [null, L.seedLayout({ keys: ["yandex.rail"], styles: { "yandex.rail": { fill: "#222" } } })], n: 2 });
eq(a4c.styles["yandex.rail"], { fill: "#222" }, "нет в образце — стиль с другого листа");
// дороги: источник Яндекса получает очередь
const a5 = mk(["egko.water"]); L.addItem(a5, "yandex.hd_roads", { tpl: T5, n: 4 }); eq(a5.layout.groups[1].items[0].src, ["egko.roads", "yandex.hd_roads"], "очередь дорог на векторной схеме");
// отказы
const f9 = mk(["nspd.parcels", "osm.roads"]); r = L.addItem(f9, "egko.buildings", { tpl: T9, n: 9, title: "Здания (ЕГКО)" });
eq([r.ok, r.code, r.text], [false, "norole", "На листе 9 нет роли «Здания» — по образцу её там не показывают"], "лист 9: зданий по образцу нет"); eq(f9.keys, ["nspd.parcels", "osm.roads"], "отказ не меняет лист");
r = L.addItem({ frozen: true, keys: ["egko.water"] }, "egko.water", { n: 2 }); eq([r.ok, r.code, r.tone, r.text], [false, "frozen", "frozen", "Лист готов, замок — Alt при отпускании сделает рабочую копию"], "готовый лист");
r = L.addItem({ kind: "title" }, "egko.water", { n: 1 }); eq(r.code, "nomap", "титул"); r = L.addItem({ panels: [{}] }, "egko.water", { n: 1 }); eq(r.code, "noedit", "две карты");
r = L.addItem(mk(["osm.roads"]), "gisogd.admin", { tpl: T9, n: 9 }); eq(r.text, "На листе 9 границы не добавляются: территория и район рисуются сами", "границы");
r = L.addItem(mk(["osm.roads"]), "my.layer", { tpl: T9, n: 9, title: "Мой" }); eq(r.code, "norole", "свой слой — прочее, по образцу нет");
// лист без layout, но с keys: layout записывается
const old1 = { keys: ["egko.water", "osm.roads"] }; r = L.addItem(old1, "egko.buildings", { tpl: T5, n: 6 }); eq([r.ok, !!old1.layout, old1.keys], [true, true, ["egko.water", "egko.buildings", "osm.roads"]], "лист без layout получает его");
// роль на другой лист
const s5 = mk(KEYS5), s6 = mk(["egko.water", "egko.buildings", "osm.roads"]), t3 = mk(["yandex.hd_roads", "osm.roads"]);
r = L.moveRole(s5, s6, "rail", { tpl: T5, n: 6 }, true); eq(r.ok, true, "копия роли"); eq(L.roleRows(s6.layout, () => ({})).map(x => x.role), ["water", "buildings", "rail", "names"], "роль встала по образцу");
eq(L.layoutKeys(s5.layout).includes("yandex.rail"), true, "с листа 5 копия не убрала"); eq(s6.keys.filter(k => /yandex/.test(k)), ["yandex.rail", "yandex.stations"], "оба слоя роли и в keys"); eq(L.matches(s6), true, "лист 6 годен");
const r1 = L.moveRole(s5, s6, "rail", { tpl: T5, n: 6 }, true); eq([r1.ok, r1.code], [false, "have"], "повторная копия — уже есть");
const k5 = s5.keys.length, rl = L.moveRole(s5, t3, "rail", { tpl: T5, n: 3 }, false); eq(rl.ok, true, "перенос");
eq(s5.keys.filter(k => /rail|stations/.test(k)), [], "перенос убрал роль с листа 5 (обе группы роли)"); eq(s5.keys.length, k5 - 2, "keys листа 5 сократились"); eq(L.matches(s5), true, "лист 5 годен");
eq(t3.keys.includes("yandex.stations"), true, "на лист 3 пришли"); eq(s5.layout.groups.some(g => g.role === "rail"), false, "групп роли на листе 5 нет");
eq(L.moveRole(s5, s5, "water", { n: 5 }).code, "same", "на тот же лист"); eq(L.moveRole(s5, f9, "water", { tpl: T9, n: 9 }, false).ok, true, "вода на лист 9 по образцу можно");
eq(L.moveRole(s5, f9, "buildings", { tpl: T9, n: 9 }, false).code, "norole", "здания на лист 9 — нельзя"); eq(L.layoutKeys(s5.layout).includes("egko.buildings"), true, "отказ не убрал роль с источника");
eq(L.moveRole(s5, { frozen: true }, "roads", { n: 2 }).tone, "frozen", "на готовый лист"); eq(L.moveRole(s5, s6, "parcels", { tpl: T5, n: 6 }).ok, true, "участки на лист 6 — по образцу листа 5, который передан как образец цели");
// выключенный на цели элемент включается переносом
const d1 = mk(["egko.water", "egko.buildings"]); L.setRole(d1, "buildings", false); eq(L.moveRole(s6, d1, "buildings", { tpl: T5, n: 1 }, true).ok, true, "выключенное включено"); eq(L.layoutKeys(d1.layout), ["egko.water", "egko.buildings"], "элемент не продублирован");
// порядок источников
const q1 = mk(["egko.water", "yandex.hd_roads", "egko.roads"]); eq(L.srcQueue(q1.layout, "roads").queue, ["egko.roads", "yandex.hd_roads"], "очередь");
eq(L.roadOrder(q1), null, "не менял — порядок не задан"); eq(L.reorderSrc(q1, "roads", 1, 0), true, "Яндекс первым"); eq(L.srcQueue(q1.layout, "roads").queue, ["yandex.hd_roads", "egko.roads"], "порядок записан");
eq(L.roadOrder(q1), ["yandex.hd_roads", "egko.roads"], "порядок владельца"); eq(L.reorderSrc(q1, "roads", 0, 0), false, "то же место"); eq(L.reorderSrc(q1, "roads", 0, 5), false, "за краем"); eq(L.reorderSrc(q1, "water", 0, 1), false, "нет очереди у воды");
eq(L.reorderSrc(q1, "roads", 0, 1), true, "и обратно"); eq(L.roadOrder(q1), null, "вернули как было — порядка владельца нет");
eq(L.reorderSrc({ frozen: true, keys: ["yandex.hd_roads"] }, "roads", 0, 1), false, "готовый лист");
const q2 = { keys: ["yandex.hd_roads", "egko.roads"] }; eq(L.reorderSrc(q2, "roads", 1, 0), true, "лист без layout: layout записывается"); eq(!!q2.layout, true, "layout записан");
eq(L.roadOrder({ keys: ["a"], layout: L.seedLayout({ keys: ["yandex.hd_roads"] }) }), null, "layout не годен — порядка нет (keys иные)");
eq(L.roadOrder({ keys: ["yandex.hd_roads"], layout: { groups: [{ id: "roads", role: "roads", items: [{ key: "yandex.hd_roads", on: true, src: ["yandex.hd_roads", "egko.roads"] }] }] } }), ["yandex.hd_roads"], "src иной, чем по умолчанию, — порядок задан (на листе один Яндекс)");
eq(L.pickByOrder(["yandex.hd_roads", "egko.roads"], { ya: 5, egko: 9 }), "yandex", "порядок владельца: главный Яндекс"); eq(L.pickByOrder(["yandex.hd_roads", "egko.roads"], { ya: 0, egko: 9 }), "egko", "главного в рамке нет — запасной");
eq(L.pickByOrder(["egko.roads", "yandex.hd_roads"], { ya: 5, egko: 0.1 }), "egko", "главный ЕГКО — хоть немного"); eq(L.pickByOrder([], { ya: 1 }), "none", "порядка нет");
// пересборка по шаблону: правленный layout переходит, оформление — из шаблона
const oldB = mk(["egko.water", "yandex.hd_roads", "egko.roads"]); L.reorderSrc(oldB, "roads", 1, 0); L.addItem(oldB, "egko.buildings", { tpl: L.seedLayout({ keys: ["egko.water", "egko.buildings"] }), n: 5 });
const fr3 = { keys: oldB.keys.slice(), layout: L.seedLayout({ keys: ["egko.water", "yandex.hd_roads", "egko.roads"], styles: { "egko.water": { fill: "#abc" } } }) };
fr3.layout.groups.forEach(g => g.items.forEach(() => {})); eq(L.matches(fr3), false, "шаблон не совпал с правленными ключами");
eq(L.carryLayout(fr3, oldB), true, "правленный состав перенесён"); eq(L.matches(fr3), true, "годен"); eq(L.srcQueue(fr3.layout, "roads").queue, ["yandex.hd_roads", "egko.roads"], "порядок источников переехал"); eq(fr3.layout.groups[0].items[0].style, { fill: "#abc" }, "оформление из шаблона");
eq(L.carryLayout({ keys: ["x"] }, oldB), false, "ключи иные — не переносится"); eq(L.carryLayout(fr3, oldB), false, "уже годен");
// что показывается на цели
const SHS = [{ kind: "title" }, mk(KEYS5), s6, f9, { frozen: true, keys: ["egko.water"] }], oc = { ctx: sh => ({ tpl: sh === f9 ? T9 : T5 }), titleOf: k => k };
let dc = L.dropCheck(SHS, 3, { type: "layer", key: "egko.buildings", title: "Здания (ЕГКО)" }, oc); eq([dc.ok, dc.tone, dc.text], [false, "bad", "На листе 4 нет роли «Здания» — по образцу её там не показывают"], "цель: отказ красной подписью");
dc = L.dropCheck(SHS, 2, { type: "layer", key: "egko.roads", title: "Дороги ЕГКО" }, oc); eq(dc.ok, true, "цель: принимает"); eq(dc.text, "Отпустите: включить «Дороги ЕГКО» на листе 3", "цель: подпись");
dc = L.dropCheck(SHS, 4, { type: "layer", key: "egko.water", title: "Вода" }, oc); eq([dc.ok, dc.tone], [false, "frozen"], "цель: готовый лист");
dc = L.dropCheck(SHS, 1, { type: "layer", key: "egko.water", title: "Вода" }, oc); eq([dc.ok, dc.tone], [false, "none"], "цель: слой уже включён");
dc = L.dropCheck(SHS, 2, { type: "layer", key: "egko.water", title: "Вода" }, { ...oc, row: "roads" }); eq([dc.ok, dc.tone, dc.text], [false, "bad", "Слой «Вода» относится к роли «Вода», а не «Дороги»"], "слой на строку чужой роли");
dc = L.dropCheck(SHS, 2, { type: "role", from: 1, role: "zouit" }, { ...oc, copy: true }); eq([dc.ok, dc.text], [true, "Отпустите: скопировать роль «ЗОУИТ» на лист 3"], "роль, копия"); dc = L.dropCheck(SHS, 2, { type: "role", from: 1, role: "zouit" }, oc); eq(dc.text, "Отпустите: перенести роль «ЗОУИТ» на лист 3", "роль, перенос");
dc = L.dropCheck(SHS, 1, { type: "role", from: 1, role: "water" }, oc); eq([dc.ok, dc.tone], [false, "none"], "роль на тот же лист");
dc = L.dropCheck(SHS, 3, { type: "role", from: 1, role: "buildings" }, oc); eq(dc.tone, "bad", "роль на лист без неё по образцу");
dc = L.dropCheck(SHS, 0, { type: "role", from: 1, role: "water" }, oc); eq(dc.code, "nomap", "роль на титул");

console.log(n + " checks ok");
