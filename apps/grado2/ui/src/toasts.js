/* ГРАДО 2 · тосты вместо строки состояния: сообщения канала notice (project.js) выходят карточками с уровнем —
   ошибка (красная, стоит, пока её не закроют; повторяемому действию — кнопка «Повторить», приём карточки выгрузки
   из окна «Данные», DataPanel.vue), успех и действие уходят сами, как тост рабочей страницы (web/app.js toast).
   Уровень задают явно — say(t, { level, retry }) из project.js; прямые записи (notice.value = …) получают уровень
   по тексту. Пустая строка карточку не создаёт — это «убрать сообщение» (так гасят подсказку MapPanel.vue, cad.js). */
import { ref } from "vue";

export const toasts = ref([]);
let seq = 0;

/* уровень прямой записи: неудача — по глаголу после «не» и словам причины, успех — по короткому ряду «готово»,
   остальное — действие. Списки — по текстам самой программы (project.js, data.js, exports.js, hub.js, collab.js…). */
const ERR = /(?:[Нн]е (?:сохрани|откры|удал|верну|отмеч|переименова|сдела|созда|загруж|прочит|посчита|собра|начал|останов|измен|ответ|скопирова|найде|объедини|рассчита|выполн|получ|выгруж)|не сохран|[Нн]ет связи|не отвечает|ошибк|неудач|это предел|уже есть|PDF лист|^Альбом: )/;
const OK = /сохранён|сохранено|Открыт проект|Открыт файл|открыли проект|Сделана копия|Создан|Создана|скопирован|вернулся|возвращён|возвращена|Возвращено|переименован|называется «|Пароль изменён|готов|Загружено|нарисован|Заполнено|упорядочен|рассчитан|стала общим проектом|в корзине|обновлён/;
const levelOf = t => ERR.test(t) ? "error" : OK.test(t) ? "success" : "action";

/* сколько висит карточка успеха или действия — как тост рабочей страницы (web/app.js): чем длиннее текст, тем дольше */
const timeoutOf = t => Math.max(4200, t.length * 55);

export function toast(text, opts) {
  if (!text) return null;
  const { level, retry, timeout, busy } = opts || {};
  const old = toasts.value.find(t => t.text === text);
  if (old) drop(old);                                        // тот же текст — одна карточка, отсчёт заново
  const t = { id: ++seq, text, level: level || levelOf(text), retry, busy: !!busy, timer: 0 };
  toasts.value.push(t);
  while (toasts.value.length > 4) drop(toasts.value[0]);     // копим не больше четырёх карточек
  if (!t.busy && t.level !== "error") t.timer = setTimeout(() => drop(t), timeout ?? timeoutOf(text));   // ошибка стоит до закрытия
  return t;
}

export function drop(t) { const i = toasts.value.indexOf(t); if (i >= 0) toasts.value.splice(i, 1); clearTimeout(t.timer); }
/* убрать карточку по тексту: пустая строка в канале notice — «убрать сообщение» (project.js, say() гасит старую перед повтором) */
export const dropText = t => { const old = toasts.value.find(x => x.text === t); if (old) drop(old); };
/* «Повторить» в карточке ошибки: карточка уходит, действие запускается заново — его итог придёт следующим тостом */
export function again(t) { drop(t); t.retry?.(); }
export const dropBusy = () => toasts.value.filter(t => t.busy).forEach(drop);
