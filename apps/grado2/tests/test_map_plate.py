"""Пластина карты на Rust (rust/crates/plate через grado_rs.render_plate, layout_io.map_plate): та же сцена, что
векторная печать карты блока, — картинкой заданного dpi; подписи не растрируются (остаются векторными поверх).
Без установленного grado_rs тесты пропускаются; сверку по пикселям с векторной картой делает rust/parity/plate."""

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402
import layout_io  # noqa: E402

LON, LAT = 37.803, 55.827


def square(d):
    return {"type": "Polygon", "coordinates": [[[LON - d, LAT - d / 2], [LON + d, LAT - d / 2], [LON + d, LAT + d / 2], [LON - d, LAT + d / 2], [LON - d, LAT - d / 2]]]}


def spec(layers, **block):
    return {"block": {"w": 100, "h": 80, "scale": 2000, "center": [LON, LAT], **block}, "layers": layers}


@unittest.skipUnless(layout_io.rust_plate(), "модуль grado_rs не установлен")
class MapPlate(unittest.TestCase):
    def test_plate_size_follows_dpi_and_colour_is_the_layer_fill(self):
        from PIL import Image
        png, info = layout_io.map_plate(spec([{"title": "Квартал", "features": [{"g": square(.0005), "fill": "#cc0000", "stroke": "#000000", "w": 1, "a": 1, "label": "А"}]}]),
                                        S.REDLN, S.LGR_DASH, None, 200)
        img = Image.open(io.BytesIO(png)).convert("RGB")
        self.assertEqual(img.size, (round(100 * 200 / 25.4 + .5), round(80 * 200 / 25.4 + .5)))
        self.assertEqual(img.getpixel((img.width // 2, img.height // 2)), (204, 0, 0))      # центр карты — заливка слоя
        self.assertEqual(img.getpixel((3, 3)), (255, 255, 255))
        self.assertGreater(info["ink"], .01)
        self.assertGreaterEqual(info["skipped"], 1)                                          # подпись не в пластине

    def test_empty_map_has_no_ink(self):
        png, info = layout_io.map_plate(spec([]), S.REDLN, S.LGR_DASH, None, 100)
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertEqual(info["ink"], 0)

    def test_hatch_dash_and_alpha_reach_the_plate(self):
        f = {"g": square(.0008), "fill": "#ddebd3", "stroke": "#2e7d32", "w": 2, "a": .5, "dash": [6, 4], "hatch": True, "hp": "45", "hc": "#2e7d32"}
        png, info = layout_io.map_plate(spec([{"title": "Р1", "features": [f]}]), S.REDLN, S.LGR_DASH, None, 150)
        from PIL import Image
        img = Image.open(io.BytesIO(png)).convert("RGB")
        greens = sum(1 for p in img.get_flattened_data() if p[1] > p[0] + 40 and p[1] > p[2] + 40)
        self.assertGreater(greens, 200, "штрихи и контур цвета hc")
        self.assertGreaterEqual(info["drawn"], 3)

    def test_server_route_returns_png_with_ink_header(self):
        import json
        import threading
        import urllib.request
        srv = S.Server(("127.0.0.1", 0))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            body = json.dumps(spec([{"title": "К", "features": [{"g": square(.0005), "fill": "#336699", "w": 0, "a": 1}]}])).encode()
            r = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}/api/print/map_png", data=body, method="POST"), timeout=10)
            self.assertEqual(r.headers["Content-Type"], "image/png")
            self.assertGreater(float(r.headers["X-Plate-Ink"]), 0)
            self.assertTrue(r.read().startswith(b"\x89PNG"))
        finally:
            srv.shutdown()
            srv.server_close()

if __name__ == "__main__":
    unittest.main()
