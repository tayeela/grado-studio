#!/usr/bin/env bash
# Установка выкладки ГРАДО 2 самим сервером (таймер grado-pull) на msk — запускать на самом msk под root, по процедуре taiLink.
# Повторяемый: что уже сделано, пропускает; перед заменой файла кладёт копию .bak-gradopull-<время>.
# Первый запуск создаёт ключ и останавливается: его открытую часть добавить в GitHub (tayeela/grado-studio → Settings →
# Deploy keys, без «Allow write access») и запустить скрипт ещё раз. Файлы службы берёт из GitHub, ветка GRADO_PULL_REF (по умолчанию main).
set -euo pipefail

P=/opt/grado/pull; R=$P/repo.git
REF=${GRADO_PULL_REF:-main}
REPO=git@github.com:tayeela/grado-studio.git
# отпечаток ключа github.com (опубликован GitHub: docs.github.com → «GitHub's SSH key fingerprints»)
GH_FP="SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU"
TS=$(date -u +%Y%m%dT%H%M%SZ)
say() { echo "== $*"; }

[ "$(id -u)" = 0 ] || { echo "нужен root"; exit 1; }
[ -d /opt/grado/app ] && systemctl cat grado >/dev/null 2>&1 || { echo "нет /opt/grado/app или службы grado — это не msk?"; exit 1; }
command -v git >/dev/null || { echo "нет git: apt-get install -y git"; exit 1; }

say "1/5 ключ GitHub только для чтения → $P/deploy_key"
install -d -m 700 $P
[ -f $P/deploy_key ] || ssh-keygen -q -t ed25519 -N '' -C "grado-pull@msk" -f $P/deploy_key
chmod 600 $P/deploy_key

say "2/5 ключ сервера github.com (сверка отпечатка)"
D=$(mktemp -d); trap 'rm -rf "$D"' EXIT
ssh-keyscan -t ed25519 github.com 2>/dev/null > "$D/kh"
[ "$(ssh-keygen -lf "$D/kh" | awk '{print $2}')" = "$GH_FP" ] || { echo "ОТПЕЧАТОК github.com НЕ СОВПАЛ — стоп"; exit 1; }
install -m 644 "$D/kh" $P/known_hosts

say "3/5 доступ к репозиторию"
[ -d $R ] || git init -q --bare $R
git --git-dir=$R remote get-url origin >/dev/null 2>&1 || git --git-dir=$R remote add origin $REPO
export GIT_SSH_COMMAND="ssh -i $P/deploy_key -o IdentitiesOnly=yes -o UserKnownHostsFile=$P/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes -o ConnectTimeout=20"
if ! git --git-dir=$R ls-remote origin main >/dev/null 2>&1; then
  echo "GitHub не пускает ключ. Добавьте его в tayeela/grado-studio → Settings → Deploy keys (без записи) и запустите скрипт снова:"
  cat $P/deploy_key.pub
  exit 2
fi
echo "ok: ключ принят"

say "4/5 скрипт и служба из ветки $REF"
git --git-dir=$R fetch -q --depth 1 origin "$REF"
put() {  # put <путь в репозитории> <куда> <права>
  git --git-dir=$R show "FETCH_HEAD:$1" > "$D/f"
  if [ -f "$2" ] && ! cmp -s "$D/f" "$2"; then cp -p "$2" "$2.bak-gradopull-$TS"; fi
  install -D -m "$3" "$D/f" "$2"
}
put tools/server_pull/grado-pull.sh /opt/grado/bin/grado-pull.sh 755
put tools/server_pull/grado-pull.service /etc/systemd/system/grado-pull.service 644
put tools/server_pull/grado-pull.timer /etc/systemd/system/grado-pull.timer 644
systemctl daemon-reload

say "5/5 отметка текущей версии и включение таймера"
# если на сайте уже версия из main — запомнить её, чтобы первый запуск не перезапускал сайт зря
/opt/grado/bin/grado-pull.sh --mark-current || true
systemctl enable --now grado-pull.timer
systemctl list-timers grado-pull.timer --no-pager
echo "Готово. Журнал выкладок: journalctl -u grado-pull -n 30"
