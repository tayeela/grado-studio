/* Команды каркаса на образце проекта: открыть, скрыть и показать слой, граница, отмена, сохранение (сервер подменён). */
import { readFileSync } from "node:fs";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { loadCore } from "../core";
import { SYMBOL_LIBRARY, ZOUIT_HATCH, type LayerStyle } from "../symbology";
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

const ZOUIT_FEAT = {
  type: "Feature" as const,
  properties: { "Вид зоны": "Водоохранная зона", "Наименование": "Водоохранная зона р. Москвы" },
  geometry: {
    type: "Polygon",
    coordinates: [[[37.52, 55.79], [37.525, 55.79], [37.525, 55.794], [37.52, 55.794], [37.52, 55.79]]],
  },
};

let saved: { url: string; body: string }[] = [];
beforeEach(() => {
  setActivePinia(createPinia());
  saved = [];
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    if (url === "/api/fetch" && init?.method === "POST") {
      return new Response(JSON.stringify({
        layers: {
          "gisogd.zouit": {
            title: "ЗОУИТ (ОГД)",
            source: "ГИС ОГД Москвы",
            fetched_at: "2026-11-20",
            features: { type: "FeatureCollection", features: [ZOUIT_FEAT] },
          },
          "ogd.virtual138": {
            title: "Природные и озеленённые территории",
            source: "ГИС ОГД Москвы",
            fetched_at: "2026-11-20",
            features: { type: "FeatureCollection", features: [ZOUIT_FEAT] },
          },
        },
        errors: {},
      }));
    }
    if (url === "/api/ogd_all/styles" && init?.method === "POST") {
      return new Response(JSON.stringify({
        styles: { virtual138: { mode: "single", fill: "#009f3c", opacity: 0.2, stroke: "#009f3c", lgrLine: 18 } },
        rev: { virtual138: 2 },
      }));
    }
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

  it("шаг И3: загрузка ЗОУИТ с автостилем, правка стиля и слоёв знака, правка атрибута и отмена Ctrl+Z", async () => {
    const cmd = useCommands(), p = useProject(), ui = useUi();
    await cmd.run("открыть Тест");
    await cmd.run("граница-пример");

    const rLoad = await cmd.exec("загрузить", ["gisogd.zouit", "ogd.virtual138"]);
    expect(rLoad.ok).toBe(true);
    const zouit = p.layer("gisogd.zouit")!;
    expect(zouit).not.toBeNull();
    const zSt = zouit.style as LayerStyle;
    expect(zSt.mode).toBe("cat");
    expect(zSt.hatch).toBe(true);
    expect(zSt.cat?.colors?.["Водоохранная зона"]).toBe(ZOUIT_HATCH["Водоохранная зона"]);

    const pk = p.layer("ogd.virtual138")!;
    expect((pk.style as LayerStyle).lgrLine).toBe(18);
    expect(ui.selectedLayer).toBe("gisogd.zouit");

    // применение знака из библиотеки (с частью знака band) + отмена
    const bandPreset = SYMBOL_LIBRARY.find(x => x.id === "zouit_band")!;
    await cmd.exec("стиль", ["gisogd.zouit", JSON.stringify(bandPreset.style)]);
    expect((p.layer("gisogd.zouit")!.style as LayerStyle).parts?.[0]?.k).toBe("band");
    await cmd.run("отменить");
    expect((p.layer("gisogd.zouit")!.style as LayerStyle).mode).toBe("cat");

    // прозрачность слоя + отмена
    await cmd.exec("слой-прозрачность", ["gisogd.zouit", "0.5"]);
    expect(p.layer("gisogd.zouit")!.layerOpacity).toBe(0.5);
    await cmd.run("отменить");
    expect(p.layer("gisogd.zouit")!.layerOpacity).toBe(1);

    // правка атрибута в таблице + _edited + отмена
    await cmd.exec("атрибут", ["gisogd.zouit", "0", "Вид зоны", "Прибрежная защитная полоса"]);
    const feat = p.data("gisogd.zouit")!.features[0];
    expect(feat.properties?.["Вид зоны"]).toBe("Прибрежная защитная полоса");
    expect(feat.properties?._edited).toBe(true);
    await cmd.run("отменить");
    expect(feat.properties?.["Вид зоны"]).toBe("Водоохранная зона");
    expect(feat.properties?._edited).toBeUndefined();

    // отмена загрузки убирает загруженные слои целиком
    await cmd.run("отменить");
    expect(p.layer("gisogd.zouit")).toBeNull();
    expect(p.layer("ogd.virtual138")).toBeNull();
    await cmd.run("вернуть");
    expect(p.layer("gisogd.zouit")).not.toBeNull();
  });
});
