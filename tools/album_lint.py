#!/usr/bin/env python3
"""Автоматические проверки оформления страниц альбома по готовому PDF — то, что компьютер видит сам, без глаз (см. docs/standards/albums/layout-qa.md).

Читает PDF утилитами poppler (pdftotext, pdffonts, pdfimages, pdfinfo) и ищет: слова, налезающие друг на друга; текст за краем страницы или ближе допустимого поля;
слишком мелкий кегль; одинаковые подписи, рассыпанные вплотную; невшитые шрифты; растровые вставки с низким разрешением; страницы не того формата или почти пустые.

  python3 tools/album_lint.py album.pdf                 — отчёт по страницам, код выхода 1, если есть замечания уровня error
  python3 tools/album_lint.py album.pdf --json          — то же JSON-ом (для свода аудита, docs/team/prompts/album-design-audit.md)
  python3 tools/album_lint.py album.pdf --margin 4      — поле от края страницы, мм (по умолчанию 2.5 — правило «не ближе 2,5 мм к краю»)

У каждой находки есть `tile` — номер плитки 3 × 2 («02» — вторая колонка первого ряда, «12» — вторая колонка второго ряда): так же названы плитки аудита.
Только стандартная библиотека и poppler; проверка этого файла — apps/grado2/tests/test_album_lint.py.
"""
import argparse
import json
import re
import subprocess
import sys

PT_MM = 25.4 / 72
A3 = (1190.55, 841.89)

# пороги: кегль и поля — из правил (docs/wiki/album-rules.md); перекрытие — доля площади меньшего слова
MIN_WORD_H_PT = 5.0          # высота рамки слова меньше — не прочесть на А3 (≈ 1,8 мм)
OVERLAP_SHARE = 0.25
DUP_RADIUS_MM = 40.0
DUP_COUNT = 3
MIN_PPI_ERROR = 60            # спутниковая основа Яндекса (z18, 256 px) на А3 даёт 75–150 ppi — это предел источника, не брак
MIN_PPI_WARN = 100


