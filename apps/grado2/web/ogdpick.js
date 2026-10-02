/* ГРАДО 2 · окно «Исходные данные»: одно дерево всех источников — ЕГРН, подборки ГИС ОГД, все слои ГИС ОГД ровно
   в порядке портала, ЕГКО, OpenStreetMap, Яндекс, рельеф. Флажки на папках и слоях, поиск, число объектов каждого
   слоя ГИС ОГД в области (по кэшу на диске, портал не трогается). Отмеченное — выбор проекта (CHECKED; слои портала —
   ключами «ogd.<код>»). Две кнопки: «Загрузить в проект» — по листу или по покрытию всех листов, «ГИС ОГД в DXF» —
   чертёж отмеченных слоёв портала по листу (runOgd в app.js). */
(function () {
  let OGD = null;          // дерево каталога ГИС ОГД с сервера
  const dlg = document.createElement("dialog");
  dlg.className = "ogdpick";
  dlg.setAttribute("aria-label", "Исходные данные");
  document.body.appendChild(dlg);
  let st = null;          // {fr, bbox, counts, sel:Set, q, only, open:Map, where}

  const GROUPS = [["nspd", "ЕГРН · НСПД"], ["gisogd", "ГИС ОГД — подборки ГРАДО"], ["ogd", "ГИС ОГД — все слои портала"],
    ["egko", "ЕГКО — картооснова ГИС ОГД"], ["osm", "OpenStreetMap"], ["yandex", "Яндекс Карты (для анализа и эскиза, не для сдачи)"], ["terrain", "Рельеф"]];
  const isOgd = k => k.startsWith("ogd.");
  const ogdNode = n => n.code ? { key: "ogd." + n.code, num: n.num, name: n.name, path: n.path } : { num: "ogd:" + n.num, name: n.name, label: n.num, children: n.children.map(ogdNode) };
  function tree() {
    return GROUPS.map(([g, name]) => {
      const ch = g === "ogd" ? (OGD ? OGD.map(ogdNode) : [])
        : Object.entries(SOURCES).filter(([k, s]) => (s.kind === g || (g === "gisogd" && s.kind === "gisogd_admin")) && !isOgd(k)).map(([k, s]) => ({ key: k, name: s.title }));
      return { num: "g:" + g, name, children: ch, loading: g === "ogd" && !OGD };
    }).filter(n => n.children.length || n.loading);
  }
  let TREE = [];
  const leaves = n => n.key ? [n] : n.children.flatMap(leaves);
  const cnt = k => isOgd(k) && st.counts ? st.counts[k.slice(4)] : undefined;
  const shown = n => {
    if (n.key) return (!st.only || !isOgd(n.key) || !st.counts || cnt(n.key) !== 0 || st.sel.has(n.key))
      && (!st.q || n.name.toLowerCase().includes(st.q) || (n.path || "").toLowerCase().includes(st.q));
    return n.children.some(shown);
  };
  const badge = k => {
    if (!isOgd(k)) return DATA[k] ? `<span class="n has" title="Уже в проекте: объектов">${fmt(DATA[k].count)}</span>` : "";
    const v = cnt(k);
    return v === undefined ? `<span class="n">…</span>` : v === null ? `<span class="n" title="Слоя нет в кэше на диске — число объектов станет известно при выгрузке">?</span>` : v ? `<span class="n has">${fmt(v)}</span>` : `<span class="n">0</span>`;
  };

  function nodeHtml(n, depth) {
    if (!shown(n)) return n.loading && depth === 0 ? `<details open style="--d:0"><summary><span class="nm">${esc(n.name)}</span><span class="n">каталог портала…</span></summary></details>` : "";
    if (n.key) return `<label class="ly" style="--d:${depth}"><input type="checkbox" data-key="${esc(n.key)}" ${st.sel.has(n.key) ? "checked" : ""}><span class="nm">${n.num ? `<b>${esc(n.num)}</b> ` : ""}${esc(n.name)}</span>${badge(n.key)}</label>`;
    const ls = leaves(n).filter(shown), on = ls.filter(l => st.sel.has(l.key)).length;
    const open = st.q || (st.open.has(n.num) ? st.open.get(n.num) : (depth === 0 && n.num !== "g:ogd") || (on && depth < 3));
    const lbl = n.label && n.label !== "Т" && !/^\d/.test(n.name) ? `<b>${esc(n.label)}</b> ` : "";
    return `<details data-num="${esc(n.num)}" ${open ? "open" : ""} style="--d:${depth}"><summary><input type="checkbox" data-folder="${esc(n.num)}" ${on && on === ls.length ? "checked" : ""} ${on && on < ls.length ? "data-mixed" : ""} aria-label="Вся папка «${esc(n.name)}»">`
      + `<span class="nm">${lbl}${esc(n.name)}</span><span class="n" title="Отмечено из показанных слоёв папки">${on} из ${ls.length}</span></summary>`
      + n.children.map(c => nodeHtml(c, depth + 1)).join("") + `</details>`;
  }
  const findNum = (nodes, num) => { for (const n of nodes) { if (!n.key && n.num === num) return n; const f = !n.key && findNum(n.children, num); if (f) return f; } return null; };

  function render() {
    TREE = tree();
    const ogdAll = TREE.flatMap(leaves).filter(l => isOgd(l.key)), nObj = st.counts ? ogdAll.filter(l => cnt(l.key)).length : null;
    const nOgd = [...st.sel].filter(isOgd).length, body = dlg.querySelector(".tree"), keep = body ? body.scrollTop : 0;
    const fr = st.fr || window.ogdFrame?.();
    dlg.innerHTML = `<header><b>Исходные данные</b><span class="sub">${esc(st.where)}</span><span class="sp"></span><button class="tb" data-a="close" title="Закрыть (Esc)"><i data-lucide="x"></i></button></header>`
      + `<div class="bar"><input type="search" data-a="q" placeholder="Поиск слоя или папки" value="${esc(st.q)}" aria-label="Поиск слоя">`
      + `<label title="Скрыть слои ГИС ОГД, у которых в области нет объектов"><input type="checkbox" data-a="only" ${st.only ? "checked" : ""}>ГИС ОГД — только с объектами</label>`
      + `<span class="sp"></span><button class="btn" data-a="obj" ${st.counts ? "" : "disabled"} title="Отметить все слои ГИС ОГД, у которых в области есть объекты">ГИС ОГД с объектами${nObj != null ? ` (${nObj})` : ""}</button><button class="btn" data-a="none">Снять все</button></div>`
      + `<div class="tree">${TREE.map(n => nodeHtml(n, 0)).join("") || `<div class="note">Ничего не найдено.</div>`}</div>`
      + `<footer><span class="note">${st.counts ? "" : "Считаю объекты ГИС ОГД в области… "}Отмечено: <b>${st.sel.size}</b>${nOgd ? `, из них слоёв портала ГИС ОГД — ${nOgd}` : ""}. Большая область для НСПД и OpenStreetMap загружается по частям, части склеиваются.</span><span class="sp"></span>`
      + `<button class="btn" data-a="close">Отмена</button>`
      + `<button class="btn" data-a="dxf" ${nOgd && fr ? "" : "disabled"} title="${fr ? `Чертёж DXF отмеченных слоёв портала ГИС ОГД по листу «${esc(fr.title)}»: порядок и номера слоёв — как в ГИС ОГД` : "Для «ГИС ОГД в DXF» нужен лист на карте: инструмент «Лист»"}"><i data-lucide="file-down"></i>ГИС ОГД в DXF${nOgd ? ` (${nOgd})` : ""}</button>`
      + `<button class="btn primary" data-a="load" ${st.sel.size && st.bbox ? "" : "disabled"} title="Загрузить отмеченное в проект по области: ${esc(st.where)}"><i data-lucide="download"></i>Загрузить в проект</button></footer>`;
    dlg.querySelectorAll("[data-mixed]").forEach(c => { c.indeterminate = true; });
    dlg.querySelector(".tree").scrollTop = keep;
    icons();
  }

  function keep() {                     // выбор — выбор проекта: сохраняется с ним
    CHECKED.clear(); st.sel.forEach(k => CHECKED.add(k));
    ALBUM.meta.ogdCodes = [...st.sel].filter(isOgd).map(k => k.slice(4)); window.markDirty?.();
  }
  dlg.addEventListener("click", e => {
    const a = e.target.closest("[data-a]")?.dataset.a;
    if (a === "close") dlg.close();
    if (a === "none") { st.sel.clear(); render(); }
    if (a === "obj" && st.counts) { Object.keys(st.counts).filter(c => st.counts[c]).forEach(c => st.sel.add("ogd." + c)); render(); }
    if (a === "load") {
      keep();
      TREE.flatMap(leaves).filter(l => isOgd(l.key) && st.sel.has(l.key)).forEach(l => { SOURCES[l.key] ||= { title: `${l.name} (ОГД)`, kind: "gisogd" }; });
      const keys = [...st.sel], bb = st.bbox; dlg.close(); window.renderSources?.(); loadKeys(keys, bb);
    }
    if (a === "dxf") {
      keep();
      const fr = st.fr || window.ogdFrame?.(), codes = [...st.sel].filter(isOgd).map(k => k.slice(4)); dlg.close(); window.runOgd(fr, codes);
    }
  });
  // флажок папки: щелчок по нему не сворачивает папку (preventDefault), выбор — вручную: все показанные слои папки
  // отмечены — снять, иначе — отметить все показанные
  dlg.addEventListener("click", e => {
    const t = e.target; if (t.dataset?.folder == null) return;
    e.preventDefault(); e.stopPropagation();
    const f = findNum(TREE, t.dataset.folder); if (!f) return;
    const ls = leaves(f).filter(shown), all = ls.every(l => st.sel.has(l.key));
    ls.forEach(l => all ? st.sel.delete(l.key) : st.sel.add(l.key)); render();
  }, true);
  // раскрытые вами папки остаются раскрытыми при перерисовке
  dlg.addEventListener("toggle", e => { const d = e.target; if (d.tagName === "DETAILS") st.open.set(d.dataset.num, d.open); }, true);
  dlg.addEventListener("change", e => {
    const t = e.target;
    if (t.dataset.key) { t.checked ? st.sel.add(t.dataset.key) : st.sel.delete(t.dataset.key); render(); }
    else if (t.dataset.a === "only") { st.only = t.checked; render(); }
  });
  let qT = null;
  dlg.addEventListener("input", e => { if (e.target.dataset.a !== "q") return; clearTimeout(qT); qT = setTimeout(() => { st.q = e.target.value.trim().toLowerCase(); render(); const q = dlg.querySelector("[data-a=q]"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 200); });
  dlg.addEventListener("keydown", e => e.stopPropagation());               // клавиши окна не уходят в команды карты

  /* fr — лист: область загрузки и DXF — этот лист. Без листа — покрытие всех листов (как «Загрузить» в окне «Данные»),
     DXF — по выбранному или последнему листу на карте. dxf — окно открыто пунктом «ГИС ОГД в DXF» меню «Выгрузка»: в первый раз
     отмечаются слои портала с объектами на листе. */
  window.openSources = async ({ fr = null, dxf = false } = {}) => {
    const sel = new Set(CHECKED);
    (ALBUM.meta.ogdCodes || []).forEach(c => sel.add("ogd." + c));              // выбор окна «Слои ГИС ОГД в DXF» до v0.60
    const first = dxf && ![...sel].some(isOgd);
    const bbox = fr ? frameBox(fr) : coverBox(), sheet = fr ? ogdSheet(fr) : null;
    const where = fr ? `лист ${ALBUM.sheets.indexOf(fr) + 1} «${fr.title}», ${SIZE_T[fr.size] || fr.size}, 1:${fmt(sheet.scale)}`
      : bbox ? "покрытие всех листов (синий пунктир в окне «Данные»)" : "области нет: нарисуйте лист или границу территории";
    st = { fr, bbox, counts: null, sel, open: new Map(), q: "", only: true, where };
    render(); dlg.showModal();
    const my = st;
    try { if (!OGD) OGD = (await api("/api/ogd_all/tree")).tree; } catch (err) { toast("Каталог ГИС ОГД не получен: " + err.message); OGD = []; }
    if (st !== my) return; render();
    if (!bbox) { my.counts = {}; return render(); }
    try { my.counts = (await api("/api/ogd_all/scan", sheet ? { sheet } : { bbox })).counts; } catch { my.counts = {}; }
    if (st !== my) return;
    if (first) Object.keys(my.counts).filter(c => my.counts[c]).forEach(c => my.sel.add("ogd." + c));
    render();
  };
  window.openOgdPicker = fr => window.openSources({ fr, dxf: true });
})();
