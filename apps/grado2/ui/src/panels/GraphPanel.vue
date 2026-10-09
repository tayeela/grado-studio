<!-- ГРАДО 2 · окно «Схема расчёта» нового интерфейса (как окно графа рабочей страницы): блоки и связи на холсте Rete.js
     (карта ядер: Rete.js 2 вместо брошенного litegraph), библиотека блоков слева, «Вся схема», «Пересчитать», «В слой».
     Схема — та же, что в файле проекта и в рабочей странице (graph.js правит её на месте); окно только показывает её и
     передаёт правки: перенос блока, связь, удаление (Del), поля блоков. Выход выбранного блока виден на карте. -->
<template>
  <div class="pane graphp" tabindex="0" @keydown="onKey">
    <div class="gbar">
      <wa-button size="s" appearance="outlined" title="Показать всю схему в окне" @click="fit"><Maximize :size="14" /> Вся схема</wa-button>
      <wa-button size="s" appearance="outlined" title="Пересчитать все блоки заново (данные могли смениться)" @click="recomputeAll"><RefreshCw :size="14" /> Пересчитать</wa-button>
      <wa-button size="s" appearance="outlined" :disabled="!canBake" title="Выход выбранного блока — обычным слоем проекта (у блоков анализа — с таблицей показателей)" @click="bakeNode(selNode)"><Stamp :size="14" /> В слой</wa-button>
      <span class="pv">{{ pv }}</span>
    </div>
    <div class="gbody">
      <div class="glib">
        <template v-for="(types, cat) in LIB" :key="cat">
          <div class="cat">{{ cat }}</div>
          <button v-for="t in types" :key="t" :title="'Добавить блок «' + TYPES[t].title + '» в середину окна'" @click="add(t)">{{ t.split("/")[1] }}</button>
        </template>
      </div>
      <div ref="box" class="gcanvas"></div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Maximize, RefreshCw, Stamp } from "@lucide/vue";
import { ClassicPreset, NodeEditor } from "rete";
import { AreaExtensions, AreaPlugin } from "rete-area-plugin";
import { ConnectionPlugin, Presets as ConnectionPresets } from "rete-connection-plugin";
import { Presets, VuePlugin } from "rete-vue-plugin";
import GraphNode from "./GraphNode.vue";
import GraphSocket from "./GraphSocket.vue";
import GraphConn from "./GraphConn.vue";
import { project } from "../store.js";
import { LIB, TYPES } from "../graphfile.js";
import { addNode, bakeNode, canConnect, connect, disconnect, fcOf, graph, infoOf, moveNode, nodeById, nodeTitle, outputOf, preview, recomputeAll, removeNode, selNode, structRev, tick } from "../graph.js";
import { fmt, m2 } from "../geom.js";

const props = defineProps(["params"]);
const box = ref(null);
let editor = null, area = null, syncing = false, chain = Promise.resolve(), fitted = false;
const SOCK = {};
const sock = t => SOCK[t] ||= new ClassicPreset.Socket(t);
const sigOf = n => JSON.stringify([n.type, (n.inputs || []).map(i => i.type), (n.outputs || []).map(o => o.type)]);

