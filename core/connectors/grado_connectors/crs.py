"""Трансформации СК без PROJ (для эталонной реализации).

Москва: МСК (как в QGIS, MSK_PROJ4 — то, что видит и вводит пользователь) и система ГИС ОГД (Бессель со смещением,
OGD_PROJ4 — родные координаты выгрузок портала); МСК = ОГД − OGD_SHIFT.

Реализовано: EPSG:3857 → EPSG:4326 (сферическая модель, точная),
EPSG:4326 → EPSG:32637 (Transverse Mercator, ряды Снайдера, точность ~мм;
сверено с PROJ 8 из комплекта QGIS-LTR) и МСК-50 → WGS84 для выгрузок ГИС ОГД
Москвы (эллипсоид Бесселя + 7-параметрический сдвиг Хельмерта). Основной путь
SHP в сервисе — ogr2ogr; msk50_to_wgs84 — фолбэк без GDAL (сверено с PROJ,
расхождение < 1 мм). Параметры МСК-50 — константой OGD_PROJ4.
"""

import math

# Две местные системы Москвы — один датум (Бессель + тот же towgs84), разный сдвиг начала:
#   • система ГИС ОГД (Бессель со смещением) — в ней лежат родные координаты выгрузок портала (SHP «Moscow_bessel»);
#     параметры — из работающего GRADO-плагина владельца (config.py, OGD_PROJ4). НЕ менять.
#   • МСК (как в QGIS) — пользовательская СК «МСК» из QGIS владельца: то же без +x_0/+y_0. В ней пользователь видит и
#     вводит координаты, в ней DXF и листы. МСК = ОГД − OGD_SHIFT точно (датум общий; сверено pyproj во всей Москве).
OGD_PROJ4 = (
    "+proj=tmerc +lat_0=55.66666666667 +lon_0=37.5 +k=1 "
    "+x_0=16.098 +y_0=14.512 +ellps=bessel "
    "+towgs84=316.151,78.924,589.650,-1.57273,2.69209,2.34693,8.4507 "
    "+units=m +no_defs"
)
MSK_PROJ4 = (
    "+proj=tmerc +lat_0=55.66666666667 +lon_0=37.5 +k=1 +x_0=0 +y_0=0 +ellps=bessel "
    "+towgs84=316.151,78.924,589.65,-1.57273,2.69209,2.34693,8.4507 +units=m +no_defs"
)
OGD_SHIFT = (16.098, 14.512)     # система ГИС ОГД − МСК, метры (false easting/northing OGD_PROJ4)

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


def wgs84_to_merc(lon, lat):
    return math.radians(lon) * _R, math.asinh(math.tan(math.radians(lat))) * _R


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


def utm37n_to_wgs84(x, y):
    """Обратный ряд Снайдера для UTM 37N. Сверено с PROJ (см. тесты)."""
    e1 = (1 - math.sqrt(1 - _E2)) / (1 + math.sqrt(1 - _E2))
    m = y / _K0
    mu = m / (_A * (1 - _E2 / 4 - 3 * _E2 ** 2 / 64 - 5 * _E2 ** 3 / 256))

    phi1 = (mu
            + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
            + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))

    sin_phi1, cos_phi1, tan_phi1 = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    c1 = _EP2 * cos_phi1 ** 2
    t1 = tan_phi1 ** 2
    n1 = _A / math.sqrt(1 - _E2 * sin_phi1 ** 2)
    r1 = _A * (1 - _E2) / (1 - _E2 * sin_phi1 ** 2) ** 1.5
    d = (x - _FE) / (n1 * _K0)

    phi = phi1 - (n1 * tan_phi1 / r1) * (
        d ** 2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * _EP2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * _EP2 - 3 * c1 ** 2) * d ** 6 / 720)
    lam = _LON0 + (
        d
        - (1 + 2 * t1 + c1) * d ** 3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * _EP2 + 24 * t1 ** 2) * d ** 5 / 120
    ) / cos_phi1
    return math.degrees(lam), math.degrees(phi)


def merc_to_utm37n(x, y):
    return wgs84_to_utm37n(*merc_to_wgs84(x, y))


# Точка (0,0) локальных метров студии = UTM(413000, 6178000) = ORIGIN
# в core/model/grado_model/project.py и apps/studio/studio_core.py.
# Долгота/широта нужны для перевода холста в тайлы XYZ (apps/studio).
ORIGIN_LON, ORIGIN_LAT = utm37n_to_wgs84(413000.0, 6178000.0)


# --- МСК-50 → WGS84 без PROJ (фолбэк, когда нет ogr2ogr/GDAL) ---------------
# Параметры — из OGD_PROJ4 выше (единственный источник истины). Цепочка:
# обратный Transverse Mercator на эллипсоиде Бесселя → геоцентрика Бесселя →
# 7-параметрический Хельмерт (Position Vector — как +towgs84 в PROJ) → WGS84.
# Сверено с ogr2ogr на реальных точках выгрузки (см. тесты, расхождение < 1 м).
_B_A = 6377397.155                   # Bessel 1841
_B_F = 1 / 299.1528128
_B_E2 = _B_F * (2 - _B_F)
_B_EP2 = _B_E2 / (1 - _B_E2)
_MSK_LAT0 = math.radians(55.66666666667)
_MSK_LON0 = math.radians(37.5)
_MSK_K0 = 1.0
_MSK_X0 = 16.098                      # false easting
_MSK_Y0 = 14.512                      # false northing
# towgs84: dx,dy,dz (м), rx,ry,rz (угл. сек), s (ppm)
_TW_D = (316.151, 78.924, 589.650)
_TW_R = tuple(math.radians(v / 3600.0) for v in (-1.57273, 2.69209, 2.34693))
_TW_S = 8.4507e-6


