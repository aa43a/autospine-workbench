import math
import unittest
from autospine_workbench.targets.character43.corrective_transport import transport
from autospine_workbench.targets.character43.area_projection import project
from test_character_area_projection import context


class TransportTests(unittest.TestCase):
    def test_correction_rotates_and_scales_without_duplicate_translation(self):
        points=transport([[100,200]],[[(0,.25),(1,.75)]],[2,0,0,2],
            [{'name':'a'},{'name':'b'}],{'a':(0,-1,2,0,999,999),'b':(1,0,0,.5,999,999)})
        self.assertEqual(points,[[100,201.75]])

    def test_warm_start_cannot_shift_fixed_points_or_accumulate_budget(self):
        base=[[0,0],[1,0],[0,.4]]
        points,_=project(context([False,False,True],.2),base,initial=[[100,100],[101,100],[100,100]])
        self.assertEqual(points[:2],base[:2])
        self.assertLessEqual(math.dist(points[2],base[2]),.200000001)

    def test_wrong_offset_inventory_rejected(self):
        with self.assertRaisesRegex(ValueError,'inventory'):
            transport([[0,0]],[[(0,1)]],[],[],{})
