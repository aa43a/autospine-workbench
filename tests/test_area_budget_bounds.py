import math
import unittest
from autospine_workbench.targets.character43.area_budget_bounds import inspect


class AreaBudgetBoundsTests(unittest.TestCase):
    def test_fixed_and_one_movable_vertex_impossibility(self):
        points=[[0,0],[1,0],[0,.1]]
        report=inspect(points,[[0,1,2]],[.5],[False,False,True],.2)
        self.assertEqual(report['status'],'infeasible_with_budget')
        self.assertAlmostEqual(report['witnesses'][0]['possible_ratio_outer_bounds'][1],.3)
        self.assertEqual(inspect(points,[[0,1,2]],[.5],[False,False,True],.4)['witnesses'],[])

    def test_winding_reversal_keeps_bound(self):
        a=inspect([[0,0],[1,0],[0,.1]],[[0,1,2]],[.5],[False]*3,10)
        b=inspect([[0,0],[1,0],[0,.1]],[[2,1,0]],[-.5],[False]*3,10)
        self.assertEqual(a['witnesses'][0]['possible_ratio_outer_bounds'],b['witnesses'][0]['possible_ratio_outer_bounds'])

    def test_large_budget_is_not_claimed_feasible(self):
        r=inspect([[0,0],[1,0],[0,-1]],[[0,1,2]],[.5],[True]*3,2)
        self.assertEqual(r['status'],'no_individual_triangle_counterexample')

    def test_invalid_data_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'nonfinite'):
            inspect([[math.nan,0],[1,0],[0,1]],[[0,1,2]],[.5],[True]*3,1)
