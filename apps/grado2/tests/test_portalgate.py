"""Очередь к порталам (portalgate.py, #51; аудит 12.10.2026, находка 7): одна выгрузка к порталу за раз."""

import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import portalgate  # noqa: E402


class PortalGate(unittest.TestCase):
    def test_second_owner_waits_same_owner_passes(self):
        g, a, b = portalgate.Gate(), object(), object()
        g.acquire({"gisogd", "nspd"}, a)
        g.acquire({"gisogd"}, a)                           # задания одной выгрузки — параллельно
        with self.assertRaises(portalgate.Busy):
            g.acquire({"nspd"}, b, timeout=0.05)
        g.acquire({"osm"}, b, timeout=0.05)                # другой портал — сразу
        got = []
        t = threading.Thread(target=lambda: (g.acquire({"gisogd"}, b), got.append(time.monotonic())))
        t.start()
        time.sleep(0.05)
        self.assertEqual(got, [])
        g.release({"gisogd"}, a)
        time.sleep(0.05)
        self.assertEqual(got, [])                          # взят дважды — держится до второго отпуска
        g.release({"gisogd", "nspd"}, a)
        t.join(1)
        self.assertEqual(len(got), 1)
        self.assertEqual(g.busy(), ["gisogd", "osm"])

    def test_portals_of_kinds(self):
        self.assertEqual(portalgate.portals_of(["gisogd", "gisogd_admin", "yandex_sit", "yandex", "nspd"]), {"gisogd", "yandex", "nspd"})


if __name__ == "__main__":
    unittest.main()
