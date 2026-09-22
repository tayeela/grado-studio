/* ГРАДО 2 · слои проекта как в QGIS: дерево с порядком прорисовки (перетаскивание), видимость,
   оформление (единое / категории / диапазоны / правила / знаки ЛГР), подписи, таблица атрибутов.
   Строка инструментов как в AutoCAD: рисование в текущий слой, вершины, перенос, удаление, замеры;
   правка выгрузок с возвратом к исходной.
   Данные слоя живут в DATA[key].fc (WGS84) — их же читает граф анализа. */

const CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"], OTHER = "#9aa1a8";
const RAMPS = { blue: ["#dcebfa", "#a8cbf1", "#6fa6e6", "#2a78d6", "#1a4f94", "#0f3363"], brick: ["#fbe4d8", "#f5b698", "#ec875b", "#cf5a2c", "#933717", "#5e200c"], green: ["#e1f2e3", "#b2dcb7", "#7ec188", "#3f9a4f", "#1f6e31", "#10461e"], grey: ["#f2f2f2", "#d4d4d4", "#aaaaaa", "#7a7a7a", "#4d4d4d", "#262626"] };
const PICK = [...CAT, "#1d1d1f", "#5f6368", "#9aa1a8", "#d4d4d4", "#ffffff", "#b3261e", "#1f7a4d", "#7a4b2a", ...RAMPS.blue.slice(0, 4), ...RAMPS.brick.slice(0, 4)];
const ramp = (n, k) => k === 1 ? [RAMPS[n][3]] : Array.from({ length: k }, (_, i) => RAMPS[n][Math.round(i * (RAMPS[n].length - 1) / Math.max(1, k - 1))]);
const ST = o => Object.assign({ mode: "single", fill: "#9aa1a8", stroke: "#5f6368", width: 1, opacity: .7, hatch: false, label: "", labelSize: 11,
  cat: { field: "", colors: {}, off: [] }, grad: { field: "", n: 5, ramp: "blue", method: "quantile" }, rules: { list: [], elseFill: "#dddddd", elseHide: false } }, o);
// порядок по умолчанию: сверху вниз (первый — самый верхний)
const PREFERRED = ["gisogd.red_lines", "nspd.buildings", "osm.buildings", "nspd.zouit", "gisogd.szz", "gisogd.vodookhr", "osm.roads", "nspd.parcels", "gisogd.func_zones", "gisogd.func_zones_tinao", "osm.water", "osm.landuse"];
function defaultStyle(key, fc) {
  const zones = lib => { const colors = {}; fc.features.forEach(f => { const v = String(f.properties.naimfunkzony ?? f.properties.naimfunkzo ?? f.properties["Вид зоны"] ?? ""); const z = lib[v.toLowerCase()]; if (z) colors[v] = z.fill; }); return colors; };
  return ST(({
    "nspd.parcels": { fill: "#ffffff", stroke: "#7d8288", width: .8, opacity: 0 },
    "nspd.buildings": { fill: "#cbc6be", stroke: "#4d4d4d", width: .8, opacity: 1 },
    "nspd.zouit": { fill: "#7a4ab0", stroke: "#7a4ab0", hatch: true },
    "osm.roads": { mode: "cat", width: 1.6, cat: { field: "Тип дороги", colors: {}, off: [] } },
    "osm.buildings": { fill: "#dcd7ce", stroke: "#8a857c", width: .7, opacity: 1 },
    "osm.water": { fill: "#b9d6ec", stroke: "#6fa6e6", width: .8, opacity: 1 },
    "osm.landuse": { mode: "cat", opacity: .35, stroke: "#b8b2a3", width: .5, cat: { field: "Землепользование", colors: {}, off: [] } },
    "gisogd.func_zones": { mode: "cat", opacity: .8, stroke: "#3c3c3c", width: .5, cat: { field: "naimfunkzony", colors: zones(GPZ), off: [] } },
    "gisogd.func_zones_tinao": { mode: "cat", opacity: .8, stroke: "#3c3c3c", width: .5, cat: { field: "Вид зоны", colors: zones(NMZ), off: [] } },
    "gisogd.szz": { fill: "#4a3aa7", stroke: "#4a3aa7", hatch: true, width: 1.2 },
    "gisogd.vodookhr": { fill: "#2a78d6", stroke: "#2a78d6", hatch: true, width: 1.2 },
    "gisogd.red_lines": { mode: "lgr", fill: "#d7191c", width: 1.3 },
  })[key] || (fc.features.some(f => f.properties._lt) ? { mode: "lgr" } : { fill: CAT[LYR.length % CAT.length], stroke: "#3d3d3d" }));
}

/* ---------- модель ---------- */
const LYR = [];                       // сверху вниз
let CUR = null;                       // текущий слой (выделен в дереве)
let SEL = null;                       // {key, f} выбранный объект
const lyr = key => LYR.find(l => l.key === key);
const geomOf = fc => { const g = fc.features.find(f => f.geometry)?.geometry?.type || ""; return /Point/.test(g) ? "point" : /Line/.test(g) ? "line" : "poly"; };
// поля с русскими названиями (подписанные сервером) — первыми, служебные поля порталов — после
const fieldsOfKey = key => (DATA[key]?.fields || []).filter(k => !k.startsWith("_")).sort((a, b) => (/[а-яё]/i.test(b) - /[а-яё]/i.test(a)));
function ensureLayer(key, title, geom) {
  let l = lyr(key);
  if (!l) {
    const fc = DATA[key]?.fc || { features: [] };
    l = { key, title: title || DATA[key]?.title || key, visible: true, layerOpacity: 1, open: false, geom: geom || geomOf(fc), style: defaultStyle(key, fc), cache: new Map() };
    if (l.style.mode === "cat") assignCats(l, true);
    const rank = k => { const i = PREFERRED.indexOf(k); return i < 0 ? -1 : i; };
    // свои слои и импорт — наверх; выгрузки — по привычному порядку (линии над застройкой, зоны внизу)
    const r = rank(key), at = r < 0 ? 0 : LYR.findIndex(x => rank(x.key) > r);
    LYR.splice(at < 0 ? LYR.length : at, 0, l);
    layerSrc[key] ||= new ol.source.Vector();
    ALLMAPS.forEach(m => attachLayer(m, l));
    if (!CUR) CUR = key;
  }
  applyOrder(); renderTree(); renderRight();
  return l;
}
function attachLayer(map, l) {
  if (map.getLayers().getArray().some(x => x.get("key") === l.key)) return;
  const ol_ = new ol.layer.Vector({ source: layerSrc[l.key], style: (f, res) => styleFor(l, f, res), declutter: true });
  ol_.set("key", l.key); map.addLayer(ol_);
}
window.attachDataLayers = map => LYR.forEach(l => attachLayer(map, l));
function applyOrder() {
  window.markDirty?.();
  ALLMAPS.forEach(m => m.getLayers().forEach(ml => { const l = lyr(ml.get("key")); if (!l) return; ml.setZIndex(10 + LYR.length - LYR.indexOf(l)); ml.setVisible(l.visible); ml.setOpacity(l.layerOpacity); }));
}
function setLayerData(key, fc) {
  const d = DATA[key]; d.original ||= JSON.parse(JSON.stringify(fc));
  layerSrc[key].clear(); layerSrc[key].addFeatures(GJ.readFeatures(fc));
  syncFromSource(key, false);
}
/* правка на карте → DATA (WGS84), которым питается граф */
function syncFromSource(key, edited = true) {
  const d = DATA[key], fs = layerSrc[key].getFeatures();
  d.fc = GJ.writeFeaturesObject(fs); d.count = fs.length;
  d.fields = [...new Set(d.fc.features.slice(0, 500).flatMap(f => Object.keys(f.properties || {})))];
  d.edited = fs.filter(f => f.get("_edited")).length;
  if (edited) dataRev++;
  lyr(key)?.cache.clear();
  renderTree(); renderTable();
}

