"""Печатный бэкенд PDF на ReportLab (BSD): векторный вывод того же списка операций, что у экранного бэкенда (scene.py).

Кириллица — TrueType из docs/standards/fonts, ReportLab встраивает только использованные глифы (подмножество) и пишет
/ToUnicode: текст листа ищется и копируется. JPEG кладётся как есть (DCTDecode). Ширины строк считает ttf.Font —
те же, по которым print_io раскладывает подписи. Вызывают print_io (альбом), grado_layout.compose, layout_io;
тесты — core/render/tests/test_render.py.
"""

import io
import math

from reportlab import rl_config
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import FILL_EVEN_ODD, FILL_NON_ZERO, Canvas

from .ttf import Font, find_font

MM2PT = 72.0 / 25.4
FAMILIES = ("ui", "serif", "mono", "ui-bold", "serif-bold", "sans", "sans-bold")


def jpeg_info(data):
    """(width, height, компоненты) из SOF-маркера JPEG."""
    try:
        return _jpeg_info(data)
    except (IndexError, TypeError) as e:
        raise ValueError(f"повреждённый JPEG: {type(e).__name__}") from None


def _jpeg_info(data):
    if data[:2] != b"\xff\xd8":
        raise ValueError("не JPEG (нет SOI)")
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            h = int.from_bytes(data[i + 5:i + 7], "big")
            w = int.from_bytes(data[i + 7:i + 9], "big")
            return w, h, data[i + 9]
        if marker == 0xD8 or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            i += 2
            continue
        i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    raise ValueError("SOF-маркер не найден")


def _rl_font(path):
    """Имя шрифта ReportLab для файла TTF (регистрируется один раз на процесс)."""
    name = "Grado-" + "".join(ch if ch.isalnum() else "-" for ch in path.rsplit("/", 1)[-1].rsplit(".", 1)[0])
    if name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(name, path))
    return name


