// collab.js: разбиение проекта на разделы и слияние по трём версиям (merge3), проверяется под node (запуск — tests/test_collab_js.py).
const assert = require("assert");
const { split, join, merge3, ensureUids, keepUid } = require("../web/collab.js");
let n = 0; const ok = (c, msg) => { assert.ok(c, "FAIL: " + msg); n++; }, eq = (a, b, msg) => { assert.deepStrictEqual(a, b, "FAIL: " + msg); n++; };

const feat = (uid, x, props = {}) => ({ type: "Feature", geometry: { type: "Point", coordinates: [37.5 + x, 55.7] }, properties: { _uid: uid, ...props } });
const fc = (...fs) => ({ type: "FeatureCollection", features: fs });
const layer = (key, fcv, extra = {}) => ({ spec: { key, title: key, geom: "point", visible: true, layerOpacity: 1, open: false, group: null, style: { mode: "single", color: "#f00", opacity: 0.5 }, ...extra },
  data: { title: key, source: "создан в проекте", fetched_at: "2026-09-30", fc: fcv, original: "=fc" } });
const project = () => ({
  format: "grado2", version: 2, app: "ГРАДО 2 0.1", name: "Тест", file: null, saved_at: "2026-09-30T10:00:00Z", dirty: false,
  view: { center: [37.5, 55.7], zoom: 15, basemap: "osm" }, territory: { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[[37, 55], [38, 55], [38, 56], [37, 55]]] } },
  imports: { "import:a.dxf": { title: "a.dxf", kind: "import" } }, checked: ["osm.roads", "nspd.parcels"], current: "bld",
  groups: [{ id: "g1", title: "Группа", visible: true, open: true }], views: [{ id: "v1", name: "Вид" }], album: { meta: { object: "Объект" }, sheets: [{ id: "s1" }] },
  layers: [layer("bld", null).spec, layer("roads", null).spec], data: { bld: layer("bld", fc(feat("aaaaaaaaaaaa", 0, { Этажность: 5 }), feat("bbbbbbbbbbbb", 1))).data, roads: layer("roads", fc()).data },
  graph: { last_node_id: 2, nodes: [{ id: 1, type: "Данные/Территория", pos: [0, 0] }], links: [] },
});

// --- split / join на форме проекта
{
  const p = project(), s = split(p);
  eq(Object.keys(s).sort(), ["layer:bld", "layer:roads", "meta"], "разделы: meta и по разделу на слой");
  eq(s.meta.current_order, ["bld", "roads"], "порядок слоёв в meta");
  eq(s.meta.checked, ["nspd.parcels", "osm.roads"], "checked отсортирован: порядок Set не считается правкой");
  ok(!("view" in s.meta) && !("current" in s.meta), "личное (вид карты, текущий слой) в разделы не попадает");
  const back = join(s, { view: p.view, current: p.current });
  for (const k of ["format", "version", "name", "view", "territory", "imports", "current", "groups", "views", "album", "layers", "data", "graph"]) eq(back[k], k === "checked" ? [] : p[k], "round trip: " + k);
  eq([...back.checked].sort(), [...p.checked].sort(), "round trip: checked");
  ok(typeof back.saved_at === "string" && /ГРАДО/.test(back.app), "join ставит saved_at и app");
  // порядок слоёв из meta, лишний ключ пропускается, слой без записи в порядке встаёт в конец
  const s2 = { ...s, meta: { ...s.meta, current_order: ["ghost", "roads"] } };
  eq(join(s2).layers.map(l => l.key), ["roads", "bld"], "join: порядок из meta, призрак пропущен, bld в конец");
  eq(join({ ...s, "layer:roads": null }).layers.map(l => l.key), ["bld"], "join: удалённый раздел (null) — слоя нет");
  eq(join(s).view, undefined, "join без личного — без view");
  const pg = project(); pg.territory._gid = "abc123";
  ok(!("_gid" in split(pg).meta.territory) && pg.territory._gid === "abc123", "метка _gid (в памяти app.js) в раздел не попадает, исходный объект цел");
}

