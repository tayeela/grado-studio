"""Альбомы по образцам владельца (26.09.2026): «План реализации ППТ КРТ» — по его шаблону PowerPoint
(«ППТ_КРТ Шаблон (И).pptx», А3 альбомный, красная шапка) и «Градостроительная концепция» — по образцу
«ГК Царицыно» (А3 альбомный, белый лист, заголовок справа).

Размеры, цвета и шрифты сняты с самого шаблона (мм листа 420 × 297): шапка — картинка волны из макета
(docs/standards/albums/pptkrt-header.jpg), заголовки и номер листа — Montserrat жирный 18–20 пт, красный E93939,
подписи карт — PT Sans жирный с белым ореолом (в шаблоне Arial/Tahoma со свечением F5F5F5).

Лист задаёт стиль полем style: "pptkrt" или "concept"; build_document в print_io передаёт такие листы сюда."""

import base64
import binascii
import re
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


MAX_PHOTO_B64 = 25 * 2**20                      # снимок в запросе — base64 не длиннее 25 МБ (JPEG из canvas — сотни КБ)


def photo_bytes(p):
    """Байты снимка из поля data (base64) или None: слишком длинный, не base64 или не JPEG/PNG по первым байтам.
    Такой снимок пропускается — в PDF пишутся только настоящие изображения."""
    data = p.get("data")
    if not isinstance(data, str) or len(data) > MAX_PHOTO_B64:
        return None
    try:
        raw = base64.b64decode(data)
    except (binascii.Error, ValueError):
        return None
    return raw if raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n" else None


def _header():
    try:
        return (ALBUMS / "pptkrt-header.jpg").read_bytes()
    except OSError:
        return None


_NB = "\xa0"
_GLUE_AFTER = re.compile(r"(?<![\w.])(№|[А-Яа-яЁёA-Za-z]{1,2}\.?|ул\.|пер\.|пр-д|просп\.|ш\.|р\.|д\.|пос\.|оз\.|тыс\.|им\.|кв\.|т\.) (?=\S)")
_GLUE_BEFORE = re.compile(r"(?<=\S) (г\.|гг\.|га|м|м²|мм|км|млн|—|–)(?=$|[\s,.;:)»])")


def _glue(text):
    """Общепринятые правила вёрстки (правило 12): предлоги, союзы, частицы и короткие слова не висят в конце строки,
    сокращения держатся за своё слово («№ 1218», «ул. Садовая», «2021 г.», «тыс. кв. м», «48,52 га»), тире не
    начинает строку — между ними неразрывный пробел."""
    t = str(text or "")
    for _ in range(2):                                   # «с по» и цепочки коротких слов — за два прохода
        t = _GLUE_AFTER.sub(lambda m: m.group(1) + _NB, t)
    return _GLUE_BEFORE.sub(lambda m: _NB + m.group(1), t)


