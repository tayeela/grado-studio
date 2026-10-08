/* ГРАДО 2 · результат схемы расчёта на карте нового интерфейса (как предпросмотр web/app.js RES): пятно застройки
   штриховкой, сохраняемые здания серым, участки и улицы эскиза, корпуса эскиза цветом этажности (подпись «12 эт.» с
   1:2 000) и выход выбранного блока оранжевым с пояснениями. Видно, пока открыты окна схемы или эскиза; выход блока —
   только при открытом окне схемы. Слои над данными проекта, в список слоёв не попадают. MapPanel зовёт attachGraphLayers. */
import { watch } from "vue";
import VectorLayer from "ol/layer/Vector.js";
import VectorSource from "ol/source/Vector.js";
import GeoJSON from "ol/format/GeoJSON.js";
import { Fill, Stroke, Style, Text } from "ol/style.js";
import { toLonLat } from "ol/proj.js";
import { theme } from "./store.js";
import { hatch, scaleDen } from "./symbology.js";
import { RESULT, fcOf, nodeById, outputOf, preview, selNode, tick } from "./graph.js";

const GJ = new GeoJSON({ featureProjection: "EPSG:3857" });
const toOl = f => GJ.readFeature(f);
const S = (fill, stroke, w) => new Style({ fill: new Fill({ color: fill }), stroke: new Stroke({ color: stroke, width: w }) });
const shade = n => ["#dcebfa", "#a8cbf1", "#6fa6e6", "#2a78d6", "#1a4f94"][Math.min(4, Math.floor(n / 6))];
const FLOOR_LABEL_DEN = 2000;
export const GROUND = { "улица": ["#e4e1da", "#b7b2a8"], "проезд": ["#e4e1da", "#b7b2a8"], "участок ИЖС": ["#eef5e4", "#7a9a5a"], "участок блока": ["#eef5e4", "#7a9a5a"], "двор": ["#f6f1dc", "#c9b77a"],
  "хозпостройка": ["#e9e2d6", "#8c7b62"], "гостевая стоянка": ["#c9d8ee", "#5577aa"], "свет соседям": ["#fdf0b8", "#d9a400"] };

export function attachGraphLayers(map) {
  const src = { site: new VectorSource(), kept: new VectorSource(), ground: new VectorSource(), sketch: new VectorSource(), prev: new VectorSource() };
  const lat = () => toLonLat(map.getView().getCenter() || [0, 0])[1];
  const den = res => scaleDen(res, lat());
  const siteHatch = () => theme.value === "dark" ? "#5fae86" : "#6dae8c";
  const L = {
    site: new VectorLayer({ source: src.site, zIndex: 5000, style: () => new Style({ fill: new Fill({ color: hatch(siteHatch()) }), stroke: new Stroke({ color: "#1f7a4d", width: 1.4, lineDash: [5, 3] }) }) }),
    kept: new VectorLayer({ source: src.kept, zIndex: 5001, style: S("#bdb8b0", "#4d4d4d", 1) }),
    ground: new VectorLayer({ source: src.ground, zIndex: 5002, style: f => { const [a, b] = GROUND[f.get("kind")] || ["#eeeeee", "#999999"]; return S(a, b, .8); } }),
    sketch: new VectorLayer({ source: src.sketch, zIndex: 5010, style: (f, res) => new Style({ fill: new Fill({ color: shade(f.get("floors")) }), stroke: new Stroke({ color: "#1a4f94", width: 1 }),
      text: den(res) <= FLOOR_LABEL_DEN ? new Text({ text: f.get("floors") + " эт.", font: "11px Arial", fill: new Fill({ color: f.get("floors") > 14 ? "#fff" : "#123" }) }) : undefined }) }),
    prev: new VectorLayer({ source: src.prev, zIndex: 5020, declutter: true, style: f => {
      const out = [S([224, 138, 0, .22], "#c46f00", 2)], t = f.get("Пояснение");
      if (t) out.push(new Style({ text: new Text({ text: String(t), font: "600 12px system-ui, sans-serif", fill: new Fill({ color: "#6b3a00" }), stroke: new Stroke({ color: "#fff", width: 3 }), overflow: false, placement: "point" }) }));
      return out; } }),
  };
  Object.values(L).forEach(l => map.addLayer(l));
  const put = (s, list) => { s.clear(true); s.addFeatures(list.filter(Boolean).map(toOl)); };
  function draw() {
    const any = preview.graph || preview.sketch;
    Object.entries(L).forEach(([k, l]) => l.setVisible(k === "prev" ? preview.graph : any));
    if (!any) return;
    put(src.site, [RESULT.site]);
    put(src.kept, RESULT.tep?.kept || []);
    const sk = RESULT.sketch || [];
    src.sketch.clear(true); src.sketch.addFeatures(sk.map(b => { const f = toOl(b.f); f.set("floors", b.floors); return f; }));
    src.ground.clear(true); src.ground.addFeatures([...(sk.streets || []), ...(sk.plots || [])].map(g => { const f = toOl(g.f); f.set("kind", g.kind); return f; }));
    src.prev.clear(true);
    const n = preview.graph && selNode.value != null && nodeById(selNode.value);
    if (n) {
      const fc = fcOf(n.id), out = outputOf(n.id, 0);
      if (fc?.length) src.prev.addFeatures(fc.map(toOl));
      else if (n.outputs?.[0]?.type === "geom" && out) src.prev.addFeature(toOl(out));
    }
  }
  watch([tick, selNode, () => preview.graph, () => preview.sketch], draw);
  watch(theme, () => L.site.changed());
  draw();
}
