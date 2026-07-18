"""Сцена: проект → список операций отрисовки в координатах листа (мм).

Операции — общий «стилевой байткод» обоих бэкендов:
  {"op": "clip", "rect": (x, y, w, h)} / {"op": "unclip"}
  {"op": "path", "rings": [[(x,y)...]], "closed", "fill", "stroke", "width", "dash"}
  {"op": "circle", "x", "y", "r", "fill", "stroke", "width"}
  {"op": "text", "x", "y", "size", "text", "color", "anchor"}
  {"op": "image", "data": bytes JPEG, "x","y","w","h" | "quad": (tl, tr, bl)}
Начало координат — левый верх листа, ось Y вниз (как на бумаге).
Картинка с "quad" кладётся параллелограммом по трём углам (подложка
Web Mercator повёрнута к сетке UTM на сближение меридианов).
"""


class MapTransform:
    """Метры СК проекта → миллиметры листа при заданном масштабе 1:S."""

    def __init__(self, frame_rect, center, scale):
        self.fx, self.fy, self.fw, self.fh = frame_rect
        self.cx, self.cy = center
        self.k = 1000.0 / scale  # мм на метр

    def to_mm(self, x, y):
        return (self.fx + self.fw / 2 + (x - self.cx) * self.k,
                self.fy + self.fh / 2 - (y - self.cy) * self.k)

    def ring(self, ring):
        return [self.to_mm(x, y) for x, y in ring]


def centroid(ring):
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(a) < 1e-12:
        return ring[0]
    return (cx / (3 * a), cy / (3 * a))


def project_extent(project):
    """Габариты всех слоёв проекта в СК проекта (по gpkg_contents)."""
    rows = project.conn.execute(
        "SELECT min(min_x), min(min_y), max(max_x), max(max_y) "
        "FROM gpkg_contents WHERE data_type='features'").fetchone()
    if rows is None or rows[0] is None:
        raise ValueError("в проекте нет объектов")
    return rows


def _polygons(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]
    return []


def _lines(geom):
    if geom["type"] == "LineString":
        return [geom["coordinates"]]
    if geom["type"] == "MultiLineString":
        return geom["coordinates"]
    return []


def _points(geom):
    if geom["type"] == "Point":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPoint":
        return geom["coordinates"]
    return []


def hatch_ops(rings, spacing, stroke, width=0.16, angle=45, cross=False):
    """Штриховка внутри полигона (мм листа): угол 0/45/90/135, cross — сетка.

    Семейство прямых n·p=c (n — нормаль к штрихам) пересекается с рёбрами
    всех колец; точки сортируются вдоль прямой, чётные пары дают отрезки —
    even-odd корректно обрабатывает дырки. Один op со многими сегментами.
    Углы по Эталону ЛГР (приказ ММА № 65): 0 горизонталь, 90 вертикаль,
    45 «///», 135 «\\\\»."""
    xs = [p[0] for r in rings for p in r]
    ys = [p[1] for r in rings for p in r]
    if not xs:
        return []
    # (нормаль, параметр вдоль штриха, шаг по c) для каждого направления
    axes = {0:   (lambda x, y: y,     lambda x, y: x,     spacing),
            90:  (lambda x, y: x,     lambda x, y: y,     spacing),
            45:  (lambda x, y: x + y, lambda x, y: x - y, spacing * 1.41421),
            135: (lambda x, y: x - y, lambda x, y: x + y, spacing * 1.41421)}
    segments = []
    for a in ([45, 135] if cross else [angle if angle in axes else 45]):
        n_of, t_of, step = axes[a]
        values = [n_of(x, y) for x, y in zip(xs, ys)]
        c = min(values) - (min(values) % step)
        c_max = max(values)
        while c <= c_max:
            hits = []
            for ring in rings:
                for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
                    s1, s2 = n_of(x1, y1) - c, n_of(x2, y2) - c
                    if (s1 > 0) == (s2 > 0):
                        continue
                    t = s1 / (s1 - s2)
                    px, py = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
                    hits.append((t_of(px, py), (px, py)))
            hits.sort(key=lambda h: h[0])
            for a2, b2 in zip(hits[::2], hits[1::2]):
                segments.append([list(a2[1]), list(b2[1])])
            c += step
    if not segments:
        return []
    return [{"op": "path", "rings": segments, "closed": False,
             "fill": None, "stroke": stroke, "width": width, "dash": None}]


