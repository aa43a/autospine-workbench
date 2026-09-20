from copy import deepcopy
import unittest

from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.motion2d.contact_candidate import estimate_plane, infer
from test_bvh_fk import bvh_map


def fixture(speed=0):
    limbs = ''.join(f'''JOINT Knee{side} {{ OFFSET {x} -1 0
      CHANNELS 3 Xrotation Yrotation Zrotation
      JOINT Ankle{side} {{ OFFSET 0 -1 0 CHANNELS 3 Xrotation Yrotation Zrotation
        End Site {{ OFFSET 0 0 1 }} }} }}''' for side, x in [('L', -1), ('R', 1)])
    rows = '\n'.join(' '.join(map(str, [i*speed, 2, 0]+[0]*15)) for i in range(20))
    bvh = parse_bvh(('HIERARCHY ROOT Hips { OFFSET 0 0 0 '
        'CHANNELS 6 Xposition Yposition Zposition Xrotation Yrotation Zrotation '
        +limbs+' }\nMOTION\nFrames: 20\nFrame Time: 0.0333333\n'+rows).encode())
    bones = [dict(role='humanoid.leg.lower.'+side, joint_name='Knee'+suffix,
        aim=dict(kind='joint', joint_name='Ankle'+suffix), rotation_policy='projected_setup_local_delta')
        for side, suffix in [('left', 'L'), ('right', 'R')]]
    bones.insert(0, dict(role='humanoid.root', joint_name='Hips',
        aim=dict(kind='joint', joint_name='KneeL'), rotation_policy='projected_setup_local_delta'))
    return bvh, bvh_map(reference=2, bones=bones)


class ContactCandidateTests(unittest.TestCase):
    def test_stationary_support_is_separate_half_open_hypothesis(self):
        bvh, mapping = fixture()
        original = deepcopy(mapping)
        report = infer(bvh, mapping)
        self.assertEqual(report['status'], 'candidate')
        self.assertEqual(len(report['markers']), 2)
        self.assertEqual(mapping, original)
        self.assertFalse(report['selected'])
        self.assertEqual(report['authority'], 'none')
        for marker in report['markers']:
            self.assertEqual(marker['start_tick'], 0)
            self.assertEqual(marker['end_tick'], report['duration_ticks'])

    def test_fast_low_ankles_are_not_contacts(self):
        bvh, mapping = fixture(speed=.1)
        self.assertEqual(infer(bvh, mapping)['markers'], [])

    def test_existing_configuration_is_not_replaced(self):
        bvh, mapping = fixture()
        mapping['contact'] = infer(bvh, mapping)['derived_contact']
        self.assertEqual(infer(bvh, mapping)['status'], 'existing_contact_configuration_preserved')

    def test_no_loop_boundary_assumption(self):
        bvh, mapping = fixture()
        mapping['clip']['loop'] = True
        self.assertEqual(infer(bvh, mapping)['status'], 'unavailable')

    def test_scale_and_signed_axis(self):
        points = [(0, i, 0) for i in range(21)]
        self.assertEqual(estimate_plane(points, '+Y', 2), 1)
        self.assertEqual(estimate_plane(points, '-Y', 2), -19)
        for points, axis, scale in [([], '+Y', 1), ([(0, float('nan'), 0)], '+Y', 1),
                                    ([(0, 0, 0)], '+W', 1), ([(0, 0, 0)], '+Y', 0)]:
            with self.assertRaises(ValueError):
                estimate_plane(points, axis, scale)


if __name__ == '__main__':
    unittest.main()
