"""Проверяет tools/album_lint.py: на PDF, собранном прямо в тесте (налезающие слова, текст за краем и за рамкой карты, мелкий кегль, невшитый шрифт),
на готовых кусках текста (переносы, «ё», тире, контрольные строки) и на PPTX, собранном в тесте (неразрывные пробелы).

Запуск: python -m unittest discover -s apps/grado2/tests (PYTHONPATH — как в tools/gate.sh). Для проверок PDF нужны утилиты poppler (pdftotext, pdffonts,
pdfimages); без них эти тесты пропускаются, остальные идут всегда.
"""
import importlib.util
import json
import shutil
import tempfile
import unittest
import zipfile
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


def bbox_html(blocks, width=1190.55, height=841.89):
    """Страница в виде вывода pdftotext -bbox-layout: blocks — [[строки текста]]; слова по 40 пт, строки через 12 пт."""
    y, parts = 100.0, []
    for lines in blocks:
        parts.append(f'<block xMin="100" yMin="{y}" xMax="400" yMax="{y + 12 * len(lines)}">')
        for text in lines:
            ws = "".join(f'<word xMin="{100 + 40 * i}" yMin="{y}" xMax="{136 + 40 * i}" yMax="{y + 10}">{w}</word>' for i, w in enumerate(text.split()))
            parts.append(f'<line xMin="100" yMin="{y}" xMax="{100 + 40 * len(text.split())}" yMax="{y + 10}">{ws}</line>')
            y += 12
        parts.append("</block>")
        y += 30
    return f'<doc><page width="{width}" height="{height}"><flow>{"".join(parts)}</flow></page></doc>'


def wrap_codes(blocks):
    """Находки check_wrap для набора блоков: [(код, текст)]."""
    pw, ph, _, bl = album_lint.parse_pages(bbox_html(blocks))[0]
    out = []
    album_lint.check_wrap(1, pw, ph, bl, out)
    return [(f["code"], f["text"]) for f in out]


@unittest.skipUnless(HAVE_POPPLER, "нет утилит poppler")
class AlbumLintTest(unittest.TestCase):
    def lint(self, texts, **kw):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.pdf"
            p.write_bytes(make_pdf(texts, **{k: v for k, v in kw.items() if k in ("width", "height")}))
            return album_lint.lint(str(p), **{k: v for k, v in kw.items() if k not in ("width", "height")})

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

    def test_tight_paragraph_lines_are_not_overlap(self):
        """Строки плотного абзаца: рамки слов в poppler шире букв и «налезают» (ложные срабатывания аудита 07.10) — наложением это не считается."""
        findings, _ = self.lint([(100, 700, 8, "Tight paragraph words here"), (100, 695, 8, "Second line directly below")])
        self.assertNotIn("overlap", self.codes(findings), findings)

    def test_page_size_must_be_a3(self):
        findings, _ = self.lint([(100, 100, 20, "Word one"), (100, 200, 20, "Word two")], width=595.0, height=842.0)
        self.assertIn("size", self.codes(findings))

    def test_label_crossing_map_frame(self):
        """Рамка карты x 7…286 мм: подпись через рамку — ошибка, у рамки ближе 2,5 мм — предупреждение, в легенде справа и внутри — молчим."""
        findings, _ = self.lint([(790, 500, 20, "Crossing"), (762, 450, 20, "Near"), (700, 400, 20, "Inside"), (830, 350, 20, "Legend")],
                                frames={1: (7, 44, 279, 239)})
        frame = {f["text"]: f["sev"] for f in findings if f["code"] == "frame"}
        self.assertEqual(frame, {"Crossing": "error", "Near": "warn"})

    def test_frame_on_page_edge_is_left_to_page_check(self):
        """Лист на всю страницу: кромки рамки совпадают с краем страницы — их проверяет edge/outside, а не frame."""
        findings, _ = self.lint([(1150, 400, 20, "Edgeword")], frames={1: (0, 44, 420, 253)})
        self.assertNotIn("frame", self.codes(findings))
        self.assertTrue({"edge", "outside"} & self.codes(findings))