def _ring_ccw(ring):
    """True — обход против часовой (в координатах y-вверх)."""
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        s += (x2 - x1) * (y2 + y1)
    return s < 0


# Штрих засечки-маркера чуть тоньше линии (см. marker_ops). Единая величина с
# холстом app.js MARKER_WIDTH_RATIO — холст и печать не расходятся по толщине.
MARKER_WIDTH_RATIO = 0.65


def _marker_glyph(px, py, tx, ty, nx, ny, shape, size, period, stroke, width,
                  lines, ops, filled=True):
    """Одна засечка в точке (px,py): касательная (tx,ty), нормаль внутрь
    (nx,ny). Линейные формы кладутся в lines (общий path), заливные — в ops.
    filled=False — контурный треугольник (обводка), как в QML fill alpha=0."""
    s = size
    if shape == "tick":
        lines.append([[px, py], [px + nx * s, py + ny * s]])
    elif shape == "tee":
        lines.append([[px, py], [px + nx * s, py + ny * s]])
        b = s * 0.5
        lines.append([[px - tx * b, py - ty * b], [px + tx * b, py + ty * b]])
    elif shape == "corner":
        lines.append([[px, py], [px + nx * s, py + ny * s]])
        lines.append([[px + nx * s, py + ny * s],
                      [px + nx * s + tx * s, py + ny * s + ty * s]])
    elif shape in ("chevron", "chevron_dot"):
        # Галка-стрелка: УЗКИЙ конец (остриё) НА линии, плечи раскрываются по
        # нормали (правка юзера: «узким концом повёрнуты к линии»). Раньше
        # остриё уходило ОТ линии — выглядело как «▽», не как галка в линию.
        w2 = s * 0.5
        lines.append([[px + nx * s - tx * w2, py + ny * s - ty * w2], [px, py]])
        lines.append([[px, py], [px + nx * s + tx * w2, py + ny * s + ty * w2]])
        if shape == "chevron_dot":
            hx = px + tx * period / 2 + nx * s * 0.5
            hy = py + ty * period / 2 + ny * s * 0.5
            ops.append({"op": "circle", "x": hx, "y": hy, "r": s * 0.15,
                        "fill": stroke, "stroke": None, "width": width})
    elif shape == "triangle":
        # «▼» остриём внутрь зоны, основание на линии. filled=False → КОНТУРНЫЙ
        # (в QML fill alpha=0: коды 11/18/50) — обводкой, а не заливкой.
        b = s * 0.5
        tri = [[px - tx * b, py - ty * b],
               [px + tx * b, py + ty * b],
               [px + nx * s, py + ny * s]]
        if filled:
            ops.append({"op": "path", "closed": True, "fill": stroke,
                        "stroke": None, "width": width, "dash": None,
                        "rings": [tri]})
        else:
            lines.append([tri[0], tri[1]])
            lines.append([tri[1], tri[2]])
            lines.append([tri[2], tri[0]])
    elif shape == "triangle2":
        # ООЗТ (код 47) — как ООПТ на эталоне: ДВА залитых треугольника,
        # наложенных друг на друга со сдвигом «вверх» (по нормали внутрь зоны).
        # Не разносить вдоль линии (▲▲ рядом) — это не эталонный знак.
        b = s * 0.5
        shift = s * 0.38  # второй треугольник сдвинут внутрь зоны
        for o in (0.0, shift):
            cx, cy = px + nx * o, py + ny * o
            ops.append({"op": "path", "closed": True, "fill": stroke,
                        "stroke": None, "width": width, "dash": None,
                        "rings": [[[cx - tx * b, cy - ty * b],
                                   [cx + tx * b, cy + ty * b],
                                   [cx + nx * s, cy + ny * s]]]})
    elif shape == "dot":
        ops.append({"op": "circle", "x": px, "y": py, "r": s / 2,
                    "fill": stroke, "stroke": None, "width": width})
    elif shape == "square":
        b = s / 2
        ops.append({"op": "path", "closed": True, "fill": stroke,
                    "stroke": None, "width": width, "dash": None,
                    "rings": [[[px - b, py - b], [px + b, py - b],
                               [px + b, py + b], [px - b, py + b]]]})
    elif shape == "diamond":
        b = s / 2
        ops.append({"op": "path", "closed": True, "fill": None,
                    "stroke": stroke, "width": width, "dash": None,
                    "rings": [[[px - b, py], [px, py - b],
                               [px + b, py], [px, py + b]]]})
    elif shape == "slashes":
        # две параллельные косые засечки «⫽» поперёк линии (Эталон: зоны
        # затопления/подтопления). Наклон по (касательная − нормаль внутрь).
        import math
        dx, dy = tx - nx, ty - ny
        dl = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dl, dy / dl        # направление штриха ~45° к линии
        h = s * 0.6                      # полудлина штриха
        sep = s * 0.45                   # разнос двух штрихов вдоль линии
        for o in (-sep / 2, sep / 2):
            cx, cy = px + tx * o, py + ty * o
            lines.append([[cx - ux * h, cy - uy * h],
                          [cx + ux * h, cy + uy * h]])


