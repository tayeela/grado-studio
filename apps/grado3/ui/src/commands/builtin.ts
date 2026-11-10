/* ГРАДО · команды каркаса (шаг И1): проект, отмена, рабочие места, слои, граница, карта, справка. Следующие шаги
   добавляют свои команды сюда же, по одной на действие, с отменой. Имена — русские, псевдонимы — как в AutoCAD.
   Проверка: commands.test.ts. */
import { CommandError, setter, type Bus, type Command, type Undo } from "./bus";
import { wgsToMsk } from "../core";
import { WORKSPACES, workspace } from "../workspaces";
import type { ProjectStore } from "../stores/project";
import type { UiStore } from "../stores/ui";
import type { Layer } from "../types/project";

export interface Ctx {
  project: ProjectStore;
  ui: UiStore;
}

const need = (c: Ctx) => {
  if (!c.project.doc) throw new CommandError("Проект не открыт: команда «открыть <название>»");
};
const layerOf = (c: Ctx, key: string | undefined): Layer => {
  need(c);
  if (!key) throw new CommandError("Нужен ключ слоя: он виден в окне «Слои»");
  const l = c.project.layer(key) || c.project.layers.find(x => (x.title || "").toLowerCase() === key.toLowerCase());
  if (!l) throw new CommandError(`Слоя «${key}» в проекте нет`);
  return l;
};
/** правка слоя с отменой: значение поля, отметка «есть правки», перерисовка карты */
const edit = <K extends keyof Layer>(c: Ctx, l: Layer, field: K, value: Layer[K]): Undo => {
  const u = setter(() => l[field], v => { l[field] = v; c.project.touch(); c.ui.map.api?.refresh(); }, value);
  return u;
};
const num = (s: string | undefined, what: string) => {
  const v = Number(String(s ?? "").replace(",", "."));
  if (!Number.isFinite(v)) throw new CommandError(`${what}: нужно число, а набрано «${s ?? ""}»`);
  return v;
};

export function builtins(bus: Bus<Ctx>): Command<Ctx>[] {
  return [
    {
      id: "открыть", title: "Открыть проект", aliases: ["OPEN"], args: "<название>",
      hint: "открыть проект из папки проектов",
      async run(c, a) {
        const name = a.join(" ").trim();
        if (!name) {
          const list = await c.project.refreshList();
          throw new CommandError(list.length ? "Какой проект? " + list.slice(0, 8).map(p => `«${p.name}»`).join(", ") : "В папке проектов пусто");
        }
        const r = await c.project.open(name);
        bus.resetHistory();
        c.ui.map.api?.refresh();
        c.ui.map.api?.fit();
        const warn = r.issues.length ? `, замечаний ${r.issues.length} (окно «Проверка проекта»)` : "";
        bus.say(`Открыт «${name}»: слоёв ${r.layers}, объектов ${r.features}${warn}`);
      },
    },
    {
      id: "сохранить", title: "Сохранить проект", aliases: ["QSAVE", "SAVE"], hint: "записать проект в папку проектов",
      async run(c) {
        need(c);
        const n = await c.project.save();
        bus.say(`Сохранено: «${n}»`);
      },
    },
    { id: "отменить", title: "Отменить", aliases: ["U", "UNDO"], hint: "Ctrl+Z",
      run() { const t = bus.undo(); bus.say(t ? `Отменено: ${t}` : "Отменять нечего"); } },
    { id: "вернуть", title: "Вернуть", aliases: ["REDO"], hint: "Ctrl+Shift+Z",
      run() { const t = bus.redo(); bus.say(t ? `Возвращено: ${t}` : "Возвращать нечего"); } },
    {
      id: "место", title: "Рабочее место", aliases: ["WS"], args: "<1–5 или название>",
      hint: WORKSPACES.map(w => `${w.n} ${w.title}`).join(", "),
      run(c, a) {
        const w = workspace(a.join(" ") || "");
        if (!w) throw new CommandError("Какое место? " + WORKSPACES.map(x => `${x.n} — ${x.title}`).join(", "));
        c.ui.ws = w.id;
        bus.say(`Рабочее место: ${w.title}`);
      },
    },
    { id: "показать", title: "Показать слой", aliases: ["LAYON"], args: "<ключ слоя>",
      run: (c, a) => edit(c, layerOf(c, a.join(" ")), "visible", true) },
    { id: "скрыть", title: "Скрыть слой", aliases: ["LAYOFF"], args: "<ключ слоя>",
      run: (c, a) => edit(c, layerOf(c, a.join(" ")), "visible", false) },
    {
      id: "переименовать", title: "Переименовать слой", aliases: ["RENAME"], args: "<ключ слоя> <новое название>",
      run(c, a) {
        const l = layerOf(c, a[0]);
        const t = a.slice(1).join(" ").trim();
        if (!t) throw new CommandError("Нужно новое название после ключа слоя");
        return edit(c, l, "title", t);
      },
    },
    {
      id: "граница", title: "Слой-граница территории", aliases: ["BOUNDARY"], args: "<ключ слоя>",
      hint: "роль границы у слоя: отдельного инструмента нет",
      run(c, a) {
        const l = layerOf(c, a.join(" "));
        if (l.geom && l.geom !== "poly") throw new CommandError("Границей может быть только слой полигонов");
        const before = c.project.layers.map(x => [x, x.role] as const);
        const apply = () => { for (const x of c.project.layers) x.role = x === l ? "territory" : (x.role === "territory" ? null : x.role); c.project.touch(); c.ui.map.api?.refresh(); };
        apply();
        return { undo: () => { for (const [x, r] of before) x.role = r; c.project.touch(); c.ui.map.api?.refresh(); }, redo: apply };
      },
    },
    {
      id: "показать-всё", title: "Показать всё", aliases: ["ZE", "ZOOM"], args: "[ключ слоя]",
      run(c, a) {
        if (!c.ui.map.api?.fit(a[0])) throw new CommandError(a[0] ? `У слоя «${a[0]}» нет объектов` : "На карте нечего вписать");
      },
    },
    {
      id: "точка", title: "Перейти к точке", aliases: ["GOTO"], args: "<X восток> <Y север> (МСК) или <широта> <долгота>",
      run(c, a) {
        const x = num(a[0], "Первое число"), y = num(a[1], "Второе число");
        // градусы (широта, долгота, как в Яндексе) или метры МСК
        const p = Math.abs(x) <= 90 && Math.abs(y) <= 180 ? wgsToMsk([y, x]) : [x, y] as [number, number];
        c.ui.map.api?.centerMsk(p);
        bus.say(`Точка МСК ${p[0].toFixed(2)} ${p[1].toFixed(2)}`);
      },
    },
    {
      id: "команды", title: "Список команд", aliases: ["HELP", "?"],
      run() { bus.say(bus.list().map(x => x.id + (x.aliases?.length ? ` (${x.aliases.join(", ")})` : "")).join(" · ")); },
    },
  ];
}
