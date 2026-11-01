"""Проверяет устойчивость фотофиксации к обходу границы и недоступным дорогам.

Запуск: python -m pytest apps/grado2/tests/test_sushpol_photos.py.
"""
import copy
import unittest
from shapely.geometry import Polygon,LineString,mapping
import preparation as P
from sushpol_photos import photo_plan,allowed_road


def project(reverse=False,old_cache=False):
    ring=[(0,0),(200,0),(200,100),(0,100),(0,0)]
    if reverse:ring=list(reversed(ring))
    territory=P.to_wgs(Polygon(ring,[[(80,40),(120,40),(120,60),(80,60),(80,40)]]))
    road=P.to_wgs(LineString([(-30,-10),(230,-10)]))
    return {'territory':{'type':'Feature','geometry':mapping(territory)},'album':{'meta':{'sushpolPreparation':{'instanceId':'stable'}}},
            'data':{'osm.roads':{'osmSchema':1 if old_cache else 2,'fc':{'features':[{'id':'road','geometry':mapping(road),'properties':{'highway':'residential'}}]}}}}


class PhotoPlan(unittest.TestCase):
    def test_reverse_boundary_keeps_ids_targets_and_candidates(self):
        first,second=photo_plan(project()),photo_plan(project(True))
        self.assertEqual(first,second)
        self.assertEqual(len(first),8)
        self.assertTrue(all(0<len(x['candidates'])<=2 for x in first))
        for x in first:
            self.assertAlmostEqual(P.to_msk(__import__('shapely').geometry.Point(x['candidates'][0])).y,-10,places=5)

    def test_old_osm_cache_cannot_supply_safe_road_candidates(self):
        self.assertTrue(all(not x['candidates'] for x in photo_plan(project(old_cache=True))))

    def test_private_tunnels_bridges_and_explicit_foot_permission(self):
        cases=[({'highway':'motorway'},False),({'highway':'service','access':'private'},False),
               ({'highway':'service','access':'private','foot':'yes'},True),
               ({'highway':'footway','foot':'no'},False),({'highway':'path','tunnel':'yes','layer':'-1'},False),
               ({'highway':'path','bridge':'yes','layer':'1'},False),({'highway':'path','layer':'nan'},False)]
        for props,expected in cases:
            with self.subTest(props=props):self.assertEqual(allowed_road(props),expected)
