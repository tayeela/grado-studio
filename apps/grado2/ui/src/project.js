/* ГРАДО 2 · проект в новом интерфейсе: список, открытие, запись в папку проектов, автосохранение, новый проект,
   файл .grado2 с диска и на диск. Те же адреса и тот же формат файла, что у рабочей страницы (web/project.js):
   GET/POST /api/project?name=… и ?autosave=1. Пишет весь файл из project.raw, меняя только то, что правит новый интерфейс
   (слои, группы, виды, граница, схема, листы «Макета листа» — ключ layouts в конце файла). */
import { nextTick, ref, toRaw, watch } from "vue";
import { basemapId, currentId, project, setProject, viewNow } from "./store.js";
import { dataRev, graphRev, resetHistory } from "./edit.js";
import { normGraph } from "./graphfile.js";
import { setSel } from "./features.js";

export const projects = ref([]);      // [{name, modified, size, album_n, star, opened}], новые сверху
export const trash = ref({ n: 0, items: [] });   // корзина папки проектов: сколько и что в ней (catalog.py)
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
export const editTick = () => tick;   // номер последней правки: окно «Листы и альбом» (albumhost.js) знает, видело ли оно её
watch([() => project.layers, () => project.groups, () => project.views, () => project.territory, () => project.layouts, basemapId, dataRev, graphRev], markDirty, { deep: true });

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
  trash.value.n = j.trash || 0;
  return j;
}

/* ---------- каталог: переименовать, копия, в корзину, вернуть, избранное (server.py post_catalog) ---------- */
async function catalogAct(act, body) {
  const r = await fetch("/api/project/" + act, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.status);
  return j;
}

/* Переименовать проект в папке; открытый сейчас проект меняет название сразу (шапка, автосохранение). */
export async function renameProject(name, to) {
  to = (to || "").trim();
  if (!to || to === name) return true;
  if (BAD_NAME.test(to)) { say("В названии не должно быть знаков / \\ : * ? \" < > | и точки в начале"); return false; }
  try {
    const j = await catalogAct("rename", { name, to });
    if (project.file === name) { project.name = project.file = j.name; autosave(); }
    say(`Проект «${name}» теперь называется «${j.name}»`);
    await listProjects();
    return true;
  } catch (e) { say("Не переименован: " + e.message); return false; }
}

/* Название открытой работы из шапки: сохранённый проект переименовывается, несохранённый — сохраняется под этим названием. */
export async function retitle(to) {
  to = (to || "").trim();
  if (!to || to === project.name) return true;
  if (project.file) return renameProject(project.file, to);
  const c = await clashOf(to);
  if (c) { say(`В папке уже есть проект «${c.name}»: выберите другое название`); return false; }
  return saveProject(to);
}

export async function copyProject(name) {
  try { const j = await catalogAct("copy", { name }); say(`Сделана копия «${j.name}»`); await listProjects(); return j.name; }
  catch (e) { say("Копия не сделана: " + e.message); return null; }
}

export async function trashProject(name) {
  try {
    await catalogAct("delete", { name });
    if (project.file === name) { project.file = null; dirty.value = true; autosave(); }   // открытая работа остаётся: «Сохранить» вернёт её в папку
    say(`Проект «${name}» в корзине. Вернуть — «Корзина» в окне «Проекты»`);
    await listProjects();
    return true;
  } catch (e) { say("Не удалён: " + e.message); return false; }
}

export async function listTrash() {
  const j = await getJSON("/api/projects/trash");
  trash.value = { n: (j.trash || []).length, items: j.trash || [] };
}

export async function restoreProject(id) {
  try { const j = await catalogAct("restore", { id }); say(`Проект «${j.name}» вернулся в папку`); await Promise.all([listProjects(), listTrash()]); return j.name; }
  catch (e) { say("Не возвращён: " + e.message); return null; }
}

export async function starProject(p) {
  const on = !p.star; p.star = on;
  try { await catalogAct("star", { name: p.name, on }); } catch (e) { p.star = !on; say("Не отмечен: " + e.message); }
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
    layouts: JSON.parse(JSON.stringify(project.layouts)),   // листы «Макета листа»: в файле всегда последним ключом (server.py with_layouts)
    ...extra,
  };
}

export function projectJSON(extra) {
  const { layouts, ...rest } = collect(extra), p = { ...rest, layouts }, big = [];   // листы — последним ключом: по нему сервер их находит
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
