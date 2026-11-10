#!/usr/bin/env bash
# Проверка ГРАДО 2 одной командой (перед каждым коммитом программы и перед выкладкой):
#   tools/gate.sh          — unit с PYTHONPATH и без, коннекторы и остальное ядро, свежесть вики, навигация документов (tools/docs_check.py),
#                            свежесть сборки нового интерфейса (tools/ui_check.sh)
#   E2E=1 tools/gate.sh    — плюс браузерные сценарии (≈6 мин) и проверка раскладки нового интерфейса (tools/ui_layout_check.mjs, ≈3 мин);
#                            E2E_ONLY=t71,t82 — только эти группы
# Печатает по строке на шаг и итог «GATE: OK» или «GATE: FAIL (шаги)». Код выхода 1 при сбое.
# Тесты идут под pytest (apps/grado2/requirements-dev.txt); без него — тем же набором через unittest.
# Браузерные сценарии: Playwright из tools/node_modules — (cd tools && npm ci).
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)" || exit 2
PY=${PY:-$HOME/.grado2/venv/bin/python}
PP="core/render:core/geom:core/layout:core/compute:core/model:core/reactive:core/connectors:apps/grado2"
LOG=${GATE_LOG:-/tmp/grado-gate}; mkdir -p "$LOG"
fail=()
step() {  # имя, команда…
  local name=$1; shift
  if "$@" >"$LOG/$name.log" 2>&1; then echo "ok   $name — $(grep -E '^(Ran|OK|wiki:|ui-layout:)| passed| skipped' "$LOG/$name.log" | tail -1 | tr -d '=')"
  else echo "FAIL $name — $LOG/$name.log"; grep -E 'STEP FAILED|^FAIL:|^ERROR:|^FAILED |^ERROR |stale' "$LOG/$name.log" | sort -u | head -8; fail+=("$name"); fi
}
if "$PY" -c "import pytest" 2>/dev/null; then T="-m pytest -q -p no:cacheprovider"; else T="-m unittest discover -s"; echo "note pytest не установлен: $PY -m pip install -r apps/grado2/requirements-dev.txt"; fi
step wiki       "$PY" tools/wiki.py --check
step docs       "$PY" tools/docs_check.py
step ruff       "$PY" -m ruff check apps/grado2 core tools
step unit       env PYTHONPATH="$PP" "$PY" $T apps/grado2/tests
step unit-bare  bash -c "cd apps/grado2 && env -u PYTHONPATH '$PY' $T tests"
step connectors env PYTHONPATH="$PP" "$PY" $T core/connectors/tests
step core       bash -c "set -e; for m in compute geom layout model reactive render; do PYTHONPATH='$PP' '$PY' $T core/\$m/tests; done"
# правки интерфейса в рабочем дереве? без node_modules проверка типов и сборки молча пропускалась (аудит 06.11, 1.4)
UI_TOUCHED=$(git diff HEAD --name-only -- apps/grado2/ui "apps/grado2/web/*.js" | wc -l | tr -d ' ')
HAVE_NODE=0; command -v node >/dev/null 2>&1 && HAVE_NODE=1
if [ -x tools/node_modules/.bin/tsc ] && [ "$HAVE_NODE" = 1 ]; then  # files with // @ts-check in apps/grado2/web; install: (cd tools && npm ci)
  step types    tools/node_modules/.bin/tsc -p tools/ts/tsconfig.json
elif [ "$HAVE_NODE" = 0 ] && [ -x tools/node_modules/.bin/tsc ]; then
  echo "skip types — node_modules есть, но node не в PATH"
elif [ "$UI_TOUCHED" != 0 ]; then
  echo "FAIL types — правки интерфейса есть, а tools/node_modules нет: (cd tools && npm ci)"; fail+=(types)
else echo "skip types — no tools/node_modules (cd tools && npm ci)"; fi
if [ -d apps/grado2/ui/node_modules ] && [ "$HAVE_NODE" = 1 ]; then  # новый интерфейс: собранное совпадает с исходниками; install: (cd apps/grado2/ui && npm ci)
  step ui       tools/ui_check.sh
elif [ "$HAVE_NODE" = 0 ] && [ -d apps/grado2/ui/node_modules ]; then
  echo "skip ui — node_modules есть, но node не в PATH"
elif [ "$UI_TOUCHED" != 0 ]; then
  echo "FAIL ui — правки интерфейса есть, а apps/grado2/ui/node_modules нет: (cd apps/grado2/ui && npm ci)"; fail+=(ui)
else echo "skip ui — no apps/grado2/ui/node_modules (cd apps/grado2/ui && npm ci)"; fi
UI3_TOUCHED=$(git diff HEAD --name-only -- apps/grado3/ui apps/grado2/web/g3 | wc -l | tr -d ' ')
if [ -d apps/grado3/ui/node_modules ] && [ "$HAVE_NODE" = 1 ]; then  # новый интерфейс /g3/ (план 09.11.2026): типы, тесты, свежая сборка; install: (cd apps/grado3/ui && npm ci)
  step ui3      tools/ui3_check.sh
elif [ "$UI3_TOUCHED" != 0 ]; then
  echo "FAIL ui3 — правки /g3/ есть, а apps/grado3/ui/node_modules нет: (cd apps/grado3/ui && npm ci)"; fail+=(ui3)
else echo "skip ui3 — no apps/grado3/ui/node_modules (cd apps/grado3/ui && npm ci)"; fi
if [ "${E2E:-}" = 1 ] || [ -n "${E2E_ONLY:-}" ]; then
  # драйвер сценариев (tests/e2e/driver.mjs) берёт module.registerHooks — он есть только в Node 22+
  if [ "$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)" -lt 22 ]; then
    echo "FAIL e2e — нужен Node 22 или новее, сейчас $(node -v 2>/dev/null || echo 'node не найден')"; fail+=(e2e-node)
  else
    step e2e      env PYTHONPATH="$PP" GATE_LOG="$LOG" GRADO2_E2E=1 "$PY" -m unittest apps/grado2/tests/test_e2e.py
  fi
  [ -d apps/grado2/ui/node_modules ] && step ui-layout node tools/ui_layout_check.mjs --out "$LOG/ui-layout"   # окна нового интерфейса по docs/ux/ui-grid.md
fi
# скипы в итогах (аудит 06.11, 1.9): «покрытие упало незаметно» становится видимым — число в скобках растёт
SKIPPED=$(cat "$LOG/unit.log" "$LOG/unit-bare.log" "$LOG/connectors.log" "$LOG/core.log" "$LOG/e2e.log" 2>/dev/null \
  | grep -oE '[0-9]+ skipped|skipped=[0-9]+' | grep -oE '[0-9]+' | awk '{s+=$1} END {print s+0}')
if [ ${#fail[@]} -eq 0 ]; then echo "GATE: OK (скипы тестов: $SKIPPED)"; else echo "GATE: FAIL (${fail[*]})"; exit 1; fi
