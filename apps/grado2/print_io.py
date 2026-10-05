"""Листы и альбом ГРАДО 2: PDF, SVG и PPTX через рендер и вёрстку ядра (core/render, core/layout).

Клиент присылает для каждого листа уже оформленные объекты — так лист повторяет карту на экране (стиль
считает тот же код, что рисует слои). Здесь: пересчёт WGS84 → МСК (метры, как в QGIS и в DXF), масштаб листа,
заливки с прозрачностью (смешение с белым: в PDF-писателе ядра альфы нет), штриховки, типы линий REDLN97
(шаблоны LIN и формы SHX — те же данные, что у экрана), легенда, таблица ТЭП, стрелка севера, масштабная
линейка, рамка и основная надпись по ГОСТ Р 21.101 (рамка и штамп — фреймы ядра).
"""

import base64
import math
import os
import time
from pathlib import Path

from grado_connectors import crs
from grado_layout import A1_LANDSCAPE, A3_LANDSCAPE, Document, Page, PageBorder, StampFrame, TableFrame
from grado_layout.compose import document_pages_ops
from grado_layout.model import Frame
from grado_render import PdfBackend, hex_to_rgb, render_svg
from grado_render.scene import hatch_ops

# слайды презентации: P — 16:9 (13,33 × 7,5 дюйма), PA4/PA3/PA2 — альбомные листы А4, А3, А2 с тем же оформлением
SLIDES = {"P": (338.67, 190.5), "PA4": (297, 210), "PA3": (420, 297), "PA2": (594, 420)}
# листы без штампа (инструмент «Лист» на карте): карта на весь лист, поля по 2 % — пропорции бумаги сохраняются;
# ориентация — поле листа orient ("P" книжная)
PAPER = {"BA4": (297, 210), "BA3": (420, 297), "BA2": (594, 420), "BA1": (841, 594), "BA0": (1189, 841)}
PAPER_MARGIN = 0.02
SIZES = {"A3": A3_LANDSCAPE, "A1": A1_LANDSCAPE, **SLIDES, **PAPER}


def page_size(size, orient=None):
    w, h = SIZES[size]
    return (h, w) if size in PAPER and orient == "P" else (w, h)


class PaperFrame(Frame):
    """Оформление листа без штампа: тонкая рамка карты и подпись в правом нижнем углу («название · М 1:…»)."""

    def __init__(self, rect, sheet):
        super().__init__(rect)
        self.sheet = sheet

    def ops(self, ctx):
        x, y, w, h = self.rect
        sh, ink = self.sheet, (0.1, 0.1, 0.1)
        border = {"op": "path", "rings": [[(x, y), (x + w, y), (x + w, y + h), (x, y + h)]], "closed": True, "fill": None, "stroke": ink, "width": 0.35, "dash": None}
        if sh.get("kind") == "situation":                       # ситуационный план — картинка для вставки в документ: только рамка
            return [border]
        text = " · ".join(v for v in (sh.get("title") or "", f"М 1:{int(round(sh['scale'])):,}".replace(",", " ")) if v)
        size = max(2.6, min(w, h) / 90)
        tw = len(text) * size * 0.55 + size * 1.6
        bx, by = x + w - tw - size * 0.6, y + h - size * 2.2 - size * 0.6
        return [{"op": "path", "rings": [[(x, y), (x + w, y), (x + w, y + h), (x, y + h)]], "closed": True, "fill": None, "stroke": ink, "width": 0.35, "dash": None},
                {"op": "path", "rings": [[(bx, by), (bx + tw, by), (bx + tw, by + size * 2.2), (bx, by + size * 2.2)]], "closed": True, "fill": (1, 1, 1), "stroke": ink, "width": 0.25, "dash": None},
                {"op": "text", "x": bx + size * 0.8, "y": by + size * 1.5, "size": size, "text": text, "color": ink}]
COLUMN = {"A3": 110, "A1": 170}             # правая колонка: легенда и ТЭП


def slide_k(size):
    """Во сколько раз оформление слайда (поля, заголовок, шапка) крупнее, чем на 16:9: растёт с шириной листа."""
    return SLIDES[size][0] / SLIDES["P"][0]
PX_MM = 0.26                                 # толщина с экрана (пиксели 96 dpi) → мм листа


def layout(size):
    """Прямоугольники листа (мм): карта, колонка легенды. Карта кончается над штампом (185×55); у слайда
    презентации штампа нет — сверху заголовок со стрелкой и шапка проекта, снизу номер слайда."""
    w, h = SIZES[size]
    if size in PAPER:
        return (w * PAPER_MARGIN, h * PAPER_MARGIN, w * (1 - 2 * PAPER_MARGIN), h * (1 - 2 * PAPER_MARGIN)), None
    if size in SLIDES:
        k, col = slide_k(size), (80 if w < 500 else 110)
        return (14 * k, 24 * k, w - 14 * k - col - 6, h - 34 * k), (w - col - 4, 24 * k, col - 4, h - 34 * k)
    col = COLUMN[size]
    map_rect = (25, 10, w - 5 - col - 25 - 5, h - 5 - StampFrame.H - 10 - 3)
    col_rect = (w - 5 - col, 10, col - 5, h - 5 - StampFrame.H - 10 - 3)
    return map_rect, col_rect


def _mix(hexc, alpha):
    """Цвет с прозрачностью поверх белого листа."""
    c = hex_to_rgb(hexc)
    if c is None:
        return None
    a = max(0.0, min(1.0, 1.0 if alpha is None else alpha))
    return tuple(1 - a * (1 - v) for v in c)


def _nice(v):
    e = 10 ** math.floor(math.log10(v))
    return min((m * e for m in (1, 2, 5, 10)), key=lambda x: abs(x - v))


class MapTransform:
    """WGS84 → МСК → мм листа. Точный пересчёт (итерации Ньютона) делается в центре листа, дальше — его разложение
    до второго порядка (якобиан и кривизна): на листе А1 1:25 000 (16 × 13 км) расхождение с точным пересчётом —
    сантиметры на местности, а лист собирается в сотни раз быстрее, чем пересчёт каждой вершины."""

    def __init__(self, rect, center_lonlat, scale):
        self.rect = rect
        self.k = 1000.0 / scale                                      # мм листа на метр
        lon0, lat0 = self.lon0, self.lat0 = center_lonlat
        f = lambda dl, dp: crs.wgs84_to_msk(lon0 + dl, lat0 + dp)
        self.cx, self.cy = f(0, 0)
        d = 0.02                                                     # шаг разностей, градусы (~1,5–2 км)
        e, w, n, s_, ne, nw, se, sw = f(d, 0), f(-d, 0), f(0, d), f(0, -d), f(d, d), f(-d, d), f(d, -d), f(-d, -d)
        c = (self.cx, self.cy)
        # по каждой координате: первые производные по долготе и широте, вторые (ll, lp, pp) — центральные разности
        self.t = [((e[i] - w[i]) / (2 * d), (n[i] - s_[i]) / (2 * d),
                   (e[i] - 2 * c[i] + w[i]) / d ** 2, (ne[i] - nw[i] - se[i] + sw[i]) / (4 * d * d), (n[i] - 2 * c[i] + s_[i]) / d ** 2)
                  for i in (0, 1)]

    def mm(self, lon, lat):
        dl, dp = lon - self.lon0, lat - self.lat0
        (a, b, aa, ab, bb), (c, e, cc, ce, ee) = self.t
        x = a * dl + b * dp + .5 * aa * dl * dl + ab * dl * dp + .5 * bb * dp * dp
        y = c * dl + e * dp + .5 * cc * dl * dl + ce * dl * dp + .5 * ee * dp * dp
        fx, fy, fw, fh = self.rect
        return (fx + fw / 2 + x * self.k, fy + fh / 2 - y * self.k)


def _simplify(pts, tol):
    """Упрощение ломаной (Дуглас — Пекер) до допуска tol мм листа: подробный контур леса или реки на мелкой схеме
    весит в PDF в десятки раз больше, чем видно глазу."""
    if len(pts) < 4:
        return pts
    x0, y0 = pts[0]
    if math.hypot(pts[-1][0] - x0, pts[-1][1] - y0) < 1e-9:
        # замкнутое кольцо: концы совпадают, отрезка-основы нет — делим кольцо по самой дальней от начала точке
        m = max(range(len(pts)), key=lambda i: (pts[i][0] - x0) ** 2 + (pts[i][1] - y0) ** 2)
        return _simplify(pts[:m + 1], tol)[:-1] + _simplify(pts[m:], tol)
    keep, stack = [0, len(pts) - 1], [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        (x1, y1), (x2, y2) = pts[i], pts[j]
        dx, dy = x2 - x1, y2 - y1
        L = math.hypot(dx, dy) or 1e-9
        best, bi = 0.0, None
        for k in range(i + 1, j):
            d = abs(dy * (pts[k][0] - x1) - dx * (pts[k][1] - y1)) / L
            if d > best:
                best, bi = d, k
        if bi is not None and best > tol:
            keep.append(bi)
            stack += [(i, bi), (bi, j)]
    return [pts[k] for k in sorted(keep)]


# Картооснова ЕГКО внутри округа (правая схема «Месторасположения» шаблона ППТ КРТ): цвета — как в шаблоне
EGKO_BASE = (("forest", "#c5dcb0", None), ("gazons", "#c5dcb0", None), ("hidrograf", "#a9cfe5", None),
             ("dorogi_pol", "#ffffff", "#d7d7d7"), ("virtual6", "#cdcdcd", None))


def egko_ops(tr, rect, mask, egko):
    """Цветная основа ЕГКО только внутри контура mask (GeoJSON округа): светлый фон, леса и газоны, вода, дороги,
    здания. Снаружи остаётся бледная подложка. Здания мельче 0,3 мм на листе пропускаются, контуры упрощаются до
    0,12 мм — схема округа в масштабе 1:100 000–1:250 000 иначе весила бы десятки мегабайт."""
    kind, parts = _parts(mask)
    rings = [[tr.mm(*p[:2]) for p in r] for poly in parts for r in poly]
    if not rings:
        return []
    out = [{"op": "clip", "rings": rings},
           {"op": "path", "rings": rings, "closed": True, "fill": hex_to_rgb("#f3f3f1"), "stroke": None, "width": 0, "dash": None}]
    # охват маски в градусах — для выборки ЕГКО из кэша
    lons = [p[0] for poly in parts for r in poly for p in r]
    lats = [p[1] for poly in parts for r in poly for p in r]
    bbox = (min(lons), min(lats), max(lons), max(lats))
    small = 0.3 / tr.k                                                  # 0,3 мм листа в метрах
    kx = 111320 * math.cos(math.radians((bbox[1] + bbox[3]) / 2))
    for code, fill, edge in EGKO_BASE:
        try:
            feats = egko(bbox, code)
        except Exception:                                               # ЕГКО не отдала слой — схема без него
            continue
        for f in feats:
            if not (f.get("geometry") or {}).get("coordinates"):
                continue
            _, fparts = _parts(f["geometry"])
            for poly in fparts:
                if not poly or len(poly[0]) < 3:
                    continue
                if code == "virtual6":
                    lo = [p[0] for p in poly[0]]
                    la = [p[1] for p in poly[0]]
                    if (max(lo) - min(lo)) * kx < small and (max(la) - min(la)) * 110540 < small:
                        continue
                prs = [r for r in (_simplify([tr.mm(*p[:2]) for p in ring], 0.12) for ring in poly) if len(r) >= 3]
                if prs:
                    out.append({"op": "path", "rings": prs, "closed": True, "fill": hex_to_rgb(fill),
                                "stroke": hex_to_rgb(edge) if edge else None, "width": 0.08, "dash": None})
    out.append({"op": "unclip"})
    return out


_TW_FONTS = {}


def _guillemets(text):
    """Прямые кавычки в подписях листа → «ёлочки»; нечётное число кавычек (обрезанное название) не трогаем."""
    t = str(text).replace("\u201c", '"').replace("\u201d", '"').replace("\u201e", '"')
    if '"' not in t or t.count('"') % 2:
        return t
    return "".join(("\u00ab" if i == 0 or t[i - 1] in " \u00a0([\u2014\u2013-" else "\u00bb") if c == '"' else c for i, c in enumerate(t))


STATION_MARK = "ст.\u00a0ж/д\u00a0"                                   # подпись станции начинается так (правило 15)


def _text_w(text, family, size):
    """Ширина строки в мм тем шрифтом, которым её напечатает PDF (для рамки подписи и проверки «целиком в рамке»)."""
    family = family or "ui"
    if family not in _TW_FONTS:
        try:
            from grado_render import Font, find_font
            _TW_FONTS[family] = Font(find_font(family))
        except Exception:
            _TW_FONTS[family] = None
    font = _TW_FONTS[family]
    return font.text_width(str(text), size) if font else size * .6 * len(str(text))


def _straight_runs(pts, junction, tol=0.6):
    """Прямые участки ломаной (мм листа): подряд идущие вершины, отклонение которых от хорды не больше tol, без
    перекрёстка внутри участка. Возвращает (длина, середина x, середина y, угол) каждого участка."""
    out, i, n = [], 0, len(pts)
    while i < n - 1:
        j = i + 1
        while j + 1 < n and not junction[j]:
            (x0, y0), (x1, y1) = pts[i], pts[j + 1]
            L = math.hypot(x1 - x0, y1 - y0) or 1e-9
            if max(abs((y1 - y0) * (pts[k][0] - x0) - (x1 - x0) * (pts[k][1] - y0)) / L for k in range(i + 1, j + 1)) > tol:
                break
            j += 1
        (x0, y0), (x1, y1) = pts[i], pts[j]
        out.append((math.hypot(x1 - x0, y1 - y0), (x0 + x1) / 2, (y0 + y1) / 2, math.atan2(y1 - y0, x1 - x0)))
        i = j
    return out


# Знаки подтопления из примера владельца «Хатминки» (30.09.2026), мм листа: (штрих, пробел) и места засечек в периоде
FLOOD = {64: (None, 0.9, (0.45,)), 65: ((3.0, 1.0), 4.0, (1.2, 2.0)), 66: ((2.0, 1.2), 3.2, ())}


def flood_ops(pts, code, color, width=0.35, tick=0.6, side=1):
    """Граница зоны подтопления по коду знака (64 сильное, 65 умеренное, 66 слабое): штрих и засечки длиной tick.
    side=1 — засечки справа по ходу в мм листа (ось y вниз), side=-1 — слева: для кольца против часовой в градусах
    (оно и на листе идёт против часовой) это внутрь зоны."""
    dash, period, ticks = FLOOD.get(code, FLOOD[66])
    out = [{"op": "path", "closed": False, "fill": None, "stroke": color, "width": width, "dash": list(dash) if dash else None, "rings": [pts]}]
    if not ticks:
        return out
    segs, t0 = [], 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        d = math.hypot(x1 - x0, y1 - y0)
        if d > 1e-9:
            segs.append((x0, y0, (x1 - x0) / d, (y1 - y0) / d, t0, d))
            t0 += d
    rings, k = [], 0
    while k * period < t0:
        for off in ticks:
            t = k * period + off
            if t >= t0:
                break
            x0, y0, ux, uy, s0, d = next((sg for sg in segs if sg[4] <= t <= sg[4] + sg[5]), segs[-1])
            x, y = x0 + ux * (t - s0), y0 + uy * (t - s0)
            nx, ny = -uy * side, ux * side
            rings.append([(x, y), (x + nx * tick, y + ny * tick)])
        k += 1
    if rings:
        out.append({"op": "path", "closed": False, "fill": None, "stroke": color, "width": width * .8, "dash": None, "rings": rings})
    return out


def _seg_box(p, q, box):
    """Отрезок p–q (мм) задевает прямоугольник box (x0, y0, x1, y1): отсечение Лианга — Барски."""
    (x0, y0), (x1, y1) = p, q
    dx, dy, t0, t1 = x1 - x0, y1 - y0, 0.0, 1.0
    for pp, qq in ((-dx, x0 - box[0]), (dx, box[2] - x0), (-dy, y0 - box[1]), (dy, box[3] - y0)):
        if pp == 0:
            if qq < 0:
                return False
            continue
        r = qq / pp
        if pp < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return False
    return True


def _in_ring(x, y, ring):
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


# места номера вокруг точки выноски: радиусы, мм (ближние — раньше) и направления через 15° (k × 15°, y вниз):
# сначала диагонали, потом стороны, потом промежуточные
LEAD_R = (7, 9, 11, 13, 15.5, 18, 21, 24, 28, 32, 42)
OBST_PAD = 0.7                                                      # запас подписи от железной дороги и границы района, мм
SPREAD = 4.0                                                        # точки выносок ближе этого — «кучка», разводятся (владелец 05.10.2026)
MAP_PAD = 2.5                                                       # поле подписей от края карты, мм (правило 11)
LEAD_K = (21, 15, 3, 9, 18, 6, 0, 12, 22, 20, 16, 14, 4, 2, 10, 8, 23, 19, 17, 13, 5, 1, 11, 7)


def _chains(lines, eps=0.05):
    """Линии улицы (мм), склеенные по общим концам в непрерывные цепочки."""
    ch = [list(l) for l in lines if len(l) > 1]
    merged = True
    while merged:
        merged = False
        for i in range(len(ch)):
            for j in range(i + 1, len(ch)):
                a, b = ch[i], ch[j]
                close = lambda p, q: abs(p[0] - q[0]) < eps and abs(p[1] - q[1]) < eps
                if close(a[-1], b[0]):
                    ch[i] = a + b[1:]
                elif close(a[-1], b[-1]):
                    ch[i] = a + b[::-1][1:]
                elif close(a[0], b[-1]):
                    ch[i] = b + a[1:]
                elif close(a[0], b[0]):
                    ch[i] = b[::-1] + a[1:]
                else:
                    continue
                del ch[j]
                merged = True
                break
            if merged:
                break
    return ch


def _axis_windows(chains, L, tol, step=1.0):
    """Отрезки оси длиной L (мм), на которых ось отходит от хорды не больше tol: (отклонение, x, y, угол хорды)."""
    out = []
    for pts in chains:
        cum = [0.0]
        for p, q in zip(pts, pts[1:]):
            cum.append(cum[-1] + math.hypot(q[0] - p[0], q[1] - p[1]))
        if cum[-1] < L:
            continue

        def at(s):
            i = max(0, min(len(cum) - 2, next((k for k in range(len(cum) - 1) if cum[k + 1] >= s), len(cum) - 2)))
            t = (s - cum[i]) / ((cum[i + 1] - cum[i]) or 1)
            return pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t, i
        s = 0.0
        while s + L <= cum[-1]:
            (ax, ay, i0), (bx, by, i1) = at(s), at(s + L)
            dx, dy = bx - ax, by - ay
            n = math.hypot(dx, dy) or 1
            dev = max([abs((pts[k][0] - ax) * dy - (pts[k][1] - ay) * dx) / n for k in range(i0 + 1, i1 + 1)] or [0])
            if dev <= tol:
                out.append((dev, (ax + bx) / 2, (ay + by) / 2, math.atan2(dy, dx)))
            s += step
    return out


def _obox_hit(cx, cy, ang, hw, hh, segs):
    """Повёрнутая коробка подписи (центр, угол, полуширина, полувысота) задевает какой-нибудь отрезок: подпись улицы
    вдоль наклонной дороги проверяется по своему контуру, а не по описанному прямоугольнику."""
    ca, sa, r = math.cos(ang), math.sin(ang), hw + hh
    for (x1, y1), (x2, y2) in segs:
        if max(x1, x2) < cx - r or min(x1, x2) > cx + r or max(y1, y2) < cy - r or min(y1, y2) > cy + r:
            continue
        p = ((x1 - cx) * ca + (y1 - cy) * sa, -(x1 - cx) * sa + (y1 - cy) * ca)
        q = ((x2 - cx) * ca + (y2 - cy) * sa, -(x2 - cx) * sa + (y2 - cy) * ca)
        if _seg_box(p, q, (-hw, -hh, hw, hh)):
            return True
    return False


def _seg_cross(a, b, c, d):
    """Отрезки a–b и c–d пересекаются (касание концами не считается)."""
    def s(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return s(c, d, a) * s(c, d, b) < 0 and s(a, b, c) * s(a, b, d) < 0


def _pole(rings, clip, extra=()):
    """Самая глубокая точка фигуры (мм листа) внутри рамки и расстояние от неё до края: туда ставится точка выноски
    или номер, а не на узкий край участка. rings — внешнее кольцо и дыры."""
    outer = rings[0]
    edges = [e for r in rings for e in zip(r, r[1:] + r[:1])]
    if extra:                                                       # и граница территории: точка не на ней (правило 11)
        bx0, by0 = min(p[0] for p in outer) - 5, min(p[1] for p in outer) - 5
        bx1, by1 = max(p[0] for p in outer) + 5, max(p[1] for p in outer) + 5
        edges += [(a, b) for a, b in extra if not (max(a[0], b[0]) < bx0 or min(a[0], b[0]) > bx1 or max(a[1], b[1]) < by0 or min(a[1], b[1]) > by1)]
    x0, y0 = max(min(p[0] for p in outer), clip[0]), max(min(p[1] for p in outer), clip[1])
    x1, y1 = min(max(p[0] for p in outer), clip[2]), min(max(p[1] for p in outer), clip[3])
    if x1 <= x0 or y1 <= y0:
        return None

    def depth(x, y):
        if not _in_ring(x, y, outer) or any(_in_ring(x, y, h) for h in rings[1:]):
            return -1.0
        best = 9e9
        for (ax, ay), (bx, by) in edges:
            vx, vy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / (vx * vx + vy * vy or 1)))
            best = min(best, math.hypot(x - ax - vx * t, y - ay - vy * t))
        return best
    for n in (32, 128):                                             # узкая полоса проскакивает между узлами крупной сетки
        step = max(x1 - x0, y1 - y0) / n
        grid = sorted(((depth(x0 + (i + .5) * step, y0 + (j + .5) * step), x0 + (i + .5) * step, y0 + (j + .5) * step)
                       for i in range(int((x1 - x0) / step) + 1) for j in range(int((y1 - y0) / step) + 1)
                       if n == 32 or _in_ring(x0 + (i + .5) * step, y0 + (j + .5) * step, outer)), reverse=True)
        if grid and grid[0][0] > 0:
            break
    else:
        return []
    best = grid[0]
    for _ in range(2):                                              # уточнение вокруг лучшей точки
        step /= 4
        best = max([best] + [(depth(best[1] + i * step, best[2] + j * step), best[1] + i * step, best[2] + j * step)
                             for i in range(-4, 5) for j in range(-4, 5)])
    # запасные точки — на случай, если лучшая закрыта подписью; по убыванию глубины
    return [(best[1], best[2], best[0])] + [(x, y, d) for d, x, y in grid[1:60] if d > 0]


