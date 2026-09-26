"""Альбомы по образцам владельца (26.09.2026): «План реализации ППТ КРТ» — по его шаблону PowerPoint
(«ППТ_КРТ Шаблон (И).pptx», А3 альбомный, красная шапка) и «Градостроительная концепция» — по образцу
«ГК Царицыно» (А3 альбомный, белый лист, заголовок справа).

Размеры, цвета и шрифты сняты с самого шаблона (мм листа 420 × 297): шапка — картинка волны из макета
(docs/standards/albums/pptkrt-header.jpg), заголовки и номер листа — Montserrat жирный 18–20 пт, красный E93939,
подписи карт — PT Sans жирный с белым ореолом (в шаблоне Arial/Tahoma со свечением F5F5F5).

Лист задаёт стиль полем style: "pptkrt" или "concept"; build_document в print_io передаёт такие листы сюда."""

from pathlib import Path

from grado_layout.model import Frame

HERE = Path(__file__).resolve().parent
ALBUMS = HERE.parents[1] / "docs" / "standards" / "albums"
RED = (0xE9 / 255, 0x39 / 255, 0x39 / 255)
RED_TITLE = (0xE7 / 255, 0x39 / 255, 0x39 / 255)
INK = (0.08, 0.08, 0.08)
PT = 0.3528                                     # мм в пункте
# листы с картой (состав — по «ГК Царицыно»): карта слева, как в шаблоне, справа колонка легенды и списков; у листа
# фотофиксации карта уже, справа снимки
MAP_RECT, PHOTO_MAP_RECT, RIGHT = (24, 44, 263, 233), (24, 44, 170, 233), 412


def _header():
    try:
        return (ALBUMS / "pptkrt-header.jpg").read_bytes()
    except OSError:
        return None


def _wrap(text, n):
    words, lines, cur = str(text or "").split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > n:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    return lines + ([cur] if cur else [])


def _text(x, y, size_pt, text, color=INK, family="sans-bold", anchor="start"):
    return {"op": "text", "x": x, "y": y, "size": size_pt * PT, "text": str(text), "color": color, "anchor": anchor,
            "font_family": family}


def _fit_pt(text, family, size_pt, width_mm, min_pt=12):
    """Кегль заголовка, при котором строка влезает в ширину: длинные названия листов «Царицыно» (до 100 знаков)
    на 18 пт вышли бы за край листа."""
    try:
        from grado_render import Font, find_font
        w = Font(find_font(family)).text_width(str(text), size_pt * PT)
    except Exception:
        return size_pt
    return size_pt if w <= width_mm else max(min_pt, size_pt * width_mm / w)


def _tab(x, y, w, h):
    """Плашка номера листа шаблона: прямоугольник с крупным скруглением слева сверху и справа снизу."""
    r1, r2 = h * .3, h * .38
    return [(x + r2 * .5, y + h), (x + w - r2, y + h), (x + w, y + h - r2), (x + w, y + r1 * .3), (x + w - r1 * .3, y),
            (x + r1, y), (x, y + r1), (x, y + h - r2 * .5)]


class PptKrtFrame(Frame):
    """Оформление листа шаблона ППТ КРТ: шапка-волна, «ППТ КРТ … (АО, район)» справа, красный заголовок со
    стрелкой, номер на красной плашке. Титульный лист — красный блок слева, белая рамка, текст белым."""

    def __init__(self, page, sheet, meta):
        super().__init__((0, 0) + tuple(page.size))
        self.sheet, self.meta = sheet, meta

    def ops(self, ctx):
        w, h = self.rect[2], self.rect[3]
        sh, m, out = self.sheet, self.meta, []
        place = m.get("place") or ""
        if sh.get("kind") == "title":
            out.append({"op": "path", "closed": True, "fill": RED_TITLE, "stroke": None, "width": 0, "dash": None,
                        "rings": [[(0, 0), (224.8, 0), (224.8, h), (0, h)]]})
            out.append({"op": "path", "closed": True, "fill": None, "stroke": (1, 1, 1), "width": 1.6, "dash": None,
                        "rings": [[(16, 16.4), (224.8, 16.4), (224.8, 280.5), (16, 280.5)]]})
            yy = 132
            for line in _wrap("Об одобрении плана реализации и утверждении проекта планировки комплексного развития "
                              "территории по адресу:", 34):
                out.append(_text(24, yy, 20, line, (1, 1, 1), "sans"))
                yy += 9
            yy += 4
            for line in _wrap(m.get("address") or m.get("object") or "АДРЕС", 30):
                out.append(_text(24, yy, 22, line, (1, 1, 1), "sans-bold"))
                yy += 9.5
            if place:
                out.append(_text(24, yy + 5, 20, f"({place})", (1, 1, 1), "sans"))
            if m.get("date"):
                out.append(_text(26, 268, 22, m["date"], (1, 1, 1), "sans-bold"))
            return out
        hdr = _header()
        out.append({"op": "path", "closed": True, "fill": (0xF2 / 255,) * 3, "stroke": None, "width": 0, "dash": None,
                    "rings": [[(264.5, 0), (w, 0), (w, 27.85), (264.5, 27.85)]]})
        if hdr:
            out.append({"op": "image", "data": hdr, "x": 0, "y": 0, "w": 265.1, "h": 27.8})
        short = m.get("short") or m.get("object") or ""
        out.append(_text(w - 7, 16, 18, f"ППТ КРТ {short}".strip(), anchor="end"))
        if place:
            out.append(_text(w - 7, 24, 18, f"({place})", anchor="end"))
        out.append({"op": "path", "closed": False, "fill": None, "stroke": RED, "width": 1.06, "dash": None,
                    "rings": [[(0, 35), (45.5, 35)]]})
        out.append({"op": "path", "closed": True, "fill": RED, "stroke": None, "width": 0, "dash": None,
                    "rings": [[(44, 33), (49, 35), (44, 37)]]})
        out.append(_text(51, 37.4, _fit_pt(sh.get("title", ""), "sans-bold", 18, w - 51 - 8), sh.get("title", ""), RED))
        out.append({"op": "path", "closed": True, "fill": RED, "stroke": None, "width": 0, "dash": None,
                    "rings": [_tab(399, 278.7, 17.8, 12.7)]})
        out.append(_text(407.9, 288, 20, ctx.get("page_no", ""), (1, 1, 1), "sans-bold", "middle"))
        return out


