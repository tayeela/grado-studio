# Журнал сервера (gravlog.py) в тестах — во временную папку: настоящие ~/.grado2/server.log и stderr владельца
# тесты не трогают. Ставится до импорта server/print_io/ogd_all: gravlog читает GRADO2_LOG при первой записи.
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# unittest-режим (gate без pytest, e2e) conftest не читает — ту же защиту ставит сам test_server.py при импорте
os.environ.setdefault("GRADO2_LOG", str(Path(tempfile.mkdtemp(prefix="grado2-log-")) / "server.log"))
atexit.register(shutil.rmtree, str(Path(os.environ["GRADO2_LOG"]).parent), ignore_errors=True)   # папка не копится в /tmp
