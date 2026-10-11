/* ГРАДО 2 · команды редактора листа и командная строка (как в AutoCAD). Устройство — с deckcraft
   (github.com/storytold/deckcraft, MIT OR Apache-2.0: crates/engine/src/cmd/mod.rs — «каждая кнопка — команда с отменой»,
   имена вида arrange.align, список commands.list). Каждая кнопка ленты (Ribbon.vue) — команда отсюда: её можно набрать
   по-русски («ВЫРОВНЯТЬ ВЛЕВО», «СДВИГ 10 -5», «МАСШТАБ 1:2000») или именем deckcraft («arrange.align left»).
   parse() превращает строку в { id, args } для SheetEditor.vue act(); проверяет commands.test.js. */

// pick — слово после команды → id кнопки; nums — сколько чисел ждёт команда (id тогда — действие с аргументами)
const C = (name, ru, t, x) => ({ name, ru: [].concat(ru), t, ...x });
export const COMMANDS = [
  C("tool.select", ["ВЫБОР", "В"], "Выбор и перемещение", { id: "tool:select" }),
  C("tool.pan", ["ЛИСТСДВИГ", "ПАН"], "Сдвиг листа мышью", { id: "tool:pan" }),
  C("tool.content", ["КАРТАСДВИГ"], "Сдвиг карты внутри рамки", { id: "tool:content" }),
  C("insert.map", ["КАРТА"], "Добавить карту", { id: "add:map" }),
  C("insert.legend", ["ЛЕГЕНДА"], "Добавить легенду", { id: "add:legend" }),
  C("insert.text", ["НАДПИСЬ", "ТЕКСТ"], "Добавить надпись", { id: "add:text" }),
  C("insert.picture", ["КАРТИНКА"], "Добавить картинку", { id: "add:picture" }),
  C("insert.north", ["СЕВЕР"], "Добавить стрелку севера", { id: "add:north" }),
  C("insert.scalebar", ["ЛИНЕЙКА"], "Добавить масштабную линейку", { id: "add:scalebar" }),
  C("insert.table", ["ТАБЛИЦА"], "Добавить таблицу", { id: "add:table" }),
  C("shape.insert.rect", ["ПРЯМОУГОЛЬНИК", "ПРЯМ"], "Добавить прямоугольник", { id: "add:rect" }),
  C("shape.insert.ellipse", ["ЭЛЛИПС"], "Добавить эллипс", { id: "add:ellipse" }),
  C("shape.insert.line", ["ЛИНИЯ"], "Добавить линию со стрелкой", { id: "add:line" }),
  C("edit.undo", ["ОТМЕНИТЬ", "О"], "Отменить", { id: "undo" }),
  C("edit.redo", ["ВЕРНУТЬ"], "Вернуть отменённое", { id: "redo" }),
  C("edit.copy", ["КОПИРОВАТЬ"], "Копировать выбранное", { id: "copy" }),
  C("edit.cut", ["ВЫРЕЗАТЬ"], "Вырезать выбранное", { id: "cut" }),
  C("edit.paste", ["ВСТАВИТЬ"], "Вставить", { id: "paste" }),
  C("edit.duplicate", ["ДУБЛИРОВАТЬ", "КОПИЯ"], "Дублировать выбранное", { id: "dup" }),
  C("edit.delete", ["УДАЛИТЬ", "СТЕРЕТЬ"], "Удалить выбранное", { id: "del" }),
  C("edit.select", ["ВСЕ"], "Выбрать все элементы", { id: "all" }),
  C("format.painter", ["ОБРАЗЕЦ", "КИСТЬ"], "Формат по образцу: оформление выбранного — на элементы, по которым щёлкнете", { id: "painter" }),
  C("arrange.align", ["ВЫРОВНЯТЬ", "ВЫР"], "Выровнять: ВЛЕВО, ЦЕНТР, ВПРАВО, ВВЕРХ, СЕРЕДИНА, ВНИЗ", { pick: {
    ВЛЕВО: "align:left", ЦЕНТР: "align:hcenter", ВПРАВО: "align:right", ВВЕРХ: "align:top", СЕРЕДИНА: "align:vcenter", ВНИЗ: "align:bottom",
    LEFT: "align:left", CENTER: "align:hcenter", RIGHT: "align:right", TOP: "align:top", MIDDLE: "align:vcenter", BOTTOM: "align:bottom" } }),
  C("arrange.distribute", ["РАСПРЕДЕЛИТЬ"], "Распределить: ГОР или ВЕРТ", { pick: { ГОР: "dist:x", ВЕРТ: "dist:y", HORIZONTAL: "dist:x", VERTICAL: "dist:y" } }),
  C("shape.same", ["ОДИНАКОВО"], "Одинаковый размер по первому выбранному: ШИРИНА или ВЫСОТА", { pick: { ШИРИНА: "same:w", ВЫСОТА: "same:h", WIDTH: "same:w", HEIGHT: "same:h" } }),
  C("arrange.reorder", ["ПОРЯДОК"], "Порядок: НАВЕРХ, ВЫШЕ, НИЖЕ, ВНИЗ", { pick: {
    НАВЕРХ: "order:top", ВЫШЕ: "order:up", НИЖЕ: "order:down", ВНИЗ: "order:bottom", FRONT: "order:top", FORWARD: "order:up", BACKWARD: "order:down", BACK: "order:bottom" } }),
  C("arrange.group", ["ГРУППА", "СГРУППИРОВАТЬ"], "Сгруппировать выбранные", { id: "group" }),
  C("arrange.ungroup", ["РАЗГРУППИРОВАТЬ", "РАСЧЛЕНИТЬ"], "Разгруппировать", { id: "ungroup" }),
  C("arrange.regroup", ["ВОССТАНОВИТЬГРУППУ"], "Собрать группу снова", { id: "regroup" }),
  C("shape.flip", ["ОТРАЗИТЬ", "ЗЕРКАЛО"], "Отразить: ГОР (слева направо) или ВЕРТ (сверху вниз)", { pick: { ГОР: "flip:h", ВЕРТ: "flip:v", HORIZONTAL: "flip:h", VERTICAL: "flip:v" } }),
  C("shape.lock", ["ЗАКРЕПИТЬ"], "Закрепить выбранные", { id: "lock" }),
  C("shape.unlock", ["ОТКРЕПИТЬ"], "Открепить все", { id: "unlock" }),
  C("shape.move", ["СДВИГ", "ПЕРЕНЕСТИ"], "Сдвинуть выбранное: СДВИГ dx dy (мм)", { id: "move", nums: 2 }),
  C("shape.position", ["МЕСТО"], "Левый верхний угол выбранного: МЕСТО x y (мм)", { id: "pos", nums: 2 }),
  C("shape.resize", ["РАЗМЕР"], "Ширина и высота выбранного: РАЗМЕР w h (мм)", { id: "size", nums: 2 }),
  C("shape.rotate", ["ПОВЕРНУТЬ", "ПОВОРОТ"], "Повернуть выбранное: ПОВЕРНУТЬ угол (градусы, против часовой — минус)", { id: "rotate", nums: 1 }),
  C("map.scale", ["МАСШТАБ"], "Масштаб выбранной карты: МАСШТАБ 1:2000", { id: "scale", nums: 1 }),
  C("map.here", ["КАКНАКАРТЕ"], "Место и масштаб карты — как в окне «Карта»", { id: "map:here" }),
  C("legend.layers", ["ЛЕГЕНДАСЛОИ"], "Строки легенды — из видимых слоёв", { id: "legend:layers" }),
  C("view.grid", ["СЕТКА"], "Показать или скрыть сетку", { id: "grid:show" }),
  C("view.snap", ["ПРИВЯЗКА"], "Привязка к сетке", { id: "grid:snap" }),
  C("view.zoom", ["ПОКАЗАТЬ", "ЗУМ"], "Показать: ВСЕ (лист), ВЫБРАННОЕ, 100", { pick: { ВСЕ: "zoom:fit", ЛИСТ: "zoom:fit", ВЫБРАННОЕ: "zoom:sel", 100: "zoom:100",
    FIT: "zoom:fit", SELECTION: "zoom:sel" } }),
  C("file.export.pdf", ["PDF", "ПДФ"], "Лист в PDF", { id: "export:pdf" }),
  C("file.export.png", ["PNG", "ПНГ"], "Лист картинкой PNG", { id: "export:png" }),
  C("commands.list", ["?", "СПРАВКА"], "Список команд", { id: "help" }),
];

