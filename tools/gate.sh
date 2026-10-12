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
step wiki       python3 tools/wiki.py --check
step docs       python3 tools/docs_check.py
step unit       env PYTHONPATH="$PP" "$PY" $T apps/grado2/tests
step unit-bare  bash -c "cd apps/grado2 && env -u PYTHONPATH '$PY' $T tests"
step connectors env PYTHONPATH="$PP" "$PY" $T core/connectors/tests
step core       bash -c "set -e; for m in compute geom layout model reactive render; do PYTHONPATH='$PP' '$PY' $T core/\$m/tests; done"
if [ -x tools/node_modules/.bin/tsc ]; then  # files with // @ts-check in apps/grado2/web; install: (cd tools && npm ci)
  step types    tools/node_modules/.bin/tsc -p tools/ts/tsconfig.json
else echo "skip types — no tools/node_modules (cd tools && npm ci)"; fi
if [ -d apps/grado2/ui/node_modules ]; then  # новый интерфейс: собранное совпадает с исходниками; install: (cd apps/grado2/ui && npm ci)
  step ui       tools/ui_check.sh
else echo "skip ui — no apps/grado2/ui/node_modules (cd apps/grado2/ui && npm ci)"; fi
if [ "${E2E:-}" = 1 ] || [ -n "${E2E_ONLY:-}" ]; then
  # драйвер сценариев (tests/e2e/driver.mjs) берёт module.registerHooks — он есть только в Node 22+
  if [ "$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)" -lt 22 ]; then
    echo "FAIL e2e — нужен Node 22 или новее, сейчас $(node -v 2>/dev/null || echo 'node не найден')"; fail+=(e2e-node)
  else
    step e2e      env PYTHONPATH="$PP" GATE_LOG="$LOG" GRADO2_E2E=1 "$PY" -m unittest apps/grado2/tests/test_e2e.py
  fi
  [ -d apps/grado2/ui/node_modules ] && step ui-layout node tools/ui_layout_check.mjs --out "$LOG/ui-layout"   # окна нового интерфейса по docs/ux/ui-grid.md
fi
if [ ${#fail[@]} -eq 0 ]; then echo "GATE: OK"; else echo "GATE: FAIL (${fail[*]})"; exit 1; fi
