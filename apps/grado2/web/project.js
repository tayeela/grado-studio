/* ГРАДО 2 · проект: сохранение в «Документы/ГРАДО 2» (файл .grado2 = JSON), открытие, новый проект,
   автосохранение с восстановлением после перезагрузки страницы.
   В файле: граница, слои (порядок, стиль, видимость), их данные с исходной выгрузкой, граф, вид карты. */

// litegraph приходит полной сборкой с демо-узлами (сеть, файлы, websocket): из файла проекта их не создать
Object.keys(LiteGraph.registered_node_types).filter(t => !/^(Данные|Параметры|Геометрия|Эскиз|Показатели|Анализ)\//.test(t))
  .forEach(t => LiteGraph.unregisterNodeType(t));
const PROJ = { name: null, file: null, dirty: false, tick: 0, savedTick: 0, autoTick: 0, loading: true };   // loading до projectStart: стартовые пересчёты — не правки
const PROJ_FORMAT = "grado2", PROJ_VERSION = 2;
/* Формат проекта с номером версии: файл старой версии при открытии проходит миграции по порядку, файл новее
   программы не открывается (иначе незнакомые поля молча пропали бы при следующем сохранении).
   v1 → v2 (ГРАДО 2 0.7–0.12): группы слоёв, виды карты, альбом листов, шестой параметр «Посадки» — этажность по цели. */
const MIGRATIONS = {
  1: p => {
    p.groups ||= []; p.views ||= []; p.album ||= { meta: {}, sheets: [] };
    (p.layers || []).forEach(l => { if (!("group" in l)) l.group = null; });
    (p.graph?.nodes || []).forEach(n => { if (n.type === "Эскиз/Посадка застройки" && Array.isArray(n.widgets_values) && n.widgets_values.length < 6) n.widgets_values[5] = "заданной"; });
    return p;
  },
};
function migrate(p) {
  let v = p.version || 1;
  if (v > PROJ_VERSION) throw new Error(`файл сохранён более новой версией ГРАДО 2 (формат ${v}, эта программа понимает до ${PROJ_VERSION}) — обновите программу`);
  while (v < PROJ_VERSION) { p = MIGRATIONS[v](p); v++; }
  p.version = PROJ_VERSION;
  // «потолок» → «предельная высота» (01.10.2026): без смены формата — идемпотентно, при каждой загрузке (migrate.js)
  return MIGRATE.renameCeiling(p);
}
window.migrateProject = migrate;

function markDirty() {
  if (PROJ.loading || window.Collab?.applying) return;           // чужие правки, пришедшие по сети, — не наши правки (collab.js)
  if (PROJ.tick === PROJ.autoTick) PROJ.pendingSince = Date.now();
  PROJ.tick++; PROJ.lastEdit = Date.now(); if (!PROJ.dirty) { PROJ.dirty = true; syncProjTitle(); }
  window.Collab?.touched();                                      // совместный режим: отправка на сервер с паузой; в локальном — пусто
}
function syncProjTitle() {
  const b = $("bProj"); if (!b) return;
  b.querySelector(".lb").textContent = (PROJ.name || "Без названия") + (PROJ.dirty ? " •" : "");
  b.title = (PROJ.name ? `Проект «${PROJ.name}»` : "Проект не сохранён") + (PROJ.dirty ? " · есть несохранённые изменения (автосохранение держит их до сохранения)" : " · сохранён") + ". Проекты — окно «Проекты», Ctrl+S — сохранить.";
  document.title = (PROJ.name || "Без названия") + (PROJ.dirty ? " •" : "") + " — ГРАДО 2";
}

function collectProject() {
  const v = sharedView;
  return {
    format: PROJ_FORMAT, version: PROJ_VERSION, app: "ГРАДО 2 " + (window.APP_VERSION || ""), name: PROJ.name, file: PROJ.file, saved_at: new Date().toISOString(), dirty: PROJ.dirty,
    view: { center: ol.proj.toLonLat(v.getCenter()), zoom: v.getZoom(), basemap: BASE },
    territory: TERR,
    imports: Object.fromEntries(Object.entries(SOURCES).filter(([k, s]) => k.startsWith("import:") || s.kind === "fgistp")),
    checked: [...CHECKED],
    current: CUR,
    groups: GROUPS.map(g => ({ ...g })), views: VIEWS, album: ALBUM,
    layers: LYR.map(l => ({ key: l.key, title: l.title, geom: l.geom, visible: l.visible, layerOpacity: l.layerOpacity, open: l.open, group: l.group, style: l.style })),
    data: Object.fromEntries(Object.entries(DATA).map(([k, d]) => [k, { title: d.title, source: d.source, fetched_at: d.fetched_at, notes: d.notes, history: d.history, shp: d.shp, fc: d.fc, original: d.original === d.fc ? "=fc" : d.original }])),   // нетронутая выгрузка не пишется дважды
    graph: graph.serialize(),
  };
}

/* Текст проекта для записи: данные слоя, которые не менялись с прошлой записи, не сериализуются заново — их JSON
   берётся из кэша по самому объекту (после правки у слоя новый объект данных). 100 000 объектов: запись без правок
   больше не замирает на десятые доли секунды. */
const JCACHE = new WeakMap();
const jsonOf = o => { let t = JCACHE.get(o); if (t === undefined) { t = JSON.stringify(o); JCACHE.set(o, t); } return t; };
function projectJSON(extra) {
  const p = { ...collectProject(), ...extra }, big = [];
  p.data = Object.fromEntries(Object.entries(p.data).map(([k, d]) => {
    const o = { ...d };
    for (const f of ["fc", "original"]) if (o[f] && typeof o[f] === "object") { big.push(o[f]); o[f] = `@@GRADO_BIG_${big.length - 1}@@`; }
    return [k, o];
  }));
  return JSON.stringify(p).replace(/"@@GRADO_BIG_(\d+)@@"/g, (_, i) => jsonOf(big[+i]));
}
function clearProject() {
  PROJ.askName = null;                                           // согласие заменить файл относится к прежнему проекту
  window.PROJ_EPOCH = (window.PROJ_EPOCH || 0) + 1;              // идущие выгрузки и подбор вариантов относятся к прежнему проекту
  if (typeof varRun !== "undefined" && varRun) varRun.stop = true;
  LYR.splice(0).forEach(l => ALLMAPS.forEach(m => m.getLayers().getArray().filter(x => x.get("key") === l.key).forEach(x => m.removeLayer(x))));
  Object.keys(DATA).forEach(k => { delete DATA[k]; layerSrc[k]?.clear(); });
  Object.keys(SOURCES).filter(k => k.startsWith("import:") || SOURCES[k].kind === "fgistp").forEach(k => delete SOURCES[k]);
  Object.assign(ALBUM.meta, { object: "", code: "", stage: "ПП", org: "", slide: "P" });   // штамп нового проекта — не от прежнего
  TERR = null; TERR_M2 = 0; TERR_REV++; terrSrc.clear(); $("bLoad").disabled = true;
  $("terrInfo").textContent = "Граница не задана: нарисуйте её на карте (двойной щелчок завершает) или возьмите пример.";
  CUR = null; setSel([]); UNDO.length = 0; REDO.length = 0; GROUPS.length = 0; VIEWS.length = 0; VIEW_CUR = null; ALBUM.sheets.length = 0; delete ALBUM.frames; window.redrawFrames?.(); ERRORS = {}; VARS = []; varSel = -1; measureSrc.clear();
  $("vlist").innerHTML = `<div class="empty">Нажмите «Подобрать варианты», чтобы сравнить типологии в пределах ограничений.</div>`;
}

// ключи из чужого файла проекта: Object.assign с «__proto__» подменил бы прототип — такие ключи отбрасываются
const BAD_KEY = /^(__proto__|constructor|prototype)$/;
const safeObj = o => Object.fromEntries(Object.entries(o && typeof o === "object" && !Array.isArray(o) ? o : {}).filter(([k]) => !BAD_KEY.test(k)));
// идентификатор вида и листа идёт в атрибуты разметки — только буквы, цифры и «_»; лист ссылается на вид тем же правилом
const safeId = id => String(id ?? "").replace(/\W/g, "");
function applyProject(p) {
  if (p?.format !== PROJ_FORMAT) throw new Error("это не файл проекта ГРАДО 2");
  p = migrate(p);
  PROJ.loading = true;
  try {
    clearProject();
    Object.entries(safeObj(p.imports)).forEach(([k, s]) => { if (s && typeof s === "object") SOURCES[k] = { ...safeObj(s), title: String(s.title ?? k), kind: String(s.kind ?? "import") }; });
    CHECKED.clear(); (p.checked || []).forEach(k => CHECKED.add(k));
    if (p.territory) setTerritory(p.territory);
    for (const s of p.layers || []) {
      const d = p.data?.[s.key]; if (!d) continue;
      DATA[s.key] = { ...d, fc: d.fc || { type: "FeatureCollection", features: [] }, count: 0, fields: [] };
      if (d.original === "=fc") delete DATA[s.key].original;      // исходная выгрузка совпадала с данными: её возьмёт setLayerData
      layerSrc[s.key] ||= new ol.source.Vector(); setLayerData(s.key, DATA[s.key].fc);
      if (!d.original) delete DATA[s.key].original;              // свой слой: «исходной выгрузки» у него нет
      if (!d.fc?.features?.length) DATA[s.key].fields = ["Наименование", "Примечание"];
      const l = ensureLayer(s.key, s.title, s.geom);
      Object.assign(l, { visible: s.visible, layerOpacity: okn(s.layerOpacity, 1), open: !!s.open, style: ST(s.style || {}) });
    }
    GROUPS.push(...(p.groups || []).map(g => ({ id: g.id, title: g.title, visible: g.visible !== false, open: g.open !== false })));   // группы — после загрузки слоёв: пока слои приходят по одному, нормализация сочла бы группы пустыми
    (p.layers || []).forEach(s => { const l = lyr(s.key); if (l) l.group = s.group || null; });
    const order = (p.layers || []).map(s => s.key);            // порядок прорисовки — как в файле
    LYR.sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
    normGroups(); LYR.forEach(l => { l.cache.clear(); l._br = null; if (kindOf(l) !== l._kind || (l.style.maxDen || 0) !== (l._maxDen || 0) || (l.style.minDen || 0) !== (l._minDen || 0)) rebuildLayer(l); else if (l.gl) restyle(l); });
    CUR = lyr(p.current) ? p.current : LYR[0]?.key || null;
    VIEWS.push(...(p.views || []).map(v => ({ ...v, id: safeId(v.id) })));
    Object.assign(ALBUM.meta, { object: "", code: "", stage: "ПП", org: "", slide: "P" }, safeObj(p.album?.meta)); window.hideSheetFrame?.(); ALBUM.sheets.splice(0, ALBUM.sheets.length, ...(p.album?.sheets || []).map(s => { const x = { ...s }; if (x.scale != null) x.scale = okn(x.scale, 0); if (x.view != null) x.view = safeId(x.view); if (x.photos != null && !Array.isArray(x.photos)) delete x.photos; return x; })); ALBUM.frames = p.album?.frames; window.migrateFrames?.();   // листы v0.56 → листы альбома
    if (p.graph) graph.configure(p.graph);
    graph._nodes.forEach(n => n.widgets?.forEach(w => { if (w.value === undefined) w.value = (w.options?.min ?? 0) > 0 ? w.options.min : 0; }));   // проект старой версии: у нового поля узла нет значения
    if (p.view?.center) { sharedView.setCenter(ol.proj.fromLonLat(p.view.center)); sharedView.setZoom(p.view.zoom); }
    if (p.view?.basemap && p.view.basemap !== BASE) setBasemap(p.view.basemap);
    go.fitted = false; dataRev++; lastSig = ""; recompute(true); renderParams();
    applyOrder(); LYR.forEach(l => layerSrc[l.key].changed()); renderSources(); renderTree(); renderRight(); renderTable(); setTool("select"); syncPreview(); portalStyles(); setBySheet(!!ALBUM.meta.treeBySheet);
    window.renderSheets?.(); window.renderViews?.();
  } finally { PROJ.loading = false; }
  // file — имя файла в папке проектов, в который этот проект сохранялся (у открытого с диска файла его нет):
  // по нему «Сохранить» отличает свой файл от чужого с тем же названием
  PROJ.name = p.name || null; PROJ.file = p.file !== undefined ? p.file : p.name || null; PROJ.dirty = !!p.dirty; PROJ.autoTick = PROJ.tick;
  PROJ.savedTick = p.dirty ? -1 : PROJ.tick; syncProjTitle();      // восстановленная несохранённая правка остаётся несохранённой
  // слои ГИС ОГД и ЕГКО из проекта до v0.32 выгружены из GeoJSON портала и стоят на ~7,7 м в стороне: сказать и дать перевыгрузить
  // с v0.32 сервер ставит shp всем слоям ГИС ОГД и ЕГКО: слой без метки смещён, в какой бы версии проект ни сохраняли
  window.STALE_OGD = Object.keys(DATA).filter(k => /^(gisogd|egko)\./.test(k) && DATA[k].fetched_at && !DATA[k].shp);
  if (STALE_OGD.length) { renderSources(); toast(STALE_OGD.length === 1 ? "В проекте слой ГИС ОГД / ЕГКО, выгруженный до v0.32: он стоит на ~7,7 м в стороне. Окно «Данные» → «Выгрузить заново»."
    : `В проекте ${plural(STALE_OGD.length, ["слой", "слоя", "слоёв"])} ГИС ОГД / ЕГКО, выгруженных до v0.32: они стоят на ~7,7 м в стороне. Окно «Данные» → «Выгрузить заново».`); }
}

// совместный режим: «Сохранить» и Ctrl+S — немедленная отправка правок на сервер (проекты лежат на сервере, не в папке)
async function hubSave() {
  if (!window.Collab?.on || !Collab.pid) return toast("Откройте совместный проект: окно «Проекты».");
  if (Collab.role === "viewer") return toast("Только просмотр: попросите владельца дать права на правку.");
  toast(await Collab.flush() ? "Сохранено на сервере" : "Нет связи с сервером: правки сохранятся, когда связь вернётся.");
}
async function saveProject(name) {
  if (window.HUB_MODE) return hubSave();
  name = (name ?? PROJ.name ?? "").trim();
  if (!name) return openProjects(true);
  // другое название, чем у своего файла, и такой проект в папке уже есть (регистр и «ё» не различаются файловой
  // системой) — без второго нажатия чужой проект не заменяется
  if (name !== PROJ.file) {
    const norm = x => x.normalize("NFC").toLowerCase();
    try {
      const clash = (await (await fetch("/api/projects")).json()).projects.find(q => norm(q.name) === norm(name));
      if (clash && !(PROJ.askName === norm(name) && Date.now() - PROJ.askT < 8000)) {
        PROJ.askName = norm(name); PROJ.askT = Date.now();
        return toast(`В папке уже есть проект «${clash.name}» (изменён ${new Date(clash.modified * 1000).toLocaleString("ru-RU")}). Сохраните ещё раз в течение 8 с, чтобы заменить его, или введите другое название.`);
      }
    } catch { }
  }
  PROJ.askName = null;
  const prev = PROJ.name, prevFile = PROJ.file; PROJ.name = name; PROJ.file = name;
  const tick = PROJ.tick, body = projectJSON({ dirty: false });
  busy(true);
  try {
    const r = await fetch("/api/project?name=" + encodeURIComponent(name), { method: "POST", headers: { "Content-Type": "application/json" }, body }); const j = await r.json();
    if (!r.ok) throw new Error(j.error === "bad project name" ? "в названии не должно быть знаков / \\ : * ? \" < > | и точки в начале" : j.error);
    PROJ.savedTick = tick; PROJ.dirty = PROJ.tick !== tick; syncProjTitle(); autosave(true);
    toast(`Проект «${name}» сохранён в папке «${j.saved.split(/[\\/]/).slice(-2, -1)[0] || "проектов"}».`); if (!$("wProjects").hidden) renderProjects();
  } catch (e) { PROJ.name = prev; PROJ.file = prevFile; syncProjTitle(); toast("Проект не сохранён: " + e.message); }
  finally { busy(false); }
}

async function openProject(name) {
  if (!confirmLoss(`Открыть «${name}»?`)) return;
  busy(true);
  try {
    const r = await fetch("/api/project?name=" + encodeURIComponent(name)); if (!r.ok) throw new Error("файл не найден");
    applyProject(await r.json()); PROJ.file = name; PROJ.dirty = false; syncProjTitle(); autosave(true);
    toast(`Открыт проект «${name}».`); winOpen("wProjects", false);
  } catch (e) { toast("Проект не открылся: " + e.message); } finally { busy(false); }
}

function newProject() {
  if (!confirmLoss("Начать новый проект?")) return;
  PROJ.loading = true;
  try { clearProject(); graph.configure(JSON.parse(DEFAULT_GRAPH)); dataRev++; lastSig = ""; recompute(true); renderParams(); renderSources(); renderTree(); renderRight(); renderTable(); setTool("select"); syncStatus(); }
  finally { PROJ.loading = false; }
  window.renderSheets?.(); window.renderViews?.();
  PROJ.name = PROJ.file = null; PROJ.dirty = false; PROJ.savedTick = PROJ.autoTick = PROJ.tick; syncProjTitle(); autosave(true);
  toast("Новый проект. Прежний остался в папке проектов, если был сохранён."); winOpen("wProjects", false);
}
const DEFAULT_GRAPH = JSON.stringify(graph.serialize());          // граф по умолчанию — снимок на старте, до правок

// несохранённое не теряем молча: второй выбор того же действия в течение 4 с подтверждает
let lossAt = 0;
function confirmLoss(what) {
  if (!PROJ.dirty) return true;
  if (Date.now() - lossAt < 4000) { lossAt = 0; return true; }
  lossAt = Date.now(); toast(`${what} Несохранённые изменения пропадут — повторите действие, чтобы подтвердить, или сначала сохраните (Ctrl+S).`); return false;
}

/* ---------- автосохранение: после каждой правки, с паузой 2 с ---------- */
// ponytail: при долгой непрерывной правке пишет файл раз в ~3 с целиком; инкрементальная запись — если проекты станут в сотни МБ
/* автосохранение — когда правки затихли на 1,5 с (перетаскивание вершины, ползунок — это десятки правок подряд),
   но не реже раза в 15 с при непрерывной работе; одно сохранение за раз */
let autoBusy = false, autoAgain = false;
async function autosave() {
  if (window.HUB_MODE) return;                     // совместный режим: локального автосохранения нет, правки уходят через Collab
  if (autoBusy) { autoAgain = true; return; }      // идёт запись — следующая пойдёт сразу за ней (новый проект не должен потеряться)
  autoBusy = true; const tick = PROJ.tick;
  try { const r = await fetch("/api/project?autosave=1", { method: "POST", headers: { "Content-Type": "application/json" }, body: projectJSON() }); if (r.ok) PROJ.autoTick = tick; } catch { }
  finally { autoBusy = false; if (autoAgain) { autoAgain = false; autosave(); } }
}
setInterval(() => {
  if (PROJ.loading || PROJ.tick === PROJ.autoTick || autoBusy) return;
  const t = Date.now(); if (t - (PROJ.lastEdit || 0) > 1500 || t - (PROJ.pendingSince || t) > 15000) autosave();
}, 500);

/* ---------- окно «Проекты» ---------- */
const fmtDate = t => new Date(t * 1000).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
const fmtSize = b => b > 1e6 ? fmt(b / 1e6, 1) + " МБ" : fmt(Math.max(1, b / 1e3)) + " КБ";
async function renderProjects() {
  let r; try { r = await (await fetch("/api/projects")).json(); } catch { $("projList").innerHTML = `<div class="empty">Сервер не отвечает</div>`; return; }
  $("projDir").textContent = r.dir; $("projDir").title = `${r.dir}\nПапка проектов: файлы .grado2 можно копировать и пересылать`;
  $("projList").innerHTML = r.projects.length ? `<table class="at"><thead><tr><th>Проект</th><th>Изменён</th><th>Размер</th><th></th></tr></thead><tbody>${r.projects.map(p =>
    `<tr${p.name === PROJ.name ? ' class="sel"' : ""}><td>${esc(p.name)}</td><td class="num">${fmtDate(p.modified)}</td><td class="num">${fmtSize(p.size)}</td><td><button class="btn" data-open="${esc(p.name)}">Открыть</button></td></tr>`).join("")}</tbody></table>`
    : `<div class="empty">Сохранённых файлов в папке нет. Открытая работа сохраняется сама (автосохранение); Ctrl+S — сохранить под именем.</div>`;
}
function openProjects(focusName) {
  winOpen("wProjects", true); $("projName").value = PROJ.name || ""; renderProjects();
  if (focusName) { $("projName").focus(); $("projName").select(); toast("Назовите проект, чтобы сохранить его."); }
}
WIN_OPEN.wProjects = () => renderProjects();      // окно, восстановленное открытым после перезагрузки, тоже подгружает список
$("bProj").onclick = () => { if (!window.HUB_MODE) return openProjects(false); (window.HubUI?.openProjects || window.HubUI?.projects)?.(); };   // в совместном режиме — окно хаба, не локальная папка
$("projSave").onclick = () => saveProject($("projName").value);
$("projName").addEventListener("keydown", e => { if (e.key === "Enter") saveProject($("projName").value); });
$("projNew").onclick = newProject;
$("projList").addEventListener("click", e => { const b = e.target.closest("[data-open]"); if (b) openProject(b.dataset.open); });
$("projDownload").onclick = () => {
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([projectJSON()], { type: "application/json" }));
  a.download = (PROJ.name || "проект") + ".grado2"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
};
$("projFile").onchange = e => { const f = e.target.files[0]; e.target.value = ""; if (f) openProjectFile(f); };
window.openProjectFile = async f => {
  if (!confirmLoss(`Открыть «${f.name}»?`)) return;
  try { const p = JSON.parse(await f.text()); p.name ||= f.name.replace(/\.grado2$/i, ""); applyProject(p); PROJ.file = null; PROJ.dirty = true; syncProjTitle(); toast(`Открыт файл «${f.name}». Сохраните проект, чтобы он появился в папке проектов.`); winOpen("wProjects", false); }
  catch (err) { toast("Файл не открылся: " + err.message); }
};
addEventListener("keydown", e => { if ((e.metaKey || e.ctrlKey) && (e.code === "KeyS" || e.key === "s")) { e.preventDefault(); saveProject(); } });   // saveProject сам уходит в hubSave в совместном режиме

