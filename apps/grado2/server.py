"""ГРАДО 2: локальный сервер.

Отдаёт веб-интерфейс из web/ и два метода:
  POST /api/fetch  {bbox:[w,s,e,n], sources:[ключ,...]} → реальные слои по области
  POST /api/tep    {terr_ha, restrict_ha, spp_new_m2, share, spp_kept_m2} → ТЭП (методика КРТ)
  POST /api/import/files {files:[{name, b64}]} → слои из GeoJSON, KML/KMZ, Shapefile, DXF (WGS84)
  POST /api/export/sat {center, rect, scale | bbox, base} → спутник Яндекса по рамке листа в МСК для AutoCAD (zip: JPG, JGW, DXF)
  POST /api/print/pdf {meta, sheets:[…]} → альбом PDF (листы А3/А1, рамка и штамп ГОСТ), /api/print/pptx → тот же альбом
  редактируемой презентацией PowerPoint, /api/print/svg → лист для просмотра
  GET  /api/projects, GET|POST /api/project?name=… | ?autosave=1 → проекты в «Документы/ГРАДО 2»

Данные берутся коннекторами ядра (core/connectors), ТЭП — движком ядра (core/compute).
Геометрия на выходе всегда WGS84 (GeoJSON), без пересчёта в СК холста.
HTTP — Starlette под uvicorn, тела запросов проверяет pydantic (раздел «HTTP» ниже).

Запуск: python3 apps/grado2/server.py [порт] [--hub]   (по умолчанию 8650; --hub или GRADO2_HUB=1 — совместный режим)
"""

import contextlib
import hashlib
import hmac
import ipaddress
import json
import math
import os
import re
import sys
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qs, quote, unquote

from pydantic import AfterValidator, BaseModel, ConfigDict, ValidationError, field_validator
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

# ---------- Пути, папка проектов, настройки запуска ----------
# в собранной программе (PyInstaller) всё лежит в папке распаковки sys._MEIPASS: web/, core/…, docs/standards/
FROZEN = getattr(sys, "frozen", False)
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
for sub in ("core/connectors", "core/compute", "core/render", "core/layout", "core/geom"):
    sys.path.insert(0, str(ROOT / sub))

from grado_compute import Engine                                   # noqa: E402
from grado_connectors import crs                                   # noqa: E402
from grado_connectors.contract import ConnectorError               # noqa: E402
from grado_connectors.fgistp import FgistpConnector                # noqa: E402
from grado_connectors.gisogd_api import GISOGD_API_LAYERS, GisogdApi  # noqa: E402
from grado_connectors import geocode as geocode_mod                # noqa: E402
from grado_connectors import nspd as nspd_mod                      # noqa: E402
from grado_connectors.nspd import NspdDirect                       # noqa: E402
from grado_connectors.osm import OsmOverpass                       # noqa: E402
from grado_connectors.terrain import TerrainContours               # noqa: E402
from grado_connectors.yandex_vmap import YandexVmap                # noqa: E402
from grado_render import acad_lin                                  # noqa: E402
import hub as hubmod                                               # noqa: E402  совместный режим (GRADO2_HUB=1)

WEB = ROOT / "web" if FROZEN else Path(__file__).resolve().parent / "web"
CACHE = Path.home() / ".grado2" / "cache"
PRESET = ROOT / "core/compute/grado_compute/presets/moscow_calc2.json"      # методика «Калькулятора 2.0» (docs/standards/moscow-ngp)
DISTRICTS = json.loads((ROOT / "core/compute/grado_compute/regulations/moscow_districts.json").read_text("utf-8"))
STYLES = ROOT / "core/render/grado_render/styles"
STYLE_FILES = {"redln97.json", "moscow_lgr.json", "moscow_genplan.json"}   # отдаются фронту как есть
# проекты — обычные файлы .grado2 (JSON) в папке документов: их видно в Finder/Проводнике, их можно переслать
PROJECTS = Path(os.environ.get("GRADO2_PROJECTS") or Path.home() / "Documents" / "ГРАДО 2")
AUTOSAVE = ".autosave"

# ---------- Источники данных: ключ слоя → (вид, параметр, название) ----------
# ключ → (коннектор, параметр, название слоя)
SOURCES = {
    "nspd.parcels": ("nspd", [36368], "Земельные участки (ЕГРН)"),
    "nspd.buildings": ("nspd", [36369], "Здания (ЕГРН)"),
    "nspd.zouit": ("nspd", [469038, 469039, 469040, 469041, 469042], "ЗОУИТ (ЕГРН)"),
    "osm.roads": ("osm", "roads", "Улично-дорожная сеть (OSM)"),
    "osm.buildings": ("osm", "buildings", "Здания (OSM)"),
    "osm.water": ("osm", "water", "Водные объекты (OSM)"),
    "osm.landuse": ("osm", "landuse", "Землепользование (OSM)"),
    "osm.social": ("osm", "social", "Школы, детсады, поликлиники (OSM)"),
    "osm.nature": ("osm", "nature", "Природные территории (OSM)"),
}
# все линии Сводного плана (СПРИТ, раздел 11 портала): красные линии УДС (1.1), общего пользования (1.2), линейных
# объектов (1.3), ОДМС (1.4), зон транспортных сооружений (1.4.1), водоохранных зон (2.6), ПЗП (2.7), ООПТ и режимов
# (3.2), ОКС на ООПТ, береговых полос (3.5), природного комплекса (3.6, 3.6.1), техзон инженерных коммуникаций (3.7).
# Прежде бралась только 1.1 — на листе ТиНАО не было ни техзон, ни границ ПК (владелец 30.09.2026). Код знака — LineCode.
SOURCES["gisogd.red_lines"] = ("gisogd", dict.fromkeys(["l1", "l2", "l3", "l4", "l25", "l16", "l17", "l7", "l57", "l8", "l41",
                                                        "l18", "l21", "l29"]), "Красные линии и ЛГР (ОГД)")
for _k in ("gisogd.func_zones", "gisogd.func_zones_tinao", "gisogd.szz", "gisogd.vodookhr"):
    SOURCES[_k] = ("gisogd", GISOGD_API_LAYERS[_k]["codes"], GISOGD_API_LAYERS[_k]["title"])
# ПЗЗ Москвы (120-ПП): подзоны несут регламент — предельные плотность, высоту и процент застройки;
# зоны — виды разрешённого использования. Старая и новая Москва — разные слои портала (коды сверены 23.09.2026).
SOURCES["gisogd.pzz_sub"] = ("gisogd", {"virtual98": None, "virtual132": None}, "ПЗЗ: подзоны — плотность, высота, застроенность (ОГД)")
SOURCES["gisogd.pzz_zones"] = ("gisogd", {"virtual90": None, "virtual130": None}, "ПЗЗ: территориальные зоны и ВРИ (ОГД)")
SOURCES["gisogd.okn"] = ("gisogd", {"virtual500": None, "virtual502": None, "virtual504": None, "virtual508": None}, "Объекты культурного наследия и их зоны (ОГД)")
# ЗОУИТ и зоны ограничений по Сводному плану (СПРИТ, раздел 11: 2.x и 3.5) — по всей Москве, включая ТиНАО; слой
# Генплана «Водоохранная зона» (gisogd.vodookhr) в ТиНАО пуст (сверено 26.09.2026 на КРТ 3141, Вороново).
# Слой, который портал не отдал, пропускается с пометкой — остальные зоны приходят (ZONES_TOLERANT).
SOURCES["gisogd.zouit"] = ("gisogd", {
    "virtual109": "Водоохранная зона", "virtual111": "Прибрежная защитная полоса", "virtual1521": "Береговая полоса",
    "virtual2386": "Зона затопления", "virtual2385": "Зона сильного подтопления", "virtual2384": "Зона умеренного подтопления",
    "virtual2383": "Зона слабого подтопления", "virtual115": "Санитарно-защитная зона (ПЗЗ)", "virtual13": "Зона охраняемого объекта",
    "virtual120": "Зона военного объекта", "virtual121": "Охранная зона радиотехнического объекта", "virtual122": "Охранная зона ООПТ",
    "virtual123": "Охранная зона объектов электроэнергетики", "virtual124": "Охранная зона линий и сооружений связи",
    "virtual126": "Охранная зона пунктов наблюдений", "virtual3097": "Охранная зона геодезических пунктов",
    "oozt_08_12_2017": "Особо охраняемая зелёная территория",
    # зоны трубопроводов (раздел 3 портала; слои 2.16 и 2.19 Сводного плана отвечают ошибкой 500, 30.09.2026)
    "virtual521": "Охранная зона трубопровода", "virtual": "Зона минимальных расстояний до трубопроводов"}, "ЗОУИТ и зоны ограничений (ОГД)")
# приаэродромные территории по подзонам (раздел 3 портала) — на листах пишутся под легендой, как в примере «Хатминки»
SOURCES["gisogd.airfield"] = ("gisogd", {
    "virtual546": "Внуково|1", "virtual547": "Внуково|2", "virtual548": "Внуково|3", "virtual550": "Внуково|4",
    "virtual552": "Внуково|5", "virtual554": "Внуково|6", "virtual535": "Шереметьево|1", "virtual536": "Шереметьево|2",
    "virtual539": "Шереметьево|3", "virtual541": "Шереметьево|4", "virtual544": "Шереметьево|5", "virtual545": "Шереметьево|6",
    "virtual1737": "Остафьево (Черное)|6"}, "Приаэродромные территории (ОГД)")
ZONES_TOLERANT = {"gisogd.zouit", "gisogd.airfield"}
SOURCES["gisogd.demolition"] = ("gisogd", {"t_1322": None}, "Уведомления о сносе (ОГД)")
SOURCES["relief.contours"] = ("terrain", None, "Рельеф: горизонтали (SRTM)")
# для листов раздела «Существующее положение»: утверждённая документация по планировке и административное деление
SOURCES["gisogd.ppt"] = ("gisogd", {"ppppppt": "ПП территории", "pppppptpu": "ПП транспортно-пересадочного узла",
                                    "ppppppulom": "ПП линейного объекта метрополитена", "ppppppulot": "ПП линейного объекта трамвая",
                                    "pppppplois": "ПП линейного объекта инженерных сооружений",
                                    "ppppppulouds": "ПП участка улично-дорожной сети", "ppppppulozhd": "ПП участка железной дороги",
                                    "pptppr": "ПП по программе реновации", "ppppppt2": "ПП КРТ"}, "Проекты планировки (ОГД)")
SOURCES["gisogd.gpzu"] = ("gisogd", {"gpzu": None}, "Градостроительные планы земельных участков (ОГД)")
SOURCES["gisogd.krt"] = ("gisogd", {"pzz_krt_virtual": None}, "Комплексное развитие территорий (ОГД)")
# листы «Обеспеченность документацией» по образцу «ГК Царицыно»: ПМТ (кварталы с проектами межевания) и АГР
SOURCES["gisogd.pmt"] = ("gisogd", {"pmtgk": None}, "Проекты межевания территории (ОГД)")
SOURCES["gisogd.agr"] = ("gisogd", {"suagr": None}, "Свидетельства об утверждении АГР (ОГД)")
SOURCES["gisogd.admin"] = ("gisogd_admin", None, "Административные округа и районы")
# эталон административного деления (run_admin); метка ADMIN_REV — в albums.js та же: другая метка в проекте — слой берётся заново
ADMIN_FILE, ADMIN_REV = ROOT / "docs" / "standards" / "admin" / "moscow-adm.geojson", "эталон 27.09.2026"
# ЕГКО Москвы — векторная картооснова портала ГИС ОГД (карта base2, коды сверены 23.09.2026). Значение кода — состояние
# здания: оно идёт в поле «Состояние», как тип зоны в «Вид зоны» у функциональных зон ТиНАО.
SOURCES["egko.buildings"] = ("egko", {"virtual6": "действующее", "virtual15": "строящееся", "virtual16": "разрушенное",
                                      "virtual17": "нулевой цикл (фундамент)"}, "Здания (ЕГКО)")
SOURCES["egko.roads"] = ("egko", {"dorogi_pol": None}, "Дороги (ЕГКО)")
SOURCES["egko.paths"] = ("egko", {"tropinki": None}, "Пешеходные дороги (ЕГКО)")
SOURCES["egko.green"] = ("egko", {"gazons": "газон", "forest": "растительность"}, "Газоны и растительность (ЕГКО)")
# тонкие реки и ручьи — линиями: по ним ставятся подписи узких рек (подпись на русле, владелец 30.09.2026)
SOURCES["egko.water"] = ("egko", {"hidrograf": None, "tonkie_reki": None}, "Водная поверхность (ЕГКО)")
# подписи рек и водоёмов картоосновы («р. Моча», «пр.») — точки с текстом, как их ставит ЕГКО
SOURCES["egko.water_labels"] = ("egko", {"podpisi_k_vodnoj_poverhnosti": None, "podpisi_k_tonkim_rekam_i_ruchjam": None},
                                "Подписи рек и водоёмов (ЕГКО)")
# пояснительные подписи картоосновы: деревни и СНТ («Д. БЕЗОБРАЗОВО») — населённые пункты подписываются на листах всегда
SOURCES["egko.place_labels"] = ("egko", {"pojasnitelnye_podpisi": None}, "Пояснительные подписи (ЕГКО)")
SOURCES["egko.fences"] = ("egko", {"fence2k": None}, "Заборы (ЕГКО)")
SOURCES["egko.addresses"] = ("egko", {"adres": None}, "Адреса (ЕГКО)")
EGKO_EXTRA = {"egko.buildings": "Состояние", "egko.green": "Вид"}     # куда пишется значение кода слоя
# Яндекс Карты — векторные тайлы vmap3 (core/connectors/grado_connectors/yandex_vmap.py): слои тайла → ключ ГРАДО 2.
# Для анализа и эскиза; в сдаваемые материалы не включать. POI и организации не выгружаются (решение владельца).
SOURCES["yandex.hd_roads"] = ("yandex", ["hd_road_surface"], "Проезжая часть (Яндекс)")
SOURCES["yandex.buildings"] = ("yandex", ["building"], "Здания (Яндекс)")
SOURCES["yandex.roads"] = ("yandex", ["road"], "Оси дорог и дорожек (Яндекс)")
SOURCES["yandex.road_edges"] = ("yandex", ["hd_road_surface_border"], "Кромки проезжей части (Яндекс)")
SOURCES["yandex.landuse"] = ("yandex", ["landuse_a"], "Функциональные зоны (Яндекс)")
SOURCES["yandex.green"] = ("yandex", ["vegetation", "vegetation_planned", "hd_road_vegetation"], "Озеленение (Яндекс)")
SOURCES["yandex.water"] = ("yandex", ["hydro_a", "hydro_l"], "Вода (Яндекс)")
SOURCES["yandex.parking"] = ("yandex", ["parking_p"], "Парковки (Яндекс)")
SOURCES["yandex.transport"] = ("yandex", ["transport_p", "transport_way"], "Транспорт (Яндекс)")
# Ситуационный план (лист А4, 1:10 000–1:25 000): те же тайлы Яндекса, но с z16 — в 16 раз меньше тайлов на ту же площадь.
# Содержание то же, координаты округлены к сетке тайла (~1,3 м; на листе 1:10 000 это 0,1 мм). На холсте эти слои —
# только обзорные. Качаются в один поток. Отдельные ключи — чтобы подробные слои холста (z18) не заменялись грубыми.
SIT_ZOOM = 16
SOURCES["sit.green"] = ("yandex_sit", ["vegetation", "vegetation_planned", "hd_road_vegetation"], "Ситплан: озеленение (Яндекс)")
SOURCES["sit.water"] = ("yandex_sit", ["hydro_a"], "Ситплан: вода (Яндекс)")
SOURCES["sit.roads_hd"] = ("yandex_sit", ["hd_road_surface"], "Ситплан: проезжая часть (Яндекс)")
SOURCES["sit.roads"] = ("yandex_sit", ["road"], "Ситплан: оси дорог (Яндекс)")
SOURCES["sit.buildings"] = ("yandex_sit", ["building"], "Ситплан: здания (Яндекс)")
SOURCES["sit.rail"] = ("yandex_sit", ["transport_way"], "Ситплан: железная дорога, главные пути (Яндекс)")
# железная дорога листов альбома — главные пути подробного уровня (z18), как на ситплане (владелец 05.10.2026)
SOURCES["yandex.rail"] = ("yandex", ["transport_way"], "Железная дорога, главные пути (Яндекс)")
# станции рельсового каркаса (правило 16 label-rules.md): метро, МЦК и МЦД — точки transport_p типа transport-metro-station,
# по одной на каждую линию: network moscow_metro (line moscow_metro-14 — МЦК, остальные — метро) или moscow_mcd (line
# moscow_mcd-D1…D5); закрытые (closed = 1) не берутся. Разбор видов — web/railstations.js. Тайлы те же, что у yandex.rail
SOURCES["yandex.stations"] = ("yandex", ["transport_p"], "Станции метро, МЦК и МЦД (Яндекс)")
# станции на карте района (#47): та же точка transport_p, но крупным тайлом z16, как ситплан, — рамка района (≈ 10 × 6 км) в предел
# тайлов z18 не входит
SOURCES["sit.stations"] = ("yandex_sit", ["transport_p"], "Ситплан: станции метро, МЦК и МЦД (Яндекс)")
# топонимы Яндекса (владелец 07.10.2026, #47: «попробуй взять топонимы из яндекса»): подписи улиц — линии road_label прямо по дорогам
# Яндекса (те же, что на снимке и в полигонах проезжей части), станции железной дороги — точки на путях, названия природных и
# городских территорий — place_label и крупные poi. Подробный уровень (z18) — листы-схемы, крупный (z16) — карта района
SOURCES["yandex.road_labels"] = ("yandex", ["road_label"], "Подписи улиц (Яндекс)")
SOURCES["yandex.rail_stations"] = ("yandex", ["transport_p"], "Станции железной дороги (Яндекс)")
SOURCES["sit.road_labels"] = ("yandex_sit", ["road_label"], "Ситплан: подписи улиц (Яндекс)")
SOURCES["sit.places"] = ("yandex_sit", ["place_label", "poi"], "Ситплан: названия территорий (Яндекс)")
_YA_RAIL = lambda p: p.get("ft_type_name") in ("transport-railway-station", "transport-railway-halt", "transport-railway-platform") and str(p.get("closed")) != "1"
# poi природных территорий: «vegetation-natpark» (национальный парк), заповедники, леса, парки; парковки («parking») — нет
_YA_AREA = lambda p: (p.get("grado_layer") == "place_label" and p.get("type") in ("named_area", "district", "park", "forest", "nature")) or \
    (p.get("grado_layer") == "poi" and bool(re.search(r"natpark|nature|reserve|forest|-park$", str(p.get("ft_type_name") or ""))))
