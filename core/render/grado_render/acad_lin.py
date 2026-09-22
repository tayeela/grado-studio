"""AutoCAD complex linetypes: reading .SHX (compiled shapes) and .LIN (linetypes).

Used for the Moscow red-line standard REDLN97.LIN + RED_LNS.SHX
(docs/standards/redln97). The result is plain data: shapes become polylines in
shape units, a linetype becomes a list of pattern elements. The web renderer,
the DXF export and (later) printing all draw from this data.

The SHX format is the AutoCAD shape specification ("AutoCAD-86 shapes 1.0"):
a header, a table of (number, byte count), then "name\\0" + shape bytes.
Pattern units in LIN are drawing units (for Moscow drawings, metres on the ground).
"""

import math
import re
import struct

# direction vectors for the 16 direction codes of a vector byte
_DIRS = [(1, 0), (1, .5), (1, 1), (.5, 1), (0, 1), (-.5, 1), (-1, 1), (-1, .5),
         (-1, 0), (-1, -.5), (-1, -1), (-.5, -1), (0, -1), (.5, -1), (1, -1), (1, -.5)]


def _s8(b):
    return b - 256 if b > 127 else b


def read_shx(data):
    """Bytes of a shape file → {name: {"no": number, "paths": [[[x, y], ...], ...]}}."""
    head = data.index(b"\x1a") + 1
    if not data.startswith(b"AutoCAD-86 shapes"):
        raise ValueError("not an AutoCAD shape file (.shx)")
    _first, _last, count = struct.unpack_from("<HHH", data, head)
    index = [struct.unpack_from("<HH", data, head + 6 + 4 * k) for k in range(count)]
    pos, raw = head + 6 + 4 * count, {}
    for number, size in index:
        chunk = data[pos:pos + size]
        pos += size
        nul = chunk.index(0)
        raw[number] = (chunk[:nul].decode("latin-1"), chunk[nul + 1:])
    out = {}
    for number, (name, spec) in raw.items():
        if name:
            out[name] = {"no": number, "paths": _draw(spec, raw)}
    return out


def _draw(spec, raw, depth=0):
    paths, cur = [], None
    x = y = 0.0
    scale, pen, stack = 1.0, True, []

    def move(dx, dy):
        nonlocal x, y, cur
        x, y = x + dx * scale, y + dy * scale
        if pen:
            if cur is None:
                cur = [[x - dx * scale, y - dy * scale]]
                paths.append(cur)
            cur.append([x, y])

    def arc(cx, cy, r, a0, a1):
        n = max(4, int(abs(a1 - a0) / (math.pi / 16)) + 1)
        for k in range(1, n + 1):
            a = a0 + (a1 - a0) * k / n
            nx, ny = cx + r * math.cos(a), cy + r * math.sin(a)
            move((nx - x) / scale, (ny - y) / scale)

    i = 0
    while i < len(spec):
        c = spec[i]
        i += 1
        if c == 0:
            break
        elif c == 1:
            pen, cur = True, None
        elif c == 2:
            pen, cur = False, None
        elif c == 3:
            scale /= spec[i]; i += 1
        elif c == 4:
            scale *= spec[i]; i += 1
        elif c == 5:
            stack.append((x, y))
        elif c == 6:
            x, y = stack.pop() if stack else (x, y)
            cur = None
        elif c == 7:                                  # subshape
            sub = raw.get(spec[i]); i += 1
            if sub and depth < 8:
                for p in _draw(sub[1], raw, depth + 1):
                    paths.append([[x + px * scale, y + py * scale] for px, py in p])
        elif c == 8:
            move(_s8(spec[i]), _s8(spec[i + 1])); i += 2
        elif c == 9:
            while True:
                dx, dy = _s8(spec[i]), _s8(spec[i + 1]); i += 2
                if dx == 0 and dy == 0:
                    break
                move(dx, dy)
        elif c == 10:                                 # octant arc
            r, oc = spec[i] * scale, spec[i + 1]; i += 2
            ccw = oc < 128
            start, n = (oc >> 4) & 7, (oc & 7) or 8
            a0 = start * math.pi / 4
            a1 = a0 + (n * math.pi / 4) * (1 if ccw else -1)
            cx, cy = x - r * math.cos(a0), y - r * math.sin(a0)
            arc(cx, cy, r, a0, a1)
        elif c == 11:                                 # fractional arc
            so, eo, rh, rl, oc = spec[i:i + 5]; i += 5
            r = (rh * 256 + rl) * scale
            ccw = oc < 128
            start, n = (oc >> 4) & 7, (oc & 7) or 8
            sgn = 1 if ccw else -1
            a0 = start * math.pi / 4 + sgn * so / 256 * math.pi / 4
            a1 = start * math.pi / 4 + sgn * ((n - 1) * math.pi / 4 + (eo / 256 * math.pi / 4 if eo else math.pi / 4))
            cx, cy = x - r * math.cos(a0), y - r * math.sin(a0)
            arc(cx, cy, r, a0, a1)
        elif c in (12, 13):                           # bulge arcs
            while True:
                dx, dy = _s8(spec[i]), _s8(spec[i + 1]); i += 2
                if c == 13 and dx == 0 and dy == 0:
                    break
                bulge = _s8(spec[i]) / 127.0; i += 1
                _bulge(move, dx, dy, bulge)
                if c == 12:
                    break
        elif c == 14:                                 # vertical-text flag: skip the next command
            i += 1
        else:
            length, d = c >> 4, c & 15
            dx, dy = _DIRS[d]
            move(dx * length, dy * length)
    return [p for p in paths if len(p) > 1]


