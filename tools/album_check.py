#!/usr/bin/env python3
"""Визуальная проверка альбома «до / после» (06.10.2026): печать PDF по спецификации на тестовом сервере, страницы в PNG,
постраничное сравнение с эталоном, вырезки изменённых мест и свод одной картинкой.

Заменяет ручной цикл приёмки (PROGRESS RULE: правка альбома принимается только после пересборки и постраничного
сравнения PDF). Спецификацию сохраняет страница: `fetch('/api/project?name=_specX', {method:'POST',
body: JSON.stringify(albumSpec(ALBUM.sheets))})` (docs/wiki/recipes.md).

  ~/.grado2/venv/bin/python tools/album_check.py --spec <папка проектов>/_specX.grado2 --name gol \
      [--server http://localhost:8671] [--update]      # --update: текущий результат становится эталоном

Эталоны: ~/.grado2/album-baseline/<name>/p-N.png, копия на GitHub — релиз `album-baseline` репозитория (архив
<name>.zip): нет на диске — скачивается оттуда, `--update` — выкладывается туда (процесс на GitHub, 06.10.2026); отчёт: /tmp/grado-album-check/<name>/ (report.md, summary.png,
crops/). Заодно альбом проверяет tools/album_lint.py: PDF (наложения слов, края листа и рамки карты, мелкий кегль, переносы, «ё», шрифты, разрешение растров),
PPTX (неразрывные пробелы; его печатает та же команда, отключается --no-pptx) и контрольные строки tools/album_expect/all.json и <имя>.json. Отчёт — в конце
report.md, там же самопроверка печати (#55: подписи под угловыми надписями и легендой, у рамки карты, подписанные дважды; не меняет код выхода). Код выхода 0 — без отличий (или --update), 1 — есть отличия (смотреть summary.png), 2 — ошибка печати,
3 — album_lint нашёл ошибки оформления (важнее отличий: их чинят, а не принимают эталоном).
Ошибки сервера печатаются как есть; порт 8650 (программа владельца) запрещён.
"""
import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import album_lint

FONT = next((str(p) for p in (Path(__file__).resolve().parents[1] / "docs" / "standards" / "fonts").glob("Montserrat*Regular*.ttf")), None)


def _font(size=14):
    try:
        return ImageFont.truetype(FONT, size) if FONT else ImageFont.load_default()
    except OSError:
        return ImageFont.load_default()

BASE = Path.home() / ".grado2" / "album-baseline"
OUT = Path("/tmp/grado-album-check")
DPI = 100            # для сравнения достаточно; вырезки — из этих же страниц
THRESH = 24          # разница яркости, ниже которой пиксель «тот же» (сглаживание шрифтов)


