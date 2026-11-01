"""ГРАДО 2 · использует извлечённые правила ВРИ прежнего альбома в серверной сборке.

Паспорт создаёт tools/extract_sushpol_rules.mjs; поля и цвета не придумываются заново.
Контрольные примеры исполняют исходный JavaScript и проверяются в test_sushpol_rules.py.
"""
import json
import re
import sys
from pathlib import Path

ROOT=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parents[2]))
PASSPORT=json.loads((ROOT/"docs/standards/albums/sushpol-rules-v1.json").read_text())
RULES=PASSPORT["rules"]
ZONES={n:(name,color) for name,color,ids in RULES["SPEC_ZONES"]+RULES["TRANSPORT_ZONES"] for n in ids}
CODES={str(c):int(n) for n,(_,_,codes) in RULES["VRI_T"].items() for c in codes}
AGRI={25,26,27,28}


def _matches(rule,text):
    return re.search(rule["pattern"],str(text),re.IGNORECASE if "i" in rule["flags"] else 0) is not None


def land_class(props,tinao=False):
    text=re.sub(r"[Cc](?=[а-яё])","с",str(props.get("ВРИ") or props.get("Разрешенное использование") or ""))
    if not text:return None
    def allowed(n):return n is not None and (tinao or n not in AGRI)
    # JavaScript \b для числового кода использует ASCII word boundary, не Unicode.
    for code in re.findall(r"\b\d{1,2}(?:\.\d{1,2}){1,3}\b",text,re.ASCII):
        if re.match(r"^1\.\d+\.\d+",code) and code not in CODES:continue
        while code:
            n=CODES.get(code)
            if allowed(n):return n
            code=code.rsplit(".",1)[0] if "." in code else ""
    for rule,n in RULES["VRI_WORDS"]:
        if allowed(n) and _matches(rule,text):return n
    return None


def osm_class(props,tinao=False):
    for field in ("Землепользование","Природа","Отдых"):
        value=props.get(field)
        if not value:continue
        for rule,n in RULES["OSM_USE"]:
            if (tinao or n not in AGRI) and _matches(rule,value):
                return 12 if n==11 and tinao else n
    return None
