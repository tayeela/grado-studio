/* ГРАДО 2 · листы сами по территории (план 08.11.2026, шаг 4: «выбрал территорию — листы по видам собрались»).
   У вида настройка auto (viewframes.js AUTO_DEF: вписать территорию с полем или заданный масштаб, формат и ориентация
   листа). Выбрали или поменяли территорию (data.js: роль слоя «Граница территории», участки по номерам) — рамка каждого
   такого вида встаёт по территории (viewframes.js terrFrame), а у вида без своего листа в «Макете листа» появляется лист:
   карта этого вида, легенда «за видом», масштабная линейка, стрелка севера, штамп; название листа — имя вида.
   Пересборка двигает только рамку вида: блоки листа идут за ней сами (sheetmaps.js sync), ручные правки листа остаются.
   Заданный масштаб и «несколько листов» — большая территория делится на листы сеткой (атлас, viewframes.js terrGrid).
   Убрали карту вида с листа — лист больше не пересобирается; удалили лист — он вернётся только при новой территории
   или по кнопке. Зовут ViewsPanel.vue и SheetPanel.vue («Собрать листы»),
   сам — при смене территории. */
import { watch } from "vue";
import * as mskMod from "../../web/msk.js";
import { project } from "./store.js";
import { setLabel } from "./edit.js";
import { newBlock, newId, newSheet, reformat } from "./sheet/model.js";
import { AUTO_DEF, boxM, ringsM, terrFrame, terrGrid } from "./viewframes.js";
import { sync } from "./panels/sheetmaps.js";

const MSK = globalThis.MSK || mskMod.default || mskMod;
const clone = o => JSON.parse(JSON.stringify(o));
export const autoOf = v => ({ ...AUTO_DEF, ...(v?.auto || {}) });
export const autoViews = () => project.views.filter(v => v.auto?.on);

/* лист вида: заготовка «Макета листа» (карта, колонка легенды, стрелка), карта — на виде, легенда — за видом, линейка */
export function autoSheet(v) {
  const a = autoOf(v), s = { id: newId("sheet"), ...newSheet({ format: a.format, orient: a.orient, title: v.name }), auto: v.id };
  const map = s.blocks.find(b => b.kind === "map");
  Object.assign(map, { view: v.id, fit: "fit", round: true });
  let leg = s.blocks.find(b => b.kind === "legend");
  const bar = newBlock("scalebar", s);
  if (!leg) {                                     // книжный лист: колонки нет — легенда полосой под картой, над штампом
    const h = Math.min(45, map.h * 0.3);
    map.h = Math.round((map.h - h - 3) * 100) / 100;
    leg = { ...newBlock("legend", s), x: map.x, y: Math.round((map.y + map.h + 3) * 100) / 100, w: map.w, h: Math.round(h * 100) / 100 };
    s.blocks.push(leg);
  }
  Object.assign(leg, { follow: true, map: map.id, items: [] });
  leg.h = Math.round((leg.h - 14) * 100) / 100;                 // под легендой — масштабная линейка
  Object.assign(bar, { x: leg.x, y: Math.round((leg.y + leg.h + 6) * 100) / 100, w: Math.min(60, leg.w), h: 8, map: map.id });
  s.blocks.push(bar);
  return s;
}

/* Собрать листы: force — пересобрать и те виды, что уже стоят по этой территории (кнопка); без force — только виды,
   у которых территория сменилась. Вид с заданным масштабом и «несколько листов» (split grid), если территория в масштаб
   не влезает, — атлас: рамка вида охватывает всю сетку, у вида листы «лист 1 из N» (sheet.autoCell — номер ячейки),
   карта каждого — своя ячейка (блок карты cell: { center, scale }, sheetmaps.js sync). Лишние листы прежней сетки
   уходят. → { made, moved, fitted: [имена видов, где масштаб пришлось уменьшить], grids: ["«вид» — N листов"], why } */
