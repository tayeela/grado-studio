/* ГРАДО 2 · меню «Выгрузка» нового интерфейса: чертёж DXF (МГГТ, МСК) и GeoJSON для QGIS (МСК) через те же адреса
   сервера, что у рабочей страницы (web/app.js exportLayers, exportTo): POST /api/export/dxf и /api/export/geojson.
   Слои выгрузки — все слои проекта и граница территории. Файл кладётся в папку загрузок браузера. */
import { project } from "./store.js";
import { busy, notice } from "./project.js";

export function exportLayers() {
  const layers = Object.entries(project.data).filter(([, d]) => d?.fc?.features).map(([k, d]) => ({
    name: d.title || k, features: d.fc, color: k === "gisogd.red_lines" ? "#d7191c" : "#808080",
    floors: d.fc.features.some(f => f.properties?.["Этажность"]),
  }));
  const t = project.raw?.territory;
  if (t?.geometry) layers.push({ name: "Граница территории", features: { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: t.geometry }] }, color: "#b3261e" });
  return layers;
}

function saveBlob(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}

async function exportTo(path, body, file, okText, failText) {
  busy.value = true;
  try {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) {
      const j = await r.json().catch(() => ({})); console.warn("export", path, r.status, j.error);
      throw new Error(r.status === 413 ? "слишком много данных" : r.status === 401 || r.status === 403 ? "нет доступа, войдите заново" : "сервер не принял данные");
    }
    saveBlob(await r.blob(), file); notice.value = okText;
  } catch (e) {
    notice.value = `${failText}: ${e instanceof TypeError ? "нет связи с программой" : e.message}`;
  } finally { busy.value = false; }
}

const NOTHING = "Выгружать нечего: загрузите данные или нарисуйте объекты";

export function exportDxf() {
  const layers = exportLayers(); if (!layers.length) { notice.value = NOTHING; return; }
  return exportTo("/api/export/dxf", { layers }, "grado2-dxf.zip",
    "DXF готов: в архиве чертёж, red_lns.shx и REDLN97.LIN; координаты МСК, метры; файл в папке загрузок", "DXF не выгружен");
}
export function exportGeojson() {
  const layers = exportLayers().map(({ name, features }) => ({ name, features })); if (!layers.length) { notice.value = NOTHING; return; }
  return exportTo("/api/export/geojson", { layers }, "grado2-geojson-msk.zip",
    "GeoJSON готов: по файлу на слой и README.txt; координаты МСК, метры; файл в папке загрузок", "GeoJSON не выгружен");
}
