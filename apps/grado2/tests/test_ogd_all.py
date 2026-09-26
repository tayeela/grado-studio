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
    {"id": 1, "parent_id": 0, "code": "f0", "name": "Слои", "type": "folder", "path": "Слои"},
    {"id": 2, "parent_id": 1, "code": "f1", "name": "1 Генплан", "type": "folder", "path": "Слои / 1 Генплан"},
    {"id": 3, "parent_id": 2, "code": "virtual1", "name": "Функциональные зоны", "type": "layer", "path": "Слои / 1 Генплан / Функциональные зоны"},
    {"id": 4, "parent_id": 1, "code": "f2", "name": "3 ПЗЗ", "type": "folder", "path": "Слои / 3 ПЗЗ"},
    {"id": 5, "parent_id": 4, "code": "virtual2", "name": "Функциональные зоны", "type": "layer", "path": "Слои / 3 ПЗЗ / Функциональные зоны"},
    {"id": 6, "parent_id": 2, "code": "virtual2_virtual", "name": "Граница: подзона", "type": "virtual", "path": "Слои / 1 Генплан / Граница: подзона"},
    {"id": 7, "parent_id": 0, "code": "t0", "name": "Территория", "type": "folder", "path": "Территория"},
    {"id": 8, "parent_id": 7, "code": "far", "name": "Далеко", "type": "layer", "path": "Территория / Далеко"},
]
SQUARE = {"type": "Polygon", "coordinates": [[[37.60, 55.70], [37.62, 55.70], [37.62, 55.72], [37.60, 55.72], [37.60, 55.70]]]}


