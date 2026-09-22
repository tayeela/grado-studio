"""Листы альбома АГК (презентационный стиль, по образцу реальных альбомов).

Каждый лист: заголовок справа вверху, номер листа в квадратике справа
внизу, карта слева, правая колонка с легендой/таблицами, выноски.
"""

import json
import math
from pathlib import Path

from grado_layout import (A3_LANDSCAPE, CalloutFrame, MapFrame, Page,
                          PageBorder, SectionedLegendFrame, SheetHeader,
                          StampFrame, TableFrame, TextFrame)
from grado_render import project_extent

MAP_RECT = (12, 10, 280, 277)
RIGHT_X, RIGHT_W = 302, 106


class SheetLayout:
    """Раскладка листа A3: где карта, где правая колонка, чем подписан лист.

    Листы описаны в координатах презентационной раскладки: правая колонка
    от y=34 до y=270. Раскладка с основной надписью ГОСТ сжимает колонку
    по высоте над штампом (185×55 в правом нижнем углу рамки 20/5).
    """

    COLUMN_TOP, COLUMN_BOTTOM = 34, 270

    def __init__(self, map_rect, right_x, right_w, top, bottom, stamp):
        self.map = map_rect
        self.right_x, self.right_w = right_x, right_w
        self.top, self.bottom = top, bottom
        self.stamp = stamp
        self.k = (bottom - top) / (self.COLUMN_BOTTOM - self.COLUMN_TOP)

    def right(self, y, h):
        """Прямоугольник правой колонки: y и h заданы в презентационной раскладке."""
        return (self.right_x, self.top + (y - self.COLUMN_TOP) * self.k,
                self.right_w, h * self.k)

    def body(self):
        """Поле листа под таблицу во всю ширину."""
        if self.stamp:
            return (25, 10, 385, self.bottom - 10)
        return (40, 30, 340, 245)

    def callout_slots(self):
        """Углы карты под рамки выносок."""
        x, y, w, h = self.map
        return [(x + 6, y + 8), (x + 6, y + h - 43), (x + w - 92, y + h - 37)]

    def header(self, page, title_lines, page_no):
        """Подпись листа. Заголовок запоминается на листе для основной надписи."""
        page.sheet_title = " ".join(title_lines)
        if self.stamp:
            return [PageBorder(page), StampFrame(page)]
        return [SheetHeader(page, title_lines, page_no)]


PRESENTATION = SheetLayout(MAP_RECT, RIGHT_X, RIGHT_W, 34, 270, stamp=False)
# Рамка 20/5: поле x 20…415, y 5…292; штамп занимает x 230…415, y 237…292.
GOST = SheetLayout((25, 10, 255, 222), 292, 118, 12, 230, stamp=True)


def layout_of(doc):
    return getattr(doc, "layout", PRESENTATION)
NICE_SCALES = [500, 1000, 2000, 2500, 5000, 10000, 20000, 25000, 50000]

# Наборы слоёв листов — декларативно из JSON (шаг 5): лист ссылается на
# имя набора, а не на список кодов.
_TEMPLATES = json.loads(
    (Path(__file__).parent / "album_templates.json").read_text(encoding="utf-8"))


def layerset_layers(project, name):
    """layer_id слоёв набора name (MODEL-01: идентичность, не код класса).

    Набор задан явным списком codes (семантических классов) или фильтром
    по стадии СЛОЯ (exclude_stages/include_stages). Возвращает список
    layer_id — уникальный, поэтому два слоя одного класса (проектный и
    исходный) не схлопываются и не дублируются. Порядок отрисовки задаёт z."""
    spec = _TEMPLATES["layersets"].get(name, {})
    infos = project.layers()
    if "codes" in spec:
        want = set(spec["codes"])
        return [i["layer_id"] for i in infos if i["code"] in want]
    excl, incl = set(spec.get("exclude_stages", [])), set(spec.get("include_stages", []))
    if not excl and not incl:
        return [i["layer_id"] for i in infos]
    # include_codes: классы, которые попадают на лист при любой стадии слоя —
    # граница территории, начерченная в проекте, нужна и на опорном плане
    always = set(spec.get("include_codes", []))
    out = []
    for i in infos:
        stage = i.get("stage")  # стадия слоя (не класса) — учитывает override
        if i["code"] in always:
            out.append(i["layer_id"])
            continue
        if excl and stage in excl:
            continue
        if incl and stage not in incl:
            continue
        out.append(i["layer_id"])
    return out


