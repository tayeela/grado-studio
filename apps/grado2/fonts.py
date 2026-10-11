"""ГРАДО 2 · каталог шрифтов для печати альбома (владелец 10.10.2026: «должна быть возможность использовать любой шрифт,
в том числе один из нескольких предустановленных»).

Три источника:
- готовые — в составе ГРАДО (docs/standards/fonts): PT Sans, PT Serif, Montserrat, у печати свои имена ui / serif / sans;
- шрифты компьютера — папки шрифтов macOS, Windows, Linux (у сервера сайта их почти нет);
- свои файлы — TTF, OTF или TTC, добавленные кнопкой «Добавить файл шрифта» (~/.grado2/fonts/user).

Шрифт в печати — семейство «f:<id>» (обычное начертание) и «f:<id>-bold» (жирное; нет жирного — обычное). Печать (PDF,
PPTX, ширина подписей) читает только TrueType с cmap формата 4 (grado_render/ttf.py), поэтому OTF с контурами CFF и TTC
один раз переводятся в такой TTF через fontTools (кривые 3-го порядка → 2-го, cu2qu) и лежат в ~/.grado2/fonts/ttf.
В списке только шрифты с кириллицей. id — первые 12 знаков sha1 имени семейства: тот же шрифт на другом компьютере
находится по имени; нет такого — печать берёт PT Sans (find_font), лист не падает.
"""

import hashlib
import json
import logging
import os
import re
import sys
import threading
from pathlib import Path

HOME = Path(os.environ.get("GRADO2_FONTS") or Path.home() / ".grado2" / "fonts")
USER, TTF, INDEX = HOME / "user", HOME / "ttf", HOME / "index.json"
MAX_UPLOAD = 20 * 2**20
EXTS = (".ttf", ".otf", ".ttc", ".otc")
CYR = 0x0416                                         # «Ж»: есть — шрифт с кириллицей
# готовые: имя в списке → семейства печати (обычное, жирное)
PRESETS = [("PT Sans", "ui", "ui-bold"), ("PT Serif", "serif", "serif-bold"), ("Montserrat", "sans", "sans-bold")]
REGULAR = {"regular", "book", "normal", "roman", "medium", "plain", "обычный"}

logging.getLogger("fontTools").setLevel(logging.ERROR)    # «timestamp seems very low» и подобное у старых шрифтов — не ошибка
_lock = threading.Lock()
_cache = {"index": None, "fams": None}


def _system_dirs():
    home = Path.home()
    if sys.platform == "darwin":
        return [Path("/System/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"), Path("/Library/Fonts"), home / "Library/Fonts"]
    if os.name == "nt":
        win = Path(os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows")
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData/Local")
        return [win / "Fonts", local / "Microsoft/Windows/Fonts"]
    return [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), home / ".local/share/fonts", home / ".fonts"]


def font_id(family):
    return hashlib.sha1(family.strip().lower().encode("utf-8")).hexdigest()[:12]


def _names(tt):
    """(семейство, начертание) из таблицы name: типографские 16/17, иначе 1/2; английская запись Windows прежде прочих."""
    def get(*ids):
        for i in ids:
            rec = tt["name"].getName(i, 3, 1, 0x409) or tt["name"].getName(i, 1, 0, 0) or tt["name"].getName(i, 3, 1)
            if rec:
                s = str(rec).strip()
                if s:
                    return s
        return ""
    return get(16, 1), get(17, 2) or "Regular"


