// snap.js: привязка надписи в макете листа (запуск — tests/test_snap_js.py). Перенос из DesignCraft, 06.10.2026.
const assert = require("assert"), path = require("path");
const S = require(path.join(__dirname, "../web/snap.js"));
let n = 0; const ok = (c, msg) => { assert.ok(c, "FAIL: " + msg); n++; };
const R = (x0, y0, x1, y1) => ({ x0, y0, x1, y1 });
const near = (a, b) => Math.abs(a - b) < 1e-9;
const page = R(0, 0, 420, 297);

let s = S.snap(R(10.8, 50, 30.8, 55), [R(10, 100, 40, 104)], 1);
ok(near(s.dx, -.8) && s.dy === 0 && s.guides.length === 1, "левый край встаёт к левому краю другой надписи, по y привязки нет");
ok(near(s.guides[0].a[0], 10) && near(s.guides[0].b[0], 10) && near(s.guides[0].a[1], 44) && near(s.guides[0].b[1], 110), "направляющая по x = 10 от верха до низа обеих рамок с выпуском 6 мм");
s = S.snap(R(10.8, 50, 30.8, 55), [R(10, 100, 40, 104)], .5);
ok(s.dx === 0 && s.guides.length === 0, "дальше зоны — без привязки и без направляющей");
s = S.snap(R(199.5, 143, 221.5, 153.6), [page], 1);
ok(near(s.dx, -.5) && near(s.dy, .2) && s.guides.length === 2, "середина надписи к середине листа по обеим осям, две направляющие");
s = S.snap(R(40.6, 0, 60, 5), [R(0, 20, 40, 25), R(40.3, 30, 50, 35)], 1);
ok(near(s.dx, -.3), "выигрывает ближайшая цель: край 40.3, а не 40");
s = S.snap(R(5, 5, 9, 9), [R(9.4, 30, 20, 40)], 1);
ok(near(s.dx, .4), "правый край к левому краю соседа (встык)");
s = S.snap(R(5, 5, 9, 9), [R(NaN, 0, 1, 1), null], 1);
ok(s.dx === 0 && s.dy === 0 && !s.guides.length, "негодные цели пропускаются");
ok(S.snap(R(0, 0, 1, 1), [page], 0).guides.length === 0 && S.snap(R(0, 0, 1, 1), [page], Infinity).dx === 0, "зона 0 или бесконечная — привязки нет");
ok(S.snap(R(0, NaN, 1, 1), [page], 1).dx === 0, "негодная рамка — привязки нет");
ok(S.ZONE_PX === 4, "зона привязки 4 пикселя, как в DesignCraft");
console.log(n + " checks ok");
