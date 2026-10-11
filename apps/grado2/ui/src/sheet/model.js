/* ГРАДО 2 · модель листа для нового редактора раскладки (как «Макет» QGIS): формат, рамка, штамп, направляющие, сетка
   и элементы листа (карта, легенда, надпись, картинка, стрелка севера, масштабная линейка, таблица, фигура, линия)
   в миллиметрах листа, начало — левый верхний угол, ось y вниз (как SVG печати). Здесь же выравнивание, распределение,
   порядок, копии, опорная точка и привязка к сетке и направляющим.
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
export const KINDS = { map: "Карта", legend: "Легенда", text: "Надпись", picture: "Картинка", north: "Стрелка севера",
  scalebar: "Масштабная линейка", table: "Таблица", rect: "Прямоугольник", ellipse: "Эллипс", line: "Линия" };
// шрифты листа — те же, что в нынешнем «Макете листа» (layout.js LAY_FONTS)
export const FONTS = ["PT Sans", "PT Serif", "Montserrat"];
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
export function newSheet({ format = "A3", orient = "L", stamp = true, title = "Лист", center = null } = {}) {
  const sheet = { format, orient, stamp, title, blocks: [], guides: { x: [], y: [] }, grid: { step: 5, show: false, snap: true }, snap: { guides: true, items: true } };
  const [w, h] = pageSize(sheet), f = frameRect(sheet);
  if (!stamp) {
    sheet.blocks.push({ ...newBlock("map", sheet), ...f, center });
    return sheet;
  }
  const col = orient === "P" ? 0 : COLUMN[format] || 110, bottom = h - MARGIN - STAMP_H - 3;
  const mapW = col ? w - MARGIN - col - (MARGIN_LEFT + MARGIN) - MARGIN : w - MARGIN - (MARGIN_LEFT + MARGIN);
  const map = { ...newBlock("map", sheet), center, x: MARGIN_LEFT + MARGIN, y: 10, w: mapW, h: bottom - 10 };
  sheet.blocks.push(map);
  if (col) sheet.blocks.push({ ...newBlock("legend", sheet), x: w - MARGIN - col, y: 10, w: col - MARGIN, h: bottom - 10 });
  sheet.blocks.push({ ...newBlock("north", sheet), x: MARGIN_LEFT + MARGIN + 4, y: 14, w: 10, h: 16 });
  return sheet;
}

// строки легенды по умолчанию: условные знаки, как в образце интерфейса; настоящая легенда придёт из слоёв листа
export const LEGEND_SAMPLE = [
  { t: "Граница территории", s: "line", c: "#d03a2f", dash: [2, .8, .4, .8] },
  { t: "Красные линии (ЛГР)", s: "line", c: "#d03a2f" },
  { t: "ЗОУИТ", s: "fill", c: "#7b61d9", f: "#d6ccf5" },
  { t: "Участки ЕГРН", s: "line", c: "#6b7280" },
  { t: "Здания существующие", s: "fill", c: "#9aa1ab", f: "#e5e7eb" },
];
// новый элемент нужного вида в середине рамки (или в прямоугольнике at, нарисованном мышью)
const SIZE = { map: [160, 110], legend: [90, 120], text: [80, 10], picture: [60, 40], north: [10, 16], scalebar: [60, 8], table: [100, 40],
  rect: [40, 25], ellipse: [30, 30], line: [50, 4] };
export function newBlock(kind, sheet, at) {
  const f = frameRect(sheet), [bw, bh] = (SIZE[kind] || [40, 20]).map((v, i) => Math.min(v, i ? f.h : f.w));
  const b = at ? { id: newId(kind), kind, x: r2(at.x), y: r2(at.y), w: r2(Math.max(at.w, 2)), h: r2(Math.max(at.h, 2)) }
    : { id: newId(kind), kind, x: r2(f.x + (f.w - bw) / 2), y: r2(f.y + (f.h - bh) / 2), w: bw, h: bh };
  if (kind === "map") Object.assign(b, { scale: 2000, center: sheet.blocks.find(x => x.kind === "map" && x.center)?.center || null, basemap: "none",
    frame: { on: true, color: "#1a1a1a", width: .35 } });
  if (kind === "legend") Object.assign(b, { title: "Условные обозначения", items: JSON.parse(JSON.stringify(LEGEND_SAMPLE)), frame: { on: false, color: "#1a1a1a", width: .25 } });
  if (kind === "text") Object.assign(b, { text: "Надпись", size: 14, font: "PT Sans", color: "#1a1a1a", align: "left", valign: "top" });
  if (kind === "scalebar") b.map = sheet.blocks.find(x => x.kind === "map")?.id || "";
  if (kind === "north") b.map = sheet.blocks.find(x => x.kind === "map")?.id || "";
  if (kind === "table") Object.assign(b, { rows: 5, cols: 3, title: "ТЭП", frame: { on: true, color: "#1a1a1a", width: .25 } });
  if (kind === "rect" || kind === "ellipse") Object.assign(b, { bg: { on: true, color: "#ffffff" }, frame: { on: true, color: "#1a1a1a", width: .35 } });
  if (kind === "line") Object.assign(b, { frame: { on: true, color: "#1a1a1a", width: .5 }, arrow: true });
  return b;
}
/* имя элемента; blocks — все элементы листа: безымянные одного вида нумеруются по порядку добавления,
   как в «Элементах» QGIS — «Прямоугольник», «Прямоугольник 2», «Прямоугольник 3» */
