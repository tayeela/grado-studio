# Рецепты (пишется вручную)

## Проверка
`tools/gate.sh` — свежесть вики, навигация документов (`tools/docs_check.py`), unit (с PYTHONPATH и без), коннекторы. `E2E=1 tools/gate.sh` — плюс браузерные
сценарии (~6 мин; во время прогона не держать открытыми тестовые серверы — медленный старт страницы даёт ложный сбой).
`E2E_ONLY=t71,t82 tools/gate.sh` — только группы. Журналы шагов — `/tmp/grado-gate/<шаг>.log`.

## Выгрузка НСПД из облачной сессии (релей)
Облако не достаёт `nspd.gov.ru` (портал рвёт соединение с иностранных адресов). Нужен релей на российском сервере:
`tools/nspd_relay/` (установка на msk одной командой, проверка, замена токена — `tools/nspd_relay/README.md`).
В облачной сессии: адрес релея в Allowed domains окружения, секреты `GRADO_NSPD_BASE=https://<домен релея>` и
`GRADO_NSPD_RELAY_TOKEN=<токен>`. Без этих переменных коннектор ходит прямо в НСПД, как раньше; токен уходит только
на релей. Проверку сертификатов отключать нельзя (правило 4).

## Вики
Страницы с пометкой «генерируется» собирает `tools/wiki.py` из кода; `sheets.md` — из самого `albums.js`, выполненного в Node
(`tools/wiki_albums.mjs`). Вручную пишутся `architecture.md`, `recipes.md`, `files.md`, `conventions.md`, `howto.md`, `album-rules.md`.
Обновляется само, в три слоя:
1. хук `pre-commit` (`tools/git-hooks`, включается `git config core.hooksPath tools/git-hooks`; в облачных сессиях — сам) пересобирает вики перед коммитом;
2. GitHub Actions `docs.yml` на каждом PR проверяет, что вики совпадает с кодом (`python3 tools/wiki.py --check`), а `wiki.yml` после пуша в
   `team/t60` и `main` пересобирает её и коммитит «wiki: пересборка из кода [skip ci]»;
3. после пуша в `team/t60` `wiki.yml` кладёт копию в приватный репозиторий `tayeela/grado-wiki` (нужен секрет `WIKI_TOKEN`, один раз —
   `.github/workflows/README.md`). Вручную или из облачной сессии: `tools/wiki_publish.sh`.
Вики устарела → `python3 tools/wiki.py`. Навигация сломана (ссылка, путь, файл без заголовка) → `python3 tools/docs_check.py`.

## Где работать
- Любая сессия (Mac или облако): ветка `task/<номер задачи>-<имя>` от `team/t60` → `tools/gate.sh` → PR в `team/t60` (CI проверяет сам) → слияние.
  В `main` — только по слову владельца «выкладывай» (навык `land`).
- Команда на Mac — ветка `team/t60`, рабочая копия `.claude/worktrees/team2`. Начало цикла: `git merge main`, `tools/gate.sh`,
  прочитать `docs/wiki/INDEX.md` и `docs/wiki/team.md`.
- `main` — программа владельца и сайт: слияние в `main` на GitHub само выкладывает сайт — сервер msk забирает `main` раз в 5 минут
  (`tools/server_pull/README.md`). Только документы команды — `git commit -- docs/team`.

## Тестовая копия программы (не 8650!)
`~/.claude/launch.json` → `grado2-team2` (порт 8661, ветка команды, проекты `/tmp/grado-team/2026-10-05/proj-t2`) и
`grado2-test` (8651, main). Запуск — инструмент preview_start по имени. В тестовой папке лежат копии: «КРТ 3229 Гольяново»,
«Безобразово 30.09 (копия)». Открыть проект из консоли: `openProject(имя)` дважды подряд (второй раз — подтверждение).

## Собрать альбом и посмотреть листы
В консоли страницы: `buildAlbum("pptkrt")` (поверх других листов — нажать «Заменить»), затем
`fetch('/api/project?name=_spec',{method:'POST',body:JSON.stringify(albumSpec(ALBUM.sheets))})` и
`curl -X POST localhost:8661/api/print/pdf --data-binary @<папка проектов>/_spec.grado2 -o a.pdf`,
`pdftoppm -r 100 -png a.pdf p`. Проверять глазами (железное правило 6) и на живых данных — не только на тестовых.

## Выкладка (только по слову владельца «выкладывай»)
Навык `land` (`.claude/skills/land/SKILL.md`): `git -C ~/grado-studio status --porcelain -- apps/grado2 core docs` пусто → в ветке команды
`git merge main` → `E2E=1 tools/gate.sh`, CI зелёный → PR `team/t60 → main` слить на GitHub → сервер msk сам выложит сайт в течение 5 минут
(`tools/server_pull/README.md`; проверить версию сайта) → на Mac в основной копии `git pull --ff-only` →
закрыть задачи, убрать метку «готово к выкладке» → запись в ЛОГ taiLink (`~/.claude/guard/log_append.py`).

## Срочное исправление на сайте
Ошибка уже на сайте и владелец ждёт: ветка `fix/<задача>` от `main` → `tools/gate.sh` → PR в `main` → слить только после слова
владельца «выкладывай» (сервер выложит сам) → сразу `git merge main` в ветку команды. Прямых коммитов в `main` нет.

## Файл проекта на сайте
Проекты — `/var/lib/grado/projects` на msk (с 07.10.2026; `ssh msk`). Перед заменой — копия в `.bak/` с датой, замена через
временный файл и `mv`, проверка sha256 и `/api/projects`, запись в ЛОГ.
