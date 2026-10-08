#!/usr/bin/env python3
"""Автоматические проверки оформления страниц альбома по готовому PDF (и PPTX) — то, что компьютер видит сам, без глаз (см. docs/standards/albums/layout-qa.md).

Читает PDF утилитами poppler (pdftotext, pdffonts, pdfimages) и ищет: слова, налезающие друг на друга; текст за краем страницы, за рамкой карты или ближе допустимого поля;
слишком мелкий кегль; одинаковые подписи, рассыпанные вплотную; невшитые шрифты; растровые вставки с низким разрешением; страницы не того формата или почти пустые;
перенос строки, где его быть не должно (предлог на конце строки, число отдельно от «га», «№» отдельно от номера, последняя строка из одного короткого слова);
слово с «ё» на одном листе и без «ё» на другом; «–» и «—» на одной странице. Контрольные строки (`--expect`) — обязательный и запрещённый текст, каждая строка с причиной.
В PPTX (`--pptx`) ещё и неразрывные пробелы: в PDF их не отличить от обычных, в презентации они хранятся как есть.

  python3 tools/album_lint.py album.pdf                 — отчёт по страницам, код выхода 1, если есть замечания уровня error
  python3 tools/album_lint.py album.pdf --json          — то же JSON-ом (для свода аудита, docs/team/prompts/album-design-audit.md)
  python3 tools/album_lint.py album.pdf --margin 4      — поле от края страницы и рамки карты, мм (по умолчанию 2.5 — правило «не ближе 2,5 мм к краю»)
  python3 tools/album_lint.py album.pdf --pptx album.pptx --spec spec.json --expect tools/album_expect/gol.json
      --pptx — презентация того же альбома; --spec — тело запроса печати ({meta, sheets}): рамки карт (`rect`) для проверки «подпись не под рамкой»;
      --expect — файл контрольных строк (можно несколько), формат — tools/album_expect/README.md

У каждой находки есть `tile` — номер плитки 3 × 2 («02» — вторая колонка первого ряда, «12» — вторая колонка второго ряда): так же названы плитки аудита.
Коды находок: overlap, outside, edge, frame, tiny, dup, hang, widow, yo, dash, nbsp, expect, font, ppi, size, blank (таблица — в layout-qa.md).
Только стандартная библиотека и poppler; проверка этого файла — apps/grado2/tests/test_album_lint.py.
"""
import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

PT_MM = 25.4 / 72
A3 = (1190.55, 841.89)

# пороги: кегль и поля — из правил (docs/wiki/album-rules.md); перекрытие — доля площади меньшего слова
MIN_WORD_H_PT = 5.0          # высота рамки слова меньше — не прочесть на А3 (≈ 1,8 мм)
OVERLAP_SHARE = 0.25
CORE_SHRINK = 0.15           # рамка слова в poppler — по ascent/descent шрифта, шире самих букв: строки плотного абзаца в такой рамке «налезают» (аудит 07.10:
                             # ложные срабатывания в списке документов); для наложений берём середину рамки — по 15 % сверху и снизу отрезаем
DUP_RADIUS_MM = 40.0
DUP_COUNT = 3
MIN_PPI_ERROR = 60            # спутниковая основа Яндекса (z18, 256 px) на А3 даёт 75–150 ppi — это предел источника, не брак
MIN_PPI_WARN = 100
WIDOW_MAX = 8                 # последняя строка из одного слова короче этого числа букв — «висячая» (правило владельца lr 13: два последних слова вместе)
SHORT_WORDS = {"а", "в", "во", "да", "до", "за", "и", "из", "к", "ко", "на", "не", "ни", "но", "о", "об", "от", "по", "с", "со", "у",
               "ли", "же", "бы", "то", "как", "при", "для", "над", "под", "без", "про"}     # предлоги, союзы, частицы до трёх букв не висят в конце строки
ABBR_END = {"ул.", "пр-д", "пер.", "просп.", "наб.", "пл.", "бульв.", "ш.", "вл.", "ст.", "№"}   # сокращение или «№» в конце строки, название — на следующей
UNIT_START = re.compile(r"^(га|тыс\.|млн|млрд|кв\.|м²|м2|г\.|мм|см|км|%)(?![\wа-яё])")          # единица в начале строки, число — в конце предыдущей

