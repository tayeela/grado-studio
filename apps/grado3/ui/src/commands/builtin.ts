/* ГРАДО · команды программы (план 09.11.2026, шаги И1 и И2): проект, отмена, рабочие места, слои и группы, граница
   территории (роль слоя, по участкам, по адресу, по КРТ, пример), поиск, подложка, карта, справка. Любое действие —
   команда с отменой Ctrl+Z. Имена — русские, псевдонимы — как в AutoCAD. Проверка: commands.test.ts. */
import { CommandError, setter, type Bus, type Command, type Undo } from "./bus";
import { unionAreaMsk, wgsToMsk } from "../core";
import { WORKSPACES, workspace } from "../workspaces";
import {
  BASEMAPS, EXAMPLE_RING, PARCELS_KEY, TERR_KEY,
  type FeatureCollection, type GeoFeature, type ProjectStore,
} from "../stores/project";
import type { AddressHit, UiStore } from "../stores/ui";
import type { Group, Layer, LayerData } from "../types/project";

export interface Ctx {
  project: ProjectStore;
  ui: UiStore;
}

const today = () => new Date().toISOString().slice(0, 10);
const fmtHa = (m2: number): string => {
  const ha = m2 / 1e4;
  return ha.toLocaleString("ru-RU", { minimumFractionDigits: ha < 1 ? 4 : 2, maximumFractionDigits: ha < 1 ? 4 : 2 }) + " га";
};

const need = (c: Ctx) => {
  if (!c.project.doc) throw new CommandError("Проект не открыт: команда «открыть <название>»");
};

const layerOf = (c: Ctx, key: string | undefined): Layer => {
  need(c);
  const q = (key || "").trim();
  if (!q) throw new CommandError("Нужен ключ слоя: он виден в окне «Слои»");
  const l = c.project.layer(q) || c.project.layers.find(x => (x.title || "").toLowerCase() === q.toLowerCase());
  if (!l) throw new CommandError(`Слоя «${q}» в проекте нет`);
  return l;
};

const groupOf = (c: Ctx, id: string | undefined): Group => {
  need(c);
  const q = (id || "").trim();
  if (!q) throw new CommandError("Нужен id или название группы");
  const g = c.project.group(q) || c.project.groups.find(x => (x.title || "").toLowerCase() === q.toLowerCase());
  if (!g) throw new CommandError(`Группы «${q}» в проекте нет`);
  return g;
};

/** правка слоя с отменой: значение поля, отметка «есть правки», перерисовка карты */
const edit = <K extends keyof Layer>(c: Ctx, l: Layer, field: K, value: Layer[K]): Undo =>
  setter(() => l[field], v => { l[field] = v; c.project.touch(); c.ui.map.api?.refresh(); }, value);

const editGroup = <K extends keyof Group>(c: Ctx, g: Group, field: K, value: Group[K]): Undo =>
  setter(() => g[field], v => { g[field] = v; c.project.touch(); c.ui.map.api?.refresh(); }, value);

const num = (s: string | undefined, what: string) => {
  const v = Number(String(s ?? "").replace(",", "."));
  if (!Number.isFinite(v)) throw new CommandError(`${what}: нужно число, а набрано «${s ?? ""}»`);
  return v;
};

const cloneLayers = (ls: Layer[]): Layer[] => ls.map(l => ({ ...l }));

/** Добавляет полигоны участков в слой nspd.parcels без повторов (по кадастровому номеру или _key). */
function mergeParcelsData(c: Ctx, feats: GeoFeature[]): { prevLayers: Layer[]; prevData: LayerData | undefined } {
  const prevLayers = cloneLayers(c.project.layers);
  const prevData = c.project.dataEntry(PARCELS_KEY);
  const oldFeats = ((prevData?.fc as FeatureCollection | undefined)?.features || []).slice();
  const seen = new Set(
    oldFeats
      .map(f => String(f.properties?.["Кадастровый номер"] || f.properties?._key || ""))
      .filter(Boolean),
  );
  const merged = [...oldFeats];
  for (const f of feats) {
    const id = String(f.properties?.["Кадастровый номер"] || f.properties?._key || "");
    if (id && seen.has(id)) continue;
    if (id) seen.add(id);
    merged.push(f);
  }
  c.project.setLayerData(PARCELS_KEY, {
    ...(prevData || {}),
    title: prevData?.title || "Земельные участки (ЕГРН)",
    source: prevData?.source || "НСПД (ЕГРН)",
    fetched_at: today(),
    fc: { type: "FeatureCollection", features: merged },
  });
  if (!c.project.layer(PARCELS_KEY)) {
    c.project.layers.unshift({
      key: PARCELS_KEY,
      title: "Земельные участки (ЕГРН)",
      geom: "poly",
      visible: true,
      group: null,
      style: { mode: "single", fill: "#2a78d6", opacity: 0.2, stroke: "#1a4f94", width: 1.5 },
    });
  }
  return { prevLayers, prevData };
}

