/* ГРАДО · состояние окна программы: текущее рабочее место, курсор над картой в МСК, масштаб, связь с картой.
   Карта (panels/MapPanel.vue) подставляет свои действия в mapApi: команды двигают карту через него, не трогая OpenLayers. */
import { defineStore } from "pinia";
import { ref } from "vue";
import type { XY } from "../core";

export interface MapApi {
  /** показать точку МСК в середине */
  centerMsk(p: XY): void;
  /** вписать слой (ключ) или всё */
  fit(key?: string): boolean;
  /** перерисовать слои проекта */
  refresh(): void;
}

export const useUi = defineStore("ui", () => {
  const ws = ref("territory");
  const cursor = ref<XY | null>(null);      // МСК, м
  const scale = ref(0);
  const map: { api: MapApi | null } = { api: null };
  return { ws, cursor, scale, map };
});

export type UiStore = ReturnType<typeof useUi>;
