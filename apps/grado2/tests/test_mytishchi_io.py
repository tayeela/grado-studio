"""Проверяет сохранение длинных текстов/таблиц и покрытие вытянутой рамки импорта.

Запуск: python -m pytest apps/grado2/tests/test_mytishchi_io.py.
"""
import unittest
from shapely.geometry import box,shape
import preparation as P
import mytishchi_io as M
from sushpol_io import frame_geometry,latest_coverage,latest_receipt,fund_share


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
        valid={'sourceKey':'source','state':'empty','expectedSublayers':['actual-code'],'checkedAt':'2026-10-31T10:00:00Z',
               'checkedParts':[{'sublayer':'actual-code','outcome':'empty','area':geometry}]}
        state={'requests':{'first':valid}}
        self.assertTrue(latest_coverage(state,'source',region))
        state['requests']['second']={**valid,'state':'failed','checkedParts':[],'checkedAt':'2026-10-31T11:00:00Z'}
        self.assertFalse(latest_coverage(state,'source',region))

    def test_latest_receipt_is_chosen_by_time_not_file_order(self):
        # Порядок ключей в файле проекта не хронологический (финальная запись прогона — из
        # снимка состояния): у Безобразово 31.10 «последней» квитанцией yandex.water в словаре
        # была провальная от 29.10, и полная свежая выгрузка помечалась «Источник недоступен».
        region=P.to_wgs(box(0,0,100,100));geometry=__import__('shapely').geometry.mapping(region)
        fresh={'sourceKey':'source','state':'received','expectedSublayers':['actual-code'],'checkedAt':'2026-10-31T16:40:00Z',
               'checkedParts':[{'sublayer':'actual-code','outcome':'received','area':geometry}]}
        old_failed={'sourceKey':'source','state':'failed','checkedParts':[],'checkedAt':'2026-10-29T18:14:24Z'}
        state={'requests':{'fresh':fresh,'old_stale':old_failed}}
        self.assertTrue(latest_coverage(state,'source',region))
        self.assertIs(latest_receipt(state,'source'),fresh)


class FundShare(unittest.TestCase):
    def test_numeric_range_preserves_both_bounds_and_text_is_not_guessed(self):
        self.assertEqual(fund_share(100,.2),"20")
        self.assertEqual(fund_share("10–30",.25),"2.5–7.5 (диапазон)")
        self.assertEqual(fund_share("0",.5),"0")
        for raw in ("свыше 10","*","30–10",False):
            with self.subTest(raw=raw):self.assertIsNone(fund_share(raw,.2))


class LegendSigns(unittest.TestCase):
    def test_zone_rows_carry_color_swatches_and_headers_are_bold(self):
        # Канон Мытищинской: у строк легенды — цветные квадраты/линии-образцы, группы — заголовки.
        ops=M.TextBlock((100,10,60,40),[{"text":"ГРАНИЦЫ","header":True},
                                        {"text":"природно-рекреационного вида","fill":"#cfe4b3"},
                                        {"text":"разрабатываемой территории","stroke":"#ff00ff","dash":[1,1]},
                                        "простая строка"],8).ops(None)
        swatch=[o for o in ops if o.get("op")=="path" and o.get("fill") is not None]
        sample=[o for o in ops if o.get("op")=="path" and o.get("dash")]
        self.assertEqual(len(swatch),1)                     # заливка зоны — один квадрат с образом цвета
        self.assertEqual(len(sample),1)                     # линия границы — образец с тем же штрихом
        self.assertEqual(sample[0]["stroke"],(1.0,0.0,1.0))
        bold=[o for o in ops if o.get("op")=="text" and o.get("font_family")=="sans-bold"]
        self.assertTrue(any("ГРАНИЦЫ" in str(o.get("text","")) for o in bold))


class AerialPhotoLayout(unittest.TestCase):
    def test_aerial_spans_upper_zone_and_ground_frames_take_bottom_row(self):
        # #144 (владелец 21.10): на месте снимков 1–4 — вид с высоты одним кадром,
        # наземные снимки становятся нижним рядом с номерами 1–4.
        blocks=M.BLOCKS["photos"]
        sh={"mytishchiKind":"photos","maps":[],"textBlocks":{},"tables":{},
            "photos":[{"aerial":True,"data":"aerial","at":[37.16,55.34],"dir":0},
                      {"data":"g1","at":[37.15,55.34],"dir":90,"number":1},
                      {"data":"g2","at":[37.15,55.34],"dir":180,"number":2},
                      {"data":"g3","at":[37.15,55.34],"dir":270,"number":3},
                      {"data":"g4","at":[37.15,55.34],"dir":0,"number":4}]}
        page=type("P",(object,),{"size":list((420,297))})()
        frames=[f for f in M.build_frames(page,sh,{"short":"тест"},None,None,None,lambda r,s:None)
                if isinstance(f,M.PhotoBlock)]
        self.assertEqual(len(frames),5)
        top=frames[0]
        self.assertGreater(top.rect[2],150)               # аэрокадр занимает всю верхнюю правую зону
        self.assertIsNone(top.number)
        for i,f in enumerate(frames[1:]):
            self.assertEqual(tuple(f.rect),tuple(blocks[f"photo_{5+i}"]["rect"]))
            self.assertEqual(f.number,i+1)


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


class SourceLineColors(unittest.TestCase):
    def test_water_and_coastal_types_keep_their_source_palette(self):
        import sushpol_io as C
        from shapely.geometry import mapping,LineString
        from unittest.mock import patch
        region=P.to_wgs(box(0,0,100,100))
        feature={"geometry":mapping(LineString(list(region.exterior.coords)[:2])),"properties":{"_lt":["L00s16b","L00s17b","L00s41b"]}}
        content=object.__new__(C.Content);content.msk=box(0,0,100,100);content.project={"data":{"gisogd.red_lines":{"fc":{"features":[feature]}}}}
        content.state={};content.territory=region;content.require=lambda *args:None
        with patch.object(C.M,"BLOCKS",{"restrictions":{"map":{"rect":[0,0,100,100]}}}):
            rows=content.map("restrictions","map",["gisogd.red_lines"])["sheet"]["layers"][0]["features"]
        self.assertEqual([r["stroke"] for r in rows],["#ff0000","#ff0000","#0018b8"])
        self.assertEqual([r["lt"] for r in rows],[["L00s16b"],["L00s17b"],["L00s41b"]])