def _bulge(move, dx, dy, bulge):
    if abs(bulge) < 1e-9:
        move(dx, dy)
        return
    # arc from the current point (0,0) to (dx,dy); theta > 0 is counter-clockwise
    chord = math.hypot(dx, dy)
    theta = 4 * math.atan(bulge)
    rad = chord / (2 * abs(math.sin(theta / 2)))
    off = (chord / 2) / math.tan(theta / 2)
    cx, cy = dx / 2 - dy / chord * off, dy / 2 + dx / chord * off
    a0 = math.atan2(-cy, -cx)
    n = max(4, int(abs(theta) / (math.pi / 16)) + 1)
    px = py = 0.0
    for k in range(1, n + 1):
        a = a0 + theta * k / n
        qx, qy = cx + rad * math.cos(a), cy + rad * math.sin(a)
        move(qx - px, qy - py)
        px, py = qx, qy


_ELEM = re.compile(r"\[[^\]]*\]|[^,\[\]]+")


def read_lin(text):
    """Text of a .lin file → {name: {"desc", "pattern": [...], "length"}}.

    Pattern elements: {"d": length} (>0 dash, <0 gap, 0 dot) or
    {"shape": NAME, "file", "s", "r", "x", "y", "abs"} or {"text": "...", "style", ...}."""
    out, name, desc = {}, None, ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("*"):
            head = line[1:].split(",", 1)
            name, desc = head[0].strip(), (head[1].strip() if len(head) > 1 else "")
            continue
        if name and line[:1].upper() == "A":
            pattern = []
            for tok in _ELEM.findall(line[line.index(",") + 1:] if "," in line else ""):
                tok = tok.strip()
                if not tok:
                    continue
                if tok.startswith("["):
                    pattern.append(_complex(tok[1:-1]))
                else:
                    try:
                        pattern.append({"d": float(tok)})
                    except ValueError:
                        pass
            out[name] = {"desc": desc, "pattern": pattern,
                         "length": sum(abs(e["d"]) for e in pattern if "d" in e)}
            name = None
    return out


def _complex(body):
    parts = [p.strip() for p in body.split(",")]
    el = {"s": 1.0, "r": 0.0, "x": 0.0, "y": 0.0, "abs": False}
    if parts[0].startswith('"'):
        el.update(text=parts[0].strip('"'), style=parts[1] if len(parts) > 1 else "STANDARD")
    else:
        el.update(shape=parts[0], file=parts[1].lower() if len(parts) > 1 else "")
    for p in parts[2:]:
        if "=" not in p:
            continue
        k, v = (s.strip().lower() for s in p.split("=", 1))
        try:
            v = float(v)
        except ValueError:
            continue
        if k in ("r", "u"):
            el["r"] = v
        elif k == "a":
            el["r"], el["abs"] = v, True
        elif k in ("s", "x", "y"):
            el[k] = v
    return el


