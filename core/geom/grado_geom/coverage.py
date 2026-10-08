"""Топологическое покрытие (coverage): зоны с общими границами.

Смежные функциональные зоны и участки межевания хранят общее ребро один
раз: правка ребра двигает обе зоны, дырки и нахлёсты невозможны
конструктивно. Сборка — из полигонов с точно совпадающими общими цепочками
вершин (так рисуют с привязками). Хранение рёбер — своё (у shapely такой
модели нет); площади и проверка целостности — shapely 2 (GEOS):
`coverage_is_valid` ловит нахлёсты и щели между зонами.
Вызывают: core/layout (пример раскладки), закрытая студия; тесты —
core/geom/tests/test_snap_coverage.py.
"""

import math

import shapely
from shapely.geometry import LinearRing, Polygon


class CoverageError(ValueError):
    pass


def _norm(pt):
    return (round(pt[0], 9), round(pt[1], 9))


def _ccw(ring):
    return ring if shapely.is_ccw(LinearRing(ring)) else ring[::-1]


class Coverage:
    def __init__(self):
        self.edges = {}    # eid -> {"pts": [...], "left": fid|None, "right": fid|None}
        self.faces = {}    # fid -> [(eid, forward)]
        self._next_eid = 1

    @classmethod
    def from_polygons(cls, polygons):
        """polygons: {fid: кольцо [(x,y), ...]} — без дырок, общие границы
        совпадают повершинно."""
        cov = cls()
        walks = {}
        seg_usage = {}  # неориентированный сегмент -> [(fid, направление)]
        for fid, ring in polygons.items():
            ring = [_norm(p) for p in ring]
            if ring[0] == ring[-1]:
                ring = ring[:-1]
            if len(ring) < 3:
                raise CoverageError(f"{fid}: вырожденное кольцо")
            ring = _ccw(ring)
            walks[fid] = ring
            for a, b in zip(ring, ring[1:] + ring[:1]):
                if a == b:
                    raise CoverageError(f"{fid}: нулевой сегмент {a}")
                key = (min(a, b), max(a, b))
                seg_usage.setdefault(key, []).append((fid, a < b))

        for key, users in seg_usage.items():
            if len(users) > 2:
                raise CoverageError(f"сегмент {key} принадлежит {len(users)} зонам — нахлёст")
            if len(users) == 2 and users[0][1] == users[1][1]:
                raise CoverageError(f"сегмент {key} обходится дважды в одном "
                                    "направлении — зоны перекрываются")

        def other_face(fid, a, b):
            key = (min(a, b), max(a, b))
            for uf, _ in seg_usage[key]:
                if uf != fid:
                    return uf
            return None

        # разбиваем обход каждой грани на цепочки с одинаковым соседом
        seg_edge = {}  # ориентированный сегмент -> (eid, forward)
        for fid, ring in walks.items():
            segs = list(zip(ring, ring[1:] + ring[:1]))
            pairs = [other_face(fid, a, b) for a, b in segs]
            # начинаем цепочку с границы смены соседа (иначе кольцо — одна цепь)
            start = 0
            for i in range(len(segs)):
                if pairs[i] != pairs[i - 1]:
                    start = i
                    break
            order = list(range(start, len(segs))) + list(range(start))
            boundary = []
            chain, chain_pair = [], object()
            for i in order:
                if pairs[i] != chain_pair and chain:
                    boundary.append((chain, chain_pair))
                    chain = []
                chain_pair = pairs[i]
                chain.append(segs[i])
            boundary.append((chain, chain_pair))

            face_edges = []
            for chain, neighbor in boundary:
                rev_key = tuple((b, a) for a, b in reversed(chain))
                if rev_key and rev_key[0] in seg_edge:
                    # цепь уже создана соседом — идём по ней в обратную сторону
                    eid, _ = seg_edge[rev_key[0]]
                    face_edges.append((eid, False))
                    cov.edges[eid]["right"] = fid
                else:
                    pts = [chain[0][0]] + [b for _, b in chain]
                    eid = cov._next_eid
                    cov._next_eid += 1
                    cov.edges[eid] = {"pts": pts, "left": fid, "right": None}
                    for seg in chain:
                        seg_edge[seg] = (eid, True)
                    face_edges.append((eid, True))
            cov.faces[fid] = face_edges
        return cov

    # --- доступ -------------------------------------------------------------

    def polygon(self, fid):
        ring = []
        for eid, forward in self.faces[fid]:
            pts = self.edges[eid]["pts"]
            pts = pts if forward else pts[::-1]
            if ring and ring[-1] == pts[0]:
                pts = pts[1:]
            ring.extend(pts)
        if ring[0] == ring[-1]:
            ring = ring[:-1]
        return ring

    def area(self, fid):
        return Polygon(self.polygon(fid)).area

    def areas(self):
        return {fid: self.area(fid) for fid in self.faces}

    def shared_edges(self):
        return [eid for eid, e in self.edges.items()
                if e["left"] is not None and e["right"] is not None]

    # --- редактирование -------------------------------------------------------

    def edit_edge(self, eid, new_pts):
        """Заменить геометрию ребра (узлы на концах неподвижны).

        Обе смежные зоны меняются одновременно — общая граница одна."""
        e = self.edges[eid]
        new_pts = [_norm(p) for p in new_pts]
        if new_pts[0] != e["pts"][0] or new_pts[-1] != e["pts"][-1]:
            raise CoverageError("концы ребра должны совпадать с узлами")
        e["pts"] = new_pts

    # --- контроль целостности ---------------------------------------------------

    def outer_ring(self):
        boundary = {eid: e for eid, e in self.edges.items() if e["right"] is None}
        if not boundary:
            raise CoverageError("нет внешней границы")
        start_eid = min(boundary)
        ring = list(boundary[start_eid]["pts"])
        used = {start_eid}
        while ring[0] != ring[-1]:
            nxt = None
            for eid, e in boundary.items():
                if eid in used:
                    continue
                if e["pts"][0] == ring[-1]:
                    nxt = e["pts"][1:]
                elif e["pts"][-1] == ring[-1]:
                    nxt = e["pts"][::-1][1:]
                if nxt:
                    used.add(eid)
                    ring.extend(nxt)
                    break
            if nxt is None:
                raise CoverageError("внешняя граница не замыкается")
        return ring[:-1]

    def validate(self, tol=1e-6):
        """Зоны образуют правильное покрытие (shapely.coverage_is_valid) и сумма их площадей ==
        площадь внешней границы (нет дырок/нахлёстов)."""
        faces = [Polygon(self.polygon(fid)) for fid in self.faces]
        if not shapely.coverage_is_valid(faces):
            raise CoverageError("зоны перекрываются или между ними щель")
        total = sum(f.area for f in faces)
        outer = Polygon(self.outer_ring()).area
        if not math.isclose(total, outer, rel_tol=tol):
            raise CoverageError(
                f"баланс не сходится: зоны {total:.6f} ≠ контур {outer:.6f}")
        return True
