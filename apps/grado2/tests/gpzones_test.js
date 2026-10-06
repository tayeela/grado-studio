// gpzones.js: имя, индекс и цвет функциональной зоны Генплана (запуск — tests/test_gpzones_js.py).
const assert = require("assert");
const G = require("../web/gpzones.js");
let n = 0; const eq = (a, b, m) => { assert.strictEqual(a, b, "FAIL: " + m + " | " + JSON.stringify(a)); n++; };
const old = { naimfunkzony: "коммунальные зоны", fztip: "130", n: 6 }, tin = { "Вид зоны": "Общественно - жилая зона", fz_type: 120 };
eq(G.zoneName(old), "коммунальные зоны", "имя старой Москвы"); eq(G.zoneIdx(old), "130", "индекс fztip");
eq(G.zoneName(tin), "Общественно - жилая зона", "имя ТиНАО"); eq(G.zoneIdx(tin), "120", "индекс fz_type");
eq(G.zoneIdx({ fztip: "130.0" }), "130", "индекс с дробной частью");
eq(G.fill(G.zoneName(old), G.zoneIdx(old)), "#ad84ae", "130 — #AD84AE по индексу");
eq(G.fill("коммунальные зоны", ""), "#ad84ae", "без индекса — по названию 130");
eq(G.fill("Общественно - жилая зона", ""), "#ee8e62", "название с пробелами у дефиса");
eq(G.fill("неизвестная", "", () => "#111111"), "#111111", "fallback");
eq(G.fill("неизвестная", ""), undefined, "без fallback");
eq(G.fill("жилая зона", "130"), "#ad84ae", "индекс сильнее названия");
// F3: один знак — одна строка легенды; название — зоны территории
const LR = G.legendRows([{ name: "промышленные зоны", idx: "130", fill: "#ad84ae", a: 90 }, { name: "коммунальные зоны", idx: "130", fill: "#ad84ae", a: 10, terr: true },
  { name: "жилая зона", idx: "200", fill: "#f3d357", a: 5 }], ["жилая зона"]);
eq(LR.length, 2, "два знака — две строки"); eq(LR[0].name, "жилая зона", "порядок образца"); eq(LR[1].name, "коммунальные зоны", "название — зона территории");
eq(LR[1].idx.join(), "130", "индекс один");
eq(G.legendRows([{ name: "А зона", idx: "130", fill: "#1", a: 1 }, { name: "Б зона", idx: "130", fill: "#1", a: 9 }])[0].name, "Б зона", "без территории — самая большая");
eq(G.legendRows([{ name: "", fill: "#1" }, null].filter(Boolean)).length, 0, "без названия — нет строки");
eq(G.legendRows([{ name: "X", fill: undefined, a: 1 }, { name: "x", fill: undefined, a: 1 }]).length, 1, "без цвета — по названию");
console.log(n + " checks ok");
