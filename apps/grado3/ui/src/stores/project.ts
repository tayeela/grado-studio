/* ГРАДО · проект — один документ (план 09.11.2026, шаги И1 и И2). Файл .grado2 читается и пишется целиком: что новый
   интерфейс ещё не правит, уходит в файл как было (как apps/grado2/ui/src/project.js). Данные слоёв (тысячи объектов)
   не реактивны — их рисует карта; счётчик dataTick сообщает окнам о замене слоя. Правят проект только команды
   (commands/builtin.ts), поэтому любая правка отменяется Ctrl+Z. Перед открытием — перевод старых имён и проверка ядром Rust,
   для файлов до 08.11.2026 — подключение поля territory как слоя-границы user:territory. Площади в МСК считает ядро Rust. */
import { defineStore } from "pinia";
import { computed, markRaw, ref, shallowRef } from "vue";
import { areaMsk, checkProject, migrateProject, unionAreaMsk } from "../core";
import type { Group, Layer, LayerData, Project } from "../types/project";
import type { Report } from "../types/check";

export const TERR_KEY = "user:territory";
export const PARCELS_KEY = "nspd.parcels";
export const EXAMPLE_RING: [number, number][] = [
  [37.5195, 55.7895], [37.5305, 55.7895], [37.5305, 55.7955], [37.5195, 55.7955], [37.5195, 55.7895],
];

export const BASEMAPS: Record<string, string> = {
  osm: "Схема OSM",
  esri: "Спутник (Esri)",
  s2: "Sentinel-2 (EOX)",
  none: "Без подложки",
};

export interface GeoFeature {
  type: "Feature";
  properties?: Record<string, unknown>;
  geometry?: { type: string; coordinates: unknown } | null;
}

export interface FeatureCollection {
  type: "FeatureCollection";
  features: GeoFeature[];
}

export interface ProjectInfo {
  name: string;
  modified: number;
  size: number;
  star?: boolean;
}

export class ApiError extends Error {}

async function api(url: string, init?: RequestInit): Promise<Response> {
  let r: Response;
  try {
    r = await fetch(url, { headers: { Accept: "application/json" }, ...init });
  } catch {
    throw new ApiError("Сервер не отвечает: проверьте, что программа запущена");
  }
  if (!r.ok) {
    let t = "";
    try { t = (await r.clone().json()).error || ""; } catch { /* тело не JSON */ }
    throw new ApiError(t || `Сервер ответил ${r.status}`);
  }
  return r;
}

const today = () => new Date().toISOString().slice(0, 10);

