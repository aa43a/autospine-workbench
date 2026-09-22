import unittest
import numpy as np
from autospine_workbench.targets.character43.local_arap import solve


class LocalArapTests(unittest.TestCase):
    def test_rigid_pose_is_invariant(self):
        setup = [[0, 0], [1, 0], [1, 1], [0, 1]]
        posed = [[3-y, 4+x] for x, y in setup]
        result, _ = solve(setup, posed, [[0, 1, 2], [0, 2, 3]], [2], 1)
        np.testing.assert_allclose(result, posed, atol=1e-9)

    def test_pins_and_budget_survive_deformation(self):
        setup = [[0, 0], [1, 0], [1, 1], [0, 1]]
        posed = [[0, 0], [1, 0], [3, 3], [0, 1]]
        result, report = solve(setup, posed, [[0, 1, 2], [0, 2, 3]], [2], .2)
        self.assertLessEqual(report['maximum_displacement'], .20000001)
        self.assertEqual([result[i] for i in (0, 1, 3)], [posed[i] for i in (0, 1, 3)])

    def test_unpinned_component_rejected(self):
        with self.assertRaises(ValueError):
            solve([[0, 0], [1, 0], [0, 1]], [[0, 0], [1, 0], [0, 1]], [[0, 1, 2]], [0, 1, 2], 1)
