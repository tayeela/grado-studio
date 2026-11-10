/* ГРАДО · шина команд в окне: одна на программу (commands/bus.ts), журнал и признаки отмены реактивны для экрана. */
import { defineStore } from "pinia";
import { ref, shallowRef } from "vue";
import { Bus, type Entry } from "../commands/bus";
import { builtins, type Ctx } from "../commands/builtin";
import { useProject } from "./project";
import { useUi } from "./ui";

export const useCommands = defineStore("commands", () => {
  const ctx: Ctx = { project: useProject(), ui: useUi() };
  const bus = new Bus<Ctx>(ctx);
  bus.register(...builtins(bus));
  const tick = ref(0);
  const journal = shallowRef<Entry[]>([]);
  bus.onChange = () => { tick.value++; journal.value = [...bus.journal]; };
  const run = (line: string) => bus.line(line);
  return { bus, tick, journal, run };
});
