import { post, postBlob, saveBlob } from "./api.js";
import { cancelDraft, filletSelection, fitView, mount, transformSelection, viewBbox } from "./canvas.js";
import {
  LAYERS, addFeatures, emit, layerById, layerRows, loadProject, plainFeatures, redoEdit,
  removeFeatures, resetProject, restoreSnapshot, selectedFeature, setFeatures, snapshot, state,
  subscribe, undoEdit,
} from "./store.js";

const EMPTY = {
  map: "Начертите границу участка или откройте файл .grado.",
  draw: "Команда: пл, отр, плг, дга, кр или слово точка.",
  album: "Лист без масштаба не выпускается. ТЭП без границы показывает «н/д».",
};

const TOOLS = [
  ["select", "Выбор"], ["point", "Точка"], ["polyline", "Линия"], ["polygon", "Полигон"],
  ["rect", "Прямоуг."], ["arc", "Дуга"], ["circle", "Круг"], ["trim", "Обрез."],
  ["extend", "Продл."], ["fillet", "Сопрячь"], ["dim", "Размер"], ["measure", "Измер."],
];
const TOOL_LABEL = Object.fromEntries(TOOLS);
const SOURCES = [
  ["osm.buildings", "OSM здания"],
  ["osm.roads", "OSM дороги"],
  ["osm.water", "OSM вода"],
  ["nspd.parcels", "НСПД участки"],
  ["nspd.buildings", "НСПД здания"],
  ["nspd.zouit", "НСПД ЗОУИТ"],
];

function denom() {
  return Math.round(96 / (state.ppm * 0.0254));
}

function cell(value) {
  return value == null || value === "" ? "н/д" : String(value);
}

function renderLayers() {
  const root = document.querySelector("#layers");
  const shelves = [];
  for (const layer of layerRows()) {
    if (!shelves.length || shelves[shelves.length - 1].name !== layer.shelf) {
      shelves.push({ name: layer.shelf, layers: [] });
    }
    shelves[shelves.length - 1].layers.push(layer);
  }
  root.innerHTML = shelves.map((shelf) => `
    <p class="shelf">${shelf.name}</p>
    ${shelf.layers.map((layer) => {
      const count = state.features.filter((feature) => feature.layer_id === layer.id).length;
      const on = state.visible[layer.id] !== false;
      const active = state.activeLayer === layer.id ? " active" : "";
      const locked = state.locked[layer.id] ? "checked" : "";
      return `<div class="layer${active}" data-layer="${layer.id}">
        <input type="checkbox" data-eye="${layer.id}" ${on ? "checked" : ""} aria-label="Видимость ${layer.title}">
        <input type="checkbox" data-lock="${layer.id}" ${locked} aria-label="Захват ${layer.title}">
        <span>${layer.title}</span><em>${count}</em></div>`;
    }).join("")}`).join("");
}

function renderInspect() {
  const root = document.querySelector("#inspect");
  const feature = selectedFeature();
  const tep = state.tep;
  const rows = tep ? tep.results.filter((row) =>
    ["calc_area", "spp", "population", "doo_norm", "school_norm", "parking_perm"].includes(row.id)) : [];
  const featureBlock = feature ? `
    <h2>Объект</h2>
    <p>${layerById(feature.layer_id)?.title || feature.layer_id}</p>
    <p class="meta">${feature.layer_id}</p>
    <p class="meta">${feature.grado_key ? "Источник " + feature.grado_key : "Начерчено здесь"}</p>` : `
    <h2>Свойства</h2>
    <p class="meta">Ничего не выбрано. Щёлкните объект в режиме выбора.</p>`;
  const area = tep && tep.inputs ? cell(tep.inputs.terr_area) : "н/д";
  root.innerHTML = `
    ${featureBlock}
    <h2>ТЭП</h2>
    <p>Граница: ${area} га</p>
    <p class="meta">Плотность берётся из профиля moscow_krt, пока её не задали отдельно.</p>
    ${rows.map((row) => `<p>${row.title}: ${cell(row.value)} ${row.value == null ? "" : row.unit}</p>`).join("")}
    <p class="meta">${tep && tep.fact ? "Факт СПП: " + cell(tep.fact.spp) + (tep.fact.floors_unknown ? `, без этажности: ${tep.fact.floors_unknown}` : "") : ""}</p>
    ${state.view === "map" ? renderSources() : ""}
    ${state.view !== "album" ? "<h2>Зависимости</h2><p class=\"meta\">Нарезка корпусов и покрытие школ в этой версии не считаются.</p>" : ""}`;
}