/** Записывает полигоны в слой границы user:territory (и при необходимости в nspd.parcels) с полной отменой Ctrl+Z. */
export function applyTerritoryPolygons(c: Ctx, feats: GeoFeature[], addToParcels: boolean, title = "Граница территории", source = "граница территории, задана в ГРАДО"): Undo {
  const polys = feats.filter(f => /Polygon/.test(f.geometry?.type || ""));
  if (!polys.length) throw new CommandError("У выбранных объектов нет площадного контура");
  const prevLayers = cloneLayers(c.project.layers);
  const prevTerrData = c.project.dataEntry(TERR_KEY);
  const prevParcelsData = c.project.dataEntry(PARCELS_KEY);

  const apply = () => {
    if (addToParcels) mergeParcelsData(c, polys);
    c.project.setLayerData(TERR_KEY, {
      ...(prevTerrData || {}),
      title: prevTerrData?.title || title,
      source: prevTerrData?.source || source,
      fetched_at: today(),
      fc: { type: "FeatureCollection", features: polys },
    });
    for (const l of c.project.layers) if (l.role === "territory" && l.key !== TERR_KEY) l.role = null;
    let tl = c.project.layer(TERR_KEY);
    if (!tl) {
      tl = {
        key: TERR_KEY,
        title,
        geom: "poly",
        visible: true,
        group: null,
        role: "territory",
        style: { mode: "single", fill: "#2446d8", opacity: 0.06, stroke: "#2446d8", width: 2.5, dash: [8, 5] },
      };
      c.project.layers.unshift(tl);
    } else {
      tl.role = "territory";
      tl.geom = "poly";
    }
    c.project.touch();
    c.ui.map.api?.refresh(true);
    c.ui.map.api?.fit(TERR_KEY);
  };

  apply();
  return {
    undo: () => {
      c.project.setLayerData(TERR_KEY, prevTerrData);
      if (addToParcels) c.project.setLayerData(PARCELS_KEY, prevParcelsData);
      c.project.layers = cloneLayers(prevLayers);
      c.project.touch();
      c.ui.map.api?.refresh(true);
    },
    redo: apply,
  };
}

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
        c.ui.map.api?.clearMark();
        c.ui.map.api?.syncBasemap();
        c.ui.map.api?.refresh(true);
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
      id: "граница", title: "Слой-граница территории", aliases: ["BOUNDARY"], args: "<ключ слоя | нет>",
      hint: "роль границы у слоя: отдельного инструмента нет; «граница нет» снимает роль",
      run(c, a) {
        need(c);
        const arg = a.join(" ").trim();
        const clear = /^(нет|none|off|снять|-)$/i.test(arg);
        const l = clear ? null : layerOf(c, arg);
        if (l && l.geom && l.geom !== "poly") throw new CommandError("Границей может быть только слой полигонов");
        const before = c.project.layers.map(x => [x, x.role] as const);
        const apply = () => {
          for (const x of c.project.layers) x.role = l && x === l ? "territory" : (x.role === "territory" ? null : x.role);
          c.project.touch();
          c.ui.map.api?.refresh();
        };
        apply();
        if (l) bus.say(`Граница территории — слой «${l.title || l.key}» (${fmtHa(c.project.territoryAreaM2)})`);
        else bus.say("Роль границы территории снята");
        return { undo: () => { for (const [x, r] of before) x.role = r; c.project.touch(); c.ui.map.api?.refresh(); }, redo: apply };
      },
    },
    {
      id: "граница-пример", title: "Поставить границу-пример", aliases: ["BEXAMPLE"],
      hint: "учебный контур территории для быстрой проверки",
      run(c) {
        need(c);
        const feat: GeoFeature = { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [EXAMPLE_RING] } };
        const u = applyTerritoryPolygons(c, [feat], false, "Граница территории", "граница-пример ГРАДО");
        bus.say(`Граница-пример: ${fmtHa(c.project.territoryAreaM2)}`);
        return u;
      },
    },
    {
      id: "найти", title: "Поиск по адресу, кадастровому номеру или № КРТ", aliases: ["FIND", "SEARCH"], args: "<запрос>",
      hint: "найти адрес (OSM), участок (НСПД) или КРТ (ГИС ОГД)",
      async run(c, a) {
        const q = a.join(" ").trim();
        if (!q) throw new CommandError("Что искать? Укажите адрес, кадастровый номер (77:…) или номер КРТ");
        let r: Response;
        try {
          r = await fetch("/api/search?q=" + encodeURIComponent(q), { headers: { Accept: "application/json" } });
        } catch {
          throw new CommandError("Нет связи с программой ГРАДО — повторите поиск");
        }
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new CommandError(j.error || `Поиск не удался (${r.status})`);
        if (j.type === "krt") {
          const features = (j.features || []) as GeoFeature[];
          const cards = (j.cards || []) as string[];
          if (!features.length) throw new CommandError(`Номер ${(j.missing || [])[0] || q} не найден в слое КРТ`);
          c.ui.search = { q, type: "krt", addresses: [], features, cards, missing: j.missing || [], notes: j.notes || [], picked: 0 };
          c.ui.map.api?.markFeatures(features);
          bus.say(`Найдено КРТ: ${cards[0] || features.length}`);
        } else if (j.type === "cadastral") {
          const features = (j.features || []) as GeoFeature[];
          if (!features.length) throw new CommandError((j.notes || [])[0] || `Участок «${q}» не найден в НСПД`);
          c.ui.search = { q, type: "cadastral", addresses: [], features, cards: [], missing: j.missing || [], notes: j.notes || [], picked: 0 };
          c.ui.map.api?.markFeatures(features);
          bus.say(`Найдено участков: ${features.length} (${fmtHa(unionAreaMsk({ type: "FeatureCollection", features }))})`);
        } else {
          const addresses = (j.results || []) as AddressHit[];
          if (!addresses.length) throw new CommandError("Ничего не нашлось в Москве и области");
          c.ui.search = { q, type: "address", addresses, features: [], cards: [], missing: [], notes: j.notes || [], picked: 0 };
          const x = addresses[0];
          c.ui.map.api?.markAddress(x.lon, x.lat, x.bbox);
          bus.say(`Найден адрес: ${x.name || x.display || q}`);
        }
      },
    },
    {
      id: "участок", title: "Участок по кадастровому номеру — границей территории", aliases: ["PARCEL"], args: "<кадастровый номер>",
      hint: "найти участок в НСПД, добавить в слой ЕГРН и сделать границей",
      async run(c, a) {
        need(c);
        const q = a.join(" ").trim();
        if (!q) throw new CommandError("Нужен кадастровый номер участка (например 77:01:0001001:1)");
        let r: Response;
        try {
          r = await fetch("/api/search?q=" + encodeURIComponent(q), { headers: { Accept: "application/json" } });
        } catch {
          throw new CommandError("Нет связи с программой ГРАДО");
        }
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new CommandError(j.error || `Поиск участка не удался (${r.status})`);
        const feats = ((j.features || []) as GeoFeature[]).filter(f => /Polygon/.test(f.geometry?.type || ""));
        if (!feats.length) throw new CommandError((j.notes || [])[0] || `Участок «${q}» с контуром не найден`);
        const u = applyTerritoryPolygons(c, feats, true, "Граница территории", `участки ЕГРН: ${q}`);
        bus.say(`Граница по участкам (${feats.length}): ${fmtHa(c.project.territoryAreaM2)}`);
        return u;
      },
    },
    {
      id: "адрес-граница", title: "Участок под адресом — границей территории", aliases: ["ADDRBOUND"],
      args: "<долгота> <широта> [название адреса]",
      hint: "найти участок ЕГРН под точкой адреса (/api/search/parcel_at) и сделать границей",
      async run(c, a) {
        need(c);
        const lon = num(a[0], "Долгота"), lat = num(a[1], "Широта");
        const label = a.slice(2).join(" ").trim() || `${lon.toFixed(5)}, ${lat.toFixed(5)}`;
        let r: Response;
        try {
          r = await fetch(`/api/search/parcel_at?lon=${lon}&lat=${lat}`, { headers: { Accept: "application/json" } });
        } catch {
          throw new CommandError("Нет связи с программой ГРАДО");
        }
        const j = await r.json().catch(() => ({}));
        if (!r.ok) throw new CommandError(j.error || "Участок под адресом не найден");
        const feats = ((j.features || []) as GeoFeature[]).filter(f => /Polygon/.test(f.geometry?.type || ""));
        if (!feats.length) throw new CommandError("У найденного под адресом участка нет контура");
        const u = applyTerritoryPolygons(c, feats, true, "Граница территории", `участок под адресом «${label}»`);
        c.ui.map.api?.clearMark();
        bus.say(`Граница — участок под адресом «${label}»: ${fmtHa(c.project.territoryAreaM2)}`);
        return u;
      },
    },
    {
      id: "участки-на-карту", title: "Добавить найденные участки в слой ЕГРН", aliases: ["PARCELSHOW"],
      run(c) {
        need(c);
        const s = c.ui.search;
        if (!s || !s.features.length) throw new CommandError("Сначала найдите участки или КРТ в окне «Поиск»");
        if (s.type === "krt") {
          c.ui.map.api?.markFeatures(s.features);
          bus.say(`На карте: ${s.cards[0] || "КРТ"}`);
          return;
        }
        const snap = mergeParcelsData(c, s.features);
        const nextData = c.project.dataEntry(PARCELS_KEY);
        const nextLayers = cloneLayers(c.project.layers);
        c.project.touch();
        c.ui.map.api?.refresh(true);
        c.ui.map.api?.fit(PARCELS_KEY);
        bus.say(`На карте: участков ${s.features.length} в слое «Земельные участки (ЕГРН)»`);
        return {
          undo: () => { c.project.setLayerData(PARCELS_KEY, snap.prevData); c.project.layers = cloneLayers(snap.prevLayers); c.project.touch(); c.ui.map.api?.refresh(true); },
          redo: () => { c.project.setLayerData(PARCELS_KEY, nextData); c.project.layers = cloneLayers(nextLayers); c.project.touch(); c.ui.map.api?.refresh(true); },
        };
      },
    },
    {
      id: "граница-по-найденному", title: "Сделать найденные участки или КРТ границей территории", aliases: ["SEARCHBOUND"],
      run(c) {
        need(c);
        const s = c.ui.search;
        if (!s || !s.features.length) throw new CommandError("Сначала найдите участки или КРТ в окне «Поиск»");
        const isKrt = s.type === "krt";
        const u = applyTerritoryPolygons(c, isKrt ? [s.features[0]] : s.features, !isKrt, "Граница территории", isKrt ? (s.cards[0] || "КРТ") : `участки: ${s.q}`);
        c.ui.map.api?.clearMark();
        bus.say(isKrt ? `Граница — ${(s.cards[0] || "КРТ").split(" · ")[0]}: ${fmtHa(c.project.territoryAreaM2)}` : `Граница по участкам (${s.features.length}): ${fmtHa(c.project.territoryAreaM2)}`);
        return u;
      },
    },
    {
      id: "группа", title: "Создать группу слоёв", aliases: ["GROUP"], args: "<название>",
      run(c, a) {
        need(c);
        const title = a.join(" ").trim();
        if (!title) throw new CommandError("Нужно название новой группы");
        const id = "grp_" + (c.project.groups.length + 1) + "_" + Math.random().toString(36).slice(2, 6);
        const g: Group = { id, title, visible: true, open: true };
        const apply = () => { c.project.groups.push({ ...g }); c.project.touch(); };
        apply();
        bus.say(`Создана группа «${title}»`);
        return {
          undo: () => { c.project.groups = c.project.groups.filter(x => x.id !== id); c.project.touch(); },
          redo: apply,
        };
      },
    },
    { id: "группа-показать", title: "Показать группу слоёв", aliases: ["GROUPON"], args: "<id или название группы>",
      run: (c, a) => editGroup(c, groupOf(c, a.join(" ")), "visible", true) },
    { id: "группа-скрыть", title: "Скрыть группу слоёв", aliases: ["GROUPOFF"], args: "<id или название группы>",
      run: (c, a) => editGroup(c, groupOf(c, a.join(" ")), "visible", false) },
    {
      id: "в-группу", title: "Переместить слой в группу", aliases: ["LAYGRP"], args: "<ключ слоя> [id группы | нет]",
      run(c, a) {
        const l = layerOf(c, a[0]);
        const target = a.slice(1).join(" ").trim();
        const gid = !target || /^(нет|none|-)$/i.test(target) ? null : groupOf(c, target).id;
        return edit(c, l, "group", gid);
      },
    },
    {
      id: "выше", title: "Поднять слой выше", aliases: ["LAYUP"], args: "<ключ слоя>",
      run(c, a) {
        const l = layerOf(c, a.join(" "));
        const i = c.project.layers.indexOf(l);
        if (i <= 0) throw new CommandError("Слой уже на самом верху");
        const swap = () => {
          const arr = c.project.layers;
          [arr[i - 1], arr[i]] = [arr[i], arr[i - 1]];
          c.project.touch();
          c.ui.map.api?.refresh();
        };
        swap();
        return { undo: swap, redo: swap };
      },
    },
    {
      id: "ниже", title: "Опустить слой ниже", aliases: ["LAYDOWN"], args: "<ключ слоя>",
      run(c, a) {
        const l = layerOf(c, a.join(" "));
        const i = c.project.layers.indexOf(l);
        if (i < 0 || i >= c.project.layers.length - 1) throw new CommandError("Слой уже в самом низу");
        const swap = () => {
          const arr = c.project.layers;
          [arr[i], arr[i + 1]] = [arr[i + 1], arr[i]];
          c.project.touch();
          c.ui.map.api?.refresh();
        };
        swap();
        return { undo: swap, redo: swap };
      },
    },
    {
      id: "удалить-слой", title: "Удалить слой", aliases: ["LAYDEL"], args: "<ключ слоя>",
      run(c, a) {
        const l = layerOf(c, a.join(" "));
        const idx = c.project.layers.indexOf(l);
        const copy = { ...l };
        const prevData = c.project.dataEntry(l.key);
        const apply = () => {
          c.project.layers = c.project.layers.filter(x => x.key !== copy.key);
          c.project.setLayerData(copy.key, undefined);
          c.project.touch();
          c.ui.map.api?.refresh(true);
        };
        apply();
        bus.say(`Удалён слой «${copy.title || copy.key}»`);
        return {
          undo: () => {
            c.project.setLayerData(copy.key, prevData);
            c.project.layers.splice(Math.min(idx, c.project.layers.length), 0, { ...copy });
            c.project.touch();
            c.ui.map.api?.refresh(true);
          },
          redo: apply,
        };
      },
    },
    {
      id: "подложка", title: "Подложка карты", aliases: ["BASEMAP"], args: "<osm | esri | s2 | none>",
      hint: Object.entries(BASEMAPS).map(([k, v]) => `${k} — ${v}`).join(", "),
      run(c, a) {
        const q = (a[0] || "").toLowerCase();
        const id = q === "спутник" ? "esri" : q === "нет" ? "none" : q;
        if (!BASEMAPS[id]) throw new CommandError("Какая подложка? " + Object.entries(BASEMAPS).map(([k, v]) => `${k} (${v})`).join(", "));
        const prev = c.project.basemap;
        const set = (v: string) => { c.project.setBasemap(v); c.ui.map.api?.syncBasemap(); };
        set(id);
        bus.say(`Подложка: ${BASEMAPS[id]}`);
        return { undo: () => set(prev), redo: () => set(id) };
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
        const p = Math.abs(x) <= 90 && Math.abs(y) <= 180 ? wgsToMsk([y, x]) : ([x, y] as [number, number]);
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
