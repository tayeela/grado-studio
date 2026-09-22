"""ГРАДО 2: локальный сервер.

Отдаёт веб-интерфейс из web/ и два метода:
  POST /api/fetch  {bbox:[w,s,e,n], sources:[ключ,...]} → реальные слои по области
  POST /api/tep    {terr_ha, restrict_ha, spp_new_m2, share, spp_kept_m2} → ТЭП (методика КРТ)

Данные берутся коннекторами ядра (core/connectors), ТЭП — движком ядра (core/compute).
Геометрия на выходе всегда WGS84 (GeoJSON), без пересчёта в СК холста.

Запуск: python3 apps/grado2/server.py [порт]   (по умолчанию 8650)
"""

import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for sub in ("core/connectors", "core/compute", "core/render"):
    sys.path.insert(0, str(ROOT / sub))

from grado_compute import Engine                                   # noqa: E402
from grado_connectors.contract import ConnectorError               # noqa: E402
from grado_connectors.gisogd_api import GISOGD_API_LAYERS, GisogdApi  # noqa: E402
from grado_connectors.nspd import NspdDirect                       # noqa: E402
from grado_connectors.osm import OsmOverpass                       # noqa: E402
from grado_render import acad_lin                                  # noqa: E402

WEB = Path(__file__).resolve().parent / "web"
CACHE = Path.home() / ".grado2" / "cache"
PRESET = ROOT / "core/compute/grado_compute/presets/moscow_krt.json"
STYLES = ROOT / "core/render/grado_render/styles"
STYLE_FILES = {"redln97.json", "moscow_lgr.json", "moscow_genplan.json"}   # отдаются фронту как есть

# ключ → (коннектор, параметр, название слоя)
SOURCES = {
    "nspd.parcels": ("nspd", [36368], "Земельные участки (ЕГРН)"),
    "nspd.buildings": ("nspd", [36369], "Здания (ЕГРН)"),
    "nspd.zouit": ("nspd", [469038, 469039, 469040, 469041, 469042], "ЗОУИТ (ЕГРН)"),
    "osm.roads": ("osm", "roads", "Улично-дорожная сеть (OSM)"),
    "osm.buildings": ("osm", "buildings", "Здания (OSM)"),
    "osm.water": ("osm", "water", "Водные объекты (OSM)"),
    "osm.landuse": ("osm", "landuse", "Землепользование (OSM)"),
}
SOURCES["gisogd.red_lines"] = ("gisogd", {"l1": None}, "Красные линии и ЛГР (ОГД)")
for _k in ("gisogd.func_zones", "gisogd.func_zones_tinao", "gisogd.szz", "gisogd.vodookhr"):
    SOURCES[_k] = ("gisogd", GISOGD_API_LAYERS[_k]["codes"], GISOGD_API_LAYERS[_k]["title"])

# НСПД отдаёт тяжёлые ответы в плотной застройке, ОГД режется из кэша слоя
LIMIT_KM2 = {"nspd": 4.0, "osm": 25.0, "gisogd": 25.0}

# читаемые имена полей; остальные поля проходят как есть
LABELS = {
    "opt_cad_num": "Кадастровый номер", "opt_readable_address": "Адрес",
    "opt_permitted_use_established_by_document": "ВРИ", "opt_land_record_category_type": "Категория земель",
    "opt_land_record_area": "Площадь участка, м²", "opt_ownership_type": "Форма собственности",
    "opt_cost_value": "Кадастровая стоимость, ₽", "opt_floors": "Этажность", "opt_purpose": "Назначение",
    "opt_build_record_area": "Площадь, м²", "opt_materials": "Материал стен", "opt_year_built": "Год постройки",
    "opt_cultural_heritage_val": "ОКН", "opt_status": "Статус",
    "building:levels": "Этажность", "name": "Название", "highway": "Тип дороги", "building": "Тип здания",
    "landuse": "Землепользование", "leisure": "Отдых", "natural": "Природа", "waterway": "Водоток",
}
NUMERIC = {"Этажность", "Год постройки", "Площадь, м²", "Площадь участка, м²", "Кадастровая стоимость, ₽"}


def bbox_km2(b):
    w, s, e, n = b
    return abs(e - w) * 111.32 * math.cos(math.radians((s + n) / 2)) * abs(n - s) * 110.54


