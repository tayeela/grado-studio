#!/usr/bin/env bash
# Напоминание после коммита или слияния в main: сайт grado.tailink.tech с Mac больше не выкладывается (с 08.10.2026, задача #73).
# Его обновляет сам сервер msk: таймер grado-pull раз в 5 минут забирает main с GitHub (tools/server_pull/README.md).
# Вызывают хуки post-commit и post-merge. Ничего не отправляет и коммит не отменяет.
[ "$(git symbolic-ref --short -q HEAD)" = main ] || exit 0
echo "ГРАДО: сайт grado.tailink.tech обновит сам сервер в течение 5 минут после того, как main окажется на GitHub (с Mac не выкладывается)"
exit 0
