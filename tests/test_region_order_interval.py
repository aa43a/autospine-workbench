from copy import deepcopy
import unittest

from test_depth_region_partition import source
from autospine_workbench.targets.character43.region_order_candidate import build
from autospine_workbench.targets.character43.depth_sample_times import repair_times


class IntervalOrderTests(unittest.TestCase):
    def test_half_open_interval_preserves_setup_and_other_animation(self):
        doc, _ = source()
        doc['animations']['other'] = deepcopy(doc['animations']['test'])
        original = deepcopy(doc)
        candidate, report = build(doc, 'a', [0, 2], 'b', 'after',
                                  animation='test', interval=[.25, .75])
        self.assertEqual(doc, original)
        self.assertEqual([s['name'] for s in candidate['slots']], report['setup_order'])
        self.assertEqual(report['setup_order'], ['a-depth-001', 'a-depth-002', 'a-depth-003', 'b'])
        self.assertEqual(report['active_order'], ['a-depth-002', 'b', 'a-depth-001', 'a-depth-003'])
        self.assertNotIn('drawOrder', candidate['animations']['other'])
        self.assertEqual(candidate['animations']['test']['drawOrder'][-1], dict(time=.75, offsets=[]))
        self.assertEqual(candidate['animations']['test']['bones'], original['animations']['test']['bones'])

    def test_invalid_interval_never_mutates_source(self):
        doc, _ = source(); original = deepcopy(doc)
        for interval in ([], [0], [0, 2], [-1, .5], [.5, .5], [.8, .2],
                         [False, .5], [0, float('nan')], [0, float('inf')]):
            with self.assertRaisesRegex(ValueError, 'interval_invalid'):
                build(doc, 'a', [0], 'b', 'after', animation='test', interval=interval)
        with self.assertRaisesRegex(ValueError, 'animation_invalid'):
            build(doc, 'a', [0], 'b', 'after', animation='absent', interval=[0, 1])
        self.assertEqual(doc, original)

    def test_boundary_samples(self):
        doc, _ = source()
        candidate, _ = build(doc, 'a', [0], 'b', 'after', animation='test', interval=[.25, .75])
        depth = dict(pairs=[dict(samples=[dict(tick=0), dict(tick=1000000)])])
        times = repair_times(candidate, 'test', depth)
        for boundary in (.25, .75):
            for delta in (-1e-4, 0, 1e-4):
                self.assertIn(boundary+delta, times)


if __name__ == '__main__':
    unittest.main()
