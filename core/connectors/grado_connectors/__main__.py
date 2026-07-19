"""CLI сервиса данных.

    python3 -m grado_connectors ingest-nspd ЗАХВАТ.json --store DIR
    python3 -m grado_connectors ingest-gisogd ВЫГРУЗКА.zip --store DIR
    python3 -m grado_connectors fetch-fgistp --uin УИН --store DIR
    python3 -m grado_connectors list --store DIR
    python3 -m grado_connectors diff SID_A SID_B --store DIR
    python3 -m grado_connectors import SID --project П.grado --layer КОД \
        [--map атрибут=свойство,...] --store DIR
"""

import argparse
import sys
from pathlib import Path

CORE = Path(__file__).parents[2]
for mod in ("model", "compute", "reactive"):
    sys.path.insert(0, str(CORE / mod))

from .diff import diff as diff_snapshots  # noqa: E402
from .fgistp import FgistpConnector  # noqa: E402
from .gisogd import GisogdZip  # noqa: E402
from .importer import import_snapshot  # noqa: E402
from .nspd import NspdCapture  # noqa: E402
from .store import SnapshotStore  # noqa: E402


def _report_saved(store, sid):
    m = store.manifest(sid)
    print(f"Снимок {sid}: {m['count']} объектов, {m['fetched_at']}")
    for note in m["notes"]:
        print(f"  примечание: {note}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="grado_connectors", description="Сервис данных ГРАДО")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest-nspd")
    p.add_argument("path")
    p = sub.add_parser("ingest-gisogd")
    p.add_argument("path")
    p = sub.add_parser("fetch-fgistp")
    p.add_argument("--uin", required=True)
    p.add_argument("--geom-type", default=None)
    p.add_argument("--status", default=None,
                   help="1 существующие / 2 планируемые; пусто = оба")
    p.add_argument("--base-url", default=None)
    sub.add_parser("list")
    p = sub.add_parser("diff")
    p.add_argument("sid_a")
    p.add_argument("sid_b")
    p = sub.add_parser("import")
    p.add_argument("sid")
    p.add_argument("--project", required=True)
    p.add_argument("--layer", required=True)
    p.add_argument("--map", dest="attr_map", default=None)
    for name, sp in sub.choices.items():
        sp.add_argument("--store", required=True)

    args = parser.parse_args(argv)
    store = SnapshotStore(args.store)

    if args.cmd == "ingest-nspd":
        conn = NspdCapture()
        _report_saved(store, store.save(conn, conn.fetch(path=args.path)))
    elif args.cmd == "ingest-gisogd":
        conn = GisogdZip()
        _report_saved(store, store.save(conn, conn.fetch(args.path)))
    elif args.cmd == "fetch-fgistp":
        kw = {"base_url": args.base_url} if args.base_url else {}
        conn = FgistpConnector(**kw)
        result = conn.fetch(args.uin, geom_type=args.geom_type,
                            statuses=((args.status,) if args.status else ("1", "2")))
        _report_saved(store, store.save(conn, result))
    elif args.cmd == "list":
        for m in store.list():
            print(f"{m['id']}  {m['count']:>5} объектов  {m['fetched_at']}  {m['source_doc'] or ''}")
    elif args.cmd == "diff":
        d = diff_snapshots(store.features(args.sid_a), store.features(args.sid_b))
        for kind in ("added", "removed", "changed"):
            print(f"{kind}: {len(d[kind])}")
            for key in d[kind][:20]:
                print(f"  {key}")
    elif args.cmd == "import":
        from grado_model import Project  # noqa: E402
        from grado_reactive import Session  # noqa: E402
        attr_map = None
        if args.attr_map:
            attr_map = dict(pair.split("=", 1) for pair in args.attr_map.split(","))
        project = Project.open(args.project)
        n = import_snapshot(store, args.sid, project, Session(project),
                            args.layer, attr_map=attr_map)
        print(f"Импортировано {n} объектов в слой {args.layer} (одна запись журнала)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
