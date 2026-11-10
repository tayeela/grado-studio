<!-- ГРАДО · каркас нового интерфейса (план 09.11.2026, шаг И1): шапка со строкой пяти шагов работы, окна рабочего места
     (dockview), командная строка с журналом и строка состояния (координаты МСК, масштаб). Окна места — workspaces.ts;
     раскладка каждого места запоминается на этом компьютере. Ctrl+Z / Ctrl+Shift+Z — общая отмена (commands/bus.ts). -->
<template>
  <div class="g3">
    <header class="g3-head">
      <span class="g3-brand">ГРАДО</span>
      <span class="g3-proj" :title="project.name">{{ project.name || "проект не открыт" }}{{ project.dirty ? " •" : "" }}</span>
      <nav class="g3-steps" aria-label="Шаги работы">
        <button v-for="w in WORKSPACES" :key="w.id" class="g3-step" :aria-current="ui.ws === w.id ? 'step' : undefined"
                :title="w.hint" @click="cmd.run('место ' + w.n)">
          <span class="n" :class="{ ok: stepDone(w.id) }">{{ w.n }}</span><span class="t">{{ w.title }}</span>
        </button>
      </nav>
      <div class="g3-undo">
        <wa-button size="small" appearance="plain" :disabled="!canUndo" :title="undoTitle" @click="cmd.run('отменить')">Отменить</wa-button>
        <wa-button size="small" appearance="plain" :disabled="!canRedo" :title="redoTitle" @click="cmd.run('вернуть')">Вернуть</wa-button>
        <wa-button size="small" appearance="filled" :disabled="!project.doc" @click="cmd.run('сохранить')">Сохранить</wa-button>
      </div>
    </header>
    <DockviewVue class="g3-dock dockview-theme-grado" :theme="dockTheme" @ready="onReady" />
    <CommandLine />
    <footer class="g3-status">
      <span>{{ cursorText }}</span>
      <span>{{ ui.scale ? "1 : " + Math.round(ui.scale).toLocaleString("ru-RU") : "" }}</span>
      <span class="grow"></span>
      <span>{{ wsHint }}</span>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, watch } from "vue";
import { DockviewVue, themeLight, type DockviewReadyEvent, type DockviewApi } from "dockview-vue";
import CommandLine from "./CommandLine.vue";
import { WORKSPACES, workspace } from "./workspaces";
import { useProject } from "./stores/project";
import { useUi } from "./stores/ui";
import { useCommands } from "./stores/commands";

const project = useProject(), ui = useUi(), cmd = useCommands();
const dockTheme = { ...themeLight, className: "dockview-theme-grado", gap: 8 };
let api: DockviewApi | null = null;

const canUndo = computed(() => (cmd.tick, cmd.bus.canUndo));
const canRedo = computed(() => (cmd.tick, cmd.bus.canRedo));
const undoTitle = computed(() => (cmd.tick, cmd.bus.undoTitle ? "Отменить: " + cmd.bus.undoTitle : "Отменять нечего"));
const redoTitle = computed(() => (cmd.tick, cmd.bus.redoTitle ? "Вернуть: " + cmd.bus.redoTitle : "Возвращать нечего"));
const cursorText = computed(() => ui.cursor ? `X ${ui.cursor[0].toFixed(2)}   Y ${ui.cursor[1].toFixed(2)}   МСК` : "МСК");
const wsHint = computed(() => workspace(ui.ws)?.hint || "");

/** шаг сделан: территория выбрана; данные есть; остальные — по мере переноса окон */
function stepDone(id: string): boolean {
  if (id === "territory") return !!project.territory;
  if (id === "data") return project.layers.length > 1;
  return false;
}

const KEY = (id: string) => "grado3.layout." + id;
function build(id: string) {
  if (!api) return;
  const w = workspace(id);
  if (!w) return;
  api.clear();
  try {
    const s = localStorage.getItem(KEY(id));
    if (s) { api.fromJSON(JSON.parse(s)); return; }
  } catch { api.clear(); }
  for (const p of w.panels) {
    api.addPanel({
      id: p.id, component: p.component, title: p.title, params: { stub: p.stub },
      ...(p.at && api.getPanel(p.at.ref) ? { position: { referencePanel: p.at.ref, direction: p.at.dir } } : {}),
      ...(p.size && p.at && (p.at.dir === "left" || p.at.dir === "right") ? { initialWidth: p.size } : {}),
      ...(p.size && p.at && (p.at.dir === "above" || p.at.dir === "below") ? { initialHeight: p.size } : {}),
    });
  }
  // во вкладках группы впереди первое окно места (Слои, а не Проект), фокус — на карте
  for (const p of w.panels) if (p.at?.dir !== "within") api.getPanel(p.id)?.api.setActive();
  api.getPanel(w.panels[0].id)?.api.setActive();
}
function onReady(e: DockviewReadyEvent) {
  api = e.api;
  build(ui.ws);
  api.onDidLayoutChange(() => { try { localStorage.setItem(KEY(ui.ws), JSON.stringify(api!.toJSON())); } catch { /* частный режим */ } });
}
watch(() => ui.ws, id => build(id));

function onKey(e: KeyboardEvent) {
  const mod = e.ctrlKey || e.metaKey;
  if (!mod) return;
  const k = e.key.toLowerCase();
  if ((k === "z" || k === "я") && !e.shiftKey) { e.preventDefault(); cmd.run("отменить"); }
  else if (((k === "z" || k === "я") && e.shiftKey) || k === "y" || k === "н") { e.preventDefault(); cmd.run("вернуть"); }
  else if (k === "s" || k === "ы") { e.preventDefault(); cmd.run("сохранить"); }
}
onMounted(async () => {
  window.addEventListener("keydown", onKey);
  // проект из адреса (?p=название) или последний изменённый
  const want = new URLSearchParams(location.search).get("p");
  try {
    const list = await project.refreshList();
    const name = want || list[0]?.name;
    if (name) await cmd.run(`открыть "${name}"`);
  } catch { /* сервер без папки проектов (совместный режим): открытие — командой */ }
});
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>
