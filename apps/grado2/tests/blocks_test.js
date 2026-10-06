// Проверка blocks.js (node apps/grado2/tests/blocks_test.js): урбан-блок не оставляет секций с фасадами ниже 50 % нормы инсоляции (T56).
const assert = require("assert");
const B = require("../web/blocks.js");
const ok = (c, m) => { assert.ok(c, m); console.log("ok -", m); };
const LAT = 55.75, O = { lat: LAT, floorH: 3, norm: 120, z: 2, reveal: 0 };
const R = (x0, y0, x1, y1, floors) => ({ ring: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], floors });
// замкнутый квартал: два крыла 100 × 16 м (юг и север), двор 30 м, торцы 16 м; везде 12 этажей по 3 м
const mk = () => { const W = 100, d = 16, g = 30; return [R(0, 0, W, d, 12), R(0, d + g, W, 2 * d + g, 12), R(0, d, d, d + g, 12), R(W - d, d, W, d + g, 12)]; };
const bad = (S, sh) => S.map((s, i) => [s, sh[i]]).filter(([s, v]) => v != null && v < .5).length;
const gfa = S => S.reduce((t, s) => t + (s.ring[2][0] - s.ring[0][0]) * (s.ring[2][1] - s.ring[0][1]) * s.floors, 0);

const S = mk(), sh0 = B.shares(S, O);
ok(sh0[1] < .5 && bad(S, sh0) === 1, `до правки северное крыло получает норму на ${Math.round(sh0[1] * 100)} % фасада (< 50 %), секций ниже нормы: ${bad(S, sh0)}`);
const g0 = gfa(S), rep = B.relax(S, O), sh1 = B.shares(S.filter(s => s.floors > 0), O);
ok(rep.failBefore === 1 && rep.failAfter === 0 && bad(S, sh1) === 0, `после правки секций ниже нормы: ${rep.failAfter}, северное крыло ${Math.round(sh1[1] * 100)} %`);
ok(S[0].floors < 12 && S[0].floors >= 2 && S[1].floors === 12 && rep.dropped.length === 0, `понижено южное крыло (${S[0].floors} эт.), северное и торцы без изменений, квартал не открыт`);
ok(gfa(S) / g0 >= .95, `площадь этажей квартала ${(100 * gfa(S) / g0).toFixed(1)} % от исходной (потеря не более 5 %)`);
// квартал, который и так проходит, не трогается
const S2 = [R(0, 0, 100, 16, 12), R(0, 70, 100, 86, 12)], r2 = B.relax(S2, O);
ok(r2.failBefore === 0 && r2.lowered === 0 && S2.every(s => s.floors === 12), "два крыла с двором 54 м проходят норму — этажность не меняется");
// двор 20 м при 24 этажах: понижения хватает или секции снимаются, но ниже нормы не остаётся ничего
const S3 = [R(0, 0, 100, 16, 24), R(0, 36, 100, 52, 24), R(0, 16, 16, 36, 24), R(84, 16, 100, 36, 24)], r3 = B.relax(S3, O);
ok(bad(S3.filter(s => s.floors > 0), B.shares(S3.filter(s => s.floors > 0), O)) === 0, `двор 20 м, 24 этажа: после правки секций ниже нормы нет (понижено ${r3.lowered}, снято ${r3.dropped.length})`);
// T12: переключатель — выключен (или не задан) этажность не трогается, включён — работает как relax
const S4 = mk(), r4 = B.relaxIf(S4, { ...O }), r4b = B.relaxIf(S4, { ...O, on: false });
ok(r4.off && r4b.off && S4.every(s => s.floors === 12), "relaxIf без on / с on:false — этажность секций не меняется");
const S5 = mk(), r5 = B.relaxIf(S5, { ...O, on: true });
ok(!r5.off && r5.failBefore === 1 && S5[0].floors < 12, `relaxIf с on:true — понижено южное крыло (${S5[0].floors} эт.)`);
console.log("все проверки пройдены");
