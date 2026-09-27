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


_FONTS = {}


def _tw(text, family, size_mm):
    """Ширина строки в мм тем же шрифтом, что встроит PDF."""
    if family not in _FONTS:
        from grado_render import Font, find_font
        _FONTS[family] = Font(find_font(family))
    return _FONTS[family].text_width(str(text), size_mm)


def _wrap_mm(text, family, size_mm, width):
    """Перенос по словам по настоящей ширине строки (а не по числу знаков)."""
    lines = []
    for para in str(text or "").split("\n"):
        cur = ""
        for w in para.split():
            t = (cur + " " + w).strip()
            if cur and _tw(t, family, size_mm) > width:
                lines.append(cur)
                cur = w
            else:
                cur = t
        lines.append(cur)
    return lines


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
    """Округ и район в левом верхнем углу карты, как в «ГК Царицыно»: «Южный административный / округ» и ниже
    «район Царицыно», строки по центру, Century Gothic 15 пт жирный с белым ореолом — читается и на снимке."""

    def __init__(self, rect, lines):
        super().__init__(rect)
        self.lines = lines

    def ops(self, ctx):
        x, y, _, _ = self.rect
        out, yy = [], y + 7.7
        for n, text in enumerate(self.lines):
            if n:
                yy += 3.0                                              # район — отбит от округа
            for line in _wrap(text, 25):
                out.append({**_text(x + 50, yy, 14.3, line, INK, "gothic-bold", "middle"), "halo": 0.6})
                yy += 5.4
        return out


# ---------- листы по образцу «ГК Царицыно» (look: "concept"): карта слева, колонка справа ----------
CONCEPT_MAP, CONCEPT_COL = (7, 44, 279, 239), (293, 44, 120, 233)
PHOTO_MAP = (7, 44, 198, 152)
PHOTO_SLOTS = [(215, 44), (319, 44), (215, 125), (319, 125), (7, 206), (111, 206), (215, 206), (319, 206)]
INK2 = (0x23 / 255, 0x1F / 255, 0x20 / 255)
S10, S12 = 10 * PT, 12.3 * PT


def _rgb(c, default=(0.3, 0.3, 0.3)):
    if not c:
        return default
    from grado_render import hex_to_rgb
    return hex_to_rgb(c) if isinstance(c, str) else tuple(c)


def concept_swatch(x, y, it, lib=None, w=8.0, h=3.0):
    """Знак легенды 8 × 3 мм: заливка (с штриховкой), контур, линия (со штрихом), тип линии REDLN97, образец текста."""
    from print_io import _mix, hatch_ops, linetype_ops
    k, out = it.get("kind", "fill"), []
    rect = [[(x, y), (x + w, y), (x + w, y + h), (x, y + h)]]
    if k == "line":
        out.append({"op": "path", "closed": False, "fill": None, "stroke": _rgb(it.get("stroke")), "width": float(it.get("width", .5)),
                    "dash": it.get("dash"), "rings": [[(x, y + h / 2), (x + w, y + h / 2)]]})
    elif k == "lt":
        if lib and it.get("name"):
            out.extend(linetype_ops([(x, y + h / 2), (x + w, y + h / 2)], it["name"], 0.5, _rgb(it.get("stroke"), (1, 0, 0)), 0.3, lib))
        else:
            out.append({"op": "path", "closed": False, "fill": None, "stroke": _rgb(it.get("stroke"), (1, 0, 0)), "width": 0.45,
                        "dash": it.get("dash"), "rings": [[(x, y + h / 2), (x + w, y + h / 2)]]})
    elif k == "text":
        out.append({**_text(x + w / 2, y + h, float(it.get("size", 10)), it.get("sample", ""), _rgb(it.get("color"), INK),
                            it.get("family", "gothic-bold"), "middle"), **({"underline": True} if it.get("underline") else {})})
    else:
        fill = it.get("fill")
        if fill and not it.get("hatch"):
            out.append({"op": "path", "closed": True, "fill": _mix(fill, it.get("a", 1)), "stroke": None, "width": 0, "dash": None, "rings": rect})
        if it.get("hatch"):
            out.extend(hatch_ops(rect, spacing=float(it.get("spacing", 1.0)), stroke=_rgb(it.get("hatch_color") or fill),
                                 angle=float(it.get("angle", 45)), width=0.15))
        out.append({"op": "path", "closed": True, "fill": None, "stroke": _rgb(it.get("stroke") or fill or "#555555"),
                    "width": float(it.get("width", .2)), "dash": it.get("dash"), "rings": rect})
    return out


