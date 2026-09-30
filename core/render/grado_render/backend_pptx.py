"""PPTX-бэкенд: тот же список операций, что у PDF и SVG, — в редактируемую презентацию PowerPoint.

Операция становится фигурой: контуры и линии — полилиниями (custGeom), подписи — надписями с настоящим текстом,
снимки и тайлы подложки — рисунками. Фигуры одной рамки листа собраны в группу (карта, легенда, оформление),
внутри карты — по слоям (операция "layer"). Обрезки в PowerPoint нет, поэтому она делается геометрией: контуры
режутся по прямоугольнику рамки, рисунки кадрируются, подписи и значки вне рамки пропускаются, а обрезка по
контуру (округ на схеме шаблона ППТ КРТ) — белой маской поверх: прямоугольник с вырезом по контуру.

Без сторонних библиотек: пакет OOXML собирается zipfile.
"""

import hashlib
import io
import math
import re
import zipfile
from xml.sax.saxutils import escape

from .ttf import Font, find_font

EMU = 36000                                          # EMU в мм
# семейство операции → гарнитура PowerPoint и жирность (те же шрифты, что встраивает PDF)
FONTS = {"ui": ("PT Sans", False), "ui-bold": ("PT Sans", True), "serif": ("PT Serif", False),
         "serif-bold": ("PT Serif", True), "sans": ("Montserrat", False), "sans-bold": ("Montserrat", True),
         "mono": ("Courier New", False)}
NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def _hex(c):
    return "%02X%02X%02X" % tuple(max(0, min(255, int(round(float(v) * 255)))) for v in c)


def _t(s):
    return escape(str(s), {'"': "&quot;"})


# ---------- геометрия обрезки ----------

def clip_polygon(ring, box):
    """Кольцо по прямоугольнику box = (x0, y0, x1, y1), Сазерленд — Ходжмен."""
    x0, y0, x1, y1 = box
    pts = list(ring)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    ix = lambda x: lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))
    iy = lambda y: lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)
    for inside, cut in ((lambda p: p[0] >= x0, ix(x0)), (lambda p: p[0] <= x1, ix(x1)),
                        (lambda p: p[1] >= y0, iy(y0)), (lambda p: p[1] <= y1, iy(y1))):
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


def _segment(a, b, box):
    """Отрезок по прямоугольнику (Лян — Барски): концы внутри или None."""
    x0, y0, x1, y1 = box
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                return None
        elif p < 0:
            t0 = max(t0, q / p)
        else:
            t1 = min(t1, q / p)
        if t0 > t1:
            return None
    return (a if t0 == 0 else (a[0] + t0 * dx, a[1] + t0 * dy)), (b if t1 == 1 else (a[0] + t1 * dx, a[1] + t1 * dy))


def clip_polyline(pts, box):
    """Ломаная по прямоугольнику: куски внутри."""
    runs, cur = [], []
    for a, b in zip(pts, pts[1:]):
        seg = _segment(a, b, box)
        if seg is None:
            if len(cur) > 1:
                runs.append(cur)
            cur = []
            continue
        p, q = seg
        if cur and cur[-1] == p:
            cur.append(q)
        else:
            if len(cur) > 1:
                runs.append(cur)
            cur = [p, q]
    if len(cur) > 1:
        runs.append(cur)
    return runs


def _bbox(rings):
    xs = [x for r in rings for x, _ in r]
    ys = [y for r in rings for _, y in r]
    return min(xs), min(ys), max(xs), max(ys)


def _inside_box(bb, box):
    return bb[0] >= box[0] and bb[1] >= box[1] and bb[2] <= box[2] and bb[3] <= box[3]


def _meet(a, b):
    if a is None:
        return b
    return max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])


def _area2(r):
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]))


