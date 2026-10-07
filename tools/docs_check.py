#!/usr/bin/env python3
"""Проверка навигации репозитория: ссылки, пути, оглавления, заголовки файлов (шаг `docs` в tools/gate.sh и в CI).

Зачем: документы и первые строки файлов — карта для человека и ИИ-агента; карта, которая врёт, хуже, чем её отсутствие.
Проверка ловит устаревшее сразу (при правке или слиянии), а не когда агент уже пошёл по битой ссылке.

  python3 tools/docs_check.py          — проверить всё, код 1 при нарушениях
  python3 tools/docs_check.py --rules  — напечатать правила и исключения

Правила:
  links   ссылка Markdown [текст](путь) ведёт на существующий файл или папку
  paths   путь в `обратных кавычках`, начинающийся с известной папки (apps/, core/, docs/, tools/ …), существует
  root    каждый файл и папка верхнего уровня названы в INDEX.md
  readme  у каждой папки из READMES есть README.md (или INDEX.md)
  index   каждый .md в docs/ назван в docs/INDEX.md или в README своей папки (ничто не лежит «ни на какой полке»)
  header  файл кода начинается с комментария «что это» (py — docstring или #-комментарий, js/mjs — // или /* */, sh — #)
Журналы и архив (JOURNALS) описывают прошлое и правилами links/paths не проверяются; закрытые программы (CLOSED) —
правилом header. Исключения заводятся здесь, с причиной, а не молчаливым пропуском.

Только стандартная библиотека; смотрит файлы git (отслеженные и новые, не игнорируемые), поэтому работает до `git add`.
"""
import ast
import fnmatch
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent

# Папки, где обязателен README.md (или INDEX.md): вход «что здесь лежит» для человека и ИИ.
READMES = ["apps", "apps/grado2", "core", "docs", "tools", "tools/git-hooks", "packaging", ".claude", ".github/workflows",
           "docs/guides", "docs/product", "docs/specs", "docs/ux", "docs/standards", "docs/archive", "docs/team", "docs/wiki"]
# Начала путей, которые правило paths проверяет в тексте документов.
KNOWN_ROOTS = ("apps/", "core/", "docs/", "tools/", "packaging/", ".claude/", ".github/")
# Пути из текста, которых в репозитории нет по замыслу: локальные копии на Mac, файлы только на машине владельца.
LOCAL_ONLY = (".claude/worktrees/", ".claude/launch.json", ".claude/.grado2_ux_audited", "apps/studio/.")
# Журналы и архив: рассказывают о прошлом (путь мог исчезнуть после переноса) — links и paths не проверяются.
JOURNALS = ("docs/grado2-changelog.md", "docs/session-log-archive.md", "docs/team/PROGRESS.md", "docs/team/BOARD.md",
            "docs/team/OWNER.md", "docs/team/DECISIONS.md", "docs/archive/", "docs/team/samples/", "docs/team/mockups/",
            "docs/standards/moscow-ngp/")
# .md в docs/, которые правило index не требует перечислять: сгенерированная вики, данные-стандарты, шаблоны заданий, журналы.
NOT_INDEXED = ("docs/wiki/", "docs/standards/", "docs/team/prompts/", "docs/team/samples/", "docs/team/mockups/", "docs/archive/")
# Закрытые программы (23.09.2026): не развиваются, заголовки им не нужны. Сторонний код и данные — тоже.
CLOSED = ("apps/studio/", "apps/wizard/", "apps/calc-web/")
HEADER_SKIP = CLOSED + ("apps/grado2/web/vendor/", "apps/grado2/tests/fixtures/", "docs/", "core/render/grado_render/styles/")
CODE_SUFFIXES = (".py", ".js", ".mjs", ".sh")


def git_files():
    out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return sorted(f for f in out.split("\0") if f and (ROOT / f).exists())


FILES = git_files()
FILESET = set(FILES)
DIRS = {str(p) for f in FILES for p in map(str, Path(f).parents) if p != "."}
errors = []


def err(rule, where, what):
    errors.append(f"{rule:7s} {where}: {what}")


def is_journal(path):
    return path.startswith(JOURNALS)


def exists(path):
    path = path.rstrip("/")
    return path in FILESET or path in DIRS


def prose(text):
    """Текст Markdown без блоков кода: примеры команд в ``` не ссылки и не обещания."""
    out, fenced = [], False
    for ln in text.splitlines():
        if ln.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            out.append(ln)
    return out


LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
TICK = re.compile(r"`([^`\n]+)`")


