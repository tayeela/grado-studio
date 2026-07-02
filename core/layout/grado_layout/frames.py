"""Фреймы альбома: рамка листа, карта, легенда, таблица, текст, штамп.

Карто-фрейм зовёт ту же сцену render, что и экран, — лист не может
разойтись с видом на экране. Штамп — упрощённая основная надпись по
мотивам формы 3 ГОСТ Р 21.101 (185×55, блок подписей + шифр/объект/
стадия/лист/организация).
"""

from .model import Frame

BLACK = (0, 0, 0)
GRAY = (0.3, 0.3, 0.3)


def _rect_ops(x, y, w, h, width=0.5, stroke=BLACK, fill=None):
    return [{"op": "path", "closed": True, "fill": fill, "stroke": stroke,
             "width": width, "dash": None,
             "rings": [[(x, y), (x + w, y), (x + w, y + h), (x, y + h)]]}]


def _text(x, y, size, text, anchor="start", color=BLACK):
    return {"op": "text", "x": x, "y": y, "size": size, "text": str(text),
            "color": color, "anchor": anchor}


def _hline(x0, x1, y, width=0.3):
    return {"op": "path", "closed": False, "fill": None, "stroke": BLACK,
            "width": width, "dash": None, "rings": [[(x0, y), (x1, y)]]}


def _vline(x, y0, y1, width=0.3):
    return {"op": "path", "closed": False, "fill": None, "stroke": BLACK,
            "width": width, "dash": None, "rings": [[(x, y0), (x, y1)]]}


class PageBorder(Frame):
    """Рамка листа по ГОСТ (внешний контур внутренней рамки)."""

    def __init__(self, page):
        super().__init__(page.inner_rect())

    def ops(self, ctx):
        return _rect_ops(*self.rect, width=0.7)


class MapFrame(Frame):
    def __init__(self, rect, scale, center=None, caption=None):
        super().__init__(rect)
        self.scale = scale
        self.center = center
        self.caption = caption

    def ops(self, ctx):
        from grado_render import build_ops
        out = build_ops(ctx["project"], self.rect, self.scale,
                        center=self.center, styles=ctx["styles"])
        out.extend(_rect_ops(*self.rect, width=0.5))
        x, y, w, h = self.rect
        caption = self.caption or f"М 1:{self.scale}"
        out.append(_text(x + w - 2, y + h - 2, 3, caption, anchor="end"))
        return out


class LegendFrame(Frame):
    def __init__(self, rect, title="Условные обозначения"):
        super().__init__(rect)
        self.title = title

    def ops(self, ctx):
        x, y, w, _ = self.rect
        out = _rect_ops(*self.rect, width=0.3)
        out.append(_text(x + 3, y + 6, 3.5, self.title))
        yy = y + 13
        for code, title, st in ctx["styles"].legend_entries(ctx["project"]):
            if st.fill is not None and st.stroke is not None:
                out.extend(_rect_ops(x + 3, yy - 3.5, 10, 5, width=st.width,
                                     stroke=st.stroke, fill=st.fill))
            elif st.stroke is not None:
                out.append({"op": "path", "closed": False, "fill": None,
                            "stroke": st.stroke, "width": st.width,
                            "dash": st.dash,
                            "rings": [[(x + 3, yy - 1), (x + 13, yy - 1)]]})
            out.append(_text(x + 16, yy, 2.8, title))
            yy += 8
        return out


