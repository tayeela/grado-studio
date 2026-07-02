"""Демо реактивного ядра: правки → живой ТЭП → undo → ветки.

    python3 -m grado_reactive demo /путь/демо.grado
"""

import sys
from pathlib import Path

CORE = Path(__file__).parents[2]
for mod in ("model", "compute"):
    sys.path.insert(0, str(CORE / mod))

from grado_compute.engine import Engine  # noqa: E402
from grado_model import Project  # noqa: E402

from .session import Session  # noqa: E402
from .tep_link import TepLink  # noqa: E402

PRESET = CORE / "compute" / "grado_compute" / "presets" / "moscow_krt.json"


def rect(x0, y0, w, h):
    return {"type": "Polygon", "coordinates": [[
        [x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h], [x0, y0]]]}


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 2 or argv[0] != "demo":
        print(__doc__)
        return 2
    path = argv[1]

    project = Project.create(path, "Демо реактивного ядра")
    project.add_layer("terr.boundary")
    project.add_layer("terr.restrict")
    session = Session(project)
    engine = Engine.from_file(PRESET)
    link = TepLink(session, engine)

    def report(step):
        print(f"{step:<58} население {engine.display('population'):>5} чел  "
              f"(расч. терр. {engine.value('calc_area'):.4g} га, ветка {session.branch})")

    session.insert_feature("terr.boundary", rect(413000, 6178000, 500, 300),
                           attrs={"name": "Демо"}, title="граница 15 га")
    rid = session.insert_feature("terr.restrict", rect(413000, 6178000, 200, 100),
                                 source="nspd", title="ЗОУИТ 2 га")
    report("1. Опорный план: граница 15 га, ограничения 2 га")

    session.update_feature("terr.restrict", rid, geom=rect(413000, 6178000, 100, 100),
                           title="уточнение ЗОУИТ до 1 га")
    report("2. Правка геометрии: ограничения ужаты до 1 га")

    session.undo()
    report("3. Undo: ограничения снова 2 га")

    session.create_branch("вариант-Б")
    session.checkout("вариант-Б")
    session.insert_feature("terr.restrict", rect(413300, 6178000, 100, 100),
                           title="доп. ограничение 1 га")
    report("4. Ветка «вариант-Б»: +1 га ограничений")

    session.checkout("main")
    report("5. Обратно в main: состояние восстановлено из журнала")

    session.checkout("вариант-Б")
    report("6. Снова «вариант-Б»: правки варианта на месте")

    print("\nЖурнал (main):")
    session.checkout("main")
    for e in session.log():
        mark = "*" if e["applied"] else " "
        print(f"  {mark} #{e['seq']} {e['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
