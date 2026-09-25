#!/usr/bin/env bash
# Автообновление сервера grado.tailink.tech: git-хуки post-commit и post-merge вызывают этот файл.
# Обновляет, только если мы на ветке main и с прошлой выкладки менялась программа (apps/grado2, core,
# docs/standards). Последний выложенный коммит — в .git/grado-deployed (общий для всех рабочих копий).
# Выкладку делает tools/deploy-server.sh (проверка версии и автооткат). Отключить разово: GRADO_NO_DEPLOY=1.
# Коммит хук не отменяет никогда: неудача выкладки — только предупреждение.
set -u
[ "${GRADO_NO_DEPLOY:-}" = 1 ] && exit 0
[ "$(git symbolic-ref --short -q HEAD)" = main ] || exit 0
top=$(git rev-parse --show-toplevel)
mark="$(git rev-parse --git-common-dir)/grado-deployed"
head=$(git rev-parse HEAD)
if [ -s "$mark" ] && git cat-file -e "$(cat "$mark")^{commit}" 2>/dev/null; then
  git diff --quiet "$(cat "$mark")" "$head" -- apps/grado2 core docs/standards && exit 0
fi
echo "ГРАДО: в main новая версия программы — обновляю grado.tailink.tech (отключить: GRADO_NO_DEPLOY=1)"
if "$top/tools/deploy-server.sh"; then
  echo "$head" > "$mark"
else
  echo "ГРАДО: сервер НЕ обновлён — на нём осталась прежняя версия; повторить: tools/deploy-server.sh" >&2
fi
exit 0
