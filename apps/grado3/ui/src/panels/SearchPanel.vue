<!-- ГРАДО · окно «Поиск» рабочего места «Территория» (план 09.11.2026, шаг И2): поиск по адресу (OSM), кадастровому
     номеру участка (НСПД) или номеру КРТ (ГИС ОГД) через /api/search; участок под найденным адресом — границей
     территории (/api/search/parcel_at); «Показать на карте» (в слой ЕГРН без повторов) и «Сделать границей территории».
     Чужую границу молча не заменяем: первый щелчок спрашивает подтверждения на 5 с, второй — заменяет. Все изменения
     проекта идут через шину команд и отменяются Ctrl+Z. Площади в га в МСК считает ядро Rust (core.ts). -->
<template>
  <div class="g3-panel g3-search" role="search">
    <div class="terr-box" :class="{ ok: !!project.territory }">
      <template v-if="project.territory">
        <div class="terr-head">
          <wa-badge variant="brand" appearance="filled">Граница территории</wa-badge>
          <b>{{ fmtHa(project.territoryAreaM2) }}</b>
        </div>
        <div class="terr-name" :title="project.territory.key">{{ project.territory.title || project.territory.key }}</div>
        <div class="terr-acts">
          <wa-button size="small" appearance="plain" @click="cmd.run('показать-всё ' + project.territory.key)">Показать на карте</wa-button>
          <wa-button size="small" appearance="plain" @click="cmd.run('граница нет')">Снять роль</wa-button>
        </div>
      </template>
      <template v-else>
        <div class="terr-empty">Граница территории ещё не выбрана. Найдите адрес, участок или КРТ ниже, отметьте слой в «Слоях» либо поставьте учебный контур.</div>
        <div class="terr-acts">
          <wa-button size="small" appearance="outlined" :disabled="!project.doc" @click="cmd.run('граница-пример')">Граница-пример</wa-button>
        </div>
      </template>
    </div>

    <form class="s-form" @submit.prevent="runSearch">
      <input ref="inp" v-model="q" class="s-inp" type="text" placeholder="Адрес, кадастровый номер или № КРТ"
             aria-label="Поиск по адресу, кадастровому номеру или номеру КРТ" autocomplete="off" spellcheck="false"
             @input="onInput" @keydown="onKey" />
      <wa-button size="small" appearance="filled" type="submit" :loading="busy" :disabled="busy || !q.trim()">Найти</wa-button>
    </form>

    <p v-if="err" class="s-msg bad" role="status">{{ err }}</p>
    <p v-else-if="busy" class="s-msg" role="status">Ищу…</p>

    <div v-if="S && !busy" class="s-res" role="listbox">
      <template v-if="S.type === 'address'">
        <button v-for="(x, i) in S.addresses" :key="i" type="button" class="s-item" :class="{ act: i === S.picked }"
                role="option" :aria-selected="i === S.picked" @click="pickAddress(i)">
          <b>{{ addrOf(x)[0] }}</b>
          <span v-if="addrOf(x)[1]" class="g3-muted">{{ addrOf(x)[1] }}</span>
        </button>
        <div v-if="S.picked >= 0 && S.addresses[S.picked]" class="s-actions">
          <wa-button size="small" appearance="filled" :loading="busy" :disabled="!project.doc" @click="applyAddressBoundary">
            {{ ask ? "Заменить вашу границу участком?" : "Участок под адресом — границей территории" }}
          </wa-button>
        </div>
      </template>

      <template v-else-if="S.type === 'cadastral'">
        <button v-for="(f, i) in S.features" :key="i" type="button" class="s-item" :class="{ act: i === S.picked }"
                role="option" :aria-selected="i === S.picked" @click="pickFeature(i)">
          <b>{{ f.properties?.["Кадастровый номер"] || f.properties?._key || "Участок" }}</b>
          <span class="g3-muted">{{ fmtHa(areaMsk(f)) }}{{ f.properties?.["ВРИ"] ? " · " + f.properties["ВРИ"] : "" }}</span>
        </button>
        <div v-if="S.missing.length" class="s-msg bad">Не найдено: {{ S.missing.join(", ") }}</div>
        <div v-if="S.features.length" class="s-actions">
          <wa-button size="small" appearance="outlined" :disabled="!project.doc" @click="cmd.run('участки-на-карту')">Показать на карте</wa-button>
          <wa-button size="small" appearance="filled" :disabled="!project.doc" @click="applyFoundBoundary">
            {{ ask ? "Заменить вашу границу участками?" : "Сделать границей территории" }}
          </wa-button>
        </div>
      </template>

      <template v-else-if="S.type === 'krt'">
        <button v-for="(_f, i) in S.features" :key="i" type="button" class="s-item" :class="{ act: i === S.picked }"
                role="option" :aria-selected="i === S.picked" @click="pickFeature(i)">
          <b>{{ S.cards[i] || "Территория КРТ" }}</b>
        </button>
        <div v-if="S.missing.length" class="s-msg bad">Не найдено: {{ S.missing.join(", ") }}</div>
        <div v-if="S.features.length" class="s-actions">
          <wa-button size="small" appearance="outlined" @click="cmd.run('участки-на-карту')">Показать на карте</wa-button>
          <wa-button size="small" appearance="filled" :disabled="!project.doc" @click="applyFoundBoundary">
            {{ ask ? "Заменить вашу границу контуром КРТ?" : "Сделать границей территории" }}
          </wa-button>
        </div>
      </template>

      <div v-for="n in S.notes" :key="n" class="s-msg g3-muted">{{ n }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { areaMsk } from "../core";
import { useProject } from "../stores/project";
import { useUi, type AddressHit } from "../stores/ui";
import { useCommands } from "../stores/commands";

const project = useProject(), ui = useUi(), cmd = useCommands();
const q = ref(ui.search?.q || "");
const busy = ref(false);
const err = ref("");
const ask = ref(false);
const inp = ref<HTMLInputElement | null>(null);
let askTimer: ReturnType<typeof setTimeout> | null = null;

const S = computed(() => ui.search);

const fmtHa = (m2: number): string => {
  const ha = m2 / 1e4;
  return ha.toLocaleString("ru-RU", { minimumFractionDigits: ha < 1 ? 4 : 2, maximumFractionDigits: ha < 1 ? 4 : 2 }) + " га";
};

/** Адрес: заголовок и подпись под ним без повтора названия в начале полного адреса. */
function addrOf(x: AddressHit): [string, string] {
  const name = (x.name || "").trim(), full = (x.display || "").trim(), parts = full.split(/,\s*/);
  if (!name) return [parts.slice(0, 2).join(", "), parts.slice(2).join(", ")];
  if (/^\d/.test(name) && parts[0] === name && parts.length > 1) return [`${parts[1]}, ${name}`, parts.slice(2).join(", ")];
  if (parts[0] === name) return [name, parts.slice(1).filter(p => p !== name).join(", ")];
  return [name, full === name ? "" : full];
}

function clearAsk() {
  if (askTimer) { clearTimeout(askTimer); askTimer = null; }
  ask.value = false;
}

function needConfirm(): boolean {
  if (project.territory && !ask.value) {
    ask.value = true;
    askTimer = setTimeout(clearAsk, 5000);
    return true;
  }
  clearAsk();
  return false;
}

function onInput() {
  clearAsk();
  err.value = "";
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") {
    q.value = "";
    err.value = "";
    clearAsk();
    ui.map.api?.clearMark();
  }
}