SIT_FILTER = {"yandex.rail_stations": _YA_RAIL, "sit.places": _YA_AREA,
              "sit.stations": lambda p: p.get("ft_type_name") == "transport-metro-station" and str(p.get("closed")) != "1",
              "sit.rail": lambda p: p.get("ft_type_name") == "transport-railway",   # без подъездных путей и веток
              "yandex.rail": lambda p: p.get("ft_type_name") == "transport-railway",
              "yandex.stations": lambda p: p.get("ft_type_name") == "transport-metro-station" and str(p.get("closed")) != "1"}

# ---------- Пределы области выгрузки, разбиение на части, подписи полей ----------
# Предел области выгрузки. НСПД и Overpass за один запрос берут не больше TILE_KM2: область больше делится на равные
# части, они запрашиваются по очереди, объекты склеиваются (общие для двух частей — по ключу объекта, один раз).
# ОГД и ЕГКО режутся из кэша слоя на диске; Яндекс сам склеивает тайлы, предел у него — время первой выгрузки
# (около минуты на 1 км²).
LIMIT_KM2 = {"gisogd_admin": 1e9, "nspd": 250.0, "osm": 150.0, "gisogd": 150.0, "egko": 150.0, "terrain": 150.0, "yandex": 40.0, "yandex_sit": 150.0}
TILE_KM2 = {"nspd": 4.0, "osm": 25.0, "egko": 150.0}
# T70: не больше MAX_TILES частей за одну выгрузку OSM и ЕГКО (по очереди, с паузой TILE_PAUSE_S); больше — отказ с сообщением
MAX_TILES = 16
TILE_PAUSE_S = 1.0
TILE_CAPPED = {"osm": "OSM", "egko": "ЕГКО"}
DATA_MARGIN_M = 60.0     # поле вокруг границы территории: область данных «граница + 60 м»

# читаемые имена полей; остальные поля проходят как есть
LABELS = {
    "opt_cad_num": "Кадастровый номер", "opt_readable_address": "Адрес",
    "opt_permitted_use_established_by_document": "ВРИ", "opt_land_record_category_type": "Категория земель",
    "opt_land_record_area": "Площадь участка, м²", "opt_ownership_type": "Форма собственности",
    "opt_cost_value": "Кадастровая стоимость, ₽", "opt_floors": "Этажность", "opt_purpose": "Назначение",
    "opt_build_record_area": "Площадь, м²", "opt_materials": "Материал стен", "opt_year_built": "Год постройки",
    "opt_cultural_heritage_val": "ОКН", "opt_status": "Статус",
    "opt_underground_floors": "Подземных этажей", "opt_year_commisioning": "Год ввода", "opt_building_name": "Наименование",
    "opt_specified_area": "Площадь уточнённая, м²", "opt_land_record_type": "Вид объекта", "opt_right_type": "Вид права",
    "building:levels": "Этажность", "name": "Название", "highway": "Тип дороги", "building": "Тип здания",
    "landuse": "Землепользование", "leisure": "Отдых", "natural": "Природа", "waterway": "Водоток",
    "railway": "Железная дорога",
}
NUMERIC = {"Этажность", "Год постройки", "Площадь, м²", "Площадь участка, м²", "Кадастровая стоимость, ₽",
           "Подземных этажей", "Год ввода", "Площадь уточнённая, м²", "Высота, м", "Длина, м", "Уровень"}


def bbox_km2(b):
    w, s, e, n = b
    return abs(e - w) * 111.32 * math.cos(math.radians((s + n) / 2)) * abs(n - s) * 110.54


def territory_bbox(territory, margin_m=DATA_MARGIN_M):
    """Прямоугольник территории [w, s, e, n] + поле в метрах (область данных листов вместо рамки листа)."""
    w, s, e, n = [float(v) for v in territory]
    dy = margin_m / 110540.0
    dx = margin_m / (111320.0 * math.cos(math.radians((s + n) / 2)))
    return [w - dx, s - dy, e + dx, n + dy]


def split_bbox(b, tile_km2):
    """Прямоугольник WGS84 → равные части, каждая не больше tile_km2 (с запасом 3 %)."""
    w, s, e, n = b
    kx = 111.32 * math.cos(math.radians((s + n) / 2))
    side = math.sqrt(tile_km2 * 0.97)
    nx, ny = max(1, math.ceil(abs(e - w) * kx / side)), max(1, math.ceil(abs(n - s) * 110.54 / side))
    dx, dy = (e - w) / nx, (n - s) / ny
    return [(w + i * dx, s + j * dy, w + (i + 1) * dx, s + (j + 1) * dy) for j in range(ny) for i in range(nx)]


def merge_layers(parts):
    """Слои одного источника из нескольких частей области → один слой. Объект на стыке частей приходит в обеих:
    он берётся один раз по ключу источника (_key), без ключа — по геометрии и полям."""
    seen, feats = set(), []
    for p in parts:
        for f in p["features"]["features"]:
            sig = f["properties"].get("_key") or json.dumps([f["geometry"], f["properties"]], sort_keys=True, ensure_ascii=False)
            if sig not in seen:
                seen.add(sig)
                feats.append(f)
    notes = list(dict.fromkeys(n for p in parts for n in p.get("notes") or []))
    return {**parts[0], "notes": notes, "features": {"type": "FeatureCollection", "features": feats}}


def clean_props(props, extra=None, only_labeled=False):
    """only_labeled: оставить только поля с русским названием (у НСПД остальное — служебные коды портала)."""
    out = {}
    for k, v in (props or {}).items():
        if k.startswith("grado_") or v in (None, "") or isinstance(v, (dict, list)) or (only_labeled and k not in LABELS):
            continue
        name = LABELS.get(k, k)
        if name in NUMERIC:
            try:
                v = float(str(v).replace(",", ".").split("-")[0])
                v = int(v) if v.is_integer() else v
            except ValueError:
                pass
        out[name] = v
    out.update(extra or {})
    return out


def _v(v):
    """Пустые значения порталов: None, 'None', '', пробел."""
    return None if v is None or str(v).strip() in ("", "None", "nan") else v


def _doc(p):
    num, d = _v(p.get("num_pp")), _v(p.get("doc_date"))
    return f"{num} от {str(d)[:10]}" if num and d else num or ""


def _reg(v):
    """Значение регламента ПЗЗ: (число | None, пояснение). «Ф» — по существующему положению, «-» — не установлено."""
    s = str(_v(v) or "").strip()
    if s in ("", "-", "—"):
        return None, "не установлена"
    if s.upper() == "Ф":
        return None, "по факту"
    try:
        return float(s.replace(",", ".")), None
    except ValueError:
        return None, s


def pzz_sub_props(p):
    num = str(_v(p.get("podzone_num")) or "")
    out = {"Номер подзоны": num, "Номер зоны": num.rsplit("-", 1)[0] if num.count("-") >= 4 else ""}
    words = []
    for src, name, unit in (("plotnost", "Плотность, тыс. м²/га", "тыс. м²/га"), ("vysota", "Высота, м", "м"), ("proczastro", "Застроенность, %", "%")):
        v, note = _reg(p.get(src))
        out[name] = int(v) if v is not None and v.is_integer() else v
        words.append(f"{name.split(',')[0].lower()} " + (f"{str(out[name]).replace('.', ',')} {unit}" if v is not None else note))
    zero = all(out[k] == 0 for k in ("Плотность, тыс. м²/га", "Высота, м", "Застроенность, %"))
    out["Регламент"] = "нулевые параметры: новое строительство не предусмотрено" if zero else " · ".join(words)
    out["Документ"] = _doc(p)
    return out


def pzz_zone_props(p):
    info = str(_v(p.get("info")) or "")
    names = [ln.strip() for ln in info.splitlines() if re.match(r"^\d+(\.\d+)+\s", ln.strip())]
    return {"Номер зоны": _v(p.get("zone_num")), "ВРИ (коды)": _v(p.get("vri_540")) or _v(p.get("vri")),
            "ВРИ": "; ".join(names)[:600] or None, "Индекс": _v(str(p.get("zone_index_literal_f") or "").strip()),
            "Учётный номер": _v(p.get("cad_num")), "Документ": _doc(p), "Регламент (PDF)": _v(p.get("red_url")),
            "Примечание": _v(p.get("other"))}


def okn_props(p):
    return {"Наименование": _v(p.get("name")), "Вид зоны": _v(p.get("type_zone")) or _v(p.get("vid_zouit")),
            "Ограничения": _v(p.get("ogran")), "Документ": _v(p.get("doc")), "Район": _v(p.get("raion_pos")), "Округ": _v(p.get("okrug"))}


def demolition_props(p):
    return {"Номер уведомления": _v(p.get("nomer")), "Дата": _v(p.get("data_")), "Адрес": _v(p.get("adres")),
            "Территория": _v(p.get("terri")), "Объект": _v(str(p.get("name_obj") or "").strip())}


AMENITY = {"school": "школа", "kindergarten": "детский сад", "clinic": "поликлиника", "doctors": "поликлиника",
           "hospital": "больница", "pharmacy": "аптека"}


def social_props(p):
    return {"Вид": AMENITY.get(p.get("amenity"), p.get("amenity")), "Название": p.get("name")}


# ---------- ЕГКО: пустые строковые поля портал отдаёт одним пробелом " " — _v считает их пустыми ----------
def egko_address(p):
    """Адрес здания в формате поля full_addr слоя «Адреса» — «Научный проезд 20 стр.4», «улица Борисовские Пруды 11 к.1»
    (сверено по 217 029 адресам 23.09.2026): улица, номер дома без слова «дом», корпус «к.», строение с приставкой из поля
    is_struct («стр.» или «соор.»), владение «вл.» (в слое адресов не встретилось ни разу)."""
    s = lambda k: str(_v(p.get(k)) or "").strip()
    parts = [s("name_str1"), s("house")]
    if s("trunk"):
        parts.append("к." + s("trunk"))
    if s("building"):
        parts.append((s("is_struct") or "стр.") + s("building"))
    if s("estate"):
        parts.append("вл." + s("estate"))
    return " ".join(x for x in parts if x) or None


EGKO_H = "Высота, м"     # поле h: проверено сверкой с этажностью ЕГРН (см. CLAUDE.md, v0.31.0)


def egko_building_props(p):
    area = _v(p.get("shape_area"))
    return {"Назначение": _v(p.get("type_zd")), "Вид": _v(p.get("vid_zd")), "Наименование": _v(p.get("name_bui")),
            "Адрес": egko_address(p), "Вторая улица": _v(p.get("name_str2")), EGKO_H: _v(p.get("h")),
            "Отметка в ЕГКО": _v(p.get("state")),     # своя отметка портала; бывает и у «действующих» (1,2 % на выборке)
            "Площадь застройки, м²": round(float(area), 1) if area is not None else None}


def egko_road_props(p):
    return {"Наименование": _v(p.get("ext_name")), "Улица или район": _v(p.get("name_str")), "Вид": _v(p.get("vid_road")) or _v(p.get("vid_str"))}


def egko_path_props(p):
    return {"Вид": _v(p.get("vid_road")), "Улица": _v(p.get("name_str")) or _v(p.get("ext_name"))}


FLORA = {"gazon": "газон"}


def egko_green_props(p):
    t = _v(p.get("type_flora"))
    return {"Тип": FLORA.get(t, t) if t else _v(p.get("vid_frst")), "Название": _v(p.get("name_frs"))}


def egko_water_props(p):
    return {"Вид": _v(p.get("vid_wat")), "Название": _v(p.get("name_wat"))}


def egko_address_props(p):
    return {"Адрес": _v(p.get("full_addr")), "Угол подписи, °": _v(p.get("angl"))}


# ---------- Яндекс: все атрибуты слоя как есть, ключевые — по-русски; площадь и длина на местности даёт коннектор ----------
def _renamed(names):
    return lambda p: {names.get(k, k): v for k, v in p.items()}


# ключ источника → свойства портала в читаемые поля (служебные поля портала не нужны в таблице)
PRESENT = {"gisogd.pzz_sub": pzz_sub_props, "gisogd.pzz_zones": pzz_zone_props, "gisogd.okn": okn_props,
           "gisogd.demolition": demolition_props, "relief.contours": lambda p: {"Высота, м": p.get("elev")},
           "osm.social": social_props,
           "egko.buildings": egko_building_props, "egko.roads": egko_road_props, "egko.paths": egko_path_props,
           "egko.green": egko_green_props, "egko.water": egko_water_props, "egko.fences": lambda p: {},
           "egko.addresses": egko_address_props, "egko.water_labels": lambda p: {"Подпись": _v(p.get("text"))}, "egko.place_labels": lambda p: {"Подпись": _v(p.get("value_n"))},
           "yandex.hd_roads": _renamed({"type": "Тип", "struct": "Конструкция", "z_level": "Уровень"}),
           "yandex.buildings": _renamed({"height": "Высота, м", "ft_type_name": "Назначение"})}
for _k in SOURCES:
    if _k.startswith(("yandex.", "sit.")) and _k not in PRESENT:
        PRESENT[_k] = dict              # без переименования; поле LineCode у Яндекса не бывает


REDLN = json.loads((STYLES / "redln97.json").read_text("utf-8"))
REDLN_IDX = acad_lin.lgr_index(REDLN["linetypes"])
_LGR = json.loads((STYLES / "moscow_lgr.json").read_text("utf-8"))["styles"].values()
LGR_BY_CODE = {int(v["lgr_code"]): v for v in _LGR if v.get("lgr_code") is not None}
LGR_COLORS = {int(v["lgr_code"]): v["stroke"] for v in _LGR if v.get("lgr_code") is not None and v.get("stroke")}
LGR_DASH = {int(v["lgr_code"]): [d * 2 for d in v["dash_mm"]] for v in _LGR if v.get("lgr_code") is not None and v.get("dash_mm")}   # мм на 1:2000 → метры


def linetype_props(props):
    """LineCode of ГИС ОГД → linetypes REDLN97 (_lt) and codes without one (_miss: [[code, sign]])."""
    code = next((v for k, v in (props or {}).items() if k.lower() in ("linelineco", "linecode")), None)
    pairs = acad_lin.parse_line_codes(code)
    if not pairs:
        return {}
    return {"LineCode": code, "_lt": acad_lin.linetypes_for_codes(pairs, REDLN["linetypes"], REDLN_IDX),
            "_miss": [list(p) for p in acad_lin.missing_codes(pairs, REDLN["linetypes"], REDLN_IDX)]}


def _layer(key, result):
    present = PRESENT.get(key)
    feats = [{"type": "Feature", "geometry": f["geometry"],
              "properties": {**clean_props(present(f.get("properties") or {}) if present else f.get("properties"), f.get("_extra"), SOURCES[key][0] == "nspd"),
                             **({} if present else linetype_props(f.get("properties"))),
                             **({"_key": f["grado_key"]} if f.get("grado_key") else {}),
                             **({"_clip": f["grado_clip"]} if f.get("grado_clip") else {})}}
             for f in result["features"] if f.get("geometry")]
    return {"title": SOURCES[key][2], "source": result.get("source_doc"),
            **({"shp": True} if SOURCES[key][0] in ("gisogd", "egko", "gisogd_admin") else {}),   # с v0.32 ОГД и ЕГКО — из SHP, в родных координатах
            "fetched_at": result.get("fetched_at") or date.today().isoformat(), "notes": result.get("notes", []),
            "features": {"type": "FeatureCollection", "features": feats}}


# ---------- поиск участка по кадастровому номеру (НСПД) ----------
CAD_CACHE = {}                    # номер -> (время, объект WGS84 или None); участок за 30 минут не меняется
CAD_CACHE_SEC = 30 * 60
CAD_FAIL = {}                     # номер -> время сбоя портала: 45 с повторный поиск отвечает сразу, мёртвый НСПД не долбим
CAD_FAIL_SEC = 45
CAD_LOCK = threading.Lock()       # к порталу — по одному запросу за раз, как и везде
CAD_LOCK_TIMEOUT = 20             # сколько ждать очереди; не дождались — 503
CAD_PAUSE = 0.5                   # пауза между номерами одного поиска (как в коннекторе)
SEARCH_DEADLINE = 30              # общий срок одного запроса поиска, с: оставшиеся номера — в notes как не проверенные


def search_cad(q, deadline=None, lock_timeout=None):
    """Строка с номерами → (code, ответ). 400 — нет верных номеров, 502 — НСПД не ответил, 503 — очередь занята
    (тексты только ASCII). Кэш и недавние сбои отвечают без замка; номера сверх срока — в notes."""
    deadline = SEARCH_DEADLINE if deadline is None else deadline
    lock_timeout = CAD_LOCK_TIMEOUT if lock_timeout is None else lock_timeout
    t0 = time.monotonic()
    nums, bad = nspd_mod.normalize_cadastral(q)
    if not nums:
        return 400, {"error": "no valid cadastral numbers (format 50:27:0000000:126)"}
    over = nums[nspd_mod.SEARCH_MAX:]
    nums = nums[:nspd_mod.SEARCH_MAX]
    feats, missing, failed, unchecked, nogeom = [], [], [], [], []
    now = time.time()
    for k, v in list(CAD_CACHE.items()):
        if now - v[0] > CAD_CACHE_SEC:
            CAD_CACHE.pop(k, None)
    for k, v in list(CAD_FAIL.items()):
        if now - v > CAD_FAIL_SEC:
            CAD_FAIL.pop(k, None)
    todo = [n for n in nums if n not in CAD_CACHE and n not in CAD_FAIL]
    if todo:
        if not CAD_LOCK.acquire(timeout=max(0.0, min(lock_timeout, deadline - (time.monotonic() - t0)))):
            return 503, {"error": "search busy, try again"}
        try:
            first = True
            for n in todo:
                if n in CAD_CACHE:                       # пока ждали замок, соседний поиск уже спросил
                    continue
                if time.monotonic() - t0 > deadline:
                    unchecked.append(n)
                    continue
                if not first:
                    time.sleep(CAD_PAUSE)
                first = False
                errs, ng = [], []
                found = nspd_mod.search_cadastral([n], errors=errs, nogeom=ng)
                if errs:
                    CAD_FAIL[n] = time.time()
                    continue
                CAD_CACHE[n] = (time.time(), next((f for f in found if f["grado_key"] == n), None))
                nogeom += ng
        finally:
            CAD_LOCK.release()
    for n in nums:
        hit = CAD_CACHE.get(n)
        if n in unchecked:
            continue
        if hit is None:
            if n in CAD_FAIL:
                failed.append(n)
        elif hit[1] is None:
            missing.append(n)
        else:
            feats.append(hit[1])
    if (failed or unchecked) and not feats and not missing:
        return 502, {"error": "NSPD did not answer, try again later"}
    layer = _layer("nspd.parcels", {"features": feats, "source_doc": "НСПД (nspd.gov.ru), поиск по кадастровому номеру"})
    notes = ([f"Не удалось запросить у НСПД: {', '.join(failed)}"] if failed else []) \
        + ([f"Не проверены, истекло время поиска — повторите: {', '.join(unchecked)}"] if unchecked else []) \
        + ([f"У участка нет контура на портале: {', '.join(nogeom)}"] if nogeom else []) \
        + ([f"Не похоже на кадастровый номер: {', '.join(bad)}"] if bad else []) \
        + ([f"Взяты первые {nspd_mod.SEARCH_MAX} номеров, остальные отброшены: {len(over)}"] if over else [])
    missing += [n for n in nogeom if n not in missing]
    return 200, {"features": layer["features"]["features"], "missing": missing, "notes": notes}