export const useProject = defineStore("project", () => {
  const doc = shallowRef<Project | null>(null);
  const layers = ref<Layer[]>([]);
  const groups = ref<Group[]>([]);
  const basemap = ref<string>((() => { try { return localStorage.getItem("grado2.base") || "osm"; } catch { return "osm"; } })());
  const name = ref("");
  const base = ref<number | null>(null);
  const dirty = ref(false);
  const dataTick = ref(0);
  const report = shallowRef<Report | null>(null);
  const list = ref<ProjectInfo[]>([]);
  const dir = ref("");

  const territory = computed(() => layers.value.find(l => l.role === "territory") || null);
  const dataEntry = (key: string): LayerData | undefined => (doc.value?.data as Record<string, LayerData | undefined> | undefined)?.[key];
  const data = (key: string): FeatureCollection | null => (dataEntry(key)?.fc as FeatureCollection | undefined) ?? null;

  /** Слой виден на карте, когда включён он сам и его группа. */
  function shown(l: Layer): boolean {
    if (l.visible === false) return false;
    const g = l.group ? groups.value.find(x => x.id === l.group) : null;
    return !g || g.visible !== false;
  }

  /** Число объектов в слое. */
  function layerCount(key: string): number {
    void dataTick.value;
    return data(key)?.features?.length || 0;
  }

  /** Плановая площадь объектов слоя в м² в МСК (через ядро Rust). */
  function layerAreaM2(key: string): number {
    void dataTick.value;
    const fc = data(key);
    return fc?.features?.length ? areaMsk(fc) : 0;
  }

  /** Плановая площадь объединения полигонов границы территории в м² в МСК (ядро Rust, без двойного счёта). */
  const territoryAreaM2 = computed(() => {
    void dataTick.value;
    const t = territory.value;
    if (!t) return 0;
    const fc = data(t.key);
    return fc?.features?.length ? unionAreaMsk(fc) : 0;
  });

  async function refreshList(): Promise<ProjectInfo[]> {
    const j = await (await api("/api/projects")).json();
    list.value = j.projects || [];
    dir.value = j.dir || "";
    return list.value;
  }

  /** Файлы до 08.11.2026 хранили границу в поле territory без слоя с ролью territory: подключаем её как слой user:territory. */
  function adoptLegacyTerritory(p: Project, ls: Layer[]) {
    if (ls.some(l => l.role === "territory")) return;
    const t = p.territory as GeoFeature | undefined;
    const gType = t?.geometry?.type;
    if (!t || (gType !== "Polygon" && gType !== "MultiPolygon")) return;
    p.data ||= {};
    if (!p.data[TERR_KEY]) {
      p.data[TERR_KEY] = {
        title: "Граница территории",
        source: "граница территории проекта",
        fetched_at: today(),
        fc: { type: "FeatureCollection", features: [{ type: "Feature", properties: t.properties || {}, geometry: t.geometry }] },
      };
    }
    const existing = ls.find(l => l.key === TERR_KEY);
    if (existing) existing.role = "territory";
    else {
      ls.push({
        key: TERR_KEY,
        title: p.data[TERR_KEY]?.title || "Граница территории",
        geom: "poly",
        visible: false,
        group: null,
        role: "territory",
        style: { mode: "single", fill: "#b0228c", opacity: 0, stroke: "#b0228c", width: 2, dash: [6, 4] },
      });
    }
  }

  /** Текст файла → проект: перевод старых имён, проверка; ошибки проверки не дают открыть. */
  function load(text: string, file: string, modified: number | null): Report {
    const fixed = migrateProject(text);
    const r = checkProject(fixed);
    report.value = r;
    if (!r.ok) throw new ApiError("Проект не открылся: " + r.issues.filter(i => i.level === "error").map(i => i.text).join("; "));
    const p = JSON.parse(fixed) as Project;
    p.data = markRaw(p.data || {});
    const ls = (p.layers || []).map(l => ({ ...l, visible: l.visible !== false }));
    adoptLegacyTerritory(p, ls);
    doc.value = markRaw(p);
    layers.value = ls;
    groups.value = (p.groups || []).map(g => ({ ...g, visible: g.visible !== false, open: g.open !== false }));
    if (p.view?.basemap && BASEMAPS[p.view.basemap]) setBasemap(p.view.basemap, false);
    name.value = file;
    base.value = modified;
    dirty.value = false;
    dataTick.value++;
    return r;
  }

  async function open(file: string): Promise<Report> {
    const r = await api("/api/project?name=" + encodeURIComponent(file));
    return load(await r.text(), file, Number(r.headers.get("X-Grado-Modified")) || null);
  }

  function setBasemap(id: string, mark = true) {
    if (!BASEMAPS[id]) return;
    basemap.value = id;
    try { localStorage.setItem("grado2.base", id); } catch { /* частный режим */ }
    if (mark && doc.value) dirty.value = true;
  }

  /** Записывает или удаляет данные слоя в doc.data; возвращает прежнее значение для отмены. */
  function setLayerData(key: string, entry: LayerData | undefined): LayerData | undefined {
    if (!doc.value) return undefined;
    const d = (doc.value.data ||= markRaw({})) as Record<string, LayerData | undefined>;
    const prev = d[key];
    if (entry === undefined) delete d[key];
    else d[key] = markRaw(entry);
    dataTick.value++;
    return prev;
  }

  /** Поле territory файла синхронно со слоем-границей (для сервера, альбома и старой страницы). */
  function currentTerritoryFeature(): GeoFeature | null {
    const t = territory.value;
    if (!t) return null;
    const polys = (data(t.key)?.features || []).filter(f => /Polygon/.test(f.geometry?.type || ""));
    if (!polys.length) return null;
    if (polys.length === 1) return { type: "Feature", properties: {}, geometry: polys[0].geometry };
    const coords: unknown[] = [];
    for (const f of polys) {
      if (f.geometry?.type === "Polygon") coords.push(f.geometry.coordinates);
      else if (f.geometry?.type === "MultiPolygon" && Array.isArray(f.geometry.coordinates)) coords.push(...f.geometry.coordinates);
    }
    return { type: "Feature", properties: {}, geometry: { type: "MultiPolygon", coordinates: coords } };
  }

  /** Файл целиком: прежние поля как были, слои и группы — из правок, листы — последним ключом. */
  function toText(): string {
    if (!doc.value) throw new ApiError("Проект не открыт");
    const view = doc.value.view ? { ...doc.value.view, basemap: basemap.value } : (doc.value.view === undefined ? undefined : null);
    const p: Record<string, unknown> = {
      ...doc.value,
      layers: layers.value.map(l => ({ ...l })),
      ...(doc.value.groups !== undefined || groups.value.length ? { groups: groups.value.map(g => ({ ...g })) } : {}),
      ...(view !== undefined ? { view } : {}),
      ...(doc.value.territory !== undefined || territory.value ? { territory: currentTerritoryFeature() } : {}),
      saved_at: new Date().toISOString(),
    };
    const { layouts, ...rest } = p;
    return JSON.stringify(layouts === undefined ? rest : { ...rest, layouts });
  }

  async function save(): Promise<string> {
    if (!name.value) throw new ApiError("У проекта нет названия");
    const q = "/api/project?name=" + encodeURIComponent(name.value) + (base.value ? "&base=" + base.value : "");
    const j = await (await api(q, { method: "POST", body: toText(), headers: { "Content-Type": "application/json" } })).json();
    base.value = j.modified ?? null;
    dirty.value = false;
    return j.saved;
  }

  const layer = (key: string) => layers.value.find(l => l.key === key) || null;
  const group = (id: string) => groups.value.find(g => g.id === id) || null;
  const touch = () => { dirty.value = true; dataTick.value++; };

  return {
    doc, layers, groups, basemap, name, base, dirty, dataTick, report, list, dir,
    territory, territoryAreaM2, dataEntry, data, shown, layerCount, layerAreaM2,
    refreshList, load, open, setBasemap, setLayerData, toText, save, layer, group, touch,
  };
});

export type ProjectStore = ReturnType<typeof useProject>;
