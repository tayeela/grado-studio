/* ГРАДО · пять рабочих мест (план 09.11.2026): раскладки окон по ходу работы, как рабочие пространства QGIS и AutoCAD.
   Не шаблоны листов: только какие окна открыты и где. Окна внутри места стыкуются как угодно (dockview), раскладка
   места запоминается на этом компьютере. Окна, которые переносятся на шагах И2–И5, пока показывают, что и когда
   в них появится (panels/StubPanel.vue). */

export interface PanelSpec {
  id: string;
  component: string;
  title: string;
  /** куда встать относительно уже открытого окна */
  at?: { ref: string; dir: "left" | "right" | "above" | "below" | "within" };
  /** для заглушки: что здесь будет и на каком шаге */
  stub?: string;
  size?: number;
}

export interface Workspace {
  id: string;
  n: number;
  title: string;
  hint: string;
  panels: PanelSpec[];
}

export const WORKSPACES: Workspace[] = [
  {
    id: "territory", n: 1, title: "Территория", hint: "найти место, выбрать слой-границу",
    panels: [
      { id: "map", component: "map", title: "Карта" },
      { id: "layers", component: "layers", title: "Слои", at: { ref: "map", dir: "left" }, size: 300 },
      { id: "project", component: "project", title: "Проект", at: { ref: "layers", dir: "within" } },
      { id: "search", component: "stub", title: "Поиск", at: { ref: "map", dir: "right" }, size: 300,
        stub: "Поиск по адресу и кадастровому номеру, участок под адресом — границей. Переезжает на шаге И2." },
    ],
  },
  {
    id: "data", n: 2, title: "Данные и оформление", hint: "слои с нашего сервера, знаки, классы по атрибутам",
    panels: [
      { id: "map", component: "map", title: "Карта" },
      { id: "layers", component: "layers", title: "Слои", at: { ref: "map", dir: "left" }, size: 300 },
      { id: "catalog", component: "stub", title: "Каталог данных", at: { ref: "layers", dir: "within" },
        stub: "Каталог ГИС ОГД и ЕГКО с нашего сервера, слой приходит уже оформленным. Шаг И3." },
      { id: "props", component: "stub", title: "Свойства", at: { ref: "map", dir: "right" }, size: 340,
        stub: "Знак из слоёв как в QGIS, классы по атрибутам, библиотека знаков, стиль из QGIS. Шаг И3." },
      { id: "table", component: "stub", title: "Таблица атрибутов", at: { ref: "map", dir: "below" }, size: 220,
        stub: "Таблица атрибутов слоя. Шаг И3." },
    ],
  },
  {
    id: "design", n: 3, title: "Проект", hint: "черчение командами, ограничения, ТЭП, варианты",
    panels: [
      { id: "map", component: "map", title: "Карта" },
      { id: "layers", component: "layers", title: "Слои", at: { ref: "map", dir: "left" }, size: 280 },
      { id: "tep", component: "stub", title: "Показатели (ТЭП)", at: { ref: "map", dir: "below" }, size: 220,
        stub: "ТЭП считает ядро Rust (уже в 84 раза быстрее Python). Черчение, привязки, ограничения, варианты, схема расчёта — шаг И5." },
    ],
  },
  {
    id: "sheets", n: 4, title: "Виды и листы", hint: "рамки видов на карте, лист рядом",
    panels: [
      { id: "map", component: "map", title: "Карта" },
      { id: "views", component: "stub", title: "Виды", at: { ref: "map", dir: "left" }, size: 300,
        stub: "Набор видов пользователя, рамки по территории, атлас-сетка. Переезжает на шаге И4." },
      { id: "sheet", component: "stub", title: "Лист", at: { ref: "map", dir: "right" }, size: 520,
        stub: "Редактор листа (Konva), легенда за видом, штамп, подписи. Шаг И4." },
    ],
  },
  {
    id: "out", n: 5, title: "Выдача", hint: "готовность листов, PDF, PPTX, DXF",
    panels: [
      { id: "check", component: "check", title: "Проверка проекта" },
      { id: "outlist", component: "stub", title: "Листы и выгрузка", at: { ref: "check", dir: "right" },
        stub: "Список листов с готовностью (пустая карта, не догрузился слой, не поместились подписи), PDF, PPTX, DXF. Шаг И4." },
    ],
  },
];

export const workspace = (id: string) => WORKSPACES.find(w => w.id === id || String(w.n) === id ||
  w.title.toLowerCase().replace(/ё/g, "е").startsWith(id.toLowerCase().replace(/ё/g, "е"))) || null;
