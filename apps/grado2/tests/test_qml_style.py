"""Стиль из QGIS (.qml → qml_style.py, POST /api/style/qml): единый символ со стопкой слоёв (заливка, штриховка, значки
вдоль линии, линия со сдвигом → полоса), категории, правила и градуированный, подписи, старый формат <prop>, отказы."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import qml_style  # noqa: E402

ZONE = """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34.4-Prizren">
 <renderer-v2 type="singleSymbol">
  <symbols>
   <symbol name="0" type="fill" alpha="1">
    <layer class="SimpleFill" enabled="1">
     <Option type="Map">
      <Option name="color" value="227,73,72,64,rgb:0.89,0.29,0.28,0.25" type="QString"/>
      <Option name="outline_color" value="227,73,72,255" type="QString"/>
      <Option name="outline_width" value="0.52" type="QString"/>
      <Option name="outline_style" value="dash" type="QString"/>
      <Option name="style" value="solid" type="QString"/>
     </Option>
    </layer>
    <layer class="LinePatternFill" enabled="1">
     <Option type="Map"><Option name="lineangle" value="135" type="QString"/><Option name="distance" value="2.6" type="QString"/></Option>
     <symbol name="@0@1" type="line" alpha="1">
      <layer class="SimpleLine" enabled="1"><Option type="Map"><Option name="line_color" value="0,0,0,255" type="QString"/><Option name="line_width" value="0.26" type="QString"/></Option></layer>
     </symbol>
    </layer>
    <layer class="SimpleLine" enabled="1">
     <Option type="Map"><Option name="line_color" value="227,73,72,100" type="QString"/><Option name="line_width" value="2.6" type="QString"/><Option name="offset" value="-1.3" type="QString"/></Option>
    </layer>
    <layer class="MarkerLine" enabled="1">
     <Option type="Map"><Option name="interval" value="5.2" type="QString"/><Option name="offset" value="1" type="QString"/></Option>
     <symbol name="@0@3" type="marker" alpha="1">
      <layer class="SimpleMarker" enabled="1"><Option type="Map"><Option name="name" value="triangle" type="QString"/><Option name="color" value="227,73,72,255" type="QString"/><Option name="size" value="1.3" type="QString"/></Option></layer>
     </symbol>
    </layer>
    <layer class="GeometryGenerator" enabled="1"><Option type="Map"/></layer>
   </symbol>
  </symbols>
 </renderer-v2>
 <labeling type="simple"><settings><text-style fieldName="вид" fontSize="9" textColor="20,20,20,255"/></settings></labeling>
