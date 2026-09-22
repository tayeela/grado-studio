/* ГРАДО 2 · проект: сохранение в «Документы/ГРАДО 2» (файл .grado2 = JSON), открытие, новый проект,
   автосохранение с восстановлением после перезагрузки страницы.
   В файле: граница, слои (порядок, стиль, видимость), их данные с исходной выгрузкой, граф, вид карты. */

const PROJ = { name: null, dirty: false, tick: 0, savedTick: 0, autoTick: 0, loading: true };   // loading до projectStart: стартовые пересчёты — не правки
const PROJ_FORMAT = "grado2", PROJ_VERSION = 1;

function markDirty() { if (PROJ.loading) return; PROJ.tick++; if (!PROJ.dirty) { PROJ.dirty = true; syncProjTitle(); } }
function syncProjTitle() {
  const b = $("bProj"); if (!b) return;
  b.querySelector(".lb").textContent = (PROJ.name || "Без названия") + (PROJ.dirty ? " •" : "");
  b.title = (PROJ.name ? `Проект «${PROJ.name}»` : "Проект не сохранён") + (PROJ.dirty ? " · есть несохранённые изменения (автосохранение держит их до сохранения)" : " · сохранён") + ". Проекты — окно «Проекты», Ctrl+S — сохранить.";
  document.title = (PROJ.name || "Без названия") + (PROJ.dirty ? " •" : "") + " — ГРАДО 2";
}

function collectProject() {
  const v = sharedView;
  return {
    format: PROJ_FORMAT, version: PROJ_VERSION, name: PROJ.name, saved_at: new Date().toISOString(), dirty: PROJ.dirty,
    view: { center: ol.proj.toLonLat(v.getCenter()), zoom: v.getZoom() },
    territory: TERR,
    imports: Object.fromEntries(Object.entries(SOURCES).filter(([k]) => k.startsWith("import:"))),
    checked: [...CHECKED],
    current: CUR,
    layers: LYR.map(l => ({ key: l.key, title: l.title, geom: l.geom, visible: l.visible, layerOpacity: l.layerOpacity, open: l.open, style: l.style })),
    data: Object.fromEntries(Object.entries(DATA).map(([k, d]) => [k, { title: d.title, source: d.source, fetched_at: d.fetched_at, notes: d.notes, fc: d.fc, original: d.original }])),
    graph: graph.serialize(),
  };
}

function clearProject() {
  LYR.splice(0).forEach(l => ALLMAPS.forEach(m => m.getLayers().getArray().filter(x => x.get("key") === l.key).forEach(x => m.removeLayer(x))));
  Object.keys(DATA).forEach(k => { delete DATA[k]; layerSrc[k]?.clear(); });
  Object.keys(SOURCES).filter(k => k.startsWith("import:")).forEach(k => delete SOURCES[k]);
  TERR = null; TERR_M2 = 0; terrSrc.clear(); $("bLoad").disabled = true;
  $("terrInfo").textContent = "Граница не задана: нарисуйте её на карте (двойной щелчок завершает) или возьмите пример.";
  CUR = null; SEL = null; UNDO.length = 0; ERRORS = {}; VARS = []; varSel = -1; measureSrc.clear();
  $("vlist").innerHTML = `<div class="empty">Нажмите «Сгенерировать», чтобы сравнить варианты.</div>`;
}

