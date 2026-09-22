/* ГРАДО 2 · ограничения для генерации (этап Э4 плана).
   Окно «Ограничения» строит из загруженных данных обычные слои группы «Ограничения»: ЗОУИТ и охранные зоны,
   отступ от красных линий, противопожарные разрывы до сохраняемых зданий, подзоны ПЗЗ без нового строительства,
   инсоляционный фронт существующих окон и солнечный потолок участка. Слои видны, стилизуются и выключаются
   как любые другие; узел графа «Ограничения» читает только ВКЛЮЧЁННЫЕ слои группы — выключил слой в дереве,
   и посадка его больше не учитывает (что видно на карте, то и учитывает генерация).
   Инсоляция — предпроектная оценка по методам ГОСТ Р 57795-2017, не сертифицированный расчёт (см. insol.js). */

const CONS = { norm: 2, z: 2, step: 4, reveal: 0, cell: 8, floorH: 3, redline: 5, cap: 150, use: { zouit: true, red: true, fire: true, pzz: true, insol: true } };
try { Object.assign(CONS, JSON.parse(localStorage.getItem("grado2.cons") || "{}")); } catch { }
const CONS_GROUP = "Ограничения";
const CK = { zouit: "cons:zouit", red: "cons:redlines", fire: "cons:fire", pzz: "cons:pzz0", front: "cons:front", ceil: "cons:ceiling" };
const EXCLUDE = [CK.zouit, CK.red, CK.fire, CK.pzz];   // слои-запреты: вычитаются из пятна застройки

/* противопожарные разрывы между новым зданием I–II степени огнестойкости (С0) и существующим — СП 4.13130.2013, табл. 1:
   I–III, С0 — 6 м; II–III С1, IV С0 — 8 м; IV–V, С1–С3 (дерево, смешанные) — 10 м. Степень берётся по материалу стен ЕГРН. */
function fireGap(f) {
  const m = String(f.properties["Материал стен"] || "").toLowerCase();
  if (/дерев|брус|бревен|каркасно|щитов/.test(m)) return 10;
  if (/смешан|проч|иные|металл/.test(m)) return 8;
  return 6;
}
const isResidential = f => { const p = f.properties, s = String(p["Назначение"] || p["Тип здания"] || "").toLowerCase(); return !/нежил/.test(s) && /жил|многокварт|residential|apartments|house|dormitory/.test(s); };
const decisionOf = f => String(f.properties["Решение"] || "сохраняем");

function consLayer(key, title, fc, geom, style) {
  const had = !!DATA[key];
  DATA[key] = { title, source: "ограничение, рассчитано " + new Date().toLocaleString("ru-RU"), fetched_at: new Date().toISOString().slice(0, 10), fc, count: fc.features.length, fields: [...new Set(fc.features.slice(0, 200).flatMap(f => Object.keys(f.properties)))] };
  layerSrc[key] ||= new ol.source.Vector(); setLayerData(key, fc); delete DATA[key].original;
  const l = ensureLayer(key, title, geom);
  if (!had) { l.style = ST(style); l.visible = true; }
  let g = GROUPS.find(x => x.title === CONS_GROUP); if (!g) { newGroup([key], CONS_GROUP); g = GROUPS.find(x => x.title === CONS_GROUP); }
  l.group = g.id; l.title = title; normGroups(); restyle(l); applyOrder();
  return l;
}
const clip = (f, terr) => { const r = inter(f, terr); return r && m2(r) > 1 ? r : null; };
const polyFeats = key => (DATA[key]?.fc.features || []).filter(f => /Polygon/.test(f.geometry?.type));

