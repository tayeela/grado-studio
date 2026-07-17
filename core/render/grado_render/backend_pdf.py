"""Печатный бэкенд: собственный PDF-писатель.

Векторный вывод, кириллица через встраиваемый TrueType (Type0/CIDFontType2,
Identity-H), потоки сжаты Flate. Исполняет тот же список операций, что и
экранный бэкенд, — см. scene.py.
"""

import zlib

from .ttf import Font, find_font

MM2PT = 72.0 / 25.4
KAPPA = 0.5522847498


def jpeg_info(data):
    """(width, height, компоненты) из SOF-маркера JPEG."""
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


def _f(x):
    return f"{x:.3f}".rstrip("0").rstrip(".")


class PdfBackend:
    def __init__(self, font_path=None):
        self._font_paths = {"ui": font_path} if font_path else {}
        self._fonts = {"ui": Font(font_path or find_font("ui"))}
        self._font_order = ["ui"]
        # Совместимость с прежним публичным атрибутом: основной шрифт — ui.
        self.font = self._fonts["ui"]
        self._used_gids = {"ui": {0}}
        self.used_gids = self._used_gids["ui"]
        self._used_families = set()
        self._img_names = {}

    def _font_for(self, family):
        family = family if family in ("ui", "serif", "mono") else "ui"
        if family not in self._fonts:
            self._fonts[family] = Font(
                self._font_paths.get(family) or find_font(family))
            self._font_order.append(family)
        self._used_gids.setdefault(family, {0})
        self._used_families.add(family)
        return family, self._fonts[family]

    def _font_name(self, family):
        return f"F{self._font_order.index(family) + 1}"

    # --- операции → поток содержимого страницы ---------------------------

    def _color(self, c, stroke):
        r, g, b = c
        return f"{_f(r)} {_f(g)} {_f(b)} {'RG' if stroke else 'rg'}\n"

    def _paint(self, fill, stroke, evenodd=False):
        """Операторы закраски. evenodd → f*/B*: путь с ДЫРАМИ (несколько колец)
        закрашивается по чётности пересечений, и выколотая часть остаётся
        пустой при ЛЮБОМ направлении обхода кольца. На nonzero (f/B) дыра
        появлялась бы только при противоположной намотке, а в данных портала
        она не гарантирована — холст по этой же причине рисует fill("evenodd").
        """
        star = "*" if evenodd else ""
        if fill is not None and stroke is not None:
            return f"B{star}\n"
        if fill is not None:
            return f"f{star}\n"
        return "S\n"

    def _path_ops(self, o, h):
        out = ""
        if o.get("fill") is not None:
            out += self._color(o["fill"], stroke=False)
        if o.get("stroke") is not None:
            out += self._color(o["stroke"], stroke=True)
            out += f"{_f(o.get('width', 0.3) * MM2PT)} w\n"
            dash = o.get("dash")
            out += (f"[{' '.join(_f(d * MM2PT) for d in dash)}] 0 d\n"
                    if dash else "[] 0 d\n")
        for ring in o["rings"]:
            pts = [(x * MM2PT, (h - y) * MM2PT) for x, y in ring]
            out += f"{_f(pts[0][0])} {_f(pts[0][1])} m\n"
            for x, y in pts[1:]:
                out += f"{_f(x)} {_f(y)} l\n"
            if o.get("closed"):
                out += "h\n"
        return out + self._paint(o.get("fill"), o.get("stroke"),
                                 o.get("evenodd") or len(o["rings"]) > 1)

    def _circle_ops(self, o, h):
        cx, cy = o["x"] * MM2PT, (h - o["y"]) * MM2PT
        r = o["r"] * MM2PT
        k = KAPPA * r
        out = ""
        if o.get("fill") is not None:
            out += self._color(o["fill"], stroke=False)
        if o.get("stroke") is not None:
            out += self._color(o["stroke"], stroke=True)
            out += f"{_f(o.get('width', 0.3) * MM2PT)} w\n[] 0 d\n"
        out += f"{_f(cx + r)} {_f(cy)} m\n"
        for dx1, dy1, dx2, dy2, dx3, dy3 in [
                (r, k, k, r, 0, r), (-k, r, -r, k, -r, 0),
                (-r, -k, -k, -r, 0, -r), (k, -r, r, -k, r, 0)]:
            out += (f"{_f(cx + dx1)} {_f(cy + dy1)} "
                    f"{_f(cx + dx2)} {_f(cy + dy2)} "
                    f"{_f(cx + dx3)} {_f(cy + dy3)} c\n")
        return out + self._paint(o.get("fill"), o.get("stroke"))

    def _text_ops(self, o, h):
        import math
        family, font = self._font_for(o.get("font_family", "ui"))
        size = o["size"] * MM2PT  # кегль задаём в мм высоты
        x = o["x"] * MM2PT
        y = (h - o["y"]) * MM2PT
        w = font.text_width(o["text"], size)
        off = -w / 2 if o.get("anchor") == "middle" else (
              -w if o.get("anchor") == "end" else 0.0)
        gids = [font.gid_for(ch) for ch in o["text"]]
        self._used_gids[family].update(gids)
        hexstr = "".join(f"{g:04X}" for g in gids)
        color = self._color(o.get("color", (0, 0, 0)), stroke=False)
        angle = o.get("angle", 0.0)
        if angle:
            # подпись вдоль линии: сцена y-вниз → страница y-вверх, угол
            # инвертируется; центрирование — вдоль повёрнутой оси текста
            ca, sa = math.cos(-angle), math.sin(-angle)
            tm = (f"{_f(ca)} {_f(sa)} {_f(-sa)} {_f(ca)} "
                  f"{_f(x + off * ca)} {_f(y + off * sa)}")
        else:
            tm = f"1 0 0 1 {_f(x + off)} {_f(y)}"  # горизонталь — прежний путь
        return (f"{color}BT\n/{self._font_name(family)} {_f(size)} Tf\n"
                f"{tm} Tm\n<{hexstr}> Tj\nET\n")

    def _page_stream(self, w, h, ops):
        out = ""
        clip_depth = 0
        for o in ops:
            if o["op"] == "image":
                name = self._img_names[o["data"]][0]
                if "quad" in o:
                    # параллелограмм по трём углам (tl, tr, bl в мм листа):
                    # единичный квадрат картинки → аффинная матрица cm
                    (tlx, tly), (trx, tr_y), (blx, bly) = o["quad"]
                    m = ((trx - tlx) * MM2PT, (tly - tr_y) * MM2PT,
                         (tlx - blx) * MM2PT, (bly - tly) * MM2PT,
                         blx * MM2PT, (h - bly) * MM2PT)
                else:
                    # осевой случай: x,y — верхний левый угол в мм;
                    # PDF рисует от нижнего
                    m = (o["w"] * MM2PT, 0, 0, o["h"] * MM2PT,
                         o["x"] * MM2PT, (h - o["y"] - o["h"]) * MM2PT)
                out += (f"q\n{' '.join(_f(v) for v in m)} cm\n"
                        f"/{name} Do\nQ\n")
            elif o["op"] == "clip":
                x, y, cw, ch = o["rect"]
                out += (f"q\n{_f(x * MM2PT)} {_f((h - y - ch) * MM2PT)} "
                        f"{_f(cw * MM2PT)} {_f(ch * MM2PT)} re W n\n")
                clip_depth += 1
            elif o["op"] == "unclip":
                out += "Q\n"
                clip_depth -= 1
            elif o["op"] == "path":
                out += self._path_ops(o, h)
            elif o["op"] == "circle":
                out += self._circle_ops(o, h)
            elif o["op"] == "text":
                out += self._text_ops(o, h)
        out += "Q\n" * clip_depth
        return out.encode("latin1")

    # --- сборка PDF -------------------------------------------------------

    def render(self, pages):
        """pages: [(w_mm, h_mm, ops)] → bytes PDF."""
        objs = {}  # num -> bytes тела объекта
        self._used_gids = {family: {0} for family in self._fonts}
        self.used_gids = self._used_gids["ui"]
        self._used_families = set()

        def stream_obj(data, extra=""):
            comp = zlib.compress(data)
            return (f"<< /Length {len(comp)} /Filter /FlateDecode {extra}>>\n"
                    f"stream\n").encode("latin1") + comp + b"\nendstream"

        # растровые вставки: JPEG кладётся в PDF как есть (DCTDecode,
        # без перекодирования); одинаковые данные встраиваются один раз
        self._img_names = {}  # bytes → (имя /ImN, номер объекта)
        for _, _, ops in pages:
            for o in ops:
                if o["op"] == "image" and o["data"] not in self._img_names:
                    self._img_names[o["data"]] = (
                        f"Im{len(self._img_names) + 1}", None)

        # Сначала строим потоки: именно здесь обнаруживаются реально
        # использованные семейства и глифы.
        page_streams = [self._page_stream(w, h, ops) for w, h, ops in pages]

        # 1 — каталог, 2 — дерево страниц; по четыре объекта на каждый TTF:
        # Type0, CIDFont, дескриптор, файл шрифта. В PDF попадают только
        # семейства, которые действительно используются на листах.
        font_refs = {}
        next_num = 3
        for family in (f for f in self._font_order if f in self._used_families):
            f = self._fonts[family]
            type0, cid, descriptor, font_file = range(next_num, next_num + 4)
            next_num += 4
            font_refs[family] = type0
            scale = 1000.0 / f.units_per_em
            widths = sorted(self._used_gids[family])
            w_array = " ".join(
                f"{g} [{_f(f.advance(g) * scale)}]" for g in widths)
            bbox = " ".join(str(int(v * scale)) for v in f.bbox)
            base = f"GradoEmbedded{self._font_name(family)}"
            flags = 33 if family == "mono" else (34 if family == "serif" else 32)
            objs[type0] = (
                f"<< /Type /Font /Subtype /Type0 /BaseFont /{base} "
                f"/Encoding /Identity-H /DescendantFonts [{cid} 0 R] >>"
            ).encode()
            objs[cid] = (
                f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /{base} "
                f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) "
                f"/Supplement 0 >> /FontDescriptor {descriptor} 0 R /DW 500 "
                f"/W [ {w_array} ] /CIDToGIDMap /Identity >>"
            ).encode()
            objs[descriptor] = (
                f"<< /Type /FontDescriptor /FontName /{base} /Flags {flags} "
                f"/FontBBox [ {bbox} ] /ItalicAngle 0 "
                f"/Ascent {int(f.ascent * scale)} /Descent {int(f.descent * scale)} "
                f"/CapHeight {int(f.ascent * scale)} /StemV 80 "
                f"/FontFile2 {font_file} 0 R >>"
            ).encode()
            objs[font_file] = stream_obj(
                f.data, extra=f"/Length1 {len(f.data)} ")

        # Растровые вставки идут после динамического набора шрифтов.
        for data, (name, _) in list(self._img_names.items()):
            num = next_num
            next_num += 1
            self._img_names[data] = (name, num)
            iw, ih, comps = jpeg_info(data)
            cs = "/DeviceGray" if comps == 1 else "/DeviceRGB"
            objs[num] = ((f"<< /Type /XObject /Subtype /Image "
                          f"/Width {iw} /Height {ih} /ColorSpace {cs} "
                          f"/BitsPerComponent 8 /Filter /DCTDecode "
                          f"/Length {len(data)} >>\nstream\n").encode("latin1")
                         + data + b"\nendstream")

        page_nums, kids = [], []
        for (w, h, ops), stream in zip(pages, page_streams):
            pnum, snum = next_num, next_num + 1
            next_num += 2
            used = sorted({self._img_names[o["data"]]
                           for o in ops if o["op"] == "image"},
                          key=lambda e: e[1])
            xobj = ("/XObject << " + " ".join(f"/{nm} {num} 0 R"
                                              for nm, num in used) + " >> "
                    if used else "")
            fonts = " ".join(
                f"/{self._font_name(family)} {font_refs[family]} 0 R"
                for family in self._font_order if family in font_refs)
            objs[pnum] = (f"<< /Type /Page /Parent 2 0 R "
                          f"/MediaBox [0 0 {_f(w * MM2PT)} {_f(h * MM2PT)}] "
                          f"/Resources << /Font << {fonts} >> {xobj}>> "
                          f"/Contents {snum} 0 R >>").encode()
            objs[snum] = stream_obj(stream)
            page_nums.append(pnum)
            kids.append(f"{pnum} 0 R")
        objs[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
        objs[2] = (f"<< /Type /Pages /Kids [ {' '.join(kids)} ] "
                   f"/Count {len(kids)} >>").encode()

        out = bytearray(b"%PDF-1.6\n%\xd0\x93\xd0\xa0\n")
        offsets = {}
        for num in sorted(objs):
            offsets[num] = len(out)
            out += f"{num} 0 obj\n".encode() + objs[num] + b"\nendobj\n"
        xref_at = len(out)
        n = max(objs) + 1
        out += f"xref\n0 {n}\n".encode()
        out += b"0000000000 65535 f \n"
        for num in range(1, n):
            out += f"{offsets[num]:010d} 00000 n \n".encode()
        out += (f"trailer\n<< /Size {n} /Root 1 0 R >>\n"
                f"startxref\n{xref_at}\n%%EOF\n").encode()
        return bytes(out)
