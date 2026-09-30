/* ГРАДО 2 · виды карты (как «Темы карты» в QGIS): вид запоминает, какие слои видны, их оформление и прозрачность,
   видимость групп, подложку и, по желанию, масштаб. «Существующее положение», «Ограничения», «Эскиз» — одна карта
   с разными видами; легенда вида собирается из его видимых слоёв. Виды сохраняются в проекте и станут листами альбома. */
const VIEWS = [];
let VIEW_CUR = null;
const clone = o => JSON.parse(JSON.stringify(o));
function captureView(name, withExtent) {
  return { id: "v" + Date.now().toString(36), name, basemap: BASE,
    layers: LYR.map(l => ({ key: l.key, visible: l.visible, style: clone(l.style), layerOpacity: l.layerOpacity })),
    groups: GROUPS.map(g => ({ id: g.id, visible: g.visible })),
    extent: withExtent ? { center: ol.proj.toLonLat(sharedView.getCenter()), zoom: sharedView.getZoom() } : null };
}
function applyView(v) {
  const byKey = new Map(v.layers.map(x => [x.key, x]));
  LYR.forEach(l => { const x = byKey.get(l.key); if (!x) { l.visible = false; return; } l.visible = x.visible; l.layerOpacity = okn(x.layerOpacity, 1); l.style = ST(clone(x.style)); restyle(l); });
  v.groups.forEach(x => { const g = grp(x.id); if (g) g.visible = x.visible; });
  if (v.basemap && v.basemap !== BASE) setBasemap(v.basemap);
  if (v.extent) { sharedView.setCenter(ol.proj.fromLonLat(v.extent.center)); sharedView.setZoom(v.extent.zoom); }
  VIEW_CUR = v.id; dataRev++; applyOrder(); renderTree(); renderRight(); renderViews();
}
// легенда вида: видимые в нём слои сверху вниз с их знаками и классами
function legendHTML(v) {
  const on = new Set(v.layers.filter(x => x.visible).map(x => x.key));
  return LYR.filter(l => on.has(l.key) && (!l.group || grp(l.group)?.visible !== false)).map(l => {
    const items = legendItems(l).slice(0, 12);
    return `<div class="lg"><div class="lgh">${symHTML(l)}<span>${esc(l.title)}</span></div>${items.map(it => `<div class="lgi">${symHTML(l, it.c)}<span>${esc(it.v || "—")}</span></div>`).join("")}</div>`;
  }).join("") || `<div class="empty">В виде нет видимых слоёв</div>`;
}
function renderViews() {
  const el = $("viewsBody"); if (!el) return;
  const cur = VIEWS.find(v => v.id === VIEW_CUR);
  el.innerHTML = `<div class="projbar"><input type="text" id="viewName" placeholder="Название вида, например «Ограничения»" aria-label="Название вида"><label class="inl" title="Вид запомнит и масштаб карты"><input type="checkbox" id="viewExt">с масштабом</label><button class="btn primary" id="viewSave" title="Запомнить видимые слои, их оформление и подложку"><i data-lucide="bookmark-plus"></i>Сохранить вид</button></div>`
    + (VIEWS.length ? `<table class="at"><tbody>${VIEWS.map(v => `<tr class="${v.id === VIEW_CUR ? "sel" : ""}"><td>${esc(v.name)}</td><td class="num">${v.layers.filter(x => x.visible).length} сл.</td><td style="white-space:nowrap"><button class="btn" data-vshow="${esc(v.id)}">Показать</button> <button class="tb" data-vupd="${esc(v.id)}" title="Заменить вид текущим состоянием карты"><i data-lucide="refresh-cw"></i></button><button class="tb" data-vdel="${esc(v.id)}" title="Удалить вид"><i data-lucide="trash-2"></i></button></td></tr>`).join("")}</tbody></table>`
      : `<div class="note">Видов пока нет. Настройте карту (какие слои видны, их стиль, подложку) и сохраните вид — например «Существующее положение», «Ограничения», «Эскиз». Переключение вида меняет карту одним щелчком.</div>`)
    + (cur ? `<div class="sect">Легенда вида «${esc(cur.name)}»</div><div class="legend">${legendHTML(cur)}</div>` : "");
  icons();
}
$("viewsBody").addEventListener("click", e => {
  const t = e.target.closest("button"); if (!t) return;
  if (t.id === "viewSave") { const name = $("viewName").value.trim() || `Вид ${VIEWS.length + 1}`; const v = captureView(name, $("viewExt").checked); VIEWS.push(v); VIEW_CUR = v.id; window.markDirty?.(); renderViews(); toast(`Вид «${name}» сохранён.`); }
  if (t.dataset.vshow) applyView(VIEWS.find(v => v.id === t.dataset.vshow));
  if (t.dataset.vupd) { const i = VIEWS.findIndex(v => v.id === t.dataset.vupd), old = VIEWS[i]; VIEWS[i] = { ...captureView(old.name, !!old.extent), id: old.id }; window.markDirty?.(); renderViews(); toast(`Вид «${old.name}» обновлён.`); }
  if (t.dataset.vdel) {
    const i = VIEWS.findIndex(v => v.id === t.dataset.vdel), used = ALBUM.sheets.filter(s => s.view === t.dataset.vdel);
    if (!confirmInline(t, `Удалить вид «${VIEWS[i].name}»?${used.length ? ` Листов с ним: ${used.length} — они перейдут на текущую карту.` : ""}`)) return;
    // лист на удалённом виде не печатает молча «что сейчас на карте»: он явно переводится на текущую карту
    used.forEach(s => { s.view = ""; }); if (VIEW_CUR === t.dataset.vdel) VIEW_CUR = null;
    const name = VIEWS[i].name; VIEWS.splice(i, 1); window.markDirty?.(); renderViews(); window.renderSheets?.();
    if (used.length) toast(`Вид «${name}» удалён. Листы ${used.map(s => `«${s.title}»`).join(", ")} теперь показывают текущую карту.`);
  }
});
window.renderViews = renderViews;
