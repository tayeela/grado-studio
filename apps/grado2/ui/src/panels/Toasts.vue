<!-- ГРАДО 2 · тосты вместо строки состояния: карточки уровней (ошибка/успех/действие) над строкой состояния, поверх окон.
     Ошибка стоит, пока её не закроют, повторяемому действию — кнопка «Повторить» (приём карточки выгрузки в «Данных»,
     DataPanel.vue: значок, главная кнопка в обводке с RotateCw); успех и действие уходят сами (тайминг — как тост
     рабочей страницы, web/app.js). Состояние и уровни — toasts.js; канал — notice из project.js. -->
<template>
  <div class="toasts">
    <div v-for="t in toasts" :key="t.id" class="toast" :class="t.level" :role="t.level === 'error' ? 'alert' : 'status'">
      <span class="ic">
        <wa-spinner v-if="t.busy"></wa-spinner>
        <CircleAlert v-else-if="t.level === 'error'" :size="16" />
        <CircleCheck v-else-if="t.level === 'success'" :size="16" />
        <Info v-else :size="16" />
      </span>
      <span class="tx">{{ t.text }}</span>
      <wa-button v-if="t.retry" size="s" variant="brand" appearance="outlined" class="again" @click="again(t)"><RotateCw slot="start" :size="14" />Повторить</wa-button>
      <wa-button v-if="t.level === 'error'" size="s" appearance="plain" class="x" aria-label="Закрыть" title="Закрыть" @click="drop(t)"><X :size="14" /></wa-button>
    </div>
  </div>
</template>

<script setup>
import { CircleAlert, CircleCheck, Info, RotateCw, X } from "@lucide/vue";
import { again, drop, toasts } from "../toasts.js";
</script>

<style>
.toasts { position: fixed; right: 14px; bottom: 34px;   /* над строкой состояния (26 px) с зазором dockview */
  z-index: 1200; display: flex; flex-direction: column; align-items: flex-end; gap: 8px; width: min(440px, calc(100vw - 28px)); }
.toast { display: flex; align-items: flex-start; gap: 8px; padding: 8px 10px; border-radius: 10px; box-shadow: var(--g-shadow-2);
  background: var(--wa-color-surface-raised); border: 1px solid var(--g-line); font-size: var(--wa-font-size-s); line-height: 1.45; color: var(--wa-color-text-normal); }
.toast .ic { flex: none; display: inline-grid; place-items: center; margin-top: 2px; color: var(--g-muted); }
.toast .tx { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.toast.error { background: var(--wa-color-danger-fill-quiet); border-color: color-mix(in srgb, var(--wa-color-danger-fill-loud) 30%, transparent); color: var(--wa-color-danger-on-quiet); }
.toast.error .ic { color: var(--wa-color-danger-on-quiet); }
.toast.success { background: var(--wa-color-success-fill-quiet); border-color: color-mix(in srgb, var(--wa-color-success-fill-loud) 30%, transparent); color: var(--wa-color-success-on-quiet); }
.toast.success .ic { color: var(--wa-color-success-fill-loud); }
.toast .again { flex: none; margin: -2px 0; }
.toast .x { flex: none; margin: -4px -6px -4px 0; }   /* крестик — как «Убрать отчёт о выгрузке» в окне «Данные» */
.toast wa-spinner { font-size: 14px; --track-width: 2px; flex: none; }
</style>
