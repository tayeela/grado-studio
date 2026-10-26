/* ГРАДО 2 · окно «Листы»: связь с движком альбома — рабочей страницей /old?embed=album (web/embed.js, albumapi.js).
   Движок без изменений (web/sheets.js, albums.js, frames.js, layout.js, ogdpick.js) собирает альбом тем же кодом, что и
   прежде, лист в лист. Он работает скрыто — невидимой рамкой iframe внутри нового интерфейса, а весь экран альбома —
   вкладка panels/AlbumPanel.vue, рамки листов на карте (те же рамки, что у видов, — viewframesmap.js) и «Макет надписей» (AlbumLayout.vue). Отдельного
   окна браузера («Подробно») больше нет (шаг 2 фаза 2, #94): всё, что было только в нём, перенесено во вкладку.
   Проект: движок получает его целиком (applyProject рабочей страницы), когда здесь была правка, которую он ещё не видел
   (перед каждым действием и когда окно снова в фокусе); правки движка (листы, загруженные слои, виды, группы) возвращаются
   сюда по разделам совместной работы (web/collab.js split, collab.js adopt) — схема расчёта и вид карты остаются здешние. */
import { nextTick, reactive, watch } from "vue";
import * as collabMod from "../../web/collab.js";
import { C, adopt } from "./collab.js";
import { editTick, markDirty, notice, projectJSON } from "./project.js";
import { project, theme } from "./store.js";
import { areaOgdReq, ogd, stopOgd } from "./data.js";

const { split } = collabMod.default || collabMod;

/* open — движок загружен; rev — номер приёма правок движка (окно перечитывает альбом) */
export const album = reactive({ lay: null, layTick: 0, open: false, ready: false, sheets: 0, rev: 0, say: "", want: null,   // want — выгрузка из меню, ждёт вкладку
  tab: false, cur: 0, fit: 0, frames: [] });   // вкладка на виду, выбранный лист, «приблизить к рамке», рамки листов (viewframesmap.js)
/* App.vue подставляет: «Сохранить» (Ctrl+S в окне альбома), открыть другой проект и показать вкладку «Листы» */
export const albumHooks = { save: async () => {}, open: () => {}, panel: () => {}, data: () => {} };

let win = null, frame = null, base = null, seenTick = -1, firstPush = true, timer = null, waiting = [];
const META = ["territory", "checked", "groups", "views", "imports", "current_order"];   // что окно альбома может поменять в проекте
const live = () => { try { return !!win && !win.closed && typeof win.applyProject === "function"; } catch { return false; } };
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
    notice.value = "Окно «Листы» не получило проект: " + e.message;
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
  album.sheets = s.album?.sheets?.length || 0; album.rev++;
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
  toast(t) { notice.value = t; album.say = t; },
  /* файл из скрытой рамки движка (web/albumapi.js): скачивает основное окно, с именем файла */
  download(b, name) {
    const url = URL.createObjectURL(new Blob([b], { type: b.type })), a = document.createElement("a");
    a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 30000);
  },
  async save() { pull(); await albumHooks.save(); if (live()) win.toast?.(notice.value || "Проект сохранён"); },
  open(name) { albumHooks.open(name); },
};

/* Движок готов — then(движок) сразу, иначе после загрузки. Окна «Подробно» нет — скрытая рамка iframe внутри страницы. */
function engine(then) {
  if (live() && album.ready) { push(false); if (then) then(win); return; }
  if (then) waiting.push(then);
  if (win && !win.closed) return;
  frame = document.createElement("iframe");
  frame.title = "Движок альбома"; frame.tabIndex = -1; frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;left:-20000px;top:0;width:1280px;height:800px;border:0;opacity:0;pointer-events:none";
  frame.src = `/old?embed=album&theme=${theme.value}`;
  document.body.appendChild(frame);
  win = frame.contentWindow; album.open = true; album.ready = false;
}
/* Действие движка: проект туда, затем fn(albumApi); результат — обещание. */
export function call(fn) {
  return new Promise((ok, bad) => engine(w => { try { ok(fn(w.albumApi)); } catch (e) { bad(e); } }));
}
/* правка альбома во вкладке: движок получает проект сразу, если он уже загружен */
export function sync() { if (live() && album.ready) push(false); }
/* правка листа i (рамка на карте: center, scale) — в раздел album проекта, как touch() движка */
export function editSheet(i, patch) {
  // сначала принять отложенную правку окна (changed → pull через 300 мс): иначе она заменит раздел album целиком и унесёт эту правку
  if (timer) { clearTimeout(timer); timer = null; pull(); }
  const a = project.raw?.album, s = a?.sheets?.[i]; if (!s) return;
  Object.assign(s, patch); a.meta ||= {}; a.meta.editedAt = new Date().toISOString();
  markDirty(); album.rev++; sync();
}
export const engineState = () => live() && album.ready ? win.albumApi?.state() : null;
export const startEngine = () => engine();
/* Рамки листов альбома — те же рамки, что у видов (viewframesmap.js): пока открыты «Виды» или «Макет листа», движок
   запускается (если в проекте есть листы) и рамки перечитываются раз в секунду, как во вкладке «Листы». */
let fpoll = 0, lastFrames = "";
function pollFrames() {
  const f = engineState()?.frames; if (!f) return;
  const t = JSON.stringify(f); if (t !== lastFrames) { lastFrames = t; album.frames = f; }
}
export function wantFrames(on) {
  clearInterval(fpoll); fpoll = 0;
  if (!on) return;
  if (album.sheets) startEngine();
  pollFrames(); fpoll = setInterval(pollFrames, 1000);
}

/* PDF и PPTX из меню «Выгрузка» — вкладка «Листы» (там видно ход выгрузки и вопрос «не всё готово»). */
export const albumFile = kind => { album.want = kind; albumHooks.panel(); };
/* «Выгрузка» → «ГИС ОГД в DXF»: лист — выбранный во вкладке (если он на карте) или последний на карте; окно «Данные» открывает
   «Исходные данные» в режиме DXF (слои портала по рамке листа), выгрузку ведёт data.js startOgd. Идёт выгрузка — пункт её останавливает. */
export async function ogdDxf() {
  if (ogd.running) return stopOgd();
  // лист альбома на карте — по его рамке; листов нет или движок альбома не ответил за 15 с — по области загрузки (раньше кнопка молчала)
  let r = null;
  if (album.sheets) try { r = await Promise.race([call(a => a.ogdSheet(album.cur)), new Promise(ok => setTimeout(() => ok(null), 15000))]); } catch { r = null; }
  r ||= areaOgdReq();
  if (!r) { notice.value = "Слои в DXF: сначала нарисуйте границу территории или вид — по ним выгружаются слои"; albumHooks.data(); return; }
  ogd.req = JSON.parse(JSON.stringify(r)); albumHooks.data();
}

watch(theme, t => { if (live()) win.setTheme?.(t); });
watch(() => C.role, role);
/* открыли другой проект — окно альбома получает его сразу; число листов — для кнопки в шапке */
watch(() => project.raw, r => { album.sheets = r?.album?.sheets?.length || 0; album.rev++; if (live() && album.ready) { firstPush = true; push(true); } }, { immediate: true });
