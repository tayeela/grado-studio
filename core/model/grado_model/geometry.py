"""Геометрия: GeoJSON-подобные структуры, WKB и GPKG-блобы, метрики.

Координаты — в проекционной СК проекта (метры), поэтому площади и длины
считаются планиметрически. Кривые (CompoundCurve) появятся при переносе
в C++ ядро; эталонная реализация ограничена линейными типами.
"""

import math
import numbers
import struct

WKB_TYPES = {
    "Point": 1,
    "LineString": 2,
    "Polygon": 3,
    "MultiPoint": 4,
    "MultiLineString": 5,
    "MultiPolygon": 6,
}
WKB_NAMES = {v: k for k, v in WKB_TYPES.items()}


class GeometryError(ValueError):
    pass


# пределы на вход: глубина вложенности списков (MultiPolygon = 4 уровня +
# точка) и общее число координатных пар
MAX_COORD_DEPTH = 6
MAX_COORD_POINTS = 5_000_000

# сколько уровней списков у координат каждого типа (Point — сама пара)
_NEST = {"Point": 0, "LineString": 1, "MultiPoint": 1, "Polygon": 2,
         "MultiLineString": 2, "MultiPolygon": 3}


def _check_coords(coords, level, need, counter):
    """Обход без рекурсии: только конечные числа, ожидаемая вложенность."""
    stack = [(coords, level)]
    while stack:
        node, lvl = stack.pop()
        if lvl > MAX_COORD_DEPTH:
            raise GeometryError("слишком глубокая вложенность координат")
        if lvl == need:  # пара x, y (допускается z)
            if not isinstance(node, (list, tuple)) or not 2 <= len(node) <= 3:
                raise GeometryError("координата должна быть парой чисел [x, y]")
            for v in node:
                if isinstance(v, bool) or not isinstance(v, numbers.Real) or not math.isfinite(v):
                    raise GeometryError(f"координата должна быть конечным числом, получено {v!r}")
            counter[0] += 1
            if counter[0] > MAX_COORD_POINTS:
                raise GeometryError("слишком много координат в геометрии")
        else:
            if not isinstance(node, (list, tuple)):
                raise GeometryError("координаты должны быть вложенными списками")
            stack.extend((c, lvl + 1) for c in node)


def validate(geom):
    if not isinstance(geom, dict) or "type" not in geom or "coordinates" not in geom:
        raise GeometryError("геометрия должна быть словарём с type и coordinates")
    if not isinstance(geom["type"], str) or geom["type"] not in _NEST:
        raise GeometryError(f"неподдерживаемый тип геометрии {geom['type']!r}")
    _check_coords(geom["coordinates"], 0, _NEST[geom["type"]], [0])
    return geom


def _enc_point(coords):
    return struct.pack("<2d", float(coords[0]), float(coords[1]))


def _enc_ring(ring):
    return struct.pack("<I", len(ring)) + b"".join(_enc_point(p) for p in ring)


def _enc_body(gtype, coords):
    if gtype == "Point":
        return _enc_point(coords)
    if gtype == "LineString":
        return _enc_ring(coords)
    if gtype == "Polygon":
        return struct.pack("<I", len(coords)) + b"".join(_enc_ring(r) for r in coords)
    # Multi*: каждый элемент — полноценная WKB-геометрия
    part = {"MultiPoint": "Point", "MultiLineString": "LineString",
            "MultiPolygon": "Polygon"}[gtype]
    return struct.pack("<I", len(coords)) + b"".join(
        wkb_encode({"type": part, "coordinates": c}) for c in coords)


def wkb_encode(geom):
    validate(geom)
    gtype = geom["type"]
    return b"\x01" + struct.pack("<I", WKB_TYPES[gtype]) + _enc_body(gtype, geom["coordinates"])


class _Reader:
    def __init__(self, buf, pos=0):
        self.buf = buf
        self.pos = pos

    def take(self, fmt):
        vals = struct.unpack_from(fmt, self.buf, self.pos)
        self.pos += struct.calcsize(fmt)
        return vals


def _dec_geometry(r):
    (order,) = r.take("<B")
    bo = "<" if order == 1 else ">"
    (wkb_type,) = r.take(bo + "I")
    gtype = WKB_NAMES.get(wkb_type & 0xFF)
    if gtype is None:
        raise GeometryError(f"неподдерживаемый WKB-тип {wkb_type}")
    if gtype == "Point":
        return {"type": gtype, "coordinates": list(r.take(bo + "2d"))}
    if gtype == "LineString":
        (n,) = r.take(bo + "I")
        return {"type": gtype, "coordinates": [list(r.take(bo + "2d")) for _ in range(n)]}
    if gtype == "Polygon":
        (n,) = r.take(bo + "I")
        rings = []
        for _ in range(n):
            (m,) = r.take(bo + "I")
            rings.append([list(r.take(bo + "2d")) for _ in range(m)])
        return {"type": gtype, "coordinates": rings}
    (n,) = r.take(bo + "I")
    parts = [_dec_geometry(r) for _ in range(n)]
    return {"type": gtype, "coordinates": [p["coordinates"] for p in parts]}


def wkb_decode(buf, pos=0):
    return _dec_geometry(_Reader(buf, pos))


def gpkg_blob(geom, srs_id):
    """Заголовок GeoPackage Binary (без envelope, little-endian) + WKB."""
    header = b"GP" + bytes([0, 0b00000001]) + struct.pack("<i", srs_id)
    return header + wkb_encode(geom)


_ENVELOPE_SIZE = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}


def gpkg_parse(blob):
    if blob[:2] != b"GP":
        raise GeometryError("не GeoPackage-геометрия (нет магии GP)")
    flags = blob[3]
    env_indicator = (flags >> 1) & 0x07
    if env_indicator not in _ENVELOPE_SIZE:
        raise GeometryError(f"недопустимый envelope indicator {env_indicator}")
    (srs_id,) = struct.unpack_from("<i", blob, 4)
    pos = 8 + _ENVELOPE_SIZE[env_indicator]
    return wkb_decode(blob, pos), srs_id


def _ring_area(ring):
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def area(geom):
    """Планиметрическая площадь, м² (внешний контур минус дырки)."""
    validate(geom)
    if geom["type"] == "Polygon":
        rings = geom["coordinates"]
        return _ring_area(rings[0]) - sum(_ring_area(r) for r in rings[1:])
    if geom["type"] == "MultiPolygon":
        return sum(area({"type": "Polygon", "coordinates": p}) for p in geom["coordinates"])
    return 0.0


def length(geom):
    """Планиметрическая длина, м."""
    validate(geom)

    def line_len(coords):
        return sum(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
                   for (x1, y1), (x2, y2) in zip(coords, coords[1:]))

    if geom["type"] == "LineString":
        return line_len(geom["coordinates"])
    if geom["type"] == "MultiLineString":
        return sum(line_len(c) for c in geom["coordinates"])
    return 0.0
