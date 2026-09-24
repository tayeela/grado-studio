"""Import of vector files for ГРАДО 2: GeoJSON, KML/KMZ, Shapefile (a set of files or a zip), DXF.

Every format ends as GeoJSON FeatureCollections in WGS84 degrees, one per source layer.
Coordinates are recognised by their size: degrees (WGS84), Web Mercator metres (EPSG:3857,
millions), or Moscow local metres (tens of km) — the same rule as the DXF import. Local metres are МСК (as the owner's
QGIS «МСК») unless the user chose «ГИС ОГД» for the import, or a Shapefile's .prj says Moscow_bessel (the ГИС ОГД system:
МСК + (16.098; 14.512)). A .prj also decides between degrees and Web Mercator.
"""

import io
import re
import json
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from grado_connectors import crs
from grado_connectors.shp_reader import read_shp

VECTOR = {".geojson", ".json", ".kml", ".kmz", ".shp", ".dxf", ".zip"}
# местные метры: МСК (как в QGIS) — по умолчанию; система ГИС ОГД — выгрузки портала и DXF ГРАДО 2 до v0.32
LOCAL = {"msk": (crs.msk_to_wgs84, "МСК (как в QGIS)"), "ogd": (crs.msk50_to_wgs84, "система ГИС ОГД (Бессель со смещением)")}


def _walk(coords, fn):
    if coords and isinstance(coords[0], (int, float)):
        return list(fn(*coords[:2]))
    return [_walk(c, fn) for c in coords]


def _pts(fc):
    out = []

    def take(c):
        if c and isinstance(c[0], (int, float)):
            out.append(c[:2])
        else:
            for x in c:
                take(x)
                if len(out) > 2000:
                    return
    for f in fc["features"]:
        if f.get("geometry"):
            take(f["geometry"].get("coordinates") or [])
        if len(out) > 2000:
            break
    return out


def _explode(fc):
    """GeometryCollection (допустимый GeoJSON, но не слой ГИС) → отдельные объекты с теми же атрибутами."""
    out = []
    for f in fc.get("features") or []:
        g = f.get("geometry") or {}
        if g.get("type") == "GeometryCollection":
            out += [{**f, "geometry": x} for x in g.get("geometries") or [] if x and x.get("coordinates")]
        else:
            out.append(f)
    fc["features"] = out
    return fc


def system_of(pts):
    """Система по самим координатам. Градусы — только если и x в ±180, и y в ±90: у местной московской системы
    восточная координата у осевого меридиана тоже бывает меньше 180 (37,5° в.д. — это x ≈ 115 м)."""
    big = max(max(abs(x), abs(y)) for x, y in pts)
    if all(abs(x) <= 180 and abs(y) <= 90 for x, y in pts):
        return "wgs"
    return "merc" if big > 1_000_000 else "local" if big <= 200_000 else None


def to_wgs84(fc, hint=None, local="msk"):
    """FeatureCollection in any of the systems → WGS84; returns (fc, system name). hint "ogd" — .prj Moscow_bessel."""
    pts = _pts(_explode(fc))
    if not pts:
        return fc, "нет координат"
    kind = hint or system_of(pts)
    if kind == "merc" and not hint:
        # без сведений о системе метры в миллионах — это Web Mercator только если точки попадают в Россию;
        # UTM и Гаусс–Крюгер тоже дают миллионы, но при чтении как Mercator уезжают за тысячи километров
        ll = [crs.merc_to_wgs84(x, y) for x, y in pts[:200]]
        if not all(19 <= lon <= 180 and 41 <= lat <= 82 for lon, lat in ll):
            raise ValueError("координаты в метрах, но не Web Mercator и не местная московская система "
                             "(похоже на UTM или Гаусс–Крюгер) — пересохраните слой в WGS84 или МСК")
    if kind is None:
        raise ValueError("координаты не похожи ни на градусы WGS84, ни на местные московские метры (десятки км), ни на Web Mercator")
    if kind == "local":
        kind = local
    fn = {"wgs": lambda x, y: (x, y), "merc": crs.merc_to_wgs84, "msk": LOCAL["msk"][0], "ogd": LOCAL["ogd"][0]}[kind]
    if fn:
        for f in fc["features"]:
            if (f.get("geometry") or {}).get("coordinates"):
                f["geometry"]["coordinates"] = _walk(f["geometry"]["coordinates"], fn)
    return fc, {"wgs": "WGS84", "merc": "Web Mercator (EPSG:3857)", "msk": LOCAL["msk"][1], "ogd": LOCAL["ogd"][1]}[kind]


