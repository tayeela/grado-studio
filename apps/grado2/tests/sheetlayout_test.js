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
console.log(n + " checks ok");
