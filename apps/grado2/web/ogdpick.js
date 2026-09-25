/* ГРАДО 2 · окно «Слои ГИС ОГД в DXF»: дерево папок и слоёв ровно в порядке портала, флажки на папках и слоях,
   число объектов каждого слоя на листе (считается по кэшу на диске, портал не трогается). По умолчанию отмечен
   прошлый выбор этого проекта (ALBUM.meta.ogdCodes), а без него — слои, у которых на листе есть объекты.
   «Выгрузить DXF» запускает выгрузку только отмеченных слоёв (runOgd в app.js). */
(function () {
  let TREE = null;
  const dlg = document.createElement("dialog");
  dlg.className = "ogdpick";
  dlg.setAttribute("aria-label", "Слои ГИС ОГД в DXF");
  document.body.appendChild(dlg);
  let st = null;          // {sheet, counts, sel:Set, q, only}

  const layers = n => n.code ? [n] : n.children.flatMap(layers);
  const cnt = c => st.counts ? st.counts[c] : undefined;
  const shown = n => {
    if (n.code) return (!st.only || !st.counts || cnt(n.code) !== 0 || st.sel.has(n.code)) && (!st.q || n.name.toLowerCase().includes(st.q) || (n.path || "").toLowerCase().includes(st.q));
    return n.children.some(shown);
  };
  const badge = c => { const v = cnt(c); return v === undefined ? `<span class="n">…</span>` : v === null ? `<span class="n" title="Слоя нет в кэше на диске — число объектов станет известно при выгрузке">?</span>` : v ? `<span class="n has">${fmt(v)}</span>` : `<span class="n">0</span>`; };

  function nodeHtml(n, depth) {
    if (!shown(n)) return "";
    if (n.code) return `<label class="ly" style="--d:${depth}"><input type="checkbox" data-code="${n.code}" ${st.sel.has(n.code) ? "checked" : ""}><span class="nm"><b>${esc(n.num)}</b> ${esc(n.name)}</span>${badge(n.code)}</label>`;
    const ls = layers(n).filter(shown), on = ls.filter(l => st.sel.has(l.code)).length, withObj = st.counts ? ls.filter(l => cnt(l.code)).length : null;   // по видимым слоям
    const open = st.q || (st.open.has(n.num) ? st.open.get(n.num) : depth === 0 || (on && depth < 3));
    return `<details data-num="${esc(n.num)}" ${open ? "open" : ""} style="--d:${depth}"><summary><input type="checkbox" data-folder="${esc(n.num)}" ${on && on === ls.length ? "checked" : ""} ${on && on < ls.length ? "data-mixed" : ""} aria-label="Вся папка «${esc(n.name)}»">`
      + `<span class="nm">${n.num && n.num !== "Т" && !/^\d/.test(n.name) ? `<b>${esc(n.num)}</b> ` : ""}${esc(n.name)}</span><span class="n" title="Отмечено из показанных слоёв папки">${on} из ${ls.length}</span></summary>`
      + n.children.map(c => nodeHtml(c, depth + 1)).join("") + `</details>`;
  }
  const findNum = (nodes, num) => { for (const n of nodes) { if (n.num === num && !n.code) return n; const f = findNum(n.children, num); if (f) return f; } return null; };

  function render() {
    const all = TREE ? TREE.flatMap(layers) : [], nObj = st.counts ? all.filter(l => cnt(l.code)).length : null;
    const body = dlg.querySelector(".tree");
    const keep = body ? body.scrollTop : 0;
    dlg.innerHTML = `<header><b>Слои ГИС ОГД в DXF</b><span class="sub">${esc(st.where)}</span><span class="sp"></span><button class="tb" data-a="close" title="Закрыть (Esc)"><i data-lucide="x"></i></button></header>`
      + `<div class="bar"><input type="search" data-a="q" placeholder="Поиск слоя или папки" value="${esc(st.q)}" aria-label="Поиск слоя">`
      + `<label title="Скрыть слои, у которых на листе нет объектов"><input type="checkbox" data-a="only" ${st.only ? "checked" : ""}>только с объектами на листе</label>`
      + `<span class="sp"></span><button class="btn" data-a="obj" ${st.counts ? "" : "disabled"} title="Отметить все слои, у которых на листе есть объекты">С объектами${nObj != null ? ` (${nObj})` : ""}</button><button class="btn" data-a="none">Снять все</button></div>`
      + `<div class="tree">${TREE ? TREE.map(n => nodeHtml(n, 0)).join("") || `<div class="note">Ничего не найдено.</div>` : `<div class="note">Каталог слоёв портала…</div>`}</div>`
      + `<footer><span class="note">${st.counts ? "" : "Считаю объекты на листе… "}Отмечено слоёв: <b>${st.sel.size}</b> из ${all.length}. Порядок и номера — как в ГИС ОГД; в AutoCAD слои встанут в том же порядке.</span><span class="sp"></span>`
      + `<button class="btn" data-a="close">Отмена</button><button class="btn primary" data-a="go" ${st.sel.size ? "" : "disabled"}><i data-lucide="file-down"></i>Выгрузить DXF</button></footer>`;
    dlg.querySelectorAll("[data-mixed]").forEach(c => { c.indeterminate = true; });
    dlg.querySelector(".tree").scrollTop = keep;
    icons();
  }

  dlg.addEventListener("click", e => {
    const a = e.target.closest("[data-a]")?.dataset.a;
    if (a === "close") dlg.close();
    if (a === "none") { st.sel.clear(); render(); }
    if (a === "obj" && st.counts) { st.sel = new Set(Object.keys(st.counts).filter(c => st.counts[c])); render(); }
    if (a === "go") {
      ALBUM.meta.ogdCodes = [...st.sel]; window.markDirty?.();          // выбор запоминается в проекте
      const fr = st.fr, codes = [...st.sel]; dlg.close(); window.runOgd(fr, codes);
    }
  });
  // флажок папки: щелчок по нему не сворачивает папку (preventDefault), выбор — вручную: все показанные слои папки
  // отмечены — снять, иначе — отметить все показанные
  dlg.addEventListener("click", e => {
    const t = e.target; if (t.dataset?.folder == null) return;
    e.preventDefault(); e.stopPropagation();
    const f = findNum(TREE, t.dataset.folder); if (!f) return;
    const ls = layers(f).filter(shown), all = ls.every(l => st.sel.has(l.code));
    ls.forEach(l => all ? st.sel.delete(l.code) : st.sel.add(l.code)); render();
  }, true);
  // раскрытые вами папки остаются раскрытыми при перерисовке
  dlg.addEventListener("toggle", e => { const d = e.target; if (d.tagName === "DETAILS") st.open.set(d.dataset.num, d.open); }, true);
  dlg.addEventListener("change", e => {
    const t = e.target;
    if (t.dataset.code) { t.checked ? st.sel.add(t.dataset.code) : st.sel.delete(t.dataset.code); render(); }
    else if (t.dataset.a === "only") { st.only = t.checked; render(); }
  });
  let qT = null;
  dlg.addEventListener("input", e => { if (e.target.dataset.a !== "q") return; clearTimeout(qT); qT = setTimeout(() => { st.q = e.target.value.trim().toLowerCase(); render(); const q = dlg.querySelector("[data-a=q]"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }, 200); });
  dlg.addEventListener("keydown", e => e.stopPropagation());               // клавиши окна не уходят в команды карты

  window.openOgdPicker = async fr => {
    const i = ALBUM.sheets.indexOf(fr), sheet = ogdSheet(fr);
    const saved = ALBUM.meta.ogdCodes;
    st = { fr, sheet, counts: null, sel: new Set(saved || []), open: new Map(), q: "", only: true, where: `лист ${i + 1} «${fr.title}», ${SIZE_T[fr.size] || fr.size}, 1:${fmt(sheet.scale)}` };
    render(); dlg.showModal();
    const my = st;
    try { if (!TREE) TREE = (await api("/api/ogd_all/tree")).tree; } catch (err) { dlg.close(); return toast("Каталог ГИС ОГД не получен: " + err.message); }
    if (st !== my) return; render();
    try { my.counts = (await api("/api/ogd_all/scan", { sheet })).counts; } catch { my.counts = {}; }
    if (st !== my) return;
    if (!saved) my.sel = new Set(Object.keys(my.counts).filter(c => my.counts[c]));   // первый раз — слои с объектами на листе
    render();
  };
})();