LGR_NAME = re.compile(r"^L(\d\d)s(\d\d)([bts])$", re.I)


def lgr_index(linetypes):
    """{code: {family: {"s"|"b"|"t": name}}} for Moscow names like L00s16b."""
    idx = {}
    for name in linetypes:
        m = LGR_NAME.match(name)
        if m:
            fam, code, side = m.group(1), int(m.group(2)), m.group(3).lower()
            idx.setdefault(code, {}).setdefault(fam, {})[side] = name
    return idx


def linetype_for(idx, code, sign, family="00"):
    """LineCode ±code → linetype name. «+» = the object lies to the right of the line
    direction → variant b; «−» → t; a variant without a side (s) wins when it exists.
    Checked on real ГИС ОГД data: +1 right 203 vs 58, −1 left 168 vs 36."""
    fam = idx.get(code, {}).get(family) or next(iter(idx.get(code, {}).values()), {})
    return fam.get("s") or fam.get("b" if sign > 0 else "t") or fam.get("t" if sign > 0 else "b")


_CARRIERS = range(1, 7)   # codes whose line carries other signs: L01s16b = code 16 on red line 01


def _get(idx, code, fam, sign):
    f = idx.get(code, {}).get(fam)
    if not f:
        return None
    return f.get("s") or f.get("b" if sign > 0 else "t")


def linetypes_for_codes(pairs, linetypes, idx=None):
    """LineCode pairs [(code, sign), ...] → names of linetypes to draw.

    Naming in REDLN97: L00sNNx — code NN alone; LCCsNNx — code NN on the carrier
    line CC (01 red line of УДС, 02 ТОП, 04 ОДМС, 06 railway right-of-way …);
    LAAxBBy — two codes without a carrier, each with its own side.
    «+» — the object lies to the right of the line → b, «−» → t."""
    idx = idx if idx is not None else lgr_index(linetypes)
    upper = {n.upper(): n for n in linetypes}
    pairs = [(c, s) for c, s in pairs if c in idx]     # codes without a REDLN97 linetype: see missing_codes()
    carriers = [(c, s) for c, s in pairs if c in _CARRIERS and c in idx]
    others = [(c, s) for c, s in pairs if (c, s) not in carriers]
    if not others:
        return [n for n in (_get(idx, c, "00", s) for c, s in carriers) if n]
    carrier = carriers[0][0] if carriers else None
    side = lambda s: "B" if s > 0 else "T"
    if carrier is None and len(others) == 2:
        (a, sa), (b, sb) = others
        for x, y in (((a, sa), (b, sb)), ((b, sb), (a, sa))):
            n = upper.get(f"L{x[0]:02d}{side(x[1])}{y[0]:02d}{side(y[1])}")
            if n:
                return [n]
    out = []
    for c, s in others:
        n = (_get(idx, c, f"{carrier:02d}", s) if carrier else None) or _get(idx, c, "00", s)
        if n:
            out.append(n)
    if carrier and not any(n.upper().startswith(f"L{carrier:02d}S") for n in out):
        n = _get(idx, carrier, "00", carriers[0][1])
        if n:
            out.insert(0, n)
    return out


def missing_codes(pairs, linetypes, idx=None):
    """Codes that REDLN97 has no linetype for (they are drawn by the ЛГР library instead)."""
    idx = idx if idx is not None else lgr_index(linetypes)
    return [(c, s) for c, s in pairs if c not in idx]


def parse_line_codes(value):
    """ГИС ОГД LineCode «1,-29» → [(1, 1), (29, -1)]. Same rule as apps/studio (legacy copy there)."""
    out, seen = [], set()
    for part in str(value or "").split(","):
        try:
            n = int(float(part))
        except ValueError:
            continue
        if n and abs(n) not in seen:
            seen.add(abs(n))
            out.append((abs(n), 1 if n > 0 else -1))
    return out
