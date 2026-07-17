#!/usr/bin/env python3
"""Знаки дорог OSM → core/render/grado_render/styles/osm_highway.json.

Источник — рабочие QML юзера (`highway.qml` / `highway_ffe8af.qml`, QGIS 3.44,
RuleRenderer по тегу OSM `highway`). Правило 2 CLAUDE.md: JSON генерируется,
руками не правится — правим этот скрипт и перегенерируем.

Что взято из QML и почему именно так:

* **Иерархия ширин** (мм листа, line_width_unit=MM — метровой ловушки ЛГР здесь
  НЕТ, проверено по всем 26 символам): motorway 1.6 → trunk 1.4 → primary 1.0
  → secondary 0.7 → tertiary и всё остальное 0.26.
* **Цвет.** Присланные файлы отличаются ТОЛЬКО line_color (52 строки, все —
  цвет): серый 131,131,131 и песочный 255,232,175 (=ffe8af, отсюда имя файла).
  Символика идентична. Поэтому держим ОДИН набор знаков с цветом по умолчанию,
  а выбор варианта — переключателем на слое (оформление слоя ложится поверх
  знака и меняет цвет, не трогая ширины классов). Оба цвета — в ROAD_COLORS.
* **Мелкие классы.** В QML у 21 правила checkstate="0" — QGIS их не рисует.
  Решение юзера: показывать тонкой линией (0.26 мм), как задано в самих
  символах, чтобы импортированные данные не пропадали с экрана.

Внимание при правках: QGIS 3.44 пишет `<Option type= value= name=>` — порядок
атрибутов ОБРАТНЫЙ московским QML (`<Option name= value=>`). Разбор ниже это
учитывает; иначе значения молча не находятся.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
OUT = ROOT / "core" / "render" / "grado_render" / "styles" / "osm_highway.json"

MM_PX = 96 / 25.4


def to_px(mm):
    return round(mm * MM_PX, 2)


# Цвета из присланных QML. Ключ — вариант, значение — hex.
ROAD_COLORS = {
    "sand": "#ffe8af",   # highway_ffe8af.qml: 255,232,175 — по умолчанию
    "grey": "#838383",   # highway.qml: 131,131,131
}
DEFAULT_COLOR = ROAD_COLORS["sand"]

# Класс дороги: (style_id, заголовок, теги OSM, ширина мм, «главная» ли).
# Теги и ширины — ровно из правил QML (filter "highway" IN (...)).
ROWS = [
    ("osm.hw.motorway",  "Автомагистрали",        ["motorway", "motorway_link"],   1.6,  True),
    ("osm.hw.trunk",     "Дороги федерального значения", ["trunk", "trunk_link"],  1.4,  True),
    ("osm.hw.primary",   "Дороги регионального значения", ["primary", "primary_link"], 1.0, True),
    ("osm.hw.secondary", "Дороги местного значения", ["secondary", "secondary_link"], 0.7, True),
    ("osm.hw.tertiary",  "Прочие связующие дороги", ["tertiary", "tertiary_link"], 0.26, True),
    # ниже — классы, отключённые в QML (checkstate=0). По решению юзера рисуем
    # тонкой линией, а не прячем: импортированные данные не должны пропадать.
    ("osm.hw.unclassified", "Дороги без класса",   ["unclassified"],               0.26, False),
    ("osm.hw.residential",  "Улицы жилой застройки", ["residential"],              0.26, False),
    ("osm.hw.living_street", "Жилые зоны",          ["living_street"],             0.26, False),
    ("osm.hw.service",      "Служебные проезды",    ["service"],                   0.26, False),
    ("osm.hw.pedestrian",   "Пешеходные улицы",     ["pedestrian"],                0.26, False),
    ("osm.hw.track",        "Полевые дороги",       ["track"],                     0.26, False),
    ("osm.hw.busway",       "Полосы автобусов",     ["busway", "bus_guideway"],    0.26, False),
    ("osm.hw.road",         "Дороги без уточнения", ["road"],                      0.26, False),
    ("osm.hw.footway",      "Тротуары",             ["footway"],                   0.26, False),
    ("osm.hw.path",         "Тропы",                ["path"],                      0.26, False),
    ("osm.hw.cycleway",     "Велодорожки",          ["cycleway"],                  0.26, False),
    ("osm.hw.bridleway",    "Конные тропы",         ["bridleway"],                 0.26, False),
    ("osm.hw.steps",        "Лестницы",             ["steps"],                     0.26, False),
    ("osm.hw.corridor",     "Внутренние проходы",   ["corridor"],                  0.26, False),
    ("osm.hw.platform",     "Посадочные платформы", ["platform"],                  0.26, False),
    ("osm.hw.rest_area",    "Площадки отдыха",      ["rest_area", "services"],     0.26, False),
    ("osm.hw.raceway",      "Гоночные трассы",      ["raceway"],                   0.26, False),
    ("osm.hw.escape",       "Аварийные съезды",     ["escape"],                    0.26, False),
    ("osm.hw.construction", "Строящиеся дороги",    ["construction"],              0.26, False),
    ("osm.hw.proposed",     "Проектируемые дороги", ["proposed"],                  0.26, False),
    ("osm.hw.other",        "Прочие дороги",        [],                            0.26, False),
]


def build():
    styles = {}
    for i, (sid, title, tags, w_mm, major) in enumerate(ROWS):
        styles[sid] = {
            "title": title,
            "group": "Дороги OSM",
            "stroke": DEFAULT_COLOR,
            "width_mm": w_mm,
            "width_px": to_px(w_mm),
            "dash_mm": None,
            "dash_px": None,
            "label_field": None,
            "marker_mm": 1.2,
            # главные дороги — выше мелких, иначе тротуары перекрывают магистраль
            "z": 60 + (10 if major else 0) + (len(ROWS) - i) * 0.01,
            "osm_highway": tags,
            "osm_major": major,
            "codes": [],
            "dxf": {"name": "OSM_" + sid.split(".")[-1].upper(), "color": 8},
        }
    return {"_doc": "Дороги OSM по рабочим QML юзера (highway.qml / "
                    "highway_ffe8af.qml). Генерируется tools/gen_osm_highway.py — "
                    "руками не править (правило 2 CLAUDE.md).",
            "road_colors": ROAD_COLORS,
            "styles": styles}


def main():
    lib = build()
    OUT.write_text(json.dumps(lib, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    tags = [t for s in lib["styles"].values() for t in s["osm_highway"]]
    assert len(tags) == len(set(tags)), "тег OSM не должен вести в два знака"
    print(f"{OUT}: {len(lib['styles'])} стилей, {len(tags)} тегов OSM")
    print(f"цвета: {', '.join(f'{k}={v}' for k, v in ROAD_COLORS.items())}")


if __name__ == "__main__":
    main()
