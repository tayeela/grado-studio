/* ГРАДО 2 · генератор посадки застройки нового интерфейса — перенос web/app.js (place, generate и их помощники) без
   изменений логики: участки пятна между улицами, корпуса вдоль длинной стороны участка, разрывы по нормам, малоэтажные
   ряды и урбан-блоки, потолок высоты из узла «Ограничения» и этажность под цель плотности. Узел «Посадка застройки»
   схемы расчёта (graph.js) зовёт generate(site, p). Координаты — местная рамка в метрах (geom.js setFrame). */
import * as turf from "@turf/turf";
import { project } from "./store.js";
import { CONS } from "./constraints.js";      // ставит globalThis.INSOL: blocks.js берёт инсоляцию оттуда
import * as blocksModule from "../../web/blocks.js";
import { LOWRISE } from "./graphfile.js";
import { bboxOf, buf, diff, fmt, inter, m2, plural, polyLL, polys, rect, ringsXY, rot, splitParts, unionAll } from "./geom.js";

const BLOCKS = globalThis.BLOCKS || blocksModule.default || blocksModule;
const openRing = r => r.length > 1 && r[0][0] === r[r.length - 1][0] && r[0][1] === r[r.length - 1][1] ? r.slice(0, -1) : r;

/* ---------- генератор посадки (локальная рамка, метры) ---------- */
/* Посадка по логике TestFit: каждый участок пятна (между улицами) — отдельно, корпуса вдоль его длинной
   стороны (минимальный описанный прямоугольник), только целые корпуса, разрывы по нормам.
   Разрыв между длинными сторонами жилых домов — не меньше 15 м (2–3 эт.) и 20 м (4 эт. и выше),
   СП 42.13330.2016 п. 7.1; и не меньше «разрыв / высота» × высота — грубая замена расчёта инсоляции
   (СанПиН 1.2.3685-21: 2 ч непрерывно). ponytail: инсоляция и противопожарные разрывы (СП 4.13130)
   не считаются по-настоящему — только этим коэффициентом; честный расчёт — отдельный узел. */
