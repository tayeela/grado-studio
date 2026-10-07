#!/usr/bin/env bash
# Установка релея к НСПД на msk (ONEDASH-RU) — запускать на самом msk под root:
#   ssh root@93.88.203.245 'bash -s' < tools/nspd_relay/install-on-msk.sh
# Скрипт повторяемый: что уже сделано, пропускает. Перед каждой правкой файла делает копию .bak-nspdrelay-<время>.
# Токен нигде не печатает. Журнал доступа релея выключен.
set -euo pipefail

HOST=${RELAY_HOST:-gp.tailink.tech}
IP=93.88.203.245
TS=$(date -u +%Y%m%dT%H%M%SZ)
CADDYFILE=/etc/caddy/Caddyfile
HOOK=/etc/letsencrypt/renewal-hooks/deploy/msk-local-certs.sh
ROOT_SHA="D2:6D:2D:02:31:B7:C3:9F:92:CC:73:85:12:BA:54:10:35:19:E4:40:5D:68:B5:BD:70:3E:97:88:CA:8E:CF:31"
SUB_SHA="BB:BD:E2:10:3E:79:0B:99:9E:C6:2B:D0:3C:F6:25:A5:A2:E7:C3:16:E1:0A:FE:6A:49:0E:ED:EA:D8:B3:FD:9B"
say() { echo "== $*"; }

[ "$(id -u)" = 0 ] || { echo "нужен root"; exit 1; }
command -v caddy >/dev/null && command -v certbot >/dev/null || { echo "нет caddy или certbot — это не msk?"; exit 1; }

say "1/6 корни Минцифры → /etc/caddy/nspd-ca.pem (сверка отпечатков SHA-256)"
# бандл собирается заново при каждом запуске (маленький, а битый файл от прошлой попытки не должен остаться)
D=$(mktemp -d); trap 'rm -rf "$D"' EXIT
curl -fsS -m 30 -o "$D/root.cer" https://gu-st.ru/content/Other/doc/russian_trusted_root_ca.cer
curl -fsS -m 30 -o "$D/sub.cer"  https://gu-st.ru/content/Other/doc/russian_trusted_sub_ca.cer
for n in root sub; do
  # через openssl в обоих случаях: на выходе ровный PEM с переводом строки в конце
  if grep -q "BEGIN CERTIFICATE" "$D/$n.cer"; then openssl x509 -in "$D/$n.cer" -outform PEM -out "$D/$n.pem"
  else openssl x509 -inform DER -in "$D/$n.cer" -outform PEM -out "$D/$n.pem"; fi
done
[ "$(openssl x509 -in "$D/root.pem" -noout -fingerprint -sha256 | cut -d= -f2)" = "$ROOT_SHA" ] || { echo "ОТПЕЧАТОК КОРНЯ НЕ СОВПАЛ — стоп"; exit 1; }
[ "$(openssl x509 -in "$D/sub.pem"  -noout -fingerprint -sha256 | cut -d= -f2)" = "$SUB_SHA" ]  || { echo "ОТПЕЧАТОК ПОДЧИНЁННОГО НЕ СОВПАЛ — стоп"; exit 1; }
cat "$D/root.pem" "$D/sub.pem" > "$D/bundle.pem"
VERIFY=$(echo | timeout 20 openssl s_client -connect nspd.gov.ru:443 -servername nspd.gov.ru -CAfile "$D/bundle.pem" 2>&1 || true)
case "$VERIFY" in
  *"Verify return code: 0 (ok)"*) ;;
  *) echo "бандл не подтверждает сертификат nspd.gov.ru — стоп"; exit 1 ;;
esac
install -m 0644 -o root -g caddy "$D/bundle.pem" /etc/caddy/nspd-ca.pem
echo "ok: сертификат НСПД проверяется по корням Минцифры"

say "2/6 токен релея → /etc/caddy/relay-token (права 640, в вывод не печатается)"
if [ ! -s /etc/caddy/relay-token ]; then
  ( umask 077; openssl rand -hex 32 | tr -d '\n' > /etc/caddy/relay-token )
fi
chown root:caddy /etc/caddy/relay-token; chmod 640 /etc/caddy/relay-token
echo "ok: $(wc -c < /etc/caddy/relay-token) знаков"

