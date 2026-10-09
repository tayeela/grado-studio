<!-- ГРАДО 2 · панель «Элементы» редактора раскладки (как «Элементы» в макете QGIS): все элементы листа сверху вниз
     в порядке рисования (верхний — первый), глаз — показать или скрыть, замок — закрепить; щелчок выбирает
     (Shift или Ctrl — добавить к выбору), двойной щелчок — переименовать. Действия выполняет SheetEditor.vue. -->
<script setup>
import { ref, nextTick } from "vue";
import { Eye, EyeOff, Lock, LockOpen, Map, List, Type, Image, Compass, Ruler, Table, Square, Circle, MoveRight } from "@lucide/vue";
import { label } from "./model.js";

const props = defineProps({ blocks: Array, sel: Array });
const emit = defineEmits(["pick", "patch"]);
const ICON = { map: Map, legend: List, text: Type, picture: Image, north: Compass, scalebar: Ruler, table: Table, rect: Square, ellipse: Circle, line: MoveRight };
const editing = ref(null);
const rows = () => [...props.blocks].reverse();
function rename(b) { editing.value = b.id; nextTick(() => document.getElementById("ip-" + b.id)?.select()); }
function done(b, e) { const v = e.target.value.trim(); editing.value = null; if (v !== label(b, props.blocks)) emit("patch", b.id, { name: v || undefined }); }
</script>

<template>
  <div class="ip">
    <div v-if="!blocks.length" class="ip-empty">На листе нет элементов. Добавьте их кнопками ленты.</div>
    <div v-for="b in rows()" :key="b.id" class="ip-r" :class="{ on: sel.includes(b.id), dim: b.hidden }"
      @click="emit('pick', b.id, $event.shiftKey || $event.ctrlKey || $event.metaKey)" @dblclick="rename(b)">
      <button class="ip-i" :title="b.hidden ? 'Показать' : 'Скрыть'" :aria-label="b.hidden ? 'Показать' : 'Скрыть'" @click.stop="emit('patch', b.id, { hidden: !b.hidden })">
        <component :is="b.hidden ? EyeOff : Eye" :size="15" :stroke-width="1.6" /></button>
      <button class="ip-i" :class="{ lit: b.locked }" :title="b.locked ? 'Открепить' : 'Закрепить'" :aria-label="b.locked ? 'Открепить' : 'Закрепить'" @click.stop="emit('patch', b.id, { locked: !b.locked })">
        <component :is="b.locked ? Lock : LockOpen" :size="14" :stroke-width="1.6" /></button>
      <component :is="ICON[b.kind]" :size="15" :stroke-width="1.6" class="ip-k" />
      <input v-if="editing === b.id" :id="'ip-' + b.id" class="ip-n" :value="label(b, blocks)" @blur="done(b, $event)" @keydown.enter="$event.target.blur()" @keydown.esc="editing = null" @click.stop>
      <span v-else class="ip-t">{{ label(b, blocks) }}</span>
    </div>
  </div>
</template>

<style scoped>
.ip { padding: 4px 6px; }
.ip-empty { color: var(--g-mute); padding: 6px; line-height: 1.4; }
.ip-r { display: flex; align-items: center; gap: 4px; height: 26px; padding: 0 4px; border-radius: 4px; cursor: default; user-select: none; }
.ip-r:hover { background: var(--g-hover); }
.ip-r.on { background: var(--g-sel); color: var(--g-accent); }
.ip-r.dim .ip-t, .ip-r.dim .ip-k { opacity: .45; }
.ip-i { width: 22px; height: 22px; display: grid; place-items: center; border: 0; background: none; color: var(--g-mute); border-radius: 4px; cursor: pointer; padding: 0; }
.ip-i:hover { background: var(--g-hover); color: var(--g-ink); }
.ip-i.lit { color: var(--g-accent); }
.ip-k { color: var(--g-mute); flex: none; margin: 0 2px; }
.ip-t { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ip-n { flex: 1; min-width: 0; font: inherit; padding: 1px 4px; border: 1px solid var(--g-accent); border-radius: 3px; }
</style>