/* ---------- оформление ---------- */
const isNum = v => typeof v === "number" || (v !== "" && v != null && !isNaN(+v));
function catValues(key, field) { const m = new Map(); layerSrc[key]?.getFeatures().forEach(f => { const v = String(f.get(field) ?? ""); m.set(v, (m.get(v) || 0) + 1); }); return [...m.entries()].sort((a, b) => b[1] - a[1]); }
function numFields(key) { const fs = layerSrc[key]?.getFeatures() || []; return fieldsOfKey(key).filter(k => fs.length && fs.slice(0, 300).every(f => f.get(k) == null || isNum(f.get(k)))); }
function assignCats(l, keep) {
  const st = l.style; if (!st.cat.field) st.cat.field = fieldsOfKey(l.key).find(k => !numFields(l.key).includes(k)) || fieldsOfKey(l.key)[0] || "";
  const c = keep ? { ...st.cat.colors } : {}; let k = Object.keys(c).length;
  catValues(l.key, st.cat.field).forEach(([v]) => { if (!c[v]) c[v] = k < CAT.length ? CAT[k++] : OTHER; });
  st.cat.colors = c; if (!keep) st.cat.off = [];
}
function breaks(l) {
  const g = l.style.grad, v = (layerSrc[l.key]?.getFeatures() || []).map(f => +f.get(g.field)).filter(x => !isNaN(x)).sort((a, b) => a - b); if (!v.length) return [0, 0];
  const b = [v[0]]; for (let i = 1; i < g.n; i++) b.push(+(g.method === "equal" ? v[0] + (v[v.length - 1] - v[0]) * i / g.n : v[Math.floor(i * v.length / g.n)]).toFixed(2)); b.push(v[v.length - 1]);
  const u = [...new Set(b)]; return u.length > 1 ? u : [u[0], u[0]];   // совпавшие границы — один класс, а не «16–16» четыре раза
}
function testRule(r, f) {
  const v = f.get(r.field), t = r.val; if (v == null) return false;
  if (r.op === "содержит") return String(v).toLowerCase().includes(String(t).toLowerCase());
  const n = isNum(v) && isNum(t), a = n ? +v : String(v), b = n ? +t : String(t);
  return { "=": a == b, "≠": a != b, ">": a > b, "<": a < b, "≥": a >= b, "≤": a <= b }[r.op];
}
function symbolOf(l, f) {
  const st = l.style; let fill = st.fill, hatch = st.hatch, hide = false;
  if (st.mode === "cat") { const v = String(f.get(st.cat.field) ?? ""); fill = st.cat.colors[v] || OTHER; hide = st.cat.off.includes(v); }
  else if (st.mode === "grad") { const b = l._br || (l._br = breaks(l)), v = +f.get(st.grad.field), cols = ramp(st.grad.ramp, (l._br || (l._br = breaks(l))).length - 1); const i = b.findIndex((x, k) => k > 0 && v <= x); fill = isNaN(v) ? OTHER : cols[Math.max(0, i - 1)] ?? cols[cols.length - 1]; }
  else if (st.mode === "rules") { const r = st.rules.list.find(r => r.field && testRule(r, f)); if (r) { fill = r.fill; hatch = r.hatch; } else { fill = st.rules.elseFill; hatch = false; hide = st.rules.elseHide; } }
  return { fill, hatch, hide };
}
const rgba = (hex, a) => { const c = [...ol.color.asArray(hex)]; c[3] = a; return c; };
const SELSTYLE = { poly: S([47, 111, 196, .15], "#2f6fc4", 3), line: S(null, "#2f6fc4", 4), point: new ol.style.Style({ image: new ol.style.Circle({ radius: 8, stroke: new ol.style.Stroke({ color: "#2f6fc4", width: 3 }) }) }) };
function styleFor(l, f, res) {
  const sel = SEL?.f === f, st = l.style;
  const out = [];
  if (st.mode === "lgr") { out.push(redLineStyle(f)); }
  else {
    const s = symbolOf(l, f); if (s.hide) return null;
    const key = `${s.fill}|${s.hatch}`; let base = l.cache.get(key);
    if (!base) {
      if (l.geom === "line") base = new ol.style.Style({ stroke: new ol.style.Stroke({ color: s.fill, width: st.width, lineCap: "round", lineJoin: "round" }) });
      else if (l.geom === "point") base = new ol.style.Style({ image: new ol.style.Circle({ radius: 2 + st.width * 2, fill: new ol.style.Fill({ color: s.fill }), stroke: new ol.style.Stroke({ color: st.stroke, width: 1 }) }) });
      else base = new ol.style.Style({ fill: new ol.style.Fill({ color: s.hatch ? hatch(s.fill) : rgba(s.fill, st.opacity) }), stroke: new ol.style.Stroke({ color: s.hatch ? s.fill : st.stroke, width: st.width }) });
      l.cache.set(key, base);
    }
    out.push(base);
  }
  if (st.label && res < 4) { const t = f.get(st.label); if (t != null && t !== "") out.push(new ol.style.Style({ text: new ol.style.Text({ text: String(t), font: `${st.labelSize}px system-ui, sans-serif`, fill: new ol.style.Fill({ color: "#1d1d1f" }), stroke: new ol.style.Stroke({ color: "#fff", width: 3 }), placement: l.geom === "line" ? "line" : "point", overflow: false }) })); }
  if (sel) out.push(SELSTYLE[l.geom]);
  return out;
}
function restyle(l) { l.cache.clear(); l._br = null; layerSrc[l.key]?.changed(); renderTree(); window.markDirty?.(); }

