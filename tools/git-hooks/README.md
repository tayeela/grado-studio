# Хуки git

Хуки лежат в репозитории, чтобы работали одинаково во всех рабочих копиях. Включаются один раз в копии командой:

```sh
git config core.hooksPath tools/git-hooks
```

В облачных сессиях Claude Code это делает `.claude/hooks/session-start.sh` (там же выключена выкладка: на сайт выкладывает только Mac владельца).

| хук | когда срабатывает | что делает |
|---|---|---|
| `pre-commit` | перед каждым коммитом | пересобирает вики `python3 tools/wiki.py` (менее 0,2 с, без сети) и добавляет `docs/wiki` в коммит; если коммит с указанием путей не подхватил вики — страховка `tools/gate.sh` |
| `post-commit` | после коммита | если коммит в `main` или `team/t60` менял `docs/wiki` — в фоне выкладывает вики в `tayeela/grado-wiki` (`tools/wiki_publish.sh`); затем вызывает `deploy-if-main.sh` |
| `post-merge` | после `git pull` и слияния | вызывает `deploy-if-main.sh` |
| `deploy-if-main.sh` | вызывается двумя хуками выше | на ветке `main`, если с прошлой выкладки менялись `apps/grado2`, `core`, `docs/standards`, запускает `tools/deploy-server.sh` (сайт на `msk`); метка последней выкладки — `.git/grado-deployed`; неудача выкладки только предупреждает, коммит не отменяет |

- Выкладку выключает переменная `GRADO_NO_DEPLOY=1` (на один запуск: `GRADO_NO_DEPLOY=1 git commit …`).
- Скрипт, запущенный из хука, обязан сбросить `GIT_DIR` и `GIT_INDEX_FILE` перед работой с другим репозиторием — иначе команды git попадут в репозиторий программы (так 06.10.2026 в ветку команды попал лишний коммит; правило `RULE` в [../../docs/team/PROGRESS.md](../../docs/team/PROGRESS.md)).
- Облачная замена pre-commit и post-commit для вики — GitHub Actions `wiki.yml` ([../../.github/workflows/README.md](../../.github/workflows/README.md)).