_STAGE_SECTIONS = (("project", "Проектные решения:"),
                   ("existing", "Существующее положение:"),
                   ("base", "Основа:"))


def sheet_legend(doc, project, layer_ids, max_entries=14):
    """Разделы легенды из слоёв, которые реально есть на листе.

    Знак — тот же, что рисует карта: знак объекта (style_id), иначе знак класса
    слоя. Слой с несколькими знаками даёт строку на каждый знак (функциональные
    зоны, красные линии УДС по LineCode). Прежде легенда была вписана руками и
    не совпадала с картой: синий «ЗОУИТ» при розовой штриховке, без зданий и УДС.
    """
    st = doc.styles
    by_stage = {}
    wanted = set(layer_ids)
    for info in project.layers():
        if info["layer_id"] not in wanted:
            continue
        layer = project.layer_by_id(info["layer_id"])
        if not layer.count():
            continue
        geom = (project.classifier.get(info["code"]).geom_type or "").replace("Multi", "")
        kind = {"Polygon": "fill", "LineString": "line", "Point": "point"}.get(geom, "fill")
        sids = [row[0] for row in project.conn.execute(
            f'SELECT DISTINCT style_id FROM "{info["table"]}" ORDER BY style_id')]
        entries = []
        for sid in sids:
            style = st.resolve_id(sid) if sid else None
            if style is None:
                style = st.resolve(info["code"])
                label = info["title"]
            else:
                label = getattr(style, "title", None) or info["title"]
            if not any(e[2] == label for e in entries):
                entries.append((kind, style, label))
        section = info.get("stage") if info.get("stage") in dict(_STAGE_SECTIONS) else "existing"
        by_stage.setdefault(section, []).extend(entries)
    sections, used = [], 0
    for stage, header in _STAGE_SECTIONS:
        entries = by_stage.get(stage, [])
        if not entries:
            continue
        room = max_entries - used
        if room <= 0:
            break
        shown = entries[:room]
        if len(entries) > room:
            shown = entries[:room - 1] + [("line", st.resolve("generic.line"),
                                           f"…и ещё {len(entries) - room + 1}")]
        sections.append((header, shown))
        used += len(shown)
    return sections


def sheet_layers(doc, project, name):
    """Слои набора листа без слоёв, скрытых пользователем на холсте.

    Скрытый слой не печатается, но в ТЭП участвует: ТЭП считается по
    объектам проекта, а не по картинке."""
    hidden = set(getattr(doc, "hidden_layers", ()) or ())
    return [lid for lid in layerset_layers(project, name) if lid not in hidden]


def fit_scale(project, rect=MAP_RECT, margin=1.12):
    x0, y0, x1, y1 = project_extent(project)
    raw = max((x1 - x0) * 1000 / rect[2], (y1 - y0) * 1000 / rect[3]) * margin
    for s in NICE_SCALES:
        if s >= raw:
            return s
    return int(math.ceil(raw / 10000) * 10000)


def title_sheet(doc, org="ГРАДО", city_year="Москва / 2026"):
    page = Page(A3_LANDSCAPE)
    w, h = page.size
    logo = TextFrame((w - 44, 16, 30, 20), [org], size=4.5, anchor="middle")
    from grado_layout.frames import _rect_ops

    class _Logo(TextFrame):
        def ops(self, ctx):
            return _rect_ops(w - 46, 12, 34, 16, width=0.5) + super().ops(ctx)

    title = TextFrame((28, 165, 250, 60),
                      [line.upper() for line in doc.title.split("\n")], size=7)
    footer = TextFrame((28, h - 30, 100, 10), [city_year], size=3.2)
    page.frames = [_Logo(logo.rect, [org], size=4.5, anchor="middle"),
                   title, footer]
    return page


