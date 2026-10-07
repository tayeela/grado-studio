import json
import sys
import os
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402

# Папка «~/Documents/ГРАДО 2» — невосстановимые данные владельца. Без GRADO2_PROJECTS server.PROJECTS указывает на неё,
# и тесты, которые пишут проекты, портили бы её. Поэтому в таком случае весь модуль работает во временной папке.
if not os.environ.get("GRADO2_PROJECTS"):
    import tempfile as _tempfile
    S.PROJECTS = Path(_tempfile.mkdtemp(prefix="grado2-test-")) / "p"


class Grado2Server(unittest.TestCase):
    def test_tep_population_only_from_new_buildings(self):
        r = S.tep(terr_ha=10, restrict_ha=1, spp_new_m2=200_000, share=0.8, spp_kept_m2=50_000)
        m = {x["id"]: x["value"] for x in r["metrics"]}
        self.assertEqual(m["spp"], 200)                   # тыс. м², только новая застройка
        self.assertEqual(m["calc_area"], 9)
        self.assertAlmostEqual(r["density_total"], 25.0)  # (200 + 50) / 10 га

    def test_tep_restrict_larger_than_territory_is_safe(self):
        # Restrictions larger than the territory: the area is clamped to 0 and densities do not divide by it.
        # Population follows the flats area («Калькулятор 2.0»), not the territory: 611 m² of flats / 33 = 18.5, rounded up to 19.
        m = {x["id"]: x["value"] for x in S.tep(1, 5, 1000, 1)["metrics"]}
        self.assertEqual(m["calc_area"], 0)
        self.assertEqual(m["density_spp"], 0)
        self.assertEqual(m["population"], 19)

    YAK = dict(terr_ha=15, restrict_ha=0, spp_new_m2=357_000, share=1, nonres_part=6, education_zone=1, k1=0.75, k2=0.2)

    def test_tep_without_constants_has_no_new_keys_and_matches_fixture(self):
        import json
        ref = json.loads((S.ROOT / "core/compute/tests/fixtures/calc2_yakimanka_15ha.json").read_text("utf-8"))["expected"]
        r = S.tep(**self.YAK)
        self.assertEqual(set(r), {"metrics", "density_total", "social"})
        m = {x["id"]: x["value"] for x in r["metrics"]}
        for k in ("population", "doo_places", "school_places"):
            self.assertEqual(m[k], ref[k], k)

    def test_tep_constants_override_doo(self):
        import math
        base = {x["id"]: x["value"] for x in S.tep(**self.YAK)["metrics"]}
        r = S.tep(**self.YAK, constants={"doo_z1": 50, "school_z1": 90})
        m = {x["id"]: x["value"] for x in r["metrics"]}
        self.assertEqual(r["constants_changed"], ["doo_z1"])          # school_z1 равна пресету: не «изменена»
        self.assertEqual(m["doo_places"], math.ceil(round(50 * base["population"] / 1000, 6)))
        self.assertGreater(m["doo_places"], base["doo_places"])
        self.assertEqual(m["school_places"], base["school_places"])
        self.assertEqual(m["population"], base["population"])
        self.assertEqual(S.tep(**self.YAK, constants={})["constants_changed"], [])

    def test_tep_constants_bad_values(self):
        for bad in ({"nope": 1}, {"doo_z1": -1}, {"doo_z1": 1e9}, {"doo_z1": "50"}, {"doo_z1": True}, {"doo_z1": float("nan")}, {"doo_z1": float("inf")}, {"doo_z1": 10**400}, [1]):
            with self.assertRaises(ValueError, msg=bad):
                S.tep(**self.YAK, constants=bad)

    B = dict(terr_ha=20, restrict_ha=0, spp_new_m2=450_000, share=1, nonres_part=6, education_zone=2, k1=1, k2=0.9)

    def test_tep_social_reserve(self):
        r = S.tep(**self.B)
        self.assertEqual(r["social"], [{"kind": "doo", "places": 263, "m2": 8416}, {"kind": "doo", "places": 262, "m2": 8384},
                                       {"kind": "school", "places": 1034, "m2": 16544}, {"kind": "clinic", "places": 159, "m2": 3500}])
        m = {x["id"]: x for x in r["metrics"]}
        self.assertEqual((m["social_res_m2"]["value"], m["social_res_ha"]["value"], m["social_res_share"]["value"]), (36844, 3.684, 18.422))
        self.assertEqual(m["social_res_ha"]["group"], "Резерв участков")
        r = S.tep(**self.B, free_doo=175, free_school=400, free_clinic=100)
        self.assertEqual([(x["kind"], x["places"], x["m2"]) for x in r["social"]],
                         [("doo", 350, 11200), ("school", 634, 12046), ("clinic", 59, 3500)])
        m = {x["id"]: x["value"] for x in r["metrics"]}
        self.assertEqual((m["social_res_m2"], m["social_res_ha"], m["social_res_share"]), (26746, 2.675, 13.373))
        a = dict(self.B, spp_new_m2=150_000, education_zone=1)
        r = S.tep(**a, free_doo=40, free_school=100, free_clinic=20)
        self.assertEqual([(x["kind"], x["places"], x["m2"]) for x in r["social"]], [("doo", 83, 2905), ("school", 151, 2869), ("clinic", 33, 3500)])
        m = {x["id"]: x["value"] for x in r["metrics"]}
        self.assertEqual((m["social_res_m2"], m["social_res_ha"], m["social_res_share"]), (9274, 0.927, 4.637))

    def test_tep_social_zero_deficit_and_surplus(self):
        r = S.tep(**self.B, free_doo=100000, free_school=100000, free_clinic=100000)
        self.assertEqual(r["social"], [])
        m = {x["id"]: x["value"] for x in r["metrics"]}
        self.assertEqual((m["doo_deficit"], m["social_res_m2"], m["social_res_share"]), (0, 0, 0))

    def test_tep_free_places_bad_values(self):
        for k in ("free_doo", "free_school", "free_clinic"):
            for bad in (-1, float("nan"), float("inf"), 100001, "5", True, 0.5):
                with self.assertRaises(ValueError, msg=(k, bad)) as cm:
                    S.tep(**self.B, **{k: bad})
                self.assertEqual(str(cm.exception), str(cm.exception).encode("ascii", "ignore").decode())

    def test_tep_parking_area_split(self):
        """Parking area. Norm area per place is NOT in the repository texts (945-PP has places only): the preset uses
        project assumptions 25 / 30 / 25 m2 per place (ground / underground / multi-storey).
        Yakimanka fixture: parking_perm = 2519 places.
        0/0: all ground, 2519 * 25 = 62 975 m2 = 6.298 ha; total 6.298 ha.
        40/0: underground ceil(2519 * 0.4) = ceil(1007.6) = 1008 places * 30 = 30 240 m2; ground 2519 - 1008 = 1511 * 25 = 37 775 m2 = 3.778 ha;
        total = 3.7775 + 3.024 = 6.8015 ha -> 6.802."""
        m = {x["id"]: x["value"] for x in S.tep(**self.YAK)["metrics"]}
        self.assertEqual(m["parking_perm"], 2519)
        self.assertEqual((m["park_ground_ha"], m["park_underground_m2"], m["park_multi_m2"], m["park_total_ha"]), (6.298, 0, 0, 6.298))
        m = {x["id"]: x["value"] for x in S.tep(**self.YAK, park_share_underground=40, park_share_multi=0)["metrics"]}
        self.assertEqual(m["parking_perm"], 2519)
        self.assertEqual((m["park_ground_ha"], m["park_underground_m2"], m["park_multi_m2"], m["park_total_ha"]), (3.778, 30240, 0, 6.802))
        m = {x["id"]: x["value"] for x in S.tep(**self.YAK, park_share_underground=0, park_share_multi=100)["metrics"]}
        self.assertEqual((m["park_ground_ha"], m["park_multi_m2"]), (0, 62975))      # 2519 * 25
        for bad in (-1, 101, 12.5, float("nan"), "5", True):
            for k in ("park_share_underground", "park_share_multi"):
                with self.assertRaises(ValueError, msg=(k, bad)):
                    S.tep(**self.YAK, **{k: bad})
        with self.assertRaises(ValueError):
            S.tep(**self.YAK, park_share_underground=60, park_share_multi=60)

    def test_tep_norms_cover_all_constants(self):
        import json
        p = json.loads(S.PRESET.read_text("utf-8"))
        n = S.tep_norms()["norms"]
        self.assertEqual([x["id"] for x in n], list(p["constants"]))
        self.assertEqual({x["id"]: x["value"] for x in n}, p["constants"])

    def test_clean_props_renames_and_parses_numbers(self):
        p = S.clean_props({"opt_floors": "9-12", "opt_cad_num": "77:1", "grado_set": "x", "name": ""})
        self.assertEqual(p, {"Этажность": 9, "Кадастровый номер": "77:1"})

    def test_nspd_keeps_only_named_fields(self):
        p = S.clean_props({"opt_floors": "9", "systemInfo": {"inserted": "x"}, "interactionId": "1", "opt_cost_index": "5"}, None, True)
        self.assertEqual(p, {"Этажность": 9})

    def test_area_limit_blocks_before_network(self):
        layers, errors = S.fetch([37.0, 55.0, 37.5, 55.5], ["nspd.parcels", "unknown"])
        self.assertEqual(layers, {})
        self.assertIn("nspd.parcels", errors)


class Egko(unittest.TestCase):
    """ЕГКО Москвы (карта base2 портала ГИС ОГД) — семь источников, читаемые поля, пробел как пустое значение."""
    KEYS = ["egko.buildings", "egko.roads", "egko.paths", "egko.green", "egko.water", "egko.fences", "egko.addresses"]

    def test_sources_registered_in_own_group(self):
        for k in self.KEYS:
            self.assertEqual(S.SOURCES[k][0], "egko", k)
            self.assertIn("ЕГКО", S.SOURCES[k][2])
        self.assertEqual(set(S.SOURCES["egko.buildings"][1]), {"virtual6", "virtual15", "virtual16", "virtual17"})
        self.assertEqual(set(S.SOURCES["egko.green"][1]), {"gazons", "forest"})
        self.assertEqual(S.LIMIT_KM2["egko"], 150.0)
        # существующие источники ГИС ОГД не тронуты
        self.assertEqual(S.SOURCES["gisogd.pzz_sub"][1], {"virtual98": None, "virtual132": None})

    def test_building_fields_and_address(self):
        p = {"orbis_id": 1.0, "type_zd": "Жилое", "vid_zd": " ", "name_bui": " ", "name_str1": "Тверская улица", "house": "18",
             "trunk": "2", "building": "1", "is_struct": "стр.", "estate": " ", "name_str2": " ", "h": 29.5, "shape_area": 812.349}
        out = S.clean_props(S.egko_building_props(p), {"Состояние": "действующее"})
        self.assertEqual(out["Адрес"], "Тверская улица 18 к.2 стр.1")
        self.assertEqual(out["Назначение"], "Жилое")
        self.assertEqual(out[S.EGKO_H], 29.5)
        self.assertEqual(out["Площадь застройки, м²"], 812.3)
        self.assertEqual(out["Состояние"], "действующее")
        self.assertNotIn("Этажность", out, "этажность из высоты не вычисляется — «Проверить нормы» принял бы оценку за данные")
        self.assertNotIn("Вид", out, "пробел — пустое значение")
        self.assertNotIn("Вторая улица", out)

    def test_estate_only_address(self):
        self.assertEqual(S.egko_address({"name_str1": "проезд Серебрякова", "house": " ", "estate": "14"}), "проезд Серебрякова вл.14")
        self.assertEqual(S.egko_address({"name_str1": "8-й Микрорайон", "house": "802", "building": "1", "is_struct": "соор."}), "8-й Микрорайон 802 соор.1")
        self.assertEqual(S.egko_address({"name_str1": "город Зеленоград", "house": " ", "trunk": "903"}), "город Зеленоград к.903")
        self.assertIsNone(S.egko_address({"name_str1": " ", "house": " "}))

    def test_spaces_are_empty_everywhere(self):
        for k in self.KEYS:
            out = S.clean_props(S.PRESENT[k]({"ext_name": " ", "name_str": " ", "vid_road": " ", "type_flora": " ", "vid_frst": " ",
                                              "vid_wat": " ", "name_wat": " ", "full_addr": " ", "angl": 12.5}))
            self.assertFalse([v for v in out.values() if str(v).strip() == ""], k)

    def test_green_and_address_names(self):
        self.assertEqual(S.egko_green_props({"type_flora": "gazon"})["Тип"], "газон")
        self.assertEqual(S.egko_green_props({"vid_frst": "Парк", "name_frs": " "}), {"Тип": "Парк", "Название": None})
        self.assertEqual(S.egko_address_props({"full_addr": "Научный проезд 20 стр.4", "angl": 56.1})["Адрес"], "Научный проезд 20 стр.4")

    def test_fetch_egko_sequential_with_state(self):
        calls = []

        class Fake:
            def __init__(self, **kw):
                calls.append(("init", kw.get("map_name"), kw.get("clip"), str(kw.get("cache_dir"))))

            def fetch(self, bbox, code):
                calls.append(("fetch", code))
                return {"features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [37.605, 55.763]},
                                      "properties": {"type_zd": "Нежилое", "h": 9.0}, "grado_key": f"base2:{code}:1"}],
                        "source_doc": "ЕГКО", "notes": []}
        old, S.GisogdApi = S.GisogdApi, Fake
        try:
            layers, errors = S.fetch([37.600, 55.760, 37.612, 55.766], ["egko.buildings"])
        finally:
            S.GisogdApi = old
        self.assertEqual(errors, {})
        self.assertEqual([c for c in calls if c[0] == "init"][0][1:3], ("base2", True))
        self.assertTrue(calls[0][3].endswith("egko"), "свой кэш ЕГКО, не gisogd")
        props = [f["properties"] for f in layers["egko.buildings"]["features"]["features"]]
        self.assertEqual(sorted(p["Состояние"] for p in props), sorted(["действующее", "строящееся", "разрушенное", "нулевой цикл (фундамент)"]))
        self.assertTrue(all(p["_key"].startswith("base2:") for p in props))


class DataBboxT70(unittest.TestCase):
    """T70: рамка листа не уходит в OSM и ЕГКО; большая область режется на части по очереди, с паузой."""
    TERR = [37.600, 55.760, 37.620, 55.772]          # ~1,5 x 1,3 км, около 2 км2
    FRAME = [37.0, 55.4, 38.2, 56.2]                 # рамка крупного листа, тысячи км2

    def _egko_fake(self, calls):
        class Fake:
            def __init__(self, **kw):
                pass

            def fetch(self, bbox, code):
                calls.append(list(bbox))
                x = (bbox[0] + bbox[2]) / 2
                return {"features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [x, bbox[1]]},
                                      "properties": {"type_zd": "Нежилое"}, "grado_key": "base2:a:1"},
                                     {"type": "Feature", "geometry": {"type": "Point", "coordinates": [x, bbox[1]]},
                                      "properties": {"type_zd": "Нежилое"}, "grado_key": f"base2:{x:.4f}"}],
                        "source_doc": "ЕГКО", "notes": []}
        return Fake

    def test_territory_bbox_replaces_sheet_frame_for_osm_and_egko(self):
        osm_calls, egko_calls = [], []
        def osm(bbox, sets, cache_dir=None):
            osm_calls.append(list(bbox))
            return {"features": [], "source_doc": "OSM", "notes": []}
        with mock.patch.object(S, "osm_fetch", osm), mock.patch.object(S, "GisogdApi", self._egko_fake(egko_calls)):
            layers, errors = S.fetch(self.FRAME, ["osm.roads", "egko.buildings"], self.TERR)
        self.assertEqual(errors, {})
        want = S.territory_bbox(self.TERR)
        self.assertEqual(osm_calls, [want])
        self.assertEqual(egko_calls, [want] * len(S.SOURCES["egko.buildings"][1]))
        self.assertLess(S.bbox_km2(want), 5)
        self.assertAlmostEqual(want[0], self.TERR[0] - 60 / (111320 * 0.5629), delta=2e-5)

    def test_without_territory_big_frame_is_refused_with_message(self):
        layers, errors = S.fetch(self.FRAME, ["osm.roads", "egko.buildings"])
        self.assertEqual(layers, {})
        self.assertIn("территория слишком велика для OSM", errors["osm.roads"])
        self.assertIn("загрузите слои частями", errors["osm.roads"])
        self.assertIn("территория слишком велика для ЕГКО", errors["egko.buildings"])

    def test_two_limits_means_two_sequential_requests_with_pause_merged_and_deduped(self):
        calls, sleeps = [], []
        import math
        h = 0.1                                     # высота ~11 км; ширина ~1,7 x предела: две части
        w = 1.7 * 150 / (110.54 * h) / (111.32 * math.cos(math.radians(55.55)))
        b = [37.0, 55.5, 37.0 + w, 55.5 + h]
        self.assertGreater(S.bbox_km2(b), 150)
        self.assertEqual(len(S.split_bbox(b, S.TILE_KM2["egko"])), 2)
        with mock.patch.object(S, "GisogdApi", self._egko_fake(calls)), mock.patch.object(S.time, "sleep", lambda t: sleeps.append(t)):
            layers, errors = S.fetch(b, ["egko.fences"])
        self.assertEqual(errors, {})
        n_codes = len(S.SOURCES["egko.fences"][1])
        self.assertEqual(len(calls), 2 * n_codes)
        self.assertLess(calls[0][0], calls[-1][0], "части идут по очереди слева направо")
        self.assertEqual(sleeps, [S.TILE_PAUSE_S])
        keys = [f["properties"]["_key"] for f in layers["egko.fences"]["features"]["features"]]
        self.assertEqual(len(keys), len(set(keys)))                  # общий объект base2:a:1 — один раз
        self.assertEqual(keys.count("base2:a:1"), 1)

    def test_osm_sequential_tiles_and_cap(self):
        calls, sleeps = [], []
        def osm(bbox, sets, cache_dir=None):
            calls.append(list(bbox))
            return {"features": [], "source_doc": "OSM", "notes": []}
        h = 0.1
        import math
        w = lambda km2: km2 / (110.54 * h) / (111.32 * math.cos(math.radians(55.5 + h / 2)))
        with mock.patch.object(S, "osm_fetch", osm), mock.patch.object(S.time, "sleep", lambda t: sleeps.append(t)):
            layers, errors = S.fetch([37.0, 55.5, 37.0 + w(300), 55.5 + h], ["osm.roads"])
            self.assertEqual(errors, {})
            self.assertEqual(len(calls), len(sleeps) + 1)
            self.assertTrue(all(S.bbox_km2(c) <= S.TILE_KM2["osm"] for c in calls))
            calls.clear()
            layers, errors = S.fetch([37.0, 55.5, 37.0 + w(500), 55.5 + h], ["osm.roads"])
        self.assertEqual(calls, [])
        self.assertIn("территория слишком велика для OSM (", errors["osm.roads"])


