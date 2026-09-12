import math
import importlib.util
import unittest
from autospine_workbench.asset.planning.cloth_interval_area import bounds
from autospine_workbench.asset.planning.cloth_shape_constraints import refine


def area(p):
    a, b, c = p
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


@unittest.skipUnless(importlib.util.find_spec('numpy') and importlib.util.find_spec('scipy'), 'optional numerical solver')
class IntervalTests(unittest.TestCase):
    def test_detects_endpoint_pass_midpoint_collapse_and_offcenter_extremum(self):
        low, high = bounds([1., .45, 1.], [0., .45, 1.5], [1., 2.45, 2.])
        self.assertAlmostEqual(low[0], 0)
        self.assertAlmostEqual(high[0], 1)
        self.assertAlmostEqual(low[1], .2)
        self.assertAlmostEqual(high[1], 2.45)
        self.assertAlmostEqual(low[2], 1)
        self.assertAlmostEqual(high[2], 2)

    def test_temporal_constraint_keeps_linear_world_interval_above_gate(self):
        setup = [[0., 0.], [1., 0.], [0., 1.]]
        angle = math.radians(120); c, s = math.cos(angle), math.sin(angle)
        target = [[0., 0.], [c, s], [-s, c]]
        points, evidence = refine(setup, [[0, 1, 2]], target, [1, 2], target,
                                  seed=setup, temporal=True)
        midpoint = [[(a+b)/2 for a, b in zip(p, q)] for p, q in zip(setup, points)]
        low, _ = bounds([area(setup)], [area(midpoint)], [area(points)])
        self.assertGreater(low[0], .5)
        self.assertEqual(points[0], target[0])
        self.assertFalse(evidence['selected'])
        self.assertIn('requires_exact_spine', evidence['temporal_scope'])
