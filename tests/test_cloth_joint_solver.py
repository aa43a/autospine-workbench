import importlib.util
import math
import unittest
from autospine_workbench.asset.planning.cloth_joint_solver import solve


@unittest.skipUnless(importlib.util.find_spec('scipy') and importlib.util.find_spec('numpy'),'optional numerical solver')
class JointSolverTests(unittest.TestCase):
    def test_fixed_vertices_budget_and_repeatability(self):
        setup=[[0.,0.],[2.,0.],[0.,2.],[2.,2.]]
        points=[[0.,0.],[2.,0.],[0.,-.5],[2.,.1]]
        args=(setup,[[0,1,2],[1,3,2]],points,[2,3],[0,1],.8)
        a,e=solve(*args);b,_=solve(*args)
        self.assertEqual(a,b);self.assertEqual(a[:2],points[:2])
        self.assertLessEqual(e['max_offset'],.8+1e-9)
        self.assertTrue(all(math.isfinite(v) for p in a for v in p))
        self.assertIn('scipy_version',e)

    def test_setup_remains_exact(self):
        p=[[0.,0.],[2.,0.],[0.,2.]]
        result,e=solve(p,[[0,1,2]],p,[2],[0,1],1.)
        self.assertEqual(result,p);self.assertEqual(e['solver_status'],'projection_sufficient')

    def test_seed_does_not_move_fixed_vertices_or_expand_budget(self):
        p=[[0.,0.],[2.,0.],[0.,2.]]
        args=(p,[[0,1,2]],p,[1,2],[0,1],.2)
        seed=[[99.,99.],[99.,99.],[99.,99.]]
        result,e=solve(*args,seed=seed)
        self.assertEqual(result[:2],p[:2])
        self.assertLessEqual(math.dist(result[2],p[2]),.2+1e-9)
        self.assertEqual(result,solve(*args,seed=seed)[0])
        with self.assertRaisesRegex(ValueError,'seed'):
            solve(*args,seed=[[0.,float('nan')]]*3)
