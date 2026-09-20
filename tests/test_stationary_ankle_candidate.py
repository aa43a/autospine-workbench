from copy import deepcopy
import unittest
from autospine_workbench.targets.character43.stationary_ankle_candidate import build
from autospine_workbench.targets.character43.affine_pose import matrices
from test_motion_contacts import fixture


class StationaryAnkleTests(unittest.TestCase):
    def inputs(self):
        doc, motion = fixture()
        for marker in motion['markers']:
            marker['end_tick'] = 1000000
        doc['bones'][0].update(rotation=20, scaleX=1.1, scaleY=.9)
        doc['animations']['walk']['bones']['foot_r'] = {'translate': [dict(time=0, x=0, y=0), dict(time=1, x=2, y=0)]}
        return doc, motion

    def test_affine_endpoint_correction_is_bounded_and_does_not_change_rig(self):
        doc, motion = self.inputs()
        original = deepcopy(doc)
        result, report = build(doc, 'walk', motion, [0, .5, 1], 100)
        self.assertIsNotNone(result)
        self.assertEqual(doc, original)
        self.assertEqual(result['bones'], doc['bones'])
        self.assertFalse(report['selected'])
        self.assertLess(report['after']['max_drift_px'], .001)
        for t in (0, .2, .7, 1):
            a, b = matrices(doc, 'walk', t), matrices(result, 'walk', t)
            self.assertEqual(a['foot_l'][:4], b['foot_l'][:4])
            self.assertEqual(a['foot_r'][:4], b['foot_r'][:4])

    def test_partial_support_not_silently_extended(self):
        doc, motion = fixture()
        with self.assertRaisesRegex(ValueError, 'full_bilateral'):
            build(doc, 'walk', motion, [0, 1], 100)

    def test_conflicting_feet_do_not_relax_endpoint_limits(self):
        doc, motion = self.inputs()
        doc['animations']['walk']['bones']['foot_r']['translate'][-1]['x'] = 20
        result, report = build(doc, 'walk', motion, [0, 1], 100)
        self.assertIsNone(result)
        self.assertEqual(report['status'], 'blocked')

    def test_unit_scale_does_not_change_admissibility(self):
        for scale in (.1, 10):
            doc, motion = self.inputs()
            for bone in doc['bones']:
                bone['x'] *= scale
                bone['y'] *= scale
            for channels in doc['animations']['walk']['bones'].values():
                for key in channels.get('translate', []):
                    key['x'] *= scale
                    key['y'] *= scale
            candidate, report = build(doc, 'walk', motion, [0, .5, 1], 100*scale)
            self.assertIsNotNone(candidate)
            self.assertLess(report['max_endpoint_shift_px']/scale, 2)


if __name__ == '__main__':
    unittest.main()
