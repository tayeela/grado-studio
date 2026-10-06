/* ГРАДО 2 · окно «Слои и листы» (T86b, 06.10.2026; слово владельца: «единая логика для всех листов, группировка слоёв по листам
   и перетаскивание, всё красиво и интуитивно понятно», макет — docs/team/mockups/2026-10-06-sheet-layers.png, вариант А).
   Три колонки: листы альбома → роли выбранного листа (глаз, источник, покрытие рамки, состояние) → слои проекта по ролям с
   номерами листов. Перетаскивание (T86c, 06.10.2026): слой банка → лист или строка роли (включить), роль → другой лист (перенос, Alt — копия),
   источники дорог — за ручку ⋮⋮ и Alt+↑/↓; цель подсвечивается и пишет, что произойдёт; Esc отменяет. Правила допустимости — sheetlayout.js (чистые функции). Строки, покрытие и номера листов считает sheetlayout.js (чистые функции,
   tests/sheetlayout_test.js); здесь только страница. Глаз правит sheet.layout (item.on) через sheetlayout.setRole, запись идёт
   в отмену (layers.js, вид записи "layout") и в проект (touch). Скрипт стоит сразу после app.js: клавиши окна перехватываются
   раньше команд карты и дерева слоёв (те слушают window в фазе перехвата и забрали бы стрелки и Пробел). */
