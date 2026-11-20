/* ГРАДО · состояние окна программы (план 09.11.2026, шаги И1 и И2): текущее рабочее место, курсор над картой в МСК,
   масштаб, результаты поиска и связь с картой. Карта (panels/MapPanel.vue) подставляет свои действия в map.api:
   команды и окно поиска двигают карту и ставят метку найденного через него, не трогая OpenLayers. */
import { defineStore } from "pinia";
import { ref, shallowRef } from "vue";
import type { XY } from "../core";
import type { GeoFeature } from "./project";

export interface AddressHit {
  name?: string;
  display?: string;
  lon: number;
  lat: number;
  bbox?: [number, number, number, number];
}

export interface SearchState {
  q: string;
  type: "address" | "cadastral" | "krt";
  addresses: AddressHit[];
  features: GeoFeature[];
  cards: string[];
  missing: string[];
  notes: string[];
  picked: number;
}

export interface MapApi {
  /** показать точку МСК в середине */
  centerMsk(p: XY): void;
  /** показать точку WGS84 [долгота, широта] или рамку [w, s, e, n] и поставить метку поиска */
  markAddress(lon: number, lat: number, bbox?: [number, number, number, number]): void;
  /** подсветить найденные объекты GeoJSON на карте и вписать их */
  markFeatures(features: GeoFeature[]): void;
  /** убрать метку поиска */
  clearMark(): void;
  /** вписать слой (ключ) или всё */
  fit(key?: string): boolean;
  /** перерисовать слои проекта (full — пересоздать источники при замене данных слоя) */
  refresh(full?: boolean): void;
  /** переключить подложку на карте */
  syncBasemap(): void;
}

export const useUi = defineStore("ui", () => {
  const ws = ref("territory");
  const cursor = ref<XY | null>(null);      // МСК, м
  const scale = ref(0);
  const search = shallowRef<SearchState | null>(null);
  const map: { api: MapApi | null } = { api: null };
  return { ws, cursor, scale, search, map };
});

export type UiStore = ReturnType<typeof useUi>;
