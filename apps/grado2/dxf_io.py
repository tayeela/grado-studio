"""DXF export/import for ГРАДО 2 on ezdxf (MIT), with the Moscow red-line linetypes REDLN97.

Export: layers (GeoJSON WGS84) → DXF R2018 in МСК, the owner's QGIS «МСК» (metres; = ГИС ОГД system − (16.098; 14.512)).
Red lines get the REDLN97 complex linetypes; the shape file red_lns.shx goes into the
archive next to the drawing, as AutoCAD expects. Import: DXF in МСК (default), the ГИС ОГД system (DXF written by
ГРАДО 2 before v0.32) or WGS84 → GeoJSON;
REDLN97 linetype names become LineCode again.
"""

import io
import re
import sys
import zipfile
from pathlib import Path

import ezdxf

from grado_connectors import crs
from grado_render import acad_lin

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))   # собранная программа — папка распаковки
STANDARD = ROOT / "docs/standards/redln97"


def _pattern_string(lt, shapes):
    parts = ["A"]
    for e in lt["pattern"]:
        if "d" in e:
            parts.append(f"{e['d']:g}")
        elif "shape" in e:
            rot = f"a={e['r']:g}" if e.get("abs") else f"r={e['r']:g}"
            no = shapes[e["shape"].upper()]["no"]      # DXF stores the shape NUMBER from the .shx index
            parts.append(f"[{no},red_lns.shx,s={e['s']:g},{rot},x={e['x']:g},y={e['y']:g}]")
    return ",".join(parts)


def _add_linetype(doc, name, lt, shapes):
    if name in doc.linetypes:
        return
    doc.linetypes.add(name, pattern=_pattern_string(lt, shapes), description=lt["desc"][:60], length=lt["length"])


def _rings(geom):
    t, c = geom["type"], geom["coordinates"]
    if t == "Polygon":
        return [(r, True) for r in c]
    if t == "MultiPolygon":
        return [(r, True) for p in c for r in p]
    if t == "LineString":
        return [(c, False)]
    if t == "MultiLineString":
        return [(r, False) for r in c]
    return []


def export_dxf(layers, redln, lgr_colors):
    """layers: [{"name", "features": FeatureCollection, "color": "#rrggbb", "floors": bool}] → zip bytes."""
    doc = ezdxf.new("R2018", setup=False)
    doc.header["$INSUNITS"] = 6            # metres
    doc.header["$LTSCALE"] = 1.0
    doc.header.custom_vars.append("GRADO_CRS", "MSK")    # метка системы: при повторном импорте выбор не нужен
    doc.styles.add_shx("red_lns.shx")
    shapes = {k.upper(): v for k, v in redln["shapes"].items()}
    msp = doc.modelspace()
    for layer in layers:
        lname = re.sub(r'[<>/\\":;?*|=`]', "_", layer["name"])[:120]
        if lname not in doc.layers:
            doc.layers.add(lname, true_color=_rgb(layer.get("color", "#808080")))
        for f in layer["features"]["features"]:
            props = f.get("properties") or {}
            names = [n for n in props.get("_lt") or [] if n in redln["linetypes"]]
            for n in names:
                _add_linetype(doc, n, redln["linetypes"][n], shapes)
            for ring, closed in _rings(f["geometry"]):
                pts = [crs.wgs84_to_msk(x, y) for x, y in ring]
                if closed and len(pts) > 1 and pts[0] == pts[-1]:
                    pts = pts[:-1]
                attrs = {"layer": lname}
                floors = props.get("floors") or props.get("Этажность")
                if layer.get("floors") and isinstance(floors, (int, float)) and floors > 0:
                    attrs["thickness"] = floors * 3.0              # extrusion: storey 3 m
                for n in names or [None]:
                    a = dict(attrs)
                    if n:
                        a["linetype"] = n
                        code = _code_of(n)
                        if code in lgr_colors:
                            a["true_color"] = _rgb(lgr_colors[code])
                    msp.add_lwpolyline(pts, close=closed, dxfattribs=a)
    buf = io.StringIO()
    doc.write(buf)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("grado2.dxf", buf.getvalue().encode("utf-8"))
        z.write(STANDARD / "RED_LNS.SHX", "red_lns.shx")
        z.write(STANDARD / "REDLN97.LIN", "REDLN97.LIN")
        z.writestr("README.txt", ("Coordinates: MSK - Moscow local system as the QGIS custom CRS 'MSK' "
                                  "(+proj=tmerc +lat_0=55.66666666667 +lon_0=37.5 +k=1 +x_0=0 +y_0=0 +ellps=bessel), metres.\n"
                                  "Red lines use REDLN97 linetypes; keep red_lns.shx next to grado2.dxf.\n").encode())
    return out.getvalue()


def _rgb(hexcolor):
    h = hexcolor.lstrip("#")[:6]
    return ezdxf.rgb2int((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))


_PAIR = re.compile(r"^L(\d\d)([BT])(\d\d)([BT])$", re.I)


def _code_of(name):
    m = acad_lin.LGR_NAME.match(name)
    if m:
        return int(m.group(2))
    m = _PAIR.match(name)
    return int(m.group(1)) if m else None


