<!-- ГРАДО 2 · окно «Слои» нового интерфейса: слои проекта по группам в порядке файла (сверху вниз — как на карте),
     глаз слоя и группы, свёртка группы, текущий слой, поиск; новый слой и новая группа, «Упорядочить слои» (data.js), перетаскивание слоёв и групп
     (SortableJS), переименование двойным щелчком, меню слоя и группы (кнопка «⋯» или правая кнопка мыши), как в
     рабочей странице (web/layers.js layerMenu, groupMenu). Правки — функциями edit.js, в файл пишет project.js. -->
<template>
  <div class="pane layers">
    <div class="tools">
      <wa-input size="s" placeholder="Найти слой" with-clear :value="q" @input="e => (q = e.target.value)" class="grow"></wa-input>
      <wa-button size="s" appearance="plain" title="Новый слой" @click="openNew"><Plus :size="16" /></wa-button>
      <wa-button size="s" appearance="plain" title="Новая группа из текущего слоя" :disabled="!currentId" @click="groupCurrent"><FolderPlus :size="16" /></wa-button>
      <wa-button size="s" appearance="plain" :disabled="!project.layers.length" title="Упорядочить слои как в опорном плане (ничего не удаляется)"
                 @click="tidyLayers"><ListOrdered :size="16" /></wa-button>
    </div>
    <p v-if="!project.layers.length" class="hint">{{ loadError || "В проекте пока нет слоёв: «+» — новый слой" }}</p>

    <div ref="list" class="blocks">
      <template v-for="b in blocks" :key="b.id">
        <div v-if="b.group" class="blk" :data-g="b.group.id">
          <div class="grp" :class="{ off: !b.group.visible }" @contextmenu.prevent="e => menuAt(e, 'g', b.group.id)">
            <button class="tw" :title="b.group.open ? 'Свернуть группу' : 'Развернуть группу'" @click="b.group.open = !b.group.open">
              <ChevronDown v-if="b.group.open || q" :size="14" /><ChevronRight v-else :size="14" />
            </button>
            <button class="eye" :title="b.group.visible ? 'Скрыть группу' : 'Показать группу'" @click="b.group.visible = !b.group.visible">
              <Eye v-if="b.group.visible" :size="15" /><EyeOff v-else :size="15" />
            </button>
            <input v-if="editing === 'g:' + b.group.id" class="ren" :value="b.group.title" @keydown.enter="e => e.target.blur()"
                   @keydown.esc="editing = ''" @blur="e => finishRename('g', b.group.id, e.target.value)" v-focus>
            <span v-else class="gname" :title="b.group.title" @dblclick="editing = 'g:' + b.group.id">{{ b.group.title }}</span>
            <span class="cnt" :title="'Слоёв в группе: ' + b.layers.length">{{ b.layers.length }}</span>
            <button class="more" title="Действия с группой" @click="e => menuAt(e, 'g', b.group.id)"><Ellipsis :size="15" /></button>
          </div>
          <div class="inner" :data-g="b.group.id">
            <div v-for="l in b.layers" v-show="b.group.open || q" :key="l.key" class="row nested" :class="{ cur: l.key === currentId, hid: !b.group.visible }" :data-key="l.key"
                 @click="currentId = l.key" @contextmenu.prevent="e => menuAt(e, 'l', l.key)">
              <LayerRow :l="l" />
            </div>
          </div>
        </div>
        <div v-else class="row" :class="{ cur: b.layers[0].key === currentId }" :data-key="b.layers[0].key"
             @click="currentId = b.layers[0].key" @contextmenu.prevent="e => menuAt(e, 'l', b.layers[0].key)">
          <LayerRow :l="b.layers[0]" />
        </div>
      </template>
    </div>

    <wa-dropdown ref="menu" class="ctx" @wa-select="onMenu" @wa-after-hide="menuFor = null">
      <button slot="trigger" class="anchor" :style="{ left: menuXY[0] + 'px', top: menuXY[1] + 'px' }" tabindex="-1" aria-hidden="true"></button>
      <template v-if="menuFor?.kind === 'l'">
        <wa-dropdown-item value="zoom">Приблизить к слою</wa-dropdown-item>
        <wa-divider></wa-divider>
        <wa-dropdown-item value="copystyle">Копировать стиль</wa-dropdown-item>
        <wa-dropdown-item v-if="styleClip && styleClip !== lyr(menuFor.id)?.title" value="pastestyle">Вставить стиль «{{ styleClip }}»</wa-dropdown-item>
        <wa-divider></wa-divider>
        <wa-dropdown-item value="rename">Переименовать</wa-dropdown-item>
        <wa-dropdown-item value="up">Выше</wa-dropdown-item>
        <wa-dropdown-item value="down">Ниже</wa-dropdown-item>
        <wa-dropdown-item v-if="lyr(menuFor.id)?.group" value="nogroup">Убрать из группы</wa-dropdown-item>
        <wa-dropdown-item v-for="g in project.groups.filter(g => g.id !== lyr(menuFor.id)?.group)" :key="g.id" :value="'to:' + g.id">В группу «{{ g.title }}»</wa-dropdown-item>
        <wa-dropdown-item value="newgroup">В новую группу</wa-dropdown-item>
        <wa-divider></wa-divider>
        <wa-dropdown-item v-if="canRevert(menuFor.id)" value="revert">Вернуть исходную выгрузку</wa-dropdown-item>
        <wa-dropdown-item value="delete" variant="danger">Удалить слой из проекта</wa-dropdown-item>
      </template>
      <template v-else-if="menuFor?.kind === 'g'">
        <wa-dropdown-item value="zoom">Приблизить к группе</wa-dropdown-item>
        <wa-dropdown-item value="rename">Переименовать</wa-dropdown-item>
        <wa-dropdown-item value="ungroup">Разгруппировать</wa-dropdown-item>
        <wa-divider></wa-divider>
        <wa-dropdown-item value="delete" variant="danger">Удалить группу вместе со слоями</wa-dropdown-item>
      </template>
    </wa-dropdown>

    <wa-dialog label="Новый слой" :open="newDlg" @wa-after-hide="newDlg = false" class="new-dlg">
      <wa-input ref="newName" size="s" label="Название" :value="newTitle" @input="e => (newTitle = e.target.value)" @keydown.enter="createNew"></wa-input>
      <wa-radio-group size="s" label="Объекты слоя" orientation="horizontal" :value="newGeom" @change="e => (newGeom = e.target.value)">
        <wa-radio appearance="button" value="poly">Полигоны</wa-radio>
        <wa-radio appearance="button" value="line">Линии</wa-radio>
        <wa-radio appearance="button" value="point">Точки</wa-radio>
      </wa-radio-group>
      <wa-button slot="footer" size="s" appearance="plain" @click="newDlg = false">Отмена</wa-button>
      <wa-button slot="footer" size="s" variant="brand" @click="createNew">Создать</wa-button>
    </wa-dialog>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import Sortable from "sortablejs";
