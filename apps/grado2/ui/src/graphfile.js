/* ГРАДО 2 · схема расчёта в файле проекта: тот же вид, что пишет рабочая страница (litegraph 0.4: nodes, links,
   widgets_values, properties), чтобы проект открывался в обеих программах. Здесь — описание типов узлов (входы, выходы,
   поля и их значения по умолчанию, как в web/app.js, web/constraints.js и web/analysis.js), схема по умолчанию
   (graph_default.json — снимок DEFAULT_GRAPH рабочей страницы) и приведение схемы старого проекта при открытии.
   Расчёт узлов — graph.js, окно — panels/GraphPanel.vue. */
import DEFAULT_GRAPH from "./graph_default.json";

export const TYPOLOGIES = ["Секции", "Квартал", "Башни", "Точка + секция", "Смешанная", "Урбан-блоки", "Блокированные", "ИЖС"], FLOOR_MODES = ["заданной", "цели плотности"], ROWS = ["прямые", "по границе"];
export const LOWRISE = new Set(["Блокированные", "ИЖС"]);        // не выше 3 этажей: ИЖС — ГрК РФ ст. 1 п. 39, дома блокированной застройки — ст. 49 ч. 2 п. 2
export const SERVICE_KINDS = ["детские сады · Москва (2151-ПП)", "школы · Москва (2151-ПП)", "аптеки и магазины · Москва (2152-ПП)",
  "детские сады · 300 м", "школы · 500 м", "поликлиники · 1000 м", "аптеки · 500 м"];
export const OPS = ["—", "=", "≠", ">", "<", "≥", "≤", "содержит", "один из"];

/* kind — цвет заголовка (как TITLE рабочей страницы); width — ширина узла при масштабе 1; widgets — поля в порядке
   widgets_values: [вид, имя, по умолчанию, {min, max, precision} | список значений] */
export const TYPES = {
  "Данные/Территория": { title: "Территория", kind: "src", width: 170, outputs: [["граница", "geom"]], widgets: [] },
  "Данные/Слой": { title: "Слой", kind: "src", width: 250, outputs: [["объекты", "geom"]],
    widgets: [["combo", "слой", ""], ["combo", "поле", "—"], ["combo", "условие", "—", OPS], ["text", "значение", ""]] },
  "Данные/Ограничения": { title: "Ограничения", kind: "src", width: 220, outputs: [["запреты", "geom"], ["предельная высота", "cap"]], widgets: [] },
  "Параметры/Число": { title: "Число", kind: "num", width: 190, outputs: [["число", "num"]], widgets: [["slider", "значение", 12, { min: 1, max: 40, precision: 0 }]] },
  "Геометрия/Буфер": { title: "Буфер", kind: "op", width: 210, inputs: [["объекты", "geom"], ["расстояние", "num"]], outputs: [["зона", "geom"]],
    widgets: [["slider", "расстояние, м", 10, { min: -30, max: 60, precision: 0 }]] },
  "Геометрия/Вычесть": { title: "Вычесть", kind: "op", width: 170, inputs: [["из", "geom"], ["вычесть", "geom"]], outputs: [["остаток", "geom"]], widgets: [] },
  "Геометрия/Объединить": { title: "Объединить", kind: "op", width: 150, inputs: [["A", "geom"], ["B", "geom"]], outputs: [["A ∪ B", "geom"]], widgets: [] },
  "Геометрия/Пересечь": { title: "Пересечь", kind: "op", width: 150, inputs: [["A", "geom"], ["B", "geom"]], outputs: [["A ∩ B", "geom"]], widgets: [] },
  "Эскиз/Посадка застройки": { title: "Посадка застройки", kind: "gen", width: 240, inputs: [["пятно", "geom"], ["этажность", "num"], ["предельная высота", "cap"]], outputs: [["посадка", "sketch"]],
    props: { run: false },
    widgets: [["combo", "типология", "Секции", TYPOLOGIES], ["slider", "ширина корпуса, м", 16, { min: 12, max: 24, precision: 0 }], ["slider", "этажность", 12, { min: 1, max: 30, precision: 0 }],
      ["slider", "разрыв / высота", 1.0, { min: .5, max: 2, precision: 2 }], ["slider", "поворот, °", 0, { min: -90, max: 90, precision: 0 }], ["combo", "этажность по", "заданной", FLOOR_MODES],
      ["slider", "участок, соток", 10, { min: 4, max: 20, precision: 0 }], ["slider", "квартал, м", 110, { min: 60, max: 200, precision: 0 }], ["toggle", "понижать этажность ради инсоляции", false], ["combo", "ряды", "прямые", ROWS]] },
  "Показатели/ТЭП КРТ": { title: "ТЭП · Москва, «Калькулятор 2.0»", kind: "tep", width: 230, inputs: [["посадка", "sketch"], ["сохраняемые", "geom"], ["ограничения", "geom"]], outputs: [["ТЭП", "tep"]],
    widgets: [["slider", "доля жилья, %", 80, { min: 0, max: 100, precision: 0 }], ["slider", "цель, тыс. м²/га", 25, { min: 5, max: 45, precision: 0 }]] },
  "Анализ/Радиусы обслуживания": { title: "Радиусы обслуживания", kind: "op", width: 260, outputs: [["в радиусе", "geom"], ["вне радиуса", "geom"]],
    widgets: [["combo", "вид", SERVICE_KINDS[0], SERVICE_KINDS], ["toggle", "высокоплотная (−30 %)", false]] },
  "Анализ/Пешая доступность": { title: "Пешая доступность", kind: "op", width: 260, outputs: [["доступно пешком", "geom"]],
    widgets: [["combo", "вид", SERVICE_KINDS[0], SERVICE_KINDS], ["slider", "минут пешком", 10, { min: 3, max: 30, precision: 0 }]] },
  "Анализ/Показатели кварталов": { title: "Показатели кварталов", kind: "op", width: 230, inputs: [["кварталы", "geom"], ["здания", "geom"]], outputs: [["кварталы", "geom"]], widgets: [] },
  "Анализ/Баланс территории": { title: "Баланс территории", kind: "op", width: 240, inputs: [["зоны", "geom"]], outputs: [["территория", "geom"]], widgets: [["text", "поле", ""]] },
};
/* библиотека узлов в окне схемы — как LIB рабочей страницы */
export const LIB = { "Данные": ["Данные/Территория", "Данные/Слой", "Данные/Ограничения"], "Параметры": ["Параметры/Число"],
  "Геометрия": ["Геометрия/Буфер", "Геометрия/Вычесть", "Геометрия/Объединить", "Геометрия/Пересечь"], "Эскиз": ["Эскиз/Посадка застройки"],
  "Показатели": ["Показатели/ТЭП КРТ"], "Анализ": ["Анализ/Радиусы обслуживания", "Анализ/Пешая доступность", "Анализ/Показатели кварталов", "Анализ/Баланс территории"] };
