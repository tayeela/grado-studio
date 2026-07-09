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

    def test_build_project_skips_malformed_feature(self):
        # объект с kind="zone" (ring-геометрия), но реальная геометрия — line
        # (напр. старый холст-баг маршрутизации) — не должен ронять весь экспорт
        broken = {"id": 999, "kind": "zone", "layer_id": "project.tp.func_zone",
                 "line": [[0, 0], [10, 10]], "props": {"zone_title": "битый"}}
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(Path(tmp) / "s.grado", "Тест",
                                          FEATURES + [broken])
            # остальные объекты собрались как обычно, битый — тихо пропущен
            codes = {i["code"] for i in p.layers()}
            self.assertIn("tp.func_zone", codes)
            self.assertEqual(sum(1 for _ in p.layer("tp.func_zone").features()), 1)
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
        # phase 4 basic rule checks
        self.assertIn("checks", out)
        self.assertTrue(any("Плотность" in c["title"] for c in out.get("checks", [])))

    def test_empty_features_defaults(self):
        out = studio_core.compute_tep([])
        self.assertGreater(out["inputs"]["terr_area"], 0)
        self.assertEqual(out["fact"]["spp"], 0)

    def test_style_overrides_affect_all_outputs(self):
        # правка эталонного знака видна на холсте (frontend_styles, px), в
        # библиотеке по id и в стиле слоя по коду (PDF, мм); сброс — эталон
        import grado_render.style as S
        try:
            studio_core.apply_style_overrides(
                {"boundary.line": {"width_px": 6, "width_mm": 3, "stroke": "#00ff00"}})
            self.assertEqual(studio_core.frontend_styles()["boundary.line"]["width"], 6)
            self.assertEqual(S.StyleSet().resolve_id("boundary.line").width, 3)
            self.assertEqual(S.StyleSet().resolve("terr.boundary").width, 3)  # слой по коду
            self.assertAlmostEqual(S.StyleSet().resolve_id("boundary.line").stroke[1], 1.0)
        finally:
            studio_core.apply_style_overrides({})
        self.assertNotEqual(studio_core.frontend_styles()["boundary.line"]["width"], 6)

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

    def test_arc_roundtrip(self):
        """Дуга (parametric arc) сохраняется в .grado через attrs и восстанавливается при открытии."""
        arc_feat = [{
            "kind": "redline",
            "layer_id": "project.apo.red_lines",
            "line": [[0, 0], [100, 0]],
            "arc": {"cx": 50, "cy": 0, "r": 50, "a0": 0, "sweep": 1.5708},
            "props": {}
        }]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "arc.grado"
            studio_core.build_project(path, "Дуга тест", arc_feat).close()
            out = studio_core.grado_to_features(path)
        arcs = [f for f in out["features"] if f.get("arc")]
        self.assertEqual(len(arcs), 1, "arc должен вернуться как parametric")
        a = arcs[0]["arc"]
        self.assertAlmostEqual(a["cx"], 50, delta=0.1)
        self.assertAlmostEqual(a["r"], 50, delta=0.1)
        self.assertGreater(a.get("sweep", 0), 1.0)
        # props не должны тащить arc_*
        self.assertNotIn("arc_cx", arcs[0].get("props", {}))

    def test_circle_roundtrip_and_buffer(self):
        """Окружность для радиусов/буферов: roundtrip + можно создать как буфер точки."""
        circ_feat = [{
            "kind": "social",
            "layer_id": "project.social.objects",
            "point": [100, 50],
            "circle": {"cx": 100, "cy": 50, "r": 300},
            "props": {"capacity": 200}
        }]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "circ.grado"
            studio_core.build_project(path, "Окружность тест", circ_feat).close()
            out = studio_core.grado_to_features(path)
        circs = [f for f in out["features"] if f.get("circle")]
        self.assertEqual(len(circs), 1)
        c = circs[0]["circle"]
        self.assertAlmostEqual(c["cx"], 100, delta=0.1)
        self.assertAlmostEqual(c["r"], 300, delta=0.1)
        self.assertNotIn("circle", circs[0].get("props", {}))  # не в props
        # buffer-like: точка + радиус даёт окружность
        self.assertEqual(circs[0]["props"].get("capacity"), 200)

    def test_make_buffer(self):
        """Генерация буферов: точка → circle, линия → офсет."""
        feats = [
            {"kind": "social", "point": [0, 0], "props": {}},
            {"kind": "redline", "line": [[0, 0], [100, 0]], "props": {}}
        ]
        bufs = studio_core.make_buffer(feats, 50, fillet=0, sides="both")
        circles = [b for b in bufs if b.get("circle")]
        lines = [b for b in bufs if b.get("line")]
        self.assertEqual(len(circles), 1)
        self.assertAlmostEqual(circles[0]["circle"]["r"], 50)
        self.assertGreaterEqual(len(lines), 1)  # at least one offset line
        # check props carry over
        self.assertIn("_buffer_dist", lines[0].get("props", {}))

    def test_arc_trim_preserve(self):
        """Тест логики: arc features сохраняют параметры после roundtrip (trim симулируется в UI, здесь проверка roundtrip)."""
        arc_feat = [{
            "kind": "redline",
            "layer_id": "project.apo.red_lines",
            "line": [[0,0],[100,0]],
            "arc": {"cx": 50, "cy": 0, "r": 50, "a0": 0, "sweep": 1.57},
            "props": {}
        }]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "arc.grado"
            studio_core.build_project(path, "Arc test", arc_feat).close()
            out = studio_core.grado_to_features(path)
        arcs = [f for f in out["features"] if f.get("arc")]
        self.assertEqual(len(arcs), 1)
        a = arcs[0]["arc"]
        self.assertAlmostEqual(a["r"], 50, delta=0.1)
        self.assertGreater(a.get("sweep", 0), 1.0)

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

    def test_circle_as_potential_trim_boundary_roundtrip(self):
        """Окружности должны roundtrip'иться и быть доступны как границы обрезки/продления
        (логика trim — в UI на клик+circleIntersect; здесь проверяем что circle + line сожительствуют и сохраняются)."""
        feats = [
            {"kind": "redline", "layer_id": "project.apo.red_lines", "line": [[0, 0], [300, 0]], "props": {}},
            {"kind": "circle", "layer_id": "project.apo.red_lines", "circle": {"cx": 150, "cy": 0, "r": 80}, "props": {}}
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c4b.grado"
            studio_core.build_project(path, "Circle boundary test", feats).close()
            out = studio_core.grado_to_features(path)
        circs = [f for f in out["features"] if f.get("circle")]
        lines = [f for f in out["features"] if f.get("line")]
        self.assertEqual(len(circs), 1)
        self.assertEqual(len(lines), 1)
        self.assertAlmostEqual(circs[0]["circle"]["r"], 80, delta=0.1)


FAKE_JPEG = bytes([0xFF, 0xD8, 0xFF, 0xC0, 0x00, 0x0B, 0x08,
                   0x00, 0x01, 0x00, 0x02, 0x03])


class TestUnderlay(unittest.TestCase):
    """Подложка листов: тайлы подменены — тесты не ходят в сеть."""

    CENTER = (413250.0, 6178150.0)  # центр FEATURES в UTM
    RECT = (12, 10, 280, 277)

    def setUp(self):
        self._orig = studio_core._tile_jpeg
        studio_core._tile_jpeg = lambda z, x, y, source="osm": FAKE_JPEG

    def tearDown(self):
        studio_core._tile_jpeg = self._orig

    def test_tile_math_roundtrip(self):
        xt, yt = studio_core._tile_xy(37.614292, 55.739888, 17)
        lon, lat = studio_core._tile_lonlat(xt, yt, 17)
        self.assertAlmostEqual(lon, 37.614292, places=9)
        self.assertAlmostEqual(lat, 55.739888, places=9)

    def test_underlay_covers_frame(self):
        ops = studio_core.tile_underlay(self.CENTER, self.RECT, 2000)
        self.assertGreater(len(ops), 10)
        self.assertLessEqual(len(ops), studio_core.MAX_UNDERLAY_TILES)
        xs = [p[0] for o in ops for p in o["quad"]]
        ys = [p[1] for o in ops for p in o["quad"]]
        fx, fy, fw, fh = self.RECT
        self.assertLess(min(xs), fx)
        self.assertGreater(max(xs), fx + fw)
        self.assertLess(min(ys), fy)
        self.assertGreater(max(ys), fy + fh)

    def test_underlay_rotated_to_utm_grid(self):
        # Web Mercator повёрнут к сетке UTM на сближение меридианов
        # (~1.1° под Москвой) — quad обязан это нести
        import math
        op = studio_core.tile_underlay(self.CENTER, self.RECT, 2000)[0]
        (tlx, tly), (trx, tr_y), _ = op["quad"]
        angle = abs(math.degrees(math.atan2(tr_y - tly, trx - tlx)))
        self.assertGreater(angle, 0.5)
        self.assertLess(angle, 2.0)

    def test_album_with_basemap_gets_ortho_sheet(self):
        # ortho добавляется только если явно в album_config['sheets'] (управляется юзером)
        # + basemap=True даёт underlay
        pdf = studio_core.make_album(
            FEATURES, "Тест", basemap=True,
            album_config={"sheets": ["title", "location", "base", "apo", "tep", "ortho"]}
        )
        self.assertIn(b"/Count 6", pdf, "добавился лист «Ортофотоплан»")
        self.assertIn(b"/Filter /DCTDecode", pdf)
        # все тайлы-заглушки одинаковы → в PDF ровно один XObject
        self.assertEqual(pdf.count(b"/Subtype /Image"), 1)

    def test_album_offline_skips_ortho(self):
        def fail(z, x, y, source="osm"):
            raise OSError("нет сети")
        studio_core._tile_jpeg = fail
        # запрашиваем ortho в конфиге, но подложка падает → builder вернёт None, лист не добавится
        pdf = studio_core.make_album(
            FEATURES, "Тест", basemap=True,
            album_config={"sheets": ["title", "location", "base", "apo", "tep", "ortho"]}
        )
        self.assertIn(b"/Count 5", pdf, "орто-лист пропущен при сбое подложки")
        self.assertNotIn(b"/DCTDecode", pdf)

    def test_print_with_basemap(self):
        pdf, scale = studio_core.make_print(FEATURES, "Печать", basemap=True)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertIn(b"/Filter /DCTDecode", pdf)

    def test_canvas_style_resolves_inline(self):
        # inline-знак «как на холсте» резолвится ПЕРЕД библиотекой; #e3007b →
        # rgb(0.890, 0, 0.482); библиотечные id и дальше работают
        from grado_render import StyleSet
        ss = StyleSet(id_styles={"canvas.0": {"fill": "#e3007b", "stroke": "#3d107b",
                                              "width_mm": 1.4}})
        st = ss.resolve_id("canvas.0")
        self.assertAlmostEqual(st.fill[0], 0.8902, places=3)
        self.assertAlmostEqual(st.fill[2], 0.4824, places=3)
        self.assertEqual(st.width, 1.4)
        self.assertIsNotNone(ss.resolve_id("boundary.line"))   # библиотека цела
        self.assertIsNone(ss.resolve_id("canvas.99"))          # неизвестный inline

    def test_print_canvas_styles_change_output(self):
        # тот же объект печатается по-разному: со своим знаком (canvas_styles)
        # и по стандарту (синтетический id неизвестен → стиль слоя)
        feats = [{"kind": "zone", "layer_id": "project.tp.func_zone",
                  "geometry_type": "polygon", "style_id": "canvas.0",
                  "ring": [[0, 0], [400, 0], [400, 300], [0, 300]],
                  "props": {"zone_title": "Ж-1"}}]
        cs = {"canvas.0": {"fill": "#e3007b", "stroke": "#3d107b", "width_mm": 1.4}}
        pdf_canvas, _ = studio_core.make_print(feats, "Тест", canvas_styles=cs)
        pdf_std, _ = studio_core.make_print(feats, "Тест")
        self.assertTrue(pdf_canvas.startswith(b"%PDF"))
        self.assertTrue(pdf_std.startswith(b"%PDF"))
        self.assertNotEqual(pdf_canvas, pdf_std)   # знак повлиял на вывод

    def test_first_tile_failure_keeps_underlay(self):
        # одиночный сбой (не сетевой) первого тайла — дырка, не потеря всего
        calls = {"n": 0}

        def flaky(z, x, y, source="osm"):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("sips сбой")
            return FAKE_JPEG
        studio_core._tile_jpeg = flaky
        ops = studio_core.tile_underlay(self.CENTER, self.RECT, 2000)
        self.assertGreater(len(ops), 10)

    def test_majority_failure_drops_underlay(self):
        # полупустая мозаика хуже её отсутствия — лист без подложки
        calls = {"n": 0}

        def mostly_fail(z, x, y, source="osm"):
            calls["n"] += 1
            if calls["n"] > 1:
                raise RuntimeError("сбой")
            return FAKE_JPEG
        studio_core._tile_jpeg = mostly_fail
        self.assertEqual(studio_core.tile_underlay(self.CENTER, self.RECT,
                                                   2000), [])

    def test_offline_does_not_retry_every_tile(self):
        # сетевая ошибка гасит дальнейшие загрузки: без этого офлайн-сборка
        # ждала бы таймаут на каждом из ~130 тайлов
        calls = {"n": 0}

        def dead(z, x, y, source="osm"):
            calls["n"] += 1
            raise OSError("сеть недоступна")
        studio_core._tile_jpeg = dead
        old = studio_core.TILE_CACHE
        with tempfile.TemporaryDirectory() as tmp:
            studio_core.TILE_CACHE = Path(tmp)
            try:
                ops = studio_core.tile_underlay(self.CENTER, self.RECT, 2000)
            finally:
                studio_core.TILE_CACHE = old
        self.assertEqual(ops, [])
        self.assertEqual(calls["n"], 1)


FAKE_PNG = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 24 + b"IEND\xaeB`\x82")


