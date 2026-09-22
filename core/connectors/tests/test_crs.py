import unittest

import _paths  # noqa: F401
from grado_connectors import crs

# Эталоны — PROJ 8 (pyproj из QGIS-LTR), см. docs/architecture.md
UTM_CASES = [
    ((37.6176, 55.7558), (413242.9638, 6179766.5783)),
    ((39.0, 55.0), (500000.0000, 6094791.4210)),
    ((37.5, 55.667), (405649.3971, 6170038.5624)),
]


class TestCrs(unittest.TestCase):
    def test_wgs84_to_utm37n_vs_proj(self):
        for (lon, lat), (ex, ey) in UTM_CASES:
            x, y = crs.wgs84_to_utm37n(lon, lat)
            self.assertAlmostEqual(x, ex, delta=0.005, msg=f"x для {lon},{lat}")
            self.assertAlmostEqual(y, ey, delta=0.005, msg=f"y для {lon},{lat}")

    def test_merc_to_wgs84_vs_proj(self):
        lon, lat = crs.merc_to_wgs84(4187345.5, 7509247.8)
        self.assertAlmostEqual(lon, 37.6155646254, places=8)
        self.assertAlmostEqual(lat, 55.7522242128, places=8)

    def test_merc_to_utm_chain(self):
        x, y = crs.merc_to_utm37n(4187345.5, 7509247.8)
        self.assertAlmostEqual(x, 413100, delta=200)
        self.assertAlmostEqual(y, 6179400, delta=400)

    def test_transform_geom_nesting(self):
        geom = {"type": "MultiPolygon", "coordinates": [
            [[[37.5, 55.7], [37.6, 55.7], [37.6, 55.8], [37.5, 55.7]]]]}
        out = crs.transform_geom(geom, crs.wgs84_to_utm37n)
        self.assertEqual(out["type"], "MultiPolygon")
        x, y = out["coordinates"][0][0][0]
        self.assertGreater(x, 300000)
        self.assertGreater(y, 6000000)

    def test_ogd_proj4_declared(self):
        self.assertIn("+ellps=bessel", crs.OGD_PROJ4)
        self.assertIn("+towgs84=", crs.OGD_PROJ4)

    def test_utm37n_to_wgs84_vs_proj(self):
        for (lon, lat), (x, y) in UTM_CASES:
            got_lon, got_lat = crs.utm37n_to_wgs84(x, y)
            self.assertAlmostEqual(got_lon, lon, places=7)
            self.assertAlmostEqual(got_lat, lat, places=7)

    def test_utm37n_roundtrip(self):
        for lon, lat in [(37.0, 55.5), (39.5, 56.2), (36.8, 54.9)]:
            x, y = crs.wgs84_to_utm37n(lon, lat)
            got_lon, got_lat = crs.utm37n_to_wgs84(x, y)
            self.assertAlmostEqual(got_lon, lon, places=7)
            self.assertAlmostEqual(got_lat, lat, places=7)

    def test_origin_lonlat_near_moscow(self):
        # ORIGIN (413000, 6178000) в демо-данных студии — окрестность Москвы
        self.assertAlmostEqual(crs.ORIGIN_LON, 37.615, delta=0.05)
        self.assertAlmostEqual(crs.ORIGIN_LAT, 55.752, delta=0.05)



class MoscowLocalRoundTrip(unittest.TestCase):
    def test_wgs84_to_msk_and_back(self):
        for lon, lat in [(37.6176, 55.7558), (37.525, 55.7925), (37.2, 55.4)]:
            e, n = crs.wgs84_to_msk50(lon, lat)
            lo, la = crs.msk50_to_wgs84(e, n)
            self.assertAlmostEqual(lo, lon, places=8)
            self.assertAlmostEqual(la, lat, places=8)

if __name__ == "__main__":
    unittest.main()
