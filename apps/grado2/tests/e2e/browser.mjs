// ГРАДО 2 · запуск headless Chrome для браузерных сценариев через Playwright (playwright-core из tools/node_modules).
// Зовут driver.mjs и collab_scenarios.mjs; браузер — свой Chrome (env CHROME или путь macOS), Playwright браузеры не скачивает.
// launch() → { page, cdp, send, logs, close }: send(method, params) — команда DevTools страницы (Input.*, Runtime.evaluate…) с ответом
// в прежнем виде { result }, cdp.on(событие) — события DevTools, logs — console.error/warn и исключения страницы (events: false — без них).
// Установка: (cd tools && npm ci).
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { resolve, dirname } from "node:path";

const TOOLS = resolve(dirname(fileURLToPath(import.meta.url)), "../../../../tools/package.json");
export const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

function playwright() {
  try { return createRequire(TOOLS)("playwright-core"); }
  catch { throw new Error("нет playwright-core: выполните (cd tools && npm ci)"); }
}

export async function launch({ width = 1440, height = 900, events = true } = {}) {
  const browser = await playwright().chromium.launch({
    executablePath: CHROME, headless: true,
    args: ["--no-first-run", "--no-default-browser-check", "--no-sandbox", "--enable-unsafe-swiftshader", `--window-size=${width},${height}`],
  });
  const context = await browser.newContext({ viewport: null });     // размер окна задаёт Emulation ниже, как раньше
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  const logs = [];
  const send = async (method, params = {}) => {
    try { return { result: await cdp.send(method, params) }; }
    catch (e) { return { error: { message: e.message } }; }
  };
  if (events) {                                                      // как прежде: console.error/warn и исключения страницы
    cdp.on("Runtime.consoleAPICalled", m => { if (["error", "warning"].includes(m.type)) logs.push(m.type + ": " + m.args.map(a => a.value ?? a.description).join(" ")); });
    cdp.on("Runtime.exceptionThrown", m => logs.push("EXCEPTION: " + (m.exceptionDetails.exception?.description || m.exceptionDetails.text)));
  }
  await send("Runtime.enable"); await send("Page.enable");
  await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
  return { browser, context, page, cdp, send, logs, close: () => browser.close().catch(() => {}) };
}
