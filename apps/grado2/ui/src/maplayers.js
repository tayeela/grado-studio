/* ГРАДО 2 · слои проекта на карте OpenLayers — общее для окна «Карта» и карт окна «Сравнение»: подложка (схема по теме,
   спутник, Sentinel-2) и слои project.layers с оформлением symbology.js, порядком и видимостью как в окне «Слои».
   layerSync(map) возвращает {vec, sync, clear}: vec — key слоя → VectorLayer; sync — привести карту к проекту. */
import TileLayer from "ol/layer/Tile.js";
import VectorLayer from "ol/layer/Vector.js";
import VectorSource from "ol/source/Vector.js";
import OSM from "ol/source/OSM.js";
import XYZ from "ol/source/XYZ.js";
import GeoJSON from "ol/format/GeoJSON.js";
import { toLonLat } from "ol/proj.js";
import { project, shown } from "./store.js";
import { indexOf } from "./features.js";
import { denToRes, fullStyle, okn, styleFunction } from "./symbology.js";

export const gjFormat = new GeoJSON({ featureProjection: "EPSG:3857" });   // в файле проекта данные в долготе и широте

/* Подложки — как web/app.js BASEMAPS: «Схема OSM» в тёмной теме — тёмная схема Esri. */
export function basemap(id, t) {
  if (id === "esri") return new TileLayer({ className: "basemap-sat", opacity: 0.9, source: new XYZ({ url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", maxZoom: 19, attributions: "Снимки © Esri, Maxar, Earthstar Geographics" }) });
  if (id === "s2") return new TileLayer({ className: "basemap-sat", opacity: 0.9, source: new XYZ({ url: "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2021_3857/default/g/{z}/{y}/{x}.jpg", maxZoom: 15, attributions: "Sentinel-2 cloudless 2021 © EOX IT Services GmbH (содержит изменённые данные Copernicus Sentinel)" }) });
  return t === "dark"
    ? new TileLayer({ source: new XYZ({ url: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", maxZoom: 16, crossOrigin: "anonymous", attributions: "Подложка © Esri, HERE, Garmin, © OpenStreetMap contributors" }) })
    : new TileLayer({ source: new OSM(), className: "basemap", opacity: 0.55 });
}

/* Объекты GeoJSON слоя → объекты карты; у каждого ссылка gj на свою запись в файле (по ней выбор и правка). */
export function readAll(fc) {
  indexOf(fc);                                      // номера _uid у всех объектов
  return (fc?.features || []).map(readOne).filter(Boolean);
}
export function readOne(gj) {
  try { const f = gjFormat.readFeature(gj); f.gj = gj; f.gjRev = f.getRevision(); return f; } catch { return null; }   // битый объект не должен ронять слой; gjRev — для записи правок черчения (cad.js)
}
/* Правка данных: только изменённые записи (новые объекты в fc) меняются на карте; тысячи прочих не перечитываются. */
const canon = v => v === null || typeof v !== "object" ? JSON.stringify(v) : Array.isArray(v) ? "[" + v.map(canon).join(",") + "]"
  : "{" + Object.keys(v).sort().filter(k => v[k] !== undefined).map(k => JSON.stringify(k) + ":" + canon(v[k])).join(",") + "}";
function patch(src, fc) {
  indexOf(fc);
  const now = new Set(fc?.features || []), have = new Set(src.getFeatures().map(f => f.gj));   // черчение само кладёт объекты в источник (cad.js)
  let gone = src.getFeatures().filter(f => !now.has(f.gj)), add = (fc?.features || []).filter(gj => !have.has(gj));
  /* тот же объект новой записью (чужая правка в совместной работе: пришёл весь слой): объект карты остаётся, меняется ссылка */
  if (gone.length && add.length) {
    const by = new Map(gone.map(f => [f.gj?.properties?._uid, f])), kept = new Set();
    add = add.filter(gj => { const f = by.get(gj.properties?._uid); if (!f || kept.has(f) || canon(f.gj) !== canon(gj)) return true; f.gj = gj; kept.add(f); return false; });
    if (kept.size) gone = gone.filter(f => !kept.has(f));
  }
  if (gone.length + add.length > 2000) { src.clear(true); src.addFeatures(readAll(fc)); return; }
  gone.forEach(f => src.removeFeature(f));
  src.addFeatures(add.map(readOne).filter(Boolean));
}
const sig = l => JSON.stringify([l.style, l.layerOpacity, l.geom]);

/* Слои карты по слоям проекта: новый слой или заменённые данные — новый источник, изменённое оформление — новый слой
   на том же источнике, видимость и порядок — на месте; слои, которых в проекте нет, убираются.
   Слой OpenLayers по описанию слоя из файла: оформление, видимость по масштабу (как в QGIS), прозрачность слоя;
   подписи разводятся (declutter), если у слоя есть подпись. Источник с объектами переиспользуется. */
export function layerSync(map) {
  const vec = {};
  const lat = () => toLonLat(map.getView().getCenter() || [0, 0])[1];
  function olLayer(l, i, n, src) {
    const st = fullStyle(l.style), la = lat();
    return new VectorLayer({
      source: src, style: styleFunction(l, project.data[l.key]?.fc, lat), declutter: !!st.label,
      visible: shown(l), zIndex: n - i, opacity: okn(l.layerOpacity, 1),
      maxResolution: st.maxDen ? denToRes(st.maxDen, la) : Infinity, minResolution: st.minDen ? denToRes(st.minDen, la) : 0,
      properties: { key: l.key },
    });
  }
  function sync() {
    const n = project.layers.length, keys = new Set(project.layers.map(l => l.key));
    for (const k in vec) if (!keys.has(k)) { map.removeLayer(vec[k]); delete vec[k]; }
    project.layers.forEach((l, i) => {
      const fc = project.data[l.key]?.fc;
      let v = vec[l.key];
      if (!v) {
        v = vec[l.key] = olLayer(l, i, n, new VectorSource({ features: readAll(fc) }));
        v.set("fc", fc); v.set("sig", sig(l)); map.addLayer(v);
      } else if (v.get("fc") !== fc || v.get("sig") !== sig(l)) {
        if (v.get("fc") !== fc) patch(v.getSource(), fc);
        const nv = olLayer(l, i, n, v.getSource()); nv.set("fc", fc); nv.set("sig", sig(l));   // стиль заново: категории и диапазоны зависят от данных
        map.getLayers().setAt(map.getLayers().getArray().indexOf(v), nv); vec[l.key] = v = nv;
      }
      v.setVisible(shown(l)); v.setZIndex(n - i);
    });
  }
  const clear = () => { for (const k in vec) { map.removeLayer(vec[k]); delete vec[k]; } };
  return { vec, sync, clear };
}
