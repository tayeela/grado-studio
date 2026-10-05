"""T82 (правило 16): станции метро, МЦК и МЦД на листе — значок и название цветом линии; вектор в PDF и PPTX; легенда."""
import sys
import unittest
import zipfile
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402
import print_io  # noqa: E402
import album_io  # noqa: E402
import rail_icons  # noqa: E402

LON, LAT = 37.525, 55.7925
RED = (1.0, 0.0, 19 / 255)
D2 = (0xE9 / 255, 0x42 / 255, 0x82 / 255)
D4 = (0x41 / 255, 0xB3 / 255, 0x84 / 255)


def pt(dx=0.0, dy=0.0):
    return {"type": "Point", "coordinates": [LON + dx, LAT + dy]}


def station(name, ic, color, dx=0.0, dy=0.0, **kw):
    return {"g": pt(dx, dy), "nm": True, "label": name, "ls": 4.4, "lf": "sans-bold", "lh": .55, "lcol": color, "la": 0, "nudge": True, "ic": ic, **kw}


def sheet(features, **kw):
    return {"title": "Лист", "size": "A3", "scale": 2000, "center": [LON, LAT], "legend": [], "tep": [],
            "layers": [{"title": "Станции", "features": features}], **kw}


def ops_of(sh):
    doc = print_io.build_document({"sheets": [sh]}, S.REDLN, S.LGR_DASH)
    return print_io.document_pages_ops(doc, None)[0][2]


def fills(ops, col):
    return [o for o in ops if o.get("op") == "path" and o.get("fill") == col and o.get("name") == "Значок станции"]


def texts(ops, needle):
    return [o for o in ops if o.get("op") == "text" and needle in str(o.get("text"))]


class RailIcons(unittest.TestCase):
    def test_paths_are_vector_and_sized(self):
        for iid in rail_icons.ICONS:
            ops = rail_icons.icon_ops(iid, 100, 100, 3.5)
            ys = [p[1] for o in ops for r in o["rings"] for p in r]
            self.assertAlmostEqual(max(ys) - min(ys), 3.5, delta=.05, msg=iid)       # высота 3,5 мм
            self.assertTrue(all(o["op"] == "path" and o["rings"] for o in ops))
        self.assertGreater(rail_icons.icon_width("mcd-d1", 3.5), rail_icons.icon_width("metro", 3.5))

    def test_metro_icon_and_red_name(self):
        ops = ops_of(sheet([station("Черкизовская", ["metro"], "#FF0013")]))
        self.assertTrue(fills(ops, RED), "значок «М» красный")
        t = texts(ops, "Черкизовская")
        self.assertEqual(len(t), 1)
        self.assertEqual(tuple(round(v, 3) for v in t[0]["color"]), tuple(round(v, 3) for v in RED), "название красное")
        self.assertTrue(t[0].get("halo"), "белая обводка")
        icon = fills(ops, RED)[0]
        ix = [p[0] for r in icon["rings"] for p in r]
        self.assertGreater(t[0]["x"], max(ix), "название справа от значка (место свободно)")

    def test_mcd_icon_and_diameter_colour(self):
        ops = ops_of(sheet([station("Белокаменная", ["mcd-d2"], "#E94282")]))
        self.assertTrue(fills(ops, D2), "параллелограмм D2")
        self.assertTrue(fills(ops, (1.0, 1.0, 1.0)), "белая надпись «D2» поверх")
        t = texts(ops, "Белокаменная")
        self.assertEqual(tuple(round(v, 3) for v in t[0]["color"]), tuple(round(v, 3) for v in D2))
        self.assertFalse(fills(ops, RED), "красного значка нет")

    def test_shared_name_two_icons_one_label(self):
        ops = ops_of(sheet([station("Нижегородская", ["metro", "mcd-d4"], "#FF0013")]))
        self.assertTrue(fills(ops, RED) and fills(ops, D4), "оба значка")
        self.assertEqual(len(texts(ops, "Нижегородская")), 1, "одна подпись")

    def test_ordinary_station_has_no_icon(self):
        ops = ops_of(sheet([{"g": pt(), "nm": True, "label": "ст. ж/д Калошино", "ls": 4.6, "lf": "sans-bold", "lh": .55, "lcol": "#141414", "la": 0}]))
        self.assertFalse([o for o in ops if o.get("name") == "Значок станции"])
        self.assertTrue(texts(ops, "Калошино"))

    def test_name_avoids_other_label_and_icon_stays(self):
        # другая подпись стоит там, где встало бы название справа: название уходит на другое место, значок остаётся
        near = {"g": pt(0.0007, 0), "nm": True, "label": "Соседняя улица очень длинная", "ls": 4.4, "lf": "sans-bold", "la": 0}
        ops = ops_of(sheet([near, station("Сокол", ["metro"], "#FF0013")]))
        self.assertTrue(fills(ops, RED))
        a, b = texts(ops, "Сокол"), texts(ops, "Соседняя")
        if a and b:
            w = print_io._text_w("Сокол", "sans-bold", 4.4)
            w2 = print_io._text_w("Соседняя улица очень длинная", "sans-bold", 4.4)
            self.assertTrue(abs(a[0]["x"] - b[0]["x"]) >= (w + w2) / 2 - .01 or abs(a[0]["y"] - b[0]["y"]) >= 4.4 * .6 * 2 - .01, "подписи не наложены")

    def test_legend_swatch(self):
        for iid in ("metro", "mcd-d1"):
            ops = album_io.concept_swatch(0, 0, {"kind": "icon", "icon": iid}, None)
            self.assertTrue(ops and all(o["op"] == "path" for o in ops), iid)
        self.assertEqual(album_io.concept_swatch(0, 0, {"kind": "icon", "icon": "nope"}, None), [])

    def test_pdf_and_pptx_render(self):
        sh = sheet([station("Нижегородская", ["metro", "mcd-d4"], "#FF0013"), station("Белокаменная", ["mcd-d2"], "#E94282", .002, .001)])
        spec = {"sheets": [sh]}
        pdf = print_io.render_pdf(spec, S.REDLN, S.LGR_DASH)
        self.assertTrue(bytes(pdf).startswith(b"%PDF"))
        pptx = print_io.render_pptx(spec, S.REDLN, S.LGR_DASH)
        xml = b"".join(zipfile.ZipFile(io.BytesIO(bytes(pptx))).read(n) for n in zipfile.ZipFile(io.BytesIO(bytes(pptx))).namelist() if n.startswith("ppt/slides/slide"))
        self.assertIn(b"FF0013", xml.upper())
        self.assertIn(b"E94282", xml.upper())
        self.assertIn("Нижегородская".encode(), xml)


if __name__ == "__main__":
    unittest.main()