def _ring_centroid(ring):
    """Центр тяжести кольца (мм листа) и его площадь: подпись встаёт в середину фигуры, а не в среднее её вершин
    (у извилистой границы округа вершины скучены по краю)."""
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        cr = x1 * y2 - x2 * y1
        a += cr
        cx += (x1 + x2) * cr
        cy += (y1 + y2) * cr
    if abs(a) < 1e-9:
        xs, ys = zip(*ring)
        return sum(xs) / len(xs), sum(ys) / len(ys), 0.0
    return cx / (3 * a), cy / (3 * a), abs(a) / 2


def clip_ring(ring, rect, pad=2.0):
    """Кольцо по прямоугольнику листа (Сазерленд — Ходжмен): штриховка и заливка огромной зоны (водоохранная,
    СЗЗ на километры) считаются только в пределах рамки — иначе штриховка перебирает все её вершины на
    каждую линию и лист собирается минутами."""
    x0, y0, w, h = rect
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x0 + w + pad, y0 + h + pad
    pts = list(ring)
    for inside, cut in ((lambda p: p[0] >= x0, lambda a, b: (x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / (b[0] - a[0]))),
                        (lambda p: p[0] <= x1, lambda a, b: (x1, a[1] + (b[1] - a[1]) * (x1 - a[0]) / (b[0] - a[0]))),
                        (lambda p: p[1] >= y0, lambda a, b: (a[0] + (b[0] - a[0]) * (y0 - a[1]) / (b[1] - a[1]), y0)),
                        (lambda p: p[1] <= y1, lambda a, b: (a[0] + (b[0] - a[0]) * (y1 - a[1]) / (b[1] - a[1]), y1))):
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cut(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cut(prev, cur))
        pts = out
        if not pts:
            break
    return pts


def _parts(g):
    t, c = g["type"], g["coordinates"]
    if t == "Polygon":
        return "poly", [c]
    if t == "MultiPolygon":
        return "poly", c
    if t == "LineString":
        return "line", [c]
    if t == "MultiLineString":
        return "line", c
    if t == "Point":
        return "point", [c]
    if t == "MultiPoint":
        return "point", c
    return None, []


# Рисунок типов линий ЛГР на листе — постоянный на бумаге при любом масштабе (как PSLTSCALE в AutoCAD): единица шаблона
# REDLN97 = 0,25 мм, засечки границ зон — через 5 мм, как в образце «ГК Царицыно» (владелец 30.09.2026). Прежде шаблон
# шёл в метрах местности, и в 1:10 000 граница зоны сливалась в сплошную линию.
LT_MM = 0.25


def linetype_ops(pts, name, k, color, width, lib):
    """Сложный тип линии AutoCAD (REDLN97) вдоль ломаной в мм листа; k — мм на метр чертежа.
    Короче двух длин шаблона — сплошная линия (правило AutoCAD, как на экране)."""
    lt = lib["linetypes"].get(name)
    shapes = {n.upper(): s for n, s in lib["shapes"].items()}
    seg, cum = [], [0.0]
    for i in range(1, len(pts)):
        d = math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
        seg.append(d)
        cum.append(cum[-1] + d)
    L = cum[-1]
    solid = [{"op": "path", "closed": False, "fill": None, "stroke": color, "width": width, "dash": None, "rings": [pts]}]
    if not lt or L < 2 * lt["length"] * k or not seg:
        return solid

    pos = [0]                                                       # t растёт монотонно — указатель по отрезкам

    def at(t):
        i = pos[0]
        while i < len(seg) - 1 and cum[i + 1] < t:
            i += 1
        pos[0] = i
        f = (t - cum[i]) / seg[i] if seg[i] else 0
        a, b = pts[i], pts[i + 1]
        ux, uy = ((b[0] - a[0]) / seg[i], (b[1] - a[1]) / seg[i]) if seg[i] else (1, 0)
        return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, ux, uy

    # знаки (засечки «Т», треугольники) в REDLN97 — контур и заливка штрихами через 0,125 единицы знака. Штрихами
    # толщиной линии (0,3 мм при знаке ~0,6 мм) с острыми изломами знак превращался в пятно с рогами (владелец
    # 05.10.2026: «условные ЛГР битые»): у знаков своя толщина — в масштабе знака, изломы скруглены
    out, rings, marks, t, guard = [], [], {}, 0.0, 0
    while t < L and guard < 20000:
        guard += 1
        for e in lt["pattern"]:
            if t >= L:
                break
            if "d" in e:
                d = e["d"] * k
                if d > 0:
                    t1 = min(t + d, L)
                    start = at(t)[:2]
                    i0 = pos[0]
                    end = at(t1)[:2]
                    rings.append([start] + [tuple(pts[i]) for i in range(i0 + 1, pos[0] + 1) if t < cum[i] < t1] + [end])
                t += abs(d)
            elif e.get("shape"):
                s = shapes.get(e["shape"].upper())
                if not s:
                    continue
                px, py, ux, uy = at(t)
                vx, vy = uy, -ux                                   # «слева по ходу» при оси y вниз
                r = math.radians(e.get("r") or 0)
                cr, sr, sc = math.cos(r), math.sin(r), (e.get("s") or 1) * k
                ax, ay, bx, by = (1, 0, 0, -1) if e.get("abs") else (ux, uy, vx, vy)
                ox = px + (e.get("x") or 0) * k * ux + (e.get("y") or 0) * k * vx
                oy = py + (e.get("x") or 0) * k * uy + (e.get("y") or 0) * k * vy
                sw = round(min(width, 0.15 * sc), 4)
                for path in s["paths"]:
                    ring = []
                    for sx, sy in path:
                        lx, ly = (sx * cr - sy * sr) * sc, (sx * sr + sy * cr) * sc
                        ring.append((ox + lx * ax + ly * bx, oy + lx * ay + ly * by))
                    if len(ring) > 1:
                        marks.setdefault(sw, []).append(ring)
    if rings:
        out.append({"op": "path", "closed": False, "fill": None, "stroke": color, "width": width, "dash": None, "rings": rings})
    for sw, rs in marks.items():
        out.append({"op": "path", "closed": False, "fill": None, "stroke": color, "width": sw, "dash": None, "rings": rs, "join": "round"})
    return out


TILE_FAIL_DIR = Path.home() / ".grado2" / "cache" / "tiles" / "_fail"     # метки неудачных тайлов: живут и после перезапуска сервера
TILE_FAIL_TTL = 3600                                                       # час: тайл, который не скачался, до истечения не запрашивается
TILE_FAIL_NOTE = "часть плиток подложки не загрузилась ({n}) — повторите через час"
TILE_COARSE_NOTE = "снимок грубее обычного: лист слишком большой для подробных плиток"


class TileGuard:
    """Отрицательный кэш подложки: тайл, который не скачался (таймаут, 4xx/5xx, нет сети), на час получает метку-файл
    в папке кэша, и листы до её истечения не ходят за ним в сеть (раньше без сети каждый лист ждал 398 с).
    Удача стирает метку. Три попытки с паузами остаются у самой выгрузки: после них метка — не больше трёх за час."""

    def __init__(self, tiles, fail_dir=None, ttl=None):
        self.tiles, self.dir = tiles, Path(fail_dir or TILE_FAIL_DIR)
        self.ttl = TILE_FAIL_TTL if ttl is None else ttl
        self.missed = set()
        self.egko = getattr(tiles, "egko", None)

    def __call__(self, z, x, y, kind="sat"):
        mark = self.dir / f"{kind}_{z}_{x}_{y}.fail"
        try:
            if time.time() - mark.stat().st_mtime < self.ttl:
                self.missed.add((z, x, y))
                return None
        except OSError:
            pass
        try:
            data = self.tiles(z, x, y) if kind == "sat" else self.tiles(z, x, y, kind)
        except OSError:
            data = None
        try:
            if data:
                mark.unlink(missing_ok=True)
            else:
                self.dir.mkdir(mode=0o700, parents=True, exist_ok=True)
                mark.touch()
                os.utime(mark)
        except OSError:
            pass
        if not data:
            self.missed.add((z, x, y))
        return data


