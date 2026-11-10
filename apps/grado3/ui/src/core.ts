/* ГРАДО · ядро Rust в браузере (план 09.11.2026, шаг С1): координаты МСК ↔ WGS84 и проверка файла проекта тем же кодом,
   что на сервере (rust/crates/crs, rust/crates/model через rust/crates/wasm). Модуль WebAssembly собирает
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
