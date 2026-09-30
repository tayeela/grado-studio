"""DXF export/import for ГРАДО 2 on ezdxf (MIT), with the Moscow red-line linetypes REDLN97.

Export: layers (GeoJSON WGS84) → DXF R2018 in МСК, the owner's QGIS «МСК» (metres; = ГИС ОГД system − (16.098; 14.512)).
Red lines get the REDLN97 complex linetypes; the shape file red_lns.shx goes into the
archive next to the drawing, as AutoCAD expects. Import: DXF in МСК (default), the ГИС ОГД system (DXF written by
ГРАДО 2 before v0.32) or WGS84 → GeoJSON;
REDLN97 linetype names become LineCode again.
"""

import io
import os
import subprocess
import math
import re
import sys
import zipfile
from pathlib import Path

import ezdxf

from grado_connectors import crs
from grado_render import acad_lin

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))   # собранная программа — папка распаковки
STANDARD = ROOT / "docs/standards/redln97"


# Символы, которых AutoCAD не допускает в именах слоёв, листов и прочих таблиц: < > / \ " : ; ? * | , = `
# (ЗАПЯТАЯ тоже: 26.09.2026 выгрузка со слоем «…геодезической, нивелирной, …» в AutoCAD не открывалась вовсе,
# без ошибки; QGIS такие имена читает). Длина — не больше 255 знаков.
_ACAD_BAD = re.compile(r'[<>/\\":;?*|,=`\x00-\x1f]')


def acad_name(text, limit=255):
    """Имя, которое AutoCAD примет: запрещённые знаки → «_», повторы пробелов схлопнуты, без пробелов по краям."""
    name = re.sub(r"\s+", " ", _ACAD_BAD.sub("_", str(text))).strip()[:limit].strip()
    return name or "_"


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


# LWPOLYLINE flag «linetype generation»: the pattern runs continuously along the whole polyline. Without it AutoCAD
# restarts the pattern at every vertex, and on dense ГИС ОГД boundaries (segments under 1 m, pattern 20 m) the
# REDLN97 signs vanish or turn along random short segments.
PLINEGEN = 128


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
        lname = acad_name(layer["name"], 120)
        if lname not in doc.layers:
            doc.layers.add(lname, true_color=_rgb(layer.get("color", "#808080")))
        for f in layer["features"]["features"]:
            props = f.get("properties") or {}
            names = [n for n in props.get("_lt") or [] if n in redln["linetypes"]]
            for n in names:
                _add_linetype(doc, n, redln["linetypes"][n], shapes)
            geom = f["geometry"]
            if geom["type"] in ("Point", "MultiPoint"):
                text = props.get("Текст")
                for x, y, *_ in ([geom["coordinates"]] if geom["type"] == "Point" else geom["coordinates"]):
                    pt = crs.wgs84_to_msk(x, y)
                    msp.add_point(pt, dxfattribs={"layer": lname})
                    if text:
                        msp.add_text(str(text), height=2.5, dxfattribs={"layer": lname, "insert": pt})
                continue
            dimv = props.get("Размер")
            if dimv not in (None, "") and geom["type"] == "LineString" and len(geom["coordinates"]) == 4:
                # размер ГРАДО 2 (выносная–размерная–выносная) — настоящий размер AutoCAD: число пересчитывается при правке
                p1, d1, d2, p2 = [crs.wgs84_to_msk(x, y) for x, y, *_ in geom["coordinates"]]
                ang = math.degrees(math.atan2(d2[1] - d1[1], d2[0] - d1[0]))
                msp.add_linear_dim(base=d1, p1=p1, p2=p2, angle=ang, dimstyle="Standard", dxfattribs={"layer": lname},
                                   override={"dimtxt": 2.5, "dimasz": 2.0, "dimexe": 1.0, "dimexo": 0.5, "dimdec": 2,
                                             "dimdsep": 44, "dimgap": 0.6}).render()
                continue
            for ring, closed in _rings(geom):
                pts = [crs.wgs84_to_msk(x, y) for x, y, *_ in ring]
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
                        a["flags"] = PLINEGEN
                        code = _code_of(n)
                        if code in lgr_colors:
                            a["true_color"] = _rgb(lgr_colors[code])
                    msp.add_lwpolyline(pts, close=closed, dxfattribs=a)
    fit_view(doc)
    buf = io.StringIO()
    doc.write(buf)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("grado2.dxf", buf.getvalue().encode("utf-8"))
        if oda_converter():                      # есть ODA File Converter — рядом кладётся тот же чертёж в DWG
            try:
                z.writestr("grado2.dwg", oda_convert(buf.getvalue().encode("utf-8"), "dxf", "DWG"))
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
        z.write(STANDARD / "RED_LNS.SHX", "red_lns.shx")
        z.write(STANDARD / "REDLN97.LIN", "REDLN97.LIN")
        z.writestr("README.txt", ("Coordinates: MSK - Moscow local system as the QGIS custom CRS 'MSK' "
                                  "(+proj=tmerc +lat_0=55.66666666667 +lon_0=37.5 +k=1 +x_0=0 +y_0=0 +ellps=bessel), metres.\n"
                                  "Red lines use REDLN97 linetypes; keep red_lns.shx next to grado2.dxf.\n").encode())
    return out.getvalue()


