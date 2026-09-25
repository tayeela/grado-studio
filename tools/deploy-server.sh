#!/usr/bin/env bash
# Обновить ГРАДО 2 на сервере grado.tailink.tech одной командой:  tools/deploy-server.sh
#
# Отправляет последний коммит (не рабочие правки) на хост AEZA-GRADO, ставит его рядом с работающей версией,
# переключает каталог и перезапускает службу grado. Если после перезапуска /api/health не отвечает новой версией —
# сам возвращает прежнюю и завершается с ошибкой. Хост с Mac напрямую недоступен: путь Mac → vps (AEZA-US) → grado
# (ssh-алиас на AEZA-US идёт через msk). Установка сервера и откат — в ЛОГе taiLink за 25.09.2026.
set -euo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

REV=$(git rev-parse --short HEAD)
VER=$(python3 -c 'import json;print(json.load(open("apps/grado2/web/version.json"))["version"])')
if [ -n "$(git status --porcelain -- apps/grado2 core docs/standards)" ]; then
  echo "Внимание: есть незакоммиченные правки — на сервер уйдёт только коммит $REV (версия $VER)."
fi
echo "Отправляю $REV (версия $VER) на grado.tailink.tech…"

# 1. код коммита — в /opt/grado/app.new
git archive --format=tar HEAD apps/grado2 core docs/standards | gzip | \
  ssh -o ConnectTimeout=20 vps "ssh -o BatchMode=yes grado 'rm -rf /opt/grado/app.new && mkdir -p /opt/grado/app.new && tar -xz -C /opt/grado/app.new'"

# 2. переключение, зависимости, перезапуск, проверка; при неудаче — прежняя версия
ssh -o ConnectTimeout=20 vps "ssh -o BatchMode=yes grado 'bash -s' -- $VER" <<'REMOTE'
set -uo pipefail
VER="$1"; A=/opt/grado/app
if ! cmp -s $A/apps/grado2/requirements.txt $A.new/apps/grado2/requirements.txt; then
  /opt/grado/venv/bin/pip install -q -r $A.new/apps/grado2/requirements.txt || { echo "зависимости не поставились — сервер не тронут"; rm -rf $A.new; exit 1; }
fi
rm -rf $A.prev && mv $A $A.prev && mv $A.new $A
systemctl restart grado
health() { curl -s -m 5 -H 'Host: 127.0.0.1:8650' http://127.0.0.1:8650/api/health; }
for i in $(seq 1 20); do
  if health | grep -q "\"version\": \"$VER\""; then echo "Готово: на сервере версия $VER"; exit 0; fi
  sleep 1
done
echo "Новая версия не ответила — возвращаю прежнюю"
journalctl -u grado -n 15 --no-pager | tail -15
rm -rf $A.failed && mv $A $A.failed && mv $A.prev $A
systemctl restart grado; sleep 3
echo "Сейчас на сервере: $(health)"
exit 1
REMOTE
