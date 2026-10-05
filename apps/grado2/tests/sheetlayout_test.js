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
console.log(n + " checks ok");
