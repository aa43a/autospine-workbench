import unittest

from autospine_workbench.asset.planning.sleeve_boundary_budget import estimate


class BudgetHeadroomTests(unittest.TestCase):
    def test_explicit_allocation_stays_within_existing_cap(self):
        setup = [[0., 0.], [10., 0.], [0., 10.]]
        base, original = estimate(setup, [[0, 1, 2]], setup, [2], 3.)
        half, evidence = estimate(setup, [[0, 1, 2]], setup, [2], 3., headroom=.5)
        full, maximum = estimate(setup, [[0, 1, 2]], setup, [2], 3., headroom=1.)
        self.assertEqual(base, 3.)
        self.assertAlmostEqual(half, 6.5)
        self.assertAlmostEqual(full, 10.)
        self.assertEqual(evidence['cap_px'], original['cap_px'])
        self.assertEqual(maximum['cap_px'], original['cap_px'])
        self.assertEqual(evidence['estimated_budget_px'], base)
        self.assertNotIn('headroom_fraction', original)

    def test_invalid_headroom_is_rejected(self):
        for value in (-.1, 1.1, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'boundary_budget_headroom'):
                estimate([[0., 0.], [1., 0.], [0., 1.]], [[0, 1, 2]],
                         [[0., 0.], [1., 0.], [0., 1.]], [2], 3., headroom=value)
