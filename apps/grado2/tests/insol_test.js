// Проверка расчёта инсоляции (node apps/grado2/tests/insol_test.js). Сверка с пособием МАрхИ (Поповский, 2018) для 55° с. ш.
const assert = require("assert");
const I = require("../web/insol.js");
const LAT = 55.75, RAD = Math.PI / 180;
const ok = (c, m) => { assert.ok(c, m); console.log("ok -", m); };

// 1. Расчётное окно 22.04 и 22.08: 6:00–18:00, как на инсографике МАрхИ (час после восхода и час до захода не считаются)
for (const d of I.DATES) { const p = I.sunPath(LAT, d.day, 5); ok(p.start === 6 && p.end === 18, `${d.name}: окно ${p.start}–${p.end}`); }

// 2. Склонение 22 апреля ≈ +12°, высота солнца в полдень = 90 − φ + δ ≈ 46°; тень 10-метрового столба ≈ 9,6 м
const p0 = I.sunPath(LAT, 112, 5), noon = p0.sun.find(s => s.t === 12);
ok(Math.abs(p0.decl / RAD - 11.9) < 0.3, `склонение 22.04 = ${(p0.decl / RAD).toFixed(2)}°`);
ok(Math.abs(noon.alt / RAD - (90 - LAT + p0.decl / RAD)) < 1e-6 && Math.abs(noon.az / RAD - 180) < 1e-6, `полдень: высота ${(noon.alt / RAD).toFixed(1)}°, азимут 180°`);
ok(Math.abs(10 / noon.tan - 9.6) < 0.2, `тень 10 м столба в полдень ${(10 / noon.tan).toFixed(2)} м`);
// восход на 55° (δ≈12°) около 4:50 — окно 6:00 = восход + ~1 ч, округлено до получаса
const h0 = Math.acos(-Math.tan(LAT * RAD) * Math.tan(p0.decl)) / RAD / 15;
ok(Math.abs(12 - h0 - 4.8) < 0.1, `восход ${(12 - h0).toFixed(2)} ч солнечного времени`);

// 3. Фасады без препятствий: восточный — с 6:00 до полудня (≈6 ч), южный — симметрично полудню
const none = I.obstacleIndex([]);
const run = (nx, ny, obs = none, z = 2) => { const pts = [{ x: 0, y: 0, z, nx, ny }]; I.evalFront(pts, obs, [p0], { norm: 120 }); return I.periods(pts[0].flags[0], p0); };
const east = run(1, 0); ok(east.length === 1 && east[0].from === 6 && east[0].min >= 350 && east[0].min <= 360, `восточный фасад: ${east[0].from}–${east[0].to}, ${east[0].min} мин`);
const south = run(0, -1); ok(Math.abs((south[0].from + south[0].to) / 2 - 12) < 1e-9, `южный фасад: ${south[0].from.toFixed(2)}–${south[0].to.toFixed(2)}, симметрично полудню`);
const north = run(0, 1); ok(north.length === 2 && north.every(r => r.from < 8.5 || r.to > 15.5), `северный фасад — утро и вечер: ${north.map(r => r.from + "–" + r.to).join(", ")}`);

// 4. Стена к югу: длинная (E–W), высота H на расстоянии D. Точка затенена, пока tg(высоты) < (H − z)·cos(азимут − 180°) / D
const H = 30, D = 20, z = 2, wall = I.obstacleIndex([{ ring: [[-500, -D - 10], [500, -D - 10], [500, -D], [-500, -D]], h: H }]);
const pts = [{ x: 0, y: 0, z, nx: 0, ny: -1 }]; I.evalFront(pts, wall, [p0], { norm: 120 });
const expect = p0.sun.map(s => s.vy < 0 && s.tan >= (H - z) * Math.cos(s.az - Math.PI) / D);
ok(pts[0].flags[0].every((f, i) => f === expect[i]), `стена ${H} м в ${D} м к югу: освещённость совпадает с формулой во всех ${p0.sun.length} отсчётах`);

// 5. Норма: непрерывно 2 ч или прерывисто 2,5 ч с периодом не короче 1 ч
ok(I.verdict([{ min: 120 }], 120).ok === "непрерывная", "120 мин подряд — норма");
ok(I.verdict([{ min: 90 }, { min: 60 }], 120).ok === "прерывистая", "90 + 60 мин — прерывистая норма");
ok(I.verdict([{ min: 70 }, { min: 70 }], 120).ok === "", "70 + 70 мин — не норма (прерывисто нужно 150)");
ok(I.verdict([{ min: 100 }, { min: 55 }], 120).ok === "прерывистая", "100 + 55 мин — прерывистая норма");
ok(I.verdict([{ min: 50 }, { min: 50 }, { min: 55 }], 120).ok === "", "три периода короче часа — не норма");

