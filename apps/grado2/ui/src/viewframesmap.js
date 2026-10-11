/* ГРАДО 2 · рамки видов на карте нового интерфейса (#119): вид = слои + рамка «где». Пока открыто окно «Виды» или
   «Макет листа», рамка каждого вида — фиолетовый прямоугольник с подписью «Ограничения · 820 × 580 м».
   «Нарисовать рамку» (vframes.draw = id вида): тянешь прямоугольник, пропорции — из vframes.aspect (Shift — свободно).
   Щелчок по рамке выбирает вид; выбранную тянут внутри (сдвиг) и за угол (размер, пропорции держатся, Shift — свободно).
   Рамка пишется в project.views[].frame ({ center: [долгота, широта], w, h — метры МСК, aspect }) — её берут блоки карты
   листов (SheetPanel.vue, viewframes.js blockFromView). Расчёты — viewframes.js; устроено как albumframes.js. */
import Feature from "ol/Feature.js";
import Polygon from "ol/geom/Polygon.js";
import MultiPoint from "ol/geom/MultiPoint.js";
import Point from "ol/geom/Point.js";
import PointerInteraction from "ol/interaction/Pointer.js";
import VectorLayer from "ol/layer/Vector.js";
import VectorSource from "ol/source/Vector.js";
import { boundingExtent } from "ol/extent.js";
import { fromLonLat, toLonLat } from "ol/proj.js";
import { Fill, RegularShape, Stroke, Style, Text } from "ol/style.js";
import { reactive, watch } from "vue";
import * as mskMod from "../../web/msk.js";
import { project } from "./store.js";
import { cadApi } from "./cad.js";
import { cornersM, fromCorners, frameLabel, ratioOf } from "./viewframes.js";

const MSK = globalThis.MSK || mskMod.default || mskMod;
const VIOLET = "#7a3fd1";
const toM = c => MSK.fromWgs(toLonLat(c)), fromM = m => fromLonLat(MSK.toWgs(m));

/* общее состояние: on — сколько окон просят рамки (Виды, Макет листа); draw — id вида, которому рисуют рамку;
   sel — выбранный вид; aspect — пропорции новой рамки; fit — «приблизить к рамке вида» (id); msg — подсказка над картой */
export const vframes = reactive({ on: 0, draw: "", sel: "", aspect: "a", fit: "", msg: "" });
export const viewOf = id => project.views.find(v => v.id === id);
export const frameCorners = f => cornersM(MSK.fromWgs(f.center), f.w, f.h);
/* рамка по текущему экрану карты (центр и охват окна «Карта» с полями 10 %) с пропорциями aspect */
export function frameFromExtent(ext, aspect) {
  const a = toM([ext[0], ext[1]]), b = toM([ext[2], ext[3]]);
  let w = Math.abs(b[0] - a[0]) * .8, h = Math.abs(b[1] - a[1]) * .8;
  const r = ratioOf(aspect); if (r) { if (w >= h) w = Math.min(w, h * r), h = w / r; else h = Math.min(h, w * r), w = h / r; }
  const c = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  return { center: MSK.toWgs(c).map(v => +v.toFixed(7)), w: Math.round(w), h: Math.round(h), aspect };
}