import { ChevronDown, ChevronRight, Ellipsis, Eye, EyeOff, FolderPlus, ListOrdered, Plus } from "@lucide/vue";
import { tidyLayers } from "../data.js";
import { currentId, project, shown } from "../store.js";
import LayerSwatch from "./LayerSwatch.vue";
import { loadError, notice } from "../project.js";
import {
  canRevert, copyStyle, groupKeys, grp, lyr, mapApi, moveLayer, newGroup, newLayer, pasteStyle, removeGroup, removeLayers,
  renameLayer, reorder, revertLayer, setGroup, styleClip, ungroup,
} from "../edit.js";

const q = ref("");
const editing = ref("");               // «l:ключ» или «g:id» — строка в режиме переименования
const vFocus = { mounted: el => { el.focus(); el.select(); } };

/* Строка слоя: глаз, образец, название (двойной щелчок — переименовать), кнопка меню. */
const LayerRow = defineComponent({
  props: { l: Object },
  setup(props) {
    return () => {
      const l = props.l, ed = editing.value === "l:" + l.key;
      const byGroup = l.visible && !shown(l);       // слой включён, но скрыт вместе с группой
      return [
        h("button", { class: "eye", title: byGroup ? "Слой не виден на карте: скрыта его группа" : l.visible ? "Скрыть слой" : "Показать слой", onClick: e => { e.stopPropagation(); l.visible = !l.visible; } },
          [h(l.visible ? Eye : EyeOff, { size: 15 })]),
        h(LayerSwatch, { l, class: "sw" }),
        ed ? h("input", { class: "ren", value: l.title, onVnodeMounted: v => { v.el.focus(); v.el.select(); }, onClick: e => e.stopPropagation(),
          onKeydown: e => { if (e.key === "Enter") e.target.blur(); if (e.key === "Escape") editing.value = ""; },
          onBlur: e => finishRename("l", l.key, e.target.value) })
          : h("span", { class: "name" + (shown(l) ? "" : " off"), title: l.title || l.key, onDblclick: () => { editing.value = "l:" + l.key; } }, l.title || l.key),
        h("button", { class: "more", title: "Действия со слоем", onClick: e => { e.stopPropagation(); menuAt(e, "l", l.key); } }, [h(Ellipsis, { size: 15 })]),
      ];
    };
  },
});

