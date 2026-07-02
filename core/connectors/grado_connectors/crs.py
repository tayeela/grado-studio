"""Трансформации СК без PROJ (для эталонной реализации).

Реализовано: EPSG:3857 → EPSG:4326 (сферическая модель, точная) и
EPSG:4326 → EPSG:32637 (Transverse Mercator, ряды Снайдера, точность ~мм;
сверено с PROJ 8 из комплекта QGIS-LTR). МСК-50 для выгрузок ГИС ОГД Москвы
(эллипсоид Бесселя + 7-параметрический сдвиг) пересчитывается через PROJ —
в сервисе данных это ogr2ogr; здесь параметры объявлены константой.
"""

import math

# МСК-50 (система координат выгрузок ГИС ОГД Москвы) — параметры из
# работающего GRADO-плагина.
OGD_PROJ4 = (
    "+proj=tmerc +lat_0=55.66666666667 +lon_0=37.5 +k=1 "
    "+x_0=16.098 +y_0=14.512 +ellps=bessel "
    "+towgs84=316.151,78.924,589.650,-1.57273,2.69209,2.34693,8.4507 "
    "+units=m +no_defs"
)

_R = 6378137.0                       # сфера Web Mercator
_A = 6378137.0                       # WGS84
_F = 1 / 298.257223563
_E2 = _F * (2 - _F)
_EP2 = _E2 / (1 - _E2)
_K0 = 0.9996
_LON0 = math.radians(39.0)           # осевой меридиан зоны 37
_FE = 500000.0


def merc_to_wgs84(x, y):
    return math.degrees(x / _R), math.degrees(math.atan(math.sinh(y / _R)))


def wgs84_to_utm37n(lon, lat):
    phi = math.radians(lat)
    lam = math.radians(lon)
    sin_phi, cos_phi, tan_phi = math.sin(phi), math.cos(phi), math.tan(phi)

    n = _A / math.sqrt(1 - _E2 * sin_phi ** 2)
    t = tan_phi ** 2
    c = _EP2 * cos_phi ** 2
    a = (lam - _LON0) * cos_phi

    m = _A * (
        (1 - _E2 / 4 - 3 * _E2 ** 2 / 64 - 5 * _E2 ** 3 / 256) * phi
        - (3 * _E2 / 8 + 3 * _E2 ** 2 / 32 + 45 * _E2 ** 3 / 1024) * math.sin(2 * phi)
        + (15 * _E2 ** 2 / 256 + 45 * _E2 ** 3 / 1024) * math.sin(4 * phi)
        - (35 * _E2 ** 3 / 3072) * math.sin(6 * phi))

    x = _K0 * n * (a + (1 - t + c) * a ** 3 / 6
                   + (5 - 18 * t + t ** 2 + 72 * c - 58 * _EP2) * a ** 5 / 120) + _FE
    y = _K0 * (m + n * tan_phi * (a ** 2 / 2
               + (5 - t + 9 * c + 4 * c ** 2) * a ** 4 / 24
               + (61 - 58 * t + t ** 2 + 600 * c - 330 * _EP2) * a ** 6 / 720))
    return x, y


def merc_to_utm37n(x, y):
    return wgs84_to_utm37n(*merc_to_wgs84(x, y))


def transform_geom(geom, fn):
    """Применяет fn(x, y) -> (x, y) ко всем координатам геометрии."""

    def walk(coords, depth):
        if depth == 0:
            return list(fn(coords[0], coords[1]))
        return [walk(c, depth - 1) for c in coords]

    depth = {"Point": 0, "LineString": 1, "MultiPoint": 1,
             "Polygon": 2, "MultiLineString": 2, "MultiPolygon": 3}[geom["type"]]
    return {"type": geom["type"], "coordinates": walk(geom["coordinates"], depth)}