def tile_ops(tr, rect, scale, tiles, lat, proj="3857", zmax=19, missing=None, want=None, miss_boxes=None, info=None):
    """Спутниковая подложка (тайлы JPEG) под объектами листа: каждый тайл — картинка по трём углам, пересчитанным в мм
    листа (МСК повёрнута относительно Меркатора — тайл ложится параллелограммом). proj="3857" — Web Mercator (Esri),
    "3395" — эллипсоидальный Меркатор (спутник Яндекса): у него другая только связь широты и номера ряда.
    missing — список, куда пишется число тайлов, которых не оказалось; miss_boxes — туда же прямоугольники (мм листа) этих тайлов.
    want(bbox_mm) — нужен ли тайл с таким прямоугольником (Esri только под дырами Яндекса). Больше 600 тайлов — уровень
    крупнее не берётся: z снижается, пока их не станет не больше 600 (раньше лист оставался без снимка); при want считаются
    только нужные тайлы. info — словарь: info["coarse"]=True, если уровень пришлось снизить (для серой пометки на листе)."""
    fx, fy, fw, fh = rect
    half_x, half_y = fw / 2 / tr.k * 1.25, fh / 2 / tr.k * 1.25                 # метры на местности с запасом на поворот
    lon0, lat0 = tr.lon0, tr.lat0
    dlon, dlat = half_x / (111320 * math.cos(math.radians(lat0))), half_y / 110540
    mpp = scale * 0.00025                                                        # метров на пиксель тайла: ~100 dpi на листе
    z = z0 = max(10, min(zmax, round(math.log2(156543.03 * math.cos(math.radians(lat0)) / mpp))))
    while True:
        n = 2 ** z
        tx = lambda lon: int((lon + 180) / 360 * n)
        lon_of = lambda x: x / n * 360 - 180
        if proj == "3395":
            from grado_connectors.yandex_vmap import HALF, lat_from_3395, lonlat_to_3395
            size = 2 * HALF / n
            ty = lambda la: int((HALF - lonlat_to_3395(0, la)[1]) / size)
            lat_of = lambda y: lat_from_3395(HALF - y * size)
        else:
            ty = lambda la: int((1 - math.asinh(math.tan(math.radians(la))) / math.pi) / 2 * n)
            lat_of = lambda y: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
        x0, x1, y0, y1 = tx(lon0 - dlon), tx(lon0 + dlon), ty(lat0 + dlat), ty(lat0 - dlat)
        def quad(x, y):
            tl, trr, bl = tr.mm(lon_of(x), lat_of(y)), tr.mm(lon_of(x + 1), lat_of(y)), tr.mm(lon_of(x), lat_of(y + 1))
            br = (trr[0] + bl[0] - tl[0], trr[1] + bl[1] - tl[1])
            return tl, trr, bl, (min(tl[0], trr[0], bl[0], br[0]), min(tl[1], trr[1], bl[1], br[1]),
                                 max(tl[0], trr[0], bl[0], br[0]), max(tl[1], trr[1], bl[1], br[1]))
        total = (x1 - x0 + 1) * (y1 - y0 + 1)
        if total > 600 and want is not None and total <= 200000:      # нужные тайлы — только те, что под дырами; счёт до 601
            total = 0
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    total += bool(want(quad(x, y)[3]))
                    if total > 600:
                        break
                if total > 600:
                    break
        if total <= 600 or z <= 1:
            break
        z -= 1
    if info is not None and z < z0:
        info["coarse"] = True
    out = []
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            tl, trr, bl, box = quad(x, y)
            if want is not None and not want(box):
                continue
            data = tiles(z, x, y)
            if not data:
                if missing is not None:
                    missing.append((z, x, y))
                if miss_boxes is not None:
                    miss_boxes.append(box)
                continue
            # тайлы внахлёст на пиксель: иначе на стыках снимков просвечивают белые точки
            e, ux, uy, vx, vy = 1 / 256, trr[0] - tl[0], trr[1] - tl[1], bl[0] - tl[0], bl[1] - tl[1]
            tl, trr, bl = ((tl[0] - (ux + vx) * e, tl[1] - (uy + vy) * e), (trr[0] + (ux - vx) * e, trr[1] + (uy - vy) * e),
                           (bl[0] + (vx - ux) * e, bl[1] + (vy - uy) * e))
            out.append({"op": "image", "data": data, "quad": (tl, trr, bl)})
    return out


