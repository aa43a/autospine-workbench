import math
import unittest
from autospine_workbench.targets.character43.triangle_area_feasibility import inspect


class AreaBoundTests(unittest.TestCase):
    def test_fixed_compression_is_provably_unrepairable(self):
        result=inspect([[0,0],[2,0],[0,.2]],[[0,1,2]],[1],[False]*3,100)
        self.assertEqual(result['impossible_triangles'],[0])
        self.assertAlmostEqual(result['rows'][0]['maximum_ratio_bound'],.2)

    def test_one_free_vertex_has_exact_bound_with_mirrored_winding(self):
        for tri,reference in (([0,1,2],1),([0,2,1],-1)):
            row=inspect([[0,0],[2,0],[0,.2]],[tri],[reference],[False,False,True],.2)['rows'][0]
            self.assertTrue(row['bound_exact']);self.assertAlmostEqual(row['maximum_ratio_bound'],.4)
            self.assertTrue(row['impossible'])

    def test_multi_vertex_bound_contains_disk_samples(self):
        points=[[0,0],[2,0],[0,.2]];budget=.4
        row=inspect(points,[[0,1,2]],[1],[True]*3,budget)['rows'][0]
        from autospine_workbench.targets.spine43.continuous_pose import area
        for i in range(40):
            moved=[[x+budget*math.cos(i*k),y+budget*math.sin(i*k)] for k,(x,y) in enumerate(points,1)]
            self.assertLessEqual(area(moved,[0,1,2]),row['maximum_ratio_bound']+1e-12)
        self.assertFalse(row['bound_exact'])

    def test_invalid_data_rejected(self):
        with self.assertRaisesRegex(ValueError,'invalid_context'):
            inspect([[0,0]],[],[],[True],float('nan'))