function sourcePhase(id) {
  const card = state.sources[id];
  if (!card || card.phase === "absent") return "нет";
  if (card.phase === "loading") return "грузится";
  return "снимок " + (card.date || "");
}

function renderSources() {
  return `<h2>Анализ</h2>
    ${SOURCES.map(([id, title]) => `<p><button type="button" data-src="${id}">${title}</button> <span class="meta">${sourcePhase(id)}</span></p>`).join("")}
    <p><button type="button" data-act="gisogd">ГИС ОГД, ZIP</button></p>
    <p><input id="uin" placeholder="УИН ФГИС ТП" value="${state.uin || ""}"></p>
    <p><button type="button" data-act="fgistp">Загрузить документ</button></p>
    <p><button type="button" data-act="inbox">Забрать захват НСПД</button></p>
    <p class="meta">data.mos.ru нет. Подложка: ${state.basemap === "off" ? "выкл" : state.basemap}.</p>
    <p><button type="button" data-base="osm">OSM</button>
       <button type="button" data-base="s2">Снимок</button>
       <button type="button" data-base="off">Без подложки</button></p>`;
}

function renderRail() {
  const rail = document.querySelector("#rail");
  if (!rail) return;
  rail.innerHTML = TOOLS.map(([id, title]) =>
    `<button type="button" data-tool="${id}" aria-pressed="${state.tool === id}" title="${title}">${title}</button>`).join("")
    + `<button type="button" data-act="join" title="Склеить">Склеить</button>`
    + `<button type="button" data-act="snap" aria-pressed="${state.snapOn}" title="Привязки">Привязка</button>`
    + `<button type="button" data-act="ortho" aria-pressed="${state.ortho}" title="Орто">Орто</button>`
    + `<button type="button" data-act="grid" aria-pressed="${state.gridOn}" title="Сетка">Сетка</button>`;
}

function renderAlbum() {
  const album = document.querySelector("#album");
  const show = state.view === "album";
  album.hidden = !show;
  if (!show) return;
  const scale = Number(state.sheetScale);
  const ready = Number.isFinite(scale) && scale >= 100 && scale <= 20000;
  if (!album.dataset.built) {
    album.dataset.built = "1";
    album.innerHTML = `
      <h2>Листы</h2>
      <ol>
        <li>Расположение</li><li>Опорный план</li><li>Схема</li><li>Сводные ТЭП</li>
      </ol>
      <label>Масштаб 1: <input id="scale" inputmode="numeric" value="${state.sheetScale}"></label>
      <p class="meta"></p>
      <button type="button" id="pdf">PDF листа</button>
      <button type="button" id="agk">Альбом</button>
      <button type="button" id="dxf">DXF</button>`;
    const scaleInput = album.querySelector("#scale");
    const rememberScale = (event) => {
      state.sheetScale = event.target.value.trim();
      emit();
    };
    scaleInput.addEventListener("input", rememberScale);
    scaleInput.addEventListener("change", rememberScale);
    album.querySelector("#pdf").addEventListener("click", () => release("/api/print", { scale: Number(state.sheetScale), paper: "A3" }));
    album.querySelector("#agk").addEventListener("click", () => release("/api/album", {
      albumConfig: { sheets: ["location", "base", "apo", "tep"] },
    }));
    album.querySelector("#dxf").addEventListener("click", () => release("/api/dxf", {}));
  }
  album.querySelector(".meta").textContent = ready
    ? "PDF листа пойдёт в этом масштабе."
    : "Лист без масштаба не выпускается.";
  album.querySelector("#pdf").disabled = !ready;
  album.querySelector("#agk").disabled = !ready;
}

