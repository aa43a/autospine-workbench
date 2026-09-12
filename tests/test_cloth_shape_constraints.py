import unittest
from autospine_workbench.asset.planning.cloth_shape_constraints import refine
from autospine_workbench.asset.planning.component_local_solver import metrics


class ClothConstraintTests(unittest.TestCase):
    def test_preserves_fixed_vertices_and_setup(self):
        p = [[0., 0.], [1., 0.], [1., 1.], [0., 1.]]; tri = [[0, 1, 2], [0, 2, 3]]
        result, info = refine(p, tri, p, [2, 3], p)
        for a, b in zip(p, result):
            for x, y in zip(a, b): self.assertAlmostEqual(x, y, places=9)
        self.assertFalse(info['selected'])
        self.assertEqual(result[:2], p[:2])
        self.assertEqual(info['profile'], 'pinned-arap-area-edge-refinement-v1')

    def test_infeasible_fixed_edge_remains_visible(self):
        p = [[0., 0.], [1., 0.], [0., 1.]]; tri = [[0, 1, 2]]
        fixed = [[0., 0.], [4., 0.], [0., 1.]]
        result, info = refine(p, tri, fixed, [2], fixed)
        self.assertEqual(result[:2], fixed[:2])
        self.assertGreater(metrics(p, result, tri)['max_edge_stretch'], 2)
        self.assertFalse(info['selected'])
