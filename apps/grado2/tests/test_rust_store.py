"""Сверка дискового хранилища Rust (`crates/store`, план 09.11.2026 шаг С3) с эталоном Python:
вырезка по области (`GisogdApi._from_lines`, `_grid_read`), подсчёт по каталогу (`ogd_all.scan`),
очередь ночного обновления (`store_stale`) и плитка карты (`store_tile`)."""

import gzip
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "core/connectors"))
sys.path.insert(0, str(HERE.parents[1] / "core/render"))

from grado_connectors.gisogd_api import GisogdApi  # noqa: E402
import ogd_all  # noqa: E402
import ogd_warm  # noqa: E402

try:
    import grado_rs
    HAS_STORE = hasattr(grado_rs, "store_query")
except ImportError:
    HAS_STORE = False


def _poly(i, x, y, d=0.005):
    g = {"type": "Polygon", "coordinates": [[[x, y], [x + d, y], [x + d, y + d], [x, y + d], [x, y]]]}
    return (x, y, x + d, y + d), f"l1:{i}", {"geometry": g, "properties": {"id": i, "name": f"ЗОУИТ {i}"}}


def _write_lines2(cache: Path, code: str, items):
    (cache / f"{code}.shp.gz").write_bytes(b"stub")
    with gzip.open(cache / f"{code}.shp.lines2.gz", "wt", encoding="utf-8") as fh:
        for bb, key, body in items:
            fh.write(",".join(repr(v) for v in bb) + "\t" + key + "\t" + json.dumps(body, ensure_ascii=False, separators=(",", ":")) + "\n")


@unittest.skipUnless(HAS_STORE, "grado_rs без store_query")
class RustStoreParity(unittest.TestCase):
    def test_from_lines_and_scan_match_python(self):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            items = [_poly(1, 37.52, 55.79), _poly(2, 37.525, 55.792), _poly(3, 37.80, 55.90)]
            _write_lines2(cache, "zouit", items)
            bbox = (37.515, 55.788, 37.532, 55.798)
            cat = [{"id": 1, "parent_id": None, "name": "Слои", "type": "folder"},
                   {"id": 2, "parent_id": 1, "name": "ЗОУИТ", "type": "layer", "code": "zouit"},
                   {"id": 3, "parent_id": 1, "name": "Нет в кэше", "type": "layer", "code": "missing"}]

            api = GisogdApi(cache_dir=cache, ttl=3600)
            with mock.patch.dict(os.environ, {"GRADO_STORE": "python"}):
                py_feats = api._from_lines("zouit", bbox)
                py_scan = ogd_all.scan(bbox, cache, cat)

            with mock.patch.dict(os.environ, {"GRADO_STORE": "rust"}):
                rs_feats = api._from_lines("zouit", bbox)
                rs_scan = ogd_all.scan(bbox, cache, cat)

            self.assertTrue((cache / "zouit.gstore").exists())
            self.assertEqual(sorted(f["grado_key"] for f in py_feats), sorted(f["grado_key"] for f in rs_feats))
            self.assertEqual(len(rs_feats), 2)
            self.assertEqual(py_scan, rs_scan)
            self.assertEqual(rs_scan, {"zouit": 2, "missing": None})

    def test_egko_grid_read_matches_python(self):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            gdir = cache / "base2.buildings.shp.grid"
            gdir.mkdir()
            (gdir / "_meta.json").write_text('{"code":"buildings","map":"base2","count":2}', "utf-8")
            items = [_poly(10, 37.521, 55.791, 0.001), _poly(11, 37.75, 55.85, 0.001)]
            with gzip.open(gdir / "3752_5579.lines.gz", "wt", encoding="utf-8") as fh:
                for bb, key, body in items[:1]:
                    fh.write(",".join(repr(v) for v in bb) + "\t" + key + "\t" + json.dumps(body, ensure_ascii=False) + "\n")
            with gzip.open(gdir / "3775_5585.lines.gz", "wt", encoding="utf-8") as fh:
                for bb, key, body in items[1:]:
                    fh.write(",".join(repr(v) for v in bb) + "\t" + key + "\t" + json.dumps(body, ensure_ascii=False) + "\n")

            api = GisogdApi(cache_dir=cache, map_name="base2", ttl=3600)
            bbox = (37.519, 55.789, 37.530, 55.796)
            with mock.patch.dict(os.environ, {"GRADO_STORE": "python"}):
                py_feats = api._grid_read("buildings", bbox)
            with mock.patch.dict(os.environ, {"GRADO_STORE": "rust"}):
                rs_feats = api._grid_read("buildings", bbox)

            self.assertTrue((cache / "base2.buildings.gstore").exists())
            self.assertEqual(sorted(f["grado_key"] for f in py_feats), sorted(f["grado_key"] for f in rs_feats))
            self.assertEqual(len(rs_feats), 1)

    def test_stale_matches_ogd_warm_and_tile_works(self):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            _write_lines2(cache, "fresh_a", [_poly(1, 37.52, 55.79)])
            api = GisogdApi(cache_dir=cache, ttl=ogd_warm.REFRESH)
            items = [{"code": "fresh_a"}, {"code": "missing_b"}, {"code": "missing_c"}]
            py_stale = [x["code"] for x in ogd_warm.stale(items, lambda c: ogd_warm.ogd_age(api, c))]
            rs_stale = grado_rs.store_stale(str(cache), "isogd", [x["code"] for x in items], float(ogd_warm.REFRESH))
            self.assertEqual(py_stale, rs_stale)

            tile_js = grado_rs.store_tile(str(cache), "isogd", "fresh_a", 0, 0, 0, 3600.0, 0.0)
            self.assertIsNotNone(tile_js)
            fc = json.loads(tile_js)
            self.assertEqual(fc["type"], "FeatureCollection")
            self.assertEqual(len(fc["features"]), 1)


if __name__ == "__main__":
    unittest.main()