say "3/6 запись DNS $HOST → $IP"
tailink-dns-upsert "${HOST%%.*}" "$IP"

say "4/6 хук сертификатов: добавить $HOST (каталог gp)"
if ! grep -q "gp.tailink.tech" "$HOOK"; then
  cp -a "$HOOK" "$HOOK.bak-nspdrelay-$TS"
  python3 - "$HOOK" <<'PY'
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
key = "  */grado.tailink.tech)     D=grado ;;\n"
assert key in s, "в хуке нет строки grado — правьте вручную"
s = s.replace(key, key + "  */gp.tailink.tech)        D=gp ;;\n", 1)
open(p, "w", encoding="utf-8").write(s)
PY
  bash -n "$HOOK"
fi

say "5/6 сертификат Let's Encrypt для $HOST (DNS-01 Cloudflare, как у соседних доменов)"
if [ ! -d "/etc/letsencrypt/live/$HOST" ]; then
  certbot certonly --non-interactive --agree-tos --authenticator dns-cloudflare \
    --dns-cloudflare-credentials /root/.secrets/cf-tailink.ini --dns-cloudflare-propagation-seconds 25 \
    --key-type ecdsa -d "$HOST"
fi
[ -s "/etc/caddy/certs/gp/fullchain.pem" ] || {
  install -d -m 0750 -o caddy -g caddy /etc/caddy/certs/gp
  install -m 0644 -o caddy -g caddy "/etc/letsencrypt/live/$HOST/fullchain.pem" /etc/caddy/certs/gp/fullchain.pem
  install -m 0600 -o caddy -g caddy "/etc/letsencrypt/live/$HOST/privkey.pem"   /etc/caddy/certs/gp/privkey.pem
}

say "6/6 блок Caddy для $HOST (с копией, проверкой и мягкой перезагрузкой)"
if ! grep -q "^https://$HOST" "$CADDYFILE"; then
  cp -a "$CADDYFILE" "$CADDYFILE.bak-nspdrelay-$TS"
  cat >> "$CADDYFILE" <<EOF

# Релей к НСПД для облачных сессий (07.10.2026): только GET/POST на /api/geoportal/*, токен в X-Grado-Relay-Token.
https://$HOST {
	tls /etc/caddy/certs/gp/fullchain.pem /etc/caddy/certs/gp/privkey.pem
	log {
		output discard
	}
	@allowed {
		path /api/geoportal/*
		method GET POST
	}
	handle @allowed {
		@token header X-Grado-Relay-Token {file./etc/caddy/relay-token}
		handle @token {
			request_body {
				max_size 2MB
			}
			reverse_proxy https://nspd.gov.ru {
				header_up Host nspd.gov.ru
				header_up Referer https://nspd.gov.ru/map
				header_up Origin https://nspd.gov.ru
				header_up -X-Grado-Relay-Token
				header_up -X-Forwarded-For
				header_up -X-Forwarded-Proto
				header_up -X-Forwarded-Host
				header_up -Via
				transport http {
					tls_server_name nspd.gov.ru
					tls_trusted_ca_certs /etc/caddy/nspd-ca.pem
					dial_timeout 10s
					response_header_timeout 60s
					read_timeout 60s
					max_conns_per_host 1
				}
			}
		}
		respond "unauthorized" 401
	}
	respond "not found" 404
}
EOF
  if caddy validate --config "$CADDYFILE" --adapter caddyfile >/dev/null 2>&1; then
    systemctl reload caddy
    echo "ok: Caddy перезагружен мягко"
  else
    cp -a "$CADDYFILE.bak-nspdrelay-$TS" "$CADDYFILE"
    echo "ПРОВЕРКА Caddy НЕ ПРОШЛА — Caddyfile возвращён из копии, ничего не перезагружено"
    exit 1
  fi
fi

say "готово. Откат: вернуть $CADDYFILE из .bak-nspdrelay-*, systemctl reload caddy; DNS: tailink-dns-upsert — удалить запись $HOST в Cloudflare."
say "токен прочитать: ssh root@$IP 'cat /etc/caddy/relay-token'"