function renderStatus() {
  const layer = layerById(state.activeLayer);
  document.querySelector("#status").textContent = [
    "UTM 37N",
    "1:" + denom(),
    "привязка " + snapToleranceText() + " м",
    state.ortho ? "орто вкл" : "орто выкл",
    state.dirty ? "правок " + state.dirty : "записано",
    autosaveText(),
    state.name,
    layer ? layer.title : "",
    TOOL_LABEL[state.tool] || "",
    state.snapHint,
    state.message,
  ].filter(Boolean).join("  ·  ");
  document.querySelector("#empty").textContent = state.features.length || state.tool === "select"
    ? "" : EMPTY[state.view];
  document.querySelector("#view-name").textContent = { map: "Карта", draw: "Чертёж", album: "Альбом" }[state.view];
}

function snapToleranceText() {
  return (Math.max(state.snap, 10 / state.ppm)).toFixed(2);
}

let tepToken = 0;
async function refreshTep() {
  const token = ++tepToken;
  try {
    const tep = await post("/api/tep", { features: plainFeatures(), name: state.name });
    if (token !== tepToken) return;
    state.tep = tep;
  } catch {
    if (token !== tepToken) return;
    state.tep = null;
    state.message = "ТЭП не посчитался";
  }
  renderInspect();
  renderStatus();
}

async function release(path, extra) {
  state.message = "";
  try {
    const target = path === "/api/album" ? "album" : path === "/api/dxf" ? "dxf" : "print";
    const report = await post("/api/preflight", { features: plainFeatures(), target });
    if (report.errors && report.errors.length) {
      state.message = report.errors[0].title;
      emit();
      return;
    }
    const file = await postBlob(path, { features: plainFeatures(), name: state.name, ...extra });
    saveBlob(file.blob, file.filename);
    state.message = "Файл собран";
  } catch (error) {
    state.message = error.message || "Выпуск остановлен";
  }
  emit();
}

async function saveGrado() {
  try {
    const file = await postBlob("/api/grado", {
      features: plainFeatures(), name: state.name, projectStyles: state.projectStyles,
    });
    const safe = state.name.replace(/[^\wа-яА-ЯёЁ .-]+/g, "").trim() || "project";
    saveBlob(file.blob, safe.endsWith(".grado") ? safe : safe + ".grado");
    state.dirty = 0;
    state.message = "Файл .grado собран";
  } catch (error) {
    state.message = error.message || "Файл не собран";
  }
  emit();
}

function setTool(tool, layerId) {
  cancelDraft();
  state.tool = tool;
  if (layerId) state.activeLayer = layerId;
  state.view = tool === "select" ? state.view : "draw";
  state.message = "";
  emit();
}

