# -*- mode: python ; coding: utf-8 -*-
# ГРАДО 2 — one folder build for Windows (.exe) and macOS (.app):  pyinstaller --noconfirm --clean packaging/grado2.spec
import json
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPEC).resolve().parents[1]
APP = ROOT / "apps/grado2"
VERSION = json.loads((APP / "web/version.json").read_text("utf-8"))["version"]
PATHEX = [str(APP)] + [str(ROOT / "core" / m) for m in ("connectors", "compute", "render", "layout", "geom")]
sys.path[:0] = PATHEX                       # collect_* ниже импортируют пакеты ядра

datas = [(str(APP / "web"), "web"),
         (str(ROOT / "core/render/grado_render/styles"), "core/render/grado_render/styles"),
         (str(ROOT / "core/compute/grado_compute/presets"), "core/compute/grado_compute/presets"),
         (str(ROOT / "core/compute/grado_compute/regulations"), "core/compute/grado_compute/regulations"),
         (str(ROOT / "docs/standards/redln97"), "docs/standards/redln97"),
         (str(ROOT / "docs/standards/admin"), "docs/standards/admin"),           # районы для долей площади (server.district_shares)
         (str(ROOT / "docs/standards/albums/pptkrt-header.jpg"), "docs/standards/albums")]   # шапка слайдов альбома (album_io)
datas += collect_data_files("certifi") + collect_data_files("ezdxf") + collect_data_files("grado_compute") + collect_data_files("grado_render")

hiddenimports = ["server", "dxf_io", "file_io", "print_io", "export_io"]
for package in ("grado_connectors", "grado_compute", "grado_render", "grado_layout", "grado_geom", "ezdxf", "PIL", "shapely"):
    hiddenimports += collect_submodules(package)

a = Analysis([str(ROOT / "packaging/grado2_entry.py")], pathex=PATHEX, binaries=[], datas=datas, hiddenimports=hiddenimports,
             hookspath=[], runtime_hooks=[], excludes=["tkinter", "PyQt5", "wx", "IPython", "pytest", "notebook", "matplotlib"],
             noarchive=False, optimize=1)
pyz = PYZ(a.pure)
icon = str(ROOT / ("packaging/AppIcon.ico" if sys.platform == "win32" else "packaging/AppIcon.icns"))
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ГРАДО 2", debug=False, strip=False, upx=False,
          console=False, icon=icon)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ГРАДО 2")
if sys.platform == "darwin":
    app = BUNDLE(coll, name="ГРАДО 2.app", icon=icon, bundle_identifier="ru.grado.grado2",
                 info_plist={"CFBundleShortVersionString": VERSION, "CFBundleVersion": VERSION, "NSHighResolutionCapable": True,
                             "CFBundleDocumentTypes": [{"CFBundleTypeName": "Проект ГРАДО 2", "CFBundleTypeExtensions": ["grado2"], "CFBundleTypeRole": "Editor"}]})
