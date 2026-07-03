import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import studio_core  # noqa: E402

FEATURES = [
    {"kind": "boundary", "ring": [[0, 0], [500, 0], [500, 300], [0, 300]],
     "props": {}},
    {"kind": "restrict", "ring": [[0, 0], [200, 0], [200, 100], [0, 100]],
     "props": {}},
    {"kind": "zone", "ring": [[0, 100], [500, 100], [500, 300], [0, 300]],
     "props": {"zone_title": "Ж-1"}},
    {"kind": "building", "ring": [[50, 150], [80, 150], [80, 170], [50, 170]],
     "props": {"floors": 10}},
    {"kind": "redline", "line": [[0, 120], [500, 120]], "props": {}},
    {"kind": "social", "point": [400, 200], "props": {"capacity": 500}},
]


class TestStudioCore(unittest.TestCase):
    def test_build_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(Path(tmp) / "s.grado", "Тест", FEATURES)
            codes = {i["code"] for i in p.layers()}
            self.assertEqual(codes, {"terr.boundary", "terr.restrict",
                                     "tp.func_zone", "oks.building",
                                     "pp.red_line", "social.object"})
            self.assertAlmostEqual(p.layer("terr.boundary").area_ha(), 15.0)
            f = next(p.layer("oks.building").features())
            self.assertEqual(f["attrs"]["floors"], 10)
            # координаты ушли в СК проекта (смещение ORIGIN)
            x = f["geom"]["coordinates"][0][0][0]
            self.assertGreater(x, 400000)
            p.close()

    def test_compute_tep(self):
        out = studio_core.compute_tep(FEATURES, {"density": 25, "ratio_zh": 80})
        self.assertAlmostEqual(out["inputs"]["terr_area"], 15.0)
        self.assertAlmostEqual(out["inputs"]["restrict_area"], 2.0)
        pop = next(r for r in out["results"] if r["id"] == "population")
        self.assertEqual(pop["value"], 4814)
        # факт по посадке: 30×20 м × 10 этажей = 6 тыс. м²
        self.assertAlmostEqual(out["fact"]["spp"], 6.0)
        self.assertAlmostEqual(out["fact"]["density"], round(6.0 / 13.0, 2))

    def test_empty_features_defaults(self):
        out = studio_core.compute_tep([])
        self.assertGreater(out["inputs"]["terr_area"], 0)
        self.assertEqual(out["fact"]["spp"], 0)

    def test_make_album(self):
        pdf = studio_core.make_album(FEATURES, "Тестовая концепция",
                                     {"density": 25, "ratio_zh": 80})
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(b"/Count 5", pdf)

    def test_redline_fillet_applied(self):
        feat = [{"kind": "redline", "props": {"radius": 20},
                 "line": [[0, 0], [100, 0], [100, 100]]}]
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(Path(tmp) / "r.grado", "Т", feat)
            f = next(p.layer("pp.red_line").features())
            coords = f["geom"]["coordinates"]
            self.assertGreater(len(coords), 3, "угол заменён дугой (линеаризация)")
            self.assertAlmostEqual(p.layer("pp.red_line").length_m(),
                                   2 * 80 + 3.14159 * 20 / 2, delta=0.1)
            p.close()

    def test_redline_radius_too_big_falls_back(self):
        feat = [{"kind": "redline", "props": {"radius": 500},
                 "line": [[0, 0], [100, 0], [100, 100]]}]
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(Path(tmp) / "r.grado", "Т", feat)
            f = next(p.layer("pp.red_line").features())
            self.assertEqual(len(f["geom"]["coordinates"]), 3,
                             "радиус не помещается — ломаная без сопряжения")
            p.close()

    def test_import_nspd_capture(self):
        merc = [[4187345.5, 7509247.8], [4187445.5, 7509247.8],
                [4187445.5, 7509347.8], [4187345.5, 7509247.8]]
        payload = {"type": "FeatureCollection", "grado_source": "nspd",
                   "features": [{"type": "Feature",
                                 "geometry": {"type": "Polygon", "coordinates": [merc]},
                                 "properties": {"options": {
                                     "cad_num": "77:09:0004021:181",
                                     "land_record_category_type": "земли нас. пунктов"}}}]}
        out = studio_core.import_nspd(payload)
        self.assertEqual(len(out["features"]), 1)
        f = out["features"][0]
        self.assertEqual(f["kind"], "parcel")
        self.assertEqual(f["props"]["cad_num"], "77:09:0004021:181")
        x, y = f["ring"][0]
        # локальные метры холста: UTM минус ORIGIN, порядок сотен метров/км
        self.assertAlmostEqual(x, 98, delta=15)
        self.assertAlmostEqual(y, 1371, delta=15)
        # круговой путь: parcel → проект → слой cad.parcel
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(Path(tmp) / "n.grado", "Т", out["features"])
            pf = next(p.layer("cad.parcel").features())
            self.assertEqual(pf["attrs"]["cad_num"], "77:09:0004021:181")
            p.close()

    def test_grado_roundtrip(self):
        """Сохранили .grado → открыли обратно: фигуры и свойства на месте."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rt.grado"
            studio_core.build_project(path, "Круговой тест", FEATURES).close()
            out = studio_core.grado_to_features(path)
        self.assertEqual(out["name"], "Круговой тест")
        kinds = sorted(f["kind"] for f in out["features"])
        self.assertEqual(kinds, ["boundary", "building", "redline",
                                 "restrict", "social", "zone"])
        boundary = next(f for f in out["features"] if f["kind"] == "boundary")
        self.assertEqual([[round(x, 6), round(y, 6)] for x, y in boundary["ring"]],
                         [[0, 0], [500, 0], [500, 300], [0, 300]])
        bld = next(f for f in out["features"] if f["kind"] == "building")
        self.assertEqual(bld["props"]["floors"], 10)
        zone = next(f for f in out["features"] if f["kind"] == "zone")
        self.assertEqual(zone["props"]["zone_title"], "Ж-1")
        soc = next(f for f in out["features"] if f["kind"] == "social")
        self.assertEqual([round(v, 6) for v in soc["point"]], [400, 200])
        self.assertEqual(soc["props"]["capacity"], 500)

    def test_import_fgistp_polygons_to_zones(self):
        payload = {
            "type": "FeatureCollection", "grado_source": "fgis_tp",
            "grado_layer_name": "ФГИС ТП — Карта функциональных зон",
            "grado_uin": "7" * 25,
            "features": [
                {"type": "Feature",
                 "geometry": {"type": "Polygon", "coordinates": [[
                     [37.6155646254, 55.7522242128], [37.617, 55.7522242128],
                     [37.617, 55.753], [37.6155646254, 55.7522242128]]]},
                 "properties": {"class_name": "Жилые зоны", "mt_status": 1}},
                {"type": "Feature",
                 "geometry": {"type": "LineString",
                              "coordinates": [[37.6, 55.75], [37.62, 55.75]]},
                 "properties": {"class_name": "Дороги"}},
            ]}
        out = studio_core.import_fgistp(payload)
        self.assertEqual(len(out["features"]), 1)
        z = out["features"][0]
        self.assertEqual(z["kind"], "zone")
        self.assertEqual(z["props"]["zone_title"], "Жилые зоны")
        x, y = z["ring"][0]
        self.assertAlmostEqual(x, 98, delta=15)
        self.assertAlmostEqual(y, 1371, delta=15)
        self.assertTrue(any("пропущено" in n for n in out["notes"]))

    def test_make_dxf(self):
        data = studio_core.make_dxf(FEATURES, "Тест DXF")
        text = data.decode("cp1251")
        self.assertTrue(text.startswith("0\nSECTION"))
        for layer in ("GRANICA_TERRITORII", "KRASNYE_LINII", "ZDANIYA"):
            self.assertIn(layer, text)
        self.assertIn("Ж-1", text)

    def test_redline_offset_with_fillet(self):
        def length(pts):
            return sum(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
                       for a, b in zip(pts, pts[1:]))
        line = [[0, 0], [100, 0], [100, 100]]
        import math
        left = studio_core.redline_offset(line, 20, 10)   # влево: r 20 → 10
        self.assertAlmostEqual(length(left), 160 + math.pi * 10 / 2, delta=0.05)
        right = studio_core.redline_offset(line, 20, -10)  # вправо: r 20 → 30
        self.assertAlmostEqual(length(right), 160 + math.pi * 30 / 2, delta=0.05)

    def test_redline_offset_collapse_raises(self):
        from grado_geom import CurveError
        with self.assertRaises(CurveError):
            studio_core.redline_offset([[0, 0], [100, 0], [100, 100]], 20, 25)

    def test_redline_stations(self):
        import math
        # fillet R=20: длина 2×80 + π·20/2 ≈ 191.416
        st = studio_core.redline_stations([[0, 0], [100, 0], [100, 100]], 20, 50)
        self.assertEqual([round(p["s"]) for p in st], [0, 50, 100, 150, 191])
        self.assertAlmostEqual(st[-1]["s"], 160 + math.pi * 10, places=2)
        self.assertAlmostEqual(st[0]["a"], 0, places=6, msg="касательная в начале — вдоль +x")
        self.assertAlmostEqual(st[-1]["a"], math.pi / 2, places=6,
                               msg="касательная в конце — вдоль +y")
        # конечная точка совпадает с концом линии
        self.assertAlmostEqual(st[-1]["x"], 100, places=6)
        self.assertAlmostEqual(st[-1]["y"], 100, places=6)

    def test_zones_report_coverage_ok(self):
        feats = [
            {"kind": "zone", "props": {"zone_title": "Ж-1"},
             "ring": [[0, 0], [100, 0], [100, 100], [0, 100]]},
            {"kind": "zone", "props": {"zone_title": "О-1"},
             "ring": [[100, 0], [200, 0], [200, 100], [100, 100]]},
        ]
        rep = studio_core.zones_report(feats)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["zones"], 2)
        self.assertAlmostEqual(rep["total_ha"], 2.0)
        self.assertEqual(rep["shared_edges"], 1)

    def test_zones_report_overlap(self):
        feats = [
            {"kind": "zone", "props": {"zone_title": "А"},
             "ring": [[0, 0], [100, 0], [100, 100], [0, 100]]},
            {"kind": "zone", "props": {"zone_title": "Б"},
             "ring": [[0, 0], [100, 0], [100, 100], [0, 100]]},
        ]
        rep = studio_core.zones_report(feats)
        self.assertFalse(rep["ok"])
        self.assertTrue(rep["error"])

    def test_zones_report_disjoint(self):
        feats = [
            {"kind": "zone", "props": {"zone_title": "А"},
             "ring": [[0, 0], [100, 0], [100, 100], [0, 100]]},
            {"kind": "zone", "props": {"zone_title": "Б"},
             "ring": [[300, 0], [400, 0], [400, 100], [300, 100]]},
        ]
        rep = studio_core.zones_report(feats)
        self.assertFalse(rep["ok"], "разорванные зоны — не покрытие")

    def test_zones_report_single_zone_none(self):
        self.assertIsNone(studio_core.zones_report(
            [{"kind": "zone", "props": {}, "ring": [[0, 0], [1, 0], [1, 1]]}]))

    def test_tep_includes_zones(self):
        out = studio_core.compute_tep(FEATURES)
        self.assertIn("zones", out)

    def test_make_print(self):
        pdf, scale = studio_core.make_print(FEATURES, "Печать")
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(b"/Count 1", pdf)
        self.assertIn(scale, [500, 1000, 2000, 2500, 5000, 10000, 20000,
                              25000, 50000])
        pdf2, s2 = studio_core.make_print(FEATURES, "Печать", scale=2000, paper="A3")
        self.assertEqual(s2, 2000)

    def test_dxf_includes_dims(self):
        feats = FEATURES + [{"kind": "dim", "props": {},
                             "line": [[0, 0], [120, 0]]}]
        text = studio_core.make_dxf(feats, "С размерами").decode("cp1251")
        self.assertIn("RAZMERY", text)
        self.assertIn("120.0 м", text)
        self.assertTrue(text.rstrip().endswith("EOF"), "вставка не сломала структуру")
        self.assertEqual(text.count("0\nENDSEC"), 3)

    def test_make_grado_is_sqlite(self):
        data = studio_core.make_grado(FEATURES, "Тест")
        self.assertTrue(data.startswith(b"SQLite format 3"))


if __name__ == "__main__":
    unittest.main()