def _clean(props):
    return {str(k): v for k, v in (props or {}).items() if v not in (None, "")}


def read_geojson(data):
    obj = json.loads(data.decode("utf-8-sig"))
    if not isinstance(obj, dict):
        raise ValueError("это не GeoJSON: нет FeatureCollection")
    code = str(((obj.get("crs") or {}).get("properties") or {}).get("name") or "")
    num = re.search(r"(\d+)\s*$", code)
    if num and "CRS84" not in code.upper() and num.group(1) not in ("4326", "3857", "900913", "3395"):
        raise ValueError(f"система координат файла ({code}) не поддерживается — пересохраните слой в WGS84 или МСК")
    if obj.get("type") == "Feature":
        obj = {"type": "FeatureCollection", "features": [obj]}
    elif obj.get("type") in ("Polygon", "MultiPolygon", "LineString", "MultiLineString", "Point", "MultiPoint"):
        obj = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": obj, "properties": {}}]}
    if obj.get("type") != "FeatureCollection":
        raise ValueError("это не GeoJSON: нет FeatureCollection")
    feats = [{"type": "Feature", "geometry": f.get("geometry"), "properties": _clean(f.get("properties"))}
             for f in obj.get("features") or [] if f.get("geometry")]
    return {"type": "FeatureCollection", "features": feats}


def _kml_coords(text):
    pts = []
    for tok in (text or "").split():
        parts = tok.split(",")
        if len(parts) >= 2:
            pts.append([float(parts[0]), float(parts[1])])
    return pts


def _kml_geoms(el, ns):
    out = []
    for g in el.iter():
        tag = g.tag.split("}")[-1]
        if tag == "Point":
            c = _kml_coords(g.findtext(f"{ns}coordinates"))
            if c:
                out.append({"type": "Point", "coordinates": c[0]})
        elif tag == "LineString":
            c = _kml_coords(g.findtext(f"{ns}coordinates"))
            if len(c) > 1:
                out.append({"type": "LineString", "coordinates": c})
        elif tag == "Polygon":
            outer = g.find(f"{ns}outerBoundaryIs/{ns}LinearRing/{ns}coordinates")
            inner = g.findall(f"{ns}innerBoundaryIs/{ns}LinearRing/{ns}coordinates")
            rings = [_kml_coords(outer.text if outer is not None else "")] + [_kml_coords(i.text) for i in inner]
            if len(rings[0]) > 2:
                out.append({"type": "Polygon", "coordinates": rings})
    return out


def read_kml(data):
    root = ET.fromstring(data)
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
    feats = []
    for pm in root.iter(f"{ns}Placemark"):
        props = {}
        if pm.findtext(f"{ns}name"):
            props["Название"] = pm.findtext(f"{ns}name").strip()
        if pm.findtext(f"{ns}description"):
            props["Описание"] = pm.findtext(f"{ns}description").strip()[:500]
        for d in pm.iter(f"{ns}Data"):
            props[d.get("name")] = d.findtext(f"{ns}value")
        for d in pm.iter(f"{ns}SimpleData"):
            props[d.get("name")] = d.text
        geoms = _kml_geoms(pm, ns)
        geom = geoms[0] if len(geoms) == 1 else {"type": "GeometryCollection", "geometries": geoms} if geoms else None
        if geom and geom["type"] == "GeometryCollection":           # несколько частей одного типа — мульти-геометрия
            kinds = {g["type"] for g in geoms}
            if len(kinds) == 1:
                geom = {"type": "Multi" + geoms[0]["type"], "coordinates": [g["coordinates"] for g in geoms]}
            else:
                for g in geoms:
                    feats.append({"type": "Feature", "geometry": g, "properties": _clean(props)})
                continue
        if geom:
            feats.append({"type": "Feature", "geometry": geom, "properties": _clean(props)})
    return {"type": "FeatureCollection", "features": feats}


