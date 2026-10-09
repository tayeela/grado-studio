"""Лист из нового редактора раскладки («Макет листа» в /next/, apps/grado2/ui/src/sheet) — в PDF и SVG.

Редактор присылает лист как есть: формат, штамп и элементы в мм листа (карта, легенда, надпись, картинка, стрелка
севера, масштабная линейка, таблица, прямоугольник, эллипс, линия), а для каждой карты — уже оформленные объекты
слоёв в её охвате (как листы альбома, print_io.sheetSpec). Карта рисуется тем же SketchMapFrame, что и альбом, остальное
повторяет рисование редактора (ui/src/sheet/draw.js): что на экране, то и на бумаге. Рамка и штамп — фреймы ядра.
map_svg — одна карта отдельной картинкой: её показывает блок карты в редакторе, чтобы масштаб и охват были точными.
"""

import base64
import io
import math

from grado_layout import Document, Page, PageBorder, StampFrame
from grado_layout.compose import _ctx
from grado_render import PdfBackend, hex_to_rgb, render_svg

import print_io

FORMATS = {"A4": (297, 210), "A3": (420, 297), "A2": (594, 420), "A1": (841, 594), "A0": (1189, 841)}
PT = 25.4 / 72                                   # 1 пт в мм: кегль надписи в редакторе — в пунктах
INK = (0.102, 0.102, 0.102)                      # #1a1a1a, как INK в draw.js
FONT = {"PT Sans": "ui", "PT Serif": "serif", "Montserrat": "sans"}
BASEMAPS = ("none", "light", "sat")


def _num(v, d=0.0, lo=-1e6, hi=1e6):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return d
    return d if v != v else max(lo, min(hi, v))


def page_size(sheet):
    a, b = FORMATS.get(sheet.get("format"), FORMATS["A3"])
    return (b, a) if sheet.get("orient") == "P" else (a, b)


def frame_rect(sheet):
    """Рамка листа, как frameRect в model.js: по ГОСТ (20 и 5 мм), без штампа — поля 2 %."""
    w, h = page_size(sheet)
    if sheet.get("stamp") is False:
        m = print_io.PAPER_MARGIN
        return (w * m, h * m, w * (1 - 2 * m), h * (1 - 2 * m))
    return (20, 5, w - 25, h - 10)


def _rgb(c, d=INK):
    v = hex_to_rgb(c) if isinstance(c, str) and c.startswith("#") else None
    return v if v is not None else d


def _fade(c, a):
    """Цвет с прозрачностью элемента поверх белой бумаги (у PDF ядра прозрачности нет)."""
    return None if c is None else tuple(1 - a * (1 - v) for v in c)