// --- номера _uid
{
  const a = fc({ type: "Feature", geometry: { type: "Point", coordinates: [1, 2] }, properties: {} }, { type: "Feature", geometry: { type: "Point", coordinates: [3, 4] }, properties: null }, feat("cccccccccccc", 2), feat("cccccccccccc", 3));
  const e = ensureUids(a, "bld");
  ok(e !== a && e.features.every(f => /^[0-9a-f]{12}$/.test(f.properties._uid)), "у объектов без номера он появляется (12 hex)");
  eq(new Set(e.features.map(f => f.properties._uid)).size, 4, "повтор номера в слое получает новый");
  ok(a.features[0].properties._uid === undefined, "вход не изменён");
  eq(ensureUids(a, "bld").features.map(f => f.properties._uid), e.features.map(f => f.properties._uid), "номера детерминированы: у разных участников совпадают");
  const full = fc(feat("dddddddddddd", 0)); ok(ensureUids(full, "x") === full, "все номера на месте — тот же объект");
  // слои без номеров сводятся как один и тот же объект
  const base = fc({ type: "Feature", geometry: { type: "Point", coordinates: [1, 2] }, properties: { a: 1 } });
  const mine = fc({ type: "Feature", geometry: { type: "Point", coordinates: [1, 2] }, properties: { a: 2 } });
  const m = merge3(layer("L", base), layer("L", mine), layer("L", base), "layer:L");
  eq(m.data.fc.features.length, 1, "слияние слоя без номеров: объект не двоится");
}

const L = "layer:bld";
const B = () => layer("bld", fc(feat("aaaaaaaaaaaa", 0, { Этажность: 5, Имя: "а" }), feat("bbbbbbbbbbbb", 1, { Этажность: 3 })));
const byUid = (sec, u) => sec.data.fc.features.find(f => f.properties._uid === u);

