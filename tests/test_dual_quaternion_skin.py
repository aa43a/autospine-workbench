import unittest
import numpy as np
from autospine_workbench.targets.character43.dual_quaternion_skin import deform


class DualQuaternionTests(unittest.TestCase):
    def test_rigid_and_antipodal_equivalence(self):
        q=np.array([np.sqrt(.5),0,0,np.sqrt(.5)])
        for quats in ([q,q],[q,-q]):
            actual=deform([[1,0,2]],[[(0,.4),(1,.6)]],quats,[[3,4,5],[3,4,5]])
            np.testing.assert_allclose(actual,[[3,5,7]],atol=1e-12)

    def test_translation_blend(self):
        result=deform([[1,2,3]],[[(0,.25),(1,.75)]],[[1,0,0,0]]*2,[[0,0,0],[4,8,12]])
        np.testing.assert_allclose(result,[[4,8,12]])

    def test_twist_preserves_radius(self):
        q=[np.cos(np.pi/3),0,0,np.sin(np.pi/3)]
        result=deform([[1,0,0]],[[(0,.5),(1,.5)]],[[1,0,0,0],q],[[0,0,0]]*2)
        self.assertAlmostEqual(np.linalg.norm(result[0]),1)
        np.testing.assert_allclose(result,[[.5,np.sqrt(.75),0]],atol=1e-12)

    def test_half_turn_or_bad_weights_rejected(self):
        with self.assertRaises(ValueError):
            deform([[1,0,0]],[[(0,.5),(1,.5)]],[[1,0,0,0],[0,1,0,0]],[[0,0,0]]*2)
        with self.assertRaises(ValueError):
            deform([[1,0,0]],[[(0,.1)]],[[1,0,0,0]],[[0,0,0]])
