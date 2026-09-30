"""Листы и альбом ГРАДО 2: PDF, SVG и PPTX через рендер и вёрстку ядра (core/render, core/layout).

Клиент присылает для каждого листа уже оформленные объекты — так лист повторяет карту на экране (стиль
считает тот же код, что рисует слои). Здесь: пересчёт WGS84 → МСК (метры, как в QGIS и в DXF), масштаб листа,
заливки с прозрачностью (смешение с белым: в PDF-писателе ядра альфы нет), штриховки, типы линий REDLN97
(шаблоны LIN и формы SHX — те же данные, что у экрана), легенда, таблица ТЭП, стрелка севера, масштабная
линейка, рамка и основная надпись по ГОСТ Р 21.101 (рамка и штамп — фреймы ядра).
"""

import base64
import math

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


def _pole(rings, clip):
    """Самая глубокая точка фигуры (мм листа) внутри рамки и расстояние от неё до края: туда ставится точка выноски
    или номер, а не на узкий край участка. rings — внешнее кольцо и дыры."""
    outer = rings[0]
    edges = [e for r in rings for e in zip(r, r[1:] + r[:1])]
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
    step = max(x1 - x0, y1 - y0) / 32
    grid = sorted(((depth(x0 + (i + .5) * step, y0 + (j + .5) * step), x0 + (i + .5) * step, y0 + (j + .5) * step)
                   for i in range(int((x1 - x0) / step) + 1) for j in range(int((y1 - y0) / step) + 1)), reverse=True)
    if not grid or grid[0][0] <= 0:
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

    out, rings, t, guard = [], [], 0.0, 0
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
                for path in s["paths"]:
                    ring = []
                    for sx, sy in path:
                        lx, ly = (sx * cr - sy * sr) * sc, (sx * sr + sy * cr) * sc
                        ring.append((ox + lx * ax + ly * bx, oy + lx * ay + ly * by))
                    if len(ring) > 1:
                        rings.append(ring)
    if rings:
        out.append({"op": "path", "closed": False, "fill": None, "stroke": color, "width": width, "dash": None, "rings": rings})
    return out


def tile_ops(tr, rect, scale, tiles, lat):
    """Спутниковая подложка (тайлы Web Mercator, JPEG) под объектами листа: каждый тайл — картинка по трём углам,
    пересчитанным в мм листа (МСК повёрнута относительно Меркатора — тайл ложится параллелограммом)."""
    fx, fy, fw, fh = rect
    half_x, half_y = fw / 2 / tr.k * 1.25, fh / 2 / tr.k * 1.25                 # метры на местности с запасом на поворот
    lon0, lat0 = tr.lon0, tr.lat0
    dlon, dlat = half_x / (111320 * math.cos(math.radians(lat0))), half_y / 110540
    mpp = scale * 0.00025                                                        # метров на пиксель тайла: ~100 dpi на листе
    z = max(10, min(19, round(math.log2(156543.03 * math.cos(math.radians(lat0)) / mpp))))
    n = 2 ** z
    tx = lambda lon: int((lon + 180) / 360 * n)
    ty = lambda la: int((1 - math.asinh(math.tan(math.radians(la))) / math.pi) / 2 * n)
    lon_of = lambda x: x / n * 360 - 180
    lat_of = lambda y: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    x0, x1, y0, y1 = tx(lon0 - dlon), tx(lon0 + dlon), ty(lat0 + dlat), ty(lat0 - dlat)
    if (x1 - x0 + 1) * (y1 - y0 + 1) > 600:
        return []
    out = []
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            data = tiles(z, x, y)
            if not data:
                continue
            tl, trr, bl = tr.mm(lon_of(x), lat_of(y)), tr.mm(lon_of(x + 1), lat_of(y)), tr.mm(lon_of(x), lat_of(y + 1))
            # тайлы внахлёст на пиксель: иначе на стыках снимков просвечивают белые точки
            e, ux, uy, vx, vy = 1 / 256, trr[0] - tl[0], trr[1] - tl[1], bl[0] - tl[0], bl[1] - tl[1]
            tl, trr, bl = ((tl[0] - (ux + vx) * e, tl[1] - (uy + vy) * e), (trr[0] + (ux - vx) * e, trr[1] + (uy - vy) * e),
                           (bl[0] + (vx - ux) * e, bl[1] + (vy - uy) * e))
            out.append({"op": "image", "data": data, "quad": (tl, trr, bl)})
    return out