def linecode_of(name):
    """REDLN97 linetype name → LineCode string of ГИС ОГД (inverse of linetypes_for_codes)."""
    sign = lambda s: "" if s.lower() in "bs" else "-"
    m = acad_lin.LGR_NAME.match(name)
    if m:
        carrier, code, side = int(m.group(1)), int(m.group(2)), m.group(3)
        return (f"{carrier}," if carrier else "") + f"{sign(side)}{code}"
    m = _PAIR.match(name)
    if m:
        return f"{sign(m.group(2))}{int(m.group(1))},{sign(m.group(4))}{int(m.group(3))}"
    return None


def written_system(doc, data=b""):
    """Система, в которой файл записал ГРАДО 2: "msk" (метка GRADO_CRS с v0.32), "ogd" (выгрузка ГРАДО 2 до v0.32 —
    ezdxf, стиль red_lns.shx, без метки) или None (чужой чертёж — решает выбор «Файлы в метрах»)."""
    mark = str(doc.header.custom_vars.get("GRADO_CRS") or "").upper()
    if mark in ("MSK", "OGD"):
        return mark.lower()
    # стиль-файл форм ezdxf при чтении в таблицу стилей не отдаёт — ищем его имя в самом файле
    by_grado = str(doc.header.get("$LASTSAVEDBY", "")).lower() == "ezdxf" and b"red_lns.shx" in data.lower()
    return "ogd" if by_grado else None


def import_dxf(data, redln, local="msk"):
    """DXF bytes → (FeatureCollection WGS84, notes). Coordinates: WGS84 degrees or local metres — local="msk" (МСК, as in
    QGIS) or "ogd" (ГИС ОГД system: the DXF files ГРАДО 2 wrote before v0.32). A file written by ГРАДО 2 says its own
    system (written_system) and wins over the choice."""
    # кодировку файл объявляет сам ($DWGCODEPAGE): чертежи R2000–R2004 из русского AutoCAD — cp1251, а не UTF-8
    from ezdxf import recover
    doc, _ = recover.read(io.BytesIO(data))
    # кодовая страница бывает потеряна (ANSI_1252 по умолчанию при байтах cp1251): имена слоёв выходят «Êðàñíûå».
    # Русский текст, прочитанный как cp1252, — это сплошь буквы À…ÿ; тогда файл перечитывается как cp1251
    if doc.dxfversion < "AC1021" and doc.encoding.lower() in ("cp1252", "iso-8859-1", "latin-1"):
        names = "".join(l.dxf.name for l in doc.layers)
        if sum("\xc0" <= c <= "\xff" for c in names) >= 3:
            doc = ezdxf.read(io.TextIOWrapper(io.BytesIO(data), encoding="cp1251", errors="replace"))
    feats, skipped, notes = [], 0, []
    upper = {n.upper(): n for n in redln["linetypes"]}
    for e in doc.modelspace():
        t = e.dxftype()
        # вершины полилинии хранятся в её собственной системе (OCS): у зеркальной полилинии x с обратным знаком
        if t == "LWPOLYLINE":
            pts, closed = [tuple(p)[:2] for p in e.vertices_in_wcs()], e.closed
        elif t == "POLYLINE" and not e.is_3d_polyline:
            pts, closed = [tuple(p)[:2] for p in e.points_in_wcs()], e.is_closed
        elif t == "LINE":
            pts, closed = [tuple(e.dxf.start[:2]), tuple(e.dxf.end[:2])], False
        else:
            skipped += 1
            continue
        if len(pts) < 2:
            continue
        lt = e.dxf.linetype if e.dxf.hasattr("linetype") else "BYLAYER"
        if lt.upper() == "BYLAYER":
            layer = doc.layers.get(e.dxf.layer) if e.dxf.layer in doc.layers else None
            lt = layer.dxf.linetype if layer else "CONTINUOUS"
        feats.append({"pts": pts, "closed": closed, "layer": e.dxf.layer, "lt": upper.get(lt.upper())})
    if not feats:
        return {"type": "FeatureCollection", "features": []}, [f"no lines or polylines (skipped {skipped})"]
    import file_io
    system = file_io.system_of([p for f in feats for p in f["pts"]][:2000])
    if system not in ("wgs", "local"):
        raise ValueError("coordinates are neither Moscow local metres (tens of km) nor WGS84 degrees")
    is_wgs = system == "wgs"
    own = written_system(doc, data)
    if own and own != local and not is_wgs:
        notes.append("файл выгружен ГРАДО 2" + (" до v0.32 — прочитан в системе ГИС ОГД" if own == "ogd" else " в МСК — прочитан в МСК")
                     + ", а не по выбору «Файлы в метрах»")
        local = own
    to = (lambda x, y: (x, y)) if is_wgs else file_io.LOCAL[local][0]
    out = []
    for f in feats:
        ring = [list(to(x, y)) for x, y in f["pts"]]
        geom = {"type": "Polygon", "coordinates": [ring + [ring[0]]]} if f["closed"] and len(ring) > 2 \
            else {"type": "LineString", "coordinates": ring}
        props = {"Слой DXF": f["layer"]}
        if f["lt"]:
            props.update({"Тип линии": f["lt"], "LineCode": linecode_of(f["lt"]), "_lt": [f["lt"]], "_miss": []})
            geom = {"type": "LineString", "coordinates": geom["coordinates"][0]} if geom["type"] == "Polygon" else geom
        out.append({"type": "Feature", "geometry": geom, "properties": props})
    notes.append(f"координаты: {'WGS84' if is_wgs else file_io.LOCAL[local][1]}; объектов {len(out)}"
                 + (f", other entities skipped: {skipped}" if skipped else ""))
    return {"type": "FeatureCollection", "features": out}, notes