def run(args):
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def pages_words(pdf):
    """[(ширина, высота, [слова{x0,y0,x1,y1,text,line}])] — по страницам, из pdftotext -bbox-layout."""
    html = run(["pdftotext", "-bbox-layout", pdf, "-"])
    pages = []
    for pm in re.finditer(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', html, re.S):
        w, h, body = float(pm.group(1)), float(pm.group(2)), pm.group(3)
        words, line_no = [], 0
        for lm in re.finditer(r"<line [^>]*>(.*?)</line>", body, re.S):
            line_no += 1
            for wm in re.finditer(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', lm.group(1)):
                x0, y0, x1, y1 = map(float, wm.groups()[:4])
                text = wm.group(5).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
                words.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": text, "line": line_no})
        pages.append((w, h, words))
    return pages


def tile(page_w, page_h, x, y):
    c = min(2, int(3 * x / page_w)) if page_w else 0
    r = min(1, int(2 * y / page_h)) if page_h else 0
    return f"{r}{c}"


def box_mm(wd):
    return [round(wd[k] * PT_MM, 1) for k in ("x0", "y0", "x1", "y1")]


def inter_area(a, b):
    w = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
    h = min(a["y1"], b["y1"]) - max(a["y0"], b["y0"])
    return w * h if w > 0 and h > 0 else 0.0


def area(a):
    return max(0.0, (a["x1"] - a["x0"]) * (a["y1"] - a["y0"]))


def check_words(page_no, pw, ph, words, margin_mm, out):
    def add(sev, code, wd, msg):
        out.append({"page": page_no, "sev": sev, "code": code, "text": wd["text"], "mm": box_mm(wd),
                    "tile": tile(pw, ph, (wd["x0"] + wd["x1"]) / 2, (wd["y0"] + wd["y1"]) / 2), "msg": msg})

    margin = margin_mm / PT_MM
    # слова, нарисованные дважды в одном месте (ореол и заливка), считаем одним
    uniq = []
    for wd in words:
        if not any(u["text"] == wd["text"] and inter_area(u, wd) > 0.8 * min(area(u), area(wd)) for u in uniq[-40:]):
            uniq.append(wd)
    for wd in uniq:
        if wd["x0"] < 0 or wd["y0"] < 0 or wd["x1"] > pw or wd["y1"] > ph:
            add("error", "outside", wd, "слово выходит за край страницы")
        elif wd["x0"] < margin or wd["y0"] < margin or wd["x1"] > pw - margin or wd["y1"] > ph - margin:
            add("warn", "edge", wd, f"слово ближе {margin_mm} мм к краю страницы")
        if (wd["y1"] - wd["y0"]) < MIN_WORD_H_PT and len(wd["text"]) > 1:
            add("warn", "tiny", wd, f"высота слова {(wd['y1'] - wd['y0']) * PT_MM:.1f} мм — мельче допустимого")
    for i, a in enumerate(uniq):
        for b in uniq[i + 1:]:
            if a["line"] == b["line"] or b["x0"] > a["x1"] or b["y0"] > a["y1"] + 40 and b["x0"] > a["x1"]:
                continue
            ov = inter_area(a, b)
            if ov and ov >= OVERLAP_SHARE * min(area(a), area(b)) and min(area(a), area(b)) > 4:
                add("error", "overlap", a, f"налезает на «{b['text']}» ({box_mm(b)})")
    # рассыпанные одинаковые подписи: строка из нескольких слов или длинное слово, повторённое вплотную
    lines = {}
    for wd in uniq:
        lines.setdefault(wd["line"], []).append(wd)
    texts = {}
    for ws in lines.values():
        text = " ".join(w["text"] for w in sorted(ws, key=lambda w: (round(w["y0"]), w["x0"])))
        if len(text) >= 8 and not text.replace(" ", "").isdigit():
            texts.setdefault(text, []).append({"text": text, "x0": min(w["x0"] for w in ws), "y0": min(w["y0"] for w in ws),
                                               "x1": max(w["x1"] for w in ws), "y1": max(w["y1"] for w in ws)})
    r = DUP_RADIUS_MM / PT_MM
    for text, ls in texts.items():
        for ln in ls:
            near = [o for o in ls if abs(o["x0"] - ln["x0"]) < r and abs(o["y0"] - ln["y0"]) < r]
            if len(near) >= DUP_COUNT:
                add("warn", "dup", ln, f"«{text}» {len(near)} раза в радиусе {DUP_RADIUS_MM:.0f} мм")
                break


def check_fonts(pdf, out):
    rows = run(["pdffonts", pdf]).splitlines()[2:]
    for row in rows:
        parts = row.split()
        if len(parts) < 7:
            continue
        # колонки: name, type, encoding, emb, sub, uni, object ID (+ номер версии)
        emb = parts[-5] if parts[-5] in ("yes", "no") else ""
        if emb == "no":
            out.append({"page": 0, "sev": "error", "code": "font", "text": parts[0], "mm": [], "tile": "", "msg": "шрифт не вшит в файл"})


def check_images(pdf, out):
    groups = {}
    for row in run(["pdfimages", "-list", pdf]).splitlines()[2:]:
        p = row.split()
        if len(p) < 14 or p[2] != "image":
            continue
        page, w, h, ppi = int(p[0]), int(p[3]), int(p[4]), min(int(p[12]), int(p[13]))
        if w < 64 or h < 64 or ppi >= MIN_PPI_WARN:
            continue
        groups.setdefault((page, w, h, ppi), 0)
        groups[(page, w, h, ppi)] += 1
    for (page, w, h, ppi), n in sorted(groups.items()):
        sev = "error" if ppi < MIN_PPI_ERROR else "warn"
        out.append({"page": page, "sev": sev, "code": "ppi", "text": f"{w}×{h}", "mm": [], "tile": "",
                    "msg": f"{n} растр. вставок {w}×{h} на {ppi} ppi — размыто на А3 (ниже {MIN_PPI_ERROR if sev == 'error' else MIN_PPI_WARN})"})


def lint(pdf, margin_mm=2.5, size=A3):
    out = []
    pages = pages_words(pdf)
    for n, (pw, ph, words) in enumerate(pages, 1):
        if abs(pw - size[0]) > 2 or abs(ph - size[1]) > 2:
            out.append({"page": n, "sev": "error", "code": "size", "text": f"{pw:.0f}×{ph:.0f}", "mm": [], "tile": "", "msg": "страница не А3 альбомная"})
        if len(words) < 8 and n > 1:
            out.append({"page": n, "sev": "warn", "code": "blank", "text": f"{len(words)} слов", "mm": [], "tile": "", "msg": "страница почти без текста"})
        check_words(n, pw, ph, words, margin_mm, out)
    check_fonts(pdf, out)
    check_images(pdf, out)
    return out, len(pages)


def main(argv):
    ap = argparse.ArgumentParser(description="автоматические проверки оформления страниц альбома (PDF)")
    ap.add_argument("pdf")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--margin", type=float, default=2.5)
    args = ap.parse_args(argv)
    findings, n_pages = lint(args.pdf, args.margin)
    errors = sum(1 for f in findings if f["sev"] == "error")
    if args.json:
        print(json.dumps({"pages": n_pages, "errors": errors, "findings": findings}, ensure_ascii=False, indent=1))
    else:
        print(f"album_lint: страниц {n_pages}, ошибок {errors}, предупреждений {len(findings) - errors}")
        for f in sorted(findings, key=lambda f: (f["page"], f["sev"] != "error", f["code"])):
            where = f" плитка {f['tile']}" if f["tile"] else ""
            print(f"  стр. {f['page']:>2} {f['sev']:5s} {f['code']:7s} «{f['text']}»{where}: {f['msg']}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
