/* ГРАДО 2 · узлы анализа графа (этап Э3): радиусы обслуживания, пешая доступность по улицам, показатели по кварталам,
   баланс территории. Каждый узел объясняет результат словами: у объектов его выхода есть поле «Пояснение», оно
   подписывается на карте, пока узел выбран. «В слой» в окне графа делает выход обычным слоем проекта (Bake). */

// радиусы обслуживания: московские НГП (2151-ПП табл. 1.4.1–1.4.2 п. 4, 2152-ПП табл. 1.3.1 — радиус зависит от округа
// территории, округ берётся из «Показателей») и федеральный СП 42.13330.2016, табл. 10.1 и 10.2. Поликлиники по 2150-ПП
// нормируются временем транспортно-пешеходного маршрута (20 / 30 мин) — радиусом их не проверить, остаётся СП.
const CAO = ok => /Центральн/i.test(ok || ""), TAO = ok => /Троицк/i.test(ok || "");
const SERVICES = {
  "детские сады · Москва (2151-ПП)": { kinds: ["детский сад"], r: ok => CAO(ok) ? 500 : 300, norm: "2151-ПП, табл. 1.4.1 п. 4 (многоквартирная застройка)" },
  "школы · Москва (2151-ПП)": { kinds: ["школа"], r: ok => CAO(ok) ? null : 1000, norm: "2151-ПП, табл. 1.4.2 п. 4 (многоквартирная застройка)" },
  "аптеки и магазины · Москва (2152-ПП)": { kinds: ["аптека"], r: ok => TAO(ok) ? 800 : 500, norm: "2152-ПП, табл. 1.3.1 п. 1.1" },
  "детские сады · 300 м": { kinds: ["детский сад"], r: 300, norm: "СП 42.13330.2016, табл. 10.1" },
  "школы · 500 м": { kinds: ["школа"], r: 500, norm: "СП 42.13330.2016, табл. 10.2" },
  "поликлиники · 1000 м": { kinds: ["поликлиника"], r: 1000, norm: "СП 42.13330.2016, табл. 10.1" },
  "аптеки · 500 м": { kinds: ["аптека"], r: 500, norm: "СП 42.13330.2016, табл. 10.1" } };
const socialPoints = kinds => (DATA["osm.social"]?.fc.features || []).filter(f => f.geometry?.type === "Point" && kinds.includes(f.properties["Вид"]));
const ha2 = f => fmt(m2(f) / 1e4, 2) + " га";

function NRadius() {
  this.addOutput("в радиусе", "geom"); this.addOutput("вне радиуса", "geom");
  this.addWidget("combo", "вид", Object.keys(SERVICES)[0], () => { }, { values: Object.keys(SERVICES) });
  this.addWidget("toggle", "высокоплотная (−30 %)", false, () => { });
  finish(this, "op", 260);
}
NRadius.title = "Радиусы обслуживания"; NRadius.prototype.onExecute = function () {
  const sv = SERVICES[this.widgets[0].value] || Object.values(SERVICES)[0], ok = RESULT.tepNode ? tepParams(RESULT.tepNode).okrug : "";
  const r0 = typeof sv.r === "function" ? sv.r(ok) : sv.r, r = r0 == null ? null : r0 * (this.widgets[1].value ? .7 : 1);
  const pts = socialPoints(sv.kinds), key = [DATA["osm.social"]?.rev, this.widgets[0].value, r, TERR_REV].join("|");
  if (r == null) { this._ck = key; this._out = [null, null]; this._fc = []; this.setOutputData(0, null); this.setOutputData(1, null); this.info = `в ЦАО школа нормируется «в границах ЦАО» (${sv.norm}) — радиусом не проверяется`; return; }
  if (this._ck !== key) {
    this._ck = key;
    const circles = pts.map(p => turf.circle(p, r, { units: "meters", steps: 48, properties: { "Пояснение": `${p.properties["Название"] || p.properties["Вид"]}: ${Math.round(r)} м` } }));
    const cover = unionAll(circles), out = TERR ? diff(TERR, cover) : null;
    this._out = [cover, out];
    this._fc = circles.concat(out ? [turf.feature(out.geometry, { "Пояснение": `вне радиуса ${Math.round(r)} м: ${ha2(out)} — здесь ${sv.kinds[0]} не доступен пешком по норме (${sv.norm})` })] : []);
    this._msg = !DATA["osm.social"] ? "загрузите «Школы, детсады, поликлиники (OSM)» в окне «Данные»" : `${pts.length} объектов · вне радиуса ${out ? ha2(out) : "0 га"} · ${sv.norm}`;
  }
  this.setOutputData(0, this._out[0]); this.setOutputData(1, this._out[1]); this.info = this._msg;
};
LiteGraph.registerNodeType("Анализ/Радиусы обслуживания", NRadius);

