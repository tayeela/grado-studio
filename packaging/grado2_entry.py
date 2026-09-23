"""Entry point of the packaged ГРАДО 2 (Windows .exe and macOS .app, PyInstaller).

Starts the local server (apps/grado2/server.py) and opens the browser. A crash at start is written to
the data folder and, on Windows, shown in a message box instead of a silently closing window.
"""

import os
import sys
import traceback
from pathlib import Path


def _data_dir():
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "GRADO2"
    return Path.home() / ".grado2"


def main():
    data = _data_dir()
    data.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None:                      # windowed build: no console, print() would fail
        log = open(data / "grado2.log", "a", encoding="utf-8")
        sys.stdout = sys.stderr = log
    try:
        import server
        server.main([])
    except SystemExit:
        raise
    except Exception as error:
        (data / "startup-error.log").write_text(traceback.format_exc(), encoding="utf-8")
        if sys.platform == "win32" and os.environ.get("GRADO2_NO_DIALOG") != "1":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, f"ГРАДО 2 не запустилась.\n\n{error}\n\nПодробности: {data / 'startup-error.log'}", "ГРАДО 2", 0x10)
            except Exception:
                pass
        raise


if __name__ == "__main__":
    main()
