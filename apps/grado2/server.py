"""ГРАДО 2: локальный сервер.

Отдаёт веб-интерфейс из web/ и два метода:
  POST /api/fetch  {bbox:[w,s,e,n], sources:[ключ,...]} → реальные слои по области
  POST /api/tep    {terr_ha, restrict_ha, spp_new_m2, share, spp_kept_m2} → ТЭП (методика КРТ)
  POST /api/import/files {files:[{name, b64}]} → слои из GeoJSON, KML/KMZ, Shapefile, DXF (WGS84)
  POST /api/print/pdf {meta, sheets:[…]} → альбом PDF (листы А3/А1, рамка и штамп ГОСТ), /api/print/svg → лист для просмотра
  GET  /api/projects, GET|POST /api/project?name=… | ?autosave=1 → проекты в «Документы/ГРАДО 2»

Данные берутся коннекторами ядра (core/connectors), ТЭП — движком ядра (core/compute).
Геометрия на выходе всегда WGS84 (GeoJSON), без пересчёта в СК холста.

Запуск: python3 apps/grado2/server.py [порт]   (по умолчанию 8650)
"""

import json
import math
import os
import re
import sys
import threading
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# в собранной программе (PyInstaller) всё лежит в папке распаковки sys._MEIPASS: web/, core/…, docs/standards/
FROZEN = getattr(sys, "frozen", False)
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
for sub in ("core/connectors", "core/compute", "core/render", "core/layout"):
    sys.path.insert(0, str(ROOT / sub))

from grado_compute import Engine                                   # noqa: E402
from grado_connectors import crs                                   # noqa: E402
from grado_connectors.contract import ConnectorError               # noqa: E402
from grado_connectors.fgistp import FgistpConnector                # noqa: E402
from grado_connectors.gisogd_api import GISOGD_API_LAYERS, GisogdApi  # noqa: E402
from grado_connectors.nspd import NspdDirect                       # noqa: E402
from grado_connectors.osm import OsmOverpass                       # noqa: E402
from grado_connectors.terrain import TerrainContours               # noqa: E402
from grado_connectors.yandex_vmap import YandexVmap                # noqa: E402
from grado_render import acad_lin                                  # noqa: E402

WEB = ROOT / "web" if FROZEN else Path(__file__).resolve().parent / "web"
CACHE = Path.home() / ".grado2" / "cache"
PRESET = ROOT / "core/compute/grado_compute/presets/moscow_calc2.json"      # методика «Калькулятора 2.0» (docs/standards/moscow-ngp)
DISTRICTS = json.loads((ROOT / "core/compute/grado_compute/regulations/moscow_districts.json").read_text("utf-8"))
STYLES = ROOT / "core/render/grado_render/styles"
STYLE_FILES = {"redln97.json", "moscow_lgr.json", "moscow_genplan.json"}   # отдаются фронту как есть
# проекты — обычные файлы .grado2 (JSON) в папке документов: их видно в Finder/Проводнике, их можно переслать
PROJECTS = Path(os.environ.get("GRADO2_PROJECTS") or Path.home() / "Documents" / "ГРАДО 2")
AUTOSAVE = ".autosave"

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
}
SOURCES["gisogd.red_lines"] = ("gisogd", {"l1": None}, "Красные линии и ЛГР (ОГД)")
for _k in ("gisogd.func_zones", "gisogd.func_zones_tinao", "gisogd.szz", "gisogd.vodookhr"):
    SOURCES[_k] = ("gisogd", GISOGD_API_LAYERS[_k]["codes"], GISOGD_API_LAYERS[_k]["title"])
# ПЗЗ Москвы (120-ПП): подзоны несут регламент — предельные плотность, высоту и процент застройки;
# зоны — виды разрешённого использования. Старая и новая Москва — разные слои портала (коды сверены 23.09.2026).
SOURCES["gisogd.pzz_sub"] = ("gisogd", {"virtual98": None, "virtual132": None}, "ПЗЗ: подзоны — плотность, высота, застроенность (ОГД)")
SOURCES["gisogd.pzz_zones"] = ("gisogd", {"virtual90": None, "virtual130": None}, "ПЗЗ: территориальные зоны и ВРИ (ОГД)")
SOURCES["gisogd.okn"] = ("gisogd", {"virtual500": None, "virtual502": None, "virtual504": None, "virtual508": None}, "Объекты культурного наследия и их зоны (ОГД)")
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
SOURCES["gisogd.admin"] = ("gisogd_admin", None, "Административные округа и районы (ОГД)")
# ЕГКО Москвы — векторная картооснова портала ГИС ОГД (карта base2, коды сверены 23.09.2026). Значение кода — состояние
# здания: оно идёт в поле «Состояние», как тип зоны в «Вид зоны» у функциональных зон ТиНАО.
SOURCES["egko.buildings"] = ("egko", {"virtual6": "действующее", "virtual15": "строящееся", "virtual16": "разрушенное",
                                      "virtual17": "нулевой цикл (фундамент)"}, "Здания (ЕГКО)")
