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


if __name__ == "__main__":
    unittest.main()
