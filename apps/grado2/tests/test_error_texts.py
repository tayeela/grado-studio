"""Правило 4 (владелец 10.10.2026, #51): текст ошибки в теле JSON — по-русски. Проверка по исходникам сервера.

Ищет в server.py, hub.py, fonts.py строковые литералы после "error": и в raise ValueError/HubError/ConnectorError —
в каждом должна быть хоть одна русская буква. Запуск — tools/gate.sh (unit).
"""

import re
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
FILES = ("server.py", "hub.py", "fonts.py")
LIT = r'f?"((?:[^"\\\n]|\\.)*)"'
PATTERNS = (re.compile(r'"error":\s*' + LIT), re.compile(r'raise (?:ValueError|HubError|ConnectorError)\((?:\d+,\s*)?' + LIT + r'(?!\.)'))
CYR = re.compile("[а-яё]", re.I)


class ErrorTextsRussian(unittest.TestCase):
    def test_error_literals_have_russian_letters(self):
        bad = []
        for name in FILES:
            for no, line in enumerate((APP / name).read_text(encoding="utf-8").splitlines(), 1):
                for pat in PATTERNS:
                    bad += [f"{name}:{no}: {m.group(1)}" for m in pat.finditer(line) if not CYR.search(m.group(1))]
        self.assertEqual(bad, [], "английский текст ошибки — переведите на русский (правило 4)")


if __name__ == "__main__":
    unittest.main()
