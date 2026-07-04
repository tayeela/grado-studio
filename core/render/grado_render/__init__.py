"""grado_render — рендер «ГРАДО Студии» (эталонная реализация).

Одна стилевая машина (scene.build_ops) — два бэкенда: SVG (экранный
прокси GPU-рендера) и собственный PDF-писатель (вектор, кириллица через
встраиваемый TrueType). WYSIWYG: оба исполняют один список операций.
"""

from .backend_pdf import PdfBackend, jpeg_info
from .backend_svg import render_svg
from .scene import MapTransform, build_ops, project_extent
from .style import Style, StyleSet, hex_to_rgb, load_library
from .ttf import Font, FontError, find_font

__all__ = ["PdfBackend", "jpeg_info", "render_svg", "build_ops",
           "project_extent", "MapTransform", "Style", "StyleSet",
           "hex_to_rgb", "load_library", "Font", "FontError", "find_font"]
__version__ = "0.1.0"