SOURCES["egko.roads"] = ("egko", {"dorogi_pol": None}, "Дороги (ЕГКО)")
SOURCES["egko.paths"] = ("egko", {"tropinki": None}, "Пешеходные дороги (ЕГКО)")
SOURCES["egko.green"] = ("egko", {"gazons": "газон", "forest": "растительность"}, "Газоны и растительность (ЕГКО)")
SOURCES["egko.water"] = ("egko", {"hidrograf": None}, "Водная поверхность (ЕГКО)")
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

# НСПД отдаёт тяжёлые ответы в плотной застройке, ОГД режется из кэша слоя
LIMIT_KM2 = {"gisogd_admin": 1e9, "nspd": 4.0, "osm": 25.0, "gisogd": 25.0, "egko": 25.0, "terrain": 60.0, "yandex": 4.0}

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
}
NUMERIC = {"Этажность", "Год постройки", "Площадь, м²", "Площадь участка, м²", "Кадастровая стоимость, ₽",
           "Подземных этажей", "Год ввода", "Площадь уточнённая, м²", "Высота, м", "Длина, м", "Уровень"}


def bbox_km2(b):
    w, s, e, n = b
    return abs(e - w) * 111.32 * math.cos(math.radians((s + n) / 2)) * abs(n - s) * 110.54


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
           "egko.addresses": egko_address_props,
           "yandex.hd_roads": _renamed({"type": "Тип", "struct": "Конструкция", "z_level": "Уровень"}),
           "yandex.buildings": _renamed({"height": "Высота, м", "ft_type_name": "Назначение"})}
for _k in SOURCES:
    if _k.startswith("yandex.") and _k not in PRESENT:
        PRESENT[_k] = dict              # без переименования; поле LineCode у Яндекса не бывает


REDLN = json.loads((STYLES / "redln97.json").read_text("utf-8"))
REDLN_IDX = acad_lin.lgr_index(REDLN["linetypes"])
_LGR = json.loads((STYLES / "moscow_lgr.json").read_text("utf-8"))["styles"].values()
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


MAX_BODY = 1536 * 2**20     # тело запроса: проект со 100 000 объектов ~100 МБ, импорт — несколько файлов в base64
PROGRESS = {}        # ключ источника → ход первой выгрузки слоя ГИС ОГД / ЕГКО целиком (GET /api/progress)
OGD_JOB, OGD_LOCK = [], threading.Lock()   # «Всё из ГИС ОГД в DWG»: одна фоновая выгрузка за раз (ogd_all.py)
EGKO_TTL = 30 * 24 * 3600   # картооснова: газоны — 1,3 ГБ, еженедельно перекачивать незачем


_TILE_LOCK = threading.Lock()


def esri_tile(z, x, y):
    """Тайл спутника Esri World Imagery (JPEG) для листа: с диска (~/.grado2/cache/tiles/esri, 90 дней), иначе
    скачать по одному, с паузой 0,1 с — портал не долбим; неудача — пустое место, лист всё равно собирается."""
    import ssl
    import time
    import urllib.request
    path = CACHE / "tiles" / "esri" / f"{z}_{x}_{y}.jpg"
    if path.exists() and time.time() - path.stat().st_mtime < 90 * 86400:
        return path.read_bytes()
    url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    with _TILE_LOCK:
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "grado2/1.0 (planning sheets)"})
                with urllib.request.urlopen(req, timeout=20, context=ctx) as r:
                    data = r.read()
                if data[:2] != b"\xff\xd8":                 # не JPEG (заглушка или ошибка) — на лист не идёт и в кэш не пишется
                    return None
                atomic_write(path, data)
                time.sleep(.1)
                return data
            except OSError:
                time.sleep(1 + attempt)
    return None