/* схема проекта → холст: убрать лишнее, добавить новое, поставить блоки на места из файла */
async function sync() {
  if (!editor) return;
  syncing = true;
  try {
    const g = graph(), want = new Map((g?.nodes || []).map(n => [String(n.id), n]));
    const wantL = new Map((g?.links || []).filter(Boolean).map(l => [String(l[0]), l]));
    for (const c of editor.getConnections()) if (!wantL.has(c.id) || !want.has(c.source) || !want.has(c.target)) await editor.removeConnection(c.id);
    for (const nd of editor.getNodes()) {
      const n = want.get(nd.id); if (n && sigOf(n) === nd.sig) continue;
      for (const c of editor.getConnections().filter(c => c.source === nd.id || c.target === nd.id)) await editor.removeConnection(c.id);
      await editor.removeNode(nd.id);
    }
    for (const [id, n] of want) {
      let nd = editor.getNode(id);
      if (!nd) {
        nd = new ClassicPreset.Node(TYPES[n.type]?.title || n.type); nd.id = id; nd.sig = sigOf(n);
        (n.inputs || []).forEach((p, i) => nd.addInput(String(i), new ClassicPreset.Input(sock(p.type), p.name)));
        (n.outputs || []).forEach((p, i) => nd.addOutput(String(i), new ClassicPreset.Output(sock(p.type), p.name)));
        await editor.addNode(nd);
      }
      const v = area.nodeViews.get(id), [x, y] = [+n.pos[0] || 0, +n.pos[1] || 0];
      if (v && (v.position.x !== x || v.position.y !== y)) await area.translate(id, { x, y });
    }
    const have = new Set(editor.getConnections().map(c => c.id));
    for (const [id, l] of wantL) {
      if (have.has(id)) continue;
      const s = editor.getNode(String(l[1])), t = editor.getNode(String(l[3]));
      if (!s?.outputs[String(l[2])] || !t?.inputs[String(l[4])]) continue;
      const c = new ClassicPreset.Connection(s, String(l[2]), t, String(l[4])); c.id = id; c.type = l[5];
      await editor.addConnection(c);
    }
  } finally { syncing = false; }
}
const requestSync = () => (chain = chain.then(sync).catch(e => console.warn("[схема]", e)));

/* «Вся схема»; пока вид не трогали руками, окно при смене размера вписывает схему заново (как fitUntouched рабочей страницы) */
let fitSig = "";
const viewSig = () => { const { x, y, k } = area.area.transform; return [x, y, k].map(v => v.toFixed(2)).join(); };
async function fit() { if (!editor?.getNodes().length) return; await AreaExtensions.zoomAt(area, editor.getNodes()); fitSig = viewSig(); }
/* Само окно вписывает схему целиком, но не мельче 60 %: мельче подписи и поля блоков не читаются (модельер QGIS открывает схему
   в натуральную величину). Тогда видно начало схемы — блоки слева вверху, остальное — перетаскиванием и колесом; «Вся схема» вписывает всегда. */
const READABLE = 0.6;
async function autoFit() {
  await fit();
  if (!editor?.getNodes().length || area.area.transform.k >= READABLE) return;
  const ps = editor.getNodes().map(n => area.nodeViews.get(n.id)?.position).filter(Boolean);
  await area.area.zoom(READABLE, 0, 0);
  await area.area.translate(16 - Math.min(...ps.map(p => p.x)) * READABLE, 16 - Math.min(...ps.map(p => p.y)) * READABLE);
  fitSig = viewSig();
}
let ro = null;
function add(type) {
  const r = box.value.getBoundingClientRect(), { x, y, k } = area.area.transform;
  const n = addNode(type, [(r.width / 2 - 100 - x) / k, (r.height / 2 - 40 - y) / k]);
  if (n) selNode.value = n.id;
}
function onKey(e) {
  if (!(e.key === "Delete" || e.key === "Backspace") || selNode.value == null) return;
  if (e.composedPath().some(n => n instanceof HTMLElement && n.matches("input, textarea, select"))) return;
  e.preventDefault(); e.stopPropagation(); removeNode(selNode.value);
}

/* строка над схемой: что на выходе выбранного блока (как подсказка #pv рабочей страницы) */
const ha = f => f ? fmt(m2(f) / 1e4, 2) + " га" : "пусто";
const pv = computed(() => {
  void tick.value;
  const n = selNode.value != null && nodeById(selNode.value);
  if (!n) return project.territory ? "Выберите блок: его выход виден на карте. Перетаскивание от гнезда к гнезду — связь, Del — удалить блок." : "Сначала задайте границу территории (окно «Данные»)";
  const t = n.outputs?.[0]?.type, out = outputOf(n.id, 0), title = nodeTitle(n);
  if (fcOf(n.id)?.length) return `«${title}»: ${infoOf(n.id)}. «В слой» — сохранить результат с таблицей.`;
  if (t === "geom") return `Выход блока «${title}»: ${ha(out)}`;
  if (t === "tep" && out) return `«${title}»: плотность ${fmt(out.density, 1)} тыс. м²/га, население ${fmt(out.m.population)} чел.`;
  if (t === "num") return `«${title}»: ${out}`;
  return `«${title}»: ${infoOf(n.id)}`;
});
const canBake = computed(() => { void tick.value; const n = selNode.value != null && nodeById(selNode.value); return !!n && (n.outputs || []).some(o => o.type === "geom"); });

