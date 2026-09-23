// ГРАДО 2 · сценарии docs/ux/grado2-ux.md в headless-браузере, без интернета: существующее положение подставляется
// синтетическими зданиями, всё остальное — как у владельца (мышь, клавиши, окна). Запуск: tests/test_e2e.py.
const check = (cond, msg) => { if (!cond) throw new Error("не выполнено: " + msg); console.log("ok -", msg); };

export default async p => {
  const box = await p.ev(`const r=$("mMain").getBoundingClientRect(); return [r.left+r.width/2, r.top+r.height/2]`);
  const [cx, cy] = box;
  const poly = async (x, y, s) => { await p.click(x, y); await p.click(x + s, y); await p.click(x + s, y + s); await p.click(x, y + s, { dbl: true, wait: 300 }); };

  // первый запуск: «С чего начать» вместо пустого экрана; F1 — клавиши
  check(await p.ev(`return !$("start").hidden`), "пустой проект показывает «С чего начать»");
  await p.key("F1", "F1", { vk: 112 }); check(await p.ev(`return !$("wKeys").hidden && $("keysBody").innerText.includes("Полигон")`), "F1 открывает окно клавиш");
  await p.ev(`winOpen("wKeys", false); return 1`);

  // A: слой, два полигона, атрибут, удаление и отмена
  await p.ev(`$("bNewLayer").click(); $("nlName").value = "Кварталы"; $("nlOk").click(); return 1`);
  await poly(cx - 150, cy - 80, 90); await poly(cx + 20, cy - 80, 90);
  check(await p.ev(`return layerSrc[CUR].getFeatures().length`) === 2, "нарисованы два полигона");
  // рамка с Shift слева направо — оба целиком внутри
  await p.key("v", "KeyV"); await p.drag(cx - 180, cy - 110, cx + 140, cy + 40, { shift: true });
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
    const t=RESULT.tepNode._tep; await runCheck(null); return [RESULT.sketch.length, t && t.density, t && t.target, window.LASTCHECK.lost]`);
  check(gen[0] > 0 && Math.abs(gen[1] - gen[2]) / gen[2] < .1, `эскиз: ${gen[0]} корпусов, плотность ${gen[1]?.toFixed(1)} при цели ${gen[2]}`);
  check(gen[3] === 0, "соседи под потолком не потеряли норму инсоляции");
  check(await p.ev(`const l=lyr("cons:ceiling"); l.visible=false; dataRev++; applyOrder(); recompute(true); await new Promise(r=>setTimeout(r,1500)); const off=RESULT.sketch.reduce((s,b)=>s+b.floors,0); l.visible=true; dataRev++; applyOrder(); recompute(true); await new Promise(r=>setTimeout(r,1500)); return off>0`), "выключенный слой потолка генерация не учитывает");
  check(await p.ev(`winOpen("wVars", true); $("bGen").click(); await new Promise(r=>setTimeout(r,300)); const running=!$("bStopVar").hidden && !$("varProg").hidden;
    $("bStopVar").click(); await new Promise(r=>{const w=setInterval(()=>{ if(!$("bGen").hidden){clearInterval(w);r();}},100);}); winOpen("wVars", false);
    return running && /остановлен/.test($("varMsg").textContent)`), "подбор вариантов идёт с полосой и останавливается «Стоп»");
  check(await p.ev(`const n=graph._nodes.find(n=>n.type==="Данные/Слой"), w=n.widgets[0], was=w.value, long="Охранные зоны объектов культурного наследия федерального значения";
    DATA["user:long"]={title:long,fc:turf.featureCollection([]),count:0,fields:[]}; w.value=long; const shown=w.options.values()[long], empty=w.options.values()[""]; w.value=was; delete DATA["user:long"];
    return shown.endsWith("…") && shown.length < long.length && empty === "—"`), "длинное имя слоя в узле графа обрезается, пустое — «—»");
  await p.ev(`bakeSketch(); return 1`);

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