def search_addr(q):
    """Строка адреса → (code, ответ). 400 — пусто или длиннее 200, 502 — Nominatim не ответил (тексты только ASCII)."""
    try:
        res = geocode_mod.geocode(q)
    except ValueError as e:
        return 400, {"error": str(e)}
    except geocode_mod.Busy:
        return 503, {"error": "search busy, try again"}
    except ConnectorError:
        return 502, {"error": "Nominatim did not answer, try again later"}
    notes = [] if res else ["Ничего не найдено в Москве и области"]
    return 200, {"results": res, "notes": notes}


KRT_RE = re.compile(r"\s*(?:(крт|krt)\s*)?(?:№|n|no\.?)?\s*(\d{1,5})\s*", re.I)
KRT_CACHE = [0.0, None]           # [время загрузки, {номер КРТ: объект}]: слой портала грузится целиком один раз, дальше из кэша
KRT_CACHE_SEC = 30 * 60
KRT_LOCK = threading.Lock()


def krt_number(q):
    """«КРТ 3229», «крт №3229», «3229» → (число, есть ли слово КРТ); иначе None. Кадастровый номер (с «:») сюда не попадает."""
    m = KRT_RE.fullmatch(q[:40]) if ":" not in q else None
    return (int(m.group(2)), bool(m.group(1))) if m else None


def krt_layer():
    """Все объекты слоя «Комплексное развитие территорий (ОГД)» по номеру КРТ (num_krt). Слой берётся у коннектора
    (диск-кэш портала), копия живёт в памяти KRT_CACHE_SEC; сбой портала — ConnectorError."""
    with KRT_LOCK:
        if KRT_CACHE[1] is not None and time.time() - KRT_CACHE[0] < KRT_CACHE_SEC:
            return KRT_CACHE[1]
        feats = {}
        for code in SOURCES["gisogd.krt"][1]:
            for f in GisogdApi(cache_dir=CACHE / "gisogd").fetch((-180, -90, 180, 90), code)["features"]:
                try:
                    n = int(float((f.get("properties") or {}).get("num_krt")))
                except (TypeError, ValueError):
                    continue
                if f.get("geometry"):
                    feats.setdefault(n, f)
        KRT_CACHE[:] = [time.time(), feats]
        return feats


def krt_card(p):
    """Строка результата: «КРТ № 3229 · ВАО, Гольяново · 2187-ПП от 12.08.2026 · 1,66 га»."""
    try:
        ha = float(p.get("p_krt") if p.get("p_krt") not in (None, "") else float(p.get("shape_area")) / 1e4)
    except (TypeError, ValueError):
        ha = None
    where = ", ".join(str(p[k]).strip() for k in ("okrug", "rayon") if str(p.get(k) or "").strip())
    parts = [f"КРТ № {int(float(p['num_krt']))}", where, str(p.get("pzz") or "").strip(), f"{ha:.2f} га".replace(".", ",") if ha is not None else ""]
    return " · ".join(x for x in parts if x)


def search_krt(n):
    """Номер КРТ → (code, ответ). 200 — features (0 или 1 объект), cards, missing; 502 — слой портала не получен (ASCII)."""
    try:
        f = krt_layer().get(n)
    except ConnectorError:
        return 502, {"error": "KRT layer not available, try again later"}
    if f is None:
        return 200, {"features": [], "cards": [], "missing": [f"КРТ {n}"], "notes": []}
    return 200, {"features": [{"type": "Feature", "geometry": f["geometry"], "properties": dict(f.get("properties") or {}), "grado_key": f.get("grado_key")}],
                 "cards": [krt_card(f.get("properties") or {})], "missing": [], "notes": []}


def search_any(q):
    """Одна строка: номер КРТ → объект слоя КРТ; кадастровые номера → поиск участка, иначе адрес. В ответ добавляется type.
    Голое число, которого нет среди КРТ, уходит в поиск адреса."""
    k = krt_number(q)
    if k:
        code, obj = search_krt(k[0])
        if k[1] or (code == 200 and obj["features"]):
            return code, ({**obj, "type": "krt"} if code == 200 else obj)
    nums, _bad = nspd_mod.normalize_cadastral(q[:2000])
    if nums:
        try:
            code, obj = search_cad(q[:2000])
        except ConnectorError:
            code, obj = 502, {"error": "NSPD did not answer, try again later"}
        kind = "cadastral"
    else:
        code, obj = search_addr(q)
        kind = "address"
    return code, ({**obj, "type": kind} if code == 200 else obj)


# ---------- Пределы тела запроса, ход выгрузки, понятные ошибки порталов ----------
# Тело запроса читается в память целиком, поэтому предел свой у каждого пути: проект со 100 000 объектов ~100 МБ,
# импорт — несколько файлов в base64, печать и экспорт несут слои проекта и фото листов; остальное — короткий JSON.
MAX_PROJECT_BODY = 400 * 2**20
MAX_BIG_BODY = 250 * 2**20
MAX_BODY = 32 * 2**20
HUB_PROJECT_RE = re.compile(r"/api/hub/project/([^/]+)(?:/(.+))?")
MAX_HUB_BODY = 2**20            # остальные POST совместного режима: вход, комментарии, доступ — короткий JSON
HUB_PUSH_RE = re.compile(r"/api/hub/project/[^/]+/push")
HUB_TEAM_RE = re.compile(r"/api/hub/team/([^/]+)(?:/(members|delete))?")
HUB_TID_RE = re.compile(r"[0-9a-f]{16}")     # id команды в адресе: только 16 hex, остальное до хаба и диска не доходит


def body_limit(path):
    """Предел тела POST по пути запроса (байты)."""
    p = path.split("?")[0]
    if p == "/api/project":
        return MAX_PROJECT_BODY
    if p == "/api/hub/projects" or HUB_PUSH_RE.fullmatch(p):      # создание с готовым файлом и запись проекта — как проект
        return MAX_PROJECT_BODY
    if p.startswith("/api/hub/"):
        return MAX_HUB_BODY
    if p.startswith(("/api/import/", "/api/print/", "/api/export/")):
        return MAX_BIG_BODY
    return MAX_BODY


INTERNAL_ERROR = "внутренняя ошибка, подробности в журнале сервера"
PRINT_PROGRESS = {}  # ход выгрузки альбома: {"kind": "pdf"|"pptx", "got": готово листов, "total": всего} (GET /api/print/progress)
PROGRESS = {}        # ключ источника → ход первой выгрузки слоя ГИС ОГД / ЕГКО целиком (GET /api/progress)
_OGD_CAT = {}


def source_ogd_code(key):
    """Код слоя каталога ГИС ОГД, который целиком отдаёт источник: `ogd.<код>` и подборка ГРАДО с одним кодом без
    подписи вида зоны (`gisogd.gpzu` = `ogd.gpzu`). Подборки из нескольких кодов и слои с подписями — None.
    Фронт по нему находит уже загруженный слой проекта под другим ключом и обновляет его, а не заводит второй."""
    if key.startswith("ogd."):
        return key[4:] or None
    src = SOURCES.get(key)
    if src and src[0] == "gisogd" and isinstance(src[1], dict) and len(src[1]) == 1:
        code, zone = next(iter(src[1].items()))
        return None if zone else code
    return None


AREA_TOO_BIG = "область слишком большая — уменьшите рамку"
# PORTAL_DOWN — текст для владельца (примечание и строка в окне), не серверная строка ошибки
PORTAL_DOWN = "портал OpenStreetMap не ответил: подождите минуту и повторите, область, уже скачанная раньше, берётся с диска"
PORTAL_DOWN_CODE = "портал OpenStreetMap ответил {code}: подождите минуту и повторите, область, уже скачанная раньше, берётся с диска"


def plain_portal_error(text):
    """Текст сбоя портала для владельца: без сырых кодов (Errno, HTTP 504, timed out). Сырой текст остаётся в журнале."""
    t = str(text or "")
    if re.search(r"out of memory|too large|слишком больш|exceeded.*(memory|limit)", t, re.I):
        return AREA_TOO_BIG
    if re.search(r"overpass|openstreetmap", t, re.I):
        # все зеркала ответили одним и тем же кодом (504) — он попадает в текст: «портал ответил 504»
        codes = set(re.findall(r"HTTP (\d{3})", t))
        if len(codes) == 1 and not re.search(r"errno|timed out|connection|urlopen", t, re.I):
            return PORTAL_DOWN_CODE.format(code=codes.pop())
        return PORTAL_DOWN
    if re.search(r"errno \d+|http 5\d\d|timed out|connection (reset|refused)|urlopen error", t, re.I):
        return "портал не ответил: подождите минуту и повторите"
    return t


def not_ready_why(spec):
    """Причины пометки «не готов» для владельца: «лист 6: легенда из 23 позиций не помещается — уменьшите число слоёв или
    шрифт». Читается после сборки PDF/PPTX/просмотра (album_io пишет sheet["_notReady"] — технические фразы).
    Возвращает [(номер листа с 1, [фраза, …]), …]."""
    out = []
    for i, sh in enumerate(spec.get("sheets") or [], start=1):
        raw = sh.get("_notReady") if isinstance(sh, dict) else None
        if not raw:
            continue
        total = sum(len(g.get("items") or []) for g in (sh.get("cLegend") or []) if isinstance(g, dict))
        why = []
        for r in raw:
            m = re.search(r"пункты легенды \((\d+)\)", r)
            if m:
                why.append(f"легенда из {total or m.group(1)} позиций не помещается — уменьшите число слоёв или шрифт")
                continue
            m = re.search(r"не поместились строки таблицы \((\d+)\)", r)
            if m:
                why.append(f"в таблицу не поместились {m.group(1)} строк — возьмите формат А1 или сократите таблицу")
                continue
            if "не помещается по ширине" in r:
                why.append(r + " — уберите столбцы или возьмите формат А1")
                continue
            if re.search(r"не поместил|не выведен", r):
                why.append(r + " — уменьшите число слоёв или возьмите формат А1")
                continue
            why.append(r)
        out.append((i, why))
    return out


def not_ready_headers(spec):
    """Заголовки ответа: номера листов «не готов» и причины (ASCII: текст кодируется %XX, браузер читает decodeURIComponent)."""
    rows = not_ready_why(spec)
    if not rows:
        return []
    why = "лист " + "; лист ".join(f"{n}: " + ", ".join(w) for n, w in rows)
    return [("X-Grado-Not-Ready", ",".join(str(n) for n, _ in rows)),
            ("X-Grado-Not-Ready-Why", quote(why[:300]))]


def _log_portal(where, text):
    if sys.stderr and text:
        sys.stderr.write(f"[portal] {where}: {text}\n")



def ogd_catalog():
    """Каталог ГИС ОГД для окна выбора слоёв: час в памяти (дерево открывается при каждой выгрузке)."""
    import time as _t
    from grado_connectors.gisogd_api import catalog
    if not _OGD_CAT or _t.time() - _OGD_CAT["at"] > 3600:
        _OGD_CAT.update(at=_t.time(), cat=catalog())
    return _OGD_CAT["cat"]


# Роли слоёв в расчётах (ограничения, анализ, эскиз): фронт ищет слой по роли, а не по фиксированному ключу — в проектах
# владельца каталожные слои лежат как `ogd.<код>`. Ключ источника -> роль (web/roles.js держит ту же таблицу для работы
# без сети; тест сверяет их). Роли: pzz_sub, pzz_zones, func_zones, zouit, szz, okn, red_lines, buildings, roads, water,
# green, social, parcels.
SOURCE_ROLES = {
    "gisogd.pzz_sub": "pzz_sub", "gisogd.pzz_zones": "pzz_zones", "gisogd.func_zones": "func_zones",
    "gisogd.func_zones_tinao": "func_zones", "nspd.zouit": "zouit", "gisogd.zouit": "zouit", "gisogd.vodookhr": "zouit",
    "gisogd.szz": "szz", "gisogd.okn": "okn", "gisogd.red_lines": "red_lines",
    "nspd.buildings": "buildings", "egko.buildings": "buildings", "osm.buildings": "buildings",
    "osm.roads": "roads", "egko.roads": "roads", "osm.water": "water", "egko.water": "water", "egko.green": "green",
    "osm.social": "social", "nspd.parcels": "parcels",
}
# Коды каталога ОГД выводятся из SOURCES: каждый код источника получает роль источника. Исключение — «красные линии»:
# в gisogd.red_lines вместе с красными линиями лежат границы водоохранных зон (l16), прибрежных защитных полос (l17) и
# береговых полос (l41) — у них есть свои полигоны в роли zouit, отступ как от красной линии для них неверен. Остальные
# коды l1..l4, l25, l7, l57, l8, l18, l21, l29 по названию каталога не проверены (офлайн названий нет) — без роли;
# владелец ставит роль слою вручную. Без роли также: virtual84/virtual87 («Пятая/Третья подзона» — приаэродромные
# подзоны Внукова, в SOURCES["gisogd.airfield"] их нет, не проверено), virtual100, gpzu, pmtgk, подписи (virtual18, virtual23).
CODE_ROLES_SKIP = {"gisogd.red_lines"}
# коды вне SOURCES; название в каталоге сверено по слою проекта «Безобразово» (заголовок слоя = название каталога)
EXTRA_CODE_ROLES = {"zu_29_06_2021": "parcels"}   # «Земельные участки (ОГД)»


def layer_roles():
    codes, titles = {}, {}
    for key, role in SOURCE_ROLES.items():
        src = SOURCES.get(key)
        if key in CODE_ROLES_SKIP or not src or src[0] != "gisogd" or not isinstance(src[1], dict):
            continue
        for code, name in src[1].items():
            codes.setdefault(code, role)
            if isinstance(name, str):
                titles.setdefault(code, name.split("|")[0])
    codes.update(EXTRA_CODE_ROLES)
    return {"sources": dict(SOURCE_ROLES), "codes": codes, "titles": titles}


OGD_JOB, OGD_LOCK = [], threading.Lock()   # «Всё из ГИС ОГД в DWG»: одна фоновая выгрузка за раз (ogd_all.py)
EGKO_TTL = 30 * 24 * 3600   # картооснова: газоны — 1,3 ГБ, еженедельно перекачивать незачем


_TILE_LOCK = threading.Lock()


# ---------- Подложки: тайлы Esri ----------
ESRI_SERVICES = {"sat": ("esri", "World_Imagery"), "light": ("esri-light", "Canvas/World_Light_Gray_Base")}


def egko_features(bbox, code):
    """Объекты слоя ЕГКО (картооснова base2) в прямоугольнике — для цветной основы схемы округа (print_io.egko_ops).
    Только из кэша на диске и с портала по обычным правилам коннектора; ошибка — слой пропускается.
    Без обрезки по рамке (clip=False): 290 тыс. объектов округа резались 40 секунд, а печать и так режет основу контуром округа."""
    return GisogdApi(cache_dir=CACHE / "egko", map_name="base2", clip=False, ttl=EGKO_TTL).fetch(bbox, code)["features"]


def esri_tile(z, x, y, kind="sat"):
    """Тайл Esri (JPEG) для листа: спутник World Imagery или светлая серая подложка (kind="light", правая карта
    «округ и районы» шаблона ППТ КРТ). С диска (~/.grado2/cache/tiles/<вид>, 90 дней), иначе скачать по одному,
    с паузой 0,1 с — портал не долбим; неудача — пустое место, лист всё равно собирается."""
    folder, service = ESRI_SERVICES.get(kind, ESRI_SERVICES["sat"])
    import time
    from grado_connectors import netutil
    from grado_connectors.contract import ConnectorError
    path = CACHE / "tiles" / folder / f"{z}_{x}_{y}.jpg"
    if path.exists() and time.time() - path.stat().st_mtime < 90 * 86400:
        return path.read_bytes()
    url = f"https://server.arcgisonline.com/ArcGIS/rest/services/{service}/MapServer/tile/{z}/{y}/{x}"
    with _TILE_LOCK:
        try:                                            # повторы — общее правило порталов (netutil)
            data = netutil.request(url, headers={"User-Agent": "grado2/1.0 (planning sheets)"}, timeout=20).content
        except ConnectorError:
            return None
        if data[:2] != b"\xff\xd8":                     # не JPEG (заглушка или ошибка) — на лист не идёт и в кэш не пишется
            return None
        atomic_write(path, data)
        time.sleep(.1)
        return data


def yandex_sat_tile(z, x, y):
    """Тайл спутника Яндекса (сетка EPSG:3395) для снимка на листах альбома (владелец 05.10.2026: спутник — Яндекс,
    самый свежий). Тот же кэш на диске, что у выгрузки снимка для AutoCAD (90 дней), скачивание по одному с паузой;
    нет тайла — None, печать подложит Esri."""
    import sat_io
    src = sat_io.YandexSat(CACHE / "tiles" / "yandex-sat")
    p = src.path(z, x, y)
    if p.exists() and time.time() - p.stat().st_mtime < sat_io.TTL:
        return p.read_bytes()
    now = time.time()
    # Яндекс отказывает (капча, бан, нет сети): 5 неудач подряд — 10 минут к нему не ходим, тайл без ответа — час;
    # иначе печать листа ждала бы по 5 с на каждый из сотен тайлов (подложка тогда — Esri).
    # 404 («снимка там нет») — не сбой: запоминается как «нет снимка» и счётчик неудач не трогает
    with _YSAT_LOCK:
        for k in [k for k, t in _YSAT["bad"].items() if t <= now]:      # просроченные записи не копятся
            del _YSAT["bad"][k]
        if _YSAT["off_until"] > now or _YSAT["bad"].get((z, x, y), 0) > now:
            return p.read_bytes() if p.exists() else None
    fail = p.with_suffix(".fail")                     # метка неудачи T69 (sat_io): тайла нет, но это не новый сбой Яндекса
    if fail.exists() and now - fail.stat().st_mtime < getattr(sat_io, "FAIL_TTL", 3600):
        return p.read_bytes() if p.exists() else None
    with _TILE_LOCK:
        status = None
        try:
            src.ensure(z, x, y)
            status = src.last_status
        except OSError:
            pass
    got = p.exists() and time.time() - p.stat().st_mtime < 60
    with _YSAT_LOCK:
        if got:
            _YSAT["fails"] = 0
        elif status == "none":
            _YSAT["bad"][(z, x, y)] = now + 3600
        else:
            _YSAT["bad"][(z, x, y)] = now + 3600
            _YSAT["fails"] += 1
            if _YSAT["fails"] >= 5:
                _YSAT["off_until"], _YSAT["fails"] = now + 600, 0
    return p.read_bytes() if p.exists() else None


