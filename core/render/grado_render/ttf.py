"""Минимальный разбор TrueType для встраивания в PDF.

Нужны: cmap (формат 4, юникод → глиф), hmtx/hhea (ширины), head (unitsPerEm,
BBox), maxp (число глифов). Файл шрифта встраивается в PDF целиком
(FontFile2), поэтому таблицы глифов не разбираются.
"""

import os
import struct
from pathlib import Path

# Кириллические TTF по ОС: macOS, Linux (DejaVu), Windows (%WINDIR%\Fonts).
# PDF поддерживает те же три семейства, что и холст: ui / serif / mono.
# TTC намеренно не используем: минимальный парсер ниже читает только TTF.
_WINDIR = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
_WIN_FONTS = os.path.join(_WINDIR, "Fonts")
# Шрифты в составе ГРАДО (docs/standards/fonts, свободная лицензия ParaType): одинаковый вид листа на Mac и на
# сервере, где системных шрифтов нет вовсе (AEZA-GRADO, 26.09.2026: печать PDF падала). PT Serif — к заголовкам
# шаблона ППТ КРТ (там Palatino), PT Sans — к подписям (там Arial и Tahoma). Жирные — ui-bold и serif-bold.
BUNDLED = Path(__file__).resolve().parents[3] / "docs" / "standards" / "fonts"
CANDIDATES = {
    # Montserrat (SIL OFL) — заголовки и номера листов альбомов: шаблон ППТ КРТ набран им, концепция — Century Gothic
    "sans": [str(BUNDLED / "Montserrat-Regular.ttf")],
    "sans-bold": [str(BUNDLED / "Montserrat-Bold.ttf")],
    # листы по образцу «ГК Царицыно» набраны Century Gothic: в PPTX идёт он (есть в Office), в PDF — близкий Montserrat
    "gothic": [str(BUNDLED / "Montserrat-Regular.ttf")],
    "gothic-bold": [str(BUNDLED / "Montserrat-Bold.ttf")],
    "ui-bold": [str(BUNDLED / "PTSans-Bold.ttf")],
    "serif-bold": [str(BUNDLED / "PTSerif-Bold.ttf")],
    "ui": [
        str(BUNDLED / "PTSans-Regular.ttf"),
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Verdana.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        os.path.join(_WIN_FONTS, "arial.ttf"),
        os.path.join(_WIN_FONTS, "tahoma.ttf"),
        os.path.join(_WIN_FONTS, "verdana.ttf"),
        os.path.join(_WIN_FONTS, "segoeui.ttf"),
        os.path.join(_WIN_FONTS, "calibri.ttf"),
    ],
    "serif": [
        str(BUNDLED / "PTSerif-Regular.ttf"),
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        os.path.join(_WIN_FONTS, "georgia.ttf"),
        os.path.join(_WIN_FONTS, "times.ttf"),
        os.path.join(_WIN_FONTS, "timesnewroman.ttf"),
    ],
    "mono": [
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/System/Library/Fonts/Supplemental/Andale Mono.ttf",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        os.path.join(_WIN_FONTS, "cour.ttf"),
        os.path.join(_WIN_FONTS, "consola.ttf"),
    ],
}


class FontError(ValueError):
    pass


def find_font(family="ui"):
    """Найти TTF с кириллицей для ui / serif / mono.

    Если специального семейства в ОС нет, возвращает системный шрифт: печать
    остаётся рабочей, а неизвестное значение из старого/внешнего проекта не
    приводит к падению.
    """
    family = family if family in CANDIDATES else "ui"
    for path in CANDIDATES[family]:
        if Path(path).exists():
            return path
    if family.endswith("-bold"):
        return find_font(family[:-5])
    if family != "ui":
        return find_font("ui")
    raise FontError("не найден TTF с кириллицей; укажите путь явно")


class Font:
    def __init__(self, path):
        self.path = str(path)
        self.data = Path(path).read_bytes()
        self.tables = self._table_directory()
        self._parse_head()
        self._parse_hhea_hmtx()
        self._parse_cmap()

    def _table_directory(self):
        (num_tables,) = struct.unpack_from(">H", self.data, 4)
        tables = {}
        for i in range(num_tables):
            tag, _check, off, length = struct.unpack_from(
                ">4sIII", self.data, 12 + 16 * i)
            tables[tag.decode("latin1")] = (off, length)
        return tables

    def _parse_head(self):
        off, _ = self.tables["head"]
        self.units_per_em = struct.unpack_from(">H", self.data, off + 18)[0]
        self.bbox = struct.unpack_from(">4h", self.data, off + 36)

    def _parse_hhea_hmtx(self):
        off, _ = self.tables["hhea"]
        self.ascent, self.descent = struct.unpack_from(">hh", self.data, off + 4)
        (num_h,) = struct.unpack_from(">H", self.data, off + 34)
        (self.num_glyphs,) = struct.unpack_from(
            ">H", self.data, self.tables["maxp"][0] + 4)
        hmtx, _ = self.tables["hmtx"]
        self.advances = []
        for i in range(num_h):
            self.advances.append(struct.unpack_from(">H", self.data, hmtx + 4 * i)[0])

    def _parse_cmap(self):
        off, _ = self.tables["cmap"]
        (num_sub,) = struct.unpack_from(">H", self.data, off + 2)
        best = None
        for i in range(num_sub):
            pid, eid, sub_off = struct.unpack_from(">HHI", self.data, off + 4 + 8 * i)
            if (pid, eid) in ((3, 1), (0, 3), (0, 4)):
                best = off + sub_off
                break
        if best is None:
            raise FontError("нет юникодной cmap (3,1)")
        (fmt,) = struct.unpack_from(">H", self.data, best)
        if fmt != 4:
            raise FontError(f"поддержан только cmap формат 4, найден {fmt}")
        (seg_x2,) = struct.unpack_from(">H", self.data, best + 6)
        n = seg_x2 // 2
        self._end = struct.unpack_from(f">{n}H", self.data, best + 14)
        self._start = struct.unpack_from(f">{n}H", self.data, best + 16 + seg_x2)
        self._delta = struct.unpack_from(f">{n}h", self.data, best + 16 + 2 * seg_x2)
        self._range_off_pos = best + 16 + 3 * seg_x2
        self._range_off = struct.unpack_from(f">{n}H", self.data, self._range_off_pos)

    def gid_for(self, ch):
        c = ord(ch)
        if c > 0xFFFF:
            return 0
        for i, end in enumerate(self._end):
            if c <= end:
                if c < self._start[i]:
                    return 0
                if self._range_off[i] == 0:
                    return (c + self._delta[i]) & 0xFFFF
                pos = (self._range_off_pos + 2 * i + self._range_off[i]
                       + 2 * (c - self._start[i]))
                (gid,) = struct.unpack_from(">H", self.data, pos)
                return (gid + self._delta[i]) & 0xFFFF if gid else 0
        return 0

    def advance(self, gid):
        if gid < len(self.advances):
            return self.advances[gid]
        return self.advances[-1] if self.advances else self.units_per_em // 2

    def width_1000(self, ch):
        """Ширина символа в единицах PDF (1000 на кегль)."""
        return self.advance(self.gid_for(ch)) * 1000.0 / self.units_per_em

    def text_width(self, text, size):
        """Ширина строки в пунктах при кегле size."""
        return sum(self.width_1000(ch) for ch in text) / 1000.0 * size