class TestTileCache(unittest.TestCase):
    """Дисковый кэш тайлов: битый файл (обрыв записи) перекачивается."""

    def setUp(self):
        self._cache = studio_core.TILE_CACHE
        self._urlopen = studio_core.urllib.request.urlopen
        self._tmp = tempfile.TemporaryDirectory()
        studio_core.TILE_CACHE = Path(self._tmp.name)
        self.calls = []

        outer = self

        class FakeResp:
            def read(self):
                return FAKE_PNG

            def __enter__(self):
                outer.calls.append(1)
                return self

            def __exit__(self, *a):
                return False

        studio_core.urllib.request.urlopen = (
            lambda req, timeout=10, context=None: FakeResp())

    def tearDown(self):
        studio_core.TILE_CACHE = self._cache
        studio_core.urllib.request.urlopen = self._urlopen
        self._tmp.cleanup()

    def test_broken_cache_is_refetched(self):
        p = studio_core.fetch_tile(17, 1, 2, "osm")
        self.assertEqual(p.read_bytes(), FAKE_PNG)
        self.assertEqual(len(self.calls), 1)
        # обрыв записи: файл существует, но неполный → перекачка
        p.write_bytes(FAKE_PNG[:10])
        studio_core.fetch_tile(17, 1, 2, "osm")
        self.assertEqual(p.read_bytes(), FAKE_PNG)
        self.assertEqual(len(self.calls), 2)
        # целый кэш сеть не дёргает
        studio_core.fetch_tile(17, 1, 2, "osm")
        self.assertEqual(len(self.calls), 2)

    def test_valid_png_checks_both_ends(self):
        self.assertTrue(studio_core._valid_jpeg(
            b"\xff\xd8" + b"\x00" * 5 + b"\xff\xd9"))
        self.assertFalse(studio_core._valid_jpeg(b"\xff\xd8\x00"))
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            f.write(FAKE_PNG[:20])
            f.flush()
            self.assertFalse(studio_core._valid_png(Path(f.name)))
            f.seek(0)
            f.write(FAKE_PNG)
            f.flush()
            self.assertTrue(studio_core._valid_png(Path(f.name)))