def marker_ops(pts, spec, stroke, width=0.3, closed=False, inward=1.0, dash=None):
    """Маркеры-засечки Эталона ЛГР вдоль линии/контура (мм листа).

    spec: {shape, period_mm, size_mm} из библиотеки. Формы образцов:
    tick ⊢, tee ⊥, corner Г, chevron ∨, chevron_dot ∨., triangle ▼,
    dot ●, square ■, diamond ◇. Засечка — по нормали inward (внутрь зоны).

    dash задан → линия штриховая: засечка стоит ТОЛЬКО на черте, не в разрыве
    (правка юзера), в центре самого длинного штриха цикла, на каждом k-м штрихе
    (k≈period/цикл). dash=None → сплошная: равномерно по period, углы свободны."""
    period = spec.get("period_mm", 20.0)
    size = spec.get("size_mm", 2.0)
    shape = spec.get("shape", "tick")
    filled = spec.get("filled", True)
    # Толщина штриха засечки: СВОЯ (ow_mm из QML outline_width), иначе чуть тоньше
    # линии (MARKER_WIDTH_RATIO, единый с холстом). ow важен для line-штрихов —
    # без него они выходили волоском (код 9 вообще исчезал).
    ow = spec.get("ow_mm")
    if shape == "tick" and ow:
        # tick: размах засечки = бо́льшая из (длина, толщина), штрих = меньшая
        # (см. app.js). Иначе код 9 (длина 0.25, толщина 1.88) — невидимый смаз.
        ext, th = max(size, ow), min(size, ow)
        size = ext
        width = max(0.05, th)
    elif ow:
        width = ow
    else:
        width = max(0.1, width * MARKER_WIDTH_RATIO)
    chain = list(pts) + ([pts[0]] if closed else [])
    ops, lines = [], []
    if dash:
        cycle = sum(dash) or period
        best_len, best_off, run = -1.0, 0.0, 0.0
        for i, seg in enumerate(dash):
            if i % 2 == 0 and seg > best_len:
                best_len, best_off = seg, run + seg / 2
            run += seg
        k = max(1, round(period / cycle))
        acc = 0.0
        for (x1, y1), (x2, y2) in zip(chain, chain[1:]):
            d = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            if d < 1e-9:
                continue
            tx, ty = (x2 - x1) / d, (y2 - y1) / d
            nx, ny = -ty * inward, tx * inward
            import math
            j = math.ceil((acc - best_off) / cycle)
            while True:
                L = j * cycle + best_off     # длина центра j-го штриха от начала
                if L > acc + d:
                    break
                if L >= acc and j % k == 0:
                    t = (L - acc) / d
                    _marker_glyph(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t,
                                  tx, ty, nx, ny, shape, size, period,
                                  stroke, width, lines, ops, filled)
                j += 1
            acc += d
    else:
        # Сплошная линия — засечки НЕПРЕРЫВНО по длине всей цепочки единым шагом
        # period (как MarkerLine в QGIS), а не делением КАЖДОГО ребра отдельно:
        # короткие рёбра пропускались, шаг d/n у каждого сегмента свой — отсюда
        # неравномерность. Согласовано с холстом (drawLineMarkers).
        acc = 0.0
        nxt = period * 0.5
        for (x1, y1), (x2, y2) in zip(chain, chain[1:]):
            d = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            if d < 1e-6:
                continue
            tx, ty = (x2 - x1) / d, (y2 - y1) / d
            nx, ny = -ty * inward, tx * inward
            while nxt <= acc + d:
                t = (nxt - acc) / d
                px, py = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
                _marker_glyph(px, py, tx, ty, nx, ny, shape, size, period,
                              stroke, width, lines, ops, filled)
                nxt += period
            acc += d
    if lines:
        ops.append({"op": "path", "rings": lines, "closed": False,
                    "fill": None, "stroke": stroke, "width": width,
                    "dash": None})
    return ops


