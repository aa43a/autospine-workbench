from copy import deepcopy
import unittest

from autospine_workbench.targets.character43.inferred_contacts import measure
from autospine_workbench.targets.character43.motion_contact_review import render
from autospine_workbench.targets.character43.final_motion_contact import recheck
from test_motion_contacts import fixture


class InferredContactTests(unittest.TestCase):
    def test_drift_measured_without_modification_or_fabricated_source_labels(self):
        doc, motion = fixture()
        hypothesis = dict(schema='autospine.source-contact-candidate/v1', markers=motion['markers'],
                          ticks_per_second=1_000_000)
        motion['markers'] = []
        original = deepcopy((doc, motion, hypothesis))
        kept, report = measure(doc, 'walk', motion, [0, .5, 1], 100, hypothesis)
        self.assertEqual((doc, motion, hypothesis), original)
        self.assertEqual(kept, doc)
        self.assertFalse(report['selected'])
        self.assertEqual(report['status'], 'inferred_proxy_drift')
        self.assertGreater(report['before']['max_drift_px'], 3.9)
        self.assertIn('自动推断', render(report).decode())

    def test_clipped_interval_is_shifted_and_intersected(self):
        doc, motion = fixture()
        hypothesis = dict(schema='autospine.source-contact-candidate/v1', markers=deepcopy(motion['markers']),
                          ticks_per_second=1_000_000)
        motion['markers'] = []
        _, report = measure(doc, 'walk', motion, [0, .5, 1], 100, hypothesis, clip_bounds=(500000, 1500000))
        self.assertAlmostEqual(report['before']['intervals'][0]['end'], .3)
        _, empty = measure(doc, 'walk', motion, [0, .5, 1], 100, hypothesis, clip_bounds=(900000, 1900000))
        self.assertEqual(empty['status'], 'inferred_support_unavailable')
        self.assertIsNone(empty['before']['passed'])

    def test_existing_source_contact_cannot_be_overwritten(self):
        doc, motion = fixture()
        with self.assertRaisesRegex(ValueError, 'take_precedence'):
            measure(doc, 'walk', motion, [0, 1], 100,
                    dict(schema='autospine.source-contact-candidate/v1', markers=[]))

    def test_final_check_uses_same_clip_windows_as_initial_measurement(self):
        doc, motion = fixture()
        hypothesis = dict(schema='autospine.source-contact-candidate/v1',
                          markers=deepcopy(motion['markers']), ticks_per_second=1_000_000)
        motion['markers'] = []
        before = deepcopy((doc, motion, hypothesis))
        for bounds, expected_end in [((500000, 1500000), .3), ((900000, 1900000), None)]:
            _, report = measure(doc, 'walk', motion, [0, .1, .2, .5, 1], 100,
                                hypothesis, clip_bounds=bounds)
            final = recheck(doc, 'walk', motion, report, [0, .1, .2, .5, 1], 100)
            intervals = final['after']['intervals']
            if expected_end is None:
                self.assertEqual(intervals, [])
                self.assertIsNone(final['after']['passed'])
            else:
                self.assertEqual(intervals[0]['start'], 0)
                self.assertEqual(intervals[0]['end'], expected_end)
                self.assertEqual(intervals[0]['end'], report['before']['intervals'][0]['end'])
                # Final Runtime samples differ from the initial augmented grid.
                self.assertEqual(intervals[0]['max_drift_px'], 1.0)
        self.assertEqual((doc, motion, hypothesis), before)


if __name__ == '__main__':
    unittest.main()
