/* ГРАДО 2 · движок альбома для окна «Листы и альбом» нового интерфейса (ui/src/albumhost.js, panels/AlbumPanel.vue).
   Новый интерфейс держит эту страницу скрытой (/old?embed=album в невидимом iframe) и зовёт её код сборки и печати:
   альбом собирается тем же buildSection / albumSpec / albumFile, что и прежде, поэтому PDF и PPTX выходят лист в лист.
   Здесь только мост: состояние (ход сборки, «не готов», строка альбома), вопросы «заменить или добавить» и «не всё
   готово» отдаются окну нового интерфейса, а не строкам этой страницы, которых владелец не видит. Проверка — tests/test_next_ui.py. */
(function () {
  "use strict";
  if (!window.EMBED) return;
  const say = t => window.EMBED_HOST?.gradoEmbed?.toast?.(String(t));
  { const toast0 = window.toast; window.toast = t => { toast0(t); say(t); }; }   // сообщения движка — в строку состояния нового интерфейса
  /* скрытая рамка: браузер не берёт имя файла у скачивания из неё («download») — файл PDF, PPTX, DXF скачивает новый интерфейс */
  if (window.parent !== window) {
    const blobs = new Map(), make0 = URL.createObjectURL, drop0 = URL.revokeObjectURL, click0 = HTMLAnchorElement.prototype.click;
    URL.createObjectURL = o => { const u = make0(o); if (o instanceof Blob) blobs.set(u, o); return u; };   // fetch(blob:) запрещён CSP — файл берётся отсюда
    URL.revokeObjectURL = u => { blobs.delete(u); drop0(u); };
    HTMLAnchorElement.prototype.click = function () {
      const host = window.EMBED_HOST?.gradoEmbed, b = blobs.get(this.href);
      if (!this.download || !b || !host?.download) return click0.call(this);
      host.download(b, this.download);
    };
  }
  const sheetAt = i => i == null ? null : ALBUM.sheets[i] || null;
  /* рамки листов для карты нового интерфейса (ui/src/albumframes.js), как frames.js: середина (долгота, широта), размер
     на местности (м), размер карты листа (мм) для правки угла, свой лист или лист раздела (пунктир), подпись рамки, полное название */
  const fmtT = s => (SIZE_T[s.size] || s.size).replace(" без штампа", "") + (isPaper(s.size) && s.orient === "P" ? " книжн." : "");
  function frames() {
    return ALBUM.sheets.map((s, i) => {
      if (!sheetOnMap(s, true)) return null;
      const c = sheetCenter(s), sc = sheetScale(s), mm = frameMM(s);
      if (!c || !(sc > 0)) return null;
      const n = `Лист ${i + 1}`, t = s.title && s.title !== n ? s.title : "";
      return { id: s.id, i, c, scale: sc, mm, wh: mm.map(v => v * sc / 1000), own: !(s.fit || s.keys),
        // на карте — короткое имя (#29: длинный заголовок закрывал фрагмент), полное — подсказкой над рамкой и в свойствах
        label: `${n} · ${fmtT(s)} · 1:${fmt(Math.round(sc))}`, title: t ? `${n}. ${t}` : n };
    }).filter(Boolean);
  }
  window.albumApi = {
    /* что показать в окне: строка альбома, ход сборки, причины «не готов» по листам, открытый вопрос «заменить или добавить» */
    state() {
      return {
        stat: albumStatText(), busy: SHBUILD > 0,
        bp: BP.on ? { text: BP.text, secs: Math.round((Date.now() - BP.t0) / 1000), canStop: BP.canStop, stop: BP.stop } : null,
        why: Object.fromEntries(ALBUM.sheets.map(s => [s.id, whyOf(s)]).filter(x => x[1])),
        ask: BUILDASK ? { name: BUILDASK.name, n: BUILDASK.n, have: ALBUM.sheets.length } : null,
        /* строка листа: формат и масштаб словами, как в прежнем окне; noScale — масштаб не выбирается (ТЭП, титул, фото, две карты, готовая вёрстка) */
        rows: Object.fromEntries(ALBUM.sheets.map(s => [s.id, { size: sizeShort(s), scale: scaleText(s), auto: !s.scale,
          noScale: !!(s.frozen || s.panels || ["tep", "title", "photos"].includes(s.kind)), frozen: !!s.frozen, tpl: !!(s.keys || s.panels) }])),
        sizes: SIZE_T, scales: SCALES, frames: frames(),
        /* файл с листами ждёт ответа «заменить или добавить» (или «большой файл — всё равно?»): вопрос задаёт окно */
        imp: IMPORT ? { name: IMPORT.name, n: IMPORT.album?.sheets.length || 0, have: ALBUM.sheets.length, big: !!IMPORT.file, mb: mb(IMPORT.size || 0) } : null,
        /* содержание своего листа (вид карты или таблица ТЭП), формат слайдов раздела, масштаб схем 5–9 — как строки прежнего окна */
        views: VIEWS.map(v => ({ id: v.id, name: v.name })), slides: Object.keys(SLIDE).map(k => [k, SIZE_T[k]]), slide: ALBUM.meta.slide || "P",
        scheme: schemeSetting(), schemeScales: SCALES.filter(v => v <= 10000),
      };
    },
    /* «Собрать»: альбом ППТ КРТ, ситуационный план, раздел 1. Поверх чужих листов движок спрашивает — ответ answer(mode). */
    build(kind) {
      if (isViewer()) return say("Только просмотр: сборка листов доступна тому, кто правит проект.");
      if (kind === "pptkrt") return track(() => window.buildAlbum("pptkrt"));
      if (kind === "sit") return buildSituation();
      if (kind === "sec1") return buildSection();
    },
    answer(mode) { return buildAnswer(mode); },
    /* «Добавить лист»: A3 или A1 по ГОСТ, слайд — как в прежнем окне (newSheet: текущий вид карты, масштаб авто) */
    add(size) {
      if (isViewer()) return say("Только просмотр: листы добавляет тот, кто правит проект.");
      const s = newSheet(); if (size) s.size = size; ALBUM.sheets.push(s); touch(); return ALBUM.sheets.length - 1;
    },
    /* «Обновить листы»: как tplManual, но вопрос о старых листах задаёт окно (legacy: true — пересобрать и их) */
    refresh(legacy) {
      if (isViewer()) return say("Только просмотр: листы обновляет тот, кто правит проект.");
      tplAdopt();
      const old = ALBUM.sheets.filter(s => s.tpl?.legacy && !s.frozen).length, frozen = ALBUM.sheets.filter(s => s.frozen).length;
      if (old && legacy == null) return { old };
      const r = tplRefresh({ legacy: !!legacy });
      if (!r.n) { say("В альбоме нет листов, собранных по шаблону (раздел, альбом ППТ КРТ, ситуационный план, таблица ТЭП)." + (frozen ? " Готовая вёрстка из файла не обновляется." : "")); return {}; }
      TPL_SIG = tplSig(); tplAfter(r, true);
      say(`Листы обновлены по новым показателям: ${r.n} ${shWord(r.n)} по шаблону` + (frozen ? `, ${frozen} из файла не тронуты` : "") + "."
        + (r.bad.length ? ` Не готовы: ${r.bad.map(s => `«${s.title}» — ${NOTREADY.get(s.id)}`).join("; ")}. Недостающие слои выгружает «Собрать».` : ""));
      return {};
    },
    stop() { if (BP.on && BP.canStop) { BP.stop = true; BP.stopAt = BP.cur; bpShow(); syncBusy(); } },
    /* что проверить до выгрузки: [{ text, sheet?, stamp? }]; пусто — можно выгружать */
    issues(kind, i) { return exportIssues(kind, sheetAt(i)); },
    /* PDF или PPTX: всего альбома (i не задан) или одного листа; вопрос «не всё готово» окно уже задало */
    file(kind, i) { return albumFile(kind, sheetAt(i), true); },
    /* картинка листа (SVG той же печати) — адрес blob: для <img> окна */
    async preview(i) {
      const s = sheetAt(i); if (!s) return null;
      const r = await fetch("/api/print/svg", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...albumSpec([s]), index: 0 }) });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.status);
      readFit(r, [s]);
      return URL.createObjectURL(await r.blob());
    },
    /* «Заполнить по слоям»: пустые № КРТ, округ и район, адрес — по загруженным слоям; что заполнено */
    fillMeta() { const d = autoMeta(); touch(); return d; },
    /* «Макет надписей» нового интерфейса (ui/src/panels/AlbumLayout.vue): запрос печати одного листа — тот же albumSpec, что у
       просмотра и макета этой страницы (layout.js); правки надписей окно подставляет само */
    spec(i) { const s = sheetAt(i); return s ? JSON.parse(JSON.stringify(albumSpec([s]))) : null; },
    /* «Слои листа»: роли листа i сверху вниз (глаз, источник, покрытие рамки, состояние) — как окно «Слои и листы» */
    roles(i) { return window.SheetLayers?.rows(i) || null; },
    /* глаз роли на листе i (только этот лист) и «вернуть к образцу» */
    role(i, gid) { window.SheetLayers?.toggleRole(i, gid); },
    resetRole(i, gid) { window.SheetLayers?.resetRoleUI(i, gid); },
    /* перетаскивание во вкладке: роль на другой лист (перенос, copy — копия), слой проекта на лист или строку роли; порядок источников */
    dropCheck(to, what, copy) { return window.SheetLayers?.check(to, what, copy) || null; },
    drop(to, what, copy) { return !!window.SheetLayers?.drop(to, what, copy); },
    bank() { return window.SheetLayers?.bank() || []; },
    reorderSrc(i, gid, from, to) { return !!window.SheetLayers?.reorder(i, gid, from, to); },
    /* фотофиксация (лист «Материалы фотофиксации»): снимки листа i для окна — имя, размер, есть ли точка съёмки (GPS), картинка */
    photos(i) {
      const s = sheetAt(i);
      return s?.kind === "photos" ? (s.photos || []).map((ph, k) => ({ k, name: ph.name || `Снимок ${k + 1}`, w: ph.w, h: ph.h, at: !!ph.at, src: "data:image/jpeg;base64," + ph.data })) : null;
    },
    /* добавить снимки (File из окна нового интерфейса): тот же addPhotoFiles — 1600 px, JPEG, точка из EXIF GPS, не больше 12 */
    addPhotos(i, files) {
      if (isViewer()) return say("Только просмотр: снимки добавляет тот, кто правит проект.");
      return addPhotoFiles(i, [...files]);
    },
    /* убрать снимок k (k не задан — все) */
    dropPhoto(i, k) {
      const s = sheetAt(i); if (!s?.photos || isViewer()) return;
      if (k == null) s.photos = []; else s.photos.splice(k, 1);
      touch();
    },
    /* спутник Яндекса по рамке листа — архив DXF + снимок в МСК для AutoCAD; dir — папка загрузок (полный путь), её спрашивает окно */
    sat(i, dir) {
      if (!sheetAt(i) || !dir) return;
      try { localStorage.setItem("grado2.dlDir", dir); } catch { }
      return satFile(i, false, dir);
    },
    /* «Содержание» своего листа: "" — текущая карта, id вида, "__tep" — таблица ТЭП (как строка «Содержание» прежнего окна) */
    setView(i, v) {
      const sh = sheetAt(i); if (!sh || isViewer() || sh.keys || sh.panels || sh.frozen) return;
      sh.kind = v === "__tep" ? "tep" : "map"; sh.view = sh.kind === "tep" ? "" : String(v || "");
      if (sh.kind === "tep") { sh.tpl = { set: "tep" }; if (!sh.title || sh.title === newSheet().title) sh.title = "Технико-экономические показатели"; }
      else if (sh.tpl?.set === "tep") delete sh.tpl;
      touch();
    },
    /* «Вернуть в центр»: лист снова по центру территории */
    resetCenter(i) { const sh = sheetAt(i); if (sh && !isViewer()) { delete sh.center; touch(); } },
    /* формат слайдов раздела: собранные слайды раздела переводятся сразу (масштаб — заново) */
    setSlide(v) {
      if (isViewer() || !SLIDE[v]) return;
      ALBUM.meta.slide = v; ALBUM.sheets.filter(x => String(x.id).startsWith("sec1_")).forEach(x => { x.size = v; x.scale = 0; }); touch();
    },
    /* масштаб схем 5–9 альбома ППТ КРТ: 0 — авто, "cover" — по границам выгрузки, число — 1:N; ответ — что сказать владельцу */
    setScheme(v) {
      if (isViewer()) return "";
      ALBUM.meta.schemeScale = v === "cover" ? "cover" : +v || undefined; touch();
      return v === "cover" ? "Масштаб схем — по границам выгрузки: рамка не меньше области загрузки данных, сит. плана и территории. Данные карты за прежней рамкой докачает «Собрать» → «Альбом ППТ КРТ»."
        : +v ? `Масштаб схем 1:${fmt(+v)}. Данные карты за прежней рамкой докачает «Собрать» → «Альбом ППТ КРТ».` : "Масштаб схем — авто, по размеру территории.";
    },
    /* «Собрать» → «Из файла…»: листы из проекта .grado2 или готовой вёрстки; вопрос «заменить или добавить» — state().imp и importAnswer */
    importFile(file) { return readAlbumFile(file); },
    importAnswer(mode) { return importAlbum(mode); },
    /* «ГИС ОГД в DXF»: лист для выгрузки — выбранный в окне (i), если он на карте, иначе последний лист на карте; запрос для /api/ogd_all/start */
    ogdSheet(i) {
      const fr = (sheetAt(i) && window.sheetOnMap?.(sheetAt(i))) ? sheetAt(i) : [...ALBUM.sheets].reverse().find(sh => window.sheetOnMap?.(sh));
      if (!fr) return null;
      const k = ALBUM.sheets.indexOf(fr), sheet = ogdSheet(fr), b = frameBox(fr);
      return { i: k, sheet, bbox: b, codes: ALBUM.meta.ogdCodes || [], boundary: TERR?.geometry || null,
        where: `листу ${k + 1} «${fr.title}» (${SIZE_T[fr.size] || fr.size}, 1:${fmt(sheet.scale)})`, name: `ОГД ${fr.title || `лист ${k + 1}`} 1-${sheet.scale}` };
    },
    /* выбор слоёв портала для DXF — в проект (как окно выбора прежней страницы) */
    keepOgd(codes) { if (!isViewer()) { ALBUM.meta.ogdCodes = [...codes]; touch(); } },
    dlDir() { try { return localStorage.getItem("grado2.dlDir") || ""; } catch { return ""; } },
    touch() { touch(); },
  };
})();