// --- объекты слоя
{
  // обе стороны добавили по объекту — остаются оба
  const mine = B(), theirs = B();
  mine.data.fc.features.push(feat("m00000000001", 5)); theirs.data.fc.features.push(feat("t00000000001", 6));
  const r = merge3(B(), mine, theirs, L);
  eq(r.data.fc.features.map(f => f.properties._uid).sort(), ["aaaaaaaaaaaa", "bbbbbbbbbbbb", "m00000000001", "t00000000001"], "оба добавления сохранены");
}
{
  // один объект: разные свойства — берутся оба изменения
  const mine = B(), theirs = B();
  byUid(mine, "aaaaaaaaaaaa").properties.Этажность = 9; byUid(theirs, "aaaaaaaaaaaa").properties.Имя = "чужое";
  const f = byUid(merge3(B(), mine, theirs, L), "aaaaaaaaaaaa");
  eq([f.properties.Этажность, f.properties.Имя], [9, "чужое"], "правки разных свойств одного объекта сложились");
}
{
  // одно свойство, по-разному — побеждает чужое
  const mine = B(), theirs = B();
  byUid(mine, "aaaaaaaaaaaa").properties.Этажность = 9; byUid(theirs, "aaaaaaaaaaaa").properties.Этажность = 7;
  eq(byUid(merge3(B(), mine, theirs, L), "aaaaaaaaaaaa").properties.Этажность, 7, "одно свойство у обоих: чужое побеждает");
  // у обоих одинаково — без конфликта
  byUid(mine, "aaaaaaaaaaaa").properties.Этажность = 7;
  eq(byUid(merge3(B(), mine, theirs, L), "aaaaaaaaaaaa").properties.Этажность, 7, "одинаковая правка");
}
{
  // геометрия: я двигал, они правили свойство
  const mine = B(), theirs = B();
  byUid(mine, "aaaaaaaaaaaa").geometry.coordinates = [38, 56]; byUid(theirs, "aaaaaaaaaaaa").properties.Имя = "х";
  const f = byUid(merge3(B(), mine, theirs, L), "aaaaaaaaaaaa");
  eq([f.geometry.coordinates, f.properties.Имя], [[38, 56], "х"], "геометрия моя + свойство чужое");
  // геометрия у обоих по-разному: чужая
  byUid(theirs, "aaaaaaaaaaaa").geometry.coordinates = [39, 57];
  eq(byUid(merge3(B(), mine, theirs, L), "aaaaaaaaaaaa").geometry.coordinates, [39, 57], "геометрия у обоих: чужая");
}
{
  // шум круговой проекции (1e-13°) не считается правкой: моя настоящая правка не теряется
  const mine = B(), theirs = B();
  byUid(mine, "aaaaaaaaaaaa").properties.Этажность = 11;
  theirs.data.fc.features.forEach(f => { f.geometry.coordinates = f.geometry.coordinates.map(c => c + 3e-13); });
  const r = merge3(B(), mine, theirs, L);
  eq(byUid(r, "aaaaaaaaaaaa").properties.Этажность, 11, "шум координат у них не затирает мою правку");
}
{
  // удаление против правки
  const mine = B(), theirs = B();
  mine.data.fc.features = mine.data.fc.features.filter(f => f.properties._uid !== "aaaaaaaaaaaa");   // я удалил
  byUid(theirs, "aaaaaaaaaaaa").properties.Этажность = 12;                                              // они правили
  eq(byUid(merge3(B(), mine, theirs, L), "aaaaaaaaaaaa").properties.Этажность, 12, "правка побеждает удаление (я удалил, они правили)");
  const m2 = B(), t2 = B();
  byUid(m2, "aaaaaaaaaaaa").properties.Этажность = 13;
  t2.data.fc.features = t2.data.fc.features.filter(f => f.properties._uid !== "aaaaaaaaaaaa");
  eq(byUid(merge3(B(), m2, t2, L), "aaaaaaaaaaaa").properties.Этажность, 13, "правка побеждает удаление (они удалили, я правил)");
  // удаление против нетронутого
  const m3 = B(), t3 = B();
  m3.data.fc.features = m3.data.fc.features.filter(f => f.properties._uid !== "bbbbbbbbbbbb");
  byUid(t3, "aaaaaaaaaaaa").properties.Имя = "у";
  const r3 = merge3(B(), m3, t3, L);
  eq(r3.data.fc.features.map(f => f.properties._uid), ["aaaaaaaaaaaa"], "удаление побеждает нетронутую сторону");
  const r4 = merge3(B(), t3, m3, L);
  eq(r4.data.fc.features.map(f => f.properties._uid), ["aaaaaaaaaaaa"], "то же в другую сторону");
}

// --- слой целиком
{
  // слой удалён у них, я правил: правка побеждает, слой возвращается
  const mine = B(); byUid(mine, "aaaaaaaaaaaa").properties.Этажность = 20;
  const r = merge3(B(), mine, null, L);
  ok(r && byUid(r, "aaaaaaaaaaaa").properties.Этажность === 20, "слой удалён чужим, но правлен мной: слой возвращается с моей правкой");
  // слой удалён у меня, они правили: возвращается чужая версия
  const theirs = B(); byUid(theirs, "bbbbbbbbbbbb").properties.Имя = "т";
  eq(byUid(merge3(B(), null, theirs, L), "bbbbbbbbbbbb").properties.Имя, "т", "я удалил, они правили: их версия");
  // удалён у них, я не трогал: слоя нет
  eq(merge3(B(), B(), null, L), null, "удалён чужим, мной не тронут: удаляется");
  // удалён у меня, они не трогали: слоя нет
  eq(merge3(B(), null, B(), L), null, "удалён мной, чужим не тронут: удаляется");
  // оба создали слой с одним ключом: объекты складываются
  const m = layer("bld", fc(feat("m00000000001", 0))), t = layer("bld", fc(feat("t00000000001", 1)));
  eq(merge3(null, m, t, L).data.fc.features.map(f => f.properties._uid).sort(), ["m00000000001", "t00000000001"], "оба создали слой: объекты обеих сторон");
  // не менял никто: то же
  eq(merge3(B(), B(), B(), L), B(), "без правок");
  // поля слоя: по одному
  const ms = B(), ts = B(); ms.spec.visible = false; ts.spec.layerOpacity = 0.3; ts.spec.style.color = "#0f0"; ms.spec.style.opacity = 0.9; ms.spec.title = "Моё";
  const rs = merge3(B(), ms, ts, L).spec;
  eq([rs.visible, rs.layerOpacity, rs.style.color, rs.style.opacity, rs.title], [false, 0.3, "#0f0", 0.9, "Моё"], "поля слоя и поля стиля по одному");
  const ms2 = B(), ts2 = B(); ms2.spec.layerOpacity = 0.1; ts2.spec.layerOpacity = 0.7;
  eq(merge3(B(), ms2, ts2, L).spec.layerOpacity, 0.7, "одно поле слоя у обоих: чужое");
  // данные слоя: поле источника
  const md = B(), td = B(); md.data.source = "мой"; td.data.fetched_at = "2026-10-01";
  const rd = merge3(B(), md, td, L).data; eq([rd.source, rd.fetched_at], ["мой", "2026-10-01"], "поля данных слоя по одному");
}

