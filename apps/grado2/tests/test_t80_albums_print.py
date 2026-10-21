"""T80: печать альбома 05.10.2026 — слои over, угол mapNoteBR над легендой ортофото, знак «rail», тонкие знаки линий, снимок Яндекса."""
import base64
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402
import print_io  # noqa: E402
import album_io  # noqa: E402

LON, LAT = 37.525, 55.7925


def sq(d, e, lon=LON, lat=LAT):
    return {"type": "Polygon", "coordinates": [[[lon - d, lat - e], [lon + d, lat - e], [lon + d, lat + e], [lon - d, lat + e], [lon - d, lat - e]]]}


def line(lon_a, lon_b):
    return {"type": "LineString", "coordinates": [[lon_a, LAT], [lon_b, LAT + .0003]]}


class OverLayerOrder(unittest.TestCase):
    """Слой с over: true рисуется после белой маски за территорией, остальные — до неё."""
    def _ops(self, over):
        sh = {"title": "Лист", "size": "A3", "scale": 2000, "center": [LON, LAT], "terrMask": .6, "territory": sq(.0012, .0007),
              "legend": [], "tep": [],
              "layers": [{"title": "Под маской", "features": [{"g": line(LON - .002, LON + .002), "stroke": "#112233", "w": 1.5}]},
                         {"title": "Граница района", **({"over": True} if over else {}),
                          "features": [{"g": line(LON - .002, LON + .002), "stroke": "#445566", "w": 1.5}]}]}
        doc = print_io.build_document({"sheets": [sh]}, S.REDLN, S.LGR_DASH)
        return print_io.document_pages_ops(doc, None)[0][2]

    @staticmethod
    def _idx(ops, color):
        return [i for i, o in enumerate(ops) if o.get("op") == "path" and o.get("stroke") and tuple(round(c * 255) for c in o["stroke"]) == color]

    def test_over_layer_after_mask(self):
        ops = self._ops(True)
        mask = [i for i, o in enumerate(ops) if o.get("op") == "path" and o.get("evenodd") and o.get("alpha") == .6]
        self.assertEqual(len(mask), 1)
        plain, over = self._idx(ops, (0x11, 0x22, 0x33)), self._idx(ops, (0x44, 0x55, 0x66))
        self.assertTrue(plain and over)
        self.assertLess(max(plain), mask[0])
        self.assertGreater(min(over), mask[0])

    def test_without_over_layer_stays_under_mask(self):
        ops = self._ops(False)
        mask = next(i for i, o in enumerate(ops) if o.get("op") == "path" and o.get("evenodd"))
        self.assertLess(max(self._idx(ops, (0x44, 0x55, 0x66))), mask)


class TopLayerOverTerritory(unittest.TestCase):
    """Слой с top: true (участки территории на схеме землепользователей) — после границы территории (владелец 21.10.2026, #144)."""
    def _ops(self, top, mask=None):
        sh = {"title": "Лист", "size": "A3", "scale": 2000, "center": [LON, LAT], "territory": sq(.0012, .0007), "legend": [], "tep": [],
              "terrStyle": {"stroke": "#ff00ff", "width": 1.8, "dash": [1.8, 1.8]}, **({"terrMask": mask} if mask else {}),
              "layers": [{"title": "Участки", **({"top": True} if top else {}),
                          "features": [{"g": sq(.0005, .0003), "stroke": "#0000ff", "fill": "#0000ff", "a": 0, "w": 1}]},
                         {"title": "Граница района", "over": True, "features": [{"g": line(LON - .002, LON + .002), "stroke": "#445566", "w": 1.5}]}]}
        doc = print_io.build_document({"sheets": [sh]}, S.REDLN, S.LGR_DASH)
        return print_io.document_pages_ops(doc, None)[0][2]

    def test_top_after_territory(self):
        for mask in (None, .55):
            ops = self._ops(True, mask)
            terr, parcel, over = (OverLayerOrder._idx(ops, c) for c in ((255, 0, 255), (0, 0, 255), (0x44, 0x55, 0x66)))
            self.assertTrue(terr and parcel and over)
            self.assertGreater(min(parcel), max(terr))
            self.assertLess(max(over), min(terr))         # over по-прежнему под границей

    def test_without_top_under_territory(self):
        ops = self._ops(False)
        self.assertLess(max(OverLayerOrder._idx(ops, (0, 0, 255))), min(OverLayerOrder._idx(ops, (255, 0, 255))))


