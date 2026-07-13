"""Сформировать version resource PyInstaller из общего version.json."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]


def build_version_file(output=None):
    manifest = json.loads(
        (ROOT / "apps/studio/web/version.json").read_text(encoding="utf-8")
    )
    version = manifest["version"]
    numeric = (0, 9, 0, int(manifest["bundle_version"]))
    output = Path(output or ROOT / "build/windows_version_info.txt")
    output.parent.mkdir(parents=True, exist_ok=True)
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={numeric}, prodvers={numeric}, mask=0x3f,
    flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'GRADO'),
    StringStruct('FileDescription', 'GRADO Studio'),
    StringStruct('FileVersion', '{version}'),
    StringStruct('InternalName', 'GRADO Studio'),
    StringStruct('LegalCopyright', 'Copyright 2026 GRADO'),
    StringStruct('OriginalFilename', 'GRADO Studio.exe'),
    StringStruct('ProductName', 'GRADO Studio'),
    StringStruct('ProductVersion', '{version}')
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
"""
    output.write_text(text, encoding="utf-8")
    return output


if __name__ == "__main__":
    print(build_version_file(sys.argv[1] if len(sys.argv) > 1 else None))