/* ---------- дерево слоёв ---------- */
function symHTML(l, color) {
  const st = l.style;
  if (st.mode === "lgr" && !color) return `<span class="sym line" style="border-top-color:#d7191c"></span>`;
  const c = color || (st.mode === "single" ? st.fill : st.mode === "cat" ? (Object.values(st.cat.colors)[0] || OTHER) : st.mode === "grad" ? ramp(st.grad.ramp, 3)[1] : (st.rules.list[0]?.fill || st.rules.elseFill));
  if (l.geom === "line") return `<span class="sym line" style="border-top-color:${c}"></span>`;
  if (l.geom === "point") return `<span class="sym pt" style="background:${c}"></span>`;
  return `<span class="sym" style="${st.hatch && !color ? `background:repeating-linear-gradient(135deg,${c} 0 1px,transparent 1px 4px);border-color:${c}` : st.mode === "single" && st.opacity === 0 && !color ? `background:transparent;border-color:${st.stroke}` : `background:${c}`}"></span>`;
}
function legendItems(l) {
  const st = l.style;
  if (st.mode === "cat") return catValues(l.key, st.cat.field).map(([v, n]) => ({ v, n, c: st.cat.colors[v] || OTHER, off: st.cat.off.includes(v), check: true }));
  if (st.mode === "grad") { const b = l._br || (l._br = breaks(l)); return ramp(st.grad.ramp, (l._br || (l._br = breaks(l))).length - 1).map((c, i) => ({ v: `${fmt(b[i], 1)} – ${fmt(b[i + 1], 1)}`, c })); }
  if (st.mode === "rules") return st.rules.list.map(r => ({ v: `${r.field} ${r.op} ${r.val}`, c: r.fill })).concat(st.rules.elseHide ? [] : [{ v: "остальные", c: st.rules.elseFill }]);
  return [];
}
function renderTree() {
  const el = $("layerTree"); if (!el) return;
  const res = RESULT.sketch.length || RESULT.site ? `<div class="tgrp" title="Как предпросмотр в Grasshopper: виден, пока открыты окна «Граф», «Эскиз», «Варианты», «Объём» или «Сравнение». В проект эскиз попадает кнопкой «Принять в проект».">Предпросмотр графа${PREVIEW_WINS.some(id => !$(id).hidden) ? "" : " · скрыт"}</div>` + RES.map(r => `<label class="tn"><span class="tw"></span><input type="checkbox" data-res="${r.id}" ${r.on !== false ? "checked" : ""} aria-label="Показывать в предпросмотре"><span class="sym" style="background:${r.color}"></span><span class="nm">${r.title}</span><span class="meta num">${r.layer.getSource().getFeatures().length || ""}</span></label>`).join("") : "";
  if (!LYR.length) { el.innerHTML = `<div class="note">Слоёв пока нет. Нажмите «+» над списком и рисуйте, выберите инструмент рисования на панели сверху (слой появится сам) или загрузите источники в окне «Данные».</div>` + res; icons(); return; }
  el.innerHTML = LYR.map((l, i) => {
    const d = DATA[l.key], items = l.open ? legendItems(l).slice(0, 60) : [];
    return `<div class="tn ${l.visible ? "" : "off"}" draggable="true" data-lk="${esc(l.key)}" aria-selected="${CUR === l.key}">
      <button class="tw" data-tw="${esc(l.key)}" aria-label="Легенда" ${["cat", "grad", "rules"].includes(l.style.mode) ? "" : 'style="visibility:hidden"'}><i data-lucide="${l.open ? "chevron-down" : "chevron-right"}"></i></button>
      <input type="checkbox" data-vis="${esc(l.key)}" ${l.visible ? "checked" : ""} aria-label="Видимость">${symHTML(l)}
      <span class="nm" title="${esc(d?.source || "")}">${esc(l.title)}</span>
      ${d?.edited && d.original ? `<span class="badge" title="Объектов выгрузки изменено вручную">изм. ${d.edited}</span>` : ""}
      <span class="meta num">${d?.count ?? 0}</span>
      <button class="tw more" data-more="${esc(l.key)}" aria-label="Меню слоя"><i data-lucide="more-horizontal"></i></button></div>`
      + items.map(it => `<div class="tn leg ${it.off ? "off" : ""}">${it.check ? `<input type="checkbox" data-catoff="${esc(l.key)}|${esc(it.v)}" ${it.off ? "" : "checked"} aria-label="Показывать">` : ""}${symHTML(l, it.c)}<span class="nm">${esc(it.v || "—")}</span>${it.n != null ? `<span class="meta num">${it.n}</span>` : ""}</div>`).join("");
  }).join("") + res;
  syncCurSelect();
  icons();
}
const tree = () => $("layerTree");
document.addEventListener("click", e => {
  const t = e.target;
  if (!tree()?.contains(t)) return;
  const tw = t.closest("[data-tw]"); if (tw) { const l = lyr(tw.dataset.tw); l.open = !l.open; renderTree(); return; }
  const more = t.closest("[data-more]"); if (more) { layerMenu(more, more.dataset.more); return; }
  if (t.matches("input")) return;
  const row = t.closest("[data-lk]"); if (row) setCurrent(row.dataset.lk);
});
document.addEventListener("dblclick", e => { const row = e.target.closest?.("#layerTree [data-lk]"); if (row && !e.target.closest("[data-tw],[data-more],input")) renameLayer(row.dataset.lk); });
document.addEventListener("change", e => {
  const t = e.target; if (!tree()?.contains(t)) return;
  if (t.dataset.vis) { lyr(t.dataset.vis).visible = t.checked; applyOrder(); renderTree(); }
  if (t.dataset.res) { RES.find(r => r.id === t.dataset.res).on = t.checked; syncPreview(); }
  if (t.dataset.catoff) { const [k, v] = t.dataset.catoff.split("|"); const l = lyr(k), st = l.style; st.cat.off = t.checked ? st.cat.off.filter(x => x !== v) : [...st.cat.off, v]; restyle(l); renderRight(); }
});
/* перетаскивание = порядок прорисовки: верхний в списке рисуется поверх */
let dragKey = null;
document.addEventListener("dragstart", e => { const row = e.target.closest?.("#layerTree [data-lk]"); if (row) { dragKey = row.dataset.lk; e.dataTransfer.effectAllowed = "move"; row.classList.add("dragging"); } });
document.addEventListener("dragover", e => { const row = e.target.closest?.("#layerTree [data-lk]"); if (!dragKey || !row) return; e.preventDefault(); const r = row.getBoundingClientRect(); document.querySelectorAll("#layerTree .drop-a,#layerTree .drop-b").forEach(x => x.classList.remove("drop-a", "drop-b")); row.classList.add(e.clientY < r.top + r.height / 2 ? "drop-a" : "drop-b"); });
document.addEventListener("drop", e => {
  const row = e.target.closest?.("#layerTree [data-lk]"); if (!dragKey || !row) return; e.preventDefault();
  const before = row.classList.contains("drop-a"), from = LYR.findIndex(l => l.key === dragKey), [l] = LYR.splice(from, 1);
  let to = LYR.findIndex(x => x.key === row.dataset.lk); if (!before) to++; LYR.splice(to, 0, l); dragKey = null; applyOrder(); renderTree();
});
document.addEventListener("dragend", () => { dragKey = null; document.querySelectorAll("#layerTree .dragging,#layerTree .drop-a,#layerTree .drop-b").forEach(x => x.classList.remove("dragging", "drop-a", "drop-b")); });

