#!/bin/bash
# ГРАДО Студия — запуск двойным кликом из Finder.
cd "$(dirname "$0")"
# если сервер уже работает — просто открыть браузер
if curl -s --max-time 1 -o /dev/null http://127.0.0.1:8643/; then
    open "http://localhost:8643"
    exit 0
fi
exec python3 apps/studio/server.py 8643 --open
