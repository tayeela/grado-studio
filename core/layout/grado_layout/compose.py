"""Сборка документа: листы → операции → PDF (печать) или SVG (экран).

Оба вывода собираются из одних и тех же операций фреймов.
"""

from grado_render import PdfBackend, StyleSet, render_svg


def _ctx(doc, project, styles, engine, page_no, sheet_title):
    return {"doc": doc, "project": project, "styles": styles or StyleSet(),
            "engine": engine, "page_no": str(page_no),
            "page_total": str(len(doc.pages)), "sheet_title": sheet_title}


def sheet_titles(doc):
    return getattr(doc, "sheet_titles", [""] * len(doc.pages))


def document_pages_ops(doc, project, styles=None, engine=None):
    titles = sheet_titles(doc)
    pages = []
    for i, page in enumerate(doc.pages, start=1):
        ctx = _ctx(doc, project, styles, engine, i, titles[i - 1])
        pages.append((page.size[0], page.size[1], page.ops(ctx)))
    return pages


def render_document_pdf(doc, project, styles=None, engine=None, font_path=None):
    pages = document_pages_ops(doc, project, styles, engine)
    return PdfBackend(font_path).render(pages)


def render_page_svg(doc, project, page_index=0, styles=None, engine=None):
    pages = document_pages_ops(doc, project, styles, engine)
    w, h, ops = pages[page_index]
    return render_svg(w, h, ops)