export function assemble({ force = false } = {}) {
  const views = autoViews(), res = { made: 0, moved: 0, fitted: [], grids: [], why: "" };
  if (!views.length) { res.why = "Нет видов с листом по территории: включите «Лист по территории» у вида"; return res; }
  const toM = c => MSK.fromWgs(c), box = project.territory ? boxM(project.territory.geometry, toM) : null;
  if (!box) { res.why = "Территория не выбрана: назначьте слою роль «Граница территории» или найдите участки по номерам"; return res; }
  const terr = box.map(Math.round).join(","), before = JSON.stringify(project.layouts || []);
  let list = clone(project.layouts || []), rings = null;
  const wgs = c => MSK.toWgs(c).map(x => +(+x).toFixed(7));
  setLabel("Собрать листы по территории");
  views.forEach(v => {
    const a = autoOf(v), sig = `${terr}|${a.split}|${a.overlap}`;
    if (!force && v.auto.terr === sig) return;               // уже по этой территории (лист могли удалить нарочно)
    const mine = () => list.filter(x => x.auto === v.id);
    let first = mine().find(x => !x.autoCell) || mine()[0];
    if (!first) { first = autoSheet(v); list.push(first); res.made++; }
    const map0 = first.blocks.find(b => b.kind === "map" && b.view === v.id);
    if (!map0) return;                                        // карту вида с листа убрали — лист теперь ручной
    rings ||= ringsM(project.territory.geometry, toM);
    const g = terrGrid(box, map0, a, rings);
    if (g) {
      const n = g.cells.length;
      v.frame = { center: wgs([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]), w: g.w, h: g.h, aspect: "free" };
      g.cells.forEach((cell, k) => {
        let s = k ? mine().find(x => x.autoCell === k) : first;
        if (!s) { s = autoSheet(v); list.push(s); res.made++; }
        s.autoCell = k;
        if (s.title === v.name || /— лист \d+ из \d+$/.test(s.title || "")) s.title = `${v.name} — лист ${k + 1} из ${n}`;
        const map = s.blocks.find(b => b.kind === "map" && b.view === v.id);
        if (map) map.cell = { center: wgs(cell.c), scale: g.scale };
      });
      list = list.filter(x => x.auto !== v.id || (x.autoCell || 0) < n);
      res.grids.push(`«${v.name}» — ${n} ${n < 5 ? "листа" : "листов"}`);
    } else {
      const f = terrFrame(box, map0, a);
      if (!f) return;
      v.frame = { center: wgs(f.c), w: f.w, h: f.h, aspect: f.aspect };
      list = list.filter(x => x.auto !== v.id || x === first);  // прежняя сетка — один лист
      delete first.autoCell;
      delete map0.cell;
      if (/— лист \d+ из \d+$/.test(first.title || "")) first.title = v.name;
      if (f.fitted) res.fitted.push(`«${v.name}» 1:${f.scale}`);
    }
    v.auto = { ...v.auto, terr: sig };
    res.moved++;
  });
  list.forEach(s => { if (s.auto) sync(s); });
  if (JSON.stringify(list) !== before) project.layouts = list;
  return res;
}
/* текст итога для строки состояния */
export function assembleNote(r) {
  if (r.why) return r.why;
  const parts = [r.made ? `новых листов: ${r.made}` : "", r.moved ? `видов по территории: ${r.moved}` : "листы уже стоят по территории"].filter(Boolean);
  return `Собрано — ${parts.join(", ")}${r.grids?.length ? `. Несколько листов сеткой: ${r.grids.join(", ")}` : ""}${r.fitted.length ? `. Территория не влезла в заданный масштаб, взят мельче: ${r.fitted.join(", ")}` : ""}`;
}

/* смена территории — листы пересобираются сами (только виды с «Листом по территории») */
let timer = 0;
watch(() => project.territory, () => {
  clearTimeout(timer);
  timer = setTimeout(() => { if (project.territory && autoViews().length) assemble(); }, 400);
});

/* правка настройки вида из окна «Виды»: формат или ориентация — лист вида перекладывается (model.js reformat),
   любая правка — рамка и лист сразу встают заново */
export function setAuto(v, patch) {
  const was = autoOf(v), next = { ...was, ...patch, terr: "" };
  v.auto = next;
  if (!next.on) return null;
  if ((patch.format && patch.format !== was.format) || (patch.orient && patch.orient !== was.orient)) {
    const list = project.layouts || [];
    if (list.some(s => s.auto === v.id)) project.layouts = list.map(s => s.auto === v.id ? reformat(clone(s), { format: next.format, orient: next.orient }) : s);
  }
  return assemble();
}