def _nspd_payload(cad, x=4187000, y=7509000):
    # 3857-координаты около Москвы; коннектор переведёт в WGS84
    return {"grado_source": "nspd", "features": [{"id": cad,
        "geometry": {"type": "Polygon", "coordinates": [[
            [x, y], [x + 100, y], [x + 100, y + 100],
            [x, y + 100], [x, y]]]},
        "properties": {"cad_num": cad}}]}


class TestSourcePipeline(unittest.TestCase):
    """Снимки источников + провенанс + журнал + diff (шаг 6)."""

    def setUp(self):
        from grado_connectors import SnapshotStore
        self._orig = studio_core.SOURCE_STORE
        self._tmp = tempfile.TemporaryDirectory()
        studio_core.SOURCE_STORE = SnapshotStore(Path(self._tmp.name) / "src")

    def tearDown(self):
        studio_core.SOURCE_STORE = self._orig
        self._tmp.cleanup()

    def test_import_creates_snapshot_and_provenance(self):
        out = studio_core.import_nspd(_nspd_payload("77:01:0001"))
        self.assertTrue(out["snapshot"]["id"].startswith("nspd-"))
        self.assertEqual(out["snapshot"]["source"], "nspd")
        self.assertEqual(out["snapshot"]["count"], 1)
        self.assertEqual(out["features"][0]["prov"]["source"], "nspd")
        self.assertEqual(out["features"][0]["prov"]["snapshot"], out["snapshot"]["id"])
        self.assertIsNone(out["diff"], "первый импорт — без diff")

    def test_reimport_idempotent(self):
        a = studio_core.import_nspd(_nspd_payload("77:01:0001"))
        b = studio_core.import_nspd(_nspd_payload("77:01:0001"))
        self.assertEqual(a["snapshot"]["id"], b["snapshot"]["id"])
        self.assertIsNone(b["diff"])
        self.assertEqual(len(studio_core.sources_journal()), 1)

    def test_changed_source_diffs(self):
        # та же территория (те же габариты), заменён участок → diff
        studio_core.import_nspd(_nspd_payload("77:01:0001"))
        out = studio_core.import_nspd(_nspd_payload("77:01:9999"))
        self.assertIsNotNone(out["diff"])
        self.assertIn("77:01:9999", out["diff"]["added"])
        self.assertIn("77:01:0001", out["diff"]["removed"])
        self.assertEqual(len(studio_core.sources_journal()), 2)

    def test_different_territory_no_false_diff(self):
        # другой квартал (другие габариты) — НЕ сравнивается с прошлым
        studio_core.import_nspd(_nspd_payload("77:01:0001", x=4187000, y=7509000))
        out = studio_core.import_nspd(
            _nspd_payload("77:05:0008", x=4200000, y=7520000))
        self.assertIsNone(out["diff"], "разные территории не диффятся")
        self.assertEqual(len(studio_core.sources_journal()), 2)

    def test_snapshot_survives_roundtrip(self):
        feats = studio_core.import_nspd(_nspd_payload("77:01:0001"))["features"]
        sid = feats[0]["prov"]["snapshot"]
        with tempfile.TemporaryDirectory() as tmp:
            gp = Path(tmp) / "p.grado"
            studio_core.build_project(gp, "RT", feats).close()
            rt = studio_core.grado_to_features(str(gp))
        # source_doc = sid (нет grado_doc) → снимок восстановлен из round-trip
        self.assertEqual(rt["features"][0]["prov"].get("snapshot"), sid)

    def test_provenance_flows_to_grado_and_back(self):
        feats = studio_core.import_nspd(_nspd_payload("77:01:0001"))["features"]
        with tempfile.TemporaryDirectory() as tmp:
            gp = Path(tmp) / "p.grado"
            p = studio_core.build_project(gp, "Провенанс", feats)
            fr = next(p.layer("cad.parcel").features())
            self.assertEqual(fr["source"], "nspd")
            self.assertTrue(fr["source_date"])
            p.close()
            rt = studio_core.grado_to_features(str(gp))
        prov = rt["features"][0].get("prov")
        self.assertEqual(prov["source"], "nspd")

    def test_manual_features_have_no_provenance(self):
        # нарисованное вручную остаётся source=manual
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(Path(tmp) / "m.grado", "Ручной", FEATURES)
            fr = next(p.layer("terr.boundary").features())
            self.assertEqual(fr["source"], "manual")
            p.close()

    def test_fgistp_import_snapshots_and_marks_source(self):
        payload = {"grado_source": "fgis_tp", "grado_uin": "77:00-1",
                   "grado_layer_name": "Генплан",
                   "features": [{"id": "z1", "geometry": {"type": "Polygon",
                        "coordinates": [[[37.6, 55.7], [37.61, 55.7],
                                         [37.61, 55.71], [37.6, 55.7]]]},
                        "properties": {"class_name": "Ж-1", "uin": "77:00-1"}}]}
        out = studio_core.import_fgistp(payload)
        self.assertEqual(out["snapshot"]["source"], "fgistp")
        self.assertEqual(out["features"][0]["prov"]["source"], "fgistp")


