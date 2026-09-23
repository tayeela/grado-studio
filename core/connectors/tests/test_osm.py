import unittest

import _paths  # noqa: F401
from grado_connectors.osm import OsmOverpass


def _way(coords, role):
    return {"type": "way", "role": role,
            "geometry": [{"lon": x, "lat": y} for x, y in coords]}


class OsmRelationHoles(unittest.TestCase):
    def test_inner_ring_kept_as_hole(self):
        outer = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        inner = [(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)]
        data = {"elements": [{"type": "relation", "id": 1, "tags": {"landuse": "grass"},
                              "members": [_way(outer, "outer"), _way(inner, "inner")]}]}
        res = OsmOverpass(transport=lambda q: data).fetch((0, 0, 10, 10), ["landuse"])
        poly = res["features"][0]["geometry"]["coordinates"][0]
        self.assertEqual(len(poly), 2)          # внешний контур + дыра
        self.assertEqual(poly[1][0], [4, 4])


class OsmSocial(unittest.TestCase):
    def test_school_node_and_school_area_become_points(self):
        area = [(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)]
        data = {"elements": [
            {"type": "node", "id": 5, "lon": 37.5, "lat": 55.7, "tags": {"amenity": "kindergarten", "name": "Сад"}},
            {"type": "way", "id": 6, "tags": {"amenity": "school", "building": "school"}, "geometry": [{"lon": x, "lat": y} for x, y in area]},
            {"type": "node", "id": 7, "lon": 1, "lat": 1, "tags": {"amenity": "bench"}}]}
        res = OsmOverpass(transport=lambda q: data).fetch((0, 0, 60, 60), ["social", "buildings"])
        social = [f for f in res["features"] if f["properties"]["grado_set"] == "social"]
        self.assertEqual(sorted(f["properties"]["amenity"] for f in social), ["kindergarten", "school"])
        school = next(f for f in social if f["properties"]["amenity"] == "school")
        self.assertEqual(school["geometry"]["type"], "Point")
        # контур школы при этом остаётся зданием
        self.assertTrue(any(f["properties"]["grado_set"] == "buildings" for f in res["features"]))


class OsmCache(unittest.TestCase):
    """Ответ Overpass кэшируется на диске: повтор и область внутри прошлой — без сети."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.calls = 0
        ring = lambda x: [(x, 0), (x + 1, 0), (x + 1, 1), (x, 1), (x, 0)]
        self.data = {"elements": [
            {"type": "way", "id": i, "tags": {"building": "yes"}, "geometry": [{"lon": a, "lat": b} for a, b in ring(i)]}
            for i in (0, 5)]}

    def tearDown(self):
        self.tmp.cleanup()

    def transport(self, q):
        self.calls += 1
        return self.data

    def conn(self, **kw):
        return OsmOverpass(transport=self.transport, cache_dir=self.tmp.name, **kw)

    def test_repeat_and_inner_area_come_from_disk(self):
        first = self.conn().fetch((0, 0, 10, 10), ["buildings"])
        self.assertEqual((self.calls, len(first["features"]), first["notes"]), (1, 2, []))
        again = self.conn().fetch((0, 0, 10, 10), ["buildings"])
        self.assertEqual((self.calls, len(again["features"])), (1, 2))
        self.assertIn("с диска", again["notes"][0])
        self.assertIn("fetched_at", again)
        inner = self.conn().fetch((4, 0, 8, 2), ["buildings"])          # внутри прошлой: лишнее отсечено
        self.assertEqual((self.calls, [f["grado_key"] for f in inner["features"]]), (1, ["way/5"]))

    def test_wider_area_or_new_set_goes_to_network(self):
        self.conn().fetch((0, 0, 10, 10), ["buildings"])
        self.conn().fetch((0, 0, 20, 10), ["buildings"])
        self.conn().fetch((0, 0, 10, 10), ["buildings", "roads"])
        self.assertEqual(self.calls, 3)

    def test_stale_answer_used_when_overpass_is_down(self):
        from grado_connectors.contract import ConnectorError
        self.conn().fetch((0, 0, 10, 10), ["buildings"])

        def down(q):
            raise ConnectorError("нет ответа")
        res = OsmOverpass(transport=down, cache_dir=self.tmp.name, fresh_s=0).fetch((0, 0, 10, 10), ["buildings"])
        self.assertEqual(len(res["features"]), 2)
        self.assertIn("не ответил", res["notes"][0])
        with self.assertRaises(ConnectorError):
            OsmOverpass(transport=down, cache_dir=self.tmp.name, fresh_s=0).fetch((0, 0, 30, 10), ["buildings"])


if __name__ == "__main__":
    unittest.main()
