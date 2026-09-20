"""Real affine foot-point QA, half-open intervals and bounded reversible correction."""
from copy import deepcopy
import unittest

from autospine_workbench.targets.character43.motion_contacts import apply, analyze, schedule


def fixture(scale=1):
    doc = dict(bones=[dict(name='root', x=0, y=0, rotation=0),
                      dict(name='foot_l', parent='root', x=-20*scale, y=0, rotation=0),
                      dict(name='foot_r', parent='root', x=20*scale, y=0, rotation=0)],
               skins=[dict(attachments={})], animations={'walk': {'bones': {'root': {
                   'translate': [dict(time=0, x=0, y=0), dict(time=1, x=5*scale, y=0)]}}}})
    motion = dict(duration_ticks=1000000, ticks_per_second=1000000,
                  markers=[dict(kind='contact', limb=s, start_tick=0, end_tick=800000, mode='annotation_only')
                           for s in ('leg.left', 'leg.right')])
    return doc, motion


class MotionContactTests(unittest.TestCase):
    def test_small_common_slip_corrected_without_changing_rig_and_can_be_disabled(self):
        doc, motion = fixture()
        original = deepcopy(doc)
        fixed, report = apply(doc, 'walk', motion, [0, .5, 1], 100)
        self.assertEqual(doc, original)
        self.assertTrue(report['selected'], report)
        self.assertEqual(report['status'], 'ankle_proxy_corrected')
        self.assertGreater(report['before']['max_drift_px'], 3.9)
        self.assertLess(report['after']['max_drift_px'], .01)
        self.assertEqual(fixed['bones'], doc['bones'])
        kept, disabled = apply(doc, 'walk', motion, [0, .5, 1], 100, enabled=False)
        self.assertEqual(kept, original)
        self.assertFalse(disabled['selected'])
        self.assertEqual(disabled['status'], 'needs_changes')

    def test_scale_covariance_and_double_support_conflict(self):
        for scale in (.2, 1, 10):
            doc, motion = fixture(scale)
            _, report = apply(doc, 'walk', motion, [0, .5, 1], 100*scale)
            self.assertTrue(report['selected'])
            self.assertAlmostEqual(report['before']['max_drift_px']/scale, 4)
        doc, motion = fixture()
        doc['animations']['walk']['bones']['foot_r'] = {'translate': [dict(time=0, x=0, y=0), dict(time=1, x=20, y=0)]}
        fixed, report = apply(doc, 'walk', motion, [0, .5, 1], 100)
        self.assertEqual(fixed, doc)
        self.assertFalse(report['selected'])
        self.assertIn('motion_contact_correction_limit_or_conflict', report['reason_codes'])

    def test_contact_end_is_excluded_but_left_limit_is_measured(self):
        doc, motion = fixture()
        times = schedule(motion, [0, 1])
        report = analyze(doc, 'walk', motion, times, 100)
        for interval in report['intervals']:
            self.assertTrue(all(s['time'] < .8 for s in interval['samples']))
            self.assertGreater(interval['worst_time'], .799999)

    def test_absent_labels_are_unknown_not_passed(self):
        doc, motion = fixture()
        motion['markers'] = []
        kept, report = apply(doc, 'walk', motion, [0, .5, 1], 100)
        self.assertEqual(kept, doc)
        self.assertIsNone(report['before']['passed'])
        self.assertEqual(report['status'], 'unavailable_no_labels')

    def test_large_correction_or_snap_never_auto_adopted(self):
        doc, motion = fixture()
        doc['animations']['walk']['bones']['root']['translate'][-1]['x'] = 100
        kept, report = apply(doc, 'walk', motion, [0, .5, 1], 100)
        self.assertEqual(kept, doc)
        self.assertFalse(report['selected'])
        doc, motion = fixture()
        doc['animations']['walk']['bones']['root']['translate'] = [
            dict(time=0, x=0, y=0), dict(time=.01, x=10, y=0), dict(time=1, x=10, y=0)]
        kept, report = apply(doc, 'walk', motion, [0, .01, 1], 100)
        self.assertEqual(kept, doc)
        self.assertEqual(report['reason_codes'], ['motion_contact_transition_too_fast'])