let menuEl = null;
const closeMenu = () => { menuEl?.remove(); menuEl = null; };
function layerMenu(anchor, key) {
  closeMenu(); const l = lyr(key), d = DATA[key];
  const items = [["Приблизить к слою", () => { const ex = layerSrc[key].getExtent(); if (isFinite(ex[0])) sharedView.fit(ex, { padding: [40, 40, 40, 40], maxZoom: 18 }); }],
    ["Таблица атрибутов", () => { setCurrent(key); openTable(true); }],
    ["Рисовать в этот слой", () => { setCurrent(key); setTool(GEOMTOOL[l.geom]); }],
    ["Переименовать", () => renameLayer(key)],
    ["Выше", () => moveLayer(key, -1)], ["Ниже", () => moveLayer(key, 1)],
    d?.original ? ["Вернуть исходную выгрузку", () => { if (!confirmInline(anchor, "Отменить все правки слоя и вернуть выгрузку?")) return; setLayerData(key, d.original); dataRev++; }] : null,
    ["Удалить слой из проекта", () => removeLayer(key)]].filter(Boolean);
  menuEl = document.createElement("div"); menuEl.className = "menu";
  menuEl.innerHTML = items.map((it, i) => `<button data-i="${i}">${esc(it[0])}</button>`).join("");
  document.body.appendChild(menuEl); const r = anchor.getBoundingClientRect(); menuEl.style.left = Math.min(r.left, innerWidth - 240) + "px"; menuEl.style.top = Math.min(r.bottom + 2, innerHeight - menuEl.offsetHeight - 8) + "px";
  menuEl.onclick = ev => { const b = ev.target.closest("[data-i]"); if (b) { closeMenu(); items[+b.dataset.i][1](); } };
}
document.addEventListener("pointerdown", e => { if (menuEl && !menuEl.contains(e.target) && !e.target.closest("[data-more]")) closeMenu(); });
// window.confirm в браузере-вьюере не работает: подтверждение — повторным выбором пункта в течение 4 с
let pendingConfirm = null;
function confirmInline(anchor, text) { const now = Date.now(); if (pendingConfirm && now - pendingConfirm < 4000) { pendingConfirm = null; return true; } pendingConfirm = now; toast(text + " Выберите пункт ещё раз, чтобы подтвердить."); return false; }
function moveLayer(key, d) { const i = LYR.findIndex(l => l.key === key), j = i + d; if (j < 0 || j >= LYR.length) return; [LYR[i], LYR[j]] = [LYR[j], LYR[i]]; applyOrder(); renderTree(); }
function renameLayer(key) {
  const row = tree().querySelector(`[data-lk="${CSS.escape(key)}"] .nm`); if (!row) return; const l = lyr(key), old = l.title;
  row.innerHTML = `<input type="text" value="${esc(old)}" style="width:100%">`; const inp = row.querySelector("input"); inp.focus(); inp.select();
  const done = ok => { const v = inp.value.trim(); if (ok && v && v !== old) { l.title = v; DATA[key].title = v; graph._nodes.forEach(n => n.widgets?.forEach(w => { if (w.name === "слой" && w.value === old) w.value = v; })); dataRev++; } renderTree(); };
  inp.onkeydown = e => { if (e.key === "Enter") done(true); if (e.key === "Escape") done(false); }; inp.onblur = () => done(true);
}
function removeLayer(key) {
  const i = LYR.findIndex(l => l.key === key); if (i < 0) return;
  if (!confirmInline(tree(), `Удалить слой «${LYR[i].title}» из проекта?`)) return;
  LYR.splice(i, 1); ALLMAPS.forEach(m => m.getLayers().getArray().filter(x => x.get("key") === key).forEach(x => m.removeLayer(x)));
  delete DATA[key]; layerSrc[key]?.clear(); if (CUR === key) CUR = LYR[0]?.key || null; if (SEL?.key === key) SEL = null;
  dataRev++; renderTree(); renderRight(); renderTable(); renderSources?.(); setTool(UIS.tool);
}
$("bNewLayer").onclick = () => {
  const box = $("newLayerBox"); box.hidden = !box.hidden; if (!box.hidden) $("nlName").focus();
};
function createLayer(name, geom) {
  const key = "user:" + Date.now().toString(36);
  DATA[key] = { title: name, source: "создан в проекте", fetched_at: new Date().toISOString().slice(0, 10), fc: { type: "FeatureCollection", features: [] }, count: 0, fields: ["Наименование", "Примечание"] };
  ensureLayer(key, name, geom); setCurrent(key); return lyr(key);
}
$("nlOk").onclick = () => {
  const l = createLayer($("nlName").value.trim() || "Новый слой", $("nlGeom").value);
  $("newLayerBox").hidden = true; $("nlName").value = ""; document.activeElement.blur(); setTool(GEOMTOOL[l.geom]);
};
$("nlName").addEventListener("keydown", e => { if (e.key === "Enter") $("nlOk").click(); });

