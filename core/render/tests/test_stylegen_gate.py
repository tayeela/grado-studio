"""Гейт правила 2: закоммиченные JSON стилей == вывод их генераторов.

Стили ЛГР/Генплана/дорог OSM генерируются из tools/gen_*.py и НЕ правятся
руками. Без этого гейта правка генератора без перегенерации (или ручная
правка JSON) проходит молча — и холст/печать расходятся с эталоном.

Тест запускает каждый генератор как подпроцесс (он пишет свой JSON),
сравнивает с закоммиченным содержимым и ВОССТАНАВЛИВАЕТ файл, чтобы прогон
тестов не оставлял дерево изменённым.
"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STYLES = ROOT / "core" / "render" / "grado_render" / "styles"

CASES = [
    ("gen_moscow_lgr.py", "moscow_lgr.json"),
    ("gen_moscow_genplan.py", "moscow_genplan.json"),
    ("gen_osm_highway.py", "osm_highway.json"),
]


class TestStyleGeneratorsInSync(unittest.TestCase):
    def _check(self, script, out_name):
        gen = ROOT / "tools" / script
        out = STYLES / out_name
        self.assertTrue(gen.exists(), f"генератор не найден: {gen}")
        committed = out.read_bytes()
        try:
            subprocess.run([sys.executable, str(gen)], cwd=str(ROOT),
                           check=True, capture_output=True)
            regenerated = out.read_bytes()
        finally:
            out.write_bytes(committed)   # не оставлять дерево изменённым
        self.assertEqual(
            regenerated, committed,
            f"{out_name} расходится с выводом {script}: перегенерируй "
            f"(python3 tools/{script}) и закоммить JSON (правило 2).")

    def test_moscow_lgr_in_sync(self):
        self._check(*CASES[0])

    def test_moscow_genplan_in_sync(self):
        self._check(*CASES[1])

    def test_osm_highway_in_sync(self):
        self._check(*CASES[2])


if __name__ == "__main__":
    unittest.main()
