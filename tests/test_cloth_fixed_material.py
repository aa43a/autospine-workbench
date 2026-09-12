import unittest
from autospine_workbench.asset.planning.cloth_fixed_material import inspect


class FixedMaterialTests(unittest.TestCase):
    def test_fixed_compression_is_infeasible_regardless_of_free_vertex(self):
        setup = [[0., 0.], [1., 0.], [0., 1.]]
        for free_point in ([0., 1.], [100., 200.]):
            result = inspect(setup, [[0., 0.], [.5, 0.], free_point], [[0, 1, 2]], [2])
            self.assertEqual(result['status'], 'infeasible_with_fixed_endpoints')
            self.assertEqual(result['violations'], [dict(edge=[0, 1], stretch=.5)])

    def test_no_counterexample_is_not_global_pass(self):
        p = [[0., 0.], [1., 0.], [0., 1.]]
        result = inspect(p, [[0., 0.], [1., 0.], [0., -1.]], [[0, 1, 2]], [2])
        self.assertEqual(result['status'], 'no_fixed_edge_counterexample')
        self.assertNotIn('passed', result)
