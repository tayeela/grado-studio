<!-- ГРАДО · окно «Каталог данных» (план 09.11.2026, шаг И3): слои с нашего сервера (ГИС ОГД, ЕГКО, НСПД, OSM,
     Яндекс, рельеф), готовые наборы, быстрый подсчёт объектов по области через Rust-хранилище (/api/ogd_all/scan),
     поиск и загрузка с автооформлением (Эталон ЛГР, ЗОУИТ, стили портала) через единую шину команд с отменой Ctrl+Z. -->
<template>
  <div class="g3-panel g3-cat">
    <p v-if="!project.doc" class="g3-muted">Откройте проект, чтобы загружать слои с сервера.</p>
    <template v-else>
      <div class="cat-bar">
        <input v-model="q" class="cat-inp" type="search" placeholder="Поиск слоя или папки…" aria-label="Поиск слоя в каталоге" />
        <wa-button size="small" variant="brand" :disabled="!sel.size || busy" @click="loadSelected">
          {{ busy ? "Загрузка…" : `Загрузить (${sel.size})` }}
        </wa-button>
      </div>

      <div class="cat-presets">
        <button v-for="p in PRESETS" :key="p.id" type="button" class="chip" :class="{ on: presetOn(p.keys) }"
                :title="p.hint" @click="togglePreset(p.keys)">
          {{ p.title }} · {{ presetAvail(p.keys).length }}
        </button>
      </div>

      <div class="cat-opts">
        <label class="chk">
          <input v-model="onlyHit" type="checkbox" />
          <span>ГИС ОГД — только с объектами</span>
        </label>
        <button type="button" class="link" :disabled="scanning" @click="scanArea">
          {{ scanning ? "Считаю…" : counts ? "Пересчитать" : "Проверить область" }}
        </button>
        <button v-if="sel.size" type="button" class="link" @click="sel = new Set()">Снять все</button>
      </div>

      <p v-if="status" class="cat-msg" :class="{ err: isErr }">{{ status }}</p>

      <div class="cat-tree">
        <details v-for="grp in groupedSources" :key="grp.id" :open="grp.id === 'gisogd' || grp.id === 'nspd' || !!q.trim()">
          <summary class="grp-sum">
            <span class="grp-nm">{{ grp.title }}</span>
            <span class="g3-muted">{{ grp.items.length }}</span>
          </summary>
          <div class="grp-body">
            <div v-for="it in grp.items" :key="it.key" class="ly-row">
              <label class="ly-lbl">
                <input type="checkbox" :checked="sel.has(it.key)" @change="toggleKey(it.key)" />
                <span class="ly-nm" :title="it.key">{{ it.title }}</span>
              </label>
              <span v-if="project.dataEntry(it.key)" class="badge has" title="Слой уже в проекте">
                {{ project.layerCount(it.key) }}
              </span>
              <button type="button" class="qload" :disabled="busy" title="Загрузить этот слой сразу" @click="loadOne(it.key)">↓</button>
            </div>
          </div>
        </details>

        <details v-if="filteredOgd.length || ogdLoading" :open="!!q.trim()">
          <summary class="grp-sum">
            <span class="grp-nm">ГИС ОГД — все слои портала</span>
            <span class="g3-muted">{{ ogdLoading ? "каталог…" : filteredOgd.length }}</span>
          </summary>
          <div class="grp-body">
            <div v-for="it in filteredOgd.slice(0, ogdLimit)" :key="it.key" class="ly-row">
              <label class="ly-lbl" :title="it.path || it.key">
                <input type="checkbox" :checked="sel.has(it.key)" @change="toggleKey(it.key)" />
                <span class="ly-nm"><b v-if="it.num">{{ it.num }}</b> {{ it.title }}</span>
              </label>
              <span v-if="ogdCount(it.code) !== undefined" class="badge" :class="{ has: (ogdCount(it.code) || 0) > 0 }">
                {{ ogdCount(it.code) === null ? "—" : ogdCount(it.code) }}
              </span>
              <button type="button" class="qload" :disabled="busy" title="Загрузить этот слой сразу" @click="loadOne(it.key)">↓</button>
            </div>
            <button v-if="filteredOgd.length > ogdLimit" type="button" class="link more" @click="ogdLimit += 120">
              Показать ещё ({{ filteredOgd.length - ogdLimit }})
            </button>
          </div>
        </details>

        <p v-if="!groupedSources.length && !filteredOgd.length && !ogdLoading" class="g3-muted">
          Ничего не найдено.
        </p>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { coverBbox } from "../commands/builtin";
import { useProject } from "../stores/project";
import { useUi } from "../stores/ui";
import { useCommands } from "../stores/commands";

interface SourceMeta {
  title: string;
  kind: string;
  code?: string;
}