/* цвета заголовков в файле — всегда светлые (файл не зависит от темы того, кто сохранял) */
export const TITLE = { src: "#cfe3d4", op: "#d6dade", gen: "#cfdcf0", tep: "#e3d6ec", num: "#f0e3c8" };

export const defaultGraph = () => JSON.parse(JSON.stringify(DEFAULT_GRAPH));
/* высота узла как у litegraph computeSize + 16 на строку пояснения (web/app.js finish) */
export const nodeHeight = (nIn, nOut, nW) => Math.max(nIn, nOut, 1) * 20 + 6 + (nW ? nW * 24 + 8 : 0) + 16;

/* Схема при открытии: нет схемы — схема по умолчанию (как новый проект рабочей страницы); у узла старой версии нет
   нового поля — значение как у рабочей страницы (web/project.js: «этажность по» — «заданной», остальное — минимум или 0). */
export function normGraph(p) {
  if (!p.graph || !Array.isArray(p.graph.nodes)) p.graph = defaultGraph();
  const g = p.graph;
  g.links ||= []; g.groups ||= []; g.config ||= {}; g.extra ||= {}; g.version ??= 0.4;
  g.last_node_id ??= Math.max(0, ...g.nodes.map(n => n.id)); g.last_link_id ??= Math.max(0, ...g.links.filter(Boolean).map(l => l[0]));
  for (const n of g.nodes) {
    const t = TYPES[n.type]; if (!t?.widgets.length) continue;
    if (n.type === "Эскиз/Посадка застройки" && Array.isArray(n.widgets_values) && n.widgets_values.length < 6) n.widgets_values[5] = "заданной";
    n.widgets_values ||= [];
    t.widgets.forEach((w, i) => { if (n.widgets_values[i] === undefined) n.widgets_values[i] = (w[3]?.min ?? 0) > 0 ? w[3].min : 0; });
  }
  return g;
}
