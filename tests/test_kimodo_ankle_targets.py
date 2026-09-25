"""NPZ ankle observations must retain source motion, basis and identity."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from tests.fixtures.kimodo_npz_archive import build_npz, motion_member_bytes
from tests.kimodo_npz_helpers import source_document, map_document
from autospine_workbench.kimodo_npz_reader import decode_kimodo_npz
from autospine_workbench.kimodo_npz_consistency import validate_kimodo_consistency
from autospine_workbench.kimodo_soma77 import SOMA77_INDEX_BY_NAME
from autospine_workbench.targets.character43.source_ankle_targets import extract, targets


class KimodoAnkleTargetsTests(unittest.TestCase):
    def bundle(self, **kwargs):
        raw = build_npz(motion_member_bytes(**kwargs))
        return SimpleNamespace(source_kind='kimodo_npz', raw_npz=raw,
            kimodo_source=source_document(raw), kimodo_map=map_document(),
            bundle_sha256='a'*64, clip_sha256='b'*64)

    def test_actual_ankles_follow_declared_basis_and_yaw(self):
        bundle = self.bundle(frame_rotations=({}, {'LeftShin': 30}, {'RightLeg': -20}))
        pose = validate_kimodo_consistency(
            decode_kimodo_npz(bundle.raw_npz, bundle.kimodo_source),
            bundle.kimodo_source).positions
        for basis in (('+X', '-Y', '+Z'), ('-Z', '-Y', '+X')):
            bundle.kimodo_map['basis'].update(zip(('screen_x', 'screen_y', 'depth'), basis))
            before = deepcopy(bundle)
            for yaw in (0, 90, -90):
                observation = extract(bundle, yaw)
                self.assertEqual(observation['times'], [0, .033333, .066667])
                self.assertEqual(observation['source_bundle_sha256'], 'a'*64)
                self.assertEqual(observation['motion_sha256'], 'b'*64)
                for frame, samples in zip(pose, observation['points']):
                    for name, actual in zip(('LeftFoot', 'RightFoot'), samples):
                        p = frame[SOMA77_INDEX_BY_NAME[name]]
                        x, y, z = [(1 if axis[0] == '+' else -1)*p['XYZ'.index(axis[1])]
                                   for axis in basis]
                        expected = (x, y, z) if yaw == 0 else ((-z, y, x) if yaw == 90 else (z, y, -x))
                        for a, b in zip(actual, expected):
                            self.assertAlmostEqual(a, b, places=10)
            self.assertEqual(bundle, before)

    def test_root_displacement_survives_contact_annotations(self):
        bundle = self.bundle(frame_rotations=({}, {}, {}),
                             contact_rows=((True,)*4,)*3)
        rows = targets(extract(bundle), [[10, 20], [30, 40]], 100)
        for frame, delta in zip(rows, (0, 10, 20)):
            for actual, initial in zip(frame['targets'], ([10, 20], [30, 40])):
                self.assertAlmostEqual(actual[0], initial[0]+delta, places=5)
                self.assertAlmostEqual(actual[1], initial[1], places=5)

    def test_inconsistent_pose_and_changed_bytes_rejected(self):
        bundle = self.bundle(posed_overrides={(1, 'LeftFoot'): (9, 9, 9)})
        with self.assertRaises(ValueError):
            extract(bundle)
        bundle = self.bundle()
        bundle.raw_npz += b'changed'
        with self.assertRaises(ValueError):
            extract(bundle)