def _point_in(g, x, y):
    """Точка внутри Polygon / MultiPolygon GeoJSON (чётно-нечётное правило по всем кольцам)."""
    if not g:
        return False
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"] if g["type"] == "MultiPolygon" else []
    inside = False
    for poly in polys:
        for ring in poly:
            for i in range(len(ring)):
                (x1, y1), (x2, y2) = ring[i - 1][:2], ring[i][:2]
                if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                    inside = not inside
    return inside


def fetch(bbox, keys):
    """Реальные слои по прямоугольнику WGS84. Возвращает (layers, errors)."""
    keys = [k for k in keys if k in SOURCES]
    area = bbox_km2(bbox)
    layers, errors = {}, {}
    for k in keys:
        lim = LIMIT_KM2[SOURCES[k][0]]
        if area > lim:
            errors[k] = f"область {area:.1f} км² больше допустимых {lim:g} км² для источника"
    keys = [k for k in keys if k not in errors]

    def run_osm():
        osm_keys = [k for k in keys if SOURCES[k][0] == "osm"]
        if not osm_keys:
            return
        res = OsmOverpass(cache_dir=CACHE / "osm").fetch(bbox, [SOURCES[k][1] for k in osm_keys])
        for k in osm_keys:
            part = [f for f in res["features"] if f["properties"].get("grado_set") == SOURCES[k][1]]
            layers[k] = _layer(k, {**res, "features": part})

    def run_nspd():                 # по очереди: у геопортала лимит частоты
        for k in (k for k in keys if SOURCES[k][0] == "nspd"):
            try:
                layers[k] = _layer(k, NspdDirect().fetch(bbox, SOURCES[k][1]))
            except ConnectorError as e:
                errors[k] = str(e)

    def run_gisogd(k):
        feats, notes, doc = [], [], None
        def tell(code, got, total, stage):
            PROGRESS[k] = {"title": SOURCES[k][2], "got": got, "total": total, "stage": stage}
        api = GisogdApi(cache_dir=CACHE / "gisogd", progress=tell)
        for code, zone in SOURCES[k][1].items():
            res = api.fetch(bbox, code)
            doc, notes = res["source_doc"], notes + res["notes"]
            for f in res["features"]:
                if zone:
                    f["_extra"] = {"Вид зоны": zone}
                feats.append(f)
        PROGRESS.pop(k, None)
        layers[k] = _layer(k, {"features": feats, "source_doc": doc, "notes": notes})

    def run_egko(ks):
        """ЕГКО — по очереди, один слой за другим: первая выгрузка газонов — 1,3 ГБ, портал не долбим параллельно."""
        for k in ks:
            feats, notes, doc = [], [], None
            def tell(code, got, total, stage, k=k):
                PROGRESS[k] = {"title": SOURCES[k][2], "got": got, "total": total, "stage": stage}
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

    def run_yandex(ks):
        """Все слои Яндекса одним проходом: тайлы качаются и разбираются один раз (3 потока, пауза, кэш на диске)."""
        def tell(got, total):
            for k in ks:
                PROGRESS[k] = {"title": SOURCES[k][2], "got": got, "total": total, "stage": "tiles"}
        try:
            res = YandexVmap(cache_dir=CACHE / "yandex", progress=tell).fetch(bbox, [n for k in ks for n in SOURCES[k][1]])
            for k in ks:
                part = [f for f in res["features"] if f["properties"].get("grado_layer") in SOURCES[k][1]]
                # вид слоя на карте берётся по первому объекту: площадные — первыми, затем линии, точки — последними
                part.sort(key=lambda f: ("Polygon" not in f["geometry"]["type"]) + (f["geometry"]["type"] == "Point"))
                layers[k] = _layer(k, {**res, "features": part})
        finally:
            for k in ks:
                PROGRESS.pop(k, None)

    def run_admin(k):
        """Все округа Москвы и районы округа, в котором лежит область: для листа «Месторасположение» нужна вся
        Москва, а не прямоугольник выгрузки. Слои портала качаются по одному (по одному слою на округ и на район)."""
        from grado_connectors.gisogd_api import catalog
        api, moscow, feats = GisogdApi(cache_dir=CACHE / "gisogd"), (36.8, 55.1, 38.0, 56.1), []
        cat = catalog()
        cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        home = None
        for it in (x for x in cat if str(x.get("code", "")).startswith("prefect_")):
            okr = it["name"]
            for f in api.fetch(moscow, it["code"])["features"]:
                f["_extra"] = {"Уровень": "округ", "Округ": okr, "Наименование": okr}
                feats.append(f)
                if home is None and _point_in(f.get("geometry"), cx, cy):
                    home = okr
        if home:
            for it in (x for x in cat if x.get("type") == "layer" and f"Районы {home} /" in str(x.get("path", ""))):
                for f in api.fetch(moscow, it["code"])["features"]:
                    f["_extra"] = {"Уровень": "район", "Округ": home, "Наименование": it["name"]}
                    feats.append(f)
        layers[k] = _layer(k, {"features": feats, "source_doc": "ГИС ОГД Москвы: административные округа и районы",
                               "notes": [] if home else ["область вне административных округов Москвы"]})

    def run_terrain(k):
        layers[k] = _layer(k, TerrainContours().fetch(bbox))

    by = lambda kind: [k for k in keys if SOURCES[k][0] == kind]
    jobs = [(by("osm"), run_osm), (by("nspd"), run_nspd)] + \
        [([k], lambda k=k: run_gisogd(k)) for k in by("gisogd")] + [([k], lambda k=k: run_terrain(k)) for k in by("terrain")] + \
        [([k], lambda k=k: run_admin(k)) for k in by("gisogd_admin")] + \
        ([(by("egko"), lambda: run_egko(by("egko")))] if by("egko") else []) + \
        ([(by("yandex"), lambda: run_yandex(by("yandex")))] if by("yandex") else [])
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        for job_keys, fut in [(ks, pool.submit(fn)) for ks, fn in jobs]:
            try:
                fut.result()
            except Exception as e:   # сеть/разбор: слой помечается ошибкой, остальные доезжают
                for k in job_keys:
                    PROGRESS.pop(k, None)
                    if k not in layers:
                        errors.setdefault(k, str(e) or type(e).__name__)
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
        k1=1.0, k2=0.9, tinao=0, territory_mode=1, unbuilt_share=25):
    """ТЭП по методике «Калькулятора 2.0» (Москва). Население, соцобъекты и машино-места — от новой застройки;
    СПП ИЖС и блокированных домов идёт в жилую с 50 м² квартир на жителя."""
    e = Engine.from_file(PRESET)
    e.set_inputs(terr_area=terr_ha, restrict_area=restrict_ha, spp_in=spp_new_m2 / 1000, ratio_zh=max(0.0, min(100.0, share * 100)),
                 spp_low_in=spp_low_m2 / 1000, nonres_part=max(0.0, min(100.0, float(nonres_part))), education_zone=2 if int(education_zone) == 2 else 1,
                 k1=k1, k2=k2, tinao=1 if tinao else 0, territory_mode=int(territory_mode) if int(territory_mode) in (1, 2, 3) else 1,
                 unbuilt_share=max(0.0, min(90.0, float(unbuilt_share))))
    return {"metrics": e.results(),
            "density_total": ((spp_new_m2 + spp_kept_m2) / 1000 / terr_ha) if terr_ha else 0.0}


