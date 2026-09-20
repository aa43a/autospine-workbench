from copy import deepcopy
import unittest

from autospine_workbench.targets.character43.contact_phase_candidate import build
from autospine_workbench.targets.character43.affine_pose import matrices
from test_motion_contacts import fixture


class ContactPhaseTests(unittest.TestCase):
    def make(self):
        doc, motion = fixture()
        motion['markers'] = [dict(kind='contact', limb=side, start_tick=start, end_tick=end)
                             for side, start, end in [('leg.left', 0, 400000),
                                 ('leg.right', 400000, 800000), ('leg.left', 840000, 950000)]]
        return doc, motion

    def test_entry_uses_corrected_position_and_release_takeover_has_no_snap(self):
        doc, motion = self.make()
        original = deepcopy(doc)
        candidate, report = build(doc, 'walk', motion, [0, .4, .8, .84, .95, 1], 100)
        self.assertIsNotNone(candidate, report['reason_codes'])
        self.assertEqual(doc, original)
        self.assertFalse(report['selected'])
        self.assertLess(report['after']['max_drift_px'], .001)
        self.assertAlmostEqual(matrices(candidate, 'walk', .4)['foot_r'][4], 20)
        for t in (.4, .8, .84, .95):
            before = matrices(candidate, 'walk', t-1e-8)['root'][4]
            after = matrices(candidate, 'walk', t+1e-8)['root'][4]
            self.assertLess(abs(after-before), 1e-5)

    def test_unbounded_release_speed_is_rejected(self):
        doc, motion = self.make()
        candidate, report = build(doc, 'walk', motion, [0, 1], 100, release_seconds=.001)
        self.assertIsNone(candidate)
        self.assertIn('phase_root_speed_limit', report['reason_codes'])

    def test_overlapping_same_foot_intervals_are_rejected(self):
        doc, motion = self.make()
        motion['markers'][2]['start_tick'] = 200000
        with self.assertRaisesRegex(ValueError, 'overlap'):
            build(doc, 'walk', motion, [0, 1], 100)

    def test_incompatible_bilateral_support_is_not_accepted(self):
        doc, motion = self.make()
        motion['markers'] = [dict(kind='contact', limb=side, start_tick=0, end_tick=1000000)
                             for side in ('leg.left', 'leg.right')]
        doc['animations']['walk']['bones']['foot_r'] = {'translate': [
            dict(time=0, x=0, y=0), dict(time=1, x=10, y=0)]}
        candidate, report = build(doc, 'walk', motion, [0, 1], 100)
        self.assertIsNone(candidate)
        self.assertIn('phase_contact_residual', report['reason_codes'])
        self.assertFalse(report['selected'])


if __name__ == '__main__':
    unittest.main()
