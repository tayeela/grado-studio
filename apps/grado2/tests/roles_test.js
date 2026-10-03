// roles.js: роль слоя в расчётах — ручная, по ключу источника, по коду каталога (запуск — tests/test_roles_js.py).
const assert = require("assert");
const Roles = require("../web/roles.js");
let n = 0; const eq = (a, b, msg) => { assert.deepStrictEqual(a, b, "FAIL: " + msg); n++; };
const fc = (...ps) => ({ fc: { features: ps.map(p => ({ type: "Feature", geometry: { type: "Polygon", coordinates: [] }, properties: p })) }, rev: 1 });
const table = { codes: { virtual109: "zouit", virtual1521: "zouit", virtual1976: "func_zones", virtual132: "pzz_sub", zu_29_06_2021: "parcels" }, titles: { virtual1976: "Природная зона" } };
const DATA = { "ogd.virtual109": { title: "Водоохранные зоны (ОГД)", ...fc({}) }, "ogd.virtual1521": { title: "Зоны береговых полос (ОГД)", ...fc({}, {}) }, "nspd.zouit": { title: "ЗОУИТ (ЕГРН)", ...fc({}) },
  "ogd.virtual1976": { title: "Природная зона (ОГД)", ...fc({}) }, "ogd.gpzu": { title: "ГПЗУ (ОГД)", ...fc({}) }, "ogd.virtual84": { title: "Пятая подзона (ОГД)", ...fc({}) },
  "egko.buildings": { title: "Здания (ЕГКО)", ...fc({}, {}, {}) }, "osm.buildings": { title: "Здания (OSM)", ...fc({}) }, "nspd.buildings": { title: "Здания (ЕГРН)", ...fc({}) },
  "egko.water": { title: "Водная поверхность (ЕГКО)", ...fc({}) }, "osm.social": { title: "Школы (OSM)", ...fc({}) }, "user:1": { title: "Мой слой", ...fc({}) }, "cons:zouit": { title: "Запрет", ...fc({}) }, "empty": { title: "нет данных" } };
const LYR = Object.keys(DATA).map(key => ({ key }));
Roles.use({ DATA, LYR, table });

// по ключу источника и по коду каталога; порядок — источники раньше каталожных слоёв
eq(Roles.keys("zouit"), ["nspd.zouit", "ogd.virtual109", "ogd.virtual1521"], "zouit: source key first, then ogd codes in project order");
eq(Roles.keys("func_zones"), ["ogd.virtual1976"], "func zones by catalog code");
eq(Roles.info("func_zones")[0].codeTitle, "Природная зона", "code title is served with the table");
eq(Roles.keys("water"), ["egko.water"], "egko water");
eq(Roles.keys("social"), ["osm.social"], "osm social");
// слой без роли и слой без данных в роли не попадают; неизвестный код — без роли («не проверено» — не угадываем)
eq([Roles.roleOf("ogd.gpzu").role, Roles.roleOf("ogd.virtual84").role, Roles.roleOf("user:1").role, Roles.roleOf("cons:zouit").role], [null, null, null, null], "unmapped layers have no role");
eq(Roles.keys("parcels"), [], "no parcels layer in data");
// здания: приоритет ЕГРН → ЕГКО → OSM; features — все слои роли подряд
eq(Roles.keys("buildings"), ["nspd.buildings", "egko.buildings", "osm.buildings"], "buildings order nspd, egko, osm");
eq(Roles.existingBuildingsKey(), "nspd.buildings", "existing buildings key by priority");
eq(Roles.features("zouit").length, 4, "features concatenate all layers of the role");
eq(Roles.sig("zouit"), "nspd.zouit:1,ogd.virtual109:1,ogd.virtual1521:1", "signature for node caches");
// ручная роль сильнее авто и забирает слой из прежней роли
LYR.find(l => l.key === "ogd.gpzu").role = "zouit";
eq(Roles.keys("zouit"), ["ogd.gpzu", "nspd.zouit", "ogd.virtual109", "ogd.virtual1521"], "manual role goes first");
LYR.find(l => l.key === "ogd.virtual1521").role = "water";
eq(Roles.keys("zouit").includes("ogd.virtual1521"), false, "manual role replaces the auto role");
eq(Roles.keys("water"), ["ogd.virtual1521", "egko.water"], "manual water layer");
LYR.find(l => l.key === "osm.buildings").role = "buildings";
eq(Roles.existingBuildingsKey(), "osm.buildings", "manual buildings layer wins the priority");
// «не участвует»
LYR.find(l => l.key === "nspd.zouit").role = "none";
eq(Roles.keys("zouit").includes("nspd.zouit"), false, "none: layer is out of its auto role");
eq(Roles.roleOf("nspd.zouit"), { role: null, manual: true }, "none is a manual state without a role");
// чужой файл: неизвестная роль не принимается; «авто» = нет поля
eq([Roles.sane("zouit"), Roles.sane("none"), Roles.sane("auto"), Roles.sane("__proto__"), Roles.sane(5)], ["zouit", "none", undefined, undefined, undefined], "sane");
LYR.find(l => l.key === "egko.water").role = "garbage";
eq(Roles.keys("water").includes("egko.water"), true, "unknown manual role is ignored, auto stays");
// слой без fc не участвует
eq(Roles.keys("zouit").includes("empty"), false, "no data no role");
// таблица кодов ещё не пришла: каталожные слои без роли, ключи источников работают
Roles.use({ table: { codes: {} } });
eq(Roles.keys("func_zones"), [], "without the code table ogd layers are not recognised");
eq(Roles.keys("social"), ["osm.social"], "source keys work without the table");
console.log(n + " checks ok");
