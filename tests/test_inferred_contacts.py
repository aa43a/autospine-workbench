from copy import deepcopy
import unittest

from autospine_workbench.targets.character43.inferred_contacts import measure
from autospine_workbench.targets.character43.motion_contact_review import render
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


if __name__ == '__main__':
    unittest.main()