class SketchMapFrame(Frame):
    """Карта листа из уже оформленных объектов клиента."""

    def __init__(self, rect, sheet, lib, lgr_dash, tiles=None, memo=None):
        super().__init__(rect)
        self.sheet, self.lib, self.lgr_dash, self.tiles = sheet, lib, lgr_dash, tiles
        # память мест подписей альбома: у листов с той же рамкой и тем же масштабом названия (улицы, реки, деревни,
        # СНТ, зоны) стоят на тех же местах — при пролистывании не прыгают (владелец 30.09.2026); другое место —
        # только если своё занято (выноска, номер), тогда подпись сдвигается или пропадает
        self.memo = memo if memo is not None else {}

    def ops(self, ctx):
        sh, rect = self.sheet, self.rect
        tr = MapTransform(rect, sh["center"], sh["scale"])
        k = tr.k
        out, labels, along, placed, runs = [{"op": "clip", "rect": tuple(rect)}], [], {}, [], {}
        roadsegs = []                                                   # оси дорог OSM (мм) с названием: подписи их не пересекают
        guard, tinfo = None, {}
        late = []                                                       # знаки поверх границы территории (точки съёмки)
        streetlines = {}                                                # название улицы → её линии (мм)
        watersegs = []                                                  # берега (мм): номер зоны Генплана — не на реке
        osegs = []                                                      # железная дорога и граница района (мм): названия не лежат на них
        if sh.get("basemap") in ("sat", "light") and self.tiles:
            out.append({"op": "layer", "name": "Подложка"})             # метки слоёв — группы фигур в PPTX (PDF их не видит)
            kind = sh["basemap"]
            guard = TileGuard(self.tiles)                                 # неудачный тайл — пустое место и метка на час
            get = lambda z, x, y: guard(z, x, y, kind)
            ysat = getattr(self.tiles, "ysat", None) if kind == "sat" else None
            if ysat:
                # снимок — спутник Яндекса, самый свежий (владелец 05.10.2026); z18 — его самый подробный настоящий уровень.
                # Где плиток Яндекса нет, под снимком лежит Esri — белых дыр на листе не бывает
                miss, boxes = [], []
                ys = tile_ops(tr, rect, sh["scale"], ysat, sh["center"][1], proj="3395", zmax=18, missing=miss, miss_boxes=boxes, info=tinfo)
                fx, fy, fw, fh = rect
                boxes = [m for m in boxes if m[0] < fx + fw and fx < m[2] and m[1] < fy + fh and fy < m[3]]   # дыры за краем листа не в счёт
                if boxes or not ys:
                    # Esri — только под дырами Яндекса (плитка Esri, задевающая любую пропавшую плитку Яндекса); нет ни одной — весь лист
                    hit = (lambda b: any(b[0] < m[2] - .5 and m[0] + .5 < b[2] and b[1] < m[3] - .5 and m[1] + .5 < b[3] for m in boxes)) if ys else None   # .5 мм — запас на поворот сетки
                    out.extend(tile_ops(tr, rect, sh["scale"], get, sh["center"][1], want=hit, info=tinfo))
                out.extend(ys)
            else:
                out.extend(tile_ops(tr, rect, sh["scale"], get, sh["center"][1], info=tinfo))
            if sh.get("veil"):                                            # белая дымка на снимке: границы участков не сливаются
                fx, fy, fw, fh = rect
                out.append({"op": "path", "closed": True, "fill": (1, 1, 1), "alpha": float(sh["veil"]), "stroke": None, "width": 0,
                            "dash": None, "rings": [[(fx, fy), (fx + fw, fy), (fx + fw, fy + fh), (fx, fy + fh)]]})
        egko = getattr(self.tiles, "egko", None)
        if sh.get("mask") and egko:
            out.append({"op": "layer", "name": "Картооснова ЕГКО"})
            out.extend(egko_ops(tr, rect, sh["mask"], egko))
        # перекрёстки: вершина, общая для двух линий (или дважды у одной) — подпись улицы через неё не проходит
        junctions = {}
        for layer in sh.get("layers", []):
            for f in layer.get("features", []):
                if f.get("label") or f.get("nl"):
                    kind, parts = _parts(f["g"])
                    if kind == "line":
                        for line in parts:
                            for q in line:
                                k2 = (round(q[0], 6), round(q[1], 6))
                                junctions[k2] = junctions.get(k2, 0) + 1
        # дороги без заливки, одним контуром (casing): сначала контуры всех кусков дорог двойной толщины, поверх —
        # их заливка цветом фона; внутренние стыки кусков закрываются, виден один общий контур (владелец 30.09.2026)
        casing = set(sh.get("casing") or [])
        cased = False
        spans = []                                                      # (слой, начало его фигур в out)
        for layer in sh.get("layers", []):
            if layer.get("key") in casing:
                if cased:
                    continue
                cased = True
                spans.append(({}, len(out)))
                out.append({"op": "layer", "name": "Дороги"})
                polys = []
                for L_ in sh.get("layers", []):
                    if L_.get("key") not in casing:
                        continue
                    for f in L_.get("features", []):
                        kind, parts = _parts(f["g"])
                        if kind != "poly":
                            continue
                        for poly in parts:
                            rings = [c for c in (clip_ring([tr.mm(*p[:2]) for p in r], rect) for r in poly) if len(c) >= 3]
                            if rings:
                                polys.append((rings, f))
                for rings, f in polys:
                    out.append({"op": "path", "rings": rings, "closed": True, "fill": None, "width": max(0.08, (f.get("w") or 1) * PX_MM) * 2,
                                "stroke": hex_to_rgb(f.get("stroke") or "#a0a0a0"), "dash": None})
                for rings, f in polys:
                    out.append({"op": "path", "rings": rings, "closed": True, "fill": hex_to_rgb(f.get("fill") or "#ffffff"),
                                "stroke": None, "width": 0, "dash": None})
                continue
            spans.append((layer, len(out)))
            out.append({"op": "layer", "name": layer.get("title") or "Слой"})
            lkey = layer.get("key") or ""
            obst = lkey == "yandex.rail" or layer.get("title") == "Граница района" or layer.get("obstacle")
            for f in layer.get("features", []):
                if isinstance(f.get("label"), str) and ('"' in f["label"] or "\u201c" in f["label"]):
                    f = {**f, "label": _guillemets(f["label"])}          # кавычки подписей — «ёлочки» (владелец 05.10.2026)
                kind, parts = _parts(f["g"])
                w = max(0.08, (f.get("w") or 1) * PX_MM)
                stroke = hex_to_rgb(f.get("stroke")) if f.get("stroke") else None
                dash = [max(0.1, float(d) * PX_MM) for d in f["dash"]] if f.get("dash") else None   # штрих карты (пикс.) → мм
                if kind == "poly":
                    best = None                                                 # подпись — одна на объект: у самой большой части
                    for poly in parts:
                        rings = [c for c in (clip_ring([tr.mm(*p[:2]) for p in r], rect) for r in poly) if len(c) >= 3]
                        if layer.get("key") == "egko.water":
                            watersegs.extend(e for r in rings for e in zip(r, r[1:] + r[:1]))
                        if not rings:
                            continue
                        a = f.get("a")
                        # прозрачная заливка — не «белая»: в PDF-писателе ядра альфы нет, и полупрозрачный цвет смешивается
                        # с белым; на спутнике такая заливка закрыла бы снимок — там рисуется только контур
                        see_through = a is not None and (a <= .02 or (sh.get("basemap") == "sat" and a < .6))
                        fill = None if f.get("hatch") or f.get("fill") is None or see_through else _mix(f["fill"], a)
                        if f.get("hatch") and f.get("fill"):
                            # узор штриховки слоя: одно направление или сетка из двух; шаг — как на карте (Эталон ЛГР: 2 мм)
                            step = max(0.8, float(f["hs"]) * PX_MM) if f.get("hs") else 1.6
                            for ang in {"0": (0,), "90": (90,), "135": (135,), "x45": (45, 135), "x0": (0, 90)}.get(f.get("hp"), (45,)):
                                out.extend(hatch_ops(rings, spacing=step, stroke=hex_to_rgb(f["fill"]), angle=ang, width=0.13))   # тонкая, как на карте
                        if fill or (stroke and f.get("w", 1) > 0):          # контур поверх штриховки, как на карте
                            out.append({"op": "path", "rings": rings, "closed": True, "fill": fill, "stroke": stroke if f.get("w", 1) > 0 else None,
                                        "width": w, "dash": dash})
                        if f.get("label"):
                            c = _ring_centroid(rings[0])
                            if best is None or c[2] > best[2]:
                                best = (*c, rings[0])
                    if f.get("label") and best:
                        labels.append((best[0], best[1], f["label"], f.get("ls"), f, best[3], abs(best[2])))
                elif kind == "line":
                    color = hex_to_rgb(f.get("lc") or f.get("stroke") or f.get("fill") or "#333333")
                    for line in parts:
                        pts = [tr.mm(*p[:2]) for p in line]
                        if len(pts) < 2:
                            continue
                        if obst:                                    # железная дорога и граница района — препятствие для названий
                            osegs.extend(zip(pts, pts[1:]))
                        if layer.get("key") == "osm.roads":
                            roadsegs.extend((a, b, str(f.get("label") or "")) for a, b in zip(pts, pts[1:]))
                        if f.get("nl"):
                            pass                                    # линия не рисуется, только подпись (улицы на снимке)
                        elif f.get("flood"):
                            out.extend(flood_ops(pts, int(f["flood"]), color, side=f.get("fside", -1)))
                        elif f.get("lt"):
                            for name in f["lt"]:
                                out.extend(linetype_ops(pts, name, LT_MM, color, max(w, 0.25), self.lib))
                        elif f.get("miss"):
                            for code, _sign in f["miss"]:
                                dash = self.lgr_dash.get(int(code))
                                out.append({"op": "path", "closed": False, "fill": None, "stroke": color, "width": max(w, 0.25),
                                            "dash": [d * LT_MM for d in dash] if dash else None, "rings": [pts]})
                            if f.get("ll"):                     # надпись знака вдоль линии (Эталон ЛГР: «техническая зона», «береговая»)
                                from grado_render.scene import line_label_ops
                                out.extend(dict(t, font_family="sans") for t in line_label_ops([tuple(p) for p in pts], f["ll"], color, 1.6, False))
                        else:
                            out.append({"op": "path", "closed": False, "fill": None, "stroke": color, "width": w, "dash": dash, "rings": [pts]})
                        if f.get("label"):
                            # подпись вдоль линии (улица): на самом длинном прямом участке без перекрёстков внутри —
                            # подпись на нём не пересекает поперечные улицы; одно название — один раз
                            keys = [(round(q[0], 6), round(q[1], 6)) for q in line]
                            streetlines.setdefault(f["label"], []).append(pts)   # ось улицы целиком — для «почти прямых» отрезков
                            for d, mx, my, ang in _straight_runs(pts, [junctions.get(k, 0) > 1 for k in keys]):
                                runs.setdefault(f["label"], []).append((d, mx, my, ang, f))   # запасные места подписи улицы
                                if not (rect[0] < mx < rect[0] + rect[2] and rect[1] < my < rect[1] + rect[3]):
                                    continue
                                if d > along.get(f["label"], (0,))[0]:
                                    along[f["label"]] = (d, mx, my, ang, f.get("ls"), f)
                elif kind == "point":
                    for p in parts:
                        x, y = tr.mm(*p[:2])
                        if f.get("nm"):                                 # слой надписей: подпись на самой точке, без значка
                            if f.get("label"):
                                placed.append((x, y, str(f["label"]), f.get("ls"), f.get("la"), f.get("lcol"), f))
                            continue
                        if f.get("nodot"):                               # подпись-плашка без значка (кадастровый номер)
                            if f.get("label"):
                                labels.append((x, y, f["label"], f.get("ls"), f))
                            continue
                        if f.get("mk") == "view":                        # точка съёмки: стрелка по направлению снимка
                            # поверх маски и границы территории: стрелка у границы не бледнеет и не прячется под пунктиром
                            late.extend(_view_mark(x, y, float(f.get("dir") or 0), hex_to_rgb(f.get("fill") or "#1f3fbf")))
                            if f.get("label"):
                                b = math.radians(float(f.get("dir") or 0))
                                labels.append((x - math.sin(b) * 4.2, y + math.cos(b) * 4.2 + 1.8, f["label"], f.get("ls"), f))
                            continue
                        out.append({"op": "circle", "x": x, "y": y, "r": max(0.5, (f.get("w") or 1) * 0.35),
                                    "fill": _mix(f.get("fill") or "#666666", 1), "stroke": stroke or (0.2, 0.2, 0.2), "width": 0.15})
                        if f.get("label"):
                            labels.append((x, y - 2, f["label"], f.get("ls"), f))
        # слои с over (граница района) — поверх белой маски за территорией: иначе их не отличить от бледных линий под ней
        if any(L_.get("over") for L_, _ in spans):
            ends = [i for _, i in spans[1:]] + [len(out)]
            moved, keep_from = [], []
            for (L_, a_), b_ in zip(spans, ends):
                if L_.get("over"):
                    moved.extend(out[a_:b_])
                    keep_from.append((a_, b_))
            for a_, b_ in reversed(keep_from):
                del out[a_:b_]
            late[:0] = moved
        if sh.get("territory"):
            out.append({"op": "layer", "name": "Граница территории"})
        if sh.get("territory") and sh.get("terrPoint"):
            # мелкая схема (вся Москва, округ): территория в доли миллиметра — точкой, как в шаблоне ППТ КРТ
            ring = [tr.mm(*p[:2]) for p in _parts(sh["territory"])[1][0][0]]
            cx, cy = sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
            out.append({"op": "circle", "x": cx, "y": cy, "r": float(sh["terrPoint"]), "fill": (0, 0, 0), "stroke": None, "width": 0})
        elif sh.get("territory"):
            _, parts = _parts(sh["territory"])
            if sh.get("terrMask"):                                    # всё за границей территории — под белой полупрозрачной маской
                fx, fy, fw, fh = rect
                holes = [[tr.mm(*p[:2]) for p in poly[0]] for poly in parts]
                out.append({"op": "path", "rings": [[(fx, fy), (fx + fw, fy), (fx + fw, fy + fh), (fx, fy + fh)]] + holes, "closed": True,
                            "fill": (1, 1, 1), "alpha": float(sh["terrMask"]), "stroke": None, "width": 0, "dash": None, "evenodd": True})
            for poly in parts:
                ts = sh.get("terrStyle") or {}                        # слайды раздела: граница ППТ — сплошная пурпурная
                out.append({"op": "path", "rings": [[tr.mm(*p[:2]) for p in poly[0]]], "closed": True,
                            "fill": _mix(ts["fill"], .35) if ts.get("fill") else None,
                            "stroke": hex_to_rgb(ts.get("stroke", "#b3261f")), "width": ts.get("width", 0.6),
                            "dash": ts.get("dash") if ts else [4, 1.2, 0.6, 1.2]})
        out.extend(late)
        grid = {}                                                     # подписи без наложений: первая занявшая место остаётся
        rx, ry, rw, rh = rect
        mem = self.memo.setdefault((tuple(round(v, 1) for v in rect), tuple(round(float(c), 7) for c in sh["center"]), sh["scale"]), {})
        # граница территории — препятствие для названий территорий и деревень (правила подписей, владелец 30.09.2026)
        tsegs, tpad = [], float((sh.get("terrStyle") or {}).get("width", 0.6)) / 2 + 0.4
        if sh.get("territory") and not sh.get("terrPoint"):
            for poly in _parts(sh["territory"])[1]:
                for r in poly:
                    pts = [tr.mm(*p[:2]) for p in r]
                    tsegs.extend(zip(pts, pts[1:]))

        # номера в кружках (листы 7–9): точка выноски — в глубине своего участка; кружок не закрывает чужие точки,
        # не стоит на чужом участке, линии выносок не пересекают друг друга и чужие подписи (владелец 30.09.2026)
        marks, clip = {}, (rx, ry, rx + rw, ry + rh)
        for x_, y_, _t, _l, f_, *_m in labels:
            if f_.get("circle"):
                rings_ = [[tr.mm(*p[:2]) for p in r] for r in f_["zone"]] if f_.get("zone") else None
                a_ = rings_ and _pole(rings_, clip, tsegs)
                if f_.get("zone2") and (not a_ or a_[0][2] < 1.5):   # в территории — узкая кромка: точка в глубине всего участка
                    r2 = [[tr.mm(*p[:2]) for p in r] for r in f_["zone2"]]
                    b_ = _pole(r2, clip, tsegs)
                    if b_ and b_[0][2] > (a_[0][2] if a_ else 0):
                        rings_, a_ = r2, b_
                marks[id(f_)] = (a_[0][0], a_[0][1], a_[0][2], rings_[0], a_) if a_ else (x_, y_ + float(f_.get("ldy") or 0), 0.0, None, [])

        # у каждого номера своя точка: совпадающая (ближе 2,5 мм к уже взятой) заменяется следующей по глубине точкой
        # своего участка (лист 8: «выноски 9, 8, 10 сходятся в одну точку»)
        seen_ = []
        for k_, m_ in marks.items():
            if any(math.hypot(m_[0] - p_[0], m_[1] - p_[1]) < SPREAD for p_ in seen_):
                for d_ in (SPREAD, 2.5):                                # сначала разводим на 4 мм, потом хотя бы на 2,5
                    c_ = next((c for c in m_[4] if all(math.hypot(c[0] - p_[0], c[1] - p_[1]) >= d_ for p_ in seen_)), None)
                    if c_ or all(math.hypot(m_[0] - p_[0], m_[1] - p_[1]) >= d_ for p_ in seen_):
                        if c_:
                            m_ = marks[k_] = (c_[0], c_[1], c_[2], m_[3], m_[4])
                        break
            seen_.append(m_)
        boxes, leads, caps = [], [], []                                 # все занятые места, линии выносок, угловые надписи

        def take(box, avoid=False, ob=None, own=None):
            # ob — повёрнутая коробка подписи улицы (центр, угол, полуразмеры): граница территории проверяется по ней;
            # подписи не закрывают точки выносок номеров (own — свой номер)
            if avoid and any(k_ != own and box[0] - 1 < m[0] < box[2] + 1 and box[1] - 1 < m[1] < box[3] + 1 for k_, m in marks.items()):
                return False
            if avoid and tsegs:
                if ob:
                    if _obox_hit(ob[0], ob[1], ob[2], ob[3] + tpad, ob[4] + tpad, tsegs):
                        return False
                else:
                    b = (box[0] - tpad, box[1] - tpad, box[2] + tpad, box[3] + tpad)
                    if any(_seg_box(p, q, b) for p, q in tsegs):
                        return False
            if avoid and osegs and not ob:                              # названия территорий и номера — не поперёк железной дороги и границы района
                b = (box[0] - OBST_PAD, box[1] - OBST_PAD, box[2] + OBST_PAD, box[3] + OBST_PAD)
                if any(_seg_box(p, q, b) for p, q in osegs):
                    return False
            cells = [(i, j) for i in range(int(box[0] // 10), int(box[2] // 10) + 1)
                     for j in range(int(box[1] // 10), int(box[3] // 10) + 1)]       # сетка 10 мм вместо перебора всех
            if any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3])
                   for c in cells for b in grid.get(c, ())):
                return False
            for c in cells:
                grid.setdefault(c, []).append(box)
            boxes.append(box)
            return True

        callout = self._callout(sh, tr, rect) if sh.get("callout") and sh.get("territory") else None
        if callout:
            take(callout[0])
        if sh.get("mapNote"):
            n = sum(len(b) if isinstance(b, list) else 2 for b in sh["mapNote"])
            caps.append((rx, ry, rx + 102, ry + 7 + 5.4 * n + 3))
            take(caps[-1])                                              # угол с округом и районом — без подписей карты
        if sh.get("mapNoteBR"):                                           # правый нижний угол — район этого угла
            from album_io import ortho_legend_h
            n = sum(len(b) if isinstance(b, list) else 2 for b in sh["mapNoteBR"])
            lift = ortho_legend_h(sh) + 2 if sh.get("bleed") else 0
            caps.append((rx + rw - 102, ry + rh - lift - 7 - 5.4 * n, rx + rw, ry + rh - lift))
            take(caps[-1])
        ink = (1, 1, 1) if sh.get("basemap") == "sat" else (0.12, 0.12, 0.12)   # на снимке тёмная подпись не читается
        out.append({"op": "layer", "name": "Подписи"})
        # порядок при нехватке места (правила подписей, docs/standards/albums/label-rules.md): надписи на своих местах —
        # реки, номера документов, надписи ГИС ОГД; затем улицы; затем названия территорий, крупные раньше мелких
        for x, y, text, ls, deg, col, pf in placed:
            # надписи ГИС ОГД: на своём месте и под своим углом (вдоль границы), цветом знака ЛГР; наложения не пропускаются
            ls = float(ls or 2.0)
            if not (rx <= x <= rx + rw and ry <= y <= ry + rh):
                continue
            ang = -math.radians(float(deg or 0))              # на листе ось Y вниз: против часовой на карте — «минус»
            text = text[:60]
            tw = _text_w(text, pf.get("lf"), ls)
            ca, sa = abs(math.cos(ang)), abs(math.sin(ang))
            ex, ey = ca * tw / 2 + sa * ls * .6, sa * tw / 2 + ca * ls * .6
            # номер документа можно сдвинуть с занятого места; надписи ГИС ОГД остаются на своём; подпись — целиком в рамке
            # сдвигаемые подписи (номера, деревни) обходят границу территории; последняя попытка — без этого условия
            # сдвигаемые подписи (деревни, СНТ, улицы по адресам): сначала места без пересечения проездов, потом любые;
            # поиск до 25 мм — обязательная подпись не пропадает, если рядом есть место (правило 11)
            near_ = ((0, 0), (0, -4), (0, 4), (-5, 0), (5, 0), (-5, -4), (5, 4), (5, -4), (-5, 4), (0, -8), (0, 8), (-10, 0), (10, 0))
            far_ = tuple((r * math.cos(a), r * math.sin(a)) for r in (14, 19, 25) for a in [k * math.pi / 6 for k in range(12)])
            moves = ([(dx, dy, 2) for dx, dy in near_] + [(dx, dy, 1) for dx, dy in near_ + far_] + [(0, 0, 0)]) if pf.get("nudge") else [(0, 0, 0)]
            was = mem.get(("p", text))
            if was:
                moves = [(was[0] - x, was[1] - y, 1)] + moves
            M = MAP_PAD
            for dx, dy, lv in moves:
                cx_, cy_ = x + dx, y + dy
                if not (cx_ - ex >= rx + M and cx_ + ex <= rx + rw - M and cy_ - ey >= ry + M and cy_ + ey <= ry + rh - M):
                    continue
                if lv == 2 and _obox_hit(cx_, cy_, ang, tw / 2, ls * .45, [(a, b) for a, b, _n in roadsegs]):
                    continue
                if take((cx_ - ex, cy_ - ey, cx_ + ex, cy_ + ey), avoid=lv > 0):
                    x, y = cx_, cy_
                    break
            else:
                continue
            mem.setdefault(("p", text), (x, y))
            extra = {k: v for k, v in (("font_family", pf.get("lf")), ("halo", pf.get("lh"))) if v}
            out.append({"op": "text", "x": x - math.sin(ang) * ls * .35, "y": y + math.cos(ang) * ls * .35, "size": ls, "text": text,
                        "color": hex_to_rgb(col) if col else ink, "anchor": "middle", "angle": ang, **extra})
        for t_, rr in runs.items():                                     # обязательная улица с участками только у края рамки
            if t_ not in along and rr[0][4].get("must"):
                b = max(rr, key=lambda r: r[0])
                along[t_] = (b[0], b[1], b[2], b[3], b[4].get("ls"), b[4])
        for text, (d, x, y, ang, ls, af) in sorted(along.items(), key=lambda t: -t[1][0]):
            ls = float(ls or 2.2)
            text = str(text)[:40]
            tw = _text_w(text, af.get("lf"), ls)
            if d < tw * 1.1 and not af.get("must"):
                continue                                                # подпись не влезает в прямой участок улицы — улица мала, не подписывается
            # места подписи — прямые участки улицы: сначала на самой дороге, затем рядом с ней вдоль неё; подпись не
            # заходит на границу территории (правила подписей, владелец 30.09.2026). Обязательная улица («ул. Придорожная»)
            # подписывается и на коротком участке — ближе к своим домам; если чистого места нет, подпись не ставится:
            # прохода без проверки границы нет, граница не пересекается ни на одном уровне (правило 1).
            hx, hy = tr.mm(*af["mustAt"]) if af.get("mustAt") else (None, None)
            rl = runs.get(text) or [(d, x, y, ang, af)]
            if af.get("must"):
                order = sorted(rl, key=lambda r: (r[0] < tw * 1.1, math.hypot(r[1] - hx, r[2] - hy) if hx is not None and r[0] >= tw * 1.1 else -r[0]))
            else:                                                       # ближе к середине листа (владелец 30.09.2026: «Калужское ш.» — не у края)
                hx, hy = rx + rw / 2, ry + rh / 2
                order = sorted((r for r in rl if r[0] >= tw * 1.1), key=lambda r: math.hypot(r[1] - hx, r[2] - hy))

            def near_terr(x_, y_):
                best_ = 9e9
                for (ax_, ay_), (bx_, by_) in tsegs:
                    vx_, vy_ = bx_ - ax_, by_ - ay_
                    t_ = max(0.0, min(1.0, ((x_ - ax_) * vx_ + (y_ - ay_) * vy_) / (vx_ * vx_ + vy_ * vy_ or 1)))
                    best_ = min(best_, math.hypot(x_ - ax_ - vx_ * t_, y_ - ay_ - vy_ * t_))
                return best_
            chains_ = _chains(streetlines.get(text, []))
            ls0, tw0 = ls, tw

            # отрезки других названных улиц, кроме тех, что упираются в эту улицу (примыкание сбоку подпись не режет)
            own_ = {(round(p_[0], 1), round(p_[1], 1)) for c_ in chains_ for p_ in c_}
            others_ = [(a, b) for a, b, n_ in roadsegs if n_ and n_ != text
                       and (round(a[0], 1), round(a[1], 1)) not in own_ and (round(b[0], 1), round(b[1], 1)) not in own_]

            def place(ls, tw, tol, first, beside=True, chains_=chains_, others_=others_):
                """Место подписи улицы при кегле ls, ширине tw и допуске отклонения оси tol; None — места нет."""
                def shifts(rd, rx0, ry0, ra):                               # сдвиги вдоль прямого участка, не сходя с него
                    m = max(0.0, (rd - tw) / 2)
                    ts = [0.0, -m / 2, m / 2, -m, m]
                    if hx is not None:
                        ts = [max(-m, min(m, (hx - rx0) * math.cos(ra) + (hy - ry0) * math.sin(ra)))] + [k * m / 3 for k in (0, -3, -2, -1, 1, 2, 3)]
                    return ts
                off = ls * .95 + tpad
                # места на самой оси улицы: отрезки длиной с подпись, где ось почти прямая (отклонение не больше четверти
                # кегля) — подпись лежит на дороге и по её направлению, даже если прямого участка между перекрёстками нет
                # (владелец 30.09.2026: «ул. Придорожная криво и залезает на границу»); ближе к домам улицы или к середине
                # обязательная улица — ближе к территории (она подписывается как улица у территории, правило 1), иначе — к
                # середине листа
                wins = _axis_windows(chains_, tw * 1.04, tol)
                if af.get("must") and tsegs:
                    wins = sorted(wins, key=lambda w_: near_terr(w_[1], w_[2]) + w_[0] * 20)[:400]
                else:
                    wins = sorted(wins, key=lambda w_: (math.hypot(w_[1] - hx, w_[2] - hy) if hx is not None else 0) + w_[0] * 20)[:400]
                cands = [(True, wx, wy, wa) for _dv, wx, wy, wa in wins]
                cands += [(True, rx0 + math.cos(ra) * t - math.sin(ra) * o, ry0 + math.sin(ra) * t + math.cos(ra) * o, ra)
                          for o in ((0.0, off, -off) if beside else (0.0,)) for rd, rx0, ry0, ra, _f in order for t in shifts(rd, rx0, ry0, ra)
                          if o or rd >= tw * 1.04]                          # на коротком прямом участке подпись свисала бы с дороги
                # граница территории не пересекается никогда, и обязательной улицы тоже (правило 1)
                was = mem.get(("s", text))
                if was and first:
                    cands = [(True, *was)] + cands
                for av, x, y, ang in cands:
                    ang = (ang + math.pi / 2) % math.pi - math.pi / 2       # не вверх ногами: угол в пределах ±90°
                    ca, sa = abs(math.cos(ang)), abs(math.sin(ang))
                    ex, ey = ca * tw / 2 + sa * ls * .6, sa * tw / 2 + ca * ls * .6
                    if x - ex < rx + MAP_PAD or x + ex > rx + rw - MAP_PAD or y - ey < ry + MAP_PAD or y + ey > ry + rh - MAP_PAD:
                        continue                                            # подпись улицы — целиком в рамке, с полем
                    if av and _obox_hit(x, y, ang, tw / 2, ls * .45, others_):
                        continue                                            # не поперёк другой названной улицы
                    if take((x - ex, y - ey, x + ex, y + ey), avoid=av, ob=(x, y, ang, tw / 2, ls * .6)):
                        return x, y, ang
                return None
            # уровни: ось почти прямая (¼ кегля) → чуть изогнутая (0,45 кегля) → обязательная улица кеглем 0,9 и 0,8;
            # граница территории не пересекается ни на одном уровне (правило 1)
            # обязательной улице важнее место у территории, чем идеально прямой отрезок: допуск сразу 0,45 кегля
            # сначала только на самой дороге (мельче до 0,8 кегля), и лишь потом рядом с ней — подпись над домами
            # выглядит «криво» (владелец 30.09.2026)
            levels = [(1, .45, False), (.9, .45, False), (.8, .45, False), (1, .45, True)] if af.get("must") else [(1, .25, True), (1, .45, True)]
            res = None
            for n_, (k_, tk_, bs_) in enumerate(levels):
                res = place(ls0 * k_, tw0 * k_, max(.6, ls0 * k_ * tk_), n_ == 0, bs_)
                if res:
                    ls, tw = ls0 * k_, tw0 * k_
                    break
            if not res and af.get("must"):
                # обязательная улица короче подписи в этой рамке (лист 4, 1:10 000): подпись продолжает ту же дорогу —
                # к оси улицы присоединяются примыкающие к её концам дороги (Сипягинское ш. — продолжение Придорожной)
                ends = [c_[k] for c_ in chains_ for k in (0, -1)]
                near_ = lambda q: any(abs(q[0] - e[0]) < .3 and abs(q[1] - e[1]) < .3 for e in ends)
                more = [l_ for n2, ls2 in streetlines.items() if n2 != text for l_ in ls2 if near_(l_[0]) or near_(l_[-1])]
                ext = _chains([p_ for c_ in chains_ for p_ in [c_]] + more)
                for k_ in (1, .9, .8):
                    ev_ = {(round(p_[0], 1), round(p_[1], 1)) for c_ in ext for p_ in c_}
                    oth2 = [(a, b) for a, b in others_ if (round(a[0], 1), round(a[1], 1)) not in ev_ and (round(b[0], 1), round(b[1], 1)) not in ev_]
                    res = place(ls0 * k_, tw0 * k_, max(.6, ls0 * k_ * .45), False, False, ext, oth2)
                    if res:
                        ls, tw = ls0 * k_, tw0 * k_
                        break
            if not res:
                continue
            x, y, ang = res
            mem.setdefault(("s", text), (x, y, ang))
            extra = {k: v for k, v in (("font_family", af.get("lf")), ("halo", af.get("lh"))) if v}
            out.append({"op": "text", "x": x - math.sin(ang) * ls * .35, "y": y + math.cos(ang) * ls * .35, "size": ls, "text": text,
                        "color": hex_to_rgb(af["lcol"]) if af.get("lcol") else ink, "anchor": "middle", "angle": ang, **extra})
        # подписи площадей и точек: крупные контуры — первыми; подпись целиком в рамке; если место занято — ищется
        # рядом внутри своего контура (названия СНТ не пропадают из-за подписи улицы)
        labels.sort(key=lambda t: -(t[6] if len(t) > 6 else 0))
        def free(f, cx, cy, cr, ax, ay, lvl):
            others = [m for k_, m in marks.items() if k_ != id(f)]
            if any(math.hypot(o[0] - cx, o[1] - cy) < cr + 1.5 for o in others):
                return False
            if lvl >= 3 and any(o[3] and _in_ring(cx, cy, o[3]) for o in others):
                return False
            box = (cx - cr - .3, cy - cr - .3, cx + cr + .3, cy + cr + .3)
            if any(_seg_box(p, q, box) for p, q in leads):
                return False
            d_ = math.hypot(ax - cx, ay - cy)
            if d_ > cr + .5:
                s_ = (cx + (ax - cx) / d_ * cr, cy + (ay - cy) / d_ * cr)
                if any(_seg_box(s_, (ax, ay), c_) for c_ in caps):          # выноска не заходит в угловые надписи
                    return False
                if any(_seg_cross(s_, (ax, ay), p, q) for p, q in leads):
                    return False
                if lvl >= 2 and any(_seg_box(s_, (ax, ay), (b[0] + .3, b[1] + .3, b[2] - .3, b[3] - .3)) for b in boxes):
                    return False
                for o in others:                                        # линия не проходит по чужой точке (общая точка — можно)
                    if math.hypot(o[0] - ax, o[1] - ay) < 2:
                        continue
                    vx, vy = ax - s_[0], ay - s_[1]
                    t = max(0.0, min(1.0, ((o[0] - s_[0]) * vx + (o[1] - s_[1]) * vy) / (vx * vx + vy * vy or 1)))
                    if math.hypot(o[0] - s_[0] - vx * t, o[1] - s_[1] - vy * t) < 1.5:
                        return False
            return True

        for x, y, text, ls, f, *more in labels:
            ring = more[0] if more else None
            if f.get("circle"):
                mk = marks[id(f)]
                def okp(c_, d_):                                        # точка выноски — не под уже поставленной подписью и не в кучке
                    return not any(b[0] - .5 < c_[0] < b[2] + .5 and b[1] - .5 < c_[1] < b[3] + .5 for b in boxes) and all(
                        math.hypot(c_[0] - m2_[0], c_[1] - m2_[1]) >= d_ for k2_, m2_ in marks.items() if k2_ != id(f))
                for d_ in (SPREAD, 2.5):
                    if okp(mk, d_):
                        break
                    c_ = next((c for c in mk[4] if okp(c, d_)), None)
                    if c_:
                        mk = marks[id(f)] = (c_[0], c_[1], c_[2], mk[3], mk[4])
                        break
                x, y = mk[0], mk[1] + float(ls or 2.2) * .35 - float(f.get("ldy") or 0)   # кружок — на точке участка
            ls = float(ls or 2.2)
            y += float(f.get("ldy") or 0)
            if not (rx <= x <= rx + rw and ry <= y <= ry + rh):
                continue
            lines = [ln[:40] for ln in str(text).split("\n")[:8]]         # подпись в несколько строк: номер и индекс зоны, коды ВРИ
            lh = ls * 1.23
            # кегль строки: lss — множители (номер зоны Генплана и индекс крупнее на 15 %, правило 11)
            sizes = [ls * float((f.get("lss") or [])[i] if i < len(f.get("lss") or []) else 1) for i in range(len(lines))]
            offs = [0.0]
            for i in range(1, len(lines)):
                offs.append(offs[-1] + sizes[i] * 1.2)
            if f.get("ul0") and ring:
                # номер зоны Генплана — в самой глубокой точке видимой части зоны, не ближе 6 мм к краю карты и
                # подальше от берегов; кусок зоны меньше подписи не подписывается (правило 11: «8 / 123» у края)
                pl_ = _pole([ring], (rx + 6, ry + 6, rx + rw - 6, ry + rh - 6), watersegs)
                need = max(_text_w(ln, f.get("lf"), sizes[i]) for i, ln in enumerate(lines)) / 2
                if not pl_ or _pole([ring], (rx + 6, ry + 6, rx + rw - 6, ry + rh - 6))[0][2] < max(need * .8, (offs[-1] + sizes[0]) * .7):
                    continue
                x, y = pl_[0][0], pl_[0][1] + sizes[0] * .35
            y -= offs[-1] / 2
            fams = f.get("lfs") or []
            bw = max(_text_w(ln, (fams[i] if i < len(fams) and fams[i] else f.get("lf")), sizes[i]) for i, ln in enumerate(lines))
            up, down = sizes[0] * 1.0, sizes[-1] * .3 + offs[-1]              # коробка подписи: y − up … y + down
            if f.get("circle"):                                             # номер в кружке («Хатминки»): коробка — круг
                cr = max(bw / 2 + ls * .25, ls * .62)
                bw, up, down = cr * 2, ls * .35 + cr, cr - ls * .35
            stn = str(text).startswith(STATION_MARK)                          # станция: узкая полоса земли вдоль путей — подпись рядом с ней
            steps = [(0, 0)] + ([(0, -5), (0, 5), (-9, 0), (9, 0), (-9, -5), (9, -5), (-9, 5), (9, 5), (0, -10), (0, 10), (-16, 0), (16, 0)]
                                + ([(r * math.cos(k * math.pi / 6), r * math.sin(k * math.pi / 6)) for r in (3, 5, 7.5, 10) for k in range(12)] if stn else [])
                                if ring else [(r * math.cos(k * math.pi / 4), r * math.sin(k * math.pi / 4)) for r in (2.5, 4.5, 6.5, 8.5) for k in range(8)]
                                if f.get("mk") == "view" else [])   # номер точки съёмки — рядом со стрелкой, как в «ГК Царицыно»
            ax, ay = x, y + offs[-1] / 2 - float(f.get("ldy") or 0)   # точка объекта (для выноски)
            if f.get("circle"):
                ax, ay = mk[0], mk[1]
                inside = mk[2] >= cr + .8 if mk[3] else f.get("inside")     # кружок целиком помещается в свой участок
            else:
                inside = f.get("inside")
            if f.get("leader"):                                             # выноска: подпись рядом, тонкая линия к объекту
                steps = ([(0, 0)] if inside else []) + [(r * math.cos(a), r * math.sin(a)) for r in LEAD_R
                                                        for a in [k * math.pi / 12 for k in LEAD_K]]
            # уровни попыток: у номеров 3 — строго (не на чужом участке), 2 — линия может задеть чужую подпись, 1 — только
            # без пересечения выносок и кружков, 0 — только не поверх других подписей, −1 — на месте как есть (номер
            # участка показывается всегда); у остальных подписей 1 — обычно, 0 — последняя, на месте как есть
            if f.get("circle"):
                # короткая выноска важнее строгости: на каждом радиусе — сначала «не на чужом участке», потом «линия
                # может задеть чужую подпись»; дальние места — только после ближних (владелец 30.09.2026: «выноска 12
                # нелогично далеко»)
                near = [(dx, dy, lvl) for dx, dy in steps[:1] for lvl in (3, 2)] if inside else []
                ring_ = steps[1:] if inside else steps
                for r0 in range(0, len(ring_), len(LEAD_K)):
                    near += [(dx, dy, lvl) for lvl in (3, 2) for dx, dy in ring_[r0:r0 + len(LEAD_K)]]
                tries = near + [(dx, dy, lvl) for lvl in (1, 0) for dx, dy in steps] + [(0, 0, -1)]
            else:
                was = mem.get(("a", str(text)))
                # названия территорий: сначала места без проездов под текстом (правило 11), потом любые в контуре
                tries = ([(was[0] - x, was[1] - y, 1)] if was else []) + ([(dx, dy, 2) for dx, dy in steps] if ring else []) \
                    + [(dx, dy, 1) for dx, dy in steps] + ([(0, 0, 0)] if ring or f.get("leader") or f.get("mk") == "view" else []) \
                    + ([(dx, dy, 0) for dx, dy in steps[1:]] + [(0, 0, -1)] if f.get("mk") == "view" else [])   # номер снимка есть всегда
            spot = None
            for dx, dy, lvl in tries:
                cx = min(max(x + dx, rx + bw / 2 + MAP_PAD), rx + rw - bw / 2 - MAP_PAD)
                cy = min(max(y + dy, ry + up + MAP_PAD), ry + rh - down - MAP_PAD)
                if ring and lvl > 0 and not stn and not _in_ring(cx, cy, ring):
                    continue
                if f.get("circle") and lvl > 0 and not free(f, cx, cy - ls * .35, cr, ax, ay, lvl):
                    continue
                if not f.get("circle") and ring and lvl == 2 and any(
                        _seg_box(a, b, (cx - bw / 2, cy - up, cx + bw / 2, cy + down)) for a, b, _n in roadsegs):
                    continue
                g_ = 1.0 if f.get("circle") and lvl > 0 else 0            # кружок — не ближе 1 мм к чужой подписи
                if take((cx - bw / 2 - g_, cy - up - g_, cx + bw / 2 + g_, cy + down + g_), avoid=lvl > 0, own=id(f)) or lvl < 0:
                    spot = (cx, cy)
                    break
            if not spot:
                continue
            x, y = spot
            if not f.get("circle"):
                mem.setdefault(("a", str(text)), spot)
            # оформление подписи из листа: шрифт (lf, у каждой строки — lfs), ореол (lh, мм; цвет — lhc), цвет (lcol),
            # белая плашка под текстом (lbox) — альбомы по шаблонам
            extra = {k: v for k, v in (("font_family", f.get("lf")), ("halo", f.get("lh"))) if v}
            if f.get("lhc"):
                extra["halo_color"] = hex_to_rgb(f["lhc"])
            if f.get("circle"):                                             # кружок: центр — на высоте середины цифр
                ccy = y - ls * .35
                lc = hex_to_rgb(f.get("lcol") or "#231f20")
                if math.hypot(x - ax, ccy - ay) > cr + .5:                  # выноска: линия с белой обводкой и точка в участке
                    d_ = math.hypot(ax - x, ay - ccy) or 1
                    sx, sy = x + (ax - x) / d_ * cr, ccy + (ay - ccy) / d_ * cr
                    leads.append(((sx, sy), (ax, ay)))
                    out.append({"op": "path", "closed": False, "fill": None, "stroke": (1, 1, 1), "width": 1.3, "dash": None, "rings": [[(sx, sy), (ax, ay)]]})
                    out.append({"op": "path", "closed": False, "fill": None, "stroke": lc, "width": 0.5, "dash": None, "rings": [[(sx, sy), (ax, ay)]]})
                    out.append({"op": "circle", "x": ax, "y": ay, "r": 1.0, "fill": lc, "stroke": (1, 1, 1), "width": 0.35})
                out.append({"op": "circle", "x": x, "y": ccy, "r": cr, "fill": (1, 1, 1), "stroke": lc, "width": 0.5})
                f = {**f, "lh": None}                                       # на белом кружке обводка не нужна
                extra = {k: v for k, v in (("font_family", f.get("lf")),) if v}
            elif f.get("leader") and math.hypot(x - ax, y - ay) > ls:         # линия от края подписи к объекту и точка на объекте
                pad = ls * .45 if f.get("lbox") else ls * .15
                x0b, x1b = x - bw / 2 - pad, x + bw / 2 + pad
                y0b, y1b = y - up - pad * .6, y + down + pad * .6
                vx, vy = ax - x, ay - y
                t = min([v for v in ((x1b - x) / vx if vx > 0 else (x0b - x) / vx if vx < 0 else 9e9,
                                     (y1b - y) / vy if vy > 0 else (y0b - y) / vy if vy < 0 else 9e9) if v > 0] or [0])
                lc = hex_to_rgb(f.get("lcol") or "#231f20")
                out.append({"op": "path", "closed": False, "fill": None, "stroke": (1, 1, 1), "width": 0.7, "dash": None,
                            "rings": [[(x + vx * t, y + vy * t), (ax, ay)]]})
                out.append({"op": "path", "closed": False, "fill": None, "stroke": lc, "width": 0.25, "dash": None,
                            "rings": [[(x + vx * t, y + vy * t), (ax, ay)]]})
                out.append({"op": "circle", "x": ax, "y": ay, "r": 0.6, "fill": lc, "stroke": (1, 1, 1), "width": 0.2})
            if f.get("lbox"):
                pad = ls * .45
                top = y - ls - pad * .6
                if f.get("lead"):                                       # выноска: белый пунктир от плашки к точке территории
                    tx, ty = tr.mm(*f["lead"][:2])
                    bottom = y + ls * .35 + (len(lines) - 1) * lh + pad * .6
                    out.append({"op": "path", "closed": False, "fill": None, "stroke": (1, 1, 1), "width": 0.35, "dash": [1.4, 0.9],
                                "rings": [[(x, top if ty < top else bottom), (tx, ty)]]})
                    out.append({"op": "circle", "x": tx, "y": ty, "r": 0.7, "fill": (1, 1, 1), "stroke": None, "width": 0})
                out.append({"op": "path", "closed": True, "fill": (1, 1, 1), "alpha": f.get("lboxAlpha"),
                            "stroke": hex_to_rgb(f["lbox"]) if isinstance(f["lbox"], str) else None,
                            "width": 0.2, "dash": None, "rings": [[(x - bw / 2 - pad, top), (x + bw / 2 + pad, top),
                                                                    (x + bw / 2 + pad, y + ls * .35 + (len(lines) - 1) * lh + pad * .6),
                                                                    (x - bw / 2 - pad, y + ls * .35 + (len(lines) - 1) * lh + pad * .6)]]})
            for i, line in enumerate(lines):
                fam = {"font_family": fams[i]} if i < len(fams) and fams[i] else {}
                ul = {"underline": True} if i == 0 and f.get("ul0") else {}   # номер зоны Генплана — подчёркнут
                out.append({"op": "text", "x": x, "y": y + offs[i], "size": sizes[i], "text": line, "anchor": "middle",
                            "color": hex_to_rgb(f["lcol"]) if f.get("lcol") else ink, **extra, **fam, **ul})
        if callout:
            out.extend(callout[1])
        notes = ([TILE_COARSE_NOTE] if tinfo.get("coarse") else []) + ([TILE_FAIL_NOTE.format(n=len(guard.missed))] if guard and guard.missed else [])
        if notes:                                                       # одна строка на лист, не по числу тайлов
            out.append({"op": "text", "x": rect[0] + 2, "y": rect[1] + rect[3] - 2, "size": 2.3, "color": (0.3, 0.3, 0.3),
                        "text": "; ".join(notes)})
        out.append({"op": "unclip"})
        for o in out:                                                   # изломы контуров — скруглённые, без острых «шипов»
            if o["op"] == "path":
                o.setdefault("join", "round")
        out.append({"op": "layer", "name": "Рамка"})
        if sh.get("noFrame"):
            pass                                                        # карта без рамки (схемы Москвы в шаблоне ППТ КРТ)
        elif str(sh.get("size", "")).startswith("P") or sh.get("kind") == "situation":
            # слайд презентации и ситуационный план: только рамка карты — без стрелки севера и линейки
            x, y, w, h = rect
            out.append({"op": "path", "closed": True, "fill": None, "stroke": (0, 0, 0), "width": 0.5, "dash": None,
                        "rings": [[(x, y), (x + w, y), (x + w, y + h), (x, y + h)]]})
        else:
            out.extend(self._frame_marks(rect, k, sh["scale"], small=rect[2] < 150))
        return out

    @staticmethod
    def _callout(sh, tr, rect):
        """Выноска «проектируемая территория»: рамка с текстом сбоку от территории и линия к ней."""
        ring = [tr.mm(*p[:2]) for p in _parts(sh["territory"])[1][0][0]]
        cx, cy = sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
        rx, ry, rw, rh = rect
        lines, ls = [str(t) for t in sh["callout"]][:3], 2.6
        w, h = max(len(t) for t in lines) * ls * .55 + 5, len(lines) * ls * 1.3 + 2.6
        left = cx > rx + rw / 2
        bx = cx - 16 - w if left else cx + 16
        bx = min(max(bx, rx + 3), rx + rw - w - 3)
        by = min(max(cy - 22 - h / 2, ry + 3), ry + rh - h - 3)
        ex, ey = (bx + w if left else bx), by + h / 2                # линия — к ближней стороне рамки
        ops = [{"op": "path", "closed": False, "fill": None, "stroke": (0, 0, 0), "width": .25, "dash": None, "rings": [[(cx, cy), (ex, ey)]]},
               {"op": "circle", "x": cx, "y": cy, "r": .7, "fill": (0, 0, 0), "stroke": None, "width": 0},
               {"op": "path", "closed": True, "fill": (1, 1, 1), "stroke": (0, 0, 0), "width": .3, "dash": None,
                "rings": [[(bx, by), (bx + w, by), (bx + w, by + h), (bx, by + h)]]}]
        for i, t in enumerate(lines):
            ops.append({"op": "text", "x": bx + w / 2, "y": by + 1.3 + ls * 1.05 + i * ls * 1.3, "size": ls, "text": t, "anchor": "middle",
                        "color": (0.1, 0.1, 0.1)})
        return (bx, by, bx + w, by + h), ops

    @staticmethod
    def _frame_marks(rect, k, scale, small=False):
        x, y, w, h = rect
        out = [{"op": "path", "closed": True, "fill": None, "stroke": (0, 0, 0), "width": 0.5, "dash": None,
                "rings": [[(x, y), (x + w, y), (x + w, y + h), (x, y + h)]]}]
        # стрелка севера: карта в МСК, север — вверх листа
        nx, ny = x + 10, y + 8
        out.append({"op": "path", "closed": True, "fill": (0, 0, 0), "stroke": (0, 0, 0), "width": 0.2, "dash": None,
                    "rings": [[(nx, ny), (nx + 3, ny + 10), (nx, ny + 7.5)]]})
        out.append({"op": "path", "closed": True, "fill": (1, 1, 1), "stroke": (0, 0, 0), "width": 0.2, "dash": None,
                    "rings": [[(nx, ny), (nx - 3, ny + 10), (nx, ny + 7.5)]]})
        out.append({"op": "text", "x": nx, "y": ny - 1.5, "size": 3.2, "text": "С", "anchor": "middle"})
        # масштабная линейка: около 50 мм, четыре деления
        m = _nice((30 if small else 50) / k)
        L, bx, by = m * k, x + 6, y + h - 8
        for i in range(4):
            out.append({"op": "path", "closed": True, "fill": (0, 0, 0) if i % 2 == 0 else (1, 1, 1), "stroke": (0, 0, 0), "width": 0.2,
                        "dash": None, "rings": [[(bx + L * i / 4, by), (bx + L * (i + 1) / 4, by), (bx + L * (i + 1) / 4, by + 1.5), (bx + L * i / 4, by + 1.5)]]})
        for i in (0, 2, 4):
            v = m * i / 4
            out.append({"op": "text", "x": bx + L * i / 4, "y": by - 1, "size": 2.2, "text": f"{v:g}", "anchor": "middle"})
        out.append({"op": "text", "x": bx + L + 3, "y": by + 1.5, "size": 2.2, "text": f"м   М 1:{int(scale):,}".replace(",", " ")})
        return out


class ColumnFrame(Frame):
    """Правая колонка: заголовок листа, легенда вида, таблица ТЭП (что влезет по высоте)."""

    def __init__(self, rect, sheet, title=True):
        super().__init__(rect)
        self.sheet, self.title = sheet, title

    def ops(self, ctx):
        x, y, w, h = self.rect
        sh, out = self.sheet, []
        yy = y + 5
        if self.title:
            for line in _wrap(sh.get("title", ""), int(w / 2.4)):
                out.append({"op": "text", "x": x, "y": yy, "size": 4.2, "text": line})
                yy += 6
            yy += 3
        tbl = sh.get("table")
        if tbl and tbl.get("rows"):
            # таблица листа (участки ЕГРН, функциональные зоны): над легендой, сколько поместится
            room = max(0, int((h * .55) / TableFrame.ROW_H) - 1)
            rows = tbl["rows"][:room]
            cols = tbl.get("cols") or [("", w, "left")]
            t = TableFrame((x, yy, w, 0), [(c[0], w * c[1], c[2]) for c in cols], rows, title=tbl.get("title", ""))
            out.extend(t.ops(ctx))
            yy += (len(rows) + 2) * TableFrame.ROW_H + 7
            if len(rows) < len(tbl["rows"]):
                out.append({"op": "text", "x": x, "y": yy - 2, "size": 2.2, "text": f"… ещё {len(tbl['rows']) - len(rows)} строк"})
                yy += 3
        if sh.get("legend"):
            out.append({"op": "text", "x": x, "y": yy, "size": 3.2, "text": "Условные обозначения"})
            yy += 6
        full = False
        for grp in sh.get("legend", []):
            if full:
                break
            if yy > y + h - 30:
                full = True
            items = grp.get("items") or [grp]
            if not full and len(items) > 1:
                for line in _wrap(grp["title"], int(w / 1.45)):
                    out.append({"op": "text", "x": x, "y": yy, "size": 2.6, "text": line})
                    yy += 3.4
                yy += 1.1
            for it in items[:14]:
                if full or yy > y + h - 8:            # место проверяется на каждой строке, иначе легенда наезжает на штамп
                    full = True
                    break
                # длинная строка легенды переносится целиком, сколько бы строк ни понадобилось (владелец 03.10.2026);
                # не помещается — легенда обрывается по строкам, а не внутри подписи
                lines = _wrap(str(it.get("label") or grp["title"]), int((w - 13) / 1.3))
                if yy + (len(lines) - 1) * 3 > y + h - 8:
                    full = True
                    break
                out.extend(_swatch(x, yy - 3, grp.get("kind", "poly"), it))
                for i, line in enumerate(lines):
                    out.append({"op": "text", "x": x + 13, "y": yy + i * 3, "size": 2.4, "text": line})
                yy += 4.8 + (len(lines) - 1) * 3
            yy += 1.5
        if full:
            out.append({"op": "text", "x": x, "y": min(yy, y + h - 3), "size": 2.4, "text": "… легенда не поместилась"})
            yy += 5
        if sh.get("note") and yy < y + h - 8:
            for line in _wrap(sh["note"], int(w / 1.3)):
                out.append({"op": "text", "x": x, "y": yy + 2, "size": 2.3, "text": line, "color": (0.3, 0.3, 0.3)})
                yy += 3.4
        # нумерованные списки документов (ППТ и ПМТ, ГПЗУ и АГР): номер — тот же, что у документа на карте
        for blk in sh.get("lists") or []:
            if yy > y + h - 12:
                break
            yy += 3
            for line in _wrap(blk["title"], int(w / 1.45)):
                out.append({"op": "text", "x": x, "y": yy, "size": 2.8, "text": line, "font_family": "ui-bold"})
                yy += 3.8
            for n, item in enumerate(blk["items"]):
                lines = _wrap(item, int(w / 1.12))
                if yy + len(lines) * 2.9 > y + h - 3:
                    out.append({"op": "text", "x": x, "y": min(yy + 1, y + h - 1), "size": 2.3, "color": (0.3, 0.3, 0.3),
                                "text": f"… ещё {len(blk['items']) - n} — на карте их номера есть"})
                    yy = y + h
                    break
                for line in lines:
                    out.append({"op": "text", "x": x, "y": yy, "size": 2.3, "text": line})
                    yy += 2.9
                yy += 1.1
        tep = sh.get("tep") or []
        if tep:
            yy += 3
            room = int((y + h - yy - 10) / TableFrame.ROW_H) - 1
            rows = tep[:max(0, room)]
            if rows:
                t = TableFrame((x, yy, w, 0), [("Показатель", w * .68, "left"), ("Значение", w * .32, "right")], rows, title="Технико-экономические показатели")
                out.extend(t.ops(ctx))
            if len(rows) < len(tep):
                out.append({"op": "text", "x": x, "y": y + h - 2, "size": 2.2, "text": f"… ещё {len(tep) - len(rows)} строк — на листе ТЭП"})
        return out


class TepSheetFrame(Frame):
    """Лист «Таблица ТЭП»: все показатели над штампом, при нехватке высоты — во вторую и третью колонку."""

    def __init__(self, rect, sheet):
        super().__init__(rect)
        self.sheet = sheet

    def ops(self, ctx):
        x, y, w, h = self.rect
        sh, out = self.sheet, []
        out.append({"op": "text", "x": x, "y": y + 6, "size": 5, "text": sh.get("title") or "Технико-экономические показатели"})
        rows, top = sh.get("tep") or [], y + 14
        if not rows:
            out.append({"op": "text", "x": x, "y": top + 6, "size": 3, "text": "Показатели не посчитаны: задайте территорию и эскиз."})
            return out
        per = max(1, int((y + h - top - 8) / TableFrame.ROW_H) - 1)            # строк в колонке (без заголовка таблицы)
        cols = [rows[i:i + per] for i in range(0, len(rows), per)]
        gap, n = 8, min(len(cols), 3)
        cw = min(180, (w - gap * (n - 1)) / n)                                 # одна колонка не растягивается на весь лист
        for i, part in enumerate(cols[:n]):
            t = TableFrame((x + i * (cw + gap), top, cw, 0), [("Показатель", cw * .7, "left"), ("Значение", cw * .3, "right")], part)
            out.extend(t.ops(ctx))
        if len(cols) > n:
            out.append({"op": "text", "x": x, "y": y + h - 2, "size": 2.4, "text": f"… не поместилось строк: {sum(map(len, cols[n:]))} — возьмите формат А1"})
        return out


def _wrap(text, n):
    # неразрывный пробел (U+00A0) держит вместе «S = 16,64 га»; в строке он печатается обычным пробелом
    words, lines, cur = [w for w in str(text).replace("\n", " ").split(" ") if w], [], ""
    for wd in words:
        if len(cur) + len(wd) + 1 > n and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = (cur + " " + wd).strip()
    return [ln.replace("\u00a0", " ") for ln in lines + ([cur] if cur else [])]


def _view_mark(x, y, bearing, color):
    """Точка съёмки как в «ГК Царицыно»: синяя стрелка-наконечник по направлению снимка (азимут от севера по часовой)."""
    b = math.radians(bearing)
    ux, uy, px, py = math.sin(b), -math.cos(b), math.cos(b), math.sin(b)       # вдоль направления и поперёк (лист: y вниз)
    pt = lambda a, c: (x + ux * a + px * c, y + uy * a + py * c)
    return [{"op": "path", "closed": True, "fill": color, "stroke": (1, 1, 1), "width": 0.25, "dash": None,
             "rings": [[pt(3.8, 0), pt(-2.3, 3.2), pt(-0.9, 0), pt(-2.3, -3.2)]]}]


def _swatch(x, y, kind, it):
    fill, stroke = it.get("fill"), it.get("stroke")
    if kind == "line":
        return [{"op": "path", "closed": False, "fill": None, "stroke": hex_to_rgb(fill or stroke or "#333333"), "width": 0.6, "dash": None,
                 "rings": [[(x + 1, y + 1.8), (x + 10, y + 1.8)]]}]
    if kind == "point":
        return [{"op": "circle", "x": x + 5.5, "y": y + 1.8, "r": 1.2, "fill": hex_to_rgb(fill or "#666666"), "stroke": (0.2, 0.2, 0.2), "width": 0.15}]
    rect = [[(x + 1, y), (x + 10, y), (x + 10, y + 3.6), (x + 1, y + 3.6)]]
    edge = hex_to_rgb(stroke or fill or "#555555")
    if min(edge) > .92:                                   # белая граница (слайды на снимке) на белой легенде не видна
        edge = (0.6, 0.6, 0.6)
    out = [{"op": "path", "closed": True, "fill": None if it.get("hatch") else _mix(fill or "#dddddd", it.get("a", 1)),
            "stroke": edge, "width": 0.2, "dash": None, "rings": rect}]
    if it.get("hatch") and fill:
        out.extend(hatch_ops(rect, spacing=1.0, stroke=hex_to_rgb(fill)))
    return out


class SlideFrame(Frame):
    """Оформление слайда презентации (как «ППТ …» в альбоме раздела): стрелка и заголовок слева сверху, шапка
    проекта справа сверху, номер слайда справа снизу; у титульного слайда — название проекта крупно и дата."""

    def __init__(self, page, sheet, meta):
        super().__init__((0, 0) + tuple(page.size))
        self.sheet, self.meta = sheet, meta

    def ops(self, ctx):
        w, h = self.rect[2], self.rect[3]
        sh, m, out = self.sheet, self.meta, []
        ink = (0.1, 0.1, 0.1)
        k = slide_k(sh.get("size")) if sh.get("size") in SLIDES else 1   # на А3 и А2 оформление крупнее, как увеличенный слайд
        if sh.get("kind") == "title":
            yy = h * .36
            for line in _wrap(m.get("object") or sh.get("title", ""), 44):
                out.append({"op": "text", "x": 16 * k, "y": yy, "size": 7.2 * k, "text": line, "color": ink, "font_family": "serif"})
                yy += 9 * k
            if m.get("place"):
                out.append({"op": "text", "x": 16 * k, "y": yy + 3 * k, "size": 5.2 * k, "text": f"({m['place']})", "color": ink, "font_family": "serif"})
            if m.get("date"):
                out.append({"op": "text", "x": 16 * k, "y": h - 26 * k, "size": 5.2 * k, "text": m["date"], "color": ink, "font_family": "serif"})
            return out
        short = m.get("short") or m.get("object") or ""
        if short:
            out.append({"op": "text", "x": w - 8 * k, "y": 9 * k, "size": 3.4 * k, "text": short, "color": ink, "anchor": "end", "font_family": "serif"})
        if m.get("place"):
            out.append({"op": "text", "x": w - 8 * k, "y": 13.6 * k, "size": 3.4 * k, "text": f"({m['place']})", "color": ink, "anchor": "end", "font_family": "serif"})
        out.append({"op": "path", "closed": False, "fill": None, "stroke": ink, "width": .5 * k, "dash": None,
                    "rings": [[(0, 19 * k), (16 * k, 19 * k)], [(13.5 * k, 17.6 * k), (16 * k, 19 * k), (13.5 * k, 20.4 * k)]]})
        out.append({"op": "text", "x": 19 * k, "y": 20.2 * k, "size": 3.8 * k, "text": sh.get("title", ""), "color": ink, "font_family": "serif"})
        out.append({"op": "text", "x": w - 8 * k, "y": h - 4 * k, "size": 3.0 * k, "text": ctx.get("page_no", ""), "color": (0.4, 0.4, 0.4), "anchor": "end"})
        return out


def photo_map_rect(size):
    """Слайд фотофиксации: карта — левые 47 % места под картой, справа снимки."""
    x, y, w, h = layout(size)[0]
    return (x, y, w * .47, h)


def panel_rects(rect, n, gap=6, cap=11):
    """Несколько карт на одном слайде (схемы ПЗЗ, округ и район): рамки в ряд, над каждой — подпись."""
    x, y, w, h = rect
    pw = (w - gap * (n - 1)) / n
    return [(x + i * (pw + gap), y + cap, pw, h - cap) for i in range(n)]


class PanelFrame(SketchMapFrame):
    """Одна из карт слайда с подписью над рамкой."""

    def ops(self, ctx):
        out = super().ops(ctx)
        x, y, w, _ = self.rect
        for i, line in enumerate(_wrap(self.sheet.get("caption", ""), int(w / 1.45))[:3][::-1]):
            out.append({"op": "text", "x": x + w / 2, "y": y - 2 - i * 3.4, "size": 2.9, "text": line, "anchor": "middle",
                        "color": (0.1, 0.1, 0.1), "font_family": "serif"})
        return out


class PhotoGridFrame(Frame):
    """Материалы фотофиксации: снимки сеткой с номерами (номера — те же, что у точек съёмки на карте)."""

    def __init__(self, rect, sheet):
        super().__init__(rect)
        self.sheet = sheet

    def ops(self, ctx):
        import album_io
        x, y, w, h = self.rect
        photos = [(p, raw) for p, raw in ((p, album_io.photo_bytes(p)) for p in self.sheet.get("photos", []) if p.get("data")) if raw][:12]
        if not photos:
            return [{"op": "text", "x": x + w / 2, "y": y + h / 2, "size": 3.2, "anchor": "middle", "color": (0.45, 0.45, 0.45),
                     "text": "Снимки не добавлены: окно «Листы», кнопка с фотоаппаратом у этого слайда"}]
        n = len(photos)
        cols = 1 if n == 1 else 2 if n <= 4 else 3
        rows = math.ceil(n / cols)
        gap = 2.5
        cw, ch = (w - gap * (cols - 1)) / cols, (h - gap * (rows - 1)) / rows
        out = []
        for i, (p, raw) in enumerate(photos):
            cx, cy = x + (i % cols) * (cw + gap), y + (i // cols) * (ch + gap)
            pw, ph = float(p.get("w") or 4), float(p.get("h") or 3)
            k = min(cw / pw, ch / ph)                                  # снимок целиком, по центру ячейки
            iw, ih = pw * k, ph * k
            ix, iy = cx + (cw - iw) / 2, cy
            out.append({"op": "image", "data": raw, "x": ix, "y": iy, "w": iw, "h": ih})
            out.append({"op": "path", "closed": True, "fill": (1, 1, 1), "stroke": None, "width": 0, "dash": None,
                        "rings": [[(ix, iy), (ix + 6, iy), (ix + 6, iy + 5), (ix, iy + 5)]]})
            out.append({"op": "text", "x": ix + 3, "y": iy + 3.8, "size": 3, "text": str(i + 1), "anchor": "middle", "color": (0.1, 0.1, 0.1)})
        return out


def build_document(spec, lib, lgr_dash, tiles=None):
    meta = {"object": spec.get("meta", {}).get("object", ""), "code": spec.get("meta", {}).get("code", ""),
            "stage": spec.get("meta", {}).get("stage", ""), "org": spec.get("meta", {}).get("org", "")}
    doc = Document(meta["object"] or "Альбом", meta=meta)
    doc.sheet_titles = []
    memo = {}                                                       # места подписей, общие для листов одной рамки
    for sh in spec["sheets"]:
        size = sh.get("size") if sh.get("size") in SIZES else "A3"
        page = Page(page_size(size, sh.get("orient")))
        if sh.get("style") == "pptkrt":                     # альбом по шаблону ППТ КРТ владельца (album_io.py)
            import album_io
            meta_p = {**meta, **(spec.get("meta") or {})}
            page.frames = album_io.build_pptkrt(page, sh, meta_p, lib, lgr_dash, tiles,
                                                lambda rect, s: SketchMapFrame(rect, s, lib, lgr_dash, tiles, memo))
            doc.pages.append(page)
            doc.sheet_titles.append(sh.get("title", ""))
            continue
        if size in PAPER:
            w, h = page.size
            map_rect = (w * PAPER_MARGIN, h * PAPER_MARGIN, w * (1 - 2 * PAPER_MARGIN), h * (1 - 2 * PAPER_MARGIN))
            page.frames = [SketchMapFrame(map_rect, sh, lib, lgr_dash, tiles, memo), PaperFrame(map_rect, sh)]
            doc.pages.append(page)
            doc.sheet_titles.append(sh.get("title", ""))
            continue
        map_rect, col_rect = layout(size)
        if size in SLIDES:
            meta_p = {**meta, **(spec.get("meta") or {})}
            if sh.get("kind") == "title":
                page.frames = [SlideFrame(page, sh, meta_p)]
            elif sh.get("kind") == "photos":
                w, h = SIZES[size]
                mr = photo_map_rect(size)
                page.frames = [SketchMapFrame(mr, sh, lib, lgr_dash, tiles, memo), PhotoGridFrame((mr[0] + mr[2] + 5, mr[1], w - 8 - mr[0] - mr[2] - 5, mr[3]), sh),
                               SlideFrame(page, sh, meta_p)]
            elif sh.get("panels"):
                page.frames = [PanelFrame(r, p, lib, lgr_dash, tiles) for r, p in zip(panel_rects(map_rect, len(sh["panels"])), sh["panels"])] + \
                    [ColumnFrame(col_rect, sh, title=False), SlideFrame(page, sh, meta_p)]
            else:
                page.frames = [SketchMapFrame(map_rect, sh, lib, lgr_dash, tiles, memo), ColumnFrame(col_rect, sh, title=False), SlideFrame(page, sh, meta_p)]
        elif sh.get("kind") == "tep":
            w, h = SIZES[size]
            page.frames = [PageBorder(page), TepSheetFrame((25, 10, w - 25 - 10, h - 5 - StampFrame.H - 10 - 3), sh), StampFrame(page)]
        else:
            page.frames = [PageBorder(page), SketchMapFrame(map_rect, sh, lib, lgr_dash), ColumnFrame(col_rect, sh), StampFrame(page)]
        doc.pages.append(page)
        doc.sheet_titles.append(sh.get("title", ""))
    return doc


# шрифты редактора макета — те, что есть у ядра (PDF встраивает их файлы, поэтому лист и PDF совпадают)
FONTS = ("ui", "ui-bold", "sans", "sans-bold", "serif", "serif-bold")


def apply_edits(ops, sheet, seen=None, items=True):
    """Правка готового листа (редактор макета): у каждой надписи листа ключ «текст#n» (n — какая по счёту такая же надпись
    на странице), по ключу — правка: сдвиг dx/dy (мм), кегль (мм), цвет, шрифт, обводка [цвет, мм], поворот (°), свой
    текст, скрыть. Свои надписи листа (items) дописываются сверху. Ключ не хранит координат: подпись найдётся и после
    пересборки листа, пока у неё тот же текст. seen — счётчик, общий для всех рамок страницы (PPTX идёт по рамкам)."""
    edits, out = sheet.get("edits"), []
    edits = edits if isinstance(edits, dict) else {}
    seen = {} if seen is None else seen
    for o in ops:
        if o.get("op") != "text":
            out.append(o)
            continue
        n = seen.get(o["text"], 0)
        seen[o["text"]] = n + 1
        o = {**o, "key": f"{o['text']}#{n}"}
        e = edits.get(o["key"])
        if isinstance(e, dict):
            if e.get("hide"):
                continue
            o = _edited(o, e)
        out.append(o)
    if items:
        out.extend(own_texts(sheet))
    return out


def own_texts(sheet):
    out, items = [], sheet.get("items")
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and str(it.get("text") or "").strip():
            o = {"op": "text", "x": _num(it.get("x")), "y": _num(it.get("y")), "size": 3.0, "text": str(it["text"]),
                 "color": (0.1, 0.1, 0.1), "key": f"item:{it.get('id')}"}
            out.append(_edited(o, {k: v for k, v in it.items() if k not in ("x", "y", "text")}))
    return out


def _num(v, d=0.0):
    """Число из правки макета; не число (файл, правленный руками) — d."""
    try:
        return float(v) if v not in (None, "") else d
    except (TypeError, ValueError):
        return d


def _edited(o, e):
    rgb = lambda c, d: hex_to_rgb(c) if isinstance(c, str) and c.startswith("#") else d
    o = dict(o)
    o["x"] += _num(e.get("dx"))
    o["y"] += _num(e.get("dy"))
    if isinstance(e.get("text"), str) and e["text"].strip():
        o["text"] = e["text"]
    if _num(e.get("size")) > 0:
        o["size"] = max(.5, min(60.0, _num(e["size"])))
    if e.get("color"):
        o["color"] = rgb(e["color"], o.get("color"))
    if e.get("font") in FONTS:
        o["font_family"] = e["font"]
    if e.get("angle") not in (None, ""):
        o["angle"] = math.radians(_num(e["angle"]))
    h = e.get("halo")
    if isinstance(h, (list, tuple)) and len(h) == 2:
        o["halo"], o["halo_color"] = max(.05, min(3.0, _num(h[1], .6))), rgb(h[0], (1, 1, 1))
    elif "halo" in e and not h:
        o.pop("halo", None)
        o.pop("halo_color", None)
    return o


def _pages(spec, lib, lgr_dash, tiles):
    pages = document_pages_ops(build_document(spec, lib, lgr_dash, tiles), None)
    return [(w, h, apply_edits(ops, sh)) for (w, h, ops), sh in zip(pages, spec["sheets"])]


def render_pdf(spec, lib, lgr_dash, tiles=None):
    return PdfBackend(None).render(_pages(spec, lib, lgr_dash, tiles))


def not_ready(spec):
    """Номера листов с пометкой «не готов» (album_io._not_ready): что-то не поместилось, а мельчить и обрывать молча
    нельзя (владелец 01.10.2026). Читается после сборки PDF или PPTX."""
    return [i for i, sh in enumerate(spec.get("sheets") or [], start=1) if isinstance(sh, dict) and sh.get("_notReady")]


# рамки листа → группы фигур в PPTX
PPTX_GROUPS = {"SketchMapFrame": "Карта", "PanelFrame": "Карта", "ColumnFrame": "Легенда", "PhotoGridFrame": "Фотографии",
               "CalloutFrame": "Выноска", "OkrugTitleFrame": "Название округа", "MapNoteFrame": "Округ и район", "ConceptColumnFrame": "Легенда", "OrthoLegendFrame": "Легенда", "ConceptPhotoFrame": "Фотографии", "StampFrame": "Штамп", "PageBorder": "Рамка листа",
               "TepSheetFrame": "ТЭП", "LegendFrame": "Легенда", "TableFrame": "Таблица"}


# ---------- PPTX: тайлы подложки по рамке карты, тяжёлые карты — растром ----------

PPTX_MAX_SHAPES = 20000          # больше фигур на слайде — карта уходит растром (LibreOffice на 244 тыс. фигур не открыл за 9 мин)
PPTX_MAX_XML = 16e6              # или оценка XML слайда больше этого (байт)
PPTX_DPI = 200                   # разрешение растра карты
PPTX_SUBPIXEL = 0.25 * 25.4 / 72  # 0,25 пт в мм: мельче глаз на листе не различает


def _op_box(ops):
    """Текущая рамка обрезки по операциям: пересечение прямоугольных clip (кольцевые — по охвату)."""
    stack = []
    for o in ops:
        if o["op"] == "clip":
            if o.get("rect"):
                x, y, w, h = o["rect"]
                b = (x, y, x + w, y + h)
            else:
                pts = [p for r in o.get("rings") or [] for p in r]
                b = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)) if pts else None
            stack.append(b)
        elif o["op"] == "unclip" and stack:
            stack.pop()
    return stack


def _meet_box(a, b):
    if a is None or b is None:
        return a or b
    return (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))


