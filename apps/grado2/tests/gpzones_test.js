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
console.log(n + " checks ok");