/* ---------- правая панель: оформление и объект ---------- */
const UIS = { rt: "style", tool: "select", sort: null, filter: "" };
const cbtn = (key, c) => `<button class="cbtn" data-color="${key}" aria-label="Выбрать цвет"><i style="background:${c}"></i></button>`;
const opts = (list, cur) => list.map(v => `<option ${String(v) === String(cur) ? "selected" : ""}>${esc(v)}</option>`).join("");
function renderRight() {
  document.querySelectorAll("[data-rtab]").forEach(b => b.setAttribute("aria-selected", b.dataset.rtab === UIS.rt));
  const el = $("rightPane"); if (!el) return;
  UIS.rt === "obj" ? renderObject(el) : renderStyle(el); icons();
}
function renderStyle(el) {
  const l = lyr(CUR); if (!l) { el.innerHTML = `<div class="empty">Выберите слой в дереве</div>`; return; }
  const st = l.style, fields = fieldsOfKey(l.key), nf = numFields(l.key), cf = fields.filter(k => !nf.includes(k));
  const modes = [["single", "Единый"], ["cat", "Категории"], ["grad", "Градуир."], ["rules", "Правила"]].concat(fields.includes("_lt") || st.mode === "lgr" || DATA[l.key]?.fc.features.some(f => f.properties._lt) ? [["lgr", "ЛГР"]] : []);
  let h = `<div class="pad"><div class="ph">${symHTML(l)}<b>${esc(l.title)}</b></div><div class="modes">${modes.map(([m, t]) => `<button data-mode="${m}" aria-pressed="${st.mode === m}">${t}</button>`).join("")}</div>`;
  const colorWord = l.geom === "line" ? "Цвет" : l.geom === "point" ? "Цвет" : "Заливка";
  if (st.mode === "lgr") h += `<div class="note" style="padding:0 0 8px">Знаки красных линий и ЛГР по стандарту REDLN97: тип линии выбирается по LineCode объекта. <a href="linetypes.html" target="_blank">Каталог типов</a>.</div>`;
  else if (st.mode === "single") h += `<div class="row"><label>${colorWord}</label>${cbtn("fill", st.fill)}${l.geom === "poly" ? `<label class="inl"><input type="checkbox" data-k="hatch" ${st.hatch ? "checked" : ""}>штриховка</label>` : ""}</div>`;
  else if (st.mode === "cat") {
    h += `<div class="row"><label>Поле</label><select data-k="cat.field">${opts(cf.length ? cf : fields, st.cat.field)}</select></div><div class="row"><label></label><button class="btn" data-recolor title="Как «Классифицировать» в QGIS: заново собрать значения поля и раздать цвета">Классифицировать</button></div>`;
    h += `<table class="cl">${catValues(l.key, st.cat.field).slice(0, 80).map(([v, n]) => `<tr class="${st.cat.off.includes(v) ? "off" : ""}"><td><input type="checkbox" data-catoff2="${esc(v)}" ${st.cat.off.includes(v) ? "" : "checked"} aria-label="Показывать"></td><td>${cbtn("cat:" + v, st.cat.colors[v] || OTHER)}</td><td>${esc(v || "—")}</td><td class="n num">${n}</td></tr>`).join("")}</table>`;
    if (l.geom === "poly") h += `<div class="row" style="margin-top:7px"><label></label><label class="inl"><input type="checkbox" data-k="hatch" ${st.hatch ? "checked" : ""}>штриховка вместо заливки</label></div>`;
  } else if (st.mode === "grad") {
    if (!nf.length) h += `<div class="empty">Нет числовых полей</div>`;
    else { if (!nf.includes(st.grad.field)) st.grad.field = nf[0]; const b = l._br || (l._br = breaks(l)), cols = ramp(st.grad.ramp, (l._br || (l._br = breaks(l))).length - 1);
      h += `<div class="row"><label>Поле</label><select data-k="grad.field">${opts(nf, st.grad.field)}</select></div><div class="row"><label>Классы</label><select data-k="grad.n">${opts([3, 4, 5, 6], st.grad.n)}</select><select data-k="grad.method"><option value="quantile" ${st.grad.method === "quantile" ? "selected" : ""}>Квантили</option><option value="equal" ${st.grad.method === "equal" ? "selected" : ""}>Равные интервалы</option></select></div>
      <div class="row"><label>Шкала</label><div class="ramps">${Object.keys(RAMPS).map(r => `<button class="ramp" data-ramp="${r}" aria-pressed="${st.grad.ramp === r}" aria-label="Шкала ${r}">${RAMPS[r].map(c => `<i style="background:${c}"></i>`).join("")}</button>`).join("")}</div></div>
      <table class="cl">${cols.map((c, i) => `<tr><td><span class="sym" style="background:${c}"></span></td><td class="num">${fmt(b[i], 1)} – ${fmt(b[i + 1], 1)}</td></tr>`).join("")}</table>`; }
  } else if (st.mode === "rules") {
    h += st.rules.list.map((r, i) => `<div class="rule"><div class="w"><select data-rule="${i}" data-rk="field" aria-label="Поле">${opts(fields, r.field)}</select><select data-rule="${i}" data-rk="op" aria-label="Условие">${opts(["=", "≠", ">", "<", "≥", "≤", "содержит"], r.op)}</select><input type="text" data-rule="${i}" data-rk="val" value="${esc(r.val)}" aria-label="Значение"></div>
      <div class="t">${cbtn("rule:" + i, r.fill)}${l.geom === "poly" ? `<label class="inl"><input type="checkbox" data-rule="${i}" data-rk="hatch" ${r.hatch ? "checked" : ""}> штриховка</label>` : ""}<span class="sp"></span><span class="num">${(layerSrc[l.key]?.getFeatures() || []).filter(f => testRule(r, f)).length} об.</span><button class="tb" data-delrule="${i}" title="Удалить правило"><i data-lucide="x"></i></button></div></div>`).join("");
    h += `<div class="row"><button class="btn" data-addrule><i data-lucide="plus"></i>Правило</button></div><div class="rule"><div class="t" style="margin:0">Остальные ${cbtn("else", st.rules.elseFill)}<label class="inl"><input type="checkbox" data-k="rules.elseHide" ${st.rules.elseHide ? "checked" : ""}> скрыть</label></div></div>`;
  }
  h += `<div class="sect" style="margin:8px -8px 8px">Контур, прозрачность, подписи</div>`;
  if (l.geom === "poly") h += `<div class="row"><label>Контур</label>${cbtn("stroke", st.stroke)}<input type="number" data-k="width" min="0" max="8" step=".1" value="${st.width}" style="width:64px" aria-label="Толщина контура"> пикс.</div>
    <div class="row"><label>Заливка, %</label><input type="range" data-k="opacity" min="0" max="1" step=".05" value="${st.opacity}" aria-label="Непрозрачность заливки"><span class="num">${Math.round(st.opacity * 100)}</span></div>`;
  else h += `<div class="row"><label>${l.geom === "point" ? "Размер" : "Толщина"}</label><input type="number" data-k="width" min=".3" max="10" step=".1" value="${st.width}" style="width:64px" aria-label="Толщина"> пикс.</div>`;
  h += `<div class="row"><label>Слой, %</label><input type="range" data-lop min="0" max="1" step=".05" value="${l.layerOpacity}" aria-label="Непрозрачность слоя"><span class="num">${Math.round(l.layerOpacity * 100)}</span></div>
    <div class="row"><label>Подпись</label><select data-k="label"><option value="">нет</option>${fields.map(k => `<option ${st.label === k ? "selected" : ""}>${esc(k)}</option>`).join("")}</select><input type="number" data-k="labelSize" min="7" max="24" value="${st.labelSize}" style="width:54px" aria-label="Кегль"></div></div>`;
  el.innerHTML = h;
}
function renderObject(el) {
  if (!SEL) { el.innerHTML = `<div class="empty">Щёлкните объект на карте или строку таблицы</div>`; return; }
  const l = lyr(SEL.key), f = SEL.f, g = f.getGeometry(), wgs = GJ.writeFeatureObject(f);
  const size = /Polygon/.test(g.getType()) ? `${fmt(turf.area(wgs), 1)} м²` : /Line/.test(g.getType()) ? `${fmt(turf.length(wgs, { units: "kilometers" }) * 1000, 2)} м` : "";
  const keys = Object.keys(f.getProperties()).filter(k => k !== "geometry" && !k.startsWith("_"));
  el.innerHTML = `<div class="pad"><div class="ph"><b>${esc(l.title)}</b></div><div class="note" style="padding:0 0 6px">${size}${f.get("_edited") ? " · изменён вручную" : ""}${f.get("_lt") ? " · " + esc(f.get("_lt").join(", ")) : ""}</div></div>
    <div class="pg">${keys.map(k => `<div class="ro" title="${esc(k)}">${esc(k)}</div><div><input type="text" data-attr="${esc(k)}" value="${esc(f.get(k))}"></div>`).join("")}</div>
    <div class="pad"><div class="row"><input type="text" id="newField" placeholder="Новое поле"><button class="btn" id="bAddField">Добавить</button></div></div>`;
}
document.addEventListener("click", e => {
  const tab = e.target.closest?.("[data-rtab]"); if (tab) { UIS.rt = tab.dataset.rtab; renderRight(); return; }
  const pane = $("rightPane"); if (!pane?.contains(e.target)) return;
  const b = e.target.closest("button"); if (!b) return; const l = lyr(CUR); if (!l) return; const st = l.style;
  if (b.id === "bAddField") { const n = $("newField").value.trim(); if (n && SEL) { pushUndo(SEL.key); SEL.f.set(n, ""); SEL.f.set("_edited", true); syncFromSource(SEL.key); renderRight(); } return; }
  if (b.dataset.mode) { st.mode = b.dataset.mode; if (st.mode === "cat" && !Object.keys(st.cat.colors).length) assignCats(l); restyle(l); renderRight(); }
  else if (b.hasAttribute("data-recolor")) { assignCats(l, false); restyle(l); renderRight(); }
  else if (b.dataset.ramp) { st.grad.ramp = b.dataset.ramp; restyle(l); renderRight(); }
  else if (b.dataset.color) openPicker(b, b.dataset.color);
  else if (b.hasAttribute("data-addrule")) { const f = fieldsOfKey(l.key)[0] || ""; st.rules.list.push({ field: f, op: "=", val: catValues(l.key, f)[0]?.[0] ?? "", fill: CAT[st.rules.list.length % 8], hatch: false }); restyle(l); renderRight(); }
  else if (b.dataset.delrule) { st.rules.list.splice(+b.dataset.delrule, 1); restyle(l); renderRight(); }
});
function onPaneEdit(e) {
  const t = e.target, pane = $("rightPane"); if (!pane?.contains(t)) return;
  if (t.dataset.attr !== undefined) { if (e.type !== "change" || !SEL) return; pushUndo(SEL.key); const v = t.value; SEL.f.set(t.dataset.attr, isNum(v) && v.trim() !== "" && !/^0\d/.test(v) ? +v : v); SEL.f.set("_edited", true); syncFromSource(SEL.key); return; }
  const l = lyr(CUR); if (!l) return; const st = l.style;
  if (t.hasAttribute("data-lop")) { l.layerOpacity = +t.value; t.nextElementSibling.textContent = Math.round(l.layerOpacity * 100); applyOrder(); return; }
  if (t.dataset.k) {
    const p = t.dataset.k.split("."), v = t.type === "checkbox" ? t.checked : ["range", "number"].includes(t.type) || p[1] === "n" ? +t.value : t.value;
    let o = st; p.slice(0, -1).forEach(x => o = o[x]); o[p[p.length - 1]] = v;
    if (t.dataset.k === "cat.field") assignCats(l, false);
    if (t.type === "range") t.nextElementSibling.textContent = Math.round(v * 100);
    restyle(l); if (e.type === "change") renderRight(); return;
  }
  if (t.dataset.catoff2 !== undefined) { const v = t.dataset.catoff2; st.cat.off = t.checked ? st.cat.off.filter(x => x !== v) : [...st.cat.off, v]; restyle(l); renderRight(); return; }
  if (t.dataset.rule !== undefined) { const r = st.rules.list[+t.dataset.rule]; r[t.dataset.rk] = t.type === "checkbox" ? t.checked : t.value; restyle(l); if (e.type === "change") renderRight(); }
}
document.addEventListener("change", onPaneEdit);
document.addEventListener("input", e => { if (e.target.type === "range" || e.target.dataset?.rk === "val") onPaneEdit(e); });

