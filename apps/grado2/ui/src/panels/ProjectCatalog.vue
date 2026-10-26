<!-- ГРАДО 2 · окно «Проекты»: каталог папки проектов карточками с превью (ProjectCard.vue). Поиск, порядок (изменённые, открытые,
     по названию), отбор (все, избранные, с альбомом), новый проект, файл с диска; у карточки — открыть, переименовать, копия, скачать,
     в корзину. «Корзина» — удалённые проекты с кнопкой «Вернуть». Данные и действия — project.js, сервер — catalog.py.
     Выбор порядка и отбора помнит браузер (localStorage «grado-catalog»). -->
<template>
  <wa-dialog class="catalog" label="Проекты" :open="open" @wa-after-hide="$emit('close')">
    <div class="cbar">
      <template v-if="tab === 'all'">
      <wa-input class="q" size="s" type="search" placeholder="Поиск по названию" aria-label="Поиск проекта" :value="q" with-clear
                @input="e => q = e.target.value"><Search slot="start" :size="15" /></wa-input>
      <div class="seg" role="radiogroup" aria-label="Какие проекты показать">
        <button v-for="f in FILTERS" :key="f[0]" type="button" role="radio" :aria-checked="pref.filter === f[0]" @click="setPref('filter', f[0])">{{ f[1] }}</button>
      </div>
      <select class="ord" :value="pref.ord" aria-label="Порядок" @change="e => setPref('ord', e.target.value)">
        <option value="modified">Сначала изменённые</option><option value="opened">Сначала открытые</option><option value="name">По названию</option>
      </select>
      </template>
      <span v-else class="ttl">Удалённые проекты</span>
      <span class="grow"></span>
      <wa-button size="s" appearance="outlined" @click="$emit('file')"><Upload slot="start" :size="15" />Файл с диска…</wa-button>
      <wa-button size="s" :appearance="tab === 'trash' ? 'filled' : 'plain'" :variant="tab === 'trash' ? 'brand' : 'neutral'"
                 :title="trash.n ? `Удалённые проекты: ${trash.n}` : 'Корзина пуста'" @click="toggleTrash"><Trash2 slot="start" :size="15" />Корзина<span v-if="trash.n" class="cnt">{{ trash.n }}</span></wa-button>
    </div>

    <template v-if="tab === 'all'">
      <div class="grid">
        <button class="pnew" type="button" @click="$emit('new')"><Plus :size="26" :stroke-width="1.5" /><span>Новый проект</span><small>пустая карта, всё с нуля</small></button>
        <ProjectCard v-for="p in shown" :key="p.name" :name="p.name" :sub="subOf(p)" :img="imgOf(p)" :star="!!p.star" :current="p.name === project.file"
                     :editing="ren === p.name" @open="$emit('open', p.name)" @star="starProject(p)" @edit="ren = p.name" @cancel="ren = null"
                     @rename="v => doRename(p.name, v)" @act="a => act(a, p)">
          <template #menu>
            <wa-dropdown-item value="open">Открыть</wa-dropdown-item>
            <wa-dropdown-item value="ren">Переименовать</wa-dropdown-item>
            <wa-dropdown-item value="copy">Сделать копию</wa-dropdown-item>
            <wa-dropdown-item value="down">Скачать файл .grado2</wa-dropdown-item>
            <wa-divider></wa-divider>
            <wa-dropdown-item value="del" variant="danger">В корзину</wa-dropdown-item>
          </template>
        </ProjectCard>
      </div>
      <p v-if="!projects.length" class="hint">В папке проектов пока ничего нет. Начните новый проект или откройте файл .grado2 с диска.</p>
      <p v-else-if="!shown.length" class="hint">Ничего не найдено{{ pref.filter !== "all" ? ": попробуйте «Все»" : "" }}.</p>
    </template>

    <template v-else>
      <p v-if="!trash.items.length" class="hint">Корзина пуста. Удалённые проекты лежат здесь, пока их не вернут.</p>
      <div v-for="t in trash.items" :key="t.id" class="trow">
        <span class="nm">{{ t.name }}</span><span class="when">удалён {{ when(t.deleted) }} · {{ size(t.size) }}</span>
        <wa-button size="s" appearance="outlined" @click="restoreProject(t.id)"><RotateCcw slot="start" :size="14" />Вернуть</wa-button>
      </div>
      <p class="hint">Корзина — папка «.trash» внутри папки проектов. Чтобы удалить навсегда, удалите файл оттуда в Finder.</p>
    </template>

    <p class="foot" :title="projDir">Папка проектов: {{ projDir }}</p>
  </wa-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { Plus, RotateCcw, Search, Trash2, Upload } from "@lucide/vue";
import ProjectCard from "./ProjectCard.vue";
import { project } from "../store.js";
import { copyProject, listProjects, listTrash, projDir, projects, renameProject, restoreProject, starProject, trash, trashProject } from "../project.js";

const props = defineProps({ open: Boolean });
const emit = defineEmits(["close", "open", "new", "file"]);

const FILTERS = [["all", "Все"], ["star", "Избранные"], ["album", "С листами ППТ КРТ"]];
const KEY = "grado-catalog";
const pref = reactive((() => { try { return { filter: "all", ord: "modified", ...JSON.parse(localStorage.getItem(KEY) || "{}") }; } catch { return { filter: "all", ord: "modified" }; } })());
function setPref(k, v) { pref[k] = v; try { localStorage.setItem(KEY, JSON.stringify(pref)); } catch { /* частный режим браузера */ } }

