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
        self.font = Font(font_path or find_font())
        self.used_gids = {0}
        self._img_names = {}

    # --- операции → поток содержимого страницы ---------------------------

    def _color(self, c, stroke):
        r, g, b = c
        return f"{_f(r)} {_f(g)} {_f(b)} {'RG' if stroke else 'rg'}\n"

    def _paint(self, fill, stroke):
        if fill is not None and stroke is not None:
            return "B\n"
        if fill is not None:
            return "f\n"
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
        return out + self._paint(o.get("fill"), o.get("stroke"))

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
        size = o["size"] * MM2PT  # кегль задаём в мм высоты
        x = o["x"] * MM2PT
        y = (h - o["y"]) * MM2PT
        if o.get("anchor") == "middle":
            x -= self.font.text_width(o["text"], size) / 2
        elif o.get("anchor") == "end":
            x -= self.font.text_width(o["text"], size)
        gids = [self.font.gid_for(ch) for ch in o["text"]]
        self.used_gids.update(gids)
        hexstr = "".join(f"{g:04X}" for g in gids)
        color = self._color(o.get("color", (0, 0, 0)), stroke=False)
        return (f"{color}BT\n/F1 {_f(size)} Tf\n"
                f"1 0 0 1 {_f(x)} {_f(y)} Tm\n<{hexstr}> Tj\nET\n")

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

        def stream_obj(data, extra=""):
            comp = zlib.compress(data)
            return (f"<< /Length {len(comp)} /Filter /FlateDecode {extra}>>\n"
                    f"stream\n").encode("latin1") + comp + b"\nendstream"

        # растровые вставки: JPEG кладётся в PDF как есть (DCTDecode,
        # без перекодирования); одинаковые данные встраиваются один раз
        self._img_names = {}  # bytes → (имя /ImN, номер объекта)
        next_num = 7
        for _, _, ops in pages:
            for o in ops:
                if o["op"] == "image" and o["data"] not in self._img_names:
                    self._img_names[o["data"]] = (
                        f"Im{len(self._img_names) + 1}", next_num)
                    next_num += 1
        for data, (_, num) in self._img_names.items():
            iw, ih, comps = jpeg_info(data)
            cs = "/DeviceGray" if comps == 1 else "/DeviceRGB"
            objs[num] = ((f"<< /Type /XObject /Subtype /Image "
                          f"/Width {iw} /Height {ih} /ColorSpace {cs} "
                          f"/BitsPerComponent 8 /Filter /DCTDecode "
                          f"/Length {len(data)} >>\nstream\n").encode("latin1")
                         + data + b"\nendstream")

        page_streams = [self._page_stream(w, h, ops) for w, h, ops in pages]

        # 1 — каталог, 2 — дерево страниц, 3 — шрифт Type0;
        # 4..6 — CIDFont, дескриптор, файл шрифта;
        # 7.. — картинки, дальше страницы и потоки
        f = self.font
        scale = 1000.0 / f.units_per_em
        widths = sorted(self.used_gids)
        w_array = " ".join(f"{g} [{_f(f.advance(g) * scale)}]" for g in widths)
        bbox = " ".join(str(int(v * scale)) for v in f.bbox)

        objs[3] = (f"<< /Type /Font /Subtype /Type0 /BaseFont /GradoEmbedded "
                   f"/Encoding /Identity-H /DescendantFonts [4 0 R] >>").encode()
        objs[4] = (f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /GradoEmbedded "
                   f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) "
                   f"/Supplement 0 >> /FontDescriptor 5 0 R /DW 500 "
                   f"/W [ {w_array} ] /CIDToGIDMap /Identity >>").encode()
        objs[5] = (f"<< /Type /FontDescriptor /FontName /GradoEmbedded /Flags 32 "
                   f"/FontBBox [ {bbox} ] /ItalicAngle 0 "
                   f"/Ascent {int(f.ascent * scale)} /Descent {int(f.descent * scale)} "
                   f"/CapHeight {int(f.ascent * scale)} /StemV 80 "
                   f"/FontFile2 6 0 R >>").encode()
        objs[6] = stream_obj(f.data, extra=f"/Length1 {len(f.data)} ")

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
            objs[pnum] = (f"<< /Type /Page /Parent 2 0 R "
                          f"/MediaBox [0 0 {_f(w * MM2PT)} {_f(h * MM2PT)}] "
                          f"/Resources << /Font << /F1 3 0 R >> {xobj}>> "
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
