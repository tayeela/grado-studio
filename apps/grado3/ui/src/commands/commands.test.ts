/* Команды каркаса на образце проекта: открыть, скрыть и показать слой, граница, отмена, сохранение (сервер подменён). */
import { readFileSync } from "node:fs";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { loadCore } from "../core";
import { useCommands } from "../stores/commands";
import { useProject } from "../stores/project";
import { useUi } from "../stores/ui";

const here = (p: string) => new URL(p, import.meta.url);
const FIXTURE = readFileSync(here("../../../../grado2/tests/fixtures/next_ui_project.grado2"), "utf8");

beforeAll(async () => { await loadCore({ module_or_path: readFileSync(here("../wasm/grado_core_wasm_bg.wasm")) }); });

let saved: { url: string; body: string }[] = [];
beforeEach(() => {
  setActivePinia(createPinia());
  saved = [];
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    if (init?.method === "POST") { saved.push({ url, body: String(init.body) }); return new Response(JSON.stringify({ saved: "Тест", modified: 2 })); }
    if (url.startsWith("/api/projects")) return new Response(JSON.stringify({ dir: "/x", projects: [{ name: "Тест", modified: 1, size: 1 }] }));
    if (url.startsWith("/api/project?name=")) return new Response(FIXTURE, { headers: { "X-Grado-Modified": "1.5" } });
    return new Response("{}", { status: 404 });
  });
});

describe("команды каркаса", () => {
  it("открыть, скрыть, отменить, вернуть, сохранить", async () => {
    const cmd = useCommands(), p = useProject();
    expect((await cmd.run("скрыть egko.buildings")).text).toMatch(/Проект не открыт/);
    const e = await cmd.run("открыть Тест");
    expect(e.ok).toBe(true);
    expect(e.text).toMatch(/Открыт «Тест»: слоёв 7/);
    expect(p.base).toBe(1.5);
    const key = p.layers[0].key;
    await cmd.run("скрыть " + key);
    expect(p.layer(key)!.visible).toBe(false);
    expect(p.dirty).toBe(true);
    await cmd.run("U");
    expect(p.layer(key)!.visible).toBe(true);
    await cmd.run("вернуть");
    expect(p.layer(key)!.visible).toBe(false);
    await cmd.run("переименовать " + key + " Новое имя");
    expect((await cmd.run("сохранить")).text).toBe("Сохранено: «Тест»");
    expect(saved[0].url).toBe("/api/project?name=%D0%A2%D0%B5%D1%81%D1%82&base=1.5");
    const out = JSON.parse(saved[0].body);
    expect(out.layers[0].title).toBe("Новое имя");
    expect(out.layers[0].visible).toBe(false);
    expect(out.data).toEqual(JSON.parse(FIXTURE).data);        // данные слоёв ушли как были
    expect(out.album).toEqual(JSON.parse(FIXTURE).album);      // то, что окно не правит, — тоже
    expect(p.base).toBe(2);
  });

  it("граница — роль одного слоя, отменяется", async () => {
    const cmd = useCommands(), p = useProject();
    await cmd.run("открыть Тест");
    const polys = p.layers.filter(l => l.geom === "poly");
    await cmd.run("граница " + polys[0].key);
    await cmd.run("граница " + polys[1].key);
    expect(p.layers.filter(l => l.role === "territory").map(l => l.key)).toEqual([polys[1].key]);
    await cmd.run("отменить");
    expect(p.territory?.key).toBe(polys[0].key);
    const line = p.layers.find(l => l.geom === "line")!;
    expect((await cmd.run("граница " + line.key)).text).toMatch(/только слой полигонов/);
  });

  it("рабочее место по номеру и названию", async () => {
    const cmd = useCommands(), ui = useUi();
    await cmd.run("место 4");
    expect(ui.ws).toBe("sheets");
    await cmd.run("место выдача");
    expect(ui.ws).toBe("out");
    expect((await cmd.run("место 9")).ok).toBe(false);
  });
});
