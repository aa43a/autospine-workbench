"""Constrained candidates must not silently fall back to arbitrary boundaries."""
import math
import unittest
from tests.test_mount_contact import rect
from autospine_workbench.asset.planning.mount_contact_search import search


class SearchTests(unittest.TestCase):
    def test_upper_edge_does_not_follow_low_pelvis_anchor(self):
        result=search(rect(0,0,12,40),rect(-3,-2,18,6),[0,0,12,40],[6,35],'garment','pelvis',100)
        self.assertTrue(result['candidates'])
        self.assertTrue(all(c['source_xy'][1]<=10 for c in result['candidates']))
        self.assertLessEqual(len(result['candidates']),3)
        self.assertEqual(result['policy'],'source_upper_quarter')

    def test_empty_hand_window_does_not_search_other_hand(self):
        result=search(rect(0,0,4,4),rect(80,0,4,4),[0,0,4,4],[1,1],'prop','hand_l',100)
        self.assertEqual(result['reason_code'],'no_boundary_in_search_window')
        self.assertEqual(result['candidates'],[])
        other=search(rect(0,0,4,4),rect(0,0,4,4),[0,0,4,4],[1,1],'prop','chest',100)
        self.assertEqual(other['policy'],'unsupported_relation')

    def test_candidate_spacing_and_translation(self):
        a=rect(0,0,30,20);b=rect(0,-3,30,4)
        result=search(a,b,[0,0,30,20],[15,10],'garment','pelvis',100)
        shifted=search({(x+100,y+20) for x,y in a},{(x+100,y+20) for x,y in b},
                       [100,20,130,40],[115,30],'garment','pelvis',100)
        self.assertEqual([r['distance_px'] for r in result['candidates']],
                         [r['distance_px'] for r in shifted['candidates']])
        points=[r['source_xy'] for r in result['candidates']]
        self.assertTrue(all(math.dist(a,b)>=8 for i,a in enumerate(points) for b in points[i+1:]))
        self.assertEqual(result,search(a,b,[0,0,30,20],[15,10],'garment','pelvis',100))

    def test_wing_window_and_nonfinite_geometry(self):
        self.assertEqual(search(rect(100,100,4,4),rect(0,0,4,4),[100,100,104,104],
                                [0,0],'wing','chest',100)['candidates'],[])
        with self.assertRaises(ValueError):search(set(),set(),[0,0,4,4],[0,0],'wing','chest',float('nan'))