class TestModel01Routing(unittest.TestCase):
    """MODEL-01b: маршрутизация по layer_id, выделенный source-слой, стиль."""

    def test_fgistp_routes_to_dedicated_source_layer(self):
        payload = {"grado_source": "fgis_tp", "grado_uin": "77:00-1",
                   "grado_layer_name": "Генплан",
                   "features": [{"id": "z1", "geometry": {"type": "Polygon",
                        "coordinates": [[[37.6, 55.7], [37.61, 55.7],
                                         [37.61, 55.71], [37.6, 55.7]]]},
                        "properties": {"class_name": "Ж-исх", "uin": "77:00-1"}}]}
        out = studio_core.import_fgistp(payload)
        self.assertEqual(out["features"][0]["layer_id"], "source.fgistp.func_zones")

    def test_two_layers_of_one_class_in_grado(self):
        feats = [
            {"kind": "boundary", "layer_id": "project.territory.boundary",
             "ring": [[0, 0], [500, 0], [500, 300], [0, 300]], "props": {}},
            {"kind": "zone", "layer_id": "project.tp.func_zone",
             "ring": [[0, 0], [500, 0], [500, 150], [0, 150]],
             "props": {"zone_title": "Ж-пр"}, "style_id": "func_zone.fill"},
            {"kind": "zone", "layer_id": "source.fgistp.func_zones",
             "ring": [[0, 150], [500, 150], [500, 300], [0, 300]],
             "props": {"zone_title": "Ж-исх"},
             "prov": {"source": "fgistp", "source_date": "2026-07-04",
                      "source_doc": "77:00-1"}},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            gp = Path(tmp) / "m.grado"
            p = studio_core.build_project(gp, "M01", feats)
            layers = p.layers()
            classes = [L["semantic_class"] for L in layers]
            self.assertEqual(classes.count("tp.func_zone"), 2, "два слоя класса")
            src = p.layer_by_id("source.fgistp.func_zones")
            self.assertEqual(src.source_kind, "fgistp")
            self.assertEqual(next(src.features())["source"], "fgistp")
            proj = p.layer_by_id("project.tp.func_zone")
            self.assertEqual(next(proj.features())["style_id"], "func_zone.fill")
            p.close()
            rt = studio_core.grado_to_features(str(gp))
        ids = {f["layer_id"] for f in rt["features"]}
        self.assertIn("source.fgistp.func_zones", ids)
        self.assertIn("project.tp.func_zone", ids)

    def test_legacy_feature_without_layer_id_routes_by_kind(self):
        # объект без layer_id (старая сцена) роутится по kind как раньше
        feats = [{"kind": "building",
                  "ring": [[0, 0], [30, 0], [30, 20], [0, 20]],
                  "props": {"floors": 9}}]
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(Path(tmp) / "l.grado", "Legacy", feats)
            self.assertEqual([L["layer_id"] for L in p.layers()],
                             ["project.apo.buildings"])
            p.close()

    def test_user_layer_fields_export_as_columns(self):
        # произвольные поля атрибутивной таблицы студии уезжают колонками .grado
        # с приведением типов из манифеста слоя (обмен с QGIS)
        feats = [{"kind": "generic", "layer_id": "user.trees",
                  "ring": [[0, 0], [40, 0], [40, 40], [0, 40]],
                  "props": {"Порода": "липа", "Кол-во": "37", "Пусто": ""}}]
        manifest = [{"layer_id": "user.trees", "code": "generic.polygon",
                     "title": "Озеленение", "stage": "project",
                     "style_id": "func_zone.fill",
                     "fields": [{"name": "Порода", "type": "text"},
                                {"name": "Кол-во", "type": "int"},
                                {"name": "Пусто", "type": "real"}]}]
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(Path(tmp) / "f.grado", "Поля",
                                          feats, layers=manifest)
            L = p.layer_by_id("user.trees")
            self.assertEqual([f["id"] for f in L.user_fields],
                             ["Порода", "Кол-во", "Пусто"])
            f = next(L.features())
            self.assertEqual(f["attrs"]["Порода"], "липа")
            self.assertEqual(f["attrs"]["Кол-во"], 37)     # "37" → int
            self.assertIsNone(f["attrs"]["Пусто"])         # пустая строка → None
            p.close()


class TestRolesTep(unittest.TestCase):
    """ТЭП по ролям слоёв, а не по литералам kind (шаг 4)."""

    def test_terr_and_restrict_from_roles(self):
        # площади входов берутся по tep_role, не по kind
        out = studio_core.compute_tep(FEATURES)
        self.assertAlmostEqual(out["inputs"]["terr_area"], 15.0, places=2)
        self.assertGreater(out["inputs"]["restrict_area"], 0)

    def test_fact_spp_from_building_role(self):
        out = studio_core.compute_tep(FEATURES)
        # одно здание 30×20 м × 10 этажей = 6.0 тыс. м²
        self.assertAlmostEqual(out["fact"]["spp"], 6.0, places=1)

    def test_new_building_layer_counts_without_code_change(self):
        # критерий шага 4: новый слой-здание учитывается в ТЭП без правки
        # compute_tep — только запись в классификаторе + карту kind→код
        import copy
        from grado_model.classifier import ClassifierClass
        orig_cls, orig_map = studio_core.CLASSIFIER, dict(studio_core.KIND_TO_CODE)
        cls = copy.deepcopy(orig_cls)
        cls.classes["oks.pavilion"] = ClassifierClass({
            "code": "oks.pavilion", "geom_type": "Polygon",
            "tep_role": "building_footprint",
            "attrs": [{"id": "floors", "type": "integer"}]})
        studio_core.CLASSIFIER = cls
        studio_core.KIND_TO_CODE["pavilion"] = "oks.pavilion"
        try:
            base = studio_core.compute_tep(FEATURES)["fact"]["spp"]
            feats = FEATURES + [{"kind": "pavilion", "props": {"floors": 2},
                                 "ring": [[0, 0], [100, 0], [100, 100], [0, 100]]}]
            more = studio_core.compute_tep(feats)["fact"]["spp"]
        finally:
            studio_core.CLASSIFIER = orig_cls
            studio_core.KIND_TO_CODE.clear()
            studio_core.KIND_TO_CODE.update(orig_map)
        # 1 га × 2 этажа = 20 тыс. м² добавилось, compute_tep не менялся
        self.assertAlmostEqual(more - base, 20.0, places=1)


class TestLayerSets(unittest.TestCase):
    """Наборы слоёв листов (шаг 5): существующее положение без проекта."""

    def test_existing_position_excludes_project_layers(self):
        from grado_wizard.sheets import layerset_layers
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(Path(tmp) / "ls.grado", "Набор", FEATURES)
            try:
                existing = set(layerset_layers(p, "existing_position"))
                apo = set(layerset_layers(p, "apo"))
            finally:
                p.close()
        # проектные слои (по layer_id) не попадают в существующее положение
        for lid in ("project.apo.buildings", "project.apo.red_lines"):
            self.assertNotIn(lid, existing)
            self.assertIn(lid, apo)
        # исходные — попадают
        self.assertIn("project.territory.boundary", existing)
        self.assertIn("project.tp.func_zone", existing)

    def test_base_plan_draws_no_buildings(self):
        # критерий шага 5: лист «Существующее положение» из исходных слоёв
        from grado_render import StyleSet, build_ops, hex_to_rgb
        from grado_wizard.sheets import (MAP_RECT, fit_scale, layerset_layers)
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(Path(tmp) / "ls.grado", "Набор", FEATURES)
            try:
                layer_ids = layerset_layers(p, "existing_position")
                ops = build_ops(p, MAP_RECT, fit_scale(p),
                                styles=StyleSet(), only=layer_ids)
                ops_all = build_ops(p, MAP_RECT, fit_scale(p), styles=StyleSet())
            finally:
                p.close()
        bld = hex_to_rgb("#f5c76b")  # заливка зданий
        fills = [o.get("fill") for o in ops if o["op"] == "path"]
        self.assertNotIn(bld, fills, "здание не рисуется на опорном плане")
        # на полном виде (АПО) здания есть — набор реально фильтрует
        self.assertIn(bld, [o.get("fill") for o in ops_all if o["op"] == "path"])


class TestStyleLibrary(unittest.TestCase):
    """Единая библиотека стилей (шаг 3): один JSON — холст, PDF и DXF."""

    def test_frontend_styles_shape(self):
        st = studio_core.frontend_styles()
        self.assertEqual(st["boundary.line"]["width"], 2.5)
        self.assertEqual(st["func_zone.fill"]["label_field"], "zone_title")
        # прозрачность заливки свёрнута в rgba() для холста
        self.assertTrue(st["restrict.hatch"]["fill"].startswith("rgba("))
        self.assertTrue(st["restrict.hatch"]["hatch"])
        # у линии заливки нет
        self.assertNotIn("fill", st["red.line.projected"])

    def test_dxf_layers_from_styles(self):
        layers, fallback = studio_core.dxf_layers_from_styles()
        self.assertEqual(layers["terr.boundary"], ("GRANICA_TERRITORII", 7))
        self.assertEqual(layers["pp.red_line"], ("KRASNYE_LINII", 1))
        self.assertEqual(fallback, ("PROCHEE", 7))

    def test_editing_json_changes_dxf(self):
        # критерий шага 3: правка стиля меняет DXF без правки кода
        import copy
        feats = FEATURES + [{"kind": "dim", "props": {},
                             "line": [[0, 0], [120, 0]]}]
        orig = studio_core.STYLE_LIB
        patched = copy.deepcopy(orig)
        patched["styles"]["boundary.line"]["dxf"]["name"] = "TEST_GRANICA"
        patched["styles"]["dimension.line"]["dxf"]["name"] = "TEST_DIM"
        studio_core.STYLE_LIB = patched
        try:
            dxf = studio_core.make_dxf(feats, "Стиль").decode("cp1251")
        finally:
            studio_core.STYLE_LIB = orig
        self.assertIn("TEST_GRANICA", dxf)
        self.assertNotIn("GRANICA_TERRITORII", dxf)
        self.assertIn("TEST_DIM", dxf, "имя слоя размеров тоже из JSON")


def _make_ogd_zip(path, inner_files):
    """Внешний ZIP с вложенным ZIP, как отдаёт портал ОГД (см. коннектор)."""
    import io
    import json
    import zipfile
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        for name, data in inner_files.items():
            zf.writestr(name, json.dumps(data, ensure_ascii=False))
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("выгрузка/данные.zip", inner.getvalue())


def _ogd_gj(coords, geom_type="Polygon", name="Зона 1"):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": 1,
         "geometry": {"type": geom_type, "coordinates": coords},
         "properties": {"NAME": name}}]}


