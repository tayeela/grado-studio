<!-- ГРАДО · командная строка (шаг И1): любая команда программы по имени или псевдониму AutoCAD, Tab — дополнить,
     стрелки — прежние строки, Enter на пустой — повтор последней, Esc — очистить. Над строкой — журнал ответов. -->
<template>
  <section class="g3-cmd" aria-label="Командная строка">
    <div ref="logEl" class="g3-log" aria-live="polite">
      <div v-for="(e, i) in cmd.journal.slice(-30)" :key="i" :class="{ bad: !e.ok }">{{ e.text }}</div>
    </div>
    <div class="g3-line">
      <label for="g3-cmd-input">Команда:</label>
      <input id="g3-cmd-input" ref="inp" v-model="text" autocomplete="off" spellcheck="false"
             placeholder="например: открыть Мой проект · скрыть ogd.123 · граница user:territory · команды"
             @keydown="onKey" @blur="hide" />
      <div v-if="hints.length" class="g3-hints" role="listbox">
        <div v-for="(h, i) in hints" :key="h.id" role="option" :aria-selected="i === sel" @mousedown.prevent="pick(h.id)">
          {{ h.id }}<small>{{ [h.args, h.aliases?.join(", ")].filter(Boolean).join(" · ") }}</small>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { useCommands } from "./stores/commands";

const cmd = useCommands();
const text = ref(""), sel = ref(0), open = ref(false);
const inp = ref<HTMLInputElement | null>(null), logEl = ref<HTMLElement | null>(null);
const history: string[] = [];
let hpos = -1;

const hints = computed(() => {
  const w = text.value.trimStart();
  if (!open.value || !w || w.includes(" ")) return [];
  return cmd.bus.complete(w).slice(0, 8);
});
watch(text, () => { open.value = true; sel.value = 0; });
watch(() => cmd.journal.length, () => nextTick(() => { if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight; }));

const hide = () => { open.value = false; };
function pick(id: string) { text.value = id + " "; nextTick(() => { open.value = false; inp.value?.focus(); }); }

async function onKey(e: KeyboardEvent) {
  if (e.key === "Tab" && hints.value.length) { e.preventDefault(); pick(hints.value[sel.value].id); return; }
  if (e.key === "ArrowDown" && hints.value.length) { e.preventDefault(); sel.value = (sel.value + 1) % hints.value.length; return; }
  if (e.key === "ArrowUp" && hints.value.length) { e.preventDefault(); sel.value = (sel.value + hints.value.length - 1) % hints.value.length; return; }
  if (e.key === "ArrowUp" && history.length) { e.preventDefault(); hpos = Math.min(history.length - 1, hpos + 1); text.value = history[history.length - 1 - hpos]; open.value = false; return; }
  if (e.key === "ArrowDown" && hpos >= 0) { e.preventDefault(); hpos--; text.value = hpos >= 0 ? history[history.length - 1 - hpos] : ""; open.value = false; return; }
  if (e.key === "Escape") { text.value = ""; open.value = false; return; }
  if (e.key === "Enter") {
    e.preventDefault();
    const line = text.value;
    if (line.trim()) history.push(line);
    hpos = -1; text.value = ""; open.value = false;
    await cmd.run(line);
  }
}
</script>
