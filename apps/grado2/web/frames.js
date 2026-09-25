/* ГРАДО 2 · «Лист» на карте — как фрейм в Figma или видовой экран в AutoCAD.
   Инструмент «Лист»: тяните прямоугольник — пропорции формата (А3 по умолчанию) держатся сами, масштаб считается из
   размера. Выбранный лист: тянуть внутри — сдвиг, за угол — размер, над листом панель: формат, ориентация, масштаб,
   «Загрузить сюда», «DXF ГИС ОГД», удалить. Граница участка не нужна. Лист живёт в МСК (центр и размер в метрах),
   поэтому на карте видно ровно то, что попадёт в чертёж. Листы хранятся в проекте (ALBUM.frames). */
(function () {
  const PAPER = { A4: [297, 210], A3: [420, 297], A2: [594, 420], A1: [841, 594], A0: [1189, 841] };
  const PT = { A4: "А4", A3: "А3", A2: "А2", A1: "А1", A0: "А0" };
  const ROUND = [500, 1000, 2000, 2500, 5000, 10000, 25000];
  const BLUE = "#1a5fb4";
  ALBUM.frames ||= [];
  let SELF = null, drawing = false, drag = null;

  const paperMM = fr => { const [a, b] = PAPER[fr.paper] || PAPER.A3; return fr.orient === "P" ? [b, a] : [a, b]; };
  const sizeM = fr => paperMM(fr).map(v => v * fr.scale / 1000);
  const toMap = p => ol.proj.fromLonLat(MSK.toWgs(p));
  const toMsk = c => MSK.fromWgs(ol.proj.toLonLat(c));
  const corners = fr => { const [w, h] = sizeM(fr), [cx, cy] = fr.c; return [[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]]; };
  const title = (fr, i) => `Лист ${i + 1} · ${PT[fr.paper] || fr.paper}${fr.orient === "P" ? " книжн." : ""} · 1:${fmt(Math.round(fr.scale))}`;
  window.frameBoxWgs = fr => { const ll = corners(fr).map(p => MSK.toWgs(p)); return [Math.min(...ll.map(p => p[0])), Math.min(...ll.map(p => p[1])), Math.max(...ll.map(p => p[0])), Math.max(...ll.map(p => p[1]))]; };

  const src = new ol.source.Vector();
  const grip = new ol.style.Style({ image: new ol.style.RegularShape({ points: 4, radius: 6, angle: Math.PI / 4, fill: new ol.style.Fill({ color: "#fff" }), stroke: new ol.style.Stroke({ color: BLUE, width: 2 }) }),
    geometry: f => new ol.geom.MultiPoint(f.getGeometry().getCoordinates()[0].slice(0, 4)) });
  const layer = new ol.layer.Vector({ source: src, zIndex: 130, style: f => {
    const on = f.get("fr") === SELF, [tl] = [f.getGeometry().getCoordinates()[0][3]];
    return [new ol.style.Style({ stroke: new ol.style.Stroke({ color: BLUE, width: on ? 2.5 : 1.5 }), fill: new ol.style.Fill({ color: on ? "rgba(26,95,180,.05)" : "rgba(26,95,180,.001)" }) }),   // почти прозрачная заливка: щелчок внутри листа его выбирает
      new ol.style.Style({ geometry: new ol.geom.Point(tl), text: new ol.style.Text({ text: f.get("label"), font: `${on ? 600 : 500} 12px system-ui, sans-serif`, textAlign: "left", textBaseline: "bottom", offsetY: -5,
        fill: new ol.style.Fill({ color: BLUE }), stroke: new ol.style.Stroke({ color: "#fff", width: 3 }) }) }),
      ...(on ? [grip] : [])];
  } });
  mMain.addLayer(layer);

  // панель над выбранным листом (как контекстная панель фрейма в Figma)
  const bar = document.createElement("div");
  bar.className = "framebar";
  const ov = new ol.Overlay({ element: bar, positioning: "bottom-left", offset: [0, -24], stopEvent: true });
  mMain.addOverlay(ov);

  function redraw() {
    src.clear();
    ALBUM.frames.forEach((fr, i) => { const r = corners(fr).map(toMap), f = new ol.Feature(new ol.geom.Polygon([[...r, r[0]]])); f.set("fr", fr); f.set("label", title(fr, i)); src.addFeature(f); });
    placeBar(); window.updateCover?.();
  }
  window.redrawFrames = redraw;
  function placeBar() {
    if (!SELF || !ALBUM.frames.includes(SELF)) { SELF = null; ov.setPosition(undefined); return; }
    ov.setPosition(toMap(corners(SELF)[3]));
    const sc = Math.round(SELF.scale);
    bar.innerHTML = `<select data-k="paper" title="Формат листа">${Object.keys(PAPER).map(k => `<option value="${k}" ${k === SELF.paper ? "selected" : ""}>${PT[k]}</option>`).join("")}</select>`
      + `<button class="tb" data-a="orient" title="${SELF.orient === "P" ? "Книжная — сделать альбомной" : "Альбомная — сделать книжной"}"><i data-lucide="${SELF.orient === "P" ? "rectangle-vertical" : "rectangle-horizontal"}"></i></button>`
      + `<label title="Масштаб листа: введите число или тяните угол рамки">1:<input data-k="scale" list="frScales" value="${sc}" inputmode="numeric"></label>`
      + `<datalist id="frScales">${ROUND.map(v => `<option value="${v}">`).join("")}</datalist>`
      + `<span class="vs"></span><button class="btn" data-a="load" title="Загрузить отмеченные в окне «Данные» источники на этот лист"><i data-lucide="download"></i>Загрузить сюда</button>`
      + `<button class="btn primary" data-a="ogd" title="Все слои ГИС ОГД внутри листа — чертёж DXF в МСК: слой портала на своём слое, цвета как на портале, лист бумаги ${PT[SELF.paper]} с видовым экраном 1:${fmt(sc)}"><i data-lucide="file-down"></i>DXF ГИС ОГД</button>`
      + `<button class="tb" data-a="del" title="Удалить лист (Del)"><i data-lucide="trash-2"></i></button>`;
    icons();
    // панель не уходит за края карты: сдвиг влево у правого края, под лист — если над листом нет места
    ov.setOffset([0, -24]); ov.setPositioning("bottom-left");
    bar.style.setProperty("--fbw", Math.max(240, mMain.getTargetElement().clientWidth - 16) + "px");   // узкая карта — панель в две строки
    requestAnimationFrame(() => {
      const m = mMain.getTargetElement().getBoundingClientRect(), r = bar.getBoundingClientRect();
      if (!r.width) return;
      const dx = r.right > m.right - 8 ? Math.max(m.right - 8 - r.right, m.left + 8 - r.left) : r.left < m.left + 8 ? m.left + 8 - r.left : 0;
      if (r.top < m.top + 4) { ov.setPositioning("top-left"); ov.setPosition(toMap(corners(SELF)[0])); ov.setOffset([dx, 10]); }
      else ov.setOffset([dx, -24]);
    });
  }
  bar.addEventListener("change", e => {
    const k = e.target.dataset.k; if (!k || !SELF) return;
    if (k === "paper") { const w = sizeM(SELF)[0]; SELF.paper = e.target.value; SELF.scale = w * 1000 / paperMM(SELF)[0]; }   // ширина на местности та же
    if (k === "scale") { const v = +String(e.target.value).replace(/\D/g, ""); if (v >= 100 && v <= 1e6) SELF.scale = v; }
    changed();
  });
  bar.addEventListener("click", e => {
    const a = e.target.closest("[data-a]")?.dataset.a; if (!a || !SELF) return;
    if (a === "orient") { SELF.orient = SELF.orient === "P" ? "L" : "P"; changed(); }
    if (a === "del") remove(SELF);
    if (a === "load") loadHere(SELF);
    if (a === "ogd") window.exportOgd?.(SELF);
  });
  bar.addEventListener("keydown", e => { if (e.key === "Enter") e.target.blur(); e.stopPropagation(); });

  function changed() { window.markDirty?.(); redraw(); }
  function select(fr) { SELF = fr; redraw(); }
  function remove(fr) {
    const i = ALBUM.frames.indexOf(fr); if (i < 0) return;
    ALBUM.frames.splice(i, 1); SELF = null; changed();
    toast(`Лист ${i + 1} удалён.`);
  }
  function loadHere(fr) {
    if (!CHECKED.size) { winOpen("wData", true); return toast("Отметьте источники в окне «Данные» — затем «Загрузить сюда» на листе или «Загрузить» в окне."); }
    loadKeys([...CHECKED], frameBoxWgs(fr));
  }
  window.selectedFrame = () => SELF;
  window.startFrame = () => { drawing = true; SELF = null; redraw(); window.clearTools?.(); mMain.getTargetElement().style.cursor = "crosshair";
    $("bFrame").setAttribute("aria-pressed", true);
    window.setHint?.("Лист: тяните прямоугольник по карте — пропорции формата держатся сами, масштаб считается из размера. Щелчок — лист на весь экран. Esc — отмена."); };
  const stopDraw = () => { drawing = false; mMain.getTargetElement().style.cursor = ""; $("bFrame").setAttribute("aria-pressed", false); window.syncStatus?.(); };

  // лист по двум углам: пропорции формата, масштаб — из размера
  function fromCorners(a, b, base) {
    const [pw, ph] = paperMM(base), dx = b[0] - a[0], dy = b[1] - a[1];
    const scale = Math.max(Math.abs(dx) / pw, Math.abs(dy) / ph) * 1000, w = pw * scale / 1000, h = ph * scale / 1000;
    return { ...base, scale, c: [a[0] + Math.sign(dx || 1) * w / 2, a[1] + Math.sign(dy || 1) * h / 2] };
  }
  const hitFrame = px => mMain.forEachFeatureAtPixel(px, f => f.get("fr"), { layerFilter: l => l === layer, hitTolerance: 6 });
  const hitGrip = px => { if (!SELF) return -1; return corners(SELF).map(toMap).findIndex(c => { const p = mMain.getPixelFromCoordinate(c); return Math.hypot(p[0] - px[0], p[1] - px[1]) < 10; }); };

  const it = new ol.interaction.Pointer({
    handleDownEvent(e) {
      if (e.originalEvent.button) return false;
      const m = toMsk(e.coordinate);
      if (drawing) { const base = { id: "f" + Date.now().toString(36), paper: SELF?.paper || ALBUM.frames.at(-1)?.paper || "A3", orient: ALBUM.frames.at(-1)?.orient || "L", scale: 1, c: m };
        ALBUM.frames.push(base); SELF = base; drag = { mode: "new", a: m, px: e.pixel }; return true; }
      if (window.CAD?.active?.()) return false;             // идёт команда черчения — лист не мешает
      const g = hitGrip(e.pixel);
      if (g >= 0) { const cs = corners(SELF); drag = { mode: "size", a: cs[(g + 2) % 4] }; return true; }
      const fr = hitFrame(e.pixel);
      // внутри листа лежат объекты чертежа: щелчок по объекту — выбор объекта, по пустому месту — выбор листа
      const other = fr && fr !== SELF && mMain.forEachFeatureAtPixel(e.pixel, () => true, { layerFilter: l => l !== layer && l.getZIndex() !== 105, hitTolerance: 3 });
      if (fr && !other) { if (fr !== SELF) select(fr); drag = { mode: "move", m0: m, c0: [...fr.c] }; return true; }
      if (SELF) { SELF = null; redraw(); }
      return false;
    },
    handleDragEvent(e) {
      if (!drag || !SELF) return;
      const m = toMsk(e.coordinate);
      if (drag.mode === "move") SELF.c = [drag.c0[0] + m[0] - drag.m0[0], drag.c0[1] + m[1] - drag.m0[1]];
      else Object.assign(SELF, fromCorners(drag.a, m, SELF));
      redraw();
    },
    handleUpEvent(e) {
      const d = drag; drag = null; if (!d) return false;
      if (d.mode !== "move" && SELF) Object.assign(SELF, fromCorners(d.a, toMsk(e.coordinate), SELF));   // последний отрезок пути мыши
      if (d.mode === "new") {
        stopDraw();
        if (Math.hypot(e.pixel[0] - d.px[0], e.pixel[1] - d.px[1]) < 6) {      // щелчок: лист на 60 % экрана, по центру щелчка
          const ex = sharedView.calculateExtent(mMain.getSize()), a = toMsk([ex[0], ex[1]]), b = toMsk([ex[2], ex[3]]), [pw, ph] = paperMM(SELF);
          SELF.scale = Math.min((b[0] - a[0]) / pw, (b[1] - a[1]) / ph) * 1000 * .6; SELF.c = d.a;
        }
        toast(`Лист ${ALBUM.frames.length}: ${PT[SELF.paper]}, 1:${fmt(Math.round(SELF.scale))}. Тяните внутри — сдвиг, за угол — размер; над листом — формат, масштаб и выгрузка.`);
      }
      changed(); return false;
    },
  });
  // лист — сразу под перехватом команд черчения (cad.js держит его последним): щелчок по рамке доходит до листа раньше
  // выбора и сдвига карты, а идущая команда черчения — раньше листа
  const place = () => { const c = mMain.getInteractions(), arr = c.getArray(); c.remove(it); const top = arr.findIndex(i => i.get("gradoTop")); c.insertAt(top < 0 ? arr.length : top, it); };
  place();
  mMain.getInteractions().on("add", ev => { if (ev.element !== it && !ev.element.get("gradoTop")) place(); });

  document.addEventListener("keydown", e => {
    if (e.target.closest?.("input,textarea,select,[contenteditable]")) return;
    if (e.key === "Escape" && drawing) { if (drag?.mode === "new") ALBUM.frames.splice(ALBUM.frames.indexOf(SELF), 1); drag = null; stopDraw(); SELF = null; redraw(); }
    else if (e.key === "Escape" && SELF) { SELF = null; redraw(); }
    else if ((e.key === "Delete" || e.key === "Backspace") && SELF && !SEL.length) { e.preventDefault(); e.stopImmediatePropagation(); remove(SELF); }
  }, true);
  $("bFrame").onclick = () => drawing ? stopDraw() : window.startFrame();
  redraw();
})();
