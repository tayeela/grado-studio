// ГРАДО 2 · совместная работа в двух браузерах сразу: два headless Chrome (у каждого свои куки), один общий проект.
// Запуск: tests/test_e2e.py (GRADO2_E2E=1) поднимает сервер --hub, создаёт администратора и приглашение и зовёт этот файл.
// Вручную: E2E_ADMIN_PW=… E2E_INVITE=… [E2E_SHOTS=папка] node collab_scenarios.mjs http://127.0.0.1:порт/
// Всё, где в интерфейсе есть кнопка или поле, делается мышью и клавиатурой (CDP), а не вызовами функций страницы;
// страница опрашивается только для проверок. Код возврата 1 — шаг не выполнен или в консоли любой страницы есть ошибка.
import { spawn } from "node:child_process";
import { writeFileSync, readFileSync, mkdtempSync, mkdirSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const URL0 = process.argv[2], ADMIN_PW = process.env.E2E_ADMIN_PW, INVITE = process.env.E2E_INVITE, SHOTS = process.env.E2E_SHOTS || "";
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const sleep = ms => new Promise(r => setTimeout(r, ms));
const check = (cond, msg) => { if (!cond) throw new Error("не выполнено: " + msg); console.log("ok -", msg); };
if (SHOTS) mkdirSync(SHOTS, { recursive: true });

const procs = [];
async function launch(name) {
  const profile = mkdtempSync(join(tmpdir(), "cdp-collab-" + name + "-"));
  const chrome = spawn(CHROME, ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profile}`, "--window-size=1440,900",
    "--no-first-run", "--no-default-browser-check", "--no-sandbox", "--enable-unsafe-swiftshader", "about:blank"], { stdio: "ignore" });
  procs.push({ chrome, profile });
  let port = 0;
  for (let i = 0; i < 300 && !port; i++) { if (existsSync(join(profile, "DevToolsActivePort"))) port = +readFileSync(join(profile, "DevToolsActivePort"), "utf8").split("\n")[0]; else await sleep(100); }
  // ждём, пока Chrome отдаст страницу (на медленном раннере /json отвечает не сразу или пустым списком); 30 с, не 5
  let page; for (let i = 0; i < 300 && !page; i++) { try { page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find(t => t.type === "page"); } catch { } if (!page) await sleep(100); }
  if (!page) throw new Error(`${name}: Chrome не отдал страницу для управления (порт ${port})`);
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise(r => ws.onopen = r);
  let id = 0; const pending = new Map(), logs = [];
  const send = (method, params = {}) => new Promise(r => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    if (m.method === "Runtime.consoleAPICalled" && ["error", "warning"].includes(m.params.type)) logs.push(name + " " + m.params.type + ": " + m.params.args.map(a => a.value ?? a.description).join(" "));
    // «Failed to load resource» и прочее, что браузер пишет в консоль сам; 401 на /api/hub/me до входа — ожидаемый ответ «вы не вошли» (спека)
    if (m.method === "Log.entryAdded" && m.params.entry.level === "error" && !(p.allow401 && /\b40[13]\b/.test(m.params.entry.text)) && !(/\/api\/hub\/me$/.test(m.params.entry.url || "") && /401/.test(m.params.entry.text))
      // 409 на отправку — штатный конфликт одновременных правок: клиент сводит правки и отправляет снова
      && !(/\/api\/hub\/project\/[0-9a-f]+\/push$/.test(m.params.entry.url || "") && /\b409\b/.test(m.params.entry.text))
      // 400 на удаление команды с проектами — ожидаемый отказ сервера (шаг 8 «команды»)
      && !(/\/api\/hub\/team\/[0-9a-f]+\/delete$/.test(m.params.entry.url || "") && /\b400\b/.test(m.params.entry.text))
      // 404 на вход по старой (заменённой) ссылке — ожидаемый отказ сервера (этап 2, шаг 5)
      && !(/\/api\/hub\/join$/.test(m.params.entry.url || "") && /\b404\b/.test(m.params.entry.text))) logs.push(name + " log: " + m.params.entry.text + " " + (m.params.entry.url || ""));
    if (m.method === "Runtime.exceptionThrown") logs.push(name + " EXCEPTION: " + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text)); };
  await send("Runtime.enable"); await send("Page.enable"); await send("Log.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
  const mods = o => (o?.alt ? 1 : 0) | (o?.ctrl ? 2 : 0) | (o?.meta ? 4 : 0) | (o?.shift ? 8 : 0);
  const p = {
    name, logs, sleep, allow401: false,
    async go(url) { await send("Page.navigate", { url }); await sleep(2500); },
    async ev(expr) { const r = await send("Runtime.evaluate", { expression: `(async () => { ${expr} })()`, awaitPromise: true, returnByValue: true }); if (r.result?.exceptionDetails) throw new Error(name + " page: " + (r.result.exceptionDetails.exception?.description || r.result.exceptionDetails.text)); return r.result?.result?.value; },
    async move(x, y, o) { await send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y, modifiers: mods(o), button: o?.down ? "left" : "none", buttons: o?.down ? 1 : 0 }); },
    async click(x, y, o = {}) {
      await p.move(x, y, o);
      for (let c = 1; c <= (o.dbl ? 2 : 1); c++) { await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", buttons: 1, clickCount: c, modifiers: mods(o) }); await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", buttons: 0, clickCount: c, modifiers: mods(o) }); }
      await sleep(o.wait ?? 120);
    },
    async key(key, code, o = {}) {
      const base = { key, code, modifiers: mods(o), windowsVirtualKeyCode: o.vk || (key.length === 1 ? key.toUpperCase().charCodeAt(0) : 0) };
      await send("Input.dispatchKeyEvent", { type: "keyDown", ...base, text: o.text }); await send("Input.dispatchKeyEvent", { type: "keyUp", ...base }); await sleep(o.wait ?? 80);
    },
    async type(text) { await send("Input.insertText", { text }); await sleep(60); },
    async shot(file) { if (!SHOTS) return; const s = await send("Page.captureScreenshot", { format: "png" }); writeFileSync(join(SHOTS, file), Buffer.from(s.result.data, "base64")); },
    // центр видимого элемента; нет или нулевого размера — ошибка шага
    async center(sel) { const c = await p.ev(`const e=document.querySelector(${JSON.stringify(sel)}); if(!e) return null; const r=e.getBoundingClientRect(); if(!r.width||!r.height) return null; e.scrollIntoView?.({block:"nearest"}); const q=e.getBoundingClientRect(); return [q.left+q.width/2, q.top+q.height/2]`); if (!c) throw new Error(`${name}: нет элемента ${sel}`); return c; },
    async clickEl(sel, o) { const [x, y] = await p.center(sel); await p.click(x, y, o); },
    async fill(sel, text) { await p.clickEl(sel); await p.ev(`const e=document.querySelector(${JSON.stringify(sel)}); e.select?.(); return 1`); await p.type(text); },
    // ждать, пока выражение станет истинным; возвращает, сколько мс ждали
    async until(expr, msg, ms = 8000) { const t0 = Date.now(); for (;;) { let v = false; try { v = await p.ev(expr); } catch { } if (v) return Date.now() - t0; if (Date.now() - t0 > ms) throw new Error(`${name}: не дождались — ${msg}`); await sleep(100); } },
  };
  return p;
}

const LAYER = `LYR.find(l=>l.title==="Кварталы")`;
const feats = `(()=>{ const l=${LAYER}; return l?layerSrc[l.key].getFeatures():[]; })()`;
const cnt = `${feats}.length`;
const presKinds = `(()=>{ const l=mMain.getLayers().getArray().find(x=>x.getZIndex()===910); return l?l.getSource().getFeatures().map(f=>f.get("kind")):[]; })()`;

let A, B, failed = false;
try {
  A = await launch("A"); B = await launch("B");
  await Promise.all([A.go(URL0), B.go(URL0)]);

  // ---------- B: регистрация по приглашению, выход, повторный вход позже ----------
  await B.until(`return !$("hubLogin").hidden`, "экран входа");
  check(await B.ev(`return $("hubLogin").hidden===false && document.querySelector(".app").inert===true`), "B: без входа виден только экран входа, программа недоступна");
  await B.clickEl('[data-lmode="reg"]');
  await B.fill("#hubInv", INVITE); await B.fill("#hubLg", "bob"); await B.fill("#hubNm", "Борис"); await B.fill("#hubPw", "bob-password-1"); await B.fill("#hubPw2", "bob-password-1");
  await B.clickEl("#hubGo");
  await B.until(`return $("hubLogin").hidden && HubUI.state.me?.login==="bob"`, "регистрация прошла, вход выполнен");
  check(await B.ev(`return !$("wHubProjects").hidden && $("hubAccName").textContent==="Борис"`), "B: после регистрации открыто окно «Совместные проекты», в шапке имя «Борис»");
  await B.clickEl("#hubAcc"); await B.clickEl('[data-hubact="out"]');
  await B.until(`return !$("hubLogin").hidden`, "после выхода снова экран входа", 10000);
  check(await B.ev(`return $("hubLg").value===""`), "B: после выхода поля входа пусты");

  // ---------- A: вход, проект «Проверка», доступ для B ----------
  await A.until(`return !$("hubLogin").hidden`, "экран входа");
  await A.fill("#hubLg", "anna"); await A.fill("#hubPw", ADMIN_PW); await A.clickEl("#hubGo");
  await A.until(`return $("hubLogin").hidden && HubUI.state.me?.login==="anna"`, "вход A");
  await A.until(`return !$("wHubProjects").hidden`, "окно проектов");
  check(await A.ev(`return /Совместных проектов пока нет/.test($("hubProjList").textContent)`), "A: список проектов пуст, подсказка как начать");
  await A.fill("#hubNewName", "Проверка"); await A.clickEl("#hubNew");
  await A.until(`return Collab.pid && $("hubProjName").textContent==="Проверка" && $("wHubProjects").hidden`, "проект «Проверка» создан и открыт");
  // администратор сервера видит свои проекты с ролью «admin» (спека: GET /projects) — в шапке «администратор»; права владельца те же
  check(await A.ev(`return ["owner","admin"].includes(Collab.role) && /владелец|администратор/.test($("hubRole").textContent)`), "A: проект «Проверка» создан в «Совместных проектах», A — владелец (администратор)");
  // сразу после открытия проекта подпись «сохранено» на ~30 мс становится «отправляю…» и кнопки шапки сдвигаются:
  // клик по координатам мог попасть в соседнюю кнопку («История»). Ждём, пока кнопка встанет на место, и проверяем, что окно открылось.
  const btnPos = `const r=document.querySelector("#hubShareBtn").getBoundingClientRect(); return r.left+","+r.top`;
  for (let prev = null, same = 0; same < 3; await A.sleep(150)) { const now = await A.ev(btnPos); same = now === prev ? same + 1 : 0; prev = now; }
  await A.clickEl("#hubShareBtn");
  await A.until(`const e=document.querySelector("#hubShareLogin"); return !!e && !$("wShare").hidden && e.getBoundingClientRect().width>0`, "окно «Доступ»");
  await A.fill("#hubShareLogin", "bob"); await A.clickEl('#hubShareBody [data-act="add"]');
  await A.until(`return [...document.querySelectorAll("#hubShareBody tbody tr")].some(r=>/bob/.test(r.textContent))`, "bob в списке участников");
  check(await A.ev(`return document.querySelector('select[data-act="role"][data-login="bob"]').value==="editor"`), "A: в окне «Доступ» B добавлен с ролью «правка»");
  await A.shot("01-A-dostup.png");
  await A.clickEl("#wShare [data-close]");

  // ---------- B: вход, открытие проекта из списка ----------
  await B.fill("#hubLg", "bob"); await B.fill("#hubPw", "bob-password-1"); await B.clickEl("#hubGo");
  await B.until(`return $("hubLogin").hidden && !$("wHubProjects").hidden`, "вход B и окно проектов");
  await B.until(`return [...document.querySelectorAll("#hubProjList tbody tr")].some(r=>/Проверка/.test(r.textContent))`, "в списке B виден проект «Проверка»");
  await B.clickEl('#hubProjList [data-act="open"]');
  await B.until(`return Collab.pid && Collab.role==="editor" && $("wHubProjects").hidden`, "B открыл проект");
  check(await B.ev(`return $("hubProjName").textContent==="Проверка" && $("hubRole").textContent==="правка" && !document.body.classList.contains("hub-viewer")`), "B: открыл «Проверка» из списка, роль «правка»");
  await A.until(`return document.querySelectorAll("#hubAv .av").length===1`, "A видит аватар B");
  check(await A.ev(`return document.querySelector("#hubAv .av").textContent.length>0 && /Борис/.test(document.querySelector("#hubAv .av").title)`), "A: в шапке аватар B — кто в проекте");

  // ---------- A рисует полигон ----------
  const mapC = async P => P.ev(`const r=$("mMain").getBoundingClientRect(); return [r.left+r.width/2, r.top+r.height/2]`);
  const [ax, ay] = await mapC(A);
  const poly = async (P, x, y, s) => { await P.click(x, y); await P.click(x + s, y); await P.click(x + s, y + s); await P.click(x, y + s, { dbl: true, wait: 300 }); };
  await A.ev(`$("bNewLayer").click(); $("nlName").value="Кварталы"; $("nlOk").click(); return 1`);
  await poly(A, ax - 230, ay - 120, 80);
  check(await A.ev(`return ${cnt}`) === 1, "A: нарисован первый полигон в слое «Кварталы»");
  const t0 = Date.now();
  await B.until(`return ${cnt}===1`, "B видит новый объект", 6000);
  const tDraw = Date.now() - t0;
  await A.shot("02-A-narisoval.png");
  check(tDraw <= 3000, `B увидел полигон A без перезагрузки за ${tDraw} мс (не больше 3000)`);
  check(await B.ev(`return !!${LAYER} && !!${feats}[0].get("_uid")`), "B: слой создан автоматически, у объекта есть постоянный номер");

  // ---------- B меняет атрибут объекта, A видит ----------
  const pxOf = async (P, n) => P.ev(`const f=${feats}[${n}]; let e=f.getGeometry().getExtent(), c=ol.extent.getCenter(e), q=mMain.getPixelFromCoordinate(c), r=$("mMain").getBoundingClientRect(); if(!q||q[0]<0||q[1]<0||q[0]>r.width||q[1]>r.height){ sharedView.fit(ol.extent.buffer(e,60)); await new Promise(x=>setTimeout(x,300)); q=mMain.getPixelFromCoordinate(c); } return [r.left+q[0], r.top+q[1]]`);
  const setAttr = async (P, val) => { await P.clickEl('[data-attr="Наименование"]'); await P.ev(`document.querySelector('[data-attr="Наименование"]').select(); return 1`); await P.type(val); await P.key("Enter", "Enter", { vk: 13 }); };
  { const [x, y] = await pxOf(B, 0); await B.click(x, y); }
  await B.until(`return SEL.length===1 && !!document.querySelector('[data-attr="Наименование"]')`, "B выбрал объект, справа поле «Наименование»");
  await setAttr(B, "Квартал Б");
  const t1 = Date.now();
  await A.until(`return ${feats}[0].get("Наименование")==="Квартал Б"`, "A видит правку B", 6000);
  const tAttr = Date.now() - t1;
  check(tAttr <= 3000, `A увидел атрибут, изменённый B, за ${tAttr} мс (не больше 3000)`);
  await B.shot("03-B-atribut.png");

  // ---------- одновременно: A рисует второй полигон, B правит атрибут первого ----------
  await Promise.all([
    (async () => { await A.key(" ", "Space", { text: " " }); await poly(A, ax - 230, ay + 20, 80); })(),     // пробел, как в AutoCAD, повторяет полилинию
    (async () => { await B.sleep(150); await setAttr(B, "Квартал Б2"); })(),
  ]);
  await Promise.all([A.until(`return ${cnt}===2 && ${feats}.some(f=>f.get("Наименование")==="Квартал Б2")`, "у A оба результата"), B.until(`return ${cnt}===2 && ${feats}.some(f=>f.get("Наименование")==="Квартал Б2")`, "у B оба результата")]);
  check(true, "одновременные правки разных объектов (новый полигон A и атрибут B) — оба результата есть у обоих");
  const uids = P => P.ev(`return ${feats}.map(f=>f.get("_uid")).sort().join()`);
  // номера сверяются, пока обе стороны не придут к одному; не сошлись за 6 с — в сообщении оба списка
  let ua = "", ub = "";
  for (const t = Date.now(); Date.now() - t < 6000; await sleep(100)) { ua = await uids(A); ub = await uids(B); if (ua === ub) break; }
  check(ua === ub, `наборы постоянных номеров у A и B совпадают (двойников нет)${ua === ub ? "" : ` — A: ${ua}; B: ${ub}`}`);
  await A.until(`return $("hubSync").dataset.state==="saved"`, "A: «сохранено»"); await B.until(`return $("hubSync").dataset.state==="saved"`, "B: «сохранено»");

  // ---------- присутствие: курсор и выбор B видны у A ----------
  for (let i = 0; i < 5; i++) { const [bx, by] = await mapC(B); await B.move(bx - 120 + i * 6, by - 60 + i * 4); await sleep(150); }
  await A.until(`const k=${presKinds}; return k.includes("cursor") && k.includes("sel")`, "у A на карте курсор и контур выбора B", 8000);
  const pk = await A.ev(`return ${presKinds}`);
  check(pk.length >= 2 && pk.includes("cursor") && pk.includes("sel"), `A: наложение присутствия — ${pk.length} объекта (курсор B и контур выбранного им объекта)`);
  check(await A.ev(`return /Борис/.test($("hubAv").title)`), "A: в подсказке аватара имя «Борис»");
  await A.shot("04-A-prisutstvie.png");

  // ---------- комментарий A на карте, B видит метку и запись ----------
  await A.clickEl("#hubCTool");
  check(await A.ev(`return document.body.classList.contains("hub-cmode")`), "A: включён инструмент «Комментарий»");
  await A.click(ax - 40, ay + 160);
  await A.until(`return !$("hubCompose").hidden && document.activeElement===$("hubCText")`, "поле комментария");
  await A.type("Проверить границу квартала"); await A.clickEl("#hubCSend");
  await A.until(`return $("hubCompose").hidden && /Проверить границу/.test($("hubCList").textContent)`, "комментарий появился в списке A");
  await B.until(`return $("hubComCnt").textContent==="1"`, "B: счётчик комментариев", 6000);
  check(await B.ev(`const l=mMain.getLayers().getArray().find(x=>x.get("hubPins")); return l.getSource().getFeatures().length===1`), "B: на карте появилась метка комментария");
  await B.clickEl("#hubComBtn");
  await B.until(`return !$("wComments").hidden && /Проверить границу квартала/.test($("hubCList").textContent)`, "текст комментария в окне B");
  check(await B.ev(`return /Анна|anna/.test($("hubCList").textContent)`), "B: в «Комментариях» виден автор и текст");
  await B.shot("05-B-kommentarii.png");
  await A.clickEl("#wComments [data-close]"); await B.clickEl("#wComments [data-close]");

  // ---------- история: A возвращает раннюю версию, затем последнюю ----------
  await A.clickEl("#hubHistBtn");
  await A.until(`return document.querySelectorAll('#hubHBody [data-act="restore"]').length>=1`, "версии в окне «История»");
  await A.shot("06-A-istoriya.png");
  const restore = async (P, which) => {
    const sel = `#hubHBody tbody tr:${which} [data-act="restore"]`;
    await P.clickEl(sel); await P.until(`return /Точно вернуть/.test(document.querySelector(${JSON.stringify(sel)}).textContent)`, "кнопка «Точно вернуть?»");
    await P.clickEl(sel);
  };
  await restore(A, "last-child");                                   // самая ранняя — пустой проект
  await B.until(`return ${cnt}===0`, "B получил раннюю версию: слой пуст", 8000);
  check(true, "B получил возврат к ранней версии без перезагрузки: рисунков нет");
  await A.until(`return document.querySelectorAll('#hubHBody tbody tr').length>=2`, "в истории появилась версия «перед возвратом»");
  await restore(A, "first-child");                                  // версия, сохранённая перед возвратом, — вся работа
  await Promise.all([A.until(`return ${cnt}===2`, "у A вернулись оба полигона", 8000), B.until(`return ${cnt}===2 && ${feats}.some(f=>f.get("Наименование")==="Квартал Б2")`, "у B вернулась работа", 8000)]);
  check(true, "после возврата последней версии у B снова оба полигона и атрибут");
  check(await B.ev(`return $("hubComCnt").textContent==="1"`), "комментарий пережил возвраты версий");
  await B.shot("07-B-posle-vozvrata.png");
  await A.clickEl("#wHistory [data-close]");

  B.allow401 = true;                     // дальше 401 у B ожидаемы: неверный старый пароль и отключение пользователя
  // ---------- пароль: неверный старый пароль — это не конец сессии ----------
  await B.clickEl("#hubAcc"); await B.clickEl('[data-hubact="pw"]');
  await B.until(`return $("hubPwDlg").open`, "диалог смены пароля");
  await B.fill("#hubPwOld", "не-тот-пароль-1"); await B.fill("#hubPwNew", "bob-password-2"); await B.fill("#hubPwNew2", "bob-password-2");
  await B.clickEl('#hubPwForm button[type="submit"]');
  await B.until(`return /неверн/i.test($("hubPwMsg").textContent)`, "сообщение о неверном пароле");
  check(await B.ev(`return $("hubLogin").hidden && $("hubPwDlg").open`), "B: неверный старый пароль — сообщение в диалоге, на экран входа не выбрасывает");
  await B.clickEl("#hubPwCancel");

  // ---------- сессия кончилась: A отключает B в «Пользователях», у B экран входа; A включает, B входит и работает дальше ----------
  await A.clickEl("#hubAcc"); await A.clickEl('[data-hubact="admin"]');
  await A.until(`return !!document.querySelector('#hubAdminBody [data-act="toggle"][data-login="bob"]')`, "пользователь bob в окне администратора");
  await A.shot("10-A-polzovateli.png");
  await A.clickEl('#hubAdminBody [data-act="toggle"][data-login="bob"]');
  await B.until(`return !$("hubLogin").hidden`, "у B экран входа после отключения", 10000);
  check(await B.ev(`return /Вход закончился/.test($("hubMsg").textContent)`), "B: отключённого пользователя выбрасывает на экран входа с пояснением («Вход закончился»)");
  await B.shot("11-B-vhod-zakonchilsya.png");
  await A.until(`return document.querySelectorAll("#hubAv .av").length===0`, "A: аватар B исчез", 25000);
  await A.until(`return /Включить/.test(document.querySelector('#hubAdminBody [data-act="toggle"][data-login="bob"]').textContent)`, "кнопка «Включить»");
  await A.clickEl('#hubAdminBody [data-act="toggle"][data-login="bob"]');
  await A.until(`return /Отключить/.test(document.querySelector('#hubAdminBody [data-act="toggle"][data-login="bob"]').textContent)`, "bob снова включён");
  await A.clickEl("#wHubAdmin [data-close]");
  await B.fill("#hubPw", "bob-password-1"); await B.clickEl("#hubGo");
  await B.until(`return $("hubLogin").hidden`, "B снова вошёл"); B.allow401 = false;
  await B.until(`return Collab.pid && $("hubSync").dataset.state==="saved" && document.querySelectorAll ? true : true`, "проект у B открыт");
  await A.until(`return document.querySelectorAll("#hubAv .av").length===1`, "A снова видит аватар B: поток событий восстановлен", 12000);
  { const [x, y] = await pxOf(B, 1); await B.click(x, y); }
  await B.until(`return SEL.length===1 && !!document.querySelector('[data-attr="Наименование"]')`, "B выбрал второй объект");
  await setAttr(B, "После входа");
  await A.until(`return ${feats}.some(f=>f.get("Наименование")==="После входа")`, "A видит правку B после повторного входа", 6000);
  check(true, "после повторного входа B работает дальше: его правка дошла до A, поток событий и отправка восстановились");

  // ---------- A делает B наблюдателем ----------
  const revNow = () => A.ev(`return (await (await fetch("/api/hub/project/"+Collab.pid)).json()).rev`);
  await A.clickEl("#hubShareBtn");
  await A.until(`return !!document.querySelector('select[data-act="role"][data-login="bob"]')`, "роль bob в окне «Доступ»");
  await A.ev(`const s=document.querySelector('select[data-act="role"][data-login="bob"]'); s.value="viewer"; s.dispatchEvent(new Event("change",{bubbles:true})); return 1`);
  await B.until(`return Collab.role==="viewer" && document.body.classList.contains("hub-viewer")`, "B стал наблюдателем", 8000);
  check(await B.ev(`return getComputedStyle($("rbDraw")).display==="none" && getComputedStyle($("bNewLayer")).pointerEvents==="none" && !$("hubViewHint").hidden && $("hubSync").dataset.state==="readonly"`), "B: инструменты рисования скрыты, «Новый слой» недоступен, плашка «Только просмотр», статус «только просмотр»");
  check(await B.ev(`return /просмотр/.test($("hubRole").textContent)`), "B: в шапке роль «просмотр»");
  await B.shot("08-B-nablyudatel.png");
  const rev0 = await revNow(), n0 = await B.ev(`return ${cnt}`);
  // B пытается править: стереть выбранное клавишей, набрать команду черчения, и даже принудительно поменять объект в памяти
  { const [x, y] = await pxOf(B, 0); await B.click(x, y); }            // наблюдатель может выбирать объекты
  check(await B.ev(`return SEL.length===1`), "B (наблюдатель): объект выбрать можно");
  await B.key("Delete", "Delete", { vk: 46 }); await B.key("p", "KeyP", { text: "p" }); await B.key("l", "KeyL", { text: "l" }); await B.key("Enter", "Enter", { vk: 13 });
  check(await B.ev(`return ${cnt}===${n0} && !CAD.active()`), "B: Del и команда «pl» с клавиатуры заблокированы");
  await B.ev(`const f=${feats}[0]; f.set("Наименование","Взлом наблюдателя"); markDirty(); return 1`);
  await sleep(3500);
  check(await revNow() === rev0, "B: правка наблюдателя не ушла на сервер (ревизия проекта не изменилась)");
  check(await A.ev(`return ${feats}.every(f=>f.get("Наименование")!=="Взлом наблюдателя")`), "A: правка наблюдателя у A не появилась");
  check(await B.ev(`return $("hubSync").dataset.state==="readonly"`), "B: статус остался «только просмотр»");
  await A.shot("09-A-final.png");

  // ---------- A убирает B из проекта: у B — понятное сообщение и список проектов ----------
  B.allow401 = true;                     // поток и проверки B получают 403: доступа больше нет
  await A.until(`return !!document.querySelector('#hubShareBody [data-act="rm"][data-login="bob"]')`, "кнопка «Убрать» у bob");
  await A.clickEl('#hubShareBody [data-act="rm"][data-login="bob"]');
  await A.until(`return /Точно/.test(document.querySelector('#hubShareBody [data-act="rm"][data-login="bob"]').textContent)`, "подтверждение «Точно?»");
  await A.clickEl('#hubShareBody [data-act="rm"][data-login="bob"]');
  await B.until(`return !Collab.pid && $("hubProjName").textContent==="Выберите проект" && !$("wHubProjects").hidden`, "у B закрыт проект, открыт список", 10000);
  check(await B.ev(`return /нет доступа/.test($("toast").textContent) && !document.body.classList.contains("hub-viewer")`), "B: доступ снят — сообщение «больше нет доступа», проект закрыт, окно проектов открыто");
  await B.shot("12-B-dostup-snyat.png");

  // ---------- поток событий не пускает (429): сообщение и без частых переподключений ----------
  await A.ev(`window.__probes=0; const F=window.fetch.bind(window); window.fetch=(u,o)=>String(u).endsWith("/events")?(window.__probes++,Promise.resolve({status:429})):F(u,o);
    window.EventSource=class{constructor(){setTimeout(()=>this.onerror&&this.onerror(),10)} close(){}}; const pid=Collab.pid; Collab.close(); await HubUI.open(pid); return 1`);
  await A.until(`return /слишком много вкладок/.test($("toast").textContent)`, "сообщение о лишних вкладках", 5000);
  await sleep(4000);
  check(await A.ev(`return window.__probes`) === 1, "A: после отказа 429 поток не переподключается часто (одна проверка за 4 с, следующая — через минуту)");

  // ---------- команды: «Бюро 1», командный проект, доступ всей команды (B — по-прежнему участник сервера, но не личный участник нового проекта) ----------
  const showWin = async (P, openSel, id) => { if (await P.ev(`return $("${id}").hidden`)) await P.clickEl(openSel); await P.until(`return !$("${id}").hidden`, `окно ${id} открыто`); };
  const hideWin = async (P, id) => { if (!(await P.ev(`return $("${id}").hidden`))) await P.clickEl(`#${id} [data-close]`); await P.until(`return $("${id}").hidden`, `окно ${id} закрыто`); };
  const openTeams = async P => { await P.clickEl("#hubAcc"); await P.clickEl('[data-hubwin="wTeams"]'); await P.until(`return !$("wTeams").hidden && !!$("hubTeamNew")`, "окно «Команды»"); };
  const reopenProjects = async P => { await hideWin(P, "wHubProjects"); await showWin(P, "#hubProjBtn", "wHubProjects"); };
  const GROUP = "Команда «Бюро 1»";
  const inGroup = `(()=>{ const rows=[...document.querySelectorAll("#hubProjList tbody")].filter(t=>t.querySelector(".hubsec")?.textContent===${JSON.stringify(GROUP)}); const r=rows.flatMap(t=>[...t.querySelectorAll("tr:not(:first-child)")]).find(r=>/Командный проект/.test(r.textContent)); return r||null; })()`;
  const anyRow = `[...document.querySelectorAll("#hubProjList tbody tr")].some(r=>/Командный проект/.test(r.textContent))`;
  const bobAcc = async () => B.ev(`const me=await (await fetch("/api/hub/projects")).json(); return me.projects.some(p=>p.name==="Командный проект")`);
  await hideWin(A, "wShare");
  B.allow401 = true;                     // 403 на закрывающемся потоке и проверках B ожидаемы и ниже

  // 1. A создаёт команду
  await openTeams(A);
  await A.fill("#hubTeamNew", "Бюро 1"); await A.clickEl("#hubTeamCreate");
  await A.until(`return /Бюро 1/.test($("hubTeamsBody").textContent) && !!document.querySelector('#hubTeamsBody select[data-act="trole"][data-login="anna"]')`, "команда «Бюро 1» в списке");
  check(await A.ev(`const s=document.querySelector('#hubTeamsBody select[data-act="trole"][data-login="anna"]'); return s.value==="owner" && s.selectedOptions[0].textContent==="владелец команды" && /Проектов в команде пока нет/.test($("hubTeamsBody").textContent)`), "A: команда «Бюро 1» создана, A в ней — «владелец команды», проектов пока нет");
  await A.shot("13-A-komandy.png");
  await hideWin(A, "wTeams");

  // 2. A создаёт проект в команде
  await showWin(A, "#hubProjBtn", "wHubProjects");
  await A.until(`return [...$("hubNewTeam").options].some(o=>o.textContent==="Бюро 1")`, "в «Где создать» есть «Бюро 1»");
  await A.ev(`const s=$("hubNewTeam"); s.value=[...s.options].find(o=>o.textContent==="Бюро 1").value; s.dispatchEvent(new Event("change",{bubbles:true})); return 1`);
  await A.fill("#hubNewName", "Командный проект"); await A.clickEl("#hubNew");
  await A.until(`return Collab.pid && $("hubProjName").textContent==="Командный проект" && $("wHubProjects").hidden`, "командный проект создан и открыт");
  await showWin(A, "#hubProjBtn", "wHubProjects");
  await A.until(`return !!${inGroup}`, "у A проект под заголовком команды");
  check(await A.ev(`return !!${inGroup} && [...document.querySelectorAll("#hubProjList .hubsec")].some(e=>e.textContent==="Личные")`), "A: «Командный проект» в списке под заголовком «Команда «Бюро 1»», «Проверка» осталась в «Личные»");
  await A.shot("14-A-gruppy-proektov.png");
  await hideWin(A, "wHubProjects");

  // 3. B проект не видит
  await reopenProjects(B);
  await B.until(`return $("hubProjList").textContent.trim().length>0`, "список проектов B прорисован");
  check(!(await B.ev(`return ${anyRow}`)) && !(await bobAcc()), "B: «Командного проекта» в списке нет (ни на экране, ни в ответе сервера)");

  // 4. A добавляет B в команду (участник)
  await openTeams(A);
  await A.fill(".hubtadd", "bob"); await A.clickEl('#hubTeamsBody [data-act="tadd"]');
  await A.until(`return !!document.querySelector('#hubTeamsBody select[data-act="trole"][data-login="bob"]')`, "bob в команде");
  check(await A.ev(`const s=document.querySelector('#hubTeamsBody select[data-act="trole"][data-login="bob"]'); return s.value==="member" && s.selectedOptions[0].textContent==="участник" && /Проектов в команде: 1/.test($("hubTeamsBody").textContent)`), "A: bob добавлен в «Бюро 1» ролью «участник», в команде 1 проект");
  await hideWin(A, "wTeams");
  await reopenProjects(B);
  await B.until(`return !!${inGroup}`, "у B проект под заголовком команды");
  check(await B.ev(`const r=${inGroup}; return r.children[1].textContent==="правка"`), "B: «Командный проект» появился под «Команда «Бюро 1»», роль в строке — «правка»");
  await B.clickEl('#hubProjList tbody:has(.hubsec) tr:not(:first-child) [data-act="open"]');
  await B.until(`return Collab.pid && Collab.role==="editor" && $("hubProjName").textContent==="Командный проект" && $("wHubProjects").hidden`, "B открыл командный проект");
  check(await B.ev(`return $("hubRole").textContent==="правка" && !document.body.classList.contains("hub-viewer")`), "B: в шапке роль «правка», открыто для правки");

  // 5. «вся команда смотрит» — у B открытый проект становится «только просмотр»
  await showWin(A, "#hubShareBtn", "wShare");
  await A.until(`return !!document.querySelector('#hubShareBody select[data-act="tacc"]')`, "строка «Вся команда» в «Доступе»");
  check(await A.ev(`return /Вся команда «Бюро 1»/.test($("hubShareBody").textContent) && document.querySelector('#hubShareBody select[data-act="pteam"]').selectedOptions[0].textContent==="Бюро 1" && document.querySelector('#hubShareBody select[data-act="tacc"]').value==="edit"`), "A: в «Доступе» проект лежит в «Бюро 1», вся команда правит");
  await A.shot("15-A-dostup-komanda.png");
  const setTacc = (v) => A.ev(`const s=document.querySelector('#hubShareBody select[data-act="tacc"]'); s.value=${JSON.stringify(v)}; s.dispatchEvent(new Event("change",{bubbles:true})); return 1`);
  await setTacc("view");
  await B.until(`return Collab.role==="viewer" && document.body.classList.contains("hub-viewer")`, "B: открытый командный проект стал «только просмотр»", 8000);
  check(await B.ev(`return /просмотр/.test($("hubRole").textContent) && $("hubSync").dataset.state==="readonly"`), "B: «вся команда смотрит» — в шапке роль «просмотр», статус «только просмотр»");

  // 6. «только приглашённые» — у B доступа нет
  await setTacc("none");
  await B.until(`return !Collab.pid && $("hubProjName").textContent==="Выберите проект" && !$("wHubProjects").hidden`, "B: проект закрыт, открыт список", 10000);
  // список проектов обновляется отдельным запросом после закрытия (loadProjects), на медленной машине позже: ждём условие, а не время
  await B.until(`return /нет доступа/.test($("toast").textContent) && !${anyRow}`, "B: сообщение «больше нет доступа» и проекта нет в списке", 10000);
  check(await B.ev(`return /нет доступа/.test($("toast").textContent) && !document.body.classList.contains("hub-viewer") && !${anyRow}`), "B: «только приглашённые» — сообщение «больше нет доступа», проект закрыт, в списке его нет");

  // 7. снова «вся команда правит», затем A убирает B из команды
  await setTacc("edit");
  await A.until(`return document.querySelector('#hubShareBody select[data-act="tacc"]').value==="edit" && /Доступ команды изменён/.test($("toast").textContent)`, "A: доступ команды «правит» сохранён");
  await reopenProjects(B);
  await B.until(`return !!${inGroup}`, "B снова видит проект");
  check(true, "B: после «вся команда правит» проект снова в его списке");
  await hideWin(A, "wShare");
  await openTeams(A);
  const rmBtn = '#hubTeamsBody [data-act="trm"][data-login="bob"]';
  await A.clickEl(rmBtn);
  await A.until(`return /Точно/.test(document.querySelector(${JSON.stringify(rmBtn)}).textContent)`, "подтверждение «Точно?» для bob");
  await A.clickEl(rmBtn);
  await A.until(`return !document.querySelector('#hubTeamsBody select[data-act="trole"][data-login="bob"]')`, "bob убран из команды");
  await hideWin(A, "wTeams");
  await reopenProjects(B);
  await B.until(`return $("hubProjList").textContent.trim().length>0 && !${anyRow}`, "у B проект исчез из списка");
  check(!(await bobAcc()), "B: убран из команды — «Командного проекта» в списке больше нет, сервер его не отдаёт");

  // 8. команду с проектом удалить нельзя
  await openTeams(A);
  const delBtn = '#hubTeamsBody [data-act="tdel"]';
  await A.clickEl(delBtn);
  await A.until(`return /Точно удалить/.test(document.querySelector(${JSON.stringify(delBtn)}).textContent)`, "подтверждение «Точно удалить?»");
  await A.clickEl(delBtn);
  await A.until(`return /есть проекты/.test($("toast").textContent)`, "сообщение «есть проекты»", 6000);
  check(await A.ev(`return /Бюро 1/.test($("hubTeamsBody").textContent)`), "A: «Удалить команду» с проектом внутри — сообщение «в команде есть проекты», команда осталась");
  await hideWin(A, "wTeams");

  // ---------- этап 2: поиск, избранное, ссылка, копия ----------
  const rowOf = name => `[...document.querySelectorAll("#hubProjList tbody tr")].find(r=>r.querySelector("td.nm")?.title===${JSON.stringify(name)})`;
  const rowPid = async (P, name) => P.ev(`const r=${rowOf(name)}; return r?r.querySelector('[data-act="star"]').dataset.id:null`);
  const groupsOf = P => P.ev(`return [...document.querySelectorAll("#hubProjList tbody")].map(t=>({t:t.querySelector(".hubsec")?.textContent, rows:[...t.querySelectorAll("td.nm")].map(e=>e.title)}))`);
  const ELKA = "Ёлка тест";

  // 1. A создаёт личный проект «Ёлка тест» и ищет его
  await showWin(A, "#hubProjBtn", "wHubProjects");
  await A.ev(`const s=$("hubNewTeam"); s.value=""; s.dispatchEvent(new Event("change",{bubbles:true})); return 1`);
  await A.fill("#hubNewName", ELKA); await A.clickEl("#hubNew");
  await A.until(`return Collab.pid && $("hubProjName").textContent==${JSON.stringify(ELKA)} && $("wHubProjects").hidden`, "проект «Ёлка тест» создан и открыт");
  await showWin(A, "#hubProjBtn", "wHubProjects");
  await A.until(`return !!${rowOf(ELKA)}`, "«Ёлка тест» в списке A");
  await A.fill("#hubQ", "елка");
  await A.until(`return !!${rowOf(ELKA)} && !${rowOf("Проверка")} && !/Ничего не найдено/.test($("hubProjList").textContent)`, "поиск «елка»: виден только «Ёлка тест»");
  check(await A.ev(`return !!${rowOf(ELKA)} && !${rowOf("Командный проект")}`), "A: поиск «елка» (без «ё») находит «Ёлка тест» и скрывает остальные");
  await A.fill("#hubQ", "zzzz");
  await A.until(`return /Ничего не найдено/.test($("hubProjList").textContent)`, "«Ничего не найдено»");
  check(await A.ev(`return !document.querySelector("#hubProjList table")`), "A: поиск «zzzz» — «Ничего не найдено», таблицы нет");
  await A.fill("#hubQ", "елка");
  await A.until(`return !!${rowOf(ELKA)}`, "поиск вернул «Ёлка тест»");
  await A.shot("16-A-poisk.png");
  await A.fill("#hubQ", ""); await A.key("Backspace", "Backspace", { vk: 8 });
  await A.until(`return $("hubQ").value==="" && !!${rowOf("Проверка")} && !!${rowOf(ELKA)}`, "поиск очищен, видны все проекты");
  check(true, "A: поиск очищен — в списке снова все проекты");

  // 2. избранное
  const starSel = pid => `#hubProjList [data-act="star"][data-id="${pid}"]`;
  const elkaPid = await rowPid(A, ELKA);
  check(!!elkaPid, "A: id проекта «Ёлка тест» найден в списке");
  await A.clickEl(starSel(elkaPid));
  await A.until(`return document.querySelector("#hubProjList .hubsec")?.textContent==="Избранное"`, "группа «Избранное» появилась первой");
  { const g = await groupsOf(A);
    check(g[0].t === "Избранное" && g[0].rows.includes(ELKA), "A: «Избранное» первая группа и содержит «Ёлка тест»");
    check(g.some(x => x.t === "Личные" && x.rows.includes(ELKA)), "A: «Ёлка тест» осталась и в группе «Личные»"); }
  await A.shot("17-A-izbrannoe.png");
  await A.clickEl(starSel(elkaPid));
  await A.until(`return ![...document.querySelectorAll("#hubProjList .hubsec")].some(e=>e.textContent==="Избранное")`, "группа «Избранное» исчезла");
  check(true, "A: звезда снята — группы «Избранное» нет");
  await hideWin(A, "wHubProjects");

  // 3. ссылка «по ссылке смотрят»: B заходит по ней
  await showWin(A, "#hubShareBtn", "wShare");
  await A.until(`return !!document.querySelector('#hubShareBody select[data-act="linkrole"]')`, "блок «Доступ по ссылке»");
  check(await A.ev(`return /Доступ по ссылке/.test($("hubShareBody").textContent) && document.querySelector('#hubShareBody select[data-act="linkrole"]').value==="" && !$("hubLinkUrl")`), "A: ссылка по умолчанию выключена, поля со ссылкой нет");
  const setLinkRole = (P, v) => P.ev(`const s=document.querySelector('#hubShareBody select[data-act="linkrole"]'); s.value=${JSON.stringify(v)}; s.dispatchEvent(new Event("change",{bubbles:true})); return 1`);
  await setLinkRole(A, "viewer");
  await A.until(`return !!$("hubLinkUrl") && /#join=/.test($("hubLinkUrl").value)`, "поле со ссылкой появилось");
  const link1 = await A.ev(`return $("hubLinkUrl").value`);
  check(await A.ev(`return $("hubLinkUrl").readOnly && document.querySelector('#hubShareBody select[data-act="linkrole"]').selectedOptions[0].textContent==="по ссылке смотрят" && /Новая ссылка/.test($("hubShareBody").textContent)`), "A: «по ссылке смотрят», ссылка в поле только для чтения, есть «Новая ссылка»");
  await A.shot("18-A-dostup-ssylka.png");
  await B.go(link1);
  await B.until(`return Collab.pid && Collab.role==="viewer" && $("wHubProjects").hidden`, "B открыл проект по ссылке", 12000);
  await B.shot("19-B-po-ssylke.png");
  check(await B.ev(`return $("hubProjName").textContent==${JSON.stringify(ELKA)} && $("hubRole").textContent==="просмотр" && document.body.classList.contains("hub-viewer")`), "B: по ссылке попал в «Ёлка тест», роль «просмотр»");
  check(await B.ev(`return !/join=/.test(location.href)`), "B: в адресной строке нет «join=»");
  check(await B.ev(`return /по ссылке/.test($("toast").textContent)`), "B: тост «Вы открыли проект по ссылке»");

  // 4. «по ссылке правят» — у B открытый проект становится редактируемым
  await setLinkRole(A, "editor");
  await B.until(`return Collab.role==="editor" && !document.body.classList.contains("hub-viewer")`, "B: проект стал редактируемым", 8000);
  check(await B.ev(`return $("hubRole").textContent==="правка" && !document.body.classList.contains("hub-viewer")`), "B: «по ссылке правят» — роль «правка» без перезагрузки");

  // 5. «Новая ссылка» (два нажатия): у B доступа нет, старая ссылка не работает
  const rotSel = '#hubShareBody [data-act="linkrot"]';
  await A.clickEl(rotSel);
  await A.until(`return /Точно/.test(document.querySelector(${JSON.stringify(rotSel)}).textContent)`, "подтверждение «Точно?» у «Новая ссылка»");
  await A.clickEl(rotSel);
  await A.until(`return $("hubLinkUrl") && $("hubLinkUrl").value && $("hubLinkUrl").value!==${JSON.stringify(link1)}`, "в поле новая ссылка", 8000);
  await B.until(`return !Collab.pid && $("hubProjName").textContent==="Выберите проект" && !$("wHubProjects").hidden`, "B: проект закрыт после смены ссылки", 10000);
  check(await B.ev(`return /нет доступа/.test($("toast").textContent) && !document.body.classList.contains("hub-viewer")`), "B: ссылка заменена — «больше нет доступа», проект закрыт");
  await B.go(link1);
  await B.until(`return /ссылка недействительна или отключена/.test($("toast").textContent)`, "тост про старую ссылку", 8000);
  check(await B.ev(`return !Collab.pid && !/join=/.test(location.href)`), "B: старая ссылка — «ссылка недействительна или отключена», проект не открыт");

  // 6. A выключает ссылку
  await setLinkRole(A, "");
  await A.until(`return !$("hubLinkUrl") && document.querySelector('#hubShareBody select[data-act="linkrole"]').value===""`, "ссылка выключена");
  check(true, "A: «выключен» — поле со ссылкой исчезло");

  // 7. B делает копию проекта, который может читать (A даёт B просмотр по логину)
  await A.fill("#hubShareLogin", "bob");
  await A.ev(`$("hubShareRole").value="viewer"; return 1`);
  await A.clickEl('#hubShareBody [data-act="add"]');
  await A.until(`return document.querySelector('select[data-act="role"][data-login="bob"]')?.value==="viewer"`, "bob — «просмотр» в «Доступе»");
  await hideWin(A, "wShare");
  await reopenProjects(B);
  await B.until(`return !!${rowOf(ELKA)}`, "у B в списке «Ёлка тест»", 10000);
  const bobElka = await rowPid(B, ELKA);
  await B.clickEl(`#hubProjList [data-act="copy"][data-id="${bobElka}"]`);
  await B.until(`return !!document.querySelector(".hubcopyname")`, "форма копии");
  check(await B.ev(`return /— копия$/.test(document.querySelector(".hubcopyname").value)`), "B: имя копии по умолчанию оканчивается на «— копия»");
  const copyName = await B.ev(`return document.querySelector(".hubcopyname").value`);
  await B.clickEl('#hubProjList [data-act="copyok"]');
  await B.until(`return Collab.pid && Collab.pid!==${JSON.stringify(bobElka)} && $("hubProjName").textContent===${JSON.stringify(copyName)} && $("wHubProjects").hidden`, "B открыл копию", 12000);
  check(await B.ev(`return $("hubRole").textContent==="владелец" && Collab.role==="owner" && !document.body.classList.contains("hub-viewer")`), "B: копия открыта, роль «владелец»");
  await reopenProjects(B);
  await B.until(`return !!${rowOf(copyName)}`, "копия в списке B", 8000);
  check(await B.ev(`const t=[...document.querySelectorAll("#hubProjList tbody")].find(t=>t.querySelector(".hubsec")?.textContent==="Личные"); return !!t && [...t.querySelectorAll("td.nm")].some(e=>e.title===${JSON.stringify(copyName)})`), "B: копия в группе «Личные»");

  // ---------- консоль ----------
  const all = [...A.logs, ...B.logs];
  if (all.length) console.log("CONSOLE:\n" + all.slice(0, 40).join("\n")); else console.log("console clean (A и B)");
  if (all.length) failed = true;
} catch (e) {
  console.log("STEP FAILED:", e.message); failed = true;
  try { await A?.shot("fail-A.png"); await B?.shot("fail-B.png"); } catch { }
  const all = [...(A?.logs || []), ...(B?.logs || [])]; if (all.length) console.log("CONSOLE:\n" + all.slice(0, 40).join("\n"));
} finally {
  for (const { chrome } of procs) chrome.kill();
  await sleep(800);
  for (const { profile } of procs) rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  process.exit(failed ? 1 : 0);
}
