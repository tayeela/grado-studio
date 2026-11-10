/* ГРАДО · проект — один документ (план 09.11.2026, шаг И1). Файл .grado2 читается и пишется целиком: что новый
   интерфейс ещё не правит, уходит в файл как было (как apps/grado2/ui/src/project.js). Данные слоёв (тысячи объектов)
   не реактивны — их рисует карта. Правят проект только команды (commands/builtin.ts), поэтому любая правка отменяется.
   Адреса сервера те же, что у нынешнего интерфейса: GET/POST /api/project, GET /api/projects; запись с base — чужие
   правки другой вкладки не затираются (ответ 409). Перед открытием — перевод старых имён и проверка ядром Rust. */
import { defineStore } from "pinia";
import { computed, markRaw, ref, shallowRef } from "vue";
import { checkProject, migrateProject } from "../core";
import type { Layer, Project } from "../types/project";
import type { Report } from "../types/check";

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

export const useProject = defineStore("project", () => {
  const doc = shallowRef<Project | null>(null);         // весь файл; слои и группы — реактивные копии ниже
  const layers = ref<Layer[]>([]);
  const name = ref("");
  const base = ref<number | null>(null);                // время файла при открытии (X-Grado-Modified)
  const dirty = ref(false);
  const report = shallowRef<Report | null>(null);
  const list = ref<ProjectInfo[]>([]);
  const dir = ref("");

  const territory = computed(() => layers.value.find(l => l.role === "territory") || null);
  const data = (key: string): unknown => (doc.value?.data as Record<string, { fc?: unknown }> | undefined)?.[key]?.fc ?? null;

  async function refreshList(): Promise<ProjectInfo[]> {
    const j = await (await api("/api/projects")).json();
    list.value = j.projects || [];
    dir.value = j.dir || "";
    return list.value;
  }

  /** Текст файла → проект: перевод старых имён, проверка; ошибки проверки не дают открыть. */
  function load(text: string, file: string, modified: number | null): Report {
    const fixed = migrateProject(text);
    const r = checkProject(fixed);
    report.value = r;
    if (!r.ok) throw new ApiError("Проект не открылся: " + r.issues.filter(i => i.level === "error").map(i => i.text).join("; "));
    const p = JSON.parse(fixed) as Project;
    if (p.data) p.data = markRaw(p.data);
    doc.value = markRaw(p);
    layers.value = (p.layers || []).map(l => ({ ...l }));
    name.value = file;
    base.value = modified;
    dirty.value = false;
    return r;
  }

  async function open(file: string): Promise<Report> {
    const r = await api("/api/project?name=" + encodeURIComponent(file));
    return load(await r.text(), file, Number(r.headers.get("X-Grado-Modified")) || null);
  }

  /** Файл целиком: прежние поля как были, слои — из правок. */
  function toText(): string {
    if (!doc.value) throw new ApiError("Проект не открыт");
    const p: Project = { ...doc.value, layers: layers.value.map(l => ({ ...l })), saved_at: new Date().toISOString() } as Project;
    const { layouts, ...rest } = p;
    return JSON.stringify(layouts === undefined ? rest : { ...rest, layouts });   // листы — последним ключом
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
  const touch = () => { dirty.value = true; };

  return { doc, layers, name, base, dirty, report, list, dir, territory, data, refreshList, load, open, toText, save, layer, touch };
});

export type ProjectStore = ReturnType<typeof useProject>;
