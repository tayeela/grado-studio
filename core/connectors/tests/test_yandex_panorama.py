"""Проверяет прямой протокол панорам, отсутствие произвольных URL и остановку 429/timeout.

Запуск: python -m pytest core/connectors/tests/test_yandex_panorama.py.
"""
import asyncio
import copy
import io
import time
import unittest
from unittest.mock import patch

import httpx
from PIL import Image
from grado_connectors import netutil
from grado_connectors import yandex_panorama as Y


def payload():
    return {"status":"success","data":{"Data":{"panoramaId":"test-pano","Point":{"coordinates":[37.62,55.75,0]},
            "EquirectangularProjection":{"Origin":[20,0]},"Images":{"imageId":"test_image",
            "Tiles":{"width":256,"height":256},"Zooms":[{"level":0,"width":2048,"height":1024}]}}}}


class ProtocolTest(unittest.TestCase):
    def test_metadata_and_overlay_independence(self):
        p = payload();p["data"]["Annotation"]={"Markers":[{"name":"интерфейс"}]}
        meta=Y.parse_metadata(p)
        self.assertEqual(meta["point"],[37.62,55.75])
        self.assertEqual(meta["origin"],20)
        self.assertNotIn("Annotation",meta)
        self.assertIsNone(meta["takenAt"])

    def test_no_panorama_and_unknown_projection_differ(self):
        with self.assertRaises(Y.PanoramaError) as e:
            Y.parse_metadata({"status":"error","code":404})
        self.assertEqual(e.exception.code,"no_panorama")
        p=payload();p["data"]["Data"]["EquirectangularProjection"]["Origin"][1]=10
        with self.assertRaises(Y.PanoramaError) as e:Y.parse_metadata(p)
        self.assertEqual(e.exception.code,"unsupported_projection")

    def test_unknown_schema_and_invalid_image_id(self):
        for p in ({},[],{"status":"success","data":{}}):
            with self.subTest(p=p),self.assertRaises(Y.PanoramaError):Y.parse_metadata(p)
        p=payload();p["data"]["Data"]["Images"]["imageId"]="../elsewhere"
        with self.assertRaises(Y.PanoramaError):Y.parse_metadata(p)

    def test_tile_url_has_fixed_origin_and_bounded_indices(self):
        m=Y.parse_metadata(payload())
        self.assertEqual(Y.tile_url(m,0,7,3),"https://pano.maps.yandex.net/test_image/0.7.3")
        for lv,x,y in [(1,0,0),(0,8,0),(0,0,-1),(0,True,0)]:
            with self.assertRaises(Y.PanoramaError):Y.tile_url(m,lv,x,y)

    def test_jpeg_body_and_size_are_verified(self):
        out=io.BytesIO();Image.new("RGB",(256,256)).save(out,"JPEG")
        Y.check_jpeg(out.getvalue(),256,256)
        for body in (b"<html>captcha</html>",out.getvalue()[:40]):
            with self.assertRaises(Y.PanoramaError):Y.check_jpeg(body,256,256)
        with self.assertRaises(Y.PanoramaError):Y.check_jpeg(out.getvalue(),128,128)


class AsyncNetworkTest(unittest.IsolatedAsyncioTestCase):
    async def test_first_429_is_not_retried(self):
        calls=[]
        async def handler(r):
            calls.append(r.url)
            return httpx.Response(429,headers={"Retry-After":"60"})
        with patch.object(netutil,"TRANSPORT",httpx.MockTransport(handler)),patch.object(netutil,"PORTAL_POLICY",None):
            with self.assertRaises(netutil.RateLimited):
                await Y.metadata(37.62,55.75,deadline=time.monotonic()+1)
        self.assertEqual(len(calls),1)

    async def test_total_deadline_cancels_inflight_operation(self):
        closed=[]
        async def handler(r):
            try:
                await asyncio.sleep(30)
                return httpx.Response(200,content=b"late")
            finally:closed.append(True)
        started=time.monotonic()
        with patch.object(netutil,"TRANSPORT",httpx.MockTransport(handler)):
            with self.assertRaises(TimeoutError):
                await netutil.arequest("https://example.test/",deadline=started+.03)
        self.assertLess(time.monotonic()-started,.5)
        self.assertEqual(closed,[True])