class WrapTest(unittest.TestCase):
    """Переносы строк внутри блока: poppler не нужен, блоки собираются из текста."""

    def test_preposition_at_line_end(self):
        self.assertEqual([c for c, _ in wrap_codes([["Об утверждении проекта на", "территории Москвы"]])], ["hang"])

    def test_number_separated_from_unit_and_sign(self):
        self.assertEqual([c for c, _ in wrap_codes([["Площадью 1,66", "га территории проекта"]])], ["hang"])
        self.assertEqual([c for c, _ in wrap_codes([["Распоряжение №", "2682-ПП утверждено сегодня"]])], ["hang"])
        self.assertEqual([c for c, _ in wrap_codes([["Проезд ул.", "Амурская ведёт к станции"]])], ["hang"])

    def test_dash_starting_a_line(self):
        self.assertEqual([c for c, _ in wrap_codes([["Станция Локомотив", "— вход с севера улицы"]])], ["hang"])

    def test_short_last_word_is_widow_only_in_a_phrase(self):
        self.assertEqual([c for c, _ in wrap_codes([["Территория сложной формы", "зоны"]])], ["widow"])
        self.assertEqual(wrap_codes([["Объединённый", "архив"]]), [], "название из двух слов в две строки — не абзац")
        self.assertEqual(wrap_codes([["Территория сложной формы", "промышленной зоны"]]), [], "в последней строке больше одного слова")

    def test_normal_text_is_quiet(self):
        self.assertEqual(wrap_codes([["Об утверждении проекта планировки", "территории по адресу"], ["Одна строка"]]), [])


class TextTest(unittest.TestCase):
    """«ё» и тире по всему альбому."""

    def check(self, pages):
        out = []
        album_lint.check_text(pages, out)
        return out

    def test_same_word_with_and_without_yo(self):
        f = self.check([(10, ["разрешенного использования"]), (11, ["разрешённого использования"])])
        self.assertEqual([(x["code"], x["page"]) for x in f], [("yo", 10)])
        self.assertIn("разрешенного", f[0]["msg"])

    def test_other_form_of_the_same_stem(self):
        """«Щелковского шоссе» на одном листе и «Щёлковское» на другом: слово другое по окончанию, основа та же."""
        f = self.check([(8, ["по Щелковского шоссе"]), (3, ["Щёлковское ш."])])
        self.assertEqual([(x["code"], x["page"]) for x in f], [("yo", 3)])

    def test_short_homographs_and_consistent_words_are_quiet(self):
        self.assertEqual(self.check([(1, ["все остальные"]), (2, ["всё остальное"]), (3, ["разрешённого"]), (4, ["разрешённого"])]), [])

    def test_mixed_dashes_on_one_page(self):
        f = self.check([(8, ["3. ТЭЦ-23 – Электрозаводская", "5. улица — дом"]), (9, ["а – б"]), (10, ["в — г"])])
        self.assertEqual([(x["code"], x["page"]) for x in f], [("dash", 8)])


