"""Скачивает метаданные и JPEG-тайлы панорам Яндекса напрямую, без плеера и интерфейса.

Вызывается panorama_io через общий netutil и Gate. Чужие URL не принимаются.
Проверки: tests/test_yandex_panorama.py; протокол streetlevel/yandex, commit 9163821.
"""
from __future__ import annotations

import io
import math
import re
from urllib.parse import urlencode

from PIL import Image, UnidentifiedImageError

from . import netutil
from .contract import ConnectorError

METADATA_URL = "https://api-maps.yandex.ru/services/panoramas/1.x/"
TILE_ORIGIN = "https://pano.maps.yandex.net/"
HEADERS = {"User-Agent": "Grado/2", "Referer": "https://yandex.ru/maps/"}
IMAGE_ID = re.compile(r"[A-Za-z0-9_-]{1,200}\Z")


class PanoramaError(ConnectorError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def parse_metadata(payload):
    if not isinstance(payload, dict):
        raise PanoramaError("metadata_unconfirmed", "Неизвестный ответ метаданных панорамы")
    if payload.get("status") == "error" and payload.get("code") == 404:
        raise PanoramaError("no_panorama", "В этой точке панорама не найдена")
    try:
        if payload.get("status") != "success":
            raise ValueError()
        data = payload["data"]["Data"]
        point = data["Point"]["coordinates"][:2]
        origin = data["EquirectangularProjection"]["Origin"]
        images = data["Images"]
        image_id = images["imageId"]
        tile = images["Tiles"]
        levels = images["Zooms"]
        pid = data["panoramaId"]
        if not isinstance(pid, str) or not pid or len(pid) > 300 or not IMAGE_ID.fullmatch(image_id):
            raise ValueError()
        if not all(_number(x) for x in point + origin) or len(point) != 2 or len(origin) != 2:
            raise ValueError()
        if not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90):
            raise ValueError()
        if origin[1] != 0:
            raise PanoramaError("unsupported_projection", "Вертикальная проекция источника не поддерживается")
        for dim in ("width", "height"):
            if type(tile[dim]) is not int or not 1 <= tile[dim] <= 1024:
                raise ValueError()
        if not isinstance(levels, list) or not 1 <= len(levels) <= 16:
            raise ValueError()
        seen = set()
        for lv in levels:
            if not all(type(lv[k]) is int for k in ("level", "width", "height")):
                raise ValueError()
            if not (0 <= lv["level"] <= 30 and 2 <= lv["width"] <= 32768 and lv["width"] == 2 * lv["height"]):
                raise PanoramaError("unsupported_projection", "Ожидается сферическая развёртка 2:1")
            if lv["level"] in seen:
                raise ValueError()
            seen.add(lv["level"])
        return {"panoramaId": pid, "imageId": image_id, "point": point,
                "origin": origin[0] % 360, "tileWidth": tile["width"], "tileHeight": tile["height"],
                "levels": levels, "takenAt": None}
    except PanoramaError:
        raise
    except (KeyError, ValueError, TypeError, AttributeError):
        raise PanoramaError("metadata_unconfirmed", "Неизвестная схема метаданных панорамы") from None


def tile_url(meta, level, x, y):
    if not IMAGE_ID.fullmatch(str(meta.get("imageId") or "")):
        raise PanoramaError("metadata_unconfirmed", "Недопустимый идентификатор изображения")
    lv = next((v for v in meta.get("levels", []) if v["level"] == level), None)
    if lv is None or type(x) is not int or type(y) is not int:
        raise PanoramaError("metadata_unconfirmed", "Неизвестный уровень или индекс тайла")
    if not (0 <= x < math.ceil(lv["width"] / meta["tileWidth"]) and
            0 <= y < math.ceil(lv["height"] / meta["tileHeight"])):
        raise PanoramaError("metadata_unconfirmed", "Тайл находится вне изображения")
    return f"{TILE_ORIGIN}{meta['imageId']}/{level}.{x}.{y}"


def check_jpeg(body, width, height):
    try:
        with Image.open(io.BytesIO(body)) as image:
            if image.format != "JPEG" or image.size != (width, height):
                raise ValueError()
            image.load()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        raise PanoramaError("tile_missing", "Получен повреждённый JPEG-тайл") from None


async def metadata(lon, lat, *, deadline, cancel=None):
    if not all(_number(x) for x in (lon, lat)) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise PanoramaError("invalid_input", "Координаты должны быть в WGS84")
    query = urlencode({"l": "stv", "lang": "ru_RU", "ll": f"{lon:.10f},{lat:.10f}",
                       "origin": "userAction", "provider": "streetview"})
    response = await netutil.arequest(METADATA_URL + "?" + query, headers=HEADERS, deadline=deadline,
                                     cancel=cancel, portal="yandex", limit=2 * 2**20)
    try:
        payload = response.json()
    except (ValueError, UnicodeError):
        raise PanoramaError("source_unavailable", "Источник вернул страницу вместо метаданных панорамы") from None
    return parse_metadata(payload)


async def tile(meta, level, x, y, *, deadline, cancel=None):
    url = tile_url(meta, level, x, y)
    response = await netutil.arequest(url, headers=HEADERS, deadline=deadline, cancel=cancel,
                                     portal="yandex", limit=4 * 2**20)
    check_jpeg(response.content, meta["tileWidth"], meta["tileHeight"])
    return response.content
