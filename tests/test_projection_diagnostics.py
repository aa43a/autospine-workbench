import unittest
from autospine_workbench.targets.character43.projection_diagnostics import summarize
from autospine_workbench.targets.character43.motion_clip import selected_ratios


class ProjectionDiagnosticsTests(unittest.TestCase):
    def test_intervals_include_all_samples_and_restore_after_gap(self):
        report = summarize({'arm': [1, .1, .15, 1, .05]}, [0, 1, 2, 3, 4])
        row = report['records'][0]
        collapsed = [r for r in row['intervals'] if r['reason'].startswith('projected_segment')]
        self.assertEqual([(r['start_time'], r['end_time']) for r in collapsed], [(1, 2), (4, 4)])
        self.assertEqual(row['minimum_time'], 4)
        self.assertFalse(report['passed'])

    def test_baseline_collapse_is_distinct_from_later_collapse(self):
        row = summarize({'leg': [0, 1, 1]}, [0, 1, 2])['records'][0]
        self.assertTrue(row['baseline_collapsed'])
        self.assertIsNone(row['relative_length'])

    def test_matches_current_length_gate_without_changing_thresholds(self):
        for values in ([1, 1, 1], [.2, .2, .3], [1, .499, 1], [.1, .3, .4], [.3, .8, .3]):
            times = [0, 1, 2]
            try:
                selected_ratios(values, times)
                passed = True
            except ValueError:
                passed = False
            self.assertEqual(summarize({'leg': values}, times)['passed'], passed)

    def test_nonfinite_and_misaligned_data_rejected(self):
        for values in ([1], [1, float('nan')], [1, -1]):
            with self.assertRaises(ValueError):
                summarize({'leg': values}, [0, 1])


if __name__ == '__main__':
    unittest.main()
