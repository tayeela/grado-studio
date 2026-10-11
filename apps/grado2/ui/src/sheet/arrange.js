/* ГРАДО 2 · группы, отражение, «формат по образцу» и точная правка (сдвиг, поворот, размер, место) для редактора листа.
   Перенесено с deckcraft (github.com/storytold/deckcraft, MIT OR Apache-2.0; NOTICE — docs/product/engine-map.md):
   crates/engine/src/cmd/arrange.rs (arrange.group, ungroup, regroup), shape.rs (shape.flip, shape.move, shape.rotate,
   shape.resize), format.rs (format.painter). У deckcraft группа — вложенная фигура; у нас лист плоский, поэтому группа —
   общий ключ group у элементов, а печать (layout_io.py) его не читает: группа живёт только в редакторе.
   Чистые функции на миллиметрах листа без Konva; зовёт SheetEditor.vue (через commands.js), проверяет commands.test.js. */
import { newBlock, newId } from "./model.js";

const r2 = v => Math.round(v * 100) / 100;

/* ---------- группы (arrange.group / ungroup / regroup) ---------- */
// id выбранных вместе с остальными элементами их групп; порядок — как в ids, затем добавленные
export function withGroups(blocks, ids) {
  const gs = new Set(ids.map(id => blocks.find(b => b.id === id)?.group).filter(Boolean));
  const extra = blocks.filter(b => gs.has(b.group) && !ids.includes(b.id)).map(b => b.id);
  return [...ids, ...extra];
}
// сгруппировать: нужно два элемента и больше; вошедшие в другие группы переходят в новую → { id: { group } }
export function group(bs) {
  if (bs.length < 2) return {};
  const g = newId("group"), out = {};
  bs.forEach(b => { out[b.id] = { group: g, was: undefined }; });
  return out;
}
// разгруппировать: элемент помнит группу (was), чтобы «Восстановить группу» собрала её снова
export function ungroup(bs) {
  const out = {};
  bs.filter(b => b.group).forEach(b => { out[b.id] = { group: undefined, was: b.group }; });
  return out;
}
// восстановить группу: все элементы листа, бывшие в группе кого-то из выбранных
export function regroup(blocks, bs) {
  const was = bs.find(b => b.was)?.was; if (!was) return {};
  const out = {};
  blocks.filter(b => b.was === was).forEach(b => { out[b.id] = { group: was, was: undefined }; });
  return Object.keys(out).length > 1 ? out : {};
}

/* ---------- отражение (shape.flip) ---------- */
// элемент поворачивается вокруг левого верхнего угла (как Konva и печать layout_io._place)
const rad = d => (d || 0) * Math.PI / 180;
const center = b => { const a = rad(b.rotation), c = Math.cos(a), s = Math.sin(a); return [b.x + c * b.w / 2 - s * b.h / 2, b.y + s * b.w / 2 + c * b.h / 2]; };
function corners(b) {
  const a = rad(b.rotation), c = Math.cos(a), s = Math.sin(a);
  return [[0, 0], [b.w, 0], [b.w, b.h], [0, b.h]].map(([u, v]) => [b.x + c * u - s * v, b.y + s * u + c * v]);
}
// рамка элементов с учётом поворота
export function turnedBounds(bs) {
  const p = bs.flatMap(corners), xs = p.map(q => q[0]), ys = p.map(q => q[1]);
  const x0 = Math.min(...xs), y0 = Math.min(...ys);
  return { x: x0, y: y0, w: Math.max(...xs) - x0, h: Math.max(...ys) - y0 };
}
const norm = d => { let v = ((d % 360) + 540) % 360 - 180; if (v === -180) v = 180; return Math.abs(v) < 1e-9 ? 0 : r2(v); };
// поставить элемент с поворотом rot так, чтобы его середина была в c
function placeAt(b, c, rot) {
  const a = rad(rot), co = Math.cos(a), s = Math.sin(a);
  return { x: r2(c[0] - (co * b.w / 2 - s * b.h / 2)), y: r2(c[1] - (s * b.w / 2 + co * b.h / 2)), rotation: rot || undefined };
}
/* отразить выбранные: axis "h" — слева направо, "v" — сверху вниз, зеркалом по середине их общей рамки.
   Места и углы отражаются; надпись остаётся читаемой, картинка не зеркалится; у линии меняется направление стрелки. */
export function flip(bs, axis) {
  if (!bs.length) return {};
  const r = turnedBounds(bs), mx = r.x + r.w / 2, my = r.y + r.h / 2, out = {};
  bs.forEach(b => {
    const [cx, cy] = center(b), rot = b.rotation || 0;
    const c = axis === "h" ? [2 * mx - cx, cy] : [cx, 2 * my - cy];
    const nr = norm(b.kind === "line" && axis === "h" ? 180 - rot : -rot);
    out[b.id] = placeAt(b, c, nr);
  });
  return out;
}

/* ---------- точная правка из командной строки (shape.move / rotate / resize, место) ---------- */
export function moveBy(bs, dx, dy) {
  const out = {}; bs.forEach(b => { out[b.id] = { x: r2(b.x + dx), y: r2(b.y + dy) }; }); return out;
}
// повернуть на угол: один элемент — вокруг своей середины (как ручка поворота), несколько — целиком вокруг середины общей рамки
export function rotateBy(bs, deg) {
  if (!bs.length) return {};
  const r = turnedBounds(bs), mx = r.x + r.w / 2, my = r.y + r.h / 2, a = rad(deg), co = Math.cos(a), s = Math.sin(a), out = {};
  bs.forEach(b => {
    const [cx, cy] = center(b), c = bs.length === 1 ? [cx, cy] : [mx + co * (cx - mx) - s * (cy - my), my + s * (cx - mx) + co * (cy - my)];
    out[b.id] = placeAt(b, c, norm((b.rotation || 0) + deg));
  });
  return out;
}
export function sizeTo(bs, w, h) {
  const out = {}; bs.forEach(b => { out[b.id] = { w: r2(Math.max(1, w ?? b.w)), h: r2(Math.max(1, h ?? b.h)) }; }); return out;
}
// левый верхний угол общей рамки выбранных — в точку x, y; элементы сохраняют места друг относительно друга
export function moveTo(bs, x, y) {
  if (!bs.length) return {};
  const r = turnedBounds(bs); return moveBy(bs, x - r.x, y - r.y);
}

/* ---------- формат по образцу (format.painter) ---------- */
// что переносится: оформление, не содержание и не место
const STYLE = ["frame", "bg", "font", "size", "color", "bold", "align", "valign", "opacity"];
const SHEET = { format: "A3", orient: "L", blocks: [] };
const accepts = kind => { const d = newBlock(kind, SHEET); return k => k === "opacity" || (k === "bold" && kind === "text") || k in d; };
export function styleOf(b) {
  const out = { kind: b.kind };
  STYLE.forEach(k => { if (b[k] !== undefined) out[k] = JSON.parse(JSON.stringify(b[k])); });
  return out;
}
// оформление образца на элементы bs: каждый берёт только то, что у него есть (надписи — шрифт, фигуры — рамку и заливку)
export function paint(style, bs) {
  const out = {};
  bs.forEach(b => {
    const ok = accepts(b.kind), p = {};
    STYLE.forEach(k => { if (k in style && ok(k)) p[k] = JSON.parse(JSON.stringify(style[k])); });
    if (Object.keys(p).length) out[b.id] = p;
  });
  return out;
}
