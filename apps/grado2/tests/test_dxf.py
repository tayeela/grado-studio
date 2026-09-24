import io
import json
import sys
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import server as S  # noqa: E402  (sets up paths to the core)

try:
    import ezdxf  # noqa: F401
    import dxf_io
except ImportError:              # ezdxf lives in the ГРАДО 2 venv (requirements.txt)
    dxf_io = None


@unittest.skipIf(dxf_io is None, "ezdxf not installed")
class DxfRoundTrip(unittest.TestCase):
    def test_export_then_import_keeps_linecode_and_coordinates(self):
        fc = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[37.52, 55.79], [37.53, 55.791]]},
             "properties": {"_lt": ["L01s18t"]}},
            {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[37.52, 55.792], [37.53, 55.792]]},
             "properties": {"_lt": ["L00s16b"]}}]}
        z = zipfile.ZipFile(io.BytesIO(dxf_io.export_dxf([{"name": "Красные линии", "features": fc}], S.REDLN, S.LGR_COLORS)))
        self.assertEqual(sorted(z.namelist()), ["README.txt", "REDLN97.LIN", "grado2.dxf", "red_lns.shx"])
        back, _ = dxf_io.import_dxf(z.read("grado2.dxf"), S.REDLN)
        codes = [f["properties"]["LineCode"] for f in back["features"]]
        self.assertEqual(codes, ["1,-18", "16"])
        x, y = back["features"][0]["geometry"]["coordinates"][0]
        self.assertAlmostEqual(x, 37.52, places=8)
        self.assertAlmostEqual(y, 55.79, places=8)

    def test_line_and_bulge_import_points_export(self):
        doc = ezdxf.new("R2018"); msp = doc.modelspace()
        msp.add_line((1000, 2000), (1100, 2000))
        msp.add_lwpolyline([(1000, 3000, 0, 0, 1), (1100, 3000)], format="xyseb")   # полукруг R50
        buf = io.StringIO(); doc.write(buf)
        back, _ = dxf_io.import_dxf(buf.getvalue().encode(), S.REDLN)
        self.assertEqual(len(back["features"]), 2)
        self.assertGreater(len(back["features"][1]["geometry"]["coordinates"]), 20)     # дуга, а не хорда
        fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"Текст": "Школа"},
              "geometry": {"type": "Point", "coordinates": [37.6, 55.75, 140]}}]}
        z = zipfile.ZipFile(io.BytesIO(dxf_io.export_dxf([{"name": "Надписи", "features": fc}], S.REDLN, S.LGR_COLORS)))
        d = ezdxf.read(io.StringIO(z.read("grado2.dxf").decode()))
        self.assertEqual(sorted(e.dxftype() for e in d.modelspace()), ["POINT", "TEXT"])
        dim = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"Размер": "40,00"},
               "geometry": {"type": "LineString", "coordinates": [[37.6, 55.75], [37.6, 55.7501], [37.6006, 55.7501], [37.6006, 55.75]]}}]}
        z = zipfile.ZipFile(io.BytesIO(dxf_io.export_dxf([{"name": "Размеры", "features": dim}], S.REDLN, S.LGR_COLORS)))
        ents = ezdxf.read(io.StringIO(z.read("grado2.dxf").decode())).modelspace()
        dims = [e for e in ents if e.dxftype() == "DIMENSION"]
        self.assertEqual(len(dims), 1)
        self.assertTrue(37 < dims[0].get_measurement() < 38.2)
        back, _ = dxf_io.import_dxf(z.read("grado2.dxf"), S.REDLN)
        d = [f for f in back["features"] if f["properties"].get("Размер")]
        self.assertEqual(len(d), 1)
        self.assertEqual(len(d[0]["geometry"]["coordinates"]), 4)
        self.assertEqual(d[0]["properties"]["Размер"], f"{dims[0].get_measurement():.2f}".replace(".", ","))

    def test_dwg_without_converter_says_how(self):
        import os
        old = os.environ.pop("GRADO2_ODA", None)
        try:
            if dxf_io.oda_converter():
                self.skipTest("ODA File Converter установлен")
            with self.assertRaisesRegex(ValueError, "ODA File Converter"):
                dxf_io.oda_convert(b"x", "dwg", "DXF")
        finally:
            if old:
                os.environ["GRADO2_ODA"] = old

    def test_export_in_msk_matches_proj_and_ogd_import(self):
        sys.path.insert(0, str(HERE.parents[1] / "core/connectors/tests"))
        from test_crs import MSK_PROJ
        (lon, lat), (mx, my) = MSK_PROJ[19]
        fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
              "geometry": {"type": "LineString", "coordinates": [[lon, lat], [lon + .001, lat]]}}]}
        z = zipfile.ZipFile(io.BytesIO(dxf_io.export_dxf([{"name": "Л", "features": fc}], S.REDLN, S.LGR_COLORS)))
        doc = ezdxf.read(io.StringIO(z.read("grado2.dxf").decode("utf-8")))
        v = list(next(iter(doc.modelspace())).vertices_in_wcs())[0]; x, y = v.x, v.y
        self.assertLess(((x - mx) ** 2 + (y - my) ** 2) ** .5, 0.001, "DXF в МСК, как PROJ с MSK_PROJ4")
        self.assertIn("MSK", z.read("README.txt").decode())
        # DXF, выгруженный ГРАДО 2 до v0.32, был в системе ГИС ОГД: читается с выбором «ГИС ОГД»
        doc2 = ezdxf.new("R2018")
        doc2.modelspace().add_lwpolyline([(mx + 16.098, my + 14.512), (mx + 116.098, my + 14.512)])
        buf = io.StringIO(); doc2.write(buf)
        back, notes = dxf_io.import_dxf(buf.getvalue().encode(), S.REDLN, "ogd")
        blon, blat = back["features"][0]["geometry"]["coordinates"][0]
        self.assertAlmostEqual(blon, lon, places=7); self.assertAlmostEqual(blat, lat, places=7)
        self.assertIn("ГИС ОГД", notes[-1])

    def test_file_written_by_grado2_says_its_system(self):
        sys.path.insert(0, str(HERE.parents[1] / "core/connectors/tests"))
        from test_crs import MSK_PROJ
        (lon, lat), (mx, my) = MSK_PROJ[19]
        fc = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
              "geometry": {"type": "LineString", "coordinates": [[lon, lat], [lon + .001, lat]]}}]}
        dxf = zipfile.ZipFile(io.BytesIO(dxf_io.export_dxf([{"name": "Л", "features": fc}], S.REDLN, S.LGR_COLORS))).read("grado2.dxf")
        # новая выгрузка несёт метку МСК: даже при выборе «ГИС ОГД» читается в МСК и не уезжает на 21 м
        back, notes = dxf_io.import_dxf(dxf, S.REDLN, "ogd")
        blon, blat = back["features"][0]["geometry"]["coordinates"][0]
        self.assertAlmostEqual(blon, lon, places=7); self.assertAlmostEqual(blat, lat, places=7)
        self.assertTrue(any("выгружен ГРАДО 2" in n for n in notes))
        # выгрузка ГРАДО 2 до v0.32 (ezdxf, стиль red_lns.shx, без метки) — система ГИС ОГД без выбора
        old = ezdxf.new("R2018", setup=False); old.styles.add_shx("red_lns.shx")
        old.modelspace().add_lwpolyline([(mx + 16.098, my + 14.512), (mx + 116.098, my + 14.512)])
        buf = io.StringIO(); old.write(buf)
        back, notes = dxf_io.import_dxf(buf.getvalue().encode(), S.REDLN)
        blon, blat = back["features"][0]["geometry"]["coordinates"][0]
        self.assertAlmostEqual(blon, lon, places=7); self.assertAlmostEqual(blat, lat, places=7)
        self.assertTrue(any("до v0.32" in n for n in notes))
        # чужой чертёж без стиля red_lns.shx — по выбору
        self.assertIsNone(dxf_io.written_system(ezdxf.new("R2018")))

    def test_linetype_uses_shape_number(self):
        doc = ezdxf.new("R2018")
        doc.styles.add_shx("red_lns.shx")
        shapes = {k.upper(): v for k, v in S.REDLN["shapes"].items()}
        dxf_io._add_linetype(doc, "L00s16b", S.REDLN["linetypes"]["L00s16b"], shapes)
        tags = {t.code: t.value for t in doc.linetypes.get("L00s16b").pattern_tags.tags}
        self.assertEqual(tags[75], 144)              # ANGLF2 in RED_LNS.SHX


class LinetypeProps(unittest.TestCase):
    def test_red_line_codes_become_linetypes(self):
        p = S.linetype_props({"linelineco": "1,-18,-29"})
        self.assertEqual(p["_lt"], ["L01s18t"])
        self.assertEqual(p["_miss"], [[29, -1]])


if __name__ == "__main__":
    unittest.main()