class ConceptColumnFrame(Frame):
    """Правая колонка листа по образцу «ГК Царицыно»: «Условные обозначения» (Century Gothic 12 пт жирный), группы
    с подчёркнутым заголовком, знаки 8 × 3 мм и подписи 10 пт; ниже — таблица зон Генплана, списки документов
    в рамках цвета документа, карточки земельных участков."""

    def __init__(self, rect, sheet, lib=None):
        super().__init__(rect)
        self.sheet, self.lib = sheet, lib

    def ops(self, ctx):
        x, y, w, h = self.rect
        sh, out, bottom = self.sheet, [], y + h
        yy = y + S12
        full = False
        if sh.get("cLegend"):
            out.append(_text(x, yy, 12.3, "Условные обозначения", INK, "gothic-bold"))
            yy += 8
            for g in sh["cLegend"]:
                if g.get("title"):
                    for line in _wrap_mm(g["title"], "gothic", S10, w):          # длинный заголовок группы — в две строки
                        out.append({**_text(x, yy, 10, line, INK2, "gothic"), "underline": True})
                        yy += 4.4
                    yy += 2.1
                for it in g.get("items", []):
                    lines = _wrap_mm(it.get("label", ""), "gothic", S10, w - 10.5)
                    if yy + (len(lines) - 1) * 4.2 > bottom - 2:
                        full = True
                        break
                    out.extend(concept_swatch(x, yy - 2.8, it, self.lib))
                    for i, line in enumerate(lines):
                        out.append(_text(x + 10.5, yy + i * 4.2, 10, line, INK2, "gothic"))
                    yy += 6.5 + (len(lines) - 1) * 4.2
                if full:
                    break
        tbl = sh.get("gpTable")
        if tbl and tbl.get("rows") and not full:
            yy += 5
            out.append(_text(x, yy, 12.3, tbl.get("title", ""), INK, "gothic-bold"))
            yy += 5
            widths = [w * c for c in tbl.get("widths", [.2, .2, .28, .32])]
            heads = [_wrap_mm(c, "gothic-bold", S10, cw - 2) for c, cw in zip(tbl["cols"], widths)]
            hh = max(len(t) for t in heads) * 4.2 + 3
            out.append({"op": "path", "closed": True, "fill": (0.9, 0.9, 0.9), "stroke": None, "width": 0, "dash": None,
                        "rings": [[(x, yy), (x + w, yy), (x + w, yy + hh), (x, yy + hh)]]})
            cx = x
            for t, cw in zip(heads, widths):
                for i, line in enumerate(t):
                    out.append(_text(cx + cw / 2, yy + 1.5 + S10 * .8 + i * 4.2 + (hh - 3 - len(t) * 4.2) / 2, 10, line, INK2, "gothic-bold", "middle"))
                cx += cw
            yy += hh + 2
            for row in tbl["rows"]:
                cells = [_wrap_mm(v, "gothic", S10, cw - 2) for v, cw in zip(row, widths)]
                rh = max(len(c) for c in cells) * 4.2 + 2
                if yy + rh > bottom:
                    break
                cx = x
                for c, cw in zip(cells, widths):
                    for i, line in enumerate(c):
                        out.append(_text(cx + cw / 2, yy + S10 * .8 + i * 4.2 + (rh - 2 - len(c) * 4.2) / 2, 10, line, INK2, "gothic", "middle"))
                    cx += cw
                yy += rh
        for blk in sh.get("cLists") or []:
            if full or yy > bottom - 12:
                break
            yy += 7
            for line in _wrap_mm(blk["title"], "gothic-bold", S12, w):
                out.append(_text(x, yy, 12.3, line, INK, "gothic-bold"))
                yy += 5
            yy += 1.5
            for n, it in enumerate(blk["items"]):
                lines = _wrap_mm(it["text"], "gothic", S10, w - 4)
                bh = len(lines) * 4.2 + 2.6
                if yy + bh > bottom:
                    out.append(_text(x, min(yy + 3, bottom), 9, f"… ещё {len(blk['items']) - n}: их номера есть на карте", (0.35, 0.35, 0.35), "gothic"))
                    full = True
                    break
                out.append({"op": "path", "closed": True, "fill": None, "stroke": _rgb(it.get("color"), INK), "width": 0.3, "dash": None,
                            "rings": [[(x, yy), (x + w, yy), (x + w, yy + bh), (x, yy + bh)]]})
                for i, line in enumerate(lines):
                    out.append(_text(x + 1.8, yy + 1.2 + S10 * .8 + i * 4.2, 10, line, INK2, "gothic"))
                yy += bh + 3.2
        cards = sh.get("cCards")
        if cards and cards.get("items") and not full:
            yy += 7
            for line in _wrap_mm(cards["title"], "gothic-bold", S12, w):
                out.append(_text(x, yy, 12.3, line, INK, "gothic-bold"))
                yy += 5
            yy += 2
            for n, card in enumerate(cards["items"]):
                rows = [(_wrap_mm(k, "gothic-bold", S10, w * .3), _wrap_mm(v, "gothic", S10, w * .64)) for k, v in card]
                ch = sum(max(len(a), len(b)) * 4.2 + 2.2 for a, b in rows)
                if yy + ch > bottom:
                    out.append(_text(x, min(yy + 3, bottom), 9, f"… и ещё участков: {len(cards['items']) - n} (кадастровые номера — на схеме)", (0.35, 0.35, 0.35), "gothic"))
                    break
                if n:
                    out.append({"op": "path", "closed": False, "fill": None, "stroke": (0.75, 0.75, 0.75), "width": 0.2, "dash": None,
                                "rings": [[(x, yy - 2.2), (x + w, yy - 2.2)]]})
                for a, b in rows:
                    rh = max(len(a), len(b)) * 4.2
                    for i, line in enumerate(a):
                        out.append(_text(x + 1, yy + 1.5 + i * 4.2 + (rh - len(a) * 4.2) / 2, 10, line, INK2, "gothic-bold"))
                    for i, line in enumerate(b):
                        out.append(_text(x + w * .34, yy + 1.5 + i * 4.2 + (rh - len(b) * 4.2) / 2, 10, line, INK2, "gothic"))
                    yy += rh + 2.2
                yy += 3
        return out


