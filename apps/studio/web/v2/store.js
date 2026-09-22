/** Один store каркаса 1.0. Холст не пишет диск сам. */

export const LAYERS = [
  { id: "project.territory.boundary", title: "Граница", shelf: "Территория", kind: "boundary", geom: "polygon" },
  { id: "source.constraints.restrict", title: "Ограничения", shelf: "Ограничения", kind: "restrict", geom: "polygon" },
  { id: "project.tp.func_zone", title: "Функциональные зоны", shelf: "Проект", kind: "zone", geom: "polygon" },
  { id: "project.apo.buildings", title: "Здания", shelf: "Проект", kind: "building", geom: "polygon" },
  { id: "project.apo.public_zones", title: "Пятна ОКС", shelf: "Проект", kind: "public", geom: "polygon" },
  { id: "project.apo.red_lines", title: "Красные линии", shelf: "Проект", kind: "redline", geom: "line" },
  { id: "project.social.objects", title: "Соцобъекты", shelf: "Проект", kind: "social", geom: "point" },
  { id: "source.nspd.parcels", title: "Участки", shelf: "НСПД", kind: "parcel", geom: "polygon" },
  { id: "source.nspd.buildings", title: "Здания", shelf: "НСПД", kind: "building", geom: "polygon" },
  { id: "source.nspd.zouit", title: "ЗОУИТ", shelf: "НСПД", kind: "restrict", geom: "polygon" },
  { id: "source.nspd.constructions", title: "Сооружения", shelf: "НСПД", kind: "redline", geom: "line" },
  { id: "source.osm.roads", title: "Дороги", shelf: "OSM", kind: "redline", geom: "line" },
  { id: "source.osm.buildings", title: "Здания", shelf: "OSM", kind: "building", geom: "polygon" },
  { id: "source.osm.landuse", title: "Землепользование", shelf: "OSM", kind: "zone", geom: "polygon" },
  { id: "source.osm.water", title: "Вода", shelf: "OSM", kind: "zone", geom: "polygon" },
  { id: "source.osm.boundaries", title: "Границы", shelf: "OSM", kind: "zone", geom: "polygon" },
  { id: "source.gisogd.func_zones", title: "Зоны", shelf: "ГИС ОГД", kind: "zone", geom: "polygon" },
  { id: "source.gisogd.red_lines", title: "Красные линии", shelf: "ГИС ОГД", kind: "redline", geom: "line" },
  { id: "source.gisogd.restrict", title: "ЗОУИТ", shelf: "ГИС ОГД", kind: "restrict", geom: "polygon" },
  { id: "source.gisogd.other", title: "Прочее", shelf: "ГИС ОГД", kind: "zone", geom: "polygon" },
  { id: "source.fgistp.func_zones", title: "Зоны", shelf: "ФГИС ТП", kind: "zone", geom: "polygon" },
];

export function layerRows() {
  const rows = LAYERS.map((layer) => ({ ...layer }));
  const seen = new Set(rows.map((layer) => layer.id));
  for (const feature of state.features) {
    const id = feature.layer_id;
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const shelf = id.startsWith("source.nspd") ? "НСПД"
      : id.startsWith("source.osm") ? "OSM"
      : id.startsWith("source.gisogd") ? "ГИС ОГД"
      : id.startsWith("source.fgistp") ? "ФГИС ТП"
      : id.startsWith("source.") ? "Импорт" : "Проект";
    rows.push({ id, title: id.split(".").slice(2).join(" · ") || id, shelf, kind: feature.kind || "generic", geom: "polygon" });
  }
  return rows;
}

export const SNAP_LABEL = {
  endpoint: "Привязка к концу",
  intersection: "Привязка к пересечению",
  midpoint: "Привязка к середине",
  nearest: "Ближайшая точка",
};

export const state = {
  name: "Новый проект",
  features: [],
  visible: Object.fromEntries(LAYERS.map((layer) => [layer.id, true])),
  locked: {},
  activeLayer: "project.territory.boundary",
  selection: null,
  picked: [],
  tool: "polygon",
  view: "draw",
  ortho: false,
  snapOn: true,
  gridOn: false,
  gridStep: 1,
  snap: 0.5,
  ppm: 4,
  origin: { x: 50, y: 40 },
  dirty: 0,
  tep: null,
  sheetScale: "",
  snapHint: "",
  message: "",
  library: {},
  projectStyles: {},
  pending: null,
  trimReady: false,
  bounds: [],
  basemap: "osm",
  sources: {},
};

const listeners = new Set();
const undo = [];
const redo = [];
let seq = 1;

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function emit() {
  for (const fn of listeners) fn();
}

export function nextId() {
  return "f" + seq++;
}

