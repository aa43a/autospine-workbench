from copy import deepcopy
import math
import unittest

from autospine_workbench.targets.character43.source_pose_fit import fit
from autospine_workbench.targets.character43.affine_pose import matrices


def fixture():
    return dict(bones=[dict(name='root', x=0, y=0, rotation=20),
        dict(name='upperarm_r', parent='root', x=2, y=3, rotation=-70),
        dict(name='forearm_r', parent='upperarm_r', x=10, y=0, rotation=15)],
        animations={'motion': {'bones': {'root': {
            'scale': [dict(time=0, x=.5, y=1.5), dict(time=1, x=.7, y=1.2)],
            'translate': [dict(time=0, x=3, y=4)]}}}})


class SourcePoseFitTests(unittest.TestCase):
    def test_fixed_yaw_resolves_camera_axis_without_inventing_rest_pose(self):
        vectors={'humanoid.arm.upper.right':[(0,0,1)]*2}
        result,report=fit(fixture(),'motion',vectors,[0,1],yaw=15,project_lengths=True)
        for time in (0,1):
            m=matrices(result,'motion',time)['upperarm_r']
            self.assertAlmostEqual(m[0],-math.sin(math.radians(15)))
            self.assertAlmostEqual(m[2],0)
        self.assertEqual(report['records'][0]['unreliable_frames'],[])

    def test_initial_raised_pose_and_parent_scaling(self):
        doc = fixture(); before = deepcopy(doc)
        vectors = {'humanoid.arm.upper.right': [(0, -1, 0), (1, -1, 0)],
                   'humanoid.arm.lower.right': [(1, 0, 0), (0, -1, 0)]}
        result, report = fit(doc, 'motion', vectors, [0, 1])
        self.assertEqual(doc, before)
        for time, expected in [(0, (90, 0)), (1, (45, 90))]:
            pose = matrices(result, 'motion', time)
            for bone, angle in zip(('upperarm_r', 'forearm_r'), expected):
                self.assertAlmostEqual(math.degrees(math.atan2(pose[bone][2], pose[bone][0])), angle)
        self.assertEqual(result['animations']['motion']['bones']['root'], doc['animations']['motion']['bones']['root'])
        self.assertFalse(report['selected'])

    def test_branch_crossing_is_short_but_camera_degeneracy_remains_flagged(self):
        vectors = {'humanoid.arm.upper.right': [(-1, -.01, 0), (-1, .01, 0)]}
        result, _ = fit(fixture(), 'motion', vectors, [0, 1])
        keys = result['animations']['motion']['bones']['upperarm_r']['rotate']
        self.assertLess(abs(keys[1]['value']-keys[0]['value']), 30)
        _, report = fit(fixture(), 'motion', {'humanoid.arm.upper.right': [(0.01, 0, 1)]*2}, [0, 1])
        self.assertEqual(len(report['records'][0]['unreliable_frames']), 2)

    def test_does_not_reuse_deforms_or_invent_degenerate_direction(self):
        doc = fixture(); doc['animations']['motion']['attachments'] = {'default': {'old': {}}}
        with self.assertRaisesRegex(ValueError, 'uncorrected_mesh'):
            fit(doc, 'motion', {}, [0, 1])
        with self.assertRaisesRegex(ValueError, 'unobservable'):
            fit(fixture(), 'motion', {'humanoid.arm.upper.right': [(0, 0, 1)]*2}, [0, 1])

    def test_camera_facing_limb_shortens_without_clamping_or_parent_scale_leak(self):
        doc = fixture()
        vectors = {'humanoid.arm.upper.right': [(0, -.8, .6)]*2,
                   'humanoid.arm.lower.right': [(.04, 0, math.sqrt(1-.04**2))]*2}
        result, report = fit(doc, 'motion', vectors, [0, 1], project_lengths=True)
        for time in (0, 1):
            pose = matrices(result, 'motion', time)
            for name, length in [('upperarm_r', .8), ('forearm_r', .04)]:
                a, b, c, d, _, _ = pose[name]
                self.assertAlmostEqual(math.hypot(a, c), length)
                self.assertAlmostEqual((a*d-b*c)/length, 1.)
        self.assertEqual(len(report['records'][1]['unreliable_frames']), 2)
        self.assertLess(report['records'][1]['maximum_axis_length_error'], 1e-10)
        with self.assertRaisesRegex(ValueError, 'existing_scale'):
            fit(result, 'motion', vectors, [0, 1], project_lengths=True)


if __name__ == '__main__':
    unittest.main()
