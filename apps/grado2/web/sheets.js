/* ГРАДО 2 · листы и альбом (этап Э6). Лист = вид карты (или текущая карта) в рамке А3/А1 с масштабом, легендой вида,
   таблицей ТЭП, стрелкой севера, масштабной линейкой и основной надписью по ГОСТ Р 21.101. Оформление объектов
   считает тот же код, что рисует слои на экране (symbolOf), поэтому лист не расходится с картой; в PDF его
   собирает рендер ядра (print_io.py): МГГТ, типы линий REDLN97, штриховки. Состав альбома хранится в проекте. */
const ALBUM = { meta: { object: "", code: "", stage: "ПП", org: "" }, sheets: [] };
const SCALES = [500, 1000, 2000, 2500, 3000, 4000, 5000, 10000, 25000];
const FRAME_MM = { A3: [275, 224], A1: [636, 521] };          // размер карты на листе (как layout() в print_io.py)
const newSheet = () => ({ id: "s" + Date.now().toString(36) + Math.random().toString(36).slice(2, 4), title: VIEWS.find(v => v.id === VIEW_CUR)?.name || "Существующее положение", size: "A3", view: VIEW_CUR || "", scale: 0, legend: true, tep: false });

function autoScale(size) {
  if (!TERR) return 2000;
  const [w, s, e, n] = turf.bbox(TERR), mx = (e - w) * 111320 * Math.cos((s + n) / 2 * Math.PI / 180), my = (n - s) * 110540, [fw, fh] = FRAME_MM[size];
  const need = Math.max(mx / fw, my / fh) * 1000 * 1.08;
  return SCALES.find(v => v >= need) || SCALES[SCALES.length - 1];
}
// состояние слоя в виде (или как сейчас на карте)
function viewLayers(sheet) {
  const v = VIEWS.find(x => x.id === sheet.view), by = v ? new Map(v.layers.map(x => [x.key, x])) : null, gv = v ? new Map(v.groups.map(x => [x.id, x.visible])) : null;
  // слой, которого не было при сохранении вида, в вид не входит — как при «Показать» (applyView)
  return LYR.map(l => { const x = by?.get(l.key); const st = x ? ST(JSON.parse(JSON.stringify(x.style))) : l.style, vis = v ? !!x?.visible : l.visible;
    const g = l.group ? (gv?.has(l.group) ? gv.get(l.group) : grp(l.group)?.visible !== false) : true;
    return { key: l.key, title: l.title, geom: l.geom, style: st, visible: vis && g, a: x ? x.layerOpacity ?? 1 : l.layerOpacity, _br: null, cache: new Map() }; }).filter(p => p.visible);
}
const sheetCenter = sheet => sheet.center || (TERR ? turf.centroid(TERR).geometry.coordinates : ol.proj.toLonLat(sharedView.getCenter()));
// показатели ТЭП строками таблицы; на листе с картой — первые 30, на листе «Таблица ТЭП» — все
function tepRows(all) {
  const t = RESULT.tepNode?._tep; if (!t) return [];
  const ms = t.metrics.filter(m => m.value);
  return [["Территория", fmt(t.terr, 2) + " га"], ["СПП новая", fmt(t.sppNew / 1000, 1) + " тыс. м²"], ["СПП сохраняемая", fmt(t.sppKept / 1000, 1) + " тыс. м²"], ["Плотность", fmt(t.density, 1) + " тыс. м²/га"], ["Застроенность", fmt(t.cover * 100, 1) + " %"]]
    .concat((all ? ms : ms.slice(0, 30)).map(m => [m.title, fmt(m.value, Number.isInteger(m.value) ? 0 : 1) + " " + m.unit]));
}
function sheetSpec(sheet) {
  if (sheet.kind === "tep") return { title: sheet.title, size: sheet.size, kind: "tep", tep: tepRows(true) };
  const size = sheet.size, scale = sheet.scale || autoScale(size), [fw, fh] = FRAME_MM[size];
  const center = sheetCenter(sheet);
  const half = [fw / 2 / 1000 * scale * 1.15, fh / 2 / 1000 * scale * 1.15], c3 = ol.proj.fromLonLat(center), stretch = 1 / Math.cos(center[1] * Math.PI / 180);
  const ext = [c3[0] - half[0] * stretch, c3[1] - half[1] * stretch, c3[0] + half[0] * stretch, c3[1] + half[1] * stretch];
  const vl = viewLayers(sheet).filter(pl => !(pl.style.maxDen && scale > pl.style.maxDen)), layers = [], legend = [];   // видимость по масштабу — и на листе, как в QGIS
  vl.slice().reverse().forEach(pl => {                                   // снизу вверх, как рисует карта
    const st = pl.style, feats = [];
    layerSrc[pl.key]?.forEachFeatureInExtent(ext, f => {
      const g = GJ.writeFeatureObject(f).geometry; if (!g) return;
      const lab = st.label ? f.get(st.label) : null;
      if (st.mode === "lgr") { const lt = f.get("_lt") || [], miss = f.get("_miss") || []; feats.push({ g, lt, miss, lc: LGRC[ltCode(lt[0] || "")] || LGRC[miss[0]?.[0]] || "#d7191c", w: st.width, label: lab }); return; }
      const s = symbolOf(pl, f); if (s.hide) return;
      feats.push({ g, fill: s.fill, stroke: pl.geom === "poly" ? st.stroke : s.fill, w: st.width, a: st.opacity * pl.a, hatch: s.hatch, label: lab == null || lab === "" ? null : String(lab), lc: pl.geom === "line" ? s.fill : undefined });
    });
    layers.push({ title: pl.title, features: feats });
  });
  if (sheet.legend) vl.forEach(pl => {
    const st = pl.style, items = st.mode === "lgr" ? [{ label: "красные линии и ЛГР (REDLN97)", fill: "#d7191c" }] : legendItems(pl).filter(it => !it.off).slice(0, 14).map(it => ({ label: it.v, fill: it.c, stroke: pl.geom === "poly" ? st.stroke : it.c, hatch: st.hatch, a: st.opacity }));
    legend.push({ title: pl.title, kind: pl.geom, items: items.length ? items : [{ label: pl.title, fill: st.fill, stroke: st.stroke, hatch: st.hatch, a: st.opacity }] });
  });
  const tep = sheet.tep ? tepRows(false) : [];
  return { title: sheet.title, size, scale, center, layers, legend, tep, territory: TERR?.geometry || null };
}
const albumSpec = list => ({ meta: ALBUM.meta, sheets: list.map(sheetSpec) });

