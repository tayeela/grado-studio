/* ГРАДО 2 · рамки видов на карте нового интерфейса (#119): вид = слои + рамка «где». Пока открыто окно «Виды» или
   «Макет листа», рамка каждого вида — фиолетовый прямоугольник с подписью «Ограничения · 820 × 580 м».
   «Нарисовать рамку» (vframes.draw = id вида): тянешь прямоугольник, пропорции — из vframes.aspect (Shift — свободно).
   Щелчок по рамке выбирает вид; выбранную тянут внутри (сдвиг) и за угол (размер, пропорции держатся, Shift — свободно).
   Рамка пишется в project.views[].frame ({ center: [долгота, широта], w, h — метры МСК, aspect }) — её берут блоки карты
   листов (SheetPanel.vue, viewframes.js blockFromView). Расчёты — viewframes.js.
   Рамки листов альбома ППТ КРТ — те же рамки (id «alb:<лист>», одна логика везде, владелец 12.10.2026): видны вместе с
   видами и пока на виду вкладка «Листы и альбом»; пропорции — карты листа, сдвиг пишет середину листа, угол — его масштаб
   (albumhost.js editSheet), рамки считает движок альбома (albumapi.js state().frames, albumhost.js wantFrames). Листы по
   шаблону — пунктиром. Щелчок по рамке выбирает лист во вкладке, выбор листа там приближает карту к его рамке.
   Пока окно «Данные» на виду, тут же — синяя рамка «Область загрузки данных» (id COVER, data.js coverFrame): её тянут
   и растягивают так же, как рамку вида, сдвинутая рамка становится своей областью проекта (data.js setCover). */
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
import { basemapId, project, viewCur, viewNow } from "./store.js";
import { notice } from "./project.js";
import { cadApi } from "./cad.js";
import { cornersM, fromCorners, frameLabel, ratioOf, sheetFromCorners } from "./viewframes.js";
import { album, editSheet, wantFrames } from "./albumhost.js";
import { coverFrame, coverOn, coverRev, setCover, terrTool } from "./data.js";

const MSK = globalThis.MSK || mskMod.default || mskMod;
const VIOLET = "#7a3fd1", BLUE = "#1a5fb4";
export const COVER = "__cover";
/* область загрузки — как вид: рамка frame; запись рамки — своя область проекта */
const coverItem = () => ({ id: COVER, name: "область загрузки данных", get frame() { return coverFrame(); }, set frame(f) { if (f?.center) setCover(f); } });
const toM = c => MSK.fromWgs(toLonLat(c)), fromM = m => fromLonLat(MSK.toWgs(m));
/* лист альбома — как вид: рамка frame (пропорции карты листа mm); запись рамки — середина и масштаб листа */
export const ALB = "alb:";
const albumItem = f => ({ id: ALB + f.id, i: f.i, mm: f.mm, name: f.label, tip: f.title, own: f.own,
  get frame() { return { center: f.c, w: f.wh[0], h: f.wh[1], aspect: `${f.mm[0]}:${f.mm[1]}` }; },
  set frame(fr) {
    if (!fr?.center) return;
    const patch = { center: fr.center.map(v => +(+v).toFixed(7)) }, sc = Math.round(fr.w * 1000 / f.mm[0]);
    if (Math.abs(sc - f.scale) >= 1) patch.scale = sc;
    editSheet(f.i, patch);
    // пока движок не пересчитал рамку, она стоит там, куда её отпустили
    album.frames = (album.frames || []).map(x => x.i === f.i ? { ...x, c: patch.center, wh: [fr.w, fr.h], ...(patch.scale ? { scale: patch.scale } : {}) } : x);
  } });
export const albumItems = () => (album.frames || []).map(albumItem);

/* вид = видимые слои, их оформление, группы, подложка (как «Темы карты» QGIS); ext — и масштаб карты */
const clone = o => JSON.parse(JSON.stringify(o));
export function captureView(title, ext) {
  return { id: "v" + Date.now().toString(36), name: title, basemap: basemapId.value,
    layers: project.layers.map(l => ({ key: l.key, visible: l.visible, style: clone(l.style), layerOpacity: l.layerOpacity })),
    groups: project.groups.map(g => ({ id: g.id, visible: g.visible })),
    extent: ext && viewNow.center ? { center: [...viewNow.center], zoom: viewNow.zoom } : null };
}
/* «Вид выделением» (владелец 26.10.2026: «просто хочу назначить вид выделением и всё»): выделил область на карте — вид готов:
   слои и оформление — как сейчас на карте, рамка — выделенная область. Рисуется как рамка вида с id NEW. */