class ExpectTest(unittest.TestCase):
    """Контрольные строки: обязательный и запрещённый текст страниц."""

    PAGES = [(1, "г. Москва, 1-й Иртышский проезд, д. 8"), (2, "Проектируемая территория – 1,66 га"), (3, "карта без выноски")]

    def run_spec(self, spec, pages=None):
        out = []
        album_lint.check_expect(pages or self.PAGES, spec, out)
        return [(f["page"], f["code"], f["sev"]) for f in out]

    def test_required_text_missing_and_found(self):
        self.assertEqual(self.run_spec({"require": [{"text": "1-й Иртышский проезд, вл. 8", "pages": [1]}]}), [(1, "expect", "error")])
        self.assertEqual(self.run_spec({"require": [{"text": "1-й Иртышский проезд, д. 8", "pages": [1]}]}), [])

    def test_required_on_each_page(self):
        spec = {"require": [{"text": "Проектируемая территория – 1,66 га", "pages": [2, 3], "each": True}]}
        self.assertEqual(self.run_spec(spec), [(3, "expect", "error")], "неразрывный пробел при сравнении равен обычному")
        spec["require"][0]["each"] = False
        self.assertEqual(self.run_spec(spec), [], "без each достаточно одной страницы")

    def test_forbidden_text_and_regex(self):
        self.assertEqual(self.run_spec({"forbid": [{"text": "проезд, д. 8", "pages": [1]}, {"re": r"территори[яи] рассмотрения"}]}), [(1, "expect", "error")])
        self.assertEqual(self.run_spec({"forbid": [{"text": "выноски", "sev": "warn"}]}), [(3, "expect", "warn")])

    def test_page_count(self):
        self.assertEqual(self.run_spec({"pages": 11}), [(0, "expect", "error")])
        self.assertEqual(self.run_spec({"pages": 3}), [])

    def test_load_expect_merges_files_and_skips_notes(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.json", Path(d) / "b.json"
            a.write_text(json.dumps({"_": "пояснение", "forbid": [{"text": "x"}], "pages": 11}), encoding="utf-8")
            b.write_text(json.dumps({"require": [{"text": "y"}], "pages": 5}), encoding="utf-8")
            spec = album_lint.load_expect([a, b])
        self.assertEqual((len(spec["forbid"]), len(spec["require"]), spec["pages"]), (1, 1, 11))

    def test_frames_from_spec(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "spec.json"
            p.write_text(json.dumps({"meta": {}, "sheets": [{"rect": [7, 44, 279, 239]}, {"title": "без рамки"}, {"rect": [0, 44, 420, 253]}]}), encoding="utf-8")
            self.assertEqual(album_lint.frames_from_spec(str(p)), {1: (7, 44, 279, 239), 3: (0, 44, 420, 253)})

    def test_shipped_expect_files_are_valid(self):
        """Файлы tools/album_expect/*.json читаются и у каждой строки есть причина."""
        files = sorted((ROOT / "tools" / "album_expect").glob("*.json"))
        self.assertTrue(files, "нет файлов контрольных строк")
        spec = album_lint.load_expect(files)
        for item in spec["require"] + spec["forbid"]:
            self.assertTrue(item.get("text") or item.get("re"), item)
            self.assertTrue(item.get("why"), f"у строки нет причины: {item}")


def make_pptx(path, slides):
    """PPTX из одних слайдов с текстом: slides — [[абзацы]]."""
    ns = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
    with zipfile.ZipFile(path, "w") as z:
        for i, paras in enumerate(slides, 1):
            body = "".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in paras)
            z.writestr(f"ppt/slides/slide{i}.xml", f"<p:sld {ns}><p:cSld><p:spTree><p:sp><p:txBody>{body}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>")


class PptxTest(unittest.TestCase):
    """Неразрывные пробелы в PPTX: правило владельца «№ 2682-ПП», «26.12.2023 г.», «1,66 га», «тыс. кв. м», «ул. …», «ст. ж/д …»."""

    def nbsp(self, paras):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.pptx"
            make_pptx(p, [paras])
            out = []
            n = album_lint.check_pptx(str(p), out)
        self.assertEqual(n, 1)
        return out

    def test_plain_spaces_are_found(self):
        out = self.nbsp(["№ 2682-ПП от 26.12.2023 г.", "территории 1,66 га, 11,13 тыс. кв. м", "ул. Амурская, пр-д № 1286", "ст. ж/д Калошино"])
        what = " ".join(f["msg"] for f in out)
        for part in ("«№» и номер", "число и единица", "«тыс. кв. м»", "сокращение и название", "«ст. ж/д» и название"):
            self.assertIn(part, what)
        self.assertTrue(all(f["code"] == "nbsp" and f["sev"] == "warn" and f["page"] == 1 for f in out))

    def test_non_breaking_spaces_are_quiet(self):
        n = " "
        self.assertEqual(self.nbsp([f"№{n}2682-ПП от 26.12.2023{n}г.", f"территории 1,66{n}га, 11,13{n}тыс.{n}кв.{n}м", f"ул.{n}Амурская, пр-д{n}№{n}1286", f"ст.{n}ж/д{n}Калошино"]), [])

    def test_ordinary_text_is_quiet(self):
        self.assertEqual(self.nbsp(["Об утверждении проекта планировки территории", "Октябрь 2026", "г. Москва, район Гольяново"]), [])

    def test_expect_applies_to_slides(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.pptx"
            make_pptx(p, [["Адрес: д.\u00a08"]])            # неразрывный пробел: nbsp молчит, строка всё равно запрещена
            out = []
            album_lint.check_pptx(str(p), out, {"forbid": [{"text": "д. 8", "pages": [1], "why": "вл."}]})
        self.assertEqual([(f["code"], f["msg"][:5]) for f in out], [("expect", "PPTX:")])


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
