import unittest
import importlib.util
from autospine_workbench.asset.planning.cloth_shape_constraints import refine
from autospine_workbench.asset.planning.component_local_solver import metrics


@unittest.skipUnless(importlib.util.find_spec('numpy') and importlib.util.find_spec('scipy'), 'optional numerical solver')
class ClothConstraintTests(unittest.TestCase):
    def test_exact_interval_continuation_keeps_rest_pose(self):
        import numpy as np
        p = [[0., 0.], [1., 0.], [0., 1.]]
        maps = [(np.asarray(p)*(1-f), np.repeat((np.eye(2)*f)[None, :, :], 3, axis=0))
                for f in (.25, .5, .75)]
        result, info = refine(p, [[0, 1, 2]], p, [2], p, seed=p,
                              interval_maps=maps, continuation=True)
        np.testing.assert_allclose(result, p, atol=1e-10, rtol=0)
        self.assertEqual(info['continuation_seed'], 'previous_world_pose')
        self.assertFalse(info['selected'])

        material, info = refine(p, [[0, 1, 2]], p, [2], p, seed=p,
                                interval_maps=maps, continuation=True, material=True, material_subframes=True)
        np.testing.assert_allclose(material, p, atol=1e-10, rtol=0)
        self.assertTrue(info['material_passed'])
        self.assertEqual(info['profile'], 'pinned-cloth-principal-stretch-subframes-v6')

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
