"""NPZ foot observations share camera rules without changing source labels."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from autospine_workbench.targets.character43.source_foot_orientation import extract
from tests.fixtures.kimodo_npz_archive import build_npz, motion_member_bytes
from tests.kimodo_npz_helpers import source_document, map_document


class KimodoFootTests(unittest.TestCase):
    def observe(self, *, yaw=0, basis=None, **kwargs):
        raw = build_npz(motion_member_bytes(**kwargs))
        source, mapping = source_document(raw), map_document()
        if basis: mapping['basis'].update(basis)
        original = deepcopy((source, mapping))
        with TemporaryDirectory() as directory:
            path = Path(directory)
            (path/'map.json').write_text(json.dumps(mapping))
            bundle = SimpleNamespace(path=path, source_kind='kimodo_npz', raw_npz=raw,
                                     kimodo_source=source)
            result = extract(bundle, yaw=yaw)
        self.assertEqual((source, mapping), original)
        return result

    def test_parent_rotation_and_relative_setup_are_preserved(self):
        report = self.observe(frame_rotations=({'LeftFoot':20},
            {'Hips':10,'LeftFoot':40}, {'LeftFoot':50}))
        self.assertEqual(report['profile'], 'declared-kimodo-relative-foot-frame-v1')
        for actual, expected in zip(report['tracks']['foot_l'], [0,30,30]):
            self.assertAlmostEqual(actual, expected, places=4)
        self.assertAlmostEqual(report['tracks']['foot_r'][1], 10, places=4)
        self.assertEqual(report['times'], [0, .033333, .066667])
        self.assertEqual(report['authority'], 'none')

    def test_unwrap_is_continuous_and_camera_yaw_is_applied(self):
        frames = ({}, {'LeftFoot':179}, {'LeftFoot':185})
        report = self.observe(frame_rotations=frames)
        self.assertAlmostEqual(report['tracks']['foot_l'][2], 185, places=4)
        rotated = self.observe(frame_rotations=({}, {'LeftFoot':30}, {'LeftFoot':40}), yaw=45)
        self.assertEqual(rotated['yaw_degrees'], 45)
        self.assertNotAlmostEqual(rotated['tracks']['foot_l'][1],30,places=2)

    def test_inconsistent_global_evidence_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'hierarchy differs'):
            self.observe(global_overrides={(1,'LeftFoot'):((1,0,0),(0,1,0),(0,0,1))})

    def test_camera_plane_collapse_is_rejected(self):
        half_turn = ((1,0,0),(0,-1,0),(0,0,-1))
        with self.assertRaisesRegex(ValueError, 'plane_unobservable'):
            self.observe(frame_rotations=({}, {}, {}), local_overrides={(1,'LeftFoot'):half_turn})


if __name__ == '__main__': unittest.main()