class TableFrame(Frame):
    """Таблица: колонки (заголовок, ширина мм, выравнивание), строки —
    списки значений. Для ТЭП строки приходят живыми из движка."""

    ROW_H = 7

    def __init__(self, rect, columns, rows, title=None):
        super().__init__(rect)
        self.columns = columns
        self.rows = rows
        self.title = title

    def ops(self, ctx):
        x, y, w, _ = self.rect
        out = []
        yy = y
        if self.title:
            out.append(_text(x, yy + 4, 3.8, self.title))
            yy += 8
        widths = [c[1] for c in self.columns]
        total_w = sum(widths)
        n_rows = len(self.rows) + 1
        h = n_rows * self.ROW_H
        out.extend(_rect_ops(x, yy, total_w, h, width=0.5))
        for i in range(1, n_rows):
            out.append(_hline(x, x + total_w, yy + i * self.ROW_H))
        cx = x
        for cw in widths[:-1]:
            cx += cw
            out.append(_vline(cx, yy, yy + h))

        def put_row(row_y, values, size):
            cx = x
            for (header, cw, align), val in zip(self.columns, values):
                if align == "right":
                    out.append(_text(cx + cw - 2, row_y, size, val, anchor="end"))
                elif align == "center":
                    out.append(_text(cx + cw / 2, row_y, size, val, anchor="middle"))
                else:
                    out.append(_text(cx + 2, row_y, size, val))
                cx += cw

        put_row(yy + 4.8, [c[0] for c in self.columns], 3.0)
        for i, row in enumerate(self.rows):
            put_row(yy + (i + 1) * self.ROW_H + 4.8, row, 2.8)
        return out


class TextFrame(Frame):
    def __init__(self, rect, lines, size=3.5, anchor="start"):
        super().__init__(rect)
        self.lines = lines if isinstance(lines, list) else [lines]
        self.size = size
        self.anchor = anchor

    def ops(self, ctx):
        x, y, w, _ = self.rect
        ax = {"start": x, "middle": x + w / 2, "end": x + w}[self.anchor]
        return [_text(ax, y + self.size * (i + 1) * 1.4, self.size, line,
                      anchor=self.anchor)
                for i, line in enumerate(self.lines)]


class StampFrame(Frame):
    """Основная надпись (упрощённая форма 3 ГОСТ Р 21.101), 185×55,
    прижата к правому нижнему углу рамки листа."""

    W, H = 185, 55

    def __init__(self, page):
        ix, iy, iw, ih = page.inner_rect()
        super().__init__((ix + iw - self.W, iy + ih - self.H, self.W, self.H))

    def ops(self, ctx):
        x, y, w, h = self.rect
        meta = ctx["doc"].meta
        out = _rect_ops(x, y, w, h, width=0.7)
        # блок подписей: 6 колонок по [10,10,10,10,15,10], 5 строк по 11
        sign_w = 65
        for i in range(1, 5):
            out.append(_hline(x, x + sign_w, y + i * 11))
        cx = x
        for cw in (10, 10, 10, 10, 15):
            cx += cw
            out.append(_vline(cx, y, y + h))
        for i, head in enumerate(("Изм.", "Кол.", "Лист", "№док", "Подп.", "Дата")):
            colx = x + (0, 10, 20, 30, 40, 55)[i]
            colw = (10, 10, 10, 10, 15, 10)[i]
            out.append(_text(colx + colw / 2, y + 3.6, 2.0, head, anchor="middle"))
        # правая часть: шифр / объект / (стадия, лист, листов | организация)
        rx = x + sign_w
        rw = w - sign_w
        out.append(_vline(rx, y, y + h, width=0.7))
        out.append(_hline(rx, x + w, y + 15, width=0.5))
        out.append(_hline(rx, x + w, y + 40, width=0.5))
        out.append(_text(rx + rw / 2, y + 9.5, 4.0, meta.get("code", ""),
                         anchor="middle"))
        out.append(_text(rx + rw / 2, y + 24, 3.2, meta.get("object", ""),
                         anchor="middle"))
        out.append(_text(rx + rw / 2, y + 33, 3.0, ctx.get("sheet_title", ""),
                         anchor="middle"))
        for i, (head, key) in enumerate((("Стадия", "stage"), ("Лист", "page_no"),
                                         ("Листов", "page_total"))):
            colx = rx + i * 20
            out.append(_vline(colx, y + 40, y + h, width=0.3) if i else
                       _vline(rx, y + 40, y + h, width=0.0))
            out.append(_text(colx + 10, y + 44, 2.2, head, anchor="middle"))
            val = meta.get(key, ctx.get(key, ""))
            out.append(_text(colx + 10, y + 51, 3.2, val, anchor="middle"))
        out.append(_vline(rx + 60, y + 40, y + h, width=0.3))
        out.append(_text(rx + 60 + (rw - 60) / 2, y + 48.5, 3.0,
                         meta.get("org", ""), anchor="middle"))
        return out
