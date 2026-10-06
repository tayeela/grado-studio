---
name: land
description: Выкладка ГРАДО 2 на сайт grado.tailink.tech по слову владельца «выкладывай» — PR ветки команды в main на GitHub, тесты, слияние, деплой, отчёт. Использовать только по явному слову владельца.
disable-model-invocation: true
---

# Выкладка («выкладывай»)

Только по слову владельца в чате. Источник правды — GitHub (docs/team/CYCLE.md).

1. Основная копия `~/grado-studio`: `git status --porcelain -- apps/grado2 core docs` пустой; иначе — стоп, сказать владельцу.
2. Рабочая копия команды (`.claude/worktrees/team2`, `team/t60`): `git merge main`, `E2E=1 tools/gate.sh` зелёный,
   `git push origin team/t60`.
3. PR выкладки `team/t60 → main` (открыт; нет — `gh pr create --base main --head team/t60 --label "готово к выкладке"`
   с описанием «что увидит владелец»). Проверки GitHub зелёные (`gh pr checks`).
4. `gh pr merge <n> --merge`; затем в основной копии `git pull --ff-only` — хук обновит сайт; прочитать вывод
   («Готово: на сервере версия …»; «отложено» или ошибка — старая версия работает, повторить `tools/deploy-server.sh`).
5. Закрыть задачи из PR (если не закрылись сами), снять метку «готово к выкладке»; строка в `docs/team/PROGRESS.md`.
6. Владельцу: версия, что изменилось на экране, результат сервера, ссылка на PR, «перезапустите программу».
