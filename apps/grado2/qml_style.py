"""ГРАДО 2 · стиль слоя из файла стиля QGIS (.qml) — план 08.11.2026, шаг 2: владелец переносит свои стили из QGIS одним
файлом. Разбор XML — стандартный xml.etree; файл с объявлением сущностей (<!ENTITY) отклоняется сразу,
размер тела ограничен сервером. Отрисовщики: «Единый символ» → единый цвет, «Категории» → категории по полю, «Градуированный» и «Правила» →
правила ГРАДО (простые условия `"поле" = 'значение'`, >, <, >=, <=, <>; сложные выражения пропускаются и попадают в
отчёт). Символ QGIS — стопка слоёв: первый SimpleFill / SimpleLine / SimpleMarker → основной знак, остальные → части
`parts` (symbology.js cleanParts): SimpleLine → линия по контуру (со сдвигом внутрь — полоса), LinePatternFill → штриховка,
MarkerLine/HashedLine → значки вдоль линии. Размеры QGIS в мм → пиксели ГРАДО (÷ 0,26 — как PX_MM печати). Подписи —
поле, кегль и цвет из «simple» labeling. Зовёт server.post_style_qml; проверяет tests/test_qml_style.py."""
import re
import xml.etree.ElementTree as ET

PX_MM = 0.26
DASH = {"dash": [6, 4], "dot": [1.5, 3], "dash dot": [8, 3, 1.5, 3], "dash dot dot": [8, 3, 1.5, 3, 1.5, 3]}
BRUSH = {"f_diagonal": "45", "b_diagonal": "135", "horizontal": "0", "vertical": "90", "cross": "x0", "diagonal_x": "x45",
         "dense1": "dots", "dense2": "dots", "dense3": "dots", "dense4": "dots", "dense5": "dots", "dense6": "dots", "dense7": "dots"}
SHAPE = {"triangle": "tri", "equilateral_triangle": "tri", "arrowhead": "tri", "filled_arrowhead": "tri", "circle": "dot",
         "cross": "cross", "cross2": "cross", "x": "cross", "line": "tick"}
OPS = {"=": "=", "<>": "≠", "!=": "≠", ">": ">", "<": "<", ">=": "≥", "<=": "≤"}


def _props(layer):
    """Свойства слоя символа: QGIS 3.x — <Option type="Map"><Option name= value=/>, старые — <prop k= v=/>."""
    p = {}
    for o in layer.iter("Option"):
        if o.get("name") and o.get("value") is not None:
            p.setdefault(o.get("name"), o.get("value"))
    for o in layer.iter("prop"):
        p.setdefault(o.get("k"), o.get("v"))
    return p


def _color(v):
    """«r,g,b,a» (QGIS 3.28+ — с хвостом «,rgb:…») или «#rrggbb» → ("#rrggbb", альфа 0..1) или (None, 0)."""
    if not v:
        return None, 0.0
    if v.startswith("#") and len(v) >= 7:
        return v[:7].lower(), 1.0
    n = [int(float(x)) for x in re.findall(r"-?\d+(?:\.\d+)?", v.split(",rgb:")[0])[:4]]
    if len(n) < 3:
        return None, 0.0
    return "#%02x%02x%02x" % tuple(max(0, min(255, x)) for x in n[:3]), (n[3] / 255 if len(n) > 3 else 1.0)


