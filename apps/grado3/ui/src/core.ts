/* ГРАДО · ядро Rust в браузере (план 09.11.2026, шаги С1, С2, И1, И2): координаты МСК ↔ WGS84, проверка файла проекта,
   плановые площади/длины/наложения в МСК и операции рисования знаков (parts и типы линий ЛГР REDLN97) тем же кодом,
   что на сервере (rust/crates/crs, model, geom, symbol через rust/crates/wasm). Модуль WebAssembly собирает
   tools/build_core_wasm.sh в src/wasm; загрузка один раз при старте (main.ts → loadCore). Проверка: core.test.ts. */
import init, * as wasm from "./wasm/grado_core_wasm.js";
import type { Report } from "./types/check";

let ready: Promise<void> | null = null;

/** Загружает модуль один раз. url — файл .wasm (в браузере берётся рядом со сборкой, в тестах — байты с диска). */
export function loadCore(src?: Parameters<typeof init>[0]): Promise<void> {
  if (!ready) ready = init(src).then(() => undefined);
  return ready;
}

export type XY = [number, number];

export interface RenderOp {
  op: "path" | "clip" | "unclip";
  rings: XY[][];
  closed?: boolean;
  fill?: [number, number, number] | null;
  stroke?: [number, number, number] | null;
  width?: number;
  dash?: number[] | null;
  join?: string;
  cap?: CanvasLineCap;
  alpha?: number;
}

/** МСК (как в QGIS): [восток, север], м → [долгота, широта]. */
export const mskToWgs = ([x, y]: XY): XY => { const r = wasm.msk_to_wgs84(x, y); return [r[0], r[1]]; };
/** [долгота, широта] → МСК. */
export const wgsToMsk = ([lon, lat]: XY): XY => { const r = wasm.wgs84_to_msk(lon, lat); return [r[0], r[1]]; };
/** Много точек за раз: плоский массив [x0, y0, x1, y1, …]. */
export const mskToWgsMany = (xy: Float64Array): Float64Array => wasm.msk_to_wgs84_many(xy);
export const wgsToMskMany = (ll: Float64Array): Float64Array => wasm.wgs84_to_msk_many(ll);

/** Проверка текста файла проекта: ошибки и замечания по-русски. */
export const checkProject = (text: string): Report => JSON.parse(wasm.check_project(text));
/** Перевод старого файла на нынешние имена (как web/migrate.js). */
export const migrateProject = (text: string): string => wasm.migrate_project(text);
export const formatVersion = (): number => wasm.project_format_version();

const asJson = (v: unknown): string => (typeof v === "string" ? v : JSON.stringify(v ?? null));

/** Плановая площадь полигонов GeoJSON (WGS84) в м² в МСК (сумма outer − holes). */
export const areaMsk = (geojson: unknown): number => wasm.geojson_area_msk(asJson(geojson));
/** Плановая длина линий GeoJSON (WGS84) в м в МСК. */
export const lengthMsk = (geojson: unknown): number => wasm.geojson_length_msk(asJson(geojson));
/** Площадь объединения полигонов GeoJSON (WGS84) в м² в МСК без двойного счёта наложений. */
export const unionAreaMsk = (geojson: unknown): number => wasm.union_area_msk(asJson(geojson));
/** Площадь пересечения (∪ regions) ∩ (∪ clips) двух GeoJSON (WGS84) в м² в МСК. */
export const overlayAreaMsk = (regions: unknown, clips: unknown): number => wasm.overlay_area_msk(asJson(regions), asJson(clips));

/** Операции рисования частей знака (line, band, hatch, marks) через ядро Rust (crates/symbol). */
export function partsOps(kind: "poly" | "line", shapes: unknown, parts: unknown, pxMm = 1): RenderOp[] {
  try { return JSON.parse(wasm.parts_ops(kind, asJson(shapes), asJson(parts), pxMm)); } catch { return []; }
}

/** Загружает библиотеку типов линий ЛГР (redln97.json) в ядро Rust. */
export const loadLinetypes = (lib: unknown): boolean => wasm.load_linetypes(asJson(lib));
export const hasLinetype = (name: string): boolean => wasm.has_linetype(name);
/** Операции рисования типа линии ЛГР (REDLN97) вдоль ломаной pts (в пикселях экрана). */
export function linetypeOps(pts: XY[], name: string, k: number, shapeK: number, color: string, width: number): RenderOp[] {
  try { return JSON.parse(wasm.linetype_ops(JSON.stringify(pts), name, k, shapeK, color, width)); } catch { return []; }
}