export function label(b, blocks) {
  if (b.name) return b.name;
  const base = KINDS[b.kind] || b.kind;
  if (!blocks) return base;
  const same = blocks.filter(x => x.kind === b.kind && !x.name), n = same.findIndex(x => x.id === b.id) + 1;
  return n > 1 ? `${base} ${n}` : base;
}
/* легенда: сколько строк помещается по высоте (шаги — как draw.js и печать layout_io.py: отступ 3, заголовок 7, строка 6,5 мм) */
export const LEGEND_ROW = 6.5;
const plural = (n, one, few, many) => { const m = n % 100, d = n % 10; return m > 10 && m < 20 ? many : d === 1 ? one : d >= 2 && d <= 4 ? few : many; };
// «3 строки не помещаются», «1 строка не помещается»
export const legendHidden = n => `${n} ${plural(n, "строка", "строки", "строк")} не ${plural(n, "помещается", "помещаются", "помещаются")}`;
export function legendFit(b) {
  const n = (b.items || []).length, fit = Math.floor((b.h - 3 - 7) / LEGEND_ROW + 1e-6);
  return Math.max(0, Math.min(n, fit));
}
// масштаб первой карты листа — по нему рисуется масштабная линейка, если у неё нет своего
export const mainScale = sheet => sheet.blocks.find(b => b.kind === "map")?.scale;
// масштаб, по которому рисуется линейка: своя карта (b.map), иначе первая карта листа
export const linkedScale = (b, sheet) => b.scale || sheet.blocks.find(x => x.id === b.map && x.kind === "map")?.scale || mainScale(sheet) || 2000;

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

// место карты: center — [долгота, широта] середины рамки; перевод миллиметров листа в градусы — по шару (для охвата
// выборки и сдвига содержимого мышью этого хватает; точную проекцию в МСК строит печать, print_io.MapTransform)
const M_LAT = 110574, M_LON = 111320;
const cosLat = lat => Math.max(.05, Math.cos(lat * Math.PI / 180));
// центр, сдвинутый на dx, dy мм листа (x — на восток, y — на юг) при масштабе scale
export function moveCenter(center, scale, dx, dy) {
  const mx = dx * scale / 1000, my = dy * scale / 1000;
  return [+(center[0] + mx / (M_LON * cosLat(center[1]))).toFixed(7), +(center[1] - my / M_LAT).toFixed(7)];
}
// где на листе (мм от середины рамки) окажется точка from, если середина рамки — to
export function centerOffset(from, to, scale) {
  return [(from[0] - to[0]) * M_LON * cosLat(to[1]) * 1000 / scale, -(from[1] - to[1]) * M_LAT * 1000 / scale];
}
// охват карты в градусах [запад, юг, восток, север] с запасом pad (подписи и линии у края не обрываются)
export function blockBounds(b, pad = 1.15) {
  const [lon, lat] = b.center, hx = b.w * b.scale / 2000 * pad, hy = b.h * b.scale / 2000 * pad;
  return [lon - hx / (M_LON * cosLat(lat)), lat - hy / M_LAT, lon + hx / (M_LON * cosLat(lat)), lat + hy / M_LAT];
}
// следующий стандартный масштаб: dir > 0 — мельче (1:2 000 → 1:2 500), dir < 0 — крупнее
export function nextScale(s, dir) {
  if (dir > 0) return SCALES.find(v => v > s) || SCALES[SCALES.length - 1];
  return [...SCALES].reverse().find(v => v < s) || SCALES[0];
}

