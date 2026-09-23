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
from grado_render import acad_lin                                  # noqa: E402

WEB = ROOT / "web" if FROZEN else Path(__file__).resolve().parent / "web"
CACHE = Path.home() / ".grado2" / "cache"
PRESET = ROOT / "core/compute/grado_compute/presets/moscow_krt.json"
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

# НСПД отдаёт тяжёлые ответы в плотной застройке, ОГД режется из кэша слоя
LIMIT_KM2 = {"nspd": 4.0, "osm": 25.0, "gisogd": 25.0, "terrain": 60.0}

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
           "Подземных этажей", "Год ввода", "Площадь уточнённая, м²"}


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


# ключ источника → свойства портала в читаемые поля (служебные поля портала не нужны в таблице)
PRESENT = {"gisogd.pzz_sub": pzz_sub_props, "gisogd.pzz_zones": pzz_zone_props, "gisogd.okn": okn_props,
           "gisogd.demolition": demolition_props, "relief.contours": lambda p: {"Высота, м": p.get("elev")},
           "osm.social": social_props}


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
                             **({"_key": f["grado_key"]} if f.get("grado_key") else {})}}
             for f in result["features"] if f.get("geometry")]
    return {"title": SOURCES[key][2], "source": result.get("source_doc"),
            "fetched_at": date.today().isoformat(), "notes": result.get("notes", []),
            "features": {"type": "FeatureCollection", "features": feats}}


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
        res = OsmOverpass().fetch(bbox, [SOURCES[k][1] for k in osm_keys])
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
        api = GisogdApi(cache_dir=CACHE / "gisogd")
        for code, zone in SOURCES[k][1].items():
            res = api.fetch(bbox, code)
            doc, notes = res["source_doc"], notes + res["notes"]
            for f in res["features"]:
                if zone:
                    f["_extra"] = {"Вид зоны": zone}
                feats.append(f)
        layers[k] = _layer(k, {"features": feats, "source_doc": doc, "notes": notes})

    def run_terrain(k):
        layers[k] = _layer(k, TerrainContours().fetch(bbox))

    by = lambda kind: [k for k in keys if SOURCES[k][0] == kind]
    jobs = [(by("osm"), run_osm), (by("nspd"), run_nspd)] + \
        [([k], lambda k=k: run_gisogd(k)) for k in by("gisogd")] + [([k], lambda k=k: run_terrain(k)) for k in by("terrain")]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        for job_keys, fut in [(ks, pool.submit(fn)) for ks, fn in jobs]:
            try:
                fut.result()
            except Exception as e:   # сеть/разбор: слой помечается ошибкой, остальные доезжают
                for k in job_keys:
                    if k not in layers:
                        errors.setdefault(k, str(e) or type(e).__name__)
    return layers, errors


# ---------- ФГИС ТП: документы территориального планирования (Минэкономразвития) ----------
FGISTP_TTL = 7 * 24 * 3600


def fgistp_catalog(conn=None):
    """Каталог документов РФ (~28 000, ~10 МБ) — с диска, раз в неделю обновляется."""
    import gzip
    import time
    path = CACHE / "fgistp" / "catalog.json.gz"
    if path.exists() and time.time() - path.stat().st_mtime < FGISTP_TTL:
        return json.loads(gzip.decompress(path.read_bytes()))
    cat = (conn or FgistpConnector()).catalog()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(cat, ensure_ascii=False).encode("utf-8")))
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


def tep(terr_ha, restrict_ha, spp_new_m2, share, spp_kept_m2=0.0):
    """ТЭП по пресету КРТ Москвы. Население и соцобъекты — только от новой застройки."""
    calc = max(terr_ha - restrict_ha, 0.0)
    e = Engine.from_file(PRESET)
    e.set_inputs(terr_area=terr_ha, restrict_area=restrict_ha,
                 density=(spp_new_m2 / 1000 / calc) if calc else 0.0,
                 ratio_zh=max(0.0, min(100.0, share * 100)))
    return {"metrics": e.results(),
            "density_total": ((spp_new_m2 + spp_kept_m2) / 1000 / terr_ha) if terr_ha else 0.0}


