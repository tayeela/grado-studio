"""Листы и альбом ГРАДО 2: PDF и SVG через рендер и вёрстку ядра (core/render, core/layout).

Клиент присылает для каждого листа уже оформленные объекты — так лист повторяет карту на экране (стиль
считает тот же код, что рисует слои). Здесь: пересчёт WGS84 → МСК (метры, как в QGIS и в DXF), масштаб листа,
заливки с прозрачностью (смешение с белым: в PDF-писателе ядра альфы нет), штриховки, типы линий REDLN97
(шаблоны LIN и формы SHX — те же данные, что у экрана), легенда, таблица ТЭП, стрелка севера, масштабная
линейка, рамка и основная надпись по ГОСТ Р 21.101 (рамка и штамп — фреймы ядра).
"""

import math

from grado_connectors import crs
from grado_layout import A1_LANDSCAPE, A3_LANDSCAPE, Document, Page, PageBorder, StampFrame, TableFrame
from grado_layout.compose import document_pages_ops
from grado_layout.model import Frame
from grado_render import PdfBackend, hex_to_rgb, render_svg
from grado_render.scene import hatch_ops

SIZES = {"A3": A3_LANDSCAPE, "A1": A1_LANDSCAPE}
COLUMN = {"A3": 110, "A1": 170}             # правая колонка: легенда и ТЭП
PX_MM = 0.26                                 # толщина с экрана (пиксели 96 dpi) → мм листа


def layout(size):
    """Прямоугольники листа (мм): карта, колонка легенды. Карта кончается над штампом (185×55)."""
    w, h = SIZES[size]
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