function runCommand(raw) {
  const text = raw.trim().toLowerCase();
  const [word, arg] = text.split(/\s+/);
  const tools = {
    "пл": "polyline", "pl": "polyline", "полилиния": "polyline",
    "отр": "segment", "l": "segment", "отрезок": "segment",
    "плг": "polygon", "pg": "polygon", "полигон": "polygon",
    "дга": "arc", "a": "arc", "дуга": "arc",
    "кр": "circle", "c": "circle", "окружность": "circle",
    "точка": "point",
  };
  if (tools[word]) {
    const tool = tools[word];
    const layer = tool === "polygon" ? state.activeLayer
      : tool === "point" ? "project.social.objects" : "project.apo.red_lines";
    setTool(tool, layer);
    return;
  }
  if (word === "прям" || word === "rect") { setTool("rect"); return; }
  if (word === "обр" || word === "tr") { setTool("trim"); state.trimReady = false; state.message = "Клик по границам, затем Enter"; emit(); return; }
  if (word === "удл" || word === "ex") { setTool("extend"); state.trimReady = false; state.message = "Клик по границам, затем Enter"; emit(); return; }
  if (word === "соед" || word === "j") { joinPicked(); return; }
  if (word === "размер") { setTool("dim"); return; }
  if (word === "измер") { setTool("measure"); return; }
  if (word === "знак" && arg) {
    const feature = selectedFeature();
    if (!feature) { state.message = "Сначала выберите объект"; emit(); return; }
    feature.style_id = arg;
    const known = state.library && state.library[arg];
    if (known) {
      const snap = {};
      for (const key of ["stroke", "fill", "width", "dash", "hatch", "dots"]) {
        const value = known[key];
        if (value == null) continue;
        if (Array.isArray(value)) snap[key] = value.slice();
        else if (typeof value === "object") snap[key] = { ...value };
        else snap[key] = value;
      }
      state.projectStyles = { ...state.projectStyles, [arg]: snap };
    }
    state.dirty += 1;
    state.message = "Знак " + arg;
    emit();
    return;
  }
  if (word === "сетка") { state.gridOn = !state.gridOn; emit(); return; }
  if (word === "буфер" && arg) { bufferPicked(Number(arg.replace(",", "."))); return; }
  if (word === "орто") {
    state.ortho = !state.ortho;
    emit();
    return;
  }
  if (word === "шаг" && arg) {
    const step = Number(arg.replace(",", "."));
    if (step > 0 && step <= 100) state.snap = step;
    emit();
    return;
  }
  if (word === "поворот" && arg) {
    transformSelection("rotate", { degrees: Number(arg.replace(",", ".")) });
    return;
  }
  if (word === "масштаб" && arg) {
    transformSelection("scale", { factor: Number(arg.replace(",", ".")) });
    return;
  }
  if ((word === "сопряжение") && arg) {
    filletSelection(Number(arg.replace(",", ".")));
    return;
  }
  if (word === "зрк" || word === "mi" || word === "зеркало") {
    state.message = "Зеркало: введите ось двумя числами, например «зрк 0 0 1 0»";
    const nums = text.split(/\s+/).slice(1).map(Number);
    if (nums.length === 4 && nums.every((n) => Number.isFinite(n))) {
      transformSelection("mirror", { a: [nums[0], nums[1]], b: [nums[2], nums[3]] });
      return;
    }
    emit();
    return;
  }
  state.message = "Нет такой команды";
  emit();
}

const PALETTE = [
  ["плг", "Полигон"], ["пл", "Полилиния"], ["отр", "Отрезок"], ["прям", "Прямоугольник"],
  ["дга", "Дуга по трём точкам"], ["кр", "Окружность"], ["точка", "Точка"],
  ["обр", "Обрезать"], ["удл", "Продлить"], ["соед", "Склеить"],
  ["буфер 10", "Буфер 10 м"], ["сопряжение 10", "Сопряжение"],
  ["поворот 90", "Поворот"], ["масштаб 2", "Масштаб"], ["зрк 0 0 1 0", "Зеркало"],
  ["размер", "Размер"], ["измер", "Измерение"], ["орто", "Орто"], ["сетка", "Сетка"],
];

function openPalette() {
  const dialog = document.querySelector("#palette");
  const query = document.querySelector("#palette-q");
  const list = document.querySelector("#palette-list");
  const paint = () => {
    const needle = query.value.trim().toLowerCase();
    list.innerHTML = PALETTE.filter(([cmd, title]) => (cmd + title).toLowerCase().includes(needle))
      .map(([cmd, title]) => `<li data-cmd="${cmd}">${title}</li>`).join("");
  };
  query.oninput = paint;
  list.onclick = (event) => {
    const item = event.target.closest("[data-cmd]");
    if (!item) return;
    runCommand(item.dataset.cmd);
    dialog.close();
  };
  paint();
  dialog.showModal();
  query.focus();
}

