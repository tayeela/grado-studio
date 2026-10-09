/* ГРАДО 2 · проект в новом интерфейсе: список, открытие, запись в папку проектов, автосохранение, новый проект,
   файл .grado2 с диска и на диск. Те же адреса и тот же формат файла, что у рабочей страницы (web/project.js):
   GET/POST /api/project?name=… и ?autosave=1. Пишет весь файл из project.raw, меняя только то, что правит новый интерфейс. */
import { nextTick, ref, toRaw, watch } from "vue";
import { basemapId, currentId, project, setProject, viewNow } from "./store.js";
import { dataRev, graphRev, resetHistory } from "./edit.js";
import { normGraph } from "./graphfile.js";
import { setSel } from "./features.js";

export const projects = ref([]);      // [{name, modified, size, album_n}], новые сверху
export const projDir = ref("");
export const loadError = ref("");
export const dirty = ref(false);      // есть правки, не записанные под именем проекта (автосохранение их держит)
export const busy = ref(false);
export const notice = ref("");        // последнее сообщение для строки состояния: «Проект сохранён», «Не сохранён: …»
export const shared = ref(false);     // общий сервер (совместная работа): своей папки проектов нет, запись идёт через хаб
export const appVersion = ref("");

const FORMAT = "grado2", VERSION = 2;
let quiet = true;                     // открытие проекта — не правка
let tick = 0, autoTick = 0, lastEdit = 0, pendingSince = 0;

async function getJSON(url) {
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(r.status + " " + url);
  return r.json();
}

function say(t) { notice.value = t; }

/* Правка проекта: окна меняют слои и группы в store — следим за ними здесь, а не в каждом окне. */
export function markDirty() {
  if (quiet) return;
  if (tick === autoTick) pendingSince = Date.now();
  tick++; lastEdit = Date.now(); dirty.value = true;
  hooks.touched();
}
/* совместная работа (collab.js, hub.js): правка уходит на сервер; общий сервер при запуске — вход и окно проектов */
export const hooks = { touched: () => {}, shared: () => {} };
/* проект с сервера совместной работы: открыт, своих несохранённых правок нет */
export async function loadShared(p, name) { await load(p, name || "", "hub"); project.file = null; dirty.value = false; loadError.value = ""; }
export function markClean() { dirty.value = false; autoTick = tick; }
watch([() => project.layers, () => project.groups, () => project.views, () => project.territory, basemapId, dataRev, graphRev], markDirty, { deep: true });

async function load(p, name, source) {
  if (p?.format !== FORMAT) throw new Error("это не файл проекта ГРАДО 2");
  if ((p.version || 1) > VERSION) throw new Error(`файл сохранён более новой версией ГРАДО 2 (формат ${p.version}) — обновите программу`);
  quiet = true;
  normGraph(p);                       // схема расчёта: по умолчанию, если её нет; новые поля узлов старой версии
  setProject(p, name, source);
  setSel([]); resetHistory();
  dirty.value = !!p.dirty; autoTick = tick;
  await nextTick();                   // наблюдатели за слоями отработали на открытии — дальше всё правки
  quiet = false;
}

export async function listProjects() {
  const j = await getJSON("/api/projects");
  projDir.value = j.dir || "";
  projects.value = [...(j.projects || [])].sort((a, b) => (b.modified || 0) - (a.modified || 0));
  return j;
}

export async function openProject(name) {
  busy.value = true;
  try {
    const p = await getJSON("/api/project?name=" + encodeURIComponent(name));
    await load(p, name, "file");
    project.file = name; dirty.value = false;
    loadError.value = "";
    say(`Открыт проект «${name}»`);
    autosave();
  } catch (e) {
    say("Проект не открылся: " + e.message);
  } finally { busy.value = false; }
}

/* Первый показ: последнее автосохранение (то, что было открыто в рабочей странице), иначе самый свежий проект. */
export async function openStartup() {
  try {
    const h = await getJSON("/api/health");
    shared.value = !!h.hub; appVersion.value = h.version || "";
  } catch { /* старый сервер без версии — работаем как с локальным */ }
  if (shared.value) { loadError.value = "Общий сервер: войдите и откройте проект в окне «Совместные проекты»"; hooks.shared(); return; }
  try {
    const j = await listProjects();
    if (j.autosave) {
      const p = await getJSON("/api/project?autosave=1");
      await load(p, p.name || "", "autosave");
      return;
    }
    if (projects.value.length) await openProject(projects.value[0].name);
    else { loadError.value = "В папке проектов пока нет ни одного проекта"; quiet = false; }
  } catch (e) {
    loadError.value = "Проект не загрузился: " + e.message;
  }
}

/* ---------- файл проекта ---------- */

/* Данные слоя, не менявшиеся с прошлой записи, не сериализуются заново (как web/project.js jsonOf). */
const JCACHE = new WeakMap();
export const jsonOf = o => { let t = JCACHE.get(o); if (t === undefined) { t = JSON.stringify(o); JCACHE.set(o, t); } return t; };

