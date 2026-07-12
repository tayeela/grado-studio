"""Чтение ESRI Shapefile (.shp + .dbf) без GDAL — фолбэк, когда нет ogr2ogr.

Возвращает GeoJSON-подобные фигуры в ИСХОДНОЙ СК файла (перепроецирование —
отдельно, msk50_to_wgs84). Поддержаны Point, PolyLine, Polygon и их Z/M-варианты
(координата Z/M игнорируется — берём только X,Y). Кодировка .dbf берётся из
.cpg, иначе cp1251 (типично для российских выгрузок ГИС ОГД). Формат — по
спецификации ESRI Shapefile (заголовок .shp = 100 байт, записи с BE-заголовком
и LE-содержимым; .dbf — dBASE III)."""

import struct
from pathlib import Path


def _read_dbf(path, encoding):
    data = path.read_bytes()
    if len(data) < 32:
        return []
    num_records = struct.unpack("<I", data[4:8])[0]
    header_size = struct.unpack("<H", data[8:10])[0]
    record_size = struct.unpack("<H", data[10:12])[0]
    fields, pos = [], 32
    while pos < len(data) and data[pos] != 0x0D:
        name = data[pos:pos + 11].split(b"\x00")[0].decode("ascii", "replace")
        ftype = chr(data[pos + 11])
        flen = data[pos + 16]
        fields.append((name, ftype, flen))
        pos += 32
    records = []
    for r in range(num_records):
        off = header_size + r * record_size
        if data[off:off + 1] == b"\x2a":     # запись помечена удалённой
            continue
        row, c = {}, off + 1
        for name, ftype, flen in fields:
            val = data[c:c + flen].decode(encoding, "replace").strip()
            c += flen
            if ftype in "NF":
                if val in ("", "*"):
                    val = None
                else:
                    try:
                        val = (int(val) if ftype == "N" and "." not in val
                               else float(val))
                    except ValueError:
                        val = None
            elif ftype == "L":
                val = (True if val in "YyTt" else
                       False if val in "NnFf" else None)
            row[name] = val
        records.append(row)
    return records


def _points(buf, off, n):
    pts = []
    for _ in range(n):
        pts.append(list(struct.unpack("<dd", buf[off:off + 16])))
        off += 16
    return pts


def _ring_area(ring):
    s = 0.0
    for i in range(len(ring) - 1):
        s += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
    return s / 2.0


def _shape(buf):
    if len(buf) < 4:
        return None
    stype = struct.unpack("<i", buf[0:4])[0]
    if stype == 0:                            # Null
        return None
    if stype in (1, 11, 21):                  # Point / PointZ / PointM
        x, y = struct.unpack("<dd", buf[4:20])
        return {"type": "Point", "coordinates": [x, y]}
    if stype in (3, 5, 13, 15, 23, 25):       # PolyLine / Polygon (+Z/M)
        nparts = struct.unpack("<i", buf[36:40])[0]
        npts = struct.unpack("<i", buf[40:44])[0]
        parts = list(struct.unpack("<%di" % nparts, buf[44:44 + 4 * nparts]))
        pts = _points(buf, 44 + 4 * nparts, npts)
        parts.append(npts)
        rings = [pts[parts[i]:parts[i + 1]] for i in range(nparts)]
        if stype in (3, 13, 23):              # PolyLine
            if len(rings) == 1:
                return {"type": "LineString", "coordinates": rings[0]}
            return {"type": "MultiLineString", "coordinates": rings}
        # Polygon: по спецификации внешнее кольцо — по часовой (area<0 при Y↑),
        # дырка — против; последующие дырки цепляются к текущему внешнему
        polys, cur = [], None
        for ring in rings:
            if _ring_area(ring) < 0 or cur is None:
                cur = [ring]
                polys.append(cur)
            else:
                cur.append(ring)
        if len(polys) == 1:
            return {"type": "Polygon", "coordinates": polys[0]}
        return {"type": "MultiPolygon", "coordinates": polys}
    if stype in (8, 18, 28):                  # MultiPoint (+Z/M)
        npts = struct.unpack("<i", buf[36:40])[0]
        return {"type": "MultiPoint", "coordinates": _points(buf, 40, npts)}
    return None                               # неизвестный тип — пропускаем


def read_shp(shp_path):
    """[.shp + .dbf] → [{"geometry": GeoJSON | None, "properties": {...}}]."""
    shp_path = Path(shp_path)
    data = shp_path.read_bytes()
    enc = "cp1251"
    cpg = shp_path.with_suffix(".cpg")
    if cpg.exists():
        tag = cpg.read_text("ascii", "replace").strip().lower()
        if "utf" in tag:
            enc = "utf-8"
        elif "866" in tag:
            enc = "cp866"
    dbf = shp_path.with_suffix(".dbf")
    attrs = _read_dbf(dbf, enc) if dbf.exists() else []
    geoms, pos, n = [], 100, len(data)
    while pos + 8 <= n:
        rec_len = struct.unpack(">i", data[pos + 4:pos + 8])[0] * 2
        geoms.append(_shape(data[pos + 8:pos + 8 + rec_len]))
        pos += 8 + rec_len
    return [{"geometry": g, "properties": attrs[i] if i < len(attrs) else {}}
            for i, g in enumerate(geoms)]