_YSAT = {"fails": 0, "off_until": 0.0, "bad": {}}
_YSAT_LOCK = threading.Lock()


esri_tile.egko = egko_features          # печать берёт цветную основу ЕГКО через тот же вход, что и тайлы
esri_tile.ysat = yandex_sat_tile        # снимок листов альбома — спутник Яндекса


def _point_in(g, x, y):
    """Точка внутри Polygon / MultiPolygon GeoJSON (shapely)."""
    if not g or g.get("type") not in ("Polygon", "MultiPolygon"):
        return False
    import shapely
    from shapely.geometry import shape
    return bool(shapely.contains_xy(shape(g), x, y))


def ogd_label_angles(code, feats, bbox, api=None):
    """Подписям слоя надписей ГИС ОГД — угол вдоль ближайшей границы из той же папки портала (поле _angle)."""
    import ogd_all
    api = api or GisogdApi(cache_dir=CACHE / "gisogd")
    w, s_, e, n = bbox
    wide = (w - 0.001, s_ - 0.001, e + 0.001, n + 0.001)          # граница чуть за краем области тоже годится
    sib = []
    try:
        for c in ogd_all.label_siblings(ogd_catalog(), code):
            sib += api.fetch(wide, c)["features"]
    except ConnectorError:
        return feats
    return ogd_all.set_label_angles(feats, sib)


# ---------- OSM (Overpass): выгрузка и кэш по областям ----------
class _OsmCacheMiss(Exception):
    pass


def _osm_no_live(query):
    raise _OsmCacheMiss


def osm_fetch(bbox, sets, cache_dir=None):
    """Выгрузка OSM: сначала всё из кэша; если наборы лежат в кэше порознь (листы просили их по отдельности), они
    собираются из него — Overpass по той же области повторно не спрашивается (T62: на копии «Безобразово» из 33 с сборки
    30 с ушло на такой повторный запрос); иначе один запрос по всем наборам."""
    cache_dir = cache_dir or CACHE / "osm"
    sets = list(sets)
    try:
        return OsmOverpass(transport=_osm_no_live, cache_dir=cache_dir).fetch(bbox, sets)
    except _OsmCacheMiss:
        pass
    if len(sets) > 1:
        try:
            cached = OsmOverpass(transport=_osm_no_live, cache_dir=cache_dir)
            parts = [cached.fetch(bbox, [x]) for x in sets]
            res = parts[0]
            for r in parts[1:]:
                res["features"] += r["features"]
                res["notes"] += [n for n in r.get("notes", []) if n not in res["notes"]]
            res["params"]["sets"] = sorted(sets)
            return res
        except _OsmCacheMiss:
            pass
    return OsmOverpass(cache_dir=cache_dir).fetch(bbox, sets)


def fetch(bbox, keys, territory=None, margin_m=DATA_MARGIN_M):
    """Реальные слои по прямоугольнику WGS84. Возвращает (layers, errors).
    territory — [w, s, e, n] территории: для OSM и ЕГКО рамка листа крупного масштаба (сотни км²) заменяется
    областью данных «территория + margin_m», если рамка больше предела одного запроса (T70).
    Кроме ключей SOURCES — любой слой каталога ГИС ОГД ключом «ogd.<код слоя>» (окно «Исходные данные»)."""
    for k in keys:
        if k.startswith("ogd.") and k not in SOURCES:
            try:
                it = next((x for x in ogd_catalog() if x.get("code") == k[4:] and x.get("type") in ("layer", "virtual")), None)
            except ConnectorError:
                it = None
            if it:
                SOURCES[k] = ("gisogd", {it["code"]: None}, f"{it['name']} (ОГД)")
            elif (twin := next((x for x in SOURCES if x != k and source_ogd_code(x) == k[4:]), None)):
                SOURCES[k] = ("gisogd", {k[4:]: None}, SOURCES[twin][2])      # каталог не ответил — тот же слой по названию подборки
    keys = [k for k in keys if k in SOURCES]
    area = bbox_km2(bbox)
    layers, errors = {}, {}
    if territory and area > LIMIT_KM2["osm"]:
        capped = [k for k in keys if SOURCES[k][0] in TILE_CAPPED]
        tb = territory_bbox(territory, margin_m)
        if capped and bbox_km2(tb) < area:
            keys = [k for k in keys if k not in capped]
            lay2, err2 = fetch(tb, capped)
            layers.update(lay2)
            errors.update(err2)
    for k in keys:
        kind = SOURCES[k][0]
        lim = LIMIT_KM2[kind]
        if kind in TILE_CAPPED:
            if area > TILE_KM2[kind] * MAX_TILES:
                errors[k] = f"территория слишком велика для {TILE_CAPPED[kind]} ({area:.0f} км²): загрузите слои частями"
        elif area > lim:
            errors[k] = f"область {area:.1f} км² больше допустимых {lim:g} км² для источника"
    keys = [k for k in keys if k not in errors]
    split = [k for k in keys if area > TILE_KM2.get(SOURCES[k][0], float("inf"))]
    keys = [k for k in keys if k not in split]

    def run_split(ks):
        """Область больше, чем источник отдаёт за раз: части по очереди, объекты склеиваются."""
        cells = split_bbox(bbox, TILE_KM2[SOURCES[ks[0]][0]])
        parts = {k: [] for k in ks}
        try:
            for i, cell in enumerate(cells):
                if i:
                    time.sleep(TILE_PAUSE_S)        # портал не долбим: пауза между частями
                for k in ks:
                    PROGRESS[k] = {"title": SOURCES[k][2], "got": i, "total": len(cells), "stage": "cells"}
                got, bad = fetch(cell, ks)
                for k in ks:
                    if k in bad:
                        errors.setdefault(k, f"часть {i + 1} из {len(cells)}: {bad[k]}")
                    elif k in got:
                        parts[k].append(got[k])
            for k in ks:
                if k not in errors and parts[k]:
                    layers[k] = merge_layers(parts[k])
        finally:
            for k in ks:
                PROGRESS.pop(k, None)

    def run_osm():
        osm_keys = [k for k in keys if SOURCES[k][0] == "osm"]
        if not osm_keys:
            return
        res = osm_fetch(bbox, [SOURCES[k][1] for k in osm_keys])
        for k in osm_keys:
            part = [f for f in res["features"] if f["properties"].get("grado_set") == SOURCES[k][1]]
            layers[k] = _layer(k, {**res, "features": part})

    def run_nspd():                 # по очереди: у геопортала лимит частоты
        for k in (k for k in keys if SOURCES[k][0] == "nspd"):
            try:
                layers[k] = _layer(k, NspdDirect().fetch(bbox, SOURCES[k][1]))
            except ConnectorError as e:
                errors[k] = str(e)

    def run_gisogd(k, nth=0, of=0):
        feats, notes, doc = [], [], None
        def tell(code, got, total, stage):
            PROGRESS[k] = {"title": SOURCES[k][2], "got": got, "total": total, "stage": stage, "nth": nth, "of": of}
        tell(None, 0, None, "wait")          # имя слоя в строке состояния — сразу, не после первого мегабайта
        api = GisogdApi(cache_dir=CACHE / "gisogd", progress=tell)
        missed = []
        for code, zone in SOURCES[k][1].items():
            try:
                res = api.fetch(bbox, code)
            except ConnectorError as e:
                if k not in ZONES_TOLERANT:
                    raise
                missed.append(f"{zone or code}: {e}")
                continue
            doc, notes = res["source_doc"], notes + res["notes"]
            for f in res["features"]:
                if zone:
                    f["_extra"] = {"Вид зоны": zone}
                feats.append(f)
        PROGRESS.pop(k, None)
        if missed and len(missed) == len(SOURCES[k][1]):
            raise ConnectorError("; ".join(missed))
        notes += [f"портал не отдал — {m}" for m in missed]
        if k.startswith("ogd.") and any(str((f.get("properties") or {}).get("text") or "").strip() for f in feats[:20]):
            feats = ogd_label_angles(k[4:], feats, bbox, api)     # надписи — вдоль границ своей папки
        layers[k] = _layer(k, {"features": feats, "source_doc": doc, "notes": notes})

    def run_ogd(ks):
        """Слои портала, выбранные в окне «Исходные данные», — по очереди: портал не долбим параллельно."""
        for i, k in enumerate(ks, 1):
            try:
                run_gisogd(k, i, len(ks))
            except ConnectorError as e:
                PROGRESS.pop(k, None)
                errors[k] = str(e)

    def run_egko(ks):
        """ЕГКО — по очереди, один слой за другим: первая выгрузка газонов — 1,3 ГБ, портал не долбим параллельно."""
        for i, k in enumerate(ks, 1):
            feats, notes, doc = [], [], None
            def tell(code, got, total, stage, k=k, i=i):
                PROGRESS[k] = {"title": SOURCES[k][2], "got": got, "total": total, "stage": stage, "nth": i, "of": len(ks)}
            tell(None, 0, None, "wait")
            api = GisogdApi(cache_dir=CACHE / "egko", progress=tell, map_name="base2", clip=True, ttl=EGKO_TTL)
            try:
                for code, val in SOURCES[k][1].items():
                    res = api.fetch(bbox, code)
                    doc, notes = res["source_doc"], notes + res["notes"]
                    for f in res["features"]:
                        if val:
                            f["_extra"] = {EGKO_EXTRA.get(k, "Вид"): val}
                        feats.append(f)
                layers[k] = _layer(k, {"features": feats, "source_doc": doc, "notes": notes})
            except ConnectorError as e:
                errors[k] = str(e)
            finally:
                PROGRESS.pop(k, None)

    def run_yandex(ks, zoom=None, workers=3):
        """Все слои Яндекса одним проходом: тайлы качаются и разбираются один раз (3 потока, пауза, кэш на диске);
        для ситуационного плана — z16 в один поток."""
        def tell(got, total):
            for k in ks:
                PROGRESS[k] = {"title": SOURCES[k][2], "got": got, "total": total, "stage": "tiles"}
        try:
            res = YandexVmap(cache_dir=CACHE / "yandex", progress=tell, workers=workers, **({"zoom": zoom} if zoom else {})).fetch(
                bbox, sorted({n for k in ks for n in SOURCES[k][1]}))
            for k in ks:
                keep = SIT_FILTER.get(k, lambda p: True)
                part = [f for f in res["features"] if f["properties"].get("grado_layer") in SOURCES[k][1] and keep(f["properties"])]
                # вид слоя на карте берётся по первому объекту: площадные — первыми, затем линии, точки — последними
                part.sort(key=lambda f: ("Polygon" not in f["geometry"]["type"]) + (f["geometry"]["type"] == "Point"))
                layers[k] = _layer(k, {**res, "features": part})
        finally:
            for k in ks:
                PROGRESS.pop(k, None)

    def run_admin(k):
        """Все округа и районы Москвы для листа «Месторасположение» (схема Москвы и схема своего округа).
        Источник — эталон владельца (27.09.2026, docs/standards/admin/moscow-adm.geojson): 12 округов и 132 района
        после реформы ТиНАО, каждый район целиком в одном округе, округ — ровно сумма его районов, районы покрывают
        Москву без щелей и наложений. В ГИС ОГД округа ТиНАО собраны из старых поселений, а новые районы нарисованы
        схематично — собирать из них границы не получилось (v0.65.4–0.65.6)."""
        doc = json.loads(ADMIN_FILE.read_text(encoding="utf-8"))
        cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        home, feats = None, []
        for f in doc["features"]:
            props = dict(f["properties"])
            if props["Уровень"] == "округ":
                props["Граница"] = ADMIN_REV
                if home is None and _point_in(f["geometry"], cx, cy):
                    home = props["Округ"]
            feats.append({"geometry": f["geometry"], "properties": {}, "_extra": props})
        layers[k] = _layer(k, {"features": feats, "source_doc": "Административные округа и районы Москвы (эталон 27.09.2026)",
                               "notes": [] if home else ["область вне административных округов Москвы"]})

    def run_terrain(k):
        layers[k] = _layer(k, TerrainContours().fetch(bbox))

    by = lambda kind: [k for k in keys if SOURCES[k][0] == kind]
    jobs = [(by("osm"), run_osm), (by("nspd"), run_nspd)] + \
        [([k], lambda k=k: run_gisogd(k)) for k in by("gisogd") if not k.startswith("ogd.")] + \
        ([(ogd, lambda: run_ogd(ogd))] if (ogd := [k for k in by("gisogd") if k.startswith("ogd.")]) else []) + [([k], lambda k=k: run_terrain(k)) for k in by("terrain")] + \
        [([k], lambda k=k: run_admin(k)) for k in by("gisogd_admin")] + \
        ([(by("egko"), lambda: run_egko(by("egko")))] if by("egko") else []) + \
        ([(by("yandex"), lambda: run_yandex(by("yandex")))] if by("yandex") else []) + \
        ([(by("yandex_sit"), lambda: run_yandex(by("yandex_sit"), SIT_ZOOM, 1))] if by("yandex_sit") else []) + \
        [(ks, lambda ks=ks: run_split(ks)) for ks in ([k for k in split if SOURCES[k][0] == kind] for kind in TILE_KM2) if ks]
    if not jobs:
        return layers, errors
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        for job_keys, fut in [(ks, pool.submit(fn)) for ks, fn in jobs]:
            try:
                fut.result()
            except Exception as e:   # сеть/разбор: слой помечается ошибкой, остальные доезжают
                for k in job_keys:
                    PROGRESS.pop(k, None)
                    if k not in layers:
                        errors.setdefault(k, str(e) or type(e).__name__)
    for k, v in list(errors.items()):
        plain = plain_portal_error(v)
        if plain != v:
            _log_portal(k, v)
            errors[k] = plain
    return layers, errors


# ---------- ФГИС ТП: документы территориального планирования (Минэкономразвития) ----------
FGISTP_TTL = 7 * 24 * 3600
_FG_MEMO = {}
_FG_LOCK = threading.RLock()


def fgistp_catalog(conn=None):
    """Каталог документов РФ (~28 000, ~10 МБ) — с диска, раз в неделю обновляется."""
    import gzip
    import time
    path = CACHE / "fgistp" / "catalog.json.gz"
    with _FG_LOCK:                                  # один скачивает каталог, остальные ждут его, а не качают параллельно
        if path.exists() and time.time() - path.stat().st_mtime < FGISTP_TTL:
            mt = path.stat().st_mtime               # поиск по названию зовёт каталог на каждое слово — держим в памяти
            if _FG_MEMO.get("mt") != mt:
                try:
                    _FG_MEMO.update(mt=mt, cat=json.loads(gzip.decompress(path.read_bytes())))
                except (OSError, EOFError, ValueError, zlib.error):
                    path.unlink(missing_ok=True)    # недописанный файл — скачать заново, а не падать неделю
                    return fgistp_catalog(conn)
            return _FG_MEMO["cat"]
        try:
            cat = (conn or FgistpConnector()).catalog()
            if not cat:
                raise ConnectorError("ФГИС ТП вернула пустой каталог")
        except ConnectorError:
            if not path.exists():                   # портал недоступен — старый каталог лучше, чем никакого
                raise
            return json.loads(gzip.decompress(path.read_bytes()))
        atomic_write(path, gzip.compress(json.dumps(cat, ensure_ascii=False).encode("utf-8")))
        return cat


def fgistp_docs(bbox, catalog):
    """Документы, чей охват пересекает область; самые местные — первыми. Охват «вся Россия» у схем РФ отсекается."""
    w, s_, e, n = bbox
    x0, y0 = crs.wgs84_to_merc(w, s_)
    x1, y1 = crs.wgs84_to_merc(e, n)
    out = []
    for d in catalog:
        try:
            a, b, c, d2 = (float(v) for v in str(d.get("stp_extent") or "").split("_"))
        except ValueError:
            continue
        if c < x0 or a > x1 or d2 < y0 or b > y1 or (c - a) > 3_000_000:
            continue
        out.append({"uin": d["uin"], "name": (d.get("stp_name") or d["uin"]).strip(), "km": round((c - a) / 1000)})
    return sorted(out, key=lambda x: x["km"])[:300]


def fgistp_search(text, catalog, limit=100):
    """Документы по названию во всём каталоге РФ: все слова запроса (регистр и «ё» не важны), самые местные — первыми."""
    norm = lambda t: str(t or "").lower().replace("ё", "е")
    words = norm(text).split()
    out = []
    for d in catalog:
        name = (d.get("stp_name") or d["uin"]).strip()
        if all(w in norm(name) for w in words):
            try:
                a, _, c, _ = (float(v) for v in str(d.get("stp_extent") or "").split("_"))
                km = round((c - a) / 1000)
            except ValueError:
                km = None
            out.append({"uin": d["uin"], "name": name, "km": km})
    return sorted(out, key=lambda x: (x["km"] is None, x["km"] or 0))[:limit]


def fgistp_fetch(uin, classids, bbox, conn=None):
    """Слои документа по одному на класс объектов, обрезанные по области (портал отдаёт документ целиком)."""
    conn = conn or FgistpConnector()
    layers_meta = conn.discover(uin)
    out = {}
    for lay in [l for l in layers_meta if l["classid"] in classids]:
        res = conn.fetch(uin, classids={lay["classid"]}, layers=[lay])
        feats = []
        for f in res["features"]:
            fb = _bbox_of(f["geometry"])
            if fb and not (fb[2] < bbox[0] or fb[0] > bbox[2] or fb[3] < bbox[1] or fb[1] > bbox[3]):
                p = f["properties"]
                props = {"Наименование": _v(p.get("naim")), "Статус": _v(p.get("status_name")), "Номер": _v(p.get("number")),
                         **{k: v for k, v in p.items() if k not in ("naim", "status_name", "number", "uin", "class_name", "class_title", "globalid") and _v(v) is not None},
                         "_key": f["grado_key"]}
                feats.append({"type": "Feature", "geometry": f["geometry"], "properties": props})
        title = (lay.get("class_title") or lay.get("class_name") or lay["classid"]).strip()
        out[f"fgistp:{uin}:{lay['classid']}"] = {"title": f"ФГИС ТП: {title}", "source": res.get("source_doc"),
                                                 "fetched_at": date.today().isoformat(), "notes": res.get("notes", []),
                                                 "features": {"type": "FeatureCollection", "features": feats}}
    return out