class SketchMapFrame(Frame):
    """Карта листа из уже оформленных объектов клиента."""

    def __init__(self, rect, sheet, lib, lgr_dash, tiles=None):
        super().__init__(rect)
        self.sheet, self.lib, self.lgr_dash, self.tiles = sheet, lib, lgr_dash, tiles

    def ops(self, ctx):
        sh, rect = self.sheet, self.rect
        tr = MapTransform(rect, sh["center"], sh["scale"])
        k = tr.k
        out, labels, along, placed, runs = [{"op": "clip", "rect": tuple(rect)}], [], {}, [], {}
        if sh.get("basemap") in ("sat", "light") and self.tiles:
            out.append({"op": "layer", "name": "Подложка"})             # метки слоёв — группы фигур в PPTX (PDF их не видит)
            kind = sh["basemap"]
            get = self.tiles if kind == "sat" else (lambda z, x, y: self.tiles(z, x, y, kind))   # спутник — прежний вызов
            out.extend(tile_ops(tr, rect, sh["scale"], get, sh["center"][1]))
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
        for layer in sh.get("layers", []):
            out.append({"op": "layer", "name": layer.get("title") or "Слой"})
            for f in layer.get("features", []):
                kind, parts = _parts(f["g"])
                w = max(0.08, (f.get("w") or 1) * PX_MM)
                stroke = hex_to_rgb(f.get("stroke")) if f.get("stroke") else None
                dash = [max(0.1, float(d) * PX_MM) for d in f["dash"]] if f.get("dash") else None   # штрих карты (пикс.) → мм
                if kind == "poly":
                    best = None                                                 # подпись — одна на объект: у самой большой части
                    for poly in parts:
                        rings = [c for c in (clip_ring([tr.mm(*p[:2]) for p in r], rect) for r in poly) if len(c) >= 3]
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
                            out.extend(_view_mark(x, y, float(f.get("dir") or 0), hex_to_rgb(f.get("fill") or "#1f3fbf")))
                            if f.get("label"):
                                b = math.radians(float(f.get("dir") or 0))
                                labels.append((x - math.sin(b) * 4.2, y + math.cos(b) * 4.2 + 1.8, f["label"], f.get("ls"), f))
                            continue
                        out.append({"op": "circle", "x": x, "y": y, "r": max(0.5, (f.get("w") or 1) * 0.35),
                                    "fill": _mix(f.get("fill") or "#666666", 1), "stroke": stroke or (0.2, 0.2, 0.2), "width": 0.15})
                        if f.get("label"):
                            labels.append((x, y - 2, f["label"], f.get("ls"), f))
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
        grid = {}                                                     # подписи без наложений: первая занявшая место остаётся
        rx, ry, rw, rh = rect
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
                a_ = rings_ and _pole(rings_, clip)
                marks[id(f_)] = (a_[0][0], a_[0][1], a_[0][2], rings_[0], a_) if a_ else (x_, y_ + float(f_.get("ldy") or 0), 0.0, None, [])

        boxes, leads = [], []                                           # все занятые места и линии выносок

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
            take((rx, ry, rx + 102, ry + 7 + 5.4 * n + 3))                  # угол с округом и районом — без подписей карты
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
            moves = [(dx, dy, True) for dx, dy in ((0, 0), (0, -4), (0, 4), (-5, 0), (5, 0), (-5, -4), (5, 4), (5, -4), (-5, 4),
                                                   (0, -8), (0, 8), (-10, 0), (10, 0))] + [(0, 0, False)] if pf.get("nudge") else [(0, 0, False)]
            for dx, dy, av in moves:
                if (x + dx - ex >= rx and x + dx + ex <= rx + rw and y + dy - ey >= ry and y + dy + ey <= ry + rh
                        and take((x + dx - ex, y + dy - ey, x + dx + ex, y + dy + ey), avoid=av)):
                    x, y = x + dx, y + dy
                    break
            else:
                continue
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
            # подписывается и на коротком участке — ближе к своим домам; если чистого места нет, последний проход — без
            # проверки границы. Необязательная улица без чистого места не подписывается.
            hx, hy = tr.mm(*af["mustAt"]) if af.get("mustAt") else (None, None)
            rl = runs.get(text) or [(d, x, y, ang, af)]
            if af.get("must"):
                order = sorted(rl, key=lambda r: (r[0] < tw * 1.1, math.hypot(r[1] - hx, r[2] - hy) if hx is not None and r[0] >= tw * 1.1 else -r[0]))
            else:
                order = sorted((r for r in rl if r[0] >= tw * 1.1), key=lambda r: -r[0])

            def shifts(rd, rx0, ry0, ra):                               # сдвиги вдоль прямого участка, не сходя с него
                m = max(0.0, (rd - tw) / 2)
                ts = [0.0, -m / 2, m / 2, -m, m]
                if hx is not None:
                    ts = [max(-m, min(m, (hx - rx0) * math.cos(ra) + (hy - ry0) * math.sin(ra)))] + [k * m / 3 for k in (0, -3, -2, -1, 1, 2, 3)]
                return ts
            off = ls * .95 + tpad
            cands = [(av, rx0 + math.cos(ra) * t - math.sin(ra) * o, ry0 + math.sin(ra) * t + math.cos(ra) * o, ra)
                     for av in ((True, False) if af.get("must") else (True,)) for o in (0.0, off, -off)
                     for rd, rx0, ry0, ra, _f in order for t in shifts(rd, rx0, ry0, ra)]
            for av, x, y, ang in cands:
                if ang > math.pi / 2 or ang < -math.pi / 2:
                    ang += math.pi                                      # не вверх ногами
                ca, sa = abs(math.cos(ang)), abs(math.sin(ang))
                ex, ey = ca * tw / 2 + sa * ls * .6, sa * tw / 2 + ca * ls * .6
                if x - ex < rx or x + ex > rx + rw or y - ey < ry or y + ey > ry + rh:
                    continue                                            # подпись улицы — целиком в рамке
                if take((x - ex, y - ey, x + ex, y + ey), avoid=av, ob=(x, y, ang, tw / 2, ls * .6)):
                    break
            else:
                continue
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
                for c_ in mk[4]:                                        # точка выноски — не под уже поставленной подписью
                    if not any(b[0] - .5 < c_[0] < b[2] + .5 and b[1] - .5 < c_[1] < b[3] + .5 for b in boxes):
                        mk = marks[id(f)] = (c_[0], c_[1], c_[2], mk[3], mk[4])
                        break
                x, y = mk[0], mk[1] + float(ls or 2.2) * .35 - float(f.get("ldy") or 0)   # кружок — на точке участка
            ls = float(ls or 2.2)
            y += float(f.get("ldy") or 0)
            if not (rx <= x <= rx + rw and ry <= y <= ry + rh):
                continue
            lines = [ln[:40] for ln in str(text).split("\n")[:8]]         # подпись в несколько строк: номер и индекс зоны, коды ВРИ
            lh = ls * 1.23
            y -= (len(lines) - 1) * lh / 2
            fams = f.get("lfs") or []
            bw = max(_text_w(ln, (fams[i] if i < len(fams) and fams[i] else f.get("lf")), ls) for i, ln in enumerate(lines))
            up, down = ls * 1.0, ls * .3 + (len(lines) - 1) * lh              # коробка подписи: y − up … y + down
            if f.get("circle"):                                             # номер в кружке («Хатминки»): коробка — круг
                cr = max(bw / 2 + ls * .25, ls * .62)
                bw, up, down = cr * 2, ls * .35 + cr, cr - ls * .35
            steps = [(0, 0)] + ([(0, -5), (0, 5), (-9, 0), (9, 0), (-9, -5), (9, -5), (-9, 5), (9, 5), (0, -10), (0, 10), (-16, 0), (16, 0)]
                                if ring else [])
            ax, ay = x, y + (len(lines) - 1) * lh / 2 - float(f.get("ldy") or 0)   # точка объекта (для выноски)
            if f.get("circle"):
                ax, ay = mk[0], mk[1]
                inside = mk[2] >= cr + .8 if mk[3] else f.get("inside")     # кружок целиком помещается в свой участок
            else:
                inside = f.get("inside")
            if f.get("leader"):                                             # выноска: подпись рядом, тонкая линия к объекту
                steps = ([(0, 0)] if inside else []) + [(r * math.cos(a), r * math.sin(a)) for r in (9, 13, 18, 24, 32, 42)
                                                        for a in [k * math.pi / 8 for k in (14, 2, 10, 6, 15, 1, 9, 7, 12, 4, 13, 3, 11, 5, 0, 8)]]
            # уровни попыток: у номеров 3 — строго (не на чужом участке), 2 — линия может задеть чужую подпись, 1 — только
            # без пересечения выносок и кружков, 0 — только не поверх других подписей, −1 — на месте как есть (номер
            # участка показывается всегда); у остальных подписей 1 — обычно, 0 — последняя, на месте как есть
            if f.get("circle"):
                tries = [(dx, dy, lvl) for lvl in (3, 2, 1, 0) for dx, dy in steps] + [(0, 0, -1)]
            else:
                tries = [(dx, dy, 1) for dx, dy in steps] + ([(0, 0, 0)] if ring or f.get("leader") else [])
            spot = None
            for dx, dy, lvl in tries:
                cx = min(max(x + dx, rx + bw / 2 + 1), rx + rw - bw / 2 - 1)
                cy = min(max(y + dy, ry + up + 1), ry + rh - down - 1)
                if ring and lvl > 0 and not _in_ring(cx, cy, ring):
                    continue
                if f.get("circle") and lvl > 0 and not free(f, cx, cy - ls * .35, cr, ax, ay, lvl):
                    continue
                if take((cx - bw / 2, cy - up, cx + bw / 2, cy + down), avoid=lvl > 0, own=id(f)) or lvl < 0:
                    spot = (cx, cy)
                    break
            if not spot:
                continue
            x, y = spot
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
                out.append({"op": "text", "x": x, "y": y + i * lh, "size": ls, "text": line, "anchor": "middle",
                            "color": hex_to_rgb(f["lcol"]) if f.get("lcol") else ink, **extra, **fam, **ul})
        if callout:
            out.extend(callout[1])
        out.append({"op": "unclip"})
        for o in out:                                                   # изломы контуров — скруглённые, без острых «шипов»
            if o["op"] == "path":
                o.setdefault("join", "round")
        out.append({"op": "layer", "name": "Рамка"})
        if sh.get("noFrame"):
            pass                                                        # карта без рамки (схемы Москвы в шаблоне ППТ КРТ)
        elif str(sh.get("size", "")).startswith("P"):
            # слайд презентации: только рамка карты — без стрелки севера и линейки (как в альбоме раздела)
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
                for line in _wrap(grp["title"], int(w / 1.45))[:2]:
                    out.append({"op": "text", "x": x, "y": yy, "size": 2.6, "text": line})
                    yy += 3.4
                yy += 1.1
            for it in items[:14]:
                if full or yy > y + h - 8:            # место проверяется на каждой строке, иначе легенда наезжает на штамп
                    full = True
                    break
                out.extend(_swatch(x, yy - 3, grp.get("kind", "poly"), it))
                # длинная строка легенды переносится (до трёх строк), а не обрезается
                lines = _wrap(str(it.get("label") or grp["title"]), int((w - 13) / 1.3))
                if len(lines) > 3:
                    lines = lines[:2] + [lines[2][:max(1, int((w - 13) / 1.3) - 1)] + "…"]
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
            for line in _wrap(blk["title"], int(w / 1.45))[:2]:
                out.append({"op": "text", "x": x, "y": yy, "size": 2.8, "text": line, "font_family": "ui-bold"})
                yy += 3.8
            for n, item in enumerate(blk["items"]):
                lines = _wrap(item, int(w / 1.12))[:4]
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
        x, y, w, h = self.rect
        photos = [p for p in self.sheet.get("photos", []) if p.get("data")][:12]
        if not photos:
            return [{"op": "text", "x": x + w / 2, "y": y + h / 2, "size": 3.2, "anchor": "middle", "color": (0.45, 0.45, 0.45),
                     "text": "Снимки не добавлены: окно «Листы», кнопка с фотоаппаратом у этого слайда"}]
        n = len(photos)
        cols = 1 if n == 1 else 2 if n <= 4 else 3
        rows = math.ceil(n / cols)
        gap = 2.5
        cw, ch = (w - gap * (cols - 1)) / cols, (h - gap * (rows - 1)) / rows
        out = []
        for i, p in enumerate(photos):
            cx, cy = x + (i % cols) * (cw + gap), y + (i // cols) * (ch + gap)
            pw, ph = float(p.get("w") or 4), float(p.get("h") or 3)
            k = min(cw / pw, ch / ph)                                  # снимок целиком, по центру ячейки
            iw, ih = pw * k, ph * k
            ix, iy = cx + (cw - iw) / 2, cy
            out.append({"op": "image", "data": base64.b64decode(p["data"]), "x": ix, "y": iy, "w": iw, "h": ih})
            out.append({"op": "path", "closed": True, "fill": (1, 1, 1), "stroke": None, "width": 0, "dash": None,
                        "rings": [[(ix, iy), (ix + 6, iy), (ix + 6, iy + 5), (ix, iy + 5)]]})
            out.append({"op": "text", "x": ix + 3, "y": iy + 3.8, "size": 3, "text": str(i + 1), "anchor": "middle", "color": (0.1, 0.1, 0.1)})
        return out


def build_document(spec, lib, lgr_dash, tiles=None):
    meta = {"object": spec.get("meta", {}).get("object", ""), "code": spec.get("meta", {}).get("code", ""),
            "stage": spec.get("meta", {}).get("stage", ""), "org": spec.get("meta", {}).get("org", "")}
    doc = Document(meta["object"] or "Альбом", meta=meta)
    doc.sheet_titles = []
    for sh in spec["sheets"]:
        size = sh.get("size") if sh.get("size") in SIZES else "A3"
        page = Page(page_size(size, sh.get("orient")))
        if sh.get("style") == "pptkrt":                     # альбом по шаблону ППТ КРТ владельца (album_io.py)
            import album_io
            meta_p = {**meta, **(spec.get("meta") or {})}
            page.frames = album_io.build_pptkrt(page, sh, meta_p, lib, lgr_dash, tiles,
                                                lambda rect, s: SketchMapFrame(rect, s, lib, lgr_dash, tiles))
            doc.pages.append(page)
            doc.sheet_titles.append(sh.get("title", ""))
            continue
        if size in PAPER:
            w, h = page.size
            map_rect = (w * PAPER_MARGIN, h * PAPER_MARGIN, w * (1 - 2 * PAPER_MARGIN), h * (1 - 2 * PAPER_MARGIN))
            page.frames = [SketchMapFrame(map_rect, sh, lib, lgr_dash, tiles), PaperFrame(map_rect, sh)]
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
                page.frames = [SketchMapFrame(mr, sh, lib, lgr_dash, tiles), PhotoGridFrame((mr[0] + mr[2] + 5, mr[1], w - 8 - mr[0] - mr[2] - 5, mr[3]), sh),
                               SlideFrame(page, sh, meta_p)]
            elif sh.get("panels"):
                page.frames = [PanelFrame(r, p, lib, lgr_dash, tiles) for r, p in zip(panel_rects(map_rect, len(sh["panels"])), sh["panels"])] + \
                    [ColumnFrame(col_rect, sh, title=False), SlideFrame(page, sh, meta_p)]
            else:
                page.frames = [SketchMapFrame(map_rect, sh, lib, lgr_dash, tiles), ColumnFrame(col_rect, sh, title=False), SlideFrame(page, sh, meta_p)]
        elif sh.get("kind") == "tep":
            w, h = SIZES[size]
            page.frames = [PageBorder(page), TepSheetFrame((25, 10, w - 25 - 10, h - 5 - StampFrame.H - 10 - 3), sh), StampFrame(page)]
        else:
            page.frames = [PageBorder(page), SketchMapFrame(map_rect, sh, lib, lgr_dash), ColumnFrame(col_rect, sh), StampFrame(page)]
        doc.pages.append(page)
        doc.sheet_titles.append(sh.get("title", ""))
    return doc


def render_pdf(spec, lib, lgr_dash, tiles=None):
    return PdfBackend(None).render(document_pages_ops(build_document(spec, lib, lgr_dash, tiles), None))


# рамки листа → группы фигур в PPTX
PPTX_GROUPS = {"SketchMapFrame": "Карта", "PanelFrame": "Карта", "ColumnFrame": "Легенда", "PhotoGridFrame": "Фотографии",
               "CalloutFrame": "Выноска", "OkrugTitleFrame": "Название округа", "MapNoteFrame": "Округ и район", "ConceptColumnFrame": "Легенда", "OrthoLegendFrame": "Легенда", "ConceptPhotoFrame": "Фотографии", "StampFrame": "Штамп", "PageBorder": "Рамка листа",
               "TepSheetFrame": "ТЭП", "LegendFrame": "Легенда", "TableFrame": "Таблица"}


def render_pptx(spec, lib, lgr_dash, tiles=None):
    """Альбом в редактируемый PPTX: те же листы, что в PDF; каждая рамка листа — группа фигур, подписи — текстом."""
    from grado_layout.compose import _ctx, sheet_titles
    from grado_render.backend_pptx import PptxBackend
    doc = build_document(spec, lib, lgr_dash, tiles)
    titles, pages = sheet_titles(doc), []
    for i, page in enumerate(doc.pages, start=1):
        ctx = _ctx(doc, None, None, None, i, titles[i - 1])
        pages.append((page.size[0], page.size[1], [(PPTX_GROUPS.get(type(f).__name__, "Оформление"), f.ops(ctx)) for f in page.frames]))
    return PptxBackend(doc.title).render(pages)


def render_preview_svg(spec, lib, lgr_dash, index=0, tiles=None):
    w, h, ops = document_pages_ops(build_document(spec, lib, lgr_dash, tiles), None)[index]
    return render_svg(w, h, ops)