def project_path(name):
    """Имя проекта → файл в PROJECTS. Имя становится именем файла, поэтому без путей и служебных знаков."""
    name = (name or "").strip()
    if name == AUTOSAVE:
        return PROJECTS / f"{AUTOSAVE}.grado2"
    if not name or name.startswith(".") or len(name) > 120 or any(c in name for c in '/\\:*?"<>|\0'):
        raise ValueError("bad project name")
    return PROJECTS / f"{name}.grado2"


def save_project(name, body):
    json.loads(body)                                  # в файл идёт только целый JSON
    path = project_path(name)
    PROJECTS.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(body)
    os.replace(tmp, path)                             # атомарно: при сбое старая версия цела
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
        if self.path.startswith("/api/fgistp/"):
            q = parse_qs(urlparse(self.path).query)
            try:
                if self.path.startswith("/api/fgistp/docs"):
                    bbox = [float(v) for v in q["bbox"][0].split(",")]
                    return self._json(200, {"docs": fgistp_docs(bbox, fgistp_catalog())})
                if self.path.startswith("/api/fgistp/layers"):
                    return self._json(200, {"layers": FgistpConnector().discover(q["uin"][0])})
            except ConnectorError as e:
                return self._json(502, {"error": str(e)})
            except (KeyError, ValueError) as e:
                return self._json(400, {"error": f"bad request: {e}"})
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

    def _project_name(self):
        q = parse_qs(urlparse(self.path).query)
        return AUTOSAVE if q.get("autosave") else (q.get("name") or [""])[0]

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if self.path == "/api/import/files":
                import base64
                import file_io
                req = json.loads(self.rfile.read(n) or b"{}")
                files = {f["name"]: base64.b64decode(f["b64"]) for f in req.get("files") or []}
                return self._json(200, {"layers": file_io.import_files(files, REDLN)})
            if self.path == "/api/import/dxf":
                import dxf_io
                fc, notes = dxf_io.import_dxf(self.rfile.read(n), REDLN)
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
                body = print_io.render_pdf(req, REDLN, LGR_DASH)
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", 'attachment; filename="grado2-album.pdf"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            if self.path == "/api/print/svg":
                import print_io
                body = print_io.render_preview_svg(req, REDLN, LGR_DASH, int(req.get("index", 0))).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
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
                f = {k: float(req.get(k) or 0) for k in ("terr_ha", "restrict_ha", "spp_new_m2", "share", "spp_kept_m2")}
                return self._json(200, tep(**f))
            return self._json(404, {"error": "no such method"})
        except (KeyError, ValueError, TypeError) as e:
            return self._json(400, {"error": f"bad request: {e}"})
        except Exception as e:      # битый DXF и т.п.: ответ с причиной, а не оборванное соединение
            return self._json(422, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, fmt, *args):     # тише: только ошибки
        if len(args) > 1 and str(args[1])[:1] in "45":
            super().log_message(fmt, *args)


def code_stamp():
    """Версия серверного кода: время правки файлов бэкенда. Разная → запущенный сервер устарел и заменяется."""
    if FROZEN:
        return json.loads((WEB / "version.json").read_text("utf-8"))["version"]
    here = Path(__file__).resolve().parent
    return max(p.stat().st_mtime for p in here.glob("*.py"))


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


def main(argv=None):
    """Запуск: свободный порт от 8650, прежняя версия на порту заменяется, окно браузера открывается само."""
    argv = sys.argv[1:] if argv is None else argv
    import webbrowser
    port = int(argv[0]) if argv else int(os.environ.get("GRADO2_PORT") or 8650)
    import signal
    import time
    for p in range(port, port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), Handler)
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
                    server = ThreadingHTTPServer(("127.0.0.1", p), Handler)
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
