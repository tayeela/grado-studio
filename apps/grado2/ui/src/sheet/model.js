/* ГРАДО 2 · модель листа для нового редактора раскладки: формат, рамка, штамп и блоки листа (карта, легенда, надпись,
   стрелка севера, масштабная линейка) в миллиметрах листа, начало — левый верхний угол, ось y вниз (как SVG печати).
   Чистые функции без Konva и без страницы: их зовёт SheetEditor.vue, проверяет model.test.js (node --test).
   Размеры повторяют печать, чтобы редактор не расходился с PDF: поля рамки — core/layout/grado_layout/model.py
   (20 и 5 мм), штамп 185×55 — frames.py StampFrame, карта и колонка легенды — print_io.layout(). */

// бумага альбомной ориентации, мм (ГОСТ 2.301)
export const FORMATS = { A4: [297, 210], A3: [420, 297], A2: [594, 420], A1: [841, 594], A0: [1189, 841] };
export const FORMAT_T = { A4: "А4", A3: "А3", A2: "А2", A1: "А1", A0: "А0" };
// поля рамки по ГОСТ Р 21.101: слева 20 мм (подшивка), остальные 5 мм; лист без штампа — поля 2 % (PAPER_MARGIN)
export const MARGIN_LEFT = 20, MARGIN = 5, PAPER_MARGIN = 0.02;
export const STAMP_W = 185, STAMP_H = 55;
// правая колонка легенды и ТЭП (COLUMN в print_io.py); у форматов, которых там нет, — по ближайшему
const COLUMN = { A4: 90, A3: 110, A2: 140, A1: 170, A0: 200 };
// стандартные масштабы карты (SCALES в sheets.js)
export const SCALES = [500, 1000, 2000, 2500, 3000, 4000, 5000, 7500, 10000, 15000, 20000, 25000, 50000, 100000, 200000, 500000, 1000000];
export const KINDS = { map: "Карта", legend: "Легенда", text: "Надпись", north: "Стрелка севера", scalebar: "Масштабная линейка" };
export const PT = 25.4 / 72;                          // 1 пт в мм: кегль в окне — в пунктах, как в QGIS

const r2 = v => Math.round(v * 100) / 100;
let seq = 0;
export const newId = kind => `${kind}-${Date.now().toString(36)}${(seq++).toString(36)}`;

// размер листа с учётом ориентации ("L" альбомная, "P" книжная)
export function pageSize(sheet) {
  const [a, b] = FORMATS[sheet.format] || FORMATS.A3;
  return sheet.orient === "P" ? [b, a] : [a, b];
}
// рамка листа: по ГОСТ, если есть штамп, иначе поля 2 %
export function frameRect(sheet) {
  const [w, h] = pageSize(sheet);
  if (sheet.stamp === false) return { x: r2(w * PAPER_MARGIN), y: r2(h * PAPER_MARGIN), w: r2(w * (1 - 2 * PAPER_MARGIN)), h: r2(h * (1 - 2 * PAPER_MARGIN)) };
  return { x: MARGIN_LEFT, y: MARGIN, w: w - MARGIN_LEFT - MARGIN, h: h - 2 * MARGIN };
}
// основная надпись: прижата к правому нижнему углу рамки (StampFrame)
export function stampRect(sheet) {
  if (sheet.stamp === false) return null;
  const f = frameRect(sheet);
  return { x: f.x + f.w - STAMP_W, y: f.y + f.h - STAMP_H, w: STAMP_W, h: STAMP_H };
}

// новый лист: карта и колонка легенды стоят там же, где их ставит print_io.layout()
export function newSheet({ format = "A3", orient = "L", stamp = true, title = "Лист" } = {}) {
  const sheet = { format, orient, stamp, title, blocks: [] };
  const [w, h] = pageSize(sheet), f = frameRect(sheet);
  if (!stamp) {
    sheet.blocks.push({ id: newId("map"), kind: "map", ...f, scale: 2000 });
    return sheet;
  }
  const col = orient === "P" ? 0 : COLUMN[format] || 110, bottom = h - MARGIN - STAMP_H - 3;
  const mapW = col ? w - MARGIN - col - (MARGIN_LEFT + MARGIN) - MARGIN : w - MARGIN - (MARGIN_LEFT + MARGIN);
  sheet.blocks.push({ id: newId("map"), kind: "map", x: MARGIN_LEFT + MARGIN, y: 10, w: mapW, h: bottom - 10, scale: 2000 });
  if (col) sheet.blocks.push({ id: newId("legend"), kind: "legend", x: w - MARGIN - col, y: 10, w: col - MARGIN, h: bottom - 10 });
  sheet.blocks.push({ id: newId("north"), kind: "north", x: MARGIN_LEFT + MARGIN + 4, y: 14, w: 10, h: 16 });
  return sheet;
}