def location_sheet(doc, project, area_ha, page_no):
    page = Page(A3_LANDSCAPE)
    L = layout_of(doc)
    scale = fit_scale(project, L.map, margin=2.2)
    legend = SectionedLegendFrame(
        L.right(40, 60),
        [("Границы:", [("line", doc.styles.resolve("terr.boundary"),
                        "граница территории разработки")])])
    if isinstance(area_ha, (int, float)) and not isinstance(area_ha, bool):
        area_line = f"площадью {area_ha:.2f} га расположена"
    else:
        area_line = "площадью н/д"
    annotation = TextFrame(
        L.right(110, 40),
        ["Разрабатываемая территория",
         area_line,
         "в границах участков правообладателя"], size=2.8)
    page.frames = [
        *L.header(page, ["Расположение рассматриваемой", "территории"], page_no),
        MapFrame(L.map, scale=scale, layers=sheet_layers(doc, project, "location")),
        legend, annotation]
    return page


def _source_table(project, layer_ids, rect):
    """Таблица источников листа существующего положения: слой → объектов →
    стадия. Ключ — layer_id (не код класса), поэтому два слоя одного класса
    дают две строки с верными названиями и счётчиками, без дублей."""
    STAGE_RU = {"base": "основа", "existing": "исходные данные",
                "project": "проект"}
    rows = []
    for lid in layer_ids:
        layer = project.layer_by_id(lid)
        cnt = layer.count()
        if cnt:
            rows.append((layer.title, str(cnt), STAGE_RU.get(layer.stage, "—")))
    if not rows:
        return None
    return TableFrame(rect,
                      [("Слой", 66, "left"), ("Об.", 14, "right"),
                       ("Источник", 26, "left")],
                      rows, title="Источники данных")


def base_plan_sheet(doc, project, page_no):
    page = Page(A3_LANDSCAPE)
    L = layout_of(doc)
    st = doc.styles.resolve
    layer_ids = sheet_layers(doc, project, "existing_position")
    legend = SectionedLegendFrame(
        L.right(40, 120), sheet_legend(doc, project, layer_ids, max_entries=int(15 * L.k)))
    frames = [
        *L.header(page, ["Опорный план.", "Существующее положение"], page_no),
        MapFrame(L.map, scale=fit_scale(project, L.map), layers=layer_ids),
        legend]
    src = _source_table(project, layer_ids, L.right(170, 100))
    if src:
        frames.append(src)
    page.frames = frames
    return page


def ortho_sheet(doc, project, page_no, underlay, attribution=""):
    """Лист «Ортофотоплан»: снимок-подложка + граница и участки ЕГРН."""
    page = Page(A3_LANDSCAPE)
    L = layout_of(doc)
    st = doc.styles.resolve
    legend = SectionedLegendFrame(
        L.right(40, 60),
        [("Границы:", [
            ("line", st("terr.boundary"), "территории разработки"),
            ("line", st("cad.parcel"), "земельных участков ЕГРН")])])
    note = TextFrame(L.right(110, 20),
                     ["Подложка:", attribution] if attribution else [],
                     size=2.6)
    page.frames = [
        *L.header(page, ["Ортофотоплан", "рассматриваемой территории"],
                  page_no),
        MapFrame(L.map, scale=fit_scale(project, L.map),
                 layers=sheet_layers(doc, project, "ortho"), underlay=underlay),
        legend, note]
    return page


def _layer_centroid(project, code, bbox_of_all=False):
    """Центр объектов ПРОЕКТНЫХ слоёв класса code.

    Слои импорта (здания НСПД/OSM того же класса) не в счёт: выноска схемы
    АПО иначе указывала в середину всего района, за край листа."""
    from grado_render.scene import centroid, _polygons, _points
    pts = []
    layer_ids = [i["layer_id"] for i in project.layers()
                 if i["code"] == code and i.get("stage") == "project"]
    features = (f for lid in layer_ids for f in project.layer_by_id(lid).features())
    for f in features:
        geom = f["geom"]
        if not geom:
            continue
        for poly in _polygons(geom):
            pts.append(centroid(poly[0]))
        for pt in _points(geom):
            pts.append(tuple(pt))
    if not pts:
        return None
    if bbox_of_all:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    return pts[0]


