# Релей к НСПД для облачных сессий

Зачем. НСПД (nspd.gov.ru) сам обрывает соединение с иностранных адресов, поэтому облачные сессии Claude Code
не могут выгружать данные портала. Релей — маленькая надстройка на российском сервере: облако ходит на наш
домен, а релей передаёт запрос в НСПД. Корни Минцифры нужны только на релее, в облаке они не нужны.

Схема: облако → `https://<домен релея>` (обычный сертификат Let's Encrypt) → релей в РФ → `https://nspd.gov.ru`.

## Что делает релей

- Принимает только GET и POST на пути `/api/geoportal/…`. Всё остальное — 404.
- Нужен заголовок `X-Grado-Relay-Token` со значением из файла токена. Нет заголовка или не тот — 401.
- Дальше передаёт запрос на `https://nspd.gov.ru` с `Host: nspd.gov.ru`, с `Referer: https://nspd.gov.ru/map`
  и `Origin: https://nspd.gov.ru`. Сертификат НСПД проверяется по корням Минцифры, отключить проверку нельзя.
- Бережёт портал: один запрос к НСПД за раз, ожидание ответа до 60 с, запрос не больше 2 МБ, кэша ответов нет.
  В обычном Caddy нет настройки «запросов в секунду» (`limit_req` есть только в nginx), поэтому частоту держит
  сам коннектор: пауза 0,4 с между запросами, не больше 3 повторов.
- Журнал доступа выключен: ни заголовков, ни тел запросов нигде не сохраняется.

## Установка на msk (ONEDASH-RU)

Файлы: `Caddyfile.example` (пример блока без секретов) и `install-on-msk.sh` (делает всё по шагам, повторяем,
перед правкой любого файла кладёт копию `.bak-nspdrelay-<время>`). Запуск с Mac, из каталога репозитория:

```bash
cd ~/grado-studio && ssh root@93.88.203.245 'bash -s' < tools/nspd_relay/install-on-msk.sh
```

Скрипт: проверяет отпечатки корней Минцифры (при несовпадении останавливается), кладёт бандл
`/etc/caddy/nspd-ca.pem`, создаёт токен `/etc/caddy/relay-token` (права 640, в вывод не печатается),
создаёт запись DNS `gp.tailink.tech`, выпускает сертификат, добавляет блок в Caddy, проверяет конфиг и мягко
перезагружает Caddy. Если проверка конфига не проходит, Caddyfile возвращается из копии.

Откат: вернуть `/etc/caddy/Caddyfile` из последней копии `.bak-nspdrelay-*`, выполнить `systemctl reload caddy`,
удалить запись `gp` в Cloudflare.

## Как проверить (с Mac)

Токен: `ssh root@93.88.203.245 'cat /etc/caddy/relay-token'` (вставлять ниже вместо `ТОКЕН`).

```bash
B=https://gp.tailink.tech
Q='/api/geoportal/v2/search/geoportal?query=77:01:0001001:1&thematicSearchId=1'
curl -s -o /dev/null -w 'без токена: %{http_code} (ждём 401)\n'  "$B$Q"
curl -s -o /dev/null -w 'не тот путь: %{http_code} (ждём 404)\n' -H 'X-Grado-Relay-Token: ТОКЕН' "$B/"
curl -s -m 70 -H 'X-Grado-Relay-Token: ТОКЕН' "$B$Q" | head -c 300; echo   # ответ НСПД: GeoJSON или «не найдено»
```

Через коннектор (один небольшой запрос на область, с паузами):

```bash
cd ~/grado-studio && GRADO_NSPD_BASE=https://gp.tailink.tech GRADO_NSPD_RELAY_TOKEN=ТОКЕН \
  PYTHONPATH=core/connectors python3 -c "
from grado_connectors.nspd import NspdDirect
r = NspdDirect().fetch((37.6200, 55.7500, 37.6210, 55.7508), [36368])
print(len(r['features']), 'объектов')"
```

## Включение в облачной сессии

1. Меню окружения в заголовке сессии → Edit → Network access → Allowed domains: добавить `gp.tailink.tech`.
2. Секреты окружения: `GRADO_NSPD_BASE=https://gp.tailink.tech` и `GRADO_NSPD_RELAY_TOKEN=<токен из файла>`.
3. Переменные читает коннектор (`core/connectors/grado_connectors/nspd.py`). Токен уходит только на релей:
   если `GRADO_NSPD_BASE` не задан, коннектор ходит напрямую в НСПД и токен не отправляет.

## Замена токена

На msk: `openssl rand -hex 32 | tr -d '\n' > /etc/caddy/relay-token` (права 640, владелец root:caddy), затем
`systemctl reload caddy`; новый токен внести в секреты окружения.