def render(server, spec, path, kind="pdf"):
    """Печать альбома по спецификации: kind "pdf" — обязательно (ошибка → код 2), "pptx" — по возможности (ошибка → None, проверка презентации пропущена)."""
    if ":8650" in server:
        sys.exit("port 8650 is the owner's program: use a test server (8651+)")
    req = urllib.request.Request(server.rstrip("/") + f"/api/print/{kind}", data=Path(spec).read_bytes(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=1800) as r:
            data = r.read()
            if kind == "pdf":
                QA[:] = layout_qa(r.headers)
    except OSError as e:
        if kind == "pdf":
            raise
        print(f"PPTX не напечатан ({e}); неразрывные пробелы не проверены", file=sys.stderr)
        return None
    if not data.startswith(b"%PDF" if kind == "pdf" else b"PK"):
        print(data[:400].decode("utf-8", "replace"), file=sys.stderr)
        if kind == "pdf":
            sys.exit(2)
        return None
    path.write_bytes(data)
    return path


QA = []               # самопроверка оформления из ответа печати PDF (#55): строки отчёта


def layout_qa(headers):
    """Места самопроверки оформления (сервер: X-Grado-Layout-QA «лист:мест», X-Grado-Layout-QA-Why JSON в %XX) — строки отчёта."""
    from urllib.parse import unquote
    count = headers.get("X-Grado-Layout-QA") or ""
    try:
        why = json.loads(unquote(headers.get("X-Grado-Layout-QA-Why") or "{}"))
    except ValueError:
        why = {}
    out = []
    for part in filter(None, count.split(",")):
        n, k = part.split(":")
        items = why.get(n) or []
        out.append(f"лист {n}: {k} мест" + ("" if len(items) >= int(k) else f" (в ответе первые {len(items)})"))
        out += [f"  - {w}" for w in items]
    return out


def pages(pdf, d):
    for p in d.glob("p-*.png"):
        p.unlink()
    subprocess.run(["pdftoppm", "-r", str(DPI), "-png", str(pdf), str(d / "p")], check=True)
    out = sorted(d.glob("p-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
    for i, p in enumerate(out, 1):                     # pdftoppm пишет p-1 или p-01 — к одному виду
        p.rename(d / f"p-{i}.png")
    return [d / f"p-{i}.png" for i in range(1, len(out) + 1)]


def page_text(pdf, n):
    r = subprocess.run(["pdftotext", "-layout", "-f", str(n), "-l", str(n), str(pdf), "-"], capture_output=True, text=True)
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def text_diff(old_pdf, new_pdf, n):
    """Строки текста страницы, которые исчезли и появились (пиксели не видят подмену букв при той же вёрстке)."""
    a, b = page_text(old_pdf, n), page_text(new_pdf, n)
    if sorted("".join(a).replace(" ", "")) == sorted("".join(b).replace(" ", "")):
        return [], []                                  # те же буквы, иначе разложены строками (подпись сдвинулась) — не текстовое изменение
    sa, sb = set(a), set(b)
    return [x for x in a if x not in sb], [x for x in b if x not in sa]


def compare(a, b):
    """Доля отличающихся пикселей и рамки мест отличий (сетка 40 пикс., соседние ячейки слиты)."""
    A, B = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if A.size != B.size:
        B = B.resize(A.size)
    m = ImageChops.difference(A, B).convert("L").point(lambda v: 255 if v > THRESH else 0)
    n = m.width * m.height - m.histogram()[0]
    if not n:
        return 0.0, [], A, B
    cell, W, H, hot = 40, m.width, m.height, set()
    for y in range(0, H, cell):
        for x in range(0, W, cell):
            if m.crop((x, y, min(W, x + cell), min(H, y + cell))).getbbox():
                hot.add((x // cell, y // cell))
    boxes, seen = [], set()
    for c in sorted(hot):                              # связные группы ячеек → рамки
        if c in seen:
            continue
        stack, grp = [c], []
        while stack:
            q = stack.pop()
            if q in seen or q not in hot:
                continue
            seen.add(q); grp.append(q)
            stack += [(q[0] + dx, q[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        xs, ys = [g[0] for g in grp], [g[1] for g in grp]
        boxes.append((min(xs) * cell, min(ys) * cell, min(W, (max(xs) + 1) * cell), min(H, (max(ys) + 1) * cell)))
    return n / (W * H) * 100, boxes, A, B


EXPECT_DIR = Path(__file__).resolve().parent / "album_expect"


def design_lint(pdf, spec=None, pptx=None, name=None):
    """Проверка оформления альбома (album_lint): ([строки отчёта], число ошибок). Контрольные строки — album_expect/all.json и <name>.json,
    рамки карт — из спецификации печати. Без poppler — пометка в отчёте, не падение; любая другая поломка линта считается ошибкой."""
    files = [f for f in (EXPECT_DIR / "all.json", EXPECT_DIR / f"{name}.json") if name and f.exists()]
    try:
        findings, n_pages = album_lint.lint(str(pdf), expect=album_lint.load_expect(files) if files else None, pptx=str(pptx) if pptx else None,
                                            frames=album_lint.frames_from_spec(spec) if spec else None)
    except (OSError, subprocess.CalledProcessError) as e:
        return [f"album_lint: не запущен ({e.__class__.__name__}), оформление не проверено"], 0
    except Exception as e:                                          # поломка самого линта не должна пройти молча как «ошибок нет»
        return [f"album_lint: упал ({e.__class__.__name__}: {e})"], 1
    return album_lint.format_lines(findings, n_pages), sum(1 for f in findings if f["sev"] == "error")


REL = "album-baseline"


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def fetch_baseline(name, base):
    """Эталона нет на диске — взять из релиза GitHub album-baseline (архив <name>.zip)."""
    tmp = OUT / f"_{name}.zip"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    r = gh("release", "download", REL, "--pattern", f"{name}.zip", "--output", str(tmp), "--clobber")
    if r.returncode:
        return False
    base.mkdir(parents=True, exist_ok=True)
    shutil.unpack_archive(str(tmp), str(base))
    return True


def publish_baseline(name, base):
    """Эталон — в релиз GitHub album-baseline (создаётся при первом запуске)."""
    arc = shutil.make_archive(str(OUT / name), "zip", str(base))
    if gh("release", "view", REL).returncode:
        gh("release", "create", REL, "--title", "Эталоны альбомов для tools/album_check.py", "--prerelease",
           "--notes", "Страницы альбомов (PNG 100 dpi) и PDF, принятые владельцем. Обновляются `album_check.py --update`.")
    r = gh("release", "upload", REL, arc, "--clobber")
    print("baseline on GitHub:" if not r.returncode else "baseline NOT uploaded:", REL, f"{name}.zip", r.stderr.strip()[:200])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--name", required=True, help="имя эталона: gol, bez, …")
    ap.add_argument("--server", default="http://localhost:8671")
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--no-pptx", action="store_true", help="не печатать PPTX (экономит ~20 с, но неразрывные пробелы не проверяются)")
    a = ap.parse_args()
    out, base = OUT / a.name, BASE / a.name
    shutil.rmtree(out, ignore_errors=True)
    (out / "crops").mkdir(parents=True)
    if not base.exists() and not a.update:
        fetch_baseline(a.name, base)
    render(a.server, a.spec, out / "album.pdf")
    pptx = None if a.no_pptx else render(a.server, a.spec, out / "album.pptx", "pptx")
    cur = pages(out / "album.pdf", out)
    if a.update or not base.exists():
        shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True)
        for p in cur:
            shutil.copy(p, base / p.name)
        shutil.copy(out / "album.pdf", base / "album.pdf")
        print(f"baseline {'updated' if a.update else 'created'}: {base} ({len(cur)} pages)")
        print("\n".join(design_lint(out / "album.pdf", a.spec, pptx, a.name)[0]))     # эталон принимают с открытыми глазами: что линт видит в нём
        publish_baseline(a.name, base)
        return 0
    rows, tiles = [], []
    old = sorted(base.glob("p-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
    if len(old) != len(cur):
        rows.append(f"- число страниц: было {len(old)}, стало {len(cur)}")
    for i, p in enumerate(cur, 1):
        q = base / f"p-{i}.png"
        if not q.exists():
            rows.append(f"- лист {i}: новый")
            continue
        pct, boxes, A, B = compare(q, p)
        rows.append(f"- лист {i}: {'без изменений' if not boxes else f'{pct:.2f} % пикселей, мест: {len(boxes)}'}")
        if (base / "album.pdf").exists():
            gone, came = text_diff(base / "album.pdf", out / "album.pdf", i)
            rows += [f"  - текст убран: «{x[:120]}»" for x in gone[:8]] + [f"  - текст добавлен: «{x[:120]}»" for x in came[:8]]
            if gone or came:
                boxes = boxes or [(0, 0, 1, 1)]
        for k, bx in enumerate(sorted(boxes, key=lambda b: -(b[2] - b[0]) * (b[3] - b[1]))[:6], 1):
            pad = 30
            r = (max(0, bx[0] - pad), max(0, bx[1] - pad), min(A.width, bx[2] + pad), min(A.height, bx[3] + pad))
            ca, cb = A.crop(r), B.crop(r)
            w, h = ca.size
            t = Image.new("RGB", (w * 2 + 12, h + 22), "white")
            t.paste(ca, (0, 22)); t.paste(cb, (w + 12, 22))
            ImageDraw.Draw(t).text((4, 3), f"лист {i}, место {k}: было | стало", fill=(200, 0, 0), font=_font())
            f = out / "crops" / f"L{i}-{k}.png"
            t.save(f)
            tiles.append(t)
    changed = [t for t in tiles]
    if changed:                                         # свод: вырезки столбиком, не шире 1400 пикс.
        sc = [t if t.width <= 1400 else t.resize((1400, int(t.height * 1400 / t.width))) for t in changed]
        S = Image.new("RGB", (max(t.width for t in sc), sum(t.height + 8 for t in sc)), "white")
        y = 0
        for t in sc:
            S.paste(t, (0, y)); y += t.height + 8
        S.save(out / "summary.png")
    lint_lines, lint_errors = design_lint(out / "album.pdf", a.spec, pptx, a.name)
    (out / "report.md").write_text(f"# Сравнение альбома «{a.name}» с эталоном\n\n" + "\n".join(rows)
                                   + (f"\n\nСвод вырезок: {out / 'summary.png'}\n" if changed else "\n\nОтличий нет.\n")
                                   + "\n## Оформление страниц (tools/album_lint.py)\n\n```\n" + "\n".join(lint_lines) + "\n```\n"
                                   + "\n## Подписи под надписями, у рамки, дважды (печать, #55)\n\n```\n"
                                   + ("\n".join(QA) or "мест нет") + "\n```\n")
    print((out / "report.md").read_text())
    print(json.dumps({"changed": bool(changed), "summary": str(out / "summary.png") if changed else None,
                      "lint_errors": lint_errors}, ensure_ascii=False))
    return 3 if lint_errors else 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