def _inward_sign(ring):
    """Знак нормали (-ty, tx), направляющий засечки внутрь кольца."""
    (x1, y1), (x2, y2) = ring[0], ring[1]
    d = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 or 1.0
    nx, ny = -(y2 - y1) / d, (x2 - x1) / d
    cx, cy = centroid(ring)
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    return 1.0 if (cx - mx) * nx + (cy - my) * ny > 0 else -1.0


def _offset_chain(pts, gap, closed=False):
    """Параллельная полилиния на gap мм (двойная линия Эталона).

    Смещение по усреднённой нормали соседних сегментов — без сшивки
    самопересечений (для знаков листа этого достаточно)."""
    chain = list(pts)
    n = len(chain)
    if n < 2:
        return chain
    out = []
    for i in range(n):
        p_prev = chain[i - 1] if (i > 0 or closed) else chain[0]
        p_next = chain[(i + 1) % n] if (i < n - 1 or closed) else chain[-1]
        dx, dy = p_next[0] - p_prev[0], p_next[1] - p_prev[1]
        d = (dx * dx + dy * dy) ** 0.5 or 1.0
        out.append([chain[i][0] - dy / d * gap, chain[i][1] + dx / d * gap])
    return out


def line_label_ops(chain, text, color, size, closed):
    """Повторяющаяся подпись вдоль линии/контура (координаты мм листа) — как
    на холсте студии: равномерно по длине дуги, по касательной, не вверх
    ногами. Красные линии/ЗОУИТ подписываются с оптимальным шагом, а не один
    раз, чтобы подпись читалась на всём протяжении знака (Эталон ЛГР)."""
    import math
    pts = list(chain)
    if not pts or not text:
        return []
    if closed and pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    segs, total = [], 0.0
    for i in range(1, len(pts)):
        ax, ay = pts[i - 1]
        bx, by = pts[i]
        ln = math.hypot(bx - ax, by - ay)
        if ln < 0.2:
            continue
        segs.append((ax, ay, bx, by, ln, total))
        total += ln
    if not segs or total < 8.0:                  # слишком мелкий знак
        return []
    text_w = len(text) * size * 0.6              # оценка ширины строки на листе
    half = text_w / 2 + size * 0.3
    step = max(text_w + size * 8, total / max(1, round(total / 45.0)))
    cx = sum(p[0] for p in pts[:-1]) / (len(pts) - 1) if closed else 0.0
    cy = sum(p[1] for p in pts[:-1]) / (len(pts) - 1) if closed else 0.0

    def _place(seg, local):
        ax, ay, bx, by, ln, s0 = seg
        t = local / ln
        x = ax + (bx - ax) * t
        y = ay + (by - ay) * t
        ang = math.atan2(by - ay, bx - ax)
        if ang > math.pi / 2 or ang < -math.pi / 2:
            ang += math.pi                       # не вверх ногами
        nx, ny = -math.sin(ang), math.cos(ang)   # нормаль к линии
        if closed and (x - cx) * nx + (y - cy) * ny < 0:
            nx, ny = -nx, -ny                    # развернуть наружу зоны
        off = size * 1.4                         # отступ от линии, чтобы читалось
        return {"op": "text", "x": x + nx * off, "y": y + ny * off,
                "size": size, "text": text, "color": color,
                "anchor": "middle", "angle": ang}

    # подпись ставится ТОЛЬКО там, где целиком помещается на ОДНОМ прямом
    # отрезке (не заходя за угол) — иначе текст вылезал за контур на изгибах
    out = []
    s = step / 2
    while s < total:
        for sg in segs:
            if sg[5] <= s <= sg[5] + sg[4]:
                local = s - sg[5]
                if half <= local <= sg[4] - half:
                    out.append(_place(sg, local))
                break
        s += step
    if not out:                                  # хотя бы одна на самом длинном отрезке
        seg = max(segs, key=lambda sg: sg[4])
        if seg[4] >= text_w:
            out.append(_place(seg, seg[4] / 2))
    return out


