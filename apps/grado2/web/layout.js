/* ГРАДО 2 · редактор макета листа (как «Макет» в QGIS): готовый лист во весь экран, любая надпись листа — заголовок,
   шапка, подписи карты, легенда — выбирается щелчком и правится: текст, шрифт, кегль, цвет, обводка, поворот, место
   (тянуть мышью или стрелками). «Текст» добавляет свою надпись. Правки хранятся в листе (edits — по ключу «текст#n»,
   items — свои надписи) и попадают в PDF и PPTX: лист собирает тот же рендер ядра (print_io.apply_edits).
   Правка — ручная поправка поверх автоматических подписей листа: правила подписей сами по себе не меняются. */
const LAY_FONTS = [["ui", "PT Sans"], ["ui-bold", "PT Sans полужирный"], ["serif", "PT Serif"], ["serif-bold", "PT Serif полужирный"],
  ["sans", "Montserrat"], ["sans-bold", "Montserrat полужирный"]];
const PT = 25.4 / 72;                                   // 1 пт в мм: кегль в окне — в пунктах, как в QGIS
let LAY = null;                                         // { i, sel, adding, z, svg }

function layoutEl() {
  let el = $("layEd"); if (el) return el;
  el = document.createElement("div"); el.id = "layEd"; el.hidden = true; el.setAttribute("role", "dialog"); el.setAttribute("aria-label", "Макет листа");
  el.innerHTML = `<header class="layh"><i data-lucide="pencil-ruler"></i><b id="layTitle">Макет листа</b><span class="sp"></span>
      <button class="tb" id="layZo" title="Мельче (Ctrl + колесо)" aria-label="Мельче"><i data-lucide="zoom-out"></i></button><button class="tb" id="layZ1" title="Лист целиком" aria-label="Лист целиком"><i data-lucide="maximize"></i></button><button class="tb" id="layZi" title="Крупнее (Ctrl + колесо)" aria-label="Крупнее"><i data-lucide="zoom-in"></i></button>
      <button class="btn" id="layAdd" aria-pressed="false" title="Своя надпись: затем щёлкните место на листе"><i data-lucide="type"></i>Текст</button>
      <button class="btn" id="layShow" title="Вернуть на лист все скрытые надписи"><i data-lucide="eye"></i>Скрытые</button>
      <button class="btn" id="layReset" title="Снять все правки надписей этого листа"><i data-lucide="rotate-ccw"></i>Сбросить всё</button>
      <button class="btn primary" id="layPdf" title="Этот лист одним PDF — с правками"><i data-lucide="file-down"></i>PDF листа</button>
      <button class="tb" id="layClose" title="Закрыть (Esc)" aria-label="Закрыть"><i data-lucide="x"></i></button></header>
    <div class="layb"><div class="lays" id="layStage"></div><aside class="layp" id="layPanel"></aside></div>`;
  document.body.appendChild(el);
  $("layClose").onclick = closeLayout;
  $("layAdd").onclick = () => setAdding(!LAY.adding);
  $("layShow").onclick = () => { const e = sheetOf().edits || {}; let n = 0; Object.values(e).forEach(x => { if (x.hide) { delete x.hide; n++; } }); window.markDirty?.(); renderLayout(); toast(n ? `Возвращено надписей: ${n}.` : "Скрытых надписей нет."); };
  $("layReset").onclick = e => { const sh = sheetOf(); if (!confirmInline(e.currentTarget, "Снять все правки надписей и удалить свои надписи этого листа?")) return;
    sh.edits = {}; sh.items = []; LAY.sel = null; window.markDirty?.(); renderLayout(); };
  $("layPdf").onclick = () => albumFile("pdf", sheetOf());
  const st = $("layStage");
  st.addEventListener("pointerdown", layDown);
  // увеличение листа: кнопки и Ctrl + колесо (как в макете QGIS)
  $("layZo").onclick = () => layZoom(LAY.z / 1.4); $("layZi").onclick = () => layZoom(LAY.z * 1.4); $("layZ1").onclick = () => layZoom(1);
  st.addEventListener("wheel", e => { if (!e.ctrlKey && !e.metaKey) return; e.preventDefault(); layZoom(LAY.z * (e.deltaY < 0 ? 1.15 : 1 / 1.15)); }, { passive: false });
  return el;
}
/* Клавиши, пока открыт макет (app.js спрашивает раньше всех обработчиков): стрелки, Delete, Esc — макету; ни одна клавиша
   не уходит в команды карты под ним (Ctrl+Z не отменит невидимую правку карты). Ввод в полях панели, Tab, Enter и пробел
   на кнопках работают как обычно; Ctrl/Cmd+S сохраняет проект. */
