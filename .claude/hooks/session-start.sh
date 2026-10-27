#!/bin/bash
# SessionStart hook, только облачные сессии Claude Code: то же окружение, что «ГРАДО 2.command» на Mac
# (~/.grado2/venv + apps/grado2/requirements.txt и requirements-dev.txt, tools/node_modules), чтобы tools/gate.sh и Stop-хуки работали без ложных сбоев;
# CHROME — встроенный Chromium контейнера для браузерных сценариев (E2E=1). Повторный запуск ничего не ломает.
set -euo pipefail
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
cd "$CLAUDE_PROJECT_DIR"
VENV="$HOME/.grado2/venv"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install -q --disable-pip-version-check -r apps/grado2/requirements.txt -r apps/grado2/requirements-dev.txt
# Playwright для браузерных сценариев и TypeScript для проверки типов (tools/package.json); без node — шаги пропускаются
if command -v npm >/dev/null; then (cd tools && npm ci --silent) || true; fi
CH=$(ls -d /opt/pw-browsers/chromium-*/chrome-linux*/chrome 2>/dev/null | head -1 || true)
if [ -n "$CH" ] && [ -n "${CLAUDE_ENV_FILE:-}" ]; then echo "export CHROME=\"$CH\"" >> "$CLAUDE_ENV_FILE"; fi
# хуки git репозитория (tools/git-hooks): pre-commit пересобирает вики, как на Mac; сайт выкладывает сам сервер (tools/server_pull)
git config core.hooksPath tools/git-hooks
