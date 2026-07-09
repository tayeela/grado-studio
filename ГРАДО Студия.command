#!/bin/bash
# ГРАДО Студия — запуск двойным кликом из Finder (macOS app-like).
# Для полноценного .app: python packaging/py2app_setup.py py2app (см. packaging/).
# Двойной клик .command или .app открывает браузер; .grado arg → авто load (CLI + /api/initial-grado).
# В .app: перетащить .grado на иконку или "Open With".
cd "$(dirname "$0")"
PORT=8643
URL="http://localhost:$PORT"
# если сервер уже работает — открыть (и попытаться загрузить файл если передан)
if curl -s --max-time 1 -o /dev/null "$URL"; then
    if [ -n "$1" ] && [[ "$1" == *.grado ]]; then
        # простой способ: открыть и пользователь может загрузить вручную
        open "$URL"
        osascript -e "tell application \"Safari\" to activate" 2>/dev/null || true
    else
        open "$URL"
    fi
    exit 0
fi
# запуск сервера в фоне + открыть
if [ -n "$1" ] && [[ "$1" == *.grado ]]; then
    python3 apps/studio/server.py "$PORT" "$1" --open &
else
    python3 apps/studio/server.py "$PORT" --open &
fi
sleep 1
open "$URL"
if [ -n "$1" ] && [[ "$1" == *.grado ]]; then
    echo "Открыт проект: $1 (должен загрузиться автоматически)"
fi
wait
