"""Bounded blend candidates preserve pose evidence and limb-length constraints."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.asset.joints.optimizer import BONES, optimize_joints, validate_joint_optimization
from autospine_workbench.benchmark.pose_contact_match import build_pose_contact_match
from autospine_workbench.pose_observations import PoseJointObservation
from tests.test_benchmark_pose_contact_match import fixture as matching_fixture


def fixture():
    candidate, probe, screen, pose = matching_fixture()
    points = {}
    for side, x in (('left', 15), ('right', 75)):
        for joint, y in (('shoulder', 15), ('elbow', 25), ('wrist', 35), ('hip', 50), ('knee', 65), ('ankle', 80)):
            points[f'{joint}.{side}'] = PoseJointObservation(x, y, .9, 'visible')
    pose = replace(pose, joints=points)
    match = build_pose_contact_match(candidate, probe, screen, pose)
    return candidate, pose, match


class JointOptimizerTests(unittest.TestCase):
    def test_pure_deterministic_and_schema(self):
        args = fixture()
        before = deepcopy(args)
        doc = optimize_joints(*args)
        self.assertEqual(doc['status'], 'candidate_requires_review')
        self.assertEqual(args, before)
        self.assertEqual(doc, validate_joint_optimization(*args, doc))
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('jsonschema unavailable')
        schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas/joint-optimization-v1.schema.json').read_text('utf-8'))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(doc)

    def test_large_contact_pull_backtracks_and_respects_constraints(self):
        candidate, pose, match = fixture()
        # Upstream matching closure is a caller boundary. Deliberately stressed
        # valid-coordinate match tests solver displacement/backtracking alone.
        match['records'][0]['position'] = [15, 90]
        doc = optimize_joints(candidate, pose, match)
        self.assertLess(doc['accepted_step'], 1)
        by_id = {row['joint_id']: row for row in doc['joints']}
        for row in doc['joints']:
            self.assertLessEqual(row['displacement_px'], doc['constraints']['max_displacement_px'])
        import math
        for a, b in BONES:
            old = math.dist((pose.joints[a].x, pose.joints[a].y), (pose.joints[b].x, pose.joints[b].y))
            new = math.dist(by_id[a]['position'], by_id[b]['position'])
            self.assertGreaterEqual(new/old, .75)
            self.assertLessEqual(new/old, 1.25)

    def test_missing_degenerate_and_weak_pose_block_without_points(self):
        for kind in ('missing', 'degenerate', 'weak'):
            candidate, pose, match = fixture()
            points = dict(pose.joints)
            if kind == 'missing':
                del points['elbow.left']
            elif kind == 'degenerate':
                points['elbow.left'] = points['wrist.left']
            else:
                points['elbow.left'] = replace(points['elbow.left'], detector_score=.49)
            doc = optimize_joints(candidate, replace(pose, joints=points), match)
            self.assertEqual(doc['status'], 'blocked')
            self.assertEqual(doc['joints'], [])

    def test_pose_only_and_missing_pose(self):
        candidate, pose, match = fixture()
        for row in match['records']:
            row.update(status='blocked', position=None, contact_id=None)
        doc = optimize_joints(candidate, pose, match)
        self.assertIn('contact_unavailable', doc['reason_codes'])
        self.assertTrue(all(row['source'] == 'pose' for row in doc['joints']))
        match['pose_sha256'] = None
        doc = optimize_joints(candidate, None, match)
        self.assertEqual(doc['reason_codes'], ['pose_observations_required'])

    def test_binding_nonfinite_and_tamper(self):
        candidate, pose, match = fixture()
        bad = deepcopy(match)
        bad['candidate_sha256'] = '0'*64
        with self.assertRaises(ValueError):
            optimize_joints(candidate, pose, bad)
        bad = deepcopy(match)
        bad['records'][0]['position'] = [10**1000, 0]
        with self.assertRaisesRegex(ValueError, 'input_invalid'):
            optimize_joints(candidate, pose, bad)
        doc = optimize_joints(candidate, pose, match)
        doc['accepted_step'] = -1
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            validate_joint_optimization(candidate, pose, match, doc)


if __name__ == '__main__':
    unittest.main()