def _label_bbox(lbl):
    """Грубая оценка bbox подписи в мм листа — без реальных метрик шрифта
    (~0.55 кегля на символ, моноширинное приближение, для greedy-фильтра
    наложения этого достаточно)."""
    w = len(lbl["text"]) * lbl["size"] * 0.55
    h = lbl["size"] * 1.2
    x, y = lbl["x"], lbl["y"]
    anchor = lbl.get("anchor", "start")
    if anchor == "middle":
        x0 = x - w / 2
    elif anchor == "end":
        x0 = x - w
    else:
        x0 = x
    return (x0, y - h, x0 + w, y + h * 0.25)


_LABEL_CELL_MM = 8.0     # подпись листа заведомо мельче ячейки


def _filter_overlapping_labels(labels):
    """Не показывать подпись, если её bbox пересекается с уже принятой
    подписью того же слоя за этот проход (greedy, аналог фильтра на холсте).

    Занятость — грид по ячейкам, а не список: раньше каждая подпись сверялась
    ЛИНЕЙНЫМ перебором со всеми уже принятыми, и на городском слое (десятки
    тысяч объектов) это давало квадратичный рост — тот же дефект, что был на
    холсте. Правило не изменилось: побеждает первый занявший место; подпись
    задевает 1-4 ячейки и сравнивается только с соседями по ним, поэтому
    результат совпадает с полным перебором."""
    cells = {}
    out = []
    for lbl in labels:
        x0, y0, x1, y1 = _label_bbox(lbl)
        lid = lbl.get("_layer_id")
        keys = [(lid, cx, cy)
                for cx in range(int(x0 // _LABEL_CELL_MM), int(x1 // _LABEL_CELL_MM) + 1)
                for cy in range(int(y0 // _LABEL_CELL_MM), int(y1 // _LABEL_CELL_MM) + 1)]
        if any(x0 < b[2] and x1 > b[0] and y0 < b[3] and y1 > b[1]
               for k in keys for b in cells.get(k, ())):
            continue
        for k in keys:
            cells.setdefault(k, []).append((x0, y0, x1, y1))
        out.append(lbl)
    return out


def build_ops(project, frame_rect, scale, center=None, styles=None,
              label_size=2.2, only=None):
    """Операции отрисовки карты проекта в рамке frame_rect (мм), М 1:scale.

    only — набор layer_id: рисовать только эти слои (опорный план не
    показывает проектную застройку). Ключ — layer_id, а не код класса,
    чтобы два слоя одного класса можно было включить порознь."""
    from .style import StyleSet
    styles = styles or StyleSet()
    if center is None:
        x0, y0, x1, y1 = project_extent(project)
        center = ((x0 + x1) / 2, (y0 + y1) / 2)
    tr = MapTransform(frame_rect, center, scale)

    layers = sorted(project.layers(),
                    key=lambda i: styles.resolve(i["code"]).z)
    if only is not None:
        layers = [i for i in layers if i["layer_id"] in set(only)]
    ops = [{"op": "clip", "rect": tuple(frame_rect)}]
    labels = []
    for info in layers:
        layer_st = styles.resolve(info["code"])
        for f in project.layer_by_id(info["layer_id"]).features():
            geom = f["geom"]
            if not geom:
                continue
            # per-object стиль (столбец style_id в .grado) важнее стиля слоя:
            # напр. водоохранная зона со знаком Эталона ЛГР на слое ЗОУИТ
            st = styles.resolve_id(f.get("style_id")) or layer_st
            # Знаки ЛГР: штрих и шаг засечек в QML заданы в метрах на местности,
            # а в библиотеке лежат в мм для опорного 1:2000 → пересчитываем на
            # масштаб ЭТОГО листа, иначе печать эталонна только при 1:2000
            # (холст делает то же через groundFactor). for_scale отдаёт тот же
            # объект для не-ЛГР стилей, так что накладных расходов нет.
            st = st.for_scale(scale)
            for poly in _polygons(geom):
                rings = [tr.ring(r) for r in poly]
                ops.append({"op": "path", "rings": rings, "closed": True,
                            "fill": st.fill, "stroke": st.stroke,
                            "width": st.width, "dash": st.dash})
                if st.hatch:
                    h = st.hatch if isinstance(st.hatch, dict) else {}
                    from .style import hex_to_rgb
                    color = hex_to_rgb(h.get("color")) or st.stroke
                    ops.extend(hatch_ops(
                        rings, spacing=h.get("spacing_mm", 1.6), stroke=color,
                        angle=h.get("angle", 45), cross=h.get("cross", False)))
                if st.line_marker and len(rings[0]) >= 3:
                    # направление засечки по знаку (Эталон): по умолчанию остриём
                    # ВНУТРЬ зоны, dir=="out" — наружу (ООПТ/ландшафт ОКН/
                    # водоохр./прибреж.), dir=="both" — по ОБЕ стороны линии
                    # (в QML это два под-маркера с углами 0 и 180: 8, 18, 55).
                    d = _inward_sign(rings[0])
                    dirs = ((d, -d) if st.line_marker.get("dir") == "both"
                            else (-d,) if st.line_marker.get("dir") == "out"
                            else (d,))
                    for side in dirs:
                        ops.extend(marker_ops(
                            rings[0], st.line_marker, st.stroke, width=st.width,
                            closed=True, inward=side, dash=st.dash))
                if st.double:
                    ops.append({"op": "path", "closed": True, "fill": None,
                                "stroke": st.stroke, "width": st.width,
                                "dash": st.dash,
                                "rings": [_offset_chain(
                                    rings[0], st.double, closed=True)]})
                if st.label and f["attrs"].get(st.label) is not None:
                    lx, ly = centroid(rings[0])
                    labels.append({"op": "text", "x": lx, "y": ly,
                                   "size": st.label_size or label_size,
                                   "text": str(f["attrs"][st.label]),
                                   "color": st.label_color or (0.15, 0.15, 0.15),
                                   "font_family": st.label_font_family or "ui",
                                   "anchor": "middle",
                                   "_layer_id": info["layer_id"]})
                if st.line_label:
                    labels.extend(dict(lbl, _layer_id=info["layer_id"]) for lbl in line_label_ops(
                        rings[0], st.line_label, st.stroke or (0.85, 0.1, 0.14),
                        label_size, closed=True))
            for line in _lines(geom):
                pts = tr.ring(line)
                ops.append({"op": "path", "rings": [pts],
                            "closed": False, "fill": None,
                            "stroke": st.stroke, "width": st.width,
                            "dash": st.dash})
                if st.line_marker and len(pts) >= 2:
                    ops.extend(marker_ops(pts, st.line_marker, st.stroke,
                                          width=st.width, dash=st.dash))
                if st.double and len(pts) >= 2:
                    ops.append({"op": "path", "closed": False, "fill": None,
                                "stroke": st.stroke, "width": st.width,
                                "dash": st.dash,
                                "rings": [_offset_chain(pts, st.double)]})
                if st.line_label and len(pts) >= 2:
                    labels.extend(dict(lbl, _layer_id=info["layer_id"]) for lbl in line_label_ops(
                        pts, st.line_label, st.stroke or (0.85, 0.1, 0.14),
                        label_size, closed=False))
            for pt in _points(geom):
                x, y = tr.to_mm(*pt)
                ops.append({"op": "circle", "x": x, "y": y, "r": st.marker,
                            "fill": st.fill, "stroke": st.stroke,
                            "width": st.width})
                if st.label and f["attrs"].get(st.label) is not None:
                    labels.append({"op": "text", "x": x, "y": y - st.marker - 1,
                                   "size": st.label_size or label_size,
                                   "text": str(f["attrs"][st.label]),
                                   "color": st.label_color or (0.1, 0.1, 0.1),
                                   "font_family": st.label_font_family or "ui",
                                   "anchor": "middle",
                                   "_layer_id": info["layer_id"]})
    labels = _filter_overlapping_labels(labels)
    for lbl in labels:
        lbl.pop("_layer_id", None)
    ops.extend(labels)
    ops.append({"op": "unclip"})
    return ops
