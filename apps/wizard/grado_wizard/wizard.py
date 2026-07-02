"""Мастер территории: граница → проект → ТЭП → альбом АГК.

Сценарий «этап 1» архитектуры: рисуешь (или подаёшь) границу — получаешь
проект с опорными слоями, ТЭП из геометрии и альбом в презентационном
стиле АГК. В продукте слои приходят из сервиса данных; эталон наполняет
их генератором territory.build_project.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parents[3]
for mod in ("model", "compute", "reactive", "render", "geom", "layout",
            "connectors"):
    p = str(ROOT / "core" / mod)
    if p not in sys.path:
        sys.path.insert(0, p)

from grado_compute.engine import Engine  # noqa: E402
from grado_layout import Document, render_document_pdf  # noqa: E402
from grado_model.tep_bridge import apply_to_engine  # noqa: E402
from grado_render import StyleSet  # noqa: E402

from .sheets import (apo_sheet, base_plan_sheet, location_sheet,  # noqa: E402
                     tep_summary_sheet, title_sheet)
from .territory import build_project, demo_boundary  # noqa: E402

PRESET = ROOT / "core" / "compute" / "grado_compute" / "presets" / "moscow_krt.json"


class TerritoryWizard:
    def __init__(self, name, boundary=None, params=None, org="ГРАДО",
                 city_year="Москва / 2026"):
        self.name = name
        self.boundary = boundary or demo_boundary()
        self.params = params or {}
        self.org = org
        self.city_year = city_year

    def run(self, project_path):
        """Возвращает (project, engine, document)."""
        project = build_project(project_path, self.name, self.boundary)
        engine = Engine.from_file(PRESET)
        apply_to_engine(project, engine)  # terr_area/restrict_area из геометрии
        if self.params:
            engine.set_inputs(**self.params)

        doc = Document(self.name,
                       meta={"org": self.org, "stage": "АГК"})
        doc.styles = StyleSet()
        area = engine.value("terr_area")
        doc.pages = [
            title_sheet(doc, org=self.org, city_year=self.city_year),
            location_sheet(doc, project, area, page_no=2),
            base_plan_sheet(doc, project, page_no=3),
            apo_sheet(doc, project, engine, page_no=4),
            tep_summary_sheet(doc, engine, page_no=5),
        ]
        doc.sheet_titles = ["", "Расположение", "Опорный план",
                            "Схема АПО", "Сводные ТЭП"]
        return project, engine, doc

    def render_pdf(self, project, engine, doc):
        return render_document_pdf(doc, project, styles=doc.styles,
                                   engine=engine)