/* пешая доступность по сети улиц OSM: граф из линий дорог (кроме автомагистралей), Дейкстра от ближайших к объектам
   узлов, достижимые куски улиц — с буфером 30 м. Скорость 4,5 км/ч (75 м/мин). */
const NO_WALK = new Set(["motorway", "motorway_link", "trunk_link", "construction", "proposed"]);
function walkGraph() {
  const roads = DATA["osm.roads"]?.fc.features || [], key = p => p[0].toFixed(1) + "," + p[1].toFixed(1);
  const nodes = new Map(), adj = [], xy = [];
  const id = p => { const k = key(p); let i = nodes.get(k); if (i === undefined) { i = xy.length; nodes.set(k, i); xy.push(p); adj.push([]); } return i; };
  roads.forEach(f => { if (NO_WALK.has(f.properties["Тип дороги"])) return; const g = f.geometry; (g.type === "LineString" ? [g.coordinates] : g.type === "MultiLineString" ? g.coordinates : []).forEach(line => {
    const ps = line.map(toXY); for (let i = 1; i < ps.length; i++) { const a = id(ps[i - 1]), b = id(ps[i]), d = Math.hypot(ps[i][0] - ps[i - 1][0], ps[i][1] - ps[i - 1][1]); adj[a].push([b, d]); adj[b].push([a, d]); } }); });
  return { xy, adj };
}
function dijkstra(G, starts, D) {
  const dist = new Float64Array(G.xy.length).fill(Infinity), heap = [];
  const push = (d, i) => { heap.push([d, i]); let k = heap.length - 1; while (k > 0) { const p = (k - 1) >> 1; if (heap[p][0] <= heap[k][0]) break; [heap[p], heap[k]] = [heap[k], heap[p]]; k = p; } };
  const pop = () => { const top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; let k = 0; for (;;) { const l = 2 * k + 1, r = l + 1; let m = k; if (l < heap.length && heap[l][0] < heap[m][0]) m = l; if (r < heap.length && heap[r][0] < heap[m][0]) m = r; if (m === k) break; [heap[m], heap[k]] = [heap[k], heap[m]]; k = m; } } return top; };
  starts.forEach(([i, d]) => { if (d < dist[i]) { dist[i] = d; push(d, i); } });
  while (heap.length) { const [d, i] = pop(); if (d > dist[i] || d > D) continue; for (const [j, w] of G.adj[i]) { const nd = d + w; if (nd < dist[j] && nd <= D) { dist[j] = nd; push(nd, j); } } }
  return dist;
}
function NWalk() {
  this.addOutput("доступно пешком", "geom");
  this.addWidget("combo", "вид", Object.keys(SERVICES)[0], () => { }, { values: Object.keys(SERVICES) });
  this.addWidget("slider", "минут пешком", 10, () => { }, { min: 3, max: 30, precision: 0, slider_color: "#9fc0a8" });
  finish(this, "op", 260);
}
NWalk.title = "Пешая доступность"; NWalk.prototype.onExecute = function () {
  const sv = SERVICES[this.widgets[0].value] || Object.values(SERVICES)[0], min = Math.round(this.widgets[1].value), D = min * 75;
  const key = [DATA["osm.roads"]?.rev, DATA["osm.social"]?.rev, this.widgets[0].value, min, LON0].join("|");
  if (this._ck !== key) {
    this._ck = key; this._out = null; this._fc = [];
    if (!DATA["osm.roads"] || !DATA["osm.social"]) { this._msg = "нужны «Улично-дорожная сеть (OSM)» и «Школы, детсады, поликлиники (OSM)»"; }
    else {
      const G = walkGraph(), pts = socialPoints(sv.kinds);
      // от объекта — к ближайшему узлу улиц (не дальше 200 м), это расстояние тоже идёт в счёт
      const starts = pts.map(p => { const q = toXY(p.geometry.coordinates); let best = -1, bd = 200; G.xy.forEach((v, i) => { const d = Math.hypot(v[0] - q[0], v[1] - q[1]); if (d < bd) { bd = d; best = i; } }); return best < 0 ? null : [best, bd]; }).filter(Boolean);
      const dist = dijkstra(G, starts, D), segs = [];
      G.adj.forEach((edges, a) => edges.forEach(([b, w]) => { if (a > b) return; const da = dist[a], db = dist[b], A = G.xy[a], B = G.xy[b];
        if (da + w <= D || db + w <= D || (da <= D && db <= D)) segs.push([A, B]);
        else { if (da < D) { const t = (D - da) / w; segs.push([A, [A[0] + (B[0] - A[0]) * t, A[1] + (B[1] - A[1]) * t]]); } if (db < D) { const t = (D - db) / w; segs.push([B, [B[0] + (A[0] - B[0]) * t, B[1] + (A[1] - B[1]) * t]]); } } }));
      if (segs.length) {
        const ml = turf.multiLineString(segs.map(s => s.map(toLL))), zone = buf(ml, 30);
        this._out = zone;
        const out = TERR && zone ? diff(TERR, zone) : null;
        this._fc = [turf.feature(zone.geometry, { "Пояснение": `${min} мин пешком до: ${sv.kinds[0]} (${pts.length}) — по улицам OSM, 4,5 км/ч` })]
          .concat(out ? [turf.feature(out.geometry, { "Пояснение": `дальше ${min} мин пешком: ${ha2(out)}` })] : []);
      }
      this._msg = `${pts.length} объектов · ${G.xy.length} узлов улиц · ${this._out ? "зона " + ha2(this._out) : "недостижимо"}`;
    }
  }
  this.setOutputData(0, this._out); this.info = this._msg;
};
LiteGraph.registerNodeType("Анализ/Пешая доступность", NWalk);