def _in_ring(pt, r):
    x, y, inside = pt[0], pt[1], False
    for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def orient(rings):
    """Кольца с дырами: наружные — в одну сторону обхода, дыры — в другую (по глубине вложенности). Тогда дыра
    остаётся пустой при любом правиле заливки — и по чётности (PDF), и по ненулевому числу оборотов."""
    if len(rings) < 2 or len(rings) > 300:
        return rings
    out = []
    for i, r in enumerate(rings):
        probe = ((r[0][0] + r[1][0]) / 2, (r[0][1] + r[1][1]) / 2) if len(r) > 1 else r[0]
        depth = sum(1 for j, o in enumerate(rings) if j != i and len(o) > 2 and _in_ring(probe, o))
        out.append(r if (_area2(r) > 0) == (depth % 2 == 0) else r[::-1])
    return out


# ---------- фигуры ----------

class _Slide:
    def __init__(self, pres, k):
        self.pres, self.k = pres, k
        self.ids, self.rels = 1, {}                       # rels: имя картинки → rId
        self.stack = [[]]                                  # [[(xml, bbox)]] — открытые группы
        self.names = [None]
        self.clips = []
        self.pending = None                                # подряд идущие линии одного вида — одной фигурой
        self.alpha = None                                  # прозрачность заливки текущей фигуры

    def e(self, v):
        # float(): числовой атрибут разметки не должен пропустить строку (v * int повторяет её)
        return int(round(float(v) * EMU * self.k))

    def nid(self):
        self.ids += 1
        return self.ids

    def add(self, xml, bb, direct=False):
        if not direct:
            self.flush()
        self.stack[-1].append((xml, bb))

    def flush(self):
        """Линии без заливки одного цвета, толщины и штриха, идущие подряд (штриховка, сетка, контуры одного слоя),
        сливаются в одну фигуру: на листе с зонами иначе выходят десятки тысяч фигур."""
        if self.pending:
            (closed, stroke, width, dash, join, name), rings = self.pending
            self.pending = None
            self._emit(rings, closed, None, stroke, width, dash, join, name)

    # группы: рамка листа → слои карты
    def open(self, name):
        self.flush()
        self.stack.append([])
        self.names.append(name)

    def close(self):
        self.flush()
        items, name = self.stack.pop(), self.names.pop()
        if not items:
            return
        if len(items) == 1:                                       # одна фигура — без группы, под именем слоя
            xml, bb = items[0]
            if name:
                xml = re.sub(r'(<p:cNvPr id="\d+" name=")[^"]*"', lambda m: m.group(1) + _t(name) + '"', xml, count=1)
            self.add(xml, bb)
            return
        bb = (min(b[0] for _, b in items), min(b[1] for _, b in items), max(b[2] for _, b in items), max(b[3] for _, b in items))
        x, y, cx, cy = bb[0], bb[1], max(1, bb[2] - bb[0]), max(1, bb[3] - bb[1])
        xf = f'<a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/><a:chOff x="{x}" y="{y}"/><a:chExt cx="{cx}" cy="{cy}"/>'
        self.add(f'<p:grpSp><p:nvGrpSpPr><p:cNvPr id="{self.nid()}" name="{_t(name or "Группа")}"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
                 f'<p:grpSpPr><a:xfrm>{xf}</a:xfrm></p:grpSpPr>{"".join(x for x, _ in items)}</p:grpSp>', bb)

    def box(self):
        box = None
        for c in self.clips:
            box = _meet(box, c["box"])
        return box

    # --- контур ---
    def path(self, rings, closed, fill, stroke, width, dash, join, name="Контур"):
        rings = [r for r in rings if len(r) >= 2]
        if not rings or (fill is None and stroke is None):
            return
        box = self.box()
        if box is not None:
            bb = _bbox(rings)
            if bb[2] < box[0] or bb[0] > box[2] or bb[3] < box[1] or bb[1] > box[3]:
                return
            if not _inside_box(bb, box):
                if closed and fill is not None:
                    cut = [c for c in (clip_polygon(r, box) for r in rings) if len(c) >= 3]
                    if cut:
                        self._shape(orient(cut), True, fill, None, width, dash, join, name)
                if stroke is not None:
                    runs = [run for r in rings for run in clip_polyline(list(r) + ([r[0]] if closed else []), box)]
                    if runs:
                        self._shape(runs, False, None, stroke, width, dash, join, name)
                return
        self._shape(orient(rings) if closed and fill is not None else rings, closed, fill, stroke, width, dash, join, name)

    def _shape(self, rings, closed, fill, stroke, width, dash, join, name):
        if fill is None:
            key = (bool(closed), tuple(stroke), width, tuple(dash) if dash else None, join, name)
            if self.pending and self.pending[0] == key and sum(len(r) for r in self.pending[1]) < 20000:
                self.pending[1].extend(rings)
                return
            self.flush()
            self.pending = (key, list(rings))
            return
        self.flush()
        self._emit(rings, closed, fill, stroke, width, dash, join, name)

    def _emit(self, rings, closed, fill, stroke, width, dash, join, name):
        pts = [[(self.e(x), self.e(y)) for x, y in r] for r in rings]
        x0 = min(x for r in pts for x, _ in r)
        y0 = min(y for r in pts for _, y in r)
        cx = max(1, max(x for r in pts for x, _ in r) - x0)
        cy = max(1, max(y for r in pts for _, y in r) - y0)
        geo = "".join(f'<a:moveTo><a:pt x="{r[0][0] - x0}" y="{r[0][1] - y0}"/></a:moveTo>'
                      + "".join(f'<a:lnTo><a:pt x="{x - x0}" y="{y - y0}"/></a:lnTo>' for x, y in r[1:])
                      + ("<a:close/>" if closed else "") for r in pts)
        nofill = "" if fill is not None else ' fill="none"'
        alpha = f'<a:alpha val="{int(float(self.alpha) * 100000)}"/>' if fill is not None and self.alpha is not None and float(self.alpha) < 1 else ""
        clr = f'<a:srgbClr val="{_hex(fill)}">{alpha}</a:srgbClr>' if alpha else f'<a:srgbClr val="{_hex(fill)}"/>' if fill is not None else ""
        fill_xml = f'<a:solidFill>{clr}</a:solidFill>' if fill is not None else "<a:noFill/>"
        self.add(f'<p:sp><p:nvSpPr><p:cNvPr id="{self.nid()}" name="{_t(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr>'
                 f'<a:xfrm><a:off x="{x0}" y="{y0}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
                 f'<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="l" t="t" r="r" b="b"/>'
                 f'<a:pathLst><a:path w="{cx}" h="{cy}"{nofill}>{geo}</a:path></a:pathLst></a:custGeom>'
                 f'{fill_xml}{self._line(stroke, width, dash, join)}</p:spPr></p:sp>',
                 (x0, y0, x0 + cx, y0 + cy), direct=True)

    def _line(self, stroke, width, dash, join):
        if stroke is None:
            return "<a:ln><a:noFill/></a:ln>"
        w = max(0.05, float(width or 0))
        d = ""
        if dash:
            ds = [float(v) for v in dash] * (2 if len(dash) % 2 else 1)
            d = "<a:custDash>" + "".join(f'<a:ds d="{max(1, int(ds[i] / w * 100000))}" sp="{max(1, int(ds[i + 1] / w * 100000))}"/>'
                                         for i in range(0, len(ds), 2)) + "</a:custDash>"
        j = "<a:round/>" if join == "round" else '<a:miter lim="1000000"/>'
        return f'<a:ln w="{self.e(w)}" cap="flat"><a:solidFill><a:srgbClr val="{_hex(stroke)}"/></a:solidFill>{d}{j}</a:ln>'

    # --- значок ---
    def circle(self, o):
        box = self.box()
        if box is not None and not (box[0] <= o["x"] <= box[2] and box[1] <= o["y"] <= box[3]):
            return
        r = o["r"]
        x, y, d = self.e(o["x"] - r), self.e(o["y"] - r), max(1, self.e(2 * r))
        fill = f'<a:solidFill><a:srgbClr val="{_hex(o["fill"])}"/></a:solidFill>' if o.get("fill") is not None else "<a:noFill/>"
        self.add(f'<p:sp><p:nvSpPr><p:cNvPr id="{self.nid()}" name="Значок"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr>'
                 f'<a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{d}" cy="{d}"/></a:xfrm><a:prstGeom prst="ellipse"><a:avLst/></a:prstGeom>'
                 f'{fill}{self._line(o.get("stroke"), o.get("width", 0.3), None, "round")}</p:spPr></p:sp>', (x, y, x + d, y + d))

    # --- надпись ---
    def text(self, o):
        box = self.box()
        if box is not None and not (box[0] <= o["x"] <= box[2] and box[1] <= o["y"] <= box[3]):
            return
        fam = o.get("font_family") or "ui"
        fam = fam if fam in FONTS else "ui"
        font = self.pres.font(fam)
        size = float(o["size"])
        asc, dsc = font.ascent / font.units_per_em * size, -font.descent / font.units_per_em * size
        w, h = font.text_width(o["text"], size) * 1.04 + size * .2, asc + dsc
        anchor = o.get("anchor")
        lx = -w / 2 if anchor == "middle" else -w if anchor == "end" else -size * .1
        ang = o.get("angle", 0.0) or 0.0
        cx, cy = lx + w / 2, -asc + h / 2                          # середина надписи от точки привязки (на базовой линии)
        ca, sa = math.cos(ang), math.sin(ang)
        mx, my = o["x"] + cx * ca - cy * sa, o["y"] + cx * sa + cy * ca
        x, y, ew, eh = self.e(mx - w / 2), self.e(my - h / 2), max(1, self.e(w)), max(1, self.e(h))
        rot = f' rot="{int(round(math.degrees(ang) * 60000)) % 21600000}"' if ang else ""
        face, bold = FONTS[fam]
        algn = {"middle": "ctr", "end": "r"}.get(anchor, "l")
        glow = ""
        if o.get("halo"):                                          # ореол подписи — «свечение», как в шаблоне владельца
            glow = (f'<a:effectLst><a:glow rad="{self.e(float(o["halo"]) * 1.6)}">'
                    f'<a:srgbClr val="{_hex(o.get("halo_color", (1, 1, 1)))}"/></a:glow></a:effectLst>')
        sz = max(100, int(round(size / 0.3528 * self.k * 100)))
        b = (' b="1"' if bold else "") + (' u="sng"' if o.get("underline") else "")
        self.add(f'<p:sp><p:nvSpPr><p:cNvPr id="{self.nid()}" name="Надпись"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr>'
                 f'<a:xfrm{rot}><a:off x="{x}" y="{y}"/><a:ext cx="{ew}" cy="{eh}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
                 f'<a:noFill/></p:spPr><p:txBody><a:bodyPr wrap="none" lIns="0" tIns="0" rIns="0" bIns="0" rtlCol="0" anchor="t">'
                 f'<a:noAutofit/></a:bodyPr><a:lstStyle/><a:p><a:pPr algn="{algn}"/><a:r><a:rPr lang="ru-RU" sz="{sz}"'
                 f'{b} dirty="0"><a:solidFill><a:srgbClr val="{_hex(o.get("color", (0, 0, 0)))}"/></a:solidFill>'
                 f'{glow}<a:latin typeface="{face}"/><a:cs typeface="{face}"/></a:rPr><a:t>{_t(o["text"])}</a:t></a:r></a:p></p:txBody></p:sp>',
                 (x, y, x + ew, y + eh))

    # --- рисунок ---
    def image(self, o):
        rid = self.rels.setdefault(self.pres.media(o["data"]), f"rId{len(self.rels) + 2}")
        box, crop, rot = self.box(), "", ""
        if "quad" in o:                                            # тайл параллелограммом: поворот и растяжение
            (tlx, tly), (trx, try_), (blx, bly) = o["quad"]
            w, h = math.hypot(trx - tlx, try_ - tly), math.hypot(blx - tlx, bly - tly)
            cx, cy = (trx + blx) / 2, (try_ + bly) / 2
            ang = math.atan2(try_ - tly, trx - tlx)
            x0, y0 = cx - w / 2, cy - h / 2
            if box is not None:
                rr = max(w, h)
                if cx + rr < box[0] or cx - rr > box[2] or cy + rr < box[1] or cy - rr > box[3]:
                    return
            if abs(ang) > 1e-4:
                rot = f' rot="{int(round(math.degrees(ang) * 60000)) % 21600000}"'
        else:
            x0, y0, w, h = o["x"], o["y"], o["w"], o["h"]
            if box is not None:
                cx0, cy0, cx1, cy1 = max(x0, box[0]), max(y0, box[1]), min(x0 + w, box[2]), min(y0 + h, box[3])
                if cx0 >= cx1 or cy0 >= cy1:
                    return
                if (cx0, cy0, cx1, cy1) != (x0, y0, x0 + w, y0 + h):          # кадрирование вместо обрезки
                    pct = lambda v, s: int(round(v / s * 100000))
                    crop = (f'<a:srcRect l="{pct(cx0 - x0, w)}" t="{pct(cy0 - y0, h)}" '
                            f'r="{pct(x0 + w - cx1, w)}" b="{pct(y0 + h - cy1, h)}"/>')
                    x0, y0, w, h = cx0, cy0, cx1 - cx0, cy1 - cy0
        x, y, ew, eh = self.e(x0), self.e(y0), max(1, self.e(w)), max(1, self.e(h))
        self.add(f'<p:pic><p:nvPicPr><p:cNvPr id="{self.nid()}" name="Рисунок"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>'
                 f'<p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="{rid}"/>{crop}<a:stretch><a:fillRect/></a:stretch></p:blipFill>'
                 f'<p:spPr><a:xfrm{rot}><a:off x="{x}" y="{y}"/><a:ext cx="{ew}" cy="{eh}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
                 f'</p:spPr></p:pic>', (x, y, x + ew, y + eh))

    # --- обрезка ---
    def clip(self, o):
        self.flush()
        if o.get("rings"):
            rings = [r for r in o["rings"] if len(r) >= 3]
            self.clips.append({"box": _meet(self.box(), _bbox(rings)) if rings else self.box(), "rings": rings,
                               "items": self.stack[-1], "start": len(self.stack[-1])})
        else:
            x, y, w, h = o["rect"]
            self.clips.append({"box": _meet(self.box(), (x, y, x + w, y + h))})

    def unclip(self):
        self.flush()
        if not self.clips:
            return
        c = self.clips.pop()
        if not c.get("rings") or c["box"] is None or len(c["items"]) <= c["start"]:
            return
        # белая маска поверх нарисованного внутри контура: прямоугольник с вырезом по контуру
        x0, y0, x1, y1 = c["box"]
        k = EMU * self.k
        drawn = c["items"][c["start"]:]
        x0 = max(x0, min(b[0] for _, b in drawn) / k)
        y0 = max(y0, min(b[1] for _, b in drawn) / k)
        x1 = min(x1, max(b[2] for _, b in drawn) / k)
        y1 = min(y1, max(b[3] for _, b in drawn) / k)
        if x0 >= x1 or y0 >= y1:
            return
        pad = 0.01
        frame = [(x0 - pad, y0 - pad), (x1 + pad, y0 - pad), (x1 + pad, y1 + pad), (x0 - pad, y1 + pad)]
        outer = self.clips
        self.clips = []                                             # маска сама по себе не режется
        self._shape(orient([frame] + [list(r) for r in c["rings"]]), True, (1, 1, 1), None, 0, None, None, "Маска")
        self.clips = outer

    def xml(self):
        self.flush()
        body = "".join(x for x, _ in self.stack[0])
        return (f'{XML}<p:sld {NS}><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
                f'<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm>'
                f'</p:grpSpPr>{body}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>')


