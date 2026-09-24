import unittest
import numpy as np
from autospine_workbench.targets.character43.surface_local_projection import solve


class LocalProjectionTests(unittest.TestCase):
    def test_rigid_pose_unchanged(self):
        p=np.array([[0.,0,0],[2,0,0],[0,2,0]])
        out,r=solve(p,p+[1,2,3],[[0,1,2]],[2])
        np.testing.assert_array_equal(out,p+[1,2,3]);self.assertTrue(r['geometry_passed'])

    def test_repairs_local_compression_with_fixed_neighbors(self):
        rest=[[0.,0,0],[2,0,0],[0,2,0]];pose=np.array([[0.,0,0],[2,0,0],[0,.4,0]])
        out,r=solve(rest,pose,[[0,1,2]],[2],budget=1)
        np.testing.assert_array_equal(out[:2],pose[:2]);self.assertTrue(r['geometry_passed'])
        self.assertLessEqual(r['maximum_displacement'],1);self.assertFalse(r['accepted'])

    def test_infeasible_fixed_or_budget_constraints_remain_failure(self):
        rest=[[0.,0,0],[2,0,0],[0,2,0]];pose=[[0.,0,0],[2,0,0],[0,.4,0]]
        for free in ([],[2]):
            _,r=solve(rest,pose,[[0,1,2]],free,budget=.01,iterations=20)
            self.assertFalse(r['geometry_passed']);self.assertLessEqual(r['maximum_displacement'],.01000001)
