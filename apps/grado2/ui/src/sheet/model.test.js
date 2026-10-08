/* Проверяет модель листа нового редактора (model.js, stamp.js): размеры совпадают с печатью, масштаб и охват,
   замечания к раскладке, смена формата. Запуск: cd apps/grado2/ui && npm test (или node --test src/sheet/model.test.js). */
import test from "node:test";
import assert from "node:assert/strict";
import { pageSize, frameRect, stampRect, newSheet, newBlock, groundSize, fitScale, scalebarStep, problems, reformat,
  clampToFrame, snapTargets, fmtScale, fmtM } from "./model.js";
import { stampOps } from "./stamp.js";

test("лист А3 и А1: размеры, рамка по ГОСТ и штамп как в печати", () => {
  const a3 = newSheet({ format: "A3" });
  assert.deepEqual(pageSize(a3), [420, 297]);
  assert.deepEqual(pageSize({ format: "A3", orient: "P" }), [297, 420]);
  assert.deepEqual(frameRect(a3), { x: 20, y: 5, w: 395, h: 287 });
  assert.deepEqual(stampRect(a3), { x: 230, y: 237, w: 185, h: 55 });
  // карта и колонка — как print_io.layout("A3"): (25, 10, 275, 224) и (305, 10, 105, 224)
  const map = a3.blocks.find(b => b.kind === "map"), leg = a3.blocks.find(b => b.kind === "legend");
  assert.deepEqual([map.x, map.y, map.w, map.h], [25, 10, 275, 224]);
  assert.deepEqual([leg.x, leg.y, leg.w, leg.h], [305, 10, 105, 224]);
  const a1 = newSheet({ format: "A1" }), m1 = a1.blocks.find(b => b.kind === "map");
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
  assert.deepEqual(texts, ["t: Надпись заходит на штамп", "m: Карта выходит за рамку листа", "m: У карты не задан масштаб"]);
  const c = clampToFrame(s.blocks[s.blocks.length - 1], s);
  assert.deepEqual([c.x, c.y], [20, 10]);
});

test("новый блок встаёт в середину рамки и не мешает", () => {
  const s = newSheet({ format: "A3", orient: "P" }), b = newBlock("text", s);
  assert.equal(b.kind, "text"); assert.equal(b.text, "Надпись");
  const f = frameRect(s);
  assert.ok(b.x >= f.x && b.x + b.w <= f.x + f.w);
  assert.equal(newBlock("scalebar", s).scale, 2000);
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
