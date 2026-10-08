#!/bin/bash
# Выкладка вики ГРАДО в приватный репозиторий GitHub tayeela/grado-wiki (владелец 06.10.2026: «выложи вики с удобной
# навигацией для ИИ на гитхаб»). Копирует docs/wiki, добавляет README.md (вход для человека и ИИ), llms.txt (список
# страниц для ИИ) и AGENTS.md (как работать). Без изменений ничего не пушит; ошибки сети не мешают коммиту.
#
# Кто запускает (везде одна и та же вики, последний запуск побеждает):
#   * GitHub Actions — .github/workflows/wiki.yml на каждый пуш в team/t60 (нужен секрет WIKI_TOKEN, см. docs/wiki/recipes.md);
#   * Mac владельца — хук post-commit, если коммит менял docs/wiki (в ветках main и team/t60);
#   * облачная сессия или вручную — tools/wiki_publish.sh (доступ к tayeela/grado-wiki даёт сама сессия).
# Как берётся доступ: WIKI_TOKEN (Actions) → gh auth (Mac) → обычный git (облачная сессия).
# Папка копии вики — WIKI_DEST (по умолчанию ~/.grado2/wiki-repo).
set -u
ROOT=$(git rev-parse --show-toplevel) || exit 0
# хук git выставляет GIT_DIR/GIT_INDEX_FILE: без сброса команды git ниже работали бы с репозиторием программы, а не вики
# (06.10.2026 так в ветку команды попал коммит, заменивший программу страницами вики)
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_PREFIX GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR
REPO="tayeela/grado-wiki"
DEST="${WIKI_DEST:-$HOME/.grado2/wiki-repo}"

# откуда клонировать и куда пушить
if [ -n "${WIKI_TOKEN:-}" ]; then
  URL="https://x-access-token:${WIKI_TOKEN}@github.com/$REPO.git"
else
  URL="https://github.com/$REPO.git"
fi
if [ ! -d "$DEST/.git" ]; then
  mkdir -p "$(dirname "$DEST")"
  if [ -z "${WIKI_TOKEN:-}" ] && command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    gh repo view "$REPO" >/dev/null 2>&1 || gh repo create "$REPO" --private -d "Вики ГРАДО 2: навигация по коду, правила альбома, карта файлов" >/dev/null || exit 0
    gh repo clone "$REPO" "$DEST" >/dev/null 2>&1 || git clone -q "$URL" "$DEST" >/dev/null 2>&1 || exit 0
  else
    git clone -q "$URL" "$DEST" >/dev/null 2>&1 || exit 0
  fi
fi
cd "$DEST" || exit 0
# защита: работаем только в репозитории вики
[ "$(git rev-parse --show-toplevel 2>/dev/null)" = "$(cd "$DEST" && pwd -P)" ] || exit 0
git remote get-url origin 2>/dev/null | grep -q 'grado-wiki' || exit 0
[ -n "${WIKI_TOKEN:-}" ] && git remote set-url origin "$URL"
git config user.name  >/dev/null 2>&1 || git config user.name  "grado-wiki-bot"
git config user.email >/dev/null 2>&1 || git config user.email "grado-wiki-bot@users.noreply.github.com"
git pull -q --rebase origin main 2>/dev/null || true

find . -maxdepth 1 -name "*.md" -delete; rm -f llms.txt
cp "$ROOT"/docs/wiki/*.md .
BR=${GITHUB_REF_NAME:-$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)}; SHA=$(git -C "$ROOT" rev-parse --short HEAD)
VER=$(python3 -c "import json;print(json.load(open('$ROOT/apps/grado2/web/version.json'))['version'])" 2>/dev/null || echo "?")
python3 - "$BR" "$SHA" "$VER" <<'PY'
import re, sys, pathlib
br, sha, ver = sys.argv[1:4]
idx = pathlib.Path("INDEX.md").read_text()
rows = re.findall(r"^\| \[([^\]]+)\]\(([^)]+)\) \| (.+?) \|$", idx, re.M)
head = (f"# Вики ГРАДО 2\n\nВерсия программы {ver}, ветка `{br}`, коммит `{sha}` репозитория `tayeela/grado-studio`.\n"
        "Копия `docs/wiki` из репозитория программы. Обновляется сама: GitHub Actions (`.github/workflows/wiki.yml`) "
        "пересобирает страницы из кода на каждый пуш в `team/t60` и кладёт сюда. Править здесь нечего — правки только в репозитории программы.\n\n")
nav = ("## Как пользоваться (человеку и ИИ)\n\n"
       "1. Не знаете, где искать, — [files.md](files.md): вопрос → файл, места на Mac владельца, ветки.\n"
       "2. Любая работа с альбомом ППТ КРТ — сначала [album-rules.md](album-rules.md): свод правил владельца.\n"
       "3. Как устроена программа — [architecture.md](architecture.md); как проверить и выложить — [recipes.md](recipes.md).\n"
       "4. Конкретика из кода — sources, sheets, modules, api, tests (ниже). Читать страницы, а не большие файлы целиком.\n"
       "5. Правила работы для ИИ-агента — [AGENTS.md](AGENTS.md).\n\n## Страницы\n\n| страница | что там |\n|---|---|\n")
pathlib.Path("README.md").write_text(head + nav + "".join(f"| [{n}]({l}) | {d} |\n" for n, l, d in rows))
pathlib.Path("llms.txt").write_text(f"# ГРАДО 2 — вики (версия {ver})\n\n> Градостроительная программа: существующее положение, альбом ППТ КРТ, PDF/PPTX. "
    "Код — tayeela/grado-studio. Начинать с files.md и album-rules.md.\n\n## Pages\n\n"
    + "".join(f"- [{n}]({l}): {re.sub(r'[*]', '', d)}\n" for n, l, d in rows))
pathlib.Path("AGENTS.md").write_text(
"# Как работать ИИ-агенту с ГРАДО 2\n\n"
"- Код — репозиторий `tayeela/grado-studio`; правила репозитория — его `CLAUDE.md`, карта папок — `INDEX.md`, карта документов — `docs/INDEX.md`.\n"
"- Вход — [files.md](files.md) (где что лежит) и [INDEX.md](INDEX.md). Страницы короткие; большие файлы кода читать кусками.\n"
"- Альбом ППТ КРТ: до любой правки — [album-rules.md](album-rules.md); новое замечание владельца — сначала в свод и в "
"`docs/standards/albums/label-rules.md`, потом код, потом настоящая пересборка на копии проекта и постраничное сравнение PDF.\n"
"- Нельзя: проекты владельца `~/Documents/ГРАДО 2`, его сервер на порту 8650, удаление кэша `~/.grado2/cache` без спроса.\n"
"- Проверка перед коммитом — `tools/gate.sh`; на сайт — только по слову владельца «выкладывай».\n"
"- Владелец — градостроитель, не программист: ответы по-русски, простыми словами, вопросы — вариантами А/Б/В.\n")
PY
git add -A
if git diff --cached --quiet; then exit 0; fi
git commit -qm "wiki: $BR $SHA (v$VER)"
git push -q origin HEAD:main 2>/dev/null || { git pull -q --rebase origin main 2>/dev/null && git push -q origin HEAD:main 2>/dev/null; } || true