@unittest.skipIf(ogd_all is None, "ezdxf not installed")
class OgdAll(unittest.TestCase):
    def test_layer_names_follow_portal_tree_order_and_are_valid_for_autocad(self):
        L = ogd_all.layer_list(CAT)
        names = [x["dxf"] for x in L]
        self.assertEqual([x["code"] for x in L], ["virtual1", "virtual2_virtual", "virtual2", "far"])   # порядок портала
        self.assertEqual(names, sorted(names))                  # AutoCAD сортирует по имени — порядок тот же
        self.assertEqual(names[0], "ОГД 01.01 1 Генплан - Функциональные зоны")
        self.assertEqual(names[3], "ОГД Т.01 Территория - Далеко")
        self.assertFalse(any(set(n) & set('<>/\\":;?*|,=`') for n in names))
        comma = ogd_all.layer_list([{"id": 1, "parent_id": 0, "name": "Слои", "type": "folder"},
                                    {"id": 2, "parent_id": 1, "code": "c", "type": "layer",
                                     "name": "Границы зон (монорельс,  канатная дорога, фуникулер)"}])[0]["dxf"]
        self.assertNotIn(",", comma)                       # AutoCAD не открывает файл со слоем с запятой
        self.assertNotIn("  ", comma)
        self.assertEqual([x["code"] for x in ogd_all.layer_list(CAT, {"far", "virtual1"})], ["virtual1", "far"])
        tree = ogd_all.catalog_tree(CAT)
        self.assertEqual([n["name"] for n in tree], ["Слои", "Территория"])
        self.assertEqual(tree[0]["children"][1]["children"][0]["code"], "virtual2")

    def test_xdata_strings_fit_autocad_255_bytes(self):
        tags = ogd_all._xdata({"vri": "Размещение жилых домов " * 30, "n": 1})
        self.assertTrue(all(len(v.encode("utf-8")) <= 255 for _, v in tags))
        self.assertTrue(tags[0][1].startswith("vri=Размещение"))
        long = ogd_all.layer_list([{"id": 1, "parent_id": 0, "name": "Б" * 300, "type": "folder"}, {"id": 2, "parent_id": 1, "code": "c1", "name": "Я" * 300, "type": "layer"}])
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

    def test_sheet_drawing_is_cut_in_msk_and_has_paper_layout_at_scale(self):
        c = list(ogd_all.crs.wgs84_to_msk(37.61, 55.71))
        sheet = {"c": c, "w": 840, "h": 594, "paper": [420, 297], "scale": 2000, "title": "Опорный"}
        layers = [{"dxf": "ОГД-Зоны", "title": "Зоны", "code": "v1", "color": "#ff8800",
                   "features": [{"geometry": SQUARE, "properties": {"a": 1}}]}]
        with mock.patch.object(ogd_all.dxf_io, "oda_converter", return_value=None):
            body, _ = ogd_all.build_drawing(layers, None, sheet=sheet)
        doc = ezdxf.read(io.StringIO(zipfile.ZipFile(io.BytesIO(body)).read("gisogd.dxf").decode("utf-8")))
        pts = [p for p in doc.modelspace().query('LWPOLYLINE[layer=="ОГД-Зоны"]')[0].get_points("xy")]
        self.assertLessEqual(max(p[0] for p in pts) - min(p[0] for p in pts), 840.001)     # полигон 1,2 км обрезан по листу
        self.assertEqual(doc.layers.get("ОГД-Зоны").rgb, (255, 136, 0))
        lay = doc.layouts.get("Лист Опорный 1-2000")
        vp = lay.query("VIEWPORT")[-1]
        self.assertAlmostEqual(vp.dxf.height / vp.dxf.view_height * 1000, 1000 / 2000 * 1000)   # 297 мм на 594 м = 1:2000
        self.assertEqual(ogd_all.portal_color("line-color: #0a4;\npolygon-fill: #ffffff;"), "#00aa44")
        # AutoCAD открывает сохранённый вид: границы и вид модели — на лист, а не 0,0 (иначе пустой экран)
        ex0, ex1 = doc.header["$EXTMIN"], doc.header["$EXTMAX"]
        self.assertTrue(ex0[0] < c[0] < ex1[0] and ex0[1] < c[1] < ex1[1])
        vp = doc.viewports.get("*Active")[0]
        self.assertAlmostEqual(vp.dxf.center[0], c[0], delta=1)
        self.assertGreater(vp.dxf.height, 594)
        self.assertEqual([l.name for l in doc.layouts], ["Model", "Лист Опорный 1-2000"])
        self.assertEqual(doc.layouts.get("Лист Опорный 1-2000").dxf_layout.dxf.taborder, 1)

    def test_sprit_lines_get_redln97_linetypes_and_shx(self):
        redln = {"lib": S.REDLN, "idx": S.REDLN_IDX, "colors": S.LGR_COLORS}
        line = {"type": "LineString", "coordinates": [[37.605, 55.705], [37.615, 55.715]]}
        layers = [{"dxf": "ОГД 11.01.01.02 Красные линии", "title": "Красные линии", "code": "l1",
                   "features": [{"geometry": line, "properties": {"linelineco": "1"}}]},
                  {"dxf": "ОГД Зоны", "title": "Зоны", "code": "v", "features": [{"geometry": SQUARE, "properties": {}}]}]
        with mock.patch.object(ogd_all.dxf_io, "oda_converter", return_value=None):
            body, _ = ogd_all.build_drawing(layers, None, (37.59, 55.69, 37.63, 55.73), redln=redln)
        z = zipfile.ZipFile(io.BytesIO(body))
        self.assertIn("red_lns.shx", z.namelist())
        self.assertIn("REDLN97.LIN", z.namelist())
        doc = ezdxf.read(io.StringIO(z.read("gisogd.dxf").decode("utf-8")))
        red = doc.modelspace().query('LWPOLYLINE[layer=="ОГД 11.01.01.02 Красные линии"]')[0]
        self.assertIn(red.dxf.linetype, doc.linetypes)
        self.assertTrue(red.dxf.linetype.upper().startswith("L"))
        self.assertTrue(red.dxf.hasattr("true_color"))            # цвет ЛГР
        self.assertTrue(red.dxf.flags & 128)                       # образец идёт по всей полилинии, а не с каждой вершины
        zone = doc.modelspace().query('LWPOLYLINE[layer=="ОГД Зоны"]')[0]
        self.assertFalse(zone.dxf.hasattr("linetype"))            # без кода линии — обычная линия слоя

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