class OrthoLegendFrame(Frame):
    """Легенда ортофотоплана «ГК Царицыно»: белая плашка в правом нижнем углу листа поверх снимка."""

    def __init__(self, sheet, page_w, page_h):
        super().__init__((page_w - 122, page_h - 36, 122, 36))
        self.sheet = sheet

    def ops(self, ctx):
        x, y, w, h = self.rect
        groups = self.sheet.get("cLegend") or []
        items = [it for g in groups for it in g.get("items", [])]
        top = y + h - (13 + 6 * len(items))
        out = [{"op": "path", "closed": True, "fill": (1, 1, 1), "stroke": None, "width": 0, "dash": None,
                "rings": [[(x, top), (x + w, top), (x + w, y + h), (x, y + h)]]}]
        yy = top + 6.5
        out.append(_text(x + 3.6, yy, 12.2, "Условные обозначения", INK, "gothic-bold"))
        yy += 5.7
        out.append(_text(x + 3.6, yy, 9, "Границы:", INK2, "gothic-bold"))
        for it in items:
            yy += 5.8
            out.extend(concept_swatch(x + 3.6, yy - 2.6, it, None, w=15, h=3))
            out.append(_text(x + 21.6, yy, 9, it.get("label", ""), INK2, "gothic"))
        return out


class ConceptPhotoFrame(Frame):
    """Снимки фотофиксации «ГК Царицыно»: два ряда по два справа от карты и ряд из четырёх внизу, снимок заполняет
    ячейку 94 × 71 мм (лишнее обрезается), номер — на белой плашке в левом верхнем углу."""

    def __init__(self, sheet):
        super().__init__((0, 0, 420, 297))
        self.sheet = sheet

    def ops(self, ctx):
        import base64
        photos = [p for p in self.sheet.get("photos", []) if p.get("data")][:len(PHOTO_SLOTS)]
        if not photos:
            return [_text(313, 160, 11, "Снимки не добавлены: окно «Листы», кнопка с фотоаппаратом у этого листа", (0.45, 0.45, 0.45),
                          "gothic", "middle")]
        out = []
        for i, p in enumerate(photos):
            sx, sy = PHOTO_SLOTS[i]
            pw, ph = float(p.get("w") or 4), float(p.get("h") or 3)
            k = max(94 / pw, 71 / ph)
            iw, ih = pw * k, ph * k
            out += [{"op": "clip", "rect": (sx, sy, 94, 71)},
                    {"op": "image", "data": base64.b64decode(p["data"]), "x": sx + (94 - iw) / 2, "y": sy + (71 - ih) / 2, "w": iw, "h": ih},
                    {"op": "unclip"},
                    {"op": "path", "closed": True, "fill": (1, 1, 1), "stroke": None, "width": 0, "dash": None,
                     "rings": [[(sx, sy), (sx + 8.6, sy), (sx + 8.6, sy + 7.6), (sx, sy + 7.6)]]},
                    _text(sx + 4.3, sy + 6.2, 19, str(i + 1), INK2, "gothic-bold", "middle")]
        return out


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
    if sh.get("look") == "concept":                   # шапка ППТ КРТ, остальное — как в «ГК Царицыно»
        pw, ph = page.size
        if sh.get("kind") == "photos":
            r = tuple(sh.get("rect") or PHOTO_MAP)
            frames = [map_frame(r, sh), ConceptPhotoFrame(sh)]
        elif sh.get("bleed"):                         # ортофотоплан — во весь лист под шапкой, легенда на снимке
            r = tuple(sh.get("rect") or (0, 44, pw, ph - 44))
            frames = [map_frame(r, sh), OrthoLegendFrame(sh, pw, ph)]
        else:
            r = tuple(sh.get("rect") or CONCEPT_MAP)
            frames = [map_frame(r, sh), ConceptColumnFrame(CONCEPT_COL, sh, lib)]
        if sh.get("mapNote"):
            frames.append(MapNoteFrame(r, sh["mapNote"]))
        return frames + [deco]
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
