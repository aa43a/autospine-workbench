"""The bridge must detect coordinate, time and topology conversion regressions."""
import hashlib
import runpy
from pathlib import Path
from copy import deepcopy
import unittest

verify = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                           'tools/verify-fbx-bvh.py'))['verify']
RAW = b'''HIERARCHY
ROOT Hips
{
 OFFSET 0 100 0
 CHANNELS 6 Xposition Yposition Zposition Xrotation Yrotation Zrotation
 End Site { OFFSET 0 10 0 }
}
MOTION
Frames: 2
Frame Time: 0.5
0 0 0 0 0 0
0 0 10 0 0 0
'''


def evidence():
    return {'source_sha256': 'a'*64,
            'bridge': {'bvh_sha256': hashlib.sha256(RAW).hexdigest(),
                       'local_to_blender_world': [[.01, 0, 0, 0], [0, 0, -.01, 0],
                                                  [0, .01, 0, 0], [0, 0, 0, 1]]},
            'bones': [{'name': 'Hips', 'parent': None}],
            'samples': [{'seconds': 0, 'joints': {'Hips': [0, 0, 1]}},
                        {'seconds': .5, 'joints': {'Hips': [0, -.1, 1]}}]}


class BridgeTests(unittest.TestCase):
    def test_explicit_centimeter_axis_conversion(self):
        original = evidence()
        snapshot = deepcopy(original)
        self.assertTrue(verify(RAW, original)['passed'])
        self.assertEqual(original, snapshot)

    def test_double_rest_offset_is_rejected(self):
        changed = RAW.replace(b'0 0 10 0 0 0', b'0 100 10 0 0 0')
        proof = evidence()
        proof['bridge']['bvh_sha256'] = hashlib.sha256(changed).hexdigest()
        self.assertFalse(verify(changed, proof)['passed'])

    def test_timing_mismatch_is_rejected(self):
        proof = evidence()
        proof['samples'][1]['seconds'] = .6
        self.assertFalse(verify(RAW, proof)['passed'])

    def test_missing_frame_and_wrong_parent_are_rejected(self):
        proof = evidence()
        proof['samples'].pop()
        with self.assertRaisesRegex(ValueError, 'frame_count'):
            verify(RAW, proof)
        proof = evidence()
        proof['bones'][0]['parent'] = 'other'
        with self.assertRaisesRegex(ValueError, 'topology'):
            verify(RAW, proof)