class LineLabelInsideMap(unittest.TestCase):
    """Надпись знака вдоль линии (ЗОУИТ) — только целиком в рамке карты, не поверх колонки легенды (#144)."""
    def test_label_kept_in_frame(self):
        code = next(iter(S.LGR_DASH))
        f = {"g": {"type": "LineString", "coordinates": [[LON - .05, LAT], [LON + .05, LAT]]}, "stroke": "#ff0000", "w": 1,
             "miss": [[code, None]], "ll": "зона мин расстояний"}
        sh = {"title": "Лист", "size": "A3", "scale": 2000, "center": [LON, LAT], "legend": [], "tep": [], "layers": [{"title": "ЗОУИТ", "features": [f]}]}
        doc = print_io.build_document({"sheets": [sh]}, S.REDLN, S.LGR_DASH)
        ops = print_io.document_pages_ops(doc, None)[0][2]
        clip = next(o for o in ops if o.get("op") == "clip")
        x0, y0, w, h = clip["rect"]
        txt = [o for o in ops if o.get("op") == "text" and o.get("text") == "зона мин расстояний"]
        self.assertTrue(txt)
        for o in txt:
            self.assertTrue(x0 < o["x"] < x0 + w and y0 < o["y"] < y0 + h, o)


class LegendLineLabel(unittest.TestCase):
    """Надпись в знаке линии легенды — до 2 мм, не шире знака, над линией (владелец 21.10.2026, #144)."""
    def test_short_label_two_mm_above_line(self):
        size, base = album_io.ll_text_fit("ТЗ", 13.0, 21.5)
        self.assertEqual(size, 2.0)
        self.assertLess(base, 21.5)

    def test_long_label_fits_swatch(self):
        size, _ = album_io.ll_text_fit("техническая зона", 13.0, 21.5)
        self.assertLess(size, 2.0)
        self.assertLessEqual(size * .56 * len("техническая зона"), 14.0 + 1e-9)

    def test_swatch_uses_fit(self):
        out = album_io.concept_swatch(10, 20, {"kind": "lt", "ll": "ТЗ", "stroke": "#ff0000"}, None)
        t = next(o for o in out if o.get("op") == "text")
        self.assertAlmostEqual(t["size"], 2.0, places=6)
        self.assertLess(t["y"], 21.5)


class MapNoteCorners(unittest.TestCase):
    RECT = (0, 44, 420, 253)

    def test_callout_line_keeps_clear_of_map_labels(self):
        # #62: линия выноски листа 2 шла вплотную к концу «Соколиная Гора»: запас вокруг подписи — 1,5 мм
        from print_io import _seg_box

        class M:
            last_ops = [{"op": "text", "x": 60, "y": 50, "size": 3, "text": "Соколиная Гора", "anchor": "middle", "font_family": "sans-bold"}]
        tb = album_io._text_boxes(M.last_ops, pad=0)[0]
        f = album_io.CalloutFrame((0, 70, 20, 10), [("разрабатываемая территория", False)], [(tb[2] + 1.0, 30)], maps=[M()])
        route = next(o["rings"][0] for o in f.ops(None) if o["op"] == "path" and not o["closed"])
        near = (tb[0] - 1.4, tb[1] - 1.4, tb[2] + 1.4, tb[3] + 1.4)
        self.assertFalse(any(_seg_box(p, q, near) for p, q in zip(route, route[1:])), route)

    def test_ortho_legend_h_grows_with_items(self):
        # строки плашки: заголовки групп и знаки (#61); первая строка — в шапке плашки
        h1 = album_io.ortho_legend_h({"cLegend": [{"items": [1]}]})
        h3 = album_io.ortho_legend_h({"cLegend": [{"items": [1, 2]}, {"items": [3]}]})
        h5 = album_io.ortho_legend_h({"cLegend": [{"title": "Границы", "items": [1, 2]}, {"title": "Транспорт", "items": [3]}, {"title": "Пусто", "items": []}]})
        self.assertAlmostEqual(h3 - h1, 5.8 * 2)
        self.assertAlmostEqual(h5 - h1, 5.8 * 4)                         # пустая группа не печатается

    def test_br_corner_sits_above_ortho_legend(self):
        sh = {"cLegend": [{"items": [1, 2, 3, 4]}], "bleed": True}
        lift = album_io.ortho_legend_h(sh) + 2
        x, y, w, h = self.RECT
        lines = ["Район Х", "второй"]
        low = album_io.MapNoteFrame(self.RECT, lines, "br", lift).ops(None)
        flat = album_io.MapNoteFrame(self.RECT, lines, "br", 0).ops(None)
        base = max(o["y"] for o in low)                      # нижняя базовая линия
        self.assertAlmostEqual(base, y + h - lift - 3)
        self.assertLess(base, y + h - album_io.ortho_legend_h(sh))   # выше верха плашки легенды
        self.assertAlmostEqual(max(o["y"] for o in flat) - base, lift)
        self.assertTrue(all(o["x"] == x + w - 50 for o in low))      # справа, а не слева
        tl = album_io.MapNoteFrame(self.RECT, lines, "tl").ops(None)
        self.assertEqual(tl[0]["x"], x + 50)
        self.assertAlmostEqual(tl[0]["y"], y + 7.7)

    def test_build_pptkrt_lifts_br_only_on_bleed_sheets(self):
        class Page:
            size = (420, 297)
        base = {"look": "concept", "title": "Лист", "mapNote": [["А"]], "mapNoteBR": [["Б"]], "cLegend": [{"items": [1, 2]}], "legend": []}
        mf = lambda r, s: album_io.Frame(r)
        for bleed in (True, False):
            sh = {**base, **({"bleed": True} if bleed else {})}
            frames = album_io.build_pptkrt(Page(), sh, {}, S.REDLN, S.LGR_DASH, None, mf)
            br = next(f for f in frames if isinstance(f, album_io.MapNoteFrame) and f.corner == "br")
            self.assertEqual(br.lift, album_io.ortho_legend_h(sh) + 2 if bleed else 0)
            self.assertTrue(any(isinstance(f, album_io.MapNoteFrame) and f.corner == "tl" for f in frames))


