/* ГРАДО 2 · загрузка проекта в новый интерфейс: список проектов и чтение файла через API рабочей программы.
   Только чтение: новый интерфейс пока ничего не сохраняет, рабочая страница и её файлы не меняются. */
import { ref } from "vue";
import { setProject } from "./store.js";

export const projects = ref([]);      // [{name, modified}], новые сверху
export const loadError = ref("");

async function getJSON(url) {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(r.status + " " + url);
  return r.json();
}

export async function listProjects() {
  const j = await getJSON("/api/projects");
  projects.value = [...(j.projects || [])].sort((a, b) => (b.modified || 0) - (a.modified || 0));
  return j;
}

export async function openProject(name) {
  const p = await getJSON("/api/project?name=" + encodeURIComponent(name));
  setProject(p, name, "file");
  loadError.value = "";
}

/* Первый показ: последнее автосохранение (то, что было открыто в рабочей странице), иначе самый свежий проект. */
export async function openStartup() {
  try {
    const j = await listProjects();
    if (j.autosave) {
      const p = await getJSON("/api/project?autosave=1");
      setProject(p, p.name || "Автосохранение", "autosave");
      return;
    }
    if (projects.value.length) await openProject(projects.value[0].name);
    else loadError.value = "В папке проектов пока нет ни одного проекта";
  } catch (e) {
    loadError.value = "Проект не загрузился: " + e.message;
  }
}