</qgis>"""

CATS = """<qgis><renderer-v2 type="categorizedSymbol" attr="Вид зоны">
 <categories><category value="ЛЭП" symbol="0" render="true" label="ЛЭП"/><category value="ВОЗ" symbol="1" render="false" label="ВОЗ"/></categories>
 <symbols>
  <symbol name="0" type="fill" alpha="1"><layer class="SimpleFill"><prop k="color" v="255,0,0,255"/><prop k="style" v="b_diagonal"/><prop k="outline_color" v="255,0,0,255"/><prop k="outline_width" v="0.26"/></layer></symbol>
  <symbol name="1" type="fill" alpha="0.5"><layer class="SimpleFill"><prop k="color" v="0,0,255,255"/><prop k="style" v="solid"/><prop k="outline_style" v="no"/></layer></symbol>
 </symbols></renderer-v2></qgis>"""

RULES = """<qgis><renderer-v2 type="RuleRenderer"><rules key="r">
 <rule filter="&quot;этажность&quot; >= 9" symbol="0" label="высокие"/>
 <rule filter="&quot;тип&quot; = 'школа'" symbol="1"/>
 <rule filter="regexp_match(&quot;тип&quot;, 'x')" symbol="1" label="сложное"/>
 </rules><symbols>
  <symbol name="0" type="line" alpha="1"><layer class="SimpleLine"><prop k="line_color" v="#112233"/><prop k="line_width" v="0.52"/></layer></symbol>
  <symbol name="1" type="line" alpha="1"><layer class="SimpleLine"><prop k="line_color" v="0,128,0,255"/><prop k="line_width" v="0.26"/><prop k="line_style" v="dot"/></layer>
   <layer class="HashedLine"><prop k="interval" v="3"/><prop k="hash_length" v="1.5"/><prop k="offset" v="-0.5"/></layer></symbol>
 </symbols></renderer-v2></qgis>"""


class QmlStyle(unittest.TestCase):
    def test_single_symbol_stack(self):
        st, rep = qml_style.convert(ZONE, "poly")
        self.assertEqual(st["mode"], "single")
        self.assertEqual(st["fill"], "#e34948")
        self.assertAlmostEqual(st["opacity"], 64 / 255, places=2)
        self.assertEqual(st["dash"], [6, 4])
        self.assertAlmostEqual(st["width"], 2.0, places=1)
        kinds = [p["k"] for p in st["parts"]]
        self.assertEqual(kinds, ["hatch", "band", "marks"])
        h, b, m = st["parts"]
        self.assertEqual((h["hp"], h["hs"]), ("135", 10.0))
        self.assertEqual(b["b"], 10.0)
        self.assertEqual((m["shape"], m["step"], m["side"]), ("tri", 20.0, 1))
        self.assertEqual((st["label"], st["labelSize"], st["labelColor"]), ("вид", 9, "#141414"))
        self.assertEqual(rep, ["слой символа GeometryGenerator не переносится"])

    def test_categories_old_prop_format(self):
        st, _ = qml_style.convert(CATS, "poly")
        self.assertEqual(st["mode"], "cat")
        self.assertEqual(st["cat"]["field"], "Вид зоны")
        self.assertEqual(st["cat"]["colors"], {"ЛЭП": "#ff0000", "ВОЗ": "#0000ff"})
        self.assertEqual(st["cat"]["off"], ["ВОЗ"])
        self.assertEqual((st["cat"]["sym"]["ЛЭП"]["hatch"], st["cat"]["sym"]["ЛЭП"]["hatchPat"]), (True, "135"))
        self.assertEqual(st["cat"]["sym"]["ВОЗ"]["width"], 0)
        self.assertAlmostEqual(st["cat"]["sym"]["ВОЗ"]["opacity"], .5)

    def test_rules_simple_filters_and_hashed_line(self):
        st, rep = qml_style.convert(RULES, "line")
        lst = st["rules"]["list"]
        self.assertEqual([(r["field"], r["op"], r["val"], r["fill"]) for r in lst], [("этажность", "≥", "9", "#112233"), ("тип", "=", "школа", "#008000")])
        self.assertEqual(lst[1]["dash"], [1.5, 3])
        self.assertEqual(lst[1]["parts"][0]["k"], "marks")
        self.assertEqual(lst[1]["parts"][0]["side"], -1)
        self.assertTrue(any("сложное" in r for r in rep))

    def test_graduated_becomes_rules_by_upper_bound(self):
        q = """<qgis><renderer-v2 type="graduatedSymbol" attr="h"><ranges>
          <range lower="10" upper="20" symbol="1"/><range lower="0" upper="10" symbol="0"/></ranges><symbols>
          <symbol name="0" type="fill"><layer class="SimpleFill"><prop k="color" v="255,255,255,255"/></layer></symbol>
          <symbol name="1" type="fill"><layer class="SimpleFill"><prop k="color" v="0,0,0,255"/></layer></symbol></symbols></renderer-v2></qgis>"""
        st, _ = qml_style.convert(q, "poly")
        self.assertEqual([(r["op"], r["val"], r["fill"]) for r in st["rules"]["list"]], [("≤", "10", "#ffffff"), ("≤", "20", "#000000")])

    def test_refusals(self):
        for bad in ("не xml", "<qgis/>", '<!DOCTYPE a [<!ENTITY x "y">]><qgis/>'):
            with self.assertRaises(ValueError):
                qml_style.convert(bad, "poly")

    def test_route(self):
        import server as S
        r = S.post_style_qml(type("C", (), {"obj": lambda self: {"text": ZONE, "geom": "poly"}})())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(json.loads(r.body)["style"]["fill"], "#e34948")
        r = S.post_style_qml(type("C", (), {"obj": lambda self: {"text": "x", "geom": "poly"}})())
        self.assertEqual(r.status_code, 400)
        self.assertIn("QGIS", json.loads(r.body)["error"])


if __name__ == "__main__":
    unittest.main()
