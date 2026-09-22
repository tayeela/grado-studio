"""Generator: Moscow red-line standard (REDLN97.LIN + RED_LNS.SHX) → styles/redln97.json.

Sources are in docs/standards/redln97 (as received from the owner, LIN in cp866).
The JSON is generated; do not edit it by hand (repo CLAUDE.md, rule 2).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core/render"))
from grado_render.acad_lin import lgr_index, read_lin, read_shx  # noqa: E402

SRC = ROOT / "docs/standards/redln97"
OUT = ROOT / "core/render/grado_render/styles/redln97.json"


def build():
    shapes = read_shx((SRC / "RED_LNS.SHX").read_bytes())
    lin = read_lin((SRC / "REDLN97.LIN").read_bytes().decode("cp866"))
    r = lambda v: round(v, 4)
    return {
        "source": "REDLN97.LIN (13.03.2003, 25.11.2005) + RED_LNS.SHX; units — drawing units (metres)",
        "shapes": {n: {"no": s["no"], "paths": [[[r(x), r(y)] for x, y in p] for p in s["paths"]]}
                   for n, s in sorted(shapes.items())},
        "linetypes": lin,
        "lgr": {str(k): v for k, v in sorted(lgr_index(lin).items())},
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(OUT)
