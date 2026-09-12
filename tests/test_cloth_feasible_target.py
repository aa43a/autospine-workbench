import importlib.util
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from autospine_workbench.asset.planning.cloth_feasible_target import fit


@unittest.skipUnless(importlib.util.find_spec('numpy') and importlib.util.find_spec('scipy'), 'optional numerical solver')
class FeasibleTargetTests(unittest.TestCase):
    def test_unreachable_target_keeps_material_and_fixed_vertices(self):
        p=[[0.,0.],[1.,0.],[0.,1.]]; target=[[0.,0.],[1.,0.],[0.,4.]]
        out,info=fit(p,[[0,1,2]],p,[2],target,p)
        self.assertEqual(out[:2],p[:2])
        self.assertTrue(info['improved'])
        self.assertGreaterEqual(info['min_constraint_margin'],0)
        self.assertLessEqual(info['material_max_stretch'],1.4)
        self.assertGreaterEqual(info['target_rms_px'],info['target_rms_lower_bound_px']-1e-8)
        self.assertFalse(info['selected'])

    def test_setup_and_invalid_seed(self):
        p=[[0.,0.],[1.,0.],[0.,1.]]
        out,info=fit(p,[[0,1,2]],p,[2],p,p)
        self.assertEqual(out,p)
        self.assertFalse(info['improved'])
        with self.assertRaisesRegex(ValueError,'fixed_seed'):
            fit(p,[[0,1,2]],p,[2],p,[[.1,0.],[1.,0.],[0.,1.]])
        with self.assertRaisesRegex(ValueError,'outside_limits'):
            fit(p,[[0,1,2]],p,[2],p,[[0.,0.],[1.,0.],[0.,4.]])

    def test_failed_infeasible_optimizer_cannot_replace_seed(self):
        import numpy as np
        p=[[0.,0.],[1.,0.],[0.,1.]]
        failed=SimpleNamespace(x=np.array([100.,100.]),status=9,success=False,nit=1)
        with patch('scipy.optimize.minimize',return_value=failed):
            out,info=fit(p,[[0,1,2]],p,[2],p,p)
        self.assertEqual(out,p)
        self.assertFalse(info['optimizer_success'])
        self.assertFalse(info['improved'])
