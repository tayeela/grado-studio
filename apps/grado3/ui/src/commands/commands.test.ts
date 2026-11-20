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

const PARCEL_FEAT = {
  type: "Feature" as const,
  properties: { "Кадастровый номер": "77:01:0001001:10", "ВРИ": "Жилая застройка" },
  geometry: {
    type: "Polygon",
    coordinates: [[[37.61, 55.75], [37.612, 55.75], [37.612, 55.751], [37.61, 55.751], [37.61, 55.75]]],
  },
};

let saved: { url: string; body: string }[] = [];
beforeEach(() => {
  setActivePinia(createPinia());
  saved = [];
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    if (init?.method === "POST") { saved.push({ url, body: String(init.body) }); return new Response(JSON.stringify({ saved: "Тест", modified: 2 })); }
    if (url.startsWith("/api/projects")) return new Response(JSON.stringify({ dir: "/x", projects: [{ name: "Тест", modified: 1, size: 1 }] }));
    if (url.startsWith("/api/project?name=")) return new Response(FIXTURE, { headers: { "X-Grado-Modified": "1.5" } });
    if (url.startsWith("/api/search/parcel_at")) return new Response(JSON.stringify({ features: [PARCEL_FEAT] }));
    if (url.startsWith("/api/search?q=77")) return new Response(JSON.stringify({ type: "cadastral", features: [PARCEL_FEAT], missing: [], notes: [] }));
    if (url.startsWith("/api/search?q=")) return new Response(JSON.stringify({ type: "address", results: [{ name: "Тверская, 1", display: "Москва, Тверская, 1", lon: 37.611, lat: 55.7505 }] }));
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

  it("шаг И2: поиск адреса и участка, участок под адресом — границей, отмена Ctrl+Z", async () => {
    const cmd = useCommands(), p = useProject(), ui = useUi();
    await cmd.run("открыть Тест");
    const rAddr = await cmd.run("найти Тверская 1");
    expect(rAddr.ok).toBe(true);
    expect(ui.search?.type).toBe("address");
    expect(ui.search?.addresses[0].name).toBe("Тверская, 1");

    const rBound = await cmd.run('адрес-граница 37.611 55.7505 "Тверская, 1"');
    expect(rBound.ok).toBe(true);
    expect(p.territory?.key).toBe("user:territory");
    expect(p.territoryAreaM2).toBeGreaterThan(1000);
    expect(p.layerCount("nspd.parcels")).toBeGreaterThanOrEqual(1);

    await cmd.run("отменить");
    expect(p.territory).toBeNull();
    await cmd.run("вернуть");
    expect(p.territory?.key).toBe("user:territory");

    // повторный поиск участка с тем же кадастровым номером не дублирует его в слое ЕГРН
    const countBefore = p.layerCount("nspd.parcels");
    await cmd.run("найти 77:01:0001001:10");
    expect(ui.search?.type).toBe("cadastral");
    await cmd.run("участки-на-карту");
    expect(p.layerCount("nspd.parcels")).toBe(countBefore);

    await cmd.run("граница нет");
    expect(p.territory).toBeNull();
    await cmd.run("граница-пример");
    expect(p.territoryAreaM2).toBeGreaterThan(100000);
  });

  it("шаг И2: группы, порядок слоёв, удаление слоя и подложка с отменой", async () => {
    const cmd = useCommands(), p = useProject();
    await cmd.run("открыть Тест");
    const n0 = p.layers.length;
    const firstKey = p.layers[0].key;
    const secondKey = p.layers[1].key;

    await cmd.run("группа Исходные данные");
    const gid = p.groups[p.groups.length - 1].id;
    await cmd.run(`в-группу ${firstKey} ${gid}`);
    expect(p.layer(firstKey)?.group).toBe(gid);
    await cmd.run(`группа-скрыть ${gid}`);
    expect(p.shown(p.layer(firstKey)!)).toBe(false);
    await cmd.run("отменить");
    expect(p.shown(p.layer(firstKey)!)).toBe(true);

    await cmd.run(`ниже ${firstKey}`);
    expect(p.layers[0].key).toBe(secondKey);
    await cmd.run("отменить");
    expect(p.layers[0].key).toBe(firstKey);

    await cmd.run(`удалить-слой ${firstKey}`);
    expect(p.layers.length).toBe(n0 - 1);
    expect(p.layer(firstKey)).toBeNull();
    await cmd.run("отменить");
    expect(p.layers.length).toBe(n0);
    expect(p.layer(firstKey)).not.toBeNull();

    await cmd.run("подложка спутник");
    expect(p.basemap).toBe("esri");
    await cmd.run("отменить");
    expect(p.basemap).toBe("osm");
  });
});
