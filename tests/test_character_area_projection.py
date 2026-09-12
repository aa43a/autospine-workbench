import math
import unittest
from autospine_workbench.targets.character43.area_projection import project
from autospine_workbench.targets.spine43.continuous_pose import area


def context(free, budget):
    return dict(row={'triangles': [[0, 1, 2]]}, areas=[.5], edges=[(0, 1), (1, 2), (0, 2)],
                lengths=[1, math.sqrt(2), 1], free=free, budget=budget)


class AreaProjectionTests(unittest.TestCase):
    def test_compression_is_repaired_with_fixed_vertices_and_original_budget(self):
        original = [[0, 0], [1, 0], [0, .4]]
        points, evidence = project(context([False, False, True], .2), original)
        self.assertEqual(points[:2], original[:2])
        self.assertGreaterEqual(area(points, [0, 1, 2])/.5, .54)
        self.assertLessEqual(math.dist(points[2], original[2]), .2)
        self.assertTrue(evidence['converged'])
        self.assertEqual(project(context([False, False, True], .2), original), (points, evidence))

    def test_insufficient_budget_does_not_accumulate_across_iterations(self):
        original = [[0, 0], [1, 0], [0, .4]]
        points, evidence = project(context([False, False, True], .01), original)
        self.assertLessEqual(math.dist(points[2], original[2]), .0100000001)
        self.assertFalse(evidence['converged'])
        self.assertEqual(evidence['iterations'], 1536)

    def test_fixed_infeasible_triangle_is_retained(self):
        original = [[0, 0], [1, 0], [0, .4]]
        points, evidence = project(context([False]*3, 1), original)
        self.assertEqual(points, original)
        self.assertFalse(evidence['converged'])

    def test_nonfinite_input_fails(self):
        with self.assertRaisesRegex(ValueError, 'nonfinite'):
            project(context([True]*3, 1), [[0, 0], [1, 0], [0, float('nan')]])

    def test_narrow_fixed_boundary_relaxes_margin_but_not_acceptance_floor(self):
        original = [[0, 0], [1, 0], [0, 1.05], [1, 1.05], [.5, .1]]
        ctx = dict(row={'triangles': [[0, 1, 4], [3, 2, 4]]}, areas=[.5, .5],
                   edges=[(0, 1), (2, 3)], lengths=[1, 1], free=[False]*4+[True], budget=.6)
        points, evidence = project(ctx, original)
        self.assertEqual(points[:4], original[:4])
        self.assertTrue(evidence['converged'])
        self.assertLess(evidence['lower_target'], .55)
        self.assertGreater(evidence['lower_target'], .5)
        self.assertGreaterEqual(min(area(points, t)/.5 for t in ctx['row']['triangles']), .5)
        self.assertLessEqual(math.dist(points[4], original[4]), .6)
