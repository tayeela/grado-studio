import math
import unittest

import _paths  # noqa: F401
from grado_connectors import crs

# Эталоны — PROJ 8 (pyproj из QGIS-LTR), см. docs/architecture.md
UTM_CASES = [
    ((37.6176, 55.7558), (413242.9638, 6179766.5783)),
    ((39.0, 55.0), (500000.0000, 6094791.4210)),
    ((37.5, 55.667), (405649.3971, 6170038.5624)),
]


# МСК (как в QGIS, MSK_PROJ4): (lon, lat) WGS84 → (X, Y). Эталон — pyproj 3.8 (PROJ), 23.09.2026; 20 точек Москвы, с ТиНАО
MSK_PROJ = [
    ((37.51192, 55.61978), (849.7130, -5272.2507)),
    ((37.67547, 55.5939), (11161.1871, -8139.7703)),
    ((37.61794, 55.69068), (7516.0135, 2627.5620)),
    ((37.379, 55.73745), (-7501.7288, 7835.2281)),
    ((37.36875, 55.7131), (-8150.7391, 5125.3738)),
    ((37.38493, 55.59994), (-7154.7885, -7475.0887)),
    ((37.56226, 55.84286), (3999.2677, 19566.2957)),
    ((37.4119, 55.64367), (-5448.4966, -2608.9491)),
    ((37.66372, 55.88274), (10344.8013, 24016.7799)),
    ((37.63855, 55.7009), (8809.9100, 3767.7934)),
    ((37.83813, 55.58537), (21420.6684, -9051.6266)),
    ((37.77923, 55.66557), (17670.7075, -139.1215)),
    ((37.42213, 55.60887), (-4808.7493, -6484.1592)),
    ((37.50424, 55.83932), (364.6070, 19170.4510)),
    ((36.8, 55.14), (-44540.9553, -58461.9032)),
    ((37.0, 55.35), (-31619.1954, -35193.2036)),
    ((37.2, 55.45), (-18884.1150, -24133.2356)),
    ((36.9, 55.25), (-38058.6028, -46275.6627)),
    ((37.45, 55.4), (-3069.3210, -29739.7259)),
    ((37.62, 55.755), (7633.2482, 9788.9148)),
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


class MoscowMsk(unittest.TestCase):
    """Рабочая МСК (как в QGIS) против PROJ: меньше 1 мм в обе стороны; система ОГД = МСК + OGD_SHIFT точно."""

    def test_wgs84_to_msk_vs_proj(self):
        for (lon, lat), (ex, ey) in MSK_PROJ:
            x, y = crs.wgs84_to_msk(lon, lat)
            self.assertLess(math.hypot(x - ex, y - ey), 0.001, f"{lon},{lat}")

    def test_msk_to_wgs84_vs_proj(self):
        for (lon, lat), (x, y) in MSK_PROJ:
            lo, la = crs.msk_to_wgs84(x, y)
            d = math.hypot((lo - lon) * 111320 * math.cos(math.radians(lat)), (la - lat) * 110540)
            self.assertLess(d, 0.001, f"{lon},{lat}")

    def test_ogd_is_msk_plus_shift(self):
        self.assertEqual(crs.OGD_SHIFT, (16.098, 14.512))
        self.assertIn("+x_0=0 ", crs.MSK_PROJ4)
        self.assertIn("+x_0=16.098 +y_0=14.512", crs.OGD_PROJ4)
        for (lon, lat), _ in MSK_PROJ[:5]:
            e, n = crs.wgs84_to_msk50(lon, lat)
            x, y = crs.wgs84_to_msk(lon, lat)
            self.assertAlmostEqual(e - x, 16.098, places=9)
            self.assertAlmostEqual(n - y, 14.512, places=9)
        self.assertEqual(crs.ogd_to_msk(100.0, 200.0), (100.0 - 16.098, 200.0 - 14.512))


if __name__ == "__main__":
    unittest.main()
