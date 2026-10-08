// Состав альбома ППТ КРТ как JSON для tools/wiki.py (страница вики sheets.md): выполняет apps/grado2/web/albums.js в песочнице Node
// (глобальные имена других файлов страницы подменяются заглушками), поэтому список листов и порядок выдачи — ровно то, что
// собирает программа, а не разбор текста регулярными выражениями. Запуск: node tools/wiki_albums.mjs (нужен только Node).
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { createRequire } from "node:module";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const WEB = path.join(ROOT, "apps/grado2/web");
const require = createRequire(import.meta.url);
const src = fs.readFileSync(path.join(WEB, "albums.js"), "utf8");

// заглушка, которая принимает любые обращения: albums.js при загрузке только описывает данные и функции
const stub = () => new Proxy(function () {}, { get: (_, k) => (k === Symbol.toPrimitive ? () => "" : stub()), apply: () => stub(), construct: () => stub() });
const stubs = new Set();
let ctx = null;
for (let tries = 0; tries < 80 && !ctx; tries++) {
  const sandbox = { console, AlbumGeo: require(path.join(WEB, "albumgeo.js")), AlbumMeta: require(path.join(WEB, "albummeta.js")),
    SheetLayout: require(path.join(WEB, "sheetlayout.js")), cloneJ: x => JSON.parse(JSON.stringify(x)) };   // cloneJ — как в sheets.js
  for (const name of stubs) sandbox[name] = stub();
  const trial = vm.createContext(sandbox);
  try { vm.runInContext(src, trial, { filename: "albums.js" }); ctx = trial; }
  catch (e) {
    const m = /^(\w+) is not defined/.exec(e.message);
    if (!m) { console.error("albums.js: " + e.message.split("\n")[0]); process.exit(1); }
    stubs.add(m[1]);
  }
}
if (!ctx) { console.error("albums.js: не удалось загрузить"); process.exit(1); }

const get = expr => vm.runInContext(expr, ctx);
const sheets = get("PPTKRT").map((s, i) => ({
  i,
  title: s.title || "",
  concept: s.concept || "",
  kind: s.kind || "",
  basemap: s.basemap || "",
  keys: s.keys || [],
  flags: ["sit", "bleed", "twin"].filter(f => s[f]).concat(s.fit ? ["fit:" + s.fit] : []),
}));
process.stdout.write(JSON.stringify({ order: get("PPTKRT_ORDER"), sheets }, null, 1) + "\n");
