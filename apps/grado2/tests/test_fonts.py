"""Любой шрифт подписей (владелец 10.10.2026): каталог fonts.py (свой файл TTF, TTC, OTF с CFF), семейство «f:<id>» в печати
PDF, PPTX и SVG, настройка альбома labelFont и правка надписи макета."""

import io
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402,F401  (пути ядра)
import fonts  # noqa: E402
import print_io  # noqa: E402
from grado_render import Font, PdfBackend, find_font, render_svg  # noqa: E402
from grado_render.backend_pptx import PptxBackend  # noqa: E402

BUNDLED = Path(__file__).resolve().parents[3] / "docs" / "standards" / "fonts"


def cff_font():
    """Маленький OTF с контурами CFF: «.notdef», «Ж», «A» — как шрифты Adobe и большинство OTF на Mac."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen

    def box(w):
        pen = T2CharStringPen(w, None)
        pen.moveTo((50, 0)); pen.lineTo((50, 700)); pen.curveTo((200, 750), (400, 750), (w - 50, 700)); pen.lineTo((w - 50, 0)); pen.closePath()
        return pen.getCharString()
    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder([".notdef", "A", "uni0416"])
    fb.setupCharacterMap({0x41: "A", 0x416: "uni0416"})
    fb.setupCFF("GradoTestCFF", {"FullName": "Grado Test CFF"}, {".notdef": box(500), "A": box(600), "uni0416": box(900)}, {})
    fb.setupHorizontalMetrics({".notdef": (500, 50), "A": (600, 50), "uni0416": (900, 50)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Grado Test CFF", "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=800, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    buf = io.BytesIO()
    fb.save(buf)
    return buf.getvalue()


def ttc_of(*paths):
    from fontTools.ttLib import TTCollection, TTFont
    c = TTCollection()
    c.fonts = [TTFont(str(p)) for p in paths]
    buf = io.BytesIO()
    c.save(buf)
    return buf.getvalue()


class Fonts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        home = Path(self.tmp.name)
        self.patches = [mock.patch.multiple(fonts, HOME=home, USER=home / "user", TTF=home / "ttf", INDEX=home / "index.json"),
                        mock.patch.object(fonts, "_system_dirs", lambda: [])]
        for p in self.patches:
            p.start()
        fonts._cache["fams"] = None
        fonts.install()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        fonts._cache["fams"] = None
        self.tmp.cleanup()

    def test_presets_and_user_ttf(self):
        L = fonts.listing()
        self.assertEqual([p["id"] for p in L["presets"]], ["ui", "serif", "sans"])
        self.assertEqual(L["fonts"], [])
        ids = fonts.add_file("Мой шрифт.ttf", (BUNDLED / "PTSans-Regular.ttf").read_bytes())
        self.assertEqual(len(ids), 1)
        fid = ids[0]
        self.assertRegex(fid, r"^f:[0-9a-f]{12}$")
        row = fonts.listing()["fonts"][0]
        self.assertEqual((row["id"], row["name"], row["bold"], row["user"]), (fid, "PT Sans", False, True))
        name, path, bold = fonts.resolve(fid)
        self.assertEqual((name, bold), ("PT Sans", False))
        self.assertEqual(find_font(fid), path)                             # печать находит файл через ttf.CUSTOM
        self.assertEqual(fonts.resolve(fid + "-bold")[1], path)            # жирного нет — обычное
        self.assertIsNone(fonts.resolve("f:000000000000"))
        self.assertTrue(find_font("f:000000000000").endswith("PTSans-Regular.ttf"))   # нет шрифта здесь — PT Sans, лист не падает

    def test_ttc_with_bold(self):
        ids = fonts.add_file("pair.ttc", ttc_of(BUNDLED / "PTSerif-Regular.ttf", BUNDLED / "PTSerif-Bold.ttf"))
        fid = ids[0]
        reg, bold = fonts.resolve(fid), fonts.resolve(fid + "-bold")
        self.assertEqual((reg[0], reg[2], bold[2]), ("PT Serif", False, True))
        self.assertNotEqual(reg[1], bold[1])
        self.assertGreater(Font(bold[1]).text_width("Ж", 10), Font(reg[1]).text_width("Ж", 10) * .9)

    def test_cff_otf_converted_for_print(self):
        fid = fonts.add_file("cff.otf", cff_font())[0]
        _, path, _ = fonts.resolve(fid)
        self.assertTrue(path.endswith(".ttf") and Path(path).parent == fonts.TTF)
        f = Font(path)                                                     # минимальный разбор печати: glyf и cmap 4
        self.assertAlmostEqual(f.text_width("Ж", 10), 9.0, places=3)
        pdf = PdfBackend().render([(60, 30, [{"op": "text", "x": 5, "y": 15, "size": 6, "text": "ЖА", "font_family": fid}])])
        self.assertTrue(pdf.startswith(b"%PDF") and b"FontFile2" in pdf)

    def test_rejects_non_fonts(self):
        with self.assertRaises(ValueError):
            fonts.add_file("x.txt", b"hello")
        with self.assertRaises(ValueError):
            fonts.add_file("x.ttf", b"not a font at all")
        self.assertEqual(list((fonts.USER).glob("*")), [])                  # испорченный файл не остаётся

    def test_label_font_setting_and_edits(self):
        fid = fonts.add_file("a.ttf", (BUNDLED / "PTSans-Regular.ttf").read_bytes())[0]
        m = print_io.label_fonts(fid)
        self.assertEqual((m[None], m["sans-bold"], m["serif"]), (fid, fid + "-bold", fid))
        self.assertEqual(print_io.label_fonts("pt-serif")["sans-bold"], "serif-bold")
        self.assertIsNone(print_io.label_fonts("f:zz"))
        self.assertIsNone(print_io.label_fonts("Arial"))
        L = [{"key": "osm.roads", "features": [{"label": "ул. Тверская", "lf": "sans-bold"}, {"label": "12"}, {"label": "П\nЖ", "lfs": ["sans-bold", None]}]}]
        out = print_io.album_settings({"labelFont": fid}, L)[0]["features"]
        self.assertEqual([f.get("lf") for f in out], [fid + "-bold", fid, fid])
        self.assertEqual(out[2]["lfs"], [fid + "-bold", None])
        o = print_io._edited({"op": "text", "x": 0, "y": 0, "size": 3, "text": "т"}, {"font": fid + "-bold"})
        self.assertEqual(o["font_family"], fid + "-bold")
        o = print_io._edited({"op": "text", "x": 0, "y": 0, "size": 3, "text": "т"}, {"font": "f:../../etc"})
        self.assertNotIn("font_family", o)

    def test_svg_and_pptx(self):
        fid = fonts.add_file("a.ttf", (BUNDLED / "PTSans-Regular.ttf").read_bytes())[0]
        ops = [{"op": "text", "x": 5, "y": 10, "size": 4, "text": "Пресня", "font_family": fid + "-bold"}]
        svg = render_svg(60, 30, ops)
        self.assertIn(f"font-family:'gf-{fid[2:]}';font-weight:bold;src:url('/api/fonts/file?f={fid}-bold')", svg)
        self.assertIn(f"font-family=\"'gf-{fid[2:]}', Arial, sans-serif\" font-weight=\"bold\"", svg)
        data = PptxBackend().render([(60, 30, [("Карта", ops)])])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            slide = z.read("ppt/slides/slide1.xml").decode("utf-8")
            pres = z.read("ppt/presentation.xml").decode("utf-8")
            self.assertTrue(any(n.startswith("ppt/fonts/") for n in z.namelist()))
        self.assertIn('typeface="PT Sans"', slide)
        self.assertIn('<p:font typeface="PT Sans"/>', pres)

    def test_index_survives_and_skips_unchanged(self):
        fonts.add_file("a.ttf", (BUNDLED / "PTSans-Regular.ttf").read_bytes())
        self.assertTrue(fonts.INDEX.exists())
        with mock.patch.object(fonts, "_faces", side_effect=AssertionError("re-read")):
            fonts._cache["fams"] = None
            self.assertEqual(len(fonts.families()), 1)                     # файл не менялся — из указателя

    def test_api_routes(self):
        import base64
        import json
        S = server
        self.assertIs(S.GET_ROUTES["/api/fonts"], S.get_fonts)
        self.assertIs(S.POST_ROUTES["/api/fonts"], S.post_font)
        self.assertEqual(S.body_limit("/api/fonts"), S.MAX_BIG_BODY)
        c = mock.Mock()
        c.q = lambda k, d="": ""
        c.obj = lambda: {"name": "a.ttf", "b64": base64.b64encode((BUNDLED / "PTSans-Regular.ttf").read_bytes()).decode()}
        j = json.loads(S.post_font(c).body)
        fid = j["ids"][0]
        self.assertEqual([f["id"] for f in j["fonts"]], [fid])
        c.q = lambda k, d="": fid + "-bold" if k == "f" else ""
        r = S.get_font_file(c)
        self.assertEqual((r.status_code, r.media_type), (200, "font/ttf"))
        self.assertEqual(r.body[:4], b"\x00\x01\x00\x00")
        c.q = lambda k, d="": "f:000000000000" if k == "f" else ""
        self.assertEqual(S.get_font_file(c).status_code, 404)


if __name__ == "__main__":
    unittest.main()
