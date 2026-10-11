"""Проверяет самопроверку оформления листа (#55): подписи под угловыми надписями и легендой, у рамки карты, подписанные
дважды; подписи на линиях слоёв — не огрех (владелец 10.10.2026, #54 вопросы 2–3).

Запуск: ~/.grado2/venv/bin/python -m pytest apps/grado2/tests/test_label_qa.py
"""

import json
import sys
import unittest
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402
import print_io  # noqa: E402
import label_qa as Q  # noqa: E402

RECT = (10, 10, 200, 150)


def label(text, x, y, size=3.8, angle=0.0):
    return {"op": "text", "x": x, "y": y + size * .35, "size": size, "text": text, "anchor": "middle", "angle": angle, "halo": .55}


def line(pts, width=0.5, stroke=(0.9, 0.1, 0.1), closed=False):
    return {"op": "path", "closed": closed, "fill": None, "stroke": stroke, "width": width, "dash": None, "rings": [pts]}


def page(*layers, outside=()):
    ops = [{"op": "clip", "rect": RECT}]
    for name, _key, items in layers:
        ops.append({"op": "layer", "name": name})
        ops.extend(items)
    return ops + [{"op": "unclip"}] + list(outside)


class LabelQA(unittest.TestCase):
    def kinds(self, ops):
        return sorted((r["kind"], r["text"], r["with"]) for r in Q.page_conflicts(ops))

    def test_labels_over_lines_are_fine(self):
        # подпись поверх красной линии, ж/д, границы района — не огрех (владелец 10.10.2026)
        ops = page(("Красные линии", "gisogd.red_lines", [line([(60, 80), (140, 80)])]),
                   ("Железная дорога", "yandex.rail", [line([(60, 100), (140, 100)])]),
                   ("Подписи", None, [label("ЖК «Квартал Метроном»", 100, 80), label("ст. ж/д Калошино", 100, 100)]))
        self.assertEqual(self.kinds(ops), [])

    def test_twice_on_one_map(self):
        ops = page(("Подписи", None, [label("ЖК «Сиреневый парк»", 60, 60), label("ЖК «Сиреневый парк»", 140, 100),
                                      label("12", 60, 120), label("12", 140, 120)]))
        self.assertEqual(self.kinds(ops), [("dup", "ЖК «Сиреневый парк»", "2")])
        self.assertEqual(Q.phrase(Q.page_conflicts(ops)[0]), "«ЖК «Сиреневый парк»» подписан 2 раза")

    def test_covered_by_corner_note_and_plate(self):
        note = label("район Гольяново", 180, 140)
        plate = {"op": "path", "closed": True, "fill": (1, 1, 1), "stroke": (0, 0, 0), "width": .3, "rings": [[(20, 20), (60, 20), (60, 40), (20, 40)]]}
        page_bg = {"op": "path", "closed": True, "fill": (1, 1, 1), "stroke": None, "width": 0, "rings": [[(0, 0), (420, 0), (420, 297), (0, 297)]]}
        head = label("Заголовок листа", 100, 5)                            # над картой: не в счёт
        ops = page(("Граница района", None, [line([(150, 140), (205, 140)])]),
                   ("Подписи", None, [label("ул. Амурская", 40, 30), label("Строитель-4", 178, 140), label("Свободно", 100, 60)]),
                   outside=[page_bg, head, plate, note])
        got = self.kinds(ops)
        self.assertIn(("cover", "ул. Амурская", "легенда"), got)
        self.assertIn(("cover", "Строитель-4", "район Гольяново"), got)
        self.assertFalse([g for g in got if g[0] not in ("cover", "edge", "dup")])
        self.assertFalse([g for g in got if g[1] == "Свободно"])

    def test_edge(self):
        ops = page(("Подписи", None, [label("ЖК «2-й Иртышский»", 100, 11.5), label("Середина", 100, 80)]))
        got = self.kinds(ops)
        self.assertEqual([g[:2] for g in got], [("edge", "ЖК «2-й Иртышский»")])

    def test_phrases_and_album(self):
        ops = page(("Подписи", None, [label("Архив", 100, 11.5)]))
        rows = Q.album_conflicts([(420, 297, page()), (420, 297, ops)])
        self.assertEqual(rows[0][0], 2)
        self.assertEqual(Q.phrase(rows[0][1][0]), "«Архив» у рамки карты (0.2 мм)")

    def test_layout_qa_writes_sheets_and_headers(self):
        ops = page(("Подписи", None, [label("Архив", 60, 60), label("Архив", 140, 100)]))
        spec = {"sheets": [{"title": "а"}, {"title": "б"}]}
        print_io.layout_qa(spec, [(420, 297, page()), (420, 297, ops)])
        self.assertEqual(spec["sheets"][0]["_labelQA"], [])
        self.assertEqual(spec["sheets"][1]["_labelQA"], ["«Архив» подписан 2 раза"])
        h = dict(S.not_ready_headers(spec))
        self.assertEqual(h["X-Grado-Layout-QA"], "2:1")
        self.assertEqual(json.loads(unquote(h["X-Grado-Layout-QA-Why"])), {"2": ["«Архив» подписан 2 раза"]})
        h["X-Grado-Layout-QA-Why"].encode("ascii")
        big = {"sheets": [{"_labelQA": [f"«Подпись номер {i}» у рамки карты (0.0 мм)" for i in range(400)]}]}
        hb = dict(S.layout_qa_headers(big))
        self.assertEqual(hb["X-Grado-Layout-QA"], "1:400")
        self.assertLessEqual(len(hb["X-Grado-Layout-QA-Why"]), S.QA_HEADER_MAX)
        self.assertTrue(json.loads(unquote(hb["X-Grado-Layout-QA-Why"]))["1"])


if __name__ == "__main__":
    unittest.main()
