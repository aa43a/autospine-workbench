import unittest
from autospine_workbench.targets.character43.group_projection_lengths import feasible_lengths, compare_continuity


class BoundedLengthTests(unittest.TestCase):
    def test_minimal_extension_and_bounds(self):
        lengths, blend = feasible_lengths([1, 1], [2, 2], 3)
        self.assertEqual(lengths, [1.5, 1.5])
        self.assertEqual(blend, .5)

    def test_no_change_when_feasible(self):
        self.assertEqual(feasible_lengths([2, 2], [3, 3], 3), ([2, 2], 0))

    def test_unreachable_is_explicit(self):
        self.assertIsNone(feasible_lengths([1, 1], [2, 2], 5))
        self.assertIsNone(feasible_lengths([3, 1], [4, 1], 1))
        with self.assertRaises(ValueError): feasible_lengths([3, 1], [2, 2], 2)

    def test_source_motion_is_not_counted_as_introduced_jump(self):
        candidate = dict(records=[dict(side='left', steps=[11., 4.])])
        source = dict(records=[dict(side='left', steps=[12., 1.])])
        row = compare_continuity(candidate, source, [0, .1, .2])['records'][0]
        self.assertEqual(row['maximum_excess_step_degrees'], 3)
        self.assertEqual(row['time'], .2)