def _mm(v, d=0.0, unit="MM"):
    """Размер QGIS → пиксели ГРАДО. Единицы: MM (по умолчанию), Pixel, Point; MapUnit — как мм (масштаба нет)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return d
    if unit == "Pixel":
        return x
    if unit == "Point":
        x *= 0.3528
    return x / PX_MM


def _r(x, k=2):
    return round(x, k)


def _sub(layer, kind):
    """Первый слой вложенного символа (линия штриховки, значок вдоль линии)."""
    for s in layer.iter("symbol"):
        if s.get("type") == kind:
            for ly in s.findall("layer"):
                return ly, float(s.get("alpha") or 1)
    return None, 1.0


def symbol(sym, geom, report):
    """Символ QGIS → поля стиля ГРАДО: {fill, opacity, stroke, width, dash, hatch, hatchPat, hatchStep, hatchColor, parts}."""
    out, parts, base = {}, [], False
    alpha = float(sym.get("alpha") or 1)
    for ly in sym.findall("layer"):
        if ly.get("enabled", "1") == "0":
            continue
        cls, p = ly.get("class") or "", _props(ly)
        unit = p.get("outline_width_unit") or p.get("line_width_unit") or p.get("size_unit") or "MM"
        if cls == "SimpleFill" and geom == "poly":
            c, a = _color(p.get("color"))
            oc, _ = _color(p.get("outline_color"))
            st, ost = p.get("style", "solid"), p.get("outline_style", "solid")
            if not base:
                base = True
                out["fill"] = c or "#9aa1a8"
                out["opacity"] = _r(0 if st == "no" else a * alpha)
                if st in BRUSH:
                    out.update(hatch=True, hatchPat=BRUSH[st], hatchColor=c, opacity=0)
                out["stroke"], out["strokeOwn"] = oc or "#000000", True
                out["width"] = 0 if ost == "no" else _r(_mm(p.get("outline_width"), 1, unit), 1)
                if ost in DASH:
                    out["dash"] = DASH[ost]
            elif st in BRUSH and c:
                parts.append({"k": "hatch", "c": c, "hp": BRUSH[st], "hs": 8, "w": 1})
            elif st != "no" and c:
                parts.append({"k": "band", "c": c, "a": _r(a * alpha), "b": 60})        # сплошная заливка поверх — широкая полоса
            continue
        if cls == "SimpleLine":
            c, a = _color(p.get("line_color") or p.get("color"))
            w = _mm(p.get("line_width"), 1, p.get("line_width_unit") or "MM")
            dash = DASH.get(p.get("line_style", "solid"))
            if p.get("use_custom_dash") == "1" and p.get("customdash"):
                try:
                    dash = [_r(_mm(x, 1, p.get("customdash_unit") or "MM"), 1) for x in p["customdash"].split(";")]
                except ValueError:
                    pass
            off = _mm(p.get("offset"), 0, p.get("offset_unit") or "MM")
            if geom == "line" and not base:
                base = True
                out.update(fill=c or "#333333", width=_r(max(.3, w), 1))
                if dash:
                    out["dash"] = dash
            elif geom == "poly" and abs(off) >= .5 and w >= 2:
                parts.append({"k": "band", "c": c or "#333333", "a": _r(a * alpha), "b": _r(w, 1)})   # широкая линия со сдвигом — полоса вдоль границы
            else:
                part = {"k": "line", "c": c or "#333333", "w": _r(max(.1, w), 1), "a": _r(a * alpha)}
                if dash:
                    part["dash"] = dash
                parts.append(part)
            continue
        if cls == "LinePatternFill":
            sub, sa = _sub(ly, "line")
            sp = _props(sub) if sub is not None else {}
            c, _ = _color(sp.get("line_color") or p.get("color"))
            ang = float(p.get("lineangle") or 45) % 180
            hp = min(("0", 0), ("45", 45), ("90", 90), ("135", 135), ("0", 180), key=lambda t: abs(t[1] - ang))[0]
            parts.append({"k": "hatch", "c": c or "#333333", "hp": hp, "hs": _r(max(4, _mm(p.get("distance"), 8, p.get("distance_unit") or "MM")), 1),
                          "w": _r(max(.1, _mm(sp.get("line_width"), .26)), 1)})
            continue
        if cls in ("MarkerLine", "HashedLine"):
            sub, _ = _sub(ly, "marker" if cls == "MarkerLine" else "line")
            sp = _props(sub) if sub is not None else {}
            c, _ = _color(sp.get("color") or sp.get("line_color"))
            shape = "tick" if cls == "HashedLine" else SHAPE.get(sp.get("name"), "dot")
            size = _mm(p.get("hash_length") if cls == "HashedLine" else sp.get("size"), 5)
            off = float(p.get("offset") or 0)
            parts.append({"k": "marks", "c": c or "#333333", "shape": shape, "step": _r(max(4, _mm(p.get("interval"), 16, p.get("interval_unit") or "MM")), 1),
                          "size": _r(max(1, size), 1), "side": -1 if off < 0 else 1, "w": _r(max(.1, _mm(sp.get("line_width"), .26)), 1)})
            continue
        if cls in ("SimpleMarker", "FontMarker", "SvgMarker") and geom == "point" and not base:
            base = True
            c, _ = _color(p.get("color"))
            oc, _ = _color(p.get("outline_color"))
            size = _mm(p.get("size"), 2, p.get("size_unit") or "MM")
            out.update(fill=c or "#2a78d6", stroke=oc or "#ffffff", width=_r(max(.3, (size / 2 - 2) / 2), 1))
            continue
        report.append(f"слой символа {cls} не переносится")
    if parts and geom != "point":
        out["parts"] = parts[:12]
    return out


def _filter(expr):
    """Простое условие правила QGIS → {field, op, val} или None."""
    m = re.fullmatch(r'\s*"([^"]+)"\s*(=|<>|!=|>=|<=|>|<)\s*(\'((?:[^\']|\'\')*)\'|-?\d+(?:\.\d+)?)\s*', expr or "")
    if not m:
        return None
    val = m.group(4).replace("''", "'") if m.group(4) is not None else m.group(3)
    return {"field": m.group(1), "op": OPS[m.group(2)], "val": val}


def convert(text, geom):
    """Текст .qml и вид геометрии слоя (poly, line, point) → (стиль ГРАДО, отчёт [строки]). Ошибка разбора — ValueError."""
    if "<!ENTITY" in text:
        raise ValueError("в файле стиля объявлены сущности XML — такой файл не открываем")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"файл не похож на стиль QGIS (.qml): {e}") from None
    r = root.find(".//renderer-v2")
    if r is None:
        raise ValueError("в файле нет отрисовщика QGIS (renderer-v2)")
    report = []
    syms = {s.get("name"): s for s in r.findall("./symbols/symbol")}
    kind = r.get("type")
    style = {"mode": "single"}
    if kind == "singleSymbol":
        if syms:
            style.update(symbol(next(iter(syms.values())), geom, report))
    elif kind == "categorizedSymbol":
        style.update(mode="cat", cat={"field": r.get("attr") or "", "colors": {}, "off": [], "sym": {}})
        for c in r.findall("./categories/category"):
            v, s = c.get("value") or "", symbol(syms[c.get("symbol")], geom, report) if c.get("symbol") in syms else {}
            style["cat"]["colors"][v] = s.pop("fill", "#9aa1a8")
            if c.get("render") == "false":
                style["cat"]["off"].append(v)
            s.pop("strokeOwn", None)
            if s:
                style["cat"]["sym"][v] = s
    elif kind in ("graduatedSymbol", "RuleRenderer"):
        rules = []
        if kind == "graduatedSymbol":
            for g in sorted(r.findall("./ranges/range"), key=lambda g: float(g.get("upper") or 0)):
                rules.append(({"field": r.get("attr") or "", "op": "≤", "val": g.get("upper")}, g.get("symbol")))
        else:
            for ru in r.iter("rule"):
                if ru.get("symbol") is None:
                    continue
                f = _filter(ru.get("filter"))
                if f is None:
                    report.append(f"правило «{ru.get('label') or ru.get('filter')}» сложнее «поле = значение» — пропущено")
                    continue
                rules.append((f, ru.get("symbol")))
        lst = []
        for f, sid in rules:
            s = symbol(syms[sid], geom, report) if sid in syms else {}
            s.pop("strokeOwn", None)
            lst.append({**f, "fill": s.pop("fill", "#9aa1a8"), **s})
        style.update(mode="rules", rules={"list": lst, "elseFill": "#dddddd", "elseHide": True})
    else:
        report.append(f"отрисовщик QGIS «{kind}» не переносится — взят только первый символ")
        if syms:
            style.update(symbol(next(iter(syms.values())), geom, report))
    lab = root.find(".//labeling/settings/text-style")
    if lab is not None and (root.find(".//labeling").get("type") == "simple") and lab.get("fieldName"):
        style["label"] = lab.get("fieldName")
        try:
            style["labelSize"] = max(7, min(24, round(float(lab.get("fontSize") or 10))))
        except ValueError:
            pass
        c, _ = _color(lab.get("textColor"))
        if c:
            style["labelColor"] = c
    return style, sorted(set(report))
