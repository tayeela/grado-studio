"""Проверяет, что новый набор не теряет слова владельца при другом числе страниц.

Запуск: python -m pytest apps/grado2/tests/test_recipe_expect.py.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tools'))
from album_check import recipe_expect


class RecipeExpect(unittest.TestCase):
    def test_legacy_count_unchanged_and_new_continuations_keep_owner_requirements(self):
        self.assertEqual(recipe_expect(None,'gol')['pages'],11)
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'spec.json'
            path.write_text(json.dumps({'sheets':[{'recipeId':'sushpol-mytishchi'} for _ in range(17)]}))
            expected=recipe_expect(path,'gol')
        self.assertEqual(expected['pages'],17)
        self.assertTrue(any('1,66 га' in v.get('text','') for v in expected['require']))
        self.assertTrue(any('вл. 8' in v.get('text','') for v in expected['require']))
        self.assertTrue(any('ценочная' in v.get('re','') for v in expected['forbid']))