def _bbox_of(geom):
    xs, ys = [], []

    def walk(c):
        if c and isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for x in c:
                walk(x)
    walk((geom or {}).get("coordinates") or [])
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def tep(terr_ha, restrict_ha, spp_new_m2, share, spp_kept_m2=0.0, spp_low_m2=0.0, nonres_part=6, education_zone=1,
        k1=1.0, k2=0.9, tinao=0, territory_mode=1, unbuilt_share=25, constants=None, free_doo=0, free_school=0, free_clinic=0,
        park_share_underground=0, park_share_multi=0):
    """ТЭП по методике «Калькулятора 2.0» (Москва). Население, соцобъекты и машино-места — от новой застройки;
    СПП ИЖС и блокированных домов идёт в жилую с 50 м² квартир на жителя.
    constants — необязательная подмена норм {id: число}; в ответе тогда есть constants_changed (id, что отличаются от пресета).
    park_share_underground, park_share_multi — доли постоянных мест (целые %, сумма до 100) в подземных и многоэтажных гаражах, остальное наземное.
    free_doo, free_school, free_clinic — свободные места существующих объектов (вручную, 0..100000); из дефицита пресет считает
    резерв участков, в ответе social = [{kind, places, m2}] (ДОО — по участку, больший первым; школа и поликлиника — 0 или 1)."""
    free = {}
    for fid, fv in (('free_doo', free_doo), ('free_school', free_school), ('free_clinic', free_clinic)):
        if isinstance(fv, bool) or not isinstance(fv, (int, float)) or not 0 <= fv <= 100000 or fv != int(fv):      # NaN fails the range; places are whole
            raise ValueError(f"{fid} must be a whole number from 0 to 100000")
        free[fid] = int(fv)
    for pid, pv in (('park_share_underground', park_share_underground), ('park_share_multi', park_share_multi)):
        if isinstance(pv, bool) or not isinstance(pv, (int, float)) or not 0 <= pv <= 100 or pv != int(pv):      # NaN fails the range; shares are whole percents
            raise ValueError(f"{pid} must be a whole number from 0 to 100")
    if park_share_underground + park_share_multi > 100:
        raise ValueError("park_share_underground and park_share_multi together must not exceed 100")
    e = Engine.from_file(PRESET)
    changed = None
    if constants is not None:
        if not isinstance(constants, dict):
            raise ValueError("constants must be an object")
        meta = e.preset.get("constants_meta", {})
        for cid, v in constants.items():
            if cid not in e.constants:
                raise ValueError(f"unknown constant {cid!r}".encode("ascii", "backslashreplace").decode())
            lo, hi = meta[cid]["min"], meta[cid]["max"]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:     # NaN fails the range; range first: isfinite(10**400) overflows
                raise ValueError(f"constant {cid} must be a number from {lo} to {hi}")
        changed = [cid for cid in e.constants if cid in constants and constants[cid] != e.constants[cid]]
        e.set_constants(**{cid: constants[cid] for cid in changed})
    e.set_inputs(terr_area=terr_ha, restrict_area=restrict_ha, spp_in=spp_new_m2 / 1000, ratio_zh=max(0.0, min(100.0, share * 100)),
                 spp_low_in=spp_low_m2 / 1000, nonres_part=max(0.0, min(100.0, float(nonres_part))), education_zone=2 if int(education_zone) == 2 else 1,
                 k1=k1, k2=k2, tinao=1 if tinao else 0, territory_mode=int(territory_mode) if int(territory_mode) in (1, 2, 3) else 1,
                 unbuilt_share=max(0.0, min(90.0, float(unbuilt_share))),
                 park_share_underground=int(park_share_underground), park_share_multi=int(park_share_multi), **free)
    def whole(v):
        return int(v) if float(v).is_integer() else v
    social = []
    n, q, r = int(e.value('doo_res_n')), int(e.value('doo_res_q')), int(e.value('doo_res_r'))
    for places in [q + 1] * r + [q] * (n - r):
        social.append({'kind': 'doo', 'places': places, 'm2': whole(places * (e.value('doo_plot_m2_1') if places <= e.value('doo_plot_cap1') else e.value('doo_plot_m2_2')))})
    if e.value('school_deficit') > 0:
        social.append({'kind': 'school', 'places': whole(e.value('school_deficit')), 'm2': whole(e.value('school_res_m2'))})
    if e.value('clinic_deficit') > 0:
        social.append({'kind': 'clinic', 'places': whole(e.value('clinic_deficit')), 'm2': whole(e.value('clinic_res_m2'))})
    out = {"metrics": e.results(), "social": social,
           "density_total": ((spp_new_m2 + spp_kept_m2) / 1000 / terr_ha) if terr_ha else 0.0}
    if changed is not None:
        out["constants_changed"] = changed
    return out


# ---------- ТЭП-нормы, район по территории, пешеходный маршрут до станции ----------
def tep_norms():
    """Нормы пресета для полей ввода: текущие значения и описание (название, единица, группа, источник, редакция, пределы)."""
    p = json.loads(PRESET.read_text("utf-8"))
    return {"preset": p["id"], "norms": [{"id": cid, "value": v, **p["constants_meta"][cid]} for cid, v in p["constants"].items()]}


def _norm_name(t):
    t = str(t or "").lower().replace("ё", "е")
    for w in ("муниципальный округ", "поселение", "район", "городской округ", "город"):
        t = t.replace(w, "")
    # порядок слов не важен: у OSM «Северное Бутово», в таблицах 945-ПП «Бутово Северное»
    return " ".join(sorted(t.replace("-", " ").split()))


_PLACE_MEMO = {}
MAX_PLACE_MEMO = 256                 # последних ответов /api/place в памяти
_PLACE_LOCK = threading.Lock()


def _rail_nodes(raw):
    """Входы и станции рельсового каркаса (метро, МЦК, МЦД) из ответа Overpass."""
    return [e for e in raw.get("elements", []) if e.get("type") == "node"
            and (e["tags"].get("railway") == "subway_entrance" or e["tags"].get("station") in ("subway", "light_rail", "monorail")
                 or e["tags"].get("railway") in ("station", "halt") and e["tags"].get("train") == "yes" or "МЦ" in e["tags"].get("network", ""))]


# пешеходная сеть для K1: всё, где можно пройти пешком (без автомагистралей и съездов с них)
WALK_HW = ("footway|path|pedestrian|living_street|residential|service|unclassified|tertiary|tertiary_link|secondary|"
           "secondary_link|primary|primary_link|steps|cycleway|track|corridor|crossing")
_ROUTE_MEMO = {}


def rail_route(lon, lat, radius=2400):
    """K1 по улицам (945-ПП прил. 6): длина пешеходного маршрута от точки территории до ближайшего входа или станции
    метро, МЦК, МЦД по сети улиц и дорожек OSM (Дейкстра). Возвращает {route_m, straight_m, station} или None."""
    import gzip
    import heapq
    import math
    key = (round(lon, 3), round(lat, 3))
    if key in _ROUTE_MEMO:
        return _ROUTE_MEMO[key]
    place_info(lon, lat)
    raw = json.loads((CACHE / "place" / f"{key[0]}_{key[1]}.json").read_text("utf-8"))
    rail = _rail_nodes(raw)
    if not rail:
        _ROUTE_MEMO[key] = None
        return None
    cache = CACHE / "place" / f"walk_{key[0]}_{key[1]}_{radius}.json.gz"
    ways = None
    if _fresh(cache):
        try:
            ways = json.loads(gzip.decompress(cache.read_bytes()))
        except (OSError, EOFError, ValueError, zlib.error):
            cache.unlink(missing_ok=True)
    if ways is None:
        q = f'[out:json][timeout:90];way(around:{radius},{lat},{lon})["highway"~"^({WALK_HW})$"]["access"!~"^(private|no)$"];out geom;'
        res = OsmOverpass()._http_post(q)
        ways = [[[p["lon"], p["lat"]] for p in e.get("geometry", [])] for e in res.get("elements", []) if e.get("type") == "way"]
        atomic_write(cache, gzip.compress(json.dumps(ways).encode("utf-8")))
    kx, ky = 111320 * math.cos(math.radians(lat)), 110540
    xy = lambda p: ((p[0] - lon) * kx, (p[1] - lat) * ky)
    ids, pts, adj = {}, [], []

    def node(p):
        k = (round(p[0], 7), round(p[1], 7))
        i = ids.get(k)
        if i is None:
            i = ids[k] = len(pts)
            pts.append(xy(p))
            adj.append([])
        return i
    for w in ways:
        for a, b in zip(w, w[1:]):
            i, j = node(a), node(b)
            d = math.dist(pts[i], pts[j])
            adj[i].append((j, d))
            adj[j].append((i, d))
    if not pts:
        _ROUTE_MEMO[key] = None
        return None
    nearest = lambda q: min(range(len(pts)), key=lambda i: (pts[i][0] - q[0]) ** 2 + (pts[i][1] - q[1]) ** 2)
    start = nearest((0.0, 0.0))
    dist = [math.inf] * len(pts)
    dist[start] = math.dist(pts[start], (0.0, 0.0))
    heap = [(dist[start], start)]
    while heap:
        d, i = heapq.heappop(heap)
        if d > dist[i] or d > radius * 1.6:
            continue
        for j, w in adj[i]:
            if d + w < dist[j]:
                dist[j] = d + w
                heapq.heappush(heap, (d + w, j))
    best = None
    for e in rail:
        q = xy((e["lon"], e["lat"]))
        j = nearest(q)
        snap = math.dist(pts[j], q)
        if snap > 150 or dist[j] == math.inf:
            continue
        route = dist[j] + snap
        if best is None or route < best["route_m"]:
            best = {"route_m": round(route), "straight_m": round(math.dist(q, (0.0, 0.0))),
                    "station": e["tags"].get("name") or (f"вход {e['tags']['ref']}" if e["tags"].get("ref") else "вход")}
    _ROUTE_MEMO[key] = best
    return best


PLACE_TTL = 90 * 86400          # район, станции и улицы меняются редко, но не никогда


def _fresh(path):
    import time
    return path.exists() and time.time() - path.stat().st_mtime < PLACE_TTL


OKRUG_FULL = {"ЦАО": "Центральный", "САО": "Северный", "СВАО": "Северо-Восточный", "ВАО": "Восточный", "ЮВАО": "Юго-Восточный",
              "ЮАО": "Южный", "ЮЗАО": "Юго-Западный", "ЗАО": "Западный", "СЗАО": "Северо-Западный", "ЗелАО": "Зеленоградский",
              "НАО": "Новомосковский", "ТАО": "Троицкий"}
MAX_PLACE_VERTICES = 100000
_ADMIN_DIST = {}


def _admin_districts():
    """Районы из эталона (docs/standards/admin/moscow-adm.geojson): [(название, код округа, полигоны, bbox)]; читается один раз."""
    if ADMIN_FILE not in _ADMIN_DIST:
        doc = json.loads(ADMIN_FILE.read_text(encoding="utf-8"))
        out = []
        for f in doc["features"]:
            pr, g = f["properties"], f["geometry"]
            if pr.get("Уровень") != "район":
                continue
            polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
            xs = [pt[0] for poly in polys for pt in poly[0]]
            ys = [pt[1] for poly in polys for pt in poly[0]]
            out.append((pr["Наименование"], pr.get("Округ", ""), polys, (min(xs), min(ys), max(xs), max(ys))))
        _ADMIN_DIST[ADMIN_FILE] = out
    return _ADMIN_DIST[ADMIN_FILE]


def place_polygons(geom):
    """Контур территории из запроса: GeoJSON Polygon / MultiPolygon в lon/lat → список полигонов [[кольцо, ...], ...].
    Не-объект, чужой тип, bool, NaN, координаты вне диапазона, больше 100 000 вершин — ValueError (ответ 400)."""
    import export_io
    if not isinstance(geom, dict) or geom.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError("polygon must be a GeoJSON Polygon or MultiPolygon")
    c = geom.get("coordinates")
    polys = [c] if geom["type"] == "Polygon" else c
    n = 0
    if not isinstance(polys, list) or not polys:
        raise ValueError("polygon coordinates are empty")
    for poly in polys:
        if not isinstance(poly, list) or not poly:
            raise ValueError("polygon rings are empty")
        for ring in poly:
            if not isinstance(ring, list) or len(ring) < 4:
                raise ValueError("polygon ring needs at least 4 points")
            n += len(ring)
            if n > MAX_PLACE_VERTICES:
                raise ValueError("polygon has too many vertices")
            for pt in ring:
                if not isinstance(pt, list) or len(pt) < 2:
                    raise ValueError("polygon point must be [lon, lat]")
                export_io._num(pt[0], "lon", 180)
                export_io._num(pt[1], "lat", 90)
    return [[[(float(pt[0]), float(pt[1])) for pt in ring] for ring in poly] for poly in polys]


def district_shares(polys):
    """Доли площади территории по районам эталона: [{name, okrug, share}] по убыванию; доли в сумме 1 (часть вне Москвы не считается)."""
    from grado_geom.overlay import union_intersection_area
    k = math.cos(math.radians(sum(pt[1] for poly in polys for pt in poly[0]) / sum(len(poly[0]) for poly in polys)))
    sq = lambda ps: [[[(x * k, y) for x, y in ring] for ring in poly] for poly in ps]
    bb = (min(pt[0] for poly in polys for pt in poly[0]), min(pt[1] for poly in polys for pt in poly[0]),
          max(pt[0] for poly in polys for pt in poly[0]), max(pt[1] for poly in polys for pt in poly[0]))
    terr, found = sq(polys), []
    for name, okrug, dpolys, b in _admin_districts():
        if b[2] < bb[0] or b[0] > bb[2] or b[3] < bb[1] or b[1] > bb[3]:
            continue
        a = union_intersection_area(terr, sq(dpolys))
        if a > 0:
            found.append([name, okrug, a])
    total = sum(f[2] for f in found)
    return [{"name": n, "okrug": o, "share": round(a / total, 4)} for n, o, a in sorted(found, key=lambda f: -f[2])] if total else []


def place_info(lon, lat, polygon=None):
    """Территориальные параметры ТЭП по точке (как маркер «Калькулятора 2.0»): район и округ по OSM, образовательная
    зона (2151-ПП), K2 (945-ПП прил. 3 с границей ТТК), ТиНАО, K1 по расстоянию до ближайшего входа или станции
    метро, МЦК, МЦД. K1 — приближение: прямое расстояние × 1,3 вместо пешеходной изохроны.
    polygon — контур территории (GeoJSON в lon/lat): район, зона и K2 берутся у района с наибольшей долей площади
    (по эталону районов, без новых запросов к порталам); без контура или вне эталона — по точке (chosen_by «centre»)."""
    import math
    polys = place_polygons(polygon) if polygon is not None else None
    key = (round(lon, 3), round(lat, 3), hashlib.sha1(json.dumps(polygon, sort_keys=True).encode()).hexdigest() if polygon is not None else None)
    with _PLACE_LOCK:
        if key in _PLACE_MEMO:
            return _PLACE_MEMO[key]
    cache = CACHE / "place" / f"{key[0]}_{key[1]}.json"      # Overpass по точке, от контура не зависит
    raw, overpass_down = None, False
    if _fresh(cache):
        try:
            raw = json.loads(cache.read_text("utf-8"))
        except ValueError:
            cache.unlink(missing_ok=True)
    if raw is None:
        q = (f"[out:json][timeout:25];is_in({lat},{lon})->.a;area.a[\"boundary\"=\"administrative\"][\"admin_level\"~\"^(5|8)$\"];out tags;"
             f"(node(around:3000,{lat},{lon})[\"railway\"=\"subway_entrance\"];node(around:3000,{lat},{lon})[\"railway\"~\"^(station|halt)$\"];);out;")
        try:
            raw = OsmOverpass()._http_post(q)
        except ConnectorError as e:
            # район по площади границы берётся из эталона районов без сети: без OSM остаются только станции (K1)
            if not (polys and district_shares(polys)):
                raise
            _log_portal("place", str(e))
            raw, overpass_down = {"elements": []}, True
        else:
            atomic_write(cache, json.dumps(raw, ensure_ascii=False).encode("utf-8"))
    areas = [e.get("tags", {}) for e in raw.get("elements", []) if e.get("type") == "area"]
    okrug = next((a.get("name") for a in areas if a.get("admin_level") == "5"), "")
    dname = next((a.get("name") for a in areas if a.get("admin_level") == "8"), "")
    tinao = int(any(w in (okrug or "") for w in ("Троицк", "Новомосковск")))
    districts, chosen_by = [], "centre"
    if polys:
        districts = district_shares(polys)
        if districts:
            top = districts[0]
            chosen_by, dname = "area", top["name"]
            okrug = f'{OKRUG_FULL[top["okrug"]]} административный округ' if top["okrug"] in OKRUG_FULL else okrug
            tinao = int(top["okrug"] in ("ТАО", "НАО"))
    table = {_norm_name(k): k for k in DISTRICTS["k2"]}
    district = table.get(_norm_name(dname))
    inside_ttk = _point_in({"type": "Polygon", "coordinates": [DISTRICTS["ttk_hull"]]}, lon, lat)
    notes = []
    zone_note = ""
    if district:
        k2row = DISTRICTS["k2"][district]
        k2 = (k2row.get("inside_ttk") if inside_ttk else k2row.get("outside_ttk")) if "inside_ttk" in k2row else \
             (k2row["exclave"] if "exclave" in k2row and lon < 37.33 else k2row["value"])
        zone = 2 if _norm_name(district) in {_norm_name(z) for z in DISTRICTS["zone2"]} else 1
    else:
        k2, zone = (0.9, 2)
        zone_note = "район не в списках 2151-ПП: принята образовательная зона 2, её можно изменить в «Нормативах»"
        notes.append(f"район «{dname or 'не определён'}» не найден в таблицах 945-ПП и 2151-ПП — K2 и зона приняты {k2} и {zone}, поправьте вручную")
    # ближайший вход или станция рельсового каркаса
    rail = _rail_nodes(raw)
    kx = 111320 * math.cos(math.radians(lat))
    dist = min((math.hypot((e["lon"] - lon) * kx, (e["lat"] - lat) * 110540) for e in rail), default=None)
    walk = dist * 1.3 if dist is not None else None
    k1 = None if overpass_down else 0.75 if walk is not None and walk < 1200 else 0.9 if walk is not None and walk <= 2200 else 1.0   # K1 без OSM неизвестен, не «1,0»
    if overpass_down:
        notes.append("станции метро не найдены: " + PORTAL_DOWN + "; K1 проверьте вручную")
    out = {"district": district or dname, "known": bool(district), "okrug": okrug, "tinao": tinao, "inside_ttk": inside_ttk,
           "zone": zone, "zone_note": zone_note, "k2": k2, "k1": k1, "rail_walk_m": round(walk) if walk is not None else None, "notes": notes,
           "districts": [{"name": d["name"], "share": d["share"]} for d in districts], "chosen_by": chosen_by}
    if overpass_down:                # неполный ответ в память не кладём: следующий запрос попробует портал снова
        return out
    with _PLACE_LOCK:
        _PLACE_MEMO[key] = out
        while len(_PLACE_MEMO) > MAX_PLACE_MEMO:                 # самый старый ключ — первый (dict хранит порядок вставки)
            del _PLACE_MEMO[next(iter(_PLACE_MEMO))]
    return out