function applyProject(p) {
  if (p?.format !== PROJ_FORMAT) throw new Error("это не файл проекта ГРАДО 2");
  PROJ.loading = true;
  try {
    clearProject();
    Object.assign(SOURCES, p.imports || {});
    CHECKED.clear(); (p.checked || []).forEach(k => CHECKED.add(k));
    if (p.territory) setTerritory(p.territory);
    for (const s of p.layers || []) {
      const d = p.data?.[s.key]; if (!d) continue;
      DATA[s.key] = { ...d, fc: d.fc || { type: "FeatureCollection", features: [] }, count: 0, fields: [] };
      layerSrc[s.key] ||= new ol.source.Vector(); setLayerData(s.key, DATA[s.key].fc);
      if (!d.original) delete DATA[s.key].original;              // свой слой: «исходной выгрузки» у него нет
      if (!d.fc?.features?.length) DATA[s.key].fields = ["Наименование", "Примечание"];
      const l = ensureLayer(s.key, s.title, s.geom);
      Object.assign(l, { visible: s.visible, layerOpacity: s.layerOpacity ?? 1, open: !!s.open, style: ST(s.style || {}) });
    }
    const order = (p.layers || []).map(s => s.key);            // порядок прорисовки — как в файле
    LYR.sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
    LYR.forEach(l => { l.cache.clear(); l._br = null; });
    CUR = lyr(p.current) ? p.current : LYR[0]?.key || null;
    if (p.graph) graph.configure(p.graph);
    if (p.view?.center) { sharedView.setCenter(ol.proj.fromLonLat(p.view.center)); sharedView.setZoom(p.view.zoom); }
    go.fitted = false; dataRev++; lastSig = ""; recompute(true); renderParams();
    applyOrder(); LYR.forEach(l => layerSrc[l.key].changed()); renderSources(); renderTree(); renderRight(); renderTable(); setTool("select");
  } finally { PROJ.loading = false; }
  PROJ.name = p.name || null; PROJ.dirty = !!p.dirty; PROJ.savedTick = PROJ.autoTick = PROJ.tick; syncProjTitle();
}

async function saveProject(name) {
  name = (name ?? PROJ.name ?? "").trim();
  if (!name) return openProjects(true);
  const prev = PROJ.name; PROJ.name = name;
  const tick = PROJ.tick, body = JSON.stringify({ ...collectProject(), dirty: false });
  busy(true);
  try {
    const r = await fetch("/api/project?name=" + encodeURIComponent(name), { method: "POST", body }); const j = await r.json();
    if (!r.ok) throw new Error(j.error === "bad project name" ? "в названии не должно быть знаков / \\ : * ? \" < > | и точки в начале" : j.error);
    PROJ.savedTick = tick; PROJ.dirty = PROJ.tick !== tick; syncProjTitle(); autosave(true);
    toast(`Проект «${name}» сохранён: ${j.saved}`); if (!$("wProjects").hidden) renderProjects();
  } catch (e) { PROJ.name = prev; syncProjTitle(); toast("Проект не сохранён: " + e.message); }
  finally { busy(false); }
}

async function openProject(name) {
  if (!confirmLoss(`Открыть «${name}»?`)) return;
  busy(true);
  try {
    const r = await fetch("/api/project?name=" + encodeURIComponent(name)); if (!r.ok) throw new Error("файл не найден");
    applyProject(await r.json()); PROJ.dirty = false; syncProjTitle(); autosave(true);
    toast(`Открыт проект «${name}».`); winOpen("wProjects", false);
  } catch (e) { toast("Проект не открылся: " + e.message); } finally { busy(false); }
}

function newProject() {
  if (!confirmLoss("Начать новый проект?")) return;
  PROJ.loading = true;
  try { clearProject(); graph.configure(JSON.parse(DEFAULT_GRAPH)); dataRev++; lastSig = ""; recompute(true); renderParams(); renderSources(); renderTree(); renderRight(); renderTable(); setTool("select"); syncStatus(); }
  finally { PROJ.loading = false; }
  PROJ.name = null; PROJ.dirty = false; PROJ.savedTick = PROJ.autoTick = PROJ.tick; syncProjTitle(); autosave(true);
  toast("Новый проект. Прежний остался в папке проектов, если был сохранён."); winOpen("wProjects", false);
}
const DEFAULT_GRAPH = JSON.stringify(graph.serialize());          // граф по умолчанию — снимок на старте, до правок