async function previewSheet(i) {
  busy(true);
  try {
    const r = await fetch("/api/print/svg", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...albumSpec([ALBUM.sheets[i]]), index: 0 }) });
    if (!r.ok) throw new Error((await r.json()).error);
    const url = URL.createObjectURL(await r.blob()), img = $("sheetPrev"); if (img.dataset.url) URL.revokeObjectURL(img.dataset.url);
    img.src = url; img.dataset.url = url; img.hidden = false;
  } catch (e) { toast("Лист не собран: " + e.message); } finally { busy(false); }
}
async function albumPdf() {
  if (!ALBUM.sheets.length) return toast("В альбоме нет листов: «Добавить лист».");
  busy(true);
  try {
    const r = await fetch("/api/print/pdf", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(albumSpec(ALBUM.sheets)) });
    if (!r.ok) throw new Error((await r.json()).error);
    const a = document.createElement("a"); a.href = URL.createObjectURL(await r.blob()); a.download = (ALBUM.meta.object || PROJ.name || "альбом") + ".pdf"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    toast(`Альбом PDF: ${ALBUM.sheets.length} л. Координаты — МГГТ, красные линии — типами REDLN97.`);
  } catch (e) { toast("PDF не собран: " + e.message); } finally { busy(false); }
}
function renderSheets() {
  const el = $("sheetsBody"); if (!el) return;
  const m = ALBUM.meta, inp = (k, ph) => `<input type="text" data-meta="${k}" value="${esc(m[k] || "")}" placeholder="${ph}" aria-label="${ph}">`;
  const vopts = s => `<option value="" ${s.kind !== "tep" && !s.view ? "selected" : ""}>текущая карта</option>` + VIEWS.map(v => `<option value="${v.id}" ${s.kind !== "tep" && v.id === s.view ? "selected" : ""}>вид «${esc(v.name)}»</option>`).join("")
    + `<option value="__tep" ${s.kind === "tep" ? "selected" : ""}>таблица ТЭП (все показатели)</option>`;
  const tepS = s => s.kind === "tep" ? "disabled" : "";
  el.innerHTML = `<div class="pad"><div class="note" style="padding:0 0 6px">Основная надпись</div><div class="meta4">${inp("object", "Объект")}${inp("code", "Шифр")}${inp("stage", "Стадия кратко: ПП, П, Р")}${inp("org", "Организация")}</div></div>`
    + `<div class="sect">Листы альбома</div>`
    + (ALBUM.sheets.length ? `<table class="at sheets"><colgroup><col style="width:26px"><col><col style="width:58px"><col style="width:20%"><col style="width:19%"><col style="width:36px"><col style="width:36px"><col style="width:148px"></colgroup><thead><tr><th>№</th><th>Название</th><th>Формат</th><th>Содержание</th><th>Масштаб</th><th title="Легенда вида">Лег.</th><th title="Таблица ТЭП">ТЭП</th><th></th></tr></thead><tbody>${ALBUM.sheets.map((s, i) => `<tr data-sh="${i}">
        <td class="num">${i + 1}</td><td><input type="text" data-sk="title" value="${esc(s.title)}" aria-label="Название листа"></td>
        <td><select data-sk="size" aria-label="Формат">${["A3", "A1"].map(v => `<option ${v === s.size ? "selected" : ""}>${v}</option>`).join("")}</select></td>
        <td><select data-sk="view" aria-label="Содержание листа">${vopts(s)}</select></td>
        <td><select data-sk="scale" aria-label="Масштаб" ${tepS(s)}><option value="0" title="Масштаб подобран так, чтобы территория поместилась на лист">авто 1:${fmt(autoScale(s.size))}</option>${SCALES.map(v => `<option value="${v}" ${v === s.scale ? "selected" : ""}>1:${fmt(v)}</option>`).join("")}</select></td>
        <td><input type="checkbox" data-sk="legend" ${s.legend ? "checked" : ""} aria-label="Легенда" ${tepS(s)}></td><td><input type="checkbox" data-sk="tep" ${s.tep ? "checked" : ""} aria-label="ТЭП" ${tepS(s)}></td>
        <td class="acts">${s.kind === "tep" ? "" : `<button class="tb" data-shframe="${i}" aria-pressed="${FRAME?.i === i}" title="Рамка листа на карте: тяните её мышью, чтобы выбрать, что попадёт на лист${s.center ? ". Сейчас лист сдвинут — «Вернуть» центрирует его на территории" : ""}"><i data-lucide="frame"></i></button>`}${s.center && s.kind !== "tep" ? `<button class="tb" data-shreset="${i}" title="Вернуть лист в центр территории"><i data-lucide="locate-fixed"></i></button>` : ""}<button class="tb" data-shprev="${i}" title="Просмотр листа"><i data-lucide="eye"></i></button><button class="tb" data-shup="${i}" title="Выше"><i data-lucide="arrow-up"></i></button><button class="tb" data-shdel="${i}" title="Удалить лист"><i data-lucide="trash-2"></i></button></td></tr>`).join("")}</tbody></table>`
      : `<div class="note">Листов пока нет. Лист берёт вид карты (окно «Виды») или текущую карту, рамку А3/А1 по ГОСТ, легенду и ТЭП.</div>`)
    + `<div class="pad row"><button class="btn" id="shAdd"><i data-lucide="file-plus"></i>Добавить лист</button><span class="sp" style="flex:1"></span><button class="btn primary" id="shPdf" title="Все листы одним PDF: рамка, штамп, масштаб, легенда"><i data-lucide="file-down"></i>PDF альбома</button></div>`
    + `<div class="sheetprev"><img id="sheetPrev" alt="Просмотр листа" hidden></div>`;
  icons();
}
const shEl = () => $("sheetsBody");
shEl().addEventListener("change", e => {
  const t = e.target, row = t.closest("[data-sh]");
  if (t.dataset.meta) { ALBUM.meta[t.dataset.meta] = t.value; window.markDirty?.(); return; }
  if (!row || !t.dataset.sk) return; const s = ALBUM.sheets[+row.dataset.sh], k = t.dataset.sk;
  if (k === "view") { s.kind = t.value === "__tep" ? "tep" : "map"; s.view = s.kind === "tep" ? "" : t.value; if (s.kind === "tep") { s.title = s.title === newSheet().title || !s.title ? "Технико-экономические показатели" : s.title; if (FRAME?.i === +row.dataset.sh) showFrame(null); } }
  else s[k] = t.type === "checkbox" ? t.checked : k === "scale" ? +t.value : t.value;
  window.markDirty?.(); if (["size", "view"].includes(k)) renderSheets();
  if (FRAME?.i === +row.dataset.sh && ["size", "scale", "title"].includes(k)) showFrame(FRAME.i);
});
shEl().addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.id === "shAdd") { ALBUM.sheets.push(newSheet()); window.markDirty?.(); renderSheets(); previewSheet(ALBUM.sheets.length - 1); }
  if (b.id === "shPdf") albumPdf();
  if (b.dataset.shprev) previewSheet(+b.dataset.shprev);
  if (b.dataset.shframe) { const i = +b.dataset.shframe; showFrame(FRAME?.i === i ? null : i); renderSheets(); }
  if (b.dataset.shreset) { const i = +b.dataset.shreset; delete ALBUM.sheets[i].center; window.markDirty?.(); if (FRAME?.i === i) showFrame(i); renderSheets(); }
  if (b.dataset.shup || b.dataset.shdel) showFrame(null);
  if (b.dataset.shup) { const i = +b.dataset.shup; if (i > 0) { [ALBUM.sheets[i - 1], ALBUM.sheets[i]] = [ALBUM.sheets[i], ALBUM.sheets[i - 1]]; window.markDirty?.(); renderSheets(); } }
  if (b.dataset.shdel) { const i = +b.dataset.shdel; if (confirmInline(b, `Удалить лист «${ALBUM.sheets[i].title}»?`)) { ALBUM.sheets.splice(i, 1); window.markDirty?.(); renderSheets(); } }
});
/* Рамка листа на карте (как видовой экран листа в AutoCAD): размер = карта листа × масштаб, тянется мышью.
   Сдвиг запоминается в листе (center), без сдвига лист стоит по центру территории. */
