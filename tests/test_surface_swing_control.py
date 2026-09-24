import unittest
import numpy as np
from autospine_workbench.targets.character43.surface_swing_control import decompose


class SwingControlTests(unittest.TestCase):
    def test_separates_twist_while_preserving_direction(self):
        swing=np.array([[0.,-1,0],[1,0,0],[0,0,1]])
        twist=np.array([[1.,0,0],[0,0,-1],[0,1,0]])
        result,report=decompose(swing@twist,[1,0,0])
        np.testing.assert_allclose(result,swing,atol=1e-12)
        self.assertAlmostEqual(report['removed_twist_degrees'],90)
        self.assertLess(report['reconstruction_error'],1e-12)
        self.assertLess(report['axis_error'],1e-12)
        self.assertFalse(report['accepted'])

    def test_identity_and_half_turn_twist(self):
        for r,angle in ((np.eye(3),0),(np.diag([1.,-1,-1]),180)):
            swing,report=decompose(r,[1,0,0])
            np.testing.assert_allclose(swing,np.eye(3))
            self.assertAlmostEqual(abs(report['removed_twist_degrees']),angle)

    def test_ambiguous_swing_and_nonrigid_input_rejected(self):
        for r in (np.diag([-1.,1,-1]),np.eye(3)*2):
            with self.assertRaises(ValueError):decompose(r,[1,0,0])
