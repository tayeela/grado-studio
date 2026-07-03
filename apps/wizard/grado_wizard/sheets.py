"""Листы альбома АГК (презентационный стиль, по образцу реальных альбомов).

Каждый лист: заголовок справа вверху, номер листа в квадратике справа
внизу, карта слева, правая колонка с легендой/таблицами, выноски.
"""

import math

from grado_layout import (A3_LANDSCAPE, CalloutFrame, MapFrame, Page,
                          SectionedLegendFrame, SheetHeader, TableFrame,
                          TextFrame)
from grado_render import project_extent

MAP_RECT = (12, 10, 280, 277)
RIGHT_X, RIGHT_W = 302, 106
NICE_SCALES = [500, 1000, 2000, 2500, 5000, 10000, 20000, 25000, 50000]


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
    scale = fit_scale(project, margin=2.2)
    legend = SectionedLegendFrame(
        (RIGHT_X, 40, RIGHT_W, 60),
        [("Границы:", [("line", doc.styles.resolve("terr.boundary"),
                        "граница территории разработки")])])
    annotation = TextFrame(
        (RIGHT_X, 110, RIGHT_W, 40),
        [f"Разрабатываемая территория",
         f"площадью {area_ha:.2f} га расположена",
         "в границах участков правообладателя"], size=2.8)
    page.frames = [
        SheetHeader(page, ["Расположение рассматриваемой", "территории"], page_no),
        MapFrame(MAP_RECT, scale=scale, layers=["terr.boundary"]),
        legend, annotation]
    return page


def base_plan_sheet(doc, project, page_no):
    page = Page(A3_LANDSCAPE)
    st = doc.styles.resolve
    legend = SectionedLegendFrame(
        (RIGHT_X, 40, RIGHT_W, 150),
        [("Границы:", [
            ("line", st("terr.boundary"), "территории разработки"),
            ("line", st("cad.parcel"), "земельных участков ЕГРН")]),
         ("Ограничения:", [
            ("fill", st("cad.zouit"), "ЗОУИТ"),
            ("fill", st("terr.restrict"), "территории, не подлежащие застройке")]),
         ("Существующее положение:", [
            ("fill", st("tp.func_zone"), "функциональные зоны генплана")])])
    page.frames = [
        SheetHeader(page, ["Опорный план.", "Существующее положение"], page_no),
        MapFrame(MAP_RECT, scale=fit_scale(project),
                 layers=["terr.boundary", "terr.restrict", "cad.zouit",
                         "cad.parcel", "tp.func_zone"]),
        legend]
    return page


def ortho_sheet(doc, project, page_no, underlay, attribution=""):
    """Лист «Ортофотоплан»: снимок-подложка + граница и участки ЕГРН."""
    page = Page(A3_LANDSCAPE)
    st = doc.styles.resolve
    legend = SectionedLegendFrame(
        (RIGHT_X, 40, RIGHT_W, 60),
        [("Границы:", [
            ("line", st("terr.boundary"), "территории разработки"),
            ("line", st("cad.parcel"), "земельных участков ЕГРН")])])
    note = TextFrame((RIGHT_X, 110, RIGHT_W, 20),
                     ["Подложка:", attribution] if attribution else [],
                     size=2.6)
    page.frames = [
        SheetHeader(page, ["Ортофотоплан", "рассматриваемой территории"],
                    page_no),
        MapFrame(MAP_RECT, scale=fit_scale(project),
                 layers=["terr.boundary", "cad.parcel"], underlay=underlay),
        legend, note]
    return page


def _layer_centroid(project, code, bbox_of_all=False):
    from grado_render.scene import centroid, _polygons, _points
    pts = []
    if code not in [i["code"] for i in project.layers()]:
        return None
    for f in project.layer(code).features():
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
    st = doc.styles.resolve
    legend = SectionedLegendFrame(
        (RIGHT_X, 34, RIGHT_W, 120),
        [("Границы:", [
            ("line", st("terr.boundary"), "территории разработки"),
            ("line", st("pp.red_line"), "красные линии (устанавливаемые)")]),
         ("Застройка:", [
            ("fill", st("oks.building"), "жилого назначения"),
            ("fill", st("pp.placement_zone"), "зоны размещения нежилых ОКС"),
            ("point", st("social.object"), "объекты социальной инфраструктуры")]),
         ("Зонирование:", [
            ("fill", st("tp.func_zone"), "функциональные зоны")])])
    d = engine.display
    tep = TableFrame(
        (RIGHT_X, 168, RIGHT_W, 100),
        [("Показатель", 72, "left"), ("Значение", 34, "right")],
        [("Территория", f"{d('terr_area')} га"),
         ("СПП всего", f"{d('spp')} тыс. м²"),
         ("СПП жилых зданий", f"{d('spp_zh')} тыс. м²"),
         ("СПП нежилых зданий", f"{d('spp_nzh')} тыс. м²"),
         ("Население", f"{d('population')} чел"),
         ("Машино-места", f"{d('parking_perm')} мм")],
        title="Технико-экономические показатели")

    x0, y0, x1, y1 = project_extent(project)
    scale = fit_scale(project)
    from grado_render import MapTransform
    tr = MapTransform(MAP_RECT, ((x0 + x1) / 2, (y0 + y1) / 2), scale)
    if callouts is None:
        callouts = default_callouts(project, engine)
    slots = [(18, 18), (18, 244), (200, 250)]  # углы карты под рамки выносок
    frames = []
    for (lines, target), (cx, cy) in zip(callouts, slots):
        frames.append(CalloutFrame((cx, cy, 64, 3 + 4.2 * len(lines)),
                                   lines, tr.to_mm(*target)))
    page.frames = [
        SheetHeader(page, ["Схема архитектурно-планировочной",
                           "организации территории"], page_no),
        MapFrame(MAP_RECT, scale=scale),
        *frames, legend, tep]
    return page


def tep_summary_sheet(doc, engine, page_no):
    page = Page(A3_LANDSCAPE)
    grouped = {}
    for r in engine.results():
        grouped.setdefault(r["group"], []).append(r)
    rows = []
    idx = 0
    for group, items in grouped.items():
        rows.append(("", group, "", ""))
        for r in items:
            idx += 1
            rows.append((str(idx), r["title"], r["unit"], str(r["value"])))
    table = TableFrame(
        (40, 30, 340, 245),
        [("№", 14, "center"), ("Наименование показателей", 240, "left"),
         ("Ед. изм.", 40, "center"), ("Значение", 45, "right")],
        rows)
    page.frames = [
        SheetHeader(page, ["Сводные основные", "технико-экономические показатели"],
                    page_no),
        table]
    return page