// новый блок нужного вида в середине рамки
export function newBlock(kind, sheet) {
  const f = frameRect(sheet), size = { map: [160, 110], legend: [90, 120], text: [80, 10], north: [10, 16], scalebar: [60, 8] }[kind] || [40, 20];
  const [bw, bh] = size.map((v, i) => Math.min(v, i ? f.h : f.w));
  const b = { id: newId(kind), kind, x: r2(f.x + (f.w - bw) / 2), y: r2(f.y + (f.h - bh) / 2), w: bw, h: bh };
  if (kind === "map") b.scale = 2000;
  if (kind === "text") Object.assign(b, { text: "Надпись", size: 14 });
  if (kind === "scalebar") b.scale = mainScale(sheet) || 2000;
  return b;
}
// масштаб первой карты листа — по нему рисуется масштабная линейка, если у неё нет своего
export const mainScale = sheet => sheet.blocks.find(b => b.kind === "map")?.scale;

// сколько метров на местности покрывает карта: ширина и высота
export const groundSize = b => [b.w * b.scale / 1000, b.h * b.scale / 1000];
// масштаб, при котором охват на местности (метры) входит в карту с запасом pad; round — ближайший стандартный крупнее
export function fitScale(b, extent, { pad = 1.08, round = true } = {}) {
  const need = Math.max(extent[0] / b.w, extent[1] / b.h) * 1000 * pad;
  if (!round) return Math.ceil(need);
  return SCALES.find(v => v >= need) || SCALES[SCALES.length - 1];
}
// длина деления масштабной линейки: «круглое» число метров, чтобы вся линейка (4 деления) уложилась в ширину блока
export function scalebarStep(b) {
  const m = b.w * b.scale / 1000 / 4, e = 10 ** Math.floor(Math.log10(m));
  return [5, 2, 1].map(k => k * e).find(v => v <= m) || e;
}
export const fmtM = m => m >= 1000 ? `${String(r2(m / 1000)).replace(".", ",")} км` : `${Math.round(m)} м`;
export const fmtScale = s => "1:" + String(s).replace(/\B(?=(\d{3})+(?!\d))/g, " ");

export const toBox = r => ({ x0: r.x, y0: r.y, x1: r.x + r.w, y1: r.y + r.h });
// цели привязки для блока: лист, рамка, штамп и остальные блоки
export function snapTargets(sheet, exceptId) {
  const [w, h] = pageSize(sheet), out = [{ x0: 0, y0: 0, x1: w, y1: h }, toBox(frameRect(sheet))];
  const s = stampRect(sheet); if (s) out.push(toBox(s));
  sheet.blocks.forEach(b => { if (b.id !== exceptId) out.push(toBox(b)); });
  return out;
}

// блок не выходит за рамку; размер не больше рамки
export function clampToFrame(b, sheet) {
  const f = frameRect(sheet), w = Math.min(b.w, f.w), h = Math.min(b.h, f.h);
  return { ...b, w, h, x: r2(Math.min(Math.max(b.x, f.x), f.x + f.w - w)), y: r2(Math.min(Math.max(b.y, f.y), f.y + f.h - h)) };
}
const overlap = (a, b) => a.x < b.x + b.w - .01 && b.x < a.x + a.w - .01 && a.y < b.y + b.h - .01 && b.y < a.y + a.h - .01;
// замечания к раскладке простыми словами: блок за рамкой, блок на штампе, карта без масштаба
export function problems(sheet) {
  const out = [], f = frameRect(sheet), s = stampRect(sheet), name = b => KINDS[b.kind] || b.kind;
  sheet.blocks.forEach(b => {
    if (b.x < f.x - .01 || b.y < f.y - .01 || b.x + b.w > f.x + f.w + .01 || b.y + b.h > f.y + f.h + .01) out.push({ id: b.id, text: `${name(b)} выходит за рамку листа` });
    if (s && overlap(b, s)) out.push({ id: b.id, text: `${name(b)} заходит на штамп` });
    if (b.kind === "map" && !(b.scale > 0)) out.push({ id: b.id, text: "У карты не задан масштаб" });
  });
  return out;
}

// смена формата или ориентации: блоки сохраняют место относительно рамки (доли ширины и высоты), карта — свой масштаб
export function reformat(sheet, patch) {
  const next = { ...sheet, ...patch }, a = frameRect(sheet), b = frameRect(next), kx = b.w / a.w, ky = b.h / a.h;
  next.blocks = sheet.blocks.map(bl => {
    const fixed = bl.kind === "north" || bl.kind === "text";      // знак и надпись не растягиваются
    const w = fixed ? bl.w : r2(bl.w * kx), h = fixed ? bl.h : r2(bl.h * ky);
    return clampToFrame({ ...bl, x: r2(b.x + (bl.x - a.x) * kx), y: r2(b.y + (bl.y - a.y) * ky), w, h }, next);
  });
  return next;
}
