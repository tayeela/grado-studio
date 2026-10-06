/* ГРАДО 2 · урбан-блоки: дозированное понижение этажности секций, чьи фасады не получают нормы инсоляции (задача T56).
   Критерий тот же, что в «Проверке норм» (constraints.js, checkNorms): у секции без северных фасадов норму СанПиН
   1.2.3685-21 (см. insol.js) должна получать не меньше половины точек фасада (шаг 6 м, шаг солнца 10 мин, окно на z над землёй).
   Метод: пока есть секции ниже 50 %, для каждой подбирается соседняя секция (чаще всего южное крыло своего квартала
   или торец соседнего), понижение которой на этаж даёт больше всего света на потерянный м² этажей; если ничто
   не помогает, секция снимается (квартал открывается). Понижается только этажность — контуры не меняются.
   Модуль без DOM: чистая функция, её же гоняет node-тест. Координаты — метры (x — восток, y — север). */
(function (root) {
  const I = typeof require !== "undefined" ? require("./insol.js") : root.INSOL;
  const area = r => Math.abs(r.reduce((s, p, i) => { const q = r[(i + 1) % r.length]; return s + p[0] * q[1] - q[0] * p[1]; }, 0)) / 2;

  /* secs: [{ring:[[x,y]…] без повтора первой точки, floors, grp?}]; o: {lat, floorH=3, norm=120 (мин), z=2, reveal=0, minF=2,
     share=.5, near=80, rounds=40, budgetMs=1500, focus: Set|Array индексов секций, которые чинятся (по умолчанию все)}. Меняет secs[i].floors на месте (0 — секция снята), возвращает отчёт. */
  function relax(secs, o) {
    const fh = o.floorH ?? 3, minF = o.minF ?? 2, share = o.share ?? .5, near = o.near ?? 80, rounds = o.rounds ?? 40, budget = o.maxSteps ?? 4000;   // бюджет в шагах, не по часам: результат одинаков на любой машине
    let steps = 0;
    const foc = o.focus ? new Set(o.focus) : null, norm = o.norm ?? 120, z = o.z ?? 2, reveal = o.reveal ?? 0;
    const paths = I.DATES.map(d => I.sunPath(o.lat, d.day, 10));
    const P = secs.map(s => ({ ring: s.ring, h: s.floors * fh }));
    const ob = I.obstacleIndex(P);                                   // высота читается при каждом луче; понижение индекс не ломает
    const pts = I.frontPoints(P, 6, z), by = secs.map(() => []);
    pts.forEach(p => by[p.b].push(p));
    const bb = P.map(p => p.bb), gfa = i => area(secs[i].ring) * secs[i].floors;
    const evalI = i => { I.evalFront(by[i], ob, paths, { norm, reveal }); const n = by[i].filter(p => !p.orient); return { n: n.length, ok: n.filter(p => p.worst.ok).length }; };
    const close = (i, j) => !(bb[j][0] > bb[i][2] + near || bb[j][2] < bb[i][0] - near || bb[j][1] > bb[i][3] + near || bb[j][3] < bb[i][1] - near);
    const st = secs.map((_, i) => evalI(i)), bad = () => st.map((s, i) => i).filter(i => (!foc || foc.has(i)) && secs[i].floors > 0 && st[i].n && st[i].ok / st[i].n < share);
    const before = bad().length, gfa0 = secs.reduce((s, _, i) => s + gfa(i), 0), lowered = new Set(), dropped = []; let timedOut = false;
    const setF = (j, f) => { secs[j].floors = f; P[j].h = f * fh; };
    for (let r = 0; r < rounds; r++) {
      const list = bad(); if (!list.length) break;
      let moved = false;
      if (++steps > budget) { timedOut = true; break; }
      for (const i of list) {
        if (st[i].ok / st[i].n >= share) continue;                   // уже исправлена понижением ради соседней секции
        let best = null;
        for (let j = 0; j < secs.length; j++) {
          if (j === i || secs[j].floors <= minF || !close(i, j)) continue;
          const f0 = secs[j].floors; setF(j, f0 - 1); const t = evalI(i); setF(j, f0);
          const gain = t.ok - st[i].ok, loss = area(secs[j].ring) || 1, score = (gain + 1e-3 * P[j].h) / loss;   // при нулевом выигрыше — самый высокий сосед
          if (!best || score > best.score) best = { j, score, gain };
        }
        if (best) { setF(best.j, Math.max(minF, secs[best.j].floors - (best.gain > 0 ? 1 : 2)));  /* без выигрыша — сразу на 2 этажа: затенение идёт от нескольких стен */ lowered.add(best.j); moved = true; }
        st[i] = evalI(i);
      }
      secs.forEach((_, i) => { if (secs[i].floors > 0) st[i] = evalI(i); });   // понижение соседей могло улучшить и другие секции
      if (!moved) break;
    }
    if (!timedOut) bad().forEach(i => { setF(i, 0); dropped.push(i); });   // ничего не помогло — квартал открывается: секции нет
    // (по истечении бюджета времени остаток не снимается: его покажет «Проверить нормы»)
    const gfa1 = secs.reduce((s, _, i) => s + gfa(i), 0);
    return { failBefore: before, failAfter: bad().length, lowered: lowered.size, dropped, timedOut, gfaBefore: gfa0, gfaAfter: gfa1 };
  }
  /* доля точек фасада с нормой для каждой секции (как в «Проверке норм»): null — у секции нет нормируемых фасадов */
  function shares(secs, o) {
    const fh = o.floorH ?? 3, P = secs.map(s => ({ ring: s.ring, h: s.floors * fh })), paths = I.DATES.map(d => I.sunPath(o.lat, d.day, 10));
    const pts = I.frontPoints(P, 6, o.z ?? 2); I.evalFront(pts, I.obstacleIndex(P), paths, { norm: o.norm ?? 120, reveal: o.reveal ?? 0 });
    return secs.map((_, i) => { const q = pts.filter(p => p.b === i && !p.orient); return q.length ? q.filter(p => p.worst.ok).length / q.length : null; });
  }
  /* переключатель «Понижать этажность ради инсоляции соседей» (окно «Эскиз»): выключен — секции не трогаются (o.on не задан или false) */
  function relaxIf(secs, o) { return o && o.on ? relax(secs, o) : { failBefore: 0, failAfter: 0, lowered: 0, dropped: [], off: true }; }
  const BLOCKS = { relax, relaxIf, shares };
  if (typeof module !== "undefined" && module.exports) module.exports = BLOCKS; else root.BLOCKS = BLOCKS;
})(typeof window !== "undefined" ? window : globalThis);