class TestGisogdImport(unittest.TestCase):
    """MODEL-плюс: подключение коннектора ГИС ОГД к студии (Фаза B)."""

    def setUp(self):
        from grado_connectors import SnapshotStore
        self._orig = studio_core.SOURCE_STORE
        self._tmp = tempfile.TemporaryDirectory()
        studio_core.SOURCE_STORE = SnapshotStore(Path(self._tmp.name) / "src")

    def tearDown(self):
        studio_core.SOURCE_STORE = self._orig
        self._tmp.cleanup()

    def _zip_bytes(self, inner_files):
        with tempfile.TemporaryDirectory() as tmp:
            zpath = Path(tmp) / "ogd.zip"
            _make_ogd_zip(zpath, inner_files)
            return zpath.read_bytes()

    def test_recognized_layer_routes_to_source_layer(self):
        poly = [[[37.6155646254, 55.7522242128], [37.617, 55.7522242128],
                 [37.617, 55.753], [37.6155646254, 55.7522242128]]]
        data = self._zip_bytes({
            "funkcionalnie_zony.geojson": _ogd_gj(poly, name="Ж-1")})
        out = studio_core.import_gisogd(data)
        self.assertEqual(len(out["features"]), 1)
        f = out["features"][0]
        self.assertEqual(f["kind"], "zone")
        self.assertEqual(f["layer_id"], "source.gisogd.func_zones")
        self.assertEqual(f["props"]["zone_title"], "Ж-1")
        self.assertEqual(f["prov"]["source"], "gisogd")
        x, y = f["ring"][0]
        self.assertAlmostEqual(x, 98, delta=15)
        self.assertAlmostEqual(y, 1371, delta=15)

    def test_unrecognized_member_noted_not_dropped_silently(self):
        poly = [[[37.6, 55.7], [37.61, 55.7], [37.61, 55.71], [37.6, 55.7]]]
        data = self._zip_bytes({"kultobjekty.geojson": _ogd_gj(poly)})
        out = studio_core.import_gisogd(data)
        self.assertEqual(out["features"], [])
        self.assertTrue(any("kultobjekty" in n and "не распознан" in n
                            for n in out["notes"]))

    def test_multiple_recognized_layers_and_roundtrip(self):
        poly = [[[37.6, 55.7], [37.61, 55.7], [37.61, 55.71], [37.6, 55.7]]]
        line = [[37.6, 55.7], [37.62, 55.7]]
        data = self._zip_bytes({
            "krasnye_linii.geojson": _ogd_gj(line, geom_type="LineString"),
            "zouit_sanitarnye.geojson": _ogd_gj(poly, name="СЗЗ предприятия"),
        })
        out = studio_core.import_gisogd(data)
        kinds = sorted(f["kind"] for f in out["features"])
        self.assertEqual(kinds, ["redline", "restrict"])
        restrict = next(f for f in out["features"] if f["kind"] == "restrict")
        self.assertEqual(restrict["layer_id"], "source.gisogd.restrict")
        self.assertEqual(restrict["props"]["kind"], "СЗЗ предприятия")
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(Path(tmp) / "ogd.grado", "ОГД", out["features"])
            ids = {i["layer_id"] for i in p.layers()}
            self.assertIn("source.gisogd.red_lines", ids)
            self.assertIn("source.gisogd.restrict", ids)
            p.close()

    def test_snapshot_and_provenance_recorded(self):
        poly = [[[37.6, 55.7], [37.61, 55.7], [37.61, 55.71], [37.6, 55.7]]]
        data = self._zip_bytes({"funkcionalnie_zony.geojson": _ogd_gj(poly)})
        out = studio_core.import_gisogd(data)
        self.assertTrue(out["snapshot"]["id"].startswith("gisogd-"))
        self.assertIsNone(out["diff"], "первый импорт — без diff")
        self.assertEqual(len(studio_core.sources_journal()), 1)

    def test_recognized_member_gets_exact_lgr_style(self):
        # без точного совпадения — общий restrict.hatch (как раньше)
        poly = [[[37.6, 55.7], [37.61, 55.7], [37.61, 55.71], [37.6, 55.7]]]
        generic = studio_core.import_gisogd(
            self._zip_bytes({"zouit_ogr.geojson": _ogd_gj(poly)}))
        self.assertNotIn("style_id", generic["features"][0])

        # "водоохранная" — распознаётся и routing (по "охран"), и точный
        # знак Эталона ЛГР (по "водоохран") — вместо общей штриховки ЗОУИТ
        data = self._zip_bytes({"vodoohrannaya_zona_reki.geojson": _ogd_gj(poly)})
        out = studio_core.import_gisogd(data)
        f = out["features"][0]
        self.assertEqual(f["layer_id"], "source.gisogd.restrict",
                         "маршрутизация не меняется — тот же слой ЗОУИТ")
        self.assertEqual(f["style_id"], "lgr.vodookhr")
        self.assertEqual(f["props"]["kind"], "Водоохранные зоны",
                         "название атрибута — из Эталона, не общее «ЗОУИТ»")

    def test_lgr_style_survives_grado_roundtrip(self):
        poly = [[[37.6, 55.7], [37.61, 55.7], [37.61, 55.71], [37.6, 55.7]]]
        feats = studio_core.import_gisogd(
            self._zip_bytes({"pribrezhnaya_zona.geojson": _ogd_gj(poly)}))["features"]
        with tempfile.TemporaryDirectory() as tmp:
            gp = Path(tmp) / "p.grado"
            studio_core.build_project(gp, "ЛГР", feats).close()
            rt = studio_core.grado_to_features(str(gp))
        self.assertEqual(rt["features"][0]["style_id"], "lgr.pribrezh")


