"""Разбирает PDF печати для тестов: объекты, распакованные потоки страниц и текст через /ToUnicode.

ReportLab пишет потоки сжатыми, а шрифты — подмножествами с однобайтовыми кодами, поэтому тесты читают PDF здесь,
а не ищут байты. Зовут test_render.py, test_pptx.py и apps/grado2/tests/test_print.py.
"""
import re
import zlib


def objects(pdf):
    """{номер: (словарь объекта, распакованный поток или None)}."""
    out = {}
    for m in re.finditer(rb"(\d+) 0 obj\s*(<<.*?>>)\s*(stream\r?\n|endobj)", pdf, re.S):
        head, data = m.group(2), None
        if m.group(3) != b"endobj":
            n = int(re.search(rb"/Length (\d+)", head).group(1))
            data = pdf[m.end():m.end() + n]
            if b"FlateDecode" in head:
                data = zlib.decompress(data)
        out[int(m.group(1))] = (head, data)
    return out


def page_streams(pdf):
    """Потоки содержимого страниц по порядку страниц."""
    objs = objects(pdf)
    pages = [h for h, _ in objs.values() if re.search(rb"/Type /Page\b", h)]
    return [objs[int(re.search(rb"/Contents (\d+) 0 R", h).group(1))][1] for h in pages]


def _unescape(s):
    out, i = bytearray(), 0
    while i < len(s):
        c = s[i]
        if c == 0x5C:                                  # обратная косая
            nxt = s[i + 1:i + 2]
            m = re.match(rb"[0-7]{1,3}", s[i + 1:i + 4])
            if m:
                out.append(int(m.group(0), 8)); i += 1 + len(m.group(0)); continue
            out += {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}.get(nxt, nxt); i += 2; continue
        out.append(c); i += 1
    return bytes(out)


def texts(pdf):
    """Строки, нарисованные операторами Tj на всех страницах, в Юникоде (через /ToUnicode шрифтов)."""
    objs = objects(pdf)
    cmaps = {}
    for head, _ in objs.values():
        name, tu = re.search(rb"/Name /(\S+)", head), re.search(rb"/ToUnicode (\d+) 0 R", head)
        if name and tu:
            cm = objs[int(tu.group(1))][1].decode("latin1")
            cmaps[name.group(1)] = {int(c, 16): "".join(chr(int(u[k:k + 4], 16)) for k in range(0, len(u), 4))
                                    for c, u in re.findall(r"<([0-9A-Fa-f]+)> <([0-9A-Fa-f]+)>", cm)}
    out = []
    for page in page_streams(pdf):
        font = None
        for m in re.finditer(rb"/(\S+) [\d.]+ Tf|\(((?:\\.|[^\\)])*)\) Tj", page, re.S):
            if m.group(1):
                font = cmaps.get(m.group(1), {})
            else:
                out.append("".join(font.get(b, "?") for b in _unescape(m.group(2))))
    return out