/* Блоки списка в порядке слоёв файла: группа встаёт там, где её первый слой; слой без группы — отдельной строкой. */
const blocks = computed(() => {
  const s = q.value.trim().toLowerCase(), out = [], byGroup = {};
  for (const l of project.layers) {
    if (s && !(l.title || l.key).toLowerCase().includes(s)) continue;
    const g = l.group && project.groups.find(x => x.id === l.group);
    if (!g) { out.push({ id: "l:" + l.key, group: null, layers: [l] }); continue; }
    if (!byGroup[g.id]) out.push(byGroup[g.id] = { id: "g:" + g.id, group: g, layers: [] });
    byGroup[g.id].layers.push(l);
  }
  return out;
});

function finishRename(kind, id, v) {
  if (editing.value !== kind + ":" + id) return;
  editing.value = "";
  if (!v.trim()) return;
  if (kind === "l") renameLayer(id, v); else { const g = grp(id); if (g) g.title = v.trim(); }
}

/* ---------- перетаскивание: верхний уровень — группы и слои без группы, внутри группы — её слои ---------- */
const list = ref(null);
let sorts = [];
function readOrder() {
  const out = [];
  for (const el of list.value.children) {
    if (el.dataset.g) el.querySelectorAll(".inner > .row").forEach(r => out.push({ key: r.dataset.key, group: el.dataset.g }));
    else if (el.dataset.key) out.push({ key: el.dataset.key, group: null });
  }
  return out;
}
let home = null;                                   // где строка стояла до перетаскивания (вместе с узлами-метками Vue)
let pt = null;                                     // последняя точка указателя во время перетаскивания
const track = e => { pt = [e.clientX, e.clientY]; };
function onStart(e) { home = [e.from, e.item.nextSibling]; pt = null; document.addEventListener("dragover", track, true); }
/* Строку слоя бросили на строку другой группы (или на слой без группы), а SortableJS оставил её в прежнем списке
   (середина чужой строки у него «мёртвая», а по пути строку сносит в корень над заголовком группы) — ставим её
   выше или ниже той строки, на которую бросили: слой попадает в группу этой строки. */
function dropOnRow(item) {
  if (!pt || !item.classList.contains("row")) return;
  const at = document.elementFromPoint(pt[0], pt[1])?.closest(".layers .row");
  if (!at || at === item || at.parentNode === item.parentNode || !list.value.contains(at)) return;
  const r = at.getBoundingClientRect();
  at.parentNode.insertBefore(item, pt[1] > r.top + r.height / 2 ? at.nextSibling : at);
}
function onEnd(e) {
  document.removeEventListener("dragover", track, true);
  dropOnRow(e.item);
  const order = readOrder();
  home[0].insertBefore(e.item, home[1]);           // вернуть DOM как было: порядок строк рисует Vue из данных
  reorder(order);
}
function mountSort() {
  sorts.forEach(s => s.destroy()); sorts = [];
  if (!list.value || q.value) return;               // при поиске порядок не меняется
  const opt = { group: "layers", animation: 120, onStart, onEnd, filter: "input, .ren", preventOnFilter: false, ghostClass: "ghost", fallbackOnBody: true, swapThreshold: 0.6 };
  sorts.push(Sortable.create(list.value, { ...opt, draggable: ".blk, .blocks > .row" }));
  list.value.querySelectorAll(".inner").forEach(el => sorts.push(Sortable.create(el, {
    ...opt, draggable: ".row", group: { name: "layers", put: (to, from, item) => !item.classList.contains("blk") },
  })));
}
onMounted(mountSort);
watch(blocks, () => nextTick(mountSort));
onBeforeUnmount(() => sorts.forEach(s => s.destroy()));

