"""Точка входа автономной Windows-сборки ГРАДО Студии."""

import os
import sys
import traceback
from pathlib import Path


def _resource_root():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).parents[1]


def _data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    return Path(base or Path.home() / "AppData" / "Local") / "GRADO Studio"


def _report_crash(error):
    data = _data_dir()
    data.mkdir(parents=True, exist_ok=True)
    log = data / "startup-error.log"
    log.write_text(traceback.format_exc(), encoding="utf-8")
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                f"ГРАДО Студия не запустилась.\n\n{error}\n\nПодробности: {log}",
                "ГРАДО Студия",
                0x10,
            )
        except Exception:
            pass


def main():
    root = _resource_root()
    os.environ.setdefault("RESOURCEPATH", str(root))
    os.environ.setdefault("GRADO_STUDIO_DATA_DIR", str(_data_dir()))
    try:
        import server
        return server.main()
    except Exception as error:
        _report_crash(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
