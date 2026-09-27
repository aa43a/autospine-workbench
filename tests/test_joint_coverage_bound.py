import unittest
import numpy as np
from autospine_workbench.targets.character43.joint_coverage_bound import check


class JointCoverageBoundTests(unittest.TestCase):
    def test_summed_budgets_cannot_bridge_far_support(self):
        mesh=dict(triangles=[0,1,2],uvs=[0,0,1,0,0,1])
        result=check(mesh,[[20,0],[24,0],[20,4]],np.full((4,4),255.),[0,0])
        self.assertEqual(result['status'],'outside_joint_displacement_budget')
        self.assertGreater(result['evidence']['conservative_distance_lower_bound_px'],10)

    def test_close_support_is_only_not_ruled_out(self):
        mesh=dict(triangles=[0,1,2],uvs=[0,0,1,0,0,1])
        result=check(mesh,[[0,0],[4,0],[0,4]],np.full((4,4),255.),[1,1])
        self.assertEqual(result['status'],'not_ruled_out')
