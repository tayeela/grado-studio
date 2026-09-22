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


if __name__ == "__main__":
    unittest.main()
