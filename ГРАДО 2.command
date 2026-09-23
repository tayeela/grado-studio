#!/bin/bash
# ГРАДО 2 on macOS without an installer: double-click. The first start creates ~/.grado2/venv and installs
# apps/grado2/requirements.txt (needs internet once); later starts open the browser in a few seconds.
cd "$(dirname "$0")" || exit 1
VENV="$HOME/.grado2/venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "Первый запуск: готовлю окружение ГРАДО 2 в $VENV…"
  python3 -m venv "$VENV" || { echo "Нужен Python 3.10+ с python.org"; read -r; exit 1; }
fi
"$VENV/bin/python" -m pip install -q --disable-pip-version-check -r apps/grado2/requirements.txt
exec "$VENV/bin/python" apps/grado2/server.py
