/* ГРАДО 2 · меню «Выгрузка» нового интерфейса: чертёж DXF (МГГТ, МСК), GeoJSON для QGIS (МСК), SHP в раскладке ГИС ОГД (МСК) и Excel с показателями
   ТЭП и списком листов альбома — через те же адреса сервера, что у рабочей страницы (web/app.js exportLayers, exportTo,
   bExpXls): POST /api/export/dxf, /api/export/geojson, /api/export/shp, /api/export/xlsx. Слои выгрузки — все слои проекта и граница
   территории. Файл кладётся в папку загрузок браузера. */
import { project } from "./store.js";
import { busy, notice } from "./project.js";
import { RESULT } from "./graph.js";

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
export function exportShp() {
  const layers = exportLayers().map(({ name, features }) => ({ name, features })); if (!layers.length) { notice.value = NOTHING; return; }
  return exportTo("/api/export/shp", { layers }, "grado2-shp-msk.zip",
    "SHP готов: по набору файлов на слой, поля латиницей как в ГИС ОГД, их русские названия в fields.csv; координаты МСК; файл в папке загрузок", "SHP не выгружен");
}

/* Excel: показатели ТЭП (как окно «Показатели») и листы альбома из файла проекта; пустое значение — пустая ячейка, не ноль.
   Масштаб листа — заданный на листе; подобранный автоматически считает рабочая страница (web/sheets.js sheetScale). */
const SIZE_T = { BA4: "А4", BA3: "А3", BA2: "А2", BA1: "А1", BA0: "А0", A3: "A3 (ГОСТ)", A1: "A1 (ГОСТ)", P: "слайд 16:9", PA4: "слайд А4", PA3: "слайд А3", PA2: "слайд А2" };
export function exportXlsx() {
  const t = RESULT.tep, num = v => v == null || v === "" || !Number.isFinite(+v) ? null : +(+v).toFixed(6);
  const sheets = (project.raw?.album?.sheets || []).map((s, i) => ({ n: i + 1, title: s.title || "",
    format: (SIZE_T[s.size] || s.size || "") + (/^BA/.test(s.size || "") && s.orient === "P" ? " книжн." : ""),
    scale: ["tep", "title", "photos"].includes(s.kind) || s.panels || !(+s.scale > 0) ? null : Math.round(+s.scale) }));
  if (!t && !sheets.length) { notice.value = "В Excel пока нечего выгружать: нужна граница территории (тогда посчитаются показатели) или листы альбома"; return; }
  const tep = t ? [["Территория и эскиз", "Территория", t.terr, "га"], ["Территория и эскиз", "СПП новая", t.sppNew / 1000, "тыс. м²"], ["Территория и эскиз", "СПП сохраняемая", t.sppKept / 1000, "тыс. м²"],
    ["Территория и эскиз", "Плотность", t.density, "тыс. м²/га"], ["Территория и эскиз", "Застроенность", t.cover * 100, "%"]]
    .map(([group, title, v, unit]) => ({ group, title, value: num(v), unit })).concat(t.metrics.map(m => ({ group: m.group || "Прочее", title: m.title, value: num(m.value), unit: m.unit || "" }))) : [];
  return exportTo("/api/export/xlsx", { tep, sheets, project: project.name || "Без названия", ...(t?.constantsChanged?.length ? { note: `Нормативы изменены вручную: ${t.constantsChanged.length}` } : {}) },
    "grado2-tep.xlsx", "Excel готов: показатели ТЭП и список листов; файл в папке загрузок", "Excel не выгружен");
}
