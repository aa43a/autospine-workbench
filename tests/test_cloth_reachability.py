import math
import unittest
from autospine_workbench.asset.planning.cloth_reachability import inspect


class ReachabilityTests(unittest.TestCase):
    def test_target_outside_anchor_path_is_impossible(self):
        p=[[0.,0.],[1.,0.],[0.,1.]];target=[[0.,0.],[1.,0.],[0.,4.]]
        r=inspect(p,p,[[0,1,2]],[2],target,upper=1.4)
        self.assertEqual(r['status'],'target_unreachable_with_fixed_boundary')
        self.assertAlmostEqual(r['target_rms_lower_bound_px'],2.6)
        self.assertEqual(r['records'][0]['path'],[0,2])
        self.assertFalse(r['selected'])

    def test_similarity_and_no_counterexample_do_not_prove_feasibility(self):
        p=[[0.,0.],[1.,0.],[0.,1.]];target=[[0.,0.],[1.,0.],[0.,4.]]
        move=lambda points:[[10-3*y,20+3*x] for x,y in points]
        r=inspect(move(p),move(p),[[0,1,2]],[2],move(target))
        self.assertAlmostEqual(r['target_rms_lower_bound_px'],7.8)
        r=inspect(p,p,[[0,1,2]],[2],p)
        self.assertEqual(r['status'],'no_path_bound_counterexample')
        self.assertNotIn('passed',r)

    def test_disconnected_and_invalid_inputs(self):
        p=[[0.,0.],[1.,0.],[0.,1.],[10.,10.]]
        r=inspect(p,p,[[0,1,2]],[3],p)
        self.assertEqual(r['unanchored_vertices'],[3])
        self.assertEqual(r['status'],'unanchored_component')
        for bad in [True,float('nan'),0]:
            with self.assertRaisesRegex(ValueError,'input'):inspect(p,p,[[0,1,2]],[2],p,upper=bad)

    def test_finite_inputs_with_overflow_are_rejected(self):
        p=[[-1e308,0.],[1e308,0.],[0.,1.]]
        with self.assertRaisesRegex(ValueError,'nonfinite_distance'):
            inspect(p,p,[[0,1,2]],[2],p)

    def test_bound_uses_moving_anchor_and_is_deterministic(self):
        p=[[0.,0.],[1.,0.],[0.,1.]]
        moved=[[10.,0.],[11.,0.],[10.,1.]]
        a=inspect(p,moved,[[0,1,2]],[2],p)
        b=inspect(p,moved,[[2,1,0]],[2],p)
        self.assertEqual(a,b)
        self.assertGreater(a['target_rms_lower_bound_px'],8.)
