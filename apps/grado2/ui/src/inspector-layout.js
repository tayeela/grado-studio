/* ГРАДО 2 · перенос прежних окон props/object в один инспектор на том же месте dockview.
   Вызывается после восстановления раскладки; проверяется inspector-layout.test.js и браузерным сценарием. */
export function mergeInspectorPanels(api) {
  const old = api.getPanel("object");
  if (!old) return false;
  const active = api.activePanel?.id === "object";
  if (!api.getPanel("props")) {
    api.addPanel({ id: "props", component: "props", title: "Свойства", position: { referencePanel: "object", direction: "within" }, inactive: !active });
  }
  api.removePanel(old);
  if (active) api.getPanel("props").api.setActive();
  return active;
}
