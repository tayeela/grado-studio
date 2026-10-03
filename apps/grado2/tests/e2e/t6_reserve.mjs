// T6 шаги 3–4: резерв участков ДОО, школы и поликлиники на карте. Вызывается из scenarios.mjs (и отдельно: см. t6_reserve_solo.mjs).
// Берёт текущий эскиз проекта, на время шага ставит просторную застройку (30 этажей, разрыв 1,2), в конце возвращает параметры.
export default async (p, check, shots) => {
  const pre = await p.ev(`const pn=RESULT.placeNode, num=graph._nodes.find(n=>n.type==="Параметры/Число"); window.__t6 = { f: num.widgets[0].value, g: pn.widgets[3].value, m: pn.widgets[5].value, tg: RESULT.tepNode.widgets[1].value };
    num.widgets[0].value=30; pn.widgets[3].value=1.2; pn.widgets[5].value="заданной"; pn.properties.run=true; pn._ck=null; RESULT.tepNode.properties.baked=null; recompute(true);
    const t0=Date.now(); while (Date.now()-t0<20000) { const t=RESULT.tepNode._tep; if (t && t.social && t.social.length && RESULT.sketch.length && Math.abs(t.sppNew - RESULT.sketch.reduce((q,b)=>q+b.m2*b.floors,0)) < 1 && reserveState().plots.length+reserveState().notes.length>0) break; await new Promise(r=>setTimeout(r,300)); }
    const t=RESULT.tepNode._tep, st=reserveState(); return [t.social.length, st.plots.length, st.notes.length, RESULT.sketch.length]`);
  p.log("  T6 бюджет проекта: " + JSON.stringify(await p.ev(`return reserveState().stats`)));
  check(await p.ev(`return !reserveState().partial`), "T6: поиск мест на примере проекта не прерван бюджетом");
  p.log(`  T6: участков от сервера ${pre[0]}, на карте ${pre[1]}, «не помещается» ${pre[2]}, корпусов ${pre[3]}`);
  check(pre[0] > 0 && pre[1] + pre[2] === pre[0] && pre[1] > 0, "T6 шаг 4: каждый участок ответа сервера либо на карте, либо в списке «не помещается»; на просторной застройке участки на карте есть");
  const geo = await p.ev(`const st=reserveState(), site=RESULT.site, sk=RESULT.sketch, t=RESULT.tepNode._tep, rr=reserveRadii(tepParams(RESULT.tepNode)); const bu=unionAll(sk.map(b=>b.f));
    const pool=t.social.map(s=>({...s})), vx=f=>f.geometry.coordinates.flatMap(r=>r.slice(0,-1)), ln=f=>turf.polygonToLine(f);
    const dist=(a,b)=>{ let d=1e12; for (const q of vx(a)) d=Math.min(d, turf.pointToLineDistance(turf.point(q), ln(b), {units:"meters"})); return d; };
    const out=st.plots.map(g=>{ const k=Object.keys(RES_KINDS).find(x=>RES_KINDS[x]===g.kind), i=pool.findIndex(s=>s.kind===k && s.places===g["Места"] && Math.abs(s.m2-g.m2)/s.m2<.003); if (i>=0) pool.splice(i,1);
      let dm=1e12; for (const b of sk) { if (!turf.booleanDisjoint(b.f,g.f)) { dm=0; break; } dm=Math.min(dm, dist(b.f,g.f), dist(g.f,b.f)); }
      return { kind:g.kind, matched:i>=0, inside:m2(inter(site,g.f))/g.m2, onBld:bu?m2(inter(bu,g.f)):0, dm, r:rr[k], places:g["Места"], def:g["Дефицит"] }; });
    const pl=st.plots; let overlap=0; for (let i=0;i<pl.length;i++) for (let j=i+1;j<pl.length;j++) overlap+=m2(inter(pl[i].f,pl[j].f)||null);
    return JSON.stringify({ out, overlap, order:st.plots.map(g=>g.kind) })`);
  const G = JSON.parse(geo); p.log("  T6 участки: " + JSON.stringify(G.out.map(o => [o.kind, Math.round(o.dm), o.r, +o.inside.toFixed(4)])));
  check(G.out.every(o => o.matched), "T6: площадь каждого участка на карте равна площади участка ответа сервера с точностью 0,3 %");
  check(G.out.every(o => o.inside >= .997), "T6: участки лежат внутри пятна застройки");
  check(G.out.every(o => o.onBld < 1 && o.dm >= 3 - .05), "T6: участки не пересекают корпуса и отстоят от них не менее чем на 3 м");
  check(G.out.every(o => !o.r || o.dm <= o.r), "T6: расстояние до ближайшего корпуса не больше радиуса (ДОО 300 м, школа 1000 м; ЦАО — 500 м и без радиуса)");
  check(G.overlap < 1, "T6: участки друг на друга не налезают");
  check(await p.ev(`const pl=RESULT.sketch.plots||[]; return reserveState().plots.every(g=>!pl.includes(g)) && pl.every(g=>!/^участок (ДОО|школы|поликлиники)$/.test(g.kind))`), "T6: резерв не попадает в sketch.plots графа (кэш посадки не портится)");
  // карта, строка в «Показателях», записка в панели эскиза
  await p.ev(`winOpen("wTep", true); winOpen("wSketch", true); updateAnalysisMap(); renderTep(); renderParams(); await new Promise(r=>setTimeout(r,800)); return 1`);
  const ui = await p.ev(`const kinds=Object.values(resSrcs).flatMap(s=>s.getFeatures()).filter(f=>/^участок (ДОО|школы|поликлиники)$/.test(f.get("kind"))).length, line=document.querySelector("#tep .resline")?.textContent||"", t=RESULT.tepNode._tep, st=reserveState();
    return [kinds, st.plots.length, line, document.querySelectorAll("#tep .note.warn").length, document.querySelectorAll("#resNote .note.warn").length, st.notes.length, t.social.length]`);
  p.log("  T6 строка: " + ui[2]);
  check(ui[0] === ui[1] && /^Резерв: /.test(ui[2]) && /га \(\d+ %\)/.test(ui[2]), "T6 шаг 3: на карте столько же участков, сколько посчитано; над показателями строка «Резерв: … · X,XXX га (YY %)»");
  const wn = await p.ev(`const sect=[...document.querySelectorAll("#tep .sect")].find(e=>e.textContent==="Резерв участков"); let n=0, e=sect?.nextElementSibling; while (e && !e.classList.contains("sect")) { if (e.classList.contains("note") && e.classList.contains("warn")) n++; e=e.nextElementSibling; } return [!!sect, n, reserveState().warns.length]`);
  check(wn[0] && wn[1] === wn[2], `T6: в группе «Резерв участков» строк-предупреждений столько же, сколько участков без места (${wn[1]})`);
  check(ui[4] === ui[5], "T6: каждому участку, который не поместился, в панели эскиза соответствует записка");
  if (shots) { await p.shot(shots + "/map.png"); await p.ev(`winOpen("wSketch", false); await new Promise(r=>setTimeout(r,400)); document.querySelector("#tep .resline").scrollIntoView({block:"center"}); return 1`); await p.shot(shots + "/tep-line.png"); }
  // СПП и плотность не зависят от резерва: тот же расчёт без резерва (свободные места больше потребности → social пуст)
  const cmp = await p.ev(`const tp=tepParams(RESULT.tepNode), free0=tp.free, m0=Object.fromEntries(RESULT.tepNode._tep.metrics.filter(m=>/^spp|^density/.test(m.id)).map(m=>[m.id,m.value])), n0=RESULT.sketch.map(b=>b.floors+":"+Math.round(b.m2)).join();
    tp.free={doo:100000,school:100000,clinic:100000}; RESULT.tepNode._key=null; recompute(true);
    const t0=Date.now(); while (Date.now()-t0<15000) { const t=RESULT.tepNode._tep; if (t && t.social && !t.social.length) break; await new Promise(r=>setTimeout(r,300)); }
    const t=RESULT.tepNode._tep, m1=Object.fromEntries(t.metrics.filter(m=>/^spp|^density/.test(m.id)).map(m=>[m.id,m.value])), empty=t.social.length===0, sum=$("tep").querySelector(".resline")?.textContent||"", plotsGone=reserveShown().length===0;
    if (free0===undefined) delete tp.free; else tp.free=free0; RESULT.tepNode._key=null; recompute(true); return JSON.stringify({ same: JSON.stringify(m0)===JSON.stringify(m1), n: Object.keys(m0).length, empty, sum, plotsGone, sk: n0===RESULT.sketch.map(b=>b.floors+":"+Math.round(b.m2)).join() })`);
  const C = JSON.parse(cmp);
  check(C.same && C.n >= 3 && C.empty && C.sk, `T6: СПП и плотность (${C.n} показателей) и корпуса те же с резервом и без него`);
  check(C.empty && /не нужен/.test(C.sum) && C.plotsGone, "T6: когда резерв не нужен, строка «Резерв участков не нужен» и на карте участков нет");
  // «Сохранить слоем»: участки уходят в слой «Эскиз: участки и дворы» с новыми «Вид»; превью второй раз не рисуется
  await p.ev(`const t0=Date.now(); while (Date.now()-t0<15000) { const t=RESULT.tepNode._tep; if (t && t.social && t.social.length && reserveState().plots.length) break; await new Promise(r=>setTimeout(r,300)); } return 1`);
  const bk = await p.ev(`const u0=UNDO.length, keys0=new Set(LYR.map(l=>l.key)), n=reserveState().plots.length; bakeSketch(); await new Promise(r=>setTimeout(r,2500));
    const nk=LYR.map(l=>l.key).filter(k=>!keys0.has(k)), pl=nk.map(k=>DATA[k]).find(d=>d&&/участки и дворы/.test(d.title)), fs=pl?pl.fc.features:[], rk=fs.filter(f=>/^участок (ДОО|школы|поликлиники)$/.test(f.properties["Вид"]));
    const drawn=Object.values(resSrcs).flatMap(s=>s.getFeatures()).filter(f=>/^участок (ДОО|школы|поликлиники)$/.test(f.get("kind"))).length, L=nk.map(k=>LYR.find(l=>l.key===k)).find(l=>l&&/участки и дворы/.test(l.title)), cat=L?L.style.cat.colors:null;
    const out=JSON.stringify({ n, saved: rk.length, places: rk.every(f=>f.properties["Места"]>0 && f.properties["Дефицит"]>0), drawn, colors: !!cat && ["участок ДОО","участок школы","участок поликлиники"].every(k=>cat[k]) });
    removeLayers(nk, "t6"); UNDO.length = u0; delete RESULT.tepNode.properties.reserveBaked; RESULT.tepNode.properties.baked=null; RESULT.tepNode._key=null; return out`);
  const B = JSON.parse(bk);
  check(B.n > 0 && B.saved === B.n && B.places && B.colors, `T6: «Сохранить слоем» кладёт ${B.saved} участков резерва в слой «Эскиз: участки и дворы» с «Вид» = новые виды, «Места» и «Дефицит»`);
  check(B.drawn === 0, "T6: после «Сохранить слоем» превью участков резерва на карте второй раз не рисуется");
  await p.ev(`const w=window.__t6, pn=RESULT.placeNode; graph._nodes.find(n=>n.type==="Параметры/Число").widgets[0].value=w.f; pn.widgets[3].value=w.g; pn.widgets[5].value=w.m; pn._ck=null; recompute(true); await new Promise(r=>setTimeout(r,2500)); return 1`);
};
