"""
py2app setup for macOS app bundle (ГРАДО Студия).

Usage (requires py2app installed):
  python3 packaging/py2app_setup.py py2app

This bundles the Python studio + server + cores. Produces dist/ГРАДО Студия.app
Supports opening .grado files (via CLI arg and Info.plist).

To build icon: use iconutil or sips to make AppIcon.icns from PNG, place in Resources or set iconfile.
Run the .app or from terminal: open dist/ГРАДО\ Студия.app --args /path/to/project.grado
"""

from setuptools import setup

APP = ['apps/studio/server.py']
DATA_FILES = [
    'apps/studio/web',
    'core',
    'apps/calc-web',
    'core/compute/grado_compute/presets',
    'core/render/grado_render/styles',
    'apps/studio/style_overrides.json',
]
OPTIONS = {
    'argv_emulation': True,
    'packages': ['grado_compute', 'grado_geom', 'grado_model', 'grado_render', 'grado_layout', 'grado_reactive', 'grado_connectors', 'grado_wizard'],
    'includes': ['engine', 'expressions', 'studio_core'],
    'excludes': ['tkinter', 'PyQt5', 'wx'],
    'plist': {
        'CFBundleName': 'ГРАДО Студия',
        'CFBundleDisplayName': 'ГРАДО Студия',
        'CFBundleIdentifier': 'tech.tailink.grado-studio',
        'CFBundleVersion': '0.49',
        'CFBundleShortVersionString': '0.49',
        'NSHumanReadableCopyright': '© 2026 ГРАДО',
        'CFBundleIconFile': 'AppIcon',  # place grado.icns as AppIcon.icns in Resources
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeName': 'ГРАДО проект',
                'CFBundleTypeExtensions': ['grado'],
                'CFBundleTypeIconFile': 'AppIcon',
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
                'UTTypeTagSpecification': {
                    'public.filename-extension': ['grado'],
                }
            }
        ],
    },
    'iconfile': None,  # set to path to .icns if available
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