export const toBox = r => ({ x0: r.x, y0: r.y, x1: r.x + r.w, y1: r.y + r.h });
// цели привязки для элемента: лист, рамка, штамп и остальные видимые элементы (except — id или список id)
export function snapTargets(sheet, except) {
  const skip = new Set([].concat(except || [])), [w, h] = pageSize(sheet), out = [{ x0: 0, y0: 0, x1: w, y1: h }, toBox(frameRect(sheet))];
  const s = stampRect(sheet); if (s) out.push(toBox(s));
  sheet.blocks.forEach(b => { if (!skip.has(b.id) && !b.hidden) out.push(toBox(b)); });
  return out;
}
// направляющие как цели привязки: вертикальная — рамка нулевой ширины во всю высоту листа
export function guideTargets(sheet) {
  const [w, h] = pageSize(sheet), g = sheet.guides || {};
  return [...(g.x || []).map(x => ({ x0: x, y0: 0, x1: x, y1: h })), ...(g.y || []).map(y => ({ x0: 0, y0: y, x1: w, y1: y }))];
}
// ближайший к краю или середине рамки узел сетки по оси, если до него не дальше tol: → сдвиг или 0
function gridShift(vals, step, tol) {
  let best = null;
  vals.forEach(v => { const d = Math.round(v / step) * step - v; if (Math.abs(d) <= tol && (best === null || Math.abs(d) < Math.abs(best))) best = d; });
  return best ?? 0;
}
/* привязка перемещаемой рамки box (мм) как в QGIS: к направляющим и элементам (умные направляющие, web/snap.js),
   затем, где по оси ничего не нашлось, — к сетке. snapFn — Snap.snap; tol — зона привязки в мм.
   → { dx, dy, guides: [{ a, b }] } */
