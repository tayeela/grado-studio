"""CLI: расчёт ТЭП по пресету.

Примеры:
    python3 -m grado_compute
    python3 -m grado_compute --set terr_area=15 --set restrict_area=2.5
    python3 -m grado_compute --preset path/to/preset.json --json
"""

import argparse
import json
import sys
from pathlib import Path

from .engine import Engine

DEFAULT_PRESET = Path(__file__).parent / "presets" / "moscow_krt.json"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="grado_compute", description="ТЭП-движок ГРАДО")
    parser.add_argument("--preset", default=str(DEFAULT_PRESET), help="путь к JSON-пресету")
    parser.add_argument("--set", dest="overrides", action="append", default=[],
                        metavar="ID=VALUE", help="переопределить входной параметр")
    parser.add_argument("--json", action="store_true", help="вывод в JSON")
    args = parser.parse_args(argv)

    engine = Engine.from_file(args.preset)
    overrides = {}
    for item in args.overrides:
        key, _, raw = item.partition("=")
        if not _:
            parser.error(f"ожидается ID=VALUE, получено {item!r}")
        overrides[key.strip()] = float(raw)
    if overrides:
        engine.set_inputs(**overrides)

    if args.json:
        json.dump(engine.results(), sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0

    print(engine.title)
    print()
    print("Входные параметры:")
    for i in engine.inputs.values():
        unit = f" {i['unit']}" if i.get("unit") else ""
        print(f"  {i['title']}: {engine.value(i['id'])}{unit}")
    group = None
    for row in engine.results():
        if row["group"] != group:
            group = row["group"]
            print(f"\n{group}:")
        unit = f" {row['unit']}" if row["unit"] else ""
        print(f"  {row['title']}: {row['value']}{unit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