class Yandex(unittest.TestCase):
    """Яндекс Карты — девять источников из тайлов vmap3; все слои одним проходом по тайлам, поля — по-русски."""
    FIX = Path(__file__).resolve().parents[3] / "core/connectors/tests/fixtures/yandex"

    def test_sources_and_limit(self):
        keys = [k for k in S.SOURCES if k.startswith("yandex.")]
        self.assertEqual(set(keys), {"yandex.hd_roads", "yandex.buildings", "yandex.roads", "yandex.road_edges", "yandex.landuse",
                                     "yandex.green", "yandex.water", "yandex.parking", "yandex.transport", "yandex.rail", "yandex.stations", "yandex.road_labels", "yandex.rail_stations"})   # топонимы Яндекса (#47)
        self.assertTrue(all(S.SOURCES[k][2].endswith("(Яндекс)") for k in keys))
        self.assertEqual(S.SOURCES["yandex.green"][1], ["vegetation", "vegetation_planned", "hd_road_vegetation"])
        self.assertFalse({"poi", "poi_navi"} & {n for k in keys for n in S.SOURCES[k][1]}, "POI и организации не выгружаются")
        self.assertEqual(S.LIMIT_KM2["yandex"], 40.0)
        layers, errors = S.fetch([37.3, 55.6, 37.6, 55.9], ["yandex.buildings"])
        self.assertIn("больше допустимых 40", errors["yandex.buildings"])

    def test_fetch_one_pass_and_readable_fields(self):
        from grado_connectors import yandex_vmap as yv
        fix, calls = self.FIX, []

        class Offline(yv.YandexVmap):
            def __init__(self, **kw):
                calls.append(kw)
                super().__init__(transport=self.read, pause=0)

            def read(self, url, timeout=None):
                q = dict(p.split("=") for p in url.split("?")[1].split("&"))
                f = fix / f"{q['z']}_{q['x']}_{q['y']}.pbf"
                return f.read_bytes() if f.exists() else b""
        # три тайла фикстуры углом; четвёртый тайл рамки отдаётся пустым
        (w, n), (e, s_) = yv.to_lonlat(*yv.tile_to_3395(18, 158445, 82054)(-3000, -3000)), yv.to_lonlat(*yv.tile_to_3395(18, 158446, 82055)(3000, 3000))
        old, S.YandexVmap = S.YandexVmap, Offline
        try:
            layers, errors = S.fetch([w, s_, e, n], ["yandex.buildings", "yandex.hd_roads", "yandex.roads"])
        finally:
            S.YandexVmap = old
        self.assertEqual(errors, {})
        self.assertEqual(len(calls), 1, "тайлы качаются один раз на все слои Яндекса")
        self.assertTrue(str(calls[0]["cache_dir"]).endswith("yandex"))
        b = [f["properties"] for f in layers["yandex.buildings"]["features"]["features"]]
        self.assertTrue(b and all(p["_key"].startswith("yandex:building:") for p in b))
        self.assertTrue(all(isinstance(p["Высота, м"], int) for p in b if "Высота, м" in p))
        self.assertTrue(all("Назначение" in p and "Площадь, м²" in p and "grado_layer" not in p for p in b))
        r = [f["properties"] for f in layers["yandex.hd_roads"]["features"]["features"]]
        self.assertTrue(r and all("Тип" in p and "type" not in p for p in r))
        self.assertTrue(all("Длина, м" in f["properties"] for f in layers["yandex.roads"]["features"]["features"]))
        self.assertIn("в сдаваемые материалы не включать", layers["yandex.buildings"]["source"])


class YandexSatBreaker(unittest.TestCase):
    """T75: 404 Яндекса («снимка нет») не считается сбоем; настоящие сбои по-прежнему отключают Яндекс на 10 минут."""

    def _run(self, exc, n):
        import tempfile
        import urllib.error
        import sat_io
        real = sat_io.YandexSat

        def transport(url):
            raise exc(url) if exc is urllib.error.HTTPError else exc("x")
        saved = dict(S._YSAT)
        S._YSAT.update({"fails": 0, "off_until": 0.0, "bad": {}})
        try:
            with tempfile.TemporaryDirectory() as d, mock.patch.object(S, "CACHE", Path(d)), \
                    mock.patch.object(sat_io.time, "sleep"), mock.patch.object(S.time, "sleep"), \
                    mock.patch.object(sat_io, "YandexSat", lambda p: real(p, pause=0, transport=transport)):
                for i in range(n):
                    self.assertIsNone(S.yandex_sat_tile(18, i, 7))
                return dict(S._YSAT)
        finally:
            S._YSAT.clear()
            S._YSAT.update(saved)

    def test_404_does_not_trip_breaker(self):
        import urllib.error
        st = self._run(lambda url: urllib.error.HTTPError(url, 404, "nf", None, None), 8)
        self.assertEqual(st["fails"], 0)
        self.assertEqual(st["off_until"], 0.0)
        self.assertEqual(len(st["bad"]), 8)                                      # но «нет снимка» запомнено

    def test_real_failures_trip_breaker(self):
        st = self._run(OSError, 5)
        self.assertGreater(st["off_until"], 0)


class SituationPlanSources(unittest.TestCase):
    """Ситуационный план: слои Яндекса с z16 в один поток, железная дорога — только главные пути."""

    def test_coarse_tiles_one_thread_main_tracks_only(self):
        keys = [k for k in S.SOURCES if k.startswith("sit.")]
        self.assertEqual(set(keys), {"sit.green", "sit.water", "sit.roads_hd", "sit.roads", "sit.buildings", "sit.rail", "sit.stations", "sit.road_labels", "sit.places"})   # станции, подписи улиц и названия территорий карты района (#47)
        self.assertTrue(all(S.SOURCES[k][0] == "yandex_sit" for k in keys))
        calls = []

        class Rec:
            def __init__(self, **kw):
                calls.append(kw)

            def fetch(self, bbox, layers):
                f = lambda t, name: {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[37.6, 55.8], [37.61, 55.8]]},
                                     "properties": {"grado_layer": "transport_way", "ft_type_name": name, "_key": t}}
                return {"features": [f("a", "transport-railway"), f("b", "transport-railway-siding")], "source": "Яндекс", "fetched_at": "x"}
        old, S.YandexVmap = S.YandexVmap, Rec
        try:
            layers, errors = S.fetch([37.6, 55.79, 37.7, 55.83], ["sit.rail"])
        finally:
            S.YandexVmap = old
        self.assertEqual(errors, {})
        self.assertEqual((calls[0]["zoom"], calls[0]["workers"]), (16, 1))
        self.assertEqual([f["properties"]["_key"] for f in layers["sit.rail"]["features"]["features"]], ["a"])   # без подъездных путей


class RailRoute(unittest.TestCase):
    """K1 по улицам: маршрут по пешеходной сети OSM до входа в метро (данные из кэша, без сети)."""
    def test_route_goes_around_the_block(self):
        import gzip, json as J, math, tempfile
        lon, lat = 37.60, 55.75
        kx, ky = 111320 * math.cos(math.radians(lat)), 110540
        ll = lambda x, y: [lon + x / kx, lat + y / ky]
        with tempfile.TemporaryDirectory() as d:
            old, S.CACHE = S.CACHE, Path(d)
            S._ROUTE_MEMO.clear(); S._PLACE_MEMO.clear()
            try:
                (Path(d) / "place").mkdir()
                key = (round(lon, 3), round(lat, 3))
                (Path(d) / "place" / f"{key[0]}_{key[1]}.json").write_text(J.dumps({"elements": [
                    {"type": "node", "lon": ll(400, 300)[0], "lat": ll(400, 300)[1], "tags": {"railway": "subway_entrance", "ref": "3"}}]}), "utf-8")
                # улица: от точки на восток 400 м, потом на север 300 м — по прямой 500 м, пешком 700 м
                ways = [[ll(0, 0), ll(400, 0)], [ll(400, 0), ll(400, 300)]]
                (Path(d) / "place" / f"walk_{key[0]}_{key[1]}_2400.json.gz").write_bytes(gzip.compress(J.dumps(ways).encode()))
                r = S.rail_route(lon, lat)
            finally:
                S.CACHE = old; S._ROUTE_MEMO.clear(); S._PLACE_MEMO.clear()
        self.assertEqual(r["route_m"], 700)
        self.assertEqual(r["straight_m"], 500)
        self.assertEqual(r["station"], "вход 3")