class TestUserLayers(unittest.TestCase):
    """Слои, созданные в панели студии («+ слой»): маршрутизация без
    хардкода в LAYER_TEMPLATES — шаблон приходит с холста в body.layers."""

    USER_LAYERS = [{"layer_id": "user.ozelenenie", "code": "tp.func_zone",
                    "title": "Озеленение", "stage": "project",
                    "style_id": "func_zone.fill"}]
    FEATS = [
        {"kind": "boundary", "ring": [[0, 0], [500, 0], [500, 300], [0, 300]],
         "props": {}},
        {"kind": "zone", "layer_id": "user.ozelenenie",
         "ring": [[10, 10], [100, 10], [100, 100], [10, 100]],
         "props": {"zone_title": "Озеленение-1"}},
    ]

    def test_build_project_routes_user_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(
                Path(tmp) / "u.grado", "Т", self.FEATS, self.USER_LAYERS)
            ids = {i["layer_id"] for i in p.layers()}
            self.assertIn("user.ozelenenie", ids)
            layer = p.layer_by_id("user.ozelenenie")
            self.assertEqual(layer.count(), 1)
            f = next(layer.features())
            self.assertEqual(f["attrs"]["zone_title"], "Озеленение-1")
            p.close()

    def test_without_layers_manifest_unknown_layer_dropped(self):
        # без body.layers пользовательский layer_id неизвестен — объект
        # тихо не попадает в проект (не падает), но и не сохраняется
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(Path(tmp) / "u.grado", "Т", self.FEATS)
            ids = {i["layer_id"] for i in p.layers()}
            self.assertNotIn("user.ozelenenie", ids)
            self.assertIn("project.territory.boundary", ids)
            p.close()

    def test_grado_roundtrip_preserves_user_layer(self):
        data = studio_core.make_grado(self.FEATS, "Т", layers=self.USER_LAYERS)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rt.grado"
            path.write_bytes(data)
            out = studio_core.grado_to_features(path)
        zone = next(f for f in out["features"] if f["kind"] == "zone")
        self.assertEqual(zone["layer_id"], "user.ozelenenie")
        self.assertEqual(zone["props"]["zone_title"], "Озеленение-1")

    def test_builtin_template_wins_on_id_collision(self):
        # пользовательский манифест не может подменить встроенный слой
        clash = [{"layer_id": "project.territory.boundary",
                  "code": "tp.func_zone", "title": "ПОДМЕНА", "style_id": "x"}]
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(
                Path(tmp) / "u.grado", "Т", self.FEATS, clash)
            info = next(i for i in p.layers()
                       if i["layer_id"] == "project.territory.boundary")
            self.assertEqual(info["code"], "terr.boundary", "встроенный код не подменён")
            p.close()

    def test_make_album_and_dxf_accept_user_layer(self):
        pdf = studio_core.make_album(self.FEATS, "Т", layers=self.USER_LAYERS)
        self.assertTrue(pdf.startswith(b"%PDF"))
        dxf = studio_core.make_dxf(self.FEATS, "Т", layers=self.USER_LAYERS)
        self.assertIn("FUNKC_ZONY", dxf.decode("cp1251"))


