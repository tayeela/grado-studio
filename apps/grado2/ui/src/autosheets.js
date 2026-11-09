/* ГРАДО 2 · листы сами по территории (план 08.11.2026, шаг 4: «выбрал территорию — листы по видам собрались»).
   У вида настройка auto (viewframes.js AUTO_DEF: вписать территорию с полем или заданный масштаб, формат и ориентация
   листа). Выбрали или поменяли территорию (data.js: роль слоя «Граница территории», участки по номерам) — рамка каждого
   такого вида встаёт по территории (viewframes.js terrFrame), а у вида без своего листа в «Макете листа» появляется лист:
   карта этого вида, легенда «за видом», масштабная линейка, стрелка севера, штамп; название листа — имя вида.
   Пересборка двигает только рамку вида: блоки листа идут за ней сами (sheetmaps.js sync), ручные правки листа остаются.
   Убрали карту вида с листа — лист больше не пересобирается; удалили лист — он вернётся только при новой территории
   или по кнопке. Зовут ViewsPanel.vue и SheetPanel.vue («Собрать листы»),
   сам — при смене территории. */
import { watch } from "vue";
import * as mskMod from "../../web/msk.js";
import { project } from "./store.js";
import { setLabel } from "./edit.js";
import { newBlock, newId, newSheet, reformat } from "./sheet/model.js";
import { AUTO_DEF, boxM, terrFrame } from "./viewframes.js";
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
   у которых территория сменилась. → { made, moved, fitted: [имена видов, где масштаб пришлось уменьшить], why } */
export function assemble({ force = false } = {}) {
  const views = autoViews(), res = { made: 0, moved: 0, fitted: [], why: "" };
  if (!views.length) { res.why = "Нет видов с листом по территории: включите «Лист по территории» у вида"; return res; }
  const box = project.territory ? boxM(project.territory.geometry, c => MSK.fromWgs(c)) : null;
  if (!box) { res.why = "Территория не выбрана: назначьте слою роль «Граница территории» или найдите участки по номерам"; return res; }
  const terr = box.map(Math.round).join(","), list = clone(project.layouts || []), before = JSON.stringify(list);
  setLabel("Собрать листы по территории");
  views.forEach(v => {
    if (!force && v.auto.terr === terr) return;               // уже по этой территории (лист могли удалить нарочно)
    let s = list.find(x => x.auto === v.id);
    if (!s) { s = autoSheet(v); list.push(s); res.made++; }
    const map = s.blocks.find(b => b.kind === "map" && b.view === v.id);
    if (!map) return;                                         // карту вида с листа убрали — лист теперь ручной
    const f = terrFrame(box, map, autoOf(v));
    if (!f) return;
    v.frame = { center: MSK.toWgs(f.c).map(x => +(+x).toFixed(7)), w: f.w, h: f.h, aspect: f.aspect };
    v.auto = { ...v.auto, terr };
    if (f.fitted) res.fitted.push(`«${v.name}» 1:${f.scale}`);
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
  return `Собрано — ${parts.join(", ")}${r.fitted.length ? `. Территория не влезла в заданный масштаб, взят мельче: ${r.fitted.join(", ")}` : ""}`;
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
    const list = project.layouts || [], i = list.findIndex(s => s.auto === v.id);
    if (i >= 0) { const l = clone(list); l[i] = reformat(l[i], { format: next.format, orient: next.orient }); project.layouts = l; }
  }
  return assemble();
}