def clean_props(props, extra=None):
    out = {}
    for k, v in (props or {}).items():
        if k.startswith("grado_") or v in (None, ""):
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


REDLN = json.loads((STYLES / "redln97.json").read_text("utf-8"))
REDLN_IDX = acad_lin.lgr_index(REDLN["linetypes"])
LGR_COLORS = {int(v["lgr_code"]): v["stroke"] for v in json.loads((STYLES / "moscow_lgr.json").read_text("utf-8"))["styles"].values()
              if v.get("lgr_code") is not None and v.get("stroke")}


def linetype_props(props):
    """LineCode of ГИС ОГД → linetypes REDLN97 (_lt) and codes without one (_miss: [[code, sign]])."""
    code = next((v for k, v in (props or {}).items() if k.lower() in ("linelineco", "linecode")), None)
    pairs = acad_lin.parse_line_codes(code)
    if not pairs:
        return {}
    return {"LineCode": code, "_lt": acad_lin.linetypes_for_codes(pairs, REDLN["linetypes"], REDLN_IDX),
            "_miss": [list(p) for p in acad_lin.missing_codes(pairs, REDLN["linetypes"], REDLN_IDX)]}


def _layer(key, result):
    feats = [{"type": "Feature", "geometry": f["geometry"],
              "properties": {**clean_props(f.get("properties"), f.get("_extra")), **linetype_props(f.get("properties"))}}
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

    by = lambda kind: [k for k in keys if SOURCES[k][0] == kind]
    jobs = [(by("osm"), run_osm), (by("nspd"), run_nspd)] + \
        [([k], lambda k=k: run_gisogd(k)) for k in by("gisogd")]
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        for job_keys, fut in [(ks, pool.submit(fn)) for ks, fn in jobs]:
            try:
                fut.result()
            except Exception as e:   # сеть/разбор: слой помечается ошибкой, остальные доезжают
                for k in job_keys:
                    if k not in layers:
                        errors.setdefault(k, str(e) or type(e).__name__)
    return layers, errors


def tep(terr_ha, restrict_ha, spp_new_m2, share, spp_kept_m2=0.0):
    """ТЭП по пресету КРТ Москвы. Население и соцобъекты — только от новой застройки."""
    calc = max(terr_ha - restrict_ha, 0.0)
    e = Engine.from_file(PRESET)
    e.set_inputs(terr_area=terr_ha, restrict_area=restrict_ha,
                 density=(spp_new_m2 / 1000 / calc) if calc else 0.0,
                 ratio_zh=max(0.0, min(100.0, share * 100)))
    return {"metrics": e.results(),
            "density_total": ((spp_new_m2 + spp_kept_m2) / 1000 / terr_ha) if terr_ha else 0.0}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB), **kw)

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
        return super().do_GET()

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if self.path == "/api/import/dxf":
                import dxf_io
                fc, notes = dxf_io.import_dxf(self.rfile.read(n), REDLN)
                return self._json(200, {"features": fc, "notes": notes})
            req = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/fetch":
                bbox = [float(v) for v in req["bbox"]]
                if len(bbox) != 4 or not (-180 <= bbox[0] < bbox[2] <= 180 and -90 <= bbox[1] < bbox[3] <= 90):
                    return self._json(400, {"error": "bbox: ожидается [запад, юг, восток, север] в градусах"})
                layers, errors = fetch(bbox, list(req.get("sources") or []))
                return self._json(200, {"layers": layers, "errors": errors})
            if self.path == "/api/export/dxf":
                import dxf_io
                body = dxf_io.export_dxf(req["layers"], REDLN, LGR_COLORS)
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", 'attachment; filename="grado2-dxf.zip"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
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


def _is_grado(port):
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/sources", timeout=1) as r:
            return "nspd.parcels" in json.loads(r.read())
    except Exception:
        return False


if __name__ == "__main__":
    import webbrowser
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8650
    for p in range(port, port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            break
        except OSError:
            if _is_grado(p):            # уже запущен — просто открыть
                print(f"ГРАДО 2 уже работает: http://127.0.0.1:{p}")
                webbrowser.open(f"http://127.0.0.1:{p}")
                sys.exit(0)
    else:
        sys.exit(f"порты {port}–{port + 19} заняты")
    print(f"ГРАДО 2: http://127.0.0.1:{p}")
    webbrowser.open(f"http://127.0.0.1:{p}")
    server.serve_forever()