async function joinPicked() {
  const lines = state.features.filter((feature) => state.picked.includes(feature.id) && feature.line);
  if (lines.length < 2) {
    state.message = "Выберите минимум две линии";
    emit();
    return;
  }
  try {
    const out = await post("/api/geom", {
      op: "join", tolerance: Math.max(state.snap, 0.5), lines: lines.map((feature) => feature.line),
    });
    const drop = new Set(lines.slice(1).map((feature) => feature.id));
    setFeatures(state.features.filter((feature) => !drop.has(feature.id)).map((feature) => (
      feature.id === lines[0].id ? { ...feature, line: out.line } : feature)));
    state.message = "Линии склеены";
  } catch {
    state.message = "Концы не совпали";
  }
  emit();
}

function replaceKeep(id, patch) {
  const feature = state.features.find((item) => item.id === id);
  if (!feature) return;
  Object.assign(feature, patch);
  if (patch.arc === undefined) delete feature.arc;
  if (patch.preview === undefined) delete feature.preview;
}

async function bufferPicked(dist) {
  const feats = plainFeatures().filter((feature) => state.picked.includes(feature.id));
  if (!feats.length || !(dist > 0)) {
    state.message = "Выберите объект и дистанцию";
    emit();
    return;
  }
  try {
    const out = await post("/api/geom", { op: "buffer", dist, features: feats });
    addFeatures(out.features || []);
    state.message = "Буфер построен";
  } catch {
    state.message = "Буфер не построен";
    emit();
  }
}

async function fetchSource(id) {
  const bbox = viewBbox();
  if (!bbox) return;
  state.sources = { ...state.sources, [id]: { phase: "loading" } };
  emit();
  try {
    const out = await post("/api/fetch-extent", { bbox, sources: [id] });
    const features = (out.groups || []).flatMap((group) => group.features || []);
    addFeatures(features);
    const stamp = out.snapshots && out.snapshots[0] && (out.snapshots[0].fetched_at || out.snapshots[0].id);
    state.sources[id] = { phase: "ready", date: String(stamp || "").slice(0, 10) };
    state.message = features.length ? `Загружено ${features.length}` : "В области пусто";
  } catch (error) {
    state.sources[id] = { phase: "absent" };
    state.message = error.message || "Источник не ответил";
  }
  emit();
}

async function importFgistp() {
  const uin = (document.querySelector("#uin") && document.querySelector("#uin").value || "").trim();
  state.uin = uin;
  state.sources = { ...state.sources, fgistp: { phase: "loading" } };
  emit();
  if (uin && !/^\d{5,40}$/.test(uin)) {
    try {
      const response = await fetch("/api/fgistp-catalog");
      if (!response.ok) throw new Error("catalog");
      const payload = await response.json();
      const catalog = Array.isArray(payload) ? payload : (payload.docs || []);
      const needle = uin.toLowerCase();
      const hit = catalog.find((row) => String(row.name || "").toLowerCase().includes(needle));
      if (!hit) {
        state.sources.fgistp = { phase: "absent" };
        state.message = "В каталоге нет такого названия";
      } else {
        document.querySelector("#uin").value = hit.uin;
        state.uin = hit.uin;
        state.sources.fgistp = { phase: "ready", date: "каталог" };
        state.message = hit.name;
      }
    } catch {
      state.sources.fgistp = { phase: "absent" };
      state.message = "Каталог не открылся";
    }
    emit();
    return;
  }
  try {
    const out = await post("/api/import-fgistp-doc", { uin });
    addFeatures(out.features || []);
    state.sources.fgistp = { phase: "ready", date: new Date().toISOString().slice(0, 10) };
    state.message = out.notes && out.notes[0] ? out.notes[0] : "Документ загружен";
  } catch {
    state.sources.fgistp = { phase: "absent" };
    state.message = "Документ не загрузился";
  }
  emit();
}

async function importInbox() {
  state.sources = { ...state.sources, nspd: { phase: "loading" } };
  emit();
  try {
    const inbox = await fetch("/api/inbox").then((response) => response.json());
    let count = 0;
    for (const item of inbox.items || []) {
      const out = await post("/api/import-nspd", { payload: item });
      addFeatures(out.features || []);
      count += (out.features || []).length;
    }
    state.sources.nspd = { phase: count ? "ready" : "absent", date: new Date().toISOString().slice(0, 10) };
    state.message = count ? `Захват: ${count}` : "Захват пуст";
  } catch {
    state.sources.nspd = { phase: "absent" };
    state.message = "Захват не прочитан";
  }
  emit();
}

