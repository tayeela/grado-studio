/* Проверяет модель листа нового редактора (model.js, stamp.js): размеры совпадают с печатью, масштаб и охват,
   замечания к раскладке, смена формата. Запуск: cd apps/grado2/ui && npm test. */
import test from "node:test";
import assert from "node:assert/strict";
import { pageSize, frameRect, stampRect, newSheet, newBlock, groundSize, fitScale, scalebarStep, problems, reformat,
  clampToFrame, snapTargets, fmtScale, fmtM, linkedScale, snapBox, align, distribute, sameSize, reorder, duplicate, refPos, fromRef,
  rulerStep, bounds, moveCenter, centerOffset, blockBounds, nextScale, label, legendFit } from "./model.js";
import { stampOps } from "./stamp.js";
import "../../../web/snap.js";
const Snap = globalThis.Snap;

test("лист А3 и А1: размеры, рамка по ГОСТ и штамп как в печати", () => {
  const a3 = newSheet({ format: "A3", center: [37.8, 55.8] });
  assert.deepEqual(pageSize(a3), [420, 297]);
  assert.deepEqual(pageSize({ format: "A3", orient: "P" }), [297, 420]);
  assert.deepEqual(frameRect(a3), { x: 20, y: 5, w: 395, h: 287 });
  assert.deepEqual(stampRect(a3), { x: 230, y: 237, w: 185, h: 55 });
  // карта и колонка — как print_io.layout("A3"): (25, 10, 275, 224) и (305, 10, 105, 224)
  const map = a3.blocks.find(b => b.kind === "map"), leg = a3.blocks.find(b => b.kind === "legend");
  assert.deepEqual([map.x, map.y, map.w, map.h], [25, 10, 275, 224]);
  assert.deepEqual([leg.x, leg.y, leg.w, leg.h], [305, 10, 105, 224]);
  const a1 = newSheet({ format: "A1", center: [37.8, 55.8] }), m1 = a1.blocks.find(b => b.kind === "map");
  assert.deepEqual([m1.x, m1.y, m1.w, m1.h], [25, 10, 636, 521]);              // FRAME_MM.A1 в sheets.js
  assert.deepEqual(problems(a3), []);
  assert.deepEqual(problems(a1), []);
});

test("лист без штампа: поля 2 %, карта на всю рамку", () => {
  const s = newSheet({ format: "A2", stamp: false });
  assert.equal(stampRect(s), null);
  assert.deepEqual(frameRect(s), { x: 11.88, y: 8.4, w: 570.24, h: 403.2 });
  assert.equal(s.blocks.length, 1);
  assert.equal(stampOps(s), null);
});

test("масштаб карты: охват на местности, подбор стандартного масштаба, деление линейки", () => {
  const b = { kind: "map", w: 275, h: 224, scale: 2000 };
  assert.deepEqual(groundSize(b), [550, 448]);
  assert.equal(fitScale(b, [1000, 500]), 4000);                // нужно 3927 → ближайший стандартный крупнее
  assert.equal(fitScale(b, [1000, 500], { round: false }), 3928);
  assert.equal(fitScale(b, [1e9, 1e9]), 1000000);
  assert.equal(scalebarStep({ w: 60, scale: 2000 }), 20);       // 120 м на 4 деления → 30 → 20 м
  assert.equal(scalebarStep({ w: 60, scale: 10000 }), 100);     // 600 м → 150 → 100 м
  assert.equal(fmtScale(25000), "1:25 000");
  assert.equal(fmtM(550), "550 м");
  assert.equal(fmtM(1250), "1,25 км");
});

test("замечания: блок за рамкой и на штампе", () => {
  const s = newSheet({ format: "A3" });
  s.blocks.push({ id: "t", kind: "text", x: 300, y: 250, w: 60, h: 10 });
  s.blocks.push({ id: "m", kind: "map", x: 10, y: 10, w: 50, h: 50, scale: 0 });
  const texts = problems(s).map(p => `${p.id}: ${p.text}`);
  assert.deepEqual(texts.filter(t => !/место/.test(t)), ["t: Надпись заходит на штамп", "m: Карта выходит за рамку листа", "m: У карты не задан масштаб"]);
  assert.ok(texts.includes("m: У карты не задано место: «Как на карте» в свойствах"));
  const c = clampToFrame(s.blocks[s.blocks.length - 1], s);
  assert.deepEqual([c.x, c.y], [20, 10]);
});

