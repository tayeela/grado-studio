/* Легенда листов 5–9 — только из нарисованного (правило 7, T85a) и общие препятствия подписей рек (правило 0, T85b).
   Чистые функции, без карты: albums.js даёт им «что есть в рамке», они отвечают «что писать». Проверки — tests/test_legendrules_js.py.
   Слово владельца 06.10.2026: «всё должно быть не по предустановленному скрипту, а максимально гибко, но при этом под цели сбора». */
(function (root) {
  // has: { ppt, pmt, gpzu, agr } — есть ли документ этого вида в рамке листа
  const BASE = { ppt: { ppt: "ППТ", pmt: "ПМТ" }, gpzu: { gpzu: "ГПЗУ", agr: "АГР" } };
  const KINDS = { ppt: ["ppt", "pmt"], gpzu: ["gpzu", "agr"] };
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
    return "в рамке нет " + all.map(k => BASE[concept][k]).join(" и ");
  }
  // группы легенды без знаков не печатаются (заголовок без пунктов)
  const pruneGroups = groups => (groups || []).filter(g => g && (g.items || []).length);
  // подпись реки не должна зависеть от того, какой лист посчитан первым: препятствия — дороги из данных проекта по
  // правилу векторных схем (ЕГКО первым, Яндекс — если у ЕГКО нет пригодного), а не из слоёв листа. areas: { ya, egko } м²
  // в рамке; pick — RoadSrc.pickRoadSource
  const obstacleSource = (areas, pick) => pick(areas, { vector: true });
  const api = { docKinds, docTitle, docWhy, pruneGroups, obstacleSource };
  if (typeof module === "object" && module.exports) module.exports = api;
  root.LegendRules = api;
})(typeof window !== "undefined" ? window : globalThis);
