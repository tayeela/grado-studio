/* tslint:disable */
/* eslint-disable */

/**
 * Экран: типы линий ЛГР (REDLN97) — библиотека грузится один раз, линии рисует canvas слоя
 */
export class LineLib {
    free(): void;
    [Symbol.dispose](): void;
    has(name: string): boolean;
    constructor(lib_json: string);
    /**
     * shape_k ≤ 0 — масштаб знаков как у шаблона
     */
    ops(pts_json: string, name: string, k: number, shape_k: number, color: string, width: number): string;
}

/**
 * Проверка файла проекта → отчёт (JSON, тип `Report` из `types/check.ts`).
 */
export function check_project(text: string): string;

/**
 * Плановая площадь полигонов GeoJSON (Feature, FeatureCollection, Geometry в WGS84) в м² в МСК:
 * сумма площадей каждого полигона (внешнее кольцо минус дыры), как features.js sizeOf.
 */
export function geojson_area_msk(text: string): number;

/**
 * Плановая длина линий GeoJSON (LineString, MultiLineString, Feature, FeatureCollection в WGS84) в м в МСК.
 */
export function geojson_length_msk(text: string): number;

/**
 * Есть ли тип линии `name` в загруженной библиотеке REDLN97.
 */
export function has_linetype(name: string): boolean;

/**
 * Операции рендера типа линии ЛГР (REDLN97) вдоль ломаной `pts_json` ([[x, y], …] в пикселях экрана).
 */
export function linetype_ops(pts_json: string, name: string, k: number, shape_k: number, color: string, width: number): string;

/**
 * Загружает библиотеку типов линий ЛГР (redln97.json) один раз в память ядра.
 */
export function load_linetypes(lib_json: string): boolean;

/**
 * Перевод старого файла на нынешние имена (как web/migrate.js) → текст JSON; не JSON — как был.
 */
export function migrate_project(text: string): string;

/**
 * МСК (X восток, Y север, м) → [долгота, широта] WGS84.
 */
export function msk_to_wgs84(x: number, y: number): Float64Array;

/**
 * Много точек за один вызов: [x0, y0, x1, y1, …] МСК → то же в WGS84 (быстрее, чем по точке).
 */
export function msk_to_wgs84_many(xy: Float64Array | number[]): Float64Array;

/**
 * Родные координаты ГИС ОГД → МСК (сдвиг).
 */
export function ogd_to_msk(x: number, y: number): Float64Array;

/**
 * Площадь пересечения (∪ regions) ∩ (∪ clips) двух GeoJSON (WGS84) в м² в МСК (шаг С2).
 */
export function overlay_area_msk(regions_text: string, clips_text: string): number;

/**
 * Экран: операции частей знака в пикселях карты (px_mm = 1) — их рисует canvas слоя (symbology.js)
 */
export function parts_ops(kind: string, shapes_json: string, parts_json: string, px_mm: number): string;

/**
 * Номер формата проекта, который знает ядро.
 */
export function project_format_version(): number;

/**
 * Площадь объединения полигонов GeoJSON (WGS84) в м² в МСК без двойного счёта наложений (grado_geom_rs::overlay).
 */
export function union_area_msk(text: string): number;

/**
 * [долгота, широта] WGS84 → МСК.
 */
export function wgs84_to_msk(lon: number, lat: number): Float64Array;

/**
 * Много точек: WGS84 → МСК.
 */
export function wgs84_to_msk_many(ll: Float64Array | number[]): Float64Array;

export type InitInput = RequestInfo | URL | Response | BufferSource | WebAssembly.Module;

export interface InitOutput {
    readonly memory: WebAssembly.Memory;
    readonly __wbg_linelib_free: (a: number, b: number) => void;
    readonly check_project: (a: number, b: number) => [number, number];
    readonly geojson_area_msk: (a: number, b: number) => number;
    readonly geojson_length_msk: (a: number, b: number) => number;
    readonly has_linetype: (a: number, b: number) => number;
    readonly linelib_has: (a: number, b: number, c: number) => number;
    readonly linelib_new: (a: number, b: number) => [number, number, number];
    readonly linelib_ops: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: number, j: number) => [number, number, number, number];
    readonly linetype_ops: (a: number, b: number, c: number, d: number, e: number, f: number, g: number, h: number, i: number) => [number, number];
    readonly load_linetypes: (a: number, b: number) => number;
    readonly migrate_project: (a: number, b: number) => [number, number];
    readonly msk_to_wgs84: (a: number, b: number) => [number, number];
    readonly msk_to_wgs84_many: (a: number, b: number) => [number, number];
    readonly ogd_to_msk: (a: number, b: number) => [number, number];
    readonly overlay_area_msk: (a: number, b: number, c: number, d: number) => number;
    readonly parts_ops: (a: number, b: number, c: number, d: number, e: number, f: number, g: number) => [number, number, number, number];
    readonly project_format_version: () => number;
    readonly union_area_msk: (a: number, b: number) => number;
    readonly wgs84_to_msk: (a: number, b: number) => [number, number];
    readonly wgs84_to_msk_many: (a: number, b: number) => [number, number];
    readonly __wbindgen_externrefs: WebAssembly.Table;
    readonly __wbindgen_malloc: (a: number, b: number) => number;
    readonly __wbindgen_realloc: (a: number, b: number, c: number, d: number) => number;
    readonly __wbindgen_free: (a: number, b: number, c: number) => void;
    readonly __externref_table_dealloc: (a: number) => void;
    readonly __wbindgen_start: () => void;
}

export type SyncInitInput = BufferSource | WebAssembly.Module;

/**
 * Instantiates the given `module`, which can either be bytes or
 * a precompiled `WebAssembly.Module`.
 *
 * @param {{ module: SyncInitInput }} module - Passing `SyncInitInput` directly is deprecated.
 *
 * @returns {InitOutput}
 */
export function initSync(module: { module: SyncInitInput } | SyncInitInput): InitOutput;

/**
 * If `module_or_path` is {RequestInfo} or {URL}, makes a request and
 * for everything else, calls `WebAssembly.instantiate` directly.
 *
 * @param {{ module_or_path: InitInput | Promise<InitInput> }} module_or_path - Passing `InitInput` directly is deprecated.
 *
 * @returns {Promise<InitOutput>}
 */
export default function __wbg_init (module_or_path?: { module_or_path: InitInput | Promise<InitInput> } | InitInput | Promise<InitInput>): Promise<InitOutput>;
