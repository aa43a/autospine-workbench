import unittest

from autospine_workbench.targets.character43.pose_refinement_feasibility import inspect, _area


class PoseRefinementFeasibilityTests(unittest.TestCase):
    def test_signed_area_obstruction_is_independent_of_new_point(self):
        setup = [[0, 0], [3, 0], [0, 3]]
        for posed in ([[0, 0], [3, 0], [0, -1]], [[0, 0], [3, 0], [0, .3]]):
            report = inspect(setup, posed, [[0, 1, 2]], [0])
            self.assertEqual(report['status'], 'infeasible_with_fixed_triangle_boundaries')
            for center in ([1, 1], [-100, 12], [0, 0], [5, -8]):
                child = [_area(posed+[center], t) for t in ([0, 1, 3], [1, 2, 3], [2, 0, 3])]
                self.assertAlmostEqual(sum(child), _area(posed, [0, 1, 2]))
                self.assertLess(min(a/1.5 for a in child), .5)

    def test_preserved_area_can_still_have_fixed_edge_obstruction(self):
        report = inspect([[0, 0], [1, 0], [0, 1]], [[0, 0], [3, 0], [0, 1/3]], [[0, 1, 2]], [0])
        self.assertEqual(report['counterexamples'][0]['area_ratio'], 1)
        self.assertEqual(report['counterexamples'][0]['reasons'], ['fixed_boundary_edge_exceeds_limit'])

    def test_clockwise_orientation_and_no_false_feasibility_claim(self):
        setup = [[0, 0], [0, 1], [1, 0]]
        result = inspect(setup, setup, [[0, 1, 2]], [0])
        self.assertEqual(result['status'], 'no_counterexample')
        self.assertFalse(result['feasible_proven'])

    def test_degenerate_and_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            inspect([[0, 0], [1, 0], [2, 0]], [[0, 0], [1, 0], [2, 0]], [[0, 1, 2]], [0])
        with self.assertRaises(ValueError):
            inspect([[0, 0], [1, 0], [0, 1]], [[0, 0], [1, 0], [0, float('nan')]], [[0, 1, 2]], [0])
