import unittest
import numpy as np
from autospine_workbench.targets.character43.directional_joint_cover import cover


class DirectionalCoverTests(unittest.TestCase):
    def test_directional_growth_avoids_unnecessary_width_expansion(self):
        B=np.diag([.4,1.]);p=[[-.4,-1],[.4,-1],[.4,1],[-.4,1]]
        out,r=cover(p,[0,0],[[-1.2,0],[1.2,0]],B)
        self.assertEqual(r['status'],'bounded_directional_cover')
        self.assertAlmostEqual(r['applied_scales'][0],3,places=5)
        self.assertAlmostEqual(r['applied_scales'][1],1,places=5)
        self.assertLessEqual(r['determinant'],2);self.assertLessEqual(r['maximum_stretch'],2)

    def test_failure_preserves_original_cover(self):
        p=[[-1,-1],[1,-1],[1,1],[-1,1]]
        out,r=cover(p,[0,0],[[4,4]],np.eye(2))
        self.assertEqual(r['status'],'no_feasible_directional_cover');self.assertEqual(out,p)

    def test_padding_is_world_space(self):
        p=[[-.5,-1],[.5,-1],[.5,1],[-.5,1]]
        out,r=cover(p,[0,0],[[.75,0]],np.diag([.5,1]),padding=.1)
        self.assertEqual(r['status'],'bounded_directional_cover')
        self.assertGreaterEqual(max(x for x,y in out),.85)

    def test_invalid_base_rejected(self):
        with self.assertRaises(ValueError):cover([[0,0],[1,0],[0,1]],[0,0],[[0,0]],np.diag([-1,1]))