def project_path(name):
    """Имя проекта → файл в PROJECTS. Имя становится именем файла, поэтому без путей и служебных знаков."""
    name = (name or "").strip()
    if name == AUTOSAVE:
        return PROJECTS / f"{AUTOSAVE}.grado2"
    if not name or name.startswith(".") or len(name) > 120 or any(c in name for c in '/\\:*?"<>|\0'):
        raise ValueError("bad project name")
    return PROJECTS / f"{name}.grado2"


_SAVE_LOCK = threading.Lock()


# ---------- Проекты на диске: запись, версии, размер папки ----------
def atomic_write(path, body):
    """Запись файла целиком или никак: свой временный файл рядом + os.replace. Общий «.tmp» на всех писателей
    давал при двух одновременных сохранениях (две вкладки, автосейв) склейку чужих хвостов — битый JSON."""
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="." + path.stem[:40] + ".", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(body)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


VERSIONS_KEEP = 40                                    # прежних версий на проект (сжатых, ~3 МБ каждая)
VERSIONS_EVERY = {True: 3600, False: 600}             # не чаще: автосохранение — раз в час, «Сохранить» — раз в 10 мин


def keep_version(path, auto):
    """Прежний файл проекта перед перезаписью — в .versions/<проект>/ГГГГММДД-ЧЧММ.grado2.gz (последние 40).
    Защита от ошибки в работе: удалённый слой, испорченная правка, чужая вкладка. С сервера копия не уходит."""
    import gzip
    import time as _t
    if not path.exists():
        return
    d = PROJECTS / ".versions" / path.stem
    old = sorted(d.glob("*.grado2.gz")) if d.exists() else []
    if old and _t.time() - old[-1].stat().st_mtime < VERSIONS_EVERY[auto]:
        return
    stamp = _t.strftime("%Y%m%d-%H%M", _t.localtime(path.stat().st_mtime))
    atomic_write(d / f"{stamp}.grado2.gz", gzip.compress(path.read_bytes(), 6))
    for p in sorted(d.glob("*.grado2.gz"))[:-VERSIONS_KEEP]:
        p.unlink(missing_ok=True)


PROJECTS_CAP = 20 * 2**30                              # вся папка проектов вместе с версиями; больше — сохранение отказывает


class QuotaExceeded(Exception):
    pass


def projects_size():
    return sum(p.stat().st_size for p in PROJECTS.rglob("*") if p.is_file()) if PROJECTS.exists() else 0


# листы «Макета листа» нового интерфейса (/next/): ключ layouts — всегда последний в файле проекта (новый интерфейс
# пишет его последним), чтобы запись рабочей страницы, которая о нём не знает, листы не стирала (save_project)
LAYOUTS_KEY = b',"layouts":'


def split_layouts(body):
    """Текст проекта → (текст без листов макета, JSON листов или None). Листы ищутся только последним ключом."""
    t = body.rstrip()
    i = t.rfind(LAYOUTS_KEY)
    if i < 0 or not t.endswith(b"}"):
        return body, None
    tail = t[i + len(LAYOUTS_KEY):-1]
    try:
        if not isinstance(json.loads(tail), list):
            return body, None
    except ValueError:
        return body, None
    return t[:i] + b"}", tail


def with_layouts(body, tail):
    """Дописать листы макета последним ключом (tail — JSON списка; None — без листов)."""
    if tail is None:
        return body
    head = body.rstrip()[:-1].rstrip()
    return head + (LAYOUTS_KEY if not head.endswith(b"{") else LAYOUTS_KEY[1:]) + tail + b"}"


def _write_project(path, name, body):
    if projects_size() + len(body) > PROJECTS_CAP:
        raise QuotaExceeded
    try:
        keep_version(path, name == AUTOSAVE)
    except OSError:
        pass                                          # версия не записалась — сохранение важнее
    atomic_write(path, body)


def save_project(name, body):
    obj = json.loads(body)                            # в файл идёт только целый JSON
    path = project_path(name)
    with _SAVE_LOCK:                                  # два сохранения подряд — по очереди, последний побеждает целиком
        if isinstance(obj, dict) and "layouts" not in obj and path.exists():
            body = with_layouts(body, split_layouts(path.read_bytes())[1])   # листы макета, о которых страница не знает, остаются
        _write_project(path, name, body)
    return path


_ALBUM_INFO = {}                # путь -> (mtime, size, (листов, собран)): разбор файла один раз на запись


def album_info(path, st=None):
    """Сколько листов в альбоме проекта и когда он собран (ALBUM.meta.builtAt) — для второй строки списка «Проекты»."""
    st = st or path.stat()
    key = (st.st_mtime_ns, st.st_size)
    hit = _ALBUM_INFO.get(str(path))
    if hit and hit[0] == key:
        return hit[1]
    res = hubmod.album_summary(path)
    _ALBUM_INFO[str(path)] = (key, res)
    return res


def list_projects():
    files = sorted(PROJECTS.glob("*.grado2"), key=lambda p: p.stat().st_mtime, reverse=True) if PROJECTS.exists() else []
    def info(p):
        st = p.stat()
        n, at = album_info(p, st)
        return {"name": p.stem, "modified": st.st_mtime, "size": st.st_size, "album_n": n, "album_at": at}
    auto = [info(p) for p in files if p.stem == AUTOSAVE]
    return {"dir": str(PROJECTS), "projects": [info(p) for p in files if p.stem != AUTOSAVE], "autosave": auto[0] if auto else None}


# ---------- HTTP: заголовки безопасности, вход по ключу, совместный режим ----------
# Скрипты — только свои (без inline и eval); карта берёт плитки Esri и EOX по https (img-src), воркеры OpenLayers — из blob:.
# connect-src data: — значки Web Awesome нового интерфейса (/next/) читаются fetch из data:-адресов внутри самого скрипта.
# frame-ancestors 'self' — страницу встраивает в рамку только сам ГРАДО: движок альбома в новом интерфейсе (ui/src/albumhost.js);
# чужой сайт её в рамку не возьмёт (защита от подмены щелчков остаётся).
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; "
       "font-src 'self' data:; connect-src 'self' data:; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")

# Ключ доступа (необязательный второй слой за паролем обратного прокси): задан GRADO2_TOKEN — без куки grado_token или
# заголовка X-Grado-Token сервер отвечает только на вход. Не задан или пуст — всё как прежде (локальная работа).
TOKEN = os.environ.get("GRADO2_TOKEN") or ""
TOKEN_COOKIE, TOKEN_HEADER = "grado_token", "X-Grado-Token"
LOGIN_OPEN = {"/login.html", "/login.js"}               # страница входа и её скрипт (CSP: inline-скриптов нет)
LOGIN_TRIES, LOGIN_WINDOW = 10, 60                      # промахов с одного адреса за окно в секундах, дальше 429
_LOGIN_FAILS, _LOGIN_LOCK = {}, threading.Lock()

# Совместный режим (GRADO2_HUB=1 или --hub): аккаунты и проекты на сервере (hub.py). HUB — экземпляр хаба, None — обычная
# локальная работа. В этом режиме GRADO2_TOKEN не действует: вход заменяют учётные записи.
HUB = None
SESSION_COOKIE = "grado_session"
# Гостевой вход (владелец 06.10.2026): GRADO2_GUEST=1 — совместный сайт открывается без пароля под учётной записью «Гость»
# (hub.guest_session). После «Выйти» кука NOGUEST_COOKIE держит экран входа, чтобы войти своим логином.
GUEST = os.environ.get("GRADO2_GUEST") == "1"
NOGUEST_COOKIE = "grado_noguest"
BIG_BODY = threading.BoundedSemaphore(3)    # одновременных запросов крупнее MAX_BODY в совместном режиме
EVENTS_RECHECK = 10               # как часто открытый поток событий заново проверяет сессию и доступ (секунды)
LOCAL_PROJECTS_OFF = "в совместном режиме проекты хранятся на сервере: окно «Совместные проекты»"
OGD_OWNER = {"login": None}        # кто запустил выгрузку «Всё из ГИС ОГД»: остановить и забрать файл может он или администратор


def hub_enabled(argv=(), env=None):
    env = os.environ if env is None else env
    return "--hub" in argv or env.get("GRADO2_HUB") == "1"


def open_hub(root=None):
    """Хаб в каталоге GRADO2_HUB_DIR, по умолчанию <проекты>/.hub."""
    hubmod.QUOTA_BYTES = PROJECTS_CAP                                 # одна квота и для локальных проектов, и для хаба
    return hubmod.Hub(root or os.environ.get("GRADO2_HUB_DIR") or PROJECTS / ".hub")


def same_token(a, b):
    """Сравнение ключей за постоянное время (по байтам), чтобы не выдавать совпавший префикс по времени ответа."""
    return hmac.compare_digest(str(a).encode("utf-8", "replace"), str(b).encode("utf-8", "replace"))


# ---------- HTTP: Starlette (BSD) под uvicorn (BSD); тела запросов проверяет pydantic (MIT) ----------
# Порядок для каждого запроса: Guard (чужой Host или Origin → 403, ключ доступа или сессия хаба, заголовки защиты на любом
# ответе) → маршрут из ROUTES → функция маршрута в пуле нитей (диск, порталы и печать — блокирующие). Чего нет в ROUTES,
# отдаёт StaticFiles из web/. Тесты: tests/test_server.py, tests/test_hub_server.py.

THREADS = 200        # нитей для запросов: печать и выгрузки идут минутами, поток событий хаба держит нить на время ожидания


def _bbox_check(v):
    if len(v) != 4 or not (-180 <= v[0] < v[2] <= 180 and -90 <= v[1] < v[3] <= 90):
        raise ValueError("ожидается [запад, юг, восток, север] в градусах")
    return v


Bbox = Annotated[list[float], AfterValidator(_bbox_check)]


class _Body(BaseModel):
    model_config = ConfigDict(extra="ignore")


class FetchBody(_Body):
    """POST /api/fetch: область данных, территория (OSM и ЕГКО берут «территория + margin_m», не рамку листа), источники."""
    bbox: Bbox
    territory: Bbox | None = None
    margin_m: float = DATA_MARGIN_M
    sources: list | None = None

    @field_validator("margin_m")
    @classmethod
    def _margin(cls, v):
        return min(max(v, 0.0), 2000.0)


class TepBody(_Body):
    """POST /api/tep: исходные числа ТЭП; поле без значения не передаётся в tep() (там своё значение по умолчанию)."""
    terr_ha: float | None = None
    restrict_ha: float | None = None
    spp_new_m2: float | None = None
    share: float | None = None
    spp_kept_m2: float | None = None
    spp_low_m2: float | None = None
    nonres_part: float | None = None
    education_zone: float | None = None
    k1: float | None = None
    k2: float | None = None
    tinao: float | None = None
    territory_mode: float | None = None
    unbuilt_share: float | None = None
    free_doo: float | None = None
    free_school: float | None = None
    free_clinic: float | None = None
    park_share_underground: float | None = None
    park_share_multi: float | None = None
    constants: dict | None = None


class PointBody(_Body):
    lon: float
    lat: float


def _invalid(e):
    """Первая ошибка pydantic словами для 400: «bbox: ожидается …»."""
    err = e.errors()[0]
    where = ".".join(str(x) for x in err.get("loc", ()) if not isinstance(x, int)) or "запрос"
    return f"{where}: {str(err.get('msg', '')).removeprefix('Value error, ')}"


def _json(code, obj, headers=None):
    """Ответ JSON; headers — {имя: значение или список значений} (две куки — два заголовка Set-Cookie)."""
    r = Response(json.dumps(obj, ensure_ascii=False).encode("utf-8"), code, media_type="application/json; charset=utf-8")
    for k, v in (headers or {}).items():
        for one in (v if isinstance(v, list) else [v]):
            r.headers.append(k, one)
    return r


def _file(body, ctype, name=None, extra=()):
    """Ответ файлом: name — имя для «Сохранить как» (латиница), extra — пары дополнительных заголовков."""
    r = Response(body, 200, media_type=ctype)
    for h, v in extra:
        r.headers.append(h, v)
    if name:
        r.headers["Content-Disposition"] = f'attachment; filename="{name}"'
    return r


