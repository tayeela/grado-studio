#!/usr/bin/env bash
# Показывает (и по флагу --yes удаляет на GitHub) ветки, целиком влитые в main или в team/t60: их коммиты остаются в истории,
# ничего не теряется. Не трогает main, team/t60 и ветки открытых PR. По умолчанию — только список (SHA рядом: ветку можно
# вернуть командой `git push origin <sha>:refs/heads/<имя>`).
#   tools/prune-merged-branches.sh          — список
#   tools/prune-merged-branches.sh --yes    — удалить перечисленные ветки
# Лучше включить и встроенную очистку GitHub: Settings → General → Pull Requests → «Automatically delete head branches».
set -eu
cd "$(git rev-parse --show-toplevel)"
git fetch -q origin
keep='^(main|team/t60|HEAD)$'
open_prs=$(gh api "repos/{owner}/{repo}/pulls?state=open&per_page=100" --paginate -q '.[].head.ref' 2>/dev/null || true)
count=0
# полное имя ссылки: короткое у refs/remotes/origin/HEAD — просто «origin» (10.10.2026 скрипт пытался удалить ветку «origin»)
for full in $(git for-each-ref --format='%(refname)' refs/remotes/origin); do
  b=${full#refs/remotes/origin/}; ref=origin/$b
  [[ $b =~ $keep ]] && continue
  printf '%s\n' "$open_prs" | grep -qx -- "$b" && continue
  git merge-base --is-ancestor "$ref" origin/main || git merge-base --is-ancestor "$ref" origin/team/t60 || continue
  printf '%s  %s\n' "$(git rev-parse --short=10 "$ref")" "$b"
  count=$((count + 1))
  if [ "${1:-}" = "--yes" ]; then git push -q origin --delete "$b"; fi
done
echo "влитых веток: $count$([ "${1:-}" = "--yes" ] && echo ' (удалены)' || echo ' (для удаления добавьте --yes)')"