class TestGenericGeomExport(unittest.TestCase):
    """generic-слои: линия/точка живут в самом объекте (не только ring)."""

    def test_geom_for_generic_line_and_point(self):
        line = studio_core._geom_for(
            {"kind": "generic", "line": [[0, 0], [10, 5]], "props": {}})
        self.assertEqual(line["type"], "LineString")
        pt = studio_core._geom_for(
            {"kind": "generic", "point": [3, 4], "props": {}})
        self.assertEqual(pt["type"], "Point")

    def test_generic_line_survives_grado_roundtrip(self):
        layers = [{"layer_id": "user.seti", "code": "generic.line",
                   "title": "Сети", "style_id": "boundary.line"}]
        feats = [{"kind": "generic", "layer_id": "user.seti",
                  "line": [[0, 0], [50, 50]], "props": {}}]
        data = studio_core.make_grado(feats, "Т", layers=layers)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "g.grado"
            path.write_bytes(data)
            out = studio_core.grado_to_features(path)
        lines = [f for f in out["features"] if f.get("line")]
        self.assertEqual(len(lines), 1, "линия generic-слоя потерялась в roundtrip")
        self.assertEqual(lines[0]["layer_id"], "user.seti")


def _fake_nspd_transport(cad="77:01:0001013:19"):
    """Ответ intersects-API: один участок EPSG:3857 (как отдаёт геопортал)."""
    def transport(url, body):
        assert "intersects" in url
        assert body["categories"] and "id" in body["categories"][0]
        return {"type": "FeatureCollection", "features": [{
            "id": 1, "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[
                [4187300, 7508800], [4187400, 7508800],
                [4187400, 7508900], [4187300, 7508800]]]},
            "properties": {"category": body["categories"][0]["id"],
                           "categoryName": "Земельные участки ЕГРН",
                           "options": {"cad_num": cad,
                                       "readable_address": "Москва"}}}]}
    return transport


def _fake_overpass_transport(query):
    assert "way" in query
    return {"elements": [
        {"type": "way", "id": 1, "tags": {"highway": "residential",
                                          "name": "Тестовая"},
         "geometry": [{"lon": 37.615, "lat": 55.75},
                      {"lon": 37.617, "lat": 55.751}]},
        {"type": "way", "id": 2, "tags": {"building": "yes",
                                          "building:levels": "5"},
         "geometry": [{"lon": 37.615, "lat": 55.75},
                      {"lon": 37.616, "lat": 55.75},
                      {"lon": 37.616, "lat": 55.751},
                      {"lon": 37.615, "lat": 55.75}]},
    ]}


