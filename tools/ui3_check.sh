#!/usr/bin/env bash
# Новый интерфейс ГРАДО (apps/grado3/ui, план 09.11.2026): проверка типов TypeScript (vue-tsc), тесты (Vitest: шина команд,
# команды, ядро Rust в WebAssembly против эталона Python) и свежесть сборки apps/grado2/web/g3. Вызывают tools/gate.sh
# (шаг ui3, если есть apps/grado3/ui/node_modules) и CI grado2-release.yml.
set -euo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)/apps/grado3/ui"
[ -d node_modules ] || npm ci --no-audit --no-fund
npx vitest run --silent
npm run build --silent >/dev/null
cd ../../grado2/web/g3
if ! git diff --quiet -- . || [ -n "$(git ls-files --others --exclude-standard -- .)" ]; then
  echo "STEP FAILED: apps/grado2/web/g3 отличается от сборки — запустите (cd apps/grado3/ui && npm run build) и закоммитьте"
  git status --short -- . | head -20
  exit 1
fi
echo "ui3: types ok, tests ok, build is fresh"