def _norm_name(t):
    t = str(t or "").lower().replace("ё", "е")
    for w in ("муниципальный округ", "поселение", "район", "городской округ", "город"):
        t = t.replace(w, "")
    # порядок слов не важен: у OSM «Северное Бутово», в таблицах 945-ПП «Бутово Северное»
    return " ".join(sorted(t.replace("-", " ").split()))


def _in_ring(x, y, ring):
    c = False
    for i in range(len(ring)):
        (x1, y1), (x2, y2) = ring[i], ring[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


_PLACE_MEMO = {}


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


def place_info(lon, lat):
    """Территориальные параметры ТЭП по точке (как маркер «Калькулятора 2.0»): район и округ по OSM, образовательная
    зона (2151-ПП), K2 (945-ПП прил. 3 с границей ТТК), ТиНАО, K1 по расстоянию до ближайшего входа или станции
    метро, МЦК, МЦД. K1 — приближение: прямое расстояние × 1,3 вместо пешеходной изохроны."""
    import math
    key = (round(lon, 3), round(lat, 3))
    if key in _PLACE_MEMO:
        return _PLACE_MEMO[key]
    cache = CACHE / "place" / f"{key[0]}_{key[1]}.json"
    raw = None
    if _fresh(cache):
        try:
            raw = json.loads(cache.read_text("utf-8"))
        except ValueError:
            cache.unlink(missing_ok=True)
    if raw is None:
        q = (f"[out:json][timeout:25];is_in({lat},{lon})->.a;area.a[\"boundary\"=\"administrative\"][\"admin_level\"~\"^(5|8)$\"];out tags;"
             f"(node(around:3000,{lat},{lon})[\"railway\"=\"subway_entrance\"];node(around:3000,{lat},{lon})[\"railway\"~\"^(station|halt)$\"];);out;")
        raw = OsmOverpass()._http_post(q)
        atomic_write(cache, json.dumps(raw, ensure_ascii=False).encode("utf-8"))
    areas = [e.get("tags", {}) for e in raw.get("elements", []) if e.get("type") == "area"]
    okrug = next((a.get("name") for a in areas if a.get("admin_level") == "5"), "")
    dname = next((a.get("name") for a in areas if a.get("admin_level") == "8"), "")
    tinao = int(any(w in (okrug or "") for w in ("Троицк", "Новомосковск")))
    table = {_norm_name(k): k for k in DISTRICTS["k2"]}
    district = table.get(_norm_name(dname))
    inside_ttk = _in_ring(lon, lat, DISTRICTS["ttk_hull"])
    notes = []
    if district:
        k2row = DISTRICTS["k2"][district]
        k2 = (k2row.get("inside_ttk") if inside_ttk else k2row.get("outside_ttk")) if "inside_ttk" in k2row else \
             (k2row["exclave"] if "exclave" in k2row and lon < 37.33 else k2row["value"])
        zone = 2 if _norm_name(district) in {_norm_name(z) for z in DISTRICTS["zone2"]} else 1
    else:
        k2, zone = (0.9, 2 if tinao else 1)
        notes.append(f"район «{dname or 'не определён'}» не найден в таблицах 945-ПП и 2151-ПП — K2 и зона приняты {k2} и {zone}, поправьте вручную")
    # ближайший вход или станция рельсового каркаса
    rail = _rail_nodes(raw)
    kx = 111320 * math.cos(math.radians(lat))
    dist = min((math.hypot((e["lon"] - lon) * kx, (e["lat"] - lat) * 110540) for e in rail), default=None)
    walk = dist * 1.3 if dist is not None else None
    k1 = 0.75 if walk is not None and walk < 1200 else 0.9 if walk is not None and walk <= 2200 else 1.0
    out = {"district": district or dname, "known": bool(district), "okrug": okrug, "tinao": tinao, "inside_ttk": inside_ttk,
           "zone": zone, "k2": k2, "k1": k1, "rail_walk_m": round(walk) if walk is not None else None, "notes": notes}
    _PLACE_MEMO[key] = out
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


def save_project(name, body):
    json.loads(body)                                  # в файл идёт только целый JSON
    path = project_path(name)
    with _SAVE_LOCK:                                  # два сохранения подряд — по очереди, последний побеждает целиком
        atomic_write(path, body)
    return path


def list_projects():
    files = sorted(PROJECTS.glob("*.grado2"), key=lambda p: p.stat().st_mtime, reverse=True) if PROJECTS.exists() else []
    info = lambda p: {"name": p.stem, "modified": p.stat().st_mtime, "size": p.stat().st_size}
    auto = [info(p) for p in files if p.stem == AUTOSAVE]
    return {"dir": str(PROJECTS), "projects": [info(p) for p in files if p.stem != AUTOSAVE], "autosave": auto[0] if auto else None}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")   # после обновления браузер не держит старые app.js
        super().end_headers()

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self._foreign():
            return self._deny()
        name = self.path.split("?")[0].removeprefix("/styles/")
        if self.path.startswith("/styles/") and name in STYLE_FILES:
            body = (STYLES / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if self.path == "/api/sources":
            return self._json(200, {k: {"title": v[2], "kind": v[0]} for k, v in SOURCES.items()})
        if self.path == "/api/health":
            return self._json(200, {"pid": os.getpid(), "stamp": STAMP, "version": VERSION})
        if self.path == "/api/progress":
            return self._json(200, dict(PROGRESS))
        if self.path == "/api/ogd_all/status":
            return self._json(200, OGD_JOB[0].state if OGD_JOB else {"running": False})
        if self.path == "/api/ogd_all/file":
            job = OGD_JOB[0] if OGD_JOB else None
            if not job or not job.file or not job.file.exists():
                return self._json(404, {"error": "no file"})
            body = job.file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            from urllib.parse import quote       # имя с названием листа — по-русски; заголовок HTTP — только латиница
            self.send_header("Content-Disposition", f"attachment; filename=\"gisogd.zip\"; filename*=UTF-8''{quote(job.file.name)}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if self.path.startswith("/api/fgistp/"):
            q = parse_qs(urlparse(self.path).query)
            try:
                if self.path.startswith("/api/fgistp/docs"):
                    if q.get("q", [""])[0].strip():
                        return self._json(200, {"docs": fgistp_search(q["q"][0], fgistp_catalog())})
                    bbox = [float(v) for v in q["bbox"][0].split(",")]
                    return self._json(200, {"docs": fgistp_docs(bbox, fgistp_catalog())})
                if self.path.startswith("/api/fgistp/layers"):
                    return self._json(200, {"layers": FgistpConnector().discover(q["uin"][0])})
            except ConnectorError as e:
                return self._json(502, {"error": str(e)})
            except (KeyError, ValueError) as e:
                return self._json(400, {"error": _bad(e)})
            except Exception as e:      # любой сбой — ответ с причиной, а не оборванное соединение
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})
            except OSError as e:
                return self._json(502, {"error": f"ФГИС ТП недоступна: {e}"})
        if self.path == "/api/projects":
            return self._json(200, list_projects())
        if self.path.startswith("/api/project?"):
            try:
                path = project_path(self._project_name())
                body = path.read_bytes()
            except (ValueError, OSError):
                return self._json(404, {"error": "no such project"})
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        return super().do_GET()

    def _foreign(self):
        """Запрос не от самой программы: чужой адрес в Host (подмена DNS на 127.0.0.1) или страница другого сайта
        (Origin). Такой сайт мог бы молча перезаписать проект обычной формой — сервер ему не отвечает."""
        port = self.server.server_address[1]
        ok = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        if (self.headers.get("Host") or "") not in ok:
            return True
        origin = self.headers.get("Origin")
        return origin is not None and origin not in {"http://" + h for h in ok}

    def _deny(self):
        self.send_response(403)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", "9")
        self.end_headers()
        self.wfile.write(b"forbidden")

    def _project_name(self):
        q = parse_qs(urlparse(self.path).query)
        return AUTOSAVE if q.get("autosave") else (q.get("name") or [""])[0]

    def do_HEAD(self):
        if self._foreign():
            return self._deny()
        return super().do_HEAD()

    def do_POST(self):
        if self._foreign():
            return self._deny()
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if not 0 <= n <= MAX_BODY:
                return self._json(413, {"error": f"запрос больше {MAX_BODY // 2**20} МБ"})
            if self.path == "/api/import/files":
                import base64
                import file_io
                req = json.loads(self.rfile.read(n) or b"{}")
                files = {f["name"]: base64.b64decode(f["b64"]) for f in req.get("files") or []}
                return self._json(200, {"layers": file_io.import_files(files, REDLN, req.get("local") or "msk")})
            if self.path.split("?")[0] == "/api/import/dxf":
                import dxf_io
                fc, notes = dxf_io.import_dxf(self.rfile.read(n), REDLN, "ogd" if "local=ogd" in self.path else "msk")
                return self._json(200, {"features": fc, "notes": notes})
            if self.path.startswith("/api/project?"):
                path = save_project(self._project_name(), self.rfile.read(n))
                return self._json(200, {"saved": str(path), "modified": path.stat().st_mtime})
            req = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/fetch":
                bbox = [float(v) for v in req["bbox"]]
                if len(bbox) != 4 or not (-180 <= bbox[0] < bbox[2] <= 180 and -90 <= bbox[1] < bbox[3] <= 90):
                    return self._json(400, {"error": "bbox: ожидается [запад, юг, восток, север] в градусах"})
                layers, errors = fetch(bbox, list(req.get("sources") or []))
                return self._json(200, {"layers": layers, "errors": errors})
            if self.path == "/api/print/pdf":
                import print_io
                body = print_io.render_pdf(req, REDLN, LGR_DASH, esri_tile)
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", 'attachment; filename="grado2-album.pdf"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            if self.path == "/api/print/svg":
                import print_io
                body = print_io.render_preview_svg(req, REDLN, LGR_DASH, int(req.get("index", 0)), esri_tile).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            if self.path == "/api/ogd_all/start":
                import ogd_all
                sheet = req.get("sheet")                  # лист, нарисованный на карте (МСК), или прежний bbox WGS84
                bbox = ogd_all.sheet_bbox_wgs(sheet) if sheet else [float(v) for v in req["bbox"]]
                if len(bbox) != 4 or not (-180 <= bbox[0] < bbox[2] <= 180 and -90 <= bbox[1] < bbox[3] <= 90):
                    return self._json(400, {"error": "bbox: ожидается [запад, юг, восток, север] в градусах"})
                if bbox_km2(bbox) > LIMIT_KM2["gisogd"]:
                    return self._json(400, {"error": f"область больше {LIMIT_KM2['gisogd']:g} км²"})
                with OGD_LOCK:
                    if OGD_JOB and OGD_JOB[0].state["running"]:
                        return self._json(409, {"error": "выгрузка уже идёт"})
                    OGD_JOB[:] = [ogd_all.Job(bbox, req.get("boundary"), CACHE / "gisogd", CACHE / "ogd_all",
                                               str(req.get("name") or "gisogd"), sheet=sheet,
                                               styles=ogd_all.portal_styles(CACHE / "gisogd"))]
                return self._json(200, OGD_JOB[0].state)
            if self.path == "/api/ogd_all/cancel":
                if OGD_JOB:
                    OGD_JOB[0].cancel.set()
                return self._json(200, {"ok": True})
            if self.path == "/api/export/dxf":
                import dxf_io
                body = dxf_io.export_dxf(req["layers"], REDLN, LGR_COLORS)
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", 'attachment; filename="grado2-dxf.zip"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            if self.path == "/api/fgistp/fetch":
                bbox = [float(v) for v in req["bbox"]]
                try:
                    return self._json(200, {"layers": fgistp_fetch(str(req["uin"]), set(req["classids"]), bbox)})
                except ConnectorError as e:
                    return self._json(502, {"error": str(e)})
            if self.path == "/api/tep":
                f = {k: float(req[k]) for k in ("terr_ha", "restrict_ha", "spp_new_m2", "share", "spp_kept_m2", "spp_low_m2", "nonres_part",
                                                "education_zone", "k1", "k2", "tinao", "territory_mode", "unbuilt_share") if req.get(k) is not None}
                return self._json(200, tep(**f))
            if self.path == "/api/place":
                try:
                    return self._json(200, place_info(float(req["lon"]), float(req["lat"])))
                except ConnectorError as e:
                    return self._json(502, {"error": str(e)})
            if self.path == "/api/rail_route":
                try:
                    return self._json(200, rail_route(float(req["lon"]), float(req["lat"])) or {})
                except ConnectorError as e:
                    return self._json(502, {"error": str(e)})
            return self._json(404, {"error": "no such method"})
        except (KeyError, ValueError, TypeError) as e:
            return self._json(400, {"error": _bad(e)})
        except Exception as e:      # битый DXF и т.п.: ответ с причиной, а не оборванное соединение
            return self._json(422, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):     # тише: только ошибки
        if len(args) > 1 and str(args[1])[:1] in "45":
            super().log_message(fmt, *args)


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


STAMP = code_stamp()          # версия кода, с которой этот процесс запущен
VERSION = json.loads((WEB / "version.json").read_text("utf-8"))["version"]


def _running(port):
    """Сведения о ГРАДО 2 на порту: {"pid", "stamp"}; {} — ГРАДО, но старый, без /api/health; None — не ГРАДО."""
    import urllib.request
    if not _is_grado(port):
        return None
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def _is_grado(port):
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/sources", timeout=1) as r:
            return "nspd.parcels" in json.loads(r.read())
    except Exception:
        return False



class Server(ThreadingHTTPServer):
    # The browser opens about fifteen script and data requests at once on start. The default listen queue of 5
    # dropped some of them (connection refused), and the page came up without app.js or layers.js now and then.
    request_queue_size = 128
    daemon_threads = True

def main(argv=None):
    """Запуск: свободный порт от 8650, прежняя версия на порту заменяется, окно браузера открывается само."""
    argv = sys.argv[1:] if argv is None else argv
    import webbrowser
    port = int(argv[0]) if argv else int(os.environ.get("GRADO2_PORT") or 8650)
    import signal
    import time
    for p in range(port, port + 20):
        try:
            server = Server(("127.0.0.1", p), Handler)
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
            os.kill(info["pid"], signal.SIGTERM)
            for _ in range(30):                           # ждём, пока порт освободится
                time.sleep(0.1)
                try:
                    server = Server(("127.0.0.1", p), Handler)
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
