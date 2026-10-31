/* ГРАДО 2 · проверяет перенос старых раскладок без потери группы и дубликатов инспектора.
   Запуск: cd apps/grado2/ui && npm test. */
import test from "node:test";
import assert from "node:assert/strict";
import { mergeInspectorPanels } from "./inspector-layout.js";

function layout(ids, active) {
  const panels = new Map(ids.map(id => [id, { id, group: id + "-group", api: { setActive() { api.activePanel = panels.get(id); } } }]));
  const added = [];
  const api = {
    activePanel: panels.get(active), getPanel: id => panels.get(id),
    addPanel(p) { added.push(p); panels.set(p.id, { id: p.id, group: panels.get(p.position.referencePanel).group, api: { setActive() { api.activePanel = panels.get(p.id); } } }); },
    removePanel(p) { panels.delete(p.id); },
  };
  return { api, panels, added };
}
test("два старых окна: положение props сохраняется, активный объект становится вкладкой", () => {
  const { api, panels, added } = layout(["map", "props", "object"], "object");
  assert.equal(mergeInspectorPanels(api), true);
  assert.equal(panels.get("props").group, "props-group");
  assert.equal(panels.has("object"), false);
  assert.equal(api.activePanel.id, "props");
  assert.deepEqual(added, []);
  assert.equal(mergeInspectorPanels(api), false);
});
test("только object: инспектор занимает ту же группу, карта остаётся активной", () => {
  const { api, panels, added } = layout(["map", "object"], "map");
  assert.equal(mergeInspectorPanels(api), false);
  assert.equal(panels.get("props").group, "object-group");
  assert.equal(api.activePanel.id, "map");
  assert.equal(added[0].inactive, true);
  assert.equal(panels.has("object"), false);
});
test("закрытые окна не появляются сами при повторном переносе", () => {
  const { api, panels } = layout(["map"], "map");
  assert.equal(mergeInspectorPanels(api), false);
  assert.deepEqual([...panels.keys()], ["map"]);
});
