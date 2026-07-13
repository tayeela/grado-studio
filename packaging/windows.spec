# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPEC).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))
from build_support import data_files_for_tree


MODULE_DIRS = ("model", "compute", "reactive", "render", "geom", "layout", "connectors")
PATHEX = [str(ROOT / "apps/studio"), str(ROOT / "apps/wizard")]
PATHEX += [str(ROOT / "core" / module) for module in MODULE_DIRS]

datas = []
for source, destination in (
    ("apps/studio/web", "web"),
    ("core", "core"),
    ("apps/calc-web", "apps/calc-web"),
):
    for target, files in data_files_for_tree(ROOT, source, destination):
        datas.extend((path, target) for path in files)
datas.append((
    str(ROOT / "apps/wizard/grado_wizard/album_templates.json"),
    "grado_wizard",
))

hiddenimports = ["server", "studio_core", "webhub"]
for package in (
    "grado_compute", "grado_geom", "grado_model", "grado_render",
    "grado_layout", "grado_reactive", "grado_connectors", "grado_wizard", "PIL",
):
    hiddenimports.extend(collect_submodules(package))

a = Analysis(
    [str(ROOT / "packaging/windows_entry.py")],
    pathex=PATHEX,
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "wx", "IPython", "pytest", "notebook"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ГРАДО Студия",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(ROOT / "packaging/AppIcon.ico"),
    version=str(ROOT / "build/windows_version_info.txt"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ГРАДО Студия",
)