def _prj_hint(text):
    t = (text or "").upper()
    if not t:
        return None
    if "MERCATOR" in t and ("PSEUDO" in t or "AUXILIARY" in t or "3857" in t):
        return "merc"
    if t.startswith("GEOGCS"):
        return "wgs"
    if "MOSCOW_BESSEL" in t:
        return "ogd"                # выгрузка ГИС ОГД: родные координаты портала
    # местная московская система (МСК из QGIS владельца): осевой меридиан 37,5°, начало широт 55°40′ —
    # решает выбор «Файлы в метрах». Любая другая проекция (UTM, Гаусс–Крюгер, МСК-50) не поддерживается:
    # прочитать её как Web Mercator значило бы молча унести слой во Францию или Казахстан
    par = dict(re.findall(r'PARAMETER\["([A-Z_]+)",\s*(-?[\d.]+)', t))
    try:
        cm, lat0 = float(par.get("CENTRAL_MERIDIAN", "nan")), float(par.get("LATITUDE_OF_ORIGIN", "nan"))
    except ValueError:
        cm = lat0 = float("nan")
    if t.startswith("PROJCS") and not (abs(cm - 37.5) < 1e-6 and abs(lat0 - 55.6666667) < 1e-4):
        name = re.match(r'PROJCS\["([^"]*)"', t)
        raise ValueError(f"система координат файла «{name.group(1) if name else 'неизвестная'}» не поддерживается — "
                         "пересохраните слой в WGS84 или МСК")
    return None


def read_shp_set(files):
    """{name: bytes} of one Shapefile (.shp, .dbf, .prj, .cpg, …) → FeatureCollection."""
    with tempfile.TemporaryDirectory() as td:
        for name, b in files.items():                  # расширение в нижний регистр: ROADS.SHP из старых выгрузок
            (Path(td) / (Path(name).stem + Path(name).suffix.lower())).write_bytes(b)
        shp = next(Path(td).glob("*.shp"))
        rows = read_shp(shp)
        prj = shp.with_suffix(".prj")
        hint = _prj_hint(prj.read_text("latin-1", "replace")) if prj.exists() else None
    fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": r["geometry"], "properties": _clean(r["properties"])}
                                                    for r in rows if r["geometry"]]}
    return fc, hint


MAX_UNPACKED = 1024 * 2**20        # 1 ГБ распакованного: слой ПЗЗ Москвы целиком — 221 МБ


def _check_unpacked(name, packed, members):
    """Архив-бомба (сотни КБ, распаковываются в гигабайты) не должна съесть память: проверка по заявленным размерам,
    а zipfile сам остановит член архива, чьё содержимое длиннее заявленного."""
    total = sum(i.file_size for i in members)
    if total > MAX_UNPACKED or (total > 50 * 2**20 and total > packed * 200):
        raise ValueError(f"архив «{name}» распаковывается в {total / 2**20:.0f} МБ — это больше допустимого; "
                         "распакуйте нужные слои и перетащите их отдельно")