class ConceptSwatchRail(unittest.TestCase):
    def test_rail_is_black_line_with_white_dashes(self):
        out = album_io.concept_swatch(10, 20, {"kind": "rail"}, None)
        paths = [o for o in out if o.get("op") == "path"]
        self.assertEqual(len(paths), 2)
        black, white = paths
        self.assertTrue(all(c < .2 for c in black["stroke"]))
        self.assertIsNone(black["dash"])
        self.assertEqual(tuple(white["stroke"]), (1, 1, 1))
        self.assertTrue(white["dash"])
        self.assertLess(white["width"], black["width"])
        self.assertEqual(black["rings"], white["rings"])
        self.assertEqual(black["rings"][0][0][0], 10)
        self.assertEqual(black["rings"][0][1][0], 10 + album_io.SW_W)


class LinetypeMarksThin(unittest.TestCase):
    """Знаки (TAWRF3, TRANG60) — не толще 0,15 масштаба знака, изломы скруглены; сама линия — своей толщины."""
    def _check(self, name, glyph, s):
        for k in (.25, .5):
            ops = print_io.linetype_ops([(0, 0), (300, 0)], name, k, (1, 0, 0), .3, S.REDLN)
            marks = [o for o in ops if o.get("join") == "round"]
            self.assertTrue(marks, name)
            sc = s * k
            for o in marks:
                self.assertLessEqual(o["width"], .15 * sc + 1e-4, f"{name} k={k}")
                self.assertLessEqual(o["width"], .3)
            self.assertEqual(ops[0]["width"], .3)
            self.assertNotIn("join", ops[0])
            self.assertGreater(sum(len(r) for o in marks for r in o["rings"]), 10)

    def test_tawrf3(self):
        lt = S.REDLN["linetypes"]["L00s05t"]
        self.assertEqual({e["shape"].upper() for e in lt["pattern"] if e.get("shape")}, {"TAWRF3"})
        self._check("L00s05t", "TAWRF3", 2.5)

    def test_trang60(self):
        lt = S.REDLN["linetypes"]["L00s11b"]
        self.assertEqual({e["shape"].upper() for e in lt["pattern"] if e.get("shape")}, {"TRANG60"})
        self._check("L00s11b", "TRANG60", 2.0)


class YandexSatPath(unittest.TestCase):
    """Если у плиток есть .ysat — рисует Яндекс; Esri (сам объект) вызывается только там, где Яндекса нет."""
    JPEG = base64.b64decode("/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=")

    def _run(self, ysat_fn):
        esri, yand = [], []

        class Tiles:
            def __call__(s, z, x, y, kind="sat"):
                esri.append((z, x, y))
                return YandexSatPath.JPEG
        t = Tiles()
        t.ysat = lambda z, x, y: (yand.append((z, x, y)), ysat_fn(z, x, y))[1]
        spec = {"sheets": [{"size": "P", "title": "Лист", "scale": 2000, "center": [37.65, 55.80], "basemap": "sat", "layers": [], "legend": [],
                            "tep": [], "territory": None}]}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(print_io, "TILE_FAIL_DIR", Path(d)):
            doc = print_io.build_document(spec, {}, {}, t)
            pages = print_io.document_pages_ops(doc, None)
        return esri, yand, [o for o in pages[0][2] if o["op"] == "image"]

    def test_yandex_used_and_esri_untouched_when_complete(self):
        esri, yand, imgs = self._run(lambda z, x, y: self.JPEG)
        self.assertTrue(yand and imgs)
        self.assertEqual(esri, [])
        self.assertTrue(all(z <= 18 for z, _, _ in yand))              # z18 — потолок: самый подробный настоящий уровень Яндекса

    def test_esri_asked_only_near_missing_yandex_tiles(self):
        esri_all, yand, _ = self._run(lambda z, x, y: None)
        esri, yand2, imgs = self._run(lambda z, x, y: self.JPEG if x % 2 else None)
        self.assertTrue(esri_all)
        self.assertTrue(imgs)
        self.assertTrue(0 < len(esri) < len(esri_all))


if __name__ == "__main__":
    unittest.main()