(function () {
  "use strict";
  const ID = "wSheetLayers", SL = () => window.SheetLayout;
  const el = () => document.getElementById(ID), bodyEl = () => document.getElementById("shlBody");
  const ST = { sel: -1, row: null, open: new Set(), bank: null, min: false, qsel: null, used: {}, flash: null, drag: null, pend: null, swallow: false, confirm: null };
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
    undo: svg('<path d="M9 14L4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>'),
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
      const rq = loaded && fr && !SL().isOwnKey(key) ? requested(key, all) : null;                // у своих слоёв области выгрузки нет: покрытие не считается
      r = { loaded, empty, error: !!(typeof ERRORS !== "undefined" && ERRORS[key]), cover: rq ? SL().frameCover(fr.bb, rq.bb) : null, est: !!rq?.est };
      if (CACHE.size > 3000) CACHE.clear();
      CACHE.set(id, r); return r;
    };
  }
  // дороги: какой источник сборка берёт на самом деле (roadsrc.js, по площади полигонов в рамке) — считается после показа окна
  function pickFor(sh, fr) {
    if (!fr || typeof RoadSrc === "undefined") return null;
    const order = SL().roadOrder(sh), id = `${sh.id}|${fr.ext.map(Math.round).join(",")}|${dsig("yandex.hd_roads")}|${dsig("egko.roads")}|${sh.basemap || ""}|${order ? order.join(">") : ""}`;
    if (PICK.has(id)) return PICK.get(id);
    if (!PENDING.has(id)) { PENDING.add(id);
      setTimeout(() => { PENDING.delete(id);
        const area = key => { let a = 0, src = layerSrc[key]; if (!src) return 0;
          src.forEachFeatureInExtent(fr.ext, f => { const t = f.getGeometry()?.getType(); if (!/Polygon/.test(t || "")) return;
            a += safe(() => { const c = turf.bboxClip({ type: "Feature", geometry: GJ.writeFeatureObject(f).geometry, properties: {} }, fr.bb); return c?.geometry?.coordinates?.length ? turf.area(c) : 0; }) || 0; }); return a; };
        const areas = { ya: area("yandex.hd_roads"), egko: area("egko.roads") };
        const p = order ? SL().pickByOrder(order, areas) : RoadSrc.pickRoadSource(areas, { vector: sh.basemap !== "sat" });     // порядок владельца главнее правила roadsrc.js (как в albums.js)
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
  // образец листа (начальный layout шаблона) и ручные правки относительно него (T86d); кэш живёт одну отрисовку
  let SEED = new Map();
  const tplLayoutOf = sh => { if (!SEED.has(sh.id)) SEED.set(sh.id, (() => { try { const f = typeof tplMake === "function" ? tplMake(sh) : null; return f ? (f.layout || SL().seedLayout(f)) : null; } catch { return null; } })()); return SEED.get(sh.id); };
  const baseOf = sh => SL().baselineOf(sh, tplLayoutOf(sh));
  const handOf = (sh, info = infoOf(sh)) => info.stored && info.editable ? SL().diffFromSeed(info.layout, baseOf(sh)) : { changed: false, roles: {}, lost: [] };
  const plusN = (n, w) => SL().plural(n, w);

  /* ---- разметка ---- */
  function sheetsCol(idx, hl) {
    const list = sheets().map((sh, i) => {
      const info = infoOf(sh), why = typeof whyOf === "function" ? whyOf(sh) : "";
      const chip = sh.frozen ? `<span class="shl-chip" title="Готовый лист: слои не меняются">${I.lock}готов</span>` : why ? `<span class="shl-chip bad" title="${esc(why)}">не готов</span>` : "";
      const hd = handOf(sh, info), dot = hd.changed ? `<span class="shl-dot" title="${esc("Есть ручные правки: " + [...Object.keys(hd.roles).map(r => SL().roleTitle(r)), ...hd.lost.map(r => "нет роли «" + SL().roleTitle(r) + "»")].join(", ") + ". Образец — шаблон листа")}"></span>` : "";
      return `<div class="shl-sh${i === idx ? " cur" : ""}${hl.has(i) ? " hl" : ""}${sh.frozen ? " frz" : ""}" role="option" aria-selected="${i === idx}" data-i="${i}" title="Щелчок — выбрать лист, двойной — открыть на холсте">`
        + `<span class="no">${i + 1}</span><span class="nm">${esc(sh.title || "Без названия")}</span><span class="st">${dot}${chip}</span>`
        + `<span class="mt${why ? " bad" : ""}">${esc(why || SL().sheetMeta(sh, info))}</span></div>`;
    }).join("");
    return `<section class="shl-col shl-c1" aria-label="Листы альбома"><div class="shl-ch">Листы альбома<span class="sp"></span><span class="n">${sheets().length}</span></div>`
      + `<div class="shl-list" role="listbox" aria-label="Листы альбома">${list || `<div class="shl-empty">В альбоме нет листов.</div>`}</div>`
      + `<div class="shl-keys"><kbd>↑</kbd><kbd>↓</kbd> лист · <kbd>Enter</kbd> открыть лист на холсте · перетащите слой или роль на лист</div></section>`;
  }
  const covHtml = (cover, empty) => {
    if (cover === null || cover === undefined) return `<div class="cov n"><div class="tr"><i style="width:0"></i></div><span>—</span></div>`;
    const p = Math.round(cover * 100);
    return `<div class="cov${empty ? " n" : cover < .9 ? " w" : ""}"><div class="tr"><i style="width:${p}%"></i></div><span>${p} %</span></div>`;
  };
  const chipHtml = b => b ? `<span class="shl-chip ${b.tone === "none" ? "" : b.tone}" title="${esc(b.text)}">${esc(b.text)}</span>` : "";
  const keyTitle = k => srcTitle(k);
  const handNote = d => { const t = SL().diffNote(d, keyTitle); return t ? t[0].toUpperCase() + t.slice(1) : t; };
  // синяя метка «изменено вручную»: щелчок по ней возвращает роль к образцу (то же, что клавиша R и ссылка под раскрытой строкой)
  const handChip = (r, d, ed) => d ? `<button class="shl-chip hand" tabindex="-1" data-reset="${esc(r.id)}" ${ed ? "" : "disabled"} title="${esc(handNote(d) + (ed ? ". Щелчок или R — вернуть автоматический выбор" : ""))}">${I.undo}изменено вручную</button>` : "";
  function rolesCol(idx) {
    const sh = sheets()[idx];
    if (!sh) return `<section class="shl-col shl-c2"><div class="shl-ch">Что на листе</div><div class="shl-list"><div class="shl-empty">Выберите лист слева.</div></div></section>`;
    const info = infoOf(sh), hand = handOf(sh, info), fr = frameOf(sh), all = sheets().map(x => ({ sh: x, fr: mapSheet(x) ? frameOf(x) : null })), asig = all.map(x => x.fr ? x.fr.ext.map(Math.round).join(",") : "").join(";"), probe = makeProbe(sh, fr, all, asig), ed = info.editable && !readOnly();
    const why = readOnly() ? "Только просмотр: слои листа меняет тот, кто правит проект" : info.why;
    let rows = "", note = "", sep = "";
    if (!info.layout) {
      rows = `<div class="shl-empty">${info.kind === "map" || !info.kind ? "Лист показывает текущую карту: состава слоёв у него нет." : info.kind === "frozen" ? "Готовый лист: вёрстка и слои зашиты в файл, здесь они не меняются. Кнопка «Скопировать как рабочий» (или Alt при отпускании слоя на лист) делает рабочую копию: она встаёт следом и меняется как обычный лист." : info.kind === "panels" ? "Две карты на слайде: у каждой свой состав, здесь он пока не показан." : "У этого листа нет слоёв карты."}</div>`;
    } else {
      const R = SL().roleRows({ groups: info.layout.groups.slice().reverse() }, probe, { chosen: () => pickFor(sh, fr) || undefined });
      rows = R.map(r => {
        const open = ST.open.has(r.id) && r.queue;
        const eye = `<button class="shl-eye" tabindex="-1" data-eye="${esc(r.id)}" ${ed ? "" : "disabled"} aria-label="${r.on ? "Скрыть" : "Показать"} роль «${esc(r.title)}» на этом листе" title="${esc(ed ? (r.on ? "Скрыть роль на этом листе (Пробел)" : "Показать роль на этом листе (Пробел)") : why)}">${r.on ? I.eye : I.eyeoff}</button>`;
        const chev = r.queue ? `<button class="shl-chv" tabindex="-1" data-open="${esc(r.id)}" aria-label="Источники роли" aria-expanded="${!!open}" title="${open ? "Свернуть" : "Откуда брать: очередь источников"}">${open ? I.chevd : I.chev}</button>` : "";
        const lt = r.items.map(it => srcTitle(it.key)).join("; ");
        let h = `<div class="shl-rl${r.id === ST.row ? " cur" : ""}${r.on ? "" : " off"}" role="row" data-g="${esc(r.id)}" data-role="${esc(r.role)}" data-title="${esc(r.title)}" aria-selected="${r.id === ST.row}" title="${esc("Слои: " + lt + ". Перетащите роль на другой лист: перенос, с Alt — копия")}">`
          + `${eye}<span class="cv">${chev}</span><span class="nm">${esc(r.title)}<small> ${r.count}</small></span><span class="srcn" title="${esc(r.source)}">${esc(r.source)}</span>${covHtml(r.empty ? null : r.cover, r.empty)}<span class="stt">${handChip(r, hand.roles[r.role], ed)}${chipHtml(r.badge)}</span></div>`;
        if (open) {
          const q = SL().queueRows(r.queue.keys, probe, r.queue.chosen), many = q.length > 1;
          h += `<div class="shl-chain" data-g="${esc(r.id)}"><div class="t">Откуда брать «${esc(r.title.toLowerCase())}». Первый источник главный, ниже — запасные. Автомат берёт первый, который закрывает рамку на 90 % и больше. ${many ? "Порядок меняется перетаскиванием за ручку ⋮⋮ или Alt+↑ / Alt+↓." : "На этом листе источник один."}</div>`
            + (hand.roles[r.role] ? `<div class="t shl-hand-t">${esc(handNote(hand.roles[r.role]))}. ${ed ? `<a href="#" data-reset="${esc(r.id)}">Вернуть автоматический выбор</a> <span class="k">(клавиша R)</span>` : ""}</div>` : "") + q.map(x => `<div class="ch2${x.used ? " use" : ""}${many && x.key === ST.qsel ? " qsel" : ""}" data-key="${esc(x.key)}" data-n="${x.n - 1}"><span class="grip${many && ed ? "" : " off"}" ${many && ed ? 'data-grip title="Перетащите, чтобы поменять порядок"' : ""}>⋮⋮</span><span class="no">${x.n}</span><span class="t2" title="${esc(srcTitle(x.key))}">${esc(srcTitle(x.key))}</span>${covHtml(x.cover, false)}${x.used ? `<span class="shl-chip good">используется</span>` : chipHtml(x.badge)}</div>`).join("") + `</div>`;
        }
        if (r.queue) ST.used[r.id] = r.queue.chosen;
        return h;
      }).join("");
      const miss = SL().missingRoles(sheets().map(s => infoOf(s).layout), idx);
      sep = miss.length ? `<div class="shl-sep">Роли, которых на этом листе по образцу нет: ${esc(miss.join(", "))}</div>` : "";
      if (R.some(r => r.badge && /^окно 40/.test(r.badge.text))) note = `<div class="shl-note"><span class="shl-chip warn">Яндекс</span>Яндекс отдаёт данные только в окне 40 км² вокруг территории. Рамка листа шире окна: за его краем слоя Яндекса нет.${R.some(r => r.queue) ? " Откройте строку «Дороги»: запасной источник виден там." : ""}</div>`;
      if (hand.lost.length) note += `<div class="shl-note"><span class="shl-chip hand">${I.undo}изменено вручную</span>С листа убраны роли: ${esc(hand.lost.map(r => "«" + SL().roleTitle(r) + "»").join(", "))}. ${ed ? `<a href="#" data-resetsheet>Вернуть весь лист к образцу</a>` : ""}</div>`;
      if (info.layout.groups.some(g => g.items.some(it => probe(it.key).est))) note += `<div class="shl-note"><span class="shl-chip">оценка</span>Покрытие — оценка по рамкам листов; станет точным после новой выгрузки слоя.</div>`;
      if (!ed && why) note += `<div class="shl-note"><span class="shl-chip">глаз выключен</span>${esc(why)}.</div>`;
    }
    return `<section class="shl-col shl-c2" aria-label="Что на листе"><div class="shl-ch">Что на листе ${idx + 1}, сверху вниз<span class="sp"></span><span class="n">порядок задан образцом</span></div>`
      + `<div class="shl-hd"><span></span><span></span><span>Роль</span><span>Источник</span><span>Покрытие рамки</span><span>Состояние</span></div>`
      + `<div class="shl-list" role="grid" aria-label="Роли листа">${rows}${sep}${note}</div>`
      + `<div class="shl-keys"><kbd>Пробел</kbd> глаз роли · <kbd>Enter</kbd> / двойной щелчок: источники · <kbd>Alt</kbd>+<kbd>↑</kbd><kbd>↓</kbd> источник выше или ниже · <kbd>R</kbd> вернуть авто · <kbd>Esc</kbd> закрыть окно</div></section>`;
  }
  function bankCol(idx) {
    const L = typeof LYR !== "undefined" ? LYR : [], g = SL().bankGroups(L.map(l => ({ key: l.key, title: l.title })), sheets(), viewKeys);
    const cur = idx + 1;
    const rows = g.map(gr => `<div class="shl-bk">${esc(gr.title)} <small>${gr.items.length}</small></div>` + gr.items.map(it =>
      `<div class="shl-bl${it.key === ST.bank ? " sel" : ""}" role="option" aria-selected="${it.key === ST.bank}" data-k="${esc(it.key)}" title="Щелчок — подсветить листы со слоем, двойной — показать слой на холсте. Перетащите на лист или на строку роли, чтобы включить слой на этом листе"><span class="nm">${esc(it.title)}</span>`
      + `<span class="ons num">${it.sheets.length ? it.sheets.map(n => n === cur ? `<b>${n}</b>` : n).join(" ") : `<i>нигде</i>`}</span></div>`).join("")).join("");
    return `<section class="shl-col shl-c3" aria-label="Слои проекта"><div class="shl-ch">Слои проекта<span class="sp"></span><span class="n">где используется</span></div>`
      + `<div class="shl-list" role="listbox" aria-label="Слои проекта">${rows || `<div class="shl-empty">В проекте пока нет слоёв.</div>`}</div>`
      + `<div class="shl-keys">Перетащите слой на лист или на роль — он включится там · щелчок — подсветить листы</div></section>`;
  }
  function hint(idx) {
    const sh = sheets()[idx];
    if (!sh) return "соберите или добавьте листы в окне «Листы и альбом».";
    if (ST.bank) { const it = (typeof lyr === "function" && lyr(ST.bank)), ns = SL().layerSheets(sheets(), ST.bank, viewKeys);
      return `слой «${it?.title || ST.bank}» ${ns.length ? "включён на " + (ns.length > 1 ? "листах " : "листе ") + ns.join(", ") : "ни на одном листе не включён"}. Двойной щелчок — показать его на холсте.`; }
    const info = infoOf(sh);
    if (readOnly()) return "режим просмотра: слои листа меняет тот, кто правит проект.";
    if (sh.frozen) return info.why + ". Кнопка «Скопировать как рабочий» сверху (или Alt при отпускании слоя на лист) делает рабочую копию, исходный лист не меняется.";
    if (!info.editable && info.why) return info.why + ".";
    if (ST.row) { const r = info.layout?.groups.find(g => g.id === ST.row); return `глаз скрывает роль «${r?.title || ""}» только на этом листе (лист ${idx + 1}); на других листах она остаётся. Пробел — глаз, Cmd+Z — отмена.${r && handOf(sh, info).roles[r.role] ? " R — вернуть роль к образцу." : ""} Перетащите роль на другой лист: перенос, с Alt — копия.`; }
    return "перетащите слой из правой колонки на лист или на строку роли — он включится на этом листе. Роль можно перетащить на другой лист (Alt — копия). Глаз скрывает роль только на этом листе.";
  }
  // верхняя строка: у готового листа — «Скопировать как рабочий»; у листа с ручными правками — «Вернуть весь лист к образцу» (с подтверждением)
  function handBar(sh, info) {
    if (readOnly()) return "";
    if (sh.frozen) return `<button class="btn" data-wcopy title="Рабочая копия встанет сразу после этого листа, с теми же слоями и без замка. Сам готовый лист не меняется">Скопировать как рабочий</button>`;
    const hd = handOf(sh, info); if (!hd.changed) { ST.confirm = null; return ""; }
    if (ST.confirm === sh.id) return `<span class="shl-ask">Вернуть весь лист к образцу? Ручные правки состава этого листа пропадут (Cmd+Z вернёт).</span><button class="btn primary" data-resetsheet-yes>Да, вернуть</button><button class="btn" data-resetsheet-no>Нет</button>`;
    return `<span class="shl-chip hand" title="Состав листа отличается от образца: ручные правки хранятся отдельно от автоматики">${I.undo}есть ручные правки</span><button class="btn" data-resetsheet title="Состав листа снова станет таким, как задаёт образец альбома">Вернуть весь лист к образцу</button>`;
  }
  function render() {
    const b = bodyEl(); if (!b) return; SEED = new Map();
    const n = sheets().length, idx = selIndex(), keep = [...b.querySelectorAll(".shl-list")].map(x => x.scrollTop);
    const sh = sheets()[idx];
    let hl = new Set(); if (ST.bank) hl = new Set(SL().layerSheets(sheets(), ST.bank, viewKeys).map(x => x - 1));
    if (!n) { b.innerHTML = `<div class="shl-none"><div>В альбоме пока нет листов.<br>Соберите альбом ППТ КРТ или добавьте лист в окне «Листы и альбом».</div><button class="btn" data-sheets>Открыть «Листы и альбом»</button></div>`
      + `<div class="shl-foot"><b>Что дальше:</b> ${esc(hint(-1))}</div>`; return; }
    const info = infoOf(sh), why = typeof whyOf === "function" ? whyOf(sh) : "";
    const bar = `<div class="shl-bar"><span>Лист:</span><span class="shl-cur" title="${esc(sh.title || "")}">${idx + 1} · ${esc(sh.title || "Без названия")}</span>`
      + (sh.frozen ? `<span class="shl-chip">${I.lock}готовый лист</span>` : why ? `<span class="shl-chip bad" title="${esc(why)}">не готов</span>` : info.layout ? `<span class="shl-chip good">лист готов к печати</span>` : "")
      + (handBar(sh, info))
      + `<span class="sp"></span><button class="btn" data-sheets title="Рамки, масштаб и выгрузка листов">Листы и альбом…</button></div>`;
    b.innerHTML = bar + `<div class="shl-grid">${sheetsCol(idx, hl)}${rolesCol(idx)}${bankCol(idx)}</div>`
      + `<div class="shl-foot"><b>Что дальше:</b> ${esc(hint(idx))}<span class="sp"></span><span class="r">правки состава хранятся в проекте</span></div>`;
    b.querySelectorAll(".shl-list").forEach((x, i) => { x.scrollTop = keep[i] || 0; });
    if (ST.flash) { const f = ST.flash; (f.sheet !== undefined ? b.querySelector(`.shl-sh[data-i="${f.sheet}"]`) : b.querySelector(`.shl-rl[data-g="${CSS.escape(f.row)}"]`))?.classList.add("fresh"); }
    b.querySelector(".shl-sh.cur")?.scrollIntoView?.({ block: "nearest" });
    document.getElementById("shlTitle").textContent = `Слои и листы${typeof ALBUM !== "undefined" && ALBUM.meta?.short ? " · альбом " + ALBUM.meta.short : ""}`;
  }
  let raf = 0;
  const refresh = () => { if (!isOpen() || raf || ST.drag) return; raf = requestAnimationFrame(() => { raf = 0; if (isOpen()) render(); }); };

  /* ---- правка: глаз на роли ---- */
  // слепок листа для отмены: состав и поля, что с ним согласованы (keys, styles, only). key — id листа или несколько через «|» (перенос между листами)
  const stateOf = s => JSON.stringify([s.layout ?? null, s.keys ?? null, s.styles ?? null, s.only ?? null]);
  // «+id» — лист целиком и его место в альбоме (рабочая копия: отмена убирает лист, возврат ставит его обратно); без плюса — только состав листа
  function snap(key) {
    return JSON.stringify(String(key).split("|").map(id => {
      if (id[0] === "+") { const k = sheets().findIndex(x => x.id === id.slice(1)); return [id, k < 0 ? null : JSON.stringify([k, sheets()[k]])]; }
      const s = sheets().find(x => x.id === id); return [id, s ? stateOf(s) : null]; }));
  }
  function changed(sh) {
    const i = sheets().indexOf(sh);
    if (typeof touch === "function") touch(); else window.markDirty?.();
    window.renderSheets?.();
    const img = document.getElementById("sheetPrev"); if (img && !img.hidden && +img.dataset.i === i) window.previewSheet?.(i);
    if (typeof LAY !== "undefined" && LAY && LAY.i === i && typeof renderLayout === "function") renderLayout();       // открытый макет листа перерисовывается сразу
    refresh();
  }
  function restore(key, snapStr) {
    let moved = false;
    JSON.parse(snapStr).forEach(([id, st]) => {
      if (id[0] === "+") {
        const k = sheets().findIndex(x => x.id === id.slice(1)); moved = true;
        if (st === null) { if (k >= 0) sheets().splice(k, 1); return; }
        const [at, obj] = JSON.parse(st); if (k >= 0) sheets()[k] = obj; else sheets().splice(Math.min(at, sheets().length), 0, obj); return;
      }
      const sh = sheets().find(x => x.id === id); if (!sh || !st) return;
      ["layout", "keys", "styles", "only"].forEach((f, j) => { const v = JSON.parse(st)[j]; if (v === null) delete sh[f]; else sh[f] = v; });
      changed(sh);
    });
    if (moved) {
      const n = sheets().length; ST.sel = Math.min(ST.sel, n - 1); try { if (typeof SHI !== "undefined" && SHI >= n) SHI = Math.max(0, n - 1); } catch { }
      if (typeof touch === "function") touch(); else window.markDirty?.();
      window.renderSheets?.(); refresh();
    }
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
  // «Вернуть автоматический выбор» (клавиша R, ссылка под строкой, синяя метка): роль листа снова как в образце; одна запись отмены
  function resetRoleUI(idx, gid) {
    const sh = sheets()[idx]; if (!sh) return;
    if (readOnly()) return toast("Только просмотр: слои листа меняет тот, кто правит проект.");
    const info = infoOf(sh); if (!info.editable) return info.why && toast(info.why[0].toUpperCase() + info.why.slice(1) + ".");
    const g = info.layout.groups.find(x => x.id === gid); if (!g) return;
    const base = info.stored ? baseOf(sh) : null, before = snap(sh.id), had = !!(base && SL().diffFromSeed(info.layout, base).roles[g.role]);
    if (!had || !SL().resetRole(sh, g.role, base, viewOf)) return toast(`Роль «${g.title}» уже как по образцу: ручных правок нет.`);
    const gone = !infoOf(sh).layout.groups.some(x => x.role === g.role);
    pushUndo({ kind: "layout", key: sh.id, label: `лист ${idx + 1}: роль «${g.title}» возвращена к образцу`, snap: before });
    ST.row = gone ? null : infoOf(sh).layout.groups.find(x => x.role === g.role).id; if (ST.row) flash({ row: ST.row });
    changed(sh); if (typeof setHint === "function") setHint(gone ? `Лист ${idx + 1}: роли «${g.title}» по образцу здесь нет, она убрана. Cmd+Z — отмена.` : `Лист ${idx + 1}: роль «${g.title}» снова как по образцу. Cmd+Z — отмена.`);
  }
  function resetSheetUI(idx) {
    const sh = sheets()[idx]; ST.confirm = null; if (!sh) return;
    if (readOnly()) return toast("Только просмотр: слои листа меняет тот, кто правит проект.");
    const info = infoOf(sh), base = info.editable && info.stored ? baseOf(sh) : null, before = snap(sh.id);
    if (!base || !SL().resetSheet(sh, base, viewOf)) { render(); return toast(`Лист ${idx + 1} уже как по образцу.`); }
    pushUndo({ kind: "layout", key: sh.id, label: `лист ${idx + 1}: состав возвращён к образцу`, snap: before });
    ST.row = null; changed(sh); if (typeof setHint === "function") setHint(`Лист ${idx + 1}: состав слоёв снова как по образцу. Cmd+Z — отмена.`);
  }
  function showLayer(key) {
    const l = typeof lyr === "function" && lyr(key); if (!l) return;
    if (!l.visible) { l.visible = true; const g = l.group && grp(l.group); if (g) g.visible = true; dataRev++; applyOrder(); }
    setCurrent(key);
    const ex = layerSrc[key]?.getExtent(); if (ex && isFinite(ex[0])) sharedView.fit(ex, { padding: [40, 40, 40, 40], maxZoom: 18 });
  }
  const hasQueue = (info, g) => info.layout.groups.some(x => x.role === g.role && x.items.some(it => Array.isArray(it.src) && it.src.length));

  /* ---- перетаскивание (T86c): указатель, а не HTML5 drag — призрак у курсора, подсветка цели, Esc и Alt работают одинаково ---- */
  const TPLC = new Map();                                        // образец листа (начальный layout шаблона) на время одного перетаскивания
  function ctxOf(sh) {
    if (!TPLC.has(sh.id)) TPLC.set(sh.id, (() => { try { return typeof tplMake === "function" ? tplMake(sh)?.layout || null : null; } catch { return null; } })());
    return { tpl: TPLC.get(sh.id), others: sheets().filter(x => x !== sh).map(x => infoOf(x).layout).filter(Boolean) };
  }
  const roleGroup = (info, role) => info.layout?.groups.find(g => g.role === role);
  const flash = f => { ST.flash = f; setTimeout(() => { if (ST.flash === f) ST.flash = null; }, 1600); };
  function dropLayer(i, key, title) {
    const sh = sheets()[i]; if (!sh) return; const before = snap(sh.id);
    const r = SL().addItem(sh, key, { ...ctxOf(sh), n: i + 1, viewOf, title }); if (!r.ok) return toast(r.text + ".");
    pushUndo({ kind: "layout", key: sh.id, label: `лист ${i + 1}: слой «${title}» включён`, snap: before });
    ST.sel = i; ST.bank = null; ST.row = roleGroup(infoOf(sh), SL().roleOf(key).role)?.id || null; if (ST.row) flash({ row: ST.row });
    changed(sh); if (typeof setHint === "function") setHint(`Лист ${i + 1}: слой «${title}» включён. Cmd+Z — отмена.`);
  }
  // рабочая копия листа с замком (Alt при отпускании или кнопка): новый лист сразу после исходного, с теми же слоями, без замка; исходный не меняется.
  // fill(copy) кладёт в копию то, что тянули; одна запись отмены на всё (копию и содержимое)
  function workingCopyOf(i, fill, label) {
    const src = sheets()[i]; if (!src) return null;
    if (readOnly()) { toast("Только просмотр: слои листа меняет тот, кто правит проект."); return null; }
    const had = new Set(sheets().map(x => x.id)), t = Date.now().toString(36); let id, k = 0; do { id = `wc_${t}${k++}`; } while (had.has(id));
    const cp = SL().workingCopy(src, { id, others: sheets().filter(x => x !== src).map(x => infoOf(x).layout).filter(Boolean), known: key => typeof lyr === "function" && !!lyr(key) });
    if (!cp) return null;
    const key = src.id + "|+" + cp.id, before = snap(key);
    sheets().splice(i + 1, 0, cp);
    const r = fill ? fill(cp, { tpl: null, others: sheets().filter(x => x !== cp).map(x => infoOf(x).layout).filter(Boolean), n: i + 2, viewOf }) : { ok: true };
    if (!r.ok) { sheets().splice(i + 1, 1); toast(r.text + "."); return null; }
    pushUndo({ kind: "layout", key, label: `рабочая копия листа ${i + 1}${label ? ": " + label : ""}`, snap: before });
    ST.sel = i + 1; ST.bank = null; ST.row = null; flash({ sheet: i + 1 }); changed(cp);
    if (typeof setHint === "function") setHint(`Лист ${i + 2}: рабочая копия листа ${i + 1}${label ? ", " + label : ""}. Исходный лист не менялся. Cmd+Z — отмена.`);
    return cp;
  }
  function dropWorking(d) {
    const i = d.tgt.i;
    if (d.type === "layer") return workingCopyOf(i, (cp, ctx) => SL().addItem(cp, d.key, { ...ctx, title: d.label }), `слой «${d.label}» добавлен`);
    const from = sheets()[d.from], rt = SL().roleTitle(d.role);
    return workingCopyOf(i, (cp, ctx) => SL().moveRole(from, cp, d.role, ctx, true), `роль «${rt}» скопирована с листа ${d.from + 1}`);
  }
  function dropRole(from, to, role, copy) {
    const a = sheets()[from], b = sheets()[to]; if (!a || !b) return; const rt = SL().roleTitle(role), before = snap(a.id + "|" + b.id);
    const r = SL().moveRole(a, b, role, { ...ctxOf(b), n: to + 1, viewOf }, copy); if (!r.ok) return toast(r.text + ".");
    pushUndo({ kind: "layout", key: a.id + "|" + b.id, label: `лист ${to + 1}: роль «${rt}» ${copy ? "скопирована" : "перенесена"} с листа ${from + 1}`, snap: before });
    if (!copy && ST.row && !infoOf(a).layout?.groups.some(x => x.id === ST.row)) ST.row = null;
    flash({ sheet: to }); if (!copy) changed(a); changed(b);
    if (typeof setHint === "function") setHint(`Роль «${rt}» ${copy ? "скопирована" : "перенесена"} на лист ${to + 1}. Cmd+Z — отмена.`);
  }
  function reorderQueue(i, gid, from, to, say) {
    const sh = sheets()[i], info = infoOf(sh), g = info.layout?.groups.find(x => x.id === gid); if (!g) return false;
    const q = SL().srcQueue(info.layout, g.role); if (!q) return false; const key = q.queue[from], before = snap(sh.id);
    if (!SL().reorderSrc(sh, g.role, from, to, viewOf)) return false;
    pushUndo({ kind: "layout", key: sh.id, label: `лист ${i + 1}: источник «${srcTitle(key)}» на место ${to + 1}`, snap: before });
    ST.qsel = key; ST.open.add(gid); changed(sh);
    if (typeof setHint === "function") setHint(`Лист ${i + 1}: «${srcTitle(key)}» ${to === 0 ? "теперь главный источник" : "на месте " + (to + 1)}. Cmd+Z — отмена.`);
    return true;
  }
  // Alt+↑ / Alt+↓: выбранный источник очереди выше или ниже (выбран — щелчком по строке; иначе тот, что используется)
  function nudgeSource(dir) {
    const i = selIndex(), sh = sheets()[i], info = infoOf(sh), g = ST.row && info.layout?.groups.find(x => x.id === ST.row);
    if (readOnly()) return toast("Только просмотр: слои листа меняет тот, кто правит проект.");
    if (!info.editable) return info.why && toast(info.why[0].toUpperCase() + info.why.slice(1) + ".");
    if (!g) return toast("Сначала выберите строку «Дороги» в средней колонке.");
    const q = SL().srcQueue(info.layout, g.role); if (!q) return toast(`У роли «${g.title}» одна очередь источников нет: Alt+↑ и Alt+↓ работают у дорог.`);
    if (q.queue.length < 2) return toast("На этом листе источник один: менять порядок не из чего.");
    const key = q.queue.includes(ST.qsel) ? ST.qsel : q.queue.includes(ST.used[g.id]) ? ST.used[g.id] : q.queue[0], from = q.queue.indexOf(key), to = from + dir;
    if (to < 0 || to >= q.queue.length) return toast(dir < 0 ? "Этот источник уже главный." : "Этот источник уже последний.");
    reorderQueue(i, g.id, from, to);
  }
  function onDown(e) {
    ST.swallow = false;
    if (e.button !== 0 || ST.drag || readOnly()) return;
    const t = e.target; if (t.closest("button,input,select,textarea,a")) return;
    let spec = null, grip = t.closest("[data-grip]");
    if (grip) { const ch = grip.closest(".ch2"), chain = grip.closest(".shl-chain"); spec = { type: "src", gid: chain.dataset.g, from: +ch.dataset.n, label: ch.querySelector(".t2").textContent }; }
    else if (t.closest(".shl-chain")) return;
    else if (t.closest(".shl-bl")) { const bl = t.closest(".shl-bl"); spec = { type: "layer", key: bl.dataset.k, label: bl.querySelector(".nm").textContent }; }
    else if (t.closest(".shl-rl")) { const rl = t.closest(".shl-rl"); spec = { type: "role", from: selIndex(), role: rl.dataset.role, label: rl.dataset.title }; }
    if (!spec) return;
    ST.pend = { spec, x: e.clientX, y: e.clientY };
    addEventListener("pointermove", onMove, true); addEventListener("pointerup", onUp, true); addEventListener("pointercancel", onCancel, true);
  }
  function stopListen() { removeEventListener("pointermove", onMove, true); removeEventListener("pointerup", onUp, true); removeEventListener("pointercancel", onCancel, true); }
  function beginDrag() {
    const g = document.createElement("div"); g.className = "shl-ghost"; g.innerHTML = `<span>${esc(ST.pend.spec.label)}</span>`; document.body.appendChild(g);
    ST.drag = { ...ST.pend.spec, ghost: g, x: ST.pend.x, y: ST.pend.y, alt: false, tgt: null, res: null }; TPLC.clear();
    document.body.classList.add("shl-dragging"); getSelection()?.removeAllRanges();
  }
  function clearMarks() { bodyEl()?.querySelectorAll(".drop,.ins-b,.ins-a").forEach(x => x.classList.remove("drop", "drop-ok", "drop-bad", "drop-frozen", "drop-none", "ins-b", "ins-a")); bodyEl()?.querySelectorAll(".shl-dcap").forEach(x => x.remove()); }
  function setFoot(text, tone) { const f = bodyEl()?.querySelector(".shl-foot"); if (!f) return; f.innerHTML = `<b>Перетаскивание:</b> <span class="dt ${tone || ""}">${esc(text)}</span><span class="sp"></span><span class="r">Esc — отмена</span>`; }
  function updateDrag() {
    const d = ST.drag; if (!d) return;
    d.ghost.style.transform = `translate(${d.x + 14}px,${d.y + 12}px)`; d.ghost.classList.toggle("cp", !!d.alt && d.type === "role");
    const el = document.elementFromPoint(d.x, d.y); clearMarks(); d.tgt = null; d.res = null;
    if (d.type === "src") {
      const chain = el?.closest(".shl-chain"); if (chain && chain.dataset.g === d.gid) {
        const rows = [...chain.querySelectorAll(".ch2")], slot = rows.filter(r => { const b = r.getBoundingClientRect(); return b.top + b.height / 2 < d.y; }).length, to = slot > d.from ? slot - 1 : slot;
        d.tgt = { to }; const ref = rows[slot] || rows[rows.length - 1]; ref.classList.add(rows[slot] ? "ins-b" : "ins-a");
        d.res = to === d.from ? { ok: false, tone: "none", text: "Источник остаётся на месте" } : { ok: true, tone: "ok", text: to === 0 ? `Отпустите: «${d.label}» станет главным источником` : `Отпустите: «${d.label}» встанет на место ${to + 1}` };
      }
    } else {
      const sh = el?.closest(".shl-sh"), rl = el?.closest(".shl-rl"), list = el?.closest(".shl-c2");
      const t = sh ? { i: +sh.dataset.i, el: sh } : rl ? { i: selIndex(), el: rl, row: rl.dataset.role } : list ? { i: selIndex(), el: list.querySelector(".shl-list") } : null;
      if (t) { d.tgt = t; d.res = SL().dropCheck(sheets(), t.i, d.type === "layer" ? { type: "layer", key: d.key, title: d.label } : { type: "role", from: d.from, role: d.role },
        { copy: d.alt, viewOf, ctx: ctxOf, row: d.type === "layer" ? t.row : undefined, titleOf: srcTitle }); }
    }
    if (d.res && d.tgt?.el) { const t = d.tgt.el; t.classList.add("drop", "drop-" + d.res.tone); if (d.res.text && d.res.tone !== "none") t.insertAdjacentHTML("beforeend", `<span class="shl-dcap ${d.res.tone}" title="${esc(d.res.text)}">${esc(d.res.text)}</span>`); }
    d.ghost.dataset.tone = d.res?.tone || "";
    setFoot(d.res?.text || (d.type === "src" ? "переставьте источник на новое место в очереди" : d.type === "layer" ? `«${d.label}»: отпустите на лист или на строку роли, чтобы включить слой на этом листе` : `роль «${d.label}»: отпустите на другой лист (Alt — копия)`), d.res?.tone);
  }
  function onMove(e) {
    const p = ST.pend; if (!p) return;
    if (!ST.drag) { if (Math.hypot(e.clientX - p.x, e.clientY - p.y) < 5) return; beginDrag(); }
    e.preventDefault(); ST.drag.x = e.clientX; ST.drag.y = e.clientY; ST.drag.alt = e.altKey; updateDrag();
  }
  function onUp(e) { if (ST.drag) { ST.drag.x = e.clientX; ST.drag.y = e.clientY; ST.drag.alt = e.altKey; updateDrag(); } endDrag(true); }
  function onCancel() { endDrag(false); }
  function endDrag(apply) {
    const d = ST.drag; stopListen(); ST.pend = null; ST.drag = null; if (!d) return;
    ST.swallow = true; setTimeout(() => { ST.swallow = false; }, 0);          // щелчок, которым кончается перетаскивание, строке не нужен
    d.ghost.remove(); document.body.classList.remove("shl-dragging"); clearMarks(); TPLC.clear();
    const res = d.res;
    if (apply && res?.ok) {
      if (res.workingCopy) dropWorking(d);
      else if (d.type === "layer") dropLayer(d.tgt.i, d.key, d.label);
      else if (d.type === "role") dropRole(d.from, d.tgt.i, d.role, d.alt);
      else reorderQueue(selIndex(), d.gid, d.from, d.tgt.to);
    } else if (apply && res && res.tone !== "none" && res.text) toast(res.text + ".");
    render();
  }
  const openSheet = i => { if (typeof openLayout === "function") openLayout(i); };

  /* ---- события ---- */
  function onClick(e) {
    const t = e.target;
    if (t.closest("[data-sheets]")) { winOpen("wSheets", true); return; }
    const rs = t.closest("[data-reset]"); if (rs) { e.preventDefault(); ST.row = rs.dataset.reset; ST.bank = null; resetRoleUI(selIndex(), rs.dataset.reset); bodyEl().focus({ preventScroll: true }); return; }
    if (t.closest("[data-resetsheet]")) { e.preventDefault(); ST.confirm = sheets()[selIndex()]?.id || null; render(); return; }
    if (t.closest("[data-resetsheet-yes]")) { resetSheetUI(selIndex()); return; }
    if (t.closest("[data-resetsheet-no]")) { ST.confirm = null; render(); return; }
    if (t.closest("[data-wcopy]")) { const i = selIndex(); workingCopyOf(i, null, ""); return; }
    const eye = t.closest("[data-eye]"); if (eye) { ST.row = eye.dataset.eye; ST.bank = null; toggleRole(selIndex(), eye.dataset.eye); bodyEl().focus({ preventScroll: true }); return; }
    const qr = t.closest(".ch2"); if (qr) { ST.qsel = qr.dataset.key; ST.row = qr.closest(".shl-chain").dataset.g; ST.bank = null; render(); bodyEl().focus({ preventScroll: true }); return; }
    const op = t.closest("[data-open]"); if (op) { const id = op.dataset.open; ST.open.has(id) ? ST.open.delete(id) : ST.open.add(id); ST.row = id; render(); bodyEl().focus({ preventScroll: true }); return; }
    const sh = t.closest(".shl-sh"); if (sh) { ST.sel = +sh.dataset.i; ST.row = null; ST.confirm = null; render(); bodyEl().focus({ preventScroll: true }); return; }
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
    if (ST.drag) { if (e.key === "Escape") { e.preventDefault(); e.stopImmediatePropagation(); endDrag(false); } else if (e.key === "Alt") { ST.drag.alt = true; updateDrag(); } return; }   // во время перетаскивания Esc отменяет его, а не закрывает окно
    if (!isOpen() || !e.target.closest?.("#" + ID) || e.target.closest("input,select,textarea") || e.metaKey || e.ctrlKey) return;
    const take = () => { e.preventDefault(); e.stopImmediatePropagation(); };
    const n = sheets().length, idx = selIndex();
    if (e.key === "Escape") { take(); winOpen(ID, false); return; }
    if (e.target.closest("[data-sheets]") && (e.key === "Enter" || e.key === " ")) return;           // кнопка «Листы и альбом…» нажимается сама
    if (e.altKey && (e.key === "ArrowDown" || e.key === "ArrowUp") && n) { take(); nudgeSource(e.key === "ArrowUp" ? -1 : 1); return; }
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && n) { take(); ST.sel = Math.min(n - 1, Math.max(0, idx + (e.key === "ArrowDown" ? 1 : -1))); ST.row = null; render(); return; }
    if (e.code === "KeyR" && !e.altKey && !e.shiftKey && n) { take(); if (ST.row) resetRoleUI(idx, ST.row); else toast("Сначала выберите роль в средней колонке: R возвращает её к образцу."); return; }
    if (e.key === " " && n) { take(); if (ST.row) toggleRole(idx, ST.row); else toast("Сначала выберите роль в средней колонке."); return; }
    if (e.key === "Enter" && n) { take(); const info = infoOf(sheets()[idx]), g = ST.row && info.layout?.groups.find(x => x.id === ST.row);
      if (g && hasQueue(info, g)) { ST.open.has(g.id) ? ST.open.delete(g.id) : ST.open.add(g.id); render(); } else openSheet(idx); }
  }

  /* ---- окно ---- */
  function setMin(on) { ST.min = on; el().classList.toggle("shmin", on); const b = document.getElementById("shlMin"); b.setAttribute("aria-pressed", on); b.title = on ? "Развернуть окно" : "Свернуть окно до заголовка"; b.innerHTML = on ? I.chevd : I.min; }
  function init() {
    const w = el(); if (!w || w.dataset.ready) return; w.dataset.ready = "1";
    const b = bodyEl(); b.addEventListener("click", e => { if (ST.swallow) { ST.swallow = false; e.stopImmediatePropagation(); e.preventDefault(); } }, true);
    b.addEventListener("pointerdown", onDown); b.addEventListener("click", onClick); b.addEventListener("dblclick", onDbl);
    document.getElementById("shlMin").onclick = () => { setMin(!ST.min); if (!ST.min) render(); };
    document.getElementById("shlMin").innerHTML = I.min;
    // «Листы и альбом» и дерево слоёв перерисовываются при любой правке листов и слоёв — окно следует за ними
    ["renderSheets", "renderTree"].forEach(fn => { const f = window[fn]; if (typeof f === "function" && !f.shl) { const g = function () { const r = f.apply(this, arguments); refresh(); return r; }; g.shl = 1; window[fn] = g; } });
  }
  addEventListener("keydown", onKey, true);
  addEventListener("keyup", e => { if (ST.drag && e.key === "Alt") { ST.drag.alt = false; updateDrag(); } }, true);
  WIN_OPEN[ID] = () => { init(); if (ST.min) setMin(false); render(); };
  window.SheetLayers = { snap, restore, render, refresh, toggleRole, resetRoleUI, resetSheetUI, workingCopyOf };
})();
