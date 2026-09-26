"""Листы и альбом ГРАДО 2: PDF и SVG через рендер и вёрстку ядра (core/render, core/layout).

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
        out, labels, along, placed = [{"op": "clip", "rect": tuple(rect)}], [], {}, []
        if sh.get("basemap") == "sat" and self.tiles:
            out.extend(tile_ops(tr, rect, sh["scale"], self.tiles, sh["center"][1]))
        for layer in sh.get("layers", []):
            for f in layer.get("features", []):
                kind, parts = _parts(f["g"])
                w = max(0.08, (f.get("w") or 1) * PX_MM)
                stroke = hex_to_rgb(f.get("stroke")) if f.get("stroke") else None
                dash = [max(0.1, float(d) * PX_MM) for d in f["dash"]] if f.get("dash") else None   # штрих карты (пикс.) → мм
                if kind == "poly":
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
                            xs, ys = zip(*rings[0])
                            labels.append((sum(xs) / len(xs), sum(ys) / len(ys), f["label"], f.get("ls")))
                elif kind == "line":
                    color = hex_to_rgb(f.get("lc") or f.get("stroke") or f.get("fill") or "#333333")
                    for line in parts:
                        pts = [tr.mm(*p[:2]) for p in line]
                        if len(pts) < 2:
                            continue
                        if f.get("lt"):
                            for name in f["lt"]:
                                out.extend(linetype_ops(pts, name, k, color, max(w, 0.25), self.lib))
                        elif f.get("miss"):
                            for code, _sign in f["miss"]:
                                dash = self.lgr_dash.get(int(code))
                                out.append({"op": "path", "closed": False, "fill": None, "stroke": color, "width": max(w, 0.25),
                                            "dash": [d * k for d in dash] if dash else None, "rings": [pts]})
                        else:
                            out.append({"op": "path", "closed": False, "fill": None, "stroke": color, "width": w, "dash": dash, "rings": [pts]})
                        if f.get("label"):
                            # подпись вдоль линии (улица): на самом длинном отрезке внутри рамки; одно название — один раз
                            for a, b in zip(pts, pts[1:]):
                                mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                                if not (rect[0] < mx < rect[0] + rect[2] and rect[1] < my < rect[1] + rect[3]):
                                    continue
                                d = math.hypot(b[0] - a[0], b[1] - a[1])
                                if d > along.get(f["label"], (0,))[0]:
                                    along[f["label"]] = (d, mx, my, math.atan2(b[1] - a[1], b[0] - a[0]), f.get("ls"))
                elif kind == "point":
                    for p in parts:
                        x, y = tr.mm(*p[:2])
                        if f.get("nm"):                                 # слой надписей: подпись на самой точке, без значка
                            if f.get("label"):
                                placed.append((x, y, str(f["label"]), f.get("ls"), f.get("la"), f.get("lcol")))
                            continue
                        out.append({"op": "circle", "x": x, "y": y, "r": max(0.5, (f.get("w") or 1) * 0.35),
                                    "fill": _mix(f.get("fill") or "#666666", 1), "stroke": stroke or (0.2, 0.2, 0.2), "width": 0.15})
                        if f.get("label"):
                            labels.append((x, y - 2, f["label"], f.get("ls")))
        if sh.get("territory"):
            _, parts = _parts(sh["territory"])
            for poly in parts:
                ts = sh.get("terrStyle") or {}                        # слайды раздела: граница ППТ — сплошная пурпурная
                out.append({"op": "path", "rings": [[tr.mm(*p[:2]) for p in poly[0]]], "closed": True,
                            "fill": _mix(ts["fill"], .35) if ts.get("fill") else None,
                            "stroke": hex_to_rgb(ts.get("stroke", "#b3261f")), "width": ts.get("width", 0.6),
                            "dash": None if ts else [4, 1.2, 0.6, 1.2]})
        grid = {}                                                     # подписи без наложений: первая занявшая место остаётся
        rx, ry, rw, rh = rect

        def take(box):
            cells = [(i, j) for i in range(int(box[0] // 10), int(box[2] // 10) + 1)
                     for j in range(int(box[1] // 10), int(box[3] // 10) + 1)]       # сетка 10 мм вместо перебора всех
            if any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3])
                   for c in cells for b in grid.get(c, ())):
                return False
            for c in cells:
                grid.setdefault(c, []).append(box)
            return True

        callout = self._callout(sh, tr, rect) if sh.get("callout") and sh.get("territory") else None
        if callout:
            take(callout[0])
        ink = (1, 1, 1) if sh.get("basemap") == "sat" else (0.12, 0.12, 0.12)   # на снимке тёмная подпись не читается
        for text, (d, x, y, ang, ls) in sorted(along.items(), key=lambda t: -t[1][0]):
            ls = float(ls or 2.2)
            text = str(text)[:40]
            tw = ls * .55 * len(text)
            if d < tw * .5:
                continue                                                # отрезок короче половины подписи — не подписывать
            if ang > math.pi / 2 or ang < -math.pi / 2:
                ang += math.pi                                          # не вверх ногами
            ca, sa = abs(math.cos(ang)), abs(math.sin(ang))
            ex, ey = ca * tw / 2 + sa * ls * .6, sa * tw / 2 + ca * ls * .6
            if not take((x - ex, y - ey, x + ex, y + ey)):
                continue
            out.append({"op": "text", "x": x - math.sin(ang) * ls * .35, "y": y + math.cos(ang) * ls * .35, "size": ls, "text": text,
                        "color": ink, "anchor": "middle", "angle": ang})
        for x, y, text, ls, deg, col in placed:
            # надписи ГИС ОГД: на своём месте и под своим углом (вдоль границы), цветом знака ЛГР; наложения не пропускаются
            ls = float(ls or 2.0)
            if not (rx <= x <= rx + rw and ry <= y <= ry + rh):
                continue
            ang = -math.radians(float(deg or 0))              # на листе ось Y вниз: против часовой на карте — «минус»
            text = text[:60]
            tw = ls * .55 * len(text)
            ca, sa = abs(math.cos(ang)), abs(math.sin(ang))
            ex, ey = ca * tw / 2 + sa * ls * .6, sa * tw / 2 + ca * ls * .6
            if not take((x - ex, y - ey, x + ex, y + ey)):
                continue
            out.append({"op": "text", "x": x - math.sin(ang) * ls * .35, "y": y + math.cos(ang) * ls * .35, "size": ls, "text": text,
                        "color": hex_to_rgb(col) if col else ink, "anchor": "middle", "angle": ang})
        for x, y, text, ls in labels:
            ls = float(ls or 2.2)
            if not (rx <= x <= rx + rw and ry <= y <= ry + rh):
                continue
            lines = [ln[:40] for ln in str(text).split("\n")[:8]]         # подпись в несколько строк: номер и индекс зоны, коды ВРИ
            lh = ls * 1.23
            y -= (len(lines) - 1) * lh / 2
            bw, bh = ls * .6 * max(len(ln) for ln in lines), ls * 1.2
            if not take((x - bw / 2, y - bh, x + bw / 2, y + ls * .3 + (len(lines) - 1) * lh)):
                continue
            for i, line in enumerate(lines):
                out.append({"op": "text", "x": x, "y": y + i * lh, "size": ls, "text": line, "color": ink, "anchor": "middle"})
        if callout:
            out.extend(callout[1])
        out.append({"op": "unclip"})
        if str(sh.get("size", "")).startswith("P"):
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


def _swatch(x, y, kind, it):
    fill, stroke = it.get("fill"), it.get("stroke")
    if kind == "line":
        return [{"op": "path", "closed": False, "fill": None, "stroke": hex_to_rgb(fill or stroke or "#333333"), "width": 0.6, "dash": None,
                 "rings": [[(x + 1, y + 1.8), (x + 10, y + 1.8)]]}]
    if kind == "point":
        return [{"op": "circle", "x": x + 5.5, "y": y + 1.8, "r": 1.2, "fill": hex_to_rgb(fill or "#666666"), "stroke": (0.2, 0.2, 0.2), "width": 0.15}]
    rect = [[(x + 1, y), (x + 10, y), (x + 10, y + 3.6), (x + 1, y + 3.6)]]
    out = [{"op": "path", "closed": True, "fill": None if it.get("hatch") else _mix(fill or "#dddddd", it.get("a", 1)),
            "stroke": hex_to_rgb(stroke or fill or "#555555"), "width": 0.2, "dash": None, "rings": rect}]
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


def render_preview_svg(spec, lib, lgr_dash, index=0, tiles=None):
    w, h, ops = document_pages_ops(build_document(spec, lib, lgr_dash, tiles), None)[index]
    return render_svg(w, h, ops)
