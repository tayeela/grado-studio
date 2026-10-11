/* ГРАДО 2 · рамки листов альбома на карте нового интерфейса (шаг 2 фаза 2, #94) — как frames.js рабочей страницы.
   Пока вкладка «Листы и альбом» на виду, каждый лист-карта — рамка на карте: размер = карта листа × масштаб, прямоугольник
   в МСК (как печатает альбом). Свои листы — синей линией, листы по шаблону (раздел, альбом ППТ КРТ) — серым пунктиром. На рамке — короткое имя
   «Лист 5 · А3 · 1:2000», полное название — подсказкой при наведении (#29).
   Щелчок по рамке выбирает лист во вкладке; выбранный: тянуть внутри — сдвиг (sheet.center), за угол — масштаб (sheet.scale),
   пропорции формата держатся сами. Рамки и размеры считает движок альбома (web/albumapi.js state().frames), правка
   пишется в раздел album проекта (albumhost.js editSheet). Выбор листа в списке вкладки приближает карту к его рамке. */
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
import { watch } from "vue";
import * as mskMod from "../../web/msk.js";
import { album, editSheet } from "./albumhost.js";
import { cadApi } from "./cad.js";

const MSK = globalThis.MSK || mskMod.default || mskMod;
const BLUE = "#1a5fb4", SEC = "#7a869a";
const toM = c => MSK.fromWgs(toLonLat(c)), fromM = m => fromLonLat(MSK.toWgs(m));

/* углы рамки в МСК: [ЮЗ, ЮВ, СВ, СЗ] */
export function corners(c, wh) {
  const [cx, cy] = MSK.fromWgs(c), [w, h] = wh;
  return [[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]];
}
/* лист по двум углам (МСК): пропорции карты листа mm, масштаб — из размера; середина — долгота и широта */
export function fromCorners(a, b, mm) {
  const [fw, fh] = mm, dx = b[0] - a[0], dy = b[1] - a[1];
  const scale = Math.max(Math.abs(dx) / fw, Math.abs(dy) / fh, 1e-3) * 1000, w = fw * scale / 1000, h = fh * scale / 1000;
  return { scale: Math.round(scale), center: MSK.toWgs([a[0] + Math.sign(dx || 1) * w / 2, a[1] + Math.sign(dy || 1) * h / 2]) };
}

