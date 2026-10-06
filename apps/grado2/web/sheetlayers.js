/* ГРАДО 2 · окно «Слои и листы» (T86b, 06.10.2026; слово владельца: «единая логика для всех листов, группировка слоёв по листам
   и перетаскивание, всё красиво и интуитивно понятно», макет — docs/team/mockups/2026-10-06-sheet-layers.png, вариант А).
   Три колонки: листы альбома → роли выбранного листа (глаз, источник, покрытие рамки, состояние) → слои проекта по ролям с
   номерами листов. Пока без перетаскивания (T86c). Строки, покрытие и номера листов считает sheetlayout.js (чистые функции,
   tests/sheetlayout_test.js); здесь только страница. Глаз правит sheet.layout (item.on) через sheetlayout.setRole, запись идёт
   в отмену (layers.js, вид записи "layout") и в проект (touch). Скрипт стоит сразу после app.js: клавиши окна перехватываются
   раньше команд карты и дерева слоёв (те слушают window в фазе перехвата и забрали бы стрелки и Пробел). */
(function () {
  "use strict";
  const ID = "wSheetLayers", SL = () => window.SheetLayout;
  const el = () => document.getElementById(ID), bodyEl = () => document.getElementById("shlBody");
  const ST = { sel: -1, row: null, open: new Set(), bank: null, min: false };
  const CACHE = new Map(), PICK = new Map(), PENDING = new Set();
  const isOpen = () => !!el() && !el().hidden;
  const readOnly = () => document.body.classList.contains("hub-viewer") || window.Collab?.role === "viewer";
  const viewOf = sh => sh.view ? VIEWS.find(v => v.id === sh.view) : null;
  const viewKeys = sh => { const v = viewOf(sh); return v ? v.layers.filter(x => x.visible).map(x => x.key) : null; };
  const srcTitle = k => (typeof SOURCES !== "undefined" && SOURCES[k]?.title) || (typeof lyr === "function" && lyr(k)?.title) || k;
  const svg = d => `<svg class="shl-i" viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
  const I = {
    eye: svg('<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'),
    eyeoff: svg('<path d="M3 3l18 18M10.6 5.1A9.7 9.7 0 0 1 12 5c6 0 10 7 10 7a17 17 0 0 1-3 3.7M6.6 6.7A17 17 0 0 0 2 12s4 7 10 7a9.6 9.6 0 0 0 4-.9"/>'),
    lock: svg('<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>'),
    chev: svg('<path d="M9 6l6 6-6 6"/>'), chevd: svg('<path d="M6 9l6 6 6-6"/>'), min: svg('<path d="M5 12h14"/>'), x: svg('<path d="M6 6l12 12M18 6L6 18"/>'),
    list: svg('<path d="M3 5h4M3 12h4M3 19h4M11 5h10M11 12h10M11 19h10"/>'),
  };

  /* ---- что известно о слое в рамке листа (дёшево, из уже выгруженного; кэш по листу, ключу, рамке и версии данных) ---- */
  function frameOf(sh) {
    try { const g = frameGeom(sh), c = g.clone(); c.transform("EPSG:3857", "EPSG:4326"); return { ext: g.getExtent(), bb: c.getExtent() }; } catch { return null; }
  }
  const dsig = k => `${typeof DATA !== "undefined" ? (DATA[k]?.count ?? "-") + "/" + (DATA[k]?.bbox || "") : ""}`;
  const mapSheet = s => !(s.frozen || s.panels || s.kind === "title" || s.kind === "tep");
  // что выгружено по слою: область выгрузки из данных слоя (bbox пишется в проект с v0.99.15); у слоя из прежнего проекта области нет —
  // она восстанавливается так же, как её задаёт сборка альбома (sheets.js buildSection): объединение рамок листов, где слой нужен,
  // для Яндекса — вокруг территории и не больше 40 км². est — оценка. Слой, который не нужен ни одному листу, остаётся без области
  function requested(key, all) {
    const d = typeof DATA !== "undefined" ? DATA[key] : null; if (d?.bbox) return { bb: d.bbox, est: false };
    if (typeof DERIVED === "undefined" || !TERR) return null;
    let u = null; const add = b => { u = u ? [Math.min(u[0], b[0]), Math.min(u[1], b[1]), Math.max(u[2], b[2]), Math.max(u[3], b[3])] : b.slice(); };
    all.forEach(({ sh, fr }) => { if (fr && (sh.keys || []).flatMap(k => DERIVED[k] || [k]).includes(key)) add(fr.bb); });
    if (!u) return null;
    if (/^yandex\.(hd_roads|roads)$/.test(key)) { add(safe(() => turf.bbox(buf(TERR, 400))) || u); }
    if (key.startsWith("yandex.")) {
      const [w, s, e, n] = u, c = turf.centroid(TERR).geometry.coordinates, kx = 111.32 * Math.cos(c[1] * Math.PI / 180), ky = 110.54, a = (e - w) * kx * (n - s) * ky;
      if (a > 40 * .97) { const f = Math.sqrt(40 * .97 / a), hx = (e - w) * f / 2, hy = (n - s) * f / 2; u = [c[0] - hx, c[1] - hy, c[0] + hx, c[1] + hy]; }
    }
    return { bb: u, est: true };
  }
  function makeProbe(sh, fr, all, asig) {
    const sig = fr ? fr.ext.map(Math.round).join(",") : "";
    return key => {
      const id = `${sh.id}|${key}|${sig}|${dsig(key)}|${typeof ERRORS !== "undefined" && ERRORS[key] ? 1 : 0}|${DATA[key]?.bbox ? "" : asig}`;
      let r = CACHE.get(id); if (r) return r;
      const d = typeof DATA !== "undefined" ? DATA[key] : null, src = typeof layerSrc !== "undefined" ? layerSrc[key] : null;
      // выгружен: есть данные или слой, либо выгрузку делали и в области ничего не нашлось (CHECKED); пусто в рамке — ни одного объекта
      const loaded = !!d || (typeof lyr === "function" && !!lyr(key)) || (typeof CHECKED !== "undefined" && CHECKED.has(key));
      let empty = false; if (loaded && fr) { if (!src) empty = true; else { let any = false; try { src.forEachFeatureInExtent(fr.ext, () => (any = true)); } catch { any = true; } empty = !any; } }
      const rq = loaded && fr ? requested(key, all) : null;
      r = { loaded, empty, error: !!(typeof ERRORS !== "undefined" && ERRORS[key]), cover: rq ? SL().frameCover(fr.bb, rq.bb) : null, est: !!rq?.est };
      if (CACHE.size > 3000) CACHE.clear();
      CACHE.set(id, r); return r;
    };
  }
  // дороги: какой источник сборка берёт на самом деле (roadsrc.js, по площади полигонов в рамке) — считается после показа окна
  function pickFor(sh, fr) {
    if (!fr || typeof RoadSrc === "undefined") return null;
    const id = `${sh.id}|${fr.ext.map(Math.round).join(",")}|${dsig("yandex.hd_roads")}|${dsig("egko.roads")}|${sh.basemap || ""}`;
    if (PICK.has(id)) return PICK.get(id);
    if (!PENDING.has(id)) { PENDING.add(id);
      setTimeout(() => { PENDING.delete(id);
        const area = key => { let a = 0, src = layerSrc[key]; if (!src) return 0;
          src.forEachFeatureInExtent(fr.ext, f => { const t = f.getGeometry()?.getType(); if (!/Polygon/.test(t || "")) return;
            a += safe(() => { const c = turf.bboxClip({ type: "Feature", geometry: GJ.writeFeatureObject(f).geometry, properties: {} }, fr.bb); return c?.geometry?.coordinates?.length ? turf.area(c) : 0; }) || 0; }); return a; };
        const p = RoadSrc.pickRoadSource({ ya: area("yandex.hd_roads"), egko: area("egko.roads") }, { vector: sh.basemap !== "sat" });
        PICK.set(id, p === "egko" ? "egko.roads" : p === "yandex" ? "yandex.hd_roads" : ""); if (PICK.size > 200) PICK.clear();
        refresh(); }, 40); }
    return null;
  }

  /* ---- состав и выбор ---- */
  const sheets = () => (typeof ALBUM !== "undefined" ? ALBUM.sheets : []) || [];
  function selIndex() {
    const n = sheets().length; if (!n) return -1;
    if (ST.sel < 0 || ST.sel >= n) { const f = window.selectedFrame?.(), k = f ? sheets().indexOf(f) : -1; ST.sel = k >= 0 ? k : Math.max(0, sheets().findIndex(s => s.kind !== "title" && s.kind !== "tep" && !s.frozen)); }
    return ST.sel;
  }
  const infoOf = sh => SL().layoutFor(sh, viewOf);
  const plusN = (n, w) => SL().plural(n, w);

  /* ---- разметка ---- */
  function sheetsCol(idx, hl) {
    const list = sheets().map((sh, i) => {
      const info = infoOf(sh), why = typeof whyOf === "function" ? whyOf(sh) : "";
      const chip = sh.frozen ? `<span class="shl-chip" title="Готовый лист: слои не меняются">${I.lock}готов</span>` : why ? `<span class="shl-chip bad" title="${esc(why)}">не готов</span>` : "";
      return `<div class="shl-sh${i === idx ? " cur" : ""}${hl.has(i) ? " hl" : ""}${sh.frozen ? " frz" : ""}" role="option" aria-selected="${i === idx}" data-i="${i}" title="Щелчок — выбрать лист, двойной — открыть на холсте">`
        + `<span class="no">${i + 1}</span><span class="nm">${esc(sh.title || "Без названия")}</span><span class="st">${chip}</span>`
        + `<span class="mt${why ? " bad" : ""}">${esc(why || SL().sheetMeta(sh, info))}</span></div>`;
    }).join("");
    return `<section class="shl-col shl-c1" aria-label="Листы альбома"><div class="shl-ch">Листы альбома<span class="sp"></span><span class="n">${sheets().length}</span></div>`
      + `<div class="shl-list" role="listbox" aria-label="Листы альбома">${list || `<div class="shl-empty">В альбоме нет листов.</div>`}</div>`
      + `<div class="shl-keys"><kbd>↑</kbd><kbd>↓</kbd> лист · <kbd>Enter</kbd> открыть лист на холсте</div></section>`;
  }
  const covHtml = (cover, empty) => {
    if (cover === null || cover === undefined) return `<div class="cov n"><div class="tr"><i style="width:0"></i></div><span>—</span></div>`;
    const p = Math.round(cover * 100);
    return `<div class="cov${empty ? " n" : cover < .9 ? " w" : ""}"><div class="tr"><i style="width:${p}%"></i></div><span>${p} %</span></div>`;
  };
  const chipHtml = b => b ? `<span class="shl-chip ${b.tone === "none" ? "" : b.tone}" title="${esc(b.text)}">${esc(b.text)}</span>` : "";
  function rolesCol(idx) {
    const sh = sheets()[idx];
    if (!sh) return `<section class="shl-col shl-c2"><div class="shl-ch">Что на листе</div><div class="shl-list"><div class="shl-empty">Выберите лист слева.</div></div></section>`;
    const info = infoOf(sh), fr = frameOf(sh), all = sheets().map(x => ({ sh: x, fr: mapSheet(x) ? frameOf(x) : null })), asig = all.map(x => x.fr ? x.fr.ext.map(Math.round).join(",") : "").join(";"), probe = makeProbe(sh, fr, all, asig), ed = info.editable && !readOnly();
    const why = readOnly() ? "Только просмотр: слои листа меняет тот, кто правит проект" : info.why;
    let rows = "", note = "", sep = "";
    if (!info.layout) {
      rows = `<div class="shl-empty">${info.kind === "map" || !info.kind ? "Лист показывает текущую карту: состава слоёв у него нет." : info.kind === "frozen" ? "Готовый лист: вёрстка и слои зашиты в файл, здесь они не меняются." : info.kind === "panels" ? "Две карты на слайде: у каждой свой состав, здесь он пока не показан." : "У этого листа нет слоёв карты."}</div>`;
    } else {
      const R = SL().roleRows({ groups: info.layout.groups.slice().reverse() }, probe, { chosen: () => pickFor(sh, fr) || undefined });
      rows = R.map(r => {
        const open = ST.open.has(r.id) && r.queue;
        const eye = `<button class="shl-eye" tabindex="-1" data-eye="${esc(r.id)}" ${ed ? "" : "disabled"} aria-label="${r.on ? "Скрыть" : "Показать"} роль «${esc(r.title)}» на этом листе" title="${esc(ed ? (r.on ? "Скрыть роль на этом листе (Пробел)" : "Показать роль на этом листе (Пробел)") : why)}">${r.on ? I.eye : I.eyeoff}</button>`;
        const chev = r.queue ? `<button class="shl-chv" tabindex="-1" data-open="${esc(r.id)}" aria-label="Источники роли" aria-expanded="${!!open}" title="${open ? "Свернуть" : "Откуда брать: очередь источников"}">${open ? I.chevd : I.chev}</button>` : "";
        const lt = r.items.map(it => srcTitle(it.key)).join("; ");
        let h = `<div class="shl-rl${r.id === ST.row ? " cur" : ""}${r.on ? "" : " off"}" role="row" data-g="${esc(r.id)}" aria-selected="${r.id === ST.row}" title="${esc("Слои: " + lt)}">`
          + `${eye}<span class="cv">${chev}</span><span class="nm">${esc(r.title)}<small> ${r.count}</small></span><span class="srcn" title="${esc(r.source)}">${esc(r.source)}</span>${covHtml(r.empty ? null : r.cover, r.empty)}<span class="stt">${chipHtml(r.badge)}</span></div>`;
        if (open) {
          const q = SL().queueRows(r.queue.keys, probe, r.queue.chosen);
          h += `<div class="shl-chain"><div class="t">Откуда брать «${esc(r.title.toLowerCase())}». Первый источник главный, ниже — запасные. Автомат берёт первый, который закрывает рамку на 90 % и больше; порядок пока менять нельзя.</div>`
            + q.map(x => `<div class="ch2${x.used ? " use" : ""}"><span class="no">${x.n}</span><span class="t2" title="${esc(srcTitle(x.key))}">${esc(srcTitle(x.key))}</span>${covHtml(x.cover, false)}${x.used ? `<span class="shl-chip good">используется</span>` : chipHtml(x.badge)}</div>`).join("") + `</div>`;
        }
        return h;
      }).join("");
      const miss = SL().missingRoles(sheets().map(s => infoOf(s).layout), idx);
      sep = miss.length ? `<div class="shl-sep">Роли, которых на этом листе по образцу нет: ${esc(miss.join(", "))}</div>` : "";
      if (R.some(r => r.badge && /^окно 40/.test(r.badge.text))) note = `<div class="shl-note"><span class="shl-chip warn">Яндекс</span>Яндекс отдаёт данные только в окне 40 км² вокруг территории. Рамка листа шире окна: за его краем слоя Яндекса нет.${R.some(r => r.queue) ? " Откройте строку «Дороги»: запасной источник виден там." : ""}</div>`;
      if (info.layout.groups.some(g => g.items.some(it => probe(it.key).est))) note += `<div class="shl-note"><span class="shl-chip">оценка</span>Покрытие — оценка по рамкам листов; станет точным после новой выгрузки слоя.</div>`;
      if (!ed && why) note += `<div class="shl-note"><span class="shl-chip">глаз выключен</span>${esc(why)}.</div>`;
    }
    return `<section class="shl-col shl-c2" aria-label="Что на листе"><div class="shl-ch">Что на листе ${idx + 1}, сверху вниз<span class="sp"></span><span class="n">порядок задан образцом</span></div>`
      + `<div class="shl-hd"><span></span><span></span><span>Роль</span><span>Источник</span><span>Покрытие рамки</span><span>Состояние</span></div>`
      + `<div class="shl-list" role="grid" aria-label="Роли листа">${rows}${sep}${note}</div>`
      + `<div class="shl-keys"><kbd>Пробел</kbd> глаз роли · <kbd>Enter</kbd> / двойной щелчок: источники · <kbd>Esc</kbd> закрыть окно</div></section>`;
  }
  function bankCol(idx) {
    const L = typeof LYR !== "undefined" ? LYR : [], g = SL().bankGroups(L.map(l => ({ key: l.key, title: l.title })), sheets(), viewKeys);
    const cur = idx + 1;
    const rows = g.map(gr => `<div class="shl-bk">${esc(gr.title)} <small>${gr.items.length}</small></div>` + gr.items.map(it =>
      `<div class="shl-bl${it.key === ST.bank ? " sel" : ""}" role="option" aria-selected="${it.key === ST.bank}" data-k="${esc(it.key)}" title="Щелчок — подсветить листы со слоем, двойной — показать слой на холсте"><span class="nm">${esc(it.title)}</span>`
      + `<span class="ons num">${it.sheets.length ? it.sheets.map(n => n === cur ? `<b>${n}</b>` : n).join(" ") : `<i>нигде</i>`}</span></div>`).join("")).join("");
    return `<section class="shl-col shl-c3" aria-label="Слои проекта"><div class="shl-ch">Слои проекта<span class="sp"></span><span class="n">где используется</span></div>`
      + `<div class="shl-list" role="listbox" aria-label="Слои проекта">${rows || `<div class="shl-empty">В проекте пока нет слоёв.</div>`}</div>`
      + `<div class="shl-keys">Щелчок — подсветить листы · двойной — показать слой на холсте</div></section>`;
  }
  function hint(idx) {
    const sh = sheets()[idx];
    if (!sh) return "соберите или добавьте листы в окне «Листы и альбом».";
    if (ST.bank) { const it = (typeof lyr === "function" && lyr(ST.bank)), ns = SL().layerSheets(sheets(), ST.bank, viewKeys);
      return `слой «${it?.title || ST.bank}» ${ns.length ? "включён на " + (ns.length > 1 ? "листах " : "листе ") + ns.join(", ") : "ни на одном листе не включён"}. Двойной щелчок — показать его на холсте.`; }
    const info = infoOf(sh);
    if (readOnly()) return "режим просмотра: слои листа меняет тот, кто правит проект.";
    if (!info.editable && info.why) return info.why + ".";
    if (ST.row) { const r = info.layout?.groups.find(g => g.id === ST.row); return `глаз скрывает роль «${r?.title || ""}» только на этом листе (лист ${idx + 1}); на других листах она остаётся. Пробел — глаз, Cmd+Z — отмена.`; }
    return "глаз скрывает роль только на этом листе; выберите роль в средней колонке и нажмите Пробел.";
  }
  function render() {
    const b = bodyEl(); if (!b) return;
    const n = sheets().length, idx = selIndex(), keep = [...b.querySelectorAll(".shl-list")].map(x => x.scrollTop);
    const sh = sheets()[idx];
    let hl = new Set(); if (ST.bank) hl = new Set(SL().layerSheets(sheets(), ST.bank, viewKeys).map(x => x - 1));
    if (!n) { b.innerHTML = `<div class="shl-none"><div>В альбоме пока нет листов.<br>Соберите альбом ППТ КРТ или добавьте лист в окне «Листы и альбом».</div><button class="btn" data-sheets>Открыть «Листы и альбом»</button></div>`
      + `<div class="shl-foot"><b>Что дальше:</b> ${esc(hint(-1))}</div>`; return; }
    const info = infoOf(sh), why = typeof whyOf === "function" ? whyOf(sh) : "";
    const bar = `<div class="shl-bar"><span>Лист:</span><span class="shl-cur" title="${esc(sh.title || "")}">${idx + 1} · ${esc(sh.title || "Без названия")}</span>`
      + (sh.frozen ? `<span class="shl-chip">${I.lock}готовый лист</span>` : why ? `<span class="shl-chip bad" title="${esc(why)}">не готов</span>` : info.layout ? `<span class="shl-chip good">лист готов к печати</span>` : "")
      + `<span class="sp"></span><button class="btn" data-sheets title="Рамки, масштаб и выгрузка листов">Листы и альбом…</button></div>`;
    b.innerHTML = bar + `<div class="shl-grid">${sheetsCol(idx, hl)}${rolesCol(idx)}${bankCol(idx)}</div>`
      + `<div class="shl-foot"><b>Что дальше:</b> ${esc(hint(idx))}<span class="sp"></span><span class="r">правки состава хранятся в проекте</span></div>`;
    b.querySelectorAll(".shl-list").forEach((x, i) => { x.scrollTop = keep[i] || 0; });
    b.querySelector(".shl-sh.cur")?.scrollIntoView?.({ block: "nearest" });
    document.getElementById("shlTitle").textContent = `Слои и листы${typeof ALBUM !== "undefined" && ALBUM.meta?.short ? " · альбом " + ALBUM.meta.short : ""}`;
  }
  let raf = 0;
  const refresh = () => { if (!isOpen() || raf) return; raf = requestAnimationFrame(() => { raf = 0; if (isOpen()) render(); }); };

  /* ---- правка: глаз на роли ---- */
  function snap(id) { const s = sheets().find(x => x.id === id); return s ? JSON.stringify(s.layout ?? null) : null; }
  function changed(sh) {
    const i = sheets().indexOf(sh);
    if (typeof touch === "function") touch(); else window.markDirty?.();
    window.renderSheets?.();
    const img = document.getElementById("sheetPrev"); if (img && !img.hidden && +img.dataset.i === i) window.previewSheet?.(i);
    if (typeof LAY !== "undefined" && LAY && LAY.i === i && typeof renderLayout === "function") renderLayout();       // открытый макет листа перерисовывается сразу
    refresh();
  }
  function restore(id, s) {
    const sh = sheets().find(x => x.id === id); if (!sh) return;
    const l = s ? JSON.parse(s) : null; if (l) sh.layout = l; else delete sh.layout;
    changed(sh);
  }
  function toggleRole(idx, gid, on) {
    const sh = sheets()[idx]; if (!sh) return;
    if (readOnly()) return toast("Только просмотр: слои листа меняет тот, кто правит проект.");
    const info = infoOf(sh); if (!info.editable) return info.why && toast(info.why[0].toUpperCase() + info.why.slice(1) + ".");
    const g = info.layout.groups.find(x => x.id === gid); if (!g) return;
    const gs = info.layout.groups.filter(x => x.role === g.role), next = on ?? !gs.some(x => x.items.some(it => it.on !== false)), before = snap(sh.id);
    if (!SL().setRole(sh, gs.map(x => x.id), next, viewOf)) return;
    pushUndo({ kind: "layout", key: sh.id, label: `лист ${idx + 1}: роль «${g.title}» ${next ? "показана" : "скрыта"}`, snap: before });
    changed(sh);
    if (typeof setHint === "function") setHint(`Лист ${idx + 1}: роль «${g.title}» ${next ? "показана" : "скрыта"} только на этом листе. Cmd+Z — отмена.`);
  }
  function showLayer(key) {
    const l = typeof lyr === "function" && lyr(key); if (!l) return;
    if (!l.visible) { l.visible = true; const g = l.group && grp(l.group); if (g) g.visible = true; dataRev++; applyOrder(); }
    setCurrent(key);
    const ex = layerSrc[key]?.getExtent(); if (ex && isFinite(ex[0])) sharedView.fit(ex, { padding: [40, 40, 40, 40], maxZoom: 18 });
  }
  const hasQueue = (info, g) => info.layout.groups.some(x => x.role === g.role && x.items.some(it => Array.isArray(it.src) && it.src.length));
  const openSheet = i => { if (typeof openLayout === "function") openLayout(i); };

  /* ---- события ---- */
  function onClick(e) {
    const t = e.target;
    if (t.closest("[data-sheets]")) { winOpen("wSheets", true); return; }
    const eye = t.closest("[data-eye]"); if (eye) { ST.row = eye.dataset.eye; ST.bank = null; toggleRole(selIndex(), eye.dataset.eye); bodyEl().focus({ preventScroll: true }); return; }
    const op = t.closest("[data-open]"); if (op) { const id = op.dataset.open; ST.open.has(id) ? ST.open.delete(id) : ST.open.add(id); ST.row = id; render(); bodyEl().focus({ preventScroll: true }); return; }
    const sh = t.closest(".shl-sh"); if (sh) { ST.sel = +sh.dataset.i; ST.row = null; render(); bodyEl().focus({ preventScroll: true }); return; }
    const rl = t.closest(".shl-rl"); if (rl) { ST.row = rl.dataset.g; ST.bank = null; render(); bodyEl().focus({ preventScroll: true }); return; }
    const bl = t.closest(".shl-bl"); if (bl) { ST.bank = ST.bank === bl.dataset.k ? null : bl.dataset.k; render(); bodyEl().focus({ preventScroll: true }); return; }
  }
  function onDbl(e) {
    const sh = e.target.closest(".shl-sh"); if (sh) { openSheet(+sh.dataset.i); return; }
    const rl = e.target.closest(".shl-rl"); if (rl && !e.target.closest("button")) { const id = rl.dataset.g; const info = infoOf(sheets()[selIndex()]), g = info.layout?.groups.find(x => x.id === id);
      if (g && hasQueue(info, g)) { ST.open.has(id) ? ST.open.delete(id) : ST.open.add(id); render(); } return; }
    const bl = e.target.closest(".shl-bl"); if (bl) showLayer(bl.dataset.k);
  }
  // клавиши окна: перехват стоит раньше команд карты, поэтому берём только свои клавиши и только когда фокус внутри окна
  function onKey(e) {
    if (!isOpen() || !e.target.closest?.("#" + ID) || e.target.closest("input,select,textarea") || e.metaKey || e.ctrlKey) return;
    const take = () => { e.preventDefault(); e.stopImmediatePropagation(); };
    const n = sheets().length, idx = selIndex();
    if (e.key === "Escape") { take(); winOpen(ID, false); return; }
    if (e.target.closest("[data-sheets]") && (e.key === "Enter" || e.key === " ")) return;           // кнопка «Листы и альбом…» нажимается сама
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && n) { take(); ST.sel = Math.min(n - 1, Math.max(0, idx + (e.key === "ArrowDown" ? 1 : -1))); ST.row = null; render(); return; }
    if (e.key === " " && n) { take(); if (ST.row) toggleRole(idx, ST.row); else toast("Сначала выберите роль в средней колонке."); return; }
    if (e.key === "Enter" && n) { take(); const info = infoOf(sheets()[idx]), g = ST.row && info.layout?.groups.find(x => x.id === ST.row);
      if (g && hasQueue(info, g)) { ST.open.has(g.id) ? ST.open.delete(g.id) : ST.open.add(g.id); render(); } else openSheet(idx); }
  }

  /* ---- окно ---- */
  function setMin(on) { ST.min = on; el().classList.toggle("shmin", on); const b = document.getElementById("shlMin"); b.setAttribute("aria-pressed", on); b.title = on ? "Развернуть окно" : "Свернуть окно до заголовка"; b.innerHTML = on ? I.chevd : I.min; }
  function init() {
    const w = el(); if (!w || w.dataset.ready) return; w.dataset.ready = "1";
    const b = bodyEl(); b.addEventListener("click", onClick); b.addEventListener("dblclick", onDbl);
    document.getElementById("shlMin").onclick = () => { setMin(!ST.min); if (!ST.min) render(); };
    document.getElementById("shlMin").innerHTML = I.min;
    // «Листы и альбом» и дерево слоёв перерисовываются при любой правке листов и слоёв — окно следует за ними
    ["renderSheets", "renderTree"].forEach(fn => { const f = window[fn]; if (typeof f === "function" && !f.shl) { const g = function () { const r = f.apply(this, arguments); refresh(); return r; }; g.shl = 1; window[fn] = g; } });
  }
  addEventListener("keydown", onKey, true);
  WIN_OPEN[ID] = () => { init(); if (ST.min) setMin(false); render(); };
  window.SheetLayers = { snap, restore, render, refresh, toggleRole };
})();