let FRAME = null;
function frameGeom(sh) {
  const [fw, fh] = FRAME_MM[sh.size], scale = sh.scale || autoScale(sh.size), c = sheetCenter(sh), c3 = ol.proj.fromLonLat(c), k = 1 / Math.cos(c[1] * Math.PI / 180);
  const hx = fw / 2 / 1000 * scale * k, hy = fh / 2 / 1000 * scale * k;
  return new ol.geom.Polygon([[[c3[0] - hx, c3[1] - hy], [c3[0] + hx, c3[1] - hy], [c3[0] + hx, c3[1] + hy], [c3[0] - hx, c3[1] + hy], [c3[0] - hx, c3[1] - hy]]]);
}
function showFrame(i) {
  if (FRAME) { mMain.removeLayer(FRAME.layer); mMain.removeInteraction(FRAME.tr); FRAME = null; }
  if (i == null || !ALBUM.sheets[i] || ALBUM.sheets[i].kind === "tep") return;
  const sh = ALBUM.sheets[i], f = new ol.Feature(frameGeom(sh)), scale = sh.scale || autoScale(sh.size);
  const layer = new ol.layer.Vector({ source: new ol.source.Vector({ features: [f] }), zIndex: 10000, style: new ol.style.Style({
    stroke: new ol.style.Stroke({ color: "#1a5fb4", width: 2.5 }), fill: new ol.style.Fill({ color: "rgba(26,95,180,.07)" }),
    text: new ol.style.Text({ text: `Лист ${i + 1} «${sh.title}», ${sh.size}, 1:${fmt(scale)}\nтяните рамку, чтобы сдвинуть`, font: "600 12px system-ui, sans-serif", fill: new ol.style.Fill({ color: "#1a5fb4" }),
      stroke: new ol.style.Stroke({ color: "#fff", width: 3 }), overflow: true }) }) });
  const tr = new ol.interaction.Translate({ layers: [layer] });
  tr.on("translateend", () => { sh.center = ol.proj.toLonLat(ol.extent.getCenter(f.getGeometry().getExtent())); window.markDirty?.(); renderSheets(); });
  mMain.addLayer(layer); mMain.addInteraction(tr); FRAME = { i, layer, tr };
  // рамку — в ту часть карты, которую не закрывает окно «Листы» (обычно оно полосой внизу)
  const m = mMain.getTargetElement().getBoundingClientRect(), w = $("wSheets").getBoundingClientRect(), pad = [24, 24, 24, 24];
  if (w.top > m.top + m.height * .3) pad[2] = Math.max(24, m.bottom - w.top + 16); else if (w.bottom < m.bottom - m.height * .3) pad[0] = Math.max(24, w.bottom - m.top + 16);
  mMain.getView().fit(f.getGeometry().getExtent(), { padding: pad, duration: 250 });
}
// окно «Листы» закрыто — рамка с карты уходит
new MutationObserver(() => { if ($("wSheets").hidden && FRAME) showFrame(null); }).observe($("wSheets"), { attributes: true, attributeFilter: ["hidden"] });
window.renderSheets = renderSheets; window.hideSheetFrame = () => showFrame(null);