const q = ref(""), tab = ref("all"), ren = ref(null);
watch(() => props.open, on => { if (on) { tab.value = "all"; ren.value = null; listProjects().catch(() => {}); } });

const norm = s => (s || "").normalize("NFC").toLowerCase().replace(/ё/g, "е");
const shown = computed(() => {
  const t = norm(q.value.trim());
  const list = projects.value.filter(p => (!t || norm(p.name).includes(t))
    && (pref.filter !== "star" || p.star) && (pref.filter !== "album" || +p.album_n > 0));
  const by = { modified: (a, b) => (b.modified || 0) - (a.modified || 0), opened: (a, b) => (b.opened || 0) - (a.opened || 0) || (b.modified || 0) - (a.modified || 0),
    name: (a, b) => a.name.localeCompare(b.name, "ru", { numeric: true }) }[pref.ord] || (() => 0);
  return [...list].sort((a, b) => (b.star ? 1 : 0) - (a.star ? 1 : 0) || by(a, b));   // избранные — первыми
});

const imgOf = p => `/api/project/preview?name=${encodeURIComponent(p.name)}&v=${Math.round((p.modified || 0) * 1000)}-${p.size || 0}`;
function when(t) {
  if (!t) return "";
  const d = new Date(t * 1000), now = new Date(), hm = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  const day = x => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime(), diff = Math.round((day(now) - day(d)) / 864e5);
  if (diff === 0) return `сегодня в ${hm}`;
  if (diff === 1) return `вчера в ${hm}`;
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", ...(d.getFullYear() !== now.getFullYear() ? { year: "numeric" } : {}) });
}
const size = b => b >= 1048576 ? `${(b / 1048576).toFixed(1).replace(".", ",")} МБ` : `${Math.max(1, Math.round((b || 0) / 1024))} КБ`;
const subOf = p => [`изменён ${when(p.modified)}`, size(p.size), +p.album_n ? `ППТ КРТ ${p.album_n} л.` : ""].filter(Boolean).join(" · ");

async function doRename(name, to) { ren.value = null; await renameProject(name, to); }
async function toggleTrash() { tab.value = tab.value === "trash" ? "all" : "trash"; if (tab.value === "trash") listTrash().catch(() => {}); }
async function download(name) {
  const r = await fetch("/api/project?name=" + encodeURIComponent(name));
  if (!r.ok) return;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await r.blob()); a.download = name + ".grado2"; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}
function act(a, p) {
  if (a === "open") emit("open", p.name);
  else if (a === "ren") ren.value = p.name;
  else if (a === "copy") copyProject(p.name);
  else if (a === "down") download(p.name);
  else if (a === "del") trashProject(p.name);
}
</script>

<style>
.catalog::part(dialog) { width: min(1120px, 96vw); max-height: 92vh; }
.catalog::part(body) { padding-top: 4px; }
.catalog .cbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 14px; position: sticky; top: 0; z-index: 2;
  background: var(--wa-color-surface-raised, var(--wa-color-surface-default)); padding: 4px 0; }
.catalog .q { width: 260px; }
.catalog .seg { display: inline-flex; padding: 2px; border-radius: 8px; background: var(--wa-color-neutral-fill-quiet); }
.catalog .seg button { border: 0; background: none; font: inherit; font-size: var(--wa-font-size-s); padding: 3px 10px; border-radius: 6px; cursor: pointer; color: var(--g-muted); }
.catalog .seg button[aria-checked=true] { background: var(--wa-color-brand-fill-quiet); color: var(--wa-color-brand-on-quiet); font-weight: 600; }
.catalog .ttl { font-weight: 600; }
.catalog .ord { font: inherit; font-size: var(--wa-font-size-s); padding: 4px 7px; border: 1px solid var(--g-line); border-radius: 6px; background: var(--wa-color-surface-default); color: var(--wa-color-text-normal); }
.catalog .grow { flex: 1; }
.catalog .cnt { margin-left: 6px; padding: 0 6px; border-radius: 8px; font-size: var(--wa-font-size-2xs); line-height: 16px; background: var(--wa-color-neutral-fill-normal); }
.catalog wa-button::part(label) { display: inline-flex; align-items: center; }
.catalog .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
.catalog .pnew { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; min-height: 186px; border: 1.5px dashed var(--g-line);
  border-radius: 12px; background: none; font: inherit; color: var(--wa-color-brand-on-quiet); cursor: pointer; }
.catalog .pnew:hover { border-color: var(--wa-color-brand-fill-loud); background: var(--wa-color-brand-fill-quiet); }
.catalog .pnew span { font-weight: 600; }
.catalog .pnew small { color: var(--g-muted); font-size: var(--wa-font-size-xs); }
.catalog .hint { color: var(--g-muted); margin: 12px 2px 0; }
.catalog .foot { color: var(--g-muted); font-size: var(--wa-font-size-xs); margin: 16px 2px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.catalog .trow { display: flex; align-items: center; gap: 12px; padding: 6px 4px; border-bottom: 1px solid var(--g-line); }
.catalog .trow .nm { font-weight: 600; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.catalog .trow .when { color: var(--g-muted); font-size: var(--wa-font-size-xs); }
</style>