async function importGisogd(file) {
  state.sources = { ...state.sources, gisogd: { phase: "loading" } };
  emit();
  try {
    const response = await fetch("/api/import-gisogd", {
      method: "POST",
      headers: { "X-Grado-Filename": encodeURIComponent(file.name) },
      body: await file.arrayBuffer(),
    });
    if (!response.ok) throw new Error("fail");
    const out = await response.json();
    const features = out.features || (out.groups || []).flatMap((group) => group.features || []);
    addFeatures(features);
    state.sources.gisogd = { phase: "ready", date: new Date().toISOString().slice(0, 10) };
    state.message = `ГИС ОГД: ${features.length}`;
  } catch {
    state.sources.gisogd = { phase: "absent" };
    state.message = "ZIP не прочитан";
  }
  emit();
}

function bind() {
  document.querySelector("#layers").addEventListener("click", (event) => {
    const eye = event.target.closest("[data-eye]");
    if (eye) {
      state.visible[eye.dataset.eye] = eye.checked;
      emit();
      return;
    }
    const lock = event.target.closest("[data-lock]");
    if (lock) {
      state.locked[lock.dataset.lock] = lock.checked;
      emit();
      return;
    }
    const layer = event.target.closest("[data-layer]");
    if (layer) {
      state.activeLayer = layer.dataset.layer;
      emit();
    }
  });
  document.querySelector("#ribbon").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const act = button.dataset.act;
    if (act === "map" || act === "draw" || act === "album") {
      state.view = act;
      emit();
    } else if (act === "boundary") setTool("polygon", "project.territory.boundary");
    else if (act === "zone") setTool("polygon", "project.tp.func_zone");
    else if (act === "select") setTool("select");
    else if (act === "new") resetProject("Новый проект");
    else if (act === "save") saveGrado();
    else if (act === "open") document.querySelector("#file").click();
    else if (act === "undo") undoEdit();
    else if (act === "redo") redoEdit();
    else if (act === "fit") fitView();
    else if (act === "palette") openPalette();
    else if (act === "join") joinPicked();
    else if (act === "snap") { state.snapOn = !state.snapOn; emit(); }
    else if (act === "ortho") { state.ortho = !state.ortho; emit(); }
    else if (act === "grid") { state.gridOn = !state.gridOn; emit(); }
    else if (act === "gisogd") document.querySelector("#gisogd").click();
    else if (act === "fgistp") importFgistp();
    else if (act === "inbox") importInbox();
  });
  document.querySelector("#rail").addEventListener("click", (event) => {
    const tool = event.target.closest("[data-tool]");
    if (tool) setTool(tool.dataset.tool, tool.dataset.tool === "point" ? "project.social.objects" : state.activeLayer);
    const act = event.target.closest("[data-act]");
    if (act) document.querySelector("#ribbon").dispatchEvent(new CustomEvent("rail"));
    if (act && act.dataset.act === "join") joinPicked();
    if (act && act.dataset.act === "snap") { state.snapOn = !state.snapOn; emit(); }
    if (act && act.dataset.act === "ortho") { state.ortho = !state.ortho; emit(); }
    if (act && act.dataset.act === "grid") { state.gridOn = !state.gridOn; emit(); }
  });
  document.querySelector("#inspect").addEventListener("click", (event) => {
    const src = event.target.closest("[data-src]");
    if (src) fetchSource(src.dataset.src);
    const base = event.target.closest("[data-base]");
    if (base) { state.basemap = base.dataset.base; state.view = "map"; emit(); }
    const act = event.target.closest("[data-act]");
    if (!act) return;
    if (act.dataset.act === "gisogd") document.querySelector("#gisogd").click();
    if (act.dataset.act === "fgistp") importFgistp();
    if (act.dataset.act === "inbox") importInbox();
  });
  document.querySelector("#cmd").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.querySelector("#command");
    runCommand(input.value);
    input.value = "";
  });
  document.querySelector("#file").addEventListener("change", async (event) => {
    const file = event.target.files && event.target.files[0];
    event.target.value = "";
    if (!file) return;
    const response = await fetch("/api/open-grado", { method: "POST", body: await file.arrayBuffer() });
    if (!response.ok) {
      state.message = "Файл не открылся";
      emit();
      return;
    }
    loadProject(await response.json());
  });
  document.querySelector("#gisogd").addEventListener("change", async (event) => {
    const file = event.target.files && event.target.files[0];
    event.target.value = "";
    if (file) importGisogd(file);
  });
  window.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openPalette();
      return;
    }
    if (event.target.id === "command" || event.target.id === "scale" || event.target.id === "uin" || event.target.id === "palette-q") return;
    if (event.key === "1") state.view = "map";
    else if (event.key === "2") state.view = "draw";
    else if (event.key === "3") state.view = "album";
    else return;
    emit();
  });
}

