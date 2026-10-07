/* Легенда листов 5–9 — только из нарисованного (правило 7, T85a) и общие препятствия подписей рек (правило 0, T85b).
   Чистые функции, без карты: albums.js даёт им «что есть в рамке», они отвечают «что писать». Проверки — tests/test_legendrules_js.py.
   Слово владельца 06.10.2026: «всё должно быть не по предустановленному скрипту, а максимально гибко, но при этом под цели сбора». */
(function (root) {
  // has: { ppt, pmt, gpzu, agr } — есть ли документ этого вида в рамке листа
  const BASE = { ppt: { ppt: "ППТ", pmt: "ПМТ" }, gpzu: { gpzu: "ГПЗУ", agr: "АГР" }, docs: { ppt: "ППТ", pmt: "ПМТ", gpzu: "ГПЗУ", agr: "АГР" } };
  const KINDS = { ppt: ["ppt", "pmt"], gpzu: ["gpzu", "agr"], docs: ["ppt", "pmt", "gpzu", "agr"] };
  const joinRu = a => a.length > 1 ? a.slice(0, -1).join(", ") + " и " + a.at(-1) : a[0];   // «А», «А и Б», «А, Б и В»
  const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  // виды документов листа, которые есть в рамке, в порядке знаков легенды
  const docKinds = (concept, has = {}) => (KINDS[concept] || []).filter(k => has[k]);
  // по правилу 12: название — по тому, что в рамке. Ничего нет — название не трогаем (лист «не готов», см. docWhy)
  function docTitle(concept, title, has = {}) {
    const all = KINDS[concept]; if (!all) return title;
    const t = String(title || ""), got = docKinds(concept, has);
    if (!got.length || got.length === all.length) return t;
    const names = BASE[concept], full = all.map(k => names[k]).join(" и ");
    return t.replace(new RegExp(esc(full) + "(?=$|[\\s,.»])"), names[got[0]]);
  }
  // почему лист «не готов»: в рамке нет ни одного документа его вида
  function docWhy(concept, has = {}) {
    const all = KINDS[concept]; if (!all || docKinds(concept, has).length) return "";
    return "в рамке нет " + joinRu(all.map(k => BASE[concept][k]));
  }
  // группы легенды без знаков не печатаются (заголовок без пунктов)
  const pruneGroups = groups => (groups || []).filter(g => g && (g.items || []).length);
  // подпись реки не должна зависеть от того, какой лист посчитан первым: препятствия — дороги из данных проекта по
  // правилу векторных схем (ЕГКО первым, Яндекс — если у ЕГКО нет пригодного), а не из слоёв листа. areas: { ya, egko } м²
  // в рамке; pick — RoadSrc.pickRoadSource
  const obstacleSource = (areas, pick) => pick(areas, { vector: true });
  // Пояснение под легендой про санитарно-защитные зоны (правило 14, F1 06.10.2026): территория лежит в зонах каждого вида,
  // а не в одной «ориентировочной». kinds: [{ code, n, share }] — код вида (5 установленные, 62 расчётные, 63 ориентировочные),
  // n — сколько зон этого вида задевает территорию, share — доля территории под зонами вида (0…1). Весь вид (≥ 99,5 %) —
  // «расположена в границах», часть — «частично расположена в границах». Полное предложение с точкой (правило 2.43)
  const SZZ_ADJ = { 5: ["установленной", "установленных"], 62: ["расчётной", "расчётных"], 63: ["ориентировочной", "ориентировочных"] };
  const SZZ_ORD = { 5: 0, 62: 1, 63: 2 };
  function szzPhrase(ks) {
    const one = ks.every(k => k.n <= 1), many = ks.every(k => k.n > 1), adj = k => SZZ_ADJ[k.code][k.n > 1 ? 1 : 0];
    const zone = n => n > 1 ? "санитарно-защитных зон" : "санитарно-защитной зоны", join = a => a.length > 1 ? a.slice(0, -1).join(", ") + " и " + a.at(-1) : a[0];
    return one || many ? join(ks.map(adj)) + " " + zone(ks[0].n) : join(ks.map(k => adj(k) + " " + zone(k.n)));
  }
  function szzNote(kinds, full = .995, min = .005) {
    const ks = (kinds || []).filter(k => SZZ_ADJ[k.code] && k.n > 0 && k.share > min).sort((a, b) => SZZ_ORD[a.code] - SZZ_ORD[b.code]);
    const all = ks.filter(k => k.share >= full), part = ks.filter(k => k.share < full);
    return [all.length ? "Территория расположена в границах " + szzPhrase(all) + "." : "",
      part.length ? "Территория частично расположена в границах " + szzPhrase(part) + "." : ""].filter(Boolean).join(" ");
  }
  // пояснения без заголовка (группа из одних строк «note») — после всех групп легенды (слайд-правило 5.9, F12)
  const isNoteGroup = g => !g.title && (g.items || []).length > 0 && g.items.every(i => i.kind === "note");
  const notesLast = groups => { const g = groups || []; return [...g.filter(x => !isNoteGroup(x)), ...g.filter(isNoteGroup)]; };
  const api = { docKinds, docTitle, docWhy, pruneGroups, obstacleSource, szzNote, notesLast };
  if (typeof module === "object" && module.exports) module.exports = api;
  root.LegendRules = api;
})(typeof window !== "undefined" ? window : globalThis);