def _wrap(text, n):
    words, lines, cur = [w for w in _glue(text).split(" ") if w], [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > n:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    return [ln.replace(_NB, " ") for ln in lines + ([cur] if cur else [])]


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


# место переноса составного слова — после его дефиса между буквами: «природно-/жилая»; слова с цифрами («1218-ПП»,
# «РФ-77-4-59-…») не делятся (правила 2.17, 2.35)
_HYPH = re.compile(r"(?<=[А-Яа-яЁёA-Za-z]-)(?=[А-Яа-яЁёA-Za-z])")


def _hyph_parts(word):
    return _HYPH.split(word) if "-" in word and not re.search(r"\d", word) else [word]


def _wrap_para(para, family, size_mm, width, hyph=False):
    lines, cur = [], ""
    for w in [w for w in para.replace("\t", " ").split(" ") if w]:   # неразрывный пробел (\xa0) держит слова вместе
        # ячейка таблицы: составное слово шире колонки переносится после своего дефиса (владелец 01.10.2026)
        parts = _hyph_parts(w) if hyph and _tw(w.replace("\xa0", " "), family, size_mm) > width else [w]
        for k, piece in enumerate(parts):
            t = (cur + (" " if k == 0 else "") + piece).strip() if cur else piece
            if cur and _tw(t.replace("\xa0", " "), family, size_mm) > width:
                lines.append(cur)
                cur = piece
            else:
                cur = t
    return lines + [cur]


def _wrap_mm(text, family, size_mm, width, orphan=True, hyph=False):
    """Перенос по словам по настоящей ширине строки (а не по числу знаков). orphan — последняя строка абзаца не бывает
    одним словом короче 8 знаков («…на кадастровый / учёт»): два последних слова связываются и переносятся вместе
    (владелец 01.10.2026, правило 2.22). Ячейки таблиц — без этого (узкая колонка разошлась бы на лишние строки), зато
    с hyph: составное слово шире колонки переносится после своего дефиса."""
    lines = []
    for para in _glue(text).split("\n"):
        para = para.rstrip()
        out = _wrap_para(para, family, size_mm, width, hyph)
        while orphan and len(out) > 1 and len(out[-1].replace("\xa0", " ").split()) < 2 and len(out[-1]) < 8:
            i = para.rfind(" ")                            # пробел перед последним словом абзаца
            pair = para[para.rfind(" ", 0, i) + 1:].strip() if i > 0 else ""
            if i <= 0 or _tw(pair.replace("\xa0", " "), family, size_mm) > width:
                break
            para = para[:i] + "\xa0" + para[i + 1:]
            out = _wrap_para(para, family, size_mm, width, hyph)
        lines += out
    return [ln.replace("\xa0", " ") for ln in lines]


def _title_lines(text, size_pt=18, width=361):
    """Название листа — всегда 18 пт (владелец 01.10.2026): одна строка, если помещается, иначе две строки примерно
    равной длины (перенос только по пробелам, предлоги и сокращения держатся за своё слово). Не помещается и в две —
    (две первые строки, False): лист помечается «не готов»."""
    s, size_mm = _glue(text), size_pt * PT
    one = s.replace("\xa0", " ")
    if _tw(one, "sans-bold", size_mm) <= width:
        return [one], True
    words, best = [w for w in s.split(" ") if w], None
    for i in range(1, len(words)):
        a, b = (" ".join(words[:i]).replace("\xa0", " "), " ".join(words[i:]).replace("\xa0", " "))
        wa, wb = _tw(a, "sans-bold", size_mm), _tw(b, "sans-bold", size_mm)
        if wa <= width and wb <= width and (best is None or max(wa, wb) < best[0]):
            best = (max(wa, wb), [a, b])
    if best:
        return best[1], True
    return _wrap_mm(text, "sans-bold", size_mm, width)[:2], False


def _col_widths(widths, cols, rows, size_mm):
    """Ширины колонок таблицы (правило 6.11): колонка не уже самого длинного неделимого слова плюс 2 мм — недостающее
    берётся у колонок с запасом, пропорционально запасу. Сначала без переноса слов, если не выходит — с переносом
    составных слов по дефису (владелец 01.10.2026). None — не помещается и так."""
    def need(split):
        out = []
        for j, head in enumerate(cols):
            cells = [(head, "sans-bold")] + [(r[j], "sans") for r in rows if j < len(r)]
            m = 0
            for text, fam in cells:
                for w in _glue(str(text)).replace("\n", " ").split(" "):
                    for piece in (_hyph_parts(w) if split else [w]):
                        if piece:
                            m = max(m, _tw(piece.replace("\xa0", " "), fam, size_mm))
            out.append(m + 2)
        return out
    for split in (False, True):
        nd = need(split)
        short = sum(max(0, n - w) for n, w in zip(nd, widths))
        spare = sum(max(0, w - n) for n, w in zip(nd, widths))
        if short <= spare + 1e-6:
            if short < 1e-6:
                return list(widths)
            return [n if n > w else w - (w - n) * short / spare for n, w in zip(nd, widths)]
    return None


NOTE_GREY = (0x59 / 255,) * 3


def _not_ready(sheet, reason):
    """Пометка «не готов»: лист не выпускается до решения владельца (правила 1.29, 1.43). Сервер сообщает номера
    таких листов; сама пометка печатается на листе серым 9 пт."""
    lst = sheet.setdefault("_notReady", [])
    if reason not in lst:
        lst.append(reason)


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
                out.append(_text(24, 268, 22, m["date"], (1, 1, 1), "sans-bold"))   # общий левый край с текстом
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
        # название — всегда 18 пт; длинное — в две строки по центру стрелки (y = 35): стрелка шаблона на месте, вторая
        # строка кончается выше карты (y = 44) (владелец 01.10.2026, правила 1.27–1.29)
        lines, fits = _title_lines(sh.get("title", ""), 18, w - 51 - 8)
        if len(lines) == 1:
            out.append(_text(51, 37.4, 18, lines[0], RED))
        else:
            lead = 7.4
            b1 = 35 + (0.7 * 18 * PT - lead) / 2                        # середина блока (верх прописных — база 2-й строки) на стрелке
            for i, line in enumerate(lines):
                out.append(_text(51, b1 + i * lead, 18, line, RED))
        if not fits:
            _not_ready(sh, "название не помещается в две строки по 18 пт")
        if sh.get("_notReady"):          # пометка «не готов» — под картой слева; рамки листа рисуются раньше шапки
            note = _wrap_mm("Лист не готов: " + "; ".join(sh["_notReady"]), "sans", 9 * PT, 385)   # целиком: снизу вверх
            for i, line in enumerate(note):
                out.append(_text(7, 292 - (len(note) - 1 - i) * 3.8, 9, line, NOTE_GREY, "sans"))
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
            out.append(_text(x + w / 2, y + h / 2 + (i - (n - 1) / 2) * 4.2 + 1.2, 9, t, INK, "sans-bold" if bold else "sans",
                             "middle"))
        return out


DARK_RED = (0x9E / 255, 0x17 / 255, 0x17 / 255)


class MapNoteFrame(Frame):
    """Округ и район в левом верхнем углу карты: «Троицкий / административный округ» и ниже «район Вороново»
    (владелец 29.09.2026), строки по центру, Montserrat жирный тёмно-красным с белым ореолом — читается и на снимке.
    Каждый блок — список строк; строка-текст переносится по 25 знаков."""

    def __init__(self, rect, lines):
        super().__init__(rect)
        self.lines = lines

    def ops(self, ctx):
        x, y, _, _ = self.rect
        out, yy = [], y + 7.7
        for n, block in enumerate(self.lines):                        # три строки с равным интервалом, как в образце (правило 11)
            for line in (block if isinstance(block, list) else _wrap(block, 25)):
                out.append({**_text(x + 50, yy, 14.3, line, DARK_RED, "sans-bold", "middle"), "halo": 0.6})
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


SW_W = 13.0                                              # ширина знака легенды, мм — одна на всех листах (правило 12)


def _dash_fit(dash, w):
    """Пунктир знака — целыми штрихами: шаг подгоняется так, чтобы знак начинался и кончался штрихом."""
    if not dash:
        return dash
    p = sum(dash)
    n = max(1, round((w - dash[0]) / p))
    k = w / (n * p + dash[0])
    return [d * k for d in dash]


def concept_swatch(x, y, it, lib=None, w=SW_W, h=3.0):
    """Знак легенды 8 × 3 мм: заливка (с штриховкой), контур, линия (со штрихом), тип линии REDLN97, образец текста."""
    from print_io import _mix, hatch_ops, linetype_ops
    k, out = it.get("kind", "fill"), []
    rect = [[(x, y), (x + w, y), (x + w, y + h), (x, y + h)]]
    if k == "line":
        out.append({"op": "path", "closed": False, "fill": None, "stroke": _rgb(it.get("stroke")), "width": float(it.get("width", .5)),
                    "dash": _dash_fit(it.get("dash"), w), "rings": [[(x, y + h / 2), (x + w, y + h / 2)]]})
    elif k == "lt":
        if lib and it.get("name"):
            # как на карте, но не крупнее, чем нужно для двух шаблонов на 8 мм знака — иначе знак сплошной
            n = float((lib.get("linetypes", {}).get(it["name"]) or {}).get("length") or 1)
            out.extend(linetype_ops([(x, y + h / 2), (x + w, y + h / 2)], it["name"], min(0.25, w / (2.05 * n)), _rgb(it.get("stroke"), (1, 0, 0)), 0.3, lib))   # 0,25 — как на карте
        else:
            out.append({"op": "path", "closed": False, "fill": None, "stroke": _rgb(it.get("stroke"), (1, 0, 0)), "width": 0.45,
                        "dash": it.get("dash"), "rings": [[(x, y + h / 2), (x + w, y + h / 2)]]})
        if it.get("ll"):                        # надпись знака над линией — как в образце «ГК Царицыно»
            size_mm = min(1.25, (w + 1) / (len(it["ll"]) * .56))      # не шире знака: длинная надпись — мельче
            out.append({**_text(x + w / 2, y + h / 2 - .45, size_mm / PT, it["ll"], _rgb(it.get("stroke"), (1, 0, 0)), "sans", "middle")})
    elif k == "flood":                                   # подтопление — знаки примера «Хатминки», засечки вниз
        from print_io import flood_ops
        out.extend(flood_ops([(x, y + h / 2 - .4), (x + w, y + h / 2 - .4)], int(it["code"]), _rgb(it.get("stroke"), (0.01, 0.51, 0.25)), side=1))
    elif k == "num":                                    # номер участка в кружке с выноской, как на карте
        c_ = _rgb(it.get("stroke"), (0.12, 0.25, 0.75))
        r_, cx_, cy_ = 1.9, x + w - 2.1, y + h / 2
        out.append({"op": "path", "closed": False, "fill": None, "stroke": c_, "width": 0.4, "dash": None, "rings": [[(x + .8, cy_), (cx_ - r_, cy_)]]})
        out.append({"op": "circle", "x": x + .8, "y": cy_, "r": 0.6, "fill": c_, "stroke": (1, 1, 1), "width": 0.2})
        out.append({"op": "circle", "x": cx_, "y": cy_, "r": r_, "fill": (1, 1, 1), "stroke": c_, "width": 0.4})
        out.append({**_text(cx_, cy_ + 0.95, 7, it.get("sample", "1"), c_, "sans-bold", "middle")})
    elif k == "text":
        out.append({**_text(x + w / 2, y + h, float(it.get("size", 10)), it.get("sample", ""), _rgb(it.get("color"), INK),
                            it.get("family", "sans-bold"), "middle"), **({"underline": True} if it.get("underline") else {})})
    else:
        fill = it.get("fill")
        if fill and not it.get("hatch"):
            out.append({"op": "path", "closed": True, "fill": _mix(fill, it.get("a", 1)), "stroke": None, "width": 0, "dash": None, "rings": rect})
        if it.get("hatch"):
            out.extend(hatch_ops(rect, spacing=float(it.get("spacing", 1.0)), stroke=_rgb(it.get("hatch_color") or fill),
                                 angle=float(it.get("angle", 45)), width=0.15))
        out.append({"op": "path", "closed": True, "fill": None, "stroke": _rgb(it.get("stroke") or fill or "#555555"),
                    "width": float(it.get("width", .2)), "dash": it.get("dash"), "rings": rect})
        if it.get("num"):                                # индекс типа зоны Генплана — в прямоугольнике знака (правило 12)
            out.append({**_text(x + w / 2, y + h / 2 + 0.85, 7, it["num"], INK, "sans-bold", "middle")})
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
            out.append(_text(x, yy, 12.3, "Условные обозначения", INK, "sans-bold"))
            yy += 8
            # знаки легенды на всех листах одного размера 13 × 3 мм: в 8 мм рисунок линии ЗОУИТ не различим (правила 11, 12)
            sw_, ind_ = SW_W, SW_W + 2.5
            for gi, g in enumerate(sh["cLegend"]):
                if g.get("title"):
                    for line in _wrap_mm(g["title"], "sans", S10, w):          # длинный заголовок группы — в две строки
                        out.append({**_text(x, yy, 10, line, INK2, "sans"), "underline": True})
                        yy += 4.4
                    yy += 2.1
                for j, it in enumerate(g.get("items", [])):
                    note = it.get("kind") == "note"                    # пояснение под легендой (приаэродромная территория) — без знака
                    lines = _wrap_mm(it.get("label", ""), "sans", S10, w if note else w - ind_)
                    if yy + (len(lines) - 1) * 4.2 > bottom - 2:
                        # не обрывать молча и не мельчить: лист помечается «не готов» (владелец 01.10.2026, правило 1.43)
                        left = len(g["items"]) - j + sum(len(g2.get("items", [])) for g2 in sh["cLegend"][gi + 1:])
                        _not_ready(sh, f"в колонку не поместились пункты легенды ({left})")
                        full = True
                        break
                    if not note:
                        out.extend(concept_swatch(x, yy - 2.8, it, self.lib, w=sw_))
                    for i, line in enumerate(lines):
                        out.append(_text(x + (0 if note else ind_), yy + i * 4.2, 10, line, INK2, "sans"))
                    yy += 6.5 + (len(lines) - 1) * 4.2
                if full:
                    break
        tbl = sh.get("gpTable")
        if tbl and tbl.get("rows") and full:
            _not_ready(sh, f"не выведена таблица «{tbl.get('title', '')}»")
        if tbl and tbl.get("rows") and not full:
            yy += 5
            for line in _wrap_mm(tbl.get("title", ""), "sans-bold", S12, w):     # длинный заголовок — в несколько строк
                out.append(_text(x, yy, 12.3, line, INK, "sans-bold"))
                yy += 5
            fs = float(tbl.get("fs", 10))                                    # кегль таблицы: у широких — мельче
            T10, lh_ = fs * PT, fs * .42
            widths = [w * c for c in tbl.get("widths", [.2, .2, .28, .32])]
            fit = _col_widths(widths, tbl["cols"], tbl["rows"], T10)
            if fit is None:                                              # слово шире колонки и после переноса по дефису
                _not_ready(sh, f"таблица «{tbl.get('title', '')}» не помещается по ширине")
            widths = fit or widths
            heads = [_wrap_mm(c, "sans-bold", T10, cw - 2, orphan=False, hyph=True) for c, cw in zip(tbl["cols"], widths)]
            hh = max(len(t) for t in heads) * lh_ + 3
            out.append({"op": "path", "closed": True, "fill": (0.9, 0.9, 0.9), "stroke": None, "width": 0, "dash": None,
                        "rings": [[(x, yy), (x + w, yy), (x + w, yy + hh), (x, yy + hh)]]})
            cx = x
            for t, cw in zip(heads, widths):
                for i, line in enumerate(t):
                    out.append(_text(cx + cw / 2, yy + 1.5 + T10 * .8 + i * lh_ + (hh - 3 - len(t) * lh_) / 2, fs, line, INK2, "sans-bold", "middle"))
                cx += cw
            yy += hh + 2
            for r, row in enumerate(tbl["rows"]):
                cells = [_wrap_mm(v, "sans", T10, cw - 2, orphan=False, hyph=True) for v, cw in zip(row, widths)]
                rh = max(len(c) for c in cells) * lh_ + 2
                if yy + rh > bottom:
                    _not_ready(sh, f"не поместились строки таблицы ({len(tbl['rows']) - r})")
                    full = True
                    break
                cx = x
                for c, cw in zip(cells, widths):
                    for i, line in enumerate(c):
                        out.append(_text(cx + cw / 2, yy + T10 * .8 + i * lh_ + (rh - 2 - len(c) * lh_) / 2, fs, line, INK2, "sans", "middle"))
                    cx += cw
                yy += rh
        for blk in sh.get("cLists") or []:
            if full or yy > bottom - 12:
                if blk.get("items"):
                    _not_ready(sh, f"не выведен список «{blk['title']}» ({len(blk['items'])})")
                full = True
                continue
            yy += 7
            for line in _wrap_mm(blk["title"], "sans-bold", S12, w):
                out.append(_text(x, yy, 12.3, line, INK, "sans-bold"))
                yy += 5
            yy += 1.5
            for n, it in enumerate(blk["items"]):
                lines = _wrap_mm(it["text"], "sans", S10, w - 4)
                bh = len(lines) * 4.2 + 2.6
                if yy + bh > bottom:
                    _not_ready(sh, f"не поместились пункты списка «{blk['title']}» ({len(blk['items']) - n})")
                    full = True
                    break
                out.append({"op": "path", "closed": True, "fill": None, "stroke": _rgb(it.get("color"), INK), "width": 0.3, "dash": None,
                            "rings": [[(x, yy), (x + w, yy), (x + w, yy + bh), (x, yy + bh)]]})
                cap_ = S10 * .7                                       # высота прописных: текст по центру рамки (правило 11)
                for i, line in enumerate(lines):
                    out.append(_text(x + 1.8, yy + (bh - (len(lines) - 1) * 4.2 - cap_) / 2 + cap_ + i * 4.2, 10, line, INK2, "sans"))
                yy += bh + 3.2
        cards = sh.get("cCards")
        if cards and cards.get("items") and full:
            _not_ready(sh, f"не выведен блок «{cards['title']}»")
        if cards and cards.get("items") and not full:
            yy += 7
            for line in _wrap_mm(cards["title"], "sans-bold", S12, w):
                out.append(_text(x, yy, 12.3, line, INK, "sans-bold"))
                yy += 5
            yy += 2
            for n, card in enumerate(cards["items"]):
                rows = [(_wrap_mm(k, "sans-bold", S10, w * .3), _wrap_mm(v, "sans", S10, w * .64)) for k, v in card]
                ch = sum(max(len(a), len(b)) * 4.2 + 2.2 for a, b in rows)
                if yy + ch > bottom:
                    _not_ready(sh, f"не поместились участки блока «{cards['title']}» ({len(cards['items']) - n})")
                    break
                if n:
                    out.append({"op": "path", "closed": False, "fill": None, "stroke": (0.75, 0.75, 0.75), "width": 0.2, "dash": None,
                                "rings": [[(x, yy - 2.2), (x + w, yy - 2.2)]]})
                for a, b in rows:
                    rh = max(len(a), len(b)) * 4.2
                    for i, line in enumerate(a):
                        out.append(_text(x + 1, yy + 1.5 + i * 4.2 + (rh - len(a) * 4.2) / 2, 10, line, INK2, "sans-bold"))
                    for i, line in enumerate(b):
                        out.append(_text(x + w * .34, yy + 1.5 + i * 4.2 + (rh - len(b) * 4.2) / 2, 10, line, INK2, "sans"))
                    yy += rh + 2.2
                yy += 3
        return out


class OrthoLegendFrame(Frame):
    """Легенда ортофотоплана «ГК Царицыно»: полупрозрачная белая плашка в правом нижнем углу листа поверх снимка,
    подписи — в одну строку (владелец 30.09.2026)."""

    def __init__(self, sheet, page_w, page_h):
        super().__init__((page_w - 122, page_h - 36, 122, 36))
        self.sheet = sheet

    def ops(self, ctx):
        _, y, w, h = self.rect
        right = self.rect[0] + w
        groups = self.sheet.get("cLegend") or []
        items = [it for g in groups for it in g.get("items", [])]
        # плашка растягивается влево, чтобы каждая подпись шла одной строкой и не заходила под номер листа (x ≥ 399 мм)
        text_w = max([_tw(it.get("label", ""), "sans", 9 * PT) for it in items] + [_tw("Условные обозначения", "sans-bold", 12.2 * PT) - 18])
        x = min(right - 122, 396 - text_w - (3.6 + SW_W + 2.5))
        body = 6.5 + 5.7 + 5.8 * len(items) + 4.5
        top = y + h - body
        out = [{"op": "path", "closed": True, "fill": (1, 1, 1), "alpha": 0.72, "stroke": None, "width": 0, "dash": None,
                "rings": [[(x, top), (right, top), (right, y + h), (x, y + h)]]}]
        yy = top + 6.5
        out.append(_text(x + 3.6, yy, 12.2, "Условные обозначения", INK, "sans-bold"))
        yy += 5.7
        out.append(_text(x + 3.6, yy, 9, "Границы:", INK2, "sans-bold"))
        for it in items:
            yy += 5.8
            out.extend(concept_swatch(x + 3.6, yy - 2.6, it, None, w=SW_W, h=3))   # тот же размер знака, что на других листах
            out.append(_text(x + 3.6 + SW_W + 2.5, yy, 9, it.get("label", ""), INK2, "sans"))
        return out


class ConceptPhotoFrame(Frame):
    """Снимки фотофиксации «ГК Царицыно»: два ряда по два справа от карты и ряд из четырёх внизу, снимок заполняет
    ячейку 94 × 71 мм (лишнее обрезается), номер — на белой плашке в левом верхнем углу."""

    def __init__(self, sheet):
        super().__init__((0, 0, 420, 297))
        self.sheet = sheet

    def ops(self, ctx):
        photos = [(p, raw) for p, raw in ((p, photo_bytes(p)) for p in self.sheet.get("photos", []) if p.get("data")) if raw][:len(PHOTO_SLOTS)]
        if not photos:
            return [_text(313, 160, 11, "Снимки не добавлены: окно «Листы», кнопка с фотоаппаратом у этого листа", (0.45, 0.45, 0.45),
                          "sans", "middle")]
        out = []
        for i, (p, raw) in enumerate(photos):
            sx, sy = PHOTO_SLOTS[i]
            pw, ph = float(p.get("w") or 4), float(p.get("h") or 3)
            k = max(94 / pw, 71 / ph)
            iw, ih = pw * k, ph * k
            out += [{"op": "clip", "rect": (sx, sy, 94, 71)},
                    {"op": "image", "data": raw, "x": sx + (94 - iw) / 2, "y": sy + (71 - ih) / 2, "w": iw, "h": ih},
                    {"op": "unclip"},
                    {"op": "path", "closed": True, "fill": (1, 1, 1), "stroke": None, "width": 0, "dash": None,
                     # плашка номера — вплотную в угол: заходит за край снимка на 0,4 мм, иначе по краю видна полоска снимка
                     "rings": [[(sx - .4, sy - .4), (sx + 8.6, sy - .4), (sx + 8.6, sy + 7.6), (sx - .4, sy + 7.6)]]},
                    _text(sx + 4.3, sy + 6.2, 19, str(i + 1), INK2, "sans-bold", "middle")]
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
            # рамка — шире самой длинной строки на 3 мм с каждой стороны, по тому же центру (правило 11, лист 2)
            need = max(_tw(t, "sans-bold" if i else "sans", 9 * PT) for i, t in enumerate(sh["callout"])) + 6
            if need > box[2]:
                box = (box[0] - (need - box[2]) / 2, box[1], need, box[3])
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