def _quad_info(quad):
    (tlx, tly), (trx, try_), (blx, bly) = quad
    ux, uy, vx, vy = trx - tlx, try_ - tly, blx - tlx, bly - tly
    corners = [(tlx, tly), (trx, try_), (trx + vx, try_ + vy), (blx, bly)]
    w, h = math.hypot(ux, uy), math.hypot(vx, vy)
    cx, cy = (trx + blx) / 2, (try_ + bly) / 2                       # так PPTX-бэкенд ставит повёрнутый рисунок
    return corners, (ux, uy, vx, vy), (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def _inside(b, box):
    return b[0] >= box[0] and b[1] >= box[1] and b[2] <= box[2] and b[3] <= box[3]


def _tile_patch(data, quad, box, ppmm=None):
    """Часть тайла-параллелограмма внутри box (мм) как прямоугольная картинка (PIL RGBA) по осям листа.
    Возвращает (картинка, (x0, y0, x1, y1) мм) или None, если тайл вне box. ppmm — пикселей на мм (по умолчанию как у тайла)."""
    import io
    from PIL import Image
    corners, (ux, uy, vx, vy), _ = _quad_info(quad)
    poly = clip_ring(corners, (box[0], box[1], box[2] - box[0], box[3] - box[1]), pad=0)
    if len(poly) < 3:
        return None
    bx0, by0 = min(p[0] for p in poly), min(p[1] for p in poly)
    bx1, by1 = max(p[0] for p in poly), max(p[1] for p in poly)
    if bx1 - bx0 < 1e-6 or by1 - by0 < 1e-6:
        return None
    im = Image.open(io.BytesIO(data)).convert("RGB")
    W, H = im.size
    ppmm = ppmm or W / (math.hypot(ux, uy) or 1)
    ow, oh = max(1, min(4096, int(math.ceil((bx1 - bx0) * ppmm)))), max(1, min(4096, int(math.ceil((by1 - by0) * ppmm))))
    sx, sy, det = (bx1 - bx0) / ow, (by1 - by0) / oh, (ux * vy - uy * vx) or 1e-9
    tlx, tly = quad[0]
    coef = (sx * vy / det * W, -sy * vx / det * W, ((bx0 - tlx) * vy - (by0 - tly) * vx) / det * W,
            -uy * sx / det * H, ux * sy / det * H, (ux * (by0 - tly) - uy * (bx0 - tlx)) / det * H)
    warped = im.transform((ow, oh), Image.AFFINE, coef, Image.BILINEAR)
    alpha = Image.new("L", im.size, 255).transform((ow, oh), Image.AFFINE, coef, Image.BILINEAR)
    out = im.resize((ow, oh)).convert("RGBA")               # подложка из самого тайла: на срезе нет чёрной каёмки
    out.paste(warped, (0, 0), alpha)
    area = abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]))) / 2
    if area < 0.995 * (bx1 - bx0) * (by1 - by0):             # по краям внутри рамки остаются углы чужих тайлов
        out.putalpha(alpha)
    return out, (bx0, by0, bx1, by1)


