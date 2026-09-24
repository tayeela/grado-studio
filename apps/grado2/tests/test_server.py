import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402


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
        self.assertEqual(S.LIMIT_KM2["egko"], 25.0)
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


class Yandex(unittest.TestCase):
    """Яндекс Карты — девять источников из тайлов vmap3; все слои одним проходом по тайлам, поля — по-русски."""
    FIX = Path(__file__).resolve().parents[3] / "core/connectors/tests/fixtures/yandex"

    def test_sources_and_limit(self):
        keys = [k for k in S.SOURCES if k.startswith("yandex.")]
        self.assertEqual(set(keys), {"yandex.hd_roads", "yandex.buildings", "yandex.roads", "yandex.road_edges", "yandex.landuse",
                                     "yandex.green", "yandex.water", "yandex.parking", "yandex.transport"})
        self.assertTrue(all(S.SOURCES[k][2].endswith("(Яндекс)") for k in keys))
        self.assertEqual(S.SOURCES["yandex.green"][1], ["vegetation", "vegetation_planned", "hd_road_vegetation"])
        self.assertFalse({"poi", "poi_navi"} & {n for k in keys for n in S.SOURCES[k][1]}, "POI и организации не выгружаются")
        self.assertEqual(S.LIMIT_KM2["yandex"], 4.0)
        layers, errors = S.fetch([37.5, 55.8, 37.6, 55.9], ["yandex.buildings"])
        self.assertIn("больше допустимых 4", errors["yandex.buildings"])

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