def _rect(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def _path(rings, fill=None, stroke=None, width=0.25, closed=True, dash=None):
    return {"op": "path", "rings": rings, "closed": closed, "fill": fill, "stroke": stroke, "width": width, "dash": dash}


def _baseline(top, fs, lh=1.0):
    """Konva ставит строку серединой в середину её высоты (fs × lh); базовая линия — ниже середины на ~0,32 кегля."""
    return top + fs * lh / 2 + 0.32 * fs


def _text(x, y, text, size, family="ui", color=INK, anchor="start"):
    return {"op": "text", "x": x, "y": y, "text": text, "size": size, "font_family": family, "color": color, "anchor": anchor}


def _fit(text, family, size, width):
    """Строка, обрезанная многоточием по ширине (ellipsis в Konva)."""
    if print_io._text_w(text, family, size) <= width:
        return text
    while text and print_io._text_w(text + "…", family, size) > width:
        text = text[:-1]
    return text + "…" if text else ""


def _wrap(text, family, size, width):
    lines = []
    for para in str(text).split("\n"):
        cur = ""
        for word in para.split(" "):
            t = f"{cur} {word}" if cur else word
            if cur and print_io._text_w(t, family, size) > width:
                lines.append(cur)
                cur = word
            else:
                cur = t
        lines.append(cur)
    return lines


def fmt_m(m):
    if m >= 1000:
        return f"{round(m / 1000, 2):g} км".replace(".", ",")
    return f"{round(m)} м"


def fmt_scale(s):
    return "1:" + f"{int(round(s)):,}".replace(",", " ")


def linked_scale(b, blocks):
    maps = [x for x in blocks if x.get("kind") == "map"]
    own = next((x for x in maps if x.get("id") == b.get("map")), None)
    return _num(b.get("scale")) or _num((own or {}).get("scale")) or _num((maps[0] if maps else {}).get("scale")) or 2000


def scalebar_step(w, scale):
    m = w * scale / 1000 / 4
    e = 10 ** math.floor(math.log10(m)) if m > 0 else 1
    return next((k * e for k in (5, 2, 1) if k * e <= m), e)


# ---------- Элементы листа: операции в собственных координатах элемента (0,0 — его левый верхний угол) ----------

def _legend(b):
    pad, row, fs, sw, sh = 3, 6.5, 2.8, 8, 4
    out = [_text(pad, _baseline(pad, 3.4), _fit(b.get("title") or "", "ui-bold", 3.4, b["w"] - 2 * pad), 3.4, "ui-bold")]
    for i, it in enumerate(b.get("items") or []):
        y = pad + 7 + i * row
        if y + row > b["h"] or not isinstance(it, dict):
            continue
        c = _rgb(it.get("c"))
        if it.get("s") == "line":
            dash = [max(0.1, _num(d)) for d in it["dash"]] if isinstance(it.get("dash"), list) and it["dash"] else None
            out.append(_path([[(pad, y + sh / 2), (pad + sw, y + sh / 2)]], stroke=c, width=0.6, closed=False, dash=dash))
        else:
            out.append(_path([_rect(pad, y, sw, sh)], fill=_rgb(it.get("f"), None), stroke=c, width=0.3))
        out.append(_text(pad + sw + 2.5, _baseline(y + .3, fs), _fit(str(it.get("t") or ""), "ui", fs, b["w"] - 2 * pad - sw - 2.5), fs))
    return out


def _table(b):
    rows, cols = max(1, int(_num(b.get("rows"), 1, 1, 200))), max(1, int(_num(b.get("cols"), 1, 1, 50)))
    th = 6 if b.get("title") else 0
    rh, cw, out = (b["h"] - th) / (rows + 1), b["w"] / cols, []
    if b.get("title"):
        out.append(_text(b["w"] / 2, _baseline(.8, 3.2), str(b["title"]), 3.2, "ui-bold", anchor="middle"))
    out.append(_path([_rect(0, th, b["w"], rh)], fill=(0.945, 0.953, 0.961), width=0))
    for r in range(rows + 2):
        out.append(_path([[(0, th + r * rh), (b["w"], th + r * rh)]], stroke=INK, width=.35 if r == 1 else .18, closed=False))
    for c in range(cols + 1):
        out.append(_path([[(c * cw, th), (c * cw, b["h"])]], stroke=INK, width=.18, closed=False))
    for c, t in enumerate(["Показатель", "Ед.", "Значение"][:cols]):
        out.append(_text(c * cw + 1, _baseline(th + rh / 2 - 1.3, 2.6), _fit(t, "ui-bold", 2.6, cw - 2), 2.6, "ui-bold"))
    return out


def _textblock(b):
    fam = FONT.get(b.get("font"), "ui") + ("-bold" if b.get("bold") else "")
    fs, lh = _num(b.get("size"), 12, 1, 400) * PT, 1.15
    lines = _wrap(b.get("text") or "", fam, fs, b["w"])
    total = len(lines) * fs * lh
    top = {"middle": (b["h"] - total) / 2, "bottom": b["h"] - total}.get(b.get("valign"), 0)
    x, anchor = {"center": (b["w"] / 2, "middle"), "right": (b["w"], "end")}.get(b.get("align"), (0, "start"))
    color = _rgb(b.get("color"))
    return [_text(x, _baseline(top + i * fs * lh, fs, lh), ln, fs, fam, color, anchor) for i, ln in enumerate(lines) if ln]


def _picture(b):
    src = b.get("src") or ""
    if not src.startswith("data:image/") or "," not in src:
        return [_path([_rect(0, 0, b["w"], b["h"])], stroke=(0.77, 0.8, 0.83), width=.25, dash=[1.5, 1])]
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(base64.b64decode(src.split(",", 1)[1]))).convert("RGBA")
        flat = Image.new("RGB", im.size, (255, 255, 255))
        flat.paste(im, mask=im.split()[3])
        buf = io.BytesIO()
        flat.save(buf, "JPEG", quality=92)
    except Exception:
        return [_path([_rect(0, 0, b["w"], b["h"])], stroke=(0.77, 0.8, 0.83), width=.25, dash=[1.5, 1])]
    k = min(b["w"] / im.width, b["h"] / im.height)          # вписать с сохранением пропорций, как в редакторе
    w, h = im.width * k, im.height * k
    return [{"op": "image", "x": (b["w"] - w) / 2, "y": (b["h"] - h) / 2, "w": w, "h": h, "data": buf.getvalue()}]