// несохранённое не теряем молча: второй выбор того же действия в течение 4 с подтверждает
let lossAt = 0;
function confirmLoss(what) {
  if (!PROJ.dirty || PROJ.savedTick === PROJ.tick && PROJ.name) return true;
  if (Date.now() - lossAt < 4000) { lossAt = 0; return true; }
  lossAt = Date.now(); toast(`${what} Несохранённые изменения пропадут — повторите действие, чтобы подтвердить, или сначала сохраните (Ctrl+S).`); return false;
}

/* ---------- автосохранение: после каждой правки, с паузой 2 с ---------- */
// ponytail: при долгой непрерывной правке пишет файл раз в ~3 с целиком; инкрементальная запись — если проекты станут в сотни МБ
let autoT = null;
function autosave(now) {
  clearTimeout(autoT); autoT = null;
  const run = async () => {
    autoT = null; const tick = PROJ.tick;
    try { const r = await fetch("/api/project?autosave=1", { method: "POST", body: JSON.stringify(collectProject()) }); if (r.ok) PROJ.autoTick = tick; } catch { }
  };
  now ? run() : autoT = setTimeout(run, 2000);
}
setInterval(() => { if (!PROJ.loading && PROJ.tick !== PROJ.autoTick && !autoT) autosave(); }, 1000);

/* ---------- окно «Проекты» ---------- */
const fmtDate = t => new Date(t * 1000).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
const fmtSize = b => b > 1e6 ? fmt(b / 1e6, 1) + " МБ" : fmt(Math.max(1, b / 1e3)) + " КБ";
async function renderProjects() {
  let r; try { r = await (await fetch("/api/projects")).json(); } catch { $("projList").innerHTML = `<div class="empty">Сервер не отвечает</div>`; return; }
  $("projDir").textContent = r.dir; $("projDir").title = "Папка проектов: файлы .grado2 можно копировать и пересылать";
  $("projList").innerHTML = r.projects.length ? `<table class="at"><thead><tr><th>Проект</th><th>Изменён</th><th>Размер</th><th></th></tr></thead><tbody>${r.projects.map(p =>
    `<tr${p.name === PROJ.name ? ' class="sel"' : ""}><td>${esc(p.name)}</td><td class="num">${fmtDate(p.modified)}</td><td class="num">${fmtSize(p.size)}</td><td><button class="btn" data-open="${esc(p.name)}">Открыть</button></td></tr>`).join("")}</tbody></table>`
    : `<div class="empty">Сохранённых проектов пока нет. Введите название выше и нажмите «Сохранить».</div>`;
}
function openProjects(focusName) {
  winOpen("wProjects", true); $("projName").value = PROJ.name || ""; renderProjects();
  if (focusName) { $("projName").focus(); $("projName").select(); toast("Назовите проект, чтобы сохранить его."); }
}
$("bProj").onclick = () => openProjects(false);
$("projSave").onclick = () => saveProject($("projName").value);
$("projName").addEventListener("keydown", e => { if (e.key === "Enter") saveProject($("projName").value); });
$("projNew").onclick = newProject;
$("projList").addEventListener("click", e => { const b = e.target.closest("[data-open]"); if (b) openProject(b.dataset.open); });
$("projDownload").onclick = () => {
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(collectProject())], { type: "application/json" }));
  a.download = (PROJ.name || "проект") + ".grado2"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
};
$("projFile").onchange = async e => {
  const f = e.target.files[0]; e.target.value = ""; if (!f || !confirmLoss(`Открыть «${f.name}»?`)) return;
  try { const p = JSON.parse(await f.text()); p.name ||= f.name.replace(/\.grado2$/i, ""); applyProject(p); PROJ.dirty = true; syncProjTitle(); toast(`Открыт файл «${f.name}». Сохраните проект, чтобы он появился в папке проектов.`); winOpen("wProjects", false); }
  catch (err) { toast("Файл не открылся: " + err.message); }
};
addEventListener("keydown", e => { if ((e.metaKey || e.ctrlKey) && (e.code === "KeyS" || e.key === "s")) { e.preventDefault(); saveProject(); } });

/* ---------- старт: восстановить последнюю работу ---------- */
window.markDirty = markDirty;
window.projectStart = async () => {
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
