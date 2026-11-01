"""Сверяет серверную классификацию со случаями, исполненными исходным landUseOf JavaScript.

Запуск: python -m pytest apps/grado2/tests/test_sushpol_rules.py.
"""
import unittest
import sushpol_rules as R


class RulesTest(unittest.TestCase):
    def test_all_original_javascript_cases(self):
        for case in R.PASSPORT['contractCases']:
            with self.subTest(case=case):
                self.assertEqual(R.land_class({'ВРИ':case['text']},case['tinao']),case['classId'])

    def test_urban_and_tinao_osm_residential(self):
        self.assertEqual(R.osm_class({'Землепользование':'residential'}),11)
        self.assertEqual(R.osm_class({'Землепользование':'residential'},True),12)
        self.assertIsNone(R.osm_class({'Землепользование':'farmland'}))