test("новый блок встаёт в середину рамки и не мешает", () => {
  const s = newSheet({ format: "A3", orient: "P" }), b = newBlock("text", s);
  assert.equal(b.kind, "text"); assert.equal(b.text, "Надпись");
  const f = frameRect(s);
  assert.ok(b.x >= f.x && b.x + b.w <= f.x + f.w);
  const sb = newBlock("scalebar", s);
  assert.equal(sb.map, s.blocks[0].id);                         // линейка привязана к первой карте листа
  assert.equal(linkedScale(sb, s), 2000);
  // цели привязки: лист, рамка, штамп и все блоки, кроме самого
  assert.equal(snapTargets(s, s.blocks[0].id).length, 3 + s.blocks.length - 1);
});

test("смена формата: блоки сохраняют место относительно рамки, масштаб карты не меняется", () => {
  const a3 = newSheet({ format: "A3" }), a1 = reformat(a3, { format: "A1" });
  assert.equal(a1.format, "A1");
  const m3 = a3.blocks[0], m1 = a1.blocks[0];
  assert.equal(m1.scale, m3.scale);
  const f3 = frameRect(a3), f1 = frameRect(a1);
  assert.ok(Math.abs((m1.x - f1.x) / f1.w - (m3.x - f3.x) / f3.w) < .001);
  assert.ok(m1.w > m3.w * 1.9);
  assert.deepEqual(problems(reformat(a3, { orient: "P" })).filter(p => /рамку/.test(p.text)), []);
});

test("штамп: линии и надписи формы 3 на месте, поля альбома подставлены", () => {
  const s = newSheet({ format: "A3", title: "Ортофотоплан" });
  const st = stampOps(s, { code: "КРТ-1", object: "Объект", stage: "ПП", org: "ГРАДО" }, { page_no: 4, page_total: 11 });
  const text = st.texts.map(t => t.text);
  for (const t of ["Изм.", "Дата", "КРТ-1", "Объект", "Ортофотоплан", "Стадия", "ПП", "4", "11", "ГРАДО"]) assert.ok(text.includes(t), t);
  const code = st.texts.find(t => t.text === "КРТ-1");
  assert.deepEqual([code.x, code.y, code.size], [230 + 65 + 60, 237 + 9.5, 4]);
  // все линии штампа внутри его прямоугольника 185×55 в правом нижнем углу рамки
  assert.ok(st.lines.every(l => l.pts.every((v, i) => i % 2 ? v >= 237 && v <= 292 : v >= 230 && v <= 415)));
});

const B = (id, x, y, w, h) => ({ id, kind: "rect", x, y, w, h });

test("выравнивание как в QGIS: несколько — по общей рамке, один — по рамке листа", () => {
  const bs = [B("a", 30, 20, 10, 10), B("b", 60, 50, 20, 6)];
  assert.deepEqual(align(bs, "left"), { a: { x: 30 }, b: { x: 30 } });
  assert.deepEqual(align(bs, "right"), { a: { x: 70 }, b: { x: 60 } });
  assert.deepEqual(align(bs, "vcenter"), { a: { y: 33 }, b: { y: 35 } });
  assert.deepEqual(align([bs[0]], "hcenter", { x: 20, y: 5, w: 395, h: 287 }), { a: { x: 212.5 } });
  assert.deepEqual(bounds(bs), { x: 30, y: 20, w: 50, h: 36 });
});

test("распределение, одинаковый размер, порядок рисования, копии", () => {
  const bs = [B("a", 0, 0, 10, 10), B("c", 100, 0, 10, 10), B("b", 20, 0, 20, 10)];
  assert.deepEqual(distribute(bs, "x"), { a: { x: 0 }, b: { x: 45 }, c: { x: 100 } });
  assert.deepEqual(distribute(bs.slice(0, 2), "x"), {});
  assert.deepEqual(sameSize(bs, "w"), { c: { w: 10 }, b: { w: 10 } });
  const ids = l => l.map(b => b.id).join("");
  assert.equal(ids(reorder(bs, ["a"], "up")), "cab");
  assert.equal(ids(reorder(bs, ["a"], "top")), "cba");
  assert.equal(ids(reorder(bs, ["b"], "bottom")), "bac");
  assert.equal(ids(reorder(bs, ["c"], "down")), "cab");
  assert.equal(ids(reorder(bs, ["b"], "up")), "acb");                 // верхний остаётся верхним
  const [d] = duplicate([{ ...bs[0], locked: true }]);
  assert.notEqual(d.id, "a"); assert.deepEqual([d.x, d.y, d.locked, d.name], [5, 5, false, "Прямоугольник (копия)"]);
});

