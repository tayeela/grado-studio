#!/usr/bin/env bash
# Вход на grado.tailink.tech через Telegram (v0.99.109): ключи бота в службы grado и grado-guest, снятие системного окна пароля Caddy.
# Запуск на msk под root, ключи — только в переменных окружения (в репозиторий не попадают):
#   TG_ID=<Client ID> TG_SECRET=<Client Secret> TG_ADMINS=@имя [TG_GUESTS='*'] bash tg-login-on-msk.sh
# TG_ADMINS входят в копию владельца (8650); TG_GUESTS ('*' — любой с Telegram) — в гостевую копию (8652), как прежний пароль guest.
# Caddy выбирает копию по первой букве куки grado_site (g — гость); подпись и роль проверяет сама копия.
# Повторяемый. Перед правкой кладёт копии .bak-tglogin-<время>; при сбое возвращает Caddyfile как был.
# Откат вручную: rm /etc/systemd/system/grado{,-guest}.service.d/tglogin.conf; cp <копия> /etc/caddy/Caddyfile; перезапуск grado, grado-guest, caddy.
set -euo pipefail
: "${TG_ID:?нужен TG_ID}" "${TG_SECRET:?нужен TG_SECRET}" "${TG_ADMINS:?нужен TG_ADMINS}"
CF=${CADDYFILE:-/etc/caddy/Caddyfile}; HOST=grado.tailink.tech; T=$(date +%Y%m%d-%H%M%S)

# 1. ключи в обе службы (файл только для root); гостевой копии — роль guest
for svc in grado grado-guest; do
  if systemctl show $svc -p Environment | grep -q 'GRADO2_HUB=1'; then
    echo "служба $svc в совместном режиме (GRADO2_HUB=1) — скрипт для сайта без хаба, останавливаюсь"; exit 1
  fi
  d=/etc/systemd/system/$svc.service.d; mkdir -p $d
  [ -f $d/tglogin.conf ] && cp -p $d/tglogin.conf $d/tglogin.conf.bak-tglogin-$T
  ( umask 077
    printf '[Service]\nEnvironment=GRADO2_TG_CLIENT_ID=%s\nEnvironment=GRADO2_TG_CLIENT_SECRET=%s\nEnvironment=GRADO2_TG_ADMINS=%s\nEnvironment=GRADO2_TG_GUESTS=%s\n' \
      "$TG_ID" "$TG_SECRET" "$TG_ADMINS" "${TG_GUESTS:-*}" > $d/tglogin.conf
    [ $svc = grado-guest ] && echo 'Environment=GRADO2_SITE_ROLE=guest' >> $d/tglogin.conf || true )
done
systemctl daemon-reload && systemctl restart grado grado-guest
for port in 8650 8652; do
  for _ in $(seq 1 30); do
    curl -s -m 5 -H "Host: 127.0.0.1:$port" http://127.0.0.1:$port/api/site | grep -q '"tg": true' && break; sleep 1
  done
  curl -s -m 5 -H "Host: 127.0.0.1:$port" http://127.0.0.1:$port/api/site | grep -q '"tg": true' || {
    echo "копия :$port не включила вход через Telegram (версия ниже 0.99.109?) — пароль Caddy не трогаю"; exit 1; }
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 -H "Host: 127.0.0.1:$port" http://127.0.0.1:$port/api/projects)
  [ "$code" = 401 ] || { echo "копия :$port без входа отвечает $code вместо 401 — пароль Caddy не трогаю"; exit 1; }
done
echo "вход через Telegram включён в обеих копиях, без входа они закрыты"

# 2. в блоке сайта: basicauth убрать, гостя узнавать по куке grado_site=g.… вместо пароля guest
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
    if site and re.match(r"@guest\s+expression\b.*http\.auth\.user", s):
        ln = ln[:len(ln) - len(ln.lstrip())] + r'@guest header_regexp Cookie (^|;\s*)grado_site=g\.'
    depth += s.count("{") - s.count("}")
    if depth == 0:
        site = False
    out.append(ln)
open(path, "w", encoding="utf-8").write("\n".join(out))
PY
if diff -q "$CF" "$CF.bak-tglogin-$T" >/dev/null; then echo "в блоке $HOST нет basicauth — Caddy не трогаю"; exit 0; fi
diff -u "$CF.bak-tglogin-$T" "$CF" | sed -E 's/\$2[aby]\$[^ ]+/<hash>/g' || true
if ! caddy validate --config "$CF" --adapter caddyfile >/dev/null 2>&1 || ! systemctl reload caddy; then
  cp -p "$CF.bak-tglogin-$T" "$CF"; systemctl reload caddy || true
  echo "Caddy не принял правку — возвращён прежний Caddyfile"; exit 1
fi
sleep 2
loc=$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' -m 10 https://$HOST/next/)
echo "https://$HOST/next/ → $loc (нужно 302 на /login.html)"
if curl -s -m 10 -D - -o /dev/null https://$HOST/ | grep -qi 'www-authenticate: basic' || [[ "$loc" != 302*login.html ]]; then
  cp -p "$CF.bak-tglogin-$T" "$CF"; systemctl reload caddy; echo "сайт ответил не так — Caddyfile возвращён"; exit 1
fi
echo "Готово: системного окна нет, вход на странице через Telegram"