def _faces(path):
    """Начертания файла: [{family, style, bold, italic, path, index}] — у TTC несколько."""
    from fontTools.ttLib import TTCollection, TTFont
    out = []
    try:
        fonts = TTCollection(str(path), lazy=True).fonts if path.suffix.lower() in (".ttc", ".otc") else [TTFont(str(path), lazy=True, fontNumber=-1)]
    except Exception:
        return out
    for n, tt in enumerate(fonts):
        try:
            cmap = tt.getBestCmap() or {}
            if CYR not in cmap:
                continue
            fam, style = _names(tt)
            if not fam or fam.startswith("."):           # скрытые системные шрифты macOS (.SF NS и подобные)
                continue
            mac = tt["head"].macStyle if "head" in tt else 0
            os2 = tt["OS/2"] if "OS/2" in tt else None
            weight = getattr(os2, "usWeightClass", 400) if os2 else 400
            st = style.lower()
            out.append({"family": fam, "style": style, "path": str(path), "index": n,
                        "bold": bool(mac & 1) or weight >= 600 or "bold" in st or "жирн" in st,
                        "italic": bool(mac & 2) or "italic" in st or "oblique" in st or "курсив" in st})
        except Exception:
            continue
    return out


def _scan():
    """Указатель: путь файла → (mtime, начертания). Перечитываются только новые и изменённые файлы."""
    old = {}
    try:
        old = json.loads(INDEX.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    new = {}
    for d in [USER, *_system_dirs()]:
        if not d.is_dir():
            continue
        for p in (d.rglob("*") if d != USER else d.iterdir()):
            if p.suffix.lower() not in EXTS or not p.is_file():
                continue
            k, m = str(p), p.stat().st_mtime
            new[k] = old[k] if k in old and old[k].get("m") == m else {"m": m, "faces": _faces(p)}
    if new != old:
        try:
            HOME.mkdir(parents=True, exist_ok=True)
            INDEX.write_text(json.dumps(new, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return new


def families(refresh=False):
    """{id: {name, regular: начертание, bold: начертание|None, user: свой файл}} — шрифты с кириллицей."""
    with _lock:
        if _cache["fams"] is not None and not refresh:
            return _cache["fams"]
        fams = {}
        for path, rec in _scan().items():
            for f in rec.get("faces") or []:
                if f["italic"]:
                    continue
                e = fams.setdefault(font_id(f["family"]), {"name": f["family"], "regular": None, "bold": None, "user": False, "_any": f})
                e["user"] = e["user"] or path.startswith(str(USER))
                slot = "bold" if f["bold"] else "regular"
                plain = f["style"].lower() in REGULAR or f["style"].lower() == "bold"
                if e[slot] is None or plain:             # обычное начертание прежде «Light», «Medium» и подобных
                    e[slot] = f
        for e in fams.values():
            e["regular"] = e["regular"] or e.pop("_any")
            e.pop("_any", None)
        _cache["fams"] = fams
        return fams


def listing():
    """Для окна выбора: готовые и прочие (имя, есть ли жирное, свой ли файл), по алфавиту."""
    fams = families()
    rest = sorted(({"id": "f:" + k, "name": v["name"], "bold": bool(v["bold"]), "user": v["user"]} for k, v in fams.items()),
                  key=lambda x: x["name"].lower())
    return {"presets": [{"id": r, "name": n, "bold": True} for n, r, _ in PRESETS], "fonts": rest}


def _to_ttf(face):
    """Начертание → TrueType-файл, понятный печати: TTF с glyf и cmap 4 — как есть, остальное — перевод (кэш по файлу)."""
    from fontTools.ttLib import TTFont
    src = Path(face["path"])
    key = hashlib.sha1(f"{src}|{face['index']}|{src.stat().st_mtime}".encode("utf-8")).hexdigest()[:16]
    out = TTF / f"{key}.ttf"
    if out.exists():
        return out
    tt = TTFont(str(src), fontNumber=face["index"]) if src.suffix.lower() in (".ttc", ".otc") else TTFont(str(src))
    if "glyf" in tt and _has_cmap4(tt) and src.suffix.lower() == ".ttf":
        return src
    if "CFF " in tt or "CFF2" in tt:
        _cff_to_glyf(tt)
    if not _has_cmap4(tt):
        _add_cmap4(tt)
    TTF.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tt.save(str(tmp))
    tmp.replace(out)
    return out


def _has_cmap4(tt):
    return any(t.format == 4 and (t.platformID, t.platEncID) in ((3, 1), (0, 3)) for t in tt["cmap"].tables)


def _add_cmap4(tt):
    from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
    sub = CmapSubtable.newSubtable(4)
    sub.platformID, sub.platEncID, sub.language = 3, 1, 0
    sub.cmap = {c: g for c, g in (tt.getBestCmap() or {}).items() if c <= 0xFFFF}
    tt["cmap"].tables.insert(0, sub)


def _cff_to_glyf(tt):
    """Контуры CFF (кубические) → glyf (квадратичные): рецепт fontTools otf2ttf (cu2qu, допуск 1 единица)."""
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    from fontTools.ttLib import newTable
    order, gs = tt.getGlyphOrder(), tt.getGlyphSet()
    glyf = newTable("glyf")
    glyf.glyphOrder, glyf.glyphs = order, {}
    for name in order:
        pen = TTGlyphPen(gs)
        gs[name].draw(Cu2QuPen(pen, 1.0, reverse_direction=True))
        glyf[name] = pen.glyph()
    tt["loca"], tt["glyf"] = newTable("loca"), glyf
    for t in ("CFF ", "CFF2", "VORG"):
        if t in tt:
            del tt[t]
    tt.sfntVersion = "\x00\x01\x00\x00"
    maxp = tt["maxp"]
    maxp.tableVersion = 0x00010000
    for k in ("maxZones", "maxTwilightPoints", "maxStorage", "maxFunctionDefs", "maxInstructionDefs", "maxStackElements",
              "maxSizeOfInstructions", "maxComponentElements", "maxPoints", "maxContours", "maxCompositePoints",
              "maxCompositeContours", "maxComponentDepth"):
        setattr(maxp, k, 0)
    maxp.maxZones = 1
    if "post" in tt:
        tt["post"].formatType, tt["post"].extraNames, tt["post"].mapping = 3.0, [], {}
    tt["head"].indexToLocFormat = 0
    tt["head"].glyphDataFormat = 0


def resolve(family):
    """Семейство печати «f:<id>[-bold]» → (имя шрифта, путь TTF, жирный ли) или None (нет такого шрифта здесь)."""
    m = re.fullmatch(r"f:([0-9a-f]{12})(-bold)?", str(family or ""))
    if not m:
        return None
    e = families().get(m.group(1)) or families(refresh=True).get(m.group(1))
    if not e:
        return None
    face = (e["bold"] if m.group(2) else None) or e["regular"]
    try:
        return e["name"], str(_to_ttf(face)), face is e["bold"]
    except Exception:
        return None


def add_file(name, data):
    """Свой файл шрифта (TTF, OTF, TTC): проверка, что это шрифт с кириллицей, — и в ~/.grado2/fonts/user. → id семейств."""
    ext = Path(str(name)).suffix.lower()
    if ext not in EXTS:
        raise ValueError("not a font file: use TTF, OTF or TTC")
    if len(data) > MAX_UPLOAD:
        raise ValueError("font file is larger than 20 MB")
    USER.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w.-]+", "_", Path(str(name)).stem)[:60] or "font"
    path = USER / f"{stem}-{hashlib.sha1(data).hexdigest()[:8]}{ext}"
    path.write_bytes(data)
    faces = _faces(path)
    if not faces:
        path.unlink(missing_ok=True)
        raise ValueError("font has no Cyrillic letters or cannot be read")
    families(refresh=True)
    return sorted({"f:" + font_id(f["family"]) for f in faces})


def face_file(family):
    """TTF начертания для просмотра в браузере (@font-face) — байты или None."""
    r = resolve(family)
    return Path(r[1]).read_bytes() if r else None


def install():
    """Подключить каталог к печати: grado_render.ttf находит «f:<id>» через resolve."""
    from grado_render import ttf
    ttf.CUSTOM["resolve"] = resolve