def import_files(files, redln=None, local="msk"):
    """files: {file name: bytes} (one drop or one «Открыть» of the file dialog). local: how to read local metres of
    files without a .prj that names the system — "msk" (МСК, как в QGIS; default) or "ogd" (система ГИС ОГД).
    Returns [{"name", "features": FeatureCollection WGS84, "notes": [...]}], one entry per source layer."""
    local = local if local in LOCAL else "msk"
    expanded = {}
    for name, b in files.items():
        suf = Path(name).suffix.lower()
        if suf == ".zip":
            with zipfile.ZipFile(io.BytesIO(b)) as z:
                members = [i for i in z.infolist() if not i.is_dir() and not Path(i.filename).name.startswith(".")]
                _check_unpacked(name, len(b), members)
                for i in members:
                    fname = i.filename
                    if not i.flag_bits & 0x800:               # имя без флага UTF-8: Finder пишет UTF-8, русская Windows — cp866
                        raw = fname.encode("cp437", "replace")
                        try:
                            fname = raw.decode("utf-8")
                        except UnicodeDecodeError:
                            fname = raw.decode("cp866", "replace")
                    expanded[fname] = z.read(i)
        elif suf == ".kmz":
            with zipfile.ZipFile(io.BytesIO(b)) as z:
                kml = next((i for i in z.infolist() if i.filename.lower().endswith(".kml")), None)
                if kml:
                    _check_unpacked(name, len(b), [kml])
                    expanded[Path(name).stem + ".kml"] = z.read(kml)
        else:
            expanded[name] = b
    out, shp_sets, skipped = [], {}, []
    for name, b in expanded.items():
        p, suf = Path(name), Path(name).suffix.lower()
        if suf in (".shp", ".dbf", ".prj", ".cpg", ".shx"):
            shp_sets.setdefault(str(p.with_suffix("")), {})[p.name] = b
            continue
        hint = None
        if suf in (".geojson", ".json"):
            try:
                fc = read_geojson(b)
            except (ValueError, AttributeError):
                if len(expanded) == 1:
                    raise
                skipped.append(p.name)                # metadata.json рядом со слоями не мешает остальным
                continue
        elif suf == ".kml":
            fc, hint = read_kml(b), "wgs"                 # KML всегда в градусах
        elif suf in (".dxf", ".dwg"):
            import dxf_io
            dxf = dxf_io.oda_convert(b, "dwg", "DXF") if suf == ".dwg" else b     # DWG — через ODA File Converter
            fc, notes = dxf_io.import_dxf(dxf, redln, local)
            out.append({"name": p.stem, "format": suf.lstrip(".").upper(), "features": fc, "notes": notes, "_dir": p.parent.name})
            continue
        else:
            continue
        fc, system = to_wgs84(fc, hint, local)
        out.append({"name": p.stem, "_dir": p.parent.name, "format": suf.lstrip(".").upper(), "features": fc,
                    "notes": [f"координаты: {system}; объектов {len(fc['features'])}"]})
    for stem, group in shp_sets.items():
        if not any(n.lower().endswith(".shp") for n in group):
            continue
        fc, hint = read_shp_set(group)
        fc, system = to_wgs84(fc, hint, local)
        notes = [f"координаты: {system}; объектов {len(fc['features'])}"]
        if not any(n.lower().endswith(".dbf") for n in group):
            notes.append("нет файла .dbf — атрибутов нет")
        out.append({"name": Path(stem).name, "_dir": Path(stem).parent.name, "format": "SHP", "features": fc, "notes": notes})
    if skipped and out:
        out[0]["notes"].append("не GeoJSON, пропущено: " + ", ".join(skipped))
    # одинаковые имена слоёв из разных папок: к имени добавляется папка, иначе второй слой затёр бы первый
    count = {}
    for o in out:
        count[o["name"]] = count.get(o["name"], 0) + 1
    used = set()
    for o in out:
        folder = o.pop("_dir", "")
        name = f"{folder}/{o['name']}" if count[o["name"]] > 1 and folder else o["name"]
        base, k = name, 2
        while name in used:
            name, k = f"{base} ({k})", k + 1
        used.add(name)
        o["name"] = name
    if not out:
        raise ValueError("нет векторных данных: ожидаются GeoJSON, KML/KMZ, Shapefile (.shp с .dbf или zip), DXF или DWG")
    return out
