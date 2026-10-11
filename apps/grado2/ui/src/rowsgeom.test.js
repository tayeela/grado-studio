/* ГРАДО 2 · проверка геометрии рядов «по границе» (rowsgeom.js): хорды повторяют контур с допуском, прямоугольник даёт
   4 стороны, дуга — ломаную; расстояние между корпусами.
   Запуск: node --test src/rowsgeom.test.js (из apps/grado2/ui) или tests/test_rowsgeom_js.py. */
import test from "node:test";
import assert from "node:assert/strict";
import { chords, gapXY } from "./rowsgeom.js";

test("прямоугольник — четыре хорды по сторонам", () => {
  const r = [[0, 0], [50, 0], [100, 0], [100, 60], [0, 60]];
  const c = chords(r, 2);
  assert.equal(c.length, 4);
  const len = c.map(([a, b]) => Math.round(Math.hypot(b[0] - a[0], b[1] - a[1]))).sort((x, y) => x - y);
  assert.deepEqual(len, [60, 60, 100, 100]);
});

test("дуга — ломаная из нескольких хорд, каждая не дальше допуска от дуги", () => {
  const R = 200, arc = Array.from({ length: 61 }, (_, i) => { const t = Math.PI * i / 60; return [R * Math.cos(t), R * Math.sin(t)]; });
  const c = chords(arc, 2);
  assert.ok(c.length >= 6 && c.length <= 30, "хорд " + c.length);
  for (const [a, b] of c) { const m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]; const sag = R - Math.hypot(...m);
    if (Math.hypot(b[0] - a[0], b[1] - a[1]) < R && Math.hypot(...a) > R - 1 && Math.hypot(...b) > R - 1) assert.ok(sag <= 2.01, "прогиб " + sag); }   // замыкающая хорда — диаметр, не дуга
});

test("расстояние между корпусами", () => {
  const sq = (x, y, s = 10) => [[x, y], [x + s, y], [x + s, y + s], [x, y + s]];
  assert.equal(gapXY(sq(0, 0), sq(5, 5)), 0);
  assert.equal(Math.round(gapXY(sq(0, 0), sq(22, 0))), 12);
  assert.equal(Math.round(gapXY(sq(0, 0), sq(13, 14)) * 10) / 10, 5);
});