export function snapBox(box, sheet, { snapFn, tol, except }) {
  const g = sheet.grid || {}, sn = sheet.snap || {}, targets = [];
  if (sn.guides !== false) targets.push(...guideTargets(sheet));
  if (sn.items !== false) targets.push(...snapTargets(sheet, except));
  const out = snapFn && targets.length ? snapFn(box, targets, tol) : { dx: 0, dy: 0, guides: [] };
  if (g.snap && g.step > 0) {
    if (!out.dx) out.dx = gridShift([box.x0, box.x1], g.step, tol);
    if (!out.dy) out.dy = gridShift([box.y0, box.y1], g.step, tol);
  }
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
    if (b.kind === "map" && !b.center) out.push({ id: b.id, text: "У карты не задано место: «Как на карте» в свойствах" });
    if (b.kind === "legend") { const hid = (b.items || []).length - legendFit(b); if (hid > 0) out.push({ id: b.id, text: `Легенда: ${legendHidden(hid)} — увеличьте высоту` }); }
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

/* ---------- опорная точка (как в QGIS: X и Y можно задавать для угла, середины стороны или центра) ---------- */
// ref: "tl", "tc", "tr", "ml", "mc", "mr", "bl", "bc", "br"
const REF = { t: 0, m: .5, b: 1, l: 0, c: .5, r: 1 };
export const REFS = ["tl", "tc", "tr", "ml", "mc", "mr", "bl", "bc", "br"];
export const refPos = (b, ref = "tl") => [r2(b.x + b.w * REF[ref[1]]), r2(b.y + b.h * REF[ref[0]])];
export const fromRef = (b, ref, x, y) => ({ x: r2(x - b.w * REF[ref[1]]), y: r2(y - b.h * REF[ref[0]]) });

/* ---------- выравнивание, распределение, размер, порядок, копии (панель «Упорядочить» QGIS) ---------- */
// общая рамка нескольких элементов
export function bounds(bs) {
  const x0 = Math.min(...bs.map(b => b.x)), y0 = Math.min(...bs.map(b => b.y));
  return { x: x0, y: y0, w: Math.max(...bs.map(b => b.x + b.w)) - x0, h: Math.max(...bs.map(b => b.y + b.h)) - y0 };
}
/* выровнять выбранные: mode left | hcenter | right | top | vcenter | bottom. Один элемент выравнивается по рамке листа
   (to = frameRect), несколько — по их общей рамке, как в QGIS. → { id: { x } | { y } } */
export function align(bs, mode, to) {
  const r = to || bounds(bs), out = {};
  bs.forEach(b => {
    if (mode === "left") out[b.id] = { x: r2(r.x) };
    if (mode === "hcenter") out[b.id] = { x: r2(r.x + (r.w - b.w) / 2) };
    if (mode === "right") out[b.id] = { x: r2(r.x + r.w - b.w) };
    if (mode === "top") out[b.id] = { y: r2(r.y) };
    if (mode === "vcenter") out[b.id] = { y: r2(r.y + (r.h - b.h) / 2) };
    if (mode === "bottom") out[b.id] = { y: r2(r.y + r.h - b.h) };
  });
  return out;
}
// распределить центры поровну между крайними: axis "x" | "y"; нужно три элемента и больше
export function distribute(bs, axis) {
  if (bs.length < 3) return {};
  const c = b => axis === "x" ? b.x + b.w / 2 : b.y + b.h / 2, s = [...bs].sort((a, b) => c(a) - c(b));
  const first = c(s[0]), step = (c(s[s.length - 1]) - first) / (s.length - 1), out = {};
  s.forEach((b, i) => { out[b.id] = axis === "x" ? { x: r2(first + step * i - b.w / 2) } : { y: r2(first + step * i - b.h / 2) }; });
  return out;
}
// одинаковый размер по первому выбранному: what "w" | "h"
export function sameSize(bs, what) {
  const out = {}; bs.slice(1).forEach(b => { out[b.id] = { [what]: bs[0][what] }; }); return out;
}
// порядок рисования: dir "up" | "down" | "top" | "bottom"; последний в списке рисуется поверх
export function reorder(blocks, ids, dir) {
  const set = new Set(ids), list = [...blocks];
  if (dir === "top") return [...list.filter(b => !set.has(b.id)), ...list.filter(b => set.has(b.id))];
  if (dir === "bottom") return [...list.filter(b => set.has(b.id)), ...list.filter(b => !set.has(b.id))];
  const idx = list.map((b, i) => set.has(b.id) ? i : -1).filter(i => i >= 0);
  if (dir === "up") for (let j = idx.length - 1; j >= 0; j--) { const i = idx[j]; if (i < list.length - 1 && !set.has(list[i + 1].id)) [list[i], list[i + 1]] = [list[i + 1], list[i]]; }
  if (dir === "down") for (const i of idx) if (i > 0 && !set.has(list[i - 1].id)) [list[i], list[i - 1]] = [list[i - 1], list[i]];
  return list;
}
// копии элементов со сдвигом (Ctrl+D, вставка): новые id, имя «… (копия)»; копии группы — своя новая группа
export function duplicate(bs, d = 5) {
  const gs = {}, g = id => id && (gs[id] ||= newId("group"));
  return bs.map(b => ({ ...JSON.parse(JSON.stringify(b)), id: newId(b.kind), x: r2(b.x + d), y: r2(b.y + d), name: `${label(b)} (копия)`, locked: false,
    group: g(b.group) || undefined, was: undefined }));
}
// шаг делений линейки: подписи не чаще, чем через minPx пикселей экрана; k — пикселей в мм
export function rulerStep(k, minPx = 50) {
  return [1, 2, 5, 10, 20, 50, 100, 200, 500].find(v => v * k >= minPx) || 1000;
}