/* ---------- расчёт ---------- */
async function computeConstraints() {
  if (!TERR) return toast("Сначала задайте границу территории (окно «Данные» или инструмент «Граница»).");
  try { localStorage.setItem("grado2.cons", JSON.stringify({ ...CONS, log: undefined })); } catch { }
  const zone = buf(TERR, 200), log = [], tick = () => new Promise(r => setTimeout(r, 0));
  busy(true); const runBtn = $("consRun"); if (runBtn) runBtn.disabled = true;
  try {
    // 1. ЗОУИТ и охранные зоны: каждая зона отдельно, с причиной — «почему здесь нельзя»
    if (CONS.use.zouit) {
      const out = [];
      [["nspd.zouit", f => f.properties["Вид зоны"] || f.properties["Наименование"] || "ЗОУИТ (ЕГРН)"], ["gisogd.szz", f => f.properties["Вид зоны"] || "СЗЗ"], ["gisogd.vodookhr", () => "Водоохранная зона"],
        ["gisogd.okn", f => /регулирован/i.test(f.properties["Вид зоны"] || "") ? null : `ОКН: ${f.properties["Вид зоны"] || "зона"}`]]
        .forEach(([k, why]) => polyFeats(k).forEach(f => { const w = why(f); if (!w) return; const c = clip(f, TERR); if (c) out.push(turf.feature(c.geometry, { "Причина": w, "Источник": DATA[k].title, "Наименование": f.properties["Наименование"] || "" })); }));
      consLayer(CK.zouit, "Запрет: ЗОУИТ и охранные зоны", turf.featureCollection(out), "poly", { mode: "cat", hatch: true, width: 1.2, cat: { field: "Причина", colors: {}, off: [] } });
      log.push(`ЗОУИТ и охранные зоны: ${out.length}` + (DATA["gisogd.okn"] ? "" : " (ОКН не загружены)"));
    }
    // 2. отступ от красных линий
    if (CONS.use.red) {
      const lines = (DATA["gisogd.red_lines"]?.fc.features || []).filter(f => /Line/.test(f.geometry?.type) && safe(() => turf.booleanIntersects(f, zone)));
      const out = lines.map(f => buf(f, CONS.redline)).filter(Boolean).map(f => clip(f, TERR)).filter(Boolean).map(f => turf.feature(f.geometry, { "Причина": `отступ ${CONS.redline} м от красной линии`, "Норма": "СП 42.13330.2016" }));
      const u = unionAll(out); const fc = turf.featureCollection(u ? [turf.feature(u.geometry, { "Причина": `отступ ${CONS.redline} м от красных линий`, "Норма": "СП 42.13330.2016" })] : []);
      consLayer(CK.red, `Запрет: ${CONS.redline} м от красных линий`, fc, "poly", { fill: "#d7191c", stroke: "#d7191c", hatch: true, width: 1 });
      log.push(DATA["gisogd.red_lines"] ? `красные линии: ${lines.length}` : "красные линии не загружены — отступ не построен");
    }
    await tick();
    // 3. сохраняемые здания и противопожарные разрывы до них
    const ek = EXIST_KEY(), exist = ek ? DATA[ek].fc.features.filter(f => /Polygon/.test(f.geometry?.type) && safe(() => turf.booleanIntersects(f, zone))) : [];
    const kept = exist.filter(f => decisionOf(f) !== "сносим");
    if (CONS.use.fire) {
      const out = kept.map(f => { const g = fireGap(f), b = buf(f, g); const c = b && clip(b, TERR); return c ? turf.feature(c.geometry, { "Причина": `противопожарный разрыв ${g} м`, "Материал стен": f.properties["Материал стен"] || "нет данных", "Норма": "СП 4.13130.2013, табл. 1" }) : null; }).filter(Boolean);
      consLayer(CK.fire, "Запрет: сохраняемые здания и пожарные разрывы", turf.featureCollection(out), "poly", { fill: "#eb6834", stroke: "#b34a1c", opacity: .25, width: .8 });
      log.push(`сохраняемых зданий: ${kept.length}` + (ek ? "" : " (здания не загружены)"));
    }
    // 4. ПЗЗ: подзоны с нулевыми параметрами — нового строительства нет
    if (CONS.use.pzz) {
      const zero = polyFeats("gisogd.pzz_sub").filter(f => /не предусмотрено/.test(f.properties["Регламент"] || "")).map(f => clip(f, TERR) && turf.feature(clip(f, TERR).geometry, { "Причина": "ПЗЗ: нулевые параметры", "Номер подзоны": f.properties["Номер подзоны"], "Документ": f.properties["Документ"] })).filter(Boolean);
      consLayer(CK.pzz, "Запрет: ПЗЗ без нового строительства", turf.featureCollection(zero), "poly", { fill: "#8a5a00", stroke: "#8a5a00", hatch: true, width: 1 });
      log.push(DATA["gisogd.pzz_sub"] ? `подзон ПЗЗ без строительства: ${zero.length}` : "ПЗЗ не загружены");
    }
    await tick();
    // 5–6. инсоляция: фронт существующих жилых окон и солнечный потолок участка
    if (CONS.use.insol) {
      const t0 = performance.now(), lat = turf.centroid(TERR).geometry.coordinates[1];
      const open = r => r.length > 1 && r[0][0] === r[r.length - 1][0] && r[0][1] === r[r.length - 1][1] ? r.slice(0, -1) : r;
      const prism = f => polys(f).map(p => ({ ring: open(p[0].map(toXY)), holes: p.slice(1).map(h => open(h.map(toXY))), h: floorsOf(f) * CONS.floorH, f }));
      const obst = kept.flatMap(prism), resid = kept.filter(isResidential).flatMap(prism);
      const ob = INSOL.obstacleIndex(obst), paths = INSOL.DATES.map(d => INSOL.sunPath(lat, d.day, 5));
      const pts = INSOL.frontPoints(resid, CONS.step, CONS.z);
      for (let i = 0; i < pts.length; i += 200) { INSOL.evalFront(pts.slice(i, i + 200), ob, paths, { norm: CONS.norm * 60, reveal: CONS.reveal }); setHint(`Инсоляция: фасады ${Math.min(pts.length, i + 200)} из ${pts.length}…`); await tick(); }
      const fmin = m => `${Math.floor(m / 60)} ч ${String(m % 60).padStart(2, "0")} мин`;
      const front = turf.featureCollection(pts.map(p => turf.point(toLL([p.x, p.y]), { "Норма": p.orient ? "не нормируется (фасад на север)" : p.worst.ok ? `выполняется (${p.worst.ok})` : "не выполняется до застройки", "Непрерывно": fmin(p.worst.cont), "Всего": fmin(p.worst.total), "Непрерывно, мин": p.worst.cont, "Здание": resid[p.b].f.properties["Адрес"] || resid[p.b].f.properties["Кадастровый номер"] || "" })));
      consLayer(CK.front, "Инсоляция: окна соседей (фронт)", front, "point", { mode: "cat", width: 1.2, cat: { field: "Норма", colors: { "выполняется (непрерывная)": "#1f7a4d", "выполняется (прерывистая)": "#eda100", "не выполняется до застройки": "#b3261e", "не нормируется (фасад на север)": "#9aa1a8" }, off: [] } });
      // сетка потолка по территории
      const tb = bboxOf(ringsXY(TERR)[0]), cell = CONS.cell, nx = Math.ceil((tb[2] - tb[0]) / cell), ny = Math.ceil((tb[3] - tb[1]) / cell);
      const grid = { x0: tb[0], y0: tb[1], cell, nx, ny, inside: new Uint8Array(nx * ny) };
      const tRings = ringsXY(TERR)[0], inPoly = (x, y) => { let c = false; for (let i = 0, j = tRings.length - 1; i < tRings.length; j = i++) { const a = tRings[i], b = tRings[j]; if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) c = !c; } return c; };
      for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) grid.inside[j * nx + i] = inPoly(tb[0] + (i + .5) * cell, tb[1] + (j + .5) * cell) ? 1 : 0;
      setHint("Инсоляция: солнечный потолок…"); await tick();
      const { env, protectedRays } = INSOL.envelope(pts, paths, grid, { norm: CONS.norm * 60, cap: CONS.cap });
      // ПЗЗ: предельная высота подзоны (где задана числом) — тоже потолок
      const pzz = polyFeats("gisogd.pzz_sub").filter(f => f.properties["Высота, м"] > 0).map(f => ({ f, h: +f.properties["Высота, м"] }));
      const cells = [];
      for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
        const n = j * nx + i; if (!grid.inside[n]) continue;
        const x = tb[0] + i * cell, y = tb[1] + j * cell, cx = toLL([x + cell / 2, y + cell / 2]);
        const hp = pzz.find(z => safe(() => turf.booleanPointInPolygon(cx, z.f)))?.h ?? null, hs = env[n] >= CONS.cap - .01 ? null : Math.max(0, env[n]);
        const top = Math.min(hs ?? Infinity, hp ?? Infinity);
        if (top === Infinity) continue;                        // клетка без ограничения по высоте — пустая, карта под ней видна
        cells.push(turf.polygon([[toLL([x, y]), toLL([x + cell, y]), toLL([x + cell, y + cell]), toLL([x, y + cell]), toLL([x, y])]], {
          "Потолок, м": top === Infinity ? null : Math.round(top * 10) / 10, "Потолок, эт.": top === Infinity ? null : Math.floor(top / CONS.floorH),
          "По инсоляции, м": hs == null ? null : Math.round(hs * 10) / 10, "По ПЗЗ, м": hp, "Почему": hs != null && (hp == null || hs <= hp) ? "тень на окна соседей" : hp != null ? "высота по ПЗЗ" : "не ограничено" }));
      }
      consLayer(CK.ceil, "Потолок застройки (инсоляция соседей, ПЗЗ)", turf.featureCollection(cells), "poly", { mode: "grad", opacity: .4, stroke: "#ffffff", width: 0, grad: { field: "Потолок, эт.", n: 5, ramp: "green", method: "equal" } });
      const north = pts.filter(p => p.orient).length, bad = pts.filter(p => !p.orient && !p.worst.ok).length;
      log.push(`инсоляция: ${pts.length} расчётных точек на ${resid.length} жилых домах; ${north} на северных фасадах (не нормируются), ${bad} не выполняют норму уже сейчас — для них «не ухудшать»; ${Math.round(performance.now() - t0)} мс`);
    }
    dataRev++; ensureConsNode(); renderTree();
    CONS.log = log; renderCons(); toast("Ограничения рассчитаны. Выключенный в дереве слой группы «Ограничения» генерация не учитывает.");
  } catch (e) { console.error(e); toast("Ограничения не рассчитаны: " + e.message); }
  finally { busy(false); if ($("consRun")) $("consRun").disabled = false; syncStatus(); }
}

