/* ГРАДО 2 · рисование элементов листа на Konva для редактора раскладки: по элементу модели (model.js) — группа Konva
   в мм листа. Карта пока заглушка с масштабом и охватом; легенда, таблица, надпись, картинка, стрелка севера,
   масштабная линейка, фигуры и линия рисуются как на листе. Зовёт SheetEditor.vue; проверяется глазами (снимки). */
import Konva from "konva";
import { PT, groundSize, fmtM, fmtScale, scalebarStep, linkedScale } from "./model.js";

export const INK = "#1a1a1a";
const SANS = "PT Sans, Inter, system-ui, sans-serif";
const imgCache = new Map();

// оформление: фон под содержимым, рамка поверх
const bgRect = b => b.bg?.on ? new Konva.Rect({ width: b.w, height: b.h, fill: b.bg.color || "#fff", listening: false }) : null;
const frameRect = b => b.frame?.on ? new Konva.Rect({ width: b.w, height: b.h, stroke: b.frame.color || INK, strokeWidth: b.frame.width || .25, listening: false }) : null;
// прозрачная подложка: щелчок в любом месте элемента выбирает его
const hit = b => new Konva.Rect({ width: b.w, height: b.h, fill: "rgba(0,0,0,0.001)" });

function mapContent(g, b) {
  g.add(new Konva.Rect({ width: b.w, height: b.h, fill: "#eef2ec", listening: false }));
  // сетка «как на карте»: даёт видеть размер и поворот видового окна, пока карта не подключена
  const step = 1000 / b.scale * (b.scale <= 2000 ? 100 : b.scale <= 10000 ? 500 : 1000), lines = [];
  if (step > 3) {
    for (let x = step; x < b.w; x += step) lines.push([x, 0, x, b.h]);
    for (let y = step; y < b.h; y += step) lines.push([0, y, b.w, y]);
  }
  lines.slice(0, 400).forEach(p => g.add(new Konva.Line({ points: p, stroke: "#d6ded2", strokeWidth: .2, listening: false })));
  const size = Math.max(2, Math.min(5, b.w / 30, b.h / 8));
  const t = b.scale > 0 ? `Карта · ${fmtScale(b.scale)}\n${groundSize(b).map(fmtM).join(" × ")} на местности` : "Карта · масштаб не задан";
  g.add(new Konva.Text({ width: b.w, height: b.h, align: "center", verticalAlign: "middle", text: t, fontSize: size, lineHeight: 1.35,
    fontFamily: SANS, fill: "#5b6b57", listening: false }));
}
function legendContent(g, b) {
  const pad = 3, row = 6.5, fs = 2.8;
  g.add(new Konva.Text({ x: pad, y: pad, width: b.w - pad * 2, text: b.title || "", fontSize: 3.4, fontStyle: "bold", fontFamily: SANS, fill: INK, listening: false }));
  (b.items || []).forEach((it, i) => {
    const y = pad + 7 + i * row; if (y + row > b.h) return;
    const sw = 8, sh = 4;
    if (it.s === "line") g.add(new Konva.Line({ points: [pad, y + sh / 2, pad + sw, y + sh / 2], stroke: it.c, strokeWidth: .6, dash: it.dash, listening: false }));
    else g.add(new Konva.Rect({ x: pad, y, width: sw, height: sh, fill: it.f || "transparent", stroke: it.c, strokeWidth: .3, listening: false }));
    g.add(new Konva.Text({ x: pad + sw + 2.5, y: y + .3, width: b.w - pad * 2 - sw - 2.5, text: it.t, fontSize: fs, fontFamily: SANS, fill: INK, wrap: "none", ellipsis: true, listening: false }));
  });
}
function tableContent(g, b) {
  const rows = Math.max(1, b.rows || 1), cols = Math.max(1, b.cols || 1), th = b.title ? 6 : 0, rh = (b.h - th) / (rows + 1), cw = b.w / cols;
  if (b.title) g.add(new Konva.Text({ x: 0, y: .8, width: b.w, align: "center", text: b.title, fontSize: 3.2, fontStyle: "bold", fontFamily: SANS, fill: INK, listening: false }));
  g.add(new Konva.Rect({ x: 0, y: th, width: b.w, height: rh, fill: "#f1f3f5", listening: false }));
  for (let r = 0; r <= rows + 1; r++) g.add(new Konva.Line({ points: [0, th + r * rh, b.w, th + r * rh], stroke: INK, strokeWidth: r === 1 ? .35 : .18, listening: false }));
  for (let c = 0; c <= cols; c++) g.add(new Konva.Line({ points: [c * cw, th, c * cw, b.h], stroke: INK, strokeWidth: .18, listening: false }));
  ["Показатель", "Ед.", "Значение"].slice(0, cols).forEach((t, c) => g.add(new Konva.Text({ x: c * cw + 1, y: th + rh / 2 - 1.3, width: cw - 2, text: t, fontSize: 2.6, fontStyle: "bold", fontFamily: SANS, fill: INK, wrap: "none", ellipsis: true, listening: false })));
}
function textContent(g, b) {
  const style = [b.bold && "bold", b.italic && "italic"].filter(Boolean).join(" ") || "normal";
  g.add(new Konva.Text({ width: b.w, height: b.h, text: b.text || "", fontSize: (b.size || 12) * PT, fontFamily: `${b.font || "PT Sans"}, ${SANS}`, fontStyle: style,
    fill: b.color || INK, align: b.align || "left", verticalAlign: b.valign || "top", lineHeight: 1.15, listening: false }));
}
function pictureContent(g, b, redraw) {
  if (!b.src) {
    g.add(new Konva.Rect({ width: b.w, height: b.h, fill: "#f6f7f9", stroke: "#c5cbd3", strokeWidth: .25, dash: [1.5, 1], listening: false }));
    g.add(new Konva.Text({ width: b.w, height: b.h, align: "center", verticalAlign: "middle", text: "Картинка\nфайл — в свойствах", fontSize: Math.min(3.2, b.w / 12), fontFamily: SANS, fill: "#7a8491", listening: false }));
    return;
  }
  let img = imgCache.get(b.src);
  if (!img) { img = new Image(); img.onload = () => redraw?.(); img.src = b.src; imgCache.set(b.src, img); }
  if (!img.complete || !img.naturalWidth) return;
  // вписать с сохранением пропорций (как «Масштабировать» в QGIS)
  const k = Math.min(b.w / img.naturalWidth, b.h / img.naturalHeight), w = img.naturalWidth * k, h = img.naturalHeight * k;
  g.add(new Konva.Image({ image: img, x: (b.w - w) / 2, y: (b.h - h) / 2, width: w, height: h, listening: false }));
}
function northContent(g, b) {
  g.add(new Konva.Line({ points: [b.w / 2, b.h * .28, b.w * .85, b.h, b.w / 2, b.h * .8], closed: true, fill: INK, listening: false }));
  g.add(new Konva.Line({ points: [b.w / 2, b.h * .28, b.w * .15, b.h, b.w / 2, b.h * .8], closed: true, fill: "#fff", stroke: INK, strokeWidth: .25, listening: false }));
  g.add(new Konva.Text({ x: 0, y: 0, width: b.w, align: "center", text: "С", fontSize: b.h * .26, fontStyle: "bold", fontFamily: SANS, fill: INK, listening: false }));
}
function scalebarContent(g, b, sheet) {
  const sc = linkedScale(b, sheet), stepM = scalebarStep({ ...b, scale: sc }), seg = stepM * 1000 / sc, bh = Math.min(1.6, b.h / 4);
  for (let i = 0; i < 4; i++) g.add(new Konva.Rect({ x: i * seg, y: b.h - bh - 3, width: seg, height: bh, fill: i % 2 ? "#fff" : INK, stroke: INK, strokeWidth: .2, listening: false }));
  for (let i = 0; i <= 4; i++) g.add(new Konva.Text({ x: i * seg - 8, y: b.h - 2.5, width: 16, align: "center", text: i ? fmtM(stepM * i).replace(" ", " ") : "0", fontSize: 2, fontFamily: SANS, fill: INK, listening: false }));
  g.add(new Konva.Text({ x: 0, y: Math.max(0, b.h - bh - 7), text: fmtScale(sc), fontSize: 2.4, fontFamily: SANS, fill: INK, listening: false }));
}

