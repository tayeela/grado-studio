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


def merged_library(names=("default", "moscow_lgr")):
    """Объединённая библиотека из нескольких JSON (системный уровень).

    Первая — базовая (несёт fallback); стили последующих добавляются к ней.
    Коллизия id стилей — ошибка данных, а не тихое перекрытие."""
    base = load_library(names[0])
    out = {"_doc": base.get("_doc", ""), "styles": dict(base["styles"])}
    if "fallback" in base:
        out["fallback"] = base["fallback"]
    for name in names[1:]:
        lib = load_library(name)
        for sid, s in lib["styles"].items():
            if sid in out["styles"]:
                raise ValueError(f"конфликт id стиля {sid!r}: {name} против {names[0]}")
            out["styles"][sid] = s
    return out


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
_BY_ID_CACHE = {}  # style_id → Style (резолв per-object стилей, см. StyleSet)


class StyleSet:
    def __init__(self, styles=None):
        self.styles = dict(DEFAULT_STYLES)
        if styles:
            self.styles.update(styles)

    def resolve(self, code):
        return self.styles.get(code, FALLBACK)

    def resolve_id(self, style_id):
        """Style по id системной библиотеки (default + Эталон ЛГР) — для
        per-object style_id из модели. None, если id неизвестен."""
        if not style_id:
            return None
        if style_id not in _BY_ID_CACHE:
            s = merged_library()["styles"].get(style_id)
            _BY_ID_CACHE[style_id] = Style.from_json(s) if s else None
        return _BY_ID_CACHE[style_id]

    def legend_entries(self, project):
        """Записи легенды для непустых слоёв проекта.

        Считаем по layer_id (не по коду класса): два слоя одного класса —
        две записи со своими названиями и верными счётчиками, без дублей и
        обращения к чужому слою."""
        entries = []
        for info in project.layers():
            if project.layer_by_id(info["layer_id"]).count() == 0:
                continue
            entries.append((info["code"], info["title"], self.resolve(info["code"])))
        return entries
