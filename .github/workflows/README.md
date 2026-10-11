# Автоматика GitHub

| файл | когда запускается | что делает |
|---|---|---|
| `grado2-release.yml` («ГРАДО 2 release») | PR, который меняет `apps/grado2/**`, `core/**`, `packaging/grado2*` или сам файл; вручную; по тегу `grado2-v*` | задача `test` (около 10 минут): модульные тесты сервера и коннекторов, затем браузерные сценарии в Chrome без интернета; задача `build` (только по тегу и вручную, можно выбрать одну систему): установщик Windows (`.exe`), его установка на чистый Windows с запуском и удалением (замеры в Summary), образ macOS (`.dmg`), по тегу — выпуск на GitHub |
| `docs.yml` («Документы и вики») | каждый PR и пуш в `main` и `team/t60`; вручную | меньше минуты: `tools/docs_check.py` (ссылки, пути, полки, заголовки файлов) и `tools/wiki.py --check` (вики совпадает с кодом) |
| `wiki.yml` («Вики (пересборка и выкладка)») | пуш в `main` и `team/t60`; вручную | пересобирает `docs/wiki` из кода и, если что-то изменилось, коммитит в ту же ветку «wiki: пересборка из кода [skip ci]»; после пуша в `team/t60` кладёт копию в приватный репозиторий `tayeela/grado-wiki` (нужен секрет `WIKI_TOKEN`) |

Шаблоны задач и PR лежат рядом: `../ISSUE_TEMPLATE/` («Замечание владельца», «Задача») и `../pull_request_template.md`.

## Секрет `WIKI_TOKEN` (один раз, две минуты)

Без него `wiki.yml` обновляет вики внутри репозитория программы, но не в `tayeela/grado-wiki` (предупреждение в журнале запуска; вики на Mac при этом
обновляет хук `post-commit`). Чтобы вики на GitHub обновлялась всегда:

1. GitHub → аватар → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token.
2. Resource owner — `tayeela`; Repository access — Only select repositories → `grado-wiki`; Permissions → Repository permissions → Contents: Read and write.
   Срок — до года (поставьте напоминание продлить).
3. Репозиторий `tayeela/grado-studio` → Settings → Secrets and variables → Actions → New repository secret: имя `WIKI_TOKEN`, значение — токен.
4. Проверка: Actions → «Вики (пересборка и выкладка)» → Run workflow на ветке `team/t60`; в `grado-wiki` появится коммит «wiki: team/t60 …».

## Как читать красный запуск

- `test` упал на шаге браузерных сценариев — смотрите, какая именно проверка (`не выполнено: …`); случайные падения по времени — задача #40, не перезапускайте «до зелёного»:
  один повтор допустим только после того, как нашли причину, что падение не из-за вашего PR.
- `docs` упал — прочитайте список нарушений в журнале: каждая строка называет правило, файл и что исправить (`python3 tools/docs_check.py` покажет то же локально);
  «вики устарела» лечится `python3 tools/wiki.py`.