class Ctx:
    """Запрос глазами маршрутов: адрес с запросом, заголовки, адрес клиента, тело и пользователь хаба (считается раз)."""

    def __init__(self, request, body=b""):
        self.request, self.body = request, body
        self.method = request.method
        q = request.url.query
        self.path = request.url.path + ("?" + q if q else "")
        self.route = request.url.path
        self.headers = request.headers
        self.query = parse_qs(q)
        self.peer = request.client.host if request.client else ""
        self.port = (request.scope.get("server") or ("", 0))[1]

    def q(self, name, default=""):
        return (self.query.get(name) or [default])[0]

    def obj(self):
        """Тело POST — JSON-объект; список, число или строка вместо него — отказ 400 (ValueError → ответ с причиной)."""
        try:
            req = json.loads(self.body or b"{}")
        except RecursionError:                           # вложенность в тысячи уровней: обычный отказ, а не 500
            raise ValueError("слишком глубокая вложенность JSON") from None
        if not isinstance(req, dict):
            raise ValueError("тело запроса должно быть JSON-объектом")
        return req

    def model(self, cls):
        """Тело по модели pydantic; ошибка — ValueError с причиной по-русски («bbox: ожидается …»)."""
        try:
            return cls.model_validate(self.obj())
        except ValidationError as e:
            raise ValueError(_invalid(e)) from None

    def content_type(self):
        return (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()

    def foreign(self):
        """Запрос не от самой программы: чужой адрес в Host (подмена DNS на 127.0.0.1) или страница другого сайта
        (Origin). Такой сайт мог бы молча перезаписать проект обычной формой — сервер ему не отвечает."""
        ok = {f"127.0.0.1:{self.port}", f"localhost:{self.port}", f"[::1]:{self.port}"}
        origins = {"http://" + h for h in ok}
        # сервер за обратным прокси (grado.tailink.tech): имя сайта задаёт GRADO2_PUBLIC_HOST, вход — пароль прокси
        public = os.environ.get("GRADO2_PUBLIC_HOST")
        if public:
            ok.add(public)
            origins.add("https://" + public)
        if (self.headers.get("Host") or "") not in ok:
            return True
        origin = self.headers.get("Origin")
        if origin is not None and origin not in origins:
            return True
        # запись по запросу, который браузер сам пометил «чужой сайт» или «соседний поддомен», — не от программы
        # (Origin у POST есть всегда, это вторая защита; GET-переходы по ссылкам извне остаются открытыми)
        return self.method == "POST" and (self.headers.get("Sec-Fetch-Site") or "").lower() in ("cross-site", "same-site")

    def cookie_value(self, name):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == name:
                return v
        return ""

    def authed(self):
        """Есть ключ доступа: кука grado_token или заголовок X-Grado-Token (для скриптов)."""
        if same_token(self.headers.get(TOKEN_HEADER) or "", TOKEN):
            return True
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == TOKEN_COOKIE and same_token(unquote(v), TOKEN):
                return True
        return False

    def local_probe(self):
        """Службы самого сервера (tools/deploy-server.sh спрашивает ход выгрузки перед перезапуском) ходят по loopback
        с Host 127.0.0.1:порт и без заголовков прокси — им ключ не нужен, но только на трёх чтениях без данных проектов."""
        return (self.method == "GET" and self.route in ("/api/health", "/api/progress", "/api/ogd_all/status")
                and self.peer in ("127.0.0.1", "::1")
                and not any(self.headers.get(h) for h in ("X-Forwarded-For", "Forwarded", "X-Real-IP")))

    def gate(self):
        """Ключ доступа или сессия хаба: ответ-отказ (или переход на вход), если дальше идти нельзя, иначе None."""
        if HUB:
            return self.hub_gate()
        if not TOKEN:
            return None
        path, method = self.route, self.method
        if method != "POST" and (path in LOGIN_OPEN or path == "/api/health") or self.local_probe():
            return None
        if method == "POST" and path in ("/api/login", "/api/logout"):
            return None
        if self.authed():
            return None
        if method != "POST" and (path.endswith("/") or path.endswith(".html") or path == "/old"):   # страницы: /, /next/, /old
            return Response(b"", 302, headers={"Location": "/login.html"})
        return _json(401, {"error": "нужен вход"})

    def hub_gate(self):
        """Совместный режим: открыты здоровье сервера, статика (в ней нет данных), вход, регистрация и «кто я»;
        остальное — только с сессией."""
        path, method = self.route, self.method
        if method in ("GET", "HEAD") and (not path.startswith("/api/") or path == "/api/health"):
            return None
        if self.local_probe():
            return None
        if method == "POST" and path in ("/api/hub/login", "/api/hub/register", "/api/hub/guest"):
            return None
        if method == "GET" and path == "/api/hub/me":
            return None
        if self.who():
            return None
        return _json(401, {"error": "нужен вход"})

    def tls(self):
        return "https" in (self.headers.get("X-Forwarded-Proto") or "").lower()

    def cookie(self, value, max_age):
        """Set-Cookie с ключом; Secure — когда прокси сообщил, что снаружи https."""
        return (f"{TOKEN_COOKIE}={quote(value, safe='')}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"
                + ("; Secure" if self.tls() else ""))

    def client_ip(self):
        return client_ip(self.peer, self.headers)

    def session_token(self):
        return self.cookie_value(SESSION_COOKIE)

    def session_cookie(self, value, max_age):
        return f"{SESSION_COOKIE}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}" + ("; Secure" if self.tls() else "")

    def noguest_cookie(self, on):
        """После «Выйти» на гостевом сайте — экран входа до закрытия браузера (кука без срока); вход любым способом её снимает."""
        return f"{NOGUEST_COOKIE}={'1' if on else ''}; Path=/; HttpOnly; SameSite=Lax" + ("" if on else "; Max-Age=0") + ("; Secure" if self.tls() else "")

    def who(self):
        """Пользователь по куке grado_session ({login, name, admin}) или None; на запрос считается один раз."""
        if not hasattr(self, "_who"):
            token = self.session_token()
            self._who = HUB.session_user(token) if token else None
        return self._who

    def ogd_may(self):
        """Выгрузку «Всё из ГИС ОГД» останавливает и забирает тот, кто её начал, или администратор."""
        if not HUB:
            return True
        u = self.who() or {}
        return bool(u.get("admin")) or (u.get("login") is not None and u.get("login") == OGD_OWNER["login"])

    def project_name(self):
        return AUTOSAVE if self.query.get("autosave") else self.q("name")

    def log_fail(self, e):
        """Причина сбоя — в журнал сервера (stderr), клиенту она не уходит."""
        _log_line(f"{self.method} {self.route}: {type(e).__name__}: {e}")


def _log_line(text):
    if sys.stderr:
        sys.stderr.write(f"[{time.strftime('%d/%b/%Y %H:%M:%S')}] {text}\n")


def client_ip(peer, headers):
    """Адрес клиента для счёта промахов. X-Forwarded-For верим, только когда запрос пришёл с самого сервера
    (127.0.0.1/::1, то есть от нашего Caddy) и берём последний адрес: его дописал прокси, первый клиент подделывает.
    Запрос с чужого адреса считается по адресу сокета. IPv6 сводится к сети /64: иначе адрес меняют на лету."""
    ip = peer
    if peer in ("127.0.0.1", "::1"):
        fwd = (headers.get("X-Forwarded-For") or "").split(",")[-1].strip()
        if fwd:
            ip = fwd
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        a = ipaddress.ip_address(peer)
    if a.version == 6:
        a = a.ipv4_mapped or ipaddress.ip_network(f"{a}/64", strict=False).network_address
    return str(a)


# ----- GET -----

def get_styles(c):
    name = c.route.removeprefix("/styles/")
    if name not in STYLE_FILES:
        return None                                      # не наш файл стиля — дальше статика (404)
    return Response((STYLES / name).read_bytes(), media_type="application/json; charset=utf-8")


def get_search_cadastral(c):
    try:
        code, obj = search_cad(c.q("q")[:2000])
    except ConnectorError:
        code, obj = 502, {"error": "NSPD did not answer, try again later"}
    return _json(code, obj)


def get_search(c):
    code, obj = (search_addr if c.route.endswith("address") else search_any)(c.q("q")[:2000])
    return _json(code, obj)


def get_sources(c):
    return _json(200, {k: {"title": v[2], "kind": v[0], **({"code": cd} if (cd := source_ogd_code(k)) else {})} for k, v in SOURCES.items()})


def get_health(c):
    return _json(200, {"pid": os.getpid(), "stamp": STAMP, "version": VERSION, "hub": HUB is not None})


def get_ogd_tree(c):
    import ogd_all
    try:
        return _json(200, {"tree": ogd_all.catalog_tree(ogd_catalog())})
    except ConnectorError as e:
        return _json(502, {"error": str(e)})


def get_ogd_file(c):
    if not c.ogd_may():
        return _json(403, {"error": "выгрузку запустил другой пользователь"})
    job = OGD_JOB[0] if OGD_JOB else None
    if not job or not job.file or not job.file.exists():
        return _json(404, {"error": "no file"})
    r = _file(job.file.read_bytes(), "application/zip")
    # имя с названием листа — по-русски; заголовок HTTP — только латиница
    r.headers["Content-Disposition"] = f"attachment; filename=\"gisogd.zip\"; filename*=UTF-8''{quote(job.file.name)}"
    return r


def get_fgistp(c):
    try:
        if c.route == "/api/fgistp/docs":
            if c.q("q").strip():
                return _json(200, {"docs": fgistp_search(c.q("q"), fgistp_catalog())})
            bbox = [float(v) for v in c.query["bbox"][0].split(",")]
            return _json(200, {"docs": fgistp_docs(bbox, fgistp_catalog())})
        return _json(200, {"layers": FgistpConnector().discover(c.query["uin"][0])})
    except ConnectorError as e:
        return _json(502, {"error": str(e)})
    except OSError as e:
        c.log_fail(e)
        return _json(502, {"error": "ФГИС ТП недоступна"})


def get_project(c):
    if HUB:
        return _json(403, {"error": LOCAL_PROJECTS_OFF})
    try:
        body = project_path(c.project_name()).read_bytes()
    except (ValueError, OSError):
        return _json(404, {"error": "no such project"})
    return Response(body, media_type="application/json; charset=utf-8")


def get_projects(c):
    if HUB:
        return _json(403, {"error": LOCAL_PROJECTS_OFF})
    return _json(200, list_projects())


GET_ROUTES = {
    "/api/search/cadastral": get_search_cadastral,
    "/api/search/address": get_search,
    "/api/search": get_search,
    "/api/sources": get_sources,
    "/api/layer_roles": lambda c: _json(200, layer_roles()),
    "/api/tep/norms": lambda c: _json(200, tep_norms()),
    "/api/health": get_health,
    "/api/progress": lambda c: _json(200, dict(PROGRESS)),
    "/api/print/progress": lambda c: _json(200, dict(PRINT_PROGRESS)),
    "/api/ogd_all/tree": get_ogd_tree,
    "/api/ogd_all/status": lambda c: _json(200, OGD_JOB[0].state if OGD_JOB else {"running": False}),
    "/api/ogd_all/file": get_ogd_file,
    "/api/fgistp/docs": get_fgistp,
    "/api/fgistp/layers": get_fgistp,
    "/api/projects": get_projects,
    "/api/project": get_project,
}


# ----- POST -----

def post_login(c):
    """POST /api/login {"token": …}: верный ключ → кука на 30 дней; неверный → 401, 10 промахов за минуту → 429."""
    if len(c.body) > 4096:
        return _json(413, {"error": "запрос слишком велик"})
    token = c.obj().get("token")
    ip, now = c.client_ip(), time.time()
    with _LOGIN_LOCK:
        for k in [k for k, v in _LOGIN_FAILS.items() if not v or now - v[-1] > LOGIN_WINDOW]:
            del _LOGIN_FAILS[k]                         # старые записи уходят, словарь не растёт
        fails = [t for t in _LOGIN_FAILS.get(ip, []) if now - t <= LOGIN_WINDOW]
        if len(fails) >= LOGIN_TRIES:
            return _json(429, {"error": "слишком много попыток, подождите минуту"})
        if not isinstance(token, str) or not same_token(token, TOKEN):
            _LOGIN_FAILS[ip] = fails + [now]
            return _json(401, {"error": "неверный ключ"})
        _LOGIN_FAILS.pop(ip, None)
    return _json(200, {"ok": True}, {"Set-Cookie": c.cookie(token, 2592000)})


def post_logout(c):
    return _json(200, {"ok": True}, {"Set-Cookie": c.cookie("", 0)})


def post_import_files(c):
    import base64
    import file_io
    req = c.obj()
    files = {f["name"]: base64.b64decode(f["b64"]) for f in req.get("files") or []}
    return _json(200, {"layers": file_io.import_files(files, REDLN, req.get("local") or "msk")})


def post_import_dxf(c):
    import dxf_io
    fc, notes = dxf_io.import_dxf(c.body, REDLN, "ogd" if c.q("local") == "ogd" else "msk")
    return _json(200, {"features": fc, "notes": notes})


def post_project(c):
    if HUB:
        return _json(403, {"error": LOCAL_PROJECTS_OFF})
    try:
        path = save_project(c.project_name(), c.body)
    except QuotaExceeded:
        return _json(507, {"error": f"папка проектов больше {PROJECTS_CAP // 2**30} ГБ: удалите старые проекты и версии"})
    return _json(200, {"saved": path.stem, "modified": path.stat().st_mtime})   # имя, не путь на диске


def post_fetch(c):
    b = c.model(FetchBody)
    layers, errors = fetch(b.bbox, list(b.sources or []), b.territory, b.margin_m)
    return _json(200, {"layers": layers, "errors": errors})


def _album(kind, render, ctype):
    def post(c):
        import print_io
        req = c.obj()
        prog = lambda got, total: PRINT_PROGRESS.update(kind=kind, got=got, total=total)
        try:
            body = getattr(print_io, render)(req, REDLN, LGR_DASH, esri_tile, prog)
        finally:
            PRINT_PROGRESS.clear()
        return _file(body, ctype, f"grado2-album.{kind}", not_ready_headers(req))   # листы «не готов»: номера и причины (ASCII)
    return post


def post_export_sat(c):
    # спутник Яндекса по рамке листа — в МСК для AutoCAD (снимок, файл привязки, DXF с растром на месте)
    import sat_io
    req = c.obj()
    try:
        frame = (sat_io.frame_msk(req["center"], req["rect"], float(req["scale"])) if req.get("rect")
                 else sat_io.bbox_msk(req["bbox"]))
        prog = lambda got, total: PROGRESS.__setitem__("sat", {"title": "Спутник Яндекса", "got": got, "total": total, "stage": "tiles"})
        base = str(req.get("base") or "")[:400]      # полный путь папки распаковки на компьютере владельца
        body = sat_io.export_sat(frame, CACHE / "tiles" / "yandex-sat", base, prog)
    except (KeyError, TypeError, ValueError) as e:
        return _json(400, {"error": str(e).encode("ascii", "replace").decode()})
    finally:
        PROGRESS.pop("sat", None)
    return _file(body, "application/zip", "sputnik_yandex_msk.zip")


def post_print_svg(c):
    import print_io
    req = c.obj()
    body = print_io.render_preview_svg(req, REDLN, LGR_DASH, int(req.get("index", 0)), esri_tile).encode("utf-8")
    return _file(body, "image/svg+xml; charset=utf-8", None, not_ready_headers(req))


def _sheet_bbox(req):
    """Лист, нарисованный на карте (МСК), или прежний bbox WGS84 — в проверенный bbox."""
    import ogd_all
    sheet = req.get("sheet")
    raw = ogd_all.sheet_bbox_wgs(sheet) if sheet else req["bbox"]
    try:
        return BboxBody.model_validate({"bbox": raw}).bbox
    except ValidationError as e:
        raise ValueError(_invalid(e)) from None


class BboxBody(_Body):
    bbox: Bbox


def post_ogd_start(c):
    import ogd_all
    req = c.obj()
    bbox = _sheet_bbox(req)
    if bbox_km2(bbox) > LIMIT_KM2["gisogd"]:
        return _json(400, {"error": f"область больше {LIMIT_KM2['gisogd']:g} км²"})
    with OGD_LOCK:
        if OGD_JOB and OGD_JOB[0].state["running"]:
            return _json(409, {"error": "выгрузка уже идёт"})
        OGD_JOB[:] = [ogd_all.Job(bbox, req.get("boundary"), CACHE / "gisogd", CACHE / "ogd_all",
                                   str(req.get("name") or "gisogd"), sheet=req.get("sheet"),
                                   styles=ogd_all.portal_styles(CACHE / "gisogd"),
                                   codes=req.get("codes"), where=req.get("where"),
                                   redln={"lib": REDLN, "idx": REDLN_IDX, "colors": LGR_COLORS, "dash": LGR_DASH})]
        OGD_OWNER["login"] = (c.who() or {}).get("login")
    return _json(200, OGD_JOB[0].state)


def post_layout(c):
    # «Макет листа» нового интерфейса (/next/): лист редактора в PDF или SVG, карта блока отдельной картинкой
    import layout_io
    req = c.obj()
    try:
        if c.route == "/api/print/layout":
            return _file(layout_io.render_pdf(req, REDLN, LGR_DASH, esri_tile), "application/pdf", "grado2-sheet.pdf")
        render = layout_io.render_page_svg if c.route == "/api/print/layout_svg" else layout_io.map_svg
        return _file(render(req, REDLN, LGR_DASH, esri_tile).encode("utf-8"), "image/svg+xml; charset=utf-8")
    except (KeyError, TypeError, ValueError) as e:
        return _json(400, {"error": str(e).encode("ascii", "replace").decode()})


def post_ogd_label_angles(c):
    # подписи слоя, загруженного до v0.63, — угол вдоль границы своей папки
    req = c.obj()
    pts = [p[:2] for p in req.get("points") or []][:20000]
    if not pts:
        return _json(200, {"angles": []})
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    feats = [{"geometry": {"type": "Point", "coordinates": p}, "properties": {"text": "x"}} for p in pts]
    ogd_label_angles(str(req.get("code") or ""), feats, (min(xs), min(ys), max(xs), max(ys)))
    return _json(200, {"angles": [f["properties"].get("_angle") for f in feats]})


def post_ogd_styles(c):
    # оформление слоёв портала ГИС ОГД в проекте — как на карте портала (CartoCSS слоя, кэш 30 дней)
    import ogd_all
    # слои ЛГР (зоны, границы, надписи СПРИТ и ЗОУИТ) — по Эталону ЛГР (moscow_lgr.json), код — из атрибута слоя
    # (field) или по названию слоя и папки; своё оформление владельца (OWN_STYLE) — сильнее всего
    req = c.obj()
    styles, out, rev = ogd_all.portal_styles(CACHE / "gisogd"), {}, {}
    try:
        cat = {x["code"]: x for x in ogd_catalog()}
    except ConnectorError:
        cat = {}
    for code, spec in list((req.get("layers") or {}).items())[:800]:
        geom, field = (spec, None) if isinstance(spec, str) else (list(spec) + [None, None])[:2]
        if geom not in ("poly", "line", "point"):
            continue
        it = cat.get(code) or {}
        parent = str(it.get("path", "")).rsplit(" / ", 2)[-2] if " / " in str(it.get("path", "")) else ""
        lgr = LGR_BY_CODE.get(ogd_all.etalon_code(it.get("name", ""), parent, field))
        try:
            if code in ogd_all.OWN_STYLE and geom == "poly":
                out[code], rev[code] = ogd_all.layer_style(code, "", geom), ogd_all.OWN_STYLE[code]["rev"]
            elif lgr:
                out[code], rev[code] = ogd_all.etalon_style(lgr, geom), ogd_all.ETALON_REV
            else:
                out[code], rev[code] = ogd_all.portal_style(styles(str(code)), geom), 1
        except (OSError, ValueError, ConnectorError):
            pass                                        # портал не ответил — слой остаётся в своём оформлении
    return _json(200, {"styles": out, "rev": rev})


def post_ogd_scan(c):
    import ogd_all
    return _json(200, {"counts": ogd_all.scan(_sheet_bbox(c.obj()), CACHE / "gisogd", ogd_catalog())})


def post_ogd_cancel(c):
    if not c.ogd_may():
        return _json(403, {"error": "выгрузку запустил другой пользователь"})
    if OGD_JOB:
        OGD_JOB[0].cancel.set()
    return _json(200, {"ok": True})


def post_export_dxf(c):
    import dxf_io
    return _file(dxf_io.export_dxf(c.obj()["layers"], REDLN, LGR_COLORS), "application/zip", "grado2-dxf.zip")


def post_export_geojson(c):
    import export_io
    return _file(export_io.export_geojson(c.obj().get("layers")), "application/zip", "grado2-geojson-msk.zip")


def post_export_xlsx(c):
    import export_io
    req = c.obj()
    body = export_io.export_xlsx(req.get("tep") or [], req.get("sheets") or [], req.get("note"), req.get("project"))
    return _file(body, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "grado2-tep.xlsx")


def post_fgistp_fetch(c):
    req = c.obj()
    bbox = [float(v) for v in req["bbox"]]
    try:
        return _json(200, {"layers": fgistp_fetch(str(req["uin"]), set(req["classids"]), bbox)})
    except ConnectorError as e:
        return _json(502, {"error": str(e)})


def post_tep(c):
    return _json(200, tep(**c.model(TepBody).model_dump(exclude_none=True)))


def post_place(c):
    import export_io
    req = c.obj()
    lon, lat = export_io._num(req["lon"], "lon", 180), export_io._num(req["lat"], "lat", 90)
    try:
        return _json(200, place_info(float(lon), float(lat), req.get("polygon")))
    except ConnectorError as e:
        _log_portal("place", str(e))
        return _json(502, {"error": plain_portal_error(str(e))})


def post_rail_route(c):
    p = c.model(PointBody)
    try:
        return _json(200, rail_route(p.lon, p.lat) or {})
    except ConnectorError as e:
        return _json(502, {"error": str(e)})


POST_ROUTES = {
    "/api/import/files": post_import_files,
    "/api/import/dxf": post_import_dxf,
    "/api/project": post_project,
    "/api/fetch": post_fetch,
    "/api/print/pdf": _album("pdf", "render_pdf", "application/pdf"),
    "/api/print/pptx": _album("pptx", "render_pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    "/api/export/sat": post_export_sat,
    "/api/print/svg": post_print_svg,
    "/api/print/layout": post_layout,
    "/api/print/layout_svg": post_layout,
    "/api/print/map_svg": post_layout,
    "/api/ogd_all/start": post_ogd_start,
    "/api/ogd_all/label_angles": post_ogd_label_angles,
    "/api/ogd_all/styles": post_ogd_styles,
    "/api/ogd_all/scan": post_ogd_scan,
    "/api/ogd_all/cancel": post_ogd_cancel,
    "/api/export/dxf": post_export_dxf,
    "/api/export/geojson": post_export_geojson,
    "/api/export/xlsx": post_export_xlsx,
    "/api/fgistp/fetch": post_fgistp_fetch,
    "/api/tep": post_tep,
    "/api/place": post_place,
    "/api/rail_route": post_rail_route,
}


# ----- совместный режим (hub.py): маршруты /api/hub/* -----

def hub_get(c):
    q, path, u = c.query, c.route, c.who()
    if path == "/api/hub/me":
        if u:
            return _json(200, {"user": u})
        if GUEST and not c.cookie_value(NOGUEST_COOKIE):     # гостевой сайт: сразу внутрь, без экрана входа
            token, user = HUB.guest_session(c.headers.get("User-Agent") or "")
            return _json(200, {"user": user}, {"Set-Cookie": c.session_cookie(token, 2592000)})
        return _json(401, {"error": "нужен вход", **({"guest": True} if GUEST else {})})
    if path == "/api/hub/users":
        return _json(200, {"users": HUB.list_users(u)})
    if path == "/api/hub/invites":
        return _json(200, {"invites": HUB.list_invites(u)})
    if path == "/api/hub/projects":
        return _json(200, {"projects": HUB.list_projects(u)})
    if path == "/api/hub/teams":
        return _json(200, {"teams": HUB.list_teams(u)})
    m = HUB_PROJECT_RE.fullmatch(path)
    if not m:
        return _json(404, {"error": "no such method"})
    pid, rest = unquote(m.group(1)), m.group(2) or ""
    if rest == "":
        return _json(200, HUB.get_project(u, pid))
    if rest == "sections":
        names = [x for v in q.get("names", []) for x in v.split(",") if x]
        return _json(200, HUB.get_sections(u, pid, names))
    if rest == "download":
        name, data = HUB.project_file(u, pid)
        stem = re.sub(r"[^A-Za-z0-9._-]", "_", name.removesuffix(".grado2"))
        ascii_name = (stem if re.search("[A-Za-z0-9]", stem) else "project") + ".grado2"
        r = _file(data, "application/octet-stream")
        r.headers["Content-Disposition"] = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"
        return r
    if rest == "events":
        return hub_events(c, u, pid)
    if rest == "comments":
        return _json(200, {"comments": HUB.comments(u, pid)})
    if rest == "history":
        return _json(200, {"history": HUB.history(u, pid)})
    if rest == "activity":
        return _json(200, {"activity": HUB.activity(u, pid)})
    if rest == "link":
        return _json(200, HUB.get_link(u, pid))
    return _json(404, {"error": "no such method"})


def hub_events(c, user, pid):
    """Поток событий проекта (SSE): одна вкладка — одна подписка. Каждые 15 с — строка «: ping»; клиент ушёл — Starlette
    прерывает поток, подписка закрывается всегда. Сессия и доступ перепроверяются раз в EVENTS_RECHECK секунд."""
    hub = HUB                                  # поток живёт дольше запроса: держим свой хаб, глобальный могут подменить
    sub = hub.subscribe(user, pid)             # отказ (нет проекта, нет доступа, слишком много потоков) — обычным ответом
    token = c.session_token()

    async def stream():
        try:
            checked = time.monotonic()
            while True:
                ev = await run_in_threadpool(sub.get, min(15, EVENTS_RECHECK))   # не дольше срока проверки сессии
                if time.monotonic() - checked >= EVENTS_RECHECK:     # вышел, сессия истекла, отключили, убрали из проекта
                    checked = time.monotonic()
                    who = await run_in_threadpool(hub.session_user, token)
                    if not who or hub.role_of(who, pid) is None:
                        break
                if ev is None:
                    if sub.closed:                 # проект удалён или доступ закрыт, очередь выбрана
                        break
                    yield b": ping\n\n"
                else:
                    yield b"data: " + json.dumps(ev).encode("ascii") + b"\n\n"
        finally:
            sub.close()
    return StreamingResponse(stream(), media_type="text/event-stream; charset=utf-8", headers={"X-Accel-Buffering": "no"})


def hub_post(c):
    path, req, u = c.route, c.obj(), c.who()
    ip, ua = c.client_ip(), c.headers.get("User-Agent") or ""
    if path in ("/api/hub/login", "/api/hub/register", "/api/hub/guest"):
        if path == "/api/hub/login":
            token, user = HUB.login(req.get("login"), req.get("password"), ip, ua)
        elif path == "/api/hub/guest":
            if not GUEST:
                return _json(403, {"error": "гостевой вход выключен"})
            token, user = HUB.guest_session(ua)
        else:
            token, user = HUB.register(req.get("invite"), req.get("login"), req.get("name"), req.get("password"), ip, ua)
        return _json(200, {"user": user}, {"Set-Cookie": [c.session_cookie(token, 2592000)] + ([c.noguest_cookie(False)] if GUEST else [])})
    if path == "/api/hub/logout":
        HUB.logout(c.session_token())
        cookies = [c.session_cookie("", 0)] + ([c.noguest_cookie(True)] if GUEST else [])
        return _json(200, {"ok": True}, {"Set-Cookie": cookies})
    if path == "/api/hub/password":
        HUB.change_password(u, req.get("old"), req.get("new"), keep_token=c.session_token())   # остальные входы гасятся
        return _json(200, {"ok": True})
    if path == "/api/hub/invites":
        return _json(200, {"code": HUB.create_invite(u)})
    if path.startswith("/api/hub/users/"):
        bad = set(req) - {"disabled", "admin", "name"}
        if bad:
            raise hubmod.HubError(400, "нельзя менять поля: " + ", ".join(sorted(map(str, bad))))
        return _json(200, {"user": HUB.update_user(u, unquote(path[len("/api/hub/users/"):]), **req)})
    if path == "/api/hub/projects":
        return _json(200, HUB.create_project(u, req.get("name"), req.get("project"), req.get("team"), req.get("team_access")))
    if path == "/api/hub/teams":
        return _json(200, HUB.create_team(u, req.get("name")))
    if path == "/api/hub/join":            # токен ссылки — только в теле запроса, не в адресе (адрес попадает в журнал)
        return _json(200, HUB.join(u, req.get("token"), ip))
    tm = HUB_TEAM_RE.fullmatch(path)
    if tm:
        tid, act = unquote(tm.group(1)), tm.group(2) or ""
        if not HUB_TID_RE.fullmatch(tid):
            return _json(404, {"error": "команда не найдена"})
        if act == "":
            return _json(200, {"name": HUB.rename_team(u, tid, req.get("name"))})
        if act == "delete":
            HUB.delete_team(u, tid)
            return _json(200, {"ok": True})
        if "role" not in req:                  # как у проекта: пропуск поля не должен убирать человека из команды
            raise hubmod.HubError(400, "укажите role: owner, member или null")
        return _json(200, {"members": HUB.set_team_member(u, tid, req.get("login"), req["role"])})
    m = HUB_PROJECT_RE.fullmatch(path)
    if not m:
        return _json(404, {"error": "no such method"})
    pid, rest = unquote(m.group(1)), m.group(2) or ""
    if rest == "":
        return _json(200, {"name": HUB.rename_project(u, pid, req.get("name"))})
    if rest == "delete":
        HUB.delete_project(u, pid)
        return _json(200, {"ok": True})
    if rest == "push":
        return _json(200, HUB.push(u, pid, req.get("base_rev"), req.get("sections"), req.get("client")))
    if rest == "members":
        if "role" not in req:                  # без роли «убрать» не выводим: пропуск поля не должен удалять человека
            raise hubmod.HubError(400, "укажите role: owner, editor, viewer или null")
        return _json(200, {"members": HUB.set_member(u, pid, req.get("login"), req["role"])})
    if rest == "team":
        if "team" not in req:                  # null = «Личные»; пропуск поля не должен переносить проект
            raise hubmod.HubError(400, "укажите team: id команды или null")
        return _json(200, HUB.set_project_team(u, pid, req["team"], req.get("team_access")))
    if rest == "star":
        if not isinstance(req.get("on"), bool):
            raise hubmod.HubError(400, "укажите on: true или false")
        return _json(200, HUB.set_star(u, pid, req["on"]))
    if rest == "copy":                     # тело короткое (имя, команда): предел 1 МБ, сам проект копируется на сервере
        return _json(200, HUB.copy_project(u, pid, req.get("name"), req.get("team"), req.get("team_access")))
    if rest == "link":
        if "role" not in req:                  # null = «выключить»; пропуск поля не должен гасить ссылку
            raise hubmod.HubError(400, "укажите role: viewer, editor или null")
        return _json(200, HUB.set_link(u, pid, req["role"], req.get("rotate", False)))
    if rest == "presence":
        HUB.presence(u, pid, req.get("client"), req.get("cursor"), req.get("layer"), req.get("sel"))
        return _json(200, {"ok": True})
    if rest == "comments":
        return _json(200, {"comment": HUB.add_comment(u, pid, req.get("text"), req.get("anchor"))})
    cm = re.fullmatch(r"comments/([^/]+)(?:/(reply|delete))?", rest)
    if cm:
        cid, act = unquote(cm.group(1)), cm.group(2)
        if act == "reply":
            return _json(200, {"comment": HUB.reply(u, pid, cid, req.get("text"))})
        if act == "delete":
            HUB.delete_comment(u, pid, cid)
            return _json(200, {"ok": True})
        return _json(200, {"comment": HUB.update_comment(u, pid, cid, req.get("text"), req.get("resolved"))})
    hm = re.fullmatch(r"history/([^/]+)/restore", rest)
    if hm:
        rev = unquote(hm.group(1))
        if not (rev.isascii() and rev.isdecimal()):
            raise hubmod.HubError(400, "некорректный номер версии")
        return _json(200, HUB.restore(u, pid, int(rev)))
    return _json(404, {"error": "no such method"})


def hub_call(c):
    """Маршруты /api/hub/*: HubError → его код и {"error": текст}; Conflict → 409 с телом конфликта; неожиданный сбой —
    500 без подробностей (причина в журнале сервера)."""
    try:
        if c.method == "POST":
            if c.content_type() != "application/json":
                return _json(415, {"error": "ожидается Content-Type: application/json"})
            return hub_post(c)
        return hub_get(c)
    except hubmod.Conflict as e:
        return _json(409, {**e.payload, "error": e.message})
    except hubmod.HubError as e:
        if e.status >= 500 and e.status != 507:         # 507 — «хранилище заполнено»: текст написан для человека
            c.log_fail(e)
            return _json(e.status, {"error": INTERNAL_ERROR})
        return _json(e.status, {"error": e.message})
    except (KeyError, ValueError, TypeError) as e:
        c.log_fail(e)
        return _json(400, {"error": "некорректный запрос"})
    except Exception as e:
        c.log_fail(e)
        return _json(500, {"error": INTERNAL_ERROR})


# ----- приём запроса -----

def _answer(c, fn):
    """Вызов маршрута с общими ответами на сбой: неверные данные → 400 с причиной, остальное → 500 (или 422 у импорта)
    без подробностей, причина в журнале сервера."""
    try:
        return fn(c)
    except (KeyError, ValueError, TypeError) as e:
        return _json(400, {"error": _bad(e)})
    except Exception as e:      # битый DXF и т.п.
        c.log_fail(e)
        if c.route.startswith("/api/import/"):
            return _json(422, {"error": "файл не удалось прочитать, подробности в журнале сервера"})
        return _json(500, {"error": INTERNAL_ERROR})


async def api_get(request):
    c = Ctx(request)
    q = request.url.query
    if c.route == "/":                  # адрес сайта открывает новый интерфейс; прежняя рабочая страница — /old
        return Response(b"", 302, headers={"Location": "/next/" + ("?" + q if q else "")})
    if c.route == "/old":               # без косой черты в конце: её скрипты и стили по-прежнему берутся из корня
        return await STATIC.get_response("index.html", request.scope)
    if HUB and c.route.startswith("/api/hub/"):
        return await run_in_threadpool(hub_call, c)
    fn = GET_ROUTES.get(c.route)
    if fn is None and c.route.startswith("/styles/"):
        fn = get_styles
    r = await run_in_threadpool(_answer, c, fn) if fn else None
    return r if r is not None else await STATIC.get_response(c.route.lstrip("/") or ".", request.scope)


async def _read_body(request, limit):
    """Тело запроса не больше limit байт; длиннее (тело кусками без Content-Length) — None, чтение прерывается."""
    parts, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            return None
        parts.append(chunk)
    return b"".join(parts)


async def api_post(request):
    c = Ctx(request)
    try:
        n = int(request.headers.get("Content-Length") or 0)
    except ValueError:
        return _json(400, {"error": "bad request: Content-Length"})
    limit = body_limit(c.route)
    if not 0 <= n <= limit:
        return _json(413, {"error": f"запрос больше {limit // 2**20} МБ"})
    big = bool(HUB) and n > MAX_BODY
    if big and not BIG_BODY.acquire(blocking=False):     # тело до 400 МБ читается в память: одновременно их принимается немного
        return _json(503, {"error": "сервер занят другой большой записью: повторите через минуту"})
    try:
        c.body = await _read_body(request, limit)
        if c.body is None:
            return _json(413, {"error": f"запрос больше {limit // 2**20} МБ"})
        if HUB:
            if c.route.startswith("/api/hub/"):
                return await run_in_threadpool(hub_call, c)
            # остальная запись тоже только JSON (кроме сырого DXF): форма с другого сайта так тело не отправит
            if c.route not in ("/api/import/dxf", "/api/project") and c.content_type() != "application/json":
                return _json(415, {"error": "ожидается Content-Type: application/json"})
        if TOKEN and not HUB and c.route in ("/api/login", "/api/logout"):
            return await run_in_threadpool(_answer, c, post_login if c.route == "/api/login" else post_logout)
        fn = POST_ROUTES.get(c.route)
        if fn is None:
            return _json(404, {"error": "no such method"})
        return await run_in_threadpool(_answer, c, fn)
    finally:
        if big:
            BIG_BODY.release()


def _deny():
    return Response(b"forbidden", 403, media_type="text/plain; charset=utf-8")


class Guard:
    """ASGI-обёртка всего приложения: чужие запросы и вход (ключ или сессия хаба) — до маршрутов; заголовки защиты и
    «no-cache» — на каждом ответе, в журнал — только ответы 4xx и 5xx (тише, как прежде)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        c = Ctx(Request(scope))

        async def send_safe(msg):
            if msg["type"] == "http.response.start":
                h = MutableHeaders(scope=msg)
                h["Cache-Control"] = "no-cache"       # после обновления браузер не держит старые app.js
                h["X-Content-Type-Options"] = "nosniff"
                h["X-Frame-Options"] = "SAMEORIGIN"
                h["Content-Security-Policy"] = CSP
                if msg["status"] >= 400:
                    _log_line(f'{c.peer} "{c.method} {c.route}" {msg["status"]}')
            await send(msg)
        if c.foreign():
            return await _deny()(scope, receive, send_safe)
        early = await run_in_threadpool(c.gate)       # сессия хаба читается с диска
        if early is not None:
            return await early(scope, receive, send_safe)
        await self.app(scope, receive, send_safe)


@contextlib.asynccontextmanager
async def _lifespan(app):
    import anyio.to_thread
    anyio.to_thread.current_default_thread_limiter().total_tokens = THREADS
    yield


STATIC = StaticFiles(directory=str(WEB), html=True, check_dir=False)
APP = Guard(Starlette(routes=[
    Route("/{path:path}", api_get, methods=["GET", "HEAD"]),
    Route("/{path:path}", api_post, methods=["POST"]),
], lifespan=_lifespan))


class Server:
    """uvicorn на своём сокете. Сокет занимается сразу: занятый порт — OSError в конструкторе (main перебирает порты).
    Очередь подключений 128: браузер при старте открывает около пятнадцати запросов сразу, очередь 5 часть из них роняла.
    Для тестов: Server(("127.0.0.1", 0)) → server_address, serve_forever() в нити, shutdown(), server_close()."""

    def __init__(self, addr, app=None):
        import socket
        import uvicorn
        self.socket = socket.create_server(addr, backlog=128)
        self.server_address = self.socket.getsockname()[:2]
        self._uv = uvicorn.Server(uvicorn.Config(app or APP, log_level="warning", access_log=False, proxy_headers=False,
                                                 server_header=False, lifespan="on", timeout_graceful_shutdown=5))
        self._done = threading.Event()

    def serve_forever(self):
        try:
            self._uv.run(sockets=[self.socket])           # SIGINT и SIGTERM uvicorn ловит сам (только в главной нити)
        finally:
            self._done.set()

    def shutdown(self):
        self._uv.should_exit = True
        self._done.wait(10)

    def server_close(self):
        self.socket.close()



def _bad(e):
    """Причина отказа для владельца: русское сообщение — как есть, техническое — с пометкой bad request (тело JSON, не заголовок)."""
    t = str(e)
    return t if re.search("[а-яё]", t, re.I) else f"bad request: {t}"


def code_stamp():
    """Версия серверного кода: время правки файлов бэкенда. Разная → запущенный сервер устарел и заменяется."""
    if FROZEN:
        return json.loads((WEB / "version.json").read_text("utf-8"))["version"]
    here = Path(__file__).resolve().parent
    # ядро тоже: обновление, затронувшее только коннекторы, иначе продолжало бы работать со старым кодом
    files = [*here.glob("*.py"), *(p for p in (here.parents[1] / "core").rglob("*.py") if "tests" not in p.parts),
             *(here.parents[1] / "core").rglob("*.json")]
    return max(p.stat().st_mtime for p in files)


# ---------- Запуск: версия кода, повторный запуск, сервер ----------
STAMP = code_stamp()          # версия кода, с которой этот процесс запущен
VERSION = json.loads((WEB / "version.json").read_text("utf-8"))["version"]


def _probe(url):
    """Запрос к своему серверу на порту: при включённом ключе доступа — с ключом, иначе /api/sources ответил бы 401."""
    import urllib.request
    return urllib.request.Request(url, headers={TOKEN_HEADER: TOKEN} if TOKEN else {})


def _running(port):
    """Сведения о ГРАДО 2 на порту: {"pid", "stamp"}; {} — ГРАДО, но старый, без /api/health; None — не ГРАДО."""
    import urllib.request
    if not _is_grado(port):
        return None
    try:
        with urllib.request.urlopen(_probe(f"http://127.0.0.1:{port}/api/health"), timeout=1) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def _is_grado(port):
    import urllib.request
    try:
        with urllib.request.urlopen(_probe(f"http://127.0.0.1:{port}/api/sources"), timeout=1) as r:
            return "nspd.parcels" in json.loads(r.read())
    except Exception:
        return False



def _is_our_process(pid):
    """pid из /api/health чужого процесса нельзя слепо убивать: командная строка должна содержать этот server.py
    (или, в собранном приложении, его исполняемый файл)."""
    import subprocess
    if not isinstance(pid, int) or pid <= 1:
        return False
    try:
        cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    marks = ["grado2/server.py", "grado2\\server.py", str(Path(__file__).resolve())]
    if FROZEN:
        marks.append(Path(sys.executable).name)
    return any(m in cmd for m in marks)



def main(argv=None):
    """Запуск: свободный порт от 8650, прежняя версия на порту заменяется, окно браузера открывается само."""
    argv = sys.argv[1:] if argv is None else argv
    import webbrowser
    global HUB
    if hub_enabled(argv):
        HUB = open_hub()
        print(f"ГРАДО 2: совместный режим, хранилище {HUB.root}")
    nums = [a for a in argv if not a.startswith("--")]
    port = int(nums[0]) if nums else int(os.environ.get("GRADO2_PORT") or 8650)
    import signal
    import time
    for p in range(port, port + 20):
        try:
            server = Server(("127.0.0.1", p))
            break
        except OSError:
            info = _running(p)
            if info is None:
                continue                                  # порт занят чужой программой
            if info.get("stamp") == STAMP:                # тот же код уже работает — просто открыть
                print(f"ГРАДО 2 уже работает: http://127.0.0.1:{p}")
                if not os.environ.get("GRADO2_NO_BROWSER"):
                    webbrowser.open(f"http://127.0.0.1:{p}")
                sys.exit(0)
            if not info.get("pid"):
                sys.exit(f"На порту {p} работает старая версия ГРАДО 2. Остановите её (Ctrl+C в её окне) и запустите снова.")
            print(f"На порту {p} работает прежняя версия ГРАДО 2 — заменяю её новой.")
            if not _is_our_process(info.get("pid")):
                print(f"Порт {p}: процесс {info.get('pid')} не похож на сервер ГРАДО 2, не останавливаю — пробую следующий порт.")
                continue
            os.kill(info["pid"], signal.SIGTERM)
            for _ in range(30):                           # ждём, пока порт освободится
                time.sleep(0.1)
                try:
                    server = Server(("127.0.0.1", p))
                    break
                except OSError:
                    pass
            else:
                sys.exit(f"Прежняя версия на порту {p} не остановилась. Остановите её вручную и запустите снова.")
            break
    else:
        sys.exit(f"порты {port}–{port + 19} заняты")
    print(f"ГРАДО 2: http://127.0.0.1:{p}")
    if not os.environ.get("GRADO2_NO_BROWSER"):      # тестовый запуск без открытия окна
        webbrowser.open(f"http://127.0.0.1:{p}")
    server.serve_forever()


if __name__ == "__main__":
    main()