export function layerById(id) {
  return LAYERS.find((layer) => layer.id === id);
}

export function plainFeatures() {
  return state.features.map((feature) => {
    const copy = { ...feature, props: { ...(feature.props || {}) } };
    delete copy.preview;
    if (copy.arc) {
      const { preview, ...arc } = copy.arc;
      copy.arc = arc;
    }
    if (copy.circle) {
      const { preview, ...circle } = copy.circle;
      copy.circle = circle;
    }
    return copy;
  });
}

function remember() {
  undo.push(JSON.stringify(state.features));
  if (undo.length > 80) undo.shift();
  redo.length = 0;
}

export function addFeature(feature) {
  const layer = feature.layer_id;
  if (layer && state.locked[layer]) {
    state.message = "Слой захвачен";
    emit();
    return;
  }
  remember();
  feature.id = feature.id || nextId();
  feature.props = feature.props || {};
  state.features.push(feature);
  state.selection = feature.id;
  state.picked = [feature.id];
  state.dirty += 1;
  state.pending = null;
  emit();
}

export function replaceFeature(id, patch) {
  const index = state.features.findIndex((feature) => feature.id === id);
  if (index < 0) return;
  remember();
  state.features[index] = { ...state.features[index], ...patch, id };
  state.dirty += 1;
  emit();
}

export function undoEdit() {
  const prev = undo.pop();
  if (!prev) return;
  redo.push(JSON.stringify(state.features));
  state.features = JSON.parse(prev);
  state.dirty += 1;
  state.selection = null;
  state.picked = [];
  emit();
}

export function redoEdit() {
  const next = redo.pop();
  if (!next) return;
  undo.push(JSON.stringify(state.features));
  state.features = JSON.parse(next);
  state.dirty += 1;
  state.selection = null;
  state.picked = [];
  emit();
}

export function addFeatures(list) {
  if (!list.length) return;
  remember();
  for (const feature of list) {
    feature.id = feature.id || nextId();
    feature.props = feature.props || {};
    state.features.push(feature);
  }
  state.dirty += list.length;
  emit();
}

export function setFeatures(features) {
  remember();
  state.features = features;
  state.dirty += 1;
  emit();
}

export function removeFeatures(ids) {
  remember();
  const drop = new Set(ids);
  state.features = state.features.filter((feature) => !drop.has(feature.id));
  state.picked = state.picked.filter((id) => !drop.has(id));
  state.selection = state.picked[0] || null;
  state.dirty += 1;
  emit();
}

export function togglePick(id, shift) {
  if (!shift) {
    state.picked = id ? [id] : [];
  } else if (id) {
    state.picked = state.picked.includes(id)
      ? state.picked.filter((item) => item !== id)
      : state.picked.concat(id);
  }
  state.selection = state.picked[0] || null;
  emit();
}

export function resetProject(name) {
  remember();
  state.name = name || "Новый проект";
  state.features = [];
  state.selection = null;
  state.picked = [];
  state.bounds = [];
  state.trimReady = false;
  state.dirty = 0;
  state.tep = null;
  state.pending = null;
  state.projectStyles = {};
  state.message = "";
  emit();
}

export function loadProject(payload) {
  state.projectStyles = payload.projectStyles || {};
  state.name = payload.name || "Проект";
  state.features = (payload.features || []).map((feature) => ({
    ...feature,
    id: feature.id || nextId(),
    props: feature.props || {},
  }));
  state.selection = null;
  state.picked = [];
  state.bounds = [];
  state.trimReady = false;
  state.dirty = 0;
  state.pending = null;
  state.view = "map";
  state.message = "";
  emit();
}

export function selectedFeature() {
  return state.features.find((feature) => feature.id === state.selection) || null;
}

export function featurePoints(feature) {
  if (!feature) return [];
  if (feature.ring) return feature.ring.map((p) => [p[0], p[1]]);
  if (feature.line) return feature.line.map((p) => [p[0], p[1]]);
  if (feature.point) return [[feature.point[0], feature.point[1]]];
  if (feature.circle) return [[feature.circle.cx, feature.circle.cy]];
  if (feature.arc) return [[feature.arc.cx, feature.arc.cy]];
  return [];
}

export function snapPolylines() {
  const lines = [];
  for (const feature of state.features) {
    if (state.visible[feature.layer_id] === false) continue;
    if (feature.ring && feature.ring.length >= 2) {
      const ring = feature.ring.map((p) => [p[0], p[1]]);
      ring.push(ring[0]);
      lines.push(ring);
    } else if (feature.line && feature.line.length >= 2) {
      lines.push(feature.line.map((p) => [p[0], p[1]]));
    }
  }
  return lines;
}