/* ---------- узел графа «Ограничения»: читает включённые слои группы ---------- */
function consExclude() {
  const on = EXCLUDE.map(lyr).filter(l => l && shown(l));
  return unionAll(on.flatMap(l => layerSrc[l.key].getFeatures().map(f => GJ.writeFeatureObject(f)).filter(f => /Polygon/.test(f.geometry?.type))));
}
// потолок корпуса: наименьший «Потолок, м» среди клеток, которые задевает пятно корпуса; null — не ограничен
function consCeiling() {
  const l = lyr(CK.ceil); if (!l || !shown(l)) return null;
  const src = layerSrc[CK.ceil];
  return f => { let top = Infinity; const ex = GJ.readFeature(f).getGeometry().getExtent(); src.forEachFeatureIntersectingExtent(ex, c => { const v = c.get("Потолок, м"); if (v != null && v < top && safe(() => turf.booleanIntersects(f, GJ.writeFeatureObject(c)))) top = v; }); return top === Infinity ? null : top; };
}
function NCons() { this.addOutput("запреты", "geom"); this.addOutput("потолок", "cap"); finish(this, "src", 220); }
NCons.title = "Ограничения"; NCons.prototype.onExecute = function () {
  const vis = [...EXCLUDE, CK.ceil].map(k => { const l = lyr(k); return l ? (shown(l) ? 1 : 0) + ":" + DATA[k]?.rev : "-"; }).join(",");
  if (this._ck !== vis) { this._ck = vis; this._ex = consExclude(); this._cap = consCeiling(); if (this._ex) this._ex.properties = {}; if (this._cap) this._cap._id = Math.random().toString(36).slice(2); }
  this.setOutputData(0, this._ex); this.setOutputData(1, this._cap);
  const n = EXCLUDE.filter(k => lyr(k) && shown(lyr(k))).length;
  this.info = lyr(CK.zouit) || lyr(CK.ceil) ? `запретов: ${n} слоя · ${ha(this._ex)}${this._cap ? " · потолок" : ""}` : "окно «Ограничения» → Рассчитать";
};
LiteGraph.registerNodeType("Данные/Ограничения", NCons);
LIB["Данные"].push("Данные/Ограничения");
$("lib").innerHTML = Object.entries(LIB).map(([c, ts]) => `<div class="cat">${c}</div>` + ts.map(t => `<button data-add="${t}"><i data-lucide="${LIBICON[c]}"></i>${t.split("/")[1]}</button>`).join("")).join("");

