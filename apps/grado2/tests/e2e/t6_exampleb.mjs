// T6 шаги 3–4 на контрольном примере B спецификации (docs/team/spec-T5-social-objects.md §4.2, вариант B1): территория 20 га, зона 2,
// СПП 450 тыс. м², свободно ДОО 175 / школа 400 / поликлиника 100. Ответ сервера → reserveSocial на синтетическом пятне 447×447 м
// с 25 домами по 15 этажей слева и свободной полосой справа. Проект и граф не трогаются (карта подменяется на время снимка).
const inner = async (p, check, shots) => {
  const R = JSON.parse(await p.ev(`
    const body = { terr_ha: 20, restrict_ha: 0, spp_new_m2: 450000, share: 1, spp_kept_m2: 0, spp_low_m2: 0, nonres_part: 6, education_zone: 2, k1: 1, k2: .9, tinao: 0, territory_mode: 1, unbuilt_share: 25 };
    const r = await api("/api/tep", { ...body, free_doo: 175, free_school: 400, free_clinic: 100 });
    const side = Math.sqrt(2e5), site = polyLL(rect(0, 0, side, side));
    const bld = []; for (let i = 0; i < 5; i++) for (let j = 0; j < 6; j++) { const f = polyLL(rect(20 + i * 60, 20 + j * 70, 70 + i * 60, 40 + j * 70)); bld.push({ f, m2: m2(f), floors: 15 }); }
    const pre = JSON.stringify(bld.map(b => [b.m2, b.floors])), spp = bld.reduce((s, b) => s + b.m2 * b.floors, 0);
    const snap = () => JSON.stringify([r.metrics, r.density_total]), before = snap();
    const radii = reserveRadii({ okrug: "Северо-Западный административный округ" }), res = reserveSocial(site, bld, r.social, radii), post = JSON.stringify(bld.map(b => [b.m2, b.floors]));
    const bu = unionAll(bld.map(b => b.f)), ln = f => turf.polygonToLine(f), vx = f => f.geometry.coordinates.flatMap(q => q.slice(0, -1));
    const dist = (a, b) => { let d = 1e12; for (const q of vx(a)) d = Math.min(d, turf.pointToLineDistance(turf.point(q), ln(b), { units: "meters" })); for (const q of vx(b)) d = Math.min(d, turf.pointToLineDistance(turf.point(q), ln(a), { units: "meters" })); return d; };
    const plots = res.plots.map(g => ({ kind: g.kind, m2: g.m2, places: g["Места"], inside: m2(inter(site, g.f)) / g.m2, onBld: m2(inter(bu, g.f) || null), dm: Math.min(...bld.map(b => dist(b.f, g.f))) }));
    // сохранить на карте для снимка
    const s0 = { c: sharedView.getCenter(), z: sharedView.getZoom() };
    window.__t6b = { s0, uam: updateAnalysisMap, fs: fillSketch }; updateAnalysisMap = () => {}; fillSketch = () => {};     // таймер графа не должен подменять картинку до снимка
    groundSrc.clear(); sketchSrc.clear(); siteSrc.clear();
    siteSrc.addFeature(toOl(site)); sketchSrc.addFeatures(bld.map(b => { const f = toOl(b.f); f.set("floors", b.floors); return f; }));
    Object.values(resSrcs).forEach(s => s.clear()); res.plots.forEach(g => { const f = toOl(g.f); f.set("kind", g.kind); resSrcs[g.kind].addFeature(f); });
    winOpen("wSketch", true); mMain.updateSize(); sharedView.fit(siteSrc.getExtent(), { size: mMain.getSize(), padding: [40, 40, 40, 40], duration: 0 });
    return JSON.stringify({ social: r.social, density: r.density_total, spp, pre: pre === post, plots, notes: res.notes, stats: res.stats, partial: !!res.partial, summary: reserveSummary({ social: r.social, terr: 20 }),
      same: before === snap(), nm: r.metrics.filter(m => /^spp|^density|^population/.test(m.id)).length })`));
  p.log("  T6 пример B: " + JSON.stringify(R.plots.map(o => [o.kind, Math.round(o.m2), Math.round(o.dm)])) + " · " + R.summary);
  p.log("  T6 бюджет B1: " + JSON.stringify(R.stats));
  check(!R.partial && R.stats.every(x => x.checks < 800 && x.tests < 60), "T6 пример B1: поиск уложился в бюджет (проверок < 800, точных < 60 на участок)");
  const want = { "участок ДОО": 11200, "участок школы": 12046, "участок поликлиники": 3500 };
  check(R.social.length === 3 && R.social.every(s => Math.abs(s.m2 - want[{ doo: "участок ДОО", school: "участок школы", clinic: "участок поликлиники" }[s.kind]]) < 1), "T6 пример B1: сервер даёт ДОО 350 мест 11 200 м², школу 12 046 м², поликлинику 3500 м²");
  check(R.plots.length === 3 && R.plots.every(o => Math.abs(o.m2 - want[o.kind]) / want[o.kind] <= .003), "T6 пример B1: на карте 3 участка нужных площадей с точностью 0,3 %");
  check(R.plots.every(o => o.inside >= .997 && o.onBld < 1 && o.dm >= 2.95), "T6 пример B1: участки внутри пятна, вне корпусов и не ближе 3 м к ним");
  check(R.plots.every(o => o.dm <= (o.kind === "участок ДОО" ? 300 : o.kind === "участок школы" ? 1000 : 1e9)), "T6 пример B1: ДОО в 300 м от домов, школа в 1000 м");
  check(R.plots.map(o => o.kind).join() === "участок школы,участок ДОО,участок поликлиники", "T6 пример B1: порядок размещения — школа, ДОО, поликлиника");
  check(R.pre && Math.abs(R.spp - 450000) / 450000 < .01 && R.same && R.nm >= 3, "T6 пример B1: корпуса, СПП (450 тыс. м²) и плотность те же до и после расчёта резерва (ответ ТЭП и корпуса в одном состоянии страницы)");
  check(R.summary === "Резерв: ДОО 1, школа 1, поликлиника 1 · 2,675 га (13 %)", "T6 пример B1: строка «Резерв: ДОО 1, школа 1, поликлиника 1 · 2,675 га (13 %)»");
  if (shots) { await p.sleep(900); await p.shot(shots + "/exampleB.png"); }
  // участок, которому нет места, не уменьшается и на карту не попадает: дома занимают пятно, свободны полосы по 44–54 м
  const T = JSON.parse(await p.ev(`
    const side = Math.sqrt(2e5), site = polyLL(rect(0, 0, side, side)), bl = [];
    for (let i = 0; i < 7; i++) for (let j = 0; j < 6; j++) bl.push({ f: polyLL(rect(20 + i * 55, 20 + j * 70, 60 + i * 55, 40 + j * 70)), floors: 15 }); bl.forEach(b => { b.m2 = m2(b.f); });
    const soc = [{ kind: "doo", places: 263, m2: 8416 }, { kind: "doo", places: 262, m2: 8384 }, { kind: "school", places: 1034, m2: 16544 }, { kind: "clinic", places: 59, m2: 3500 }];
    const res = reserveSocial(site, bl, soc, reserveRadii({}));
    const s0 = window.__t6b.s0; 
    return JSON.stringify({ n: res.plots.length, kinds: res.plots.map(g => g.kind), notes: res.notes, warns: res.warns, areas: res.plots.map(g => g.m2), stats: res.stats, partial: !!res.partial })`));
  p.log("  T6 бюджет тесного пятна: " + JSON.stringify(T.stats));
  check(!T.partial, "T6: на тесном пятне поиск не прерван бюджетом — участки без места честно «не помещается»");
  p.log("  T6 тесное пятно: " + JSON.stringify(T.kinds) + " · " + T.notes.join(" | "));
  check(T.notes.length >= 2 && T.notes.some(x => /^ДОО №1 \(0,842 га\) не помещается в свободной земле пятна/.test(x)) && T.notes.every(x => /освободите землю$/.test(x)), "T6: участок без места — на карте его нет, записка «ДОО №1 (0,842 га) не помещается в свободной земле пятна … — освободите землю»");
  check(T.areas.every(a => Math.abs(a - 3500) / 3500 <= .003) && T.warns.length === T.notes.length, "T6: размещённый участок не сжат (поликлиника 3500 м² ±0,3 %), каждой записке соответствует строка-предупреждение");
  // бюджет исчерпан: не «не помещается», а «поиск прерван»; результат один и тот же на любом компьютере (счёт шагов, не время)
  const Q = JSON.parse(await p.ev(`const side = Math.sqrt(2e5), site = polyLL(rect(0, 0, side, side)), bl = [], was = RES_TESTS;
    for (let i = 0; i < 5; i++) for (let j = 0; j < 6; j++) { const f = polyLL(rect(20 + i * 60, 20 + j * 70, 70 + i * 60, 40 + j * 70)); bl.push({ f, m2: m2(f), floors: 15 }); }
    const soc = [{ kind: "school", places: 634, m2: 12046 }]; let a, b; RES_TESTS = 0; try { a = reserveSocial(site, bl, soc, reserveRadii({})); b = reserveSocial(site, bl, soc, reserveRadii({})); } finally { RES_TESTS = was; }
    return JSON.stringify({ n: a.plots.length, partial: !!a.partial, notes: a.notes, same: JSON.stringify([a.notes, a.stats]) === JSON.stringify([b.notes, b.stats]) })`));
  check(Q.n === 0 && Q.partial && Q.notes.length === 1 && /поиск места прерван: слишком сложное пятно$/.test(Q.notes[0]) && !/не помещается/.test(Q.notes[0]) && Q.same, "T6: бюджет поиска исчерпан — записка «поиск места прерван: слишком сложное пятно», не «не помещается»; повтор даёт то же");
};
export default async (p, check, shots) => {
  try { await inner(p, check, shots); }
  finally {      // заглушки карты и вид возвращаются даже при упавшей проверке
    await p.ev(`const w = window.__t6b; if (w) { updateAnalysisMap = w.uam; fillSketch = w.fs; winOpen("wSketch", false); sharedView.setCenter(w.s0.c); sharedView.setZoom(w.s0.z); delete window.__t6b; updateAnalysisMap(); } return 1`);
  }
};
