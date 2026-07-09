#!/bin/bash
# ГРАДО Студия — запуск двойным кликом из Finder (локально, только для вас).
#
# Что делает: находит Python 3, при первом запуске доустанавливает certifi
# (нужен для карты-подложки и загрузки данных по HTTPS), поднимает локальный
# сервер на http://localhost:8643 и открывает его в браузере ОДИН раз.
# Данные никуда не уходят — сервер слушает только этот компьютер.
#
# Перетащите файл .grado на иконку (или «Открыть с помощью») — проект
# откроется автоматически (если сервер ещё не был запущен).
#
# Первый запуск: macOS может спросить разрешение — правый клик по файлу →
# «Открыть» → «Открыть». Полноценный .app: packaging/py2app_setup.py.

cd "$(dirname "$0")" || exit 1
PORT=8643
URL="http://localhost:$PORT"
GRADO_ARG=""
if [ -n "$1" ] && [[ "$1" == *.grado ]]; then GRADO_ARG="$1"; fi

echo "════════════════════════════════════════════"
echo "  ГРАДО Студия — локальный запуск"
echo "════════════════════════════════════════════"

# --- 1. рабочий Python 3 --------------------------------------------------
PY=""
for cand in python3 /usr/local/bin/python3 /usr/bin/python3 \
            /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
    if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info>=(3,8) else 1)' 2>/dev/null; then
        PY="$cand"; break
    fi
done
if [ -z "$PY" ]; then
    echo ""
    echo "  ⚠  Не найден Python 3.8+."
    echo "     Установите его с https://www.python.org/downloads/ и запустите снова."
    echo ""
    echo "Окно можно закрыть."
    read -r _; exit 1
fi
echo "  Python: $("$PY" --version 2>&1)"

# --- 2. certifi (для HTTPS: подложка карты, НСПД, OSM) --------------------
# опционально: без него подложка/данные могут не грузиться на сборках
# python.org (нет доступа к системным сертификатам). Ставим тихо, не падаем.
if ! "$PY" -c 'import certifi' >/dev/null 2>&1; then
    echo "  Доустанавливаю компонент certifi (один раз)…"
    "$PY" -m pip install --user --quiet certifi >/dev/null 2>&1 \
        && echo "  certifi установлен." \
        || echo "  ⚠  certifi поставить не удалось — карта-подложка может не грузиться (не критично)."
fi

# --- 3. сервер уже работает? тогда просто открыть -------------------------
if curl -s --max-time 1 -o /dev/null "$URL" 2>/dev/null; then
    echo "  Сервер уже запущен — открываю браузер."
    [ -n "$GRADO_ARG" ] && echo "  (файл $GRADO_ARG откройте кнопкой «Открыть…» в студии)"
    open "$URL"
    echo ""
    echo "Готово. Это окно можно закрыть."
    exit 0
fi

# --- 4. старт сервера + ожидание готовности + одно открытие браузера ------
echo "  Запускаю сервер на $URL …"
if [ -n "$GRADO_ARG" ]; then
    "$PY" apps/studio/server.py "$PORT" "$GRADO_ARG" &
else
    "$PY" apps/studio/server.py "$PORT" &
fi
SERVER_PID=$!

# останавливаем сервер при закрытии окна / Ctrl-C
trap 'echo ""; echo "Останавливаю сервер…"; kill $SERVER_PID 2>/dev/null; exit 0' INT TERM

# ждём, пока сервер начнёт отвечать (до ~15 с), затем открываем браузер один раз
opened=0
for _ in $(seq 1 30); do
    if curl -s --max-time 1 -o /dev/null "$URL" 2>/dev/null; then
        open "$URL"; opened=1; break
    fi
    # сервер умер на старте (порт занят другим процессом, ошибка импорта)?
    kill -0 $SERVER_PID 2>/dev/null || break
    sleep 0.5
done

if [ "$opened" -eq 0 ]; then
    echo ""
    echo "  ⚠  Сервер не ответил. Возможно, порт $PORT занят другой программой."
    echo "     Закройте её и запустите снова."
    kill $SERVER_PID 2>/dev/null
    echo ""
    echo "Окно можно закрыть."
    read -r _; exit 1
fi

echo ""
echo "  ✓ Студия открыта в браузере: $URL"
[ -n "$GRADO_ARG" ] && echo "  ✓ Проект $GRADO_ARG загружается автоматически."
echo ""
echo "  Чтобы завершить работу — закройте это окно (или нажмите Ctrl-C)."
echo "  Пока окно открыто, студия работает."

# держим окно и сервер живыми
wait $SERVER_PID
