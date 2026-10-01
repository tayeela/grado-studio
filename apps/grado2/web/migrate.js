/* ГРАДО 2 · переименование «потолок» → «предельная высота» в проектах (решение владельца 01.10.2026).
   Идемпотентно и без смены номера формата: идёт при каждой загрузке проекта (project.js → migrate, в том числе
   из совместной работы: collab.js → join → applyProject). Трогает только служебный слой «cons:ceiling»
   (поля, стиль) и гнёзда узлов графа «Данные/Ограничения» и «Эскиз/Посадка застройки»; одноимённые поля
   в слоях пользователя остаются как есть. Проверяется под node (tests/migrate_test.js). */
(function (root) {
  const CEIL_KEY = "cons:ceiling";
  const FIELDS = { "Потолок, м": "Предельная высота, м", "Потолок, эт.": "Предельная высота, эт." };
  const SOCKET = { old: "потолок", neu: "предельная высота" };
  const ren = f => (typeof f === "string" && Object.hasOwn(FIELDS, f) ? FIELDS[f] : f);

  function renameCeiling(p) {
    if (!p || typeof p !== "object") return p;
    // стиль слоя: поле раскраски, поле градации, поля правил, подпись
    const spec = (p.layers || []).find(l => l?.key === CEIL_KEY), st = spec?.style;
    if (st && typeof st === "object") {
      if (st.label) st.label = ren(st.label);
      if (st.cat) st.cat.field = ren(st.cat.field);
      if (st.grad) st.grad.field = ren(st.grad.field);
      (st.rules?.list || []).forEach(r => { if (r) r.field = ren(r.field); });
    }
    // данные: свойства объектов слоя (и исходная выгрузка, если она отдельный объект)
    const d = p.data?.[CEIL_KEY];
    for (const fc of d ? [d.fc, d.original && typeof d.original === "object" && d.original !== d.fc ? d.original : null] : []) {
      for (const f of fc?.features || []) {
        const pr = f?.properties; if (!pr || !Object.keys(FIELDS).some(k => Object.hasOwn(pr, k))) continue;
        f.properties = Object.fromEntries(Object.entries(pr).map(([k, v]) => [ren(k), v]));   // порядок полей сохраняется
      }
    }
    // граф: гнёзда по имени, только в узлах программы
    for (const n of p.graph?.nodes || []) {
      const side = n?.type === "Данные/Ограничения" ? n.outputs : n?.type === "Эскиз/Посадка застройки" ? n.inputs : null;
      (side || []).forEach(s => { if (s && s.name === SOCKET.old) s.name = SOCKET.neu; if (s && s.label === SOCKET.old) s.label = SOCKET.neu; });
    }
    return p;
  }
  const api = { renameCeiling, CEIL_KEY };
  if (typeof module === "object" && module.exports) module.exports = api; else root.MIGRATE = api;
})(typeof self !== "undefined" ? self : this);