/* показатели по кварталам: для каждой части входного пятна (квартала между улицами) — СПП, плотность, застроенность и
   средняя этажность существующих зданий (центр здания внутри квартала); без входа «здания» — слой зданий проекта */
function NBlocks() { this.addInput("кварталы", "geom"); this.addInput("здания", "geom"); this.addOutput("кварталы", "geom"); finish(this, "op", 230); }
NBlocks.title = "Показатели кварталов"; NBlocks.prototype.onExecute = function () {
  // без входа — кварталы как территория между улицами (буфер 10 м от линий OSM, кроме тротуаров и дорожек)
  let bl = this.getInputData(0);
  if (!bl && TERR && DATA["osm.roads"]) { this._auto ||= {}; const k = DATA["osm.roads"].rev + "|" + TERR_M2; if (this._auto.k !== k) { const streets = DATA["osm.roads"].fc.features.filter(f => /Line/.test(f.geometry?.type) && !/footway|path|steps|cycleway|service|track|pedestrian/.test(f.properties["Тип дороги"] || "")); this._auto = { k, g: diff(TERR, unionAll(streets.map(f => buf(f, 10)))) }; } bl = this._auto.g; }
  const bi = this.getInputData(1), key = gid(bl) + gid(bi) + dataRev;
  if (this._ck !== key) {
    this._ck = key; this._fc = [];
    const ek = EXIST_KEY(), blds = bi?.properties?._src || (ek ? DATA[ek].fc.features : []), polyB = blds.filter(f => /Polygon/.test(f.geometry?.type));
    const cents = polyB.map(f => ({ f, c: safe(() => turf.pointOnFeature(f)) })).filter(x => x.c);
    this._fc = (bl ? splitParts(bl) : []).filter(p => m2(p) > 500).map((p, i) => {
      const inB = cents.filter(x => safe(() => turf.booleanPointInPolygon(x.c, p))).map(x => x.f), a = m2(p);
      const fp = inB.reduce((s, f) => s + m2(f), 0), spp = inB.reduce((s, f) => s + m2(f) * floorsOf(f), 0), dens = spp / 1000 / (a / 1e4);
      return turf.feature(p.geometry, { "Квартал": i + 1, "Площадь, га": +(a / 1e4).toFixed(2), "Зданий": inB.length, "СПП, тыс. м²": +(spp / 1000).toFixed(1), "Плотность, тыс. м²/га": +dens.toFixed(1),
        "Застроенность, %": +(fp / a * 100).toFixed(1), "Средняя этажность": fp ? +(spp / fp).toFixed(1) : 0,
        "Пояснение": `кв. ${i + 1}: ${fmt(dens, 1)} тыс. м²/га, ${fp ? fmt(spp / fp, 1) : 0} эт., застроено ${fmt(fp / a * 100, 0)} %` });
    });
    this._msg = bl ? `${this._fc.length} кварталов · зданий ${polyB.length}${this.getInputData(0) ? "" : " · кварталы — между улицами OSM"}` : "подайте на вход кварталы или загрузите улицы OSM";
  }
  this.setOutputData(0, bl); this.info = this._msg;
};
LiteGraph.registerNodeType("Анализ/Показатели кварталов", NBlocks);