def fit_view(doc):
    """Границы чертежа и вид модели — на данные. Без этого в заголовке остаются «пустые» границы (1e20), а вид —
    центр 0,0 и высота 1000 м: объекты в МСК лежат в километрах от начала, и AutoCAD открывает файл без ошибки,
    но с пустым экраном (QGIS сам приближается к данным и этого не видно; жалоба владельца 26.09.2026)."""
    from ezdxf import bbox
    ext = bbox.extents(doc.modelspace(), fast=True)
    if not ext.has_data:
        return
    (x0, y0, _), (x1, y1, _) = ext.extmin, ext.extmax
    msp = doc.modelspace()                  # ezdxf пишет $EXTMIN/$EXTMAX из самой модели, заголовок перезаписывается
    msp.reset_extents((x0, y0, 0), (x1, y1, 0))
    msp.reset_limits((x0, y0), (x1, y1))
    w, h = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
    doc.set_modelspace_vport(height=max(h, w * 0.7) * 1.05, center=((x0 + x1) / 2, (y0 + y1) / 2))


def oda_converter():
    """ODA File Converter (бесплатный, opendesign.com) — единственный путь к DWG без AutoCAD; сам не ставится.
    Путь можно задать переменной GRADO2_ODA."""
    import glob
    import shutil
    cands = [os.environ.get("GRADO2_ODA") or "", "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter",
             *glob.glob("/Applications/ODA*/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"),
             *glob.glob(r"C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe"),
             shutil.which("ODAFileConverter") or ""]
    return next((c for c in cands if c and os.path.isfile(c)), None)


def oda_convert(data, src_ext, out_fmt):
    """Файл src_ext (dwg/dxf) → байты DXF или DWG (ACAD2018) через ODA File Converter."""
    import tempfile
    exe = oda_converter()
    if not exe:
        raise ValueError("DWG читается и пишется через бесплатный ODA File Converter (opendesign.com): установите его "
                         "или пересохраните чертёж в DXF")
    with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
        (Path(src) / f"in.{src_ext}").write_bytes(data)
        try:
            subprocess.run([exe, src, dst, "ACAD2018", out_fmt, "0", "1", f"*.{src_ext.upper()}"],
                           capture_output=True, timeout=180, check=False)
        except subprocess.TimeoutExpired:          # зависший конвертер — обычная ошибка для пользователя, не 500
            raise ValueError("ODA File Converter не уложился в 3 минуты: чертёж слишком сложный или повреждён — "
                             "пересохраните его в DXF") from None
        out = next(Path(dst).glob(f"*.{out_fmt.lower()}"), None) or next(Path(dst).glob(f"*.{out_fmt.upper()}"), None)
        if not out:
            raise ValueError(f"ODA File Converter не создал {out_fmt}: чертёж повреждён или версия не поддерживается")
        return out.read_bytes()


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
    from ezdxf import recover, path as ezpath
    from file_io import check_size
    check_size("DXF", len(data))                   # recover.read держит файл в памяти целиком, в несколько раз больше размера
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
        # дуги полилиний (bulge) раскладываются в хорды до 5 см: иначе скругление красной линии становится прямой
        if t in ("LWPOLYLINE", "POLYLINE") and not (t == "POLYLINE" and e.is_3d_polyline):
            closed = e.closed if t == "LWPOLYLINE" else e.is_closed
            pts = [(v.x, v.y) for v in ezpath.make_path(e).flattening(0.05)]
            if closed and len(pts) > 2 and pts[0] == pts[-1]:
                pts = pts[:-1]
        elif t == "LINE":
            pts, closed = [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)], False
        elif t == "DIMENSION" and e.dimtype in (0, 1):
            # линейный и параллельный размер → ломаная выносная–размерная–выносная с полем «Размер», как рисует DIM
            p1, p2, b = e.dxf.defpoint2, e.dxf.defpoint3, e.dxf.defpoint
            a = math.radians(e.dxf.get("angle", 0.0)) if e.dimtype == 0 else math.atan2(p2.y - p1.y, p2.x - p1.x)
            ux, uy = math.cos(a), math.sin(a)
            foot = lambda p: (b.x + ((p.x - b.x) * ux + (p.y - b.y) * uy) * ux, b.y + ((p.x - b.x) * ux + (p.y - b.y) * uy) * uy)
            pts, closed = [(p1.x, p1.y), foot(p1), foot(p2), (p2.x, p2.y)], False
            meas = abs((p2.x - p1.x) * ux + (p2.y - p1.y) * uy)
            feats.append({"pts": pts, "closed": False, "layer": e.dxf.layer, "lt": None, "dim": f"{meas:.2f}".replace(".", ",")})
            continue
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
        return {"type": "FeatureCollection", "features": []}, [f"нет линий и полилиний (пропущено объектов: {skipped} — блоки, окружности, тексты)"]
    import file_io
    system = file_io.system_of([p for f in feats for p in f["pts"]][:2000])
    if system not in ("wgs", "local"):
        raise ValueError("координаты не похожи ни на местные московские метры, ни на градусы WGS84")
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
        props = {"Слой DXF": f["layer"], **({"Размер": f["dim"]} if f.get("dim") else {})}
        if f["lt"]:
            props.update({"Тип линии": f["lt"], "LineCode": linecode_of(f["lt"]), "_lt": [f["lt"]], "_miss": []})
            geom = {"type": "LineString", "coordinates": geom["coordinates"][0]} if geom["type"] == "Polygon" else geom
        out.append({"type": "Feature", "geometry": geom, "properties": props})
    notes.append(f"координаты: {'WGS84' if is_wgs else file_io.LOCAL[local][1]}; объектов {len(out)}"
                 + (f", пропущено прочих объектов: {skipped}" if skipped else ""))
    return {"type": "FeatureCollection", "features": out}, notes
