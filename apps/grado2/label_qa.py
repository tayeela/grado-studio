"""Самопроверка оформления листа (#55, аудит #53): подписи карты, закрытые легендой или угловой надписью, стоящие у
рамки карты ближе 2,5 мм, подписанные на карте дважды.

Подписи поверх линий слоёв и угловые надписи на линиях — не огрех (владелец 10.10.2026, #54 вопросы 2–3: «подпись
просто поверх линий, не страшно»), их проверка не ищет.

Работает по готовым операциям страницы (после правок макета и типографики — то, что уйдёт в PDF и PPTX), поэтому
видит итог, а не намерение размещения. Только обнаружение и отчёт.

Карта — участок операций между "clip" и "unclip". Подписи — тексты слоя «Подписи». Закрывают карту тексты и белые
плашки других рамок, лежащие на карте (угловые надписи, легенда на снимке). Правило: docs/wiki/album-rules.md §2.
"""
import math

EDGE_MM = 2.5                    # подпись не ближе к рамке карты (правило 11)
EDGE_TOL = 0.25                  # запас на приближённую рамку подписи: размещение держит ровно 2,5 мм
WHITE = (1, 1, 1)


def _white(c):
    return c is not None and all(abs(float(a) - b) < .02 for a, b in zip(c, WHITE))


def label_box(o):
    """Повёрнутая рамка текстовой операции: (центр x, центр y, угол, полуширина, полувысота) в мм листа.
    Тело букв: от базовой линии на 0,7 кегля вверх (печать ставит базу на 0,35 кегля ниже центра подписи)."""
    from print_io import _text_w
    size = float(o["size"])
    w = _text_w(o["text"], o.get("font_family"), size)
    ang = float(o.get("angle") or 0)
    ca, sa = math.cos(ang), math.sin(ang)
    anchor = o.get("anchor") or "start"
    along = 0.0 if anchor == "middle" else -w / 2 if anchor == "end" else w / 2   # сдвиг центра вдоль строки от точки привязки
    up = size * .35                                                    # центр — выше базовой линии
    cx = o["x"] + along * ca + math.sin(ang) * up
    cy = o["y"] + along * sa - math.cos(ang) * up
    return cx, cy, ang, max(.1, w / 2 - .15), size * .33


def _corners(b):
    cx, cy, ang, hw, hh = b
    ca, sa = math.cos(ang), math.sin(ang)
    return [(cx + dx * ca - dy * sa, cy + dx * sa + dy * ca) for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]


def _aabb(b):
    pts = _corners(b)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _overlap(a, b):
    """Пересечение двух повёрнутых рамок (теорема о разделяющей оси)."""
    pa, pb = _corners(a), _corners(b)
    for poly in (pa, pb):
        for i in range(4):
            (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % 4]
            nx, ny = y1 - y2, x2 - x1
            sa_ = [nx * x + ny * y for x, y in pa]
            sb_ = [nx * x + ny * y for x, y in pb]
            if max(sa_) <= min(sb_) or max(sb_) <= min(sa_):
                return False
    return True


def page_conflicts(ops):
    """Места на странице: [{"text", "with", "kind"}]; kind — "cover" (подпись под with: угловая надпись, легенда),
    "edge" (ближе 2,5 мм к рамке карты, with — зазор), "dup" (подпись на карте дважды, with — сколько раз)."""
    maps, cur, outside = [], None, []
    for o in ops:
        op = o.get("op")
        if op == "clip":
            cur = {"rect": tuple(o["rect"]), "labels": [], "layer": None}
            maps.append(cur)
        elif op == "unclip":
            cur = None
        elif cur is None:
            outside.append(o)
        elif op == "layer":
            cur["layer"] = o.get("name")
        elif op == "text" and cur["layer"] == "Подписи" and o.get("text") and o.get("size"):
            cur["labels"].append(o)
    out = []
    for m in maps:
        if not m["labels"]:
            continue
        rx, ry, rw, rh = m["rect"]
        covers = []                                                     # тексты и белые плашки других рамок на этой карте
        for o in outside:
            if o.get("op") == "text" and o.get("text") and o.get("size"):
                b = label_box(o)
                x0, y0, x1, y1 = _aabb(b)
                if x1 > rx and x0 < rx + rw and y1 > ry and y0 < ry + rh:
                    covers.append((b, o["text"], "text"))
            elif o.get("op") == "path" and o.get("closed") and o.get("fill") is not None and _white(o["fill"]) and o.get("rings"):
                xs = [p[0] for r in o["rings"] for p in r]
                ys = [p[1] for r in o["rings"] for p in r]
                x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
                inside = x0 >= rx - 1 and y0 >= ry - 1 and x1 <= rx + rw + 1 and y1 <= ry + rh + 1
                if inside and (x1 - x0) * (y1 - y0) < .5 * rw * rh:
                    covers.append((((x0 + x1) / 2, (y0 + y1) / 2, 0.0, (x1 - x0) / 2, (y1 - y0) / 2), "легенда", "plate"))
        for o in m["labels"]:
            b = label_box(o)
            t = o["text"]
            for cb, ct, ck in covers:
                if _overlap(b, cb):
                    out.append({"text": t, "with": ct if ck == "text" else "легенда", "kind": "cover"})
                    break
            x0, y0, x1, y1 = _aabb(b)
            gap = min(x0 - rx, y0 - ry, rx + rw - x1, ry + rh - y1)
            if gap < EDGE_MM - EDGE_TOL:
                out.append({"text": t, "with": f"{max(0.0, gap):.1f} мм", "kind": "edge"})
        seen = {}
        for o in m["labels"]:
            if sum(c.isalpha() for c in o["text"]) >= 3:                # номера зон и выносок повторяются законно
                seen[o["text"]] = seen.get(o["text"], 0) + 1
        out += [{"text": t, "with": str(n), "kind": "dup"} for t, n in seen.items() if n > 1]
    return _dedupe(out)


def _dedupe(rows):
    seen, out = set(), []
    for r in rows:
        k = (r["text"], r["with"], r["kind"])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def phrase(r):
    """Строка для владельца: «ЖК «Сиреневый парк» подписан 2 раза»."""
    t = f"«{r['text']}»"
    if r["kind"] == "dup":
        return f"{t} подписан {r['with']} {_times(int(r['with']))}"
    return {"cover": f"{t} под «{r['with']}»", "edge": f"{t} у рамки карты ({r['with']})"}[r["kind"]]


def _times(n):
    return "раза" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "раз"


def album_conflicts(pages):
    """[(номер листа с 1, [места])] по операциям страниц [(w, h, ops)] — только листы, где места есть."""
    out = []
    for i, (_w, _h, ops) in enumerate(pages, start=1):
        rows = page_conflicts(ops)
        if rows:
            out.append((i, rows))
    return out
