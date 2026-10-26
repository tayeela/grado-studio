#!/usr/bin/env bash
# Вход на grado.tailink.tech через Telegram (v0.99.108): ключи бота в службу grado и снятие системного окна пароля Caddy.
# Запуск на msk под root, ключи — только в переменных окружения (в репозиторий не попадают):
#   TG_ID=<Client ID> TG_SECRET=<Client Secret> TG_ADMINS=@имя bash tg-login-on-msk.sh
# Повторяемый. Перед правкой кладёт копии .bak-tglogin-<время>; при сбое возвращает Caddyfile и службу как были.
# Откат вручную: rm /etc/systemd/system/grado.service.d/tglogin.conf; cp <копия> /etc/caddy/Caddyfile; перезапуск grado и caddy.
set -euo pipefail
: "${TG_ID:?нужен TG_ID}" "${TG_SECRET:?нужен TG_SECRET}"
CF=${CADDYFILE:-/etc/caddy/Caddyfile}; HOST=grado.tailink.tech
DROP=/etc/systemd/system/grado.service.d; T=$(date +%Y%m%d-%H%M%S)

# 1. ключи в службу grado (файл только для root)
if systemctl show grado -p Environment | grep -q 'GRADO2_GUEST=1'; then
  echo "у службы grado гостевой вход (GRADO2_GUEST=1): без пароля Caddy сайт откроется всем — останавливаюсь"; exit 1
fi
mkdir -p $DROP
[ -f $DROP/tglogin.conf ] && cp -p $DROP/tglogin.conf $DROP/tglogin.conf.bak-tglogin-$T
umask 077
printf '[Service]\nEnvironment=GRADO2_TG_CLIENT_ID=%s\nEnvironment=GRADO2_TG_CLIENT_SECRET=%s\nEnvironment=GRADO2_TG_ADMINS=%s\n' \
  "$TG_ID" "$TG_SECRET" "${TG_ADMINS:-}" > $DROP/tglogin.conf
systemctl daemon-reload && systemctl restart grado
for _ in $(seq 1 20); do
  curl -s -m 5 -H 'Host: 127.0.0.1:8650' http://127.0.0.1:8650/api/hub/me | grep -q '"tg": true' && break; sleep 1
done
curl -s -m 5 -H 'Host: 127.0.0.1:8650' http://127.0.0.1:8650/api/hub/me | grep -q '"tg": true' || {
  echo "программа не включила вход через Telegram (версия ниже 0.99.108?) — пароль Caddy не трогаю"; exit 1; }
echo "вход через Telegram включён в программе"

# 2. снять basic_auth только в блоке сайта grado.tailink.tech
cp -p "$CF" "$CF.bak-tglogin-$T"
python3 - "$CF" "$HOST" <<'PY'
import re, sys
path, host = sys.argv[1], sys.argv[2]
lines = open(path, encoding="utf-8").read().split("\n")
out, depth, site, skip = [], 0, False, 0
for ln in lines:
    s = ln.strip()
    if depth == 0 and host in s and s.endswith("{"):
        site = True
    if site and not skip and re.match(r"(basic_?auth)\b", s):
        skip = 1 if s.endswith("{") else 0           # блок с логинами или одна строка
        continue
    if skip > 0:
        skip += s.count("{") - s.count("}")
        continue
    depth += s.count("{") - s.count("}")
    if depth == 0:
        site = False
    out.append(ln)
open(path, "w", encoding="utf-8").write("\n".join(out))
PY
if diff -q "$CF" "$CF.bak-tglogin-$T" >/dev/null; then echo "в блоке $HOST нет basic_auth — Caddy не трогаю"; exit 0; fi
diff -u "$CF.bak-tglogin-$T" "$CF" | sed -E 's/\$2[aby]\$[^ ]+/<hash>/g' || true
if ! caddy validate --config "$CF" --adapter caddyfile >/dev/null 2>&1 || ! systemctl reload caddy; then
  cp -p "$CF.bak-tglogin-$T" "$CF"; systemctl reload caddy || true
  echo "Caddy не принял правку — возвращён прежний Caddyfile"; exit 1
fi
sleep 2
code=$(curl -s -o /dev/null -w '%{http_code}' -m 10 https://$HOST/api/hub/me)
echo "https://$HOST/api/hub/me → $code (нужно 401 от программы, без окна браузера)"
curl -s -m 10 -D - -o /dev/null https://$HOST/ | grep -qi 'www-authenticate: basic' && {
  cp -p "$CF.bak-tglogin-$T" "$CF"; systemctl reload caddy; echo "окно пароля осталось — Caddyfile возвращён"; exit 1; }
echo "Готово: системного окна нет, вход на странице через Telegram"
