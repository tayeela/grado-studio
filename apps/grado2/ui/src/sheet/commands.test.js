/* Проверяет команды редактора листа (commands.js) и перенесённое с deckcraft (arrange.js): разбор командной строки,
   группы, отражение, точная правка, «Формат по образцу». Запуск: cd apps/grado2/ui && npm test. */
import test from "node:test";
import assert from "node:assert/strict";
import { COMMANDS, parse, titleOf } from "./commands.js";
import { withGroups, group, ungroup, regroup, flip, moveBy, moveTo, sizeTo, rotateBy, styleOf, paint, turnedBounds } from "./arrange.js";
import { newBlock, duplicate } from "./model.js";

const SH = { format: "A3", orient: "L", blocks: [] };
const box = (id, x, y, w, h, extra = {}) => ({ id, kind: "rect", x, y, w, h, ...extra });
const apply = (bs, m) => bs.map(b => ({ ...b, ...(m[b.id] || {}) }));

test("командная строка: русские и deckcraft-имена, уточнения, числа", () => {
  assert.equal(parse("выровнять влево").id, "align:left");
  assert.equal(parse("arrange.align right").id, "align:right");
  assert.equal(parse("ВЫР середина").id, "align:vcenter");
  assert.deepEqual(parse("сдвиг 10 -2,5").args, [10, -2.5]);
  assert.deepEqual(parse("масштаб 1:2000").args, [2000]);
  assert.equal(parse("отразить гор").id, "flip:h");
  assert.equal(parse("группа").id, "group");
  assert.equal(parse("ВСЁ").id, "all");
  assert.equal(parse("показать всё").id, "zoom:fit");
  assert.match(parse("выровнять").error, /ВЛЕВО/);
  assert.match(parse("сдвиг 10").error, /dx dy/);
  assert.match(parse("абв").error, /Нет команды/);
  assert.equal(parse("  ").error, "");
  // у каждой команды своё имя, русские имена не повторяются
  const names = COMMANDS.flatMap(c => [c.name, ...c.ru].map(n => n.toUpperCase().replace(/Ё/g, "Е")));
  assert.equal(new Set(names).size, names.length);
  assert.equal(titleOf("flip:v"), "Отразить");
});

test("группы: щелчок берёт всю группу, разгруппировать и собрать снова, копия — своя группа", () => {
  let bs = [box("a", 0, 0, 10, 10), box("b", 20, 0, 10, 10), box("c", 40, 0, 10, 10)];
  assert.deepEqual(group([bs[0]]), {});
  bs = apply(bs, group([bs[0], bs[1]]));
  assert.ok(bs[0].group && bs[0].group === bs[1].group && !bs[2].group);
  assert.deepEqual(withGroups(bs, ["a"]), ["a", "b"]);
  assert.deepEqual(withGroups(bs, ["c"]), ["c"]);
  const g = bs[0].group;
  bs = apply(bs, ungroup(bs.slice(0, 2)));
  assert.equal(bs[0].group, undefined); assert.equal(bs[0].was, g);
  bs = apply(bs, regroup(bs, [bs[1]]));
  assert.equal(bs[0].group, g); assert.equal(bs[1].group, g);
  const cp = duplicate(bs.slice(0, 2));
  assert.ok(cp[0].group && cp[0].group === cp[1].group && cp[0].group !== g);
  assert.equal(duplicate([bs[2]])[0].group, undefined);
});

test("отражение: места по общей рамке, углы, стрелка линии разворачивается", () => {
  const bs = [box("a", 0, 0, 10, 10), box("b", 30, 0, 10, 20)];
  const m = flip(bs, "h");
  assert.deepEqual([m.a.x, m.a.y], [30, 0]); assert.deepEqual([m.b.x, m.b.y], [0, 0]);
  const v = flip(bs, "v");
  assert.deepEqual([v.a.x, v.a.y], [0, 10]); assert.deepEqual([v.b.x, v.b.y], [30, 0]);
  // линия слева направо после отражения смотрит справа налево: поворот 180, середина на месте
  const ln = { id: "l", kind: "line", x: 10, y: 10, w: 40, h: 4 }, f = flip([ln], "h").l;
  assert.equal(f.rotation, 180); assert.deepEqual([f.x, f.y], [50, 14]);
  // повёрнутая фигура: угол отражается, рамка с поворотом та же
  const r = box("r", 0, 0, 20, 10, { rotation: 30 }), fr = flip([r], "h").r;
  assert.equal(fr.rotation, -30);
  const a = turnedBounds([r]), b = turnedBounds([{ ...r, ...fr }]);
  ["x", "y", "w", "h"].forEach(k => assert.ok(Math.abs(a[k] - b[k]) < .02, k));
  // дважды — как было
  const twice = apply(apply([r], flip([r], "v")), flip(apply([r], flip([r], "v")), "v"))[0];
  assert.ok(Math.abs(twice.x - r.x) < .02 && Math.abs(twice.y - r.y) < .02 && twice.rotation === 30);
});

test("точная правка: сдвиг, место общей рамки, размер, поворот вокруг середины", () => {
  const bs = [box("a", 10, 10, 10, 10), box("b", 30, 20, 10, 10)];
  assert.deepEqual(moveBy(bs, 5, -2.5), { a: { x: 15, y: 7.5 }, b: { x: 35, y: 17.5 } });
  assert.deepEqual(moveTo(bs, 0, 0), { a: { x: 0, y: 0 }, b: { x: 20, y: 10 } });
  assert.deepEqual(sizeTo([bs[0]], 50, 0), { a: { w: 50, h: 1 } });
  const r = rotateBy([bs[0]], 90).a;
  assert.equal(r.rotation, 90); assert.deepEqual([r.x, r.y], [20, 10]);   // середина (15, 15) на месте
  assert.equal(rotateBy([{ ...bs[0], ...r }], -90).a.rotation, undefined);
  // два элемента поворачиваются целиком: на 180 — меняются местами
  const two = rotateBy(bs, 180);
  assert.deepEqual([two.a.x, two.a.y, two.a.rotation], [40, 30, 180]);
  assert.deepEqual([two.b.x, two.b.y], [20, 20]);
});

test("формат по образцу: каждый берёт своё оформление, место и текст не трогаются", () => {
  const src = { ...newBlock("text", SH), font: "PT Serif", size: 20, color: "#d03a2f", bold: true };
  const st = styleOf(src);
  const txt = { ...newBlock("text", SH), id: "t", text: "Своя" }, rect = { ...newBlock("rect", SH), id: "r" };
  const m = paint(st, [txt, rect]);
  assert.deepEqual(m.t, { font: "PT Serif", size: 20, color: "#d03a2f", bold: true, align: "left", valign: "top" });
  assert.equal(m.r, undefined);                                          // у прямоугольника нет шрифта — ничего не меняется
  const fr = styleOf({ ...newBlock("rect", SH), frame: { on: true, color: "#ff0000", width: 1 }, bg: { on: false, color: "#fff" } });
  const m2 = paint(fr, [{ ...newBlock("map", SH), id: "m" }, txt]);
  assert.deepEqual(m2.m, { frame: { on: true, color: "#ff0000", width: 1 } });   // у карты рамка есть, заливки нет
  assert.equal(m2.t, undefined);
});
