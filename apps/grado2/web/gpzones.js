/* Генплан (лист 6 альбома): название и индекс типа функциональной зоны, цвет по таблице MapInfo ТиНАО (правило 13).
   Старая Москва (gisogd.func_zones, virtual1742) несёт naimfunkzony + fztip; ТиНАО (gisogd.func_zones_tinao) — «Вид зоны» + fz_type.
   Цвет — по индексу из любого слоя, сплошной; нет индекса — по названию, иначе fallback (палитра Эталона). Тесты — tests/test_gpzones_js.py. */
(function (root) {
  const TABLE = { 100: "#f76767", 120: "#ee8e62", 123: "#c07c7e", 124: "#e8b154", 130: "#ad84ae", 134: "#ca9568", 140: "#d5af29",
    200: "#f3d357", 230: "#c2a9a2", 240: "#c5c557", 300: "#b1b5e1", 340: "#abb9ab", 400: "#78ce93", 600: "#999999", 800: "#e8f2c7" };
  const norm = n => String(n || "").toLowerCase().replace(/\s*-\s*/g, "-").replace(/\s+/g, " ").trim();   // «общественно - жилая  зона»
  const BY_NAME = { "общественная зона": 100, "общественно-жилая зона": 120, "общественно-производственно-жилая зона": 123,
    "природно-общественно-жилая зона": 124, "общественно-производственная зона": 130, "коммунальные зоны": 130,   // старая Москва: 6 / 130 / 257 тыс. кв. м совпадает с порталом
    "природно-общественно-производственная зона": 134, "природно-общественная зона": 140, "жилая зона": 200, "производственно-жилая зона": 230,
    "природно-жилая зона": 240, "производственная зона": 300, "природно-производственная зона": 340, "природная зона": 400,
    "зона объектов внешнего транспорта": 600, "сельскохозяйственная зона": 800 };
  const pick = (p, ...ks) => { for (const k of ks) { const v = p && p[k]; if (v != null && v !== "") return String(v); } return ""; };
  const zoneName = p => pick(p, "Вид зоны", "naimfunkzony", "naimfunkzo", "Название", "name");
  const zoneIdx = p => pick(p, "fztip", "fztype", "fz_type").split(".")[0];
  // fallback — вызывающий передаёт то, что делал раньше (палитра Эталона по названию)
  const fill = (name, idx, fallback) => TABLE[+idx] || TABLE[BY_NAME[norm(name)]] || (fallback ? fallback(norm(name)) : undefined);
  const api = { TABLE, BY_NAME, norm, zoneName, zoneIdx, fill };
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GpZones = api;
})(typeof window !== "undefined" ? window : globalThis);