// Автосохранение: свой файл на сервере (.autosave-v2.json, 10 резервных копий).
// До чтения сохранённого не пишем ничего — пустой старт затёр бы проект.
const AUTOSAVE = "/api/autosave-v2";
let autosave = { ready: false, key: "", timer: 0, at: "", failed: false };

function autosaveText() {
  if (!autosave.ready) return "";
  if (autosave.failed) return "автосохранение не удалось";
  return autosave.at ? "автосохранено " + autosave.at : "";
}

async function writeAutosave() {
  autosave.timer = 0;
  const body = JSON.stringify(snapshot());
  if (body === autosave.key) return;
  try {
    const response = await fetch(AUTOSAVE, {
      method: "POST", headers: { "Content-Type": "application/json" }, body,
    });
    if (!response.ok) throw new Error(String(response.status));
    autosave.key = body;
    autosave.failed = false;
    autosave.at = new Date().toTimeString().slice(0, 5);
  } catch {
    autosave.failed = true;
  }
  renderStatus();
}

function scheduleAutosave() {
  if (!autosave.ready) return;
  clearTimeout(autosave.timer);
  autosave.timer = setTimeout(writeAutosave, 1500);
}

async function restoreAutosave() {
  try {
    const response = await fetch(AUTOSAVE);
    if (response.ok) {
      const payload = await response.json();
      const saved = payload && (payload.state || payload);
      if (restoreSnapshot(saved)) {
        autosave.key = JSON.stringify(snapshot());
        state.message = saved.features.length
          ? `Восстановлен проект «${state.name}»: объектов ${saved.features.length}` : "";
      }
      autosave.ready = true;
    } else {
      // Файл повреждён: не перезаписываем, резервные копии остаются на диске.
      state.message = "Автосохранение не прочитано, запись остановлена";
    }
  } catch {
    state.message = "Сервер не ответил, автосохранение выключено";
  }
  emit();
}

window.addEventListener("beforeunload", () => {
  if (!autosave.ready) return;
  const body = JSON.stringify(snapshot());
  if (body !== autosave.key) navigator.sendBeacon(AUTOSAVE, new Blob([body], { type: "application/json" }));
});

let tepKey = "";
subscribe(() => {
  scheduleAutosave();
  renderLayers();
  renderRail();
  renderInspect();
  renderAlbum();
  renderStatus();
  for (const id of ["map", "draw", "album"]) {
    const tab = document.querySelector("#tab-" + id);
    if (tab) tab.setAttribute("aria-selected", state.view === id ? "true" : "false");
  }
  const key = JSON.stringify(plainFeatures());
  if (key !== tepKey) {
    tepKey = key;
    refreshTep();
  }
});

fetch("/api/styles").then((response) => response.json()).then((library) => {
  state.library = library || {};
  emit();
}).catch(() => {});

bind();
mount(document.querySelector("#sheet"));
emit();
restoreAutosave();
