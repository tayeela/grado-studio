<!-- ГРАДО 2 · карточка проекта в каталоге: превью территории (PNG с сервера, catalog.py), название, строка сведений, звёздочка
     и меню действий. Одна и та же карточка в окне «Проекты» (ProjectCatalog.vue, папка проектов) и «Совместные проекты»
     (HubWindows.vue, общий сервер). Щелчок по карточке — открыть, двойной щелчок по названию или пункт меню — переименовать. -->
<template>
  <article class="pcard" :class="{ cur: current }" tabindex="0" :aria-label="`Проект «${name}»`"
           @click="!editing && $emit('open')" @keydown.enter.self="$emit('open')">
    <div class="pv">
      <img v-if="img && !noImg" :src="img" alt="" loading="lazy" @error="noImg = true">
      <div v-else class="empty"><MapIcon :size="28" :stroke-width="1.5" /><span>{{ emptyText }}</span></div>
      <span v-if="current" class="badge">Открыт</span>
      <button v-if="star !== undefined" class="star" :class="{ on: star }" type="button" :aria-pressed="star"
              :title="star ? 'Убрать из избранного' : 'В избранное'" @click.stop="$emit('star')"><Star :size="15" :fill="star ? 'currentColor' : 'none'" /></button>
    </div>
    <div class="body">
      <input v-if="editing" ref="inp" class="ren" :value="name" maxlength="120" aria-label="Новое название проекта"
             @click.stop @keydown.enter.prevent="done($event.target.value)" @keydown.esc.stop.prevent="$emit('cancel')" @blur="done($event.target.value)">
      <div v-else class="nm" :title="renamable ? name + ' — двойной щелчок, чтобы переименовать' : name" @dblclick.stop="renamable && $emit('edit')">{{ name }}</div>
      <div class="sub"><slot name="sub">{{ sub }}</slot></div>
      <wa-dropdown v-if="$slots.menu" class="more" placement="bottom-end" @click.stop @wa-select="e => $emit('act', e.detail.item.value)">
        <wa-button slot="trigger" size="s" appearance="plain" :aria-label="`Действия с проектом «${name}»`" title="Действия"><Ellipsis :size="16" /></wa-button>
        <slot name="menu" />
      </wa-dropdown>
    </div>
  </article>
</template>

<script setup>
import { nextTick, ref, watch } from "vue";
import { Ellipsis, Map as MapIcon, Star } from "@lucide/vue";

const props = defineProps({
  name: { type: String, required: true },
  sub: { type: String, default: "" },
  img: { type: String, default: "" },
  star: { type: Boolean, default: undefined },
  current: Boolean,
  editing: Boolean,
  renamable: { type: Boolean, default: true },
  emptyText: { type: String, default: "Пока без объектов" },
});
const emit = defineEmits(["open", "star", "edit", "rename", "cancel", "act"]);
const noImg = ref(false), inp = ref(null);
watch(() => props.img, () => { noImg.value = false; });
watch(() => props.editing, async on => { if (on) { await nextTick(); inp.value?.focus(); inp.value?.select(); } }, { immediate: true });
let sent = false;
watch(() => props.editing, on => { if (on) sent = false; });
function done(v) { if (sent) return; sent = true; v = v.trim(); if (v && v !== props.name) emit("rename", v); else emit("cancel"); }
</script>

<style>
.pcard { position: relative; display: flex; flex-direction: column; border: 1px solid var(--g-line); border-radius: 12px; overflow: hidden; cursor: pointer;
  background: var(--wa-color-surface-default); transition: border-color .12s, box-shadow .12s, transform .12s; outline: none; min-width: 0; }
.pcard:hover { border-color: color-mix(in srgb, var(--wa-color-brand-fill-loud) 45%, var(--g-line)); box-shadow: var(--g-shadow-2, 0 4px 14px rgb(0 0 0 / .08)); }
.pcard:focus-visible { outline: 2px solid var(--wa-color-focus); outline-offset: 2px; }
.pcard.cur { border-color: var(--wa-color-brand-fill-loud); box-shadow: 0 0 0 1px var(--wa-color-brand-fill-loud); }
.pcard .pv { position: relative; aspect-ratio: 16 / 10; background: #f1f3f6; border-bottom: 1px solid var(--g-line); }
.pcard .pv img { width: 100%; height: 100%; object-fit: cover; display: block; }
.pcard .pv .empty { position: absolute; inset: 0; display: grid; place-content: center; justify-items: center; gap: 6px; color: #8a93a0; font-size: var(--wa-font-size-xs); }
.pcard .badge { position: absolute; left: 8px; top: 8px; padding: 1px 8px; border-radius: 8px; font-size: var(--wa-font-size-2xs); font-weight: 600;
  background: var(--wa-color-brand-fill-loud); color: var(--wa-color-brand-on-loud); }
.pcard .star { position: absolute; right: 6px; top: 6px; display: grid; place-items: center; width: 28px; height: 28px; border-radius: 8px; border: 0; cursor: pointer;
  background: rgb(255 255 255 / .85); color: #5c6573; opacity: 0; transition: opacity .12s; }
.pcard:hover .star, .pcard .star:focus-visible, .pcard .star.on { opacity: 1; }
.pcard .star.on { color: #e8a200; }
.pcard .body { position: relative; padding: 8px 36px 9px 11px; min-height: 48px; }
.pcard .nm { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pcard .ren { width: 100%; box-sizing: border-box; font: inherit; font-weight: 600; padding: 1px 5px; margin: -2px 0 -1px -6px; border: 1px solid var(--wa-color-focus);
  border-radius: 5px; background: var(--wa-color-surface-default); color: var(--wa-color-text-normal); }
.pcard .sub { color: var(--g-muted); font-size: var(--wa-font-size-xs); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 2px; font-variant-numeric: tabular-nums; }
.pcard .more { position: absolute; right: 4px; top: 7px; display: block; }
.pcard .more wa-button::part(base) { padding-inline: 4px; }
</style>
