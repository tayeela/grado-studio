/* ГРАДО 2 · листы альбома на карте — как фреймы в Figma или видовые экраны в AutoCAD.
   Каждый лист-карта альбома (ALBUM.sheets) — рамка на карте: её размер = карта листа (frameMM) × масштаб. Инструмент
   «Лист»: тяните прямоугольник — пропорции формата держатся сами (по умолчанию А3 без штампа), масштаб считается из
   размера; появляется новый лист альбома. Выбранный лист: тянуть внутри — сдвиг (sheet.center), за угол — размер
   (sheet.scale), над листом панель: название, формат, ориентация, масштаб, «Загрузить сюда», «DXF ГИС ОГД», «Просмотр»,
   удалить. Листы раздела (строятся по территории) видны на карте, пока открыто окно «Листы»; обзорные схемы Москвы
   и округа, таблица ТЭП и титул рамки не имеют. Граница участка не нужна. */
(function () {
  const BLUE = "#1a5fb4", SEC = "#7a869a";
  const ROUND = [500, 1000, 2000, 2500, 5000, 10000, 25000];
  let SELF = null, drawing = false, drag = null;

  // лист на карте: карта-лист без обзорной подгонки; листы раздела — только при открытом окне «Листы» (или force)
  const sheetOnMap = (sh, force) => !["tep", "title", "photos"].includes(sh.kind) && !sh.panels && !["moscow", "district", "okrug"].includes(sh.fit)
    && (force || !(sh.fit || sh.keys) || !$("wSheets").hidden);
  window.sheetOnMap = sheetOnMap;
  const own = sh => !(sh.fit || sh.keys);
  const toMap = p => ol.proj.fromLonLat(MSK.toWgs(p));
  const toMsk = c => MSK.fromWgs(ol.proj.toLonLat(c));
  const sizeM = sh => frameMM(sh).map(v => v * sheetScale(sh) / 1000);
  const centerMsk = sh => MSK.fromWgs(sheetCenter(sh));
  const corners = sh => { const [w, h] = sizeM(sh), [cx, cy] = centerMsk(sh); return [[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]]; };
  const fmtT = sh => (SIZE_T[sh.size] || sh.size).replace(" без штампа", "") + (isPaper(sh.size) && sh.orient === "P" ? " книжн." : "");
  const label = sh => { const n = `Лист ${ALBUM.sheets.indexOf(sh) + 1}`; return `${n}${sh.title && sh.title !== n ? ` «${sh.title}»` : ""} · ${fmtT(sh)} · 1:${fmt(Math.round(sheetScale(sh)))}`; };
  window.sheetMsk = sh => ({ c: centerMsk(sh), wh: sizeM(sh) });

  const src = new ol.source.Vector();
  const grip = new ol.style.Style({ image: new ol.style.RegularShape({ points: 4, radius: 6, angle: Math.PI / 4, fill: new ol.style.Fill({ color: "#fff" }), stroke: new ol.style.Stroke({ color: BLUE, width: 2 }) }),
    geometry: f => new ol.geom.MultiPoint(f.getGeometry().getCoordinates()[0].slice(0, 4)) });
  const layer = new ol.layer.Vector({ source: src, zIndex: 130, style: f => {
    const sh = f.get("sh"), on = sh === SELF, col = own(sh) ? BLUE : SEC, tl = f.getGeometry().getCoordinates()[0][3];
    return [new ol.style.Style({ stroke: new ol.style.Stroke({ color: col, width: on ? 2.5 : 1.5, lineDash: own(sh) ? undefined : [8, 5] }),
        fill: new ol.style.Fill({ color: on ? "rgba(26,95,180,.05)" : "rgba(26,95,180,.001)" }) }),     // почти прозрачная заливка: щелчок внутри выбирает лист
      new ol.style.Style({ geometry: new ol.geom.Point(tl), text: new ol.style.Text({ text: f.get("label"), font: `${on ? 600 : 500} 12px system-ui, sans-serif`, textAlign: "left", textBaseline: "bottom", offsetY: -5,
        fill: new ol.style.Fill({ color: col }), stroke: new ol.style.Stroke({ color: "#fff", width: 3 }) }) }),
      ...(on ? [grip] : [])];
  } });
  mMain.addLayer(layer);

  const bar = document.createElement("div");
  bar.className = "framebar";
  const ov = new ol.Overlay({ element: bar, positioning: "bottom-left", offset: [0, -24], stopEvent: true });
  mMain.addOverlay(ov);

  // fromSheets — вызов из renderSheets: таблицу обратно не перерисовываем
  function redraw(fromSheets) {
    src.clear();
    ALBUM.sheets.forEach(sh => { if (!sheetOnMap(sh, sh === SELF)) return; const r = corners(sh).map(toMap), f = new ol.Feature(new ol.geom.Polygon([[...r, r[0]]])); f.set("sh", sh); f.set("label", label(sh)); src.addFeature(f); });
    if (!drag) placeBar();
    window.updateCover?.();
    if (fromSheets !== true && !drag && !$("wSheets").hidden) window.renderSheets?.();
  }
  window.redrawFrames = redraw;
  function placeBar() {
    if (!SELF || !ALBUM.sheets.includes(SELF)) { SELF = null; ov.setPosition(undefined); return; }
    ov.setPosition(toMap(corners(SELF)[3]));
    const sc = Math.round(sheetScale(SELF)), pap = isPaper(SELF.size);
    bar.innerHTML = `<input data-k="title" class="ti" value="${esc(SELF.title || "")}" aria-label="Название листа" title="Название листа — печатается на листе">`
      + `<select data-k="size" title="Формат листа: без штампа — карта на весь лист; ГОСТ — со штампом и легендой; слайды — для презентации">${Object.keys(SIZE_T).map(k => `<option value="${k}" ${k === SELF.size ? "selected" : ""}>${SIZE_T[k]}</option>`).join("")}</select>`
      + (pap ? `<button class="tb" data-a="orient" title="${SELF.orient === "P" ? "Книжная — сделать альбомной" : "Альбомная — сделать книжной"}"><i data-lucide="${SELF.orient === "P" ? "rectangle-vertical" : "rectangle-horizontal"}"></i></button>` : "")
      // типовые масштабы — обычный список, не datalist: подсказки datalist оставались висеть на карте, когда панель
      // перерисовывалась после ввода (25.09.2026, Яндекс Браузер)
      + `<label title="Масштаб листа: впишите число или тяните угол рамки">1:<input data-k="scale" value="${sc}" inputmode="numeric"></label>`
      + `<select data-k="scale" class="sc" aria-label="Типовой масштаб" title="Типовой масштаб"><option value="">▾</option>${ROUND.map(v => `<option value="${v}">1:${fmt(v)}</option>`).join("")}</select>`
      + `<span class="vs"></span><button class="btn" data-a="load" title="Выбрать, что загрузить на этот лист: окно «Исходные данные»"><i data-lucide="download"></i>Загрузить сюда</button>`
      + `<button class="btn primary" data-a="ogd" title="Все слои ГИС ОГД внутри листа — чертёж DXF в МСК: слой портала на своём слое, цвета как на портале, лист бумаги с видовым экраном 1:${fmt(sc)}"><i data-lucide="file-down"></i>DXF ГИС ОГД</button>`
      + `<button class="tb" data-a="prev" title="Просмотр листа (окно «Листы»)"><i data-lucide="eye"></i></button>`
      + `<button class="tb" data-a="del" title="Удалить лист (Del)"><i data-lucide="trash-2"></i></button>`;
    icons();
    // панель не уходит за края карты: сдвиг у правого края, под лист — если над листом нет места
    bar.style.setProperty("--fbw", Math.max(240, mMain.getTargetElement().clientWidth - 16) + "px");
    ov.setOffset([0, -24]); ov.setPositioning("bottom-left");
    requestAnimationFrame(() => {
      if (!SELF) return;
      const m = mMain.getTargetElement().getBoundingClientRect(), r = bar.getBoundingClientRect();
      if (!r.width) return;
      const dx = r.right > m.right - 8 ? Math.max(m.right - 8 - r.right, m.left + 8 - r.left) : r.left < m.left + 8 ? m.left + 8 - r.left : 0;
      if (r.top < m.top + 4) { ov.setPositioning("top-left"); ov.setPosition(toMap(corners(SELF)[0])); ov.setOffset([dx, 10]); }
      else ov.setOffset([dx, -24]);
    });
  }
  bar.addEventListener("change", e => {
    const k = e.target.dataset.k; if (!k || !SELF) return;
    if (k === "title") SELF.title = e.target.value;
    if (k === "size") { const w = sizeM(SELF)[0], c = sheetCenter(SELF); SELF.size = e.target.value; SELF.center = c; SELF.scale = w * 1000 / frameMM(SELF)[0]; }   // ширина на местности та же
    if (k === "scale") { const v = +String(e.target.value).replace(/\D/g, ""); if (v >= 100 && v <= 1e6) { SELF.center = sheetCenter(SELF); SELF.scale = v; } }
    changed();
  });
  bar.addEventListener("click", e => {
    const a = e.target.closest("[data-a]")?.dataset.a; if (!a || !SELF) return;
    if (a === "orient") { SELF.center = sheetCenter(SELF); SELF.scale = sheetScale(SELF); SELF.orient = SELF.orient === "P" ? "L" : "P"; changed(); }
    if (a === "del") remove(SELF);
    if (a === "load") loadHere(SELF);
    if (a === "ogd") window.exportOgd?.(SELF);
    if (a === "prev") { const i = ALBUM.sheets.indexOf(SELF); winOpen("wSheets", true); requestAnimationFrame(() => window.previewSheet?.(i)); }
  });
  bar.addEventListener("keydown", e => { if (e.key === "Enter") e.target.blur(); e.stopPropagation(); });

  function changed() { window.markDirty?.(); redraw(); }
  function remove(sh) {
    const i = ALBUM.sheets.indexOf(sh); if (i < 0) return;
    ALBUM.sheets.splice(i, 1); SELF = null; changed();
    toast(`Лист ${i + 1} «${sh.title}» удалён.`);
  }
  function loadHere(sh) {
    window.openSources({ fr: sh });              // окно «Исходные данные»: что загрузить на этот лист
  }
  window.selectedFrame = () => SELF;
  window.selectSheetFrame = (sh, fit) => {
    SELF = sh; redraw(true);
    if (sh && fit) { const ex = ol.extent.boundingExtent(corners(sh).map(toMap)); sharedView.fit(ex, { padding: [70, 40, 40, 40], duration: 250 }); }
  };
  window.startFrame = () => { drawing = true; SELF = null; redraw(true); window.clearTools?.(); mMain.getTargetElement().style.cursor = "crosshair";
    $("bFrame").setAttribute("aria-pressed", true);
    window.setHint?.("Лист: тяните прямоугольник по карте — пропорции формата держатся сами, масштаб считается из размера. Щелчок — лист на весь экран. Esc — отмена."); };
  const stopDraw = () => { drawing = false; mMain.getTargetElement().style.cursor = ""; $("bFrame").setAttribute("aria-pressed", false); window.syncStatus?.(); };

  // лист по двум углам: пропорции карты листа, масштаб — из размера
  function fromCorners(a, b, sh) {
    const [fw, fh] = frameMM(sh), dx = b[0] - a[0], dy = b[1] - a[1];
    const scale = Math.max(Math.abs(dx) / fw, Math.abs(dy) / fh, 1e-3) * 1000, w = fw * scale / 1000, h = fh * scale / 1000;
    return { scale, center: MSK.toWgs([a[0] + Math.sign(dx || 1) * w / 2, a[1] + Math.sign(dy || 1) * h / 2]) };
  }
  const hitSheet = px => mMain.forEachFeatureAtPixel(px, f => f.get("sh"), { layerFilter: l => l === layer, hitTolerance: 6 });
  const hitGrip = px => { if (!SELF) return -1; return corners(SELF).map(toMap).findIndex(c => { const p = mMain.getPixelFromCoordinate(c); return Math.hypot(p[0] - px[0], p[1] - px[1]) < 10; }); };

  const it = new ol.interaction.Pointer({
    handleDownEvent(e) {
      if (e.originalEvent.button) return false;
      const m = toMsk(e.coordinate);
      if (drawing) {
        const last = [...ALBUM.sheets].reverse().find(own) || {};
        const sh = { ...newSheet(), title: `Лист ${ALBUM.sheets.length + 1}`, size: isPaper(last.size) ? last.size : "BA3", orient: last.orient || "L", view: "", legend: false, tep: false, kind: "map", scale: 1, center: MSK.toWgs(m) };
        ALBUM.sheets.push(sh); SELF = sh; drag = { mode: "new", a: m, px: e.pixel }; return true;
      }
      if (window.CAD?.active?.()) return false;             // идёт команда черчения — лист не мешает
      const g = hitGrip(e.pixel);
      if (g >= 0) { drag = { mode: "size", a: corners(SELF)[(g + 2) % 4] }; return true; }
      const sh = hitSheet(e.pixel);
      // внутри листа лежат объекты чертежа: щелчок по объекту — выбор объекта, по пустому месту — выбор листа
      const other = sh && sh !== SELF && mMain.forEachFeatureAtPixel(e.pixel, () => true, { layerFilter: l => l !== layer && l.getZIndex() !== 105, hitTolerance: 3 });
      if (sh && !other) { if (sh !== SELF) { SELF = sh; redraw(true); } drag = { mode: "move", m0: m, c0: centerMsk(sh) }; return true; }
      if (SELF) { SELF = null; redraw(true); }
      return false;
    },
    handleDragEvent(e) {
      if (!drag || !SELF) return;
      const m = toMsk(e.coordinate);
      if (drag.mode === "move") SELF.center = MSK.toWgs([drag.c0[0] + m[0] - drag.m0[0], drag.c0[1] + m[1] - drag.m0[1]]);
      else Object.assign(SELF, fromCorners(drag.a, m, SELF));
      drag.moved = true; redraw(true);
    },
    handleUpEvent(e) {
      const d = drag; drag = null; if (!d) return false;
      if (d.mode !== "move" && SELF) Object.assign(SELF, fromCorners(d.a, toMsk(e.coordinate), SELF));   // последний отрезок пути мыши
      if (d.mode === "new") {
        stopDraw();
        if (Math.hypot(e.pixel[0] - d.px[0], e.pixel[1] - d.px[1]) < 6) {      // щелчок: лист на 60 % экрана, по центру щелчка
          const ex = sharedView.calculateExtent(mMain.getSize()), a = toMsk([ex[0], ex[1]]), b = toMsk([ex[2], ex[3]]), [fw, fh] = frameMM(SELF);
          SELF.scale = Math.min((b[0] - a[0]) / fw, (b[1] - a[1]) / fh) * 1000 * .6; SELF.center = MSK.toWgs(d.a);
        }
        toast(`${label(SELF)}. Тяните внутри — сдвиг, за угол — размер; над листом — формат, масштаб и выгрузка. Лист уже в альбоме (окно «Листы»).`);
      } else if (d.mode === "move" && !d.moved) { redraw(true); return false; }   // простой щелчок: только выбор
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
    if (e.key === "Escape" && drawing) { if (drag?.mode === "new") ALBUM.sheets.splice(ALBUM.sheets.indexOf(SELF), 1); drag = null; stopDraw(); SELF = null; redraw(); }
    else if (e.key === "Escape" && SELF) { SELF = null; redraw(true); }
    else if ((e.key === "Delete" || e.key === "Backspace") && SELF && !SEL.length) { e.preventDefault(); e.stopImmediatePropagation(); remove(SELF); }
  }, true);
  $("bFrame").onclick = () => drawing ? stopDraw() : window.startFrame();

  // листы v0.56 жили отдельно (ALBUM.frames, центр в МСК) — переносятся в альбом листами без штампа
  window.migrateFrames = () => {
    (ALBUM.frames || []).forEach((fr, i) => ALBUM.sheets.push({ ...newSheet(), id: fr.id || "f" + i, title: `Лист ${ALBUM.sheets.length + 1}`, size: "B" + (fr.paper || "A3"),
      orient: fr.orient || "L", scale: fr.scale, center: MSK.toWgs(fr.c), view: "", legend: false, tep: false, kind: "map" }));
    delete ALBUM.frames; redraw(true);
  };
  window.migrateFrames();
})();
