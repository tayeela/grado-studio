// albummeta.js: адрес из точек ЕГКО, номер КРТ, «не затирать введённое» (запуск — tests/test_albummeta_js.py).
const assert = require("assert");
const M = require("../web/albummeta.js");
let n = 0; const eq = (a, b, msg) => { assert.deepStrictEqual(a, b, "FAIL: " + msg); n++; };
eq(M.parseAddr("1-й Иртышский проезд 8 стр.1"), { street: "1-й Иртышский проезд", house: "8" }, "ordinal 1-й is not a house");
eq(M.parseAddr("город Москва, улица Фрунзе, дом 12а к.2"), { street: "улица Фрунзе", house: "12а" }, "prefix and «дом» dropped");
eq(M.parseAddr("Шоссе Энтузиастов 12/1"), { street: "Шоссе Энтузиастов", house: "12/1" }, "fraction house");
eq(M.parseAddr("без номера"), null, "no house");
const A = (...a) => a;
eq(M.addressText(A("1-й Иртышский проезд 8 стр.1", "1-й Иртышский проезд 8 стр.2", "1-й Иртышский проезд 8")), "г. Москва, 1-й Иртышский проезд, д. 8", "one street one house");
eq(M.addressText(A("1-й Иртышский проезд 8", "1-й Иртышский проезд 10", "Богданова улица 3")), "г. Москва, 1-й Иртышский проезд", "houses differ: street only");
eq(M.addressText(A("Богданова улица 3", "Богданова улица 3 стр.2", "Иртышский проезд 8")), "г. Москва, Богданова улица, д. 3", "street with most points wins");
eq(M.addressText(A("", "нет")), "", "nothing to build from");
eq(M.krtText([{ properties: { num_krt: "3228" } }, { properties: { num_krt: "3229" } }, { properties: { num_krt: "" } }], f => f.properties.num_krt === "3229" ? 5 : 1), "№ 3229", "largest overlap");
eq(M.krtText([{ properties: { num_krt: "7" } }], () => 0), "", "no overlap: empty");
eq(M.placeJoin("ВАО", "Гольяново"), "ВАО, район Гольяново", "place");
eq(M.placeJoin("", ""), "", "place empty");
// не затирать введённое
let m = { short: "№ 1", place: "", address: "" };
eq(M.fillMeta(m, { short: "№ 3229", place: "ВАО, район Гольяново", address: "" }), ["place"], "typed short kept, empty place filled");
eq([m.short, m.place, m.auto], ["№ 1", "ВАО, район Гольяново", { place: true }], "state after first fill");
eq(M.fillMeta(m, { place: "СВАО, район Х" }), ["place"], "auto-filled value is refreshed");
M.typed(m, "place"); m.place = "Мой район";
eq(M.fillMeta(m, { place: "ВАО, район Гольяново" }), [], "after user edit — kept");
eq(m.place, "Мой район", "user text intact");
eq(M.fillMeta(m, { address: "" }), [], "empty found value changes nothing");

// T74: что не готово до выгрузки
const S = (i, o = {}) => ({ i, title: "Лист" + i, why: "", photos: null, empty: [], ...o });
const full = { short: "№ 1", place: "ВАО", address: "г. Москва" };
eq(M.exportIssues({ terr: true, meta: full, sheets: [S(0), S(1)] }), [], "everything ready: empty list");
eq(M.exportIssues({ terr: false, meta: full, sheets: [S(0)] }).map(x => x.text), ["Территория не задана: карты листов будут без границы"], "no territory");
eq(M.exportIssues({ terr: true, meta: { short: " ", place: "", address: "x" }, sheets: [] }), [{ text: "В шапке не заполнено: № КРТ, округ/район", stamp: true }], "header fields named");
eq(M.exportIssues({ terr: true, meta: {}, title: false, sheets: [] }), [], "single non-title sheet: header not checked");
eq(M.exportIssues({ terr: true, meta: { ...full, address: "" }, sheets: [S(2, { why: "нет адреса" })] }).map(x => x.text), ["В шапке не заполнено: адрес"], "«нет адреса» not repeated");
eq(M.exportIssues({ terr: true, meta: full, sheets: [S(1, { why: "слой «A» не загрузился", empty: ["B", "C"] }), S(4, { photos: 0 }), S(5, { photos: 3 })] }),
  [{ text: "лист 2 «Лист1»: слой «A» не загрузился; слои «B», «C» в рамке листа пусты", sheet: 1 }, { text: "лист 5 «Лист4»: Фотофиксация: снимков нет", sheet: 4 }], "sheet reasons, empty layers, photos");
console.log(n + " checks ok");
