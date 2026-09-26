import sys
import os
import unittest
from unittest import mock
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
