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
    "mono": "'Courier New', monospace",
}


def _css(c):
    if c is None:
        return "none"
    return f"rgb({int(c[0] * 255)},{int(c[1] * 255)},{int(c[2] * 255)})"


def _pts(ring):
    return " ".join(f"{x:.3f},{y:.3f}" for x, y in ring)


def render_svg(w, h, ops, font_family="Arial, sans-serif"):
    body = []
    defs = []
    open_groups = 0
    for o in ops:
        if o["op"] == "clip":
            _CLIP_COUNTER[0] += 1
            cid = f"clip{_CLIP_COUNTER[0]}"
            x, y, cw, ch = o["rect"]
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
            dash = (f' stroke-dasharray="{",".join(str(d) for d in o["dash"])}"'
                    if o.get("dash") else "")
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
            body.append(
                f'<path d="{d.strip()}" fill="{_css(o.get("fill"))}"{eo} '
                f'stroke="{_css(o.get("stroke"))}" '
                f'stroke-width="{o.get("width", 0.3)}"{dash}/>')
        elif o["op"] == "circle":
            body.append(
                f'<circle cx="{o["x"]:.3f}" cy="{o["y"]:.3f}" r="{o["r"]}" '
                f'fill="{_css(o.get("fill"))}" stroke="{_css(o.get("stroke"))}" '
                f'stroke-width="{o.get("width", 0.3)}"/>')
        elif o["op"] == "text":
            anchor = {"middle": "middle", "end": "end"}.get(o.get("anchor"), "start")
            ang = o.get("angle", 0.0)
            # сцена и SVG обе y-вниз → угол в градусах напрямую (по часовой)
            tf = (f' transform="rotate({math.degrees(ang):.2f} '
                  f'{o["x"]:.3f} {o["y"]:.3f})"') if ang else ""
            family = o.get("font_family")
            op_font = (font_family if family in (None, "ui") else
                       _FONT_FAMILIES.get(family, font_family))
            body.append(
                f'<text x="{o["x"]:.3f}" y="{o["y"]:.3f}"{tf} '
                f'font-size="{o["size"]}" font-family="{op_font}" '
                f'text-anchor="{anchor}" fill="{_css(o.get("color", (0, 0, 0)))}">'
                f'{_esc(o["text"])}</text>')
    body.extend("</g>" * open_groups)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" height="{h}mm" '
            f'viewBox="0 0 {w} {h}">\n<defs>{"".join(defs)}</defs>\n'
            + "\n".join(body) + "\n</svg>\n")


def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
