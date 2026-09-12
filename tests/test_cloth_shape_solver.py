from copy import deepcopy
import importlib.util
import unittest
from autospine_workbench.asset.planning.cloth_shape_solver import solve


@unittest.skipUnless(importlib.util.find_spec('numpy') and importlib.util.find_spec('scipy'), 'optional numerical solver')
class ClothShapeTests(unittest.TestCase):
    def test_setup_fixed_boundary_and_determinism(self):
        points = [[0., 0.], [1., 0.], [1., 1.], [0., 1.]]
        triangles = [[0, 1, 2], [0, 2, 3]]
        before = deepcopy(points)
        result, report = solve(points, triangles, points, [2, 3], points)
        for p, q in zip(points, result):
            for a, b in zip(p, q): self.assertAlmostEqual(a, b, places=10)
        self.assertEqual(points, before)
        self.assertFalse(report['selected'])
        target = [[0., 0.], [1., 0.], [1.2, .8], [.2, .8]]
        changed = solve(points, triangles, points, [2, 3], target)
        self.assertEqual(changed, solve(points, triangles, points, [2, 3], target))
        self.assertEqual(changed[0][:2], points[:2])
        self.assertNotEqual(changed[0][2:], points[2:])
        seeded = solve(points, triangles, points, [2, 3], target, seed=changed[0])
        self.assertEqual(seeded[0][:2], points[:2])
        self.assertTrue(seeded[1]['seeded'])

    def test_unanchored_and_degenerate_fail(self):
        points = [[0., 0.], [1., 0.], [0., 1.]]
        with self.assertRaisesRegex(ValueError, 'unanchored'):
            solve(points, [[0, 1, 2]], points, [0, 1, 2], points)
        with self.assertRaisesRegex(ValueError, 'degenerate'):
            p = [[0., 0.], [1., 0.], [2., 0.]]
            solve(p, [[0, 1, 2]], p, [2], p)
        with self.assertRaisesRegex(ValueError, 'seed'):
            solve(points, [[0, 1, 2]], points, [2], points, seed=[[float('nan'), 0]]*3)
