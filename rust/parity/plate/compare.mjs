// Сверка пластины на Rust с векторной картой: SVG того же списка операций растрирует Chromium в тот же размер,
// считаются средняя разница каналов и доля пикселей с разницей > 64 (из 255). Запуск: после dump.py —
// CHROME=… node rust/parity/plate/compare.mjs; код выхода 1, если сцена расходится (средняя > 3 или доля > 2 %).
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url)), ROOT = resolve(HERE, "../../..");
const pw = createRequire(join(ROOT, "tools/package.json"))("playwright-core");
const meta = JSON.parse(readFileSync(join(HERE, "out/meta.json"), "utf-8"));
const br = await pw.chromium.launch({ executablePath: process.env.CHROME, args: ["--no-sandbox"] });
const page = await br.newPage();
let bad = 0;
for (const [name, m] of Object.entries(meta)) {
  const W = Math.ceil(m.w * m.dpi / 25.4), H = Math.ceil(m.h * m.dpi / 25.4);
  const svg = readFileSync(join(HERE, `out/${name}.svg`), "utf-8").replace(/width="[\d.]+mm" height="[\d.]+mm"/, `width="${W}" height="${H}"`);
  const png = readFileSync(join(HERE, `out/${name}.png`)).toString("base64");
  const r = await page.evaluate(async ({ svg, png, W, H }) => {
    const load = src => new Promise((ok, bad) => { const i = new Image(); i.onload = () => ok(i); i.onerror = bad; i.src = src; });
    const px = img => { const c = new OffscreenCanvas(W, H), x = c.getContext("2d"); x.fillStyle = "#fff"; x.fillRect(0, 0, W, H); x.drawImage(img, 0, 0, W, H); return x.getImageData(0, 0, W, H).data; };
    const a = px(await load("data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(svg))))), b = px(await load("data:image/png;base64," + png));
    let sum = 0, big = 0, inkA = 0, inkB = 0;
    for (let i = 0; i < a.length; i += 4) {
      const d = (Math.abs(a[i] - b[i]) + Math.abs(a[i + 1] - b[i + 1]) + Math.abs(a[i + 2] - b[i + 2])) / 3;
      sum += d; if (d > 64) big++;
      if (a[i] < 250 || a[i + 1] < 250 || a[i + 2] < 250) inkA++;
      if (b[i] < 250 || b[i + 1] < 250 || b[i + 2] < 250) inkB++;
    }
    const n = a.length / 4;
    return { mean: sum / n, big: big / n, inkSvg: inkA / n, inkPlate: inkB / n };
  }, { svg, png, W, H });
  const ok = r.mean <= 3 && r.big <= 0.02;
  if (!ok) bad++;
  console.log(`${ok ? "ok  " : "FAIL"} ${name} ${W}×${H}: средняя разница ${r.mean.toFixed(2)}, сильно разных ${(r.big * 100).toFixed(2)} %, закраска svg ${(r.inkSvg * 100).toFixed(1)} % / пластина ${(r.inkPlate * 100).toFixed(1)} %`);
}
await br.close();
process.exit(bad ? 1 : 0);
