<!-- ГРАДО 2 · выбор шрифта подписей: готовые в списке сразу, «Другой шрифт…» — окно с поиском по шрифтам компьютера и
     кнопкой «Добавить файл шрифта» (TTF, OTF, TTC). Значение — то, что понимает печать: готовые — свои имена (pt-sans, ui-bold…),
     любой другой — «f:<id>» или «f:<id>-bold» (apps/grado2/fonts.py). Имя выбранного шрифта приходит наружу вторым аргументом
     change — его хранят рядом, чтобы показать, даже если на другом компьютере такого шрифта нет (печать тогда — PT Sans). -->
<template>
  <div class="fpick" @wa-show.stop @wa-hide.stop @wa-after-show.stop @wa-after-hide.stop>
  <wa-select size="s" :label="label" :value="selValue" :disabled="disabled" data-font-pick @change="pick($event)">
    <wa-option v-for="p in presets" :key="p[0]" :value="p[0]">{{ p[1] }}</wa-option>
    <wa-option v-if="custom" :value="value">{{ customName }}</wa-option>
    <wa-divider></wa-divider>
    <wa-option value="@other">Другой шрифт…</wa-option>
  </wa-select>
  <wa-dialog label="Шрифт подписей" :open="open" class="fontdlg" @wa-after-hide="open = false" @wa-after-show="focusSearch">
    <wa-input ref="search" size="s" placeholder="Найти шрифт" :value="q" with-clear aria-label="Найти шрифт" @input="q = $event.target.value"></wa-input>
    <p v-if="fonts.err" class="fd-err">Список шрифтов не получен: {{ fonts.err }}</p>
    <p v-else-if="fonts.busy && !fonts.list.length" class="fd-hint"><wa-spinner></wa-spinner> Читаю шрифты компьютера — в первый раз это до минуты.</p>
    <ul v-else class="fd-list" role="listbox" aria-label="Шрифты с русскими буквами">
      <template v-for="f in shown" :key="f.id">
        <li role="option" :aria-selected="value === f.id" :class="{ on: value === f.id }" :style="{ fontFamily: css(f.name) }" @click="choose(f.id, f.name)">
          {{ f.name }}<small v-if="f.user"> свой файл</small></li>
        <li v-if="withBold && f.bold" role="option" :aria-selected="value === f.id + '-bold'" :class="{ on: value === f.id + '-bold' }"
            :style="{ fontFamily: css(f.name), fontWeight: 700 }" @click="choose(f.id + '-bold', f.name + ' полужирный')">{{ f.name }} полужирный</li>
      </template>
      <li v-if="fonts.loaded && !shown.length" class="fd-none">Ничего не нашлось{{ q ? ` по «${q}»` : "" }}.</li>
    </ul>
    <p class="fd-hint">Только шрифты с русскими буквами. Шрифт попадёт в PDF и PPTX целиком, файл с собой носить не нужно.
      Если на другом компьютере такого шрифта нет, лист там напечатается PT Sans.</p>
    <p v-if="upErr" class="fd-err">{{ upErr }}</p>
    <input ref="file" type="file" accept=".ttf,.otf,.ttc,.otc" hidden @change="upload" />
    <wa-button slot="footer" size="s" appearance="outlined" :loading="fonts.busy" @click="file.click()">Добавить файл шрифта…</wa-button>
    <wa-button slot="footer" size="s" appearance="plain" :disabled="fonts.busy" title="Перечитать папки шрифтов: новый шрифт поставлен, пока программа открыта" @click="loadFonts(true)">Обновить список</wa-button>
    <wa-button slot="footer" size="s" appearance="plain" @click="open = false">Закрыть</wa-button>
  </wa-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from "vue";
import { addFontFile, fontName, fonts, loadFonts } from "../fonts.js";

/* presets — [[значение, подпись]] (первым может идти «Как сейчас»); name — сохранённое имя выбранного «f:…» шрифта */
const props = defineProps({ value: { type: String, default: "" }, presets: { type: Array, required: true }, label: String,
  name: String, disabled: Boolean, withBold: Boolean });
const emit = defineEmits(["change"]);
const open = ref(false), q = ref(""), upErr = ref(""), search = ref(null), file = ref(null);
const custom = computed(() => props.value.startsWith("f:"));
const customName = computed(() => { const n = fontName(props.value); return n ? n + (props.value.endsWith("-bold") ? " полужирный" : "") : props.name || "шрифт не найден"; });
const selValue = computed(() => props.value || props.presets[0]?.[0] || "");
const shown = computed(() => { const s = q.value.trim().toLowerCase(); return fonts.list.filter(f => !s || f.name.toLowerCase().includes(s)); });
const css = n => `"${n.replace(/["\\]/g, "")}", var(--wa-font-family-body)`;

function pick(e) {
  const v = e.target.value;
  if (v === "@other") { e.target.value = selValue.value; open.value = true; loadFonts(); return; }   // в списке остаётся прежний шрифт
  emit("change", v, "");
}
function choose(id, name) { emit("change", id, name); open.value = false; }
function focusSearch() { nextTick(() => search.value?.focus?.()); }
async function upload(e) {
  const f = e.target.files?.[0]; e.target.value = ""; if (!f) return;
  upErr.value = "";
  try { const ids = await addFontFile(f); if (ids[0]) choose(ids[0], fontName(ids[0])); } catch (err) { upErr.value = "Шрифт не добавлен: " + (err.message || err); }
}
</script>

<style>
.fontdlg { --width: 440px; }
.fontdlg wa-input { margin-bottom: 8px; }
.fontdlg .fd-list { list-style: none; margin: 0; padding: 4px; max-height: 340px; overflow-y: auto; border: 1px solid var(--g-line); border-radius: 8px; }
.fontdlg .fd-list li { padding: 6px 8px; border-radius: 6px; cursor: pointer; font-size: 15px; line-height: 1.3; }
.fontdlg .fd-list li:hover { background: var(--g-hover, rgba(36, 70, 216, .06)); }
.fontdlg .fd-list li.on { background: var(--g-accent-soft, rgba(36, 70, 216, .12)); }
.fontdlg .fd-list li small { font-family: var(--wa-font-family-body); color: var(--g-muted); font-size: var(--wa-font-size-xs); margin-left: 6px; }
.fontdlg .fd-list .fd-none { cursor: default; color: var(--g-muted); font-size: var(--wa-font-size-s); }
.fontdlg .fd-hint { margin: 8px 0 0; color: var(--g-muted); font-size: var(--wa-font-size-xs); line-height: 1.4; display: flex; gap: 6px; align-items: center; }
.fontdlg .fd-err { margin: 8px 0 0; color: var(--wa-color-danger-on-quiet, #b42318); font-size: var(--wa-font-size-s); }
</style>
