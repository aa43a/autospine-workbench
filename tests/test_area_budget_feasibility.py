import math
import unittest
from autospine_workbench.targets.character43.area_budget_feasibility import inspect
from autospine_workbench.targets.spine43.continuous_pose import area


class AreaBudgetFeasibilityTests(unittest.TestCase):
    def test_exact_one_free_disk_bound_and_reverse_winding(self):
        for tri,ref in (([0,1,2],1),([0,2,1],-1)):
            ctx=dict(row={'triangles':[tri]},areas=[ref],free=[False,False,True],budget=.1)
            row=inspect(ctx,[[0,0],[2,0],[1,.3]],[.5])['failures'][0]
            self.assertAlmostEqual(row['maximum_oriented_area'],.4)
            self.assertTrue(row['exact_disk_bound'])
            ctx['budget']=.2
            self.assertEqual(inspect(ctx,[[0,0],[2,0],[1,.3]],[.5])['failures'],[])

    def test_conservative_multi_vertex_bound_does_not_reject_reachable_samples(self):
        points=[[0,0],[2,0],[1,.3]];tri=[0,1,2]
        ctx=dict(row={'triangles':[tri]},areas=[1.],free=[True]*3,budget=.2)
        for i in range(24):
            moved=[[x+.2*math.cos(i+j),y+.2*math.sin(i+j)] for j,(x,y) in enumerate(points)]
            self.assertEqual(inspect(ctx,points,[area(moved,tri)])['failures'],[])

    def test_fixed_triangle_cannot_be_repaired_by_more_sweeps(self):
        ctx=dict(row={'triangles':[[0,1,2]]},areas=[1.],free=[False]*3,budget=100)
        result=inspect(ctx,[[0,0],[2,0],[1,.3]],[.5])
        self.assertEqual(result['failures'][0]['free_vertices'],0)