/* ---------- старт: восстановить последнюю работу ---------- */
window.markDirty = markDirty;
// Режим (обычный или совместный) узнаётся первым делом: на общем сервере без входа отвечают только /api/health и страницы,
// поэтому startApp (app.js) ждёт hubGate — после входа идут остальные запросы; вход и открытие проекта ведёт hub.js
let modeP = null;
window.hubGate = () => modeP ||= (async () => {
  try { window.HUB_MODE = !!(await (await fetch("/api/health")).json()).hub; } catch { window.HUB_MODE = false; }
  window.dispatchEvent(new Event("grado:mode"));       // hub.js ждёт режим (вход, окна, движок Collab); один раз за страницу
  if (window.HUB_MODE) await window.HubUI?.requireSession();
  window.HUB_IN = true;
})();
window.projectStart = async () => {
  await window.hubGate();
  if (window.HUB_MODE) { PROJ.loading = false; PROJ.dirty = false; PROJ.savedTick = PROJ.autoTick = PROJ.tick; syncProjTitle(); window.HubUI?.enter?.(); return; }
  try {
    const list = await (await fetch("/api/projects")).json();       // без автосохранения — без лишнего запроса и 404
    const p = list.autosave ? await (await fetch("/api/project?autosave=1")).json() : null;
    if (p && (p.layers?.length || p.territory || p.name)) {
      applyProject(p);
      return toast(`Восстановлена последняя работа${p.name ? ` («${p.name}»)` : ""} от ${new Date(p.saved_at).toLocaleString("ru-RU")}. Новый проект — окно «Проекты».`);
    }
  } catch (e) { console.warn("autosave restore", e); }
  PROJ.loading = false; PROJ.dirty = false; PROJ.savedTick = PROJ.autoTick = PROJ.tick; syncProjTitle();
};
syncProjTitle();
