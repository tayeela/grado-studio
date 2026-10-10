<!-- ГРАДО 2 · окно «Карта» нового интерфейса: OpenLayers, подложка (схема по теме, спутник, Sentinel-2), граница
     территории и слои открытого проекта из store.project.
     Порядок слоёв — как в окне «Слои» (верхний рисуется поверх), видимость — слой и его группа.
     Оформление — все способы рабочей страницы (symbology.js): единое, категории, диапазоны, правила, знаки ЛГР, подписи, масштаб.
     Размер карты следит за окном dockview (ResizeObserver); масштаб пишет в store.scale, вид — в store.viewNow (для записи проекта).
     Черчение как в AutoCAD (команды, привязки, ручки, командная строка над картой) — cad.js, подключается к этой карте;
     поиск по адресу, кадастровому номеру и № КРТ над картой — MapSearch.vue; метки комментариев и указатели участников
     совместной работы — hubmap.js; рамки листов альбома — albumframes.js. -->
<template><div class="mapbox">
  <!-- карта — одна остановка Tab: стрелки двигают, «+» и «−» меняют масштаб (клавиши OpenLayers); объекты слоя доступны
       списком в «Таблице атрибутов» (#30) -->
  <div ref="el" class="map" tabindex="0" role="application" aria-roledescription="карта"
       aria-label="Карта. Стрелки — сдвиг, плюс и минус — масштаб. Объекты текущего слоя списком — в окне «Таблица атрибутов»"></div>
  <!-- «Только карта» под кнопками масштаба (#26): остальные окна прячутся, повтор — возвращает -->
  <div class="ol-control maponly"><button type="button" :title="mapOnly ? 'Вернуть окна (Ctrl+\\ или Esc)' : 'Только карта: спрятать остальные окна (Ctrl+\\)'"
       :aria-pressed="mapOnly" @click="winApi.mapOnly()"><Minimize2 v-if="mapOnly" :size="14" /><Maximize2 v-else :size="14" /></button></div>
  <MapSearch v-if="mref" :map="mref" /></div></template>

<script setup>
import { onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";
import MapSearch from "./MapSearch.vue";
import Map from "ol/Map.js";
import View from "ol/View.js";
import VectorLayer from "ol/layer/Vector.js";
import VectorSource from "ol/source/Vector.js";
import { containsExtent, createEmpty, extend, isEmpty } from "ol/extent.js";
import { defaults as defaultInteractions } from "ol/interaction/defaults.js";
import DragBox from "ol/interaction/DragBox.js";
import { shiftKeyOnly } from "ol/events/condition.js";
import { Circle as CircleStyle, Fill, Stroke, Style } from "ol/style.js";
import { fromLonLat, toLonLat } from "ol/proj.js";
import { basemapId, cursor, mapOnly, project, scale, theme, viewNow, winApi } from "../store.js";
import { Maximize2, Minimize2 } from "@lucide/vue";
import { dataRev, mapApi } from "../edit.js";
import { mskOf, sel, selected, setSel, toggleSel } from "../features.js";
import { loadLibs, scaleDen } from "../symbology.js";
import Draw from "ol/interaction/Draw.js";
import Modify from "ol/interaction/Modify.js";
import Text from "ol/style/Text.js";
import { fromExtent } from "ol/geom/Polygon.js";
import Feature from "ol/Feature.js";
import { coverBox, coverOn, importFiles, setTerritory, terrTool } from "../data.js";
import { notice } from "../project.js";
import { attachGraphLayers } from "../graphmap.js";
import { basemap, gjFormat, layerSync, readOne } from "../maplayers.js";
import { attachCad, cadApi } from "../cad.js";
import { attachHub, hubClick } from "../hubmap.js";
import { attachFrames } from "../albumframes.js";

const el = ref(null);
let map, ro, offCad = null, offHub = null, offFrames = null;
const mref = shallowRef(null);           // карта для поиска над ней (MapSearch.vue)
const fmt = gjFormat;

const lat = () => toLonLat(map.getView().getCenter())[1];

/* Граница территории (project.territory): штрихпунктир, как у рабочей страницы; при правке — с голубым ореолом и ручками.
   Нарисовать — многоугольник (двойной щелчок завершает, Esc отменяет), править — ручки на вершинах (Alt+щелчок удаляет вершину). */
const terrSrc = new VectorSource();
const terrStyle = new Style({ stroke: new Stroke({ color: "#b3261e", width: 2, lineDash: [12, 4, 2, 4] }) });
const terrHalo = new Style({ stroke: new Stroke({ color: "rgba(30,111,217,.45)", width: 7 }) });
function drawTerr() {
  terrSrc.clear(true);
  const t = project.territory; if (!t?.geometry) return;
  try { terrSrc.addFeature(fmt.readFeature(t)); } catch { /* граница повреждена — карта без неё */ }
}
let draw = null, modify = null;
function setTerrTool(t) {
  if (draw) { map.removeInteraction(draw); draw = null; }
  if (modify) { map.removeInteraction(modify); modify = null; }
  if (t === "draw") {
    draw = new Draw({ type: "Polygon", style: [terrHalo, terrStyle] });
    draw.on("drawend", e => { const gj = fmt.writeFeatureObject(e.feature); terrTool.value = ""; setTerritory(gj, { keep: true }); notice.value = "Граница нарисована. Править вершины — «Изменить границу»"; });
    map.addInteraction(draw); notice.value = "Обведите территорию щелчками, двойной щелчок завершает, Esc — отмена";
  } else if (t === "edit") {
    if (!terrSrc.getFeatures().length) { terrTool.value = ""; return; }
    modify = new Modify({ source: terrSrc, deleteCondition: e => e.originalEvent.altKey && e.type === "singleclick" });
    modify.on("modifyend", () => setTerritory(fmt.writeFeatureObject(terrSrc.getFeatures()[0]), { keep: true }));
    map.addInteraction(modify); notice.value = "Тяните вершину, щелчок по стороне — новая вершина, Alt+щелчок — удалить вершину; Esc — готово";
  }
  terrLayer?.changed();
}

/* Область загрузки данных: синий пунктир, пока окно «Данные» на виду. */
const coverSrc = new VectorSource();
const coverStyle = new Style({ stroke: new Stroke({ color: "#1a5fb4", width: 1.5, lineDash: [6, 5] }),
  text: new Text({ text: "область загрузки данных", font: "12px Onest, system-ui, sans-serif", placement: "line", fill: new Fill({ color: "#1a5fb4" }),
    stroke: new Stroke({ color: "#fff", width: 3 }), textBaseline: "bottom", offsetY: -3 }) });
function drawCover() {
  coverSrc.clear(true);
  const b = coverOn.value && coverBox(); if (!b) return;
  coverSrc.addFeature(new Feature(fromExtent(b).transform("EPSG:4326", "EPSG:3857")));
}
let terrLayer = null;

/* слои проекта на карте — maplayers.js (то же для карт окна «Сравнение»); здесь — ещё подсветка выбора */
let LS = null, vec = {};               // vec: key слоя → VectorLayer
function sync() { LS.sync(); drawSel(); }

/* ---------- выбор: щелчок, Shift+щелчок, рамка с Shift; подсветка поверх слоёв ---------- */
const selSrc = new VectorSource();
const SELSTYLE = {
  poly: new Style({ fill: new Fill({ color: "rgba(47,111,196,.15)" }), stroke: new Stroke({ color: "#2f6fc4", width: 3 }) }),
  line: new Style({ stroke: new Stroke({ color: "#2f6fc4", width: 4 }) }),
  point: new Style({ image: new CircleStyle({ radius: 8, stroke: new Stroke({ color: "#2f6fc4", width: 3 }) }) }),
};
const gkind = f => { const t = f.getGeometry()?.getType() || ""; return /Point/.test(t) ? "point" : /Line/.test(t) ? "line" : "poly"; };
function drawSel() {
  selSrc.clear(true);
  selSrc.addFeatures(selected().slice(0, 5000).map(s => readOne(s.f)).filter(Boolean));
}
function hitAt(pixel) {
  let hit = null;
  map.forEachFeatureAtPixel(pixel, (f, layer) => { const key = layer?.get("key"); if (!key || !f.gj) return; hit = { key, uid: f.gj.properties._uid }; return true; },
    { hitTolerance: 4, layerFilter: la => !!la.get("key") && la.getVisible() });
  return hit;
}
function onClick(e) {
  if (terrTool.value) return;                       // рисуем или правим границу — щелчок не выбирает объекты
  if (cadApi.active?.() || performance.now() - (cadApi.lastEnd || 0) < 400) return;   // щелчок — ввод для команды черчения
  if (hubClick(e)) return;                          // метка комментария или комментарий на карте (совместная работа)
  const hit = hitAt(e.pixel), add = e.originalEvent.shiftKey || e.originalEvent.metaKey || e.originalEvent.ctrlKey;
  if (add) { if (hit) toggleSel(hit); }
  else setSel(hit ? [hit] : []);
}
function onBox(box) {
  const ext = box.getGeometry().getExtent(), out = [];
  project.layers.forEach(l => {
    const v = vec[l.key]; if (!v?.getVisible()) return;
    v.getSource().forEachFeatureIntersectingExtent(ext, f => { if (f.gj) out.push({ key: l.key, uid: f.gj.properties._uid }); });
  });
  setSel([...sel, ...out]);
}

/* Другой проект: слои заново и его вид карты (или все объекты в кадре). Пока окно карты не получило размер
   (dockview ещё раскладывает окна), вид ставится позже — иначе «всё в кадре» на нулевом окне даёт обзор всей Земли. */
let viewPending = true;
function opened() {
  LS.clear();
  sync();
  drawTerr(); drawCover();
  viewPending = true; applyView();
}
function applyView() {
  const size = map.getSize();
  if (!viewPending || !size || !size[0] || !size[1]) return;
  viewPending = false;
  const v = project.view, view = map.getView();
  if (v?.center?.length === 2 && Number.isFinite(+v.zoom)) { view.setCenter(fromLonLat(v.center)); view.setZoom(+v.zoom); }
  else if (terrSrc.getFeatures().length) view.fit(terrSrc.getExtent(), { padding: [40, 40, 40, 40], maxZoom: 18 });
  else zoomTo(Object.keys(vec), 0);
}
/* Вид карты из окна «Виды»: центр (долгота, широта) и уровень. */
mapApi.fitExtent = (bb, duration = 200) => map.getView().fit(fromExtent(bb).transform("EPSG:4326", "EPSG:3857").getExtent(), { padding: [40, 40, 40, 40], maxZoom: 17, duration });
mapApi.setView = (center, zoom) => { const v = map.getView(); v.setCenter(fromLonLat(center)); v.setZoom(zoom); };

mapApi.fitFeature = gj => { const f = readOne(gj); if (f) map.getView().fit(f.getGeometry().getExtent(), { padding: [80, 80, 80, 80], maxZoom: 19, duration: 150 }); };
function zoomTo(keys, duration = 200) {
  const ext = createEmpty();
  keys.forEach(k => { const s = vec[k]?.getSource(); if (s?.getFeatures().length) extend(ext, s.getExtent()); });
  if (!isEmpty(ext)) map.getView().fit(ext, { padding: [40, 40, 40, 40], maxZoom: 18, duration });
}

onMounted(() => {
  map = new Map({
    target: el.value, layers: [basemap(basemapId.value, theme.value), terrLayer = new VectorLayer({ source: terrSrc, zIndex: 9999, style: () => terrTool.value === "edit" ? [terrHalo, terrStyle] : terrStyle }),
      new VectorLayer({ source: coverSrc, zIndex: 9998, style: coverStyle }), new VectorLayer({ source: selSrc, zIndex: 10000, style: f => SELSTYLE[gkind(f)] })],
    view: new View({ center: fromLonLat([37.62, 55.75]), zoom: 11 }),
    interactions: defaultInteractions({ shiftDragZoom: false }),   // Shift+рамка — выбор, как в рабочей странице
  });
  LS = layerSync(map); vec = LS.vec; mref.value = map;
  offCad = attachCad(map, { vec, sync: () => LS.sync(), terrSrc });     // команды черчения: щелчки, ручки, командная строка
  offHub = attachHub(map);                         // совместная работа: метки комментариев, указатели других участников
  offFrames = attachFrames(map);                   // рамки листов альбома, пока вкладка «Листы и альбом» на виду
  const box = new DragBox({ condition: shiftKeyOnly });
  box.on("boxend", () => onBox(box)); map.addInteraction(box);
  map.on("singleclick", onClick);
  map.on("pointermove", e => { if (!e.dragging) cursor.value = mskOf(toLonLat(e.coordinate)); });   // координаты курсора в строке состояния
  map.getViewport().addEventListener("mouseleave", () => { cursor.value = null; });
  attachGraphLayers(map);                          // результат схемы расчёта: пятно, эскиз, выход выбранного блока
  const upd = () => {
    if (viewPending) return;                        // вид проекта ещё не поставлен: в файл не должен уйти случайный
    const v = map.getView();
    scale.value = scaleDen(v.getResolution(), lat());     // как в рабочей странице: 0,2646 мм на пиксель, поправка на широту
    viewNow.center = toLonLat(v.getCenter()); viewNow.zoom = v.getZoom();   // вид уходит в файл при записи, сдвиг карты — не правка
  };
  map.on("moveend", upd); upd();
  ro = new ResizeObserver(() => { map.updateSize(); if (viewPending) { applyView(); upd(); } }); ro.observe(el.value);
  opened();
  mapApi.zoomTo = zoomTo; mapApi.view = map.getView();
  loadLibs().then(() => map.render());   // знаки ЛГР появляются, когда пришли библиотеки
  watch([basemapId, theme], ([id, t]) => map.getLayers().setAt(0, basemap(id, t)));
  watch(() => project.raw, opened);
  watch([() => project.layers, () => project.groups, dataRev], sync, { deep: true });
  watch(sel, drawSel);
  watch(() => project.territory, () => { drawTerr(); drawCover(); });
  watch(coverOn, on => {
    drawCover(); if (!on || !coverSrc.getFeatures().length) return;
    const ex = coverSrc.getExtent(), v = map.getView();      // область за краем экрана — карта отдаляется, чтобы пунктир было видно весь
    if (!containsExtent(v.calculateExtent(map.getSize()), ex)) v.fit(ex, { padding: [40, 40, 40, 40], duration: 250 });
  });
  watch(terrTool, setTerrTool);
  /* файл, брошенный на карту, — импорт слоя (файл проекта открывается меню «Проект») */
  el.value.addEventListener("dragover", e => { if ([...e.dataTransfer.types].includes("Files")) { e.preventDefault(); el.value.classList.add("dropfile"); } });
  el.value.addEventListener("dragleave", e => { if (!el.value.contains(e.relatedTarget)) el.value.classList.remove("dropfile"); });
  el.value.addEventListener("drop", e => {
    el.value.classList.remove("dropfile"); if (!e.dataTransfer.files.length) return; e.preventDefault();
    const fs = [...e.dataTransfer.files];
    if (fs.some(f => /\.grado2$/i.test(f.name))) { notice.value = "Файл проекта открывается меню «Проект» → «Открыть файл .grado2 с диска»"; return; }
    importFiles(fs);
  });
});

onBeforeUnmount(() => { offCad?.(); offHub?.(); offFrames?.(); ro?.disconnect(); map?.setTarget(undefined); });
</script>

<style>
.mapbox { position: relative; width: 100%; height: 100%; }
.map { position: relative; width: 100%; height: 100%; background: var(--g-canvas); }
.map.cmode { cursor: crosshair; }
.mapbox .maponly { position: absolute; top: calc(.5em + 56px); right: .5em; }
.mapbox .maponly button { width: 24px; height: 24px; display: grid; place-items: center; }
.map.dropfile { outline: 3px dashed var(--wa-color-brand-border-loud); outline-offset: -6px; }
</style>