test("опорная точка: X и Y центра или угла и обратно", () => {
  const b = B("a", 10, 20, 40, 30);
  assert.deepEqual(refPos(b, "mc"), [30, 35]);
  assert.deepEqual(refPos(b, "br"), [50, 50]);
  assert.deepEqual(fromRef(b, "mc", 100, 100), { x: 80, y: 85 });
});

test("привязка: к направляющей, к элементу, к сетке там, где больше не к чему", () => {
  const s = newSheet({ format: "A3" });
  s.blocks = [B("m", 25, 10, 100, 100)];
  s.guides = { x: [200], y: [] };
  s.grid = { step: 10, snap: true };
  const opt = { snapFn: Snap.snap, tol: 1.5 };
  // левый край у направляющей 200
  assert.equal(snapBox({ x0: 200.8, y0: 150.3, x1: 230.8, y1: 160.3 }, s, opt).dx.toFixed(2), "-0.80");
  // по y ничего нет рядом, кроме сетки 150
  assert.equal(snapBox({ x0: 200.8, y0: 150.3, x1: 230.8, y1: 160.3 }, s, opt).dy.toFixed(2), "-0.30");
  // правый край у левого края карты? нет: верх у верха карты (10)
  assert.equal(snapBox({ x0: 140, y0: 11, x1: 160, y1: 21 }, s, opt).dy.toFixed(2), "-1.00");
  s.snap = { guides: false, items: false }; s.grid.snap = false;
  assert.deepEqual(snapBox({ x0: 200.8, y0: 150.3, x1: 230.8, y1: 160.3 }, s, opt), { dx: 0, dy: 0, guides: [] });
});

test("деления линейки не гуще 50 пикселей", () => {
  assert.equal(rulerStep(3.78), 20);      // 100 %: 20 мм ≈ 76 px
  assert.equal(rulerStep(1.5), 50);
  assert.equal(rulerStep(30), 2);
});

test("место карты: сдвиг на миллиметры листа, обратный пересчёт и охват", () => {
  const c = [37.8, 55.8];
  // 10 мм на восток в 1:2 000 — 20 м; 20 мм на юг — 40 м
  const m = moveCenter(c, 2000, 10, 20);
  assert.ok(m[0] > c[0] && m[1] < c[1]);
  const [dx, dy] = centerOffset(m, c, 2000);
  assert.ok(Math.abs(dx - 10) < .05 && Math.abs(dy - 20) < .05);
  // охват блока 100 × 50 мм в 1:2 000 — 200 × 100 м: по широте ≈ 0,0009°, без запаса
  const [w, s, e, n] = blockBounds({ center: c, w: 100, h: 50, scale: 2000 }, 1);
  assert.ok(Math.abs((n - s) * 110574 - 100) < .5 && Math.abs((e - w) * 111320 * Math.cos(55.8 * Math.PI / 180) - 200) < .5);
  assert.equal(nextScale(2000, 1), 2500);
  assert.equal(nextScale(2000, -1), 1000);
  assert.equal(nextScale(500, -1), 500);
  // новая карта берёт место у карты, что уже есть на листе
  const sh = newSheet({ format: "A3", center: c });
  assert.deepEqual(newBlock("map", sh).center, c);
});

test("имена элементов: безымянные одного вида нумеруются, легенда считает строки, что помещаются", () => {
  const bs = [{ id: "a", kind: "rect" }, { id: "m", kind: "map" }, { id: "b", kind: "rect" }, { id: "n", kind: "rect", name: "Врезка" }, { id: "c", kind: "rect" }];
  assert.deepEqual(bs.map(b => label(b, bs)), ["Прямоугольник", "Карта", "Прямоугольник 2", "Врезка", "Прямоугольник 3"]);
  assert.equal(label(bs[2]), "Прямоугольник");
  // как печать (layout_io._legend): отступ 3 + заголовок 7, строка 6,5 мм — в 40 мм помещаются 4 строки
  const leg = { kind: "legend", h: 40, items: Array.from({ length: 7 }, (_, i) => ({ t: String(i) })) };
  assert.equal(legendFit(leg), 4);
  assert.equal(legendFit({ ...leg, h: 300 }), 7);
  assert.ok(problems({ format: "A3", blocks: [{ id: "l", x: 30, y: 30, w: 50, ...leg }] }).some(p => p.text === "Легенда: 3 строки не помещаются — увеличьте высоту"));
});
