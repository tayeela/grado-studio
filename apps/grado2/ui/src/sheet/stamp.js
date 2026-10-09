/* ГРАДО 2 · основная надпись (штамп) листа для редактора раскладки: линии и тексты в мм листа.
   Повторяет печать (core/layout/grado_layout/frames.py, StampFrame — упрощённая форма 3 ГОСТ Р 21.101, 185×55),
   поэтому штамп в редакторе стоит и делится так же, как в PDF. Чистая функция; рисует SheetEditor.vue,
   проверяет model.test.js. */
import { stampRect } from "./model.js";

/* → { lines: [{ pts: [x0, y0, x1, y1], w }], texts: [{ x, y, size, text, anchor }] } или null у листа без штампа.
   meta — поля штампа альбома (object, code, stage, org); ctx — sheet_title, page_no, page_total */
export function stampOps(sheet, meta = {}, ctx = {}) {
  const r = stampRect(sheet); if (!r) return null;
  const { x, y, w, h } = r, lines = [], texts = [];
  const hl = (x0, x1, yy, lw = .3) => lines.push({ pts: [x0, yy, x1, yy], w: lw });
  const vl = (xx, y0, y1, lw = .3) => lines.push({ pts: [xx, y0, xx, y1], w: lw });
  const tx = (tx_, ty, size, text, anchor = "middle") => texts.push({ x: tx_, y: ty, size, text: String(text ?? ""), anchor });
  // контур
  hl(x, x + w, y, .7); hl(x, x + w, y + h, .7); vl(x, y, y + h, .7); vl(x + w, y, y + h, .7);
  // блок подписей: 6 колонок [10, 10, 10, 10, 15, 10], 5 строк по 11
  const signW = 65, cols = [10, 10, 10, 10, 15, 10], heads = ["Изм.", "Кол.", "Лист", "№док", "Подп.", "Дата"];
  for (let i = 1; i < 5; i++) hl(x, x + signW, y + i * 11);
  let cx = x;
  cols.forEach((cw, i) => { tx(cx + cw / 2, y + 3.6, 2, heads[i]); cx += cw; if (i < 5) vl(cx, y, y + h); });
  // правая часть: шифр / объект и название листа / стадия, лист, листов | организация
  const rx = x + signW, rw = w - signW;
  vl(rx, y, y + h, .7); hl(rx, x + w, y + 15, .5); hl(rx, x + w, y + 40, .5);
  tx(rx + rw / 2, y + 9.5, 4, meta.code);
  tx(rx + rw / 2, y + 24, 3.2, meta.object);
  tx(rx + rw / 2, y + 33, 3, ctx.sheet_title ?? sheet.title);
  [["Стадия", meta.stage], ["Лист", ctx.page_no], ["Листов", ctx.page_total]].forEach(([head, val], i) => {
    const colx = rx + i * 20; if (i) vl(colx, y + 40, y + h);
    tx(colx + 10, y + 44, 2.2, head); tx(colx + 10, y + 51, 3.2, val ?? "");
  });
  vl(rx + 60, y + 40, y + h);
  tx(rx + 60 + (rw - 60) / 2, y + 48.5, 3, meta.org);
  return { lines, texts };
}
