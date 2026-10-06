// Снимок панорамы Яндекса для листа «Фотофиксация» без наложений (владелец 06.10.2026: «должно быть только фото»):
// Chrome headless + CDP, скрыты метки домов, кнопки, логотип и миникарта. Запуск: node tools/panorama_shot.mjs <ссылка> <out.png>
// (WAIT=мс — ожидание загрузки, по умолчанию 12000). Кадр для листа: вырезать (550, 0, 2650, 1400) и уменьшить до 1500×1000;
// точка и направление съёмки — из развёрнутой ссылки (panorama[point], panorama[direction]).
import { spawn } from "node:child_process";
const [,, url, out] = process.argv;
const port = 9300 + Math.floor(Math.random() * 500);
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ["--headless=new", `--remote-debugging-port=${port}`, "--window-size=1600,1100", "--hide-scrollbars", `--user-data-dir=/tmp/grado-pano-prof-${port}`, "about:blank"], { stdio: "ignore" });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let ws; for (let i = 0; i < 40; i++) { try { const l = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); const p = l.find(x => x.type === "page"); if (p) { ws = p.webSocketDebuggerUrl; break; } } catch {} await sleep(250); }
const sock = new WebSocket(ws); await new Promise(r => sock.onopen = r);
let id = 0; const pend = new Map(); sock.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } };
const cmd = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); sock.send(JSON.stringify({ id: i, method, params })); });
await cmd("Emulation.setDeviceMetricsOverride", { width: 1600, height: 1100, deviceScaleFactor: 2, mobile: false });
await cmd("Network.setUserAgentOverride", { userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36" });
await cmd("Page.enable"); await cmd("Page.navigate", { url });
await sleep(+(process.env.WAIT||12000));
const css = `.panorama-player-placemark,.panorama-player-view__top-block,.panorama-player-view__controls,.panorama-player-view__right-controls,.panorama-player-view__logo,.panorama-controls-view,.panorama-minimap-view{display:none!important}`;
await cmd("Runtime.evaluate", { expression: `(()=>{const s=document.createElement('style');s.textContent=${JSON.stringify(css)};document.head.appendChild(s);const c=document.querySelector('.panorama-player-view__player-container');const r=c?c.getBoundingClientRect():null;return JSON.stringify(r)})()`, returnByValue: true }).then(r => console.log("player", r.result?.result?.value));
await sleep(2500);
const shot = await cmd("Page.captureScreenshot", { format: "png" });
const fs = await import("node:fs"); fs.writeFileSync(out, Buffer.from(shot.result.data, "base64"));
sock.close(); chrome.kill(); await sleep(500); (await import("node:fs")).rmSync(`/tmp/grado-pano-prof-${port}`, { recursive: true, force: true }); process.exit(0);