def pptx_clip_tiles(ops):
    """Тайлы подложки, торчащие за рамку карты, режутся по рамке (PPTX не умеет обрезку: PDF режет clip-ом).
    Рисунок почти без поворота кадрируется бэкендом (srcRect); повёрнутый перерисовывается прямоугольным куском
    внутри рамки. Целые тайлы остаются как есть."""
    import io
    out, stack = [], []
    for o in ops:
        if o["op"] == "clip":
            stack.append(o)
        elif o["op"] == "unclip" and stack:
            stack.pop()
        if o["op"] != "image" or "quad" not in o or not stack:
            out.append(o)
            continue
        box = None
        for c in stack:
            if c.get("rect"):
                x, y, w, h = c["rect"]
                box = _meet_box(box, (x, y, x + w, y + h))
        if box is None:
            out.append(o)
            continue
        corners, (ux, uy, vx, vy), plain = _quad_info(o["quad"])
        xs, ys = [p[0] for p in corners], [p[1] for p in corners]
        if _inside((min(xs), min(ys), max(xs), max(ys)), box) and _inside(plain, box):
            out.append(o)
        elif max(xs) < box[0] or min(xs) > box[2] or max(ys) < box[1] or min(ys) > box[3]:
            continue
        elif max(abs(uy), abs(vx)) < 0.05:                       # поворот меньше полупикселя: прямой рисунок, обрежет бэкенд
            out.append({"op": "image", "data": o["data"], "x": o["quad"][0][0], "y": o["quad"][0][1], "w": ux, "h": vy})
        else:
            got = _tile_patch(o["data"], o["quad"], box)
            if got is None:
                continue
            im, (x0, y0, x1, y1) = got
            buf = io.BytesIO()
            if im.getchannel("A").getextrema()[0] == 255:
                im.convert("RGB").save(buf, "JPEG", quality=88)
            else:
                im.save(buf, "PNG")
            out.append({"op": "image", "data": buf.getvalue(), "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0})
    return out


def pptx_thin(ops):
    """Фигуры, которых на листе не видно, в PPTX не нужны: замкнутые контуры мельче 0,25 пт пропускаются, подробные
    кольца упрощаются (Дуглас — Пекер, 0,25 пт)."""
    out = []
    for o in ops:
        if o["op"] != "path":
            out.append(o)
            continue
        rings = []
        for r in o["rings"]:
            if len(r) >= 20:
                s = _simplify(list(r), PPTX_SUBPIXEL)
                r = s if len(s) >= (3 if o.get("closed") else 2) else r
            rings.append(r)
        xs, ys = [p[0] for r in rings for p in r], [p[1] for r in rings for p in r]
        # крошечный замкнутый контур пропускается, только если у него нет заметной обводки (точка 0,5 мм линией — видна)
        if o.get("closed") and xs and max(xs) - min(xs) < PPTX_SUBPIXEL and max(ys) - min(ys) < PPTX_SUBPIXEL \
                and not (o.get("fill") is None and (o.get("width") or 0) > PPTX_SUBPIXEL):
            continue
        out.append({**o, "rings": rings})
    return out


def pptx_weight(ops):
    """(число фигур, оценка веса XML в байтах) слайда по операциям рамки; линии без заливки одного вида подряд
    бэкенд сливает в одну фигуру, как и здесь."""
    shapes = pts = 0
    prev = None
    for o in ops:
        t = o["op"]
        if t == "path":
            n = sum(len(r) for r in o["rings"])
            pts += n
            if o.get("fill") is None:
                key = (bool(o.get("closed")), tuple(o["stroke"] or ()), o.get("width"), tuple(o.get("dash") or ()))
                if key != prev:
                    shapes += 1
                prev = key
            else:
                shapes += 1
                prev = None
        else:
            prev = None
            shapes += t in ("text", "circle", "image") or (t == "clip" and bool(o.get("rings")))
    return shapes, shapes * 600 + pts * 55


def _dash_runs(pts, dash):
    """Ломаная (мм) → куски штриха: dash — [штрих, пробел, ...] в мм."""
    pat = [max(0.05, float(v)) for v in dash] or [1.0]
    pat = pat * (2 if len(pat) % 2 else 1)
    runs, cur, i, left, on = [], [pts[0]], 0, pat[0], True
    for a, b in zip(pts, pts[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        pos = 0.0
        while d - pos > left:
            pos += left
            p = (a[0] + (b[0] - a[0]) * pos / d, a[1] + (b[1] - a[1]) * pos / d)
            if on:
                cur.append(p)
                runs.append(cur)
            cur = [p]
            on = not on
            i = (i + 1) % len(pat)
            left = pat[i]
        left -= d - pos
        if on:
            cur.append(b)
    if on and len(cur) > 1:
        runs.append(cur)
    return runs


def pptx_rasterize(ops, dpi=PPTX_DPI):
    """Операции карты → список из одной картинки PNG (все контуры и снимки, с обрезкой) и поверх неё подписей и значков
    векторно. Рамка — внешний clip карты; без него рисунок всей карты по охвату контуров."""
    import io
    from PIL import Image, ImageChops, ImageDraw
    box = None
    for c in ops:
        if c["op"] == "clip" and c.get("rect"):
            x, y, w, h = c["rect"]
            box = (x, y, x + w, y + h)
            break
    if box is None:
        pts = [p for o in ops if o["op"] == "path" for r in o["rings"] for p in r]
        if not pts:
            return ops
        box = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
    x0, y0, x1, y1 = box
    pmm = dpi / 25.4
    W, H = max(1, int(round((x1 - x0) * pmm))), max(1, int(round((y1 - y0) * pmm)))
    ss = 2 if W * H * 4 <= 36e6 else 1                               # сглаживание: рисуем вдвое крупнее и уменьшаем
    k, cw, ch = pmm * ss, W * ss, H * ss
    px = lambda p: ((p[0] - x0) * k, (p[1] - y0) * k)
    layers = [Image.new("RGBA", (cw, ch), (0, 0, 0, 0))]
    masks = []

    def poly_mask(rings):
        m = Image.new("1", (cw, ch), 0)
        for r in rings:
            t = Image.new("1", (cw, ch), 0)
            ImageDraw.Draw(t).polygon([px(p) for p in r], fill=1)
            m = ImageChops.logical_xor(m, t)
        return m.convert("L")

    def blend(layer, rings, color, alpha, bb):
        a = max(0, min(1, float(alpha)))
        ex = [px(p) for r in rings for p in r]
        l, t = max(0, int(min(p[0] for p in ex)) - 1), max(0, int(min(p[1] for p in ex)) - 1)
        r_, b_ = min(cw, int(max(p[0] for p in ex)) + 2), min(ch, int(max(p[1] for p in ex)) + 2)
        if r_ <= l or b_ <= t:
            return
        m = Image.new("1", (r_ - l, b_ - t), 0)
        for r in rings:
            tmp = Image.new("1", m.size, 0)
            ImageDraw.Draw(tmp).polygon([(px(p)[0] - l, px(p)[1] - t) for p in r], fill=1)
            m = ImageChops.logical_xor(m, tmp)
        patch = Image.new("RGBA", m.size, tuple(int(round(v * 255)) for v in color) + (0,))
        patch.putalpha(m.convert("L").point(lambda v: int(v * a)))
        layer.alpha_composite(patch, (l, t))

    rest = []
    for o in ops:
        t = o["op"]
        layer = layers[-1]
        if t == "clip":
            if o.get("rect"):
                x, y, w, h = o["rect"]
                full = x <= x0 and y <= y0 and x + w >= x1 and y + h >= y1
                masks.append(None if full else poly_mask([[(x, y), (x + w, y), (x + w, y + h), (x, y + h)]]))
            else:
                rings = [r for r in o.get("rings") or [] if len(r) >= 3]
                masks.append(poly_mask(rings) if rings else None)
            if masks[-1] is not None:
                layers.append(Image.new("RGBA", (cw, ch), (0, 0, 0, 0)))
        elif t == "unclip":
            if masks:
                m = masks.pop()
                if m is not None:
                    top = layers.pop()
                    top.putalpha(ImageChops.multiply(top.getchannel("A"), m))
                    layers[-1].alpha_composite(top)
        elif t == "path":
            rings = [r for r in o["rings"] if len(r) >= 2]
            if not rings:
                continue
            fill, stroke = o.get("fill"), o.get("stroke")
            if o.get("closed") and fill is not None:
                rgb = tuple(int(round(v * 255)) for v in fill)
                alpha = o.get("alpha")
                if alpha is not None and float(alpha) < 1:
                    blend(layer, rings, fill, alpha, None)
                elif len(rings) == 1:
                    ImageDraw.Draw(layer).polygon([px(p) for p in rings[0]], fill=rgb + (255,))
                else:
                    m = poly_mask(rings)
                    layer.paste(Image.new("RGBA", (cw, ch), rgb + (255,)), (0, 0), m)
            if stroke is not None:
                d = ImageDraw.Draw(layer)
                col = tuple(int(round(v * 255)) for v in stroke) + (255,)
                wpx = max(1, int(round(float(o.get("width") or 0.1) * k)))
                for r in rings:
                    line = list(r) + ([r[0]] if o.get("closed") else [])
                    for run in (_dash_runs(line, o["dash"]) if o.get("dash") else [line]):
                        d.line([px(p) for p in run], fill=col, width=wpx, joint="curve" if wpx > 2 else None)
        elif t == "image":
            try:
                if "quad" in o:
                    got = _tile_patch(o["data"], o["quad"], box, ppmm=k)
                    if got:
                        im, (bx0, by0, bx1, by1) = got
                        layer.alpha_composite(im, (int(round((bx0 - x0) * k)), int(round((by0 - y0) * k))))
                else:
                    im = Image.open(io.BytesIO(o["data"])).convert("RGBA").resize((max(1, int(round(o["w"] * k))), max(1, int(round(o["h"] * k)))))
                    layer.alpha_composite(im.crop((max(0, int(round((x0 - o["x"]) * k))), max(0, int(round((y0 - o["y"]) * k))), im.width, im.height)),
                                          (max(0, int(round((o["x"] - x0) * k))), max(0, int(round((o["y"] - y0) * k)))))
            except Exception:                                            # битый снимок: остальная карта должна собраться
                continue
        elif t in ("text", "circle"):
            rest.append(o)
    while len(layers) > 1:
        top = layers.pop()
        layers[-1].alpha_composite(top)
    img = layers[0].resize((W, H), Image.LANCZOS) if ss > 1 else layers[0]
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return ([{"op": "clip", "rect": (x0, y0, x1 - x0, y1 - y0)}, {"op": "layer", "name": "Карта (растр)"},
             {"op": "image", "data": buf.getvalue(), "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}] + rest + [{"op": "unclip"}])


RASTER_NOTE = "Карта этого слайда вставлена картинкой (PNG, 200 dpi): векторных фигур было слишком много для PowerPoint. Подписи, легенда и рамка остались текстом и фигурами."


def pptx_notes(data, notes):
    """Заметки слайдов к готовому PPTX: notes — {номер слайда: текст}. Добавляет образец заметок, страницы заметок и связи."""
    import io
    import zipfile
    if not notes:
        return data
    src = zipfile.ZipFile(io.BytesIO(data))
    files = {n: src.read(n) for n in src.namelist()}
    ns = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
          'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
    head = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    grp = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
           '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')
    rel = lambda rid, typ, target: (f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/{typ}" Target="{target}"/>')
    rels = lambda body: head + f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{body}</Relationships>'
    files["ppt/theme/theme2.xml"] = files["ppt/theme/theme1.xml"]
    files["ppt/notesMasters/notesMaster1.xml"] = (head + f'<p:notesMaster {ns}><p:cSld><p:spTree>{grp}<p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x="685800" y="4400550"/>'
        '<a:ext cx="5486400" cy="3600450"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/>'
        '<a:p><a:endParaRPr lang="ru-RU"/></a:p></p:txBody></p:sp></p:spTree></p:cSld><p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" '
        'accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/></p:notesMaster>').encode("utf-8")
    files["ppt/notesMasters/_rels/notesMaster1.xml.rels"] = rels(rel("rId1", "theme", "../theme/theme2.xml")).encode("utf-8")
    types = files["[Content_Types].xml"].decode("utf-8")
    add = ('<Override PartName="/ppt/notesMasters/notesMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml"/>'
           '<Override PartName="/ppt/theme/theme2.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>')
    for n, text in sorted(notes.items()):
        files[f"ppt/notesSlides/notesSlide{n}.xml"] = (head + f'<p:notes {ns}><p:cSld><p:spTree>{grp}<p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes"/>'
            '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>'
            f'<a:p><a:r><a:rPr lang="ru-RU"/><a:t>{text.replace("&", "&amp;").replace("<", "&lt;")}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld>'
            '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>').encode("utf-8")
        files[f"ppt/notesSlides/_rels/notesSlide{n}.xml.rels"] = rels(
            rel("rId1", "notesMaster", "../notesMasters/notesMaster1.xml") + rel("rId2", "slide", f"../slides/slide{n}.xml")).encode("utf-8")
        srel = files[f"ppt/slides/_rels/slide{n}.xml.rels"].decode("utf-8")
        files[f"ppt/slides/_rels/slide{n}.xml.rels"] = srel.replace("</Relationships>", rel("rId900", "notesSlide", f"../notesSlides/notesSlide{n}.xml") + "</Relationships>").encode("utf-8")
        add += f'<Override PartName="/ppt/notesSlides/notesSlide{n}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"/>'
    files["[Content_Types].xml"] = types.replace("</Types>", add + "</Types>").encode("utf-8")
    pres = files["ppt/presentation.xml"].decode("utf-8")
    files["ppt/presentation.xml"] = pres.replace("</p:sldMasterIdLst>", '</p:sldMasterIdLst><p:notesMasterIdLst><p:notesMasterId r:id="rId900"/></p:notesMasterIdLst>', 1).encode("utf-8")
    prel = files["ppt/_rels/presentation.xml.rels"].decode("utf-8")
    files["ppt/_rels/presentation.xml.rels"] = prel.replace("</Relationships>", rel("rId900", "notesMaster", "notesMasters/notesMaster1.xml") + "</Relationships>").encode("utf-8")
    buf = io.BytesIO()
    z = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED)
    z.writestr("[Content_Types].xml", files.pop("[Content_Types].xml"))
    for name, blob in files.items():
        z.writestr(name, blob)
    z.close()
    return buf.getvalue()


def render_pptx(spec, lib, lgr_dash, tiles=None):
    """Альбом в редактируемый PPTX: те же листы, что в PDF; каждая рамка листа — группа фигур, подписи — текстом.
    Тайлы подложки режутся по рамке карты; слайд, где фигур больше PPTX_MAX_SHAPES, получает карту картинкой (PNG
    200 dpi) — подписи, легенда и рамка остаются векторными, в заметках слайда сказано, что карта растровая."""
    from grado_layout.compose import _ctx, sheet_titles
    from grado_render.backend_pptx import PptxBackend
    doc = build_document(spec, lib, lgr_dash, tiles)
    titles, pages, notes = sheet_titles(doc), [], {}
    for i, (page, sh) in enumerate(zip(doc.pages, spec["sheets"]), start=1):
        ctx, seen = _ctx(doc, None, None, None, i, titles[i - 1]), {}
        groups = []
        for f in page.frames:
            name, ops = PPTX_GROUPS.get(type(f).__name__, "Оформление"), apply_edits(f.ops(ctx), sh, seen, items=False)
            if name == "Карта":
                ops = pptx_thin(pptx_clip_tiles(ops))
            groups.append((name, ops))
        weights = [pptx_weight(ops) for _, ops in groups]
        total = [sum(w[0] for w in weights), sum(w[1] for w in weights)]
        for j in sorted(range(len(groups)), key=lambda j: -weights[j][0]):          # самая тяжёлая карта — первой
            if total[0] <= PPTX_MAX_SHAPES and total[1] <= PPTX_MAX_XML:
                break
            if groups[j][0] == "Карта":
                ops = pptx_rasterize(groups[j][1])
                groups[j] = (groups[j][0], ops)
                new = pptx_weight(ops)
                total = [total[0] - weights[j][0] + new[0], total[1] - weights[j][1] + new[1]]
                notes[i] = RASTER_NOTE
        own = own_texts(sh)
        pages.append((page.size[0], page.size[1], groups + ([("Свои надписи", own)] if own else [])))
    return pptx_notes(PptxBackend(doc.title).render(pages), notes)


def render_preview_svg(spec, lib, lgr_dash, index=0, tiles=None):
    w, h, ops = _pages(spec, lib, lgr_dash, tiles)[index]
    return render_svg(w, h, ops)
