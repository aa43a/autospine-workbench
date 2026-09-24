import math
import unittest
from autospine_workbench.targets.character43.circular_bend_capacity import inspect, nonuniform_area_bound


class CircularBendCapacityTests(unittest.TestCase):
    def test_straight_and_uniform_scale(self):
        self.assertTrue(inspect([0, 0], [100, 0], [200, 0], 10, 200)['meets_inner_area'])
        one = inspect([0, 0], [100, 0], [100, 100], 10, 200)
        two = inspect([30, -20], [230, -20], [230, 180], 20, 400)
        self.assertAlmostEqual(one['maximum_inner_area_factor'], two['maximum_inner_area_factor'])
        self.assertAlmostEqual(2*one['radius'], two['radius'])

    def test_optimum_matches_dense_search(self):
        row = inspect([0, 0], [100, 0], [40, 80], 12, 200)
        theta = math.radians(row['turn_degrees'])
        loss = 2*math.tan(theta/2)-theta
        samples = [12+(row['radius_limit']-12)*i/10000 for i in range(1, 10001)]
        numerical = max((200-loss*r)/200*(1-12/r) for r in samples)
        self.assertAlmostEqual(row['maximum_inner_area_factor'], numerical, places=7)

    def test_fold_and_collapsed_inputs(self):
        self.assertFalse(inspect([0, 0], [100, 0], [1, 1], 20, 200)['meets_inner_area'])
        self.assertEqual(inspect([0, 0], [100, 0], [0, 0], 20, 200)['status'], 'reversal')
        with self.assertRaises(ValueError):
            inspect([0, 0], [0, 0], [100, 0], 20, 200)

    def test_nonuniform_bound_includes_inner_and_outer_area(self):
        row = nonuniform_area_bound([0, 0], [100, 0], [100, 100], 12, 200)
        radius = row['minimum_radius']
        self.assertAlmostEqual(.5/(1-12/radius), 2/(1+12/radius))
        for candidate in (radius, radius+10, radius+20):
            capacity = (200-(2-math.pi/2)*candidate-12*math.pi/2)/.5
            self.assertLessEqual(capacity, row['maximum_rest_length']+1e-9)
        self.assertTrue(row['necessary_bound_passed'])
        self.assertFalse(nonuniform_area_bound([0, 0], [100, 0], [1, 1], 20, 200)['necessary_bound_passed'])