// узел встаёт между пятном застройки и посадкой: пятно − запреты, потолок — в посадку
function ensureConsNode() {
  const place = graph._nodes.find(n => n.type === "Эскиз/Посадка застройки"); if (!place) return;
  if (graph._nodes.some(n => n.type === "Данные/Ограничения")) return;
  const src = place.inputs[0]?.link != null ? graph.links[place.inputs[0].link] : null, from = src && graph.getNodeById(src.origin_id);
  const nc = add("Данные/Ограничения", [place.pos[0] - 250, place.pos[1] + 260]);
  const nd = add("Геометрия/Вычесть", [place.pos[0] - 20, place.pos[1] + 200], n => n.title = "Пятно с ограничениями");
  if (from) from.connect(src.origin_slot, nd, 0);
  nc.connect(0, nd, 1); nd.connect(0, place, 0);
  if (!place.inputs[2]) place.addInput("потолок", "cap");
  nc.connect(1, place, 2);
  toast("В граф добавлен узел «Ограничения»: пятно застройки минус запреты, высота корпусов — не выше потолка.");
}

/* ---------- окно ---------- */
window.renderCons = renderCons;
function renderCons() {
  const c = CONS, chk = (k, t, hint) => `<label class="lr" title="${esc(hint)}"><input type="checkbox" data-cu="${k}" ${c.use[k] ? "checked" : ""}><span class="nm">${t}</span></label>`;
  const num = (k, t, min, max, step, hint) => `<div class="row" title="${esc(hint)}"><label>${t}</label><input type="number" data-cn="${k}" value="${c[k]}" min="${min}" max="${max}" step="${step}" style="width:80px"></div>`;
  $("consBody").innerHTML = `<div class="pad"><div class="note" style="padding:0 0 8px">Запреты вычитаются из пятна застройки; потолок ограничивает высоту корпусов. Всё строится из загруженных данных и появляется в группе слоёв «Ограничения»: выключите слой — генерация перестанет его учитывать.</div></div>`
    + `<div class="sect">Что учитывать</div>`
    + chk("zouit", "ЗОУИТ, СЗЗ, водоохранные, зоны ОКН", "Из загруженных слоёв ЕГРН и ГИС ОГД. Зоны регулирования застройки ОКН не запрещают строить и не учитываются.")
    + chk("red", "Отступ от красных линий", "Буфер от красных линий ГИС ОГД, СП 42.13330.2016")
    + chk("fire", "Сохраняемые здания и противопожарные разрывы", "Все здания, кроме отмеченных «сносим» в реестре. Разрыв 6/8/10 м по материалу стен, СП 4.13130.2013 табл. 1")
    + chk("pzz", "Подзоны ПЗЗ без нового строительства", "Подзоны с нулевыми параметрами (плотность, высота и застроенность — 0)")
    + chk("insol", "Инсоляция окон соседей и солнечный потолок", "Расчётные точки на фасадах сохраняемых жилых домов; потолок — наибольшая высота, при которой соседи не теряют норму")
    + `<div class="sect">Параметры</div><div class="pad">`
    + num("redline", "Отступ от КЛ, м", 0, 30, 1, "Расстояние от красной линии до застройки")
    + num("norm", "Норма, ч", 1, 3, .5, "СанПиН 1.2.3685-21, центральная зона: 2 ч непрерывно (1,5 ч — при реконструкции в центре и при двух инсолируемых комнатах)")
    + num("z", "Высота окна, м", .5, 30, .1, "Высота расчётной точки над землёй: окно нижнего жилого этажа")
    + num("step", "Шаг точек, м", 2, 20, 1, "Через сколько метров по фасаду ставить расчётную точку")
    + num("reveal", "Теневой угол окна, °", 0, 45, 1, "Откосы окна и лоджии: солнце под более острым углом к фасаду в окно не попадает")
    + num("floorH", "Высота этажа, м", 2.7, 4.5, .1, "Для высоты существующих зданий (по этажности ЕГРН) и перевода потолка в этажи")
    + num("cell", "Клетка потолка, м", 4, 20, 1, "Размер клетки сетки солнечного потолка")
    + `</div><div class="pad"><button class="btn primary" id="consRun"><i data-lucide="shield-check"></i>Рассчитать ограничения</button></div>`
    + (c.log ? `<div class="sect">Результат</div><div class="note">${c.log.map(esc).join("<br>")}</div>` : "")
    + `<div class="note" style="color:var(--warn)">Инсоляция — предпроектная оценка по методам ГОСТ Р 57795-2017 (22 апреля и 22 августа, солнечное время, без первого часа после восхода и последнего перед заходом). Не заменяет сертифицированный расчёт для экспертизы. Рельеф не учитывается, высота зданий — этажность × высота этажа, школы и детские сады отдельно не выделяются.</div>`;
  icons();
}
$("consBody").addEventListener("change", e => {
  const t = e.target; if (t.dataset.cu) CONS.use[t.dataset.cu] = t.checked; if (t.dataset.cn) CONS[t.dataset.cn] = +t.value;
  try { localStorage.setItem("grado2.cons", JSON.stringify({ ...CONS, log: undefined })); } catch { }
});
$("consBody").addEventListener("click", e => { if (e.target.closest("#consRun")) computeConstraints(); });
