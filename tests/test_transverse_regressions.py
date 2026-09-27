import unittest
from m4_transverse_regressions import classify


class TransverseRegressionsTests(unittest.TestCase):
    def test_fixed_vs_movable_uses_the_solver_positive_weight_rule(self):
        setup=[[0,0],[2,0],[0,2],[2,2]]
        influences=[[(0,1),(1,0)],[(0,1)],[(0,1)],[(0,.5),(1,.5)]]
        frames=[(0,setup),(.37,[[0,0],[2,0],[0,.5],[2,.5]])]
        rows=classify(setup,[[0,1,2],[1,3,2]],influences,frames)
        self.assertEqual([r['fixed'] for r in rows],[True,False])
        self.assertEqual([r['drivers'] for r in rows],[[0],[0,1]])
        self.assertTrue(all(r['time']==.37 and r['minimum_area_ratio']==.25 for r in rows))

    def test_retains_worst_time_and_does_not_report_healthy_triangle(self):
        setup=[[0,0],[2,0],[0,2]];weights=[[(0,1)]]*3
        self.assertEqual(classify(setup,[[0,1,2]],weights,[(0,setup)]),[])
        rows=classify(setup,[[0,1,2]],weights,[(0,setup),(1,[[0,0],[2,0],[0,.2]]),(2,setup)])
        self.assertEqual(rows[0]['time'],1)
        self.assertAlmostEqual(rows[0]['minimum_area_ratio'],.1)
