"""SHP-ридер без GDAL + пересчёт МСК-50 → WGS84.

Эталонные значения msk50_to_wgs84 получены из PROJ (gdaltransform комплекта
QGIS-LTR) на тех же точках — тест фиксирует совпадение с PROJ без GDAL в
рантайме. Shapefile'ы строятся вручную (struct) — проверка чистого ридера."""

import struct
import tempfile
import unittest
from pathlib import Path

from grado_connectors.crs import msk50_to_wgs84
from grado_connectors.shp_reader import read_shp


def _shp_header(shape_type, file_len_words):
    h = bytearray(100)
    struct.pack_into(">i", h, 0, 9994)               # file code
    struct.pack_into(">i", h, 24, file_len_words)    # длина файла (16-битные слова)
    struct.pack_into("<i", h, 28, 1000)              # версия
    struct.pack_into("<i", h, 32, shape_type)
    return h


def _make_point_shp(path, x, y):
    content = struct.pack("<idd", 1, x, y)           # type=1, X, Y
    rec = struct.pack(">ii", 1, len(content) // 2) + content
    hdr = _shp_header(1, (100 + len(rec)) // 2)
    path.write_bytes(bytes(hdr) + rec)


def _make_polygon_shp(path, ring):
    ring = ring + [ring[0]]                           # замкнуть
    npts = len(ring)
    body = struct.pack("<i", 5)                       # type=5 (Polygon)
    body += struct.pack("<4d", 0, 0, 0, 0)            # bbox (не проверяем)
    body += struct.pack("<ii", 1, npts)               # numParts, numPoints
    body += struct.pack("<i", 0)                      # parts[0]
    for px, py in ring:
        body += struct.pack("<dd", px, py)
    rec = struct.pack(">ii", 1, len(body) // 2) + body
    hdr = _shp_header(5, (100 + len(rec)) // 2)
    path.write_bytes(bytes(hdr) + rec)


def _make_dbf(path, fields, row, encoding="cp1251"):
    """fields = [(name, type, length)], row = [значения]."""
    hdr = bytearray(32)
    hdr[0] = 0x03
    struct.pack_into("<I", hdr, 4, 1)                 # 1 запись
    header_size = 32 + 32 * len(fields) + 1
    record_size = 1 + sum(f[2] for f in fields)
    struct.pack_into("<H", hdr, 8, header_size)
    struct.pack_into("<H", hdr, 10, record_size)
    out = bytes(hdr)
    for name, ftype, flen in fields:
        fd = bytearray(32)
        fd[0:len(name)] = name.encode("ascii")
        fd[11] = ord(ftype)
        fd[16] = flen
        out += bytes(fd)
    out += b"\x0d"
    rec = b"\x20"                                     # флаг «не удалено»
    for (name, ftype, flen), val in zip(fields, row):
        rec += str(val).encode(encoding, "replace")[:flen].ljust(flen)
    path.write_bytes(out + rec)


class TestMsk50(unittest.TestCase):
    # (easting, northing) -> (lon, lat) из PROJ
    REF = [((6000, 9000), (37.5937137450253, 55.7478064930313)),
           ((40000, 15000), (38.1359862038977, 55.800091426315)),
           ((20000, 5000), (37.816358146533, 55.7115089434084))]

    def test_matches_proj(self):
        for (e, n), (rlon, rlat) in self.REF:
            lon, lat = msk50_to_wgs84(e, n)
            self.assertAlmostEqual(lon, rlon, places=7)
            self.assertAlmostEqual(lat, rlat, places=7)


class TestShpReader(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_point_with_attrs(self):
        _make_point_shp(self.d / "p.shp", 6000.0, 9000.0)
        _make_dbf(self.d / "p.dbf",
                  [("NAME", "C", 20), ("KOD", "N", 4)], ["Зона Ж", 42])
        feats = read_shp(self.d / "p.shp")
        self.assertEqual(len(feats), 1)
        self.assertEqual(feats[0]["geometry"]["type"], "Point")
        self.assertEqual(feats[0]["geometry"]["coordinates"], [6000.0, 9000.0])
        self.assertEqual(feats[0]["properties"]["NAME"], "Зона Ж")
        self.assertEqual(feats[0]["properties"]["KOD"], 42)

    def test_polygon_ring(self):
        ring = [[0, 0], [100, 0], [100, 100], [0, 100]]   # CCW
        _make_polygon_shp(self.d / "z.shp", ring)
        feats = read_shp(self.d / "z.shp")
        self.assertEqual(feats[0]["geometry"]["type"], "Polygon")
        # первое кольцо замкнуто и содержит все вершины
        outer = feats[0]["geometry"]["coordinates"][0]
        self.assertEqual(outer[0], outer[-1])
        self.assertEqual(len(outer), 5)


if __name__ == "__main__":
    unittest.main()