export const NEW = "__newview";
const newItem = () => ({ id: NEW, name: "новый вид", made: "",
  set frame(fr) {
    if (!fr?.center || this.made) return;
    const v = captureView(`Вид ${project.views.length + 1}`, false);
    v.frame = fr; project.views.push(v); viewCur.value = v.id; this.made = v.id;
    notice.value = `Вид «${v.name}» готов: его можно поставить на лист. Переименовать — в окне «Виды»`;
  },
  get frame() { return null; } });
export function newViewBySelection() {
  if (cadApi.active?.()) cadApi.cancel?.();          // идущая команда черчения перехватила бы мышь
  vframes.aspect = "free"; vframes.sel = ""; vframes.draw = NEW;
  notice.value = "Выделите область на карте: тяните рамку от угла до угла. Esc — отмена";
}

/* общее состояние: on — сколько окон просят рамки (Виды, Макет листа); draw — id вида, которому рисуют рамку;
   sel — выбранный вид; aspect — пропорции новой рамки; fit — «приблизить к рамке вида» (id); msg — подсказка над картой */
export const vframes = reactive({ on: 0, draw: "", sel: "", aspect: "a", fit: "", msg: "" });
export const viewOf = id => id === COVER ? coverItem() : id === NEW ? newItem() : String(id).startsWith(ALB) ? albumItems().find(v => v.id === id)
  : project.views.find(v => v.id === id);
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
  const gripOf = col => new Style({ image: new RegularShape({ points: 4, radius: 6, angle: Math.PI / 4, fill: new Fill({ color: "#fff" }), stroke: new Stroke({ color: col, width: 2 }) }),
    geometry: f => new MultiPoint(f.getGeometry().getCoordinates()[0].slice(0, 4)) });
  const grip = gripOf(VIOLET), gripB = gripOf(BLUE);
  const layer = new VectorLayer({ source: src, zIndex: 9989, style: f => {
    const id = f.get("id"), on = id === vframes.sel, tl = f.getGeometry().getCoordinates()[0][3], cov = id === COVER, col = cov ? BLUE : VIOLET;
    // область загрузки: внутри не ловит мышь, пока не выбрана (карту внутри неё двигают как обычно), — выбирают щелчком по краю;
    // лист альбома по шаблону — пунктиром
    return [new Style({ stroke: new Stroke({ color: col, width: on ? 2.5 : 1.5, lineDash: cov ? [6, 5] : f.get("draft") ? [6, 4] : f.get("tpl") ? [8, 5] : undefined }),
        fill: cov && !on ? undefined : new Fill({ color: on ? (cov ? "rgba(26,95,180,.05)" : "rgba(122,63,209,.06)") : "rgba(122,63,209,.001)" }) }),
      new Style({ geometry: new Point(tl), text: new Text({ text: f.get("label"), font: `${on ? 600 : 500} 12px Onest, system-ui, sans-serif`, textAlign: "left", textBaseline: "bottom", offsetY: -5,
        fill: new Fill({ color: col }), stroke: new Stroke({ color: "#fff", width: 3 }) }), zIndex: on ? 3 : 2 }),   // подпись выбранной — поверх совпавших рамок
      ...(on && !f.get("draft") ? [cov ? gripB : grip] : [])];
  } });
  map.addLayer(layer);

  const views = () => vframes.on > 0 || !!vframes.draw;
  const shown = () => views() || coverOn.value || album.tab;
  const items = () => [...(views() ? project.views : []), ...((views() || album.tab) && !vframes.draw ? albumItems() : []),
    ...(coverOn.value && !vframes.draw ? [coverItem()] : []), ...(vframes.draw === NEW ? [newItem()] : [])];
  const geomOf = v => live && live.id === v.id ? live : v.frame ? { c: MSK.fromWgs(v.frame.center), w: v.frame.w, h: v.frame.h } : null;
  function redraw() {
    src.clear(true); layer.setVisible(shown()); if (!shown()) return;
    // совпавшие рамки (листы альбома одного места и масштаба) — одна подпись, выбранной рамки: иначе надписи ложатся друг на друга
    const seen = new Set(), all = items();
    [...all.filter(v => v.id === vframes.sel), ...all.filter(v => v.id !== vframes.sel)].forEach(v => {
      const g = geomOf(v); if (!g) return;
      const key = [g.c[0], g.c[1], g.w, g.h].map(Math.round).join(), dup = seen.has(key); seen.add(key);
      const r = cornersM(g.c, g.w, g.h).map(fromM), f = new Feature(new Polygon([[...r, r[0]]]));
      f.setProperties({ id: v.id, label: dup ? "" : v.mm ? v.name : frameLabel(v.name, g), draft: !v.frame, tpl: v.mm && !v.own, tip: v.tip || "" }); src.addFeature(f);
    });
  }
  // рамки лежат друг на друге (листы альбома одного места): под мышью выбранная — она, иначе верхняя
  const hit = px => { const ids = map.getFeaturesAtPixel(px, { layerFilter: l => l === layer, hitTolerance: 6 }).map(f => f.get("id"));
    return ids.includes(vframes.sel) ? vframes.sel : ids[0]; };
  const hitGrip = px => {
    const v = viewOf(vframes.sel), g = v && geomOf(v); if (!g) return -1;
    return cornersM(g.c, g.w, g.h).map(fromM).findIndex(c => { const p = map.getPixelFromCoordinate(c); return Math.hypot(p[0] - px[0], p[1] - px[1]) < 10; });
  };
  const other = px => map.forEachFeatureAtPixel(px, () => true, { layerFilter: l => l !== layer && !!l.get("key"), hitTolerance: 3 });
  const save = (v, g) => { v.frame = { center: MSK.toWgs(g.c).map(x => +x.toFixed(7)), w: Math.round(g.w * 10) / 10, h: Math.round(g.h * 10) / 10, aspect: v.frame?.aspect || vframes.aspect }; };
  const ratioFor = (v, draw, shift) => shift || v.id === COVER ? null : ratioOf(draw ? vframes.aspect : v.frame?.aspect);   // область загрузки — без пропорций

  const it = new PointerInteraction({
    handleDownEvent(e) {
      if (!shown() || e.originalEvent.button || cadApi.active?.() || terrTool.value) return false;   // рисуют или правят границу — рамки не мешают
      const m = toM(e.coordinate);
      if (vframes.draw) { drag = { mode: "draw", id: vframes.draw, a: m }; return true; }
      const gi = hitGrip(e.pixel);
      if (gi >= 0) { const v = viewOf(vframes.sel), g = geomOf(v); drag = { mode: "size", id: v.id, a: cornersM(g.c, g.w, g.h)[(gi + 2) % 4] }; return true; }
      const id = hit(e.pixel);
      if (!id || (id !== vframes.sel && other(e.pixel))) return false;   // объект слоя внутри рамки — выбор объекта
      vframes.sel = id; redraw();
      const v = viewOf(id); if (v?.mm) album.cur = v.i;                // лист альбома — выбран и во вкладке
      const g = v && geomOf(v); if (!g) return true;
      drag = { mode: "move", id, m0: m, c0: g.c, w: g.w, h: g.h };
      return true;
    },
    handleDragEvent(e) {
      if (!drag) return;
      const m = toM(e.coordinate), v = viewOf(drag.id); if (!v) return;
      if (drag.mode === "move") live = { id: v.id, c: [drag.c0[0] + m[0] - drag.m0[0], drag.c0[1] + m[1] - drag.m0[1]], w: drag.w, h: drag.h };
      else if (v.mm) live = { id: v.id, ...sheetFromCorners(drag.a, m, v.mm) };   // лист альбома: пропорции и ориентация — карты листа
      else {
        const r = ratioFor(v, drag.mode === "draw", e.originalEvent.shiftKey);
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
        vframes.sel = v.made || v.id;
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
    // над рамкой листа альбома — его полное название (на рамке — короткое, #29)
    const tip = id ? src.getFeatures().find(f => f.get("id") === id)?.get("tip") || "" : "";
    if (tip || el.dataset.vframeTip) { el.title = tip; el.dataset.vframeTip = tip ? "1" : ""; }
  };
  map.on("pointermove", onMove);
  const onKey = e => { if (e.key === "Escape" && vframes.draw) { vframes.draw = ""; vframes.msg = ""; live = null; drag = null; redraw(); } };
  window.addEventListener("keydown", onKey);

  const stops = [
    watch(() => [vframes.on, vframes.draw, vframes.sel, project.views.map(v => [v.id, v.name, v.frame]), coverOn.value, coverRev.value, project.territory, project.raw,
      album.tab, album.frames], redraw, { deep: true }),
    // «Виды» или «Макет листа» открыты — рамки листов альбома нужны и без вкладки альбома
    watch(() => vframes.on > 0, wantFrames, { immediate: true }),
    // выбор листа во вкладке — выбор его рамки; «приблизить» (album.fit) — к рамке выбранного листа
    watch(() => [album.cur, album.tab, album.frames], () => {
      if (!album.tab) return;
      const f = (album.frames || []).find(x => x.i === album.cur);
      if (f && vframes.sel !== ALB + f.id && (!vframes.sel || String(vframes.sel).startsWith(ALB))) vframes.sel = ALB + f.id;
    }),
    watch(() => album.fit, k => {
      if (!k) return;
      album.fit = 0;
      const f = (album.frames || []).find(x => x.i === album.cur); if (f) { vframes.sel = ALB + f.id; vframes.fit = ALB + f.id; }
    }),
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
