// roadclean.js: чистка полигонов дорог листа (запуск — tests/test_roadsrc_js.py). T84, 06.10.2026.
const assert = require("assert"), path = require("path");
const W = path.join(__dirname, "../web/");
const turf = require(W + "vendor/turf.min.js"), R = require(W + "roadclean.js");
let n = 0; const ok = (c, msg) => { assert.ok(c, "FAIL: " + msg); n++; };
const lat0 = 55.7, lon0 = 37.6, mx = 111320 * Math.cos(lat0 * Math.PI / 180), my = 111320;
const ll = ([x, y]) => [lon0 + x / mx, lat0 + y / my];                       // метры от начала → градусы
const rect = (x0, y0, x1, y1) => ({ type: "Polygon", coordinates: [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]].map(ll)] });
const A = g => turf.area({ type: "Feature", geometry: g, properties: {} });
const BB = [lon0 - 10 / mx, lat0 - 10 / my, lon0 + 300 / mx, lat0 + 300 / my];
const sq = (x, y, s) => rect(x, y, x + s, y + s)

// фильтры: обрывки < 10 м² и дыры < 25 м²
let g = R.filterParts({ type: "MultiPolygon", coordinates: [rect(0, 0, 20, 20).coordinates, rect(50, 0, 52, 3).coordinates] });   // 400 и 6 м²
ok(g.type === "Polygon" && A(g) > 390, "обрывок 6 м² убран, крупный остался (Polygon)");
const holed = { type: "Polygon", coordinates: [rect(0, 0, 40, 40).coordinates[0], sq(5, 5, 4).coordinates[0], sq(20, 20, 8).coordinates[0]] };   // дыры 16 и 64 м²
g = R.filterParts(holed); ok(g.coordinates.length === 2, "дыра 16 м² закрыта, дыра 64 м² осталась");
ok(R.filterParts(rect(0, 0, 2, 2)) === null, "всё меньше порога — null");
ok(R.filterParts(null) === null && R.filterParts({ type: "Point", coordinates: [0, 0] }) === null, "не полигон — null");
ok(R.filterParts(sq(0, 0, 3), 5) !== null && R.filterParts(sq(0, 0, 3), 10) === null, "порог задаётся (9 м²)");

// плитки: каждый кусок ровно в одной плитке, пустые плитки пропущены
const boxes = [[0, 0, 1, 1], [0.1, 0.1, 0.2, 0.2], [9, 9, 10, 10], [-5, -5, -4, -4], [99, 99, 100, 100]];
const t = R.tiles(boxes, [0, 0, 10, 10], 2), flat = t.flat().sort();
ok(flat.join() === "0,1,2,3,4" && t.length === 2, "плитки: все куски по разу, кроме дальних — в край, 2 плитки");

// слияние: нахлёст + волосяная щель 0.2 м → одна фигура без швов
const pieces = [rect(0, 0, 100, 8), rect(100.2, 0, 200, 8), rect(50, -30, 58, 30), rect(150, 3, 158, 60)];
const c = R.clean(turf, pieces, BB);
ok(c && c.type === "Polygon" && c.coordinates.length === 1, "куски и щель 0.2 м слиты в один полигон без дыр");
ok(A(c) > 2300 && A(c) < 2500, "площадь сохранена: " + Math.round(A(c)) + " м²");
// островок < 25 м² внутри проезжей части закрыт, большой — остаётся
const ring = [rect(0, 0, 100, 10), rect(0, 40, 100, 50), rect(0, 10, 10, 40), rect(90, 10, 100, 40)];
const isl = R.clean(turf, ring, BB);
ok(isl.coordinates.length === 2, "кольцо дорог: дыра-двор (80×30) осталась");
const isl2 = R.clean(turf, [{ type: "Polygon", coordinates: [rect(0, 0, 60, 60).coordinates[0], sq(25, 25, 4).coordinates[0]] }], BB);
ok(isl2.type === "Polygon" && isl2.coordinates.length === 1, "островок 16 м² внутри проезжей части закрыт");
// мелкий обрывок отдельно — убран
const frag = R.clean(turf, [rect(0, 0, 100, 8), rect(200, 200, 202, 204)], BB);
ok(frag.type === "Polygon", "отдельный обрывок 8 м² убран");
// вне рамки + 5 % — отсекается; пересечение рамки — обрезается
ok(R.clean(turf, [rect(5000, 5000, 5100, 5100)], BB) === null, "дорога далеко за рамкой — ничего");
const cut = R.clean(turf, [rect(-2000, 0, 2000, 8)], BB), cb = turf.bbox({ type: "Feature", geometry: cut, properties: {} });
ok(cb[0] >= BB[0] - (BB[2] - BB[0]) * .051 && cb[2] <= BB[2] + (BB[2] - BB[0]) * .051, "длинная дорога обрезана рамкой с запасом 5 %");
ok(R.clean(turf, [], BB) === null, "пусто — null");

// скорость на синтетике: ТиНАО (48 га, 290 кусков) и плотная Москва 1:1000 (3000 кусков)
function strip(x0, y0, x1, y1, w) { const dx = x1 - x0, dy = y1 - y0, L = Math.hypot(dx, dy), nx = -dy / L * w / 2, ny = dx / L * w / 2;
  return { type: "Polygon", coordinates: [[[x0 + nx, y0 + ny], [x1 + nx, y1 + ny], [x1 - nx, y1 - ny], [x0 - nx, y0 - ny], [x0 + nx, y0 + ny]].map(ll)] }; }
function grid(size, step, seg) { const r = []; for (let k = 0; k <= size; k += step) for (let s = 0; s < size; s += seg) { r.push(strip(k, s, k, s + seg + 1, 7)); r.push(strip(s, k, s + seg + 1, k, 7)); } return r; }
for (const [name, size, step, seg, limit] of [["ТиНАО 48 га", 700, 100, 40, 3000], ["плотная Москва", 1200, 40, 25, 6000]]) {
  const gs = grid(size, step, seg), bb = [lon0 - 5 / mx, lat0 - 5 / my, lon0 + (size + 5) / mx, lat0 + (size + 5) / my], t0 = Date.now();
  const r = R.clean(turf, gs, bb), ms = Date.now() - t0;
  ok(r && r.type === "Polygon", name + ": " + gs.length + " кусков слиты в один полигон");
  ok(ms < limit, name + ": " + ms + " мс (< " + limit + ")");
  console.log("  " + name + ": " + gs.length + " кусков → " + ms + " мс");
}
console.log(n + " checks ok");