// --- meta
{
  const M = () => split(project()).meta;
  const info = { conflicts: [] };
  // разные ключи — складываются
  const mine = M(), theirs = M(); mine.groups = [{ id: "g1", title: "Моя", visible: true, open: true }]; theirs.views = [{ id: "v1", name: "Чужой вид" }, { id: "v2", name: "Ещё" }];
  const r = merge3(M(), mine, theirs, "meta", info);
  eq([r.groups[0].title, r.views.length, info.conflicts], ["Моя", 2, []], "разные ключи meta складываются без конфликта");
  // один ключ у обоих: побеждает чужое, ключ назван
  const m2 = M(), t2 = M(), i2 = { conflicts: [] }; m2.album = { meta: { object: "Моё" }, sheets: [] }; t2.album = { meta: { object: "Чужое" }, sheets: [{ id: "s9" }] };
  const r2 = merge3(M(), m2, t2, "meta", i2);
  eq([r2.album.meta.object, i2.conflicts], ["Чужое", ["album"]], "ключ meta у обоих: чужое, конфликт назван");
  // граница и граф
  const m3 = M(), t3 = M(), i3 = { conflicts: [] }; m3.territory = null; t3.graph = { ...t3.graph, last_node_id: 7 };
  const r3 = merge3(M(), m3, t3, "meta", i3); eq([r3.territory, r3.graph.last_node_id, i3.conflicts], [null, 7, []], "граница моя, граф чужой");
  // одинаково — без конфликта
  const m4 = M(), t4 = M(), i4 = { conflicts: [] }; m4.checked = t4.checked = ["osm.roads"];
  eq(merge3(M(), m4, t4, "meta", i4).checked, ["osm.roads"], "одинаковая правка"); eq(i4.conflicts, [], "одинаковая правка — не конфликт");
  // порядок слоёв: чужой порядок + мой новый слой на своём месте
  const m5 = M(), t5 = M(); m5.current_order = ["bld", "mine", "roads"]; t5.current_order = ["roads", "bld", "theirs"];
  eq(merge3(M(), m5, t5, "meta").current_order, ["roads", "bld", "mine", "theirs"], "порядок: чужой + мой слой после соседа слева");
  // я убрал слой, они порядок меняли
  const m6 = M(), t6 = M(); m6.current_order = ["bld"]; t6.current_order = ["roads", "bld"];
  eq(merge3(M(), m6, t6, "meta").current_order, ["bld"], "слой, убранный мной и не тронутый ими, из порядка уходит");
  // источники: по записям
  const m7 = M(), t7 = M(); m7.imports = { ...m7.imports, "import:m.dxf": { title: "m" } }; t7.imports = { ...t7.imports, "import:t.dxf": { title: "t" } };
  eq(Object.keys(merge3(M(), m7, t7, "meta").imports).sort(), ["import:a.dxf", "import:m.dxf", "import:t.dxf"], "источники: записи обеих сторон");
  // название: хаб ставит сам — у меня без изменений, берётся чужое
  const t8 = M(); t8.name = "Новое имя"; eq(merge3(M(), M(), t8, "meta").name, "Новое имя", "название от хаба применяется");
  // альбом по листам (T35)
  const AB = () => ({ meta: { object: "Объект" }, sheets: [{ id: "s1", title: "Лист 1", num: "1" }, { id: "s2", title: "Лист 2", num: "2" }] });
  const AM = (f) => { const x = M(); x.album = AB(); f(x.album); return x; };
  const ids = r => r.album.sheets.map(x => x.id);
  // 1: каждый добавил по листу
  { const i = { conflicts: [] }, r = merge3(AM(() => { }), AM(a => a.sheets.push({ id: "m1", title: "Мой" })), AM(a => a.sheets.push({ id: "t1", title: "Чужой" })), "meta", i);
    eq(ids(r), ["s1", "s2", "m1", "t1"], "альбом: листы обеих сторон, без двойников"); eq(i.conflicts, [], "новые листы — не конфликт"); }
  // 2: один лист правлен по-разному
  { const i = { conflicts: [] }, r = merge3(AM(() => { }), AM(a => { a.sheets[0].title = "Моё"; }), AM(a => { a.sheets[0].title = "Чужое"; }), "meta", i);
    eq([r.album.sheets[0].title, r.album.sheets.length, i.conflicts], ["Чужое", 2, ["album:лист 1"]], "один лист у обоих: чужое, конфликт назван по листу"); }
  // 3: правки разных листов
  { const i = { conflicts: [] }, r = merge3(AM(() => { }), AM(a => { a.sheets[0].title = "Моё"; }), AM(a => { a.sheets[1].title = "Чужое"; }), "meta", i);
    eq([r.album.sheets.map(x => x.title), i.conflicts], [["Моё", "Чужое"], []], "правки разных листов сохранены обе"); }
  // 4: я убрал лист; они не трогали — убран; они правили — вернулся с правкой
  { const r = merge3(AM(() => { }), AM(a => a.sheets.splice(1, 1)), AM(() => { }), "meta"); eq(ids(r), ["s1"], "лист убран мной, ими не тронут — убран");
    const r2 = merge3(AM(() => { }), AM(a => a.sheets.splice(1, 1)), AM(a => { a.sheets[1].title = "Правка"; }), "meta"); eq(r2.album.sheets.map(x => x.title), ["Лист 1", "Правка"], "лист убран мной, ими правлен — вернулся с правкой");
    const r3 = merge3(AM(() => { }), AM(() => { }), AM(a => a.sheets.splice(0, 1)), "meta"); eq(ids(r3), ["s2"], "лист убран ими, мной не тронут — убран"); }
  // 5: паспорт альбома правил один, листы целы
  { const i = { conflicts: [] }, r = merge3(AM(() => { }), AM(a => { a.meta.object = "Новый объект"; }), AM(a => { a.sheets[1].title = "Чужое"; }), "meta", i);
    eq([r.album.meta.object, r.album.sheets.map(x => x.title), i.conflicts], ["Новый объект", ["Лист 1", "Чужое"], []], "meta альбома моя, листы чужие");
    const r2 = merge3(AM(() => { }), AM(a => { a.meta.object = "Новый объект"; }), AM(() => { }), "meta"); eq([r2.album.meta.object, ids(r2)], ["Новый объект", ["s1", "s2"]], "только meta.object правлен — листы не тронуты"); }
  // старые листы без id: по месту не сводятся, список целиком; чужой побеждает, без двойников
  { const L = (...t) => t.map(title => ({ title })), i = { conflicts: [] };
    const r = merge3(AM(a => { a.sheets = L("A", "B"); }), AM(a => { a.sheets = L("B"); }), AM(a => { a.sheets = L("A", "B2"); }), "meta", i);
    eq([r.album.sheets.map(x => x.title), i.conflicts], [["A", "B2"], ["album"]], "листы без id: список целиком, чужой, без двойников");
    const i2 = { conflicts: [] }, r2 = merge3(AM(a => { a.sheets = L("A", "B"); }), AM(a => { a.sheets = L("A", "B", "C"); }), AM(a => { a.meta.org = "Х"; a.sheets = L("A", "B"); }), "meta", i2);
    eq([r2.album.sheets.map(x => x.title), r2.album.meta.org, i2.conflicts], [["A", "B", "C"], "Х", []], "листы без id: правил только я — мой список");
    const r3 = merge3(AM(a => { a.sheets.push({ id: "s1", title: "Повтор" }); }), AM(a => { a.sheets.push({ id: "s1", title: "Повтор" }, { id: "m" }); }), AM(a => { a.sheets.push({ id: "s1", title: "Повтор" }); a.sheets[0].title = "T"; }), "meta");
    eq(r3.album.sheets.length, 3, "повтор id в списке: целиком, ничего не потеряно"); }
  // meta.object по-разному, листы не тронуты
  { const i = { conflicts: [] }, r = merge3(AM(() => { }), AM(a => { a.meta.object = "Моё"; }), AM(a => { a.meta.object = "Чужое"; }), "meta", i);
    eq([r.album.meta.object, ids(r), i.conflicts], ["Чужое", ["s1", "s2"], ["album"]], "meta.object по-разному: обычный конфликт «album», листы целы"); }
  // мета-раздела нет ни у кого
  eq(merge3(M(), M(), M(), "meta"), M(), "meta без правок");
}

