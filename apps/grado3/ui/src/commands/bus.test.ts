import { describe, expect, it } from "vitest";
import { Bus, CommandError, setter, splitLine } from "./bus";

const make = () => {
  const ctx = { n: 0, log: [] as string[] };
  const bus = new Bus(ctx);
  bus.register(
    { id: "плюс", title: "Прибавить", aliases: ["ADD", "+"], run: (c, a) => setter(() => c.n, v => { c.n = v; }, c.n + Number(a[0] || 1)) },
    { id: "сказать", title: "Сказать", run: (c, a) => { c.log.push(a.join(" ")); } },
    { id: "сломать", title: "Сломать", run: () => { throw new CommandError("Так нельзя"); } },
    { id: "упасть", title: "Упасть", run: () => { throw new Error("boom"); } },
    { id: "отменить", title: "Отменить", run: () => { bus.undo(); } },
  );
  return { ctx, bus };
};

describe("шина команд", () => {
  it("имя, псевдоним, начало имени", async () => {
    const { ctx, bus } = make();
    await bus.line("плюс 2");
    await bus.line("ADD 3");
    await bus.line("пл");
    expect(ctx.n).toBe(6);
    expect(bus.find("add")?.id).toBe("плюс");
    expect(bus.find("с")).toBeNull();                 // начало «с» у двух команд
  });

  it("отмена и повтор одни на всё", async () => {
    const { ctx, bus } = make();
    await bus.line("плюс 5");
    await bus.line("плюс 1");
    expect(bus.undoTitle).toBe("Прибавить");
    bus.undo();
    expect(ctx.n).toBe(5);
    bus.undo();
    expect(ctx.n).toBe(0);
    expect(bus.canUndo).toBe(false);
    bus.redo();
    expect(ctx.n).toBe(5);
    await bus.line("плюс 10");                       // новая правка гасит повтор
    expect(bus.canRedo).toBe(false);
    expect(ctx.n).toBe(15);
  });

  it("команда без отмены не попадает в стек", async () => {
    const { ctx, bus } = make();
    await bus.line('сказать "два слова" «и ещё»');
    expect(ctx.log).toEqual(["два слова и ещё"]);
    expect(bus.canUndo).toBe(false);
  });

  it("пустая строка — повтор последней, как в AutoCAD", async () => {
    const { ctx, bus } = make();
    expect((await bus.line("")).ok).toBe(false);
    await bus.line("плюс 2");
    await bus.line("");
    expect(ctx.n).toBe(4);
  });

  it("ошибки — по-русски в журнале", async () => {
    const { bus } = make();
    expect((await bus.line("сломать")).text).toBe("Так нельзя");
    expect((await bus.line("упасть")).text).toBe("Команда «Упасть» не выполнилась: boom");
    expect((await bus.line("нечто")).text).toMatch(/^Нет команды «нечто»/);
    expect((await bus.line("с")).text).toMatch(/не одна: сказать, сломать/);
    expect(bus.journal.filter(e => !e.ok).length).toBe(4);
  });

  it("имена не повторяются", () => {
    const { bus } = make();
    expect(() => bus.register({ id: "ещё", title: "x", aliases: ["add"], run: () => {} })).toThrow(/уже занято/);
  });

  it("разбор строки", () => {
    expect(splitLine('открыть "Мой проект" 2')).toEqual(["открыть", "Мой проект", "2"]);
  });
});
