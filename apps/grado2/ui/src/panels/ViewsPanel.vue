<!-- ГРАДО 2 · окно «Виды» нового интерфейса (как «Темы карты» в QGIS и web/views.js рабочей страницы): вид запоминает,
     какие слои видны, их оформление и прозрачность, видимость групп, подложку и, по желанию, масштаб. «Показать»
     возвращает карту к виду одним щелчком; легенда вида — его видимые слои с классами. Виды хранятся в файле проекта
     (поле views, тот же формат) и служат листам альбома: удалённый вид переводит свои листы на текущую карту. -->
<template>
  <div class="pane views">
    <div class="bar">
      <wa-input size="s" placeholder="Название вида, например «Ограничения»" :value="name" @input="e => (name = e.target.value)" @keydown.enter="add"></wa-input>
      <wa-checkbox size="s" :checked="withExt" title="Вид запомнит и масштаб карты" @change="e => (withExt = e.target.checked)">с масштабом</wa-checkbox>
      <wa-button size="s" variant="brand" title="Запомнить видимые слои, их оформление и подложку" @click="add"><BookmarkPlus :size="15" /> Сохранить вид</wa-button>
    </div>

    <p v-if="!project.views.length" class="hint">Видов пока нет. Настройте карту (какие слои видны, их стиль, подложку) и сохраните вид —
      например «Существующее положение», «Ограничения», «Эскиз». Переключение вида меняет карту одним щелчком.</p>
    <table v-else class="vl">
      <tr v-for="v in project.views" :key="v.id" :class="{ cur: v.id === viewCur }">
        <td class="nm" :title="`Показать вид «${v.name}»: ${v.layers.filter(x => x.visible).length} видимых слоёв${v.extent ? ', с масштабом' : ''}`" @click="show(v)">
          <Eye :size="14" /> {{ v.name }}<span class="n"> · {{ v.layers.filter(x => x.visible).length }} сл.{{ v.extent ? " · масштаб" : "" }}</span></td>
        <td class="act">
          <wa-button size="s" appearance="plain" title="Заменить вид текущим состоянием карты" @click="update(v)"><RefreshCw :size="14" /></wa-button>
          <wa-button size="s" :appearance="confirmId === v.id ? 'filled' : 'plain'" :variant="confirmId === v.id ? 'danger' : 'neutral'"
                     :title="confirmId === v.id ? 'Нажмите ещё раз, чтобы удалить' : 'Удалить вид'" @click="remove(v)">
            <template v-if="confirmId === v.id">Удалить?</template><Trash2 v-else :size="14" /></wa-button>
        </td>
      </tr>
    </table>
    <p v-if="confirmId && usedBy(confirmId).length" class="hint">Листов с этим видом: {{ usedBy(confirmId).length }} — они перейдут на текущую карту.</p>

    <template v-if="cur">
      <div class="sect">Легенда вида «{{ cur.name }}»</div>
      <p v-if="!legend.length" class="hint">В виде нет видимых слоёв</p>
      <div v-for="g in legend" :key="g.key" class="lg">
        <div class="lgh"><span class="sw" :class="g.sw.kind" :style="{ '--c': g.sw.c, '--e': g.sw.e }"></span>{{ g.title }}</div>
        <div v-for="(it, i) in g.items" :key="i" class="lgi">
          <span class="sw" :class="g.sw.kind === 'line' ? 'line' : g.sw.kind === 'point' ? 'point' : 'poly'" :style="{ '--c': it.c, '--e': it.c }"></span>{{ it.v || "—" }}</div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { BookmarkPlus, Eye, RefreshCw, Trash2 } from "@lucide/vue";
import { basemapId, project, setBasemap, swatchOf, viewCur, viewNow } from "../store.js";
import { dataRev, grp, mapApi } from "../edit.js";
import { notice } from "../project.js";
import { fullStyle, legendItems, okn } from "../symbology.js";

const name = ref(""), withExt = ref(false), confirmId = ref("");
const clone = o => JSON.parse(JSON.stringify(o));

