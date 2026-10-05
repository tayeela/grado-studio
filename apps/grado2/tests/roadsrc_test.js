// roadsrc.js: выбор источника дорог листа (запуск — tests/test_roadsrc_js.py).
const assert = require("assert");
const { pickRoadSource: P } = require("../web/roadsrc.js");
let n = 0; const eq = (a, b, msg) => { assert.strictEqual(a, b, "FAIL: " + msg); n++; };
eq(P({ ya: 1000, uds: 1000, egko: 800 }), "yandex", "Москва: Яндекс покрывает всё");
eq(P({ ya: 1000, uds: 1200 }), "yandex", "Яндекс ≥ 20 % УДС");
eq(P({ ya: 1000, uds: 5000 }), "yandex", "ровно 20 % — ещё Яндекс");
eq(P({ ya: 900, uds: 5000, egko: 3000 }), "egko", "мало полигонов Яндекса, есть ЕГКО");
eq(P({ ya: 900, uds: 5000 }), "uds", "мало полигонов Яндекса, ЕГКО нет — оси");
eq(P({ ya: 0, uds: 4000, egko: 2000 }), "egko", "Безобразово: полигонов Яндекса нет, есть ЕГКО");
eq(P({ ya: 0, uds: 4000 }), "uds", "полигонов нет, ЕГКО нет — оси");
eq(P({ ya: 0, uds: 0, egko: 100 }), "egko", "только ЕГКО");
eq(P({ ya: 500 }), "yandex", "оси не загружены — остаётся Яндекс");
eq(P({}), "none", "дорог нет нигде");
eq(P({ ya: 0, uds: 0, egko: 0 }), "none", "нули");
eq(P({ ya: 100, uds: 1000, egko: 0 }, .5), "uds", "порог задаётся");
console.log(n + " checks ok");