class SketchMapFrame(Frame):
    """Карта листа из уже оформленных объектов клиента."""

    def __init__(self, rect, sheet, lib, lgr_dash):
        super().__init__(rect)
        self.sheet, self.lib, self.lgr_dash = sheet, lib, lgr_dash

    def ops(self, ctx):
        sh, rect = self.sheet, self.rect
        tr = MapTransform(rect, sh["center"], sh["scale"])
        k = tr.k
        out, labels = [{"op": "clip", "rect": tuple(rect)}], []
        for layer in sh.get("layers", []):
            for f in layer.get("features", []):
                kind, parts = _parts(f["g"])
                w = max(0.08, (f.get("w") or 1) * PX_MM)
                stroke = hex_to_rgb(f.get("stroke")) if f.get("stroke") else None
                if kind == "poly":
                    for poly in parts:
                        rings = [c for c in (clip_ring([tr.mm(*p[:2]) for p in r], rect) for r in poly) if len(c) >= 3]
                        if not rings:
                            continue
                        fill = None if f.get("hatch") or f.get("fill") is None else _mix(f["fill"], f.get("a"))
                        out.append({"op": "path", "rings": rings, "closed": True, "fill": fill, "stroke": stroke if f.get("w", 1) > 0 else None,
                                    "width": w, "dash": None})
                        if f.get("hatch") and f.get("fill"):
                            # узор штриховки слоя: одно направление или сетка из двух; точки на листе — косой штриховкой
                            for ang in {"0": (0,), "90": (90,), "135": (135,), "x45": (45, 135), "x0": (0, 90)}.get(f.get("hp"), (45,)):
                                out.extend(hatch_ops(rings, spacing=1.6, stroke=hex_to_rgb(f["fill"]), angle=ang))
                        if f.get("label"):
                            xs, ys = zip(*rings[0])
                            labels.append((sum(xs) / len(xs), sum(ys) / len(ys), f["label"]))
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
                            out.append({"op": "path", "closed": False, "fill": None, "stroke": color, "width": w, "dash": None, "rings": [pts]})
                        if f.get("label"):
                            m = pts[len(pts) // 2]
                            labels.append((m[0], m[1], f["label"]))
                elif kind == "point":
                    for p in parts:
                        x, y = tr.mm(*p[:2])
                        out.append({"op": "circle", "x": x, "y": y, "r": max(0.5, (f.get("w") or 1) * 0.35),
                                    "fill": _mix(f.get("fill") or "#666666", 1), "stroke": stroke or (0.2, 0.2, 0.2), "width": 0.15})
                        if f.get("label"):
                            labels.append((x, y - 2, f["label"]))
        if sh.get("territory"):
            _, parts = _parts(sh["territory"])
            for poly in parts:
                out.append({"op": "path", "rings": [[tr.mm(*p[:2]) for p in poly[0]]], "closed": True, "fill": None,
                            "stroke": (0.7, 0.15, 0.12), "width": 0.6, "dash": [4, 1.2, 0.6, 1.2]})
        grid = {}                                                     # подписи без наложений: первая занявшая место остаётся
        rx, ry, rw, rh = rect
        for x, y, text in labels:
            if not (rx <= x <= rx + rw and ry <= y <= ry + rh):
                continue
            text = str(text)[:40]
            bw, bh = 1.3 * len(text), 2.6
            box = (x - bw / 2, y - bh, x + bw / 2, y + 0.6)
            cells = [(i, j) for i in range(int(box[0] // 10), int(box[2] // 10) + 1)
                     for j in range(int(box[1] // 10), int(box[3] // 10) + 1)]       # сетка 10 мм вместо перебора всех
            if any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3])
                   for c in cells for b in grid.get(c, ())):
                continue
            for c in cells:
                grid.setdefault(c, []).append(box)
            out.append({"op": "text", "x": x, "y": y, "size": 2.2, "text": text, "color": (0.12, 0.12, 0.12), "anchor": "middle"})
        out.append({"op": "unclip"})
        out.extend(self._frame_marks(rect, k, sh["scale"]))
        return out

    @staticmethod
    def _frame_marks(rect, k, scale):
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
        m = _nice(50 / k)
        L, bx, by = m * k, x + 6, y + h - 8
        for i in range(4):
            out.append({"op": "path", "closed": True, "fill": (0, 0, 0) if i % 2 == 0 else (1, 1, 1), "stroke": (0, 0, 0), "width": 0.2,
                        "dash": None, "rings": [[(bx + L * i / 4, by), (bx + L * (i + 1) / 4, by), (bx + L * (i + 1) / 4, by + 1.5), (bx + L * i / 4, by + 1.5)]]})
        for i in (0, 2, 4):
            v = m * i / 4
            out.append({"op": "text", "x": bx + L * i / 4, "y": by - 1, "size": 2.2, "text": f"{v:g}", "anchor": "middle"})
        out.append({"op": "text", "x": bx + L + 3, "y": by + 1.5, "size": 2.2, "text": f"м   М 1:{scale:g}"})
        return out


class ColumnFrame(Frame):
    """Правая колонка: заголовок листа, легенда вида, таблица ТЭП (что влезет по высоте)."""

    def __init__(self, rect, sheet):
        super().__init__(rect)
        self.sheet = sheet

    def ops(self, ctx):
        x, y, w, h = self.rect
        sh, out = self.sheet, []
        yy = y + 5
        for line in _wrap(sh.get("title", ""), int(w / 2.4)):
            out.append({"op": "text", "x": x, "y": yy, "size": 4.2, "text": line})
            yy += 6
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
                out.append({"op": "text", "x": x, "y": yy, "size": 2.6, "text": grp["title"][:60]})
                yy += 4.5
            for it in items[:14]:
                if full or yy > y + h - 8:            # место проверяется на каждой строке, иначе легенда наезжает на штамп
                    full = True
                    break
                out.extend(_swatch(x, yy - 3, grp.get("kind", "poly"), it))
                out.append({"op": "text", "x": x + 13, "y": yy, "size": 2.4, "text": str(it.get("label") or grp["title"])[:int((w - 13) / 1.25)]})
                yy += 4.8
            yy += 1.5
        if full:
            out.append({"op": "text", "x": x, "y": min(yy, y + h - 3), "size": 2.4, "text": "… легенда не поместилась"})
            yy += 5
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
    words, lines, cur = str(text).split(), [], ""
    for wd in words:
        if len(cur) + len(wd) + 1 > n and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = (cur + " " + wd).strip()
    return lines + ([cur] if cur else [])


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


def build_document(spec, lib, lgr_dash):
    meta = {"object": spec.get("meta", {}).get("object", ""), "code": spec.get("meta", {}).get("code", ""),
            "stage": spec.get("meta", {}).get("stage", ""), "org": spec.get("meta", {}).get("org", "")}
    doc = Document(meta["object"] or "Альбом", meta=meta)
    doc.sheet_titles = []
    for sh in spec["sheets"]:
        size = sh.get("size") if sh.get("size") in SIZES else "A3"
        page = Page(SIZES[size])
        map_rect, col_rect = layout(size)
        if sh.get("kind") == "tep":
            w, h = SIZES[size]
            page.frames = [PageBorder(page), TepSheetFrame((25, 10, w - 25 - 10, h - 5 - StampFrame.H - 10 - 3), sh), StampFrame(page)]
        else:
            page.frames = [PageBorder(page), SketchMapFrame(map_rect, sh, lib, lgr_dash), ColumnFrame(col_rect, sh), StampFrame(page)]
        doc.pages.append(page)
        doc.sheet_titles.append(sh.get("title", ""))
    return doc


def render_pdf(spec, lib, lgr_dash):
    return PdfBackend(None).render(document_pages_ops(build_document(spec, lib, lgr_dash), None))


def render_preview_svg(spec, lib, lgr_dash, index=0):
    w, h, ops = document_pages_ops(build_document(spec, lib, lgr_dash), None)[index]
    return render_svg(w, h, ops)