export function collect(extra = {}) {
  const raw = project.raw;
  const rawGroup = Object.fromEntries((raw.groups || []).map(g => [g.id, g]));
  const v = { ...(raw.view || {}), ...(viewNow.center ? { center: viewNow.center, zoom: viewNow.zoom } : {}), basemap: basemapId.value };
  return {
    ...raw,
    format: FORMAT, version: raw.version || VERSION, app: "ГРАДО 2 " + appVersion.value,
    name: project.name || null, file: project.file ?? null, saved_at: new Date().toISOString(), dirty: dirty.value,
    view: v,
    current: currentId.value || raw.current || null,
    groups: project.groups.map(g => ({ ...(rawGroup[g.id] || {}), ...toRaw(g) })),
    layers: project.layers.map(l => ({ ...toRaw(l), style: toRaw(l.style) })),
    views: JSON.parse(JSON.stringify(project.views)),
    data: project.data || {},
    territory: project.territory || null,
    ...extra,
  };
}

export function projectJSON(extra) {
  const p = collect(extra), big = [];
  p.data = Object.fromEntries(Object.entries(p.data).map(([k, d]) => {
    const o = { ...d };
    if (o.original === o.fc && o.fc) o.original = "=fc";        // не правились — в файл один раз, как у рабочей страницы
    for (const f of ["fc", "original"]) if (o[f] && typeof o[f] === "object") { big.push(o[f]); o[f] = `@@GRADO_BIG_${big.length - 1}@@`; }
    return [k, o];
  }));
  return JSON.stringify(p).replace(/"@@GRADO_BIG_(\d+)@@"/g, (_, i) => jsonOf(big[+i]));
}

const BAD_NAME = /[\\/:*?"<>|]|^\./;
const norm = x => x.normalize("NFC").toLowerCase();

/* Есть ли в папке другой проект с этим названием (регистр и «ё» файловая система не различает). */
export async function clashOf(name) {
  if (!name || name === project.file) return null;
  try { await listProjects(); } catch { return null; }
  return projects.value.find(q => norm(q.name) === norm(name)) || null;
}

/* «Сохранить»: под своим названием; новое название — после проверки clashOf в окне. Возвращает true, если записано. */
export async function saveProject(name) {
  if (shared.value) { say("Общий сервер: правки уходят на сервер сами"); return false; }
  name = (name ?? project.name ?? "").trim();
  if (!name) return false;
  if (BAD_NAME.test(name)) { say("В названии не должно быть знаков / \\ : * ? \" < > | и точки в начале"); return false; }
  const prev = [project.name, project.file];
  project.name = name; project.file = name;
  const t = tick, body = projectJSON({ dirty: false });
  busy.value = true;
  try {
    const r = await fetch("/api/project?name=" + encodeURIComponent(name), { method: "POST", headers: { "Content-Type": "application/json" }, body });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error === "bad project name" ? "недопустимое название" : (j.error || r.status));
    if (tick === t) dirty.value = false;
    project.source = "file";
    say(`Проект «${name}» сохранён`);
    autosave();
    return true;
  } catch (e) {
    [project.name, project.file] = prev;
    say("Проект не сохранён: " + e.message);
    return false;
  } finally { busy.value = false; }
}

/* Новый пустой проект: прежний остаётся в папке, если был сохранён. */
export async function newProject() {
  await load({ format: FORMAT, version: VERSION, name: null, groups: [], layers: [], data: {}, views: [], album: { meta: {}, sheets: [] } }, "", "new");
  project.file = null; dirty.value = false; loadError.value = "";
  say("Новый проект. Прежний остался в папке проектов, если был сохранён");
  autosave();
}

/* Файл .grado2 с диска: открывается как несохранённый — «Сохранить» положит его в папку проектов. */
export async function openFile(file) {
  try {
    const p = JSON.parse(await file.text());
    p.name ||= file.name.replace(/\.grado2$/i, "");
    await load(p, p.name, "disk");
    project.file = null; dirty.value = true; markDirty();
    say(`Открыт файл «${file.name}». Сохраните проект, чтобы он появился в папке проектов`);
  } catch (e) { say("Файл не открылся: " + e.message); }
}

export function downloadProject() {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([projectJSON()], { type: "application/json" }));
  a.download = (project.name || "проект") + ".grado2"; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}

/* ---------- автосохранение: правки затихли на 1,5 с, но не реже раза в 15 с; одна запись за раз ---------- */
let autoBusy = false, autoAgain = false;
export async function autosave() {
  if (shared.value || quiet) return;
  if (autoBusy) { autoAgain = true; return; }
  autoBusy = true; const t = tick;
  try {
    const r = await fetch("/api/project?autosave=1", { method: "POST", headers: { "Content-Type": "application/json" }, body: projectJSON() });
    if (r.ok) autoTick = t;
  } catch { /* сервер не ответил — следующая правка попробует снова */ }
  finally { autoBusy = false; if (autoAgain) { autoAgain = false; autosave(); } }
}
setInterval(() => {
  if (quiet || tick === autoTick || autoBusy) return;
  const t = Date.now();
  if (t - lastEdit > 1500 || t - (pendingSince || t) > 15000) autosave();
}, 500);