window.LAYKEYS = e => {
  if (!LAY || $("layEd")?.hidden) return false;
  if (e.key === "Escape") { if (LAY.adding) setAdding(false); else closeLayout(); return true; }
  if ((e.ctrlKey || e.metaKey) && (e.code === "KeyS" || e.key === "s")) return false;
  const tag = e.target?.tagName || "";
  if (/INPUT|SELECT|TEXTAREA/.test(tag) || e.key === "Tab" || e.ctrlKey || e.metaKey || (tag === "BUTTON" && (e.key === "Enter" || e.key === " "))) {
    e.stopImmediatePropagation(); return false; }
  const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
  if (d && LAY.sel) { const k = e.shiftKey ? 5 : .5; moveSel(d[0] * k, d[1] * k); }
  if ((e.key === "Delete" || e.key === "Backspace") && LAY.sel) hideSel();
  return true;
};
function setAdding(on) { LAY.adding = on; $("layAdd").setAttribute("aria-pressed", on); layHint(on ? "Щёлкните на листе место новой надписи." : ""); }
const sheetOf = () => ALBUM.sheets[LAY.i];
const isItem = key => key.startsWith("item:");
const itemOf = key => (sheetOf().items || []).find(x => "item:" + x.id === key);
// правка выбранной надписи: у своей надписи — сама надпись (x, y), у надписи листа — запись edits[key] (dx, dy)
const editOf = key => isItem(key) ? itemOf(key) : ((sheetOf().edits ||= {})[key] ||= {});
function layHint(t) { const h = $("layHint"); if (h) h.textContent = t || "Щелчок — выбрать надпись; тянуть — сдвинуть (стрелки — на 0,5 мм, Shift — на 5 мм); Delete — скрыть."; }

function openLayout(i) {
  const sh = ALBUM.sheets[i]; if (!sh || sh.kind === "tep") return toast("У листа ТЭП нет макета для правки надписей.");
  LAY = { i, sel: null, adding: false, z: 1 }; const el = layoutEl(); el.hidden = false;
  $("layTitle").textContent = `Макет: ${sh.title}`; icons(); layPanel(); return renderLayout();
}
function closeLayout() { const el = $("layEd"); if (el) el.hidden = true; LAY = null; renderSheets(); }

let layReq = 0;
async function renderLayout() {
  if (!LAY) return;
  const n = ++layReq, st = $("layStage");
  st.classList.add("busy");
  try {
    const r = await fetch("/api/print/svg", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...albumSpec([sheetOf()]), index: 0 }) });
    if (!r.ok) throw new Error((await r.json()).error);
    const t = await r.text(); if (n !== layReq || !LAY) return;
    st.innerHTML = t; const svg = st.querySelector("svg"); svg.removeAttribute("width"); svg.removeAttribute("height");
    svg.querySelectorAll("text[data-key]").forEach(x => x.classList.add("layt"));
    // панель не пересобирается, пока в ней печатают: иначе курсор уходит из поля на каждой перерисовке листа
    LAY.svg = svg; layZoom(LAY.z); markSel(); if (LAY.panelKey !== LAY.sel || !$("layPanel").contains(document.activeElement)) layPanel();
  } catch (e) { toast("Лист не собран: " + e.message); } finally { if (n === layReq) st.classList.remove("busy"); }
}
function layZoom(z) {
  LAY.z = Math.max(1, Math.min(8, z)); if (!LAY.svg) return;
  LAY.svg.style.width = LAY.z * 100 + "%"; LAY.svg.style.maxWidth = LAY.z === 1 ? "" : "none";
}
const selEl = () => LAY.sel && LAY.svg && [...LAY.svg.querySelectorAll("text[data-key]")].find(x => x.dataset.key === LAY.sel);
// рамка выбранной надписи — в той же системе координат (мм листа), с поворотом надписи
function markSel() {
  LAY.svg?.querySelector("#laySel")?.remove(); const t = selEl(); if (!t) return;
  const b = t.getBBox(), r = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  Object.entries({ id: "laySel", x: b.x - .6, y: b.y - .4, width: b.width + 1.2, height: b.height + .8, fill: "none", stroke: "#1a5fb4", "stroke-width": .35, "stroke-dasharray": "1 .6", "pointer-events": "none" }).forEach(([k, v]) => r.setAttribute(k, v));
  if (t.getAttribute("transform")) r.setAttribute("transform", t.getAttribute("transform"));
  t.after(r);
}
const svgPt = e => { const p = LAY.svg.createSVGPoint(); p.x = e.clientX; p.y = e.clientY; return p.matrixTransform(LAY.svg.getScreenCTM().inverse()); };

