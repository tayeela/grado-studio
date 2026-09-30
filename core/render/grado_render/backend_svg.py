"""Экранный бэкенд: SVG (в C++ ядре его место занимает GPU-рендер).

Исполняет тот же список операций, что и PDF-бэкенд, — один стилевой
байткод, два вывода.
"""

import base64
import math

_CLIP_COUNTER = [0]
_FONT_FAMILIES = {
    "ui": "Arial, sans-serif",
    "serif": "Georgia, 'Times New Roman', serif",
    "ui-bold": "'PT Sans', Arial, sans-serif",
    "sans": "Montserrat, 'Century Gothic', Arial, sans-serif",
    "sans-bold": "Montserrat, 'Century Gothic', Arial, sans-serif",
    "serif-bold": "'PT Serif', Georgia, serif",
    "mono": "'Courier New', monospace",
}


def _num(v):
    """Числовой атрибут разметки: число остаётся как есть (вывод прежний
    байт-в-байт), всё остальное приводится float() — строка с разметкой
    не пройдёт (ValueError/TypeError), а не попадёт в атрибут."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    return float(v)


def _css(c):
    if c is None:
        return "none"
    return f"rgb({int(c[0] * 255)},{int(c[1] * 255)},{int(c[2] * 255)})"


def _pts(ring):
    return " ".join(f"{x:.3f},{y:.3f}" for x, y in ring)


def render_svg(w, h, ops, font_family="Arial, sans-serif"):
    w, h = _num(w), _num(h)
    font_family = _esc(str(font_family))
    body = []
    defs = []
    open_groups = 0
    for o in ops:
        if o["op"] == "clip":
            _CLIP_COUNTER[0] += 1
            cid = f"clip{_CLIP_COUNTER[0]}"
            if o.get("rings"):
                d = " ".join("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in r) + " Z" for r in o["rings"])
                defs.append(f'<clipPath id="{cid}"><path d="{d}" clip-rule="evenodd"/></clipPath>')
            else:
                x, y, cw, ch = (_num(v) for v in o["rect"])
                defs.append(f'<clipPath id="{cid}">'
                            f'<rect x="{x}" y="{y}" width="{cw}" height="{ch}"/>'
                            f"</clipPath>")
            body.append(f'<g clip-path="url(#{cid})">')
            open_groups += 1
        elif o["op"] == "unclip":
            body.append("</g>")
            open_groups -= 1
        elif o["op"] == "image":
            b64 = base64.b64encode(o["data"]).decode("ascii")
            href = f'href="data:image/jpeg;base64,{b64}"'
            if "quad" in o:
                # параллелограмм: единичный квадрат → matrix(a b c d e f)
                (tlx, tly), (trx, tr_y), (blx, bly) = o["quad"]
                m = (trx - tlx, tr_y - tly, blx - tlx, bly - tly, tlx, tly)
                body.append(
                    f'<image x="0" y="0" width="1" height="1" '
                    f'preserveAspectRatio="none" '
                    f'transform="matrix({" ".join(f"{v:.5f}" for v in m)})" '
                    f'{href}/>')
            else:
                body.append(
                    f'<image x="{o["x"]:.3f}" y="{o["y"]:.3f}" '
                    f'width="{o["w"]:.3f}" height="{o["h"]:.3f}" '
                    f'preserveAspectRatio="none" {href}/>')
        elif o["op"] == "path":
            dash = (f' stroke-dasharray="{",".join(str(_num(d)) for d in o["dash"])}"'
                    if o.get("dash") else "")
            join = ' stroke-linejoin="round"' if o.get("join") == "round" else ""
            d = ""
            for ring in o["rings"]:
                d += f"M {_pts(ring[:1])} L {_pts(ring[1:])} "
                if o.get("closed"):
                    d += "Z "
            # путь с ДЫРАМИ (несколько колец) — заливка по чётности, иначе
            # выколотая часть закрасилась бы при «неправильной» намотке кольца
            # (в данных портала направление обхода не гарантировано)
            eo = (' fill-rule="evenodd"'
                  if (o.get("evenodd") or len(o["rings"]) > 1) else "")
            fo = f' fill-opacity="{_num(o["alpha"])}"' if o.get("alpha") is not None and _num(o["alpha"]) < 1 else ""
            body.append(
                f'<path d="{d.strip()}" fill="{_css(o.get("fill"))}"{eo}{fo} '
                f'stroke="{_css(o.get("stroke"))}" '
                f'stroke-width="{_num(o.get("width", 0.3))}"{dash}{join}/>')
        elif o["op"] == "circle":
            body.append(
                f'<circle cx="{o["x"]:.3f}" cy="{o["y"]:.3f}" r="{_num(o["r"])}" '
                f'fill="{_css(o.get("fill"))}" stroke="{_css(o.get("stroke"))}" '
                f'stroke-width="{_num(o.get("width", 0.3))}"/>')
        elif o["op"] == "text":
            anchor = {"middle": "middle", "end": "end"}.get(o.get("anchor"), "start")
            ang = o.get("angle", 0.0)
            # сцена и SVG обе y-вниз → угол в градусах напрямую (по часовой)
            tf = (f' transform="rotate({math.degrees(ang):.2f} '
                  f'{o["x"]:.3f} {o["y"]:.3f})"') if ang else ""
            family = o.get("font_family")
            weight = ' font-weight="bold"' if str(family or "").endswith("-bold") else ""
            halo = (f' stroke="{_css(o.get("halo_color", (1, 1, 1)))}" stroke-width="{_num(o["halo"]) * 2:.3f}" '
                    f'paint-order="stroke" stroke-linejoin="round"') if o.get("halo") else ""
            under = ' text-decoration="underline"' if o.get("underline") else ""
            op_font = (font_family if family in (None, "ui") else
                       _FONT_FAMILIES.get(family, font_family))
            body.append(
                f'<text x="{o["x"]:.3f}" y="{o["y"]:.3f}"{tf} '
                f'font-size="{_num(o["size"])}" font-family="{op_font}"'
                f'{weight}{halo}{under} '
                f'text-anchor="{anchor}" fill="{_css(o.get("color", (0, 0, 0)))}">'
                f'{_esc(o["text"])}</text>')
    body.extend("</g>" * open_groups)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" height="{h}mm" '
            f'viewBox="0 0 {w} {h}">\n<defs>{"".join(defs)}</defs>\n'
            + "\n".join(body) + "\n</svg>\n")


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#x27;"))
