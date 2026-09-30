import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "model"))

from grado_render import backend_pdf, render_svg  # noqa: E402
from grado_render.acad_lin import read_shx  # noqa: E402
from grado_render.backend_pptx import PptxBackend  # noqa: E402
from grado_render.ttf import Font, FontError  # noqa: E402


class TestSvgEscape(unittest.TestCase):
    def test_quotes_escaped_in_text(self):
        svg = render_svg(100, 100, [{"op": "text", "x": 1, "y": 2, "size": 3,
                                     "text": "a\"b'c<d>&"}])
        self.assertIn("a&quot;b&#x27;c&lt;d&gt;&amp;", svg)

    def test_numeric_attr_cannot_carry_markup(self):
        evil = '1" onload="alert(1)'
        for op in ({"op": "circle", "x": 1, "y": 1, "r": evil, "fill": None, "stroke": None},
                   {"op": "text", "x": 1, "y": 1, "size": evil, "text": "t"},
                   {"op": "path", "rings": [[(0, 0), (1, 1)]], "fill": None,
                    "stroke": (0, 0, 0), "width": evil}):
            with self.assertRaises(ValueError):
                render_svg(10, 10, [op])

    def test_numeric_output_unchanged(self):
        svg = render_svg(10, 10, [{"op": "circle", "x": 1, "y": 2, "r": 3, "fill": None,
                                   "stroke": None, "width": 0.3}])
        self.assertIn('r="3" ', svg)


class TestPptxNumeric(unittest.TestCase):
    def test_markup_in_number_rejected(self):
        ops = [{"op": "circle", "x": 1, "y": 1, "r": '1"/><evil', "fill": (0, 0, 0)}]
        with self.assertRaises((ValueError, TypeError)):
            PptxBackend().render([(100, 100, [("g", ops)])])


class TestMalformedBinary(unittest.TestCase):
    def test_shx_garbage(self):
        for data in (b"", b"\x1a", b"AutoCAD-86 shapes 1.0\r\n\x1a",
                     b"AutoCAD-86 shapes 1.0\r\n\x1a" + struct.pack("<HHH", 1, 1, 60000)):
            with self.assertRaises(ValueError):
                read_shx(data)

    def test_shx_self_referencing_subshape_bounded(self):
        # фигура 1 вызывает сама себя много раз: без бюджета — экспоненциальный взрыв
        spec = b"A\x00" + bytes([7, 1] * 100) + b"\x00"
        head = b"AutoCAD-86 shapes 1.0\r\n\x1a" + struct.pack("<HHH", 1, 1, 1) + struct.pack("<HH", 1, len(spec))
        with self.assertRaises(ValueError):
            read_shx(head + spec)

    def test_jpeg_truncated(self):
        for data in (b"\xff\xd8\xff\xc0", b"\xff\xd8", b"\xff\xd8\xff\xe0\x00"):
            with self.assertRaises(ValueError):
                backend_pdf.jpeg_info(data)

    def test_ttf_garbage(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.ttf"
            p.write_bytes(b"\x00\x01\x00\x00\x00\x05" + b"\xff" * 20)
            with self.assertRaises(FontError):
                Font(p)


if __name__ == "__main__":
    unittest.main()