export function attachFrames(map) {
  const src = new VectorSource();
  let drag = null, live = null;          // live — рамка, которую сейчас тянут: { i, c, wh }
  const grip = new Style({ image: new RegularShape({ points: 4, radius: 6, angle: Math.PI / 4, fill: new Fill({ color: "#fff" }), stroke: new Stroke({ color: BLUE, width: 2 }) }),
    geometry: f => new MultiPoint(f.getGeometry().getCoordinates()[0].slice(0, 4)) });
  const layer = new VectorLayer({ source: src, zIndex: 9990, style: f => {
    const fr = f.get("fr"), on = fr.i === album.cur, col = fr.own ? BLUE : SEC, tl = f.getGeometry().getCoordinates()[0][3];
    return [new Style({ stroke: new Stroke({ color: col, width: on ? 2.5 : 1.5, lineDash: fr.own ? undefined : [8, 5] }),
        fill: new Fill({ color: on ? "rgba(26,95,180,.05)" : "rgba(26,95,180,.001)" }) }),   // почти прозрачная заливка: щелчок внутри выбирает лист
      new Style({ geometry: new Point(tl), text: new Text({ text: fr.label, font: `${on ? 600 : 500} 12px Onest, system-ui, sans-serif`, textAlign: "left", textBaseline: "bottom", offsetY: -5,
        fill: new Fill({ color: col }), stroke: new Stroke({ color: "#fff", width: 3 }) }) }),
      ...(on ? [grip] : [])];
  } });
  map.addLayer(layer);

  const list = () => album.tab ? album.frames || [] : [];
  function redraw() {
    src.clear(true);
    list().forEach(fr0 => {
      const fr = live && live.i === fr0.i ? { ...fr0, ...live } : fr0;
      const r = corners(fr.c, fr.wh).map(fromM), f = new Feature(new Polygon([[...r, r[0]]]));
      f.set("fr", fr); src.addFeature(f);
    });
  }
  const frameAt = i => { const fr = list().find(x => x.i === i); return fr && live && live.i === i ? { ...fr, ...live } : fr; };
  const hit = px => map.forEachFeatureAtPixel(px, f => f.get("fr"), { layerFilter: l => l === layer, hitTolerance: 6 });
  const hitGrip = px => {
    const fr = frameAt(album.cur); if (!fr) return -1;
    return corners(fr.c, fr.wh).map(fromM).findIndex(c => { const p = map.getPixelFromCoordinate(c); return Math.hypot(p[0] - px[0], p[1] - px[1]) < 10; });
  };
  const other = px => map.forEachFeatureAtPixel(px, () => true, { layerFilter: l => l !== layer && !!l.get("key"), hitTolerance: 3 });

  const it = new PointerInteraction({
    handleDownEvent(e) {
      if (!album.tab || e.originalEvent.button || cadApi.active?.()) return false;   // идёт команда черчения — рамка не мешает
      const g = hitGrip(e.pixel);
      if (g >= 0) { const fr = frameAt(album.cur); drag = { mode: "size", fr, a: corners(fr.c, fr.wh)[(g + 2) % 4] }; return true; }
      const fr = hit(e.pixel);
      // внутри листа лежат объекты: щелчок по объекту — выбор объекта, по пустому месту — выбор листа
      if (!fr || (fr.i !== album.cur && other(e.pixel))) return false;
      if (fr.i !== album.cur) { album.cur = fr.i; redraw(); }
      drag = { mode: "move", fr, m0: toM(e.coordinate), c0: MSK.fromWgs(fr.c) };
      return true;
    },
    handleDragEvent(e) {
      if (!drag) return;
      const m = toM(e.coordinate), fr = drag.fr;
      if (drag.mode === "move") live = { i: fr.i, c: MSK.toWgs([drag.c0[0] + m[0] - drag.m0[0], drag.c0[1] + m[1] - drag.m0[1]]), wh: fr.wh };
      else { const r = fromCorners(drag.a, m, fr.mm); live = { i: fr.i, c: r.center, wh: fr.mm.map(v => v * r.scale / 1000), scale: r.scale }; }
      drag.moved = true; redraw();
    },
    handleUpEvent() {
      const d = drag; drag = null;
      if (!d) return false;
      if (d.moved && live) {
        const patch = { center: live.c.map(v => +v.toFixed(7)) };
        if (d.mode === "size") patch.scale = live.scale;
        editSheet(d.fr.i, patch);
        // пока движок не пересчитал рамку, она стоит там, куда её отпустили
        album.frames = (album.frames || []).map(x => x.i === d.fr.i ? { ...x, c: live.c, wh: live.wh, ...(live.scale ? { scale: live.scale } : {}) } : x);
      }
      live = null; redraw();
      return false;
    },
  });
  it.set("albumFrames", true); it.set("gradoFrame", true);
  // рамка — сразу под перехватом команд черчения (cad.js gradoTop): щелчок по рамке доходит до неё раньше выбора и сдвига карты
  const place = () => { const c = map.getInteractions(), arr = c.getArray(); if (arr.includes(it)) c.remove(it); const top = arr.findIndex(i => i.get("gradoTop")); c.insertAt(top < 0 ? arr.length : top, it); };
  place();
  const onAdd = ev => { if (ev.element !== it && !ev.element.get("gradoTop") && !ev.element.get("gradoFrame")) place(); };   // две рамки (листы, виды) не переставляют друг друга по кругу
  map.getInteractions().on("add", onAdd);

  // курсор: над углом выбранной рамки — размер, над рамкой — сдвиг
  const onMove = e => {
    if (e.dragging || !album.tab || cadApi.active?.()) return;
    const el = map.getTargetElement(), g = hitGrip(e.pixel), fr = g < 0 && hit(e.pixel);
    const want = g === 0 || g === 2 ? "nesw-resize" : g === 1 || g === 3 ? "nwse-resize" : fr && fr.i === album.cur ? "move" : "";
    if (want || el.dataset.frameCursor) { el.style.cursor = want; el.dataset.frameCursor = want ? "1" : ""; }
    // подсказка над рамкой — полное название листа (на рамке — короткое, #29)
    const tip = fr ? fr.title || fr.label : "";
    if (tip || el.dataset.frameTip) { el.title = tip; el.dataset.frameTip = tip ? "1" : ""; }
  };
  map.on("pointermove", onMove);

  const stops = [
    watch(() => [album.tab, album.frames, album.cur], redraw, { deep: false }),
    // выбор листа в списке вкладки — карта приближается к его рамке (если она есть)
    watch(() => album.fit, k => {
      if (!k) return;
      album.fit = 0;
      const fr = frameAt(album.cur); if (!fr) return;
      map.getView().fit(boundingExtent(corners(fr.c, fr.wh).map(fromM)), { padding: [70, 40, 40, 40], duration: 250, maxZoom: 18 });
    }),
  ];
  redraw();
  return () => { stops.forEach(s => s()); map.un("pointermove", onMove); map.getInteractions().un("add", onAdd); map.removeInteraction(it); map.removeLayer(layer); };
}
