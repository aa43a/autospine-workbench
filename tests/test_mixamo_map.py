"""Explicit named mappings must not guess absent joints or accept wrong ancestry."""
import unittest
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.bvh_map_validation import BvhMapValidationError
from autospine_workbench.bvh_motion_compiler import compile_bvh_motion
from autospine_workbench.motion2d.mixamo_map import build_map


def source(prefix='', wrong_parent=False):
    children = {'Hips': ['Spine', 'LeftUpLeg', 'RightUpLeg'], 'Spine': ['Spine1'],
                'Spine1': ['Spine2'], 'Spine2': ['Neck', 'LeftArm', 'RightArm'],
                'Neck': ['Head'], 'LeftArm': ['LeftForeArm'], 'LeftForeArm': ['LeftHand'],
                'RightArm': ['RightForeArm'], 'RightForeArm': ['RightHand'],
                'LeftUpLeg': ['LeftLeg'], 'LeftLeg': ['LeftFoot'], 'LeftFoot': ['LeftToeBase'],
                'RightUpLeg': ['RightLeg'], 'RightLeg': ['RightFoot'], 'RightFoot': ['RightToeBase']}
    if wrong_parent:
        children['LeftArm'] = []
        children['RightArm'].append('LeftForeArm')
    count = 0
    def node(name, root=False):
        nonlocal count
        count += 6 if root else 3
        channels = '6 Xposition Yposition Zposition' if root else '3'
        text = f"{'ROOT' if root else 'JOINT'} {prefix+name}\n{{\nOFFSET 1 2 3\n"
        text += f'CHANNELS {channels} Xrotation Yrotation Zrotation\n'
        text += ''.join(node(child) for child in children.get(name, []))
        if not children.get(name):
            text += 'End Site { OFFSET 1 2 3 }\n'
        return text+'}\n'
    raw = 'HIERARCHY\n'+node('Hips', True)+'MOTION\nFrames: 2\nFrame Time: 0.5\n'
    return (raw + (' '.join(['0']*count)+'\n')*2).encode()


def mapped(raw, **kwargs):
    return build_map(parse_bvh(raw), clip_id='test.walk', reference_length=10,
                     screen_x='+Z', screen_y='+Y', depth='+X', **kwargs)


class MixamoMapTests(unittest.TestCase):
    def test_compiles_with_explicit_prefix_and_no_inferred_loop(self):
        raw = source('mixamorig:')
        result = compile_bvh_motion(raw, mapped(raw, prefix='mixamorig:')).document
        self.assertEqual(len(result['tracks']), 13)
        self.assertFalse(result['loop'])
        self.assertEqual(result['markers'], [])

    def test_missing_names_and_crossed_arm_topology_fail(self):
        with self.assertRaises(BvhMapValidationError):
            mapped(source('unknown:'))
        with self.assertRaisesRegex(BvhMapValidationError, 'descend|topology'):
            mapped(source(wrong_parent=True))

    def test_contact_requires_all_explicit_values(self):
        with self.assertRaisesRegex(ValueError, 'parameters_required'):
            mapped(source(), contact={'floor': 0})
        m = mapped(source(), contact=dict(floor=0, height=3, speed=10,
                                          minimum_frames=3, gap_frames=0))
        self.assertEqual(m['contact']['mode'], 'annotation_only')
        self.assertEqual(m['contact']['feet'][0]['foot_joint_name'], 'LeftToeBase')
