/* Нормативы расчёта ТЭП: окно с полями норм, предзаполненными действующими значениями пресета (GET /api/tep/norms).
   Правки хранятся только как разница {id: число} в параметрах узла ТЭП (tepParams(node).constants): они сохраняются
   вместе с графом проекта и ходят в совместной работе без смены формата. tepRequest шлёт их как constants. */
(() => {
  "use strict";
  let CAT = null, BY = {}, loading = null, built = null, query = "", timers = {};
  const $n = () => $("norms");
  const viewer = () => document.body.classList.contains("hub-viewer");
  const num = v => Number(v).toLocaleString("ru-RU", { maximumFractionDigits: 6 });
  const fold = s => String(s || "").toLowerCase().replace(/ё/g, "е");
  const node = () => RESULT.tepNode || null;

  function load() {
    return loading ||= fetch("/api/tep/norms").then(r => r.json()).then(j => {
      if (!Array.isArray(j.norms)) throw new Error(j.error || "нет данных");
      CAT = j; BY = Object.fromEntries(j.norms.map(n => [n.id, n])); return j;
    }).catch(e => { loading = null; throw e; });
  }
  const ready = () => load().catch(() => null);

  /* Правки из проекта: убранная из пресета норма или значение вне пределов отбрасываются с сообщением; совпавшие с действующим — молча */
  function clean(tp) {
    const o = tp?.constants; if (!o || !CAT) return;
    const bad = []; let changed = false;
    for (const [id, v] of Object.entries(o)) {
      const n = BY[id];
      if (!n) { bad.push(id); delete o[id]; changed = true; }
      else if (typeof v !== "number" || !(v >= n.min && v <= n.max)) { bad.push(n.title); delete o[id]; changed = true; }
      else if (v === n.value) { delete o[id]; changed = true; }
    }
    if (!Object.keys(o).length) delete tp.constants;
    if (bad.length) {
      toast(bad.length === 1 ? `Норматив «${bad[0]}» из проекта убран из расчёта или вне допустимых пределов — взято действующее значение.` : `Нормативов из проекта убрано из расчёта или вне допустимых пределов: ${bad.length} — взяты действующие значения.`);
      if (!viewer()) window.markDirty?.();
    }
    return changed;
  }
  function constants(tp) { clean(tp); return tp?.constants && Object.keys(tp.constants).length ? { ...tp.constants } : null; }

  function parse(inp, n) {
    if (inp.validity?.badInput || inp.value.trim() === "") return { ok: false };
    const v = Number(inp.value); return { ok: Number.isFinite(v) && v >= n.min && v <= n.max, v };
  }
  function apply(id, v) {
    const nd = node(); if (!nd || viewer()) return;
    const tp = tepParams(nd), n = BY[id], o = tp.constants ||= {};
    if (v === n.value) delete o[id]; else o[id] = v;
    if (!Object.keys(o).length) delete tp.constants;
    sync(); window.markDirty?.(); recompute(true);
  }
  function resetAll() {
    const nd = node(); if (!nd || viewer()) return;
    delete tepParams(nd).constants; sync(); window.markDirty?.(); recompute(true);
  }

  /* «Условия проекта»: зона норм и свободные места в существующих объектах — лежат в tp.zone / tp.zoneSet / tp.free, не в tp.constants,
     поэтому «Вернуть все действующие» их не трогает. Вводит владелец: программа не знает, сколько мест свободно рядом. */
  const FREE = [["doo", "Свободные места в ДОО", "мест", "Места в существующих детских садах рядом, которые не нужны нынешним жителям. Они уменьшают участок, который нужно зарезервировать."],
    ["school", "Свободные места в школах", "мест", "Места в существующих школах рядом, которые не нужны нынешним жителям. Они уменьшают участок школы."],
    ["clinic", "Свободные посещения в смену в поликлиниках", "посещ. в смену", "Незанятая мощность существующих поликлиник рядом. Если свободных нет, оставьте 0."]];
  const FREE_MAX = 100000, fbad = "Допустимо целое число от 0 до 100\u00a0000";
  function condHtml() {
    return `<section class="ncond"><div class="nct">Условия проекта</div>
      <div class="crow"><div class="nt">Образовательная зона</div><div class="nin"><select id="normZone" aria-label="Образовательная зона"><option value="1">зона 1</option><option value="2">зона 2</option></select></div>
        <div class="ns" id="normZoneSrc"></div></div>
      ${FREE.map(([k, t, u, h]) => `<div class="crow" data-free="${k}"><div class="nt">${t}</div><div class="nin"><input type="number" step="1" min="0" max="${FREE_MAX}" value="0" data-fid="${k}" aria-label="${t}"><span class="nu">${u}</span></div>
        <div class="ns">${h}</div><div class="nerr" hidden>${fbad}</div></div>`).join("")}</section>`;
  }
  function parseFree(inp) {
    if (inp.validity?.badInput || inp.value.trim() === "") return { ok: false };
    const v = Number(inp.value); return { ok: Number.isInteger(v) && v >= 0 && v <= FREE_MAX, v };
  }
  function applyFree(k, v) {
    const nd = node(); if (!nd || viewer()) return;
    const tp = tepParams(nd); if ((tp.free?.[k] ?? 0) === v) return;
    (tp.free ||= {})[k] = v; window.markDirty?.(); recompute(true);
  }
  function applyZone(z) {
    const nd = node(); if (!nd || viewer()) return;
    const tp = tepParams(nd); if (tp.zoneSet && tp.zone === z) return;
    tp.zone = z; tp.zoneSet = true; window.markDirty?.(); recompute(true);     // tp.auto не трогаем: K1, K2, ТиНАО остаются «по району»
  }
  // вручную: выбрана здесь или в «Показателях» (zoneSet), либо в старом проекте (auto = false) зона расходится с зоной района
  const zoneManual = tp => !!tp.zoneSet || (tp.zoneDist != null && tp.zone !== tp.zoneDist);
  function zoneSrc(tp) {
    if (zoneManual(tp)) return `выбрана вручную${tp.zoneDist != null ? ` · <button class="btn" data-nzone-auto title="Снова взять зону по району территории">по району</button>` : ""}`;
    if (tp.zoneNote) return "зона 2 принята: район не в списках 2151-ПП";
    return tp.district ? `по району ${esc(tp.district)}` : "район определяется…";
  }
  const newest = () => CAT.norms.map(n => n.edition).filter(Boolean).map(e => ({ e, k: e.split(".").reverse().join("") })).sort((a, b) => b.k.localeCompare(a.k))[0]?.e;
  function rowHtml(n) {
    const src = esc(n.source) + (n.edition ? `, ред. ${esc(n.edition)}` : "");
    return `<div class="nrow" data-id="${esc(n.id)}" data-t="${esc(fold(n.title))}"><div class="nt">${esc(n.title)}</div>
      <div class="nin"><input type="number" step="any" min="${n.min}" max="${n.max}" value="${n.value}" data-nid="${esc(n.id)}" aria-label="${esc(n.title)}"><span class="nu">${esc(n.unit)}</span>
      <button class="tb nrev" data-nrev="${esc(n.id)}" title="Вернуть действующее" aria-label="Вернуть действующее" hidden><i data-lucide="rotate-ccw"></i></button></div>
      <div class="ns">${src}</div><div class="nch" hidden>действующее: ${esc(num(n.value))}</div><div class="nerr" hidden>Допустимо от ${esc(num(n.min))} до ${esc(num(n.max))}</div></div>`;
  }
  function build() {
    const box = $n(); if (!box) return; const nd = node();
    if (!nd) { built = null; box.innerHTML = `<div class="nempty">В схеме расчёта нет узла «Показатели».</div>`; return; }
    if (!CAT) { built = null; box.innerHTML = `<div class="nempty">Загружаю нормативы…</div>`; return; }
    clean(tepParams(nd));
    const groups = []; CAT.norms.forEach(n => { let g = groups.find(x => x.name === n.group); if (!g) groups.push(g = { name: n.group, items: [] }); g.items.push(n); });
    box.innerHTML = condHtml() + `<div class="nhead"><p>Действующие значения на ${esc(newest() || "—")}. Измените число, если норматив обновился, — расчёт пересчитается.</p>
      <p class="nro" hidden>Только просмотр: менять нормативы может владелец или редактор проекта.</p>
      <div class="nbar"><input type="search" id="normQ" placeholder="Найти норматив: сад, стоянка…" aria-label="Найти норматив" value="${esc(query)}"><button class="btn" id="normAll" title="Убрать все ручные правки и взять действующие значения" disabled>Вернуть все действующие</button></div></div>`
      + groups.map(g => `<details class="ngrp" open data-g="${esc(g.name)}"><summary>${esc(g.name)} <small></small></summary>${g.items.map(rowHtml).join("")}</details>`).join("")
      + `<div class="nempty" id="normNone" hidden>Ничего не найдено.</div>`;
    built = nd; window.lucide?.createIcons?.({ attrs: { "stroke-width": 1.75 } }); sync(); filter();
  }
  function sync() {
    const box = $n(); if (!box || !built) return; const nd = node(); if (nd !== built) return build();
    const tp = tepParams(nd), o = tp.constants || {}, ro = viewer(); let cnt = 0;
    const zs = $("normZone"); if (zs) { zs.value = String(tp.zone); zs.disabled = ro; $("normZoneSrc").innerHTML = zoneSrc(tp); box.querySelector("[data-nzone-auto]")?.toggleAttribute("disabled", ro); }
    box.querySelectorAll(".crow[data-free] input").forEach(i => { i.disabled = ro; if (!i.closest(".crow").classList.contains("bad") && document.activeElement !== i) i.value = tp.free?.[i.dataset.fid] ?? 0; });
    box.querySelectorAll(".nrow").forEach(row => {
      const id = row.dataset.id, n = BY[id], inp = row.querySelector("input"), chg = id in o;
      if (chg) cnt++;
      row.classList.toggle("chg", chg);
      row.querySelector(".nch").hidden = !chg; row.querySelector(".nrev").hidden = !chg || ro; inp.disabled = ro;
      if (!row.classList.contains("bad") && document.activeElement !== inp) inp.value = chg ? o[id] : n.value;
    });
    box.querySelectorAll(".ngrp").forEach(g => { const k = g.querySelectorAll(".nrow.chg").length; g.querySelector("summary small").textContent = k ? `изменено: ${k}` : ""; });
    const all = $("normAll"); if (all) all.disabled = !cnt || ro;
    box.querySelector(".nro").hidden = !ro;
  }
  function filter() {
    const box = $n(); if (!box || !built) return; const q = fold(query.trim()); let any = false;
    box.querySelectorAll(".ngrp").forEach(g => {
      let vis = 0; g.querySelectorAll(".nrow").forEach(r => { const on = !q || r.dataset.t.includes(q); r.hidden = !on; if (on) vis++; });
      g.hidden = !vis; if (q && vis) g.open = true; if (vis) any = true;
    });
    $("normNone").hidden = any;
  }
  function refresh() { if (!$("wNorms") || $("wNorms").hidden) return; if (!built) build(); else sync(); }

  document.addEventListener("input", e => {
    const t = e.target; if (t.id === "normQ") { query = t.value; filter(); return; }
    const fk = t.dataset?.fid; if (fk && t.closest("#norms")) {
      const row = t.closest(".crow"), p = parseFree(t); row.classList.toggle("bad", !p.ok); row.querySelector(".nerr").hidden = p.ok;
      clearTimeout(timers["f" + fk]); if (p.ok) timers["f" + fk] = setTimeout(() => applyFree(fk, p.v), 450); return; }
    const id = t.dataset?.nid; if (!id || !t.closest("#norms")) return;
    const row = t.closest(".nrow"), p = parse(t, BY[id]);
    row.classList.toggle("bad", !p.ok); row.querySelector(".nerr").hidden = p.ok;
    clearTimeout(timers[id]); if (p.ok) timers[id] = setTimeout(() => apply(id, p.v), 450);
  });
  document.addEventListener("change", e => {
    const t = e.target;
    if (t.id === "normZone") { applyZone(+t.value); return; }
    const fk = t.dataset?.fid; if (fk && t.closest("#norms")) { const p = parseFree(t); clearTimeout(timers["f" + fk]); if (p.ok) applyFree(fk, p.v); return; }
    const id = t.dataset?.nid; if (!id || !t.closest("#norms")) return;
    const p = parse(t, BY[id]); clearTimeout(timers[id]); if (p.ok) apply(id, p.v);
  });
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-norms-open]"); if (b) { winOpen("wNorms", true); return; }
    const r = e.target.closest("[data-nrev]"); if (r && r.closest("#norms")) {
      const row = r.closest(".nrow"); row.classList.remove("bad"); row.querySelector(".nerr").hidden = true; clearTimeout(timers[r.dataset.nrev]); apply(r.dataset.nrev, BY[r.dataset.nrev].value); return; }
    if (e.target.closest("#normAll")) resetAll();
    if (e.target.closest("[data-nzone-auto]") && e.target.closest("#norms")) { const nd = node(); if (!nd || viewer()) return; const tp = tepParams(nd);
      delete tp.zoneSet; tp.zone = tp.zoneDist ?? tp.zone; window.markDirty?.(); recompute(true); }
  });
  WIN_OPEN.wNorms = () => { build(); load().then(() => { build(); }).catch(err => { const bx = $n(); if (bx) bx.innerHTML = `<div class="nempty">Нормативы не загрузились: ${esc(err.message)}. Закройте окно и откройте снова.</div>`; }); };
  window.Norms = { ready, constants, clean, refresh, open: () => winOpen("wNorms", true) };
})();
