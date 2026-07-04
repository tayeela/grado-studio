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
                if st.label and f["attrs"].get(st.label) is not None:
                    lx, ly = centroid(rings[0])
                    labels.append({"op": "text", "x": lx, "y": ly,
                                   "size": label_size,
                                   "text": str(f["attrs"][st.label]),
                                   "color": (0.15, 0.15, 0.15),
                                   "anchor": "middle"})
            for line in _lines(geom):
                ops.append({"op": "path", "rings": [tr.ring(line)],
                            "closed": False, "fill": None,
                            "stroke": st.stroke, "width": st.width,
                            "dash": st.dash})
            for pt in _points(geom):
                x, y = tr.to_mm(*pt)
                ops.append({"op": "circle", "x": x, "y": y, "r": st.marker,
                            "fill": st.fill, "stroke": st.stroke,
                            "width": st.width})
                if st.label and f["attrs"].get(st.label) is not None:
                    labels.append({"op": "text", "x": x, "y": y - st.marker - 1,
                                   "size": label_size,
                                   "text": str(f["attrs"][st.label]),
                                   "color": (0.1, 0.1, 0.1),
                                   "anchor": "middle"})
    ops.extend(labels)
    ops.append({"op": "unclip"})
    return ops
