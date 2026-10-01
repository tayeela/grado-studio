// migrate.js: «потолок» → «предельная высота» в старом проекте (запуск — tests/test_migrate_js.py)
const assert = require("assert");
const { renameCeiling } = require("../web/migrate.js");
const { split, join } = require("../web/collab.js");
let n = 0; const ok = (c, m) => { assert.ok(c, "FAIL: " + m); n++; }, eq = (a, b, m) => { assert.deepStrictEqual(a, b, "FAIL: " + m); n++; };
const cell = (m, e) => ({ type: "Feature", geometry: { type: "Point", coordinates: [37.5, 55.7] }, properties: { _uid: "aaaaaaaaaaaa", "Потолок, м": m, "Потолок, эт.": e, "По ПЗЗ, м": 30, "Почему": "высота по ПЗЗ" } });
const mine = { type: "FeatureCollection", features: [{ type: "Feature", geometry: { type: "Point", coordinates: [37.5, 55.7] }, properties: { _uid: "bbbbbbbbbbbb", "Потолок, м": 99 } }] };
const old = () => ({
  format: "grado2", version: 2, name: "Старый", checked: [], groups: [], views: [], album: { meta: {}, sheets: [] }, view: { center: [37.5, 55.7], zoom: 15, basemap: "osm" },
  layers: [
    { key: "cons:ceiling", title: "Предельная высота застройки", geom: "poly", visible: true, layerOpacity: 1, open: false, group: null,
      style: { mode: "grad", label: "Потолок, м", cat: { field: "Потолок, м", colors: {}, off: [] }, grad: { field: "Потолок, эт.", n: 5, ramp: "green", method: "equal" }, rules: { list: [{ field: "Потолок, м", op: "<", val: "30", fill: "#f00" }, { field: "По ПЗЗ, м", op: "=", val: "30", fill: "#0f0" }], elseFill: "#ddd", elseHide: false } } },
    { key: "mine", title: "Мой слой", geom: "point", visible: true, layerOpacity: 1, open: false, group: null,
      style: { mode: "grad", cat: { field: "", colors: {}, off: [] }, grad: { field: "Потолок, м", n: 5, ramp: "blue", method: "equal" }, rules: { list: [{ field: "Потолок, м", op: "=", val: "1", fill: "#f00" }], elseFill: "#ddd", elseHide: false } } },
  ],
  data: { "cons:ceiling": { title: "t", fc: { type: "FeatureCollection", features: [cell(45.5, 15), cell(null, null)] } }, mine: { title: "m", fc: mine, original: "=fc" } },
  graph: { last_node_id: 3, links: [[1, 2, 1, 3, 2, "cap"]], nodes: [
    { id: 2, type: "Данные/Ограничения", outputs: [{ name: "запреты", type: "geom" }, { name: "потолок", type: "cap", links: [1] }] },
    { id: 3, type: "Эскиз/Посадка застройки", inputs: [{ name: "пятно", type: "geom" }, { name: "этажность", type: "num" }, { name: "потолок", type: "cap", link: 1 }] },
    { id: 4, type: "Данные/Слой", outputs: [{ name: "потолок", type: "geom" }] }] },
});
const check = p => {
  const c = p.layers[0].style, f = p.data["cons:ceiling"].fc.features;
  eq(c.label, "Предельная высота, м", "подпись"); eq(c.cat.field, "Предельная высота, м", "cat.field"); eq(c.grad.field, "Предельная высота, эт.", "grad.field");
  eq(c.rules.list.map(r => r.field), ["Предельная высота, м", "По ПЗЗ, м"], "поля правил; чужое поле правила не тронуто");
  eq(Object.keys(f[0].properties), ["_uid", "Предельная высота, м", "Предельная высота, эт.", "По ПЗЗ, м", "Почему"], "поля объекта, порядок сохранён");
  eq([f[0].properties["Предельная высота, м"], f[0].properties["Предельная высота, эт."], f[1].properties["Предельная высота, м"]], [45.5, 15, null], "значения");
  ok(!JSON.stringify(f).includes("Потолок"), "в данных слоя «Потолок» не осталось");
  eq(p.graph.nodes[0].outputs[1].name, "предельная высота", "выход NCons"); eq(p.graph.nodes[1].inputs[2].name, "предельная высота", "вход посадки");
  eq(p.graph.nodes[2].outputs[0].name, "потолок", "гнездо чужого узла не тронуто");
  eq(p.graph.nodes[1].inputs[2].link, 1, "связь цела");
};
{ // миграция и идемпотентность
  const p = renameCeiling(old()); check(p);
  const once = JSON.stringify(p); renameCeiling(p); eq(JSON.stringify(p), once, "второй прогон ничего не меняет"); check(p);
  // слой пользователя «mine»: поля и стиль с именем «Потолок, м» остались
  eq(p.data.mine.fc.features[0].properties["Потолок, м"], 99, "слой пользователя: данные"); eq(p.layers[1].style.grad.field, "Потолок, м", "слой пользователя: стиль"); eq(p.layers[1].style.rules.list[0].field, "Потолок, м", "слой пользователя: правило");
}
{ // новый проект без слоя и графа, пустой ввод
  eq(renameCeiling({ format: "grado2", version: 2 }), { format: "grado2", version: 2 }, "проект без слоя и графа");
  eq(renameCeiling(null), null, "null"); 
}
{ // совместная работа: старый проект с хаба → split → join (как loadProject) → миграция
  const p = join(split(old()), {}); check(renameCeiling(p));
  const nz = q => JSON.stringify({ ...q, saved_at: 0 }); eq(nz(renameCeiling(join(split(p), {}))), nz(p), "split/join новой формы стабилен");
}
console.log(n + " checks ok");