/* элемент → группа Konva; redraw — перерисовать лист, когда догрузится картинка */
export function blockNode(b, sheet, redraw) {
  const g = new Konva.Group({ id: b.id, x: b.x, y: b.y, rotation: b.rotation || 0, opacity: b.opacity ?? 1, name: "block",
    draggable: !b.locked, listening: !b.locked, visible: !b.hidden });
  g.add(hit(b));
  if (b.kind === "ellipse") {
    g.add(new Konva.Ellipse({ x: b.w / 2, y: b.h / 2, radiusX: b.w / 2, radiusY: b.h / 2, fill: b.bg?.on ? b.bg.color : undefined,
      stroke: b.frame?.on ? b.frame.color : undefined, strokeWidth: b.frame?.width || .25, listening: false }));
    return g;
  }
  if (b.kind === "line") {
    const c = b.frame?.color || INK, wd = b.frame?.width || .5;
    g.add(b.arrow ? new Konva.Arrow({ points: [0, b.h / 2, b.w, b.h / 2], stroke: c, fill: c, strokeWidth: wd, pointerLength: 2.5, pointerWidth: 2, listening: false })
      : new Konva.Line({ points: [0, b.h / 2, b.w, b.h / 2], stroke: c, strokeWidth: wd, listening: false }));
    return g;
  }
  const bg = bgRect(b); if (bg) g.add(bg);
  ({ map: mapContent, legend: legendContent, table: tableContent, text: textContent, picture: pictureContent, north: northContent, scalebar: scalebarContent }[b.kind]
    || (() => {}))(g, b, b.kind === "scalebar" ? sheet : redraw);
  const fr = frameRect(b); if (fr) g.add(fr);
  return g;
}
