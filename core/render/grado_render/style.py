"""Стилевая машина: стиль — данные из единой JSON-библиотеки.

Один источник (styles/default.json) кормит три вывода: холст студии,
листы PDF/SVG и DXF (docs/archive/studio/fixes-geometry-layout.md, шаг 3). Здесь стиль
разрешается по коду классификатора в объект Style (цвета — rgb 0..1,
ширина — мм листа); тот же JSON фронт забирает для холста (ширина px),
а DXF-экспорт — для имён слоёв и цветов ACI. Правка одного JSON меняет
все три вывода без изменения кода.
"""

import copy
import json
from pathlib import Path

STYLE_DIR = Path(__file__).parent / "styles"
_LIBRARY_CACHE = {}

# QML spritlines: minScale=10000 при hasScaleBasedVisibilityFlag=1 — детальный
# знак ЛГР (штрих + засечки) виден только до 1:10000; на более мелких масштабах
# QGIS показывает spritlines_uds, где MarkerLine нет вовсе. Держим то же и на
# холсте (app.js LGR_DETAIL_MAX_DENOM), и в печати (Style.for_scale).
LGR_DETAIL_MAX_DENOM = 10000

# Пользовательские правки эталонных знаков (глобальные для студии). Накладываются
# ПОВЕРХ сгенерированной библиотеки (default + moscow_lgr) — сам генератор
# tools/gen_moscow_lgr.py и его JSON не трогаются (правило 2 CLAUDE.md). Каждая
# запись — частичный патч знака в формате библиотеки: {style_id: {ключ: значение}}.
# Пусто по умолчанию; заполняется set_style_overrides из style_overrides.json.
_OVERRIDES = {}


def set_style_overrides(overrides):
    """Заменить набор пользовательских правок знаков и пересобрать зависимое.

    Влияет ВЕЗДЕ через один источник: merged_library (per-id стиль → PDF-объекты
    и холст) и DEFAULT_STYLES (стиль слоя по коду → PDF-слои). Кэш резолва по id
    чистим — иначе старый знак застрянет."""
    global _OVERRIDES, DEFAULT_STYLES
    _OVERRIDES = dict(overrides or {})
    _BY_ID_CACHE.clear()
    DEFAULT_STYLES = _build_default_styles()


def style_overrides():
    return dict(_OVERRIDES)


def load_library(name="default"):
    """Сырая библиотека стилей из JSON (кэш по имени)."""
    if name not in _LIBRARY_CACHE:
        with open(STYLE_DIR / f"{name}.json", encoding="utf-8") as fh:
            _LIBRARY_CACHE[name] = json.load(fh)
    return _LIBRARY_CACHE[name]


