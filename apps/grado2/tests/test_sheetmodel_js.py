"""Модель листа нового редактора раскладки (ui/src/sheet/model.js, stamp.js): размеры как в печати, масштаб, замечания;
команды и командная строка (commands.js), группы, отражение, «Формат по образцу» (arrange.js, с deckcraft).

Запускает ui/src/sheet/model.test.js и commands.test.js через `node --test`; библиотеки из ui/node_modules не нужны.
Запуск: python3 -m unittest apps/grado2/tests/test_sheetmodel_js.py
"""
import shutil
import subprocess
import unittest
from pathlib import Path

SHEET = Path(__file__).resolve().parents[1] / "ui" / "src" / "sheet"
TESTS = [SHEET / "model.test.js", SHEET / "commands.test.js", SHEET.parent / "viewframes.test.js"]   # и рамка вида (#119)


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class SheetModelJs(unittest.TestCase):
    def test_sheet_model(self):
        r = subprocess.run(["node", "--test", *map(str, TESTS)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("# fail 0", r.stdout)


if __name__ == "__main__":
    unittest.main()