class PdfBackend:
    def __init__(self, font_path=None):
        self._font_paths = {"ui": font_path} if font_path else {}
        self._fonts = {"ui": Font(font_path or find_font("ui"))}
        self.font = self._fonts["ui"]                       # основной шрифт — ui (прежний публичный атрибут)

    def _font_for(self, family):
        family = family if family in FAMILIES else "ui"
        if family not in self._fonts:
            self._fonts[family] = Font(self._font_paths.get(family) or find_font(family))
        f = self._fonts[family]
        return _rl_font(f.path), f

    # --- операции → холст ReportLab ---------------------------------------

    @staticmethod
    def _pen(c, o, h, reset_dash=True):
        """Цвета, толщина, излом и штрих пути; путь в пунктах страницы (y вверх)."""
        if o.get("fill") is not None:
            c.setFillColorRGB(*o["fill"])
        if o.get("stroke") is not None:
            c.setStrokeColorRGB(*o["stroke"])
            c.setLineWidth(o.get("width", 0.3) * MM2PT)
            c.setLineJoin(1 if o.get("join") == "round" else 0)   # скруглённые изломы — без острых «шипов» на контурах карты
            dash = o.get("dash")
            if dash:
                c.setDash([d * MM2PT for d in dash], 0)
            elif reset_dash:
                c.setDash([], 0)

    @staticmethod
    def _rings(c, rings, h, closed=True):
        p = c.beginPath()
        for ring in rings:
            if not ring:
                continue
            p.moveTo(ring[0][0] * MM2PT, (h - ring[0][1]) * MM2PT)
            for x, y in ring[1:]:
                p.lineTo(x * MM2PT, (h - y) * MM2PT)
            if closed:
                p.close()
        return p

    def _path(self, c, o, h):
        """Путь с ДЫРАМИ (несколько колец) закрашивается по чётности: выколотая часть остаётся пустой при любом
        направлении обхода — в данных портала намотка не гарантирована (холст рисует так же, fill("evenodd"))."""
        self._pen(c, o, h)
        fill, stroke = o.get("fill") is not None, o.get("stroke") is not None
        evenodd = o.get("evenodd") or len(o["rings"]) > 1
        c.drawPath(self._rings(c, o["rings"], h, o.get("closed")), fill=1 if fill else 0,
                   stroke=1 if stroke or not fill else 0, fillMode=FILL_EVEN_ODD if evenodd else FILL_NON_ZERO)

    def _circle(self, c, o, h):
        fill, stroke = o.get("fill") is not None, o.get("stroke") is not None
        self._pen(c, {k: o.get(k) for k in ("fill", "stroke", "width")}, h)
        c.circle(o["x"] * MM2PT, (h - o["y"]) * MM2PT, o["r"] * MM2PT,
                 stroke=1 if stroke or not fill else 0, fill=1 if fill else 0)

    def _text(self, c, o, h):
        name, font = self._font_for(o.get("font_family", "ui"))
        size = o["size"] * MM2PT                            # кегль задаём в мм высоты
        x, y = o["x"] * MM2PT, (h - o["y"]) * MM2PT
        w = font.text_width(o["text"], size)
        off = -w / 2 if o.get("anchor") == "middle" else (-w if o.get("anchor") == "end" else 0.0)
        angle = o.get("angle", 0.0)
        # подпись вдоль линии: сцена y-вниз → страница y-вверх, угол инвертируется; центрирование — вдоль оси текста
        ca, sa = (math.cos(-angle), math.sin(-angle)) if angle else (1.0, 0.0)
        tm = (ca, sa, -sa, ca, x + off * ca, y + off * sa)

        def run(mode):
            t = c.beginText()
            t.setFont(name, size)
            t.setTextTransform(*tm)
            t.setTextRenderMode(mode)
            t.textOut(o["text"])
            c.drawText(t)
        if o.get("halo"):
            # ореол подписи (как «свечение» в PowerPoint): сначала обводка букв цветом фона, поверх — сами буквы;
            # обводка сплошная — штрих предыдущей линии (граница территории) сброшен
            c.saveState()
            c.setStrokeColorRGB(*o.get("halo_color", (1, 1, 1)))
            c.setLineWidth(o["halo"] * MM2PT * 2)
            c.setLineJoin(1)
            c.setDash([], 0)
            run(1)
            c.restoreState()
        c.setFillColorRGB(*o.get("color", (0, 0, 0)))
        run(0)
        if o.get("underline") and not angle:
            # подчёркнутая строка (заголовки групп легенды «ГК Царицыно»): черта по ширине текста этим же шрифтом
            c.saveState()
            c.setStrokeColorRGB(*o.get("color", (0, 0, 0)))
            c.setLineWidth(size * 0.05)
            c.setDash([], 0)
            uy = y - size * 0.14
            c.line(x + off, uy, x + off + w, uy)
            c.restoreState()

    def _image(self, c, o, h, cache):
        img = cache.get(o["data"])
        if img is None:
            jpeg_info(o["data"])                            # не JPEG — ValueError, как прежде
            img = cache[o["data"]] = ImageReader(io.BytesIO(o["data"]))
        c.saveState()
        if "quad" in o:
            # параллелограмм по трём углам (tl, tr, bl в мм листа): единичный квадрат картинки → аффинная матрица
            (tlx, tly), (trx, tr_y), (blx, bly) = o["quad"]
            c.transform((trx - tlx) * MM2PT, (tly - tr_y) * MM2PT, (tlx - blx) * MM2PT, (bly - tly) * MM2PT,
                        blx * MM2PT, (h - bly) * MM2PT)
        else:
            # осевой случай: x,y — верхний левый угол в мм; PDF рисует от нижнего
            c.transform(o["w"] * MM2PT, 0, 0, o["h"] * MM2PT, o["x"] * MM2PT, (h - o["y"] - o["h"]) * MM2PT)
        c.drawImage(img, 0, 0, 1, 1)
        c.restoreState()

    def _page(self, c, w, h, ops, images):
        depth = 0
        for o in ops:
            op = o["op"]
            if op == "image":
                self._image(c, o, h, images)
            elif op == "clip" and o.get("rings"):
                # обрезка по контуру (округ на схеме шаблона ППТ КРТ): кольца, правило чётности — дыры остаются вне
                c.saveState()
                c.clipPath(self._rings(c, o["rings"], h), stroke=0, fill=0, fillMode=FILL_EVEN_ODD)
                depth += 1
            elif op == "clip":
                x, y, cw, ch = o["rect"]
                c.saveState()
                p = c.beginPath()
                p.rect(x * MM2PT, (h - y - ch) * MM2PT, cw * MM2PT, ch * MM2PT)
                c.clipPath(p, stroke=0, fill=0)
                depth += 1
            elif op == "unclip":
                if depth:
                    c.restoreState()
                    depth -= 1
            elif op == "path":
                a = o.get("alpha")
                if a is not None and a < 1:                 # полупрозрачная заливка (подложка легенды на снимке)
                    c.saveState()
                    c.setFillAlpha(round(float(a), 3))
                    self._path(c, o, h)
                    c.restoreState()
                else:
                    self._path(c, o, h)
            elif op == "circle":
                self._circle(c, o, h)
            elif op == "text":
                self._text(c, o, h)
        for _ in range(depth):
            c.restoreState()

    def render(self, pages):
        """pages: [(w_mm, h_mm, ops)] → bytes PDF."""
        rl_config.useA85 = 0                                # потоки — только Flate, без ASCII85 (меньше и читается тестами)
        buf = io.BytesIO()
        c = Canvas(buf, pageCompression=1, invariant=1, initialFontName=self._font_for("ui")[0])  # без лишней Helvetica
        c.setCreator("ГРАДО 2")
        c.setAuthor("")
        c.setTitle("")
        images = {}                                         # одинаковые JPEG встраиваются один раз
        for w, h, ops in pages:
            c.setPageSize((w * MM2PT, h * MM2PT))
            self._page(c, w, h, ops, images)
            c.showPage()
        c.save()
        return buf.getvalue()
