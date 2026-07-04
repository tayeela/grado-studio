"""Стилевая машина: стиль — данные из единой JSON-библиотеки.

Один источник (styles/default.json) кормит три вывода: холст студии,
листы PDF/SVG и DXF (docs/fixes-geometry-layout.md, шаг 3). Здесь стиль
разрешается по коду классификатора в объект Style (цвета — rgb 0..1,
ширина — мм листа); тот же JSON фронт забирает для холста (ширина px),
а DXF-экспорт — для имён слоёв и цветов ACI. Правка одного JSON меняет
все три вывода без изменения кода.
"""

import json
from pathlib import Path

STYLE_DIR = Path(__file__).parent / "styles"
_LIBRARY_CACHE = {}


def load_library(name="default"):
    """Сырая библиотека стилей из JSON (кэш по имени)."""
    if name not in _LIBRARY_CACHE:
        with open(STYLE_DIR / f"{name}.json", encoding="utf-8") as fh:
            _LIBRARY_CACHE[name] = json.load(fh)
    return _LIBRARY_CACHE[name]


def hex_to_rgb(value):
    """'#rrggbb' → (r, g, b) в 0..1; None → None."""
    if value is None:
        return None
    v = value.lstrip("#")
    return tuple(int(v[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


class Style:
    def __init__(self, fill=None, stroke=None, width=0.3, dash=None,
                 label=None, marker=1.2, z=0, hatch=False):
        self.fill = fill          # (r,g,b) 0..1 | None
        self.stroke = stroke      # (r,g,b) | None
        self.width = width        # мм
        self.dash = dash          # [мм, ...] | None
        self.label = label        # имя атрибута для подписи
        self.marker = marker      # радиус маркера точек, мм
        self.z = z                # порядок отрисовки (меньше — ниже)
        self.hatch = hatch        # диагональная штриховка 45° (ЗОУИТ и т.п.)

    @classmethod
    def from_json(cls, s):
        return cls(
            fill=hex_to_rgb(s.get("fill")),
            stroke=hex_to_rgb(s.get("stroke")),
            width=s.get("width_mm", 0.3),
            dash=s.get("dash_mm"),
            label=s.get("label_field"),
            marker=s.get("marker_mm", 1.2),
            z=s.get("z", 0),
            hatch=s.get("hatch", False))


def _build_default_styles(name="default"):
    """code → Style: разворачиваем codes каждого стиля в индекс по коду."""
    lib = load_library(name)
    by_code = {}
    for s in lib["styles"].values():
        st = Style.from_json(s)
        for code in s.get("codes", []):
            by_code[code] = st
    return by_code


# Базовая библиотека к классификатору (продолжение библиотеки QML GRADO),
# теперь построенная из styles/default.json
DEFAULT_STYLES = _build_default_styles()
FALLBACK = Style.from_json(load_library()["fallback"])


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
