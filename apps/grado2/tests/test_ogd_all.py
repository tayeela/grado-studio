import io
import sys
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import server as S  # noqa: E402,F401  (sets up paths to the core)

try:
    import ezdxf
    import ogd_all
except ImportError:              # ezdxf lives in the ГРАДО 2 venv (requirements.txt)
    ogd_all = None

CAT = [
    {"code": "f1", "name": "Генплан", "type": "folder", "path": "Генплан"},
    {"code": "virtual1", "name": "Функциональные зоны", "type": "layer", "path": "Генплан / Функциональные зоны"},
    {"code": "virtual2", "name": "Функциональные зоны", "type": "layer", "path": "ПЗЗ / Функциональные зоны"},
    {"code": "virtual2_virtual", "name": "Граница: подзона", "type": "virtual", "path": "Генплан / Граница: подзона"},
    {"code": "far", "name": "Далеко", "type": "layer", "path": "Генплан / Далеко"},
]
SQUARE = {"type": "Polygon", "coordinates": [[[37.60, 55.70], [37.62, 55.70], [37.62, 55.72], [37.60, 55.72], [37.60, 55.70]]]}


@unittest.skipIf(ogd_all is None, "ezdxf not installed")
class OgdAll(unittest.TestCase):
    def test_layer_names_are_unique_and_valid_for_autocad(self):
        names = [x["dxf"] for x in ogd_all.layer_list(CAT)]
        self.assertEqual(len(names), 4)                          # папки не выгружаются, «виртуальные» слои — да
        self.assertEqual(len({n.lower() for n in names}), 4)
        self.assertIn("ОГД-Генплан-Граница_ подзона", names)
        self.assertEqual(ogd_all.layer_list([{"code": "c", "name": "Пятая подзона", "type": "layer",
            "path": "Слои / 11 Сводный план / 2.4 Приаэродромные / Внуково / Пятая подзона"}])[0]["dxf"], "ОГД-11-Внуково-Пятая подзона")
        self.assertFalse(any(set(n) & set('<>/\\":;?*|=`') for n in names))

    def test_xdata_strings_fit_autocad_255_bytes(self):
        tags = ogd_all._xdata({"vri": "Размещение жилых домов " * 30, "n": 1})
        self.assertTrue(all(len(v.encode("utf-8")) <= 255 for _, v in tags))
        self.assertTrue(tags[0][1].startswith("vri=Размещение"))
        long = ogd_all.layer_list([{"code": "c1", "name": "Я" * 300, "type": "layer", "path": "Слои / 1 А / Б / " + "Я" * 300}])
        self.assertLessEqual(len(long[0]["dxf"]), 100)

    def test_drawing_has_layer_per_portal_layer_with_attributes(self):
        layers = [{"dxf": "ОГД-Генплан-Зоны", "title": "Зоны", "code": "v1",
                   "features": [{"geometry": SQUARE, "properties": {"naimfunkzony": "Жилая зона", "summfondpersp": 12.5}}]},
                  {"dxf": "ОГД-Точки", "title": "Точки", "code": "v2",
                   "features": [{"geometry": {"type": "Point", "coordinates": [37.61, 55.71]}, "properties": {"id": 7}}]}]
        with mock.patch.object(ogd_all.dxf_io, "oda_converter", return_value=None):
            body, dwg = ogd_all.build_drawing(layers, SQUARE, (37.59, 55.69, 37.63, 55.73))
        self.assertFalse(dwg)
        z = zipfile.ZipFile(io.BytesIO(body))
        doc = ezdxf.read(io.StringIO(z.read("gisogd.dxf").decode("utf-8")))
        msp = doc.modelspace()
        poly = msp.query('LWPOLYLINE[layer=="ОГД-Генплан-Зоны"]')[0]
        self.assertIn((1000, "naimfunkzony=Жилая зона"), list(poly.get_xdata("GISOGD")))
        self.assertEqual(len(msp.query('LWPOLYLINE[layer=="Рамка листа"]')), 1)
        self.assertEqual(len(msp.query('POINT[layer=="ОГД-Точки"]')), 1)
        self.assertEqual(len(msp.query('LWPOLYLINE[layer=="Граница территории"]')), 1)
        x, y = poly.get_points("xy")[0]                        # МСК: метры в сотнях–тысячах от начала, не градусы
        self.assertGreater(abs(x) + abs(y), 1000)
        csv_text = z.read("атрибуты/ОГД-Генплан-Зоны.csv").decode("utf-8-sig")
        self.assertIn(poly.dxf.handle, csv_text)
        self.assertIn("Жилая зона", csv_text)

    def test_job_clips_skips_empty_and_survives_a_broken_layer(self):
        class FakeApi:
            def __init__(self, **kw):
                pass

            def fetch(self, bbox, code):
                if code == "virtual2":
                    raise ogd_all.ConnectorError("HTTP 500")
                big = {"type": "Polygon", "coordinates": [[[37.5, 55.6], [37.7, 55.6], [37.7, 55.8], [37.5, 55.8], [37.5, 55.6]]]}
                far = {"type": "Point", "coordinates": [38.5, 56.5]}
                return {"features": [{"geometry": far if code == "far" else big, "properties": {"c": code}}]}
        with mock.patch.object(ogd_all, "catalog", return_value=CAT), mock.patch.object(ogd_all, "GisogdApi", FakeApi), \
                mock.patch.object(ogd_all.dxf_io, "oda_converter", return_value=None):
            import tempfile
            with tempfile.TemporaryDirectory() as d:
                job = ogd_all.Job((37.60, 55.70, 37.62, 55.72), SQUARE, Path(d), Path(d) / "out")
                for _ in range(100):
                    if not job.state["running"]:
                        break
                    time.sleep(0.05)
                st = job.state
                self.assertEqual((st["done"], st["total"], st["found"]), (4, 4, 2), st)
                self.assertEqual(len(st["errors"]), 1)
                doc = ezdxf.read(io.StringIO(zipfile.ZipFile(job.file).read("gisogd.dxf").decode("utf-8")))
                xs = [x for e in doc.modelspace().query("LWPOLYLINE") for x, _ in e.get_points("xy")]
                self.assertLess(max(xs) - min(xs), 1400)       # полигон 0,2° обрезан по рамке 0,02° (~1,26 км)
                calls = []                                     # второй раз слой, который портал не отдал, не ждут
                FakeApi.fetch = lambda self, bbox, code, f=FakeApi.fetch: calls.append(code) or f(self, bbox, code)
                job = ogd_all.Job((37.60, 55.70, 37.62, 55.72), None, Path(d), Path(d) / "out")
                while job.state["running"]:
                    time.sleep(0.05)
                self.assertNotIn("virtual2", calls)
                self.assertIn("пропущен", job.state["errors"][0])


if __name__ == "__main__":
    unittest.main()
