/* ГРАДО 2 · рамка вида (#119): вид = что видно (слои, оформление, подложка) + где (рамка на карте). Рамку рисуют на
   карте с пропорциями или размером, блок «Карта» на листе выбирает вид и показывает его рамку — как фрейм InDesign
   или карта макета QGIS. Здесь чистые расчёты в метрах МСК без OpenLayers и Vue: пропорции, рамка по двум углам,
   середина и масштаб блока по рамке («Вписать» / «Заполнить», круглый масштаб).
   Зовут viewframesmap.js (рамки на карте), ViewsPanel.vue, SheetPanel.vue и sheetmaps.js; проверяет viewframes.test.js. */
import { SCALES } from "./sheet/model.js";

// пропорции рамки: r — длинная сторона к короткой; ориентация (лёжа или стоя) берётся из того, как тянули рамку
export const ASPECTS = [
  { id: "free", t: "Свободно" },
  { id: "a", t: "А-формат (1 : 1,41)", r: Math.SQRT2 },
  { id: "4:3", t: "4 : 3", r: 4 / 3 },
  { id: "16:9", t: "16 : 9", r: 16 / 9 },
  { id: "3:2", t: "3 : 2", r: 1.5 },
  { id: "1:1", t: "1 : 1", r: 1 },
];
/* число пропорций: id из ASPECTS или свои «a:b» (в том числе «5,5:2»); свободно или ошибка — null */
export function ratioOf(aspect) {
  const known = ASPECTS.find(a => a.id === aspect); if (known) return known.r ?? null;
  const m = /^\s*(\d+(?:[.,]\d+)?)\s*[:x×/]\s*(\d+(?:[.,]\d+)?)\s*$/.exec(String(aspect || ""));
  if (!m) return null;
  const a = +m[1].replace(",", "."), b = +m[2].replace(",", ".");
  return a > 0 && b > 0 ? Math.max(a, b) / Math.min(a, b) : null;
}
/* стороны w × h (м) под пропорции: лёжа, если w ≥ h; держится большая сторона — рамка не уменьшается от смены пропорций */
export function withRatio(w, h, r) {
  if (!r) return [w, h];
  return w >= h ? [w, w / r] : [h / r, h];
}
/* рамка по двум углам (МСК, м): a — неподвижный угол, b — где курсор; с пропорциями рамка охватывает протянутое */
export function fromCorners(a, b, r) {
  let w = Math.abs(b[0] - a[0]), h = Math.abs(b[1] - a[1]);
  if (r) { if (w >= h) h = Math.max(h, w / r), w = h * r; else w = Math.max(w, h / r), h = w * r; }
  const sx = Math.sign(b[0] - a[0]) || 1, sy = Math.sign(b[1] - a[1]) || 1;
  return { c: [a[0] + sx * w / 2, a[1] + sy * h / 2], w, h };
}
/* углы рамки (МСК) по середине c и сторонам: [ЮЗ, ЮВ, СВ, СЗ] */
export const cornersM = (c, w, h) => [[c[0] - w / 2, c[1] - h / 2], [c[0] + w / 2, c[1] - h / 2], [c[0] + w / 2, c[1] + h / 2], [c[0] - w / 2, c[1] + h / 2]];

/* масштаб блока листа (w × h мм) по рамке (м): «Вписать» — рамка видна целиком, «Заполнить» — блок закрыт целиком.
   round — ближайший стандартный: у «Вписать» мельче (рамка не обрежется), у «Заполнить» — крупнее (полей не будет). */
export function blockScale(b, frame, { fit = "fit", round = true } = {}) {
  if (!(b.w > 0 && b.h > 0 && frame?.w > 0 && frame?.h > 0)) return 0;
  const kx = frame.w / b.w * 1000, ky = frame.h / b.h * 1000, s = fit === "fill" ? Math.min(kx, ky) : Math.max(kx, ky);
  if (!round) return Math.round(s);
  if (fit === "fill") return [...SCALES].reverse().find(v => v <= s * 1.0001) || Math.round(s);
  return SCALES.find(v => v >= s * 0.9999) || Math.round(s);
}
/* середина и масштаб блока карты по виду: { center, scale } или null, если у вида нет рамки */
export function blockFromView(b, view) {
  const f = view?.frame; if (!f?.center || !(f.w > 0)) return null;
  return { center: f.center.map(v => +(+v).toFixed(7)), scale: blockScale(b, f, { fit: b.fit || "fit", round: b.round !== false }) };
}
/* высота блока под пропорции рамки при той же ширине (кнопка «Блок по рамке») */
export const blockHeightFor = (b, frame) => frame?.w > 0 ? Math.round(b.w * frame.h / frame.w * 100) / 100 : b.h;
/* подпись рамки на карте и в списке: «Ограничения · 820 × 580 м», от 10 км — «12,3 × 8,7 км» */
export function frameLabel(name, f) {
  const km = Math.max(f.w, f.h) >= 10000, n = v => km ? String(Math.round(v / 100) / 10).replace(".", ",") : String(Math.round(v)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return `${name} · ${n(f.w)} × ${n(f.h)} ${km ? "км" : "м"}`;
}