def check_markdown(path):
    text = (ROOT / path).read_text("utf-8", "replace")
    base = Path(path).parent
    for n, ln in enumerate(prose(text), 1):
        for m in LINK.finditer(ln):
            href = m.group(1)
            if re.match(r"[a-z][a-z0-9+.-]*:", href, re.I) or href.startswith("#"):
                continue
            target = unquote(href.split("#")[0].split("?")[0])
            if not target:
                continue
            full = target.lstrip("/") if target.startswith("/") else (base / target).as_posix()
            full = re.sub(r"(^|/)\./", r"\1", full)
            parts = []
            for seg in full.split("/"):                       # убрать «папка/..»
                if seg == "..":
                    if parts:
                        parts.pop()
                else:
                    parts.append(seg)
            if not exists("/".join(parts)):
                err("links", f"{path}:{n}", f"ссылка на несуществующее «{href}»")
        for m in TICK.finditer(ln):
            raw = m.group(1).strip()
            if not raw.startswith(KNOWN_ROOTS) or raw.startswith(LOCAL_ONLY):
                continue
            cand = [raw] + ([raw.split()[0]] if " " in raw else [])
            ok = False
            for c in cand:
                c = c.rstrip(".,;:)»")
                c = re.sub(r":\d+(-\d+)?$", "", c)            # server.py:172 → server.py
                if any(ch in c for ch in "<>{}$|~…") or c.startswith(LOCAL_ONLY):
                    ok = True
                elif "*" in c:
                    ok = any(fnmatch.fnmatch(f, c) for f in FILES)
                else:
                    ok = exists(c)
                if ok:
                    break
            if not ok:
                err("paths", f"{path}:{n}", f"путь `{raw}` не найден в репозитории")


def check_readmes():
    for d in READMES:
        if not any(f"{d}/{n}" in FILESET for n in ("README.md", "INDEX.md")):
            err("readme", d + "/", "нет README.md — добавьте «что здесь лежит» (docs/CLAUDE.md, раздел «Полки»)")


def check_root():
    idx = (ROOT / "INDEX.md").read_text("utf-8", "replace") if "INDEX.md" in FILESET else ""
    for top in sorted({f.split("/")[0] for f in FILES}):
        name = top + "/" if top in DIRS else top
        if name not in idx:
            err("root", top, "не назван в INDEX.md — добавьте строку в карту репозитория")


def check_index():
    index_text = (ROOT / "docs/INDEX.md").read_text("utf-8", "replace") if "docs/INDEX.md" in FILESET else ""
    for f in FILES:
        if not (f.startswith("docs/") and f.endswith(".md")) or f.startswith(NOT_INDEXED):
            continue
        d = str(Path(f).parent)
        name = Path(f).name
        if name in ("README.md", "INDEX.md", "CLAUDE.md"):
            continue
        shelf = ""
        for cand in (f"{d}/README.md", f"{d}/INDEX.md"):
            if cand in FILESET:
                shelf += (ROOT / cand).read_text("utf-8", "replace")
        if name not in index_text and name not in shelf:
            err("index", f, "не назван ни в docs/INDEX.md, ни в README своей полки")


def lead_ok(path, text):
    if path.endswith(".py"):
        try:
            if (ast.get_docstring(ast.parse(text)) or "").strip():
                return True
        except SyntaxError:
            pass
        body = [ln for ln in text.splitlines() if not ln.startswith("#!") and "coding" not in ln[:20]]
        return bool(body) and body[0].startswith("#") and len(body[0].strip("# ")) >= 12
    lines = text.splitlines()
    if path.endswith(".sh"):
        return any(ln.startswith("#") and not ln.startswith("#!") and len(ln.strip("# ")) >= 12 for ln in lines[:6])
    first = next((ln.strip() for ln in lines if ln.strip()), "")
    return first.startswith("//") or first.startswith("/*")


def check_headers():
    for f in FILES:
        if not f.endswith(CODE_SUFFIXES) or f.startswith(HEADER_SKIP) or f.endswith("__init__.py"):
            continue
        text = (ROOT / f).read_text("utf-8", "replace")
        if text.strip() and not lead_ok(f, text):
            err("header", f, "нет заголовка: первой строкой — что делает файл и кто его вызывает (docs/CLAUDE.md, «Заголовок файла»)")


def main(argv):
    if "--rules" in argv:
        print(__doc__)
        return 0
    for f in FILES:
        if f.endswith(".md") and not is_journal(f):
            check_markdown(f)
    check_root()
    check_readmes()
    check_index()
    check_headers()
    if errors:
        print(f"docs: {len(errors)} нарушений")
        for e in errors[:200]:
            print("  " + e)
        if len(errors) > 200:
            print(f"  … и ещё {len(errors) - 200}")
        return 1
    print("docs: навигация в порядке")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
