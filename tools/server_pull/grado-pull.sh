#!/usr/bin/env bash
# Выкладка ГРАДО 2 самим сервером msk: забирает ветку main с GitHub и, если поменялась программа, ставит её на сайт grado.tailink.tech.
# Запускает служба grado-pull (таймер grado-pull.timer раз в 5 минут) под root; ставит install-on-msk.sh, на сервере файл лежит в
# /opt/grado/bin/grado-pull.sh. Проверка версии по /api/health и автооткат — как в прежнем tools/deploy-server.sh (выкладка с Mac).
# Журнал: journalctl -u grado-pull. Ключ GitHub — только чтение и только этот репозиторий (/opt/grado/pull/deploy_key).
#   grado-pull.sh                 — обычный запуск (что делает таймер)
#   grado-pull.sh --mark-current  — запомнить main как уже выложенный, ничего не перезапуская (один раз при установке)
set -uo pipefail
P=/opt/grado/pull; A=/opt/grado/app; R=$P/repo.git
PATHS="apps/grado2 core docs/standards"
export GIT_DIR=$R
unset GIT_INDEX_FILE GIT_WORK_TREE
export GIT_SSH_COMMAND="ssh -i $P/deploy_key -o IdentitiesOnly=yes -o UserKnownHostsFile=$P/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes -o ConnectTimeout=20"

exec 9>"$P/lock"
flock -n 9 || { echo "предыдущая выкладка ещё идёт — пропускаю"; exit 0; }

git fetch -q --depth 1 origin +refs/heads/main:refs/heads/main || { echo "GitHub не ответил — попробую в следующий раз"; exit 1; }
REV=$(git rev-parse main)
# «отпечаток» программы: объекты трёх папок; другие правки в main (документы команды и т. п.) сайт не перезапускают
KEY=$(for d in $PATHS; do git rev-parse "$REV:$d"; done | tr '\n' ' ')
VER=$(git show "$REV:apps/grado2/web/version.json" | python3 -c 'import sys,json;print(json.load(sys.stdin)["version"])')
health() { curl -s -m 5 -H 'Host: 127.0.0.1:8650' http://127.0.0.1:8650/api/health; }

if [ "${1:-}" = --mark-current ]; then
  if health | grep -q "\"version\": \"$VER\""; then
    echo "$KEY" > "$P/deployed"; echo "$REV" > "$P/deployed.rev"
    echo "Отмечено: на сайте уже версия $VER (main ${REV:0:7}), выкладывать нечего"; exit 0
  fi
  echo "На сайте не версия $VER из main — не отмечаю; таймер выложит main сам"; exit 1
fi

[ "$KEY" = "$(cat "$P/deployed" 2>/dev/null)" ] && exit 0
# этот же код уже не поднялся и был откачен — не перезапускать сайт каждые 5 минут, ждать нового коммита в main
[ "$KEY" = "$(cat "$P/failed" 2>/dev/null)" ] && exit 0

echo "В main новая программа: ${REV:0:7}, версия $VER — выкладываю"
# сервер занят (идёт первая выгрузка слоя или «DXF ГИС ОГД») — перезапуск её оборвал бы: следующий запуск таймера попробует снова
H='Host: 127.0.0.1:8650'
busy=$(curl -s -m 5 -H "$H" http://127.0.0.1:8650/api/progress | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)
job=$(curl -s -m 5 -H "$H" http://127.0.0.1:8650/api/ogd_all/status | python3 -c 'import sys,json;print(int(bool(json.load(sys.stdin).get("running"))))' 2>/dev/null || echo 0)
if [ "${busy:-0}" != 0 ] || [ "${job:-0}" != 0 ]; then
  echo "Сервер занят выгрузкой — не перезапускаю, попробую через 5 минут"; exit 0
fi

rm -rf $A.new && mkdir -p $A.new
# shellcheck disable=SC2086
git archive --format=tar "$REV" $PATHS | tar -x -C $A.new || { echo "не распаковался код — сервер не тронут"; rm -rf $A.new; exit 1; }
if ! cmp -s $A/apps/grado2/requirements.txt $A.new/apps/grado2/requirements.txt; then
  /opt/grado/venv/bin/pip install -q -r $A.new/apps/grado2/requirements.txt || { echo "зависимости не поставились — сервер не тронут"; rm -rf $A.new; exit 1; }
fi
rm -rf $A.prev && mv $A $A.prev && mv $A.new $A
systemctl restart grado
systemctl restart grado-guest 2>/dev/null || true   # гостевая копия (вход guest, свои проекты) — тот же код
for _ in $(seq 1 20); do
  if health | grep -q "\"version\": \"$VER\""; then
    echo "$KEY" > "$P/deployed"; echo "$REV" > "$P/deployed.rev"; rm -f "$P/failed"
    echo "Готово: на сервере версия $VER (main ${REV:0:7})"
    git gc -q --prune=now 2>/dev/null || true
    exit 0
  fi
  sleep 1
done
echo "Новая версия $VER не ответила — возвращаю прежнюю"
journalctl -u grado -n 15 --no-pager | tail -15
rm -rf $A.failed && mv $A $A.failed && mv $A.prev $A
systemctl restart grado; systemctl restart grado-guest 2>/dev/null || true; sleep 3
echo "$KEY" > "$P/failed"
echo "Сейчас на сервере: $(health)"
exit 1
