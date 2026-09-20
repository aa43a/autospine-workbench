from copy import deepcopy
import unittest

from autospine_workbench.targets.character43.support_timeline import build
from autospine_workbench.targets.character43.motion_contacts import analyze, schedule


def fixture():
    bones = [dict(name='root', x=0, y=0, rotation=0)]
    for s, x in [('l', -2), ('r', 2)]:
        bones.extend([dict(name='thigh_'+s, parent='root', x=x, y=0, rotation=-90),
                      dict(name='calf_'+s, parent='thigh_'+s, x=10, y=0, rotation=20),
                      dict(name='foot_'+s, parent='calf_'+s, x=10, y=0, rotation=0)])
    document = dict(bones=bones, animations={'walk': {'bones': {'root': {'translate': [
        dict(time=0, x=0, y=0), dict(time=1.2, x=2, y=0)]}}}})
    motion = dict(ticks_per_second=1000000, duration_ticks=1200000, markers=[
        dict(kind='contact', limb='leg.right', start_tick=0, end_tick=400000),
        dict(kind='contact', limb='leg.left', start_tick=350000, end_tick=800000)])
    return document, motion


class TimelineTests(unittest.TestCase):
    def test_causal_entry_release_and_dense_contact(self):
        doc, motion = fixture(); original = deepcopy(doc)
        candidate, report = build(doc, 'walk', motion, [0, 1.2], 20)
        self.assertIsNotNone(candidate, report.get('failure'))
        self.assertEqual(doc, original)
        self.assertEqual(candidate['bones'], doc['bones'])
        self.assertLessEqual(report['root_speed_px_per_second'], 40)
        self.assertLessEqual(report['rotation_speed_degrees_per_second'], 180)
        for value in report['rows'][-1]['angles'].values(): self.assertEqual(value, 0)
        self.assertEqual(report['rows'][-1]['root_shift'], [0, 0])
        qa = analyze(candidate, 'walk', motion, schedule(motion, [r['time'] for r in report['rows']]), 20)
        self.assertTrue(qa['passed'])

    def test_overlapping_same_limb_is_rejected(self):
        doc, motion = fixture(); motion['markers'][1]['limb'] = 'leg.right'
        with self.assertRaisesRegex(ValueError, 'interval_overlap'):
            build(doc, 'walk', motion, [0, 1.2], 20)