class Projects(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.old, S.PROJECTS = S.PROJECTS, Path(self.tmp.name) / "p"

    def tearDown(self):
        S.PROJECTS = self.old
        self.tmp.cleanup()

    def test_save_list_and_autosave_apart(self):
        S.save_project("Хорошёво", b'{"format": "grado2"}')
        S.save_project(".autosave", b'{"format": "grado2"}')
        r = S.list_projects()
        self.assertEqual([p["name"] for p in r["projects"]], ["Хорошёво"])
        self.assertIsNotNone(r["autosave"])
        self.assertEqual(S.project_path("Хорошёво").read_bytes(), b'{"format": "grado2"}')

    def test_list_carries_album_summary(self):
        alb = {"meta": {"builtAt": "2026-10-03T09:40:00.000Z"}, "sheets": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
        S.save_project("С альбомом", json.dumps({"format": "grado2", "album": alb}).encode())
        S.save_project("Без альбома", b'{"format": "grado2"}')
        S.save_project("Пустой", json.dumps({"format": "grado2", "album": {"meta": {}, "sheets": []}}).encode())
        by = {p["name"]: p for p in S.list_projects()["projects"]}
        self.assertEqual((by["С альбомом"]["album_n"], by["С альбомом"]["album_at"]), (3, "2026-10-03T09:40:00.000Z"))
        self.assertEqual((by["Без альбома"]["album_n"], by["Без альбома"]["album_at"]), (None, None))
        self.assertEqual(by["Пустой"]["album_n"], 0)
        S.save_project("С альбомом", json.dumps({"format": "grado2", "album": {"meta": {}, "sheets": [{}]}}).encode())   # запись новее — счёт заново
        self.assertEqual({p["name"]: p["album_n"] for p in S.list_projects()["projects"]}["С альбомом"], 1)

    def test_album_summary_skips_the_big_data(self):
        """Строка про альбом не требует разбора всего файла: альбом читается окном, большая граница и слои вокруг не мешают."""
        big = {"format": "grado2", "territory": {"p": "я" * 3_000_000},
               "album": {"meta": {"builtAt": "2026-10-03T12:40:00"}, "sheets": [{"id": i, "t": "а" * 700} for i in range(9)]},
               "layers": [{"k": "z" * 2_000_000}]}
        S.save_project("Большой", json.dumps(big, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        r = {p["name"]: p for p in S.list_projects()["projects"]}["Большой"]
        self.assertEqual((r["album_n"], r["album_at"]), (9, "2026-10-03T12:40:00"))
        S.save_project("Пустой файл", b"{}")
        self.assertIsNone({p["name"]: p for p in S.list_projects()["projects"]}["Пустой файл"]["album_n"])

    def test_names_cannot_escape_the_folder(self):
        for bad in ("../x", "a/b", "", ".hidden", "c:x"):
            with self.assertRaises(ValueError):
                S.project_path(bad)

    def test_broken_json_is_not_written(self):
        with self.assertRaises(ValueError):
            S.save_project("x", b"{not json")
        self.assertFalse(S.project_path("x").exists())


if __name__ == "__main__":
    unittest.main()


class PublicHost(unittest.TestCase):
    """За обратным прокси сервер принимает имя из GRADO2_PUBLIC_HOST, чужие имена и чужие страницы — нет."""

    def ask(self, host, origin=None):
        import os
        import threading
        import urllib.request
        srv = S.Server(("127.0.0.1", 0), S.Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/health", headers={"Host": host, **({"Origin": origin} if origin else {})})
            try:
                return urllib.request.urlopen(req, timeout=5).status
            except urllib.error.HTTPError as e:
                return e.code
        finally:
            srv.shutdown()
            srv.server_close()

    def test_public_host_from_env(self):
        import os
        from unittest import mock
        self.assertEqual(self.ask("grado.tailink.tech"), 403)
        with mock.patch.dict(os.environ, {"GRADO2_PUBLIC_HOST": "grado.tailink.tech"}):
            self.assertEqual(self.ask("grado.tailink.tech"), 200)
            self.assertEqual(self.ask("grado.tailink.tech", "https://grado.tailink.tech"), 200)
            self.assertEqual(self.ask("grado.tailink.tech", "https://evil.example"), 403)
            self.assertEqual(self.ask("evil.example"), 403)


class SplitArea(unittest.TestCase):
    """Область больше, чем НСПД или Overpass отдают за раз: части по очереди, объекты склеиваются."""

    def test_split_bbox_covers_area_with_small_parts(self):
        b = (37.50, 55.70, 37.62, 55.76)                       # ~7,5 × 6,6 км
        cells = S.split_bbox(b, 4.0)
        self.assertTrue(all(S.bbox_km2(c) <= 4.0 for c in cells))
        self.assertAlmostEqual(sum(S.bbox_km2(c) for c in cells), S.bbox_km2(b), places=3)
        self.assertEqual((min(c[0] for c in cells), max(c[3] for c in cells)), (b[0], b[3]))

    def test_nspd_over_limit_goes_by_parts_and_merges_duplicates(self):
        calls = []

        class FakeNspd:
            def fetch(self, bbox, cats):
                calls.append(tuple(bbox))
                f = lambda key: {"type": "Feature", "grado_key": key, "geometry": {"type": "Point", "coordinates": [37.55, 55.72]},
                                 "properties": {"cad_num": key}}
                return {"features": [f("77:01:1"), f(f"77:01:{len(calls) + 1}")], "notes": [], "source_doc": "НСПД"}
        with mock.patch.object(S, "NspdDirect", FakeNspd):
            layers, errors = S.fetch([37.50, 55.70, 37.56, 55.73], ["nspd.parcels"])   # ~3,8 × 3,3 км
        self.assertEqual(errors, {})
        self.assertGreater(len(calls), 1)
        keys = [f["properties"]["_key"] for f in layers["nspd.parcels"]["features"]["features"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(keys), len(calls) + 1)             # общий для всех частей участок — один раз
        self.assertEqual(S.PROGRESS, {})


class AnyOgdLayer(unittest.TestCase):
    """Любой слой каталога ГИС ОГД загружается в проект ключом «ogd.<код>» (окно «Исходные данные»)."""

    def test_ogd_key_fetches_that_layer(self):
        asked = []

        class FakeApi:
            def __init__(self, **kw):
                pass

            def fetch(self, bbox, code):
                asked.append(code)
                return {"features": [{"geometry": {"type": "Point", "coordinates": [37.6, 55.75]}, "properties": {"text": "т.з."}}],
                        "source_doc": "ГИС ОГД", "notes": []}
        cat = [{"code": "virtual25", "name": "Надписи технических зон", "type": "layer"}]
        with mock.patch.object(S, "ogd_catalog", return_value=cat), mock.patch.object(S, "GisogdApi", FakeApi):
            layers, errors = S.fetch([37.59, 55.74, 37.61, 55.76], ["ogd.virtual25", "ogd.nope"])
        self.assertEqual(errors, {})
        self.assertEqual(asked, ["virtual25"])
        self.assertEqual(layers["ogd.virtual25"]["title"], "Надписи технических зон (ОГД)")
        self.assertNotIn("ogd.nope", layers)
        S.SOURCES.pop("ogd.virtual25", None)


class ProjectVersions(unittest.TestCase):
    """Перед перезаписью проекта прежний файл сохраняется сжатой версией в .versions/<проект>/."""

    def test_previous_file_is_kept_and_old_versions_pruned(self):
        import gzip
        import tempfile
        with tempfile.TemporaryDirectory() as d, mock.patch.object(S, "PROJECTS", Path(d)):
            S.save_project("Участок", b'{"v": 1}')
            self.assertFalse((Path(d) / ".versions").exists())            # первой записи нечего хранить
            S.save_project("Участок", b'{"v": 2}')
            vs = list((Path(d) / ".versions" / "Участок").glob("*.grado2.gz"))
            self.assertEqual([gzip.decompress(v.read_bytes()) for v in vs], [b'{"v": 1}'])
            S.save_project("Участок", b'{"v": 3}')                        # 10 минут не прошло — новой версии нет
            self.assertEqual(len(list((Path(d) / ".versions" / "Участок").glob("*"))), 1)
            with mock.patch.object(S, "VERSIONS_EVERY", {True: 0, False: 0}), mock.patch.object(S, "VERSIONS_KEEP", 1):
                os.utime(vs[0], (0, 0))
                S.save_project("Участок", b'{"v": 4}')
            left = list((Path(d) / ".versions" / "Участок").glob("*.grado2.gz"))
            self.assertEqual(len(left), 1)
            self.assertEqual(gzip.decompress(left[0].read_bytes()), b'{"v": 3}')


class AdminReference(unittest.TestCase):
    """Административное деление — эталон владельца: район целиком в одном округе, округ — сумма его районов."""

    def test_okrugs_and_districts_from_reference(self):
        layers, errors = S.fetch((37.10, 55.40, 37.12, 55.41), ["gisogd.admin"])   # Вороново, ТАО
        self.assertEqual(errors, {})
        fs = layers["gisogd.admin"]["features"]["features"]
        okrugs = {f["properties"]["Наименование"] for f in fs if f["properties"]["Уровень"] == "округ"}
        districts = [f for f in fs if f["properties"]["Уровень"] == "район"]
        self.assertEqual(len(okrugs), 12)
        self.assertEqual(len(districts), 132)
        self.assertTrue(all(d["properties"]["Округ"] in okrugs for d in districts))
        self.assertTrue(all(f["properties"]["Граница"] == S.ADMIN_REV for f in fs if f["properties"]["Уровень"] == "округ"))
        self.assertEqual(layers["gisogd.admin"]["notes"], [])


class HttpHardening(unittest.TestCase):
    """Заголовки защиты, пределы тела, форма JSON, ответы об ошибках без подробностей, квота папки проектов."""

    def setUp(self):
        import tempfile
        import threading
        self.tmp = tempfile.TemporaryDirectory()                          # тест POST /api/project не должен писать в настоящую папку проектов
        self.old, S.PROJECTS = S.PROJECTS, Path(self.tmp.name) / "p"
        self.srv = S.Server(("127.0.0.1", 0), S.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        S.PROJECTS = self.old
        self.tmp.cleanup()

    def call(self, path, data=None):
        import json
        import urllib.error
        import urllib.request
        req = urllib.request.Request(self.base + path, data=data, method="POST" if data is not None else "GET")
        try:
            r = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as e:
            r = e
        body = r.read()
        return r.status if hasattr(r, "status") else r.code, r.headers, body, (json.loads(body) if body[:1] == b"{" else None)

    def test_security_headers_everywhere(self):
        for path, data in (("/api/health", None), ("/", None), ("/api/tep", b"{}"), ("/api/tep", b"[]")):
            _, h, _, _ = self.call(path, data)
            self.assertEqual(h["X-Content-Type-Options"], "nosniff", path)
            self.assertEqual(h["X-Frame-Options"], "DENY", path)
            self.assertIn("frame-ancestors 'none'", h["Content-Security-Policy"], path)
        csp = S.CSP
        self.assertIn("script-src 'self';", csp)
        self.assertNotIn("unsafe-eval", csp)
        self.assertNotIn("script-src 'self' 'unsafe", csp)
        self.assertIn("img-src 'self' data: blob: https:", csp)        # плитки Esri и EOX

    def test_tep_constants_and_norms_over_http(self):
        import json
        body = {"terr_ha": 15, "restrict_ha": 0, "spp_new_m2": 357000, "share": 1}
        code, _, _, j = self.call("/api/tep", json.dumps({**body, "constants": {"doo_z1": 50}}).encode())
        self.assertEqual((code, j["constants_changed"]), (200, ["doo_z1"]))
        for bad in ({"nope": 1}, {"doo_z1": 1e9}):
            code, _, _, j = self.call("/api/tep", json.dumps({**body, "constants": bad}).encode())
            self.assertEqual(code, 400)
            self.assertTrue(j["error"].isascii(), j["error"])
        code, _, _, j = self.call("/api/tep/norms")
        self.assertEqual(code, 200)
        self.assertEqual(len(j["norms"]), len(json.loads(S.PRESET.read_text("utf-8"))["constants"]))
        self.assertEqual(j["norms"][0].keys() >= {"id", "value", "title", "unit", "group", "source", "edition", "min", "max"}, True)

    def test_tep_parking_area_over_http_bad_share_is_400(self):
        import json
        body = {"terr_ha": 15, "restrict_ha": 0, "spp_new_m2": 357000, "share": 1}
        code, _, _, j = self.call("/api/tep", json.dumps({**body, "park_share_underground": 40}).encode())
        self.assertEqual(code, 200)
        self.assertEqual({x["id"]: x["value"] for x in j["metrics"]}["park_underground_m2"] > 0, True)
        for bad in ({"park_share_multi": 101}, {"park_share_underground": 2.5}, {"park_share_underground": 70, "park_share_multi": 40}):
            code, _, _, j = self.call("/api/tep", json.dumps({**body, **bad}).encode())
            self.assertEqual(code, 400, bad)
            self.assertTrue(j["error"].isascii(), j["error"])
        code, _, _, j = self.call("/api/tep/norms")
        ids = {x["id"]: x for x in j["norms"]}
        for k in ("park_m2_ground", "park_m2_underground", "park_m2_multi"):
            self.assertEqual((ids[k]["group"], ids[k]["status"], ids[k]["source"]), ("Стоянки и транспорт", "unverified", "проектное допущение — в постановлениях нет"))

    def test_local_project_40mb_body_saves(self):
        """Проект с данными и альбомом готовой вёрстки (импорт «Из файла…») больше 32 МБ: путь записи проекта принимает его."""
        self.assertGreaterEqual(S.body_limit("/api/project?name=x"), 128 * 2**20)
        self.assertGreater(S.body_limit("/api/project?autosave=1"), S.MAX_BODY)
        body = json.dumps({"format": "grado2", "pad": "x" * (40 * 2**20)}).encode()
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            old, S.PROJECTS = S.PROJECTS, Path(tmp) / "p"
            try:
                path = S.save_project("Большой", body)
                self.assertEqual(path.stat().st_size, len(body))
            finally:
                S.PROJECTS = old

    def test_body_limits_per_path(self):
        self.assertEqual(S.body_limit("/api/project?name=x"), S.MAX_PROJECT_BODY)
        self.assertEqual(S.body_limit("/api/project?autosave=1"), S.MAX_PROJECT_BODY)
        self.assertEqual(S.body_limit("/api/import/files"), S.MAX_BIG_BODY)
        self.assertEqual(S.body_limit("/api/tep"), S.MAX_BODY)
        self.assertEqual(S.body_limit("/api/fetch"), S.MAX_BODY)
        self.assertLess(S.MAX_BODY, S.MAX_BIG_BODY)

    def test_oversize_body_is_413_and_project_has_own_limit(self):
        with mock.patch.object(S, "MAX_BODY", 100):
            code, _, _, j = self.call("/api/tep", b'{"terr_ha":1,' + b" " * 200 + b"}")
            self.assertEqual(code, 413)
            self.assertIn("запрос больше", j["error"])
            self.assertEqual(self.call("/api/tep", b'{"terr_ha":1,"restrict_ha":0,"spp_new_m2":1,"share":1}')[0], 200)      # в пределе — проходит
            self.assertNotEqual(self.call("/api/place", b"{" + b" " * 200 + b"}")[0], 200)
            self.assertNotEqual(self.call("/api/project?name=zzz", b"{" + b" " * 200 + b"}")[0], 413)   # проект — свой предел

    def test_non_object_json_is_400(self):
        for path in ("/api/print/pdf", "/api/print/svg", "/api/export/dxf", "/api/fgistp/fetch", "/api/tep", "/api/import/files"):
            for body in (b"[]", b"5", b'"x"', b"null"):
                code, _, _, j = self.call(path, body)
                self.assertEqual(code, 400, (path, body))
                self.assertIn("JSON-объект", j["error"])

    def test_unexpected_error_is_generic_and_logged(self):
        import io
        err = io.StringIO()
        with mock.patch.object(S, "tep", side_effect=RuntimeError("секрет /etc/passwd")), mock.patch("sys.stderr", err):
            code, _, body, j = self.call("/api/tep", b"{}")
        self.assertEqual(code, 500)
        self.assertEqual(j["error"], S.INTERNAL_ERROR)
        self.assertNotIn(b"passwd", body)
        self.assertIn("RuntimeError: секрет /etc/passwd", err.getvalue())

    def test_project_save_returns_name_and_quota(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d, mock.patch.object(S, "PROJECTS", Path(d)):
            code, _, _, j = self.call("/api/project?name=proba", b'{"a":1}')
            self.assertEqual((code, j["saved"]), (200, "proba"))
            with mock.patch.object(S, "PROJECTS_CAP", 10):
                code, _, _, j = self.call("/api/project?name=proba2", b'{"a":1}')
                self.assertEqual(code, 507)
                self.assertFalse((Path(d) / "proba2.grado2").exists())

    def test_handler_has_socket_timeout(self):
        self.assertEqual(S.Handler.timeout, 120)

    def test_kill_only_our_server(self):
        self.assertFalse(S._is_our_process(os.getpid()))            # процесс тестов — не server.py
        self.assertFalse(S._is_our_process(None))
        self.assertFalse(S._is_our_process(1))
        ok = mock.Mock(stdout="/venv/bin/python apps/grado2/server.py\n")
        with mock.patch("subprocess.run", return_value=ok):
            self.assertTrue(S._is_our_process(4242))
        with mock.patch("subprocess.run", return_value=mock.Mock(stdout="nginx: worker process\n")):
            self.assertFalse(S._is_our_process(4242))


class AccessToken(unittest.TestCase):
    """Необязательный ключ доступа GRADO2_TOKEN: выключен — всё как прежде; включён — без куки или заголовка только вход."""
    TOKEN = "test-key-for-unit-tests"

    def setUp(self):
        import threading
        self.srv = S.Server(("127.0.0.1", 0), S.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.port = self.srv.server_address[1]
        S._LOGIN_FAILS.clear()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        S._LOGIN_FAILS.clear()

    def on(self):
        return mock.patch.object(S, "TOKEN", self.TOKEN)

    def call(self, path, body=None, headers=None, method=None):
        import http.client
        import json
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        data = None if body is None else json.dumps(body).encode()
        c.request(method or ("POST" if data is not None else "GET"), path, body=data, headers={"Content-Type": "application/json", **(headers or {})})
        r = c.getresponse()
        raw = r.read()
        c.close()
        return r.status, r, (json.loads(raw) if raw[:1] == b"{" else raw)

    def test_off_by_default_nothing_changes(self):
        self.assertEqual(S.TOKEN, "")                                  # тесты не зависят от окружения владельца
        self.assertEqual(self.call("/api/sources")[0], 200)
        self.assertEqual(self.call("/")[0], 200)
        self.assertEqual(self.call("/api/login", {"token": "x"})[0], 404)   # без ключа такого метода нет

    def test_empty_token_means_off(self):
        with mock.patch.object(S, "TOKEN", ""):
            self.assertEqual(self.call("/api/sources")[0], 200)

    def test_health_and_login_page_open(self):
        with self.on():
            s, _, body = self.call("/api/health")
            self.assertEqual(s, 200)
            self.assertIn("version", body)
            self.assertEqual(self.call("/login.html")[0], 200)
            self.assertEqual(self.call("/login.js")[0], 200)

    def test_deploy_probes_work_from_loopback_only_without_proxy_headers(self):
        with self.on():
            self.assertEqual(self.call("/api/progress")[0], 200)
            self.assertEqual(self.call("/api/ogd_all/status")[0], 200)
            self.assertEqual(self.call("/api/progress", headers={"X-Forwarded-For": "203.0.113.5"})[0], 401)
            self.assertEqual(self.call("/api/sources")[0], 401)       # остальное чтение закрыто и с loopback

    def test_unauthenticated_page_redirects_and_api_is_401(self):
        with self.on():
            for path in ("/", "/index.html"):
                s, r, _ = self.call(path)
                self.assertEqual((s, r.getheader("Location")), (302, "/login.html"), path)
            s, _, body = self.call("/api/sources")
            self.assertEqual((s, body), (401, {"error": "нужен вход"}))
            self.assertEqual(self.call("/app.js")[0], 401)
            self.assertEqual(self.call("/api/tep", {"terr_ha": 1})[0], 401)
            self.assertEqual(self.call("/", method="HEAD")[0], 302)

    def test_wrong_token_is_401_without_cookie(self):
        with self.on():
            s, r, body = self.call("/api/login", {"token": "nope"})
            self.assertEqual((s, r.getheader("Set-Cookie")), (401, None))
            self.assertNotIn(self.TOKEN, str(body))
            self.assertEqual(self.call("/api/login", {"token": 5})[0], 401)
            self.assertEqual(self.call("/api/login", {})[0], 401)

    def test_right_token_sets_strict_httponly_cookie_which_passes(self):
        with self.on():
            s, r, body = self.call("/api/login", {"token": self.TOKEN})
            self.assertEqual((s, body), (200, {"ok": True}))
            cookie = r.getheader("Set-Cookie")
            self.assertIn(f"grado_token={self.TOKEN};", cookie)
            for part in ("HttpOnly", "SameSite=Strict", "Max-Age=2592000", "Path=/"):
                self.assertIn(part, cookie)
            self.assertNotIn("Secure", cookie)                          # прямое http без прокси
            sent = {"Cookie": cookie.split(";")[0]}
            self.assertEqual(self.call("/api/sources", headers=sent)[0], 200)
            self.assertEqual(self.call("/", headers=sent)[0], 200)
            self.assertEqual(self.call("/api/sources", headers={"Cookie": "a=b; grado_token=wrong"})[0], 401)

    def test_secure_flag_behind_tls_proxy(self):
        with self.on():
            _, r, _ = self.call("/api/login", {"token": self.TOKEN}, {"X-Forwarded-Proto": "https"})
            self.assertIn("; Secure", r.getheader("Set-Cookie"))

    def test_header_passes(self):
        with self.on():
            self.assertEqual(self.call("/api/sources", headers={"X-Grado-Token": self.TOKEN})[0], 200)
            self.assertEqual(self.call("/api/sources", headers={"X-Grado-Token": "x"})[0], 401)

    def test_logout_clears_cookie(self):
        with self.on():
            s, r, _ = self.call("/api/logout", {})
            self.assertEqual(s, 200)
            self.assertIn("Max-Age=0", r.getheader("Set-Cookie"))

    def test_lockout_after_ten_failures_per_client(self):
        with self.on():
            for _ in range(S.LOGIN_TRIES):
                self.assertEqual(self.call("/api/login", {"token": "bad"}, {"X-Forwarded-For": "198.51.100.7"})[0], 401)
            self.assertEqual(self.call("/api/login", {"token": "bad"}, {"X-Forwarded-For": "198.51.100.7"})[0], 429)
            self.assertEqual(self.call("/api/login", {"token": self.TOKEN}, {"X-Forwarded-For": "198.51.100.7"})[0], 429)   # и верный — после минуты
            self.assertEqual(self.call("/api/login", {"token": self.TOKEN}, {"X-Forwarded-For": "198.51.100.8"})[0], 200)   # другой клиент не задет
            with mock.patch.object(S.time, "time", return_value=S.time.time() + S.LOGIN_WINDOW + 1):
                self.assertEqual(self.call("/api/login", {"token": self.TOKEN}, {"X-Forwarded-For": "198.51.100.7"})[0], 200)

    def test_compare_is_constant_time_and_token_not_in_urls_or_logs(self):
        with self.on(), mock.patch.object(S.hmac, "compare_digest", wraps=S.hmac.compare_digest) as cd:
            self.call("/api/login", {"token": "bad"})
            self.call("/api/sources", headers={"X-Grado-Token": "bad"})
            self.assertGreaterEqual(cd.call_count, 2)
            for c in cd.call_args_list:
                self.assertTrue(all(isinstance(a, bytes) for a in c.args))   # сравнение по байтам
        self.assertTrue(S.same_token("ключ", "ключ"))
        self.assertFalse(S.same_token("ключ", "ключ2"))

    def test_login_body_limit_and_shape(self):
        with self.on():
            self.assertEqual(self.call("/api/login", [1])[0], 400)
            self.assertEqual(self.call("/api/login", {"token": "x" * 5000})[0], 413)


class HubHttp(unittest.TestCase):
    """Совместный режим (GRADO2_HUB=1): настоящий сервер на свободном порту, хаб во временной папке.
    Вход по куке grado_session, проекты с ролями, push и конфликт, события SSE, закрытые локальные проекты."""

    @classmethod
    def setUpClass(cls):
        import threading
        cls.srv = S.Server(("127.0.0.1", 0), S.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.port = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [mock.patch.object(S.hubmod, "SCRYPT_N", 2 ** 4)]      # быстрый scrypt: в тестах не нужна стойкость
        for p in self.patches:
            p.start()
        self.hub = S.hubmod.Hub(Path(self.tmp.name) / "hub")
        self.hub_patch = mock.patch.object(S, "HUB", self.hub)
        self.hub_patch.start()
        self.hub.create_user("boss", "password-boss", "Начальник", admin=True)
        self.hub.create_user("ann", "password-ann", "Анна")
        self.hub.create_user("vic", "password-vic", "Виктор")

    def tearDown(self):
        self.hub_patch.stop()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def call(self, path, body=None, cookie=None, headers=None, method=None, raw=None, ctype="application/json"):
        import http.client
        import json
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        h = {**({"Content-Type": ctype} if data is not None else {}), **({"Cookie": cookie} if cookie else {}), **(headers or {})}
        c.request(method or ("POST" if data is not None else "GET"), path, body=data, headers=h)
        r = c.getresponse()
        payload = r.read()
        c.close()
        return r.status, r, (json.loads(payload) if payload[:1] in (b"{", b"[") else payload)

    def login(self, login, password=None):
        s, r, j = self.call("/api/hub/login", {"login": login, "password": password or f"password-{login if login != 'boss' else 'boss'}"})
        self.assertEqual(s, 200, j)
        return r.getheader("Set-Cookie").split(";")[0]

    def test_search_routes_need_session(self):
        for path in ("/api/search?q=x", "/api/search/address?q=x", "/api/search/cadastral?q=50:27:0000000:126"):
            with mock.patch.object(S.nspd_mod, "search_cadastral") as m, mock.patch.object(S.geocode_mod, "geocode") as g:
                self.assertEqual(self.call(path)[0], 401, path)
                self.assertFalse(m.called or g.called)               # до порталов без входа не доходит

    def new_project(self, cookie, name="Тест"):
        s, _, j = self.call("/api/hub/projects", {"name": name}, cookie)
        self.assertEqual(s, 200, j)
        return j["id"]

    def test_guest_mode(self):
        """GRADO2_GUEST=1 (владелец 06.10.2026): сайт открывается гостем без пароля; гость — не администратор, видит только
        проекты, куда позван; после «Выйти» — экран входа (кука grado_noguest), кнопка «Войти гостем» возвращает гостя."""
        self.assertEqual(self.call("/api/hub/guest", {})[0], 403)                 # выключено — гостевого входа нет
        with mock.patch.object(S, "GUEST", True):
            s, r, j = self.call("/api/hub/me")
            self.assertEqual((s, j["user"]["login"], j["user"]["admin"], j["user"].get("guest")), (200, "guest", False, True))
            guest = r.getheader("Set-Cookie").split(";")[0]
            self.assertEqual(self.call("/api/hub/me", cookie=guest)[2]["user"]["name"], "Гость")
            ann = self.login("ann")
            pid = self.new_project(ann, "Чужой")
            self.assertEqual(self.call("/api/hub/projects", cookie=guest)[2]["projects"], [])     # чужие проекты не видны
            self.assertEqual(self.call("/api/hub/invites", {}, guest)[0], 403)                    # приглашать может только администратор
            self.assertEqual(self.call("/api/hub/login", {"login": "guest", "password": ""})[0], 401)   # по паролю гостем не войти
            s, _, j = self.call(f"/api/hub/project/{pid}/members", {"login": "guest", "role": "editor"}, ann)
            self.assertEqual(s, 200, j)
            self.assertEqual([p["id"] for p in self.call("/api/hub/projects", cookie=guest)[2]["projects"]], [pid])   # позвали — виден
            s, r, _ = self.call("/api/hub/logout", {}, guest)
            out = r.getheader("Set-Cookie")
            self.assertIn("grado_noguest=1", out)
            s, _, j = self.call("/api/hub/me", cookie="grado_noguest=1")
            self.assertEqual((s, j.get("guest")), (401, True))                     # экран входа с кнопкой «Войти гостем»
            s, r, j = self.call("/api/hub/guest", {}, "grado_noguest=1")
            self.assertEqual((s, j["user"]["login"]), (200, "guest"))
            self.assertIn("grado_noguest=; ", r.getheader("Set-Cookie"))
        self.hub.update_user(self.hub.session_user(self.login("boss").split("=", 1)[1]), "guest", disabled=True)
        with mock.patch.object(S, "GUEST", True):
            self.assertEqual(self.call("/api/hub/me")[0], 403)                    # администратор отключил гостя

    @staticmethod
    def layer(title="Слой", n=0):
        return {"spec": {"title": title, "geom": "poly"}, "data": {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"_uid": f"{i:012x}"}, "geometry": None} for i in range(n)]}}

    # ----- вход и закрытые места -----

    def test_health_has_hub_flag_and_keeps_version_match(self):
        s, r, j = self.call("/api/health")
        self.assertEqual((s, j["hub"]), (200, True))
        with mock.patch.object(S, "HUB", None):
            j = self.call("/api/health")[2]
            self.assertIs(j["hub"], False)
            self.assertIn("pid", j)
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port)
        c.request("GET", "/api/health")
        raw = c.getresponse().read().decode()
        c.close()
        self.assertIn(f'"version": "{S.VERSION}"', raw)             # по этой строке скрипт выкладки сверяет версию

    def test_everything_but_the_public_list_needs_a_session(self):
        for path in ("/api/sources", "/api/hub/projects", "/api/hub/users", "/api/progress.x", "/api/hub/project/" + "0" * 16):
            s, _, j = self.call(path)
            self.assertEqual((s, j), (401, {"error": "нужен вход"}), path)
        for path, body in (("/api/tep", {"terr_ha": 1}), ("/api/fetch", {}), ("/api/hub/projects", {"name": "x"}),
                           ("/api/hub/logout", {}), ("/api/ogd_all/cancel", {}), ("/api/import/files", {})):
            self.assertEqual(self.call(path, body)[0], 401, path)
        self.assertEqual(self.call("/api/hub/me")[0], 401)
        self.assertEqual(self.call("/")[0], 200)                    # статика открыта: из неё строится экран входа
        self.assertEqual(self.call("/api/health")[0], 200)
        self.assertEqual(self.call("/api/progress")[0], 200)        # проба выкладки с loopback, как и при ключе доступа
        self.assertEqual(self.call("/api/progress", headers={"X-Forwarded-For": "203.0.113.5"})[0], 401)
        self.assertEqual(self.call("/api/hub/me", headers={"Cookie": "grado_session=" + "x" * 40})[0], 401)

    def test_login_cookie_flags_and_me(self):
        s, r, j = self.call("/api/hub/login", {"login": "ann", "password": "password-ann"})
        self.assertEqual((s, j), (200, {"user": {"login": "ann", "name": "Анна", "admin": False}}))
        cookie = r.getheader("Set-Cookie")
        for part in ("grado_session=", "HttpOnly", "SameSite=Lax", "Max-Age=2592000", "Path=/"):
            self.assertIn(part, cookie)
        self.assertNotIn("Secure", cookie)
        self.assertNotIn("Strict", cookie)
        _, r2, _ = self.call("/api/hub/login", {"login": "ann", "password": "password-ann"}, headers={"X-Forwarded-Proto": "https"})
        self.assertIn("; Secure", r2.getheader("Set-Cookie"))
        self.assertEqual(self.call("/api/hub/me", cookie=cookie.split(";")[0])[2]["user"]["login"], "ann")
        self.assertEqual(self.call("/api/sources", cookie=cookie.split(";")[0])[0], 200)
        s, r3, j = self.call("/api/hub/login", {"login": "ann", "password": "nope-nope"})
        self.assertEqual((s, j["error"], r3.getheader("Set-Cookie")), (401, "неверный логин или пароль", None))

    def test_session_only_from_cookie(self):
        token = self.login("ann").split("=", 1)[1]
        for h in ({"X-Grado-Token": token}, {"Authorization": "Bearer " + token}, {"X-Grado-Session": token}):
            self.assertEqual(self.call("/api/hub/me", headers=h)[0], 401)
        self.assertEqual(self.call("/api/hub/me?grado_session=" + token)[0], 401)

    def test_logout_ends_session_and_clears_cookie(self):
        cookie = self.login("ann")
        s, r, _ = self.call("/api/hub/logout", {}, cookie)
        self.assertEqual(s, 200)
        self.assertIn("Max-Age=0", r.getheader("Set-Cookie"))
        self.assertEqual(self.call("/api/hub/me", cookie=cookie)[0], 401)

    def test_register_by_invite(self):
        admin = self.login("boss")
        s, _, j = self.call("/api/hub/invites", {}, admin)
        self.assertEqual(s, 200)
        code = j["code"]
        self.assertEqual(self.call("/api/hub/invites", {}, self.login("ann"))[0], 403)       # приглашения — только администратору
        s, r, j = self.call("/api/hub/register", {"invite": code, "login": "newbie", "name": "Новичок", "password": "password-new"})
        self.assertEqual((s, j["user"]["login"]), (200, "newbie"))
        self.assertIn("grado_session=", r.getheader("Set-Cookie"))
        self.assertEqual(self.call("/api/hub/register", {"invite": code, "login": "other1", "name": "", "password": "password-new"})[0], 403)
        self.assertEqual(self.call("/api/hub/me", cookie=r.getheader("Set-Cookie").split(";")[0])[2]["user"]["name"], "Новичок")

    def test_local_project_endpoints_are_closed(self):
        cookie = self.login("ann")
        for path, body in (("/api/projects", None), ("/api/project?name=x", None), ("/api/project?autosave=1", b'{"a":1}')):
            s, _, j = self.call(path, raw=body, cookie=cookie)
            self.assertEqual(s, 403, path)
            self.assertIn("Совместные проекты", j["error"])
        self.assertEqual(self.call("/api/project?name=x")[0], 401)      # без входа — сначала вход

    def test_token_gate_env_is_ignored_in_hub_mode(self):
        with mock.patch.object(S, "TOKEN", "secret-key-xyz"):
            s, r, _ = self.call("/")
            self.assertEqual(s, 200)                                    # не 302 на login.html
            self.assertEqual(self.call("/api/sources", headers={"X-Grado-Token": "secret-key-xyz"})[0], 401)
            self.assertEqual(self.call("/api/sources", headers={"Cookie": "grado_token=secret-key-xyz"})[0], 401)
            self.assertEqual(self.call("/api/login", {"token": "secret-key-xyz"}, cookie=self.login("ann"))[0], 404)
            cookie = self.login("ann")                                   # вход по учётной записи работает без ключа
            self.assertEqual(self.call("/api/sources", cookie=cookie)[0], 200)

    # ----- формат запроса и пределы -----

    def test_hub_post_needs_json_content_type(self):
        cookie = self.login("ann")
        for ctype in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x"):
            s, _, j = self.call("/api/hub/projects", raw=b'{"name":"x"}', cookie=cookie, ctype=ctype)
            self.assertEqual(s, 415, ctype)
        self.assertEqual(self.call("/api/hub/login", raw=b'{"login":"ann","password":"password-ann"}', ctype="text/plain")[0], 415)
        self.assertEqual(self.call("/api/hub/projects", raw=b'{"name":"x"}', cookie=cookie, ctype="application/json; charset=utf-8")[0], 200)

    def test_foreign_origin_is_denied(self):
        cookie = self.login("ann")
        self.assertEqual(self.call("/api/hub/projects", {"name": "x"}, cookie, headers={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.call("/api/hub/projects", cookie=cookie, headers={"Host": "evil.example"})[0], 403)

    def test_body_limits(self):
        pid = "a" * 16
        self.assertEqual(S.body_limit("/api/hub/projects"), S.MAX_PROJECT_BODY)
        self.assertEqual(S.body_limit(f"/api/hub/project/{pid}/push"), S.MAX_PROJECT_BODY)
        for p in ("/api/hub/login", f"/api/hub/project/{pid}", f"/api/hub/project/{pid}/comments", f"/api/hub/project/{pid}/members",
                  f"/api/hub/project/{pid}/push/x", "/api/hub/projects/x"):
            self.assertEqual(S.body_limit(p), S.MAX_HUB_BODY, p)
        self.assertEqual(S.MAX_HUB_BODY, 2 ** 20)
        cookie = self.login("ann")
        with mock.patch.object(S, "MAX_HUB_BODY", 100):
            s, _, j = self.call("/api/hub/login", raw=b'{"login":"a",' + b" " * 200 + b'"password":"b"}')
            self.assertEqual(s, 413)
            self.assertEqual(self.call("/api/hub/projects", raw=b'{"name":"x"' + b" " * 200 + b"}", cookie=cookie)[0], 200)   # создание — предел проекта

    def test_malformed_body_is_400_without_details(self):
        cookie = self.login("ann")
        for raw in (b"{not json", b"[]", b"5"):
            s, _, j = self.call("/api/hub/projects", raw=raw, cookie=cookie)
            self.assertEqual(s, 400, raw)
            self.assertNotIn("Expecting", str(j))

    def test_unexpected_error_is_generic_and_logged(self):
        import io
        cookie = self.login("ann")
        err = io.StringIO()
        with mock.patch.object(self.hub, "list_projects", side_effect=RuntimeError("секрет /etc/passwd")), mock.patch("sys.stderr", err):
            s, _, j = self.call("/api/hub/projects", cookie=cookie)
        self.assertEqual((s, j["error"]), (500, S.INTERNAL_ERROR))
        self.assertIn("RuntimeError", err.getvalue())
        err = io.StringIO()
        with mock.patch.object(self.hub, "list_projects", side_effect=S.hubmod.HubError(500, "файл users.json повреждён")), mock.patch("sys.stderr", err):
            s, _, j = self.call("/api/hub/projects", cookie=cookie)
        self.assertEqual((s, j["error"]), (500, S.INTERNAL_ERROR))
        self.assertIn("users.json", err.getvalue())                   # причина в журнале, клиенту не уходит

    # ----- проекты, роли, запись -----

    def test_project_create_get_push_and_stale_push_conflict(self):
        ann, vic = self.login("ann"), self.login("vic")
        pid = self.new_project(ann)
        s, _, j = self.call("/api/hub/projects", cookie=ann)
        self.assertEqual([p["id"] for p in j["projects"]], [pid])
        self.assertEqual(self.call("/api/hub/projects", cookie=vic)[2]["projects"], [])
        s, _, j = self.call(f"/api/hub/project/{pid}", cookie=ann)
        self.assertEqual((s, j["role"], j["rev"]), (200, "owner", 1))
        self.assertIn("meta", j["sections"])
        self.assertEqual(self.call(f"/api/hub/project/{pid}", cookie=vic)[0], 403)
        # доступ: Анна даёт Виктору правку
        s, _, j = self.call(f"/api/hub/project/{pid}/members", {"login": "vic", "role": "editor"}, ann)
        self.assertEqual((s, {m["login"]: m["role"] for m in j["members"]}), (200, {"ann": "owner", "vic": "editor"}))
        s, _, j = self.call(f"/api/hub/project/{pid}/push", {"base_rev": 1, "client": "cA", "sections": {"layer:a": self.layer("А", 2)}}, ann)
        self.assertEqual((s, j), (200, {"rev": 2}))
        s, _, j = self.call(f"/api/hub/project/{pid}/push", {"base_rev": 1, "client": "cB", "sections": {"layer:a": self.layer("Б")}}, vic)
        self.assertEqual(s, 409)
        self.assertEqual(j["rev"], 2)
        self.assertEqual(j["conflicts"]["layer:a"]["rev"], 2)
        self.assertEqual(j["conflicts"]["layer:a"]["value"]["spec"]["title"], "А")
        self.assertIn("error", j)
        # после слияния — повторная запись на свежей ревизии проходит
        s, _, j = self.call(f"/api/hub/project/{pid}/push", {"base_rev": 2, "client": "cB", "sections": {"layer:a": self.layer("Б")}}, vic)
        self.assertEqual((s, j), (200, {"rev": 3}))
        s, _, j = self.call(f"/api/hub/project/{pid}/sections?names=layer:a,meta", cookie=ann)
        self.assertEqual((s, j["rev"], j["sections"]["layer:a"]["spec"]["title"]), (200, 3, "Б"))

    def test_viewer_cannot_push_but_can_comment(self):
        ann, vic = self.login("ann"), self.login("vic")
        pid = self.new_project(ann)
        self.call(f"/api/hub/project/{pid}/members", {"login": "vic", "role": "viewer"}, ann)
        s, _, j = self.call(f"/api/hub/project/{pid}/push", {"base_rev": 1, "client": "cV", "sections": {"layer:x": self.layer()}}, vic)
        self.assertEqual(s, 403)
        self.assertIn("только просмотр", j["error"])
        s, _, j = self.call(f"/api/hub/project/{pid}/comments", {"text": "Вопрос по границе", "anchor": {"lonlat": [37.6, 55.7]}}, vic)
        self.assertEqual((s, j["comment"]["author"]), (200, "vic"))
        cid = j["comment"]["id"]
        self.assertEqual(self.call(f"/api/hub/project/{pid}/comments", cookie=ann)[2]["comments"][0]["id"], cid)
        s, _, j = self.call(f"/api/hub/project/{pid}/comments/{cid}/reply", {"text": "Ответ"}, ann)
        self.assertEqual((s, len(j["comment"]["replies"])), (200, 1))
        s, _, j = self.call(f"/api/hub/project/{pid}/comments/{cid}", {"resolved": True}, ann)
        self.assertTrue(j["comment"]["resolved"])
        self.assertEqual(self.call(f"/api/hub/project/{pid}/comments/{cid}/delete", {}, vic)[0], 200)        # автор удаляет свой
        self.assertEqual(self.call(f"/api/hub/project/{pid}/comments", cookie=ann)[2]["comments"], [])

    def test_members_route_needs_explicit_role_and_owner(self):
        ann, vic = self.login("ann"), self.login("vic")
        pid = self.new_project(ann)
        s, _, j = self.call(f"/api/hub/project/{pid}/members", {"login": "vic"}, ann)
        self.assertEqual(s, 400)                                     # пропуск role не означает «убрать»
        self.assertEqual(self.call(f"/api/hub/project/{pid}/members", {"login": "vic", "role": "editor"}, vic)[0], 403)
        self.assertEqual(self.call(f"/api/hub/project/{pid}/members", {"login": "ghost", "role": "editor"}, ann)[0], 404)

    def test_rename_history_restore_delete(self):
        ann = self.login("ann")
        pid = self.new_project(ann, "Старое")
        s, _, j = self.call(f"/api/hub/project/{pid}", {"name": "Новое"}, ann)
        self.assertEqual((s, j), (200, {"name": "Новое"}))
        self.call(f"/api/hub/project/{pid}/push", {"base_rev": 2, "client": "c1", "sections": {"layer:a": self.layer("А", 1)}}, ann)
        s, _, j = self.call(f"/api/hub/project/{pid}/history", cookie=ann)
        self.assertEqual(s, 200)
        self.assertTrue(j["history"] and {"rev", "t", "login", "size"} <= set(j["history"][0]))
        s, _, j = self.call(f"/api/hub/project/{pid}/activity", cookie=ann)
        self.assertTrue(j["activity"])
        rev = self.call(f"/api/hub/project/{pid}/history", cookie=ann)[2]["history"][-1]["rev"]
        s, _, j = self.call(f"/api/hub/project/{pid}/history/{rev}/restore", {}, ann)
        self.assertEqual(s, 200)
        self.assertIn("rev", j)
        self.assertEqual(self.call(f"/api/hub/project/{pid}/history/x/restore", {}, ann)[0], 400)
        self.assertEqual(self.call(f"/api/hub/project/{pid}/delete", {}, self.login("vic"))[0], 403)
        self.assertEqual(self.call(f"/api/hub/project/{pid}/delete", {}, ann)[0], 200)
        self.assertEqual(self.call(f"/api/hub/project/{pid}", cookie=ann)[0], 404)

    def test_download_has_ascii_fallback_and_rfc5987_name(self):
        ann = self.login("ann")
        pid = self.new_project(ann, "Хорошёво: КРТ №3")
        s, r, raw = self.call(f"/api/hub/project/{pid}/download", cookie=ann)
        self.assertEqual(s, 200)
        disp = r.getheader("Content-Disposition")
        disp.encode("ascii")                                          # заголовок HTTP — только ASCII
        self.assertTrue(disp.startswith("attachment; filename=\""))
        self.assertIn("filename*=UTF-8''", disp)
        self.assertIn("%D0%A5%D0%BE%D1%80", disp)
        self.assertEqual(raw["format"], "grado2")

    def test_user_admin_routes(self):
        boss, ann = self.login("boss"), self.login("ann")
        s, _, j = self.call("/api/hub/users", cookie=boss)
        self.assertEqual((s, sorted(u["login"] for u in j["users"])), (200, ["ann", "boss", "vic"]))
        self.assertEqual(self.call("/api/hub/users", cookie=ann)[0], 403)
        s, _, j = self.call("/api/hub/users/vic", {"disabled": True}, boss)
        self.assertEqual((s, j["user"]["disabled"]), (200, True))
        self.assertEqual(self.call("/api/hub/login", {"login": "vic", "password": "password-vic"})[0], 403)
        self.assertEqual(self.call("/api/hub/users/vic", {"pw": "x"}, boss)[0], 400)
        self.assertEqual(self.call("/api/hub/password", {"old": "password-ann", "new": "password-ann-2"}, ann)[0], 200)
        self.assertEqual(self.call("/api/hub/login", {"login": "ann", "password": "password-ann-2"})[0], 200)

    def test_admin_sees_every_project(self):
        pid = self.new_project(self.login("ann"))
        s, _, j = self.call("/api/hub/projects", cookie=self.login("boss"))
        self.assertEqual([(p["id"], p["role"]) for p in j["projects"]], [(pid, "admin")])

    def test_ogd_job_only_for_starter_or_admin(self):
        ann, vic, boss = self.login("ann"), self.login("vic"), self.login("boss")
        with mock.patch.dict(S.OGD_OWNER, {"login": "ann"}), mock.patch.object(S, "OGD_JOB", []):
            self.assertEqual(self.call("/api/ogd_all/cancel", {}, vic)[0], 403)
            self.assertEqual(self.call("/api/ogd_all/file", cookie=vic)[0], 403)
            self.assertEqual(self.call("/api/ogd_all/cancel", {}, ann)[0], 200)
            self.assertEqual(self.call("/api/ogd_all/file", cookie=ann)[0], 404)       # его файл: доступ есть, файла ещё нет
            self.assertEqual(self.call("/api/ogd_all/cancel", {}, boss)[0], 200)
            self.assertEqual(self.call("/api/ogd_all/status", cookie=vic)[0], 200)

    # ----- события -----

    def open_stream(self, pid, cookie):
        """Поток событий в отдельной нити: возвращает (соединение, ответ, очередь событий)."""
        import http.client
        import json
        import queue
        import threading
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", f"/api/hub/project/{pid}/events", headers={"Cookie": cookie})
        r = c.getresponse()
        q = queue.Queue()

        def pump():
            try:
                while True:
                    line = r.readline()
                    if not line:
                        q.put(None)
                        return
                    if line.startswith(b"data: "):
                        q.put(json.loads(line[6:]))
                    elif line.startswith(b": ping"):
                        q.put({"type": "ping"})
            except (OSError, ValueError):
                q.put(None)
        threading.Thread(target=pump, daemon=True).start()
        return c, r, q

    def test_sse_headers_and_rev_event_from_another_session(self):
        import queue
        ann, vic = self.login("ann"), self.login("vic")
        pid = self.new_project(ann)
        self.call(f"/api/hub/project/{pid}/members", {"login": "vic", "role": "editor"}, ann)
        c, r, q = self.open_stream(pid, ann)
        try:
            self.assertEqual(r.status, 200)
            self.assertTrue(r.getheader("Content-Type").startswith("text/event-stream"))
            self.assertEqual(r.getheader("X-Accel-Buffering"), "no")
            self.assertEqual(r.getheader("Cache-Control"), "no-cache")
            self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff")
            self.assertIn("frame-ancestors", r.getheader("Content-Security-Policy"))
            first = q.get(timeout=3)
            self.assertEqual(first["type"], "presence")                # новая подписка сразу видит, кто в проекте
            s, _, j = self.call(f"/api/hub/project/{pid}/push", {"base_rev": 1, "client": "cV", "sections": {"layer:z": self.layer("Z", 1)}}, vic)
            self.assertEqual(s, 200)
            ev = None
            for _ in range(10):
                try:
                    e = q.get(timeout=3)
                except queue.Empty:
                    break
                if e and e.get("type") == "rev":
                    ev = e
                    break
            self.assertIsNotNone(ev, "событие rev не пришло за 3 с")
            self.assertEqual((ev["rev"], ev["by"], ev["client"]), (2, "vic", "cV"))
            self.assertIn("layer:z", ev["sections"])
        finally:
            c.close()

    def test_sse_needs_session_and_access_and_ends_on_delete(self):
        ann, vic = self.login("ann"), self.login("vic")
        pid = self.new_project(ann)
        self.assertEqual(self.call(f"/api/hub/project/{pid}/events")[0], 401)
        s, r, j = self.call(f"/api/hub/project/{pid}/events", cookie=vic)
        self.assertEqual((s, r.getheader("Content-Type").split(";")[0]), (403, "application/json"))      # отказ обычным ответом, не потоком
        self.assertEqual(self.call("/api/hub/project/" + "f" * 16 + "/events", cookie=ann)[0], 404)
        c, r, q = self.open_stream(pid, ann)
        try:
            self.assertEqual(q.get(timeout=3)["type"], "presence")
            self.assertEqual(self.call(f"/api/hub/project/{pid}/delete", {}, ann)[0], 200)
            seen = []
            while True:
                e = q.get(timeout=5)
                if e is None:
                    break                                                # поток закрылся сам
                seen.append(e["type"])
            self.assertIn("deleted", seen)
        finally:
            c.close()

    def test_sse_presence_post(self):
        ann = self.login("ann")
        pid = self.new_project(ann)
        c, r, q = self.open_stream(pid, ann)
        try:
            q.get(timeout=3)
            s, _, j = self.call(f"/api/hub/project/{pid}/presence", {"client": "cA", "cursor": [37.6, 55.7], "layer": None, "sel": []}, ann)
            self.assertEqual(s, 200)
            got = None
            for _ in range(6):
                e = q.get(timeout=3)
                if e and e.get("type") == "presence" and any(u.get("client") == "cA" for u in e["users"]):
                    got = e
                    break
            self.assertIsNotNone(got)
            self.assertEqual(got["users"][0]["login"], "ann")
            self.assertEqual(self.call(f"/api/hub/project/{pid}/presence", {"client": "cA", "cursor": "x"}, ann)[0], 400)
        finally:
            c.close()

    # ----- разбор безопасности -----

    def test_client_ip_trusts_forwarded_for_only_from_the_proxy_on_this_host(self):
        def ip(peer, xff=None):
            h = S.Handler.__new__(S.Handler)
            h.client_address = (peer, 5000)
            h.headers = {"X-Forwarded-For": xff} if xff is not None else {}
            return h._client_ip()
        self.assertEqual(ip("127.0.0.1", "6.6.6.6, 203.0.113.9"), "203.0.113.9")     # последний: его дописал наш Caddy
        self.assertEqual(ip("::1", "203.0.113.9"), "203.0.113.9")
        self.assertEqual(ip("198.51.100.7", "1.2.3.4"), "198.51.100.7")              # с чужого адреса заголовку не верим
        self.assertEqual(ip("198.51.100.7"), "198.51.100.7")
        self.assertEqual(ip("127.0.0.1", "not-an-ip"), "127.0.0.1")                  # мусор — адрес сокета
        self.assertEqual(ip("127.0.0.1"), "127.0.0.1")
        self.assertEqual(ip("127.0.0.1", "2001:db8:1:2:aaaa:bbbb:cccc:dddd"), ip("127.0.0.1", "2001:db8:1:2::1"))   # IPv6 — по сети /64
        self.assertNotEqual(ip("127.0.0.1", "2001:db8:1:2::1"), ip("127.0.0.1", "2001:db8:1:3::1"))
        self.assertEqual(ip("127.0.0.1", "::ffff:203.0.113.9"), "203.0.113.9")

    def test_ip_throttle_ignores_forged_first_forwarded_entry(self):
        for i in range(S.hubmod.IP_FAILS):
            s, _, _ = self.call("/api/hub/login", {"login": f"ghost{i:03d}", "password": "x" * 9},
                                headers={"X-Forwarded-For": f"10.{i}.0.1, 203.0.113.50"})
            self.assertEqual(s, 401)
        s, _, _ = self.call("/api/hub/login", {"login": "ann", "password": "password-ann"},
                            headers={"X-Forwarded-For": "172.16.0.1, 203.0.113.50"})
        self.assertEqual(s, 429)                                                      # подделка первого адреса счёт не обнулила
        s, _, _ = self.call("/api/hub/login", {"login": "ann", "password": "password-ann"},
                            headers={"X-Forwarded-For": "203.0.113.51"})
        self.assertEqual(s, 200)

    def test_password_change_ends_other_sessions_keeps_this_one(self):
        here, elsewhere = self.login("ann"), self.login("ann")
        self.assertEqual(self.call("/api/hub/password", {"old": "password-ann", "new": "password-ann-2"}, here)[0], 200)
        self.assertEqual(self.call("/api/hub/me", cookie=here)[0], 200)
        self.assertEqual(self.call("/api/hub/me", cookie=elsewhere)[0], 401)

    def test_every_post_needs_json_in_hub_mode(self):
        cookie = self.login("ann")
        for path in ("/api/tep", "/api/fetch", "/api/export/dxf", "/api/print/svg", "/api/import/files"):
            for ctype in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x"):
                s, _, j = self.call(path, raw=b'{"terr_ha": 1}', cookie=cookie, ctype=ctype)
                self.assertEqual(s, 415, (path, ctype))
        self.assertEqual(self.call("/api/tep", {"terr_ha": 10, "restrict_ha": 1, "spp_new_m2": 1000, "share": 1}, cookie)[0], 200)
        s, _, _ = self.call("/api/import/dxf", raw=b"garbage", cookie=cookie, ctype="application/octet-stream")
        self.assertNotEqual(s, 415)                                                   # сырой DXF — единственное исключение

    def test_post_marked_cross_site_by_the_browser_is_denied(self):
        cookie = self.login("ann")
        for site in ("cross-site", "same-site"):
            s, _, _ = self.call("/api/hub/projects", {"name": "x"}, cookie, headers={"Sec-Fetch-Site": site})
            self.assertEqual(s, 403, site)
        for site in ("same-origin", "none"):
            self.assertEqual(self.call("/api/hub/projects", {"name": "x"}, cookie, headers={"Sec-Fetch-Site": site})[0], 200)
        # переход по ссылке со стороннего сайта — GET, главная страница открывается (данных в ней нет)
        self.assertEqual(self.call("/", headers={"Sec-Fetch-Site": "cross-site"})[0], 200)

    def test_every_state_changing_hub_route_checks_origin_and_json(self):
        ann = self.login("ann")
        pid = self.new_project(ann)
        routes = ["/api/hub/logout", "/api/hub/password", "/api/hub/invites", "/api/hub/users/vic", "/api/hub/projects",
                  f"/api/hub/project/{pid}", f"/api/hub/project/{pid}/push", f"/api/hub/project/{pid}/members",
                  f"/api/hub/project/{pid}/presence", f"/api/hub/project/{pid}/comments",
                  f"/api/hub/project/{pid}/comments/abc", f"/api/hub/project/{pid}/comments/abc/reply",
                  f"/api/hub/project/{pid}/comments/abc/delete", f"/api/hub/project/{pid}/history/1/restore",
                  f"/api/hub/project/{pid}/delete", "/api/hub/teams", f"/api/hub/project/{pid}/team",
                  f"/api/hub/project/{pid}/star", f"/api/hub/project/{pid}/copy", f"/api/hub/project/{pid}/link", "/api/hub/join"]
        tid = self.call("/api/hub/teams", {"name": "К"}, ann)[2]["id"]
        routes += [f"/api/hub/team/{tid}", f"/api/hub/team/{tid}/members", f"/api/hub/team/{tid}/delete"]
        for path in routes:
            self.assertEqual(self.call(path, {}, ann, headers={"Origin": "https://evil.example"})[0], 403, path)
            self.assertEqual(self.call(path, {}, ann, headers={"Host": "evil.example"})[0], 403, path)
            self.assertEqual(self.call(path, raw=b"{}", cookie=ann, ctype="text/plain")[0], 415, path)
        self.assertEqual(self.call("/api/hub/me", cookie=ann)[0], 200)                # ничего из этого не сработало
        self.assertEqual([t["id"] for t in self.call("/api/hub/teams", cookie=ann)[2]["teams"]], [tid])
        self.assertEqual(self.call(f"/api/hub/project/{pid}", cookie=ann)[0], 200)

    def test_get_routes_have_no_side_effects(self):
        ann = self.login("ann")
        pid = self.new_project(ann)
        before = self.call(f"/api/hub/project/{pid}", cookie=ann)[2]["rev"]
        for path in ("/api/hub/me", "/api/hub/projects", "/api/hub/teams", f"/api/hub/project/{pid}", f"/api/hub/project/{pid}/sections?names=meta",
                     f"/api/hub/project/{pid}/comments", f"/api/hub/project/{pid}/history", f"/api/hub/project/{pid}/activity",
                     f"/api/hub/project/{pid}/download", f"/api/hub/project/{pid}/link"):
            self.call(path, cookie=ann)
        self.assertEqual(self.call(f"/api/hub/project/{pid}", cookie=ann)[2]["rev"], before)
        # «опасные» слова в GET не превращаются в действия
        tid = self.call("/api/hub/teams", {"name": "К"}, ann)[2]["id"]
        for path in (f"/api/hub/project/{pid}/delete", f"/api/hub/project/{pid}/push", "/api/hub/logout", f"/api/hub/project/{pid}/members",
                     f"/api/hub/project/{pid}/team", f"/api/hub/team/{tid}", f"/api/hub/team/{tid}/members", f"/api/hub/team/{tid}/delete",
                     f"/api/hub/project/{pid}/star", f"/api/hub/project/{pid}/copy", "/api/hub/join"):
            self.assertEqual(self.call(path, cookie=ann)[0], 404, path)
        self.assertEqual(self.call(f"/api/hub/project/{pid}", cookie=ann)[0], 200)
        self.assertEqual(len(self.call("/api/hub/teams", cookie=ann)[2]["teams"]), 1)
        self.assertEqual(len(self.call("/api/hub/projects", cookie=ann)[2]["projects"]), 1)      # копии не появилось
        self.assertFalse(self.call("/api/hub/projects", cookie=ann)[2]["projects"][0]["star"])

    # ----- избранное, копия, доступ по ссылке (этап 2) -----

    def listed(self, cookie):
        return {p["id"]: p for p in self.call("/api/hub/projects", cookie=cookie)[2]["projects"]}

    def test_star_on_off_is_reflected_in_the_list(self):
        ann = self.login("ann")
        pid = self.new_project(ann)
        self.assertIs(self.listed(ann)[pid]["star"], False)
        s, _, j = self.call(f"/api/hub/project/{pid}/star", {"on": True}, ann)
        self.assertEqual((s, j), (200, {"star": True}))
        self.assertIs(self.listed(ann)[pid]["star"], True)
        self.assertEqual(self.call(f"/api/hub/project/{pid}/star", {"on": False}, ann)[2], {"star": False})
        self.assertIs(self.listed(ann)[pid]["star"], False)

    def test_star_route_needs_boolean_on_and_access(self):
        ann, vic = self.login("ann"), self.login("vic")
        pid = self.new_project(ann)
        for body in ({}, {"on": "true"}, {"on": 1}, {"on": None}, {"on": []}):
            self.assertEqual(self.call(f"/api/hub/project/{pid}/star", body, ann)[0], 400, body)
        self.assertIs(self.listed(ann)[pid]["star"], False)
        self.assertEqual(self.call(f"/api/hub/project/{pid}/star", {"on": True}, vic)[0], 403)     # чужой проект

    def test_copy_creates_own_project_with_default_name(self):
        ann, vic = self.login("ann"), self.login("vic")
        pid = self.new_project(ann, "Участок")
        s, _, j = self.call(f"/api/hub/project/{pid}/copy", {}, ann)
        self.assertEqual(s, 200, j)
        self.assertEqual(set(j), {"id", "rev"})
        self.assertNotEqual(j["id"], pid)
        row = self.listed(ann)[j["id"]]
        self.assertEqual((row["name"], row["role"]), ("Участок — копия", "owner"))
        s, _, j2 = self.call(f"/api/hub/project/{pid}/copy", {"name": "Моя"}, ann)
        self.assertEqual(self.listed(ann)[j2["id"]]["name"], "Моя")
        # зритель тоже может сделать копию, владельцем копии становится он
        self.call(f"/api/hub/project/{pid}/members", {"login": "vic", "role": "viewer"}, ann)
        s, _, j3 = self.call(f"/api/hub/project/{pid}/copy", {}, vic)
        self.assertEqual(s, 200, j3)
        self.assertEqual(self.listed(vic)[j3["id"]]["role"], "owner")
        self.assertNotIn("vic", self.call(f"/api/hub/project/{pid}", cookie=ann)[2].get("members", {}))

    def test_copy_into_foreign_team_is_403_and_needs_access(self):
        ann, vic = self.login("ann"), self.login("vic")
        pid = self.new_project(vic, "Мой")
        self.call(f"/api/hub/project/{pid}/members", {"login": "ann", "role": "viewer"}, vic)
        tid = self.call("/api/hub/teams", {"name": "Бюро"}, vic)[2]["id"]          # ann в этой команде нет
        before = len(self.listed(ann))
        self.assertEqual(self.call(f"/api/hub/project/{pid}/copy", {"team": tid}, ann)[0], 403)
        self.assertEqual(len(self.listed(ann)), before)
        other = self.new_project(vic, "Закрытый")
        self.assertEqual(self.call(f"/api/hub/project/{other}/copy", {}, ann)[0], 403)

    def test_copy_keeps_the_small_hub_body_limit(self):
        self.assertEqual(S.body_limit("/api/hub/project/" + "0" * 16 + "/copy"), S.MAX_HUB_BODY)
        self.assertEqual(S.body_limit("/api/hub/join"), S.MAX_HUB_BODY)
        self.assertEqual(S.body_limit("/api/hub/project/" + "0" * 16 + "/link"), S.MAX_HUB_BODY)
        self.assertLess(S.MAX_HUB_BODY, S.MAX_PROJECT_BODY)
        ann = self.login("ann")
        pid = self.new_project(ann)
        s, _, j = self.call(f"/api/hub/project/{pid}/copy", raw=b"{}", cookie=ann, headers={"Content-Length": str(S.MAX_HUB_BODY + 10)})    # заявлен больше 1 МБ: отказ до чтения
        self.assertEqual(s, 413, j)

    def link_on(self, cookie, pid, role="viewer"):
        s, _, j = self.call(f"/api/hub/project/{pid}/link", {"role": role}, cookie)
        self.assertEqual(s, 200, j)
        return j["link"]["token"]

    def test_link_join_gives_the_role(self):
        ann, vic = self.login("ann"), self.login("vic")
        pid = self.new_project(ann)
        self.assertEqual(self.call(f"/api/hub/project/{pid}", cookie=vic)[0], 403)
        self.assertEqual(self.call(f"/api/hub/project/{pid}/link", cookie=ann)[2], {"link": None, "users": []})
        token = self.link_on(ann, pid, "viewer")
        self.assertEqual(self.call(f"/api/hub/project/{pid}/link", cookie=ann)[2]["link"], {"token": token, "role": "viewer"})
        s, _, j = self.call("/api/hub/join", {"token": token}, vic)
        self.assertEqual((s, j["id"], j["role"]), (200, pid, "viewer"), j)
        self.assertEqual(self.call(f"/api/hub/project/{pid}", cookie=vic)[2]["role"], "viewer")
        self.assertEqual(self.listed(ann)[pid]["link_role"], "viewer")
        self.assertEqual(self.call(f"/api/hub/project/{pid}/link", cookie=ann)[2]["users"][0]["login"], "vic")

    def test_join_needs_a_session_and_a_token(self):
        ann = self.login("ann")
        pid = self.new_project(ann)
        token = self.link_on(ann, pid)
        self.assertEqual(self.call("/api/hub/join", {"token": token})[0], 401)
        for body in ({}, {"token": 5}, {"token": ""}, {"token": "x" * 65}):
            self.assertEqual(self.call("/api/hub/join", body, ann)[0], 400, body)

    def test_only_owner_reads_and_changes_the_link(self):
        ann, vic = self.login("ann"), self.login("vic")
        pid = self.new_project(ann)
        self.assertEqual(self.call(f"/api/hub/project/{pid}/link", cookie=vic)[0], 403)          # посторонний
        self.assertEqual(self.call(f"/api/hub/project/{pid}/link", {"role": "viewer"}, vic)[0], 403)
        self.call(f"/api/hub/project/{pid}/members", {"login": "vic", "role": "editor"}, ann)    # редактор — тоже не владелец
        self.assertEqual(self.call(f"/api/hub/project/{pid}/link", cookie=vic)[0], 403)
        self.assertEqual(self.call(f"/api/hub/project/{pid}/link", {"role": "viewer"}, vic)[0], 403)
        self.assertIsNone(self.call(f"/api/hub/project/{pid}/link", cookie=ann)[2]["link"])
        stranger = self.new_project(vic, "Чужой")
        self.assertEqual(self.call(f"/api/hub/project/{stranger}/link", cookie=ann)[0], 403)
        self.assertEqual(self.call(f"/api/hub/project/{pid}/link", {"role": "owner"}, ann)[0], 400)
        for body in ({}, {"rotate": True}):                       # без role ссылку не трогаем
            self.assertEqual(self.call(f"/api/hub/project/{pid}/link", body, ann)[0], 400, body)
        self.link_on(ann, pid)
        self.assertEqual(self.call(f"/api/hub/project/{pid}/link", {"role": "viewer", "rotate": "yes"}, ann)[0], 400)
        self.assertIsNotNone(self.call(f"/api/hub/project/{pid}/link", cookie=ann)[2]["link"])

    def test_link_rotate_kills_old_token_and_joined_access(self):
        ann, vic = self.login("ann"), self.login("vic")
        pid = self.new_project(ann)
        old = self.link_on(ann, pid, "editor")
        self.assertEqual(self.call("/api/hub/join", {"token": old}, vic)[2]["role"], "editor")
        s, _, j = self.call(f"/api/hub/project/{pid}/link", {"role": "editor", "rotate": True}, ann)
        self.assertEqual(s, 200, j)
        self.assertNotEqual(j["link"]["token"], old)
        self.assertEqual(self.call("/api/hub/join", {"token": old}, vic)[0], 404)
        self.assertEqual(self.call(f"/api/hub/project/{pid}", cookie=vic)[0], 403)
        self.assertEqual(self.call("/api/hub/join", {"token": j["link"]["token"]}, vic)[0], 200)      # новая ссылка работает
        self.assertEqual(self.call(f"/api/hub/project/{pid}", cookie=vic)[2]["role"], "editor")

    def test_link_off_closes_access_and_the_event_stream(self):
        ann, vic = self.login("ann"), self.login("vic")
        pid = self.new_project(ann)
        token = self.link_on(ann, pid)
        self.assertEqual(self.call("/api/hub/join", {"token": token}, vic)[0], 200)
        c, r, q = self.open_stream(pid, vic)
        try:
            self.assertEqual(q.get(timeout=3)["type"], "presence")
            s, _, j = self.call(f"/api/hub/project/{pid}/link", {"role": None}, ann)
            self.assertEqual((s, j), (200, {"link": None, "users": []}))
            for _ in range(40):
                if q.get(timeout=5) is None:
                    break
            else:
                self.fail("поток остался открытым после отключения ссылки")
        finally:
            c.close()
        self.assertEqual(self.call(f"/api/hub/project/{pid}", cookie=vic)[0], 403)
        self.assertEqual(self.call("/api/hub/join", {"token": token}, vic)[0], 404)

    def test_bad_join_tokens_are_throttled_apart_from_password_login(self):
        ann, vic = self.login("ann"), self.login("vic")
        for i in range(5):
            self.assertEqual(self.call("/api/hub/join", {"token": f"nope{i}"}, vic)[0], 404, i)
        s, _, j = self.call("/api/hub/join", {"token": "nope5"}, vic)
        self.assertEqual(s, 429, j)
        pid = self.new_project(ann)
        token = self.link_on(ann, pid)
        self.assertEqual(self.call("/api/hub/join", {"token": token}, vic)[0], 429)       # даже верная ссылка — позже
        self.assertEqual(self.call("/api/hub/login", {"login": "vic", "password": "password-vic"})[0], 200)   # пароль не заблокирован
        self.assertEqual(self.call("/api/hub/join", {"token": "nope"}, ann)[0], 404)       # другой логин со своим счётом

    def test_join_token_never_reaches_the_server_log(self):
        import io
        ann, vic = self.login("ann"), self.login("vic")
        pid = self.new_project(ann)
        token = self.link_on(ann, pid)
        bad = "BADTOKEN-" + "z" * 20
        err = io.StringIO()
        with mock.patch.object(S.sys, "stderr", err):
            self.call("/api/hub/join", {"token": bad}, vic)
            self.call("/api/hub/join", {"token": token}, vic)
            self.call("/api/hub/join", raw=b'{"token": "' + bad.encode() + b'"', cookie=vic)       # битый JSON
            self.call(f"/api/hub/project/{pid}/link", {"role": 5}, ann)
        log = err.getvalue()
        self.assertNotIn(token, log)
        self.assertNotIn(bad, log)
        self.assertNotIn(token, str(self.call("/api/hub/project/" + pid + "/activity", cookie=ann)[2]))

    def test_deeply_nested_json_is_a_plain_400(self):
        cookie = self.login("ann")
        for depth in (200_000,):                                 # и разобрать, и записать обратно такую вложенность нельзя
            deep = b"[" * depth + b"]" * depth
            body = b'{"name":"x","project":{"format":"grado2","version":2,"layers":[{"key":"a"}],"data":{"a":{"x":' + deep + b"}}}}"
            s, _, j = self.call("/api/hub/projects", raw=body, cookie=cookie)
            self.assertEqual(s, 400, depth)
            self.assertNotIn("Recursion", str(j))
            self.assertEqual(self.call("/api/hub/login", raw=b'{"login":' + deep + b"}", ctype="application/json")[0], 400)
        self.assertEqual(self.call("/api/tep", raw=b'{"a":' + b"[" * 200_000 + b"]" * 200_000 + b"}", cookie=cookie)[0], 400)

    def test_quota_answer_is_readable_not_generic(self):
        cookie = self.login("ann")
        with mock.patch.object(S.hubmod, "QUOTA_BYTES", 10), mock.patch.object(S.hubmod, "QUOTA_CHECK_FROM", 0):
            s, _, j = self.call("/api/hub/projects", {"name": "x"}, cookie)
        self.assertEqual(s, 507)
        self.assertIn("хранилище", j["error"])

    def test_open_hub_uses_the_projects_quota(self):
        import tempfile
        old = S.hubmod.QUOTA_BYTES
        try:
            with tempfile.TemporaryDirectory() as d:
                S.open_hub(Path(d) / "h")
            self.assertEqual(S.hubmod.QUOTA_BYTES, S.PROJECTS_CAP)
        finally:
            S.hubmod.QUOTA_BYTES = old

    def test_sse_stream_count_is_capped_per_user(self):
        ann = self.login("ann")
        pid = self.new_project(ann)
        with mock.patch.object(S.hubmod, "SSE_PER_USER", 2):
            streams = [self.open_stream(pid, ann) for _ in range(2)]
            try:
                for c, r, q in streams:
                    self.assertEqual(q.get(timeout=3)["type"], "presence")
                s, r, j = self.call(f"/api/hub/project/{pid}/events", cookie=ann)
                self.assertEqual((s, r.getheader("Content-Type").split(";")[0]), (429, "application/json"))
                self.assertEqual(self.call(f"/api/hub/project/{pid}/events", cookie=self.login("ann"))[0], 429)    # лимит на человека, а не на сессию
            finally:
                for c, _, _ in streams:
                    c.close()

    def test_sse_stream_ends_after_logout(self):
        ann = self.login("ann")
        pid = self.new_project(ann)
        with mock.patch.object(S, "EVENTS_RECHECK", 0.3):
            c, r, q = self.open_stream(pid, ann)
            try:
                self.assertEqual(q.get(timeout=3)["type"], "presence")
                self.assertEqual(self.call("/api/hub/logout", {}, ann)[0], 200)
                for _ in range(40):
                    if q.get(timeout=5) is None:
                        break
                else:
                    self.fail("поток остался открытым после выхода")
            finally:
                c.close()

    def test_sse_stream_ends_when_account_disabled(self):
        boss, vic = self.login("boss"), self.login("vic")
        pid = self.new_project(self.login("ann"))
        self.call(f"/api/hub/project/{pid}/members", {"login": "vic", "role": "viewer"}, self.login("ann"))
        c, r, q = self.open_stream(pid, vic)
        try:
            self.assertEqual(q.get(timeout=3)["type"], "presence")
            self.assertEqual(self.call("/api/hub/users/vic", {"disabled": True}, boss)[0], 200)
            for _ in range(40):
                if q.get(timeout=5) is None:
                    break
            else:
                self.fail("поток отключённого пользователя остался открытым")
        finally:
            c.close()

    # ----- команды -----

    def test_team_create_list_rename(self):
        ann, vic = self.login("ann"), self.login("vic")
        s, _, j = self.call("/api/hub/teams", {"name": "  Бюро  "}, ann)
        self.assertEqual(s, 200, j)
        tid = j["id"]
        self.assertRegex(tid, r"^[0-9a-f]{16}$")
        t = self.call("/api/hub/teams", cookie=ann)[2]["teams"]
        self.assertEqual([(x["id"], x["name"], x["role"], x["projects"]) for x in t], [(tid, "Бюро", "owner", 0)])
        self.assertEqual(t[0]["members"], [{"login": "ann", "name": "Анна", "role": "owner"}])
        self.assertEqual(self.call("/api/hub/teams", cookie=vic)[2], {"teams": []})        # чужую команду не видно
        self.assertEqual(self.call(f"/api/hub/team/{tid}", {"name": "Атлас"}, vic)[0], 403)
        self.assertEqual(self.call(f"/api/hub/team/{tid}", {"name": "Атлас"}, ann)[2], {"name": "Атлас"})
        self.assertEqual(self.call(f"/api/hub/team/{tid}", {"name": " "}, ann)[0], 400)
        self.assertEqual(self.call("/api/hub/teams", cookie=ann)[2]["teams"][0]["name"], "Атлас")
        self.assertEqual(self.call("/api/hub/teams", cookie="")[0], 401)

    def test_team_members_need_explicit_role_and_owner(self):
        ann, vic, boss = self.login("ann"), self.login("vic"), self.login("boss")
        tid = self.call("/api/hub/teams", {"name": "Бюро"}, ann)[2]["id"]
        path = f"/api/hub/team/{tid}/members"
        s, _, j = self.call(path, {"login": "vic"}, ann)                      # без role — 400, ничего не меняется
        self.assertEqual(s, 400, j)
        self.assertEqual(len(self.call("/api/hub/teams", cookie=ann)[2]["teams"][0]["members"]), 1)
        s, _, j = self.call(path, {"login": "vic", "role": "member"}, ann)
        self.assertEqual((s, [(m["login"], m["role"]) for m in j["members"]]), (200, [("ann", "owner"), ("vic", "member")]))
        self.assertEqual(self.call(path, {"login": "boss", "role": "member"}, vic)[0], 403)      # участник не владелец
        self.assertEqual(self.call(path, {"login": "vic", "role": "owner"}, vic)[0], 403)
        self.assertEqual(self.call(path, {"login": "vic", "role": "root"}, ann)[0], 400)
        self.assertEqual(self.call(path, {"login": "ghost", "role": "member"}, ann)[0], 404)
        s, _, j = self.call(path, {"login": "vic", "role": None}, vic)        # выйти может любой участник
        self.assertEqual((s, [m["login"] for m in j["members"]]), (200, ["ann"]))
        self.assertEqual(self.call("/api/hub/teams", cookie=vic)[2], {"teams": []})
        self.assertEqual(self.call(path, {"login": "ann", "role": None}, ann)[0], 400)          # последний владелец

    def test_team_project_visible_to_member_and_access_switch(self):
        ann, vic = self.login("ann"), self.login("vic")
        tid = self.call("/api/hub/teams", {"name": "Бюро"}, ann)[2]["id"]
        self.call(f"/api/hub/team/{tid}/members", {"login": "vic", "role": "member"}, ann)
        s, _, j = self.call("/api/hub/projects", {"name": "Общий", "team": tid}, ann)
        self.assertEqual(s, 200, j)
        pid = j["id"]
        items = self.call("/api/hub/projects", cookie=vic)[2]["projects"]
        self.assertEqual([(x["id"], x["role"], x["team"], x["team_name"], x["team_access"]) for x in items],
                         [(pid, "editor", tid, "Бюро", "edit")])
        self.assertEqual(self.call(f"/api/hub/project/{pid}", cookie=vic)[0], 200)
        self.assertEqual(self.call("/api/hub/teams", cookie=ann)[2]["teams"][0]["projects"], 1)
        self.assertEqual(self.call("/api/hub/projects", {"name": "x", "team": tid}, self.login("boss"))[0], 200)   # админ может
        self.assertEqual(self.call("/api/hub/projects", {"name": "x", "team": "0" * 16}, ann)[0], 404)
        self.assertEqual(self.call("/api/hub/projects", {"name": "x", "team": tid, "team_access": "all"}, ann)[0], 400)
        self.assertEqual(self.call(f"/api/hub/project/{pid}/team", {"team_access": "none"}, ann)[0], 400)    # без ключа team
        self.assertEqual(self.call(f"/api/hub/project/{pid}/team", {"team": tid, "team_access": "none"}, vic)[0], 403)
        s, _, j = self.call(f"/api/hub/project/{pid}/team", {"team": tid, "team_access": "none"}, ann)
        self.assertEqual((s, j), (200, {"team": tid, "team_access": "none"}))
        self.assertEqual(self.call(f"/api/hub/project/{pid}", cookie=vic)[0], 403)
        self.assertNotIn(pid, [x["id"] for x in self.call("/api/hub/projects", cookie=vic)[2]["projects"]])
        s, _, j = self.call(f"/api/hub/project/{pid}/team", {"team": None}, ann)                  # обратно в «Личные»
        self.assertEqual((s, j["team"]), (200, None))
        self.assertIsNone([x for x in self.call("/api/hub/projects", cookie=ann)[2]["projects"] if x["id"] == pid][0]["team"])

    def test_team_delete_refused_while_it_has_projects(self):
        ann, vic = self.login("ann"), self.login("vic")
        tid = self.call("/api/hub/teams", {"name": "Бюро"}, ann)[2]["id"]
        pid = self.call("/api/hub/projects", {"name": "Общий", "team": tid}, ann)[2]["id"]
        self.assertEqual(self.call(f"/api/hub/team/{tid}/delete", {}, vic)[0], 403)
        self.assertEqual(self.call(f"/api/hub/team/{tid}/delete", {}, ann)[0], 400)
        self.assertEqual(len(self.call("/api/hub/teams", cookie=ann)[2]["teams"]), 1)
        self.assertEqual(self.call(f"/api/hub/project/{pid}/delete", {}, ann)[0], 200)
        self.assertEqual(self.call(f"/api/hub/team/{tid}/delete", {}, ann)[2], {"ok": True})
        self.assertEqual(self.call("/api/hub/teams", cookie=ann)[2], {"teams": []})

    def test_team_id_in_url_is_never_a_path(self):
        ann = self.login("ann")
        self.call("/api/hub/teams", {"name": "Бюро"}, ann)
        for tid in ("..", "%2e%2e", "..%2f..", "%2e%2e%2fusers", "A" * 16, "0" * 15, "0" * 17, "%00", "g" * 16):
            for suffix in ("", "/members", "/delete"):
                s, _, j = self.call(f"/api/hub/team/{tid}{suffix}", {"name": "x", "login": "ann", "role": None}, ann)
                self.assertIn(s, (404,), (tid, suffix, s))
        self.assertEqual(self.call(f"/api/hub/team/{'0' * 16}/delete", {}, ann)[0], 404)        # правильной формы, но нет
        self.assertEqual(self.call(f"/api/hub/team/{'0' * 16}/other", {}, ann)[0], 404)

    def test_team_routes_use_the_small_body_limit(self):
        for path in ("/api/hub/teams", f"/api/hub/team/{'0' * 16}", f"/api/hub/team/{'0' * 16}/members",
                     f"/api/hub/team/{'0' * 16}/delete", f"/api/hub/project/{'0' * 16}/team"):
            self.assertEqual(S.body_limit(path), S.MAX_HUB_BODY, path)
        ann = self.login("ann")
        with mock.patch.object(S, "MAX_HUB_BODY", 100):                  # настоящий предел 413 на маленьком теле
            self.assertEqual(self.call("/api/hub/teams", raw=b'{"name":"x"' + b" " * 200 + b"}", cookie=ann)[0], 413)
        self.assertEqual(self.call("/api/hub/teams", cookie=ann)[2], {"teams": []})

    def test_sse_stream_ends_when_member_removed_from_team(self):
        ann, vic = self.login("ann"), self.login("vic")
        tid = self.call("/api/hub/teams", {"name": "Бюро"}, ann)[2]["id"]
        self.call(f"/api/hub/team/{tid}/members", {"login": "vic", "role": "member"}, ann)
        pid = self.call("/api/hub/projects", {"name": "Общий", "team": tid}, ann)[2]["id"]
        c, r, q = self.open_stream(pid, vic)
        try:
            self.assertEqual(q.get(timeout=3)["type"], "presence")
            self.assertEqual(self.call(f"/api/hub/team/{tid}/members", {"login": "vic", "role": None}, ann)[0], 200)
            for _ in range(40):
                if q.get(timeout=5) is None:
                    break
            else:
                self.fail("поток остался открытым после выхода из команды")
        finally:
            c.close()

    def test_dates_and_paths_do_not_leak_in_errors(self):
        ann = self.login("ann")
        pid = self.new_project(ann)
        for path, body in ((f"/api/hub/project/{pid}/push", {"base_rev": "x", "sections": {}, "client": "c"}),
                           (f"/api/hub/project/{pid}/comments", {"text": 5}),
                           (f"/api/hub/project/{pid}/members", {"login": "../../etc", "role": "viewer"}),
                           ("/api/hub/project/..%2f..%2fetc/push", {"base_rev": 0, "sections": {}, "client": "c"}),
                           (f"/api/hub/project/{pid}/history/99999999999999999999/restore", {})):
            s, _, j = self.call(path, body, ann)
            text = str(j)
            self.assertGreaterEqual(s, 400, path)
            for bad in ("/Users", "Traceback", str(Path(self.tmp.name)), ".json", "hub.py", "Errno"):
                self.assertNotIn(bad, text, (path, bad))

    def test_project_id_in_url_is_never_a_path(self):
        ann = self.login("ann")
        self.new_project(ann)
        for pid in ("..", "%2e%2e", "..%2f..", "%2e%2e%2f%2e%2e%2fusers.json", "A" * 16, "0" * 15, "0" * 17, "%00"):
            for path in (f"/api/hub/project/{pid}", f"/api/hub/project/{pid}/download", f"/api/hub/project/{pid}/comments"):
                s, _, j = self.call(path, cookie=ann)
                self.assertIn(s, (400, 404), (path, s))
        self.assertEqual(self.call("/api/hub/project/" + "0" * 16 + "/comments/%2e%2e%2f%2e%2e/delete", {}, ann)[0] // 100, 4)


class DxfUidNotExported(unittest.TestCase):
    """Служебные поля `_uid` и `_edited` не попадают в DXF: сервер берёт из свойств только названные поля (Текст, Размер, floors, _lt)."""

    def test_uid_and_edited_are_not_in_dxf(self):
        import io
        import zipfile
        import dxf_io
        fc = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[37.6, 55.7], [37.61, 55.7], [37.61, 55.71], [37.6, 55.7]]]},
             "properties": {"_uid": "deadbeef0123", "_edited": True, "Этажность": 5}},
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [37.6, 55.7]},
             "properties": {"_uid": "cafebabe4567", "Текст": "Подпись"}}]}
        z = zipfile.ZipFile(io.BytesIO(dxf_io.export_dxf([{"name": "Слой", "features": fc}], S.REDLN, S.LGR_COLORS)))
        text = z.read("grado2.dxf").decode("utf-8")
        for needle in ("deadbeef0123", "cafebabe4567", "_uid", "_edited"):
            self.assertNotIn(needle, text)
        self.assertIn("Подпись", text)


class NonHubUnchanged(unittest.TestCase):
    """Без GRADO2_HUB хаб не участвует: прежние маршруты, health с hub:false, маршрутов /api/hub/* нет."""

    def setUp(self):
        import threading
        self.srv = S.Server(("127.0.0.1", 0), S.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.port = self.srv.server_address[1]

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def get(self, path, data=None):
        import http.client
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("POST" if data is not None else "GET", path, body=data, headers={"Content-Type": "application/json"})
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, body

    def test_default_is_local(self):
        import json
        self.assertIsNone(S.HUB)
        s, body = self.get("/api/health")
        self.assertEqual((s, json.loads(body)["hub"]), (200, False))
        self.assertEqual(self.get("/api/projects")[0], 200)
        self.assertEqual(self.get("/api/sources")[0], 200)
        self.assertEqual(self.get("/api/hub/projects")[0], 404)
        self.assertEqual(self.get("/api/hub/login", b"{}")[0], 404)

    def test_hub_switch_parsing(self):
        self.assertFalse(S.hub_enabled([], {}))
        self.assertFalse(S.hub_enabled(["8672"], {"GRADO2_HUB": "0"}))
        self.assertTrue(S.hub_enabled(["8672", "--hub"], {}))
        self.assertTrue(S.hub_enabled(["--hub"], {}))
        self.assertTrue(S.hub_enabled([], {"GRADO2_HUB": "1"}))


class SearchCadastral(unittest.TestCase):
    """GET /api/search/cadastral: поиск участка по номеру; коннектор подменён, портал не трогаем."""

    def setUp(self):
        import threading
        S.CAD_CACHE.clear()
        S.CAD_FAIL.clear()
        self.pause = mock.patch.object(S, "CAD_PAUSE", 0)
        self.pause.start()
        self.srv = S.Server(("127.0.0.1", 0), S.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.port = self.srv.server_address[1]

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.pause.stop()
        S.CAD_CACHE.clear()
        S.CAD_FAIL.clear()

    def get(self, q):
        import http.client
        import json
        import urllib.parse
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", "/api/search/cadastral?q=" + urllib.parse.quote(q))
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, json.loads(body)

    @staticmethod
    def _feat(num):
        return {"type": "Feature", "grado_key": num,
                "geometry": {"type": "Polygon", "coordinates": [[[37.6, 55.7], [37.601, 55.7], [37.601, 55.701], [37.6, 55.7]]]},
                "properties": {"opt_cad_num": num, "opt_specified_area": "1000,5", "opt_land_record_area": 900,
                               "opt_permitted_use_established_by_document": "жилая", "service_code": 7}}

    def test_garbage_is_400_ascii(self):
        s, o = self.get("hello, 12:3")
        self.assertEqual(s, 400)
        self.assertTrue(o["error"].isascii())

    def test_success_shape_and_cache(self):
        def fake(nums, errors=None, **kw):
            return [self._feat(n) for n in nums if n.endswith(":126")]
        with mock.patch.object(S.nspd_mod, "search_cadastral", side_effect=fake) as m:
            s, o = self.get("50:27:0000000:126, 77:22:0030223:315")
            self.assertEqual(s, 200)
            self.assertEqual(len(o["features"]), 1)
            p = o["features"][0]["properties"]
            self.assertEqual(p["Кадастровый номер"], "50:27:0000000:126")
            self.assertEqual(p["Площадь уточнённая, м²"], 1000.5)
            self.assertEqual(p["ВРИ"], "жилая")
            self.assertNotIn("service_code", p)
            self.assertEqual(o["missing"], ["77:22:0030223:315"])
            self.assertEqual(self.get("50:27:0000000:126 77:22:0030223:315")[0], 200)
            self.assertEqual(m.call_count, 2)                       # по одному вызову на номер; второй поиск целиком из кэша

    def test_portal_down_is_502_ascii(self):
        def fake(nums, errors=None, **kw):
            errors.extend((n, "x") for n in nums)
            return []
        with mock.patch.object(S.nspd_mod, "search_cadastral", side_effect=fake):
            s, o = self.get("50:27:0000000:126")
        self.assertEqual(s, 502)
        self.assertTrue(o["error"].isascii())

    def test_connector_error_is_502_ascii(self):
        with mock.patch.object(S.nspd_mod, "search_cadastral", side_effect=S.ConnectorError("НСПД: что-то")):
            s, o = self.get("50:27:0000000:126")
        self.assertEqual(s, 502)
        self.assertTrue(o["error"].isascii())

    def test_lock_timeout_is_503_but_cache_answers(self):
        S.CAD_CACHE["50:27:0000000:126"] = (S.time.time(), self._feat("50:27:0000000:126"))
        with mock.patch.object(S, "CAD_LOCK_TIMEOUT", 0.2), mock.patch.object(S.nspd_mod, "search_cadastral") as m:
            S.CAD_LOCK.acquire()
            try:
                s, o = self.get("77:22:0030223:315")
                self.assertEqual(s, 503)
                self.assertEqual(o["error"], "search busy, try again")
                self.assertEqual(self.get("50:27:0000000:126")[0], 200)     # кэш — до замка, занятость его не держит
            finally:
                S.CAD_LOCK.release()
            self.assertFalse(m.called)

    def test_address_lock_timeout_is_503(self):
        with mock.patch.object(S.geocode_mod, "geocode", side_effect=S.geocode_mod.Busy("x")):
            s, o = S.search_addr("Вороново")
        self.assertEqual((s, o["error"]), (503, "search busy, try again"))

    def test_failure_is_cached_briefly(self):
        def fake(nums, errors=None, **kw):
            errors.extend((n, "x") for n in nums)
            return []
        with mock.patch.object(S.nspd_mod, "search_cadastral", side_effect=fake) as m:
            self.assertEqual(self.get("50:27:0000000:126")[0], 502)
            self.assertEqual(self.get("50:27:0000000:126")[0], 502)
            self.assertEqual(m.call_count, 1)                     # второй поиск портал не трогает
            S.CAD_FAIL["50:27:0000000:126"] -= S.CAD_FAIL_SEC + 1
            self.get("50:27:0000000:126")
            self.assertEqual(m.call_count, 2)                     # срок вышел — снова спрашиваем

    def test_deadline_reports_unchecked(self):
        def fake(nums, errors=None, **kw):
            return [self._feat(n) for n in nums]
        with mock.patch.object(S.nspd_mod, "search_cadastral", side_effect=fake) as m:
            s, o = S.search_cad("50:27:0000000:1 50:27:0000000:2", deadline=-1)
        self.assertEqual(s, 502)                                  # ничего не проверено
        self.assertFalse(m.called)
        n = [0]

        def slow(nums, errors=None, **kw):
            n[0] += 1
            S.time.sleep(0.05)
            return [self._feat(x) for x in nums]
        with mock.patch.object(S.nspd_mod, "search_cadastral", side_effect=slow):
            s, o = S.search_cad("50:27:0000000:1 50:27:0000000:2 50:27:0000000:3", deadline=0.02)
        self.assertEqual(s, 200)
        self.assertEqual(len(o["features"]), 1)
        self.assertTrue(any("50:27:0000000:2, 50:27:0000000:3" in x and "Не проверены" in x for x in o["notes"]))

    def test_parcel_without_contour_is_reported(self):
        def fake(nums, errors=None, nogeom=None, **kw):
            nogeom.extend(nums)
            return []
        with mock.patch.object(S.nspd_mod, "search_cadastral", side_effect=fake):
            s, o = self.get("50:27:0000000:126")
        self.assertEqual(s, 200)
        self.assertEqual(o["missing"], ["50:27:0000000:126"])
        self.assertTrue(any("нет контура" in x for x in o["notes"]))


class SearchKrt(unittest.TestCase):
    """T72: поиск по номеру КРТ в слое «Комплексное развитие территорий (ОГД)»; слой подменён, сети нет."""
    FEAT = {"type": "Feature", "grado_key": "pzz_krt_virtual:3784",
            "geometry": {"type": "Polygon", "coordinates": [[[37.8, 55.8], [37.8025, 55.8], [37.8025, 55.8015], [37.8, 55.8]]]},
            "properties": {"num_krt": 3229.0, "okrug": "ВАО", "rayon": "Гольяново", "pzz": "2187-ПП от 12.08.2026", "p_krt": 1.65667491492196}}

    def setUp(self):
        S.KRT_CACHE[:] = [0.0, None]
        self.api = mock.patch.object(S, "GisogdApi")
        self.fetch = self.api.start().return_value.fetch
        self.fetch.return_value = {"features": [self.FEAT, {"type": "Feature", "geometry": None, "properties": {"num_krt": 1.0}}]}

    def tearDown(self):
        self.api.stop()
        S.KRT_CACHE[:] = [0.0, None]

    def test_number_forms(self):
        for q in ("КРТ 3229", "крт 3229", "КРТ №3229", "krt3229", " 3229 "):
            self.assertEqual(S.krt_number(q)[0], 3229, q)
        self.assertTrue(S.krt_number("крт 3229")[1])
        self.assertFalse(S.krt_number("3229")[1])
        for q in ("50:27:0000000:126", "улица 3229", "КРТ", "1234567", ""):
            self.assertIsNone(S.krt_number(q), q)

    def test_card_and_cache(self):
        s, o = S.search_any("КРТ 3229")
        self.assertEqual((s, o["type"]), (200, "krt"))
        self.assertEqual(o["cards"], ["КРТ № 3229 · ВАО, Гольяново · 2187-ПП от 12.08.2026 · 1,66 га"])
        self.assertEqual(o["features"][0]["geometry"]["type"], "Polygon")
        S.search_any("3229")
        self.assertEqual(self.fetch.call_count, 1)                    # слой грузится один раз

    def test_bare_number_not_found_falls_to_address(self):
        with mock.patch.object(S.geocode_mod, "geocode", return_value=[]) as g:
            s, o = S.search_any("999")
        self.assertEqual((s, o["type"]), (200, "address"))
        g.assert_called_once()

    def test_not_found_with_word_is_missing(self):
        s, o = S.search_any("КРТ 999")
        self.assertEqual((s, o["type"], o["features"], o["missing"]), (200, "krt", [], ["КРТ 999"]))

    def test_layer_failure_is_502_ascii(self):
        self.fetch.side_effect = S.ConnectorError("ГИС ОГД: нет связи")
        s, o = S.search_any("КРТ 3229")
        self.assertEqual(s, 502)
        self.assertTrue(o["error"].isascii())


class SearchAddress(unittest.TestCase):
    """GET /api/search/address и /api/search; Nominatim подменён."""
    setUp, tearDown = SearchCadastral.setUp, SearchCadastral.tearDown
    _feat = staticmethod(SearchCadastral._feat)

    def get(self, q, path="/api/search/address"):
        import http.client
        import json
        import urllib.parse
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", path + "?q=" + urllib.parse.quote(q))
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, json.loads(body)

    RES = [{"name": "Vor", "display": "Vor, Moscow", "lon": 37.1, "lat": 55.3, "bbox": [37, 55, 38, 56], "kind": "village"}]

    def test_address_ok_empty_and_long(self):
        with mock.patch.object(S.geocode_mod, "geocode", return_value=self.RES):
            s, o = self.get("Вороново")
        self.assertEqual((s, o["results"], o["notes"]), (200, self.RES, []))
        s, o = self.get("   ")
        self.assertEqual(s, 400)
        self.assertTrue(o["error"].isascii())
        s, o = self.get("я" * 201)
        self.assertEqual(s, 400)
        self.assertTrue(o["error"].isascii())

    def test_address_502(self):
        with mock.patch.object(S.geocode_mod, "geocode", side_effect=S.ConnectorError("x")):
            s, o = self.get("Вороново")
        self.assertEqual(s, 502)
        self.assertTrue(o["error"].isascii())

    def test_dispatcher(self):
        with mock.patch.object(S.geocode_mod, "geocode", return_value=self.RES) as g, \
                mock.patch.object(S.nspd_mod, "search_cadastral", side_effect=lambda n, errors=None, **kw: [self._feat(x) for x in n]) as c:
            s, o = self.get("Вороново", "/api/search")
            self.assertEqual((s, o["type"], len(o["results"])), (200, "address", 1))
            s, o = self.get("50:27:0000000:126", "/api/search")
            self.assertEqual((s, o["type"], len(o["features"])), (200, "cadastral", 1))
            self.assertEqual((g.call_count, c.call_count), (1, 1))
        self.assertEqual(self.get("", "/api/search")[0], 400)


class T61Portal(unittest.TestCase):
    def test_sources_expose_single_catalog_code(self):
        # подборка ГРАДО с одним кодом и слой каталога — один и тот же слой портала (T61: перевыгрузка не должна дублировать)
        self.assertEqual(S.source_ogd_code("gisogd.gpzu"), "gpzu")
        self.assertEqual(S.source_ogd_code("ogd.gpzu"), "gpzu")
        self.assertEqual(S.source_ogd_code("gisogd.pmt"), "pmtgk")
        for k in ("gisogd.red_lines", "gisogd.zouit", "gisogd.pzz_sub", "gisogd.ppt", "osm.roads", "nspd.parcels", "egko.green"):
            self.assertIsNone(S.source_ogd_code(k), k)

    def test_fetch_ogd_key_falls_back_to_curated_twin_when_catalog_is_down(self):
        S.SOURCES.pop("ogd.gpzu", None)
        with mock.patch.object(S, "ogd_catalog", side_effect=S.ConnectorError("down")), \
                mock.patch.object(S, "bbox_km2", side_effect=RuntimeError("stop")):
            with self.assertRaises(RuntimeError):
                S.fetch([37.5, 55.7, 37.51, 55.71], ["ogd.gpzu"])
        try:
            self.assertEqual(S.SOURCES["ogd.gpzu"][1], {"gpzu": None})
            self.assertEqual(S.SOURCES["ogd.gpzu"][2], S.SOURCES["gisogd.gpzu"][2])
        finally:
            S.SOURCES.pop("ogd.gpzu", None)

    def test_plain_portal_error_hides_raw_text(self):
        raw = "Overpass не ответил (Errno 54; HTTP 504; timed out) — попробуйте позже или уменьшите область"
        out = S.plain_portal_error(raw)
        self.assertEqual(out, S.PORTAL_DOWN)
        for bad in ("Overpass", "Errno", "HTTP", "timed out"):
            self.assertNotIn(bad, out)
        self.assertIn("повторите", out)
        self.assertNotIn("Errno", S.plain_portal_error("[Errno 54] Connection reset by peer"))
        self.assertEqual(S.plain_portal_error("слой не найден (HTTP 404)"), "слой не найден (HTTP 404)")
        self.assertEqual(S.plain_portal_error(""), "")
        big = "Overpass не ответил (runtime error: Query ran out of memory; HTTP 429) — попробуйте позже или уменьшите область"
        self.assertEqual(S.plain_portal_error(big), S.AREA_TOO_BIG)
        self.assertEqual(S.plain_portal_error("Overpass: area too large"), S.AREA_TOO_BIG)

    def test_plain_portal_error_names_the_code_when_every_mirror_gave_the_same(self):
        # T62: «портал ответил 504» — код виден владельцу, остального сырого текста нет
        out = S.plain_portal_error("Overpass не ответил (HTTP 504; HTTP 504; HTTP 504) — попробуйте позже или уменьшите область")
        self.assertTrue(out.startswith("портал OpenStreetMap ответил 504: "))
        for bad in ("Overpass", "HTTP", "Errno"):
            self.assertNotIn(bad, out)
        self.assertEqual(S.plain_portal_error("Overpass не ответил (HTTP 504; HTTP 502) — попробуйте позже"), S.PORTAL_DOWN)

    def test_not_ready_reasons_are_plain_and_headers_ascii(self):
        legend = [{"title": "А", "items": [{"label": str(i)} for i in range(15)]}, {"title": "Б", "items": [{"label": str(i)} for i in range(8)]}]
        spec = {"sheets": [{"title": "ok"}, {"_notReady": ["в колонку не поместились пункты легенды (5)"], "cLegend": legend},
                           {"_notReady": ["не поместились строки таблицы (7)", "название не помещается в две строки по 18 пт"]}]}
        rows = dict(S.not_ready_why(spec))
        self.assertEqual(set(rows), {2, 3})
        self.assertEqual(rows[2], ["легенда из 23 позиций не помещается — уменьшите число слоёв или шрифт"])
        self.assertIn("в таблицу не поместились 7 строк", rows[3][0])
        self.assertEqual(rows[3][1], "название не помещается в две строки по 18 пт")        # прочие фразы — как есть
        h = dict(S.not_ready_headers(spec))
        self.assertEqual(h["X-Grado-Not-Ready"], "2,3")
        h["X-Grado-Not-Ready-Why"].encode("ascii")                       # заголовок ASCII
        from urllib.parse import unquote
        self.assertTrue(unquote(h["X-Grado-Not-Ready-Why"]).startswith("лист 2: легенда из 23 позиций"))
        self.assertEqual(S.not_ready_headers({"sheets": [{"title": "ok"}]}), [])

    def test_osm_fetch_combines_sets_cached_separately_without_asking_overpass(self):
        # T62: «улицы» и «землепользование» этой же области лежат в кэше порознь — сборка берёт их оттуда, портал не спрашивается
        import tempfile
        way = lambda i, tags: {"type": "way", "id": i, "tags": tags, "geometry": [{"lon": 0, "lat": 0}, {"lon": 1, "lat": 0}, {"lon": 1, "lat": 1}, {"lon": 0, "lat": 1}, {"lon": 0, "lat": 0}]}
        roads, land = {"elements": [way(1, {"highway": "residential"})]}, {"elements": [way(2, {"landuse": "grass"})]}
        bb = (0.0, 0.0, 1.0, 1.0)
        with tempfile.TemporaryDirectory() as d:
            S.OsmOverpass(transport=lambda q: roads, cache_dir=d).fetch(bb, ["roads"])
            S.OsmOverpass(transport=lambda q: land, cache_dir=d).fetch(bb, ["landuse"])
            with mock.patch.object(S.OsmOverpass, "_http_post", side_effect=AssertionError("Overpass не должен спрашиваться")):
                res = S.osm_fetch(bb, ["landuse", "roads"], cache_dir=d)
            self.assertEqual(sorted(f["properties"]["grado_set"] for f in res["features"]), ["landuse", "roads"])
            self.assertEqual(res["params"]["sets"], ["landuse", "roads"])
            # в кэше нет одного из наборов — один запрос по обоим, как раньше
            asked = []
            with mock.patch.object(S.OsmOverpass, "_http_post", side_effect=lambda q: asked.append(q) or {"elements": []}):
                S.osm_fetch(bb, ["roads", "water"], cache_dir=d)
            self.assertEqual(len(asked), 1)

    def test_place_info_survives_overpass_failure_when_polygon_is_known(self):
        poly = {"type": "Polygon", "coordinates": [[[37.52, 55.78], [37.53, 55.78], [37.53, 55.79], [37.52, 55.79], [37.52, 55.78]]]}
        S._PLACE_MEMO.clear()
        with mock.patch.object(S, "_fresh", return_value=False), \
                mock.patch.object(S.OsmOverpass, "_http_post", side_effect=S.ConnectorError("Overpass не ответил (HTTP 504)")):
            r = S.place_info(37.525, 55.785, poly)
            self.assertTrue(r["district"] and r["chosen_by"] == "area")
            self.assertTrue(any("станции метро не найдены" in x and "Overpass" not in x for x in r["notes"]), r["notes"])
            self.assertIsNone(r["k1"])                              # K1 без OSM неизвестен: клиент не перезапишет прежний
            self.assertIsNone(r["rail_walk_m"])
            self.assertEqual(S._PLACE_MEMO, {})                    # неполный ответ не запоминается
            with self.assertRaises(S.ConnectorError):              # без контура район берётся только из OSM
                S.place_info(37.525, 55.785, None)

    def test_place_info_k1_is_known_when_overpass_answers(self):
        poly = {"type": "Polygon", "coordinates": [[[37.52, 55.78], [37.53, 55.78], [37.53, 55.79], [37.52, 55.79], [37.52, 55.78]]]}
        S._PLACE_MEMO.clear()
        with mock.patch.object(S, "_fresh", return_value=False), mock.patch.object(S, "atomic_write"), \
                mock.patch.object(S.OsmOverpass, "_http_post", return_value={"elements": []}):
            r = S.place_info(37.525, 55.785, poly)
        self.assertEqual(r["k1"], 1.0)                              # ответ пришёл, станций рядом нет — K1 1,0 настоящий
        S._PLACE_MEMO.clear()
