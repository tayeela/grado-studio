/* ГРАДО 2 · окно «Листы и альбом»: альбом ППТ КРТ, рамки листов на карте, макет надписей, PDF и PPTX, ГИС ОГД в DXF.
   Это движок рабочей страницы без изменений (web/sheets.js, albums.js, frames.js, layout.js, ogdpick.js) в отдельном окне
   браузера по адресу /old?embed=album (web/embed.js): альбом собирается тем же кодом, что и прежде, лист в лист.
   Окно открывается как макет в QGIS — своим окном рядом с основным.
   Проект: окно получает его целиком (applyProject рабочей страницы), когда здесь была правка, которую окно ещё не видело
   (при открытии и когда окно снова в фокусе); правки окна (листы, загруженные слои, виды, группы) возвращаются сюда
   по разделам совместной работы (web/collab.js split, collab.js adopt) — схема расчёта и вид карты остаются здешние. */
import { nextTick, reactive, watch } from "vue";
import * as collabMod from "../../web/collab.js";
import { C, adopt } from "./collab.js";
import { editTick, markDirty, notice, projectJSON } from "./project.js";
import { project, theme } from "./store.js";

const { split } = collabMod.default || collabMod;

export const album = reactive({ open: false, ready: false, sheets: 0 });
/* App.vue подставляет: «Сохранить» (Ctrl+S в окне альбома) и открыть другой проект («Альбомы лежат в других проектах») */
export const albumHooks = { save: async () => {}, open: () => {} };

let win = null, base = null, seenTick = -1, firstPush = true, timer = null, waiting = [];
const META = ["territory", "checked", "groups", "views", "imports", "current_order"];   // что окно альбома может поменять в проекте
const live = () => !!win && !win.closed && typeof win.applyProject === "function";
const txt = v => JSON.stringify(v ?? null);
const clone = v => v == null ? v : JSON.parse(JSON.stringify(v));

/* Снимок разделов окна: тексты meta и альбома, у слоёв — описание и ссылки на данные (данные заменяются новым объектом). */
function snap(s) {
  const b = { meta: {}, album: txt(s.album), layers: {} };
  for (const k of META) b.meta[k] = txt(s.meta[k]);
  for (const n of Object.keys(s)) if (n.startsWith("layer:")) b.layers[n] = layerSig(s[n]);
  return b;
}
function layerSig(v) {
  const { fc, original, ...rest } = v.data || {};
  return { spec: txt(v.spec), head: txt(rest), fc, n: fc?.features?.length, feats: fc?.features, original };
}
const sameLayer = (a, b) => a.spec === b.spec && a.head === b.head && a.fc === b.fc && a.feats === b.feats && a.n === b.n && a.original === b.original;

/* Проект → окно: целиком, если окно ещё не видело последнюю правку. Вид карты — только в первый раз: дальше у окна свой. */
function push(force) {
  if (!live()) return;
  if (timer) { clearTimeout(timer); timer = null; pull(); }
  if (!force && editTick() === seenTick) return;
  try {
    const p = JSON.parse(projectJSON());
    if (!firstPush) delete p.view;
    win.applyProject(p);
    base = snap(split(win.collectProject()));
    seenTick = editTick(); firstPush = false;
    album.sheets = p.album?.sheets?.length || 0;
  } catch (e) {
    console.warn("albumhost: проект не передан", e);
    notice.value = "Окно «Листы и альбом» не получило проект: " + e.message;
  }
  role();
}

/* Окно → проект: только изменившиеся там разделы. */
function pull() {
  if (!live() || !base) return;
  const s = split(win.collectProject()), changed = {}, metaKeys = META.filter(k => txt(s.meta[k]) !== base.meta[k]);
  if (metaKeys.length) changed.meta = clone(s.meta);
  if (txt(s.album) !== base.album) changed.album = clone(s.album);
  const names = new Set([...Object.keys(s).filter(n => n.startsWith("layer:")), ...Object.keys(base.layers)]);
  for (const n of names) {
    if (!s[n]) { changed[n] = null; continue; }
    const was = base.layers[n];
    if (was && sameLayer(was, layerSig(s[n]))) continue;
    const { fc, original, ...rest } = s[n].data || {};
    changed[n] = { spec: clone(s[n].spec), data: s[n].data ? { ...clone(rest), fc: clone(fc), ...(original === undefined ? {} : { original: typeof original === "string" ? original : clone(original) }) } : null };
  }
  base = snap(s);
  const keys = Object.keys(changed);
  if (!keys.length) return;
  const caughtUp = editTick() === seenTick;          // здешних правок, которых окно не видело, нет — после приёма их тоже не будет
  if (keys.length === 1 && changed.album) project.raw.album = changed.album;
  else adopt(changed, metaKeys);
  album.sheets = s.album?.sheets?.length || 0;
  markDirty();
  if (caughtUp) nextTick(() => { seenTick = editTick(); });
}

/* наблюдатель — новому интерфейсу; роль «только просмотр» в совместном режиме — окну (sheets.js isViewer) */
function role() { if (live()) win.document.body.classList.toggle("hub-viewer", C.role === "viewer"); }

window.gradoEmbed = {
  ready(w) {
    win = w; firstPush = true; album.open = true;
    push(true); album.ready = true;
    const list = waiting; waiting = [];
    list.forEach(fn => { try { fn(win); } catch (e) { console.warn("albumhost", e); } });
  },
  changed() { clearTimeout(timer); timer = setTimeout(() => { timer = null; pull(); }, 300); },
  focus() { push(false); },
  closed(w) {
    if (w !== win) return;
    clearTimeout(timer); timer = null;
    try { pull(); } catch (e) { console.warn("albumhost: последние правки окна", e); }
    win = null; base = null; album.open = album.ready = false;
  },
  async save() { pull(); await albumHooks.save(); if (live()) win.toast?.(notice.value || "Проект сохранён"); },
  open(name) { albumHooks.open(name); },
};

/* Открыть окно альбома (или вывести вперёд) и, когда оно готово, выполнить then(окно): выгрузка PDF, ГИС ОГД. */
export function openAlbum(then) {
  if (live() && album.ready) { win.focus(); push(false); if (then) then(win); return; }
  if (then) waiting.push(then);
  if (win && !win.closed) { win.focus(); return; }
  const w = Math.round(screen.availWidth * .85), h = Math.round(screen.availHeight * .85);
  win = window.open(`/old?embed=album&theme=${theme.value}`, "grado-album", `popup,width=${w},height=${h}`);
  if (!win) { waiting = []; notice.value = "Браузер не дал открыть окно «Листы и альбом»: разрешите всплывающие окна для этого сайта"; return; }
  album.open = true; album.ready = false;
}

export const albumFile = kind => openAlbum(w => w.albumFile(kind));
export const ogdDxf = () => openAlbum(w => w.document.getElementById("bOgdAll")?.click());

watch(theme, t => { if (live()) win.setTheme?.(t); });
watch(() => C.role, role);
/* открыли другой проект — окно альбома получает его сразу; число листов — для кнопки в шапке */
watch(() => project.raw, r => { album.sheets = r?.album?.sheets?.length || 0; if (live() && album.ready) { firstPush = true; push(true); } }, { immediate: true });
addEventListener("pagehide", () => { if (live()) win.close(); });   // основное окно закрыли — окно альбома без него не работает