const up = s => s.toLocaleUpperCase("ru").replace(/Ё/g, "Е");
const KEY = new Map();
COMMANDS.forEach(c => [c.name, ...c.ru].forEach(n => KEY.set(up(n), c)));
// число: десятичная запятая и масштаб «1:2000» (берётся знаменатель)
const num = w => { const m = /^1:(\d[\d\s]*)$/.exec(w); const v = m ? +m[1] : +w.replace(",", "."); return Number.isFinite(v) ? v : null; };

/* строка → { cmd, id, args } или { error }: первое слово — команда, остальное — уточнение или числа */
export function parse(line) {
  const words = String(line || "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return { error: "" };
  const cmd = KEY.get(up(words[0]));
  if (!cmd) return { error: `Нет команды «${words[0]}». «?» — список команд` };
  const rest = words.slice(1);
  if (cmd.pick) {
    const id = rest.length ? cmd.pick[up(rest[0])] : null;
    return id ? { cmd, id, args: [] } : { error: `${cmd.ru[0]}: уточните — ${Object.keys(cmd.pick).filter(k => /[А-Я0-9]/.test(k[0])).join(", ")}` };
  }
  if (cmd.nums) {
    const args = rest.map(num);
    if (args.length < cmd.nums || args.slice(0, cmd.nums).some(v => v === null)) return { error: `${cmd.t}` };
    return { cmd, id: cmd.id, args: args.slice(0, cmd.nums) };
  }
  return { cmd, id: cmd.id, args: [] };
}
// подсказки для поля ввода: русские имена и пояснение
export const hints = () => COMMANDS.map(c => ({ v: c.ru[0], t: c.t }));
// команда кнопки ленты — для подписи истории отмены
export const titleOf = id => COMMANDS.find(c => c.id === id || Object.values(c.pick || {}).includes(id))?.t?.split(":")[0] || "";
