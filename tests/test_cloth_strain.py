import importlib.util
import unittest
from autospine_workbench.asset.planning.cloth_strain import prepare, stretches


@unittest.skipUnless(importlib.util.find_spec('numpy'), 'optional strain analysis')
class StrainTests(unittest.TestCase):
    def test_principal_stretches_survive_canvas_similarity(self):
        import numpy as np
        rest = np.array([[0., 0.], [2., 0.], [.3, 1.]])
        deformed = rest @ np.diag([.25, 2.])
        for rotation in (np.eye(2), np.array([[0., -1.], [1., 0.]])):
            p = 30*rest @ rotation+[21, 34]; q = 30*deformed @ rotation+[21, 34]
            low, high = stretches(q, prepare(p, [[0, 1, 2]]))
            self.assertAlmostEqual(low[0], .25)
            self.assertAlmostEqual(high[0], 2.)

    def test_area_preserving_shear_is_still_material_distortion(self):
        import numpy as np
        from autospine_workbench.asset.planning.component_local_solver import metrics
        rest = [[0., 0.], [1., 0.], [0., 1.]]; tri = [[0, 1, 2]]
        deformed = [[0., 0.], [1., 0.], [1.2, 1.]]
        self.assertFalse(metrics(rest, deformed, tri)['bad_triangles'])
        low, high = stretches(deformed, prepare(rest, tri))
        self.assertLess(low[0], .7)
        self.assertGreater(high[0]/low[0], 3)
        with self.assertRaisesRegex(ValueError, 'degenerate'):
            prepare([[0, 0], [1, 0], [2, 0]], tri)
