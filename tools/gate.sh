#!/usr/bin/env bash
# Проверка ГРАДО 2 одной командой (перед каждым коммитом программы и перед выкладкой):
#   tools/gate.sh          — unit с PYTHONPATH и без, коннекторы, свежесть вики
#   E2E=1 tools/gate.sh    — плюс браузерные сценарии (≈6 мин); E2E_ONLY=t71,t82 — только эти группы
# Печатает по строке на шаг и итог «GATE: OK» или «GATE: FAIL (шаги)». Код выхода 1 при сбое.
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)" || exit 2
PY=${PY:-$HOME/.grado2/venv/bin/python}
PP="core/render:core/geom:core/layout:core/compute:core/model:core/reactive:core/connectors:apps/grado2"
LOG=${GATE_LOG:-/tmp/grado-gate}; mkdir -p "$LOG"
fail=()
step() {  # имя, команда…
  local name=$1; shift
  if "$@" >"$LOG/$name.log" 2>&1; then echo "ok   $name — $(grep -E '^(Ran|OK|wiki:)' "$LOG/$name.log" | tail -1)"
  else echo "FAIL $name — $LOG/$name.log"; grep -E 'STEP FAILED|^FAIL:|^ERROR:|stale' "$LOG/$name.log" | sort -u | head -8; fail+=("$name"); fi
}
step wiki       python3 tools/wiki.py --check
step unit       env PYTHONPATH="$PP" "$PY" -m unittest discover -s apps/grado2/tests -p "test_*.py"
step unit-bare  bash -c "cd apps/grado2 && env -u PYTHONPATH '$PY' -m unittest discover -s tests -p 'test_*.py'"
step connectors env PYTHONPATH="$PP" "$PY" -m unittest discover -s core/connectors/tests -p "test_*.py"
if [ "${E2E:-}" = 1 ] || [ -n "${E2E_ONLY:-}" ]; then
  step e2e      env PYTHONPATH="$PP" GRADO2_E2E=1 "$PY" -m unittest apps/grado2/tests/test_e2e.py
fi
if [ ${#fail[@]} -eq 0 ]; then echo "GATE: OK"; else echo "GATE: FAIL (${fail[*]})"; exit 1; fi
