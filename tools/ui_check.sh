#!/usr/bin/env bash
# Проверка, что собранный новый интерфейс (apps/grado2/web/next) совпадает с исходниками apps/grado2/ui.
# Вызывают tools/gate.sh (шаг ui, если есть apps/grado2/ui/node_modules) и CI grado2-release.yml. Пересобирает и сравнивает с git.
set -euo pipefail
cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)/apps/grado2/ui"
[ -d node_modules ] || npm ci --no-audit --no-fund
npm run build --silent >/dev/null
cd ../web/next
if ! git diff --quiet -- . || [ -n "$(git ls-files --others --exclude-standard -- .)" ]; then
  echo "STEP FAILED: apps/grado2/web/next отличается от сборки — запустите (cd apps/grado2/ui && npm run build) и закоммитьте"
  git status --short -- . | head -20
  exit 1
fi
echo "ui: build is fresh"
