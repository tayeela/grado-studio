"""
py2app setup for macOS app bundle (ГРАДО Студия).

Usage (requires py2app installed):
  python3 packaging/py2app_setup.py py2app

This bundles the Python studio + server + cores. Produces dist/ГРАДО Студия.app
Supports opening .grado files (via CLI arg and Info.plist).

To build icon: use iconutil or sips to make AppIcon.icns from PNG, place in Resources or set iconfile.
Run the .app or from terminal: open "dist/ГРАДО Студия.app" --args /path/to/project.grado
"""

import json
import sys
from pathlib import Path

from setuptools import setup

sys.path.insert(0, str(Path(__file__).parent))
from build_support import data_files_for_tree  # noqa: E402

ROOT = Path(__file__).parents[1]
for module_dir in ("model", "compute", "reactive", "render", "geom", "layout",
                   "connectors"):
    sys.path.insert(0, str(ROOT / "core" / module_dir))
sys.path.insert(0, str(ROOT / "apps" / "wizard"))
VERSION = json.loads(
    (ROOT / 'apps/studio/web/version.json').read_text(encoding='utf-8'))
ICON = ROOT / "packaging" / "AppIcon.icns"

APP = ['apps/studio/server.py']
DATA_FILES = (
    data_files_for_tree(ROOT, 'apps/studio/web', 'web') +
    data_files_for_tree(ROOT, 'core', 'core') +
    data_files_for_tree(ROOT, 'apps/calc-web', 'calc-web')
)
PLIST = {
    'CFBundleName': 'ГРАДО Студия',
    'CFBundleDisplayName': 'ГРАДО Студия',
    'CFBundleIdentifier': 'tech.tailink.grado-studio',
    'CFBundleVersion': VERSION['bundle_version'],
    'CFBundleShortVersionString': VERSION['bundle_short_version'],
    'NSHumanReadableCopyright': '© 2026 ГРАДО',
    'CFBundleDocumentTypes': [
        {
            'CFBundleTypeName': 'ГРАДО проект',
            'CFBundleTypeExtensions': ['grado'],
            'CFBundleTypeRole': 'Editor',
            'LSHandlerRank': 'Owner',
            'LSItemContentTypes': ['tech.tailink.grado'],
        }
    ],
    'UTExportedTypeDeclarations': [
        {
            'UTTypeIdentifier': 'tech.tailink.grado',
            'UTTypeConformsTo': ['public.data'],
            'UTTypeDescription': 'ГРАДО проект',
            'UTTypeTagSpecification': {'public.filename-extension': ['grado']},
        }
    ],
}
if ICON.exists():
    PLIST['CFBundleIconFile'] = 'AppIcon'
    PLIST['CFBundleDocumentTypes'][0]['CFBundleTypeIconFile'] = 'AppIcon'
OPTIONS = {
    'argv_emulation': True,
    'packages': ['grado_compute', 'grado_geom', 'grado_model', 'grado_render', 'grado_layout', 'grado_reactive', 'grado_connectors', 'grado_wizard'],
    'includes': ['studio_core'],
    'excludes': ['tkinter', 'PyQt5', 'wx', 'IPython', 'ipykernel', 'jupyter',
                 'notebook', 'pytest', 'numpy.tests', 'test', 'packaging',
                 'setuptools', 'pkg_resources'],
    'plist': PLIST,
}
if ICON.exists():
    OPTIONS['iconfile'] = str(ICON)

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
