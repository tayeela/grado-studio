// albumgeo.js: кэш okrugMain по геометрии и углы листа по рамке в МСК (запуск — tests/test_albumgeo_js.py). T10/T11, 06.10.2026.
const assert = require("assert");
const G = require("../web/albumgeo.js"), MSK = require("../web/msk.js");
let n = 0; const eq = (a, b, msg) => { assert.deepStrictEqual(a, b, "FAIL: " + msg); n++; }, ok = (c, msg) => { assert.ok(c, "FAIL: " + msg); n++; };
// кэш: один расчёт на объект, ревизию и параметры
let calls = 0; const memo = G.memoByGeometry((f, km) => { calls++; return { km, f }; });
const okrug = { geometry: { type: "MultiPolygon", coordinates: [] } }, other = { geometry: { type: "MultiPolygon", coordinates: [] } };
const a = memo(okrug, 1, 3);
eq(calls, 1, "первый вызов считает");
ok(memo(okrug, 1, 3) === a && memo(okrug, 1, 3) === a, "повтор — тот же результат из кэша");
eq(calls, 1, "повторы не считают");
memo(okrug, 1, 5); eq(calls, 2, "другой km — новый расчёт");
memo(okrug, 2, 3); eq(calls, 3, "новая ревизия границы — новый расчёт");
memo(other, 1, 3); eq(calls, 4, "другой округ — свой расчёт");
memo(other, 1, 3); eq(memo.misses, 4, "счётчик промахов");
const nogeo = { id: 1 }; memo(nogeo, 1, 3); memo(nogeo, 1, 3); eq(calls, 6, "без геометрии не кэшируется, не падает");
// углы листа: рамка 279 × 239 мм, масштаб 2000 → 558 × 478 м в МСК
const c = [37.7, 55.78], rect = [7, 44, 279, 239], sc = 2000, fr = .03;
const { tl, br } = G.cornerPoints(c, rect, sc, MSK, fr), cm = MSK.fromWgs(c), w = 279 * 2, h = 239 * 2;
const tlM = MSK.fromWgs(tl), brM = MSK.fromWgs(br);
const near = (x, y, tol, msg) => ok(Math.abs(x - y) < tol, `${msg}: ${x} ≠ ${y}`);
near(tlM[0], cm[0] - w / 2 + fr * w, 1e-3, "левый верхний: x в МСК"); near(tlM[1], cm[1] + h / 2 - fr * h, 1e-3, "левый верхний: y в МСК");
near(brM[0], cm[0] + w / 2 - fr * w, 1e-3, "правый нижний: x в МСК"); near(brM[1], cm[1] - h / 2 + fr * h, 1e-3, "правый нижний: y в МСК");
// такой угол в градусах (прежний способ — по рамке в градусах) лежит в другом месте: МСК повёрнута относительно меридианов
const dLon = (w / 2) / (111320 * Math.cos(c[1] * Math.PI / 180)), dLat = (h / 2) / 111320;
const oldTl = [c[0] - dLon + 2 * fr * dLon, c[1] + dLat - 2 * fr * dLat], oldM = MSK.fromWgs(oldTl);
ok(Math.hypot(oldM[0] - tlM[0], oldM[1] - tlM[1]) > 0.5, "в МСК угол отличается от угла рамки в градусах");
eq(G.cornerPoints(c, rect, sc, MSK).tl, tl, "функция чистая");
console.log(n + " checks ok");
