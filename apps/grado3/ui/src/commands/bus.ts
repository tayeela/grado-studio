/* ГРАДО · шина команд (план 09.11.2026, шаг И1): любое действие программы — команда с именем, подписью и отменой.
   Одна отмена (Ctrl+Z) и один повтор на всю программу вместо своей в каждом окне; любую команду можно набрать в
   командной строке (как в AutoCAD: русское имя или английский псевдоним, начало имени, Enter — повтор последней).
   Каждое выполнение пишется в журнал. Чистый TypeScript без Vue: реактивность даёт stores/commands.ts.
   Устройство взято у deckcraft (MIT/Apache, как apps/grado2/ui/src/sheet/commands.js). Проверка: bus.test.ts. */

/** Что команда умеет отменить. Возвращает её run(); нет отмены — команда ничего в проекте не меняла. */
export interface Undo {
  undo(): void;
  redo(): void;
}

export interface Command<C = unknown> {
  /** имя в командной строке: русское, одним словом или через дефис */
  id: string;
  /** подпись для меню, журнала и отмены: «Скрыть слой» */
  title: string;
  /** английские и короткие имена: OPEN, Z, U… */
  aliases?: string[];
  /** что набирать после имени: «<ключ слоя>» */
  args?: string;
  /** подсказка одной строкой */
  hint?: string;
  run(ctx: C, args: string[]): Undo | void | Promise<Undo | void>;
}

export interface Entry {
  at: number;
  id: string;
  title: string;
  args: string[];
  ok: boolean;
  /** ответ команды или текст ошибки, по-русски */
  text: string;
}

/** Ошибка команды: текст увидит человек, по-русски. */
export class CommandError extends Error {}

const norm = (s: string) => s.trim().toLowerCase().replace(/ё/g, "е");

/** Разбор строки: слова через пробел, «в кавычках» — одно слово. */
export function splitLine(line: string): string[] {
  const out: string[] = [];
  const re = /"([^"]*)"|«([^»]*)»|(\S+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(line))) out.push(m[1] ?? m[2] ?? m[3]);
  return out;
}

export class Bus<C> {
  private cmds: Command<C>[] = [];
  private done: { title: string; u: Undo }[] = [];
  private undone: { title: string; u: Undo }[] = [];
  readonly journal: Entry[] = [];
  private last: string | null = null;
  private reply: string | null = null;      // ответ выполняемой команды (say), уходит в её запись журнала
  private running = 0;
  /** зовётся после любого изменения: журнал, отмена, повтор (stores/commands.ts обновляет экран) */
  onChange: () => void = () => {};
  /** сколько шагов отмены держать */
  limit = 200;

  constructor(private ctx: C) {}

  register(...list: Command<C>[]): void {
    for (const c of list) {
      const names = [c.id, ...(c.aliases || [])].map(norm);
      const clash = this.cmds.find(x => [x.id, ...(x.aliases || [])].map(norm).some(n => names.includes(n)));
      if (clash) throw new Error(`имя команды «${c.id}» уже занято командой «${clash.id}»`);
      this.cmds.push(c);
    }
  }

  list(): readonly Command<C>[] {
    return this.cmds;
  }

  /** Команда по имени: точное имя или псевдоним, затем единственное начало имени. */
  find(name: string): Command<C> | null {
    const n = norm(name);
    if (!n) return null;
    const exact = this.cmds.find(c => norm(c.id) === n || (c.aliases || []).some(a => norm(a) === n));
    if (exact) return exact;
    const pre = this.cmds.filter(c => norm(c.id).startsWith(n));
    return pre.length === 1 ? pre[0] : null;
  }

  /** Подсказки для набора: имена, начинающиеся с набранного. */
  complete(prefix: string): Command<C>[] {
    const n = norm(prefix);
    return this.cmds.filter(c => norm(c.id).startsWith(n) || (c.aliases || []).some(a => norm(a).startsWith(n)));
  }

  /** Строка командной строки. Пустая — повтор последней команды, как в AutoCAD. */
  async line(text: string): Promise<Entry> {
    const words = splitLine(text);
    if (!words.length) {
      if (!this.last) return this.note("", "Нечего повторить: команд ещё не было", false);
      return this.line(this.last);
    }
    const c = this.find(words[0]);
    if (!c) {
      const near = this.complete(words[0]).map(x => x.id);
      return this.note(words[0], near.length ? `Команда «${words[0]}» не одна: ${near.join(", ")}` :
        `Нет команды «${words[0]}». Список — команда «команды»`, false);
    }
    return this.exec(c.id, words.slice(1), text);
  }

  /** Выполняет команду по id. Отменяемый результат — в стек отмены, стек повтора очищается. */
  async exec(id: string, args: string[] = [], text?: string): Promise<Entry> {
    const c = this.find(id);
    if (!c) return this.note(id, `Нет команды «${id}»`, false);
    let res: Undo | void;
    this.running++;
    this.reply = null;
    try {
      res = await c.run(this.ctx, args);
    } catch (e) {
      const msg = e instanceof CommandError ? e.message : `Команда «${c.title}» не выполнилась: ${(e as Error).message}`;
      return this.note(c.id, msg, false, c.title, args);
    } finally {
      this.running--;
    }
    if (res) {
      this.done.push({ title: c.title, u: res });
      if (this.done.length > this.limit) this.done.shift();
      this.undone = [];
    }
    if (c.id !== "отменить" && c.id !== "вернуть") this.last = text ?? [c.id, ...args].join(" ");
    const reply = this.reply ?? c.title;
    this.reply = null;
    return this.note(c.id, reply, true, c.title, args);
  }

  /** Ответ команды человеку («Сохранено: …»): во время выполнения — текст её записи в журнале, иначе — последней записи. */
  say(text: string): void {
    if (this.running) { this.reply = text; return; }
    const e = this.journal[this.journal.length - 1];
    if (e) e.text = text;
    this.onChange();
  }

  get canUndo(): boolean {
    return this.done.length > 0;
  }
  get canRedo(): boolean {
    return this.undone.length > 0;
  }
  /** что отменит Ctrl+Z: подпись последней команды */
  get undoTitle(): string | null {
    return this.done[this.done.length - 1]?.title ?? null;
  }
  get redoTitle(): string | null {
    return this.undone[this.undone.length - 1]?.title ?? null;
  }

  undo(): string | null {
    const s = this.done.pop();
    if (!s) return null;
    s.u.undo();
    this.undone.push(s);
    this.onChange();
    return s.title;
  }

  redo(): string | null {
    const s = this.undone.pop();
    if (!s) return null;
    s.u.redo();
    this.done.push(s);
    this.onChange();
    return s.title;
  }

  /** Новый проект — история прежнего не относится к нему. */
  resetHistory(): void {
    this.done = [];
    this.undone = [];
    this.onChange();
  }

  private note(id: string, text: string, ok: boolean, title = id, args: string[] = []): Entry {
    const e: Entry = { at: Date.now(), id, title, args, ok, text };
    this.journal.push(e);
    if (this.journal.length > 500) this.journal.shift();
    this.onChange();
    return e;
  }
}

/** Отмена для простой правки: поставить значение и вернуть прежнее. */
export function setter<T>(get: () => T, set: (v: T) => void, value: T): Undo {
  const before = get();
  set(value);
  return { undo: () => set(before), redo: () => set(value) };
}
