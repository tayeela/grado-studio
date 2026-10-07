"""Проверяет tools/album_lint.py на PDF, собранном прямо в тесте: налезающие слова, текст за краем, мелкий кегль, невшитый шрифт.

Запуск: python -m unittest discover -s apps/grado2/tests (PYTHONPATH — как в tools/gate.sh). Нужны утилиты poppler (pdftotext, pdffonts, pdfimages);
без них тесты пропускаются.
"""
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("album_lint", ROOT / "tools" / "album_lint.py")
album_lint = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(album_lint)

HAVE_POPPLER = all(shutil.which(x) for x in ("pdftotext", "pdffonts", "pdfimages"))


def make_pdf(texts, width=1190.55, height=841.89):
    """Одностраничный PDF со шрифтом Helvetica (не вшит): texts — [(x, y, кегль, текст)]."""
    stream = "".join(f"BT /F1 {size} Tf {x} {y} Td ({text}) Tj ET\n" for x, y, size, text in texts).encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>".encode(),
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


@unittest.skipUnless(HAVE_POPPLER, "нет утилит poppler")
class AlbumLintTest(unittest.TestCase):
    def lint(self, texts, **kw):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.pdf"
            p.write_bytes(make_pdf(texts, **kw))
            return album_lint.lint(str(p))

    def codes(self, findings):
        return {f["code"] for f in findings}

    def test_overlap_edge_tiny_and_font(self):
        findings, pages = self.lint([(100, 700, 20, "Overlap"), (110, 705, 20, "Collision"), (1150, 400, 20, "Edgeword"), (300, 300, 3, "Tiny")])
        self.assertEqual(pages, 1)
        codes = self.codes(findings)
        self.assertIn("overlap", codes, "слова, налезающие друг на друга")
        self.assertTrue({"outside", "edge"} & codes, "слово у края страницы")
        self.assertIn("tiny", codes, "кегль 3 пт")
        self.assertIn("font", codes, "Helvetica не вшит")

    def test_clean_page_has_no_text_findings(self):
        findings, _ = self.lint([(100, 700, 20, "First"), (100, 600, 20, "Second line"), (400, 400, 20, "Third")])
        self.assertFalse(self.codes(findings) & {"overlap", "outside", "edge", "tiny"}, findings)

    def test_page_size_must_be_a3(self):
        findings, _ = self.lint([(100, 100, 20, "Word one"), (100, 200, 20, "Word two")], width=595.0, height=842.0)
        self.assertIn("size", self.codes(findings))


class FormatLinesTest(unittest.TestCase):
    """Текст отчёта (его печатают album_lint.py и album_check.py): poppler не нужен."""

    def test_header_counts_and_order(self):
        row = lambda page, sev, code, tile="": {"page": page, "sev": sev, "code": code, "text": "x", "mm": [], "tile": tile, "msg": "m"}
        lines = album_lint.format_lines([row(2, "warn", "edge", "01"), row(2, "error", "overlap"), row(1, "warn", "tiny")], 2)
        self.assertEqual(lines[0], "album_lint: страниц 2, ошибок 1, предупреждений 2")
        self.assertIn("стр.  1", lines[1], "страницы идут по порядку")
        self.assertIn("error", lines[2], "на странице сначала ошибки")
        self.assertIn("плитка 01", lines[3])

    def test_no_findings_is_one_line(self):
        self.assertEqual(album_lint.format_lines([], 11), ["album_lint: страниц 11, ошибок 0, предупреждений 0"])


if __name__ == "__main__":
    unittest.main()
