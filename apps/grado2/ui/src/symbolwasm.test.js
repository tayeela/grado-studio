/* Слои знака на Rust в браузере (rust/crates/symbol → src/wasm, план 08.11 шаг 3): модуль WebAssembly собирается
   и даёт то же, что печать: значки внутрь полигона при любом ходе кольца, полоса — обрезанный контур двойной ширины
   с прозрачностью части, размеры × pixelRatio. Запуск: cd apps/grado2/ui && npm test. */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { initSync, parts_ops, LineLib } from "./wasm/grado_symbol.js";

initSync({ module: readFileSync(new URL("./wasm/grado_symbol_bg.wasm", import.meta.url)) });
const ops = (kind, shapes, parts, k = 1) => JSON.parse(parts_ops(kind, JSON.stringify(shapes), JSON.stringify(parts), k));

test("значки внутрь при любом ходе кольца, наружу — при side −1", () => {
  for (const ring of [[[0, 0], [100, 0], [100, 100], [0, 100]], [[0, 0], [0, 100], [100, 100], [100, 0]]])
    for (const [side, inside] of [[1, true], [-1, false]]) {
      const o = ops("poly", [[ring]], [{ k: "marks", shape: "tick", step: 25, size: 6, side }]);
      assert.equal(o.length, 16);
      for (const m of o) { const [x, y] = m.rings[0][1]; assert.equal(x > 0 && x < 100 && y > 0 && y < 100, inside, JSON.stringify(m.rings[0])); }
    }
});

test("полоса: обрезка по полигону, контур 2b × pixelRatio, прозрачность части", () => {
  const o = ops("poly", [[[[0, 0], [50, 0], [50, 50], [0, 50]]]], [{ k: "band", c: "#e34948", a: 0.35, b: 6 }], 2);
  assert.deepEqual(o.map(x => x.op), ["clip", "path", "unclip"]);
  assert.equal(o[1].width, 24); assert.equal(o[1].alpha, 0.35);
  assert.deepEqual(o[1].stroke.map(v => Math.round(v * 255)), [0xe3, 0x49, 0x48]);
});

test("линия: только значки и линия, штрих × pixelRatio", () => {
  const o = ops("line", [[[0, 0], [100, 0]]], [{ k: "band", b: 5 }, { k: "line", c: "#000000", w: 2, dash: [6, 4] }, { k: "marks", step: 20 }], 2);
  assert.equal(o[0].width, 4); assert.deepEqual(o[0].dash, [12, 8]);
  assert.equal(o.length, 1 + 3);
});

test("типы линий ЛГР (REDLN97) на Rust: все типы библиотеки строятся, у знаков своя тонкая линия, короткая — сплошная", () => {
  const lib = JSON.parse(readFileSync(new URL("../../../../core/render/grado_render/styles/redln97.json", import.meta.url), "utf8"));
  const ll = new LineLib(JSON.stringify({ linetypes: lib.linetypes, shapes: lib.shapes }));
  const line = JSON.stringify([[0, 0], [400, 30], [550, 300]]);
  let marks = 0;
  for (const name of Object.keys(lib.linetypes)) {
    const o = JSON.parse(ll.ops(line, name, 4, 0, "#d7191c", 1.3));
    assert.ok(o.length >= 1, name);
    for (const r of o) { assert.equal(r.op, "path"); assert.ok(r.width <= 1.3 + 1e-9, name); if (r.join === "round") marks++; }
  }
  assert.ok(marks > 100, "знаки REDLN97 есть");
  const short = JSON.parse(ll.ops(JSON.stringify([[0, 0], [3, 0]]), "LERROR", 4, 0, "#000000", 1));
  assert.equal(short.length, 1); assert.equal(short[0].rings[0].length, 2);
  assert.ok(ll.has("LERROR") && !ll.has("НЕТ"));
});