class TestFetchExtent(unittest.TestCase):
    """«Данные по области»: прямые источники → слои-приёмники по layer_id."""

    def setUp(self):
        from grado_connectors import SnapshotStore
        self._orig = studio_core.SOURCE_STORE
        self._tmp = tempfile.TemporaryDirectory()
        studio_core.SOURCE_STORE = SnapshotStore(Path(self._tmp.name) / "src")

    def tearDown(self):
        studio_core.SOURCE_STORE = self._orig
        self._tmp.cleanup()

    BBOX = [37.61, 55.749, 37.62, 55.752]

    def test_nspd_direct_normalizes_like_capture(self):
        from grado_connectors import NspdDirect
        conn = NspdDirect(transport=_fake_nspd_transport())
        result = conn.fetch(self.BBOX, [36368])
        self.assertEqual(len(result["features"]), 1)
        f = result["features"][0]
        self.assertEqual(f["properties"]["opt_cad_num"], "77:01:0001013:19")
        lon, lat = f["geometry"]["coordinates"][0][0]
        self.assertAlmostEqual(lon, 37.615, delta=0.01)   # 3857 → WGS84

    def test_osm_sets_split_and_close_rings(self):
        from grado_connectors import OsmOverpass
        conn = OsmOverpass(transport=_fake_overpass_transport)
        result = conn.fetch(self.BBOX, ["roads", "buildings"])
        sets = {f["properties"]["grado_set"] for f in result["features"]}
        self.assertEqual(sets, {"roads", "buildings"})
        bld = next(f for f in result["features"]
                   if f["properties"]["grado_set"] == "buildings")
        self.assertEqual(bld["geometry"]["type"], "Polygon")

    def test_fetch_extent_routes_by_layer_id(self):
        import grado_connectors
        orig_nspd = grado_connectors.NspdDirect
        orig_osm = grado_connectors.OsmOverpass
        fake_n = _fake_nspd_transport()

        class FakeNspd(orig_nspd):
            def __init__(self):
                super().__init__(transport=fake_n)

        class FakeOsm(orig_osm):
            def __init__(self):
                super().__init__(transport=_fake_overpass_transport)

        grado_connectors.NspdDirect = FakeNspd
        grado_connectors.OsmOverpass = FakeOsm
        try:
            out = studio_core.fetch_extent(
                self.BBOX, ["osm.roads", "osm.buildings", "nspd.parcels"])
        finally:
            grado_connectors.NspdDirect = orig_nspd
            grado_connectors.OsmOverpass = orig_osm
        by_src = {g["source"]: g for g in out["groups"]}
        road = by_src["osm.roads"]["features"][0]
        self.assertEqual(road["layer_id"], "source.osm.roads")
        self.assertIn("line", road)
        self.assertEqual(road["prov"]["source"], "osm")
        bld = by_src["osm.buildings"]["features"][0]
        self.assertEqual(bld["layer_id"], "source.osm.buildings")
        self.assertIn("ring", bld)
        parcel = by_src["nspd.parcels"]["features"][0]
        self.assertEqual(parcel["layer_id"], "source.nspd.parcels")
        self.assertEqual(parcel["props"]["cad_num"], "77:01:0001013:19")
        self.assertEqual(parcel["prov"]["source"], "nspd")
        self.assertEqual(len(out["snapshots"]), 2, "снимок OSM + снимок НСПД")

    def test_fetch_extent_features_export_to_grado(self):
        import grado_connectors
        orig = grado_connectors.OsmOverpass

        class FakeOsm(orig):
            def __init__(self):
                super().__init__(transport=_fake_overpass_transport)

        grado_connectors.OsmOverpass = FakeOsm
        try:
            out = studio_core.fetch_extent(self.BBOX, ["osm.roads", "osm.buildings"])
        finally:
            grado_connectors.OsmOverpass = orig
        feats = [f for g in out["groups"] for f in g["features"]]
        with tempfile.TemporaryDirectory() as tmp:
            gp = Path(tmp) / "e.grado"
            p = studio_core.build_project(gp, "Экстент", feats)
            ids = [i["layer_id"] for i in p.layers()]
            self.assertIn("source.osm.roads", ids)
            self.assertIn("source.osm.buildings", ids)
            road_layer = p.layer_by_id("source.osm.roads")
            self.assertEqual(len(list(road_layer.features())), 1,
                             "линия OSM-дороги не должна выпадать из экспорта")
            p.close()

    def test_full_nspd_attribution_and_fields(self):
        # ВСЕ options-поля НСПД → props с русскими именами + список столбцов
        def transport(url, body):
            return {"type": "FeatureCollection", "features": [{
                "id": 1, "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[
                    [4187300, 7508800], [4187400, 7508800],
                    [4187400, 7508900], [4187300, 7508800]]]},
                "properties": {"category": 36368, "options": {
                    "cad_num": "77:01:1", "cost_value": 100.5,
                    "ownership_type": "Частная",
                    "какой_то_новый_ключ": "значение"}}}]}
        import grado_connectors
        orig = grado_connectors.NspdDirect

        class Fake(orig):
            def __init__(self):
                super().__init__(transport=transport)

        grado_connectors.NspdDirect = Fake
        try:
            out = studio_core.fetch_extent(self.BBOX, ["nspd.parcels"])
        finally:
            grado_connectors.NspdDirect = orig
        g = out["groups"][0]
        p = g["features"][0]["props"]
        self.assertEqual(p["cad_num"], "77:01:1")
        self.assertEqual(p["кадастровая стоимость, ₽"], 100.5)
        self.assertEqual(p["форма собственности"], "Частная")
        self.assertEqual(p["какой_то_новый_ключ"], "значение",
                         "неизвестные ключи геопортала не теряются")
        names = {fd["name"] for fd in g["fields"]}
        self.assertIn("cad_num", names)          # базовые — с русским label
        self.assertIn("кадастровая стоимость, ₽", names)
        cad = next(fd for fd in g["fields"] if fd["name"] == "cad_num")
        self.assertEqual(cad["label"], "кадастровый номер")
        cost = next(fd for fd in g["fields"]
                    if fd["name"] == "кадастровая стоимость, ₽")
        self.assertEqual(cost["type"], "real")

    def test_builtin_receiver_gets_fields_from_manifest(self):
        # манифест с fields для ВСТРОЕННОГО слоя-приёмника: колонки мержатся,
        # code/title встроенного не подменяются
        manifest = [{"layer_id": "source.nspd.parcels", "code": "ПОДМЕНА",
                     "title": "ПОДМЕНА",
                     "fields": [{"name": "кадастровая стоимость, ₽",
                                 "type": "real"}]}]
        feats = [{"kind": "parcel", "layer_id": "source.nspd.parcels",
                  "ring": [[0, 0], [50, 0], [50, 50]],
                  "props": {"cad_num": "77:01:1",
                            "кадастровая стоимость, ₽": 100.5}}]
        with tempfile.TemporaryDirectory() as tmp:
            p = studio_core.build_project(Path(tmp) / "f.grado", "Т",
                                          feats, manifest)
            info = next(i for i in p.layers()
                        if i["layer_id"] == "source.nspd.parcels")
            self.assertEqual(info["code"], "cad.parcel", "code не подменён")
            fr = next(p.layer_by_id("source.nspd.parcels").features())
            self.assertEqual(fr["attrs"]["кадастровая стоимость, ₽"], 100.5)
            self.assertEqual(fr["attrs"]["cad_num"], "77:01:1")
            p.close()

    def test_area_limit_guards(self):
        with self.assertRaises(ValueError):
            studio_core.fetch_extent([37.0, 55.0, 38.0, 56.0], ["nspd.parcels"])

    def test_unknown_source_noted(self):
        out = studio_core.fetch_extent(self.BBOX, ["чушь"])
        self.assertFalse(out["groups"])
        self.assertTrue(any("неизвестный" in n for n in out["notes"]))


if __name__ == "__main__":
    unittest.main()
