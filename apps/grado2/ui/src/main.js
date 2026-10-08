/* ГРАДО 2 · пробная страница нового редактора раскладки листа: лист А3 с картой, легендой и штампом.
   Запуск: cd apps/grado2/ui && npm run dev. В программу редактор войдёт вместе с каркасом интерфейса на Vue 3 (шаг 3 плана). */
import { createApp, h, ref } from "vue";
import SheetEditor from "./sheet/SheetEditor.vue";
import { newSheet } from "./sheet/model.js";

const sheet = ref(newSheet({ format: "A3", title: "Схема существующего использования территории" }));
const meta = { object: "Комплексное развитие территории (пример)", code: "КРТ-00-ПП", stage: "ПП", org: "ГРАДО" };
createApp({
  setup: () => () => h(SheetEditor, { modelValue: sheet.value, "onUpdate:modelValue": v => { sheet.value = v; window.SHEET = v; }, meta, page: { page_no: 6, page_total: 11 } }),
}).mount("#app");
window.SHEET = sheet.value;