export function attachViewFrames(map) {
  const src = new VectorSource();
  let drag = null, live = null;          // live — рамка, которую сейчас тянут или рисуют: { id, c (МСК), w, h }
  const grip = new Style({ image: new RegularShape({ points: 4, radius: 6, angle: Math.PI / 4, fill: new Fill({ color: "#fff" }), stroke: new Stroke({ color: VIOLET, width: 2 }) }),
    geometry: f => new MultiPoint(f.getGeometry().getCoordinates()[0].slice(0, 4)) });
  const layer = new VectorLayer({ source: src, zIndex: 9989, style: f => {
    const id = f.get("id"), on = id === vframes.sel, tl = f.getGeometry().getCoordinates()[0][3];
    return [new Style({ stroke: new Stroke({ color: VIOLET, width: on ? 2.5 : 1.5, lineDash: f.get("draft") ? [6, 4] : undefined }),
        fill: new Fill({ color: on ? "rgba(122,63,209,.06)" : "rgba(122,63,209,.001)" }) }),
      new Style({ geometry: new Point(tl), text: new Text({ text: f.get("label"), font: `${on ? 600 : 500} 12px Onest, system-ui, sans-serif`, textAlign: "left", textBaseline: "bottom", offsetY: -5,
        fill: new Fill({ color: VIOLET }), stroke: new Stroke({ color: "#fff", width: 3 }) }) }),
      ...(on && !f.get("draft") ? [grip] : [])];
  } });
  map.addLayer(layer);

  const shown = () => vframes.on > 0 || !!vframes.draw;
  const geomOf = v => live && live.id === v.id ? live : v.frame ? { c: MSK.fromWgs(v.frame.center), w: v.frame.w, h: v.frame.h } : null;
  function redraw() {
    src.clear(true); layer.setVisible(shown()); if (!shown()) return;
    project.views.forEach(v => {
      const g = geomOf(v); if (!g) return;
      const r = cornersM(g.c, g.w, g.h).map(fromM), f = new Feature(new Polygon([[...r, r[0]]]));
      f.setProperties({ id: v.id, label: frameLabel(v.name, g), draft: !v.frame }); src.addFeature(f);
    });
  }
  const hit = px => map.forEachFeatureAtPixel(px, f => f.get("id"), { layerFilter: l => l === layer, hitTolerance: 6 });
  const hitGrip = px => {
    const v = viewOf(vframes.sel), g = v && geomOf(v); if (!g) return -1;
    return cornersM(g.c, g.w, g.h).map(fromM).findIndex(c => { const p = map.getPixelFromCoordinate(c); return Math.hypot(p[0] - px[0], p[1] - px[1]) < 10; });
  };
  const other = px => map.forEachFeatureAtPixel(px, () => true, { layerFilter: l => l !== layer && !!l.get("key"), hitTolerance: 3 });
  const save = (v, g) => { v.frame = { center: MSK.toWgs(g.c).map(x => +x.toFixed(7)), w: Math.round(g.w * 10) / 10, h: Math.round(g.h * 10) / 10, aspect: v.frame?.aspect || vframes.aspect }; };

  const it = new PointerInteraction({
    handleDownEvent(e) {
      if (!shown() || e.originalEvent.button || cadApi.active?.()) return false;
      const m = toM(e.coordinate);
      if (vframes.draw) { drag = { mode: "draw", id: vframes.draw, a: m }; return true; }
      const gi = hitGrip(e.pixel);
      if (gi >= 0) { const v = viewOf(vframes.sel), g = geomOf(v); drag = { mode: "size", id: v.id, a: cornersM(g.c, g.w, g.h)[(gi + 2) % 4] }; return true; }
      const id = hit(e.pixel);
      if (!id || (id !== vframes.sel && other(e.pixel))) return false;   // объект слоя внутри рамки — выбор объекта
      vframes.sel = id; redraw();
      const g = geomOf(viewOf(id)); if (!g) return true;
      drag = { mode: "move", id, m0: m, c0: g.c, w: g.w, h: g.h };
      return true;
    },
    handleDragEvent(e) {
      if (!drag) return;
      const m = toM(e.coordinate), v = viewOf(drag.id); if (!v) return;
      if (drag.mode === "move") live = { id: v.id, c: [drag.c0[0] + m[0] - drag.m0[0], drag.c0[1] + m[1] - drag.m0[1]], w: drag.w, h: drag.h };
      else {
        const r = e.originalEvent.shiftKey ? null : ratioOf(drag.mode === "draw" ? vframes.aspect : v.frame?.aspect);
        live = { id: v.id, ...fromCorners(drag.a, m, r) };
      }
      drag.moved = true; redraw();
    },
    handleUpEvent() {
      const d = drag; drag = null; if (!d) return false;
      const v = viewOf(d.id);
      if (d.moved && live && v && live.w > 1 && live.h > 1) {
        if (d.mode === "draw") v.frame = { aspect: vframes.aspect };
        save(v, live);
        vframes.sel = v.id;
        if (d.mode === "draw") { vframes.draw = ""; vframes.msg = ""; }
      }
      live = null; redraw();
      return false;
    },
  });
  it.set("viewFrames", true); it.set("gradoFrame", true);
  const place = () => { const c = map.getInteractions(), arr = c.getArray(); if (arr.includes(it)) c.remove(it); const top = arr.findIndex(i => i.get("gradoTop")); c.insertAt(top < 0 ? arr.length : top, it); };
  place();
  const onAdd = ev => { if (ev.element !== it && !ev.element.get("gradoTop") && !ev.element.get("gradoFrame")) place(); };   // две рамки (листы, виды) не переставляют друг друга по кругу
  map.getInteractions().on("add", onAdd);

  const onMove = e => {
    if (e.dragging || !shown() || cadApi.active?.()) return;
    const el = map.getTargetElement(), gi = vframes.draw ? -1 : hitGrip(e.pixel), id = gi < 0 && !vframes.draw && hit(e.pixel);
    const want = vframes.draw ? "crosshair" : gi === 0 || gi === 2 ? "nesw-resize" : gi === 1 || gi === 3 ? "nwse-resize" : id && id === vframes.sel ? "move" : "";
    if (want || el.dataset.vframeCursor) { el.style.cursor = want; el.dataset.vframeCursor = want ? "1" : ""; }
  };
  map.on("pointermove", onMove);
  const onKey = e => { if (e.key === "Escape" && vframes.draw) { vframes.draw = ""; vframes.msg = ""; live = null; drag = null; redraw(); } };
  window.addEventListener("keydown", onKey);

  const stops = [
    watch(() => [vframes.on, vframes.draw, vframes.sel, project.views.map(v => [v.id, v.name, v.frame])], redraw, { deep: true }),
    watch(() => vframes.fit, id => {
      if (!id) return;
      vframes.fit = "";
      const f = viewOf(id)?.frame; if (!f) return;
      map.getView().fit(boundingExtent(frameCorners(f).map(fromM)), { padding: [70, 40, 40, 40], duration: 250, maxZoom: 18 });
    }),
  ];
  redraw();
  return () => { stops.forEach(s => s()); map.un("pointermove", onMove); window.removeEventListener("keydown", onKey);
    map.getInteractions().un("add", onAdd); map.removeInteraction(it); map.removeLayer(layer); };
}