function capture(title, ext) {
  return { id: "v" + Date.now().toString(36), name: title, basemap: basemapId.value,
    layers: project.layers.map(l => ({ key: l.key, visible: l.visible, style: clone(l.style), layerOpacity: l.layerOpacity })),
    groups: project.groups.map(g => ({ id: g.id, visible: g.visible })),
    extent: ext && viewNow.center ? { center: [...viewNow.center], zoom: viewNow.zoom } : null };
}
function add() {
  const t = name.value.trim() || `Вид ${project.views.length + 1}`, v = capture(t, withExt.value);
  project.views.push(v); viewCur.value = v.id; name.value = "";
  notice.value = `Вид «${t}» сохранён`;
}
/* Слой, которого в виде нет (добавлен позже), скрывается — как у рабочей страницы. */
function show(v) {
  const by = new Map(v.layers.map(x => [x.key, x]));
  project.layers.forEach(l => {
    const x = by.get(l.key); if (!x) { l.visible = false; return; }
    l.visible = x.visible; l.layerOpacity = okn(x.layerOpacity, 1); l.style = fullStyle(clone(x.style));
  });
  v.groups.forEach(x => { const g = grp(x.id); if (g) g.visible = x.visible; });
  if (v.basemap) setBasemap(v.basemap);
  if (v.extent?.center) mapApi.setView?.(v.extent.center, v.extent.zoom);
  viewCur.value = v.id; confirmId.value = "";
}
function update(v) {
  const i = project.views.indexOf(v);
  project.views.splice(i, 1, { ...capture(v.name, !!v.extent), id: v.id }); viewCur.value = v.id;
  notice.value = `Вид «${v.name}» обновлён`;
}
const sheets = () => project.raw?.album?.sheets || [];
const usedBy = id => sheets().filter(s => s.view === id);
/* Удаление — со второго нажатия. Лист на удалённом виде не печатает молча «что сейчас на карте»: он явно переводится
   на текущую карту (album.sheets[].view = ""), как в web/views.js. */
function remove(v) {
  if (confirmId.value !== v.id) { confirmId.value = v.id; return; }
  const used = usedBy(v.id);
  used.forEach(s => { s.view = ""; });
  project.views.splice(project.views.indexOf(v), 1);
  if (viewCur.value === v.id) viewCur.value = null;
  confirmId.value = "";
  notice.value = used.length ? `Вид «${v.name}» удалён. Листы ${used.map(s => `«${s.title}»`).join(", ")} теперь показывают текущую карту`
    : `Вид «${v.name}» удалён. Ctrl+Z — вернуть`;
}

const cur = computed(() => project.views.find(v => v.id === viewCur.value));
/* Легенда: видимые в виде слои сверху вниз (в порядке окна «Слои») с их знаком и до 12 классов. */
const legend = computed(() => {
  const v = cur.value; if (!v) return [];
  dataRev.value;
  const on = new Map(v.layers.filter(x => x.visible).map(x => [x.key, x]));
  return project.layers.filter(l => on.has(l.key) && (!l.group || v.groups.find(g => g.id === l.group)?.visible !== false)).map(l => {
    const st = fullStyle(clone(on.get(l.key).style));
    return { key: l.key, title: l.title, sw: swatchOf({ ...l, style: st }), items: legendItems(st, project.data[l.key]?.fc).filter(it => !it.off).slice(0, 12) };
  });
});
</script>

<style>
.views .bar { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin-bottom: var(--wa-space-s); }
.views .bar wa-input { flex: 1 1 180px; min-width: 0; margin: 0 !important; }
.views .bar wa-checkbox { margin: 0 !important; }
.views table.vl { width: 100%; border-collapse: collapse; font-size: var(--wa-font-size-s); table-layout: fixed; }
.views table.vl td { padding: 2px 4px; border-bottom: 1px solid var(--g-line); }
.views table.vl tr.cur td { background: var(--wa-color-brand-fill-quiet); }
.views td.nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
.views td.nm:hover { color: var(--wa-color-brand-on-quiet); }
.views td.nm svg { vertical-align: -2px; color: var(--g-muted); }
.views .n { color: var(--g-muted); font-size: var(--wa-font-size-xs); }
.views td.act { width: 96px; white-space: nowrap; text-align: right; }
.views td.act wa-button::part(base) { padding-inline: 5px; }
.views .sect { margin: var(--wa-space-m) 0 4px; font-weight: 600; font-size: var(--wa-font-size-s); }
.views .lg { margin-bottom: 6px; font-size: var(--wa-font-size-s); }
.views .lgh { display: flex; gap: 6px; align-items: center; }
.views .lgi { display: flex; gap: 6px; align-items: center; padding-left: 22px; color: var(--g-muted); font-size: var(--wa-font-size-xs); }
.views .sw { width: 16px; height: 10px; flex: none; box-sizing: border-box; }
.views .sw.line { border-bottom: 2.5px solid var(--c); height: 6px; }
.views .sw.poly { background: color-mix(in srgb, var(--c) 45%, transparent); border: 1px solid var(--e); }
.views .sw.poly.hatch { background: repeating-linear-gradient(135deg, var(--c) 0 1px, transparent 1px 4px); }
.views .sw.point { width: 10px; margin: 0 3px; border-radius: 50%; background: var(--c); border: 1px solid var(--e); }
</style>
