<!-- ГРАДО 2 · числовое поле со степпером «− 0,35 +», как в образце интерфейса: принимает запятую и точку, правка
     уходит по Enter, уходу из поля или кнопкам. Используется в панели свойств редактора раскладки (PropsPanel.vue). -->
<script setup>
import { Minus, Plus } from "lucide-vue-next";
const props = defineProps({ modelValue: Number, step: { type: Number, default: 1 }, min: { type: Number, default: -1e9 }, max: { type: Number, default: 1e9 }, digits: { type: Number, default: 2 }, label: String });
const emit = defineEmits(["update:modelValue"]);
const show = v => v == null || !Number.isFinite(v) ? "" : String(+v.toFixed(props.digits)).replace(".", ",");
const put = v => { if (!Number.isFinite(v)) return; v = Math.min(props.max, Math.max(props.min, +v.toFixed(props.digits))); if (v !== props.modelValue) emit("update:modelValue", v); };
const typed = e => { const v = parseFloat(String(e.target.value).replace(",", ".").replace(/\s/g, "")); if (Number.isFinite(v)) put(v); else e.target.value = show(props.modelValue); };
</script>

<template>
  <div class="nf">
    <button type="button" tabindex="-1" :aria-label="`${label || ''} меньше`" @click="put((modelValue || 0) - step)"><Minus :size="13" /></button>
    <input :value="show(modelValue)" :aria-label="label" inputmode="decimal" @change="typed" @keydown.enter="typed">
    <button type="button" tabindex="-1" :aria-label="`${label || ''} больше`" @click="put((modelValue || 0) + step)"><Plus :size="13" /></button>
  </div>
</template>

<style scoped>
.nf { display: flex; align-items: center; border: 1px solid var(--g-line-strong); border-radius: 5px; background: #fff; height: 26px; }
.nf:focus-within { border-color: var(--g-accent); box-shadow: 0 0 0 2px var(--g-ring); }
.nf input { flex: 1; min-width: 0; width: 100%; border: 0; text-align: center; font: inherit; background: none; outline: none; padding: 0; }
.nf button { width: 22px; height: 24px; display: grid; place-items: center; border: 0; background: none; color: var(--g-mute); cursor: pointer; padding: 0; }
.nf button:hover { color: var(--g-ink); }
</style>
