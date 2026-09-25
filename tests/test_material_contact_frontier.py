import unittest
import numpy as np
from autospine_workbench.targets.character43.material_contact_frontier import locate


class MaterialFrontierTests(unittest.TestCase):
    def fixture(self):
        y, x = np.mgrid[:3, :4]
        points = np.stack((x + .5, y + .5), axis=-1)
        return np.full((3, 4), 255), np.tile([255, 255, 0, 0], (3, 1)), points, np.ones((3, 4), bool)

    def test_crossing_is_in_material_not_mesh_perimeter(self):
        args = self.fixture()
        result = locate(*args, [2, 1.5], 10)
        self.assertEqual(len(result['samples']), 3)
        self.assertAlmostEqual(result['samples'][0]['world'][0], 1.5 + 1/255)
        self.assertFalse(result['selected'])
        self.assertEqual(result['authority'], 'none')

    def test_support_and_radius_do_not_create_artificial_frontier(self):
        arm, body, points, valid = self.fixture()
        self.assertEqual(locate(arm, np.full_like(body, 255), points, valid, [2, 1.5], .5)['samples'], [])
        arm[:, 2] = 0
        self.assertEqual(locate(arm, body, points, valid, [2, 1.5], 10)['samples'], [])
        arm[:, 2] = 255
        valid[:, 2] = False
        self.assertEqual(locate(arm, body, points, valid, [2, 1.5], 10)['samples'], [])

    def test_world_space_radius_and_input_unchanged(self):
        args = self.fixture()
        before = [a.copy() for a in args]
        result = locate(*args, [1.5, 1.5], .01)
        self.assertEqual(len(result['samples']), 1)
        for a, b in zip(args, before):
            np.testing.assert_array_equal(a, b)
        with self.assertRaises(ValueError):
            locate(*args, [0, 0], float('nan'))
