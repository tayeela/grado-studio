"""Проверяет геометрию скачанного кадра: направление, стык, качество и неполные тайлы.

Запуск: python -m pytest apps/grado2/tests/test_panorama_io.py.
"""
import io
import math
import threading
import time
import unittest

from PIL import Image
import panorama_io as P
from grado_connectors import yandex_panorama as Y


def meta():
    return {"imageId":"grid","panoramaId":"grid","origin":20,"tileWidth":256,"tileHeight":256,
            "levels":[{"level":0,"width":2048,"height":1024}]}


class ProjectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        img=Image.new("RGB",(2048,1024))
        img.putdata([(round(x/2047*255),round(y/1023*255),128) for y in range(1024) for x in range(2048)])
        cls.tiles={}
        for x in range(8):
            for y in range(4):
                out=io.BytesIO();img.crop((x*256,y*256,(x+1)*256,(y+1)*256)).save(out,"JPEG",quality=98)
                cls.tiles[(x,y)]=out.getvalue()
        img.close()

    def test_direction_advances_quarter_panorama(self):
        a=P.plan(meta(),20,200,120);b=P.plan(meta(),110,200,120)
        self.assertAlmostEqual(b["uv"](100,60)[0]-a["uv"](100,60)[0],2048/4)
        self.assertEqual(a["uv"](100,60)[1],512)

    def test_rendered_center_has_known_source_direction(self):
        fp=P.plan(meta(),200,200,120)
        raw=P.project_frame(meta(),fp,self.tiles)
        with Image.open(io.BytesIO(raw)) as im:
            self.assertEqual(im.size,(200,120))
            r,g,b=im.getpixel((100,60))
            self.assertAlmostEqual(r,128,delta=3);self.assertAlmostEqual(g,128,delta=3);self.assertAlmostEqual(b,128,delta=3)

    def test_seam_uses_both_ends_without_black_padding(self):
        fp=P.plan(meta(),20,200,120)
        raw=P.project_frame(meta(),fp,self.tiles)
        with Image.open(io.BytesIO(raw)) as im:
            self.assertGreater(im.getpixel((70,60))[0],220)
            self.assertLess(im.getpixel((130,60))[0],40)
            for x in (0,70,100,130,199):self.assertAlmostEqual(im.getpixel((x,60))[2],128,delta=15)

    def test_incomplete_frame_is_not_returned(self):
        fp=P.plan(meta(),180,200,120)
        tiles={k:self.tiles[k] for k in fp["keys"][1:]}
        with self.assertRaises(Y.PanoramaError) as e:P.project_frame(meta(),fp,tiles)
        self.assertEqual(e.exception.code,"tile_missing")

    def test_resolution_and_cancellation_are_explicit(self):
        with self.assertRaises(Y.PanoramaError) as e:P.plan(meta(),180)
        self.assertEqual(e.exception.code,"insufficient_resolution")
        cancel=threading.Event();cancel.set()
        with self.assertRaises(Y.PanoramaError) as e:P.plan(meta(),180,200,120,cancel=cancel)
        self.assertEqual(e.exception.code,"cancelled")
        with self.assertRaises(Y.PanoramaError) as e:P.plan(meta(),180,200,120,deadline=time.monotonic()-1)
        self.assertEqual(e.exception.code,"timeout")