/* ---------- меню слоя и группы ---------- */
const menu = ref(null), menuFor = ref(null), menuXY = ref([0, 0]);
async function menuAt(e, kind, id) {
  const r = list.value.closest(".layers").getBoundingClientRect();
  menuXY.value = [e.clientX - r.left, e.clientY - r.top];
  menuFor.value = { kind, id };
  await nextTick(); menu.value.open = true;
}
function onMenu(e) {
  const v = e.detail.item.value, { kind, id } = menuFor.value;
  if (kind === "l") {
    const l = lyr(id);
    if (v === "zoom") mapApi.zoomTo([id]);
    else if (v === "copystyle") { copyStyle(id); notice.value = `Стиль «${l.title}» скопирован`; }
    else if (v === "pastestyle") { const sameGeom = pasteStyle(id); notice.value = sameGeom ? "Стиль вставлен" : "Стиль вставлен из слоя другого вида объектов: проверьте оформление"; }
    else if (v === "rename") editing.value = "l:" + id;
    else if (v === "up") moveLayer(id, -1);
    else if (v === "down") moveLayer(id, 1);
    else if (v === "nogroup") setGroup(id, null);
    else if (v.startsWith("to:")) setGroup(id, v.slice(3));
    else if (v === "newgroup") editing.value = "g:" + newGroup([id]);
    else if (v === "revert") { revertLayer(id); notice.value = `«${l.title}»: исходная выгрузка возвращена. Ctrl+Z — отменить`; }
    else if (v === "delete") { removeLayers([id]); notice.value = `Слой «${l.title}» удалён. Ctrl+Z — вернуть`; }
  } else {
    const g = grp(id);
    if (v === "zoom") mapApi.zoomTo(groupKeys(id));
    else if (v === "rename") editing.value = "g:" + id;
    else if (v === "ungroup") ungroup(id);
    else if (v === "delete") { const n = groupKeys(id).length; removeGroup(id); notice.value = `Группа «${g.title}» удалена вместе со слоями: ${n}. Ctrl+Z — вернуть`; }
  }
}

/* ---------- новый слой и новая группа ---------- */
const newDlg = ref(false), newTitle = ref(""), newGeom = ref("poly"), newName = ref(null);
async function openNew() { newTitle.value = ""; newDlg.value = true; await nextTick(); setTimeout(() => newName.value?.focus(), 50); }
function createNew() { newLayer(newTitle.value.trim() || "Новый слой", newGeom.value); newDlg.value = false; }
function groupCurrent() { if (currentId.value) editing.value = "g:" + newGroup([currentId.value]); }
</script>

<style>
.layers { position: relative; }
.layers .tools { display: flex; gap: 2px; align-items: center; margin-bottom: var(--wa-space-xs); }
.layers .tools wa-input { margin-bottom: 0; flex: 1; min-width: 0; }
.layers .row, .layers .grp { display: flex; align-items: center; gap: 6px; padding: 3px 4px; border-radius: var(--wa-border-radius-s); cursor: default; }
.layers .row.nested { padding-left: 24px; }
.layers .row:hover, .layers .grp:hover { background: var(--wa-color-neutral-fill-quiet); }
.layers .row.cur { background: var(--wa-color-brand-fill-quiet); color: var(--wa-color-brand-on-quiet); }
.layers .grp { margin-top: var(--wa-space-xs); font-weight: 600; }
.layers .grp .cnt { margin-left: auto; color: var(--g-muted); font-weight: 400; font-size: var(--wa-font-size-xs); }
.layers .grp.off .gname { color: var(--g-muted); }
.layers .eye, .layers .tw, .layers .more { all: unset; display: inline-flex; color: var(--g-muted); cursor: pointer; padding: 3px; margin: -2px; border-radius: 4px; }   /* значок 16 px, цель для мыши 22 px */
/* «⋯» прозрачна, а не скрыта: так до неё доходит Tab, и при фокусе она видна */
.layers .more { opacity: 0; margin-left: auto; }
.layers .grp .more { margin-left: 0; }
.layers .row:hover .more, .layers .grp:hover .more, .layers .row.cur .more, .layers .row:focus-within .more, .layers .grp:focus-within .more { opacity: 1; }
.layers .eye:focus-visible, .layers .tw:focus-visible, .layers .more:focus-visible { outline: 2px solid var(--wa-color-focus); opacity: 1; }
.layers .row.hid .eye { opacity: .4; }
.layers .row.hid .sw { filter: opacity(.4); }   /* opacity самого образца — прозрачность слоя */   /* группа скрыта — слои в ней приглушены */
.layers .name, .layers .gname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.layers .name.off { color: var(--g-muted); }
.layers .ren { flex: 1; min-width: 0; font: inherit; padding: 1px 4px; border: 1px solid var(--wa-color-brand-fill-loud); border-radius: 3px; background: var(--wa-color-surface-default); color: inherit; }
.layers .ghost { opacity: .4; background: var(--wa-color-brand-fill-quiet); }
.layers .inner:empty { min-height: 4px; }
.layers .ctx { position: absolute; left: 0; top: 0; }
.layers .ctx .anchor { position: absolute; width: 1px; height: 1px; padding: 0; border: 0; opacity: 0; pointer-events: none; }
.new-dlg wa-input { margin-bottom: var(--wa-space-m); }
</style>