let popEl = null;
const closePop = () => { popEl?.remove(); popEl = null; };
function openPicker(anchor, key) {
  closePop(); const l = lyr(CUR), st = l.style;
  const set = c => { if (key === "fill") st.fill = c; else if (key === "stroke") st.stroke = c; else if (key === "else") st.rules.elseFill = c; else if (key.startsWith("cat:")) st.cat.colors[key.slice(4)] = c; else st.rules.list[+key.slice(5)].fill = c; restyle(l); renderRight(); };
  popEl = document.createElement("div"); popEl.className = "pop";
  popEl.innerHTML = `<div class="g">${PICK.map(c => `<button style="background:${c}" data-c="${c}" aria-label="${c}"></button>`).join("")}</div><input type="text" placeholder="#RRGGBB" aria-label="Цвет HEX">`;
  document.body.appendChild(popEl); const r = anchor.getBoundingClientRect(); popEl.style.left = Math.min(r.left, innerWidth - 206) + "px"; popEl.style.top = Math.min(r.bottom + 4, innerHeight - 200) + "px";
  popEl.onclick = e => { const b = e.target.closest("[data-c]"); if (b) set(b.dataset.c); };
  popEl.querySelector("input").onchange = e => { if (/^#[0-9a-f]{6}$/i.test(e.target.value)) set(e.target.value.toLowerCase()); };
}
document.addEventListener("pointerdown", e => { if (popEl && !popEl.contains(e.target) && !e.target.closest("[data-color]")) closePop(); });

/* ---------- таблица атрибутов ---------- */
function openTable(on) { winOpen("wTable", on); }
function renderTable() {
  if ($("wTable").hidden) return; const l = lyr(CUR), el = $("attrBody");
  $("attrTitle").textContent = l ? `${l.title} · ${DATA[l.key]?.count ?? 0} объектов · двойной щелчок по ячейке — правка` : "Выберите слой в дереве";
  if (!l) { el.innerHTML = ""; return; }
  const cols = fieldsOfKey(l.key); let rows = layerSrc[l.key].getFeatures().slice();
  if (UIS.filter) { const q = UIS.filter.toLowerCase(); rows = rows.filter(f => cols.some(k => String(f.get(k) ?? "").toLowerCase().includes(q))); }
  if (UIS.sort && cols.includes(UIS.sort.k)) rows.sort((a, b) => { const x = a.get(UIS.sort.k), y = b.get(UIS.sort.k); return (isNum(x) && isNum(y) ? x - y : String(x ?? "").localeCompare(String(y ?? ""), "ru")) * UIS.sort.d; });
  const shown = rows.slice(0, 1500);
  el.innerHTML = `<table class="at"><thead><tr><th></th>${cols.map(k => `<th data-sort="${esc(k)}">${esc(k)}${UIS.sort?.k === k ? (UIS.sort.d > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead><tbody>${shown.map((f, i) => `<tr data-uid="${ol.util.getUid(f)}" class="${SEL?.f === f ? "sel" : ""}"><td class="rn">${i + 1}${f.get("_edited") ? "*" : ""}</td>${cols.map(k => `<td data-cell="${esc(k)}">${esc(f.get(k) ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table>${rows.length > shown.length ? `<div class="note">Показаны первые ${shown.length} из ${rows.length}; уточните фильтр.</div>` : ""}`;
}
const featByUid = (key, uid) => layerSrc[key].getFeatures().find(f => String(ol.util.getUid(f)) === String(uid));
$("attrBody").addEventListener("click", e => {
  const th = e.target.closest("[data-sort]"); if (th) { const k = th.dataset.sort; UIS.sort = { k, d: UIS.sort?.k === k ? -UIS.sort.d : 1 }; renderTable(); return; }
  const tr = e.target.closest("[data-uid]"); if (!tr) return; const f = featByUid(CUR, tr.dataset.uid); if (!f) return;
  select(CUR, f); sharedView.fit(f.getGeometry().getExtent(), { padding: [80, 80, 80, 80], maxZoom: 19, duration: 150 });
});
$("attrBody").addEventListener("dblclick", e => {
  const td = e.target.closest("[data-cell]"); if (!td) return;
  const f = featByUid(CUR, td.parentElement.dataset.uid), k = td.dataset.cell; td.innerHTML = `<input type="text" value="${esc(f.get(k) ?? "")}">`;
  const inp = td.querySelector("input"); inp.focus(); inp.select();
  const done = ok => { if (ok && inp.value !== String(f.get(k) ?? "")) { pushUndo(CUR); const v = inp.value; f.set(k, isNum(v) && v.trim() !== "" && !/^0\d/.test(v) ? +v : v); f.set("_edited", true); syncFromSource(CUR); if (SEL?.f === f) renderRight(); } else renderTable(); };
  inp.onkeydown = ev => { if (ev.key === "Enter") done(true); if (ev.key === "Escape") done(false); }; inp.onblur = () => done(true);
});
$("attrFilter").oninput = e => { UIS.filter = e.target.value; renderTable(); };
$("bTable").onclick = () => openTable();

/* ---------- выбор ---------- */
function select(key, f) { const prev = SEL; SEL = f ? { key, f } : null; if (prev) layerSrc[prev.key]?.changed(); if (SEL) layerSrc[key].changed(); UIS.rt = SEL ? "obj" : UIS.rt; renderRight(); renderTable(); syncRibbon(); }
mMain.on("singleclick", e => {
  if (UIS.tool !== "select") return;
  let hit = null;
  mMain.forEachFeatureAtPixel(e.pixel, (f, layer) => { const k = layer?.get("key"); if (!k || !lyr(k)) return; hit = { k, f }; return true; }, { hitTolerance: 4, layerFilter: la => { const l = lyr(la.get("key")); return !!l && l.visible; } });
  // как «Определить объекты» в QGIS: выбор не меняет текущий слой, иначе рисование уйдёт в чужую выгрузку
  select(hit?.k, hit?.f || null);
});
function setCurrent(key) {
  if (!lyr(key)) return; CUR = key; renderTree(); renderRight(); renderTable();
  // инструмент рисования остаётся, если геометрия слоя подходит, иначе — инструмент под его геометрию
  const t = TOOLS[UIS.tool]; setTool(t.geom && t.geom !== lyr(key).geom ? GEOMTOOL[lyr(key).geom] : UIS.tool);
}
function syncCurSelect() {
  const s = $("curLayer"); if (!s) return;
  s.innerHTML = LYR.length ? LYR.map(l => `<option value="${esc(l.key)}" ${l.key === CUR ? "selected" : ""}>${esc(l.title)} · ${{ poly: "полигоны", line: "линии", point: "точки" }[l.geom]}</option>`).join("") : `<option>нет слоёв — появится при рисовании</option>`;
  s.disabled = !LYR.length;
}
$("curLayer").onchange = e => setCurrent(e.target.value);

/* ---------- строка инструментов ---------- */
const GEOMTOOL = { point: "point", line: "line", poly: "poly" };
const TOOLS = {
  select: { hint: "Выбор: щёлкните объект — его атрибуты справа. Del — удалить, Esc — снять выбор." },
  point: { geom: "point", hint: "Точка: щелчок ставит точку в слой «%»." },
  line: { geom: "line", hint: "Линия в слой «%»: щёлкайте вершины, двойной щелчок завершает, Backspace убирает последнюю вершину, Esc — отмена." },
  poly: { geom: "poly", hint: "Полигон в слой «%»: щёлкайте вершины, двойной щелчок завершает, Backspace убирает последнюю вершину, Esc — отмена." },
  rect: { geom: "poly", hint: "Прямоугольник в слой «%»: щёлкните первый угол, затем противоположный." },
  vertex: { hint: "Вершины слоя «%»: тяните вершину; щелчок по ребру добавляет вершину, Alt+щелчок удаляет." },
  move: { hint: "Перенос: тяните объект слоя «%»." },
  mlen: { hint: "Длина: щёлкайте точки, двойной щелчок завершает. Замеры остаются на карте, Esc стирает." },
  marea: { hint: "Площадь: щёлкайте вершины, двойной щелчок завершает. Замеры остаются на карте, Esc стирает." },
  terr: { hint: "Граница территории: щёлкайте углы, двойной щелчок завершает." } };
const KEYS = { KeyV: "select", KeyP: "point", KeyL: "line", KeyG: "poly", KeyR: "rect", KeyE: "vertex", KeyM: "move", KeyD: "mlen", KeyA: "marea", KeyB: "terr" };
// слой для рисования: текущий, если геометрия подходит; иначе свой слой той же геометрии; иначе новый
function targetLayer(geom) {
  const cur = lyr(CUR); if (cur?.geom === geom) return cur;
  const own = LYR.find(l => l.geom === geom && l.key.startsWith("user:"));
  if (own) { setCurrentQuiet(own.key); return own; }
  const l = createLayerQuiet({ point: "Точки", line: "Линии", poly: "Полигоны" }[geom], geom);
  toast(`Создан слой «${l.title}»: новые объекты попадут в него. Переименовать — двойной щелчок в списке слоёв.`); return l;
}
const setCurrentQuiet = key => { CUR = key; renderTree(); renderRight(); renderTable(); };
function createLayerQuiet(name, geom) { const key = "user:" + Date.now().toString(36);
  DATA[key] = { title: name, source: "создан в проекте", fetched_at: new Date().toISOString().slice(0, 10), fc: { type: "FeatureCollection", features: [] }, count: 0, fields: ["Наименование", "Примечание"] };
  ensureLayer(key, name, geom); setCurrentQuiet(key); return lyr(key); }
const measureSrc = new ol.source.Vector();
mMain.addLayer(new ol.layer.Vector({ source: measureSrc, zIndex: 120, style: f => [S([224, 138, 0, .15], "#c46f00", 2), new ol.style.Style({ text: new ol.style.Text({ text: f.get("label") || "", font: "600 12px system-ui, sans-serif", fill: new ol.style.Fill({ color: "#7a4200" }), stroke: new ol.style.Stroke({ color: "#fff", width: 3 }), overflow: true, placement: "point" }) })] }));
const measureText = g => g.getType() === "Polygon" ? `${fmt(ol.sphere.getArea(g), 0)} м² · ${fmt(ol.sphere.getArea(g) / 1e4, 3)} га` : `${fmt(ol.sphere.getLength(g), 1)} м`;
let toolI = [], drawing = null;
function setTool(t) {
  if (!TOOLS[t]) t = "select";
  toolI.forEach(i => mMain.removeInteraction(i)); toolI = []; drawing = null;
  let l = lyr(CUR);
  const geom = TOOLS[t].geom;
  if (geom) l = targetLayer(geom);
  else if ((t === "vertex" || t === "move") && !l) { toast("Сначала выберите слой в списке."); t = "select"; }
  UIS.tool = t;
  const src = l && layerSrc[l.key];
  const draw = opts => { const d = new ol.interaction.Draw(opts); d.on("drawstart", e => { drawing = d; if (opts.source === src) pushUndo(l.key); if (opts.measure) e.feature.getGeometry().on("change", ev => setHint(measureText(ev.target))); });
    d.on("drawabort", () => { drawing = null; syncStatus(); }); toolI.push(d); return d; };
  if (geom) {
    const d = draw({ source: src, type: t === "rect" ? "Circle" : { point: "Point", line: "LineString", poly: "Polygon" }[geom], geometryFunction: t === "rect" ? ol.interaction.Draw.createBox() : undefined });
    d.on("drawend", e => { drawing = null; e.feature.setProperties({ _edited: true, _new: true }); fieldsOfKey(l.key).forEach(k => e.feature.set(k, "")); setTimeout(() => { syncFromSource(l.key); select(l.key, e.feature); syncStatus(); }, 0); });
  } else if (t === "vertex") {
    const mo = new ol.interaction.Modify({ source: src, deleteCondition: e => ol.events.condition.altKeyOnly(e) && ol.events.condition.singleClick(e) });
    mo.on("modifystart", () => pushUndo(l.key)); mo.on("modifyend", e => { e.features.forEach(f => f.set("_edited", true)); syncFromSource(l.key); if (SEL) renderRight(); }); toolI.push(mo);
  } else if (t === "move") {
    const la = mMain.getLayers().getArray().find(x => x.get("key") === l.key);
    const tr = new ol.interaction.Translate({ layers: [la] });
    tr.on("translatestart", () => pushUndo(l.key)); tr.on("translateend", e => { e.features.forEach(f => f.set("_edited", true)); syncFromSource(l.key); }); toolI.push(tr);
  } else if (t === "mlen" || t === "marea") {
    const d = draw({ source: measureSrc, type: t === "mlen" ? "LineString" : "Polygon", measure: true });
    d.on("drawend", e => { drawing = null; const g = e.feature.getGeometry(); e.feature.set("label", measureText(g)); setHint(measureText(g) + " — замер оставлен на карте, Esc стирает."); });
  } else if (t === "terr") {
    const d = draw({ source: new ol.source.Vector(), type: "Polygon" });
    d.on("drawend", e => { drawing = null; setTerritory(GJ.writeFeatureObject(e.feature)); setTool("select"); toast("Граница задана. Выгрузка источников — окно «Данные»."); });
  }
  if (["point", "line", "poly", "rect", "vertex", "move"].includes(t) && $("snapT").checked) LYR.filter(x => x.visible).forEach(x => toolI.push(new ol.interaction.Snap({ source: layerSrc[x.key], pixelTolerance: 10 })));
  toolI.forEach(i => mMain.addInteraction(i));
  mMain.getTargetElement().style.cursor = t === "select" ? "" : t === "move" ? "move" : "crosshair";
  syncRibbon(); syncStatus();
}
function syncRibbon() {
  document.querySelectorAll("[data-tool]").forEach(b => b.setAttribute("aria-pressed", b.dataset.tool === UIS.tool));
  $("bDelFeat").disabled = !SEL; $("bUndo").disabled = !UNDO.length;
}
let hintOverride = null;
const setHint = t => { hintOverride = t; $("stHint").textContent = t; };
function syncStatus() {
  hintOverride = null; const l = lyr(CUR);
  $("stHint").textContent = !TERR && !LYR.length && UIS.tool === "select" ? "С чего начать: нарисуйте что угодно инструментами сверху, задайте границу территории (B) или откройте окно «Данные»." : TOOLS[UIS.tool].hint.replace("%", l?.title || "—");
  $("stLayer").innerHTML = l ? `слой <b>${esc(l.title)}</b>` : "";
}
window.syncStatus = syncStatus;
document.querySelectorAll("[data-tool]").forEach(b => b.onclick = () => setTool(b.dataset.tool));
$("snapT").onchange = () => setTool(UIS.tool);
$("bDelFeat").onclick = () => { if (!SEL) return toast("Выберите объект: инструмент «Выбор», щелчок по объекту."); const k = SEL.key; pushUndo(k); layerSrc[k].removeFeature(SEL.f); SEL = null; syncFromSource(k); renderRight(); syncRibbon(); };
$("bUndo").onclick = undo;
const UNDO = [];
function pushUndo(key) { UNDO.push({ key, fc: JSON.stringify(GJ.writeFeaturesObject(layerSrc[key].getFeatures())) }); if (UNDO.length > 60) UNDO.shift(); syncRibbon(); }
function undo() { if (drawing) { drawing.removeLastPoint(); return; } const u = UNDO.pop(); if (!u) return toast("Отменять нечего."); layerSrc[u.key].clear(); layerSrc[u.key].addFeatures(GJ.readFeatures(JSON.parse(u.fc))); SEL = null; syncFromSource(u.key); renderRight(); syncRibbon(); }
addEventListener("keydown", e => {
  if (e.target.matches?.("input,select,textarea") || e.target.closest?.("#wGraph")) return;
  // e.code не зависит от раскладки (русская тоже работает); без code — по латинской букве
  const code = e.code || (/^[a-z]$/i.test(e.key) ? "Key" + e.key.toUpperCase() : "");
  if ((e.metaKey || e.ctrlKey) && code === "KeyZ") { e.preventDefault(); undo(); return; }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (e.key === "Backspace" && drawing) { e.preventDefault(); drawing.removeLastPoint(); }
  else if ((e.key === "Delete" || e.key === "Backspace") && SEL) { e.preventDefault(); $("bDelFeat").click(); }
  else if (e.key === "Escape") { if (drawing) { drawing.abortDrawing(); return; } measureSrc.clear(); select(null, null); setTool("select"); }
  else if (KEYS[code]) { e.preventDefault(); setTool(KEYS[code]); }
});
// в подсказках Windows показывает Ctrl, macOS — ⌘
if (/Mac/.test(navigator.platform)) document.querySelectorAll("[title*='Ctrl+Z']").forEach(b => b.title = b.title.replace("Ctrl+Z", "⌘Z"));
mMain.on("pointermove", e => { const [lo, la] = ol.proj.toLonLat(e.coordinate); $("stXY").textContent = `${la.toFixed(5)}° с.ш. ${lo.toFixed(5)}° в.д.`; });
const syncScale = () => { const r = sharedView.getResolution(), la = ol.proj.toLonLat(sharedView.getCenter())[1]; $("stScale").textContent = "1:" + fmt(Math.round(r * Math.cos(la * Math.PI / 180) / 0.000264583 / 10) * 10); };
sharedView.on("change:resolution", syncScale); syncScale();

ALLMAPS.forEach(m => window.attachDataLayers(m));
renderTree(); renderRight(); setTool("select");