def _meridian_arc(phi, a, e2):
    return a * (
        (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * phi
        - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * math.sin(2 * phi)
        + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * math.sin(4 * phi)
        - (35 * e2 ** 3 / 3072) * math.sin(6 * phi))


def msk50_to_wgs84(east, north):
    """(easting, northing) в системе ГИС ОГД (Бессель со смещением, OGD_PROJ4) → (lon, lat) WGS84, градусы.
    Имя историческое: это НЕ рабочая МСК пользователя — для неё msk_to_wgs84."""
    a, e2, ep2 = _B_A, _B_E2, _B_EP2
    # обратный TM (ряды Снайдера) → широта/долгота на датуме Бесселя
    m0 = _meridian_arc(_MSK_LAT0, a, e2)
    m = m0 + (north - _MSK_Y0) / _MSK_K0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    phi1 = (mu
            + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
            + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    sp, cp, tp = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    c1 = ep2 * cp ** 2
    t1 = tp ** 2
    n1 = a / math.sqrt(1 - e2 * sp ** 2)
    r1 = a * (1 - e2) / (1 - e2 * sp ** 2) ** 1.5
    d = (east - _MSK_X0) / (n1 * _MSK_K0)
    phi = phi1 - (n1 * tp / r1) * (
        d ** 2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720)
    lam = _MSK_LON0 + (
        d - (1 + 2 * t1 + c1) * d ** 3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120
    ) / cp
    # геодезические (Бессель) → геоцентрика → Хельмерт → геодезические (WGS84)
    sinp, cosp, sinl, cosl = math.sin(phi), math.cos(phi), math.sin(lam), math.cos(lam)
    nn = a / math.sqrt(1 - e2 * sinp ** 2)
    x = nn * cosp * cosl
    y = nn * cosp * sinl
    z = nn * (1 - e2) * sinp
    dx, dy, dz = _TW_D
    rx, ry, rz = _TW_R
    ms = 1 + _TW_S
    xo = ms * (x - rz * y + ry * z) + dx          # Position Vector (PROJ towgs84)
    yo = ms * (rz * x + y - rx * z) + dy
    zo = ms * (-ry * x + rx * y + z) + dz
    # геоцентрика WGS84 → геодезические (Bowring)
    aw, e2w = _A, _E2
    bw = aw * math.sqrt(1 - e2w)
    ep2w = e2w / (1 - e2w)
    p = math.hypot(xo, yo)
    th = math.atan2(zo * aw, p * bw)
    lat = math.atan2(zo + ep2w * bw * math.sin(th) ** 3,
                     p - e2w * aw * math.cos(th) ** 3)
    lon = math.atan2(yo, xo)
    return math.degrees(lon), math.degrees(lat)


def wgs84_to_msk50(lon, lat):
    """(lon, lat) WGS84 → (easting, northing) в системе ГИС ОГД (Бессель со смещением, OGD_PROJ4).

    Inverse of msk50_to_wgs84 by Newton iterations: the forward chain is written once,
    and the round trip stays consistent to millimetres."""
    kx = 111320.0 * math.cos(math.radians(lat))
    e = (lon - math.degrees(_MSK_LON0)) * kx + _MSK_X0
    n = (lat - math.degrees(_MSK_LAT0)) * 110540.0 + _MSK_Y0
    for _ in range(6):
        lo, la = msk50_to_wgs84(e, n)
        e -= (lo - lon) * kx
        n -= (la - lat) * 110540.0
        if abs(lo - lon) < 1e-11 and abs(la - lat) < 1e-11:
            break
    return e, n


def msk_to_wgs84(x, y):
    """(X восток, Y север) в МСК (как в QGIS, MSK_PROJ4) → (lon, lat) WGS84. Через систему ГИС ОГД и сдвиг: формулы одни."""
    return msk50_to_wgs84(x + OGD_SHIFT[0], y + OGD_SHIFT[1])


def wgs84_to_msk(lon, lat):
    """(lon, lat) WGS84 → (X восток, Y север) в МСК (как в QGIS, MSK_PROJ4)."""
    e, n = wgs84_to_msk50(lon, lat)
    return e - OGD_SHIFT[0], n - OGD_SHIFT[1]


def ogd_to_msk(x, y):
    """Родные координаты ГИС ОГД → МСК: сдвиг, без пересчёта через градусы."""
    return x - OGD_SHIFT[0], y - OGD_SHIFT[1]


def transform_geom(geom, fn):
    """Применяет fn(x, y) -> (x, y) ко всем координатам геометрии."""

    def walk(coords, depth):
        if depth == 0:
            return list(fn(coords[0], coords[1]))
        return [walk(c, depth - 1) for c in coords]

    depth = {"Point": 0, "LineString": 1, "MultiPoint": 1,
             "Polygon": 2, "MultiLineString": 2, "MultiPolygon": 3}[geom["type"]]
    return {"type": geom["type"], "coordinates": walk(geom["coordinates"], depth)}
