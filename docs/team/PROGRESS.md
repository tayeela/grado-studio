# Журнал команды ГРАДО 2

Новые циклы сверху. Строки `RULE:` — уроки, которые обязана прочитать каждая следующая задача.

RULE: The owner's program and the site change only after the owner's word «выкладывай»; all program work happens in
the team worktree `.claude/worktrees/team` on branch `team/grado2`.

RULE: Before taking a status claim from a role, check the changelog entry it cites: the changelog keeps old «not done»
lines under entries that were done later (Э11 was «not done» at line 1513 and done in v0.36.0).
RULE: Social-object placement (T6) starts only after the preset constants audit (T4) and the norms spec with a fixture
test (T5); plot areas are the table minimum «не менее».

- 02.10.2026, цикл 1 — задачи T1 и T2 (частично). T1: совещание продакта, архитектора, нормоконтролёра и креативного
  директора в два круга; план сверен с v0.91.1 (новый раздел «Where we are (02.10.2026)» в ветке команды, 532d0e5),
  очередь T2–T12 в BOARD, решение в DECISIONS. T2а: ошибка 500 ленты событий в unit-тестах — поток пережил подмену
  хаба тестом; обработчик держит свой хаб (v0.91.2, 2180962). Проверка: 3 прогона unit-тестов по 355 — OK, без
  `session_user`; ревью архитектора PASS (прод не меняется). Браузерные сценарии: 4 прогона из 5 зелёные, один упал на
  `#hubShareLogin` — это остаток T2. Дальше: T2 (стабильность сценария), T3 (`_uid` ЕГРН), T4 (сверка констант).
- 02.10.2026 — команда создана: роли в `.claude/agents/grado-*.md`, порядок цикла в `docs/team/CYCLE.md`,
  рабочая копия `.claude/worktrees/team` на ветке `team/grado2` (от main 2c9c6ea, v0.91.1). Первая задача — T1.
