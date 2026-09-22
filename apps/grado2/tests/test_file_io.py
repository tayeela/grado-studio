"""Import of GeoJSON, KML and Shapefile for ГРАДО 2: coordinates end up in WGS84 whatever came in."""

import io
import json
import struct
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402,F401  (sets up sys.path for the core)
import file_io  # noqa: E402
from grado_connectors import crs  # noqa: E402


def _fc(geom, **props):
    return json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": geom, "properties": props}]}).encode()


def _shp_polygon(ring):
    ring = ring + [ring[0]]
    body = struct.pack("<i", 5) + struct.pack("<4d", 0, 0, 0, 0) + struct.pack("<ii", 1, len(ring)) + struct.pack("<i", 0)
    for x, y in ring:
        body += struct.pack("<dd", x, y)
    rec = struct.pack(">ii", 1, len(body) // 2) + body
    h = bytearray(100)
    struct.pack_into(">i", h, 0, 9994); struct.pack_into(">i", h, 24, (100 + len(rec)) // 2)
    struct.pack_into("<i", h, 28, 1000); struct.pack_into("<i", h, 32, 5)
    return bytes(h) + rec


def _dbf(name, value):
    hdr = bytearray(32); hdr[0] = 3
    struct.pack_into("<I", hdr, 4, 1); struct.pack_into("<H", hdr, 8, 32 + 32 + 1); struct.pack_into("<H", hdr, 10, 1 + 20)
    fd = bytearray(32); fd[0:len(name)] = name.encode(); fd[11] = ord("C"); fd[16] = 20
    return bytes(hdr) + bytes(fd) + b"\r" + b" " + value.encode("cp1251").ljust(20) + b"\x1a"


class FileImport(unittest.TestCase):
    def test_geojson_in_degrees_stays(self):
        [lay] = file_io.import_files({"a.geojson": _fc({"type": "Point", "coordinates": [37.6, 55.75]}, name="x")})
        self.assertEqual(lay["features"]["features"][0]["geometry"]["coordinates"], [37.6, 55.75])
        self.assertIn("WGS84", lay["notes"][0])

    def test_geojson_in_mggt_is_converted(self):
        lon, lat = 37.5, 55.79
        e, n = crs.wgs84_to_msk50(lon, lat)
        [lay] = file_io.import_files({"b.json": _fc({"type": "Point", "coordinates": [e, n]})})
        x, y = lay["features"]["features"][0]["geometry"]["coordinates"]
        self.assertAlmostEqual(x, lon, places=5); self.assertAlmostEqual(y, lat, places=5)
        self.assertIn("МГГТ", lay["notes"][0])

    def test_geojson_in_web_mercator_is_converted(self):
        x, y = crs.wgs84_to_merc(37.6, 55.75)
        [lay] = file_io.import_files({"c.geojson": _fc({"type": "Point", "coordinates": [x, y]})})
        lon, lat = lay["features"]["features"][0]["geometry"]["coordinates"]
        self.assertAlmostEqual(lon, 37.6, places=6); self.assertAlmostEqual(lat, 55.75, places=6)

    def test_kml_placemark_polygon_with_hole_and_data(self):
        kml = b"""<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><name>Kvartal</name>
          <ExtendedData><Data name="floors"><value>9</value></Data></ExtendedData>
          <Polygon><outerBoundaryIs><LinearRing><coordinates>37.5,55.7,0 37.6,55.7,0 37.6,55.8,0 37.5,55.7,0</coordinates></LinearRing></outerBoundaryIs>
          <innerBoundaryIs><LinearRing><coordinates>37.55,55.72 37.56,55.72 37.56,55.73 37.55,55.72</coordinates></LinearRing></innerBoundaryIs></Polygon></Placemark></Document></kml>"""
        [lay] = file_io.import_files({"d.kml": kml})
        f = lay["features"]["features"][0]
        self.assertEqual(f["geometry"]["type"], "Polygon")
        self.assertEqual(len(f["geometry"]["coordinates"]), 2)
        self.assertEqual(f["properties"], {"Название": "Kvartal", "floors": "9"})

    def test_kmz_is_unzipped(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("doc.kml", b'<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><Point><coordinates>37.6,55.75</coordinates></Point></Placemark></kml>')
        [lay] = file_io.import_files({"e.kmz": buf.getvalue()})
        self.assertEqual(lay["features"]["features"][0]["geometry"]["coordinates"], [37.6, 55.75])

    def test_shapefile_in_zip_with_russian_attribute(self):
        e0, n0 = crs.wgs84_to_msk50(37.5, 55.79)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("zones/zone.shp", _shp_polygon([(e0, n0), (e0 + 100, n0), (e0 + 100, n0 + 100)]))
            z.writestr("zones/zone.dbf", _dbf("NAME", "Жилая"))
        [lay] = file_io.import_files({"zones.zip": buf.getvalue()})
        f = lay["features"]["features"][0]
        self.assertEqual(f["properties"]["NAME"], "Жилая")
        self.assertAlmostEqual(f["geometry"]["coordinates"][0][0][0], 37.5, places=5)
        self.assertEqual(lay["format"], "SHP")

    def test_nothing_readable_raises(self):
        with self.assertRaises(ValueError):
            file_io.import_files({"notes.txt": b"hello"})


class PortalFields(unittest.TestCase):
    def test_pzz_subzone_regulation(self):
        p = server.pzz_sub_props({"podzone_num": "77-02-17-100500-000001", "plotnost": "29,3", "vysota": "-", "proczastro": "Ф", "num_pp": "689-ПП", "doc_date": "2021-05-27 00:00:00"})
        self.assertEqual(p["Плотность, тыс. м²/га"], 29.3)
        self.assertIsNone(p["Высота, м"]); self.assertIsNone(p["Застроенность, %"])
        self.assertEqual(p["Номер зоны"], "77-02-17-100500")
        self.assertIn("высота не установлена", p["Регламент"]); self.assertIn("застроенность по факту", p["Регламент"])
        self.assertEqual(p["Документ"], "689-ПП от 2021-05-27")

    def test_pzz_zero_parameters_mean_no_new_construction(self):
        p = server.pzz_sub_props({"plotnost": "0", "vysota": "0", "proczastro": "0"})
        self.assertEqual(p["Высота, м"], 0)
        self.assertIn("не предусмотрено", p["Регламент"])

    def test_pzz_integer_height_stays_integer(self):
        self.assertEqual(server.pzz_sub_props({"vysota": "75"})["Высота, м"], 75)

    def test_zone_vri_names_from_info_text(self):
        p = server.pzz_zone_props({"zone_num": "77-1", "vri_540": "2.6, 3.5.1", "info": "2.6 Многоэтажная жилая застройка\nРазмещение домов\n3.5.1 Образование\nтекст"})
        self.assertEqual(p["ВРИ"], "2.6 Многоэтажная жилая застройка; 3.5.1 Образование")


class Fgistp(unittest.TestCase):
    def test_docs_filtered_by_extent_and_local_first(self):
        m = lambda lo, la: server.crs.wgs84_to_merc(lo, la)
        (a, b), (c, d) = m(37.4, 55.6), m(37.8, 55.9)
        cat = [{"uin": "big", "stp_name": "Схема РФ", "stp_extent": "-20037433_5034737_20037507_13605912"},
               {"uin": "msk", "stp_name": "Генплан Москвы", "stp_extent": f"{a}_{b}_{c}_{d}"},
               {"uin": "far", "stp_name": "Саратов", "stp_extent": "5043946_6655096_5153363_6781806"},
               {"uin": "small", "stp_name": "ППТ", "stp_extent": f"{a + 100}_{b + 100}_{a + 900}_{b + 900}"},
               {"uin": "bad", "stp_name": "без охвата", "stp_extent": ""}]
        docs = server.fgistp_docs([37.4, 55.6, 37.5, 55.7], cat)
        self.assertEqual([d["uin"] for d in docs], ["small", "msk"])


if __name__ == "__main__":
    unittest.main()
