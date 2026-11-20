/* Ядро в WebAssembly считает как Python-эталон: rust/parity/crs/reference.json (тот же файл, что сверяет Rust бит-в-бит).
   В браузере библиотека math у WebAssembly своя, поэтому здесь допуск: метры — 1e-8 м, градусы — 1e-13°. */
import { readFileSync } from "node:fs";
import { describe, expect, it, beforeAll } from "vitest";
import {
  areaMsk, checkProject, formatVersion, hasLinetype, lengthMsk, linetypeOps,
  loadCore, loadLinetypes, migrateProject, mskToWgs, mskToWgsMany, overlayAreaMsk, partsOps, unionAreaMsk, wgsToMsk,
} from "./core";

const here = (p: string) => new URL(p, import.meta.url);

beforeAll(async () => { await loadCore({ module_or_path: readFileSync(here("./wasm/grado_core_wasm_bg.wasm")) }); });

describe("координаты", () => {
  const ref: { fn: string; in: [number, number]; out: [number, number] }[] =
    JSON.parse(readFileSync(here("../../../../rust/parity/crs/reference.json"), "utf8"));
  it("МСК → WGS84 как в Python", () => {
    const cases = ref.filter(c => c.fn === "msk_to_wgs84");
    expect(cases.length).toBeGreaterThan(300);
    for (const c of cases) {
      const g = mskToWgs(c.in);
      expect(Math.abs(g[0] - c.out[0])).toBeLessThan(1e-13);
      expect(Math.abs(g[1] - c.out[1])).toBeLessThan(1e-13);
    }
  });
  it("WGS84 → МСК как в Python", () => {
    for (const c of ref.filter(c => c.fn === "wgs84_to_msk")) {
      const g = wgsToMsk(c.in);
      expect(Math.abs(g[0] - c.out[0])).toBeLessThan(1e-8);
      expect(Math.abs(g[1] - c.out[1])).toBeLessThan(1e-8);
    }
  });
  it("много точек = по одной", () => {
    const one = mskToWgs([1500, -2500]);
    expect(Array.from(mskToWgsMany(new Float64Array([1500, -2500])))).toEqual(one);
  });
});

describe("проект", () => {
  it("проверка образца и ошибок", () => {
    const text = readFileSync(here("../../../grado2/tests/fixtures/next_ui_project.grado2"), "utf8");
    const r = checkProject(text);
    expect(r.ok).toBe(true);
    expect(r.layers).toBe(7);
    const bad = checkProject('{"format":"grado2","version":9}');
    expect(bad.ok).toBe(false);
    expect(bad.issues[0].text).toMatch(/более новой программой/);
    expect(formatVersion()).toBe(2);
  });
  it("перевод «потолок» — как migrate.js", () => {
    const inp = readFileSync(here("../../../../rust/crates/model/tests/data/migrate_in.json"), "utf8");
    const out = JSON.parse(readFileSync(here("../../../../rust/crates/model/tests/data/migrate_out.json"), "utf8"));
    expect(JSON.parse(migrateProject(inp))).toEqual(out);
  });
});

describe("геометрия МСК и рисование знаков (шаги С2 и И2)", () => {
  it("площадь, объединение, пересечение и длина в МСК", () => {
    const ring = [[0, 0], [100, 0], [100, 50], [0, 50], [0, 0]].map(([x, y]) => mskToWgs([x, y]));
    const feat = { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [ring] } };
    expect(Math.abs(areaMsk(feat) - 5000)).toBeLessThan(0.05);
    expect(Math.abs(unionAreaMsk({ type: "FeatureCollection", features: [feat, feat] }) - 5000)).toBeLessThan(0.05);
    const clipRing = [[50, 0], [150, 0], [150, 50], [50, 50], [50, 0]].map(([x, y]) => mskToWgs([x, y]));
    const clip = { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [clipRing] } };
    expect(Math.abs(overlayAreaMsk(feat, clip) - 2500)).toBeLessThan(0.05);
    const line = { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [mskToWgs([0, 0]), mskToWgs([30, 40])] } };
    expect(Math.abs(lengthMsk(line) - 50)).toBeLessThan(0.01);
  });
  it("части знака и типы линий ЛГР через ядро Rust", () => {
    const ops = partsOps("poly", [[[[0, 0], [100, 0], [100, 100], [0, 100]]]], [{ k: "band", b: 5, c: "#2446d8", a: 0.4 }], 1);
    expect(ops.map(o => o.op)).toEqual(["clip", "path", "unclip"]);
    const lib = readFileSync(here("../../../../core/render/grado_render/styles/redln97.json"), "utf8");
    expect(loadLinetypes(lib)).toBe(true);
    expect(hasLinetype("L00s01s")).toBe(true);
    const lops = linetypeOps([[0, 0], [400, 0]], "L00s01s", 2, 0, "#e01b24", 1.5);
    expect(lops.length).toBeGreaterThanOrEqual(1);
    expect(lops[0].rings.length).toBeGreaterThan(1);
  });
});