/* баланс территории: площадь внутри границы по значениям поля входного слоя (функц. зоны, ПЗЗ, землепользование) */
function NBalance() { this.addInput("зоны", "geom"); this.addOutput("территория", "geom"); this.addWidget("text", "поле", "", () => { }); finish(this, "op", 240); }
NBalance.title = "Баланс территории"; NBalance.prototype.onExecute = function () {
  const z = this.getInputData(0), src = z?.properties?._src || [], key = gid(z) + this.widgets[0].value + TERR_REV;
  if (this._ck !== key && TERR) {
    this._ck = key; this._fc = [];
    const fields = [...new Set(src.slice(0, 200).flatMap(f => Object.keys(f.properties || {})))].filter(k => !k.startsWith("_"));
    const field = this.widgets[0].value || fields.find(k => new Set(src.map(f => f.properties[k])).size > 1 && src.every(f => typeof (f.properties[k] ?? "") === "string")) || fields[0];
    if (field && !this.widgets[0].value) this.widgets[0].value = field;
    const by = new Map(); src.filter(f => /Polygon/.test(f.geometry?.type)).forEach(f => { const x = inter(f, TERR); if (!x) return; const v = String(f.properties[field] ?? "—"); (by.get(v) || by.set(v, []).get(v)).push(x); });
    const total = TERR_M2, rows = [...by].map(([v, parts]) => { const u = unionAll(parts); return { v, u, a: m2(u) }; }).sort((a, b) => b.a - a.a);
    const covered = rows.reduce((s, r) => s + r.a, 0);
    this._fc = rows.map(r => turf.feature(r.u.geometry, { [field || "Значение"]: r.v, "Площадь, га": +(r.a / 1e4).toFixed(2), "Доля, %": +(r.a / total * 100).toFixed(1), "Пояснение": `${r.v}: ${fmt(r.a / 1e4, 2)} га (${fmt(r.a / total * 100, 1)} %)` }));
    this._msg = field ? `${rows.length} значений «${field}» · покрыто ${fmt(covered / total * 100, 0)} % территории` : "подайте на вход слой зон (узел «Слой»)";
  }
  this.setOutputData(0, TERR); this.info = this._msg || "нет территории";
};
LiteGraph.registerNodeType("Анализ/Баланс территории", NBalance);

LIB["Анализ"] = ["Анализ/Радиусы обслуживания", "Анализ/Пешая доступность", "Анализ/Показатели кварталов", "Анализ/Баланс территории"]; LIBICON["Анализ"] = "chart-no-axes-combined";
$("lib").innerHTML = Object.entries(LIB).map(([c, ts]) => `<div class="cat">${c}</div>` + ts.map(t => `<button data-add="${t}"><i data-lucide="${LIBICON[c]}"></i>${t.split("/")[1]}</button>`).join("")).join("");

/* «В слой» (Bake): выход выбранного узла — обычный слой проекта; у узлов анализа — с таблицей показателей */
function bakeNode(n) {
  if (!n) return toast("Выберите узел в графе.");
  const out = n.outputs?.findIndex(o => o.type === "geom"), g = out >= 0 ? n.getOutputData(out) : null;
  const feats = n._fc?.length ? n._fc : g ? [turf.feature(g.geometry, { "Узел": n.title })] : [];
  if (!feats.length) return toast("У узла нет геометрии на выходе.");
  const key = "user:" + Date.now().toString(36), title = `Анализ: ${n.title}`, fc = turf.featureCollection(feats.map(f => turf.feature(f.geometry, { ...f.properties })));
  DATA[key] = { title, source: "выход узла графа, " + new Date().toLocaleDateString("ru-RU"), fetched_at: new Date().toISOString().slice(0, 10), fc, count: fc.features.length, fields: [] };
  layerSrc[key] = new ol.source.Vector(); setLayerData(key, fc); delete DATA[key].original;
  const l = ensureLayer(key, title, geomOf(fc)); l.style = ST({ ...l.style, label: "Пояснение", opacity: .35 }); restyle(l); setCurrent(key); dataRev++;
  toast(`Слой «${title}»: ${feats.length} объектов с таблицей показателей. Граф на него больше не влияет.`);
}
$("bBakeNode").onclick = () => bakeNode(selNode);
