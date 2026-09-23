/* ГРАДО 2 · точное черчение, как в AutoCAD.
   · У курсора — длина текущего отрезка и его угол, для полигона ещё площадь, для прямоугольника — стороны.
   · Ввод с клавиатуры во время рисования: «25» — точка в 25 м по направлению курсора; «25<90» — длина и угол;
     «@10;-5» — смещение от последней точки; «12345,6;6789» — точка в координатах МГГТ. Enter вводит, Esc отменяет.
   · Орто (F8 или флажок, Shift — на время): отрезок только вдоль или поперёк предыдущего (первый — по осям).
   · Привязка показывает, к чему притянулась точка: вершина, середина, пересечение, на линии.
   Все длины, углы и площади считаются в МГГТ — в той же системе, в которой программа выгружает DXF и листы:
   X на восток, Y на север, угол от направления на восток против часовой стрелки. */

(() => {                       // своя область видимости: у скриптов без модулей общий глобальный лексический контекст
const toM = c => MGGT.fromWgs(ol.proj.toLonLat(c));
const fromM = m => ol.proj.fromLonLat(MGGT.toWgs(m));
const CAD = { ortho: false, shift: false, draw: null, tool: null, src: null, sketch: null, cursor: null, snapped: null };
try { CAD.ortho = localStorage.getItem("grado2.ortho") === "1"; } catch { }

/* прямоугольник по осям МГГТ, а не по осям карты: в DXF он выходит ровным */
function boxM(coords, geom) {
  const a = toM(coords[0]), b = toM(coords[coords.length - 1]);
  const ring = [[a[0], a[1]], [b[0], a[1]], [b[0], b[1]], [a[0], b[1]], [a[0], a[1]]].map(fromM);
  if (geom) geom.setCoordinates([ring]); else geom = new ol.geom.Polygon([ring]);
  return geom;
}

/* зафиксированные вершины текущего рисунка (без точки под курсором), координаты карты */
function fixedPts() {
  const g = CAD.sketch?.getGeometry(); if (!g) return [];
  if (CAD.tool === "rect") return [g.getCoordinates()[0][0]];          // первый угол: boxM начинает кольцо с него
  if (g.getType() === "LineString") return g.getCoordinates().slice(0, -1);
  if (g.getType() === "Polygon") return openRing(g.getCoordinates()[0]).slice(0, -1);
  return [];
}
/* кольцо недорисованного полигона: после первой вершины [v0, курсор], дальше [v0, …, курсор, v0] — замыкающую точку снимаем */
function openRing(r) { return r.length > 2 && same(r[0], r[r.length - 1]) ? r.slice(0, -1) : r; }
const same = (p, q) => Math.abs(p[0] - q[0]) < 1e-6 && Math.abs(p[1] - q[1]) < 1e-6;
const ang = (p, q) => Math.atan2(q[1] - p[1], q[0] - p[0]);
const deg = r => ((r * 180 / Math.PI) % 360 + 360) % 360;

/* орто: направление кратно 90° к предыдущему отрезку; длина — проекция курсора на это направление (как в AutoCAD) */
function orthoPoint(a, prev, c) {
  const A = toM(a), C = toM(c), L = Math.hypot(C[0] - A[0], C[1] - A[1]); if (L < 1e-6) return c;
  const ref = prev ? ang(toM(prev), A) : 0, cur = ang(A, C), q = Math.round((cur - ref) / (Math.PI / 2)) * (Math.PI / 2) + ref;
  const d = L * Math.cos(cur - q);
  return fromM([A[0] + d * Math.cos(q), A[1] + d * Math.sin(q)]);
}
const orthoOn = () => CAD.ortho !== CAD.shift;

/* перехват событий карты до привязки и рисования: орто подменяет координату, привязка потом может её перебить */
const cadI = new ol.interaction.Interaction({ handleEvent: e => {
  if (!CAD.draw || !e.coordinate) return true;
  CAD.shift = !!e.originalEvent?.shiftKey;
  const fx = fixedPts();
  if (fx.length && CAD.tool !== "rect" && orthoOn() && /^(pointermove|pointerdown|pointerup|click|singleclick|dblclick)$/.test(e.type)) {
    const c = orthoPoint(fx[fx.length - 1], fx[fx.length - 2], e.coordinate);
    e.coordinate = c; e.pixel = e.map.getPixelFromCoordinate(c);
  }
  if (e.type === "pointermove") { CAD.cursor = e.coordinate; tip(); }
  return true;
} });

/* ---------- подсказка у курсора ---------- */
const tipEl = document.createElement("div"); tipEl.className = "cadtip"; tipEl.hidden = true;
const tipOv = new ol.Overlay({ element: tipEl, offset: [16, 14], positioning: "top-left", stopEvent: false });
mMain.addOverlay(tipOv);
const shoelace = pts => { let s = 0; for (let i = 0; i < pts.length; i++) { const p = pts[i], q = pts[(i + 1) % pts.length]; s += p[0] * q[1] - q[0] * p[1]; } return Math.abs(s) / 2; };
function tip() {
  const g = CAD.sketch?.getGeometry(), lines = [];
  if (g && CAD.tool === "rect") {
    const r = g.getCoordinates()[0].map(toM), w = Math.abs(r[1][0] - r[0][0]), h = Math.abs(r[2][1] - r[1][1]);
    lines.push(`${fmt(w, 2)} × ${fmt(h, 2)} м`, `площадь ${fmt(w * h, 1)} м²`);
  } else if (g && /LineString|Polygon/.test(g.getType())) {
    const pts = (g.getType() === "Polygon" ? openRing(g.getCoordinates()[0]) : g.getCoordinates()).map(toM);
    if (pts.length >= 2) {
      const a = pts[pts.length - 2], b = pts[pts.length - 1], L = Math.hypot(b[0] - a[0], b[1] - a[1]);
      lines.push(`${fmt(L, 2)} м · ${fmt(deg(ang(a, b)), 1)}°` + (orthoOn() ? " · орто" : ""));
      let tot = 0; for (let i = 1; i < pts.length; i++) tot += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
      if (g.getType() === "Polygon") { if (pts.length >= 3) lines.push(`площадь ${fmt(shoelace(pts), 1)} м²`); }
      else if (pts.length > 2) lines.push(`всего ${fmt(tot, 2)} м`);
    }
  }
  if (CAD.snapped) lines.push("привязка: " + CAD.snapped);
  tipEl.hidden = !lines.length || !CAD.cursor || !CAD.draw;
  if (!tipEl.hidden) { tipEl.innerHTML = lines.map(esc).join("<br>"); tipOv.setPosition(CAD.cursor); }
}

/* ---------- метка привязки ---------- */
const snapSrc = new ol.source.Vector();
/* метка крупнее точки рисования и другого цвета, чтобы не прятаться под ней: квадрат — вершина, треугольник — середина,
   косой крест — пересечение, ромб — точка на линии (обозначения как у объектных привязок AutoCAD) */
const MK = new ol.style.Stroke({ color: "#e8590c", width: 2.2 });
const MARKS = {
  "вершина": new ol.style.RegularShape({ points: 4, radius: 10, angle: Math.PI / 4, stroke: MK }),
  "середина": new ol.style.RegularShape({ points: 3, radius: 11, stroke: MK }),
  "пересечение": new ol.style.RegularShape({ points: 4, radius1: 11, radius2: 0, angle: Math.PI / 4, stroke: MK }),
  "на линии": new ol.style.RegularShape({ points: 4, radius: 10, stroke: MK }) };
const markStyle = kind => new ol.style.Style({ image: MARKS[kind] || MARKS["вершина"] });
mMain.addLayer(new ol.layer.Vector({ source: snapSrc, zIndex: 130, style: f => markStyle(f.get("kind")) }));
const flat = g => { const out = []; const walk = c => typeof c[0] === "number" ? out.push(c) : c.forEach(walk); walk(g.getCoordinates()); return out; };
function snapKind(e) {
  if (e.segment && !same(e.segment[0], e.segment[1])) return "на линии";
  const g = e.feature?.getGeometry(); if (!g?.getCoordinates) return "вершина";
  const c = flat(g); if (c.some(p => same(p, e.vertex))) return "вершина";
  for (let i = 1; i < c.length; i++) if (same([(c[i - 1][0] + c[i][0]) / 2, (c[i - 1][1] + c[i][1]) / 2], e.vertex)) return "середина";
  return "пересечение";
}
/* середины отрезков — нулевые отрезки [m, m]: привязка к вершине ловит их как точку */
const withMids = rings => rings.flatMap(r => r.slice(1).flatMap((b, i) => { const a = r[i]; const m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]; return [[a, b], [m, m]]; }));
const SEGMENTERS = {
  LineString: g => withMids([g.getCoordinates()]), MultiLineString: g => withMids(g.getCoordinates()),
  Polygon: g => withMids(g.getCoordinates()), MultiPolygon: g => withMids(g.getCoordinates().flat()) };
function watchSnap(snap) {
  snap.on("snap", e => { const k = snapKind(e); CAD.snapped = k; snapSrc.clear(true); snapSrc.addFeature(new ol.Feature({ geometry: new ol.geom.Point(e.vertex), kind: k })); tip(); });
  snap.on("unsnap", () => { CAD.snapped = null; snapSrc.clear(); tip(); });
  return snap;
}
const makeSnap = opts => watchSnap(new ol.interaction.Snap({ pixelTolerance: 10, segmenters: SEGMENTERS, ...opts }));

/* ---------- подключение к инструменту рисования ---------- */
function attach(d, tool, src) {
  CAD.draw = d; CAD.tool = tool; CAD.src = src; CAD.sketch = null;
  d.on("drawstart", e => { CAD.sketch = e.feature; e.feature.getGeometry().on("change", tip); tip(); });
  const done = () => { CAD.sketch = null; tip(); };
  d.on("drawend", done); d.on("drawabort", done);
}
function detach() { CAD.draw = null; CAD.tool = null; CAD.sketch = null; CAD.snapped = null; snapSrc.clear(); hideInput(); tip(); }

/* ---------- ввод с клавиатуры ---------- */
const inEl = document.createElement("input"); inEl.className = "cadin"; inEl.hidden = true; inEl.spellcheck = false;
inEl.placeholder = "25 · 25<90 · @10;5 · x;y"; inEl.title = "Длина по курсору · длина<угол · @смещение по X;Y · X;Y в МГГТ. Enter — ввести, Esc — отмена";
mMain.getOverlayContainerStopEvent().appendChild(inEl);        // слой оверлеев со stopEvent: щелчок по полю не ставит вершину
const NUM = "(-?\\d+(?:[.,]\\d+)?)";
const num = s => +s.replace(",", ".");
function hideInput() { inEl.hidden = true; inEl.value = ""; inEl.classList.remove("bad"); }
function showInput(ch) {
  const px = CAD.cursor ? mMain.getPixelFromCoordinate(CAD.cursor) : [40, 40];
  const below = tipEl.hidden ? 14 : 14 + tipEl.offsetHeight + 4;          // под подсказкой, чтобы не закрывать её строки
  inEl.style.left = `${Math.round(px[0] + 16)}px`; inEl.style.top = `${Math.round(px[1] + below)}px`;
  inEl.hidden = false; inEl.value = ch; inEl.focus();
}
/* строка → точка в координатах карты; ошибка — текстом для строки состояния */
function parse(s) {
  s = s.trim(); const fx = fixedPts(), a = fx[fx.length - 1];
  let m;
  if ((m = s.match(new RegExp(`^@${NUM}\\s*[; ]\\s*${NUM}$`)))) {
    if (!a) return "Смещение @ считается от последней точки: сначала поставьте первую.";
    const A = toM(a); return fromM([A[0] + num(m[1]), A[1] + num(m[2])]);
  }
  if ((m = s.match(new RegExp(`^${NUM}\\s*[; ]\\s*${NUM}$`)))) return fromM([num(m[1]), num(m[2])]);
  if ((m = s.match(new RegExp(`^@?${NUM}\\s*<\\s*${NUM}$`)))) {
    if (!a) return "Длина и угол считаются от последней точки: сначала поставьте первую.";
    const A = toM(a), L = num(m[1]), q = num(m[2]) * Math.PI / 180; return fromM([A[0] + L * Math.cos(q), A[1] + L * Math.sin(q)]);
  }
  if ((m = s.match(new RegExp(`^${NUM}$`)))) {
    if (!a) return "Одно число — это длина от последней точки. Первую точку задайте щелчком или координатами X;Y.";
    if (CAD.tool === "rect") return "Для прямоугольника введите противоположный угол: @ширина;высота.";
    const A = toM(a), C = CAD.cursor ? toM(CAD.cursor) : [A[0] + 1, A[1]], q = ang(A, C), L = num(m[1]);
    return fromM([A[0] + L * Math.cos(q), A[1] + L * Math.sin(q)]);
  }
  return "Не понял ввод. Примеры: 25 · 25<90 · @10;-5 · 12345,6;6789,1 (X;Y в МГГТ).";
}
/* готовый объект — тем же путём, что и щелчок мышью: событие завершения, затем в источник */
function commit(f) { const d = CAD.draw; d.abortDrawing(); d.dispatchEvent({ type: "drawend", feature: f }); CAD.src?.addFeature(f); }
function applyInput() {
  const r = parse(inEl.value); if (typeof r === "string") { inEl.classList.add("bad"); setHint(r); return; }
  hideInput(); const d = CAD.draw, t = CAD.tool;
  if (t === "point") commit(new ol.Feature(new ol.geom.Point(r)));
  else if (t === "rect") { if (!CAD.sketch) d.appendCoordinates([r]); else commit(new ol.Feature(boxM([fixedPts()[0], r]))); }
  else d.appendCoordinates([r]);
  CAD.cursor = r; mMain.render(); tip();
}
function finish() {
  const fx = fixedPts(), need = CAD.tool === "line" || CAD.tool === "mlen" ? 2 : 3;
  if (!CAD.sketch || fx.length < need) { setHint(`Завершить можно, когда поставлено не меньше ${need} точек.`); return; }
  CAD.draw.finishDrawing();                 // точку под курсором OpenLayers в объект не берёт
}
inEl.addEventListener("keydown", e => {
  e.stopPropagation();
  if (e.key === "Enter") { e.preventDefault(); inEl.value.trim() ? applyInput() : (hideInput(), finish()); }
  else if (e.key === "Escape") { e.preventDefault(); hideInput(); mMain.getTargetElement().focus?.(); }
});
inEl.addEventListener("input", () => inEl.classList.remove("bad"));
// первая цифра, «@» или «-» во время рисования открывает поле ввода у курсора
addEventListener("keydown", e => {
  if (!CAD.draw || e.target.matches?.("input,select,textarea") || e.metaKey || e.ctrlKey || e.altKey) return;
  if (/^[0-9@.,\-]$/.test(e.key)) { e.preventDefault(); e.stopPropagation(); showInput(e.key); }
  else if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); finish(); }
}, true);

function setOrtho(on) {
  CAD.ortho = on; try { localStorage.setItem("grado2.ortho", on ? "1" : "0"); } catch { }
  const b = document.getElementById("orthoT"); if (b) b.checked = on; tip();
}
addEventListener("keydown", e => { if (e.key === "F8") { e.preventDefault(); setOrtho(!CAD.ortho); setHint(`Орто ${CAD.ortho ? "включено" : "выключено"} (F8).`); } });

window.CAD = Object.assign(CAD, { i: cadI, attach, detach, boxM, makeSnap, setOrtho, toM, fromM, parse });
})();