function hull(pts) {                 // выпуклая оболочка (монотонная цепь)
  const P = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]), cr = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lo = [], up = [];
  for (const p of P) { while (lo.length > 1 && cr(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); }
  for (const p of P.reverse()) { while (up.length > 1 && cr(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop(); up.push(p); }
  return lo.slice(0, -1).concat(up.slice(0, -1));
}
export function partFrame(ring, extra) {     // угол длинной оси участка и его габарит в повёрнутой системе
  const h = hull(ring), box = a => { const q = h.map(p => rot(p, -a, [0, 0])); return bboxOf(q); };
  let best = null;
  h.forEach((p, k) => { const q = h[(k + 1) % h.length], a = Math.atan2(q[1] - p[1], q[0] - p[0]), b = box(a), ar = (b[2] - b[0]) * (b[3] - b[1]); if (!best || ar < best.ar) best = { a, ar }; });
  let a = best.a, b = box(a); if (b[2] - b[0] < b[3] - b[1]) { a += Math.PI / 2; b = box(a); }
  a += extra; return { a, b: box(a) };
}
export function generate(site, p) {
  let out = place(site, p);
  /* потолок (узел «Ограничения»): корпус не выше наименьшего потолка под ним — инсоляция соседей и высота по ПЗЗ;
     ниже двух этажей корпус не ставится. Разрывы между корпусами считаются от наибольшей этажности — после
     понижения они с запасом, а не впритык */
  const fh = CONS.floorH;
  const plots = out.plots, streets = out.streets, note = out.note;
  // малоэтажный дом (ИЖС, блокированный) может быть и одноэтажным; остальные корпуса ниже двух этажей не ставятся
  out = out.map(b => { const top = p.cap ? p.cap(b.f) : null, max = Math.min(b.maxF ?? Infinity, top == null ? b.floors : Math.min(b.floors, Math.floor(top / fh))); return max >= (b.minF ?? 2) ? { ...b, max, floors: max, capped: max < b.floors } : null; }).filter(Boolean);   // capped — потолок ниже задуманного
  // участок без дома (дом не поместился под потолком) остаётся свободным, а не пропадает
  out.plots = plots || []; out.streets = streets || []; out.note = note;
  if (!p.goal) return out;
  /* этажность под цель плотности («выращивание» внутри потолка): всем корпусам одна этажность, упёршиеся в свой
     потолок остаются на нём, недобор раздаётся остальным — пока не набрана нужная СПП или всем некуда расти */
  const need = p.goal.need;
  const fill = list => {
    let free = list.slice().sort((a, b) => a.max - b.max), fixed = 0;
    while (free.length) {
      const area = free.reduce((s, b) => s + b.m2, 0), f = Math.max(Math.min(...free.map(b => b.minF ?? 2)), Math.round((need - fixed) / area));
      const low = free.filter(b => b.max <= f);
      if (!low.length) { free.forEach(b => { b.floors = Math.min(b.max, f); }); break; }
      low.forEach(b => { b.floors = b.max; fixed += b.m2 * b.max; }); free = free.filter(b => b.max > f);
    }
    // одна общая этажность округляется вниз до полэтажа — при 5 этажах это до 10 % цели; добор по этажу корпусам с запасом
    let spp = list.reduce((s, b) => s + b.m2 * b.floors, 0);
    for (const b of list.slice().sort((a, b) => b.m2 - a.m2)) { if (spp >= need) break; if (b.floors < b.max) { b.floors++; spp += b.m2; } }
    return spp;
  };
  let spp = fill(out);
  /* цель набрана — корпуса под низкой предельной высотой (инсоляция соседей, ПЗЗ) убираются по одному, начиная с самого низкого, пока
     остальные добирают цель своей этажностью. Их пятна остаются дворами: там свет нужен соседям. Урбан-блоки, блокированные
     и ИЖС не прореживаются — у них корпус часть квартала, ряда или участка (grp). Решение владельца 23.09.2026 (Э10). */
  const dropped = [];
  if (spp >= need * .97) {
    const cand = out.filter(b => b.capped && b.grp == null).sort((a, b) => a.max - b.max || a.m2 - b.m2);
    let keep = out.slice();
    for (const b of cand) {
      const rest = keep.filter(x => x !== b);
      if (fill(rest) >= need * .97) { keep = rest; dropped.push(b); } else break;
    }
    if (dropped.length) {
      spp = fill(keep);
      const kept = new Set(keep), plots2 = out.plots, streets2 = out.streets, note2 = out.note;
      out = out.filter(b => kept.has(b)); out.plots = plots2; out.streets = streets2; out.note = note2;
      // пятна снятых корпусов, касающиеся друг друга, — одно пятно; вид свой, чтобы не читалось как пустой участок
      const u = unionAll(dropped.map(b => b.f)), parts = u ? polys(u).map(c => turf.polygon(c)) : dropped.map(b => b.f);
      parts.forEach(f => out.plots.push({ f, kind: "свет соседям", m2: m2(f), "Причина": "корпус снят: низкая предельная высота, соседям нужен свет" }));
    } else spp = fill(out);
  }
  out.dropped = dropped.length;
  out.goal = spp < need * .97 ? `цель не достигнута: не хватает ${fmt((need - spp) / 1000, 1)} тыс. м²` : `цель ${p.goal.target} тыс. м²/га${dropped.length ? ` · ${plural(dropped.length, ["корпус снят", "корпуса сняты", "корпусов снято"])}: свет соседям` : ""}`;
  return out;
}
function place(site, p) {
  if (!site) return [];
  const out = [], extra = p.angle * Math.PI / 180; out.plots = []; out.streets = [];
  const fits = (part, ring) => { const f = polyLL(ring), ar = m2(f); return m2(inter(part, f)) >= ar * .997 ? f : null; };   // корпус целиком на пятне (0,3 % — погрешность площади)
  const low = LOWRISE.has(p.typ), push = (f, floors, kind, extra = {}) => out.push({ f, floors: low ? Math.min(3, floors) : floors, m2: m2(f), kind, ...(low ? { maxF: 3, minF: 1 } : {}), ...extra });
  const plot = (f, kind, props = {}) => f && out.plots.push({ f, kind, m2: m2(f), ...props });
  let grp = 0;
  for (const part of splitParts(site)) {
    if (m2(part) < 1500) continue;
    const { a, b } = partFrame(ringsXY(part)[0], extra), W = rp => rp.map(q => rot(q, a, [0, 0]));
    const span = (lo, hi, size, gap) => { const n = Math.max(0, Math.floor((hi - lo + gap) / (size + gap))); const s0 = lo + (hi - lo - (n * size + (n - 1) * gap)) / 2; return Array.from({ length: n }, (_, i) => s0 + i * (size + gap)); };
    const H = p.floors * 3, gapLong = Math.max(p.gap * H, p.floors >= 4 ? 20 : 15), brk = 12;
    const tower = p.width + 8, tfl = Math.round(p.floors * 1.6);
    // ряд секций; withTowers — через одну вставляется точечный дом (башня), как в точечно-секционной застройке
    const row = (v, withTowers) => {
      let u = b[0], k = 0;
      while (u < b[2]) {
        if (withTowers && k % 2 === 1) { const f = fits(part, W(rect(u, v - (tower - p.width) / 2, u + tower, v - (tower - p.width) / 2 + tower))); if (f) { push(f, tfl, "башня"); u += tower + brk; k++; continue; } }
        const L = [60, 40].find(len => u + len <= b[2] + .1 && fits(part, W(rect(u, v, u + len, v + p.width))));
        if (L) { push(polyLL(W(rect(u, v, u + L, v + p.width))), p.floors, "секция"); u += L + brk; k++; } else u += 5;   // секция 60 м, у края — 40 м
      }
    };
    if (p.typ === "Секции" || p.typ === "Точка + секция") {
      for (const v of span(b[1], b[3], p.width, gapLong)) row(v, p.typ === "Точка + секция");
    } else if (p.typ === "Смешанная") {                 // секции по краям участка (вдоль улиц), внутри — башни
      const rows = span(b[1], b[3], p.width, gapLong);
      rows.forEach((v, i) => { if (i === 0 || i === rows.length - 1) row(v, false);
        else { const g = Math.max(20, p.gap * tfl * 3 * .6); for (const u of span(b[0], b[2], tower, g)) { const f = fits(part, W(rect(u, v - (tower - p.width) / 2, u + tower, v - (tower - p.width) / 2 + tower))); if (f) push(f, tfl, "башня"); } } });
    } else if (p.typ === "Башни") {
      const s = p.width + 8, fl = Math.round(p.floors * 1.6), gap = Math.max(20, p.gap * fl * 3 * .6);
      for (const v of span(b[1], b[3], s, gap)) for (const u of span(b[0], b[2], s, gap)) { const f = fits(part, W(rect(u, v, u + s, v + s))); if (f) push(f, fl, "башня"); }
    } else if (p.typ === "ИЖС" || p.typ === "Блокированные") {
      lowRise(part, a, b, W, span);
    } else if (p.typ === "Урбан-блоки") {
      urbanBlocks(part, a, b, W, span);
    } else {                                    // квартал: периметр по краю участка с проездом во двор
      if (m2(part) < 2500) continue;
      perimeter(part, b, W, Math.max(3, Math.round(p.floors * .7)), "квартал");
    }
  }
  if (p.typ === "Урбан-блоки" && !out.length) out.note ||= `квартал ${p.block} × ${Math.round(p.block * .8)} м не помещается в пятно — уменьшите «квартал, м»`;
  return out;

  function perimeter(part, b, W, floors, kind) {
    const ring = diff(part, buf(part, -p.width)) || part, cx = (b[0] + b[2]) / 2;
    const r = diff(ring, polyLL(W(rect(cx - 7, b[1] - 5, cx + 7, b[3] + 5)))) || ring;
    splitParts(r).forEach(q => { if (m2(q) >= 150) push(q, floors, kind); });
  }
  function pieces(f) { return f ? splitParts(f) : []; }
  // часть прямоугольника внутри пятна (одним куском), если её площадь не меньше доли share от прямоугольника
  function clipped(part, ring, share) { const f = polyLL(ring), full = m2(f); if (m2(inter(part, f)) >= full * .997) return f;
    const q = pieces(inter(part, f)).sort((x, y) => m2(y) - m2(x))[0]; return q && m2(q) >= full * share ? q : null; }
  function street(part, W, x0, y0, x1, y1, kind) { const f = inter(part, polyLL(W(rect(x0, y0, x1, y1)))); if (f && m2(f) > 50) out.streets.push({ f, kind, m2: m2(f) }); }

  /* ИЖС и блокированные дома — полосы «ряд участков — ряд участков — проезд»: участки двух рядов смыкаются задними
     границами, лицом выходят на свой проезд (у края пятна — на внешнюю улицу). Проезд 12 м в красных линиях.
     ИЖС (ГрК РФ ст. 1 п. 39: отдельно стоящий дом не выше 3 этажей): участок заданной площади, фронт ~ корень из
     площади / 1,6; дом до 12 × 12 м, 5 м от красной линии проезда и не ближе 3 м к границам соседних участков
     (СП 42.13330). Блокированные (ГрК РФ ст. 49 ч. 2 п. 2: не выше 3 этажей, не больше 10 домов в ряду): блок
     7 м по фасаду, глубина — «ширина корпуса» (10–14 м), 5 м палисадник и 12 м сад за домом — между длинными
     сторонами соседних рядов 24 м (не меньше 15 м для 2–3 этажей, СП 42.13330); в ряду до 6 блоков, между рядами
     домов по фасаду — 10 м проход. */
  function lowRise(part, a, b, W, span) {
    const S = 12, izs = p.typ === "ИЖС";
    const area = Math.max(400, p.plot * 100), F = Math.min(40, Math.max(18, Math.round(Math.sqrt(area / 1.6)))), Dz = Math.round(area / F);
    const uw = 7, hd = Math.max(10, Math.min(14, p.width)), G = 12, D = izs ? Dz : 5 + hd + G;
    const pitch = 2 * D + S, Hv = b[3] - b[1], m = Math.max(0, Math.floor((Hv + S) / pitch));
    const v0 = b[1] + (Hv - (m * pitch - S)) / 2;
    const front = new Array(Math.max(0, m - 1)).fill(0);        // домов лицом на каждый проезд — для гостевых мест
    // дома крайних рядов смотрят на внешнюю улицу, её в эскизе нет: их гостевые места — на ближайшем проезде
    let orphan = 0;
    const faces = (k, up, n) => { if (!front.length) { orphan += n; return; } front[Math.max(0, Math.min(front.length - 1, up ? k : k - 1))] += n; };
    for (let k = 0; k < m; k++) {
      const vs = v0 + k * pitch;
      if (k < m - 1) street(part, W, b[0] - 5, vs + 2 * D, b[2] + 5, vs + 2 * D + S, "проезд");
      for (const [r0, up] of [[vs, false], [vs + D, true]]) {        // up — ряд лицом к верхней границе полосы
        if (izs) {
          for (const u of span(b[0], b[2], F, 0)) {
            // у неровной границы участок подрезается ею, если осталось не меньше 70 % площади и дом помещается целиком
            const hw = Math.min(12, F - 8), hh = Math.min(12, D - 5 - 10), hu = u + (F - hw) / 2, hv = up ? r0 + D - 5 - hh : r0 + 5;
            const pl = clipped(part, W(rect(u, r0, u + F, r0 + D)), .7), house = pl && fits(part, W(rect(hu, hv, hu + hw, hv + hh))); if (!house) continue;
            plot(pl, "участок ИЖС", { "Площадь, сот.": Math.round(m2(pl) / 10) / 10 });
            push(house, p.floors, "дом ИЖС", { grp: ++grp }); faces(k, up, 1);
            // хозпостройка или гараж 4 × 6 м в глубине участка, 1 м от задней и боковой границ (СП 42.13330, п. 7.1):
            // в СПП не входит, показывается на участке — где дом и сарай стоят вместе, видно сразу
            const ov = up ? r0 + 1 : r0 + D - 1 - 6, out1 = polyLL(W(rect(u + 1, ov, u + 5, ov + 6)));
            if (Math.abs((up ? hv : hv + hh) - (up ? ov + 6 : ov)) >= 6 && m2(inter(pl, out1)) >= m2(out1) * .99)
              plot(out1, "хозпостройка", { "Площадь, м²": 24 });
          }
        } else {
          // ряды раскладываются от середины полосы: пробный проход слева даёт остаток на правом конце,
          // и начало сдвигается на половину остатка — полоса не «прижата» к одному краю
          const memo = new Map(), once = (k, fn) => memo.has(k) ? memo.get(k) : (memo.set(k, fn()), memo.get(k));
          const rowsFrom = (u0, dry) => { let u = u0, last = u0, count = 0;
            while (u + 3 * uw <= b[2] + .1) {
              const hv = up ? r0 + D - 5 - hd : r0 + 5;
              const units = []; for (let i = 0; i < 6; i++) { const x = u + i * uw, q = once("c" + x, () => clipped(part, W(rect(x, r0, x + uw, r0 + D)), .6)); if (!q) break; units.push(q); }
              let n = units.length; while (n >= 3 && !once("f" + u + ":" + n, () => fits(part, W(rect(u, hv, u + n * uw, hv + hd))))) n--;
              if (n < 3) { u += units.length ? uw : 5; continue; }
              count += n; last = u + n * uw;
              if (!dry) { grp++;
                for (let i = 0; i < n; i++) plot(units[i], "участок блока", { "Площадь, сот.": Math.round(m2(units[i]) / 10) / 10, "Блок": grp });
                push(polyLL(W(rect(u, hv, u + n * uw, hv + hd))), p.floors, "блокированный дом", { grp, "Блоков": n }); faces(k, up, n); }
              u += n * uw + 10;
            }
            return { count, slack: b[2] - last }; };
          const first = rowsFrom(b[0], true), shift = Math.max(0, first.slack / 2);
          const alt = shift > 1 ? rowsFrom(b[0] + shift, true) : null;
          rowsFrom(alt && alt.count >= first.count ? b[0] + shift : b[0], false);
        }
      }
    }
    /* Гостевые места по 945-ПП: постоянных мест жителей ИЖС и блокированных домов — 1,6 на дом (Прил. 5 п. 2, «C»; блок
       блокированного дома — дом), гостевых — 10 % от них (п. 6.2.3.2), с округлением вверх. Постоянные — на своих участках.
       Гостевые — плоскостные «карманы» 2,5 м вдоль проезда (улица местного значения: гостевые на прилегающей стороне
       допускаются, Прил. 7), по 6 м на место параллельно проезду; группами не реже чем через 400 м — до места не дальше
       200 м (п. 6.1.2.5.2). */
    if (orphan) out.note ||= `гостевых мест по 945-ПП нужно ${Math.ceil(orphan * .16 - 1e-9)}: внутренних проездов нет — разместите на внешней улице`;
    let short = 0;
    front.forEach((n, k) => {
      if (!n) return;
      const need = Math.ceil(n * 1.6 * .1 - 1e-9), L = b[2] - b[0], groups = Math.max(1, Math.ceil(L / 400)), per = Math.ceil(need / groups);
      const vs = v0 + k * pitch + 2 * D;                       // край проезда со стороны домов полосы k
      let left = need;
      for (let g = 0; g < groups && left > 0; g++) {
        const nn = Math.min(per, left), len = nn * 6, c = b[0] + L * (g + .5) / groups;
        for (const du of [0, -60, 60, -120, 120]) {            // у неровной границы карман сдвигается вдоль проезда
          const f = polyLL(W(rect(c - len / 2 + du, vs, c + len / 2 + du, vs + 2.5)));
          if (m2(inter(part, f)) >= m2(f) * .95) { out.streets.push({ f, kind: "гостевая стоянка", m2: m2(f), "Мест": nn }); left -= nn; break; }
        }
      }
      short += left;
    });
    if (short) out.note ||= `гостевых мест по 945-ПП не поместилось вдоль проездов: ${short} — разместите на внешней улице или парковке`;
  }

  /* урбан-блоки: сетка кварталов «квартал, м» × 0,8 с улицами 20 м между ними; по периметру квартала — секции
     глубиной «ширина корпуса» сплошным фронтом на улицу (первый этаж — нежилой), углы северной стороны — акценты ×1,4
     по этажности, сторона, обращённая на юг, — 0,6 от заданной (её углы — заданная), чтобы солнце попадало во двор; в торцевых сторонах — проход
     во двор 12 м. Квартал ставится только целиком внутри пятна. */
  function urbanBlocks(part, a, b, W, span) {
    const S = 20, Bu = p.block, Bv = Math.round(p.block * .8), d = p.width;
    if (Bu < 2 * d + 20 || Bv < 2 * d + 20) { out.note = `квартал ${Bu} × ${Bv} м меньше двух корпусов по ${d} м и двора 20 м — нужно от ${Math.ceil((2 * d + 20) / .8)} м`; return false; }
    const us = span(b[0], b[2], Bu, S), vs = span(b[1], b[3], Bv, S);
    let placed = 0;
    const side = (nx, ny) => { const c = Math.cos(a), s_ = Math.sin(a); return nx * s_ + ny * c; };        // северная составляющая наружной нормали стороны
    const south = [[0, -1], [0, 1], [-1, 0], [1, 0]].map(([nx, ny]) => side(nx, ny)), minN = Math.min(...south);
    const fl = { corner: Math.round(p.floors * 1.4), mid: p.floors, south: Math.max(2, Math.round(p.floors * .6)) };
    const at = new Set();                       // клетки сетки с кварталом: улицы — только между ними
    us.forEach((x0, i) => vs.forEach((y0, j) => {
      const x1 = x0 + Bu, y1 = y0 + Bv;
      if (!fits(part, W(rect(x0, y0, x1, y1)))) { if (cutBlock(part, W, x0, y0, x1, y1, d, Bu * Bv)) { placed++; at.add(i + ":" + j); } return; }
      placed++; grp++; at.add(i + ":" + j);
      const put = (r, floors, kind) => push(polyLL(W(r)), floors, kind, { grp, "1 этаж": "нежилой, на улицу" });
      const isS = k => south[k] === minN && minN < -.5;          // сторона смотрит на юг (отклонение не больше 60°)
      // нижняя и верхняя стороны — во всю длину с углами; боковые — между ними, с проходом во двор посередине
      [[y0, y0 + d, 0], [y1 - d, y1, 1]].forEach(([ya, yb, k]) => {
        // акценты — только на углах северной стороны: высокие южные углы затеняли дворовые фасады боковых секций
        const c = d + 10, L = Bu - 2 * c, cf = isS(k) ? fl.mid : fl.corner;
        if (L < 15) { const xm = (x0 + x1) / 2; put(rect(x0, ya, xm, yb), cf, "урбан-блок: угол"); put(rect(xm, ya, x1, yb), cf, "урбан-блок: угол"); return; }
        put(rect(x0, ya, x0 + c, yb), cf, "урбан-блок: угол"); put(rect(x1 - c, ya, x1, yb), cf, "урбан-блок: угол");
        const n = Math.max(1, Math.round(L / 45)), step = L / n;
        for (let i = 0; i < n; i++) put(rect(x0 + c + i * step, ya, x0 + c + (i + 1) * step, yb), isS(k) ? fl.south : fl.mid, isS(k) ? "урбан-блок: южная сторона" : "урбан-блок");
      });
      [[x0, x0 + d, 2], [x1 - d, x1, 3]].forEach(([xa, xb, k]) => {
        const ya = y0 + d, yb = y1 - d, ym = (ya + yb) / 2, f = isS(k) ? fl.south : fl.mid, kind = isS(k) ? "урбан-блок: южная сторона" : "урбан-блок";
        if (yb - ya >= 36) { put(rect(xa, ya, xb, ym - 6), f, kind); put(rect(xa, ym + 6, xb, yb), f, kind); } else put(rect(xa, ya, xb, yb), f, kind);
      });
      plot(polyLL(W(rect(x0 + d, y0 + d, x1 - d, y1 - d))), "двор", { "Блок": grp });
      // T56: секции, чьи фасады не набирают 50 % нормы инсоляции из-за затенения своим кварталом, — понижение соседних крыльев (blocks.js)
      const TERR = project.territory;
      if (p.relax && BLOCKS?.relaxIf && TERR) {
        const g = out.filter(b => b.grp === grp), secs = g.map(b => ({ ring: openRing(ringsXY(b.f)[0]), floors: b.floors }));
        BLOCKS.relaxIf(secs, { on: p.relax, lat: turf.centroid(TERR).geometry.coordinates[1], floorH: CONS.floorH, norm: CONS.norm * 60, z: CONS.z, reveal: CONS.reveal });
        g.forEach((b, i) => { b.floors = secs[i].floors; });
        g.forEach((b, i) => { if (!secs[i].floors) out.splice(out.indexOf(b), 1); });
      }
    }));
    if (!placed) return false;
    us.forEach((x0, i) => vs.forEach((y0, j) => {
      if (!at.has(i + ":" + j)) return;
      if (at.has(i + 1 + ":" + j)) street(part, W, x0 + Bu, y0, us[i + 1], y0 + Bv, "улица");
      if (at.has(i + ":" + (j + 1))) street(part, W, x0, y0 + Bv, x0 + Bu, vs[j + 1], "улица");
      if (at.has(i + 1 + ":" + j) && at.has(i + ":" + (j + 1)) && at.has(i + 1 + ":" + (j + 1))) street(part, W, x0 + Bu, y0 + Bv, us[i + 1], vs[j + 1], "улица");   // перекрёсток
    }));
    return true;
  }
  /* квартал у границы пятна (улица, отступ, существующие дома): часть клетки сетки внутри пятна, если это не меньше
     60 % квартала; секции идут по её наружному контуру (внутрь, вокруг сохраняемых домов, лент не будет), фронт режется
     на секции по 45 м; этажность — заданная */
  function cutBlock(part, W, x0, y0, x1, y1, d, full) {
    const cp = pieces(inter(part, polyLL(W(rect(x0, y0, x1, y1))))).sort((x, y) => m2(y) - m2(x))[0];
    if (!cp || m2(cp) < full * .6) return 0;
    // квартал без двора — не квартал: двор не меньше 20 % его площади и 600 м², иначе клетка остаётся пустой
    const outer = turf.polygon([cp.geometry.coordinates[0]]), core = buf(outer, -d), yard = core && inter(core, cp);
    if (!yard || m2(yard) < Math.max(600, m2(cp) * .2)) return 0;
    const ring = inter(diff(outer, core), cp); if (!ring) return 0;
    grp++; let n = 0;
    for (let tx = x0; tx < x1 - .1; tx += 45) for (let ty = y0; ty < y1 - .1; ty += 45)
      pieces(inter(ring, polyLL(W(rect(tx, ty, Math.min(tx + 45, x1), Math.min(ty + 45, y1))))))
        .forEach(q => { if (m2(q) >= 150) { push(q, p.floors, "урбан-блок", { grp, "1 этаж": "нежилой, на улицу" }); n++; } });
    plot(yard, "двор", { "Блок": grp });
    return n ? 1 : 0;
  }
}
