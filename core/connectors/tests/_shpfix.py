"""Тестовый «портал»: слой GeoJSON → zip-выгрузка SHP, как её отдаёт ГИС ОГД (format=shp).

Геометрия пишется в родных координатах ГИС ОГД (OGD_PROJ4): тестовые слои заданы в WGS84 и переводятся в систему ОГД
(wgs84_to_msk50), а коннектор переводит их обратно. Имена полей .dbf обрезаются до 10 знаков, как у портала.
"""

import io
import struct
import zipfile

import _paths  # noqa: F401
from grado_connectors.crs import wgs84_to_msk50

PRJ = ('PROJCS["Moscow_bessel",GEOGCS["GCS_Bessel_1841",DATUM["D_Bessel_1841",SPHEROID["Bessel_1841",6377397.155,'
       '299.1528128]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.017453292519943295]],PROJECTION["Transverse_Mercator"],'
       'PARAMETER["False_Easting",0.0],PARAMETER["False_Northing",0.0],PARAMETER["Central_Meridian",37.5],'
       'PARAMETER["Scale_Factor",1.0],PARAMETER["Latitude_Of_Origin",55.66666666666666],UNIT["Meter",1.0]]')


def _area(ring):
    return sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)) / 2


def _parts(geom):
    t, c = geom["type"], geom["coordinates"]
    if t == "Point":
        return 1, [[c]]
    if t == "LineString":
        return 3, [c]
    if t == "MultiLineString":
        return 3, c
    polys = [c] if t == "Polygon" else c
    rings = []
    for rs in polys:
        for i, r in enumerate(rs):
            outer = i == 0
            if (_area(r) < 0) != outer:          # внешнее — по часовой, дыры — против (спецификация ESRI)
                r = r[::-1]
            rings.append(r)
    return 5, rings


def _record(geom):
    stype, parts = _parts(geom)
    if stype == 1:
        x, y = parts[0][0]
        return struct.pack("<idd", 1, x, y), 1
    pts = [p for part in parts for p in part]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    head = struct.pack("<i4d2i", stype, min(xs), min(ys), max(xs), max(ys), len(parts), len(pts))
    offs, n = [], 0
    for part in parts:
        offs.append(n)
        n += len(part)
    return head + struct.pack(f"<{len(offs)}i", *offs) + b"".join(struct.pack("<dd", *p[:2]) for p in pts), stype


def _dbf(rows):
    names = []
    for r in rows:
        for k in r:
            if k not in names:
                names.append(k)
    fields = []
    for k in names:
        vals = [r.get(k) for r in rows]
        num = all(v is None or isinstance(v, (int, float)) for v in vals)
        fields.append((k[:10], "N" if num else "C", 19 if num else 254, 6 if num and any(isinstance(v, float) for v in vals) else 0, k))
    head_len, rec_len = 32 + 32 * len(fields) + 1, 1 + sum(f[2] for f in fields)
    out = bytearray(struct.pack("<4BIHH20x", 3, 126, 9, 23, len(rows), head_len, rec_len))
    for name, typ, ln, dec, _ in fields:
        out += name.encode("ascii").ljust(11, b"\0") + typ.encode() + b"\0" * 4 + bytes([ln, dec]) + b"\0" * 14
    out += b"\x0d"
    for r in rows:
        out += b" "
        for name, typ, ln, dec, full in fields:
            v = r.get(full)
            if typ == "N":
                s = "" if v is None else (f"{v:.{dec}f}" if dec else str(int(v)))
                out += s.rjust(ln).encode("ascii")
            else:
                out += ("" if v is None else str(v)).encode("utf-8")[:ln].ljust(ln, b" ")
    return bytes(out + b"\x1a")


def shp_zip(layer, native=False):
    """FeatureCollection (WGS84, либо уже в системе ОГД при native=True) → байты zip, как format=shp портала.
    Объекты без геометрии пишутся нулевой записью (тип 0)."""
    to = (lambda p: p) if native else (lambda p: list(wgs84_to_msk50(p[0], p[1])))

    def conv(c):
        return to(c) if isinstance(c[0], (int, float)) else [conv(x) for x in c]

    shp, rows, stypes = b"", [], set()
    for i, f in enumerate(layer["features"]):
        g = f.get("geometry")
        if g:
            body, st = _record({"type": g["type"], "coordinates": conv(g["coordinates"])})
            stypes.add(st)
        else:
            body = struct.pack("<i", 0)
        shp += struct.pack(">2i", i + 1, len(body) // 2) + body
        rows.append(f.get("properties") or {})
    st = stypes.pop() if len(stypes) == 1 else 5
    header = struct.pack(">7i", 9994, 0, 0, 0, 0, 0, (100 + len(shp)) // 2) + struct.pack("<2i4d4d", 1000, st, 0, 0, 0, 0, 0, 0, 0, 0)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        z.writestr("Слой.shp", header + shp)
        z.writestr("Слой.dbf", _dbf(rows))
        z.writestr("Слой.prj", PRJ)
        z.writestr("Слой.cpg", "UTF-8")
    return buf.getvalue()