def default_callouts(project, engine):
    """Выноски листа АПО из реальных объектов проекта и чисел движка."""
    d = engine.display
    out = []
    target = _layer_centroid(project, "oks.building", bbox_of_all=True)
    if target:
        out.append((["Многоквартирная жилая застройка",
                     f"СПП жилых зданий: {d('spp_zh')} тыс. кв. м",
                     f"население: {d('population')} чел"], target))
    target = _layer_centroid(project, "social.object")
    if target:
        out.append((["Образовательная организация",
                     f"потребность: {d('school_norm')} мест ОО,",
                     f"{d('doo_norm')} мест ДОО"], target))
    target = _layer_centroid(project, "pp.placement_zone")
    if target:
        out.append((["Зона размещения нежилых ОКС",
                     f"нежилая СПП: {d('spp_nzh')} тыс. кв. м"], target))
    return out


def apo_sheet(doc, project, engine, page_no, callouts=None):
    page = Page(A3_LANDSCAPE)
    L = layout_of(doc)
    st = doc.styles.resolve
    legend = SectionedLegendFrame(
        L.right(34, 120), sheet_legend(doc, project, sheet_layers(doc, project, "apo"),
                                       max_entries=int(15 * L.k)))
    d = engine.display
    tep = TableFrame(
        L.right(168, 100),
        [("Показатель", 72, "left"), ("Значение", 34, "right")],
        [("Территория в границе", f"{d('terr_area')} га"),
         ("Расчётная площадь", f"{d('calc_area')} га"),
         ("СПП всего", f"{d('spp')} тыс. м²"),
         ("СПП жилых зданий", f"{d('spp_zh')} тыс. м²"),
         ("СПП нежилых зданий", f"{d('spp_nzh')} тыс. м²"),
         ("Население", f"{d('population')} чел"),
         ("Машино-места", f"{d('parking_perm')} мм")],
        title="Технико-экономические показатели")

    x0, y0, x1, y1 = project_extent(project)
    scale = fit_scale(project, L.map)
    from grado_render import MapTransform
    tr = MapTransform(L.map, ((x0 + x1) / 2, (y0 + y1) / 2), scale)
    if callouts is None:
        callouts = default_callouts(project, engine)
    slots = L.callout_slots()
    frames = []
    for (lines, target), (cx, cy) in zip(callouts, slots):
        frames.append(CalloutFrame((cx, cy, 64, 3 + 4.2 * len(lines)),
                                   lines, tr.to_mm(*target)))
    page.frames = [
        *L.header(page, ["Схема архитектурно-планировочной",
                         "организации территории"], page_no),
        MapFrame(L.map, scale=scale, layers=sheet_layers(doc, project, "apo")),
        *frames, legend, tep]
    return page


def tep_summary_sheet(doc, engine, page_no):
    page = Page(A3_LANDSCAPE)
    L = layout_of(doc)
    grouped = {}
    for r in engine.results():
        grouped.setdefault(r["group"], []).append(r)
    rows = []
    idx = 0
    # Факт по начерченным зданиям: для концепции это главные цифры, а ниже —
    # потенциал по нормативной плотности. Без факта лист показывал только потенциал.
    fact = getattr(engine, "fact", None) or {}
    if fact.get("spp") is not None:
        rows.append(("", "Застройка по чертежу", "", ""))
        idx += 1
        rows.append((str(idx), "СПП зданий по чертежу", "тыс. м²", str(fact["spp"])))
        idx += 1
        rows.append((str(idx), "Плотность застройки по чертежу", "тыс. м²/га",
                     str(fact.get("density"))))
        if fact.get("floors_unknown"):
            idx += 1
            rows.append((str(idx), "Здания без этажности (не в СПП)", "шт.",
                         str(fact["floors_unknown"])))
    for group, items in grouped.items():
        rows.append(("", "Расчётный потенциал по нормативной плотности"
                     if group == "Застройка" else group, "", ""))
        for r in items:
            idx += 1
            rows.append((str(idx), r["title"], r["unit"], str(r["value"])))
    table = TableFrame(
        L.body(),
        [("№", 14, "center"), ("Наименование показателей", 240, "left"),
         ("Ед. изм.", 40, "center"), ("Значение", 45, "right")],
        rows)
    page.frames = [
        *L.header(page, ["Сводные основные", "технико-экономические показатели"],
                  page_no),
        table]
    return page
