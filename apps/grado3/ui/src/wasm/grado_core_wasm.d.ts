/* tslint:disable */
/* eslint-disable */

/**
 * Проверка файла проекта → отчёт (JSON, тип `Report` из `types/check.ts`).
 */
export function check_project(text: string): string;

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
 * Номер формата проекта, который знает ядро.
 */
export function project_format_version(): number;

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
    readonly check_project: (a: number, b: number) => [number, number];
    readonly migrate_project: (a: number, b: number) => [number, number];
    readonly msk_to_wgs84: (a: number, b: number) => [number, number];
    readonly msk_to_wgs84_many: (a: number, b: number) => [number, number];
    readonly ogd_to_msk: (a: number, b: number) => [number, number];
    readonly project_format_version: () => number;
    readonly wgs84_to_msk: (a: number, b: number) => [number, number];
    readonly wgs84_to_msk_many: (a: number, b: number) => [number, number];
    readonly __wbindgen_externrefs: WebAssembly.Table;
    readonly __wbindgen_malloc: (a: number, b: number) => number;
    readonly __wbindgen_realloc: (a: number, b: number, c: number, d: number) => number;
    readonly __wbindgen_free: (a: number, b: number, c: number) => void;
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