def _north(b):
    w, h = b["w"], b["h"]
    return [_path([[(w / 2, h * .28), (w * .85, h), (w / 2, h * .8)]], fill=INK, width=0),
            _path([[(w / 2, h * .28), (w * .15, h), (w / 2, h * .8)]], fill=(1, 1, 1), stroke=INK, width=.25),
            _text(w / 2, _baseline(0, h * .26), "С", h * .26, "ui-bold", anchor="middle")]


def _scalebar(b, blocks):
    sc = linked_scale(b, blocks)
    step = scalebar_step(b["w"], sc)
    seg, bh, out = step * 1000 / sc, min(1.6, b["h"] / 4), []
    for i in range(4):
        out.append(_path([_rect(i * seg, b["h"] - bh - 3, seg, bh)], fill=(1, 1, 1) if i % 2 else INK, stroke=INK, width=.2))
    for i in range(5):
        out.append(_text(i * seg, _baseline(b["h"] - 2.5, 2), fmt_m(step * i) if i else "0", 2, anchor="middle"))
    out.append(_text(0, _baseline(max(0, b["h"] - bh - 7), 2.4), fmt_scale(sc), 2.4))
    return out


def _ellipse(b, n=72):
    rx, ry = b["w"] / 2, b["h"] / 2
    return [(rx + rx * math.cos(2 * math.pi * i / n), ry + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _line(b):
    c, wd = _rgb((b.get("frame") or {}).get("color")), _num((b.get("frame") or {}).get("width"), .5, .05, 20)
    y = b["h"] / 2
    if not b.get("arrow"):
        return [_path([[(0, y), (b["w"], y)]], stroke=c, width=wd, closed=False)]
    return [_path([[(0, y), (b["w"] - 2.5, y)]], stroke=c, width=wd, closed=False),
            _path([[(b["w"], y), (b["w"] - 2.5, y - 1), (b["w"] - 2.5, y + 1)]], fill=c, stroke=c, width=wd)]


def _placeholder(b, text):
    return [_path([_rect(0, 0, b["w"], b["h"])], fill=(0.933, 0.949, 0.925), width=0),
            _text(b["w"] / 2, b["h"] / 2, text, max(2, min(5, b["w"] / 30, b["h"] / 8)), color=(0.36, 0.42, 0.34), anchor="middle")]


def map_sheet(b, mp):
    """Блок карты → лист для SketchMapFrame: центр (долгота, широта), масштаб, подложка и слои в охвате блока."""
    c = b.get("center")
    if not (isinstance(c, (list, tuple)) and len(c) == 2) or _num(b.get("scale")) <= 0:
        return None
    lon, lat = _num(c[0], None, -180, 180), _num(c[1], None, -85, 85)
    if lon is None or lat is None:
        return None
    mp = mp if isinstance(mp, dict) else {}
    basemap = b.get("basemap") if b.get("basemap") in BASEMAPS else "none"
    # noFrame: рамку, стрелку севера и линейку ставит сам лист (свои элементы редактора), у карты их нет
    return {"center": [lon, lat], "scale": _num(b["scale"], 2000, 50, 5e6), "basemap": basemap, "noFrame": True,
            "layers": [l for l in (mp.get("layers") or []) if isinstance(l, dict)]}


def _map(b, mp, lib, lgr_dash, tiles):
    """Карта в мм листа: SketchMapFrame альбома в прямоугольнике блока (поворот карты не поддержан — как в альбоме)."""
    sh = map_sheet(b, mp)
    if sh is None:
        return _placeholder(b, "Карта: укажите место — «Как на карте»")
    return print_io.SketchMapFrame((b["x"], b["y"], b["w"], b["h"]), sh, lib, lgr_dash, tiles).ops({})


def _local(b, blocks):
    """Операции элемента в его координатах; карта рисуется отдельно (в координатах листа)."""
    kind = b.get("kind")
    if kind == "ellipse":
        bg, fr = b.get("bg") or {}, b.get("frame") or {}
        return [_path([_ellipse(b)], fill=_rgb(bg.get("color"), (1, 1, 1)) if bg.get("on") else None,
                      stroke=_rgb(fr.get("color")) if fr.get("on") else None, width=_num(fr.get("width"), .25, 0, 20))]
    if kind == "line":
        return _line(b)
    out = []
    bg = b.get("bg") or {}
    if bg.get("on"):
        out.append(_path([_rect(0, 0, b["w"], b["h"])], fill=_rgb(bg.get("color"), (1, 1, 1)), width=0))
    out += {"legend": _legend, "table": _table, "text": _textblock, "picture": _picture, "north": _north,
            "scalebar": lambda x: _scalebar(x, blocks)}.get(kind, lambda x: [])(b)
    return out


def _frame_ops(b):
    fr = b.get("frame") or {}
    if not fr.get("on") or b.get("kind") in ("ellipse", "line"):
        return []
    return [_path([_rect(0, 0, b["w"], b["h"])], stroke=_rgb(fr.get("color")), width=_num(fr.get("width"), .25, 0, 20))]


def _place(ops, b):
    """Из координат элемента — в лист: сдвиг, поворот вокруг левого верхнего угла (как в Konva), прозрачность."""
    x0, y0, a = b["x"], b["y"], math.radians(_num(b.get("rotation")))
    ca, sa, op = math.cos(a), math.sin(a), _num(b.get("opacity"), 1, 0, 1)
    pt = lambda x, y: (x0 + x * ca - y * sa, y0 + x * sa + y * ca)
    out = []
    for o in ops:
        o = dict(o)
        if o["op"] == "path":
            o["rings"] = [[pt(x, y) for x, y in r] for r in o["rings"]]
            o["fill"], o["stroke"] = _fade(o.get("fill"), op), _fade(o.get("stroke"), op)
        elif o["op"] == "text":
            o["x"], o["y"] = pt(o["x"], o["y"])
            o["angle"] = o.get("angle", 0) + a
            o["color"] = _fade(o.get("color"), op)
        elif o["op"] == "image":
            x, y, w, h = o.pop("x"), o.pop("y"), o.pop("w"), o.pop("h")
            if a:
                o["quad"] = (pt(x, y), pt(x + w, y), pt(x, y + h))
            else:
                o.update(x=x0 + x, y=y0 + y, w=w, h=h)
        out.append(o)
    return out


def _block(b):
    b = dict(b)
    for k, d in (("x", 0), ("y", 0), ("w", 10), ("h", 10)):
        b[k] = _num(b.get(k), d, -1e4 if k in "xy" else .1, 1e4)
    return b


class _Blocks:
    """Элементы листа одной «рамкой» страницы: снизу вверх в порядке списка, как слои Konva."""

    def __init__(self, sheet, maps, lib, lgr_dash, tiles):
        self.sheet, self.maps, self.lib, self.lgr_dash, self.tiles = sheet, maps, lib, lgr_dash, tiles

    def ops(self, ctx):
        raw = [b for b in self.sheet.get("blocks") or [] if isinstance(b, dict)]
        blocks = [_block(b) for b in raw]
        out = []
        for b in blocks:
            if b.get("hidden"):
                continue
            if b.get("kind") == "map":
                own = _place(_frame_ops(b), {**b, "rotation": 0, "opacity": 1})
                out += _map(b, self.maps.get(b.get("id")), self.lib, self.lgr_dash, self.tiles) + own
            else:
                out += _place(_local(b, blocks) + _frame_ops(b), b)
        return out


class _PaperBorder:
    def __init__(self, rect):
        self.rect = rect

    def ops(self, ctx):
        return [_path([_rect(*self.rect)], stroke=INK, width=.35)]


def _doc(spec):
    meta = spec.get("meta") if isinstance(spec.get("meta"), dict) else {}
    m = {k: str(meta.get(k) or "") for k in ("object", "code", "stage", "org")}
    return Document(m["object"] or "Лист", meta=m)


def _page(doc, item, lib, lgr_dash, tiles, no, total):
    """Один лист: {sheet, maps: {id карты: {layers}}} → (w, h, ops); no и total — «Лист» и «Листов» штампа."""
    sheet = item.get("sheet") if isinstance(item.get("sheet"), dict) else {}
    maps = item.get("maps") if isinstance(item.get("maps"), dict) else {}
    page = Page(page_size(sheet))
    blocks = _Blocks(sheet, maps, lib, lgr_dash, tiles)
    page.frames = ([PageBorder(page), StampFrame(page), blocks] if sheet.get("stamp") is not False
                   else [_PaperBorder(frame_rect(sheet)), blocks])
    ctx = _ctx(doc, None, None, None, no, str(sheet.get("title") or ""))
    ctx["page_total"] = str(total)
    w, h = page.size
    return w, h, page.ops(ctx)


def build_pages(spec, lib, lgr_dash, tiles=None):
    """spec = {meta, sheets: [{sheet, maps}]} — все листы макета одним документом, либо {meta, sheet, maps, page:
    {page_no, page_total}} — один лист с его номером в списке листов."""
    doc = _doc(spec)
    if isinstance(spec.get("sheets"), list):
        items = [x for x in spec["sheets"] if isinstance(x, dict)]
        return [_page(doc, x, lib, lgr_dash, tiles, i, len(items)) for i, x in enumerate(items, start=1)]
    pg = spec.get("page") if isinstance(spec.get("page"), dict) else {}
    no, total = int(_num(pg.get("page_no"), 1, 1, 9999)), int(_num(pg.get("page_total"), 1, 1, 9999))
    return [_page(doc, spec, lib, lgr_dash, tiles, no, max(no, total))]


def build_page(spec, lib, lgr_dash, tiles=None):
    return build_pages(spec, lib, lgr_dash, tiles)[0]


def render_pdf(spec, lib, lgr_dash, tiles=None):
    pages = build_pages(spec, lib, lgr_dash, tiles)
    if not pages:
        raise ValueError("no sheets")
    return PdfBackend(None).render(pages)


def render_page_svg(spec, lib, lgr_dash, tiles=None):
    return render_svg(*build_page(spec, lib, lgr_dash, tiles))


def map_svg(spec, lib, lgr_dash, tiles=None):
    """Одна карта блока картинкой SVG (w × h мм): {block: {w, h, center, scale, basemap}, layers}."""
    b = _block({**(spec.get("block") or {}), "x": 0, "y": 0})
    sh = map_sheet(b, {"layers": spec.get("layers")})
    if sh is None:
        raise ValueError("map block: center and scale required")
    ops = print_io.SketchMapFrame((0, 0, b["w"], b["h"]), sh, lib, lgr_dash, tiles).ops({})
    return render_svg(b["w"], b["h"], ops)