interface OgdTreeNode {
  name: string;
  num?: string;
  code?: string;
  instead?: string;
  path?: string;
  children?: OgdTreeNode[];
}

interface FlatOgd {
  key: string;
  code: string;
  num: string;
  title: string;
  path: string;
}

const GROUP_ORDER: [string, string][] = [
  ["gisogd", "ГИС ОГД — подборки ГРАДО"],
  ["nspd", "ЕГРН · НСПД"],
  ["egko", "ЕГКО — картооснова ГИС ОГД"],
  ["osm", "OpenStreetMap"],
  ["yandex", "Яндекс Карты (для анализа)"],
  ["terrain", "Рельеф"],
];

const PRESETS = [
  {
    id: "limits", title: "Ограничения (ЗОУИТ)",
    hint: "ЗОУИТ, СЗЗ, водоохранные зоны, красные линии, ОКН",
    keys: ["gisogd.zouit", "gisogd.szz", "gisogd.vodookhr", "gisogd.red_lines", "gisogd.okn", "gisogd.airfield"],
  },
  {
    id: "exist", title: "Опорный план",
    hint: "Здания, вода, зелень, дороги, участки ЕГРН, районы",
    keys: ["egko.buildings", "egko.water", "egko.green", "osm.roads", "nspd.parcels", "gisogd.admin"],
  },
  {
    id: "docs", title: "Граддокументация",
    hint: "Функциональные зоны ГП, зоны ПЗЗ, ППТ, ПМТ, ГПЗУ, КРТ",
    keys: ["gisogd.func_zones", "gisogd.pzz_zones", "gisogd.ppt", "gisogd.pmt", "gisogd.gpzu", "gisogd.krt"],
  },
];

const project = useProject(), ui = useUi(), cmd = useCommands();
const sources = ref<Record<string, SourceMeta>>({});
const ogdFlat = ref<FlatOgd[]>([]);
const ogdLoading = ref(false);
const counts = ref<Record<string, number | null> | null>(null);
const scanning = ref(false);
const q = ref("");
const onlyHit = ref(false);
const sel = ref<Set<string>>(new Set());
const busy = ref(false);
const status = ref("");
const isErr = ref(false);
const ogdLimit = ref(80);

function flattenOgd(nodes: OgdTreeNode[], out: FlatOgd[], seen: Set<string>) {
  for (const n of nodes || []) {
    if (n.code) {
      const code = n.instead || n.code;
      const key = "ogd." + code;
      if (!seen.has(key)) {
        seen.add(key);
        out.push({
          key,
          code,
          num: n.num || "",
          title: n.instead ? `${n.name} — полигонами` : n.name,
          path: n.path || "",
        });
      }
    }
    if (n.children?.length) flattenOgd(n.children, out, seen);
  }
}

async function loadCatalog() {
  try {
    const r = await fetch("/api/sources", { headers: { Accept: "application/json" } });
    if (r.ok) sources.value = await r.json();
  } catch { /* офлайн или сервер недоступен */ }
  ogdLoading.value = true;
  try {
    const r = await fetch("/api/ogd_all/tree", { headers: { Accept: "application/json" } });
    if (r.ok) {
      const j = await r.json();
      const flat: FlatOgd[] = [];
      flattenOgd(j.tree || [], flat, new Set());
      ogdFlat.value = flat;
    }
  } catch { /* дерево портала не получено */ } finally {
    ogdLoading.value = false;
  }
}

async function scanArea() {
  const bb = coverBbox({ project, ui });
  if (!bb) { status.value = "Сначала задайте границу территории или откройте карту."; isErr.value = true; return; }
  scanning.value = true;
  status.value = "Считаю объекты ГИС ОГД в области…";
  isErr.value = false;
  try {
    const r = await fetch("/api/ogd_all/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ bbox: bb }),
    });
    if (!r.ok) throw new Error(`Сервер ответил ${r.status}`);
    const j = await r.json();
    counts.value = j.counts || {};
    const hit = Object.values(counts.value || {}).filter(v => typeof v === "number" && v > 0).length;
    onlyHit.value = hit > 0;
    status.value = hit ? `В кэше сервера найдено слоёв с объектами: ${hit}.` : "В локальном кэше сервера по этой области объектов нет.";
  } catch (e) {
    status.value = "Подсчёт не удался: " + (e as Error).message;
    isErr.value = true;
  } finally {
    scanning.value = false;
  }
}

const presetAvail = (keys: string[]) => keys.filter(k => Boolean(sources.value[k]));
const presetOn = (keys: string[]) => {
  const avail = presetAvail(keys);
  return avail.length > 0 && avail.every(k => sel.value.has(k));
};
function togglePreset(keys: string[]) {
  const avail = presetAvail(keys);
  const on = presetOn(keys);
  const next = new Set(sel.value);
  for (const k of avail) on ? next.delete(k) : next.add(k);
  sel.value = next;
}

