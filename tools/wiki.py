#!/usr/bin/env python3
"""Вики проекта ГРАДО 2 (docs/wiki/) — собирается из файлов репозитория, без сети и без кэша данных.

Зачем: агенту и человеку нужна короткая и всегда свежая сводка (что где лежит, какие источники данных, какие листы
и правила), вместо чтения больших файлов целиком. Страницы, помеченные «генерируется», переписываются этим
скриптом; architecture.md, recipes.md и album-rules.md пишутся руками и здесь не трогаются.

  python3 tools/wiki.py          — пересобрать docs/wiki/
  python3 tools/wiki.py --check  — код 1, если вики устарела (часть проверки tools/gate.sh)

Только стандартная библиотека; вывод детерминирован (без дат и времени), чтобы --check не ловил ложных отличий.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "apps" / "grado2"
WEB = APP / "web"
OUT = ROOT / "docs" / "wiki"
GEN = "<!-- генерируется tools/wiki.py — не править руками -->\n\n"


def read(p):
    try:
        return Path(p).read_text("utf-8")
    except OSError:
        return ""


def rel(p):
    return str(Path(p).relative_to(ROOT))


# ---------- источники данных (server.py SOURCES) ----------
def sources():
    s = read(APP / "server.py")
    rows = []
    for m in re.finditer(r'^SOURCES\["([^"]+)"\]\s*=\s*\(', s, re.M):
        i, depth = m.end() - 1, 0
        for j in range(i, len(s)):
            depth += {"(": 1, ")": -1}.get(s[j], 0)
            if depth == 0:
                break
        body = s[i:j + 1]
        strs = re.findall(r'"([^"\\]*)"', body)
        kind = strs[0] if strs else ""
        title = strs[-1] if strs else ""
        line = s.count("\n", 0, m.start()) + 1
        rows.append((m.group(1), kind, title, line))
    loops = re.findall(r'^for _k in \(([^)]*)\):', s, re.M)
    filt = sorted(set(re.findall(r'"([a-z_]+\.[a-z_0-9.]+)":\s*lambda', s)))
    lim = re.search(r"^LIMIT_KM2\s*=\s*(\{[^}]*\})", s, re.M)
    out = [GEN, "# Источники данных (server.py, SOURCES)\n\n",
           f"{len(rows)} ключей. Ключ слоя — `источник.имя`; вид — коннектор (gisogd, egko, nspd, osm, yandex…).\n\n",
           "| ключ | вид | название | строка |\n|---|---|---|---|\n"]
    out += [f"| `{k}` | {kind} | {t} | server.py:{ln} |\n" for k, kind, t, ln in sorted(rows)]
    if lim:
        out.append(f"\nПредел области выгрузки, км² (LIMIT_KM2): `{' '.join(lim.group(1).split())}`\n")
    if filt:
        out.append(f"\nСлои с фильтром объектов (SIT_FILTER): {', '.join(f'`{k}`' for k in filt)}\n")
    if loops:
        out.append("\nОбщие настройки задаются циклами `for _k in (…)` в server.py.\n")
    return "".join(out)


# ---------- листы альбомов (albums.js PPTKRT_C, sheets.js SEC1 / SIT) ----------
def _array_block(src, name):
    m = re.search(r"const " + re.escape(name) + r"\s*=\s*\[", src)
    if not m:
        return ""
    i, depth = m.end() - 1, 0
    for j in range(i, len(src)):
        depth += {"[": 1, "]": -1}.get(src[j], 0)
        if depth == 0:
            return src[i:j + 1]
    return ""


def _top_objects(block):
    objs, depth, start = [], 0, None
    for i, c in enumerate(block):
        if c == "{":
            if depth == 1:
                start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 1 and start is not None:
                objs.append(block[start:i + 1])
                start = None
        elif c == "[" and depth == 0:
            depth = 1
    return objs


def _sheet_rows(src, name):
    rows = []
    for o in _top_objects(_array_block(src, name)):
        t = re.search(r'title:\s*"([^"]*)"', o)
        keys = re.search(r"keys:\s*\[([^\]]*)\]", o)
        rows.append({
            "title": t.group(1) if t else "",
            "concept": (re.search(r'concept:\s*"([^"]*)"', o) or [None, ""])[1],
            "kind": (re.search(r'kind:\s*"([^"]*)"', o) or [None, ""])[1],
            "basemap": (re.search(r'basemap:\s*"([^"]*)"', o) or [None, ""])[1],
            "keys": re.findall(r'"([^"]+)"', keys.group(1)) if keys else [],
        })
    return rows


def sheets():
    a, s = read(WEB / "albums.js"), read(WEB / "sheets.js")
    out = [GEN, "# Листы альбомов\n\n",
           "Состав листов задают массивы ниже; дальнейший выбор (источник дорог, станции, районы, зоны) делает\n",
           "`conceptSheet` в albums.js по данным рамки листа. Подробно о правилах — rules.md.\n"]
    for title, src, name, first in (("План реализации ППТ КРТ, листы 3–9 (albums.js PPTKRT_C; 1 — титул, 2 — месторасположение)", a, "PPTKRT_C", 3),
                                    ("Раздел «Существующее положение» (sheets.js SEC1)", s, "SEC1", 1)):
        rows = _sheet_rows(src, name)
        out.append(f"\n## {title}\n\n| № | лист | concept / kind | основа | ключи слоёв |\n|---|---|---|---|---|\n")
        for n, r in enumerate(rows, first):
            ck = " / ".join(x for x in (r["concept"], r["kind"]) if x) or "—"
            out.append(f"| {n} | {r['title']} | {ck} | {r['basemap'] or 'белая'} | {', '.join(f'`{k}`' for k in r['keys'])} |\n")
    pushes = re.findall(r"PPTKRT_C\.forEach\(sh => \{([^\n]*)", a)
    if pushes:
        out.append("\n### Ключи, добавляемые всем листам ППТ КРТ (forEach в albums.js)\n\n")
        for p in pushes:
            ks = re.findall(r'"([a-z_]+\.[a-z_0-9.]+)"', p)
            out.append(f"- {', '.join(f'`{k}`' for k in dict.fromkeys(ks))}\n")
    concepts = sorted(set(re.findall(r'k === "([a-z]+)"', a)))
    if concepts:
        out.append(f"\nВетки conceptSheet по виду листа: {', '.join(f'`{c}`' for c in concepts)}.\n")
    return "".join(out)


# ---------- маршруты сервера ----------
def api():
    s = read(APP / "server.py")
    head = re.search(r'^"""(.*?)"""', s, re.S)
    routes = sorted(set(re.findall(r'"(/api/[a-z0-9_/]+)"', s)))
    out = [GEN, "# Маршруты сервера (server.py)\n\n"]
    if head:
        out.append("```\n" + head.group(1).strip() + "\n```\n\n")
    out.append(f"Все упомянутые в коде пути ({len(routes)}):\n\n")
    out += [f"- `{r}`\n" for r in routes]
    return "".join(out)


# ---------- модули: файл, строки, первый комментарий, функции ----------
def _lead_comment(text, py):
    if py:
        m = re.match(r'\s*(?:#[^\n]*\n)*\s*"""(.*?)"""', text, re.S)
        return (m.group(1).strip().split("\n\n")[0] if m else "").replace("\n", " ")
    m = re.match(r"\s*/\*(.*?)\*/", text, re.S)
    if m:
        return " ".join(m.group(1).split())
    lines = []
    for ln in text.splitlines():
        if ln.startswith("//"):
            lines.append(ln[2:].strip())
        elif lines or ln.strip():
            break
    return " ".join(lines)


def _functions(text, py):
    names = []
    if py:
        for m in re.finditer(r"^(?:class|def) (\w+)", text, re.M):
            names.append(m.group(1))
    else:
        for m in re.finditer(r"^(?:async )?function (\w+)|^const (\w+) = (?:async )?(?:\(|[a-z_]+ =>)", text, re.M):
            names.append(m.group(1) or m.group(2))
    return names


def modules():
    out = [GEN, "# Модули ГРАДО 2\n\n",
           "Файл — строк — назначение (первый комментарий файла) — функции и классы верхнего уровня.\n"]
    for title, files in (("Сервер и печать (apps/grado2/*.py)", sorted(APP.glob("*.py"))),
                         ("Страница (apps/grado2/web/*.js)", sorted(WEB.glob("*.js"))),
                         ("Ядро: коннекторы (core/connectors/grado_connectors)", sorted((ROOT / "core/connectors/grado_connectors").glob("*.py"))),
                         ("Ядро: печать (core/render/grado_render)", sorted((ROOT / "core/render/grado_render").glob("*.py")))):
        out.append(f"\n## {title}\n")
        for f in files:
            if f.name.startswith("_") and f.name != "__init__.py" or f.name == "__init__.py":
                continue
            t = read(f)
            py = f.suffix == ".py"
            lead = _lead_comment(t, py)
            fn = _functions(t, py)
            out.append(f"\n### `{rel(f)}` — {t.count(chr(10))} стр.\n\n")
            if lead:
                out.append(lead[:600] + ("…" if len(lead) > 600 else "") + "\n\n")
            if fn:
                out.append("Функции: " + ", ".join(f"`{n}`" for n in fn[:80]) + (f" и ещё {len(fn) - 80}" if len(fn) > 80 else "") + "\n")
    return "".join(out)


# ---------- правила оформления (label-rules.md) ----------
def rules():
    p = ROOT / "docs/standards/albums/label-rules.md"
    t = read(p)
    out = [GEN, "# Правила оформления альбома (свод)\n\n",
           f"Полный текст — `{rel(p)}` (решения владельца, главнее всего) и `docs/standards/albums/slide-layout-rules.md`.\n",
           "Здесь — первые строки пунктов, чтобы найти нужный.\n"]
    section = ""
    for ln in t.splitlines():
        if ln.startswith("## "):
            section = ln[3:].strip()
            out.append(f"\n## {section}\n\n")
        m = re.match(r"^(\d+[а-я]?)\. (.*)", ln)
        if m:
            out.append(f"- **{m.group(1)}.** {m.group(2)[:200]}\n")
    return "".join(out)


# ---------- тесты ----------
def tests():
    d = APP / "tests"
    out = [GEN, "# Тесты\n\n", "Запуск всего — `tools/gate.sh` (с E2E: `E2E=1 tools/gate.sh`).\n\n",
           "| файл | классы | проверок |\n|---|---|---|\n"]
    for f in sorted(d.glob("test_*.py")):
        t = read(f)
        cls = re.findall(r"^class (\w+)", t, re.M)
        out.append(f"| `{f.name}` | {', '.join(cls)} | {len(re.findall(r'^    def test_', t, re.M))} |\n")
    for f in sorted(d.glob("*_test.js")):
        t = read(f)
        out.append(f"| `{f.name}` | JS | {len(re.findall(r'(?:^|[^a-zA-Z])(?:eq|ok|check)\(', t))} |\n")
    e2e = read(d / "e2e" / "scenarios.mjs")
    groups = sorted(set(re.findall(r'p\.group\("([^"]+)"', e2e)))
    if groups:
        out.append(f"\nГруппы браузерных сценариев (E2E_ONLY=…): {', '.join(f'`{g}`' for g in groups)}\n")
    return "".join(out)


# ---------- команда: очередь и последние циклы ----------
def team():
    b, p = read(ROOT / "docs/team/BOARD.md"), read(ROOT / "docs/team/PROGRESS.md")
    out = [GEN, "# Команда: что ждёт, что в очереди, что готово\n\n",
           "Источник — docs/team/BOARD.md и PROGRESS.md (там же полные тексты).\n"]
    for sec in ("Ждёт владельца", "В работе", "Очередь", "Готово к выкладке"):
        m = re.search(r"^## " + sec + r"\n(.*?)(?=^## |\Z)", b, re.S | re.M)
        if m:
            body = m.group(1).strip()
            out.append(f"\n## {sec}\n\n{body}\n")
    rules_ = re.findall(r"^RULE: .*(?:\n(?!RULE:|- |\n).*)*", p, re.M)
    if rules_:
        out.append("\n## Правила команды (RULE из PROGRESS.md)\n\n")
        out += [f"- {' '.join(r[6:].split())}\n" for r in rules_]
    cycles = re.findall(r"^- \d\d\.\d\d\.\d{4}.*(?:\n  .*)*", p, re.M)[:2]
    if cycles:
        out.append("\n## Последние циклы\n\n" + "\n".join(cycles) + "\n")
    return "".join(out)


# ---------- журнал: последние записи ----------
def changelog():
    t = read(ROOT / "docs/grado2-changelog.md")
    heads = re.findall(r"^- \*\*(.+?)\*\*", t, re.M)[:20]
    return GEN + "# Последние изменения (docs/grado2-changelog.md, сверху — новые)\n\n" + "".join(f"- {h}\n" for h in heads)


# ---------- оглавление ----------
def index():
    ver = json.loads(read(WEB / "version.json") or "{}").get("version", "?")
    return (GEN + f"# Вики ГРАДО 2 (версия {ver})\n\n"
            "Начинать отсюда. Страницы короткие и собираются из кода при каждом коммите (`tools/wiki.py`).\n\n"
            "| страница | что там |\n|---|---|\n"
            "| [architecture.md](architecture.md) | как устроена программа: части, данные, печать (вручную) |\n"
            "| [album-rules.md](album-rules.md) | **свод правил альбома ППТ КРТ — читать до любой работы с листами** (вручную) |\n"
            "| [recipes.md](recipes.md) | как: проверить, собрать альбом на тестовой копии, выложить, срочно исправить (вручную) |\n"
            "| [sources.md](sources.md) | источники данных: ключи слоёв, порталы, пределы |\n"
            "| [sheets.md](sheets.md) | листы альбомов: состав, ключи слоёв, основа |\n"
            "| [rules.md](rules.md) | правила оформления владельца — пункты по номерам |\n"
            "| [modules.md](modules.md) | файлы кода: назначение и функции |\n"
            "| [api.md](api.md) | маршруты сервера |\n"
            "| [tests.md](tests.md) | тесты и группы браузерных сценариев |\n"
            "| [team.md](team.md) | очередь команды, ждёт владельца, готово к выкладке, правила команды |\n"
            "| [changelog-recent.md](changelog-recent.md) | 20 последних записей журнала |\n")


PAGES = {"INDEX.md": index, "sources.md": sources, "sheets.md": sheets, "api.md": api, "modules.md": modules,
         "rules.md": rules, "tests.md": tests, "team.md": team, "changelog-recent.md": changelog}


def main(argv):
    check = "--check" in argv
    stale = []
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in PAGES.items():
        text = fn()
        p = OUT / name
        if read(p) != text:
            stale.append(name)
            if not check:
                p.write_text(text, "utf-8")
    if check:
        if stale:
            print("wiki: stale pages: " + ", ".join(stale) + " — run python3 tools/wiki.py")
            return 1
        print("wiki: up to date")
        return 0
    print("wiki: " + (("updated " + ", ".join(stale)) if stale else "no changes"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
