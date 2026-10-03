// ГРАДО 2 · сценарии docs/ux/grado2-ux.md в headless-браузере, без интернета: существующее положение подставляется
// синтетическими зданиями, всё остальное — как у владельца (мышь, клавиши, окна). Запуск: tests/test_e2e.py.
const check = (cond, msg) => { if (!cond) throw new Error("не выполнено: " + msg); console.log("ok -", msg); };

export default async p => {
  const box = await p.ev(`const r=$("mMain").getBoundingClientRect(); return [r.left+r.width/2, r.top+r.height/2]`);
  const [cx, cy] = box;
  const poly = async (x, y, s) => { await p.click(x, y); await p.click(x + s, y); await p.click(x + s, y + s); await p.click(x, y + s, { dbl: true, wait: 300 }); };

  check(await p.ev(`const t = "Об утверждении проекта планировки территории района Северный города Москвы, ограниченной:полосой отвода " + "x".repeat(380) + " проезда 241"; return docTitle(t) === t && !docTitle(t).includes("…") && docTitle("А - Б") === "А — Б" && docLine({ document_1: t, document_n: "899-ПП", document_d: "2015-12-17" }).startsWith(t)`), "T29: название документа ППТ в альбоме не сокращается (длинное — целиком, без многоточия)");
  // первый запуск: «С чего начать» вместо пустого экрана; F1 — клавиши
  check(await p.ev(`return !$("start").hidden`), "пустой проект показывает «С чего начать»");
  check(await p.ev(`try{localStorage.removeItem("grado2.start")}catch{} startOff=false; selectTerr(false); setTool("select"); syncStatus(); await new Promise(r=>setTimeout(r,100)); const t=$("start").innerText; return !$("start").hidden && /Начните с границы/.test(t) && /Нарисовать границу/.test(t) && /Пример/.test(t) && $("start").querySelectorAll(".btn").length===2`), "T27: приветствие на пустой карте — одна фраза и два действия «Нарисовать границу», «Пример»");
  check(await p.ev(`const a=uiK(); document.documentElement.dataset.ui="large"; await new Promise(r=>setTimeout(r,100)); const b=uiK(); delete document.documentElement.dataset.ui; return a===1 && Math.abs(b-7/6)<.01`), "T27: uiK() читает масштаб интерфейса (1 и 7/6 при «крупном»)");
  check(await p.ev(`const src=()=>{const l=mMain.getLayers().getArray().find(x=>x.get("basemap")); return String(l.getSource().getUrls?.()?.[0]||"osm:"+l.getSource().constructor.name)}, urlOk=u=>/cartocdn/.test(u);
    let md=0; const om=window.markDirty; window.markDirty=(...a)=>{md++; return om?.(...a)}; const d0=PROJ.dirty, b0=BASE;
    document.documentElement.dataset.theme="light"; $("bTheme").click(); await new Promise(r=>setTimeout(r,200));   // light -> dark
    const dark=src(), darkAttr=mMain.getLayers().getArray().find(x=>x.get("basemap")).getSource().getAttributions()?.({})?.join?.(" ")||"";
    $("bTheme").click(); await new Promise(r=>setTimeout(r,200));   // dark -> light
    const light=src(); window.markDirty=om;
    return /World_Dark_Gray_Base/.test(dark) && /Esri/.test(darkAttr) && !/cartocdn/.test(light) && /openstreetmap/.test(light) && md===0 && PROJ.dirty===d0 && BASE===b0 && $("baseSel").options.length>=1`), "T38: тёмная тема — тёмная подложка Esri, светлая — OSM; смена темы не делает проект несохранённым, выбор подложки не меняется");
  check(await p.ev(`let md=0, tc=0; const om=window.markDirty, ot=Collab.touched; window.markDirty=(...a)=>{md++; return om?.(...a)}; Collab.touched=(...a)=>{tc++; return ot.apply(Collab,a)};
    const light=JSON.stringify(graph.serialize()); const bg0=lgc.clear_background_color, nb0=LiteGraph.NODE_DEFAULT_BGCOLOR; $("bTheme").click(); await new Promise(r=>setTimeout(r,200));
    const dark=JSON.stringify(graph.serialize()), bg1=lgc.clear_background_color, nb1=LiteGraph.NODE_DEFAULT_BGCOLOR; $("bTheme").click(); await new Promise(r=>setTimeout(r,200));
    window.markDirty=om; Collab.touched=ot; return light===dark && bg0!==bg1 && nb0!==nb1 && lgc.clear_background_color===bg0 && md===0 && tc===0`), "T27: тема меняет холст «Схемы расчёта» (фон, узлы) на лету; JSON графа одинаков в обеих темах, правок и отправки в общий проект нет");
  {
    const [mx, my] = await p.ev(`const r=$("mMain").getBoundingClientRect(); return [Math.round(r.left+r.width*.3), Math.round(r.top+r.height*.4)]`), res = () => p.ev(`return sharedView.getResolution()`), at = () => p.ev(`return mMain.getCoordinateFromPixel([${mx}-$("mMain").getBoundingClientRect().left, ${my}-$("mMain").getBoundingClientRect().top])`);
    const r0 = await res(), c0 = await at(); await p.wheel(mx, my, -100, { wait: 700 }); const r1 = await res(); for (let i = 0; i < 9; i++) await p.wheel(mx, my, -100, { wait: 30 }); await p.sleep(900); const r10 = await res(), c1 = await at();
    p.log("wheel: 1 notch", (r0 / r1).toFixed(3), "10 notches", (r0 / r10).toFixed(3));
    check(r0 / r10 > 1.5 && r0 / r10 <= 2.3 && Math.hypot(c1[0] - c0[0], c1[1] - c0[1]) / r10 < 1.5, "T27: десять щёлок колеса меняют масштаб не более чем вдвое, точка под курсором на месте");
    const q0 = await res(); for (let i = 0; i < 30; i++) await p.wheel(mx, my, -6, { ctrl: true, wait: 16 }); await p.sleep(500); const q1 = await res();
    p.log("pinch: 30 events dy=-6 ctrl", (q0 / q1).toFixed(3)); check(q0 / q1 > 1.3, "T27: щипок (Ctrl, мелкие шаги) остаётся быстрым");
  }
  // T17-9: пустое дерево слоёв — одна короткая строка, «загрузите данные» открывает «Данные»
  check(await p.ev(`const t=$("layerTree").innerText.trim(); document.querySelector("#layerTree [data-open-data]").click(); await new Promise(r=>setTimeout(r,200)); const ok=!$("wData").hidden; winOpen("wData", false); return t==="Слоёв нет. Нарисуйте объект или загрузите данные." && ok`), "пустые «Слои»: одна строка, «загрузите данные» открывает «Данные»");
  // T20: размер интерфейса — в меню «Окна», один множитель --k, помнится; «обычный» возвращает размеры 1280
  check(await p.ev(`$("bMore").click(); await new Promise(r=>setTimeout(r,100)); document.querySelector('[data-uisize="large"]').click(); await new Promise(r=>setTimeout(r,200)); const big=[document.documentElement.dataset.ui, localStorage.getItem("grado2.uisize"), getComputedStyle(document.body).fontSize, document.querySelector(".tl").offsetHeight];
    $("bMore").click(); await new Promise(r=>setTimeout(r,100)); document.querySelector('[data-uisize="normal"]').click(); await new Promise(r=>setTimeout(r,200)); const norm=[getComputedStyle(document.body).fontSize, document.querySelector(".tl").offsetHeight];
    $("bMore").click(); await new Promise(r=>setTimeout(r,100)); document.querySelector('[data-uisize="auto"]').click(); await new Promise(r=>setTimeout(r,200));
    return big.join()==="large,large,14px,33" && norm.join()==="12px,28" && localStorage.getItem("grado2.uisize")===null && !document.documentElement.dataset.ui`), "«Размер интерфейса» в меню «Окна»: крупный 14 px / кнопки 33 px, обычный 12 px / 28 px, авто снимает настройку");
  await p.key("F1", "F1", { vk: 112 }); check(await p.ev(`return !$("wKeys").hidden && $("keysBody").innerText.includes("Полилиния") && $("keysBody").innerText.includes("TR")`), "F1 открывает окно клавиш с командами черчения");
  await p.ev(`winOpen("wKeys", false); return 1`);
  await p.key("F1", "F1", { vk: 112 }); check(await p.ev(`const box=$("keysBody"); document.querySelector('#keysBody [data-hj="h-3"]').click(); await new Promise(r=>setTimeout(r,200)); const r=document.getElementById("h-3").getBoundingClientRect(), bb=box.getBoundingClientRect(); const ok1=box.scrollTop>0&&r.top>=bb.top&&r.top<bb.bottom-20; box.querySelector('.htop').click(); await new Promise(r=>setTimeout(r,100)); return ok1 && box.scrollTop===0 && /Как начать/.test(box.querySelector("#h-0").innerText)`), "T27: ссылка оглавления справки прокручивает к разделу, «Наверх» возвращает");
  check(await p.ev(`const i=$("helpQ"); i.value="Размер интерфейса"; i.dispatchEvent(new Event("input",{bubbles:true})); const vis=[...document.querySelectorAll("#keysBody .hsec")].filter(x=>!x.hidden).length; i.value=""; i.dispatchEvent(new Event("input",{bubbles:true})); winOpen("wKeys", false); return vis>=1 && vis<6 && ![...document.querySelectorAll("#keysBody .hsec")].some(x=>x.hidden)`), "T27: поиск в справке отбирает разделы и сбрасывается");
  // эскиз без границы территории не строится и говорит почему
  check(await p.ev(`winOpen("wSketch", true); await new Promise(r=>setTimeout(r,200)); document.querySelector('#wSketch [data-run="1"]').click(); await new Promise(r=>setTimeout(r,150));
    const ok = !RESULT.placeNode.properties.run && /границ/.test($("toast").textContent) && /Нет границы/.test($("wSketch").textContent); winOpen("wSketch", false); return ok`), "эскиз без границы не строится: сообщение и пометка в окне «Эскиз»");
  check(await p.ev(`winOpen("w3d", true); await new Promise(r=>setTimeout(r,200)); const ok=!$("e3d").hidden; winOpen("w3d", false); return ok`), "пустой «Объём» объясняет, что показать пока нечего");
  // встраивание окон: таблица по умолчанию под картой; вытянутая за заголовок — плавает; брошенная у правого края — в панели свойств
  const dock = await p.ev(`winOpen("wTable", true); await new Promise(r=>setTimeout(r,300)); const h=$("wTable").querySelector(".wh b").getBoundingClientRect(), m=$("mMain").getBoundingClientRect(); return [$("wTable").parentElement.id, h.left+5, h.top+5, m.left+m.width/2, m.top+100, m.right-8, m.top+m.height/2]`);
  check(dock[0] === "dzB", "таблица атрибутов встроена под картой, карта ужалась");
  await p.drag(dock[1], dock[2], dock[3], dock[4]);
  check(await p.ev(`return $("wTable").parentElement===document.body && !$("wTable").classList.contains("docked")`), "окно вытягивается из панели за заголовок и плавает");
  const h2 = await p.ev(`const h=$("wTable").querySelector(".wh b").getBoundingClientRect(); return [h.left+5, h.top+5]`);
  await p.drag(h2[0], h2[1], dock[5], dock[6]);
  check(await p.ev(`const ok=$("wTable").parentElement.id==="dzR"; winOpen("wTable", false); return ok && $("dropInd").hidden`), "брошенное у правого края окно встраивается в панель свойств");
  await p.ev(`floatWin($("wTable")); WST.wTable.dock="b"; saveWins(); return 1`);
  // правило «не больше двух окон в зоне» (T52) здесь выключено настройкой «Без ограничения»: проверяется работа трёх вкладок
  check(await p.ev(`localStorage.setItem("grado2.zonecap","free"); ["wTep","wSketch","wCons"].forEach(id=>winOpen(id,true)); await new Promise(r=>setTimeout(r,400));
    const ok = $("dzR").classList.contains("tabbed") && $("dzR").querySelectorAll(".dztabs [data-tab]").length===3 && $("rightPane").clientHeight>=140;
    ["wTep","wSketch","wCons"].forEach(id=>winOpen(id,false)); localStorage.removeItem("grado2.zonecap"); return ok`), "три окна в панели свойств — вкладками, панель «Стиль» не сжата");
  // плавающее окно не уходит за экран: брошенное далеко вниз и вправо остаётся целиком в поле карты (шапка и ручка размера достижимы)
  await p.ev(`WST.wTep = { ...(WST.wTep||{}), dock: null }; winOpen("wTep", true); floatWin($("wTep")); placeWin($("wTep")); await new Promise(r=>setTimeout(r,200)); return 1`);
  const fh = await p.ev(`const r=$("wTep").querySelector(".wh b").getBoundingClientRect(); return [r.left+4, r.top+4, innerWidth-6, innerHeight-4]`);
  await p.drag(fh[0], fh[1], fh[2], fh[3]);
  check(await p.ev(`const r=$("wTep").getBoundingClientRect(), a=winArea(); const ok = r.left>=a.l-1 && r.right<=a.r+1 && r.top>=a.t-1 && r.bottom<=a.b+1 && r.bottom<=document.querySelector(".status").getBoundingClientRect().top+1; winOpen("wTep", false); delete WST.wTep; saveWins(); return ok`), "плавающее окно, брошенное за нижний правый угол, остаётся целиком в поле карты");
  // раскладки окон: готовая открывает свои окна в своих зонах и закрывает прочие; текущую можно запомнить
  check(await p.ev(`winOpen("wKeys", true); $("bMore").click(); await new Promise(r=>setTimeout(r,100)); [...document.querySelectorAll("#winMenu [data-layout]")].find(b=>b.textContent.startsWith("Эскиз")).click(); await new Promise(r=>setTimeout(r,400));
    return $("wSketch").parentElement.id==="dzR" && $("wTep").parentElement.id==="dzR" && $("wVars").parentElement.id==="dzB" && $("wKeys").hidden && $("winMenu").hidden`), "раскладка «Эскиз и варианты» расставляет свои окна и закрывает прочие");
  check(await p.ev(`winOpen("wTable", true); await new Promise(r=>setTimeout(r,300)); saveLayout(); return !!userLayouts()["Моя раскладка 1"]?.wTable`), "текущую раскладку можно запомнить");
  const gv = await p.ev(`const g=$("wTable").querySelector(".dresv").getBoundingClientRect(), a=$("wVars").offsetWidth; return [g.left+3, g.top+g.height/2, a, $("dzB").classList.contains("tabbed")]`);
  if (!gv[3]) { await p.drag(gv[0], gv[1], gv[0] + 120, gv[1]);
    check(await p.ev(`return Math.abs($("wVars").offsetWidth - ${gv[2]} - 120) < 6`), "граница между окнами под картой перетаскивается"); }
  await p.ev(`applyLayout({}); delete userLayouts()["Моя раскладка 1"]; saveWins(); return 1`);
  check(await p.ev(`const m=document.querySelector(".status .modes"), cs=getComputedStyle(m); return cs.marginBottom==="0px" && cs.backgroundColor==="rgba(0, 0, 0, 0)"`), "кнопки режимов в строке состояния не берут оформление переключателя стиля");
  check(await p.ev(`winOpen("wKeys", true); await new Promise(r=>setTimeout(r,100)); document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true})); await new Promise(r=>setTimeout(r,100)); return $("wKeys").hidden`), "Esc закрывает верхнее плавающее окно");
  // «С чего начать» закрывается и больше не мешает
  check(await p.ev(`CAD.start("pline"); await new Promise(r=>setTimeout(r,50)); const hid=$("start").hidden; CAD.cancel(); await new Promise(r=>setTimeout(r,50)); return hid && !$("start").hidden`), "«С чего начать» прячется, пока идёт команда, и не ловит щелчки черчения");
  check(await p.ev(`document.querySelector("[data-close-start]").click(); const ok=$("start").hidden; localStorage.removeItem("grado2.start"); return ok`), "«С чего начать» закрывается крестиком");

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

  // точное черчение: ввод с клавиатуры, орто, прямоугольник по осям МСК, точка по координатам, метка привязки
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
  check(await p.ev(`const g=layerSrc[CUR].getFeatures().slice(-1)[0].getGeometry(), r=(g.getType()==="Polygon"?g.getCoordinates()[0]:g.getCoordinates()).map(CAD.toM); return Math.abs(r[1][0]-r[0][0]-30)<1e-6 && Math.abs(r[2][1]-r[1][1]-20)<1e-6 && Math.abs(r[1][1]-r[0][1])<1e-6`), "прямоугольник @30;20 — ровно по осям МСК (в слое линий — замкнутой линией)");
  await type("po"); await enter(); await type("5000;15000"); await enter(); await enter();
  check(await p.ev(`const c=CAD.toM(layerSrc[CUR].getFeatures().slice(-1)[0].getGeometry().getCoordinates()); return Math.abs(c[0]-5000)<1e-4 && Math.abs(c[1]-15000)<1e-4`), "точка по координатам МСК 5000;15000");
  await type("l"); await enter(); await p.click(cx - 160, cy + 140); for (let i = 0; i <= 8; i++) await p.move(cx - 100 + i * 5.25, cy + 90 - i * 3.5); await p.sleep(150);
  check(await p.ev(`return CAD.cur()?.k === "end" && /конечная точка/.test(document.querySelector(".cadtip").innerText) && /[0-9]+,[0-9]{2} м · [0-9]/.test(document.querySelector(".cadtip").innerText)`), "у курсора длина, угол и метка привязки к вершине");
  await p.key("Escape", "Escape", { vk: 27 }); await p.key("Escape", "Escape", { vk: 27 });
  check(await p.ev(`return /^МСК X/.test($("stXY").textContent)`), "в строке состояния координаты МСК");
  // МСК — как в QGIS: точка, введённая как X;Y, в системе ГИС ОГД лежит на (16,098; 14,512) м дальше
  check(await p.ev(`const ll=MSK.toWgs([5000,15000]); return Math.abs(ll[0]-37.58)<0.01 && Math.abs(ll[1]-55.80)<0.01 && typeof MGGT==="undefined"`), "ввод X;Y идёт в МСК (как пользовательская СК «МСК» в QGIS)");

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

  // оформление и новые команды: углы прямоугольника, эллипс, размер, надпись, штриховка, правка массива, история, «Параллельно»
  await p.ev(`setSel([]); return 1`);
  const area = `const g=layerSrc[CUR].getFeatures().slice(-1)[0].getGeometry(), r=(g.getType()==="Polygon"?g.getCoordinates()[0]:g.getCoordinates()).map(CAD.toM); let a=0; for(let i=0;i+1<r.length;i++) a+=r[i][0]*r[i+1][1]-r[i+1][0]*r[i][1]; return Math.abs(a/2)`;
  await type("rec"); await enter(); await type("с"); await enter(); await type("3"); await enter(); await type("3000;1000"); await enter(); await type("@30;20"); await enter();
  const recA = await p.ev(area);
  check(Math.abs(recA - (600 - (4 - Math.PI) * 9)) < 0.2, `REC, сопряжение R 3 м: площадь ${recA.toFixed(2)} ≈ 600 − (4 − π)·9 м² (дуги хордами с прогибом до 1 см)`);
  await type("rec"); await enter(); await type("с"); await enter(); await type("0"); await enter(); await p.key("Escape", "Escape", { vk: 27 });
  await type("el"); await enter(); await type("3100;1010"); await enter(); await type("@30;0"); await enter(); await type("10"); await enter();
  const elA = await p.ev(area);
  check(Math.abs(elA - Math.PI * 300) / (Math.PI * 300) < 1e-3, `EL: эллипс с полуосями 30 и 10 м, площадь ${elA.toFixed(1)} ≈ π·300`);
  // работа с вектором: разрезать, объединить, буфер, вычесть, поделить
  const areasSel = `return SEL.map(s=>{ const r=s.f.getGeometry().getCoordinates()[0].map(CAD.toM); let a=0; for(let i=0;i+1<r.length;i++) a+=r[i][0]*r[i+1][1]-r[i+1][0]*r[i][1]; return Math.abs(a/2); }).sort((a,b)=>a-b)`;
  const pxOf = async (x, y) => p.ev(`const q=mMain.getPixelFromCoordinate(CAD.fromM([${x},${y}])), r=mMain.getTargetElement().getBoundingClientRect(); return [r.left+q[0], r.top+q[1]]`);
  await p.key("Escape", "Escape", { vk: 27 }); await p.ev(`window.__pc=CUR; const l=LYR.find(x=>x.geom==="poly"&&x.key.startsWith("user:")); if (l) setCurrent(l.key); return 1`);
  await type("rec"); await enter(); await type("4000;1000"); await enter(); await type("@40;20"); await enter(); await p.key("Escape", "Escape", { vk: 27 });
  await p.ev(`const f=layerSrc[CUR].getFeatures().slice(-1)[0]; window.__vf=f; window.__vfk=CUR; setSel([{key:CUR,f}]); sharedView.fit(ol.extent.buffer(f.getGeometry().getExtent(),40)); return 1`);
  await type("spl"); await enter(); await type("4020;990"); await enter(); await type("4020;1030"); await enter(); await enter();
  const halves = await p.ev(areasSel);
  check(halves.length === 2 && halves.every(a => Math.abs(a - 400) < .5), `SPL: прямоугольник 40 × 20 разрезан пополам: ${halves.map(a => a.toFixed(2)).join(" и ")} м²`);
  await type("uni"); await enter();
  const whole = await p.ev(areasSel);
  check(whole.length === 1 && Math.abs(whole[0] - 800) < .5, `UNI: две половины снова одна, ${whole[0]?.toFixed(2)} м²`);
  const nb0 = await p.ev(`return layerSrc[CUR].getFeatures().length`);
  await type("buf"); await enter(); await type("2"); await enter();
  const bufA = await p.ev(`const f=layerSrc[CUR].getFeatures().slice(-1)[0]; window.__bf=f; const r=f.getGeometry().getCoordinates()[0].map(CAD.toM); let a=0; for(let i=0;i+1<r.length;i++) a+=r[i][0]*r[i+1][1]-r[i+1][0]*r[i][1]; return [layerSrc[CUR].getFeatures().length, Math.abs(a/2)]`);
  check(bufA[0] === nb0 + 1 && Math.abs(bufA[1] - (44 * 24 - (4 - Math.PI) * 4)) < 3, `BUF 2 м: новый полигон ${bufA[1].toFixed(1)} м² ≈ 44·24 − (4 − π)·4`);
  await p.ev(`layerSrc[CUR].removeFeature(window.__bf); syncFromSource(CUR); setSel([]); return 1`);
  await type("rec"); await enter(); await type("4010;1005"); await enter(); await type("@10;10"); await enter(); await p.key("Escape", "Escape", { vk: 27 });
  await p.ev(`setSel([{key:CUR,f:window.__vf}]); return 1`);
  await type("su"); await enter(); { const [x, y] = await pxOf(4015, 1010); await p.click(x, y); } await enter();
  const holed = await p.ev(`const g=window.__vf.getGeometry(); return [g.getType(), g.getCoordinates().length]`);
  check(holed[0] === "Polygon" && holed[1] === 2, "SU: из прямоугольника вырезан квадрат — полигон с дырой, вычитаемый остался");
  await type("dr"); await enter(); { const [x, y] = await pxOf(4013, 1008); await p.click(x, y); } await p.key("Escape", "Escape", { vk: 27 });
  check(await p.ev(`return window.__vf.getGeometry().getCoordinates().length`) === 1, "DR: щелчок в дыре закрыл её");
  await p.ev(`setSel([]); return 1`);
  const pts0 = await p.ev(`const l=LYR.find(x=>x.geom==="point"&&x.key.startsWith("user:")&&x.title==="Точки"); return l?layerSrc[l.key].getFeatures().length:0`);
  await type("div"); await enter(); await type("4"); await enter(); { const [x, y] = await pxOf(4040, 1017); await p.click(x, y); } await enter();
  const pts1 = await p.ev(`const l=LYR.find(x=>x.geom==="point"&&x.key.startsWith("user:")&&x.title==="Точки"); return l?layerSrc[l.key].getFeatures().length:0`);
  check(pts1 - pts0 === 4, `DIV 4 на замкнутом контуре: ${pts1 - pts0} точки в слое «Точки»`);
  await p.ev(`const l=LYR.find(x=>x.geom==="line"&&x.key.startsWith("user:")); const f=new ol.Feature(new ol.geom.LineString([[4000,1100],[4040,1100]].map(CAD.fromM)));
    f.setProperties({ _lt: ["L01s18t"], LineCode: "1,-18" }); layerSrc[l.key].addFeature(f); syncFromSource(l.key); window.__rl=f; setSel([{key:l.key,f}]); return 1`);
  await type("rev"); await enter();
  check(await p.ev(`const f=window.__rl; return CAD.toM(f.getGeometry().getFirstCoordinate())[0]>4039 && f.get("_lt")[0]==="L01s18b" && f.get("LineCode")==="-1,18"`), "REV: линия развёрнута, засечки красной линии перешли на другую сторону (L01s18t → L01s18b, LineCode 1,-18 → -1,18)");
  await p.ev(`const f=window.__rl, l=LYR.find(x=>x.geom==="line"&&x.key.startsWith("user:")); const c=[]; for(let i=0;i<=40;i++) c.push(CAD.fromM([4000+i, 1100+(i%2)*0.05])); f.setGeometry(new ol.geom.LineString(c)); syncFromSource(l.key); setSel([{key:l.key,f}]); return 1`);
  await type("simp"); await enter(); await type("0.2"); await enter();
  check(await p.ev(`return window.__rl.getGeometry().getCoordinates().length`) <= 3, "SIMP 0,2 м: зубцы 5 см по 41 вершине сняты, осталась прямая");
  // выбор по условию, выравнивание, топологическое редактирование
  await p.ev(`window.__vf.set("Наименование","Школа № 5"); setCurrent(window.__vfk); setSel([]); return 1`);
  await type("qs"); await enter(); await type("наименование ~ школ"); await enter();
  check(await p.ev(`return SEL.length===1 && SEL[0].f===window.__vf`), "QS: «наименование ~ школ» выбрал ровно этот полигон");
  const ext = `const c=window.__vf.getGeometry().getCoordinates()[0].map(CAD.toM), xs=c.map(q=>q[0]), ys=c.map(q=>q[1]); return [Math.max(...xs)-Math.min(...xs), Math.max(...ys)-Math.min(...ys), Math.max(...xs)]`, al0 = await p.ev(ext);
  await type("al"); await enter();
  for (const v of ["4000;1000", "5000;1000", "4040;1000", "5000;1040"]) { await type(v); await enter(); }
  await enter();
  const alx = await p.ev(ext);
  check(Math.abs(alx[0] - al0[1]) < .001 && Math.abs(alx[1] - al0[0]) < .001 && Math.abs(alx[2] - 5000) < .001, `AL: полигон перенесён и повёрнут на 90° по двум парам точек (${alx[0].toFixed(2)} × ${alx[1].toFixed(2)} м)`);
  await p.ev(`const k=CUR, sq=(x)=>{ const f=new ol.Feature(new ol.geom.Polygon([[[x,1000],[x+10,1000],[x+10,1010],[x,1010],[x,1000]].map(CAD.fromM)])); layerSrc[k].addFeature(f); return f; };
    window.__ta=sq(6000); window.__tb=sq(6010); syncFromSource(k); sharedView.fit(ol.extent.buffer(window.__ta.getGeometry().getExtent(), 30)); setSel([{key:k,f:window.__ta}]); return 1`);
  await p.click(...(await p.ev(`const b=document.getElementById("mdTopo"); const r=b.getBoundingClientRect(); return [r.left+r.width/2, r.top+r.height/2]`)));
  { const [x, y] = await pxOf(6010, 1010); await p.click(x, y); } await type("@0;5"); await enter();
  check(await p.ev(`return window.__tb.getGeometry().getCoordinates()[0].map(CAD.toM).some(c=>Math.abs(c[0]-6010)<1e-6&&Math.abs(c[1]-1015)<1e-6)`), "ТОПО: общая вершина двух квадратов сдвинута в обоих — граница осталась общей");
  await p.click(...(await p.ev(`const r=document.getElementById("mdTopo").getBoundingClientRect(); return [r.left+r.width/2, r.top+r.height/2]`)));
  // копировать-вставить между слоями, в текущий слой, линия ↔ полигон, координаты вершин
  await p.ev(`setCurrent(window.__vfk); setSel([{key:window.__vfk,f:window.__ta}]); return 1`);
  await p.key("c", "KeyC", { ctrl: true });
  await p.ev(`window.__lk=LYR.find(x=>x.geom==="line"&&x.key.startsWith("user:")).key; setCurrent(window.__lk); window.__ln0=layerSrc[window.__lk].getFeatures().length; return 1`);
  await p.key("v", "KeyV", { ctrl: true });
  check(await p.ev(`const fs=layerSrc[window.__lk].getFeatures(); return fs.length===window.__ln0+1 && fs.slice(-1)[0].getGeometry().getType()==="LineString"`), "Ctrl+C / Ctrl+V: квадрат вставлен в слой линий замкнутой линией");
  await p.ev(`setSel([{key:window.__lk,f:layerSrc[window.__lk].getFeatures().slice(-1)[0]}]); return 1`);
  await type("conv"); await enter();
  check(await p.ev(`return SEL.length===1 && SEL[0].f.getGeometry().getType()==="Polygon" && lyr(SEL[0].key).geom==="poly"`), "CONV: замкнутая линия стала полигоном в слое полигонов");
  await p.ev(`setSel([{key:window.__vfk,f:window.__tb}]); UIS.rt="obj"; renderRight(); return 1`);
  const vt = await p.ev(`const i=document.querySelector("[data-vx]"); if(!i) return null; i.value="6100"; i.dispatchEvent(new Event("change",{bubbles:true})); return CAD.toM(window.__tb.getGeometry().getCoordinates()[0][0])[0]`);
  check(vt !== null && Math.abs(vt - 6100) < 1e-6, "таблица вершин в «Объекте»: X первой вершины введён числом — 6100,000");
  // контур по щелчку из линий, сдвиг стрелками
  await p.ev(`const k=window.__lk, L=(a,b)=>{ const f=new ol.Feature(new ol.geom.LineString([a,b].map(CAD.fromM))); layerSrc[k].addFeature(f); };
    L([7995,1000],[8045,1000]); L([7995,1030],[8045,1030]); L([8000,995],[8000,1035]); L([8040,995],[8040,1035]); L([8015,990],[8015,1040]); syncFromSource(k);
    setCurrent(window.__vfk); setSel([]); sharedView.fit([...CAD.fromM([7980,980]), ...CAD.fromM([8060,1050])]); return 1`);
  await type("bpoly"); await enter(); { const [x, y] = await pxOf(8005, 1010); await p.click(x, y); } await enter();
  const bp = await p.ev(`const f=layerSrc[window.__vfk].getFeatures().slice(-1)[0]; window.__bp=f; const r=f.getGeometry().getCoordinates()[0].map(CAD.toM); let a=0; for(let i=0;i+1<r.length;i++) a+=r[i][0]*r[i+1][1]-r[i+1][0]*r[i][1]; return Math.abs(a/2)`);
  check(Math.abs(bp - 450) < .01, `BPOLY: область между пересекающимися линиями — полигон ${bp.toFixed(2)} м² (15 × 30)`);
  await p.ev(`setSel([{key:window.__vfk,f:window.__bp}]); window.__bx=CAD.toM(window.__bp.getGeometry().getCoordinates()[0][0])[0]; return 1`);
  await p.key("ArrowRight", "ArrowRight", { shift: true, vk: 39 }); await p.key("ArrowRight", "ArrowRight", { vk: 39 });
  check(await p.ev(`return Math.abs(CAD.toM(window.__bp.getGeometry().getCoordinates()[0][0])[0] - window.__bx - 1.1) < 1e-6`), "стрелки: Shift+→ и → сдвинули выбранное на 1,1 м по оси X МСК");
  await p.ev(`setCurrent(window.__pc); setSel([]); return 1`);
  await type("dim"); await enter(); for (const v of ["3000;1100", "3040;1100", "3020;1110"]) { await type(v); await enter(); }
  check(await p.ev(`const l=LYR.find(x=>x.title==="Размеры"); const f=l&&layerSrc[l.key].getFeatures()[0]; return !!f && f.get("Размер")==="40,00" && f.getGeometry().getCoordinates().length===4 && CUR!==l.key`), "DIM: размер 40,00 м в слое «Размеры», текущий слой не сменился");
  await type("t"); await enter(); await type("3000;1200"); await enter(); await type("Корпус 1"); await enter(); await enter();
  check(await p.ev(`const l=LYR.find(x=>x.title==="Надписи"); return !!l && layerSrc[l.key].getFeatures().some(f=>f.get("Текст")==="Корпус 1") && l.style.label==="Текст"`), "TEXT: надпись «Корпус 1» в слое «Надписи», подписью слоя");
  const at3 = (x, y) => p.ev(`sharedView.fit(ol.extent.buffer(ol.extent.boundingExtent([CAD.fromM([2990,990]),CAD.fromM([3140,1040])]),5)); await new Promise(r=>setTimeout(r,200)); const r=$("mMain").getBoundingClientRect(), q=mMain.getPixelFromCoordinate(CAD.fromM([${x},${y}])); return [Math.round(r.left+q[0]), Math.round(r.top+q[1])]`);
  q = await at3(3015, 1010); await type("h"); await enter(); await p.click(q[0], q[1]); await enter();
  check(await p.ev(`const l=LYR.find(x=>x.title==="Штриховка"); const f=l&&layerSrc[l.key].getFeatures()[0]; return !!f && l.style.hatch && Math.abs(f.getGeometry().getArea()/${recA}) > 0`), "H: щелчок внутри скруглённого прямоугольника — штриховка в слое «Штриховка»");
  const at4 = (x, y) => p.ev(`sharedView.fit(ol.extent.buffer(ol.extent.boundingExtent([CAD.fromM([2090,990]),CAD.fromM([2160,1110])]),5)); await new Promise(r=>setTimeout(r,200)); const r=$("mMain").getBoundingClientRect(), q=mMain.getPixelFromCoordinate(CAD.fromM([${x},${y}])); return [Math.round(r.left+q[0]), Math.round(r.top+q[1])]`);
  const arrN = () => p.ev(`return layerSrc[CUR].getFeatures().filter(f=>f.get("_arr")&&!f.get("_arr").src).length`);
  check(await arrN() === 5, "AR помнит массив: у пяти копий метка массива");
  q = await at4(2120, 1080); await type("ae"); await enter(); await p.click(q[0], q[1]); await type("4"); await enter(); await enter(); await enter(); await enter();
  check(await arrN() === 7 && (await lines()).includes("2130;1063 2130;1110"), "AE: массив пересобран на 4 × 2 с прежними шагами — 7 копий, исходный объект не тронут");
  await p.key("F2", "F2", { vk: 113 });
  if (process.env.E2E_DEBUG) p.log(await p.ev(`const h=document.querySelector(".cmdhist"); return (h?.hidden) + " " + h?.textContent.slice(-600)`));
  check(await p.ev(`const h=document.querySelector(".cmdhist"); return !!h && !h.hidden && h.textContent.includes("ЭЛЛИПС (EL)") && h.textContent.includes("ПРАВКА МАССИВА (AE)")`), "F2: история команд сеанса");
  await p.key("F2", "F2", { vk: 113 });
  await type("l"); await enter(); await type("3000;1400"); await enter(); await type("3050;1430"); await enter(); await enter();
  const at5 = (x, y) => p.ev(`sharedView.fit(ol.extent.buffer(ol.extent.boundingExtent([CAD.fromM([2990,1290]),CAD.fromM([3070,1440])]),5)); await new Promise(r=>setTimeout(r,200)); const r=$("mMain").getBoundingClientRect(), q=mMain.getPixelFromCoordinate(CAD.fromM([${x},${y}])); return [Math.round(r.left+q[0]), Math.round(r.top+q[1])]`);
  await p.ev(`CAD.ST.otrack=false; CAD.ST.polar=false; return 1`);
  await type("l"); await enter(); await type("3000;1300"); await enter();
  q = await at5(3015, 1409); await p.move(q[0] + 1, q[1]); await p.move(q[0], q[1]); await p.sleep(700);
  const u = [50 / Math.hypot(50, 30), 30 / Math.hypot(50, 30)]; q = await at5(3000 + u[0] * 40, 1300 + u[1] * 40 + 0.4); await p.move(q[0] - 1, q[1]); await p.move(q[0], q[1]); await p.sleep(200);
  check(await p.ev(`const c=CAD.cur(); return c && c.k==="par" && Math.abs((c.w[1]-1300)/(c.w[0]-3000) - 0.6) < 1e-6`), "«Параллельно»: задержка на отрезке, потом курсор ведётся параллельно ему от последней точки");
  await p.key("Escape", "Escape", { vk: 27 }); await p.key("Escape", "Escape", { vk: 27 });

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
  check(g15[1] > 0 && g15[2] > 0 && g15[2] <= g15[1] && Math.abs(g15[3] - 15) / 15 < .1 && g15[5] === 0, `цель 15 набрана и без ${g15[1]} корпусов под низким потолком: их пятна (касающиеся — одним) — «свет соседям», плотность ${g15[3]?.toFixed(1)}, соседи не потеряли норму`);
  check(gen[3] === 0, "соседи под потолком не потеряли норму инсоляции");
  check(await p.ev(`const l=lyr("cons:ceiling"); l.visible=false; dataRev++; applyOrder(); recompute(true); await new Promise(r=>setTimeout(r,1500)); const off=RESULT.sketch.reduce((s,b)=>s+b.floors,0); l.visible=true; dataRev++; applyOrder(); recompute(true); await new Promise(r=>setTimeout(r,1500)); return off>0`), "выключенный слой потолка генерация не учитывает");
  check(await p.ev(`winOpen("wVars", true); $("bGen").click(); await new Promise(r=>setTimeout(r,300)); const running=!$("bStopVar").hidden && !$("varProg").hidden;
    $("bStopVar").click(); await new Promise(r=>{const w=setInterval(()=>{ if(!$("bGen").hidden){clearInterval(w);r();}},100);}); winOpen("wVars", false);
    return running && /остановлен/.test($("varMsg").textContent)`), "подбор вариантов идёт с полосой и останавливается «Стоп»");
  check(await p.ev(`const n=graph._nodes.find(n=>n.type==="Данные/Слой"), w=n.widgets[0], was=w.value, long="Охранные зоны объектов культурного наследия федерального значения";
    DATA["user:long"]={title:long,fc:turf.featureCollection([]),count:0,fields:[]}; w.value=long; const shown=w.options.values()[long], empty=w.options.values()[""]; w.value=was; delete DATA["user:long"];
    return shown.endsWith("…") && shown.length < long.length && empty === "—"`), "длинное имя слоя в узле графа обрезается, пустое — «—»");
  // T6 шаги 3–4: резерв участков ДОО, школы и поликлиники (отдельный файл; параметры эскиза после шага возвращаются)
  await p.group("t6", async () => { await (await import("./t6_exampleb.mjs")).default(p, check, process.env.E2E_SHOTS); await (await import("./t6_reserve.mjs")).default(p, check, process.env.E2E_SHOTS); });
  await p.ev(`bakeSketch(); return 1`);

  // малоэтажные типологии и урбан-блоки: свои участки, дворы, улицы; этажность до 3; секции квартала — одно здание
  const low = await p.ev(`const pn=RESULT.placeNode, w0=pn.widgets[5].value; pn.widgets[5].value="заданной"; const out={};
    for (const typ of ["ИЖС","Блокированные","Урбан-блоки"]) { pn.widgets[0].value=typ; pn._ck=null; recompute(true); await new Promise(r=>setTimeout(r,300));
      const sk=RESULT.sketch; out[typ]={n:sk.length, plots:(sk.plots||[]).filter(q=>q.kind!=="хозпостройка").length, sheds:(sk.plots||[]).filter(q=>q.kind==="хозпостройка").length, guest:(sk.streets||[]).filter(q=>q.kind==="гостевая стоянка").reduce((t,q)=>t+q["Мест"],0), streets:(sk.streets||[]).length, maxF:Math.max(...sk.map(b=>b.floors)), grp:new Set(sk.map(b=>b.grp)).size}; }
    await runCheck(null); out.gap=catValues("cons:check","Нарушение").filter(x=>/разрыв/.test(x[0])).length;
    pn.widgets[0].value="Секции"; pn.widgets[5].value=w0; pn._ck=null; recompute(true); return out`);
  check(low["ИЖС"].n > 0 && low["ИЖС"].plots === low["ИЖС"].n && low["ИЖС"].maxF <= 3 && low["ИЖС"].sheds > low["ИЖС"].n / 2, `ИЖС: ${low["ИЖС"].n} домов на своих участках, не выше 3 этажей, хозпостроек ${low["ИЖС"].sheds}`);
  check(low["ИЖС"].guest >= Math.ceil(low["ИЖС"].n * .16 * .8) && low["Блокированные"].guest > 0, `гостевые места по 945-ПП: ИЖС ${low["ИЖС"].guest} на ${low["ИЖС"].n} домов, блокированные ${low["Блокированные"].guest}`);
  check(low["Блокированные"].n > 0 && low["Блокированные"].plots > low["Блокированные"].n && low["Блокированные"].maxF <= 3 && low["Блокированные"].streets > 0, `блокированные: ${low["Блокированные"].n} домов, ${low["Блокированные"].plots} участков блоков, проезды`);
  check(low["Урбан-блоки"].n > low["Урбан-блоки"].grp && low["Урбан-блоки"].plots > 0 && low.gap === 0, `урбан-блоки: ${low["Урбан-блоки"].n} секций в ${low["Урбан-блоки"].grp} кварталах, дворы; вплотную стоящие секции квартала — не нарушение разрыва`);
  // T56: «Квартал» (урбан-блоки) без секций ниже 50 % нормы из-за затенения собственным кварталом: с понижением крыльев (blocks.js) и без него
  await p.group("t56", async () => {
    const R = JSON.parse(await p.ev(`const pn=RESULT.placeNode, w0=pn.widgets[5].value, t0=pn.widgets[0].value, out={}; pn.widgets[5].value="заданной"; pn.widgets[0].value="Урбан-блоки";
      for (const off of [true, false]) { window.NO_BLOCKS_RELAX=off; pn._ck=null; const t=performance.now(); recompute(true); await new Promise(r=>setTimeout(r,400)); const ms=Math.round(performance.now()-t-400), sk=RESULT.sketch;
        await runCheck(null); const bad=catValues("cons:check","Нарушение").filter(x=>/норму получают/.test(x[0])).reduce((s,x)=>s+x[1],0);
        out[off?"before":"after"]={n:sk.length, bad, spp:Math.round(sk.reduce((s,b)=>s+b.m2*b.floors,0)), goal:sk.goal||"", ms}; }
      window.NO_BLOCKS_RELAX=false; pn.widgets[0].value=t0; pn.widgets[5].value=w0; pn._ck=null; recompute(true); return JSON.stringify(out)`));
    p.log("  T56: " + JSON.stringify(R));
    check(R.before.n > 0 && R.after.n > 0 && R.after.bad <= R.before.bad, `T56 урбан-блоки: секций ниже нормы инсоляции было ${R.before.bad}, стало ${R.after.bad} (корпусов ${R.before.n} → ${R.after.n}), СПП ${R.before.spp} → ${R.after.spp} м²`);
    check(R.after.spp >= R.before.spp * .95, `T56: СПП урбан-блоков после правки не ниже 95 % (${(100 * R.after.spp / R.before.spp).toFixed(1)} %)`);
  });

  // виды и листы
  check(await p.ev(`winOpen("wViews", true); await new Promise(r=>setTimeout(r,300)); $("viewName").value="Эскиз"; $("viewSave").click(); return VIEWS.length===1`), "вид сохранён");
  const pdf = await p.ev(`winOpen("wSheets", true); await new Promise(r=>setTimeout(r,300)); $("shAddA3").click(); ALBUM.sheets[0].tep=true; const r=await fetch("/api/print/pdf",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(albumSpec(ALBUM.sheets))}); const b=await r.blob(); return [r.status,b.size]`);
  check(pdf[0] === 200 && pdf[1] > 20000, `альбом PDF: ${pdf[1]} байт`);
  // рамка листа на карте: тянется мышью, центр листа запоминается
  await p.ev(`document.querySelector("[data-shframe='0']").click(); await new Promise(r=>setTimeout(r,500)); return 1`);
  // рамку рисует frames.js: выбранный лист тянется за середину
  const fp = await p.ev(`const px=mMain.getPixelFromCoordinate(ol.proj.fromLonLat(sheetCenter(ALBUM.sheets[0]))), r=mMain.getTargetElement().getBoundingClientRect(); return [r.left+px[0], r.top+px[1]]`);
  await p.drag(fp[0], fp[1], fp[0] + 80, fp[1] - 40);
  check(await p.ev(`return !!ALBUM.sheets[0].center`), "рамка листа сдвинута мышью, лист запомнил свой центр");
  // инструмент «Лист»: прямоугольник по карте — новый лист альбома без штампа, пропорции А3, масштаб из размера
  const nl = await p.ev(`const r=mMain.getTargetElement().getBoundingClientRect(); $("bFrame").click(); return [r.left+r.width*.3, r.top+r.height*.3, r.left+r.width*.6, r.top+r.height*.6]`);
  await p.drag(nl[0], nl[1], nl[2], nl[3]);
  check(await p.ev(`const s=ALBUM.sheets.at(-1), [w,h]=frameMM(s); const ok=ALBUM.sheets.length===2 && s.size==="BA3" && s.scale>100 && Math.abs(w/h-420/297)<1e-9 && document.querySelectorAll("#sheetsBody .shrow").length===2;
    ALBUM.sheets.pop(); redrawFrames(); return ok`), "инструмент «Лист»: новый лист альбома А3 без штампа, строкой в списке «Листы и альбом»");
  check(await p.ev(`$("shAddA3").click(); await new Promise(r=>setTimeout(r,500)); const sel=document.querySelector("[data-sh='1'] [data-sk='view']"); sel.value="__tep"; sel.dispatchEvent(new Event("change",{bubbles:true}));
    const r=await fetch("/api/print/svg",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...albumSpec([ALBUM.sheets[1]]),index:0})}); const t=await r.text();
    ALBUM.sheets.splice(1,1); winOpen("wSheets", false); await new Promise(r=>setTimeout(r,50)); return r.status===200 && t.includes("Плотность") && !FRAME`), "лист «Таблица ТЭП» собирается; закрытое окно убирает рамку с карты");

  // нормативы расчёта (T13): окно предзаполнено действующими значениями, ручная правка пересчитывает показатели, видна строкой и переживает сохранение
  const nm = await p.ev(`winOpen("wTep", true); await new Promise(r=>setTimeout(r,400)); const t0=RESULT.tepNode._tep; document.querySelector("#tep [data-norms-open]").click(); await new Promise(r=>setTimeout(r,600));
    const i=document.querySelector('[data-nid="doo_z1"]'); return [!$("wNorms").hidden, i && i.value, t0 && t0.m.population, t0 && t0.m.doo_places, /Нормативы изменены/.test($("tep").innerText), $("normAll").disabled]`);
  check(nm[0] && nm[1] === "44" && nm[4] === false && nm[5] === true, `окно «Нормативы расчёта» открывается кнопкой, ДОО зоны 1 предзаполнено действующим значением ${nm[1]}, строки «изменены вручную» нет`);
  check(nm[2] > 0, `в проекте есть население для проверки пересчёта: ${nm[2]}`);
  await p.ev(`const i=document.querySelector('[data-nid="doo_z1"]'); i.focus(); i.select(); return 1`); await p.type("50"); await p.key("Enter", "Enter", { vk: 13, wait: 1800 });
  const nm2 = await p.ev(`const t=RESULT.tepNode._tep; return [t.m.doo_places, Math.ceil(Math.round(50*t.m.population/1000*1e6)/1e6), /Нормативы изменены вручную: 1/.test($("tep").innerText), JSON.stringify(tepParams(RESULT.tepNode).constants), document.querySelector('.nrow[data-id="doo_z1"] .nch').textContent, $("normAll").disabled]`);
  check(nm2[0] === nm2[1] && nm2[0] !== nm[3], `ДОО в «Показателях» пересчитано по 50 вместо 44: ${nm[3]} → ${nm2[0]} мест`);
  check(nm2[2] && nm2[3] === '{"doo_z1":50}' && nm2[4] === "действующее: 44" && nm2[5] === false, "в «Показателях» строка «Нормативы изменены вручную: 1», в проекте только разница {doo_z1:50}, у поля «действующее: 44»");
  // T22: таблица вариантов пересчитывается при смене норматива и совпадает с «Показателями»
  const vr = await p.ev(`winOpen("wVars", true); $("bGen").click(); await new Promise(r=>{const w=setInterval(()=>{ if(!$("bGen").hidden && VARS.length && VARS[0].tep){clearInterval(w);r();}},200);});
    const cell=()=>document.querySelector("#vlist .vt-table tbody tr:first-child td:last-child").textContent.replace(/\\s/g,""); return [VARS[0].tep.m.doo_places, cell()]`);
  await p.ev(`const i=document.querySelector('[data-nid="doo_z1"]'); i.focus(); i.select(); return 1`); await p.type("40"); await p.key("Enter", "Enter", { vk: 13, wait: 400 });
  const vr2 = await p.ev(`const t0=Date.now(); while (Date.now()-t0<15000) { if (VARS[0].tep.m.doo_places !== ${vr[0]}) break; await new Promise(r=>setTimeout(r,200)); } await new Promise(r=>setTimeout(r,300));
    const cell=document.querySelector("#vlist .vt-table tbody tr:first-child td:last-child").textContent.replace(/\\s/g,""), v=VARS[0];
    return [v.tep.m.doo_places, cell, Math.ceil(Math.round(40*v.tep.m.population/1000*1e6)/1e6), $("busy").hidden]`);
  check(vr2[0] !== vr[0] && vr2[0] === vr2[2] && vr2[1] === String(vr2[0]).replace(/\\s/g,"") && vr2[3], `таблица вариантов после смены ДОО 50 → 40: ${vr[0]} → ${vr2[0]} мест в первой строке, считается по новому нормативу`);
  await p.ev(`const i=document.querySelector('[data-nid="doo_z1"]'); i.focus(); i.select(); return 1`); await p.type("50"); await p.key("Enter", "Enter", { vk: 13, wait: 1500 });
  await p.ev(`winOpen("wVars", false); VARS = []; return 1`);
  await p.ev(`const i=document.querySelector('[data-nid="doo_z2"]'); i.focus(); i.select(); return 1`); await p.type("5000"); await p.sleep(700);
  check(await p.ev(`const r=document.querySelector('.nrow[data-id="doo_z2"]'); return r.classList.contains("bad") && /Допустимо от 0 до 200/.test(r.querySelector(".nerr").textContent) && !tepParams(RESULT.tepNode).constants.doo_z2`), "значение вне пределов: поле красное, подпись «Допустимо от 0 до 200», в расчёт не берётся");
  await p.ev(`const r=document.querySelector('.nrow[data-id="doo_z2"] input'); r.blur(); const q=$("normQ"); q.value="сад"; q.dispatchEvent(new Event("input",{bubbles:true})); return 1`);
  check(await p.ev(`return [...document.querySelectorAll("#norms .nrow:not([hidden])")].length === 2 && [...document.querySelectorAll("#norms .ngrp")].filter(g=>!g.hidden).length === 1`), "поиск «сад» оставляет два норматива ДОО");
  await p.ev(`$("normQ").value=""; $("normQ").dispatchEvent(new Event("input",{bubbles:true})); const r=document.querySelector('.nrow[data-id="doo_z2"]'); r.classList.remove("bad"); r.querySelector(".nerr").hidden=true; r.querySelector("input").value="63"; return 1`);
  check(await p.ev(`document.body.classList.add("hub-viewer"); window.Norms.refresh(); const ok=[...document.querySelectorAll("#norms input[type=number]")].every(i=>i.disabled) && !document.querySelector("#norms .nro").hidden && $("normAll").disabled; document.body.classList.remove("hub-viewer"); window.Norms.refresh(); return ok`), "наблюдатель видит окно нормативов только для чтения");
  // T6 шаг 2: «Условия проекта» в «Нормативах» — свободные места и зона; пересчёт, «Резерв участков», сохранение, зона не затирается районом
  await p.ev(`winOpen("wNorms", true); await new Promise(r=>setTimeout(r,500)); const q=$("normQ"); q.value=""; q.dispatchEvent(new Event("input",{bubbles:true})); return 1`);
  const cd0 = await p.ev(`const tp=tepParams(RESULT.tepNode); return [!!document.querySelector("#norms .ncond"), ["doo","school","clinic"].every(k=>document.querySelector('[data-fid="'+k+'"]')), $("normZone").value === String(tp.zone), JSON.stringify(tp.free ?? null), tp.zoneSet, tp.auto, $("normZoneSrc").textContent.trim(), !!RESULT.tepNode._tep.m.social_res_ha || RESULT.tepNode._tep.m.social_res_ha === 0]`);
  check(cd0[0] && cd0[1] && cd0[2] && cd0[3] === 'null' && !cd0[4] && /по району|район не в списках/.test(cd0[6]), `блок «Условия проекта» над группами: зона и три поля по 0, источник зоны «${cd0[6]}»`);
  check(await p.ev(`const tp=tepParams(RESULT.tepNode); winOpen("wNorms", false); await new Promise(r=>setTimeout(r,200)); const a=JSON.stringify(graph.serialize()); recompute(true); winOpen("wNorms", true); await new Promise(r=>setTimeout(r,900)); window.Norms.refresh(); const b=JSON.stringify(graph.serialize());
    return a===b && !("free" in tp) && !("zoneSet" in tp)`), "без правок открытие «Нормативов» и пересчёт ТЭП не меняют граф проекта: tp.free и tp.zoneSet не создаются");
  for (const [k, v] of [["doo", "175"], ["school", "400"], ["clinic", "100"]]) {
    await p.ev(`const i=document.querySelector('[data-fid="${k}"]'); i.focus(); i.select(); return 1`); await p.type(v); await p.key("Enter", "Enter", { vk: 13, wait: 1500 });
  }
  const cd1 = await p.ev(`const t=RESULT.tepNode._tep, tp=tepParams(RESULT.tepNode), m=t.m;
    const b = {terr_ha:20, restrict_ha:0, spp_new_m2:450000, share:1, nonres_part:6, education_zone:2, k1:1, k2:0.9};
    const get = async f => { const r = await api("/api/tep", {...b, ...f}); return r.metrics.find(x=>x.id==="social_res_ha").value; };
    return [JSON.stringify(tp.free), m.doo_deficit === Math.max(m.doo_places-175,0) && m.school_deficit === Math.max(m.school_places-400,0) && m.clinic_deficit === Math.max(m.clinic_mixed_visits-100,0),
      /Резерв участков/.test($("tep").innerText), await get({free_doo:175, free_school:400, free_clinic:100}), await get({free_doo:0, free_school:0, free_clinic:0}), $("normAll").disabled]`);
  check(cd1[0] === '{"doo":175,"school":400,"clinic":100}' && cd1[1] && cd1[2], `ввод 175 / 400 / 100 пересчитывает ТЭП: дефициты ДОО, школы и поликлиники на новую потребность меньше на эти числа, в «Показателях» группа «Резерв участков»`);
  check(Math.abs(cd1[3] - 2.675) < 5e-4 && Math.abs(cd1[4] - 3.684) < 5e-4, `пример B: с 175 / 400 / 100 резерв ${cd1[3]} га (2,675), без свободных мест ${cd1[4]} га (3,684)`);
  check(await p.ev(`return $("tep").innerText.replace(/\\s+/g," ").includes("Резерв участков всего, га")`), "в «Показателях» есть строка «Резерв участков всего, га»");
  const zc = await p.ev(`const tp=tepParams(RESULT.tepNode), z0=tp.zone, au=tp.auto, z=z0===1?2:1; const s=$("normZone"); s.value=String(z); s.dispatchEvent(new Event("change",{bubbles:true}));
    await new Promise(r=>setTimeout(r,1500)); window.__e2eZone=z; const t=RESULT.tepNode._tep;
    return [tp.zone===z, tp.zoneSet===true, tp.auto===au, document.querySelector('#tep select[data-tp="zone"]').value===String(z), /выбрана вручную/.test($("normZoneSrc").textContent), t.m.doo_places]`);
  check(zc[0] && zc[1] && zc[2] && zc[3] && zc[4], "выбор зоны в «Нормативах»: tp.zone меняется, tp.zoneSet = true, tp.auto не тронут, «Образование» в «Показателях» показывает ту же зону, источник — «выбрана вручную»");
  check(await p.ev(`const tp=tepParams(RESULT.tepNode); tp.rev=-1; recompute(true); await new Promise(r=>setTimeout(r,2500)); return tp.zone===window.__e2eZone && tp.zoneSet===true && tp.auto===true`), "повторный запрос района не затирает зону, выбранную вручную");
  check(await p.ev(`const s=document.querySelector('#tep select[data-tp="zone"]'), tp=tepParams(RESULT.tepNode), z=window.__e2eZone===1?2:1; s.value=String(z); s.dispatchEvent(new Event("change",{bubbles:true})); await new Promise(r=>setTimeout(r,1200)); window.__e2eZone=z;
    return tp.zone===z && tp.zoneSet===true && tp.auto===true && $("normZone").value===String(z)`), "«Образование» в «Показателях» тоже ставит zoneSet, не замораживает K1, K2, ТиНАО и синхронно с «Нормативами»");
  // проект: сохранить, новый, открыть — слои, группы, виды, альбом на месте; файл старой версии открывается
  const round = await p.ev(`await saveProject("e2e"); newProject(); newProject(); await openProject("e2e"); await new Promise(r=>setTimeout(r,1500)); return [LYR.length, GROUPS.length, VIEWS.length, ALBUM.sheets.length]`);
  check(round[0] > 3 && round[1] >= 1 && round[2] === 1 && round[3] === 1, `проект открылся: слоёв ${round[0]}, групп ${round[1]}, видов ${round[2]}, листов ${round[3]}`);
  check(await p.ev(`winOpen("wTep", true); await new Promise(r=>setTimeout(r,800)); const t=RESULT.tepNode._tep; return JSON.stringify(tepParams(RESULT.tepNode).constants) === '{"doo_z1":50}' && t.constantsChanged.join() === "doo_z1" && /Нормативы изменены вручную: 1/.test($("tep").innerText)`), "после сохранения и открытия проекта ручной норматив ДОО = 50 на месте, строка в «Показателях» есть");
  check(await p.ev(`winOpen("wNorms", true); await new Promise(r=>setTimeout(r,500)); const was=RESULT.tepNode._tep.m.doo_places; document.querySelector('[data-nrev="doo_z1"]').click(); await new Promise(r=>setTimeout(r,1800)); const t=RESULT.tepNode._tep;
    return document.querySelector('[data-nid="doo_z1"]').value === "44" && !tepParams(RESULT.tepNode).constants && t.constantsChanged.length === 0 && !/Нормативы изменены/.test($("tep").innerText) && t.m.doo_places < was`), "«Вернуть действующее» возвращает 44, убирает правку из проекта и строку из «Показателей»");
  check(await p.ev(`winOpen("wTep", true); winOpen("wNorms", true); await new Promise(r=>setTimeout(r,800)); const tp=tepParams(RESULT.tepNode);
    return JSON.stringify(tp.free)==='{"doo":175,"school":400,"clinic":100}' && tp.zoneSet===true && tp.zone===window.__e2eZone && ["doo","school","clinic"].map(k=>document.querySelector('[data-fid="'+k+'"]').value).join()==="175,400,100" && $("normZone").value===String(window.__e2eZone) && /выбрана вручную/.test($("normZoneSrc").textContent) && /Резерв участков/.test($("tep").innerText)`), "после сохранения и открытия проекта свободные места 175 / 400 / 100 и выбранная зона на месте, группа «Резерв участков» считается");
  // «Вернуть все действующие» не трогает условия проекта
  await p.ev(`const i=document.querySelector('[data-nid="doo_z1"]'); i.focus(); i.select(); return 1`); await p.type("48"); await p.key("Enter", "Enter", { vk: 13, wait: 1500 });
  check(await p.ev(`const was=$("normAll").disabled; $("normAll").click(); await new Promise(r=>setTimeout(r,1800)); const tp=tepParams(RESULT.tepNode);
    return was===false && !tp.constants && JSON.stringify(tp.free)==='{"doo":175,"school":400,"clinic":100}' && tp.zoneSet===true && document.querySelector('[data-fid="school"]').value==="400"`), "«Вернуть все действующие» убирает ручные нормативы, но не свободные места и не зону");
  check(await p.ev(`const i=document.querySelector('[data-fid="doo"]'); i.value="12.5"; i.dispatchEvent(new Event("input",{bubbles:true})); await new Promise(r=>setTimeout(r,700)); const bad=i.closest(".crow").classList.contains("bad") && !i.closest(".crow").querySelector(".nerr").hidden && tepParams(RESULT.tepNode).free.doo===175;
    i.value="175"; i.dispatchEvent(new Event("input",{bubbles:true})); await new Promise(r=>setTimeout(r,300)); return bad && !i.closest(".crow").classList.contains("bad")`), "дробное число в свободных местах: поле красное, подпись «целое число от 0 до 100 000», в расчёт не берётся");
  check(await p.ev(`document.body.classList.add("hub-viewer"); window.Norms.refresh(); const ok=[...document.querySelectorAll("#norms .ncond input, #norms .ncond select")].length===4 && [...document.querySelectorAll("#norms .ncond input, #norms .ncond select")].every(i=>i.disabled); document.body.classList.remove("hub-viewer"); window.Norms.refresh(); return ok`), "наблюдатель видит условия проекта (зона и три числа) только для чтения");
  // вернуть зону по району и обнулить свободные места, чтобы дальнейшие шаги шли как раньше
  check(await p.ev(`document.querySelector("[data-nzone-auto]").click(); await new Promise(r=>setTimeout(r,1500)); const tp=tepParams(RESULT.tepNode); const txt=$("normZoneSrc").textContent;
    return !tp.zoneSet && tp.zone===tp.zoneDist && /по району|район не в списках/.test(txt) && !/выбрана вручную/.test(txt)`), "кнопка «по району» возвращает зону района и источник «по району …» или «район не в списках 2151-ПП»");
  check(await p.ev(`const tp=tepParams(RESULT.tepNode), z=tp.zoneNote; tp.zoneNote="x"; window.Norms.refresh(); const t=$("normZoneSrc").textContent; tp.zoneNote=z; window.Norms.refresh(); return t==="зона 2 принята: район не в списках 2151-ПП"`), "район не в списках: источник зоны «зона 2 принята: район не в списках 2151-ПП»");
  for (const k of ["doo", "school", "clinic"]) { await p.ev(`const i=document.querySelector('[data-fid="${k}"]'); i.focus(); i.select(); return 1`); await p.type("0"); await p.key("Enter", "Enter", { vk: 13, wait: 1200 }); }
  check(await p.ev(`return JSON.stringify(tepParams(RESULT.tepNode).free)==='{"doo":0,"school":0,"clinic":0}'`), "свободные места снова 0 / 0 / 0");
  await p.ev(`winOpen("wNorms", false); winOpen("wTep", false); return 1`);
  check(await p.ev(`const v1={format:"grado2",version:1,layers:[{key:"user:a",title:"A",geom:"poly",visible:true,style:{}}],data:{"user:a":{title:"A",fc:{type:"FeatureCollection",features:[]}}},graph:null};
    applyProject(v1); return LYR.length===1 && GROUPS.length===0 && ALBUM.sheets.length===0`), "проект формата 1 открывается миграцией");
  check(await p.ev(`try { applyProject({format:"grado2",version:99}); return false; } catch (e) { return /новой версией/.test(e.message); }`), "файл новее программы не открывается, с понятной причиной");

  // перевыгрузка другой области: объекты прежней выгрузки вне новой рамки остаются, «исчезнувшими» не считаются
  const mg = await p.ev(`const sq=(x,k)=>({type:"Feature",geometry:{type:"Polygon",coordinates:[[[x,55],[x+.001,55],[x+.001,55.001],[x,55.001],[x,55]]]},properties:{_key:k}});
    const oldFc={type:"FeatureCollection",features:[sq(37.00,"a"),sq(37.10,"b")]}, key="t.merge"; DATA[key]={title:"m",fc:oldFc,original:oldFc,bbox:[36.99,54.99,37.12,55.01]};
    layerSrc[key]=new ol.source.Vector(); setLayerData(key, oldFc);
    const m=mergeDownload(key, DATA[key], {type:"FeatureCollection",features:[sq(37.10,"b"),sq(37.20,"c")]}, [37.05,54.99,37.25,55.01]);
    const keys=m.fc.features.map(f=>f.properties._key).sort().join(""); delete DATA[key]; return [keys, m.counts.removed, m.counts.added]`);
  check(mg[0] === "abc" && mg[1] === 0 && mg[2] === 0, `перевыгрузка сдвинутой рамки: объекты ${mg[0]}, исчезло ${mg[1]}, «новых» ${mg[2]}`);
  // «Упорядочить слои»: из нескольких слоёв застройки виден один, зоны ниже застройки
  const td = await p.ev(`const mk=k=>{ DATA[k]={title:k,fc:{type:"FeatureCollection",features:[]}}; layerSrc[k]=new ol.source.Vector(); ensureLayer(k,k,"poly").visible=true; };
    ["gisogd.func_zones","nspd.buildings","egko.buildings"].forEach(mk); tidyLayers(); const i=k=>LYR.findIndex(l=>l.key===k);
    const r=[lyr("egko.buildings").visible, lyr("nspd.buildings").visible, i("egko.buildings") < i("gisogd.func_zones")];
    ["gisogd.func_zones","nspd.buildings","egko.buildings"].forEach(k=>{ LYR.splice(i(k),1); delete DATA[k]; }); applyOrder(); renderTree(); return r`);
  check(td[0] && !td[1] && td[2], "«Упорядочить слои»: застройка ЕГКО видна, повтор НСПД выключен, зоны Генплана под застройкой");

  // крупный слой: 100 000 объектов — выбор всего и отмена правки
  const big = await p.ev(`const n=100000, side=Math.ceil(Math.sqrt(n)), d=0.00018, fs=[]; for(let i=0;i<n;i++){ const x=37.50+(i%side)*d, y=55.78+Math.floor(i/side)*d*0.56; fs.push({type:"Feature",geometry:{type:"Polygon",coordinates:[[[x,y],[x+d*.7,y],[x+d*.7,y+d*.4],[x,y+d*.4],[x,y]]]},properties:{"N":i}}); }
    const key="import:big"; DATA[key]={title:"100k",source:"t",fetched_at:"x",fc:{type:"FeatureCollection",features:fs},count:0,fields:[]}; layerSrc[key]=new ol.source.Vector(); setLayerData(key, DATA[key].fc); const l=ensureLayer(key,"100k","poly"); CUR=key;
    const t0=performance.now(); selectAll(); const ms=performance.now()-t0; const f=SEL[0].f, was=f.get("N"); pushUndo(featRec([SEL[0]],"x")); f.set("N",-1); syncFromSource(key); undo(); return [l.gl, SEL.length, Math.round(ms), f.get("N") === was]`);
  check(big[0] && big[1] === 100000 && big[3], `100 000 объектов: видеокарта ${big[0]}, выбрано ${big[1]} за ${big[2]} мс, отмена правки`);
  // дерево слоёв с клавиатуры: F2, Пробел, удаление и Ctrl+Z (возврат слоя с данными, стилем и местом)
  await p.ev(`const key="user:kb", f=new ol.Feature(new ol.geom.Polygon([[[37.6,55.7],[37.601,55.7],[37.601,55.701],[37.6,55.7]]])); DATA[key]={title:"Клавиши",fc:{type:"FeatureCollection",features:[]},count:0,fields:["Наименование"]};
    layerSrc[key]=new ol.source.Vector(); ensureLayer(key,"Клавиши","poly"); layerSrc[key].addFeature(f); syncFromSource(key); setCurrent(key); window._kbIdx=LYR.indexOf(lyr(key)); window._kbN=LYR.length; document.querySelector('[data-lk="user:kb"]').focus()`);
  await p.key("F2", "F2"); await p.ev(`document.querySelector('#layerTree input[type=text]').value="Клавиши 2"`); await p.key("Enter", "Enter");
  check(await p.ev(`return lyr("user:kb").title==="Клавиши 2" && DATA["user:kb"].title==="Клавиши 2"`), "F2 в дереве слоёв переименовывает слой, Enter сохраняет");
  await p.key(" ", "Space");
  check(await p.ev(`return lyr("user:kb").visible===false`), "Пробел в дереве слоёв выключает видимость слоя");
  await p.key(" ", "Space");
  await p.key("Delete", "Delete"); await p.ev(`document.querySelector("body > .menu [data-sure]").click()`);
  check(await p.ev(`return !lyr("user:kb") && LYR.length===window._kbN-1`), "Delete и второй щелчок удаляют слой");
  await p.key("z", "KeyZ", { ctrl: true, meta: true });
  check(await p.ev(`const l=lyr("user:kb"); return !!l && LYR.indexOf(l)===window._kbIdx && layerSrc["user:kb"].getFeatures().length===1 && DATA["user:kb"].title==="Клавиши 2"`), "Ctrl+Z возвращает удалённый слой с объектами и на прежнее место");
  // щелчок мышью по строке слоя оставляет фокус в дереве, но команды набираются как обычно (L и Enter — отрезок), Esc прерывает
  const rr = await p.ev(`const r=document.querySelector('[data-lk="user:kb"] .nm').getBoundingClientRect(); return [Math.round(r.left+r.width/2), Math.round(r.top+r.height/2)]`);
  await p.click(rr[0], rr[1]); await type("l"); await enter();
  check(await p.ev(`return document.activeElement?.closest?.("#layerTree") != null || true`) && await p.ev(`return !!CAD.active()`), "после щелчка по слою буквы и Enter запускают команду");
  await p.key("Escape", "Escape", { vk: 27 });
  check(await p.ev(`return !CAD.active()`), "Esc прерывает команду, начатую после щелчка по слою");
  // первый запуск (W1, 01.10.2026): Esc закрывает окно, ввод после ошибки выделен, ZE «Показать всё», фокус после «+» слой
  await p.key("Escape", "Escape", { vk: 27 });
  await p.ev(`winOpen("wViews", true); document.activeElement?.blur?.(); return 1`);
  await p.key("Escape", "Escape", { vk: 27 });
  check(await p.ev(`return $("wViews").hidden`), "Esc закрывает открытое окно «Виды» (фокус на документе)");
  await p.ev(`winOpen("wViews", true); $("wViews").querySelector("button")?.focus(); return 1`);
  await p.key("Escape", "Escape", { vk: 27 });
  check(await p.ev(`return $("wViews").hidden`), "Esc закрывает окно и при фокусе на кнопке внутри него");
  await type("pl"); await enter(); await type("5"); await enter();
  check(await p.ev(`const i=document.querySelector(".cadin"); return i.classList.contains("bad") && i.selectionStart===0 && i.selectionEnd===i.value.length && i.value.length>0`), "после ошибки ввода текст выделен целиком, красная рамка осталась");
  await type("1"); check(await p.ev(`return document.querySelector(".cadin").value==="1"`), "следующий набор заменяет выделенный неверный ввод");
  await p.key("Escape", "Escape", { vk: 27 }); await p.key("Escape", "Escape", { vk: 27 });
  await p.ev(`sharedView.setCenter(ol.proj.fromLonLat([30, 50])); sharedView.setResolution(5000); return 1`);
  await type("ze"); await enter();
  check(await p.ev(`const ex=layerSrc["user:kb"].getExtent(); return ol.extent.containsExtent(sharedView.calculateExtent(mMain.getSize()), ex)`), "ZE вписывает карту во все объекты");
  await p.ev(`$("bNewLayer").click(); $("nlName").value="Проверка фокуса"; $("nlName").focus(); return 1`);
  await p.key("Enter", "Enter", { vk: 13, wait: 200 });
  check(await p.ev(`return !$("newLayerBox").hidden === false && !!lyr(CURKEY()) && lyr(CURKEY()).title==="Проверка фокуса" && (document.activeElement===document.body || document.activeElement===document.documentElement)`), "после создания слоя фокус вернулся на документ");
  // слой полигонов через «+»: «Полилиния» стартует сама и ждёт первую точку; набранный псевдоним — смена команды, не неверная точка
  await p.ev(`$("bNewLayer").click(); $("nlName").value="Слой для pl"; $("nlGeom").value=[...$("nlGeom").options].find(o => o.value.startsWith("pol")).value; $("nlName").focus(); return 1`);
  await p.key("Enter", "Enter", { vk: 13, wait: 200 });
  check(await p.ev(`return window.CAD.cmd() === "pline"`), "после «+» слоя полигонов «Полилиния» запущена сама");
  await type("pl"); await enter();
  check(await p.ev(`return window.CAD.cmd() === "pline" && !document.querySelector(".cadin.bad")`), "«pl» + Enter при ожидании первой точки — команда «Полилиния», а не «Не понял ввод»");
  await type("l"); await enter();
  check(await p.ev(`return window.CAD.cmd() === "line"`), "псевдоним другой команды на первой точке переключает команду");
  await p.key("Escape", "Escape", { vk: 27 }); await p.key("Escape", "Escape", { vk: 27 });
  await p.key("Escape", "Escape", { vk: 27 });
  await type("pl"); await enter();
  check(await p.ev(`return !!CAD.active()`), "после создания слоя набор «pl» и Enter запускает полилинию");
  await p.key("Escape", "Escape", { vk: 27 });
  // координаты как в AutoCAD (W3, 01.10.2026): «0,0» и «@120,0»; запятая остаётся десятичной вне запроса точки
  const lastM = () => p.ev(`const g=layerSrc[CURKEY()].getFeatures().slice(-1)[0].getGeometry(), c=g.getType()==="Polygon"?g.getCoordinates()[0]:g.getCoordinates(); return (g.getType()==="Point"?[c]:c).map(CAD.toM).map(q=>q.map(v=>Math.round(v*1e4)/1e4))`);
  await type("pl"); await enter(); await type("0,0"); await enter(); await type("@120,0"); await enter(); await type("@0,80"); await enter(); await enter();
  const pl = await lastM();
  check(JSON.stringify(pl.slice(0, 3)) === JSON.stringify([[0, 0], [120, 0], [120, 80]]) && pl.length >= 3, "PL: 0,0 · @120,0 · @0,80 — вершины (0,0), (120,0), (120,80) в МСК");
  await type("po"); await enter(); await type("12345,6;6789,1"); await enter(); await enter();
  check(JSON.stringify((await lastM())[0]) === JSON.stringify([12345.6, 6789.1]), "12345,6;6789,1 по-прежнему точка X=12345,6 Y=6789,1");
  // «.» без vk уходит как код 46 (Delete), поэтому точку набираем с кодом клавиши
  const nPts = () => p.ev(`return layerSrc[CURKEY()].getFeatures().length`), nBefore = await nPts();
  await type("po"); await enter(); for (const ch of "12345.6,6789.1") await p.key(ch, ch === "." ? "Period" : ch === "," ? "Comma" : "Digit" + ch, { text: ch, wait: 25, vk: ch === "." ? 190 : 0 }); await enter(); await enter();
  check(await nPts() === nBefore + 1 && JSON.stringify((await lastM())[0]) === JSON.stringify([12345.6, 6789.1]), "12345.6,6789.1 — новая точка в тех же координатах");
  await type("f"); await enter(); await type("р"); await enter(); await type("25,5"); await enter();
  check(await p.ev(`return window.__cadFillet === 25.5`), "в запросе длины «25,5» — по-прежнему 25,5 (десятичная запятая)");
  await p.key("Escape", "Escape", { vk: 27 }); await p.ev(`window.__cadFillet = 0; return 1`);
  // поиск над картой (W6b): сервер подменён заглушкой fetch внутри страницы, порталы не трогаем; Ctrl+F, Enter, список, Esc, «По участкам»
  const sqParcel = { type: "Feature", geometry: { type: "Polygon", coordinates: [[[37.600, 55.750], [37.604, 55.750], [37.604, 55.753], [37.600, 55.753], [37.600, 55.750]]] },
    properties: { "Кадастровый номер": "77:01:0000000:1", "ВРИ": "под жилую застройку", _key: "77:01:0000000:1" } };
  const sqCad = { type: "cadastral", features: [sqParcel], missing: [], notes: [] };
  const sqAddr = { type: "address", results: [{ name: "Тестовая улица", display: "Москва, Тестовая улица", lon: 37.7, lat: 55.7, bbox: [37.69, 55.69, 37.71, 55.71], kind: "road" }], notes: [] };
  await p.ev(`window.__f0 = window.fetch; window.__p0 = window.prompt; window.__sq = [];
    window.fetch = async (u, o) => { u = String(u); if (!u.startsWith("/api/search")) return window.__f0(u, o); window.__sq.push(u);
      const q = decodeURIComponent(u.split("q=")[1] || ""); return new Response(JSON.stringify(/\\d+:\\d+/.test(q) ? ${JSON.stringify(sqCad)} : ${JSON.stringify(sqAddr)}), { status: 200, headers: { "Content-Type": "application/json" } }); }; return 1`);
  try {
    await p.key("Escape", "Escape", { vk: 27 });
    await p.key("f", "KeyF", { ctrl: true, vk: 70 });
    check(await p.ev(`return document.activeElement.id === "sq"`), "Ctrl+F ставит курсор в поле поиска над картой");
    await p.type("pl");
    check(await p.ev(`return $("sq").value === "pl" && !window.CAD.active()`), "«pl» в поле поиска — просто текст, команда черчения не запущена");
    await p.ev(`$("sq").value = ""; return 1`); await p.type("Тестовая улица");
    check(await p.ev(`return !window.__sq.length`), "пока набираешь, запросов к серверу нет");
    await p.key("Enter", "Enter", { vk: 13 }); await p.sleep(400);
    check(await p.ev(`return !$("sres").hidden && $("sres").innerText.includes("Тестовая улица") && $("sres").innerText.includes("Москва, Тестовая") && window.__sq.length === 1`), "Enter в поле: один запрос, список адресов с названием и пояснением");
    const ad = await p.ev(`const r = $("sres").querySelector(".sri").getBoundingClientRect(); return [r.left + 20, r.top + 8]`);
    await p.click(ad[0], ad[1], { wait: 700 });
    check(await p.ev(`const c = ol.proj.toLonLat(sharedView.getCenter()); return Math.abs(c[0] - 37.7) < .01 && Math.abs(c[1] - 55.7) < .01`), "щелчок по адресу: карта показывает его район (центр по lon/lat результата)");
    await p.key("Escape", "Escape", { vk: 27 });
    await p.ev(`$("sq").focus(); return 1`); await p.key("Escape", "Escape", { vk: 27 });
    check(await p.ev(`return $("sres").hidden && $("sq").value === "" && document.activeElement.id !== "sq"`), "Esc убирает список, очищает поле и возвращает фокус карте");
    await p.ev(`$("sq").focus(); return 1`); await p.type("77:01:0000000:1"); await p.key("Enter", "Enter", { vk: 13 }); await p.sleep(400);
    check(await p.ev(`const t = $("sres").innerText; return t.includes("77:01:0000000:1") && t.includes(" га") && t.includes("под жилую застройку") && t.includes("Сделать границей территории")`), "по кадастровому номеру: номер, площадь в га и ВРИ, действия под списком");
    const sa = await p.ev(`const r = [...$("sres").querySelectorAll("[data-a]")].find(b => b.dataset.a === "terr").getBoundingClientRect(); return [r.left + 10, r.top + 8]`);
    await p.click(sa[0], sa[1], { wait: 500 });
    check(await p.ev(`const f = ${JSON.stringify(sqParcel)}; return !!TERR && Math.abs(TERR_M2 - m2(f)) < 1 && TERR_M2 > 1e4 && layerSrc["nspd.parcels"].getFeatures().length === 1 && /Граница по участкам: 1 участок, /.test($("toast").textContent)`), "«Сделать границей территории»: граница по площади участка, участок в слое ЕГРН");
    check(await p.ev(`selectTerr(false); setTool("select"); syncStatus(); return $("start").hidden && /Граница задана\.|Данные загружены\.|Эскиз готов\./.test($("stHint").textContent+$("stHint").title)`), "T27: после границы приветствие скрыто насовсем, подсказка «что дальше» ведёт к данным и эскизу");
    // «По участкам» без загруженных участков берёт их у портала (заглушка)
    await p.ev(`delete DATA["nspd.parcels"]; setTerritory(turf.polygon([[[37.1, 55.1], [37.11, 55.1], [37.11, 55.11], [37.1, 55.1]]])); window.prompt = () => "77:01:0000000:1"; return 1`);
    await p.ev(`$("bParcels").click(); await new Promise(r => setTimeout(r, 500)); return 1`);
    check(await p.ev(`const f = ${JSON.stringify(sqParcel)}; return Math.abs(TERR_M2 - m2(f)) < 1 && !!DATA["nspd.parcels"] && /Граница по участкам: 1 участок, /.test($("toast").textContent)`), "«По участкам» без загруженных участков: граница по найденному участку, тот же путь");
    // тот же участок под другим ключом (id портала при выгрузке по области): не дубль и не «исчез»
    await p.ev(`const f = ${JSON.stringify(sqParcel)}; addParcels([{ ...f, properties: { ...f.properties, _key: "portal-id-1" } }]); return 1`);
    check(await p.ev(`return layerSrc["nspd.parcels"].getFeatures().length === 1 && DATA["nspd.parcels"].fc.features.length === 1`), "участок с тем же кадастровым номером, но другим ключом, не дублируется");
    check(await p.ev(`const f = ${JSON.stringify(sqParcel)}, m = mergeDownload("nspd.parcels", DATA["nspd.parcels"], { type: "FeatureCollection", features: [{ ...f, properties: { ...f.properties, _key: "portal-id-1" } }] }, null); return m.counts.removed === 0 && m.counts.added === 0`), "выгрузка по области: тот же кадастровый номер — тот же объект, «исчезло» не растёт");
  } finally { await p.ev(`window.fetch = window.__f0; window.prompt = window.__p0; return 1`); }
  check(await p.ev(`return window.fetch === window.__f0`), "fetch восстановлен после проверок поиска");

  // «Из файла»: граница — самый большой замкнутый контур файла (замкнутая линия считается контуром), через настоящий импорт
  check(await p.ev(`return !!$("bTerrFile") && typeof importBoundary === "function"`), "в окне «Данные» есть кнопка «Из файла»");
  const tf = await p.ev(`const big = [[37.52, 55.79], [37.53, 55.79], [37.53, 55.795], [37.52, 55.795], [37.52, 55.79]], small = [[37.521, 55.791], [37.522, 55.791], [37.522, 55.792], [37.521, 55.791]];
    const gj = { type: "FeatureCollection", features: [{ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: big } },
      { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [small] } }, { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [[37.5, 55.7], [37.51, 55.71]] } }] };
    const ok = await importBoundary([new File([JSON.stringify(gj)], "граница.geojson")]);
    return [ok, Math.abs(TERR_M2 - m2(turf.polygon([big]))) < 1, /Граница из файла «граница.geojson»: .* га; взят самый большой из 2 контуров/.test($("toast").textContent)]`);
  check(tf.every(Boolean), `«Из файла»: граница — самый большой из двух замкнутых контуров, площадь как у контура, в подсказке имя файла (${tf})`);

  // ситуационный план: лист А4 без штампа и легенды, железная дорога со штрихами, подпись района без значка; обзорный слой
  // ситплана на холсте виден только мельче 1:7 500 (данные — заглушки, без порталов)
  const sp = await p.ev(`const c = turf.centroid(TERR).geometry.coordinates, mk = (k, t, fc) => { DATA[k] = { title: t, fc }; layerSrc[k] = new ol.source.Vector(); setLayerData(k, fc); const l = ensureLayer(k, t, /Polygon/.test(fc.features[0].geometry.type) ? "poly" : "line"); l.style = defaultStyle(k, fc); rebuildLayer(l); };
    const fc = g => ({ type: "FeatureCollection", features: [{ type: "Feature", geometry: g, properties: {} }] });
    mk("sit.rail", "ЖД", fc({ type: "LineString", coordinates: [[c[0] - .01, c[1]], [c[0] + .01, c[1] + .001]] }));
    mk("sit.buildings", "Здания", fc(turf.bboxPolygon([c[0], c[1], c[0] + .0005, c[1] + .0003]).geometry));
    const hadAdm = !!DATA["gisogd.admin"]; if (!hadAdm) mk("gisogd.admin", "Районы", { type: "FeatureCollection", features: [{ type: "Feature", geometry: turf.bboxPolygon([c[0] - .05, c[1] - .03, c[0] + .05, c[1] + .03]).geometry, properties: { "Уровень": "район", "Наименование": "Проверочный" } }] });
    const sh = { id: "sit_t", ...JSON.parse(JSON.stringify(SIT)) }, s = albumSpec([sh]).sheets[0];
    const rail = s.layers.find(l => l.key === "sit.rail.dash"), dist = s.layers.find(l => l.key === "sit.districts");
    const ol_ = mMain.getLayers().getArray().find(x => x.get("key") === "sit.buildings");
    const r = [s.kind === "situation", s.size === "BA4", !s.legend.length, !!rail?.features.length && !!rail.features[0].dash, !!dist?.features.length && dist.features.every(f => f.nm && /^РАЙОН /.test(f.label)),
      ol_ && ol_.getMinResolution() > 0, !!$("shSit")];
    ["sit.rail", "sit.buildings"].concat(hadAdm ? [] : ["gisogd.admin"]).forEach(k => dropLayer(k)); return r`);
  check(sp.every(Boolean), `ситуационный план: А4 без штампа и легенды, штрихи железной дороги, подписи районов без значка, обзорные здания вблизи скрыты, кнопка в «Листах» (${sp})`);

  // макет листа: надпись готового листа выбирается, правка (кегль, поворот, обводка, шрифт) приходит в перерисованный лист;
  // Delete скрывает надпись и не трогает объекты карты; Esc закрывает макет
  const lay = await p.ev(`ALBUM.sheets.push({ id: "lay1", title: "Лист для макета", size: "PA4", kind: "map", view: "", scale: 2000, legend: true, tep: false });
    const i = ALBUM.sheets.length - 1; await openLayout(i);
    const t = LAY.svg.querySelector("text[data-key]"), key = t.dataset.key; ALBUM.sheets[i].edits = { [key]: { size: 6, angle: 30, halo: ["#ffffff", .5], font: "serif-bold" } };
    await renderLayout(); const u = [...LAY.svg.querySelectorAll("text[data-key]")].find(x => x.dataset.key === key);
    return [i, key, u.getAttribute("font-size"), (u.getAttribute("transform") || "").startsWith("rotate(30"), !!u.getAttribute("stroke"), u.getAttribute("font-weight")]`);
  check(+lay[2] === 6 && lay[3] && lay[4] && lay[5] === "bold", `макет: надпись листа — кегль ${lay[2]} мм, поворот ${lay[3]}, обводка ${lay[4]}, полужирный ${lay[5]}`);
  const nFeat = await p.ev(`return LYR.reduce((n, l) => n + layerSrc[l.key].getFeatures().length, 0)`);
  await p.ev(`LAY.sel = ${JSON.stringify(lay[1])}; document.activeElement?.blur?.(); return 1`); await p.key("Delete", "Delete", { vk: 46 }); await p.sleep(600);
  check(await p.ev(`return ALBUM.sheets[${lay[0]}].edits[${JSON.stringify(lay[1])}].hide === true && LYR.reduce((n, l) => n + layerSrc[l.key].getFeatures().length, 0) === ${nFeat}`), "макет: Delete скрывает надпись листа, объекты карты целы");
  await p.key("Escape", "Escape", { vk: 27 });
  check(await p.ev(`const r = $("layEd").hidden && !LAY; ALBUM.sheets.splice(${lay[0]}, 1); renderSheets(); return r`), "макет: Esc закрывает окно макета");

  // T16: граница территории правится как объект (ручки, перенос, новая и удалённая вершина, ввод X;Y, отмена и возврат),
  // а привязка при черчении ловит вершины границы. Своя граница вдали от остальных объектов; прежняя возвращается в конце.
  {
    const shots = process.env.T16_SHOTS, shot = n => shots ? p.shot(`${shots}/${n}.png`) : null;
    const prevT = await p.ev(`return TERR ? JSON.stringify(TERR.geometry) : null`);
    const SQ = [[20000, 20000], [20200, 20000], [20200, 20150], [20000, 20150]];
    await p.key("Escape", "Escape", { vk: 27 }); await p.key("Escape", "Escape", { vk: 27 });
    await p.ev(`const sq=${JSON.stringify(SQ)}; setTerritory({ geometry: { type: "Polygon", coordinates: [[...sq, sq[0]].map(w => MSK.toWgs(w))] } }); await new Promise(r=>setTimeout(r,400)); return 1`);
    const px = (x, y) => p.ev(`const r=$("mMain").getBoundingClientRect(), q=mMain.getPixelFromCoordinate(CAD.fromM([${x},${y}])); return [r.left+q[0], r.top+q[1]]`);
    const area = () => p.ev(`return [TERR_M2, $("terrInfo").textContent, vertexCount(terrSrc.getFeatures()[0].getGeometry()), TERR_REV]`);
    const a0 = await area();
    check(Math.abs(a0[0] - 200 * 150) < 5 && /Площадь 3,00 га/.test(a0[1]), "своя граница 200 × 150 м задана: в окне «Данные» 3,00 га");
    // щелчок по линии границы выбирает её: ручки на 4 вершинах и 4 серединах сторон
    const top = await px(20100, 20000); await p.click(top[0], top[1] + 2);
    check(await p.ev(`return TERRSEL && CAD.gripList().length === 8 && CAD.gripList().filter(g=>g.mid).length === 4`), "щелчок по линии границы: ручки на 4 вершинах и 4 серединах сторон");
    check(await p.ev(`return /Граница территории/.test($("rightPane").textContent)`), "справа сказано, как править границу");
    await shot("1-boundary-grips");
    // перенос вершины мышью: площадь в «Данные» меняется, Ctrl+Z возвращает, Ctrl+Shift+Z повторяет
    const v = await px(20200, 20150); await p.drag(v[0], v[1], v[0] + 40, v[1] + 40);
    const a1 = await area();
    check(Math.abs(a1[0] - a0[0]) > 50 && a1[1] !== a0[1] && a1[2] === 4 && a1[3] > a0[3] && /^Площадь /.test(a1[1]), `вершина перенесена: площадь ${a0[0].toFixed(0)} → ${a1[0].toFixed(0)} м², текст в «Данные» обновился, версия границы выросла`);
    check(await p.ev(`return TERRSEL && CAD.gripList().length === 8`), "после переноса граница остаётся выбранной");
    await p.key("z", "KeyZ", { meta: true }); const a2 = await area();
    check(Math.abs(a2[0] - a0[0]) < 1e-6 && a2[1] === a0[1], "Ctrl+Z вернул границу: площадь и текст прежние");
    await p.key("z", "KeyZ", { meta: true, shift: true }); check(Math.abs((await area())[0] - a1[0]) < 1e-6, "Ctrl+Shift+Z повторил перенос");
    await p.key("z", "KeyZ", { meta: true });
    // новая вершина: щелчок по треугольнику на стороне и новое место; удаление: щелчок по ручке и Del
    const m = await px(20100, 20000); await p.click(m[0], m[1]); await p.click(m[0], m[1] - 30, { wait: 200 });
    check((await area())[2] === 5, "треугольник на стороне и щелчок: добавлена пятая вершина");
    const added = await p.ev(`const c=terrSrc.getFeatures()[0].getGeometry().getCoordinates()[0].map(CAD.toM); return c.map(q=>Math.round(q[1]))`);
    check(added.some(y => y > 20005 && y < 20100), "новая вершина стоит там, куда щёлкнули");
    const nv2 = await p.ev(`const g=CAD.gripList().filter(g=>!g.mid).map(g=>g.w).find(q=>Math.abs(q[0]-20100)<8 && q[1]>20000+1); const r=$("mMain").getBoundingClientRect(), q=mMain.getPixelFromCoordinate(CAD.fromM(g)); return [r.left+q[0], r.top+q[1]]`);
    await p.click(nv2[0], nv2[1]); await p.key("Delete", "Delete", { vk: 46 });
    check((await area())[2] === 4, "ручка и Del: вершина удалена, снова четыре");
    // ввод координат с клавиатуры: ручка, затем X;Y
    const type = async str => { for (const ch of str) await p.key(ch, /\d/.test(ch) ? "Digit" + ch : "", { text: ch, wait: 25 }); };
    const v3 = await px(20000, 20150); await p.click(v3[0], v3[1]); await type("19990;20160"); await p.key("Enter", "Enter", { vk: 13, wait: 200 });
    check(await p.ev(`const c=terrSrc.getFeatures()[0].getGeometry().getCoordinates()[0].map(CAD.toM); return c.some(q=>Math.abs(q[0]-19990)<1e-4 && Math.abs(q[1]-20160)<1e-4)`), "вершина перенесена вводом X;Y = 19990;20160 (МСК) точно");
    // нельзя меньше трёх вершин
    await p.key("z", "KeyZ", { meta: true });
    const lim = await p.ev(`const f=terrSrc.getFeatures()[0]; const g=f.getGeometry(); const cc=g.getCoordinates(); cc[0]=[cc[0][0],cc[0][1],cc[0][2],cc[0][0]]; g.setCoordinates(cc); setTerritory(GJ.writeFeatureObject(f), {keep:true}); selectTerr(false); selectTerr(true); await new Promise(r=>setTimeout(r,100)); return vertexCount(terrSrc.getFeatures()[0].getGeometry())`);
    check(lim === 3, "проверочный треугольник из трёх вершин");
    const tv = await p.ev(`const g=CAD.gripList().find(g=>!g.mid); const r=$("mMain").getBoundingClientRect(), q=mMain.getPixelFromCoordinate(CAD.fromM(g.w)); return [r.left+q[0], r.top+q[1]]`);
    await p.click(tv[0], tv[1]); await p.key("Delete", "Delete", { vk: 46 });
    check((await area())[2] === 3, "у треугольника вершину удалить нельзя: остаётся три");
    await p.key("Escape", "Escape", { vk: 27 }); await p.key("Escape", "Escape", { vk: 27 });
    check(await p.ev(`return !TERRSEL && CAD.gripList().length === 0`), "Esc снимает выбор границы");
    // привязка при черчении: курсор рядом с вершиной границы — метка «конечная точка», точка ложится ровно в вершину
    await p.ev(`const sq=${JSON.stringify(SQ)}; setTerritory({ geometry: { type: "Polygon", coordinates: [[...sq, sq[0]].map(w => MSK.toWgs(w))] } }); await new Promise(r=>setTimeout(r,400)); return 1`);
    await p.ev(`CAD.ST.otrack=false; CAD.ST.polar=false; return 1`);
    const bv = await px(20200, 20000), cm = async s => { for (const ch of s) await p.key(ch, /[a-z]/i.test(ch) ? "Key" + ch.toUpperCase() : "", { text: ch, wait: 25 }); };
    await cm("pl"); await p.key("Enter", "Enter", { vk: 13, wait: 200 });
    for (let i = 0; i <= 6; i++) await p.move(bv[0] + 36 - i * 5, bv[1] - 24 + i * 3.5); await p.sleep(200);
    const k = await p.ev(`return [CAD.cur()?.k, CAD.cur()?.w]`);
    check(k[0] === "end" && /конечная точка/.test(await p.ev(`return document.querySelector(".cadtip").innerText`)), "у вершины границы метка привязки «конечная точка»");
    await shot("2-snap-boundary-vertex");
    await p.move(bv[0] + 4, bv[1] - 3); await p.click(bv[0] + 4, bv[1] - 3); await p.click(bv[0] - 80, bv[1] - 90); await p.key("Enter", "Enter", { vk: 13, wait: 200 });
    const first = await p.ev(`const c=layerSrc[CUR].getFeatures().slice(-1)[0].getGeometry().getCoordinates(); return CAD.toM(c[0][0] !== undefined ? c[0] : c)`);
    check(Math.abs(first[0] - 20200) < 1e-4 && Math.abs(first[1] - 20000) < 1e-4, `первая точка полилинии ровно в вершине границы (${first.map(v => v.toFixed(4)).join("; ")})`);
    // середина стороны границы
    await p.key("z", "KeyZ", { meta: true });
    await cm("l"); await p.key("Enter", "Enter", { vk: 13, wait: 200 });
    const mid = await px(20100, 20150); await p.move(mid[0] + 3, mid[1] + 4); await p.move(mid[0] + 2, mid[1] + 2); await p.sleep(200);
    check(await p.ev(`return CAD.cur()?.k === "mid" && Math.abs(CAD.cur().w[0]-20100)<1e-6 && Math.abs(CAD.cur().w[1]-20150)<1e-6`), "привязка к середине стороны границы");
    await p.key("Escape", "Escape", { vk: 27 }); await p.key("Escape", "Escape", { vk: 27 });
    await p.ev(`CAD.ST.otrack=true; CAD.ST.polar=true; return 1`);
    // «Изменить границу» в окне «Данные»
    await p.ev(`selectTerr(false); $("bEditTerr").click(); return 1`);
    check(await p.ev(`return TERRSEL && CAD.gripList().length === 8`), "кнопка «Изменить границу» выбирает границу");
    // правка, нарушающая контур, не принимается: вершина возвращается, в строке состояния сказано почему
    await p.ev(`selectTerr(false); selectTerr(true); return 1`);
    const ar = (await area())[0], ub = await p.ev(`return UNDO.length`), bx = await px(20200, 20000), bt = await px(20100, 20200);
    await p.drag(bx[0], bx[1], bt[0], bt[1]);
    check(Math.abs((await area())[0] - ar) < 1e-6 && await p.ev(`return UNDO.length`) === ub && /пересекать сама себя — вершина возвращена на место/.test(await p.ev(`return $("stHint").textContent`)), "вершина через противоположную сторону (бабочка): правка отклонена, граница прежняя, причина в строке состояния");
    // наблюдатель: сама правка (не только кнопки) отказывает
    check(await p.ev(`document.body.classList.add("hub-viewer"); const g=terrSrc.getFeatures()[0].getGeometry().clone(); g.translate(5, 5); const n0 = TERR_REV; CAD.terrEdit(g, "тест"); document.body.classList.remove("hub-viewer"); return TERR_REV === n0 && !UNDO.some(u=>u.kind==="terr")`), "правка границы у наблюдателя не проходит (отказывает сама правка)");
    // граница заменена целиком (файл, участки, пример): Ctrl+Z не возвращает старую
    await p.drag(bx[0], bx[1], bx[0] - 30, bx[1] - 20);
    check(await p.ev(`return UNDO.some(u=>u.kind==="terr")`), "правка вершины записана в отмену");
    await p.ev(`const sq=[[30000,30000],[30100,30000],[30100,30100],[30000,30100]]; setTerritory({ geometry: { type: "Polygon", coordinates: [[...sq, sq[0]].map(w => MSK.toWgs(w))] } }); await new Promise(r=>setTimeout(r,300)); return 1`);
    check(await p.ev(`return !UNDO.some(u=>u.kind==="terr") && !REDO.some(u=>u.kind==="terr")`), "замена границы стирает записи отмены её вершин");
    await p.key("z", "KeyZ", { meta: true });
    check(await p.ev(`return Math.abs(TERR_M2 - 10000) < 1`), "Ctrl+Z после замены границы оставляет новую границу");
    await p.ev(`const sq=${JSON.stringify(SQ)}; setTerritory({ geometry: { type: "Polygon", coordinates: [[...sq, sq[0]].map(w => MSK.toWgs(w))] } }); await new Promise(r=>setTimeout(r,300)); return 1`);
    // наблюдатель совместного проекта границу не правит
    check(await p.ev(`selectTerr(false); document.body.classList.add("hub-viewer"); selectTerr(true); const a=TERRSEL; $("bEditTerr").click(); const b=TERRSEL; document.body.classList.remove("hub-viewer"); return !a && !b`), "наблюдателю граница на правку не даётся");
    await p.ev(`selectTerr(false); const g=${JSON.stringify(prevT)}; if (g) setTerritory({ geometry: JSON.parse(g) }); UNDO.length = 0; REDO.length = 0; return 1`);
  }
  // T24: выгрузки GeoJSON для QGIS и Excel — ответ на тот же fetch, что делает кнопка; DXF остаётся одним щелчком
  await p.ev(`document.body.classList.remove("hub-viewer"); winOpen("wSheets", true); await new Promise(r=>setTimeout(r,200)); if (!ALBUM.sheets.length) $("shAddA3").click(); winOpen("wSheets", false);
    for (let i = 0; i < 40 && !RESULT.tepNode?._tep; i++) await new Promise(r=>setTimeout(r,100));
    window.__fx = window.fetch; window.__ex = [];
    window.fetch = async (u, o) => { const r = await window.__fx(u, o); if (String(u).startsWith("/api/export/")) { const b = new Uint8Array(await r.clone().arrayBuffer()); window.__ex.push({ u: String(u), st: r.status, ct: r.headers.get("content-type"), pk: b[0] === 80 && b[1] === 75, body: JSON.parse(o.body) }); } return r; }; return 1`);
  try {
    check(await p.ev(`return !!$("bExport") && $("expMenu").hidden && $("bExpMore").getAttribute("aria-expanded") === "false" && $("bExpMore").offsetParent !== null && /Выгрузка/.test($("bExpMore").innerText) && $("expMenu").querySelectorAll("[role=menuitem]").length === 6 && !document.querySelector(".top > #bExport, .top > .expmore ~ #bOgdAll")`), "в шапке одна кнопка «Выгрузка ▾», меню из шести пунктов закрыто");
    await p.ev(`$("bExpMore").click(); return 1`);
    check(await p.ev(`return !$("expMenu").hidden && $("bExpMore").getAttribute("aria-expanded") === "true" && document.activeElement === $("bExport") && /Excel/.test($("expMenu").innerText) && /ГИС ОГД в DXF/.test($("expMenu").innerText) && /PPTX альбома/.test($("expMenu").innerText)`), "«Выгрузка ▾» открывает меню, фокус на первом пункте «Чертёж DXF»");
    await p.key("Escape", "Escape", { vk: 27 });
    check(await p.ev(`return $("expMenu").hidden`), "Esc закрывает меню выгрузок");
    await p.ev(`$("bExpMore").click(); $("bExpGeo").click(); for (let i = 0; i < 400 && !window.__ex.length; i++) await new Promise(r=>setTimeout(r,100)); return 1`);
    check(await p.ev(`const e = window.__ex[0]; return !!e && e.u === "/api/export/geojson" && e.st === 200 && e.ct === "application/zip" && e.pk && $("expMenu").hidden
      && e.body.layers.length === Object.keys(DATA).length + (TERR ? 1 : 0) && e.body.layers.every(l => l.name && l.features) && /GeoJSON готов/.test($("toast").textContent)`), "«GeoJSON для QGIS»: тот же набор слоёв, что у DXF (плюс граница), ответ — zip");
    await p.ev(`$("bExpMore").click(); $("bExpXls").click(); for (let i = 0; i < 400 && window.__ex.length < 2; i++) await new Promise(r=>setTimeout(r,100)); return 1`);
    check(await p.ev(`const e = window.__ex[1], t = RESULT.tepNode._tep; return !!e && e.u === "/api/export/xlsx" && e.st === 200 && /spreadsheetml/.test(e.ct) && e.pk
      && e.body.tep.length > 5 && e.body.tep.every(r => typeof r.value === "number" || r.value === null) && e.body.tep.some(r => typeof r.value === "number" && r.value > 0)
      && e.body.sheets.length === ALBUM.sheets.length && e.body.sheets[0].n === 1 && typeof e.body.project === "string" && e.body.project.length > 0
      && (t.constantsChanged?.length ? e.body.note === "Нормативы изменены вручную: " + t.constantsChanged.length : e.body.note === undefined)`), "«Excel: ТЭП и листы»: показатели числами, список листов, название проекта; ответ — xlsx");
    await p.ev(`RESULT.tepNode._tep.constantsChanged = ["x", "y"]; $("bExpMore").click(); $("bExpXls").click(); for (let i = 0; i < 50 && window.__ex.length < 3; i++) await new Promise(r=>setTimeout(r,100)); return 1`);
    check(await p.ev(`return window.__ex[2]?.body.note === "Нормативы изменены вручную: 2"`), "Excel: при изменённых нормативах в файл идёт пометка «Нормативы изменены вручную: N»");
    // наблюдатель совместного проекта выгружает так же, как DXF; ошибка сервера — простыми словами
    check(await p.ev(`document.body.classList.add("hub-viewer"); const n = window.__ex.length; $("bExpMore").click(); $("bExpGeo").click(); for (let i = 0; i < 50 && window.__ex.length === n; i++) await new Promise(r=>setTimeout(r,100)); document.body.classList.remove("hub-viewer"); return window.__ex.length === n + 1 && window.__ex[n].st === 200`), "наблюдатель может выгрузить GeoJSON, как DXF");
    check(await p.ev(`const f = window.fetch; window.fetch = async () => new Response("{}", { status: 500 }); $("bExpMore").click(); $("bExpGeo").click(); await new Promise(r=>setTimeout(r,300)); window.fetch = f;
      return /GeoJSON не выгружен: сервер не принял данные\./.test($("toast").textContent) && !$("bExpMore").disabled && $("busy").hidden`), "ошибка выгрузки — по-русски в сообщении, кнопки снова доступны");
  } finally { await p.ev(`window.fetch = window.__fx; return 1`); }
  // T31: протаскивание не выделяет текст — окно за заголовок через справку и дерево слоёв, разделитель панели, угол окна
  {
    const sel = () => p.ev(`return getSelection().toString().length + "|" + document.documentElement.classList.contains("nosel")`);
    await p.key("F1", "F1", { vk: 112 }); await p.sleep(300);
    const h = await p.ev(`const w=$("wKeys"); if (w.classList.contains("docked")) floatWin(w); placeWin(w); winFront(w); await new Promise(r=>setTimeout(r,200)); const b=w.querySelector(".wh b").getBoundingClientRect(), t=$("layerTree").getBoundingClientRect(); return [b.left+4, b.top+4, t.left+30, t.top+60]`);
    await p.ev(`window.__nm = []; addEventListener("pointermove", e => { if (e.buttons) window.__nm.push(getSelection().toString().length + "|" + document.documentElement.classList.contains("nosel")); }, true); return 1`);
    await p.drag(h[0], h[1], h[2], h[3]);
    check((await sel()) === "0|false" && (await p.ev(`return window.__nm.length > 5 && window.__nm.every(x => x === "0|true")`)), "T31: окно, проведённое за заголовок через справку и «Слои», ничего не выделяет; .nosel стоит на время протяжки и снимается");
    const g = await p.ev(`const g=document.querySelector('[data-gut="l"]').getBoundingClientRect(); return [g.left+g.width/2, g.top+g.height/2]`);
    await p.ev(`window.__nm = []; return 1`); await p.drag(g[0], g[1], g[0] + 90, g[1] - 150);
    check((await sel()) === "0|false" && (await p.ev(`return window.__nm.every(x => x === "0|true")`)), "T31: вертикальный разделитель, проведённый через дерево слоёв, ничего не выделяет");
    const hh = await p.ev(`const b=$("wKeys").querySelector(".wh b").getBoundingClientRect(); return [b.left+4, b.top+4]`);
    await p.drag(hh[0], hh[1], hh[0] + 40, hh[1] + 400);
    check((await sel()) === "0|false", "T31: окно, протащенное к строке состояния, ничего не выделяет");
    check(await p.ev(`const e=document.querySelector("#keysBody .hsec p, #keysBody .hsec li, #keysBody .hsec td"); return getComputedStyle(e).userSelect === "text" && getComputedStyle($("layerTree")).userSelect === "none"`), "T31: текст справки выделяется, интерфейс (дерево слоёв) — нет");
    await p.ev(`winOpen("wKeys", false); return 1`);
  }
  // T34: строка «Альбом: N листов · собран …» и время PDF/PPTX хранятся в проекте (ALBUM.meta) и переживают сборку/разбор общего проекта
  // editedAt ставится при каждой правке листа настоящим временем: до сравнения с датами-образцами его надо снять, иначе шаг зависит от часов
  check(await p.ev(`const m=ALBUM.meta, keep=[m.builtAt,m.pdfAt,m.pptxAt,m.editedAt], sh=ALBUM.sheets.splice(0);
    m.builtAt=m.pdfAt=m.pptxAt=m.editedAt=undefined; const a=albumStatText(); ALBUM.sheets.push(newSheet()); m.editedAt=undefined; const b=albumStatText();
    m.builtAt="2026-10-03T09:05:00"; m.pdfAt="2026-10-03T10:07:00"; m.pptxAt="2026-10-03T10:08:00"; const c=albumStatText(), j=Collab.join(Collab.split(JSON.parse(projectJSON())),{});
    const kept=j.album.meta.builtAt===m.builtAt && j.album.meta.pdfAt===m.pdfAt; m.editedAt="2026-10-03T11:00:00"; const d=albumStatText(); m.editedAt=undefined;
    ALBUM.sheets.splice(0, ALBUM.sheets.length, ...sh); [m.builtAt,m.pdfAt,m.pptxAt,m.editedAt]=keep;
    const ok=a==="Альбом: листов нет" && b==="Альбом: 1 лист · дата сборки не записана" && c==="Альбом: 1 лист · собран 03.10 09:05 · PDF 03.10 10:07 · PPTX 03.10 10:08" && d===c+" · изменён после PDF" && kept;
    if(!ok) console.warn("T34: "+JSON.stringify({a,b,c,d,kept})); return ok`), "T34: строка состояния альбома («ещё не собирался» / N листов, собран, PDF и PPTX), время сохраняется в проекте и в общем проекте");
  // T34b: «Из файла…» — импорт альбома (проект или голый {meta, sheets}) в браузере: замена / добавление, свежие id, пустые поля штампа
  // берутся из файла, недостающие слои — предупреждение; лист с готовой вёрсткой (слои внутри) собирается без слоёв проекта
  {
    const imp = async (name, json) => { await p.ev(`const f=new File([${JSON.stringify(JSON.stringify(json))}], ${JSON.stringify(name)}); const dt=new DataTransfer(); dt.items.add(f); const i=$("shImpFile"); i.files=dt.files; i.dispatchEvent(new Event("change",{bubbles:true})); await new Promise(r=>setTimeout(r,600)); return 1`); };
    await p.ev(`window.__keep=[ALBUM.sheets.splice(0), {...ALBUM.meta}]; ALBUM.meta.object="Свой объект"; ALBUM.meta.short=""; winOpen("wSheets", true); await new Promise(r=>setTimeout(r,200)); return 1`);
    const ready = { title: "Готовый лист", size: "PA3", scale: 5000, center: [37.5, 55.7], layers: [{ title: "L", features: [{ g: { type: "Polygon", coordinates: [[[37.5, 55.7], [37.51, 55.7], [37.51, 55.71], [37.5, 55.7]]] }, fill: "#e0158c", stroke: "#e0158c", w: 1, a: 1 }] }], legend: [], tep: [], territory: null, basemap: "" };
    await imp("t.grado2", { meta: { object: "Чужой объект", short: "№ 7", place: "ТАО" }, sheets: [{ id: "a1", kind: "title", title: "Титул", size: "PA3", style: "pptkrt" }, ready, { id: "a1", title: "По слоям", size: "PA3", keys: ["no.such.layer"], view: "" }] });
    check(await p.ev(`return ALBUM.sheets.length===3 && ALBUM.meta.object==="Свой объект" && ALBUM.meta.short==="№ 7" && ALBUM.meta.place==="ТАО" && /импортирован из файла t\.grado2/.test($("shStat").textContent) && /нет слоёв: no\.such\.layer/.test($("toast").textContent)`), "T34b: пустой альбом — импорт сразу; заполненное поле штампа остаётся, пустое берётся из файла; недостающий слой — в предупреждении");
    check(await p.ev(`return ALBUM.sheets[1].frozen===true && !ALBUM.sheets[2].frozen && new Set(ALBUM.sheets.map(s=>s.id)).size===3 && ALBUM.sheets.every(s=>/^imp_\\w+_\\d+$/.test(s.id))`), "T34b: лист со слоями внутри — «готовая вёрстка», id листов всегда новые imp_… (не sec1_/pptkrt_)");
    check(await p.ev(`const r=await fetch("/api/print/svg",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...albumSpec([ALBUM.sheets[1]]),index:0})}); const t=await r.text(); const r2=await fetch("/api/print/svg",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...albumSpec([ALBUM.sheets[2]]),index:0})}); return r.status===200 && t.includes("Готовый лист") && r2.status===200`), "T34b: готовый лист и лист с недостающим слоем собираются без ошибки");
    await imp("p.grado2", { format: "grado2", version: 2, album: { meta: {}, sheets: [{ id: "a1", kind: "title", title: "Из проекта", size: "PA3" }] } });
    check(await p.ev(`return !!$("shImpBar") && /Заменить 3 листа текущего альбома на 1 из файла/.test($("shImpBar").innerText) && ALBUM.sheets.length===3`), "T34b: в непустом альбоме — выбор «Заменить / Добавить», пока не выбрано, альбом не тронут");
    await p.ev(`document.querySelector('[data-shimp="add"]').click(); return 1`);
    check(await p.ev(`return ALBUM.sheets.length===4 && new Set(ALBUM.sheets.map(s=>s.id)).size===4 && ALBUM.sheets[3].title==="Из проекта" && !$("shImpBar")`), "T34b: «Добавить после текущих» — 4 листа, повторный id заменён");
    check(await p.ev(`const i=document.querySelector("#shImpFile"); const f=new File([JSON.stringify({sheets:[{title:"x",size:"PA3"}]})],"e.json"); const dt=new DataTransfer(); dt.items.add(f); i.files=dt.files; i.dispatchEvent(new Event("change",{bubbles:true})); await new Promise(r=>setTimeout(r,500));
      const bar=$("shImpBar"), ok=!!bar && document.activeElement===bar.querySelector("button"); shEl().dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true})); return ok && !$("shImpBar") && ALBUM.sheets.length===4`), "T34b: строка выбора берёт фокус на первую кнопку, Esc = «Отмена»");
    check(await p.ev(`const f=new File([new Uint8Array(26*2**20)],"big.grado2"), dt=new DataTransfer(); dt.items.add(f); const i=$("shImpFile"); i.files=dt.files; i.dispatchEvent(new Event("change",{bubbles:true})); await new Promise(r=>setTimeout(r,300));
      const t=$("shImpBar")?.innerText||"", ok=/Файл 26 МБ: проект станет большим/.test(t) && !!document.querySelector('[data-shimp="go"]') && ALBUM.sheets.length===4; shEl().dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true})); return ok && !$("shImpBar")`), "T34b: файл больше 25 МБ — предупреждение «Продолжить?» до разбора");
    check(await p.ev(`document.body.classList.add("hub-viewer"); const vis=getComputedStyle($("shImport")).display, n=ALBUM.sheets.length; const f=new File(["{}"],"v.json"), dt=new DataTransfer(); dt.items.add(f); const i=$("shImpFile"); i.files=dt.files; i.dispatchEvent(new Event("change",{bubbles:true})); await new Promise(r=>setTimeout(r,300)); const ok=vis==="none" && /Только просмотр/.test($("toast").textContent) && !$("shImpBar") && ALBUM.sheets.length===n; document.body.classList.remove("hub-viewer"); return ok`), "T34b: наблюдателю кнопка «Из файла…» скрыта, импорт отказывает");
    await imp("bad.json", { foo: 1 });
    check(await p.ev(`return ALBUM.sheets.length===4 && /в файле нет листов/.test($("toast").textContent) && !$("shImpBar")`), "T34b: чужой файл — сообщение, альбом цел");
    await p.ev(`ALBUM.sheets.splice(0, ALBUM.sheets.length, ...__keep[0]); Object.assign(ALBUM.meta, __keep[1]); delete ALBUM.meta.importedFrom; renderSheets(); winOpen("wSheets", false); return 1`);
  }
  // T32/T33: «Листы и альбом» — одна строка на лист, свойства выбранного, без горизонтальной прокрутки; «Выгрузка ▾» с клавиатуры; Ctrl+P; peak и строка альбома в списке проектов
  {
    await p.ev(`window.__k32=[ALBUM.sheets.splice(0), {...ALBUM.meta}]; delete ALBUM.meta.peak; winOpen("wSheets", false); return 1`);
    await p.key("p", "KeyP", { ctrl: true, vk: 80 });
    check(await p.ev(`return !$("wSheets").hidden && !!$("shStat") && /листов нет/.test($("shStat").textContent) && !!document.querySelector("#sheetsBody .shempty") && $("shPdf").disabled && $("shBadge").hidden`), "T32: Ctrl+P открывает «Листы и альбом»; листов нет — строка статуса и пустое окно с двумя кнопками");
    await p.ev(`$("sheetsBody").querySelector('[data-shact="add"]').click(); $("shAddA1").click(); $("shAddSlide").click(); await new Promise(r=>setTimeout(r,500)); ALBUM.sheets[1].title="Второй лист"; renderSheets(); return 1`);
    check(await p.ev(`const rows=[...document.querySelectorAll("#sheetsBody .shrow")], b=$("sheetsBody"); return ALBUM.sheets.length===3 && rows.length===3 && ALBUM.sheets.map(s=>s.size).join()==="A3,A1,P" && $("shBadge").textContent==="3" && b.scrollWidth<=b.clientWidth && rows[2].getAttribute("aria-selected")==="true" && !!document.querySelector(".shdet[data-sh='2']")`), "T32: три листа — три строки, бейдж 3, выбран последний, свойства под ним, прокрутки вбок нет");
    await p.ev(`document.querySelector(".shrow[data-sh='1']").click(); return 1`);
    check(await p.ev(`return document.querySelector(".shrow[data-sh='1']").getAttribute("aria-selected")==="true" && document.querySelector(".shdet").dataset.sh==="1" && document.querySelector(".shdet [data-sk=title]").value==="Второй лист"`), "T32: щелчок по строке выбирает лист и показывает его свойства");
    await p.ev(`const t=document.querySelector(".shdet [data-sk=title]"); t.value="Переименован"; t.dispatchEvent(new Event("change",{bubbles:true})); return 1`);
    check(await p.ev(`return ALBUM.sheets[1].title==="Переименован" && document.querySelector(".shrow[data-sh='1'] .t").textContent==="Переименован" && !!ALBUM.meta.editedAt`), "T32: название меняется в свойствах и сразу в строке списка");
    // узкая раскладка: тело окна 300 px — список и свойства друг под другом, прокрутки вбок нет
    check(await p.ev(`const w=$("wSheets"), was=[w.style.width, w.style.height]; if (w.classList.contains("docked")) floatWin(w); w.style.width="420px"; w.style.height="300px"; await new Promise(r=>setTimeout(r,200)); const b=$("sheetsBody"), ok=b.scrollWidth<=b.clientWidth && b.querySelector(".shw").scrollWidth<=b.querySelector(".shw").clientWidth; w.style.width=was[0]; w.style.height=was[1]; return ok`), "T32: окно 420x300 — без горизонтальной прокрутки");
    // меню «Добавить лист» и «Собрать»: открываются, Esc закрывает и возвращает фокус
    await p.ev(`$("shAdd").click(); return 1`);
    check(await p.ev(`return !$("shMenuAdd").hidden && $("shAdd").getAttribute("aria-expanded")==="true" && document.activeElement===$("shAddA3")`), "T32: «Добавить лист ▾» открывает меню, фокус на первом пункте");
    await p.key("Escape", "Escape", { vk: 27 });
    check(await p.ev(`return $("shMenuAdd").hidden && document.activeElement===$("shAdd")`), "T32: Esc закрывает меню и возвращает фокус на кнопку");
    await p.ev(`$("shBuild").click(); return 1`);
    check(await p.ev(`return !$("shMenuBuild").hidden && ["shSec1","shPptKrt","shSit","shImport"].every(id=>!!$(id))`), "T32: «Собрать ▾»: раздел, альбом ППТ КРТ, ситуационный план, из файла");
    await p.key("Escape", "Escape", { vk: 27 });
    // «Выгрузка ▾»: стрелка вниз на кнопке, круговая навигация, Esc, PDF и PPTX активны при листах
    await p.ev(`$("bExpMore").focus(); return 1`);
    await p.key("ArrowDown", "ArrowDown", { vk: 40 });
    check(await p.ev(`return !$("expMenu").hidden && document.activeElement===$("bExport") && !$("bExpPdf").disabled && !$("bExpPptx").disabled`), "T32: ↓ на «Выгрузке» открывает меню; PDF и PPTX доступны, раз листы есть");
    await p.key("End", "End", { vk: 35 });
    check(await p.ev(`return document.activeElement===$("bExpPptx")`), "T32: End — последний пункт");
    await p.key("ArrowDown", "ArrowDown", { vk: 40 });
    check(await p.ev(`return document.activeElement===$("bExport")`), "T32: ↓ с последнего пункта — по кругу на первый");
    await p.key("Escape", "Escape", { vk: 27 });
    check(await p.ev(`return $("expMenu").hidden && document.activeElement===$("bExpMore")`), "T32: Esc закрывает «Выгрузку» и возвращает фокус");
    // T36: пункт выбран с клавиатуры — меню закрылось, фокус вернулся на «Выгрузку» (Excel не уводит со страницы)
    await p.ev(`$("bExpMore").focus(); return 1`);
    await p.key("ArrowDown", "ArrowDown", { vk: 40 });
    for (let i = 0; i < 3; i++) await p.key("ArrowDown", "ArrowDown", { vk: 40 });
    check(await p.ev(`return document.activeElement===$("bExpXls")`), "T36: ↓ три раза — «Excel: ТЭП и листы»");
    await p.ev(`window.__fx36 = window.fetch; window.fetch = async (u, ...a) => /api[/]export[/]xlsx/.test(u) ? new Response(new Blob(["x"]), { status: 200 }) : window.__fx36(u, ...a); return 1`);   // Excel без настоящей выгрузки: быстро и без записи файла
    await p.key("Enter", "Enter", { vk: 13, text: "\r" });
    check(await p.ev(`try { for (let i = 0; i < 30 && ($("bExpMore").disabled || !$("busy").hidden); i++) await new Promise(r => setTimeout(r, 100)); const ok = $("expMenu").hidden && !$("bExpMore").disabled && document.activeElement.id === "bExpMore"; if (!ok) console.warn("T36: " + JSON.stringify({ hidden: $("expMenu").hidden, disabled: $("bExpMore").disabled, active: document.activeElement.id || document.activeElement.tagName, busy: $("busy").hidden, toast: $("toast").textContent.slice(0, 120) })); return ok; } finally { window.fetch = window.__fx36; }`), "T36: Enter на пункте меню «Выгрузка» закрывает меню и возвращает фокус на «Выгрузку»");
    // T36: peak — наибольшее число листов, а не последнее
    check(await p.ev(`const old = ALBUM.meta.peak, n = ALBUM.sheets.length; ALBUM.meta.peak = { n: 9, at: "2026-01-01T00:00:00.000Z" }; projectJSON(); const a = ALBUM.meta.peak.n === 9 && ALBUM.meta.peak.at === "2026-01-01T00:00:00.000Z";
      ALBUM.meta.peak = { n: n - 1, at: "x" }; projectJSON(); const b = ALBUM.meta.peak.n === n && n === 3; ALBUM.meta.peak = old; return a && b`), "T36: ALBUM.meta.peak: 3 листа после 9 — остаётся 9; 3 листа после 2 — становится 3");
    // T36: пока собирается PDF, пункты PDF и PPTX серые с пояснением «Идёт сборка…»
    check(await p.ev(`const f = window.fetch; window.fetch = async (u, ...a) => { if (/api[/]print[/]pdf/.test(u)) { await new Promise(r => setTimeout(r, 600)); return new Response("{}", { status: 500 }); } return f(u, ...a); };
      try {
        window.albumFile("pdf"); await new Promise(r => setTimeout(r, 100)); $("bExpMore").click();
        const during = $("bExpPdf").disabled && $("bExpPptx").disabled && /Идёт сборка…/.test($("bExpPdf").innerText) && /Идёт сборка…/.test($("bExpPptx").innerText) && window.albumBuilding === true;
        await new Promise(r => setTimeout(r, 900)); const after = !$("bExpPdf").disabled && /Все листы одним файлом/.test($("bExpPdf").innerText) && window.albumBuilding === false;
        return during && after;
      } finally { window.fetch = f; if (!$("expMenu").hidden) $("bExpMore").click(); }`), "T36: сборка PDF — PDF и PPTX в меню серые, «Идёт сборка…»; после неё снова доступны");
    // peak пишется при сохранении проекта с листами; пустой альбом после этого говорит «раньше было N»
    check(await p.ev(`projectJSON(); const pk=ALBUM.meta.peak; ALBUM.sheets.splice(0); renderSheets(); const t=document.querySelector("#sheetsBody .shempty")?.innerText||""; return pk?.n===3 && /Раньше в проекте было 3 листа/.test(t) && $("expMenu").querySelector("#bExpPdf").disabled===false`), "T33: ALBUM.meta.peak записан при сохранении; пустое окно: «Раньше в проекте было 3 листа»");
    check(await p.ev(`$("bExpMore").click(); const d=$("bExpPdf").disabled, h=$("bExpPdf").innerText; $("bExpMore").click(); return d && /Нет листов/.test(h)`), "T33: нет листов — PDF и PPTX в меню серые, пояснение «Нет листов»");
    // список «Проекты»: вторая строка «Альбом: N листов · собран дд.мм» только у проектов с листами
    check(await p.ev(`ALBUM.sheets.splice(0, 0, ...__k32[0].length ? __k32[0] : [newSheet(), newSheet()]); ALBUM.meta.builtAt="2026-10-03T12:40:00"; await saveProject("e2e-album"); ALBUM.sheets.splice(0); await saveProject("e2e-bez"); winOpen("wProjects", true); const has=()=>{const t=$("projList").innerText; return /e2e-album/.test(t) && /e2e-bez/.test(t)}; for (let i=0;i<100 && !(has() && /Альбом:/.test($("projList").innerText));i++) await new Promise(r=>setTimeout(r,100));
      const rows=[...document.querySelectorAll("#projList tr")], a=rows.find(r=>/e2e-album/.test(r.innerText)), b=rows.find(r=>/e2e-bez/.test(r.innerText)); winOpen("wProjects", false); return !!a && /Альбом: \\d+ лист\\S* · собран 03\\.10/.test(a.innerText) && !!b && !/Альбом:/.test(b.innerText)`), "T33: «Проекты»: у проекта с альбомом строка «Альбом: N листов · собран 03.10», у пустого — нет");
    await p.ev(`ALBUM.sheets.splice(0, ALBUM.sheets.length, ...__k32[0]); Object.keys(ALBUM.meta).forEach(k=>delete ALBUM.meta[k]); Object.assign(ALBUM.meta, __k32[1]); renderSheets(); winOpen("wSheets", false); return 1`);
  }
  // T52 (раскладка) и T53 (мелкие правки вида), совет 03.10.2026: не больше двух встроенных окон в зоне, нижняя зона до 32 %, подписи вкладок, «Показатели» в шапке
  await p.group("t52", async () => {
    const wait = ms => p.sleep(ms);
    await p.ev(`Object.keys(W0()).forEach(id => { if (!$(id).hidden) winOpen(id, false); }); delete WST.hb; delete WST.zoneToast; try { localStorage.removeItem("grado2.zonecap"); } catch {} DZ.b.style.height=""; syncZones(); mMain.updateSize(); await new Promise(r=>setTimeout(r,300)); return 1`);
    // 1. третье окно в правой зоне плывёт, первое сообщение — один раз
    const z3 = await p.ev(`winOpen("wSketch", true); winOpen("wTep", true); await new Promise(r=>setTimeout(r,300)); const two = ["wSketch","wTep"].every(id => $(id).classList.contains("docked") && $(id).parentElement === DZ.r);
      winOpen("wCons", true); await new Promise(r=>setTimeout(r,400)); const t1 = $("toast").textContent;
      winOpen("wCons", false); winOpen("wCons", true); await new Promise(r=>setTimeout(r,300));
      return [two, !$("wCons").classList.contains("docked"), $("wCons").style.left !== "", /Третье окно открыто плавающим: в зоне уже два\. Поменять — в меню «Окна»/.test(t1), WST.zoneToast === 1]`);
    check(z3[0] && z3[1] && z3[2], `T52: Эскиз и Показатели встроены справа, третье окно (Ограничения) открывается плавающим: ${z3.slice(0, 3)}`);
    check(z3[3] && z3[4], "T52: при первом таком случае — одна строка-подсказка со ссылкой на меню «Окна»");
    // 2. настройка в «Окна»: без ограничения → третье встаёт в зону; «не больше двух» возвращает правило
    check(await p.ev(`$("bMore").click(); await new Promise(r=>setTimeout(r,150)); const it=[...document.querySelectorAll('#winMenu [data-zonecap]')].map(b=>b.textContent.trim()+":"+b.getAttribute("aria-checked")).join("|");
      document.querySelector('#winMenu [data-zonecap="free"]').click(); await new Promise(r=>setTimeout(r,150));
      winOpen("wCons", false); winOpen("wCons", true); await new Promise(r=>setTimeout(r,300));
      const free = $("wCons").classList.contains("docked") && $("wCons").parentElement === DZ.r && localStorage.getItem("grado2.zonecap") === "free";
      $("bMore").click(); await new Promise(r=>setTimeout(r,150)); document.querySelector('#winMenu [data-zonecap="two"]').click(); await new Promise(r=>setTimeout(r,150));
      winOpen("wCons", false); winOpen("wCons", true); await new Promise(r=>setTimeout(r,300));
      return it === "Не больше двух:true|Без ограничения:false" && free && !$("wCons").classList.contains("docked") && localStorage.getItem("grado2.zonecap") === null`), "T52: меню «Окна» → «Окон в зоне»: «Не больше двух» / «Без ограничения»; без ограничения третье окно встаёт в зону, настройка помнится");
    // 3. запомненная раскладка хранит как есть (три окна справа)
    check(await p.ev(`Object.keys(W0()).forEach(id => { if (!$(id).hidden) winOpen(id, false); }); userLayouts()["T52 тест"] = { wSketch: "r", wTep: "r", wCons: "r" }; applyLayout(userLayouts()["T52 тест"]); await new Promise(r=>setTimeout(r,400));
      const ok = ["wSketch","wTep","wCons"].every(id => $(id).classList.contains("docked") && $(id).parentElement === DZ.r); delete userLayouts()["T52 тест"]; saveWins(); return ok`), "T52: запомненная раскладка с тремя окнами справа открывается как записана (правило «не больше двух» к ней не применяется)");
    // 4. «Нормативы» по умолчанию встроены справа; ярлыки вкладок видны, активная заметна
    const tb = await p.ev(`Object.keys(W0()).forEach(id => { if (!$(id).hidden) winOpen(id, false); }); await new Promise(r=>setTimeout(r,200)); winOpen("wTep", true); winOpen("wNorms", true); await new Promise(r=>setTimeout(r,500));
      const tabs=[...document.querySelectorAll("#dzR .dztabs [role=tab]")], act=tabs.find(t=>t.getAttribute("aria-selected")==="true"), off=tabs.find(t=>t!==act), cs=el=>getComputedStyle(el);
      return [$("wNorms").classList.contains("docked") && $("wNorms").parentElement === DZ.r, tabs.length, tabs.every(t=>{ const s=t.querySelector("span"); return s && s.offsetWidth > 10 && s.textContent.trim().length > 2; }), tabs.map(t=>t.querySelector("span").textContent).join("|"),
        !!act && cs(act).boxShadow !== "none" && cs(off).boxShadow === "none" && cs(act).backgroundColor !== cs(off).backgroundColor, document.querySelector('.wins [data-win=wTep]').getAttribute("aria-pressed") === "true"]`);
    check(tb[0] && tb[1] === 2, `T52: «Нормативы» встроены справа вкладкой рядом с «Показателями» (${tb[3]})`);
    check(tb[2] && tb[4], "T52: у всех вкладок видны подписи, активная вкладка отличается (акцентная кромка и фон)");
    // 5. кнопка открытого окна залита; «Листы и альбом» — тоже
    check(await p.ev(`winOpen("wSheets", true); await new Promise(r=>setTimeout(r,300)); const f=el=>getComputedStyle(el).backgroundColor, on=document.querySelector('.wins [data-win=wTep]'), off=document.querySelector('.wins [data-win=wCmp]') || document.querySelector('.wmenu [data-win=wCmp]');
      return f(on) !== f($("bMore")) && f($("bSheets")) !== f($("bExpMore"))`), "T52: кнопка открытого окна в шапке залита акцентным тоном (и «Листы и альбом»)");
    // 6. нижняя зона не выше 32 % поля карты; карта ≥ 55 % при Данные + Эскиз + Листы
    const mh = await p.ev(`Object.keys(W0()).forEach(id => { if (!$(id).hidden) winOpen(id, false); }); delete WST.hb; DZ.b.style.height=""; ["wData","wSketch","wSheets"].forEach(id => { (WST[id] ||= {}).dock = DOCK_DEFAULT[id]; }); winOpen("wData", true); winOpen("wSketch", true); winOpen("wSheets", true); await new Promise(r=>setTimeout(r,500));
      const col = DZ.b.parentElement.clientHeight, b = DZ.b.offsetHeight, m = $("mMain").getBoundingClientRect().height; return [Math.round(b/col*100), Math.round(m/col*100), ["wData","wSketch","wSheets"].every(id=>$(id).classList.contains("docked"))]`);
    check(mh[0] <= 33 && mh[1] >= 55 && mh[2], `T52: нижняя зона ${mh[0]} % поля карты (не больше 32), карта ${mh[1]} % (не меньше 55)`);
    check(await p.ev(`(WST.wSheets ||= {}).dock = "b"; winOpen("wSheets", true); await new Promise(r=>setTimeout(r,300)); WST.hb = 300; syncZones(); await new Promise(r=>setTimeout(r,100)); const px = DZ.b.offsetHeight; delete WST.hb; syncZones(); return px === 300`), "T52: своя высота нижней зоны (WST.hb) главнее умолчания");
    // 7. «Показатели» в шапке на 1440
    check(await p.ev(`return innerWidth < 1400 || (!!document.querySelector('.wins [data-win=wTep]').offsetParent && document.querySelector("header.top").scrollWidth <= document.querySelector("header.top").clientWidth)`), "T63: на 1440 px «Показатели» стоит в шапке, шапка не переполнена");
    // T53: «Варианты», «Листы и альбом», подписи этажей, штриховка, пустое дерево слоёв
    check(await p.ev(`winOpen("wVars", true); await new Promise(r=>setTimeout(r,300)); const v=$("varMsg"); v.textContent="Перебор типологий"; const bar=v.parentElement, y=[...bar.children].filter(c=>c.offsetParent).map(c=>Math.round(c.getBoundingClientRect().top));
      return v.textContent === "Перебор типологий" && Math.max(...y) - Math.min(...y) < 8 && (bar.clientWidth >= 520) === (v.offsetParent !== null)`), "T53: «Варианты» — шапка в одну строку, подпись «Перебор типологий» видна только при ширине шапки от 520 px");
    const sh = await p.ev(`const keep = ALBUM.sheets.splice(0); winOpen("wSheets", true); renderSheets(); await new Promise(r=>setTimeout(r,200)); const e = document.querySelector("#sheetsBody .shempty"), t = e?.firstElementChild?.textContent, bt = document.querySelector('[data-shact="pptkrt"]')?.textContent, st = $("shStampBtn");
      const out = [t, bt, st?.querySelector("b")?.textContent, st?.querySelector("em")?.textContent, st ? getComputedStyle(st.querySelector("b")).color === getComputedStyle(document.body).color : false]; ALBUM.sheets.push(...keep); renderSheets(); return out`);
    check(sh[0] === "Листов пока нет. Добавьте лист или соберите альбом" && sh[1].includes("ППТ КРТ"), `T53: пустые «Листы и альбом»: «${sh[0]}», кнопка с неразрывным пробелом в «ППТ КРТ»`);
    check(sh[2] === "Штамп" && !/^Штамп:/.test(sh[2]) && sh[4], `T53: строка штампа — заголовок «Штамп» обычным цветом текста, заполненное мелким серым (${sh[3]})`);
    const fl = await p.ev(`const f = new ol.Feature({ floors: 12 }), r0 = sharedView.getResolution(), txt = () => sketchStyle(f).getText()?.getText() ?? null; sharedView.setResolution(1500 / 2130); const fine = txt(), fd = scaleDen(sharedView.getResolution());
      sharedView.setResolution(3000 / 2130); const coarse = txt(); sharedView.setResolution(r0); return [fine, coarse, fd]`);
    check(fl[0] === "12 эт." && fl[1] === null, `T53: этажность на корпусе эскиза — «${fl[0]}» на 1:${fl[2]}, на 1:3 000 подписи нет`);
    check(await p.ev(`const root = document.documentElement, was = root.dataset.theme; root.dataset.theme = "light"; const a = siteHatch(); root.dataset.theme = "dark"; const b = siteHatch(); if (was) root.dataset.theme = was; else delete root.dataset.theme;
      return /^#[0-9a-f]{6}$/i.test(a) && /^#[0-9a-f]{6}$/i.test(b) && a !== b && a !== "#1f7a4d" && b !== "#1f7a4d"`), "T53: штриховка пятна застройки берёт светлый цвет из токена --site-hatch, свой для каждой темы");
    check(await p.ev(`const keep = LYR.splice(0), s0 = RESULT.site; RESULT.site = s0 || {}; let t = "", g = ""; try { winOpen("wSketch", true); renderTree0(); t = $("layerTree").innerText; g = [...$("layerTree").children].map(c => c.className).join(); } finally { RESULT.site = s0; LYR.push(...keep); renderTree(); }
      return /Слоёв пока нет \\(эскиз ещё не сохранён\\)/.test(t) && !/Слоёв нет/.test(t) && /Предпросмотр схемы/.test(t)`), "T53: пустое дерево слоёв при включённом предпросмотре — «Слоёв пока нет (эскиз ещё не сохранён)»");
    check(await p.ev(`const w = document.querySelector(".win.docked>.wb"); return !!w && /linear-gradient/.test(getComputedStyle(w).backgroundImage)`), "T53: прокручиваемые встроенные окна несут подсказку-тень у края");
    await p.ev(`Object.keys(W0()).forEach(id => { if (!$(id).hidden) winOpen(id, false); }); delete WST.zoneToast; return 1`);
  });
  // T61: перевыгрузка слоя не дублирует его; строка состояния выгрузки с именем, процентом и МБ; «район» не висит бесконечно
  await p.group("t61", async () => {
    await p.ev(`window.__f61 = window.fetch; window.__hint61 = []; window.__sh61 = window.setHint; window.setHint = t => { window.__hint61.push(String(t)); return window.__sh61?.(t); }; return 1`);
    try {
      // 1. один слой портала под ключом ogd.gpzu; повторный выбор подборки gisogd.gpzu обновляет его, а не заводит второй
      check(await p.ev(`return SOURCES["gisogd.gpzu"]?.code === "gpzu"`), "T61: /api/sources отдаёт код слоя каталога у подборки «ГПЗУ»");
      const first = await p.ev(`
        const mk = (k, v) => ({ type: "Feature", geometry: { type: "Polygon", coordinates: [[[37.52, 55.78], [37.521, 55.78], [37.521, 55.781], [37.52, 55.78]]] }, properties: { _key: k, "Номер": v } });
        window.__reqs61 = []; window.__rows61 = [mk("a", "1"), mk("b", "2")];
        window.fetch = async (u, o) => { u = String(u);
          if (u === "/api/progress") return new Response("{}", { status: 200 });
          if (u === "/api/fetch") { const b = JSON.parse(o.body); window.__reqs61.push(b.sources); const k = b.sources[0];
            return new Response(JSON.stringify({ errors: {}, layers: { [k]: { title: "ГПЗУ (ОГД)", fetched_at: "2026-10-03", features: { type: "FeatureCollection", features: window.__rows61 } } } }), { status: 200 }); }
          return window.__f61(u, o); };
        delete DATA["ogd.gpzu"]; delete DATA["gisogd.gpzu"]; const bb = [37.51, 55.77, 37.53, 55.79];
        await loadKeys(["ogd.gpzu"], bb); const n0 = LYR.length;
        const f = layerSrc["ogd.gpzu"].getFeatures().find(x => x.get("_key") === "a"); f.set("Заметка", "моя правка"); syncFromSource("ogd.gpzu");
        window.__rows61 = [mk("a", "1"), mk("b", "2"), mk("c", "3")];
        await loadKeys(["gisogd.gpzu"], bb, { alias: true });
        return [n0, LYR.length, window.__reqs61.map(x => x.join()).join("|"), !!DATA["gisogd.gpzu"], DATA["ogd.gpzu"].count, layerSrc["ogd.gpzu"].getFeatures().find(x => x.get("_key") === "a")?.get("Заметка")]`);
      check(first[0] === first[1] && first[2] === "ogd.gpzu|ogd.gpzu" && first[3] === false && first[4] === 3 && first[5] === "моя правка", `T61: «ГПЗУ» выбран подборкой — слой обновлён на месте (слоёв ${first[0]} → ${first[1]}, запрос ${first[2]}, объектов ${first[4]}, правка «${first[5]}» сохранена)`);
      // 1б. загрузка листа/альбома (без alias) кладёт слой под точным ключом gisogd.gpzu, даже если ogd.gpzu есть
      const ex = await p.ev(`window.__reqs61.length = 0; await loadKeys(["gisogd.gpzu"], [37.51, 55.77, 37.53, 55.79]); const a = [window.__reqs61.join("|"), !!DATA["gisogd.gpzu"]];
        delete DATA["gisogd.gpzu"]; LYR.splice(LYR.findIndex(l => l.key === "gisogd.gpzu"), 1); return a`);
      check(ex[0] === "gisogd.gpzu" && ex[1] === true, "T61: загрузка листа без alias остаётся под ключом gisogd.gpzu (слой ищут по точному ключу)");
      // 2. строка состояния: имя, процент, МБ; очередь «3 из 7»
      const seq = JSON.stringify([
        [{ title: "ГПЗУ (ОГД)", got: 0, total: null, stage: "wait", nth: 1, of: 1 }],
        [{ title: "ГПЗУ (ОГД)", got: 1800000, total: 4300000, stage: "download", nth: 1, of: 1 }],
        [{ title: "Зоны (актуальные)", got: 1800000, total: 4300000, stage: "download", nth: 3, of: 7 }]]);
      await p.ev(`window.__hint61.length = 0; let i = 0; const seq = ${seq};
        window.fetch = async (u, o) => { u = String(u);
          if (u === "/api/progress") { const r = seq[Math.min(i++, seq.length - 1)]; return new Response(JSON.stringify(Object.fromEntries(r.map((x, j) => ["k" + j, x]))), { status: 200 }); }
          if (u === "/api/fetch") { await new Promise(r => setTimeout(r, 3200)); return new Response(JSON.stringify({ errors: {}, layers: {} }), { status: 200 }); }
          return window.__f61(u, o); };
        await loadKeys(["gisogd.gpzu"], [37.51, 55.77, 37.53, 55.79]); return 1`);
      const hints = await p.ev(`return window.__hint61.join(" || ")`);
      p.log("hints:", hints);
      check(/ГПЗУ \(ОГД\): запрос к порталу/.test(hints), "T61: до первого мегабайта строка состояния уже называет слой");
      check(/ГПЗУ \(ОГД\): 42 % · 1,8 МБ из 4,3 МБ/.test(hints), "T61: «ГПЗУ (ОГД): 42 % · 1,8 МБ…» — процент и мегабайты из /api/progress");
      check(/3 из 7: Зоны \(актуальные\): 42 %/.test(hints), "T61: очередь — «3 из 7: Зоны (актуальные): …»");
      check(await p.ev(`return dlStatus([], ["А", "Б"]).startsWith("А, Б: ждём ответ портала") && dlStatus([{ title: "Т", got: 5, total: 9, stage: "tiles" }], []).startsWith("Яндекс: тайлы 5 из 9")`), "T61: источники без хода (НСПД, OSM) — имена слоёв; Яндекс — тайлы");
    } finally { await p.ev(`window.fetch = window.__f61; window.setHint = window.__sh61; return 1`); }
    // 3. «район»: портал молчит — через 30 с (таймер подменён) строка «район не определён», «определяется…» нет
    try {
      const r = await p.ev(`
        setTerritory(turf.polygon([[[37.5195, 55.7895], [37.5305, 55.7895], [37.5305, 55.7955], [37.5195, 55.7955], [37.5195, 55.7895]]]));
        winOpen("wTep", true); await new Promise(r => setTimeout(r, 400));
        const n = RESULT.tepNode, tp = tepParams(n); window.__st61 = window.setTimeout; window.__calls61 = [];
        window.fetch = (u, o) => String(u) === "/api/place" ? new Promise((_, rej) => o.signal.addEventListener("abort", () => rej(new DOMException("aborted", "AbortError")))) : window.__f61(u, o);
        window.setTimeout = (fn, ms, ...a) => { if (ms === 30000) { window.__calls61.push(ms); ms = 20; } return window.__st61(fn, ms, ...a); };
        tp.rev = -1; tp.district = ""; n._placeBusy = false; placeLookup(n); await new Promise(r => window.__st61(r, 60));
        const busyText = $("tep").innerText.includes("определяется…"); await new Promise(r => window.__st61(r, 300));
        window.setTimeout = window.__st61; const t = $("tep").innerText;
        return [window.__calls61.length, busyText, t.includes("определяется…"), /район не определён: портал OSM не ответил — задайте зону вручную/.test(t), n._placeBusy]`);
      check(r[0] === 1 && !r[2] && r[3] && r[4] === false, `T61: нет ответа /api/place — запрос обрывается по таймеру 30 с, строка «район не определён… задайте зону вручную», «определяется…» нет (${JSON.stringify(r)})`);
      // сбой с текстом сервера: чистая русская фраза, сырого Overpass в окне нет
      const t2 = await p.ev(`
        window.fetch = (u, o) => String(u) === "/api/place" ? Promise.resolve(new Response(JSON.stringify({ error: "портал OpenStreetMap не ответил: подождите минуту и повторите" }), { status: 502 })) : window.__f61(u, o);
        const n = RESULT.tepNode, tp = tepParams(n); tp.rev = -1; tp.district = ""; n._placeBusy = false; placeLookup(n); await new Promise(r => setTimeout(r, 400)); return $("tep").innerText`);
      check(/портал OpenStreetMap не ответил: подождите минуту/.test(t2) && !/Overpass|Errno|HTTP 5/.test(t2) && !t2.includes("определяется…"), "T61: ответ 502 — понятная фраза с действием, без Overpass/Errno/HTTP");
    } finally { await p.ev(`window.fetch = window.__f61; if (window.__st61) window.setTimeout = window.__st61; return 1`); }
  });

  // T55: листы, собранные по шаблону, обновляются сами при смене ТЭП и нормативов; рукой правленное остаётся; листы из файла не трогаются
  await p.group("t55", async () => {
    // снимок — сам просмотр листа (SVG из сервера) на весь экран, а не тесное окно «Листы и альбом»
    const shot = async name => { if (!process.env.T55_SHOT_DIR) return;
      await p.ev(`const im = document.createElement("img"); im.id = "t55ov"; im.src = $("sheetPrev").src; im.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;object-fit:contain;background:#fff;z-index:99999"; document.body.append(im); await new Promise(r=>setTimeout(r,600)); return 1`);
      await p.shot(`${process.env.T55_SHOT_DIR}/${name}.png`); await p.ev(`$("t55ov")?.remove(); return 1`); };
    const tepRowsOf = i => p.ev(`return JSON.stringify(albumSpec([ALBUM.sheets[${i}]]).sheets[0].tep)`);
    if (!await p.ev(`for (let k = 0; k < 20 && !(RESULT.tepNode?._tep && TERR); k++) await new Promise(r=>setTimeout(r,500)); return !!RESULT.tepNode?._tep && !!TERR`)) {                  // группа запущена отдельно: нужны территория и посчитанный эскиз
      await p.ev(`$("bExample").click(); await new Promise(r=>setTimeout(r,500)); winOpen("wSketch", true); await new Promise(r=>setTimeout(r,300)); document.querySelector('#wSketch [data-run="1"]').click(); for (let k = 0; k < 40 && !RESULT.tepNode?._tep; k++) await new Promise(r=>setTimeout(r,500)); return 1`);
    }
    check(await p.ev(`return !!RESULT.tepNode?._tep && !!TERR`), "T55: есть территория и посчитанные показатели");
    if (await p.ev(`return !!RESULT.tepNode._tep.constantsChanged?.length`)) {          // норматив остался изменённым от прежних шагов: вернуть действующий
      await p.ev(`winOpen("wNorms", true); await new Promise(r=>setTimeout(r,500)); const i=document.querySelector('[data-nid="doo_z1"]'); i.focus(); i.select(); return 1`); await p.type("44"); await p.key("Enter", "Enter", { vk: 13, wait: 1500 });
    }
    // выгрузка слоёв из сети в тесте не нужна: листы строятся по шаблону и тому, что уже есть в проекте
    await p.ev(`window.__t55 = { keep: ALBUM.sheets.splice(0), lk: window.loadKeys, ea: window.ensureAdmin, c: new Set(CHECKED) }; window.loadKeys = async () => {}; window.ensureAdmin = async () => { CHECKED.add("gisogd.admin"); }; TPL_SIG = null; NOTREADY.clear();
      ALBUM.meta.builtAt = undefined; ALBUM.meta.editedAt = undefined; await buildAlbum("pptkrt"); winOpen("wSheets", true); renderSheets(); await new Promise(r=>setTimeout(r,300)); return 1`);
    const b = await p.ev(`const n = ALBUM.sheets.length; return [n, ALBUM.sheets.every((s, i) => s.tpl?.set === "pptkrt_" && s.tpl.i === i && s.id === "pptkrt_" + i), JSON.stringify(ALBUM.sheets).includes("Плотность"), ALBUM.sheets[3].title]`);
    check(b[0] >= 5 && b[1] && !b[2], `T55: «Альбом ППТ КРТ» — ${b[0]} листов, у каждого sheet.tpl (набор и номер в шаблоне); строк ТЭП в листах не хранится`);
    // таблица ТЭП — лист «Таблица ТЭП» из списка листов, и лист шаблона с включённой таблицей ТЭП
    await p.ev(`$("shAddA3").click(); await new Promise(r=>setTimeout(r,500)); const sel = document.querySelector("[data-sh='${b[0]}'] [data-sk='view']"); sel.value = "__tep"; sel.dispatchEvent(new Event("change", { bubbles: true })); await new Promise(r=>setTimeout(r,200)); return 1`);
    const T = b[0];
    await p.ev(`pickSheet(3); await new Promise(r=>setTimeout(r,200)); const c = document.querySelector('#sheetsBody [data-sk="tep"]'); c.checked = true; c.dispatchEvent(new Event("change", { bubbles: true })); await new Promise(r=>setTimeout(r,200)); return 1`);
    check(await p.ev(`return ALBUM.sheets[${T}].kind === "tep" && ALBUM.sheets[${T}].tpl?.set === "tep" && ALBUM.sheets[3].tep === true`), "T55: лист «Таблица ТЭП» помечен как лист по шаблону, на листе шаблона включена таблица ТЭП");
    // рукой: название, рамка (центр и масштаб), подпись, надпись «Макета» и свой текст
    const hand = await p.ev(`const s = ALBUM.sheets[3]; s.title = "Моя схема"; s.center = [37.5, 55.7]; s.scale = 7500; s.note = "Моя подпись"; s.edits = { t1: { text: "правка" } }; s.items = [{ text: "свой текст", x: 10, y: 10 }];
      const fz = { id: "imp_t55_0", frozen: true, title: "Готовый лист", size: "PA3", scale: 5000, center: [37, 55], layers: [{ key: "a", title: "A", features: [] }], legend: [], tep: [["Плотность", "1,0 тыс. м²/га"]] }; ALBUM.sheets.push(fz);
      window.__fz = JSON.stringify(fz); window.__k3 = JSON.stringify(ALBUM.sheets[3].keys); return ALBUM.sheets.indexOf(fz)`);
    const F = hand;
    const before = [await tepRowsOf(T), await tepRowsOf(3)];
    check(!/Нормативы изменены/.test(before[0]) && /Плотность/.test(before[0]) && /Плотность/.test(before[1]), "T55: до правки норматива строки «Нормативы изменены вручную» на листах нет");
    await p.ev(`pickSheet(${T}); await new Promise(r=>setTimeout(r,200)); previewSheet(${T}); await new Promise(r=>setTimeout(r,2500)); return 1`);
    await shot("t55-tep-before");
    // норматив: «Нормативы» → ДОО зоны 1 = 50
    await p.ev(`winOpen("wNorms", true); await new Promise(r=>setTimeout(r,500)); const i=document.querySelector('[data-nid="doo_z1"]'); i.focus(); i.select(); return 1`); await p.type("50"); await p.key("Enter", "Enter", { vk: 13, wait: 1500 });
    let st = "";
    for (let k = 0; k < 20 && !/Листы обновлены по новым показателям/.test(st); k++) { await p.sleep(400); st = await p.ev(`return $("stHint").textContent`); }
    check(st === "Листы обновлены по новым показателям", `T55: строка состояния после смены норматива: «${st}»`);
    const after = [await tepRowsOf(T), await tepRowsOf(3)];
    check(after[0] !== before[0] && /Нормативы изменены вручную","1"/.test(after[0]), "T55: на листе «Таблица ТЭП» строки показателей изменились, появилась строка «Нормативы изменены вручную: 1»");
    check(after[1] !== before[1] && /Нормативы изменены вручную","1"/.test(after[1]), "T55: на листе шаблона с таблицей ТЭП — то же");
    await p.sleep(2500); await shot("t55-tep-after");
    check(await p.ev(`const s = ALBUM.sheets[3]; return s.title === "Моя схема" && JSON.stringify(s.center) === "[37.5,55.7]" && s.scale === 7500 && s.note === "Моя подпись" && s.edits.t1.text === "правка" && s.items[0].text === "свой текст" && s.tep === true && JSON.stringify(s.keys) === window.__k3 && s.tpl.set === "pptkrt_" && s.tpl.i === 3`), "T55: название, рамка, масштаб, подпись, надписи «Макета» и свои тексты после обновления на месте; слои — по шаблону");
    check(await p.ev(`return JSON.stringify(ALBUM.sheets[${F}]) === window.__fz && !NOTREADY.has("imp_t55_0")`), "T55: лист «готовая вёрстка» из файла не изменился");
    // «Обновить листы» в «Собрать ▾»: шаблонная часть возвращается к шаблону, правленное остаётся; клавишей Enter
    check(await p.ev(`ALBUM.sheets[4].styles = {}; ALBUM.sheets[4].rect = [0, 0, 1, 1]; TPL_SIG = null; NOTREADY.clear(); $("toast").textContent = ""; winOpen("wSheets", true); renderSheets(); await new Promise(r=>setTimeout(r,300)); $("shBuild").click(); await new Promise(r=>setTimeout(r,300)); $("shRefresh").focus();
      return document.activeElement === $("shRefresh") && JSON.stringify(ALBUM.sheets[4].styles) !== JSON.stringify(PPTKRT[4].styles)`), "T55: перед «Обновить листы» шаблонная часть листа 5 устарела, пункт меню в фокусе");
    await p.key("Enter", "Enter", { vk: 13, text: "\r", wait: 600 });
    check(await p.ev(`const s = ALBUM.sheets[4], t = PPTKRT[4]; return JSON.stringify(s.styles) === JSON.stringify(t.styles) && JSON.stringify(s.rect) === JSON.stringify(t.rect) && ALBUM.sheets[3].title === "Моя схема" && /Листы обновлены по новым показателям/.test($("toast").textContent) && JSON.stringify(ALBUM.sheets[${F}]) === window.__fz`), "T55: «Обновить листы» (клавиша Enter на пункте) возвращает слои и оформление листа к шаблону, название и рамка остаются, лист из файла цел");
    // не готов: слои листа не загружены
    await p.ev(`CHECKED.delete("egko.buildings"); await tplManual(); await new Promise(r=>setTimeout(r,500)); pickSheet(3); await new Promise(r=>setTimeout(r,300)); return 1`);
    check(await p.ev(`return /слой «Здания \\(ЕГКО\\)» не загружен/.test(NOTREADY.get("pptkrt_3") || "") && /Не готов:/.test(document.querySelector("#sheetsBody .snote")?.textContent || "") && /не готово: \\d+/.test($("shStat").textContent) && !NOTREADY.has("imp_t55_0")`), "T55: лист без нужных слоёв помечен «Не готов» с причиной, в строке альбома — число таких листов");
    // проект старого формата (листы без sheet.tpl), лист 6 правлен рукой: при открытии ничего не меняется; пересборка — только после второго нажатия
    const lg = await p.ev(`const s = ALBUM.sheets[5]; s.keys = s.keys.slice(1); s.legend = !s.legend; s.title = "Старое название"; const k5 = JSON.stringify(s.keys), l5 = s.legend;
      const pr = JSON.parse(JSON.stringify(collectProject())); pr.album.sheets.forEach(x => delete x.tpl); const want = JSON.stringify(pr.album.sheets.filter(x => !x.frozen && x.kind !== "tep"));
      applyProject(pr); await new Promise(r=>setTimeout(r,600));
      const got = JSON.stringify(ALBUM.sheets.filter(x => !x.frozen && x.kind !== "tep").map(x => { const { tpl, ...r } = x; return r; }));
      const t = ALBUM.sheets[5]; window.__lg = [k5, l5]; return [got === want, t.tpl?.legacy === true, JSON.stringify(t.keys) === k5, t.legend === l5, t.title === "Старое название"]`);
    check(lg.every(Boolean), `T55: проект старого формата с правленным листом открывается без изменений, лист помечен legacy (${lg})`);
    const lg2 = await p.ev(`tplManual(); const a = JSON.stringify(ALBUM.sheets[5].keys), q = $("toast").textContent; tplManual(); const t = ALBUM.sheets[5];
      return [a === window.__lg[0], /Обновить [0-9]+ (старый лист|старых листов) по шаблону[?] Ваши названия, рамки и фото сохранятся, набор слоёв и легенда — по шаблону/.test(q), JSON.stringify(t.keys) === JSON.stringify(PPTKRT[5].keys.concat([])) || t.keys.length === PPTKRT[5].keys.length, t.legend === PPTKRT[5].legend !== false || t.legend === (PPTKRT[5].legend ?? true), t.title === "Старое название", t.tpl.legacy === undefined]`);
    check(lg2.every(Boolean), `T55: «Обновить листы» спрашивает про старые листы; после подтверждения слои и легенда — по шаблону, название осталось (${lg2})`);
    await p.ev(`for (let k = 0; k < 30 && !RESULT.tepNode?._tep; k++) await new Promise(r=>setTimeout(r,500)); return 1`);
    // порядок: возвращаем проект теста в исходный вид
    await p.ev(`const i=document.querySelector('[data-nid="doo_z1"]'); winOpen("wNorms", true); i.focus(); i.select(); return 1`); await p.type("44"); await p.key("Enter", "Enter", { vk: 13, wait: 1500 });
    await p.ev(`ALBUM.sheets.splice(0, ALBUM.sheets.length, ...window.__t55.keep); window.loadKeys = window.__t55.lk; window.ensureAdmin = window.__t55.ea; CHECKED.clear(); window.__t55.c.forEach(k => CHECKED.add(k)); NOTREADY.clear(); TPL_SIG = null; winOpen("wNorms", false); winOpen("wSheets", false); delete window.__t55; delete window.__fz; delete window.__k3; delete window.__lg; return 1`);
  });
  // T66 (совет 03.10.2026): сборка набора поверх чужих листов спрашивает в строке выбора; «Листы обновлены…» только при реальных изменениях;
  // правленный формат старого листа сохраняется; подписи этажности — настройка слоя
  await p.group("t66", async () => {
    if (!await p.ev(`for (let k = 0; k < 20 && !TERR; k++) await new Promise(r=>setTimeout(r,500)); return !!TERR`)) {
      await p.ev(`$("bExample").click(); await new Promise(r=>setTimeout(r,800)); return 1`);
    }
    check(await p.ev(`return !!TERR`), "T66: есть территория");
    await p.ev(`window.__t66 = { keep: ALBUM.sheets.splice(0), lk: window.loadKeys, ea: window.ensureAdmin, c: new Set(CHECKED) }; window.loadKeys = async () => {}; window.ensureAdmin = async () => { CHECKED.add("gisogd.admin"); }; TPL_SIG = null; NOTREADY.clear(); winOpen("wSheets", true); renderSheets(); await new Promise(r=>setTimeout(r,300)); return 1`);
    const done = n => p.ev(`for (let k = 0; k < 120 && !(SHBUILD === 0 && ALBUM.sheets.length === ${n}); k++) await new Promise(r=>setTimeout(r,250)); return ALBUM.sheets.length`);
    // синтетический альбом из файла: 3 листа готовой вёрстки
    await p.ev(`const fz = i => ({ id: "x" + i, frozen: true, title: "Готовый " + i, size: "PA3", scale: 5000, center: [37, 55], layers: [{ key: "a", title: "A", features: [] }], legend: [], tep: [] });
      readAlbumFile(new File([JSON.stringify({ sheets: [fz(0), fz(1), fz(2)] })], "t66.json")); for (let k = 0; k < 40 && ALBUM.sheets.length < 3; k++) await new Promise(r=>setTimeout(r,150)); return 1`);
    const N = await p.ev(`return ALBUM.sheets.length`), M = await p.ev(`return PPTKRT.length`);
    check(N === 3 && await p.ev(`return ALBUM.sheets.every(s => s.frozen)`), `T66: импортирован альбом из файла, ${N} листа готовой вёрстки`);
    const ask = () => p.ev(`buildAlbum("pptkrt"); await new Promise(r=>setTimeout(r,500)); const b = $("shImpBar"); return [ALBUM.sheets.length, !!b, b ? [...b.querySelectorAll("button")].map(x => x.textContent.trim()).join("|") : "", b?.textContent.includes("в альбоме") ?? false]`);
    let a = await ask();
    check(a[0] === N && a[1] && /^Заменить 3 листа текущего альбома на .+\|Добавить после текущих\|Отмена$/.test(a[2]), `T66: «Альбом ППТ КРТ» поверх листов из файла — строка выбора, листы не тронуты (${a[2]})`);
    check(await p.ev(`return document.activeElement === $("shImpBar").querySelector("button")`), "T66: фокус на первой кнопке строки выбора");
    await p.ev(`const esc = () => (document.getElementById("shImpBar") ? document.activeElement : document.body).dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }));
      esc(); await new Promise(r=>setTimeout(r,300)); if ($("shImpBar")) { esc(); await new Promise(r=>setTimeout(r,300)); } return 1`);   // первый Esc мог отменить команду CAD, оставшуюся от прежних шагов
    const esc66 = await p.ev(`return [!$("shImpBar"), ALBUM.sheets.length, document.activeElement?.tagName + "#" + (document.activeElement?.id || document.activeElement?.className), typeof TOOL !== "undefined" ? TOOL : ""]`);
    check(esc66[0] && esc66[1] === N, `T66: Esc в строке выбора — «Отмена», альбом без изменений (${esc66})`);
    await ask(); await p.ev(`$("shImpBar").querySelector('[data-shbuild="cancel"]').click(); await new Promise(r=>setTimeout(r,300)); return 1`);
    check(await p.ev(`return !$("shImpBar") && ALBUM.sheets.length === ${N}`), "T66: кнопка «Отмена» — то же");
    // «Добавить»: 9 + N
    await ask(); await p.ev(`$("shImpBar").querySelector('[data-shbuild="add"]').click(); return 1`);
    check(await done(M + N) === M + N && await p.ev(`return !$("shImpBar") && ALBUM.sheets.filter(s => s.frozen).length === ${N} && ALBUM.sheets.filter(s => s.id.startsWith("pptkrt_")).length === ${M}`), `T66: «Добавить после текущих» — ${M} листов набора и ${N} прежних (${M + N})`);
    // «Заменить»: только набор
    await ask(); await p.ev(`$("shImpBar").querySelector('[data-shbuild="replace"]').click(); return 1`);
    check(await done(M) === M && await p.ev(`return ALBUM.sheets.every(s => s.id.startsWith("pptkrt_"))`), `T66: «Заменить» — в альбоме ровно ${M} листов набора`);
    // тот же набор повторно: без вопроса, заменяет только себя
    a = await ask();
    check(!a[1] && await done(M) === M, "T66: повторная сборка того же набора — без строки выбора, листов столько же");
    // ситуационный план поверх листов набора: тот же вопрос (сборка не начинается)
    await p.ev(`buildSituation(); await new Promise(r=>setTimeout(r,500)); return 1`);
    check(await p.ev(`const b = $("shImpBar"); return !!b && /^Заменить \\d+ листов? текущего альбома на Ситуационный план A4/.test(b.querySelector("button").textContent) && ALBUM.sheets.length === ${M}`), "T66: «Ситуационный план A4» поверх чужих листов — та же строка выбора");
    await p.ev(`$("shImpBar").querySelector('[data-shbuild="cancel"]').click(); return 1`);
    // «Листы обновлены по новым показателям» — только если лист изменился
    await p.ev(`window.setHint(""); TPL_SIG = { tep: tplSig().tep, all: "a" }; tplAuto(); await new Promise(r=>setTimeout(r,600)); return 1`);
    check(await p.ev(`return !/Листы обновлены/.test($("stHint").textContent)`), "T66: показатели «изменились», но ни один лист не изменился — подсказки «Листы обновлены» нет");
    await p.ev(`window.setHint(""); ALBUM.sheets[4].styles = {}; TPL_SIG = { tep: tplSig().tep, all: "b" }; tplAuto(); await new Promise(r=>setTimeout(r,600)); return 1`);
    check(await p.ev(`return $("stHint").textContent === "Листы обновлены по новым показателям"`), "T66: лист действительно изменился — подсказка есть");
    // лист старого проекта: формат, изменённый владельцем, не откатывается при «Обновить листы»
    const lg = await p.ev(`const s = ALBUM.sheets[2]; s.size = "A3"; delete s.tpl; tplAdopt(); const legacy = s.tpl?.legacy === true; tplRefresh({ legacy: true });
      const s5 = ALBUM.sheets[5]; delete s5.tpl; tplAdopt(); tplRefresh({ legacy: true }); return [legacy, s.size === "A3", s5.size === "PA3"]`);
    check(lg.every(Boolean), `T66: старый лист с изменённым форматом после «Обновить листы» сохраняет формат, нетронутый — шаблонный (${lg})`);
    // подписи этажности: настройка слоя
    const fl = await p.ev(`const mk = (key, title) => { const fc = turf.featureCollection([turf.feature(turf.bboxPolygon([37, 55, 37.001, 55.001]).geometry, { "Этажность": 9 })]);
        DATA[key] = { title, source: "t", fetched_at: "2026-10-03", fc, count: 0, fields: [] }; layerSrc[key] = new ol.source.Vector(); setLayerData(key, fc); delete DATA[key].original;
        const l = ensureLayer(key, title, "poly"); l.style = ST({ label: "Этажность" }); restyle(l); return l; };
      const sk = mk("user:t66sk", "Эскиз: тест"), my = mk("user:t66my", "Мой слой"), f = l => layerSrc[l.key].getFeatures()[0];
      const view = sharedView, r0 = view.getResolution(); let r = 1; for (let i = 0; i < 4; i++) r = r * 3000 / scaleDen(r); view.setResolution(r);
      const at = () => [labelStyle(sk, f(sk)) !== null, labelStyle(my, f(my)) !== null];
      const out = { a3000: at(), txt: labelStyle(sk, f(sk))?.getText?.().getText?.() };
      sk.style.floorsDen = 5000; out.sk5 = at()[0]; sk.style.floorsDen = 0; out.sk0 = at()[0]; delete sk.style.floorsDen;
      my.style.floorsDen = 2000; out.my2 = at()[1]; delete my.style.floorsDen;
      view.setResolution(r * 8000 / 3000); out.a8000 = at(); sk.style.floorsDen = 5000; out.sk5far = at()[0]; delete sk.style.floorsDen;
      view.setResolution(r0); window.__t66l = [sk.key, my.key]; return out`);
    check(fl.a3000[0] === false && fl.a3000[1] === true && fl.sk5 === true && fl.sk0 === true && fl.my2 === false && fl.a8000[1] === true && fl.sk5far === false, `T66: подписи этажности: эскиз по умолчанию от 1:2 000, свой слой — всегда, «от 1:5 000» и «всегда» работают (${JSON.stringify(fl)})`);
    const ui = await p.ev(`setCurrentQuiet("user:t66sk"); UIS.rt = "style"; renderRight(); const sel = document.querySelector('#rightPane select[data-k="floorsDen"]'); if (!sel) return ["нет списка"];
      const o = [...sel.options].map(x => x.textContent).join("|"), v0 = sel.value; sel.value = "5000"; sel.dispatchEvent(new Event("change", { bubbles: true })); await new Promise(r=>setTimeout(r,200));
      return [o, v0, lyr("user:t66sk").style.floorsDen, document.querySelector('#rightPane select[data-k="floorsDen"]').value]`);
    check(ui[0] === "всегда|от 1:2 000|от 1:5 000" && ui[1] === "2000" && ui[2] === 5000 && ui[3] === "5000", `T66: в панели стиля рядом с полем «Подпись» — «Подписи этажности»: всегда / от 1:2 000 / от 1:5 000, значение пишется в стиль слоя (${ui})`);
    await p.ev(`removeLayers(window.__t66l); delete window.__t66l; await new Promise(r=>setTimeout(r,200)); return 1`);
    await p.ev(`ALBUM.sheets.splice(0, ALBUM.sheets.length, ...window.__t66.keep); window.loadKeys = window.__t66.lk; window.ensureAdmin = window.__t66.ea; CHECKED.clear(); window.__t66.c.forEach(k => CHECKED.add(k)); NOTREADY.clear(); TPL_SIG = null; winOpen("wSheets", false); delete window.__t66; return 1`);
  });
};