function toggleKey(k: string) {
  const next = new Set(sel.value);
  if (next.has(k)) next.delete(k); else next.add(k);
  sel.value = next;
}

const ogdCount = (code: string): number | null | undefined => counts.value ? counts.value[code] : undefined;

const groupedSources = computed(() => {
  const needle = q.value.trim().toLowerCase();
  return GROUP_ORDER.map(([id, title]) => {
    const items = Object.entries(sources.value)
      .filter(([k, s]) => (s.kind === id || (id === "gisogd" && s.kind === "gisogd_admin")) && !k.startsWith("ogd."))
      .map(([key, s]) => ({ key, title: s.title || key }))
      .filter(it => !needle || it.title.toLowerCase().includes(needle) || it.key.toLowerCase().includes(needle));
    return { id, title, items };
  }).filter(g => g.items.length);
});

const filteredOgd = computed(() => {
  const needle = q.value.trim().toLowerCase();
  return ogdFlat.value.filter(it => {
    if (onlyHit.value && counts.value && ogdCount(it.code) === 0 && !sel.value.has(it.key)) return false;
    if (!needle) return true;
    return it.title.toLowerCase().includes(needle) || it.path.toLowerCase().includes(needle) || it.code.toLowerCase().includes(needle);
  });
});

async function runLoad(keys: string[]) {
  if (!keys.length || busy.value) return;
  busy.value = true;
  isErr.value = false;
  status.value = `Загружаю слои (${keys.length})…`;
  try {
    const entry = await cmd.exec("загрузить", keys);
    status.value = entry.text;
    isErr.value = !entry.ok;
  } finally {
    busy.value = false;
  }
}

const loadSelected = () => runLoad([...sel.value]);
const loadOne = (k: string) => runLoad([k]);

onMounted(() => { loadCatalog(); });
</script>

<style scoped>
.g3-cat { display: flex; flex-direction: column; gap: 8px; height: 100%; box-sizing: border-box; }
.cat-bar { display: flex; gap: 6px; align-items: center; }
.cat-inp { flex: 1; min-width: 0; padding: 5px 8px; border: 1px solid var(--wa-color-neutral-border-normal); border-radius: 6px; background: var(--wa-color-surface-default); color: inherit; font: inherit; font-size: 12px; }
.cat-presets { display: flex; flex-wrap: wrap; gap: 4px; }
.chip { border: 1px solid var(--wa-color-neutral-border-normal); background: var(--wa-color-surface-default); color: inherit; border-radius: 999px; padding: 3px 8px; font: inherit; font-size: 11px; cursor: pointer; }
.chip.on { background: var(--wa-color-brand-fill-quiet); border-color: var(--wa-color-brand-border-normal); color: var(--wa-color-brand-on-quiet); font-weight: 600; }
.cat-opts { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 11px; }
.chk { display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
.link { border: 0; background: none; color: var(--wa-color-brand-on-quiet); font: inherit; font-size: 11px; cursor: pointer; padding: 0; text-decoration: underline; }
.link:disabled { opacity: 0.5; cursor: default; }
.cat-msg { margin: 0; font-size: 12px; padding: 6px 8px; border-radius: 6px; background: var(--wa-color-surface-lowered); }
.cat-msg.err { color: var(--wa-color-danger-on-quiet); background: var(--wa-color-danger-fill-quiet); }
.cat-tree { flex: 1; min-height: 0; overflow: auto; display: flex; flex-direction: column; gap: 6px; }
.grp-sum { display: flex; justify-content: space-between; align-items: center; padding: 4px 6px; border-radius: 6px; background: var(--wa-color-surface-lowered); cursor: pointer; font-size: 11px; font-weight: 600; }
.grp-body { display: flex; flex-direction: column; gap: 2px; padding: 4px 2px 4px 6px; }
.ly-row { display: flex; align-items: center; gap: 6px; min-height: 24px; }
.ly-lbl { flex: 1; min-width: 0; display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; }
.ly-nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.badge { font-size: 11px; color: var(--wa-color-text-quiet); padding: 1px 5px; border-radius: 4px; background: var(--wa-color-surface-lowered); flex-shrink: 0; }
.badge.has { color: var(--wa-color-brand-on-quiet); background: var(--wa-color-brand-fill-quiet); font-weight: 600; }
.qload { border: 0; background: none; color: var(--wa-color-text-quiet); cursor: pointer; padding: 2px 5px; border-radius: 4px; font-size: 12px; }
.qload:hover { background: var(--wa-color-surface-lowered); color: var(--wa-color-text-normal); }
.more { margin-top: 4px; align-self: flex-start; }
</style>
