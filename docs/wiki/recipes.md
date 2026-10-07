# Рецепты (пишется вручную)

## Проверка
`tools/gate.sh` — unit (с PYTHONPATH и без), коннекторы, свежесть вики. `E2E=1 tools/gate.sh` — плюс браузерные
сценарии (~6 мин; во время прогона не держать открытыми тестовые серверы — медленный старт страницы даёт ложный сбой).
`E2E_ONLY=t71,t82 tools/gate.sh` — только группы. Журналы шагов — `/tmp/grado-gate/<шаг>.log`.

## Вики
Собирается сама (pre-commit, `tools/wiki.py`). Вручную — только `architecture.md` и `recipes.md`. Вики устарела →
`python3 tools/wiki.py`.

## Где работать
- Команда — ветка `team/t60`, рабочая копия `.claude/worktrees/team2`. Начало цикла: `git merge main`, `tools/gate.sh`,
  прочитать `docs/wiki/INDEX.md` и `docs/wiki/team.md`.
- `main` — программа владельца и сайт: коммит программы в `main` сам выкладывает сайт (хук `deploy-if-main.sh`).
  Только документы команды — `GRADO_NO_DEPLOY=1 git commit -- docs/team`.

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
`git -C ~/grado-studio status --porcelain -- apps/grado2 core docs` пусто → в ветке команды `git merge main` →
`E2E=1 tools/gate.sh` → в main `git merge --ff-only team/t60` (хук выложит сайт; при обрыве сети — повторить
`tools/deploy-server.sh`, путь Mac → msk; ГРАДО на msk с 07.10.2026) → `git push origin main team/t60` → запись в ЛОГ taiLink
(`~/.claude/guard/log_append.py`).

## Срочное исправление на сайте
Ошибка уже на сайте и владелец ждёт: правка прямо в main → `tools/gate.sh` → коммит (выкладка сама) → сразу
`git merge main` в ветку команды.

## Файл проекта на сайте
Проекты — `/var/lib/grado/projects` на msk (с 07.10.2026; `ssh msk`). Перед заменой — копия в `.bak/` с датой, замена через
временный файл и `mv`, проверка sha256 и `/api/projects`, запись в ЛОГ.