def merged_library(names=("default", "moscow_lgr", "moscow_genplan",
                          "osm_highway")):
    """Объединённая библиотека из нескольких JSON (системный уровень) +
    пользовательские правки знаков поверх.

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
    # правки эталонных знаков — частичный мердж поверх; новый id (не из
    # библиотеки) не добавляем как знак (правки — только существующих)
    for sid, patch in _OVERRIDES.items():
        if sid in out["styles"] and isinstance(patch, dict):
            out["styles"][sid] = {**out["styles"][sid], **patch}
    return out


def hex_to_rgb(value):
    """'#rrggbb' → (r, g, b) в 0..1; None → None."""
    if value is None:
        return None
    v = value.lstrip("#")
    return tuple(int(v[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _dots_from_json(d):
    """dots из JSON → внутренний вид с rgb-цветом (или None)."""
    if not d:
        return None
    return {"color": hex_to_rgb(d.get("color")),
            "size_mm": d.get("size_mm", 0.6),
            "spacing_mm": d.get("spacing_mm", 2.0)}


class Style:
    def __init__(self, fill=None, stroke=None, width=0.3, dash=None,
                 label=None, marker=1.2, z=0, hatch=False,
                 line_marker=None, double=None, line_label=None,
                 label_size=None, label_color=None, label_font_family=None,
                 ground_units=False, ref_scale=2000, dots=None):
        self.fill = fill          # (r,g,b) 0..1 | None
        self.stroke = stroke      # (r,g,b) | None
        self.width = width        # мм
        self.dash = dash          # [мм, ...] | None
        self.label = label        # имя атрибута для подписи
        self.marker = marker      # радиус маркера точек, мм
        self.z = z                # порядок отрисовки (меньше — ниже)
        self.hatch = hatch        # штриховка: bool (легаси 45°) | dict Эталона
        self.dots = dots          # точечный узор ПОВЕРХ заливки (PointPatternFill): {color(rgb), size_mm, spacing_mm} | None
        self.line_marker = line_marker  # засечки Эталона ЛГР: {shape, period_mm, size_mm}
        self.double = double      # двойная параллельная линия: зазор, мм
        self.line_label = line_label  # повторяющаяся подпись вдоль линии/контура (ЛГР)
        self.label_size = label_size    # кегль подписи, мм (None → label_size сцены)
        self.label_color = label_color  # цвет подписи (r,g,b) | None → дефолт сцены
        self.label_font_family = label_font_family  # ui | serif | mono
        # Знаки ЛГР: в рабочих QML Москвы штрих (customdash_unit=MapUnit) и шаг
        # засечек (interval_unit=MapUnit) заданы в МЕТРАХ НА МЕСТНОСТИ, а в
        # библиотеке записаны в мм для опорного масштаба ref_scale (1:2000).
        # Печать в другом масштабе обязана пересчитать их (see for_scale),
        # иначе рисунок эталонен только при 1:2000 — как это и было.
        self.ground_units = ground_units
        self.ref_scale = ref_scale

    def for_scale(self, scale):
        """Копия стиля, пересчитанная на масштаб листа 1:scale (ровно по QML).

        В рабочих QML Москвы штрих (customdash_unit), шаг (interval_unit) И
        размер (size_unit) засечек заданы в MapUnit — МЕТРАХ НА МЕСТНОСТИ, а в
        библиотеке лежат в мм для опорного ref_scale (1:2000). Множим все три
        на ОДИН коэффициент: штрих и период — обязательно вместе (иначе засечка
        уедет с черты), размер — чтобы знак ужимался пропорционально, а не
        оставался крупным на мелком штрихе.

        Сверх того у spritlines minScale=10000 при hasScaleBasedVisibilityFlag=1
        — детальный знак виден только до 1:10000 (дальше QGIS берёт
        spritlines_uds, где MarkerLine нет). За пределом снимаем засечки.

        Для не-ЛГР стилей (ground_units=False) возвращается сам объект.
        """
        if not self.ground_units or not scale:
            return self
        detail = scale <= LGR_DETAIL_MAX_DENOM
        if scale == self.ref_scale and detail:
            return self
        f = self.ref_scale / float(scale)
        clone = copy.copy(self)
        if self.dash:
            clone.dash = [d * f for d in self.dash]
        if self.line_marker:
            if not detail:
                clone.line_marker = None
            else:
                lm = dict(self.line_marker)
                if lm.get("period_mm"):
                    lm["period_mm"] = lm["period_mm"] * f
                if lm.get("size_mm"):
                    lm["size_mm"] = lm["size_mm"] * f
                # ow (толщина штриха засечки) в QML тоже MapUnit — метры:
                # без пересчёта глиф ужимался, а штрих оставался прежним и
                # засечка вырождалась в кляксу. Множим тем же коэффициентом.
                if lm.get("ow_mm"):
                    lm["ow_mm"] = lm["ow_mm"] * f
                clone.line_marker = lm
        return clone

    @classmethod
    def from_json(cls, s):
        style = cls._from_json(s)
        style.title = s.get("title")  # подпись знака в легенде листа
        return style

    @classmethod
    def _from_json(cls, s):
        return cls(
            fill=hex_to_rgb(s.get("fill")),
            stroke=hex_to_rgb(s.get("stroke")),
            width=s.get("width_mm", 0.3),
            dash=s.get("dash_mm"),
            label=s.get("label_field"),
            marker=s.get("marker_mm", 1.2),
            z=s.get("z", 0),
            hatch=s.get("hatch", False),
            line_marker=s.get("line_marker"),
            double=s.get("double_mm"),
            line_label=s.get("line_label"),
            label_size=s.get("label_size_mm"),
            label_color=hex_to_rgb(s.get("label_color")),
            label_font_family=s.get("label_font_family"),
            ground_units=s.get("ground_units", False),
            ref_scale=s.get("ref_scale", 2000),
            dots=_dots_from_json(s.get("dots")))


def _build_default_styles(name="default"):
    """code → Style: разворачиваем codes каждого стиля в индекс по коду.

    Источник — merged_library (с правками знаков), чтобы правка эталонного
    знака отражалась и на слоях, рисуемых по коду классификатора."""
    lib = merged_library()
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
    def __init__(self, styles=None, id_styles=None, layer_labels=None):
        self.styles = dict(DEFAULT_STYLES)
        # подписи по слоям, как их настроил пользователь на холсте:
        # {layer_id: {"label": поле | None, "line_label": текст | None}}.
        # Ключ есть — значение перекрывает знак; None = подпись выключена.
        self.layer_labels = dict(layer_labels or {})
        if styles:
            self.styles.update(styles)
        # inline-стили по id (напр. «как на холсте» из студии): резолвятся
        # ПЕРЕД системной библиотекой и не идут в глобальный кэш — так один
        # экспорт со своими знаками не влияет на другие. Значения — Style
        # или JSON-словарь (тот же формат, что styles/default.json).
        self.id_styles = {}
        if id_styles:
            for sid, s in id_styles.items():
                self.id_styles[sid] = s if isinstance(s, Style) else Style.from_json(s)

    def resolve(self, code):
        return self.styles.get(code, FALLBACK)

    def resolve_id(self, style_id):
        """Style по id: сперва inline-стили этого набора (студийные «как на
        холсте»), затем системная библиотека (default + Эталон ЛГР) — для
        per-object style_id из модели. None, если id неизвестен."""
        if not style_id:
            return None
        if style_id in self.id_styles:
            return self.id_styles[style_id]
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