// перевыгрузка ЕГРН (T3): те же кадастровые номера, новые id портала, шум координат — `_uid` неизменённых участков сохраняется
{
  const N = 120, parcel = (i, id, noise, dx = 0) => ({ type: "Feature", geometry: { type: "Point", coordinates: [37.5 + i * 1e-4 + noise + dx, 55.7] },
    properties: { _key: "77:01:000" + i, "Кадастровый номер": "77:01:000" + i, id_portal: id } });
  const first = ensureUids(fc(...Array.from({ length: N }, (_, i) => parcel(i, "p" + i, 0))), "nspd.parcels");   // то, что на карте
  // новая выгрузка: участок 5 исчез, 0 сдвинут, 999 новый; порядок в списке другой
  const dl = Array.from({ length: N }, (_, i) => i).filter(i => i !== 5).reverse().map(i => parcel(i, "q" + i, 1e-9 * (i % 7), i === 0 ? 5e-5 : 0)).concat(parcel(999, "q999", 0));
  const bare = ensureUids(fc(...dl), "nspd.parcels").features;                    // как было: номер считается заново из места и геометрии
  const curBy = new Map(first.features.map(f => [f.properties._key, f]));
  const old = first.features.map(f => f.properties._uid);
  const kept = dl.map(f => keepUid(f, curBy.get(f.properties._key)));
  const same = kept.filter(f => curBy.has(f.properties._key) && f.properties._uid === curBy.get(f.properties._key).properties._uid).length;
  ok(bare.filter(f => curBy.has(f.properties._key) && f.properties._uid === curBy.get(f.properties._key).properties._uid).length < N * 0.5, "без переноса номера теряются");
  ok(same / (N - 1) >= 0.99, "перенос: >= 99 % прежних номеров (" + same + " из " + (N - 1) + ")");
  eq(kept.find(f => f.properties._key === "77:01:0000").properties._uid, curBy.get("77:01:0000").properties._uid, "геометрия изменилась — номер прежний");
  ok(kept.find(f => f.properties._key === "77:01:0000").geometry.coordinates[0] > 37.5 + 4e-5, "геометрия обновилась");
  ok(!kept.some(f => f.properties._key === "77:01:0005"), "исчезнувший участок не вернулся");
  ok(!old.includes(kept.find(f => f.properties._key === "77:01:000999").properties._uid || "x"), "у нового участка нового номера нет в старых");
  eq(keepUid(dl[0], undefined), dl[0], "нет старого объекта — вход как есть");
}

console.log("collab: " + n + " checks ok");
