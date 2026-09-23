// ГРАДО 2 · сценарии docs/ux/grado2-ux.md в headless-браузере, без интернета: существующее положение подставляется
// синтетическими зданиями, всё остальное — как у владельца (мышь, клавиши, окна). Запуск: tests/test_e2e.py.
const check = (cond, msg) => { if (!cond) throw new Error("не выполнено: " + msg); console.log("ok -", msg); };

export default async p => {
  const box = await p.ev(`const r=$("mMain").getBoundingClientRect(); return [r.left+r.width/2, r.top+r.height/2]`);
  const [cx, cy] = box;
  const poly = async (x, y, s) => { await p.click(x, y); await p.click(x + s, y); await p.click(x + s, y + s); await p.click(x, y + s, { dbl: true, wait: 300 }); };

  // первый запуск: «С чего начать» вместо пустого экрана; F1 — клавиши
  check(await p.ev(`return !$("start").hidden`), "пустой проект показывает «С чего начать»");
  await p.key("F1", "F1", { vk: 112 }); check(await p.ev(`return !$("wKeys").hidden && $("keysBody").innerText.includes("Полилиния") && $("keysBody").innerText.includes("TR")`), "F1 открывает окно клавиш с командами черчения");
  await p.ev(`winOpen("wKeys", false); return 1`);

  // A: слой, два полигона, атрибут, удаление и отмена
  await p.ev(`$("bNewLayer").click(); $("nlName").value = "Кварталы"; $("nlOk").click(); return 1`);
  // «+ Слой» включает полилинию в этот слой; как в AutoCAD, пробел повторяет команду для второго контура
  await poly(cx - 150, cy - 80, 90); await p.key(" ", "Space", { text: " " }); await poly(cx + 20, cy - 80, 90);
  check(await p.ev(`return layerSrc[CUR].getFeatures().length`) === 2, "нарисованы два полигона");
  // рамка с Shift слева направо — оба целиком внутри
  await p.key("Escape", "Escape", { vk: 27 }); await p.drag(cx - 180, cy - 110, cx + 140, cy + 40, { shift: true });
  check(await p.ev(`return SEL.length`) === 2, "рамка выбрала оба полигона");
  const inp = await p.ev(`const i=document.querySelector('[data-battr="Наименование"]'); const b=i.getBoundingClientRect(); return [b.left+20,b.top+8]`);
  await p.click(inp[0], inp[1]); await p.type("Квартал 1"); await p.key("Enter", "Enter", { vk: 13 });
  check(await p.ev(`return layerSrc[CUR].getFeatures().every(f=>f.get("Наименование")==="Квартал 1")`), "общая правка атрибута у двух объектов");
  await p.key("Delete", "Delete", { vk: 46 }); check(await p.ev(`return layerSrc[CUR].getFeatures().length`) === 0, "Del удалил выбранные");
  await p.key("z", "KeyZ", { meta: true }); check(await p.ev(`return layerSrc[CUR].getFeatures().length`) === 2, "Ctrl+Z вернул их");
  await p.key("z", "KeyZ", { meta: true, shift: true }); check(await p.ev(`return layerSrc[CUR].getFeatures().length`) === 0, "Ctrl+Shift+Z снова удалил");
  await p.key("z", "KeyZ", { meta: true });
  // отмена стиля
  check(await p.ev(`const l=lyr(CUR), was=l.style.fill; UIS.rt="style"; renderRight(); document.querySelector('[data-color="fill"]').click(); document.querySelector('.pop [data-c="#e34948"]').click(); const changed=l.style.fill; undo(); return changed==="#e34948" && l.style.fill===was`), "смена заливки отменяется");

  // точное черчение: ввод с клавиатуры, орто, прямоугольник по осям МГГТ, точка по координатам, метка привязки
  const type = async str => { for (const ch of str) await p.key(ch, /[a-z]/i.test(ch) ? "Key" + ch.toUpperCase() : /\d/.test(ch) ? "Digit" + ch : "", { text: ch, wait: 25 }); };
  const enter = () => p.key("Enter", "Enter", { vk: 13, wait: 200 });
  await type("pl"); await enter(); await p.click(cx - 60, cy + 60); await p.move(cx + 60, cy + 60);
  await type("40<0"); await enter(); await type("25<90"); await enter(); await type("@-40;0"); await enter(); await enter();
  check(await p.ev(`const r=layerSrc[CUR].getFeatures().slice(-1)[0].getGeometry().getCoordinates()[0].map(CAD.toM); const e=[]; for(let i=1;i<r.length;i++) e.push(Math.hypot(r[i][0]-r[i-1][0], r[i][1]-r[i-1][1]));
    return r.length===5 && [40,25,40,25].every((v,i)=>Math.abs(e[i]-v)<0.001)`), "полигон 40 × 25 м набран с клавиатуры: стороны точны до миллиметра");
  await p.ev(`setTool("line"); CAD.setOrtho(true); return 1`);
  await p.click(cx + 100, cy - 220); await p.click(cx + 190, cy - 205); await p.click(cx + 200, cy - 150); await enter(); await p.ev(`CAD.setOrtho(false); return 1`);   // клики вдали от других объектов: привязка сильнее орто
  check(await p.ev(`const c=layerSrc[CUR].getFeatures().slice(-1)[0].getGeometry().getCoordinates().map(CAD.toM), a=(p,q)=>Math.atan2(q[1]-p[1],q[0]-p[0])*180/Math.PI; return Math.abs(a(c[0],c[1]))<1e-6 && Math.abs(a(c[1],c[2])+90)<1e-6`), "орто: отрезки строго по оси и под прямым углом");
  await type("rec"); await enter(); await p.click(cx + 60, cy + 40); await type("@30;20"); await enter();
  check(await p.ev(`const g=layerSrc[CUR].getFeatures().slice(-1)[0].getGeometry(), r=(g.getType()==="Polygon"?g.getCoordinates()[0]:g.getCoordinates()).map(CAD.toM); return Math.abs(r[1][0]-r[0][0]-30)<1e-6 && Math.abs(r[2][1]-r[1][1]-20)<1e-6 && Math.abs(r[1][1]-r[0][1])<1e-6`), "прямоугольник @30;20 — ровно по осям МГГТ (в слое линий — замкнутой линией)");
  await type("po"); await enter(); await type("5000;15000"); await enter(); await enter();
  check(await p.ev(`const c=CAD.toM(layerSrc[CUR].getFeatures().slice(-1)[0].getGeometry().getCoordinates()); return Math.abs(c[0]-5000)<1e-4 && Math.abs(c[1]-15000)<1e-4`), "точка по координатам МГГТ 5000;15000");
  await type("l"); await enter(); await p.click(cx - 160, cy + 140); for (let i = 0; i <= 8; i++) await p.move(cx - 100 + i * 5.25, cy + 90 - i * 3.5); await p.sleep(150);
  check(await p.ev(`return CAD.cur()?.k === "end" && /конточка/.test(document.querySelector(".cadtip").innerText) && /[0-9]+,[0-9]{2} м · [0-9]/.test(document.querySelector(".cadtip").innerText)`), "у курсора длина, угол и метка привязки к вершине");
  await p.key("Escape", "Escape", { vk: 27 }); await p.key("Escape", "Escape", { vk: 27 });
  check(await p.ev(`return /^МГГТ X/.test($("stXY").textContent)`), "в строке состояния координаты МГГТ");

  // команды AutoCAD: отрезки по координатам, обрезка, удлинение, подобие, сопряжение, поворот, отслеживание
  await p.ev(`CAD.ST.otrack=false; CAD.ST.polar=false; return 1`);
  for (const [a, b] of [["1000;1000", "1100;1000"], ["1030;980", "1030;1020"], ["1070;980", "1070;1020"]]) { await type("l"); await enter(); await type(a); await enter(); await type(b); await enter(); await enter(); }
  const lines = () => p.ev(`return layerSrc[CUR].getFeatures().filter(f=>f.getGeometry().getType()==="LineString").map(f=>f.getGeometry().getCoordinates().map(CAD.toM).map(q=>q.map(v=>Math.round(v*1000)/1000).join(";")).join(" "))`);
  const at = (x, y) => p.ev(`sharedView.fit(ol.extent.buffer(ol.extent.boundingExtent([CAD.fromM([990,970]),CAD.fromM([1110,1030])]),5)); await new Promise(r=>setTimeout(r,200)); const r=$("mMain").getBoundingClientRect(), q=mMain.getPixelFromCoordinate(CAD.fromM([${x},${y}])); return [Math.round(r.left+q[0]), Math.round(r.top+q[1])]`);
  let q = await at(1050, 1000); await type("tr"); await enter(); await p.click(q[0], q[1] + 1); await enter();
  check((await lines()).filter(l => /^1000;1000 1030;1000$|^1070;1000 1100;1000$/.test(l)).length === 2, "TR: середина отрезка между двумя кромками отрезана, остались два отдельных отрезка");
  q = await at(1027, 1000); await type("ex"); await enter(); await p.click(q[0], q[1] + 1); await enter();
  check((await lines()).includes("1000;1000 1070;1000"), "EX: отрезок удлинён до следующей кромки");
  q = await at(1030, 1010); await type("o"); await enter(); await type("5"); await enter(); await p.click(q[0], q[1]); q = await at(1040, 1010); await p.click(q[0], q[1]); await enter();
  check((await lines()).includes("1035;980 1035;1020"), "O: подобие на 5 м в сторону щелчка");
  await type("f"); await enter(); await type("р"); await enter(); await type("3"); await enter();
  q = await at(1070, 990); await p.click(q[0] + 1, q[1]); q = await at(1085, 1000); await p.click(q[0], q[1] + 1);
  check((await lines()).some(l => l === "1070;980 1070;997") && (await lines()).some(l => l === "1073;1000 1100;1000"), "F: сопряжение радиусом 3 м подрезает оба отрезка и вставляет дугу");
  await p.ev(`setSel(layerSrc[CUR].getFeatures().filter(f=>Math.abs(f.getGeometry().getCoordinates().map(CAD.toM)[0][0]-1035)<1e-6).map(f=>({key:CUR,f}))); return SEL.length`);
  await type("ro"); await enter(); await type("1035;1000"); await enter(); await type("90"); await enter();
  check((await lines()).includes("1055;1000 1015;1000"), "RO: поворот выбранного отрезка на 90° вокруг базовой точки");
  await p.key("z", "KeyZ", { meta: true }); check((await lines()).includes("1035;980 1035;1020"), "Ctrl+Z отменяет поворот");
  // полилиния с дуговым участком, фаска, увеличение, массив, растянуть
  await type("pl"); await enter(); for (const v of ["2000;1000", "2020;1000", "д", "2030;1010", "л", "2030;1030"]) { await type(v); await enter(); } await enter();
  check((await lines()).some(l => l.startsWith("2000;1000 2020;1000") && l.endsWith("2030;1010 2030;1030")), "PL: дуговой участок (Д), касательный к прямому, и снова прямой (Л)");
  for (const [a, b] of [["2100;1000", "2140;1000"], ["2100;1000", "2100;1040"]]) { await type("l"); await enter(); await type(a); await enter(); await type(b); await enter(); await enter(); }
  const at2 = (x, y) => p.ev(`sharedView.fit(ol.extent.buffer(ol.extent.boundingExtent([CAD.fromM([2090,990]),CAD.fromM([2160,1060])]),5)); await new Promise(r=>setTimeout(r,200)); const r=$("mMain").getBoundingClientRect(), q=mMain.getPixelFromCoordinate(CAD.fromM([${x},${y}])); return [Math.round(r.left+q[0]), Math.round(r.top+q[1])]`);
  await type("cha"); await enter(); await type("д"); await enter(); await type("2"); await enter(); await type("3"); await enter();
  q = await at2(2120, 1000); await p.click(q[0], q[1] + 1); q = await at2(2100, 1020); await p.click(q[0] + 1, q[1]);
  check((await lines()).includes("2102;1000 2140;1000") && (await lines()).includes("2100;1003 2100;1040") && (await lines()).includes("2102;1000 2100;1003"), "CHA: фаска 2 × 3 м между двумя отрезками");
  await type("len"); await enter(); await type("в"); await enter(); await type("50"); await enter(); q = await at2(2138, 1000); await p.click(q[0], q[1] + 1); await enter();
  check((await lines()).includes("2102;1000 2152;1000"), "LEN: отрезок доведён до полной длины 50 м");
  await p.ev(`setSel(layerSrc[CUR].getFeatures().filter(f=>{const c=f.getGeometry().getCoordinates().map(CAD.toM); return Math.abs(c[0][0]-2100)<1e-6 && Math.abs(c[c.length-1][1]-1040)<1e-6;}).map(f=>({key:CUR,f}))); return SEL.length`);
  const n0 = await p.ev(`return layerSrc[CUR].getFeatures().length`);
  await type("ar"); await enter(); await enter(); for (const v of ["3", "2"]) { await type(v); await enter(); }
  await type("10"); await p.sleep(100);
  check(await p.ev(`const g=CAD.ghosts(); return g.length===5 && g.some(c=>Math.abs(c[0]-2120)<0.01 && Math.abs(c[1]-1003)<0.01)`), "AR: копии видны призраками ещё до Enter и следуют за набираемым шагом");
  await enter(); await type("60"); await enter();
  check(await p.ev(`return layerSrc[CUR].getFeatures().length`) === n0 + 5 && (await lines()).includes("2120;1063 2120;1100"), "AR: прямоугольный массив 3 × 2 с шагом 10 и 60 м");
  await p.ev(`setSel([]); return 1`); await type("s"); await enter(); for (const v of ["2095;1035", "2105;1045", "2100;1040", "@0;10"]) { await type(v); await enter(); }
  check((await lines()).includes("2100;1003 2100;1050"), "S: секущая рамка захватила верхнюю вершину, растянуто на 10 м");

  // отслеживание: задержка на конце отрезка даёт «+», дальше — пунктирная линия выравнивания
  await p.ev(`CAD.ST.otrack=true; setSel([]); return 1`); await type("l"); await enter(); q = await at(1100, 1025); await p.click(q[0], q[1]);
  const e = await at(1000, 1000); for (let i = 3; i >= 0; i--) await p.move(e[0] + i * 3, e[1] + i * 2); await p.sleep(600);
  for (let i = 1; i <= 6; i++) await p.move(e[0] + 1, e[1] - i * 12); await p.sleep(150);
  // захваченной может оказаться и первая точка отрезка (курсор постоял на ней после щелчка) — как в AutoCAD; важна точка 1000;1000
  check(await p.ev(`const c=CAD.cur(); return CAD.acq().some(a=>Math.hypot(a.w[0]-1000,a.w[1]-1000)<1e-6) && c.k==="track" && Math.abs(c.w[0]-1000)<1e-6`), "ОТСЛЕЖ: после задержки на конечной точке курсор ведётся по пунктирной вертикали через неё");
  // орто при захваченной точке: отслеживание лишь останавливает курсор на оси, отрезок остаётся строго горизонтальным
  await p.key("Escape", "Escape", { vk: 27 }); await p.key("Escape", "Escape", { vk: 27 });
  await p.ev(`CAD.setOrtho(true); return 1`); await type("l"); await enter(); await type("1050;1025"); await enter();
  // под нагрузкой обработчик мыши отстаёт от пауз — перед щелчком ждём, что точка захвачена и курсор ведётся линией
  const until = js => p.ev(`for (let i=0;i<30;i++){ if (${js}) return true; await new Promise(r=>setTimeout(r,100)); } return false`);
  const e2 = await at(1030, 1020); for (let i = 3; i >= 0; i--) await p.move(e2[0] + i * 3, e2[1] + i * 2); await p.sleep(600);
  await until(`CAD.acq().some(a=>Math.hypot(a.w[0]-1030,a.w[1]-1020)<1e-6)`);
  q = await at(1031, 1027); await p.move(q[0] + 6, q[1]); await p.move(q[0], q[1]); await p.sleep(150);
  await until(`CAD.cur()?.k==="track"`);
  await p.click(q[0], q[1]); await enter(); await p.ev(`CAD.setOrtho(false); return 1`);
  if (!(await lines()).some(l => /^1050;1025 /.test(l) && /^1050;1025 1030;1025$/.test(l))) p.log("DBG", JSON.stringify((await lines()).filter(l => /^1050;1025/.test(l))));
  check((await lines()).some(l => /^1050;1025 1030;1025$/.test(l)), "ОРТО + ОТСЛЕЖ: точка на оси там, где её пересекает линия отслеживания, отрезок строго горизонтален");
  // слишком большой выбор: ручек нет, и строка состояния говорит об этом
  await p.ev(`setSel(Array.from({length:1600},(_,i)=>{const f=new ol.Feature(new ol.geom.LineString([CAD.fromM([3000+i,900]),CAD.fromM([3000+i,901])])); layerSrc[CUR].addFeature(f); return {key:CUR,f};})); return 1`);
  check(await p.ev(`return CAD.gripsCut() && /ручки|ручек/.test($("stHint").textContent)`), "Ручки: при слишком большом выборе строка состояния объясняет, почему их нет");
  await p.ev(`SEL.forEach(s=>layerSrc[CUR].removeFeature(s.f)); setSel([]); syncFromSource(CUR); return CAD.gripsCut()`);
  // ручки: выбрать отрезок, щёлкнуть по ручке, ввести новое положение
  await p.ev(`setSel(layerSrc[CUR].getFeatures().filter(f=>{const c=f.getGeometry().getCoordinates().map(CAD.toM); return Math.abs(c[0][0]-1050)<1e-6 && Math.abs(c[0][1]-1025)<1e-6;}).map(f=>({key:CUR,f}))); return SEL.length`);
  q = await at(1030, 1025); await p.click(q[0], q[1]); await type("@0;-5"); await enter();
  check((await lines()).includes("1050;1025 1030;1020"), "ручка: щелчок по вершине выбранного отрезка и @0;-5 — вершина сдвинута ровно на 5 м");
  await p.key("Escape", "Escape", { vk: 27 }); await p.key("Escape", "Escape", { vk: 27 });

  // группы
  check(await p.ev(`const id=newGroup([CUR],"Проект"); grp(id).visible=false; applyOrder(); const hidden=!shown(lyr(CUR)); grp(id).visible=true; applyOrder(); return hidden`), "скрытая группа прячет свои слои");

  // существующее положение: пример территории и синтетические жилые дома вокруг
  await p.ev(`$("bExample").click(); const fs=[]; for (let i=0;i<6;i++) for (let j=0;j<3;j++) { const x=-260+i*90, y=-230+j*170;
      fs.push(turf.polygon([[toLL([x,y]),toLL([x+60,y]),toLL([x+60,y+14]),toLL([x,y+14]),toLL([x,y])]], {"Назначение":"Многоквартирный дом","Этажность":9+(i+j)%8,"Материал стен":"Панельные"})); }
    const fc=turf.featureCollection(fs); DATA["nspd.buildings"]={title:"Здания (ЕГРН)",source:"тест",fetched_at:"2026-09-23",fc,count:fs.length,fields:[]}; layerSrc["nspd.buildings"]=new ol.source.Vector(); setLayerData("nspd.buildings", fc); ensureLayer("nspd.buildings","Здания (ЕГРН)"); dataRev++; return 1`);
  // реестр: снос двух домов
  check(await p.ev(`makeRegister("nspd.buildings"); const fs=layerSrc["nspd.buildings"].getFeatures().slice(0,2); setSel(fs.map(f=>({key:"nspd.buildings",f}))); setDecision("сносим"); return catValues("nspd.buildings","Решение").find(x=>x[0]==="сносим")?.[1]===2`), "реестр: два дома отмечены «сносим»");

  // ограничения: фронт и потолок
  const cons = await p.ev(`await computeConstraints(); return [layerSrc["cons:front"].getFeatures().length, layerSrc["cons:ceiling"].getFeatures().length, graph._nodes.some(n=>n.type==="Данные/Ограничения")]`);
  check(cons[0] > 100 && cons[1] > 100 && cons[2], `ограничения: фронт ${cons[0]} точек, потолок ${cons[1]} клеток, узел в графе`);
  check(await p.ev(`const lay=()=>mMain.getLayers().getArray().find(x=>x.get("key")==="cons:front"), r0=sharedView.getResolution(); sharedView.setResolution(denToRes(5000)); await new Promise(r=>setTimeout(r,200));
    const hidden=!lay().isVisible(); sharedView.setResolution(denToRes(1000)); await new Promise(r=>setTimeout(r,200)); const shownNear=lay().isVisible(); sharedView.setResolution(r0); return hidden && shownNear`), "точки фронта видны только крупнее 1:2500 (видимость по масштабу)");

  // генерация под цель плотности и проверка норм
  const gen = await p.ev(`const pn=RESULT.placeNode; pn.properties.run=true; pn.widgets[5].value="цели плотности"; pn._ck=null; recompute(true); await new Promise(r=>setTimeout(r,3000));
    const t=RESULT.tepNode._tep; await runCheck(null); return [RESULT.sketch.length, t && t.density, t && t.target, window.LASTCHECK.lost, RESULT.sketch.dropped, (RESULT.sketch.plots||[]).filter(g=>g["Причина"]).length, RESULT.placeNode.info]`);
  check(gen[0] > 0 && Math.abs(gen[1] - gen[2]) / gen[2] < .1, `эскиз: ${gen[0]} корпусов, плотность ${gen[1]?.toFixed(1)} при цели ${gen[2]}`);
  p.log(`  убрано под низким потолком: ${gen[4]}; ${gen[6]}`);
  const g15 = await p.ev(`const t=RESULT.tepNode; window.__was=t.widgets[1].value; t.widgets[1].value=15; RESULT.placeNode._ck=null; recompute(true); await new Promise(r=>setTimeout(r,2500));
    const tp=RESULT.tepNode._tep, s=RESULT.sketch, out=[s.length, s.dropped, (s.plots||[]).filter(g=>g["Причина"]).length, tp && tp.density, RESULT.placeNode.info];
    await runCheck(null); out.push(window.LASTCHECK.lost); winOpen("wSketch", true); await new Promise(r=>setTimeout(r,500)); return out`);
  if (process.env.E2E_SHOTS) await p.shot(process.env.E2E_SHOTS + "/g15.png");
  await p.ev(`const t=RESULT.tepNode; winOpen("wSketch", false); t.widgets[1].value=window.__was; RESULT.placeNode._ck=null; recompute(true); await new Promise(r=>setTimeout(r,2500)); return 1`);
  p.log(`  цель 15: ${g15[4]}`);
  check(g15[1] > 0 && g15[1] === g15[2] && Math.abs(g15[3] - 15) / 15 < .1 && g15[5] === 0, `цель 15 набрана и без ${g15[1]} корпусов под низким потолком: их пятна — дворы, плотность ${g15[3]?.toFixed(1)}, соседи не потеряли норму`);
  check(gen[3] === 0, "соседи под потолком не потеряли норму инсоляции");
  check(await p.ev(`const l=lyr("cons:ceiling"); l.visible=false; dataRev++; applyOrder(); recompute(true); await new Promise(r=>setTimeout(r,1500)); const off=RESULT.sketch.reduce((s,b)=>s+b.floors,0); l.visible=true; dataRev++; applyOrder(); recompute(true); await new Promise(r=>setTimeout(r,1500)); return off>0`), "выключенный слой потолка генерация не учитывает");
  check(await p.ev(`winOpen("wVars", true); $("bGen").click(); await new Promise(r=>setTimeout(r,300)); const running=!$("bStopVar").hidden && !$("varProg").hidden;
    $("bStopVar").click(); await new Promise(r=>{const w=setInterval(()=>{ if(!$("bGen").hidden){clearInterval(w);r();}},100);}); winOpen("wVars", false);
    return running && /остановлен/.test($("varMsg").textContent)`), "подбор вариантов идёт с полосой и останавливается «Стоп»");
  check(await p.ev(`const n=graph._nodes.find(n=>n.type==="Данные/Слой"), w=n.widgets[0], was=w.value, long="Охранные зоны объектов культурного наследия федерального значения";
    DATA["user:long"]={title:long,fc:turf.featureCollection([]),count:0,fields:[]}; w.value=long; const shown=w.options.values()[long], empty=w.options.values()[""]; w.value=was; delete DATA["user:long"];
    return shown.endsWith("…") && shown.length < long.length && empty === "—"`), "длинное имя слоя в узле графа обрезается, пустое — «—»");
  await p.ev(`bakeSketch(); return 1`);

  // малоэтажные типологии и урбан-блоки: свои участки, дворы, улицы; этажность до 3; секции квартала — одно здание
  const low = await p.ev(`const pn=RESULT.placeNode, w0=pn.widgets[5].value; pn.widgets[5].value="заданной"; const out={};
    for (const typ of ["ИЖС","Блокированные","Урбан-блоки"]) { pn.widgets[0].value=typ; pn._ck=null; recompute(true); await new Promise(r=>setTimeout(r,300));
      const sk=RESULT.sketch; out[typ]={n:sk.length, plots:(sk.plots||[]).length, streets:(sk.streets||[]).length, maxF:Math.max(...sk.map(b=>b.floors)), grp:new Set(sk.map(b=>b.grp)).size}; }
    await runCheck(null); out.gap=catValues("cons:check","Нарушение").filter(x=>/разрыв/.test(x[0])).length;
    pn.widgets[0].value="Секции"; pn.widgets[5].value=w0; pn._ck=null; recompute(true); return out`);
  check(low["ИЖС"].n > 0 && low["ИЖС"].plots === low["ИЖС"].n && low["ИЖС"].maxF <= 3, `ИЖС: ${low["ИЖС"].n} домов на своих участках, не выше 3 этажей`);
  check(low["Блокированные"].n > 0 && low["Блокированные"].plots > low["Блокированные"].n && low["Блокированные"].maxF <= 3 && low["Блокированные"].streets > 0, `блокированные: ${low["Блокированные"].n} домов, ${low["Блокированные"].plots} участков блоков, проезды`);
  check(low["Урбан-блоки"].n > low["Урбан-блоки"].grp && low["Урбан-блоки"].plots > 0 && low.gap === 0, `урбан-блоки: ${low["Урбан-блоки"].n} секций в ${low["Урбан-блоки"].grp} кварталах, дворы; вплотную стоящие секции квартала — не нарушение разрыва`);

  // виды и листы
  check(await p.ev(`winOpen("wViews", true); await new Promise(r=>setTimeout(r,300)); $("viewName").value="Эскиз"; $("viewSave").click(); return VIEWS.length===1`), "вид сохранён");
  const pdf = await p.ev(`winOpen("wSheets", true); await new Promise(r=>setTimeout(r,300)); $("shAdd").click(); ALBUM.sheets[0].tep=true; const r=await fetch("/api/print/pdf",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(albumSpec(ALBUM.sheets))}); const b=await r.blob(); return [r.status,b.size]`);
  check(pdf[0] === 200 && pdf[1] > 20000, `альбом PDF: ${pdf[1]} байт`);
  // рамка листа на карте: тянется мышью, центр листа запоминается
  await p.ev(`document.querySelector("[data-shframe='0']").click(); await new Promise(r=>setTimeout(r,500)); return 1`);
  const fp = await p.ev(`const e=FRAME.layer.getSource().getFeatures()[0].getGeometry().getExtent(), px=mMain.getPixelFromCoordinate([e[0]+(e[2]-e[0])*.3,(e[1]+e[3])/2]), r=mMain.getTargetElement().getBoundingClientRect(); return [r.left+px[0], r.top+px[1]]`);
  await p.drag(fp[0], fp[1], fp[0] + 80, fp[1] - 40);
  check(await p.ev(`return !!ALBUM.sheets[0].center`), "рамка листа сдвинута мышью, лист запомнил свой центр");
  check(await p.ev(`$("shAdd").click(); await new Promise(r=>setTimeout(r,500)); const sel=document.querySelector("[data-sh='1'] [data-sk='view']"); sel.value="__tep"; sel.dispatchEvent(new Event("change",{bubbles:true}));
    const r=await fetch("/api/print/svg",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...albumSpec([ALBUM.sheets[1]]),index:0})}); const t=await r.text();
    ALBUM.sheets.splice(1,1); winOpen("wSheets", false); await new Promise(r=>setTimeout(r,50)); return r.status===200 && t.includes("Плотность") && !FRAME`), "лист «Таблица ТЭП» собирается; закрытое окно убирает рамку с карты");

  // проект: сохранить, новый, открыть — слои, группы, виды, альбом на месте; файл старой версии открывается
  const round = await p.ev(`await saveProject("e2e"); newProject(); newProject(); await openProject("e2e"); await new Promise(r=>setTimeout(r,1500)); return [LYR.length, GROUPS.length, VIEWS.length, ALBUM.sheets.length]`);
  check(round[0] > 3 && round[1] >= 1 && round[2] === 1 && round[3] === 1, `проект открылся: слоёв ${round[0]}, групп ${round[1]}, видов ${round[2]}, листов ${round[3]}`);
  check(await p.ev(`const v1={format:"grado2",version:1,layers:[{key:"user:a",title:"A",geom:"poly",visible:true,style:{}}],data:{"user:a":{title:"A",fc:{type:"FeatureCollection",features:[]}}},graph:null};
    applyProject(v1); return LYR.length===1 && GROUPS.length===0 && ALBUM.sheets.length===0`), "проект формата 1 открывается миграцией");
  check(await p.ev(`try { applyProject({format:"grado2",version:99}); return false; } catch (e) { return /новой версией/.test(e.message); }`), "файл новее программы не открывается, с понятной причиной");

  // крупный слой: 100 000 объектов — выбор всего и отмена правки
  const big = await p.ev(`const n=100000, side=Math.ceil(Math.sqrt(n)), d=0.00018, fs=[]; for(let i=0;i<n;i++){ const x=37.50+(i%side)*d, y=55.78+Math.floor(i/side)*d*0.56; fs.push({type:"Feature",geometry:{type:"Polygon",coordinates:[[[x,y],[x+d*.7,y],[x+d*.7,y+d*.4],[x,y+d*.4],[x,y]]]},properties:{"N":i}}); }
    const key="import:big"; DATA[key]={title:"100k",source:"t",fetched_at:"x",fc:{type:"FeatureCollection",features:fs},count:0,fields:[]}; layerSrc[key]=new ol.source.Vector(); setLayerData(key, DATA[key].fc); const l=ensureLayer(key,"100k","poly"); CUR=key;
    const t0=performance.now(); selectAll(); const ms=performance.now()-t0; const f=SEL[0].f, was=f.get("N"); pushUndo(featRec([SEL[0]],"x")); f.set("N",-1); syncFromSource(key); undo(); return [l.gl, SEL.length, Math.round(ms), f.get("N") === was]`);
  check(big[0] && big[1] === 100000 && big[3], `100 000 объектов: видеокарта ${big[0]}, выбрано ${big[1]} за ${big[2]} мс, отмена правки`);
};