class CalloutFrame(Frame):
    """Выноска шаблона «рассматриваемая территория / Район …»: скруглённая пунктирная рамка между двумя картами
    и тонкие линии от неё к точке территории на каждой карте (точка — кружок на конце линии)."""

    def __init__(self, box, lines, targets):
        super().__init__(box)
        self.lines, self.targets = lines, targets        # targets — [(x, y) мм листа]

    def ops(self, ctx):
        x, y, w, h = self.rect
        out = []
        for tx, ty in self.targets:
            sx = x if tx < x else x + w
            mid = (sx + tx) / 2
            out.append({"op": "path", "closed": False, "fill": None, "stroke": (0, 0, 0), "width": 0.22, "dash": None,
                        "rings": [[(sx, y + h / 2), (mid, y + h / 2), (tx, ty)]]})
        r = 3.0
        ring = [(x + r, y), (x + w - r, y), (x + w, y + r), (x + w, y + h - r), (x + w - r, y + h), (x + r, y + h),
                (x, y + h - r), (x, y + r)]
        out.append({"op": "path", "closed": True, "fill": (1, 1, 1), "stroke": (0, 0, 0), "width": 0.53,
                    "dash": [0.5, 0.9], "rings": [ring]})
        n = len(self.lines)
        for i, (t, bold) in enumerate(self.lines):
            out.append(_text(x + w / 2, y + h / 2 + (i - (n - 1) / 2) * 4.2 + 1.2, 9, t, INK, "ui-bold" if bold else "ui",
                             "middle"))
        return out


class MapNoteFrame(Frame):
    """Округ и район в левом верхнем углу карты («Южный административный округ / район Царицыно»), с ореолом —
    читается и на снимке."""

    def __init__(self, rect, lines):
        super().__init__(rect)
        self.lines = lines

    def ops(self, ctx):
        x, y, _, _ = self.rect
        return [{**_text(x + 4, y + 7 + i * 4.6, 11, line, INK, "ui-bold"), "halo": 0.7} for i, line in enumerate(self.lines)]


class OkrugTitleFrame(Frame):
    """Название округа крупно в правом верхнем углу карты округа («СЕВЕРНЫЙ АДМИНИСТРАТИВНЫЙ ОКРУГ»)."""

    def __init__(self, rect, text):
        super().__init__(rect)
        self.text = text

    def ops(self, ctx):
        x, y, w, _ = self.rect
        out = []
        for i, line in enumerate(_wrap(str(self.text).upper(), 16)):
            out.append({**_text(x + w - 4, y + 9 + i * 6.2, 16, line, INK, "sans-bold", "end"), "halo": 0.6})
        return out


def build_pptkrt(page, sh, meta, lib, lgr_dash, tiles, map_frame):
    """Рамки листа шаблона ППТ КРТ. map_frame(rect, sheet) — карта печати (SketchMapFrame) для этой рамки."""
    deco = PptKrtFrame(page, sh, meta)
    if sh.get("kind") == "title":
        return [deco]
    frames = []
    if sh.get("panels"):
        maps = []
        for p in sh["panels"]:
            f = map_frame(tuple(p["rect"]), p)
            maps.append(f)
            frames.append(f)
            if p.get("okrugTitle"):
                frames.append(OkrugTitleFrame(tuple(p["rect"]), p["okrugTitle"]))
        if sh.get("callout") and sh.get("territory_lonlat"):
            from print_io import MapTransform
            pts = []
            for f in maps:
                tr = MapTransform(f.rect, f.sheet["center"], f.sheet["scale"])
                pts.append(tr.mm(*sh["territory_lonlat"]))
            box = tuple(sh.get("calloutBox") or (187, 185, 47, 21))
            frames.append(CalloutFrame(box, [(t, i > 0) for i, t in enumerate(sh["callout"])], pts))
    elif sh.get("kind") == "photos":
        from print_io import PhotoGridFrame
        r = tuple(sh.get("rect") or PHOTO_MAP_RECT)
        gx = r[0] + r[2] + 6
        frames += [map_frame(r, sh), PhotoGridFrame((gx, r[1], RIGHT - gx, r[3]), sh)]
    else:
        from print_io import ColumnFrame
        r = tuple(sh.get("rect") or MAP_RECT)
        frames.append(map_frame(r, sh))
        cx = r[0] + r[2] + 7
        if sh.get("legend") or sh.get("table") or sh.get("lists") or sh.get("note"):
            frames.append(ColumnFrame((cx, r[1] + 2, RIGHT - cx, r[3] - 2), sh, title=False))
    if sh.get("mapNote") and not sh.get("panels"):
        frames.append(MapNoteFrame(tuple(sh.get("rect") or (PHOTO_MAP_RECT if sh.get("kind") == "photos" else MAP_RECT)), sh["mapNote"]))
    return frames + [deco]