async function runSearch() {
  const text = q.value.trim();
  if (!text || busy.value) return;
  clearAsk();
  err.value = "";
  busy.value = true;
  try {
    const res = await cmd.run(`найти ${text}`);
    if (!res.ok) err.value = res.text || "Ничего не найдено";
  } finally {
    busy.value = false;
  }
}

function pickAddress(i: number) {
  if (!ui.search) return;
  clearAsk();
  ui.search = { ...ui.search, picked: i };
  const x = ui.search.addresses[i];
  if (x) ui.map.api?.markAddress(x.lon, x.lat, x.bbox);
}

function pickFeature(i: number) {
  if (!ui.search) return;
  clearAsk();
  ui.search = { ...ui.search, picked: i };
  const f = ui.search.features[i];
  if (f) ui.map.api?.markFeatures([f]);
}

async function applyAddressBoundary() {
  const s = ui.search;
  const x = s?.type === "address" ? s.addresses[s.picked] : null;
  if (!x || busy.value) return;
  if (needConfirm()) return;
  busy.value = true;
  err.value = "";
  try {
    const title = addrOf(x)[0].replace(/"/g, "");
    await cmd.run(`адрес-граница ${x.lon} ${x.lat} "${title}"`);
  } finally {
    busy.value = false;
  }
}

async function applyFoundBoundary() {
  if (!ui.search?.features.length) return;
  if (needConfirm()) return;
  await cmd.run("граница-по-найденному");
}

function onFindKey(e: KeyboardEvent) {
  if (!(e.ctrlKey || e.metaKey) || e.shiftKey || e.altKey || e.code !== "KeyF") return;
  const t = e.target as HTMLElement | null;
  if (t && t !== inp.value && t.matches?.("input, textarea, select, [contenteditable]")) return;
  e.preventDefault();
  inp.value?.focus();
  inp.value?.select();
}

onMounted(() => window.addEventListener("keydown", onFindKey));
onBeforeUnmount(() => { clearAsk(); window.removeEventListener("keydown", onFindKey); });
</script>

<style scoped>
.g3-search { display: flex; flex-direction: column; gap: 10px; }
.terr-box { padding: 8px 10px; border: 1px solid var(--wa-color-neutral-border-quiet); border-radius: 8px; background: var(--wa-color-surface-lowered); display: grid; gap: 4px; }
.terr-box.ok { border-color: var(--wa-color-brand-border-normal); background: var(--wa-color-brand-fill-quiet); }
.terr-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.terr-name { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.terr-empty { font-size: 12px; color: var(--wa-color-text-quiet); }
.terr-acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 2px; }
.s-form { display: flex; gap: 6px; }
.s-inp { flex: 1; min-width: 0; padding: 6px 8px; border: 1px solid var(--wa-color-neutral-border-normal); border-radius: 6px; background: var(--wa-color-surface-default); color: inherit; font: inherit; }
.s-inp:focus { outline: 2px solid var(--wa-color-focus); outline-offset: -1px; }
.s-msg { margin: 0; font-size: 12px; }
.s-msg.bad { color: var(--wa-color-danger-on-quiet); }
.s-res { display: flex; flex-direction: column; gap: 2px; }
.s-item { display: grid; width: 100%; text-align: left; gap: 2px; padding: 6px 8px; border: 1px solid transparent; border-radius: 6px; background: none; color: inherit; font: inherit; cursor: pointer; }
.s-item:hover, .s-item.act { background: var(--wa-color-surface-lowered); border-color: var(--wa-color-neutral-border-quiet); }
.s-actions { display: flex; flex-wrap: wrap; gap: 6px; padding-top: 6px; border-top: 1px solid var(--wa-color-neutral-border-quiet); margin-top: 4px; }
</style>
