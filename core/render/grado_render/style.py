"""Стилевая машина: стиль — данные, привязанные к коду классификатора.

Оба бэкенда (экранный SVG и печатный PDF) исполняют один и тот же список
операций, собранный сценой по этим стилям, — WYSIWYG гарантирован
отсутствием второй реализации стилизации.
"""


class Style:
    def __init__(self, fill=None, stroke=None, width=0.3, dash=None,
                 label=None, marker=1.2, z=0):
        self.fill = fill          # (r,g,b) 0..1 | None
        self.stroke = stroke      # (r,g,b) | None
        self.width = width        # мм
        self.dash = dash          # [мм, ...] | None
        self.label = label        # имя атрибута для подписи
        self.marker = marker      # радиус маркера точек, мм
        self.z = z                # порядок отрисовки (меньше — ниже)


# Базовая библиотека к классификатору (продолжение библиотеки QML GRADO)
DEFAULT_STYLES = {
    "tp.func_zone": Style(fill=(0.98, 0.94, 0.75), stroke=(0.72, 0.62, 0.35),
                          width=0.25, label="zone_title", z=0),
    "cad.zouit": Style(fill=(0.80, 0.88, 0.97), stroke=(0.45, 0.62, 0.80),
                       width=0.25, dash=[2, 1], z=1),
    "terr.restrict": Style(fill=(0.96, 0.86, 0.86), stroke=(0.75, 0.35, 0.35),
                           width=0.3, dash=[3, 1.5], z=2),
    "oks.building": Style(fill=(0.96, 0.78, 0.42), stroke=(0.55, 0.40, 0.15),
                          width=0.2, label="floors", z=3),
    "cad.parcel": Style(stroke=(0.35, 0.30, 0.20), width=0.2, z=4),
    "uds.road_axis": Style(stroke=(0.40, 0.40, 0.40), width=0.4,
                           dash=[6, 2], z=5),
    "pp.red_line": Style(stroke=(0.85, 0.10, 0.10), width=0.6, z=6),
    "terr.boundary": Style(stroke=(0.10, 0.10, 0.10), width=0.8,
                           dash=[8, 2, 2, 2], z=7),
    "pp.placement_zone": Style(fill=(0.97, 0.76, 0.79), stroke=(0.75, 0.35, 0.42),
                               width=0.35, label="purpose", z=5),
    "social.object": Style(fill=(0.20, 0.45, 0.75), stroke=(0.10, 0.25, 0.45),
                           width=0.2, label="kind", marker=1.5, z=8),
}

FALLBACK = Style(stroke=(0.5, 0.5, 0.5), width=0.3)


class StyleSet:
    def __init__(self, styles=None):
        self.styles = dict(DEFAULT_STYLES)
        if styles:
            self.styles.update(styles)

    def resolve(self, code):
        return self.styles.get(code, FALLBACK)

    def legend_entries(self, project):
        """Записи легенды для слоёв, реально присутствующих в проекте."""
        entries = []
        for info in project.layers():
            if project.layer(info["code"]).count() == 0:
                continue
            entries.append((info["code"], info["title"], self.resolve(info["code"])))
        return entries