let off = null;
onMounted(async () => {
  editor = new NodeEditor();
  area = new AreaPlugin(box.value);
  const conn = new ConnectionPlugin(), render = new VuePlugin();
  render.addPreset(Presets.classic.setup({ customize: { node: () => GraphNode, socket: () => GraphSocket, connection: () => GraphConn } }));
  conn.addPreset(ConnectionPresets.classic.setup());
  editor.use(area); area.use(conn); area.use(render);
  AreaExtensions.simpleNodesOrder(area);
  AreaExtensions.selectableNodes(area, AreaExtensions.selector(), { accumulating: AreaExtensions.accumulateOnCtrl() });
  AreaExtensions.restrictor(area, { scaling: { min: 0.15, max: 2 } });
  // правки на холсте → схема проекта (свои правки при синхронизации не возвращаются обратно)
  editor.addPipe(ctx => {
    if (syncing) return ctx;
    if (ctx.type === "connectioncreate") {
      const c = ctx.data;
      if (canConnect(c.source, +c.sourceOutput, c.target, +c.targetInput)) connect(+c.source, +c.sourceOutput, +c.target, +c.targetInput);
      return undefined;                     // связь добавит синхронизация — с номером из схемы
    }
    if (ctx.type === "connectionremoved") disconnect(ctx.data.id);
    return ctx;
  });
  area.addPipe(ctx => {
    if (ctx.type === "nodepicked") selNode.value = +ctx.data.id;
    else if (ctx.type === "pointerdown" && !ctx.data.event.target.closest?.(".gnode")) selNode.value = null;
    else if (ctx.type === "nodedragged" && !syncing) { const v = area.nodeViews.get(ctx.data.id); if (v) moveNode(ctx.data.id, v.position.x, v.position.y); }
    return ctx;
  });
  await requestSync();
  ro = new ResizeObserver(() => { if (fitSig && fitSig === viewSig()) autoFit(); }); ro.observe(box.value);
  const api = props.params?.api;
  preview.graph = api ? api.isVisible : true;
  if (preview.graph) requestAnimationFrame(() => { autoFit(); fitted = true; });
  off = api?.onDidVisibilityChange?.(e => { preview.graph = e.isVisible; if (e.isVisible && !fitted) requestAnimationFrame(() => { autoFit(); fitted = true; }); });
});
watch(structRev, requestSync);
watch(() => project.raw, () => { fitted = false; requestSync().then(() => { if (preview.graph) { autoFit(); fitted = true; } }); });
onBeforeUnmount(() => { off?.dispose?.(); ro?.disconnect(); preview.graph = false; area?.destroy(); editor = null; });
</script>

<style>
.graphp { display: flex; flex-direction: column; padding: 0; outline: none; }
.graphp .gbar { display: flex; align-items: center; gap: 6px; padding: 4px 6px; border-bottom: 1px solid var(--g-line); flex-wrap: wrap; }
.graphp .gbar wa-button::part(base) { gap: 4px; }
.graphp .pv { font-size: var(--wa-font-size-xs); color: var(--g-muted); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.graphp .gbody { flex: 1; display: flex; min-height: 0; }
.graphp .glib { width: 150px; flex: none; overflow: auto; border-right: 1px solid var(--g-line); padding: 4px; font-size: var(--wa-font-size-s); }
.graphp .glib .cat { font-weight: 600; margin: 6px 0 2px; color: var(--g-muted); font-size: var(--wa-font-size-xs); text-transform: uppercase; letter-spacing: .03em; }
.graphp .glib button { display: block; width: 100%; text-align: left; border: 0; background: none; padding: 3px 6px; border-radius: 4px; cursor: pointer; color: inherit; font: inherit; }
.graphp .glib button:hover { background: var(--wa-color-neutral-fill-quiet); }
.graphp .gcanvas { flex: 1; position: relative; overflow: hidden; background: var(--g-canvas);
  background-image: radial-gradient(var(--g-line) 1px, transparent 1px); background-size: 20px 20px; }
</style>
