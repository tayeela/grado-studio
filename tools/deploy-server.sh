#!/usr/bin/env bash
# Обновить ГРАДО 2 на сервере grado.tailink.tech одной командой:  tools/deploy-server.sh
#
# Отправляет последний коммит (не рабочие правки) на msk (ONEDASH-RU, 93.88.203.245), ставит его рядом с работающей
# версией, переключает каталог и перезапускает службу grado. Если после перезапуска /api/health не отвечает новой
# версией — сам возвращает прежнюю и завершается с ошибкой. С 07.10.2026 ГРАДО работает на самом msk (перенос с
# AEZA-GRADO, который перестал отвечать), поэтому выкладка идёт Mac → msk без перехода на другой хост.
# Перенос и откат — в ЛОГе taiLink за 07.10.2026; установка прежнего сервера — за 25.09.2026.
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
  ssh -o ConnectTimeout=20 msk 'rm -rf /opt/grado/app.new && mkdir -p /opt/grado/app.new && tar -xz -C /opt/grado/app.new'

# 2. переключение, зависимости, перезапуск, проверка; при неудаче — прежняя версия
ssh -o ConnectTimeout=20 msk "bash -s -- $VER" <<'REMOTE'
set -uo pipefail
VER="$1"; A=/opt/grado/app
# сервер занят (идёт первая выгрузка слоя или «DXF ГИС ОГД») — перезапуск её оборвал бы: откладываем
H='Host: 127.0.0.1:8650'
busy=$(curl -s -m 5 -H "$H" http://127.0.0.1:8650/api/progress | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)
job=$(curl -s -m 5 -H "$H" http://127.0.0.1:8650/api/ogd_all/status | python3 -c 'import sys,json;print(int(bool(json.load(sys.stdin).get("running"))))' 2>/dev/null || echo 0)
if [ "${busy:-0}" != 0 ] || [ "${job:-0}" != 0 ]; then
  echo "Сервер занят выгрузкой — не перезапускаю, чтобы её не оборвать. Обновление отложено: повторите tools/deploy-server.sh позже."
  rm -rf $A.new; exit 3
fi
if ! cmp -s $A/apps/grado2/requirements.txt $A.new/apps/grado2/requirements.txt; then
  /opt/grado/venv/bin/pip install -q -r $A.new/apps/grado2/requirements.txt || { echo "зависимости не поставились — сервер не тронут"; rm -rf $A.new; exit 1; }
fi
rm -rf $A.prev && mv $A $A.prev && mv $A.new $A
systemctl restart grado
systemctl restart grado-guest 2>/dev/null || true   # гостевая копия (вход guest, свои проекты) — тот же код, с 07.10.2026
health() { curl -s -m 5 -H 'Host: 127.0.0.1:8650' http://127.0.0.1:8650/api/health; }
for i in $(seq 1 20); do
  if health | grep -q "\"version\": \"$VER\""; then echo "Готово: на сервере версия $VER"; exit 0; fi
  sleep 1
done
echo "Новая версия не ответила — возвращаю прежнюю"
journalctl -u grado -n 15 --no-pager | tail -15
rm -rf $A.failed && mv $A $A.failed && mv $A.prev $A
systemctl restart grado; systemctl restart grado-guest 2>/dev/null || true; sleep 3
echo "Сейчас на сервере: $(health)"
exit 1
REMOTE
