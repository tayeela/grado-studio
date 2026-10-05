// railstations.js: вид станции (метро / МЦК / МЦД D1–D5), слияние одноимённых, легенда (запуск — tests/test_railstations_js.py).
const assert = require("assert");
const R = require("../web/railstations.js");
let n = 0; const eq = (a, b, msg) => { assert.deepStrictEqual(a, b, "FAIL: " + msg + " | " + JSON.stringify(a)); n++; };
const st = (name, line, network, extra) => ({ ft_type_name: "transport-metro-station", name, line, network, closed: "0", ...extra });
const metro = (name, no = 8) => st(name, "moscow_metro-" + no, "moscow_metro", { p_name: "Калининская линия" });
const mck = name => st(name, "moscow_metro-14", "moscow_metro", { p_name: "Московское центральное кольцо" });
const mcd = (name, d) => st(name, "moscow_mcd-" + d, "moscow_mcd", { p_name: "МЦД-" + d.slice(1) + " диаметр" });

eq(R.kindOf(metro("Перово")), { kind: "metro", name: "Перово" }, "метро");
eq(R.kindOf(metro("Некрасовка", 15)), { kind: "metro", name: "Некрасовка" }, "Некрасовская линия — метро");
eq(R.kindOf(mck("Локомотив")), { kind: "mck", name: "Локомотив" }, "МЦК по line moscow_metro-14");
eq(R.kindOf({ ...metro("Белокаменная"), line: "", p_name: "Московское центральное кольцо" }).kind, "mck", "МЦК по названию линии");
for (const d of ["D1", "D2", "D3", "D4", "D5"]) eq(R.kindOf(mcd("Вешняки", d)), { kind: "mcd", d, name: "Вешняки" }, "МЦД " + d);
eq(R.kindOf({ ...mcd("Вешняки", "D3"), line: "" }).d, "D3", "диаметр по названию «МЦД-3 …»");
eq(R.kindOf(mcd("Х", "D6")), null, "диаметра D6 нет среди значков");
eq(R.kindOf({ ...metro("Перово"), closed: "1" }), null, "закрытая станция");
eq(R.kindOf({ ...metro("Рижская (закрыта)") }), null, "«(закрыта)» в названии");
eq(R.kindOf({ ft_type_name: "transport-railway-station", name: "Маленковская" }), null, "обычная ж/д станция — без значка");
eq(R.kindOf({ ft_type_name: "transport-bus-stop", name: "Остановка" }), null, "остановка");
eq(R.kindOf(st("Х", "spb_metro-1", "spb_metro")), null, "чужая сеть");
eq(R.kindOf({ get: k => ({ ft_type_name: "transport-metro-station", name: "Сокол", network: "moscow_metro", line: "moscow_metro-2" })[k] }).kind, "metro", "объект с get()");

const at = (x, y) => [37.7 + x / 1e5 * 1.0, 55.8 + y / 1e5];
// Черкизовская: метро и МЦК-станция с другим названием рядом; Нижегородская: метро ×3, МЦК и МЦД-4 — один объект
let s = R.stations([{ props: metro("Нижегородская", 11), coord: at(0, 0) }, { props: metro("Нижегородская", 15), coord: at(30, 20) }, { props: mck("Нижегородская"), coord: at(10, 10) },
  { props: mcd("Нижегородская", "D4"), coord: at(200, 100) }]);
eq(s.length, 1, "одно название рядом — одна станция");
eq(s[0].icons, ["metro", "mcd-d4"], "значок «М» один, рядом значок МЦД-4");
eq(s[0].color, R.METRO_COLOR, "название красное, если есть метро / МЦК");
eq(s[0].mck && s[0].metro, true, "и метро, и МЦК");
s = R.stations([{ props: mcd("Перово", "D3"), coord: at(0, 0) }, { props: mcd("Перово", "D1"), coord: at(5, 0) }]);
eq(s[0].icons, ["mcd-d1", "mcd-d3"], "два диаметра — по порядку");
eq(s[0].color, R.METRO_COLOR, "МЦД без метро — название тоже красное (владелец 06.10.2026)");
s = R.stations([{ props: mcd("Андроновка", "D3"), coord: at(0, 0) }]);
eq([s[0].icons, s[0].color], [["mcd-d3"], R.METRO_COLOR], "МЦД-3: свой значок, название красное");
s = R.stations([{ props: metro("Перово"), coord: [37.79, 55.75] }, { props: metro("Перово"), coord: [37.5, 55.9] }]);
eq(s.length, 2, "одинаковое название далеко (>700 м) — разные станции");
s = R.stations([{ props: metro("Сокол", 2), coord: null }, { props: { ft_type_name: "transport-bus-stop", name: "Сокол" }, coord: at(0, 0) }]);
eq(s.length, 0, "без координат и не станции — пусто");

// легенда — только виды, что есть
eq(R.legendItems([]), [], "пустой лист — без значков");
eq(R.legendItems(R.stations([{ props: metro("Перово"), coord: at(0, 0) }])), [{ icon: "metro", label: "станция метро" }], "только метро");
eq(R.legendItems(R.stations([{ props: mck("Локомотив"), coord: at(0, 0) }])), [{ icon: "metro", label: "станция МЦК" }], "только МЦК");
eq(R.legendItems(R.stations([{ props: mck("Локомотив"), coord: at(0, 0) }, { props: metro("Черкизовская", 1), coord: at(900, 0) }, { props: mcd("Белокаменная", "D2"), coord: at(2000, 0) },
  { props: mcd("Х", "D1"), coord: at(4000, 0) }])).map(x => x.label), ["станция метро и МЦК", "станция МЦД D1", "станция МЦД D2"], "метро, МЦК, два диаметра");

eq(R.bare("ст. ж/д Перово"), "перово", "сравнение с подписью ЕГКО");
eq(R.bare("Станция Перово"), "перово", "«Станция»");
eq(R.bare("Перово"), "перово", "без приставки");
// как приходит с сервера: имя Яндекса — в поле «Название» (yandex_vmap), поля name нет (живая точка «Перово», 06.10.2026)
eq(R.stations([{ props: { ft_type_name: "transport-metro-station", closed: "0", network: "moscow_metro", line: "moscow_metro-8", "Название": "Перово" }, coord: [37.786, 55.751] }]).map(s => s.name),
  ["Перово"], "имя из поля «Название»");
console.log(n + " checks ok");