class PptxBackend:
    """pages: [(w_mm, h_mm, [(имя группы, ops)])] → bytes PPTX. Размер слайда — по первой странице, остальные
    вписываются в него с сохранением пропорций."""

    def __init__(self, title="Альбом"):
        self.title = title
        self._fonts, self._media = {}, {}

    def font(self, family):
        if family not in self._fonts:
            self._fonts[family] = Font(find_font(family))
        return self._fonts[family]

    def media(self, data):
        key = hashlib.sha1(data).hexdigest()
        if key not in self._media:
            ext = "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "jpeg"
            self._media[key] = (f"image{len(self._media) + 1}.{ext}", data)
        return self._media[key][0]

    def _page(self, w, h, groups, W, H):
        s = _Slide(self, min(W / w, H / h))
        for name, ops in groups:
            s.open(name)
            depth = 0                                               # подгруппы слоёв внутри рамки
            for o in ops:
                t = o["op"]
                if t == "layer":
                    for _ in range(depth):
                        s.close()
                    s.open(o.get("name") or "Слой")
                    depth = 1
                elif t == "path":
                    s.alpha = o.get("alpha")
                    s.path(o["rings"], o.get("closed"), o.get("fill"), o.get("stroke"), o.get("width", 0.3), o.get("dash"), o.get("join"))
                    s.alpha = None
                elif t == "circle":
                    s.circle(o)
                elif t == "text":
                    s.text(o)
                elif t == "image":
                    s.image(o)
                elif t == "clip":
                    s.clip(o)
                elif t == "unclip":
                    s.unclip()
            for _ in range(depth):
                s.close()
            s.clips = []
            s.close()
        return s

    def render(self, pages):
        W, H = pages[0][0], pages[0][1]
        slides = [self._page(w, h, groups, W, H) for w, h, groups in pages]
        n = len(slides)
        buf = io.BytesIO()
        z = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED)
        exts = {name.rsplit(".", 1)[1] for name, _ in self._media.values()}
        z.writestr("[Content_Types].xml", XML + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   + "".join(f'<Default Extension="{e}" ContentType="image/{e}"/>' for e in sorted(exts))
                   + '<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>'
                   '<Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>'
                   '<Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>'
                   '<Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>'
                   '<Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/>'
                   '<Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/>'
                   '<Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/>'
                   '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
                   '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
                   + "".join(f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
                             for i in range(1, n + 1)) + "</Types>")
        rel = lambda rid, typ, target: f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/{typ}" Target="{target}"/>'
        rels = lambda body: XML + f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{body}</Relationships>'
        z.writestr("_rels/.rels", rels(rel("rId1", "officeDocument", "ppt/presentation.xml")
                                       + '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                                       + rel("rId3", "extended-properties", "docProps/app.xml")))
        z.writestr("docProps/core.xml", XML + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                   'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
                   f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>{_t(self.title)}</dc:title><dc:creator>ГРАДО 2</dc:creator>'
                   '</cp:coreProperties>')
        z.writestr("docProps/app.xml", XML + '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
                   f'<Application>ГРАДО 2</Application><Slides>{n}</Slides></Properties>')
        z.writestr("ppt/presentation.xml", XML + f'<p:presentation {NS} saveSubsetFonts="1">'
                   '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>'
                   + "".join(f'<p:sldId id="{255 + i}" r:id="rId{i + 1}"/>' for i in range(1, n + 1))
                   + f'</p:sldIdLst><p:sldSz cx="{int(round(W * EMU))}" cy="{int(round(H * EMU))}"/><p:notesSz cx="6858000" cy="9144000"/>'
                   '</p:presentation>')
        z.writestr("ppt/_rels/presentation.xml.rels", rels(
            rel("rId1", "slideMaster", "slideMasters/slideMaster1.xml")
            + "".join(rel(f"rId{i + 1}", "slide", f"slides/slide{i}.xml") for i in range(1, n + 1))
            + rel(f"rId{n + 2}", "presProps", "presProps.xml") + rel(f"rId{n + 3}", "viewProps", "viewProps.xml")
            + rel(f"rId{n + 4}", "theme", "theme/theme1.xml") + rel(f"rId{n + 5}", "tableStyles", "tableStyles.xml")))
        z.writestr("ppt/presProps.xml", XML + f'<p:presentationPr {NS}/>')
        z.writestr("ppt/viewProps.xml", XML + f'<p:viewPr {NS}><p:normalViewPr><p:restoredLeft sz="15620"/><p:restoredTop sz="94660"/>'
                   '</p:normalViewPr><p:gridSpacing cx="72008" cy="72008"/></p:viewPr>')
        z.writestr("ppt/tableStyles.xml", XML + '<a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                   'def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>')
        z.writestr("ppt/theme/theme1.xml", XML + THEME)
        tree = ('<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm>'
                '<a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>')
        z.writestr("ppt/slideMasters/slideMaster1.xml", XML + f'<p:sldMaster {NS}>'
                   + tree.replace("<p:cSld>", '<p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>')
                   + '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" '
                   'accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
                   '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
                   '<p:txStyles><p:titleStyle><a:lvl1pPr><a:defRPr sz="3200"/></a:lvl1pPr></p:titleStyle><p:bodyStyle><a:lvl1pPr>'
                   '<a:defRPr sz="1800"/></a:lvl1pPr></p:bodyStyle><p:otherStyle><a:lvl1pPr><a:defRPr sz="1800"/></a:lvl1pPr>'
                   '</p:otherStyle></p:txStyles></p:sldMaster>')
        z.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", rels(
            rel("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml") + rel("rId2", "theme", "../theme/theme1.xml")))
        z.writestr("ppt/slideLayouts/slideLayout1.xml", XML + f'<p:sldLayout {NS} type="blank" preserve="1">'
                   + tree.replace("<p:cSld>", '<p:cSld name="Пустой слайд">') + '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>')
        z.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", rels(rel("rId1", "slideMaster", "../slideMasters/slideMaster1.xml")))
        names = {name: data for name, data in self._media.values()}
        for i, s in enumerate(slides, start=1):
            z.writestr(f"ppt/slides/slide{i}.xml", s.xml())
            z.writestr(f"ppt/slides/_rels/slide{i}.xml.rels", rels(
                rel("rId1", "slideLayout", "../slideLayouts/slideLayout1.xml")
                + "".join(rel(rid, "image", f"../media/{name}") for name, rid in s.rels.items())))
        for name, data in names.items():
            z.writestr(f"ppt/media/{name}", data)
        z.close()
        return buf.getvalue()


def _scheme(name, val):
    return f'<a:{name}><a:srgbClr val="{val}"/></a:{name}>'


THEME = ('<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="ГРАДО">'
         '<a:themeElements><a:clrScheme name="ГРАДО">'
         + "".join(_scheme(n, v) for n, v in (("dk1", "000000"), ("lt1", "FFFFFF"), ("dk2", "1F1F1F"), ("lt2", "F2F2F2"),
                                              ("accent1", "E93939"), ("accent2", "2B3CC4"), ("accent3", "72A36F"),
                                              ("accent4", "F5D58A"), ("accent5", "A9CFE5"), ("accent6", "8A8A8A"),
                                              ("hlink", "2B3CC4"), ("folHlink", "7F3F98")))
         + '</a:clrScheme><a:fontScheme name="ГРАДО">'
         '<a:majorFont><a:latin typeface="Montserrat"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
         '<a:minorFont><a:latin typeface="PT Sans"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
         '<a:fmtScheme name="ГРАДО"><a:fillStyleLst>' + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' * 3
         + '</a:fillStyleLst><a:lnStyleLst>' + '<a:ln w="6350"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>' * 3
         + '</a:lnStyleLst><a:effectStyleLst>' + '<a:effectStyle><a:effectLst/></a:effectStyle>' * 3
         + '</a:effectStyleLst><a:bgFillStyleLst>' + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' * 3
         + '</a:bgFillStyleLst></a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/></a:theme>')