function layDown(e) {
  if (!LAY?.svg || e.button !== 0) return;
  const p = svgPt(e);
  if (LAY.adding) {                                      // своя надпись в месте щелчка
    const sh = sheetOf(), id = Date.now().toString(36);
    (sh.items ||= []).push({ id, x: +p.x.toFixed(2), y: +p.y.toFixed(2), text: "Надпись", size: 3.5, font: "ui", color: "#1a1a1a" });
    setAdding(false); LAY.sel = "item:" + id;
    window.markDirty?.(); renderLayout().then(() => $("layText")?.select()); return;
  }
  const t = e.target.closest?.("text[data-key]");
  if (!t) { LAY.sel = null; markSel(); layPanel(); return; }
  LAY.sel = t.dataset.key; markSel(); layPanel();
  // перетаскивание: надпись едет за мышью сразу, правка записывается по отпусканию
  const base = t.getAttribute("transform") || "", start = p; let d = [0, 0];
  t.setPointerCapture?.(e.pointerId);
  const mv = ev => { const q = svgPt(ev); d = [q.x - start.x, q.y - start.y]; t.setAttribute("transform", `translate(${d[0]} ${d[1]}) ${base}`); LAY.svg.querySelector("#laySel")?.setAttribute("transform", `translate(${d[0]} ${d[1]}) ${base}`); };
  const up = () => { t.removeEventListener("pointermove", mv); t.removeEventListener("pointerup", up);
    if (Math.hypot(d[0], d[1]) > .2) moveSel(d[0], d[1]); };
  t.addEventListener("pointermove", mv); t.addEventListener("pointerup", up);
}
function moveSel(dx, dy) {
  const e = editOf(LAY.sel); if (!e) return;
  if (isItem(LAY.sel)) { e.x = +(e.x + dx).toFixed(2); e.y = +(e.y + dy).toFixed(2); } else { e.dx = +((e.dx || 0) + dx).toFixed(2); e.dy = +((e.dy || 0) + dy).toFixed(2); }
  window.markDirty?.(); renderLayout();
}
function hideSel() {
  if (!LAY.sel) return;
  if (isItem(LAY.sel)) { const sh = sheetOf(); sh.items = sh.items.filter(x => "item:" + x.id !== LAY.sel); } else editOf(LAY.sel).hide = true;
  LAY.sel = null; window.markDirty?.(); renderLayout();
}
// текущие свойства надписи — с листа (как нарисовано), правка поверх
function curOf(t) {
  const rgb = s => { const m = String(s || "").match(/\d+/g); return m ? "#" + m.slice(0, 3).map(v => (+v).toString(16).padStart(2, "0")).join("") : "#000000"; };
  const rot = (t.getAttribute("transform") || "").match(/rotate\(([-\d.]+)/);
  return { text: t.textContent, size: +t.getAttribute("font-size"), color: rgb(t.getAttribute("fill")), angle: rot ? +(+rot[1]).toFixed(1) : 0,
    halo: t.getAttribute("stroke") ? [rgb(t.getAttribute("stroke")), +t.getAttribute("stroke-width") / 2] : null };
}
function layPanel() {
  const p = $("layPanel"), t = LAY.sel && selEl(); LAY.panelKey = LAY.sel;
  if (!t) { p.innerHTML = `<div class="note">Щёлкните надпись на листе — заголовок, подпись улицы, строку легенды — чтобы изменить её текст, шрифт, кегль, цвет, обводку и поворот.<br><br>«Текст» — своя надпись.</div><div class="note" id="layHint"></div>`; layHint(""); return; }
  const e = editOf(LAY.sel), c = curOf(t), item = isItem(LAY.sel), font = e.font || (item ? "ui" : "");
  const halo = e.halo !== undefined ? e.halo : c.halo;
  p.innerHTML = `<div class="sect">${item ? "Своя надпись" : "Надпись листа"}</div><div class="pad lf">
    <label>Текст<textarea id="layText" rows="2">${esc(item ? e.text : e.text || c.text)}</textarea></label>
    <label>Шрифт<select id="layFont">${item ? "" : `<option value="" ${font ? "" : "selected"}>как на листе</option>`}${LAY_FONTS.map(([v, n]) => `<option value="${v}" ${v === font ? "selected" : ""}>${n}</option>`).join("")}</select></label>
    <div class="row2"><label>Кегль, пт<input id="laySize" type="number" min="2" max="170" step=".5" value="${+(c.size / PT).toFixed(1)}"></label>
      <label>Цвет<input id="layColor" type="color" value="${e.color || c.color}"></label></div>
    <div class="row2"><label>Поворот, °<input id="layAngle" type="number" min="-180" max="180" step="1" value="${e.angle ?? c.angle}"></label>
      <label title="${item ? "Положение надписи на листе от левого верхнего угла" : "Сдвиг надписи от её места на листе"}">${item ? "Положение, мм" : "Сдвиг, мм"}<input readonly value="${item ? `${fmt(e.x, 1)}; ${fmt(e.y, 1)}` : `${fmt(e.dx || 0, 1)}; ${fmt(e.dy || 0, 1)}`}"></label></div>
    <label class="chk"><input id="layHalo" type="checkbox" ${halo ? "checked" : ""}>Обводка (буфер)</label>
    <div class="row2"><label>Цвет обводки<input id="layHaloC" type="color" value="${halo?.[0] || "#ffffff"}"></label>
      <label>Толщина, мм<input id="layHaloW" type="number" min=".1" max="3" step=".1" value="${halo?.[1] ?? .6}"></label></div>
    <div class="row"><button class="btn" id="layHide">${item ? "Удалить" : "Скрыть"}</button>${item ? "" : `<button class="btn" id="layUndo" title="Вернуть надпись как была">Сбросить правку</button>`}</div>
  </div><div class="note" id="layHint"></div>`;
  layHint("");
  const set = (k, v) => { const x = editOf(LAY.sel); if (v === "" || v == null) delete x[k]; else x[k] = v; window.markDirty?.(); clearTimeout(LAY.t); LAY.t = setTimeout(renderLayout, 350); };
  $("layText").oninput = ev => { if (item && !ev.target.value.trim()) return; set("text", ev.target.value); };   // пустая своя надпись пропала бы с листа — её удаляют кнопкой
  $("layFont").onchange = ev => set("font", ev.target.value);
  $("laySize").onchange = ev => set("size", +(+ev.target.value * PT).toFixed(3));
  $("layColor").oninput = ev => set("color", ev.target.value);
  $("layAngle").onchange = ev => set("angle", ev.target.value === "" ? "" : +ev.target.value);
  const halo2 = () => { const x = editOf(LAY.sel); x.halo = $("layHalo").checked ? [$("layHaloC").value, +$("layHaloW").value || .6] : null; window.markDirty?.(); clearTimeout(LAY.t); LAY.t = setTimeout(renderLayout, 350); };
  $("layHalo").onchange = halo2; $("layHaloC").oninput = halo2; $("layHaloW").onchange = halo2;
  $("layHide").onclick = hideSel;
  if (!item) $("layUndo").onclick = () => { delete sheetOf().edits[LAY.sel]; window.markDirty?.(); renderLayout(); };
}
window.openLayout = openLayout;
