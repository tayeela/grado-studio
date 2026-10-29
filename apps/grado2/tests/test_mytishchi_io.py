"""Проверяет сохранение длинных текстов/таблиц и покрытие вытянутой рамки импорта.

Запуск: python -m pytest apps/grado2/tests/test_mytishchi_io.py.
"""
import unittest
from shapely.geometry import box,shape
import preparation as P
import mytishchi_io as M
from sushpol_io import frame_geometry,latest_coverage,fund_share


class MytishchiLayout(unittest.TestCase):
    def test_long_grapheme_sequence_survives_wrap(self):
        text='Объект '+('а\u0301бв'*300)
        lines=M.wrap(text,40,8)
        self.assertEqual(''.join(lines).replace(' ',''),text.replace(' ',''))
        self.assertTrue(all(not line.startswith('\u0301') for line in lines))

    def test_frame_actual_extent_exceeds_heuristic_padding(self):
        center,scale,region=frame_geometry(box(0,0,1000,100),[0,0,260,230])
        bounds=P.to_msk(region).bounds
        self.assertGreater(bounds[3]-bounds[1],1000)
        self.assertTrue(P.to_msk(region).buffer(.001).covers(box(0,0,1000,100)))

    def test_empty_confirmed_source_is_valid_and_new_failure_invalidates_old_receipt(self):
        region=P.to_wgs(box(0,0,100,100));geometry=__import__('shapely').geometry.mapping(region)
        valid={'sourceKey':'source','state':'empty','expectedSublayers':['actual-code'],
               'checkedParts':[{'sublayer':'actual-code','outcome':'empty','area':geometry}]}
        state={'requests':{'first':valid}}
        self.assertTrue(latest_coverage(state,'source',region))
        state['requests']['second']={**valid,'state':'failed','checkedParts':[]}
        self.assertFalse(latest_coverage(state,'source',region))


class FundShare(unittest.TestCase):
    def test_numeric_range_preserves_both_bounds_and_text_is_not_guessed(self):
        self.assertEqual(fund_share(100,.2),"20")
        self.assertEqual(fund_share("10–30",.25),"2.5–7.5 (диапазон)")
        self.assertEqual(fund_share("0",.5),"0")
        for raw in ("свыше 10","*","30–10",False):
            with self.subTest(raw=raw):self.assertIsNone(fund_share(raw,.2))


class LongTable(unittest.TestCase):
    def test_szz_long_row_fits_narrow_number_column_and_retains_all_text(self):
        text="Очень длинное название объекта "*100
        block=M.BLOCKS["restrictions"]["restrictions_table"]
        table=M.table_pages([{"key":"szz","values":["1",text,"Адрес","Документ"]}],
                            ["№","Название","Адрес","Решение РПН / размер СЗЗ"],block["columnWidthsMm"],block["rect"],8,padding=.4)
        self.assertGreater(len(table["pages"]),1)
        recovered="".join(line for page in table["pages"] for row in page for line in row["cells"][1] if line!="(продолжение)")
        self.assertEqual(recovered.replace(" ",""),text.replace(" ",""))
        for page in table["pages"]:
            self.assertLessEqual(table["headHeight"]+sum(row["height"] for row in page),block["rect"][3]+.001)
            for row in page:self.assertEqual(row["cells"][0],["1"])


class AdministrativeUseClass(unittest.TestCase):
    def test_tinao_abbreviation_preserves_agricultural_use_instead_of_industrial(self):
        from sushpol_io import Content
        from sushpol_rules import land_class,ZONES
        from shapely.geometry import mapping
        parcel={"geometry":mapping(box(37.15,55.33,37.17,55.35)),
                "properties":{"ВРИ":"Для ведения сельскохозяйственного производства"}}
        content=object.__new__(Content)
        for title in ("ТАО","НАО","Троицкий административный округ","Новомосковский административный округ"):
            with self.subTest(title=title):
                content.okrugs=[{"geometry":mapping(box(37,55,38,56)),"properties":{"Наименование":title}}]
                self.assertEqual(land_class(parcel["properties"],content.tinao(parcel)),27)
                self.assertEqual(ZONES[27][1],"#b8a47f")
        content.okrugs=[{"geometry":mapping(box(37,55,38,56)),"properties":{"Наименование":"ЦАО"}}]
        self.assertFalse(content.tinao(parcel))