// 6. Солнечный потолок: любая застройка ниже потолка сохраняет норму у всех точек, которые её выполняли
const existing = [{ ring: [[0, 0], [60, 0], [60, 14], [0, 14]], h: 27 }, { ring: [[80, -10], [94, -10], [94, 50], [80, 50]], h: 45 }];
const ob = I.obstacleIndex(existing), front = I.frontPoints(existing, 4, 2), paths = I.DATES.map(d => I.sunPath(LAT, d.day, 5));
I.evalFront(front, ob, paths, { norm: 120 });
const before = front.map(p => !p.orient && !!p.worst.ok);
ok(front.some(p => p.orient) && front.filter(p => p.orient).every(p => p.ny > 0.3 || Math.abs(p.nx) < 0.99), `северные фасады (${front.filter(p => p.orient).length} точек) отмечены как не нормируемые`);
const grid = { x0: -40, y0: -120, cell: 5, nx: 36, ny: 22 }; grid.inside = new Uint8Array(grid.nx * grid.ny).fill(1);
const { env } = I.envelope(front, paths, grid, { norm: 120, cap: 150 });
let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
for (let trial = 0; trial < 6; trial++) {
  const add = [];
  for (let k = 0; k < 14; k++) {                        // случайные корпуса ровно под потолком (верх = минимум потолка по пятну)
    const i = Math.floor(rnd() * (grid.nx - 3)), j = Math.floor(rnd() * (grid.ny - 3)), w = 1 + Math.floor(rnd() * 3), h = 1 + Math.floor(rnd() * 3);
    let top = Infinity; for (let a = i; a < i + w; a++) for (let b = j; b < j + h; b++) top = Math.min(top, env[b * grid.nx + a]);
    const x = grid.x0 + i * grid.cell, y = grid.y0 + j * grid.cell;
    if (top > 0.5) add.push({ ring: [[x, y], [x + w * grid.cell, y], [x + w * grid.cell, y + h * grid.cell], [x, y + h * grid.cell]], h: top - 1e-6 });
  }
  const pts2 = front.map(p => ({ ...p })); I.evalFront(pts2, I.obstacleIndex(existing.concat(add)), paths, { norm: 120 });
  const lost = pts2.filter((p, n) => before[n] && !p.worst.ok).length;   // до застройки выполняли — и после выполняют
  ok(lost === 0, `проба ${trial + 1}: ${add.length} корпусов под потолком — норму не потерял ни один из ${before.filter(Boolean).length} фасадов`);
}
// и наоборот: корпус выше потолка там, где потолок низкий, норму ломает
let low = 0; for (let n = 1; n < env.length; n++) if (env[n] < env[low]) low = n;
const li = low % grid.nx, lj = Math.floor(low / grid.nx), lx = grid.x0 + li * grid.cell, ly = grid.y0 + lj * grid.cell;
const tall = { ring: [[lx - 10, ly - 10], [lx + 15, ly - 10], [lx + 15, ly + 15], [lx - 10, ly + 15]], h: 120 };
const pts3 = front.map(p => ({ ...p })); I.evalFront(pts3, I.obstacleIndex(existing.concat([tall])), paths, { norm: 120 });
ok(pts3.some((p, n) => before[n] && !p.worst.ok), `корпус 120 м в клетке с потолком ${env[low].toFixed(1)} м нарушает норму соседей`);
// 7. Дом-колодец: точки на фасадах двора смотрят во двор, стены двора затеняют их
const yardHouse = { ring: [[0, 0], [60, 0], [60, 60], [0, 60]], holes: [[[20, 20], [20, 40], [40, 40], [40, 20]]], h: 30 };
const yp = I.frontPoints([yardHouse], 5, 2).filter(p => p.yard);
ok(yp.length === 16 && yp.every(p => { const cx = p.x - 30, cy = p.y - 30; return p.nx * cx + p.ny * cy < 0; }), `двор: ${yp.length} точек, все смотрят внутрь двора`);
I.evalFront(yp, I.obstacleIndex([yardHouse]), paths, { norm: 120 });
ok(yp.every(p => !p.worst.ok), "двор 20×20 м при высоте 30 м — норма во дворе не выполняется (затеняют свои стены)");
// рельеф: дом на земле 10 м — окна на 10 + z, а стена 30 м на земле 0 затеняет его меньше, чем такой же дом на земле 0
{ const low = { ring: [[0, -30], [40, -30], [40, -20], [0, -20]], h: 30, g: 0 }, sq = g => ({ ring: [[0, 0], [40, 0], [40, 10], [0, 10]], h: g + 15, g });
  const pa = I.DATES.map(d => I.sunPath(55.75, d.day, 5));
  const on = g => { const b = sq(g), pts = I.frontPoints([b], 4, 2).filter(p => p.ny < -0.9); I.evalFront(pts, I.obstacleIndex([low, b]), pa, { norm: 120 }); return pts; };
  const p0 = on(0), p10 = on(10);
  ok(p10.every(p => Math.abs(p.z - 12) < 1e-9) && p0.every(p => p.z === 2), "окно встаёт на свою землю: z = g + 2");
  ok(p10.reduce((s, p) => s + p.worst.cont, 0) > p0.reduce((s, p) => s + p.worst.cont, 0), "дом выше на склоне получает больше солнца за той же стеной"); }
console.log("все проверки пройдены");