# где обычный пробел должен быть неразрывным (правило владельца lr 12, 13, 20; album-rules §2); проверка PPTX
NBSP_RULES = [
    (re.compile(r"№ (?=[\dA-ZА-ЯЁ])"), "«№» и номер"),
    (re.compile(r"(?<=\d) (?=(?:га|тыс\.|млн|млрд|кв\.|м²|м³|м2|мм|см|км|г\.|%)(?![\wа-яё]))"), "число и единица или «г.»"),
    (re.compile(r"(?<=тыс\.) (?=кв\.)|(?<=кв\.) (?=м(?![\wа-яё]))"), "«тыс. кв. м»"),
    (re.compile(r"\b(?:ул|пер|просп|наб|пл|бульв|ш|вл|д)\. (?=[A-ZА-ЯЁ\d«„\"])|\bпр-д (?=[A-ZА-ЯЁ\d№«])"), "сокращение и название или номер"),
    (re.compile(r"\bст\. (?=ж/д)|\bж/д (?=[A-ZА-ЯЁ«])"), "«ст. ж/д» и название"),
]
WORD_RU = re.compile(r"[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)*")


def run(args):
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


# ---------- разбор PDF и PPTX ----------

def _unescape(s):
    return s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")


def parse_pages(html):
    """[(ширина, высота, [слова{x0,y0,x1,y1,text,line}], [блоки: [строки{text,x0,y0,x1,y1,words}]])] — из вывода pdftotext -bbox-layout."""
    pages = []
    for pm in re.finditer(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', html, re.S):
        w, h, body = float(pm.group(1)), float(pm.group(2)), pm.group(3)
        words, blocks, line_no = [], [], 0
        for bm in re.finditer(r"<block [^>]*>(.*?)</block>", body, re.S):
            lines = []
            for lm in re.finditer(r"<line ([^>]*)>(.*?)</line>", bm.group(1), re.S):
                line_no += 1
                lw = []
                for wm in re.finditer(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', lm.group(2)):
                    x0, y0, x1, y1 = map(float, wm.groups()[:4])
                    lw.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": _unescape(wm.group(5)), "line": line_no})
                if lw:
                    lines.append({"text": " ".join(x["text"] for x in lw), "words": lw, "x0": min(x["x0"] for x in lw), "y0": min(x["y0"] for x in lw),
                                  "x1": max(x["x1"] for x in lw), "y1": max(x["y1"] for x in lw)})
                    words.extend(lw)
            if lines:
                blocks.append(lines)
        pages.append((w, h, words, blocks))
    return pages


def pages_words(pdf):
    return parse_pages(run(["pdftotext", "-bbox-layout", pdf, "-"]))


_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def pptx_pages(path):
    """[(номер слайда, [абзацы])] — текст презентации как есть (неразрывные пробелы сохраняются)."""
    pages = []
    with zipfile.ZipFile(path) as z:
        names = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
        for i, name in enumerate(names, 1):
            paras = []
            for p in ET.fromstring(z.read(name)).iter(_A + "p"):
                text = "".join((el.text or "") if el.tag == _A + "t" else " " for el in p.iter() if el.tag in (_A + "t", _A + "br"))
                if text.strip():
                    paras.append(text)
            pages.append((i, paras))
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


def core(wd):
    """Середина рамки слова: без верхней и нижней кромки шрифта (см. CORE_SHRINK)."""
    d = (wd["y1"] - wd["y0"]) * CORE_SHRINK
    return {"x0": wd["x0"], "x1": wd["x1"], "y0": wd["y0"] + d, "y1": wd["y1"] - d}


def norm(s):
    """Неразрывные и узкие пробелы, переводы строк — в один обычный пробел: так сравнивают контрольные строки."""
    return re.sub(r"\s+", " ", s).strip()


# ---------- проверки слов и строк страницы ----------

def finding(page, sev, code, text, msg, mm=None, tile_="", ):
    return {"page": page, "sev": sev, "code": code, "text": text, "mm": mm or [], "tile": tile_, "msg": msg}


def check_words(page_no, pw, ph, words, margin_mm, out):
    def add(sev, code, wd, msg):
        out.append(finding(page_no, sev, code, wd["text"], msg, box_mm(wd), tile(pw, ph, (wd["x0"] + wd["x1"]) / 2, (wd["y0"] + wd["y1"]) / 2)))

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
    # наложения: слова по возрастанию левого края — дальше правого края слова a искать нечего
    cores = sorted(((core(w), w) for w in uniq), key=lambda t: t[0]["x0"])
    for i, (ca, a) in enumerate(cores):
        for cb, b in cores[i + 1:]:
            if cb["x0"] >= ca["x1"]:
                break
            if a["line"] == b["line"]:
                continue
            ov = inter_area(ca, cb)
            if ov and ov >= OVERLAP_SHARE * min(area(ca), area(cb)) and min(area(ca), area(cb)) > 4:
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


def check_frame(page_no, pw, ph, words, frame_mm, margin_mm, out):
    """Подпись, пересекающая рамку карты или лежащая у её внутренней кромки (рамка `rect` листа: x, y, ширина, высота — мм от левого верхнего угла).
    Кромки, совпадающие с краем страницы (лист на всю страницу), проверяет check_words."""
    x, y, w, h = frame_mm
    fr = {"x0": x / PT_MM, "y0": y / PT_MM, "x1": (x + w) / PT_MM, "y1": (y + h) / PT_MM}
    m = margin_mm / PT_MM
    inner = {"x0": fr["x0"] > 1, "y0": fr["y0"] > 1, "x1": fr["x1"] < pw - 1, "y1": fr["y1"] < ph - 1}
    seen = set()
    for wd in words:
        if wd["x1"] <= fr["x0"] or wd["x0"] >= fr["x1"] or wd["y1"] <= fr["y0"] or wd["y0"] >= fr["y1"]:
            continue                                              # слово целиком вне рамки: легенда, заголовок, номер листа
        key = (wd["text"], round(wd["x0"]), round(wd["y0"]))
        if key in seen:
            continue
        seen.add(key)
        sides = [k for k in ("x0", "y0") if inner[k] and wd[k] < fr[k]] + [k for k in ("x1", "y1") if inner[k] and wd[k] > fr[k]]
        near = [k for k in ("x0", "y0") if inner[k] and fr[k] <= wd[k] < fr[k] + m] + [k for k in ("x1", "y1") if inner[k] and fr[k] - m < wd[k] <= fr[k]]
        t = tile(pw, ph, (wd["x0"] + wd["x1"]) / 2, (wd["y0"] + wd["y1"]) / 2)
        if sides:
            out.append(finding(page_no, "error", "frame", wd["text"], "подпись пересекает рамку карты — обрезана", box_mm(wd), t))
        elif near:
            out.append(finding(page_no, "warn", "frame", wd["text"], f"подпись ближе {margin_mm} мм к рамке карты", box_mm(wd), t))


def check_wrap(page_no, pw, ph, blocks, out):
    """Переносы строк внутри блока текста: предлог или союз на конце строки, число отдельно от единицы, «№» и сокращение отдельно от названия,
    тире в начале строки, последняя строка из одного короткого слова (правила владельца lr 12, 13, 20)."""
    def add(code, ln, msg):
        out.append(finding(page_no, "warn", code, ln["text"][-40:] if code == "hang" else ln["text"], msg, [round(ln[k] * PT_MM, 1) for k in ("x0", "y0", "x1", "y1")],
                           tile(pw, ph, (ln["x0"] + ln["x1"]) / 2, (ln["y0"] + ln["y1"]) / 2)))

    for lines in blocks:
        if len(lines) < 2:
            continue
        for i, ln in enumerate(lines[:-1]):
            nxt = lines[i + 1]
            last = ln["words"][-1]["text"]
            bare = re.sub(r"[^\wёЁ-]", "", last).lower()
            first = nxt["words"][0]["text"]
            if bare in SHORT_WORDS and not last[-1:] in ",.;:":
                add("hang", ln, f"«{last}» остаётся в конце строки — должно уйти вниз вместе со словом")
            elif last in ABBR_END and re.match(r"[A-ZА-ЯЁ\d«„\"]", first):
                add("hang", ln, f"«{last}» отделено от «{first}» переносом строки")
            elif re.search(r"\d$", last) and UNIT_START.match(first):
                add("hang", ln, f"число «{last}» отделено от «{first}» переносом строки")
        for ln in lines[1:]:
            if ln["words"][0]["text"] in ("–", "—", "-"):
                add("hang", ln, "строка начинается с тире")
        tail = lines[-1]["words"]
        prior = sum(len(x["words"]) for x in lines[:-1])
        if len(tail) == 1 and prior >= 2 and len(re.sub(r"[^А-Яа-яЁёA-Za-z]", "", tail[0]["text"])) < WIDOW_MAX:
            add("widow", lines[-1], "последняя строка — одно короткое слово")


def check_text(pages, out):
    """Проверки текста всего альбома (pages — [(номер, [строки])]): «ё» в одном слове по-разному, «–» и «—» на одной странице."""
    forms = {}                                                    # нормализованное слово → {написание: {страницы}}
    stems = {}                                                    # первые 6 букв (ё = е) → {написание начала: {слово: {страницы}}}
    for n, lines in pages:
        text = " ".join(lines)
        if "–" in text and "—" in text:
            out.append(finding(n, "warn", "dash", "– —", "на странице и короткое «–», и длинное «—» тире — должно быть одно"))
        for w in WORD_RU.findall(text):
            lw = w.lower()
            if len(lw) < 5:
                continue
            forms.setdefault(lw.replace("ё", "е"), {}).setdefault(lw, set()).add(n)
            if len(lw) >= 7:
                stems.setdefault(lw[:6].replace("ё", "е"), {}).setdefault(lw[:6], {}).setdefault(lw, set()).add(n)

    def pgs(s):
        return ", ".join(str(p) for p in sorted(s))

    for key, fs in sorted(forms.items()):
        if len(fs) > 1:
            first = min(min(p) for p in fs.values())
            out.append(finding(first, "warn", "yo", " / ".join(sorted(fs)), "слово написано и с «ё», и без неё: " + "; ".join(f"«{w}» (стр. {pgs(p)})" for w, p in sorted(fs.items()))))
    for key, starts in sorted(stems.items()):
        if len(starts) > 1:
            words = {w: p for ws in starts.values() for w, p in ws.items()}
            if len({w.replace("ё", "е") for w in words}) == 1:
                continue                                          # то же слово целиком — уже сказано выше
            first = min(min(p) for p in words.values())
            out.append(finding(first, "warn", "yo", " / ".join(sorted(words)), "основа слова написана и с «ё», и без неё: " + "; ".join(f"«{w}» (стр. {pgs(p)})" for w, p in sorted(words.items()))))


def check_expect(pages, spec, out, where="PDF"):
    """Контрольные строки (tools/album_expect/*.json): обязательный и запрещённый текст страниц; каждая строка с причиной.
    pages — [(номер, текст страницы)]; элемент: {"text": …} или {"re": …}, "pages": […] (по умолчанию все), "each": true (обязательна на каждой из pages),
    "sev": "warn", "why": «откуда правило»."""
    def hit(item, text):
        return re.search(item["re"], text) if "re" in item else norm(item["text"]) in text

    def label(item):
        return item.get("text") or item.get("re")

    nums = [n for n, _ in pages]
    texts = {n: norm(t) for n, t in pages}
    if spec.get("pages") and len(pages) != spec["pages"]:
        out.append(finding(0, "error", "expect", f"{len(pages)} вместо {spec['pages']}", f"{where}: число страниц не то, что ожидается ({spec['pages']})"))
    for item in spec.get("require", []):
        want = [n for n in (item.get("pages") or nums) if n in texts]
        found = [n for n in want if hit(item, texts[n])]
        sev, why = item.get("sev", "error"), item.get("why", "")
        if item.get("each"):
            for n in want:
                if n not in found:
                    out.append(finding(n, sev, "expect", label(item), f"{where}: на странице нет обязательной строки «{label(item)}»" + (f" — {why}" if why else "")))
        elif not found:
            out.append(finding((want or [0])[0], sev, "expect", label(item), f"{where}: нет обязательной строки «{label(item)}»" + (f" — {why}" if why else "")))
    for item in spec.get("forbid", []):
        for n in (item.get("pages") or nums):
            if n in texts and hit(item, texts[n]):
                out.append(finding(n, item.get("sev", "error"), "expect", label(item), f"{where}: запрещённая строка «{label(item)}»" + (f" — {item['why']}" if item.get("why") else "")))


def load_expect(paths):
    """Сливает файлы контрольных строк в один набор; ключи на «_» — пояснения, их пропускают."""
    spec = {"require": [], "forbid": []}
    for p in paths:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        spec["require"] += d.get("require", [])
        spec["forbid"] += d.get("forbid", [])
        if d.get("pages") and not spec.get("pages"):
            spec["pages"] = d["pages"]
    return spec


def check_pptx(path, out, spec=None):
    """PPTX того же альбома: неразрывные пробелы там, где их требует правило, и контрольные строки (текст слайда — как в файле)."""
    pages = pptx_pages(path)
    for n, paras in pages:
        counts = {}
        for text in paras:
            for rx, what in NBSP_RULES:
                for m in rx.finditer(text):
                    c = counts.setdefault(what, [0, text[max(0, m.start() - 14):m.end() + 14].replace("\n", " ")])
                    c[0] += 1
        for what, (k, sample) in counts.items():
            out.append(finding(n, "warn", "nbsp", sample, f"PPTX: {k} мест с обычным пробелом вместо неразрывного ({what})"))
    if spec:
        check_expect([(n, " ".join(paras)) for n, paras in pages], spec, out, where="PPTX")
    return len(pages)


# ---------- шрифты, растры, свод ----------

def check_fonts(pdf, out):
    rows = run(["pdffonts", pdf]).splitlines()[2:]
    for row in rows:
        parts = row.split()
        if len(parts) < 7:
            continue
        # колонки: name, type, encoding, emb, sub, uni, object ID (+ номер версии)
        emb = parts[-5] if parts[-5] in ("yes", "no") else ""
        if emb == "no":
            out.append(finding(0, "error", "font", parts[0], "шрифт не вшит в файл"))


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
        out.append(finding(page, sev, "ppi", f"{w}×{h}", f"{n} растр. вставок {w}×{h} на {ppi} ppi — размыто на А3 (ниже {MIN_PPI_ERROR if sev == 'error' else MIN_PPI_WARN})"))


def lint(pdf, margin_mm=2.5, size=A3, expect=None, pptx=None, frames=None):
    """Все проверки. expect — набор контрольных строк (load_expect), pptx — путь к презентации, frames — {номер страницы: (x, y, ширина, высота) мм}.
    Возвращает ([находки], число страниц)."""
    out = []
    pages = pages_words(pdf)
    texts = []
    for n, (pw, ph, words, blocks) in enumerate(pages, 1):
        if abs(pw - size[0]) > 2 or abs(ph - size[1]) > 2:
            out.append(finding(n, "error", "size", f"{pw:.0f}×{ph:.0f}", "страница не А3 альбомная"))
        if len(words) < 8 and n > 1:
            out.append(finding(n, "warn", "blank", f"{len(words)} слов", "страница почти без текста"))
        check_words(n, pw, ph, words, margin_mm, out)
        check_wrap(n, pw, ph, blocks, out)
        if frames and frames.get(n):
            check_frame(n, pw, ph, words, frames[n], margin_mm, out)
        texts.append((n, [ln["text"] for lines in blocks for ln in lines]))
    check_text(texts, out)
    if expect:
        check_expect([(n, " ".join(lines)) for n, lines in texts], expect, out)
    if pptx:
        check_pptx(pptx, out, expect)
    check_fonts(pdf, out)
    check_images(pdf, out)
    return out, len(pages)


def format_lines(findings, n_pages):
    """Текст отчёта: заголовок со счётом и по строке на находку (сначала ошибки каждой страницы). Нужен и album_check.py."""
    errors = sum(1 for f in findings if f["sev"] == "error")
    lines = [f"album_lint: страниц {n_pages}, ошибок {errors}, предупреждений {len(findings) - errors}"]
    for f in sorted(findings, key=lambda f: (f["page"], f["sev"] != "error", f["code"])):
        where = f" плитка {f['tile']}" if f["tile"] else ""
        lines.append(f"  стр. {f['page']:>2} {f['sev']:5s} {f['code']:7s} «{f['text']}»{where}: {f['msg']}")
    return lines


def frames_from_spec(path):
    """Рамки карт листов из тела запроса печати: {номер страницы: (x, y, ширина, высота)}; страница = лист по порядку."""
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    return {i: tuple(s["rect"]) for i, s in enumerate(spec.get("sheets", []), 1) if isinstance(s.get("rect"), list) and len(s["rect"]) == 4}


def main(argv):
    ap = argparse.ArgumentParser(description="автоматические проверки оформления страниц альбома (PDF, PPTX)")
    ap.add_argument("pdf")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--margin", type=float, default=2.5)
    ap.add_argument("--pptx", help="презентация того же альбома: неразрывные пробелы и контрольные строки")
    ap.add_argument("--spec", help="тело запроса печати (JSON со списком sheets): рамки карт для проверки подписей у рамки")
    ap.add_argument("--expect", action="append", default=[], help="файл контрольных строк (tools/album_expect/*.json); можно несколько")
    args = ap.parse_args(argv)
    findings, n_pages = lint(args.pdf, args.margin, expect=load_expect(args.expect) if args.expect else None, pptx=args.pptx,
                             frames=frames_from_spec(args.spec) if args.spec else None)
    errors = sum(1 for f in findings if f["sev"] == "error")
    if args.json:
        print(json.dumps({"pages": n_pages, "errors": errors, "findings": findings}, ensure_ascii=False, indent=1))
    else:
        print("\n".join(format_lines(findings, n_pages)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
