/* Проверяет рамку вида (viewframes.js, #119): пропорции, рамка по двум углам, масштаб блока «Вписать» и «Заполнить»,
   высота блока по рамке, подпись, рамка под заданный масштаб. Запуск: cd apps/grado2/ui && npm test. */
import test from "node:test";
import assert from "node:assert/strict";
import { ratioOf, withRatio, fromCorners, cornersM, blockScale, blockFromView, blockHeightFor, frameLabel, frameForScale } from "./viewframes.js";

const near = (a, b, e = 1e-6) => assert.ok(Math.abs(a - b) < e, `${a} ≈ ${b}`);

test("пропорции: из списка, свои «3:2» и «5,5:2», свободно — нет", () => {
  near(ratioOf("a"), Math.SQRT2); near(ratioOf("16:9"), 16 / 9);
  near(ratioOf("3:2"), 1.5); near(ratioOf("2:3"), 1.5); near(ratioOf("5,5:2"), 2.75);
  assert.equal(ratioOf("free"), null); assert.equal(ratioOf("абв"), null); assert.equal(ratioOf("0:2"), null);
  assert.deepEqual(withRatio(400, 100, 2), [400, 200]);
  assert.deepEqual(withRatio(100, 400, 2), [200, 400]);
  assert.deepEqual(withRatio(300, 100, null), [300, 100]);
});

test("рамка по двум углам: свободно — как протянули, с пропорциями — охватывает протянутое", () => {
  const f = fromCorners([0, 0], [400, -300], null);
  assert.deepEqual(f, { c: [200, -150], w: 400, h: 300 });
  const g = fromCorners([0, 0], [400, 100], 2);                       // лёжа: высота дотянута до 200
  near(g.w, 400); near(g.h, 200); assert.deepEqual(g.c, [200, 100]);
  const h = fromCorners([0, 0], [-100, 400], 4 / 3);                  // стоя: ширина 300
  near(h.w, 300); near(h.h, 400); assert.deepEqual(h.c, [-150, 200]);
  assert.deepEqual(cornersM([0, 0], 4, 2), [[-2, -1], [2, -1], [2, 1], [-2, 1]]);
});

test("масштаб блока по рамке: вписать — мельче, заполнить — крупнее, круглый по списку", () => {
  const b = { w: 275, h: 224 }, fr = { w: 800, h: 500 };
  assert.equal(blockScale(b, fr, { fit: "fit", round: false }), 2909);   // 800 м в 275 мм
  assert.equal(blockScale(b, fr, { fit: "fit" }), 3000);
  assert.equal(blockScale(b, fr, { fit: "fill", round: false }), 2232); // 500 м в 224 мм
  assert.equal(blockScale(b, fr, { fit: "fill" }), 2000);
  assert.equal(blockScale({ w: 100, h: 100 }, { w: 200, h: 200 }), 2000);  // ровно 1:2000 не превращается в 1:2500
  assert.equal(blockScale({ w: 0, h: 1 }, fr), 0);
  const v = { frame: { center: [37.5, 55.75], w: 800, h: 500 } };
  assert.deepEqual(blockFromView({ ...b }, v), { center: [37.5, 55.75], scale: 3000 });
  assert.deepEqual(blockFromView({ ...b, fit: "fill", round: false }, v).scale, 2232);
  assert.equal(blockFromView(b, { layers: [] }), null);
  assert.equal(blockHeightFor({ w: 275, h: 224 }, fr), 171.88);
});

test("подпись рамки: метры с пробелами, от 10 км — километры", () => {
  assert.equal(frameLabel("Ограничения", { w: 820.4, h: 1580 }), "Ограничения · 820 × 1 580 м");
  assert.equal(frameLabel("Округ", { w: 12340, h: 8700 }), "Округ · 12,3 × 8,7 км");
});

test("рамка под масштаб: блок 300 × 200 мм при 1:2 000 — рамка 600 × 400 м, масштаб ровно 1:2 000 и при «Заполнить»", () => {
  const b = { w: 300, h: 200 }, f = frameForScale(b, { center: [37.6, 55.7], w: 820, h: 300, aspect: "a" }, 2000);
  assert.deepEqual(f, { center: [37.6, 55.7], w: 600, h: 400, aspect: "300:200" });
  assert.equal(blockScale(b, f), 2000); assert.equal(blockScale(b, f, { fit: "fill" }), 2000);
  assert.equal(blockScale(b, frameForScale(b, f, 1730), { round: false }), 1730);
  near(ratioOf(frameForScale({ w: 180.5, h: 120 }, f, 1000).aspect), 180.5 / 120);
  assert.equal(frameForScale({ w: 0, h: 10 }, f, 1000), f);
});
