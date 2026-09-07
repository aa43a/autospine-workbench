"""Synthetic reviewed points retain user central anchors and exact local FK."""
from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.asset.joints.reviewed_skeleton import build_reviewed_skeleton, validate_reviewed_skeleton
from autospine_workbench.benchmark.assisted_joint_draft import build_assisted_joint_draft
from autospine_workbench.benchmark.joint_draft import JOINTS
from tests.test_benchmark_assisted_joint_draft import fixture as assisted_fixture


def fixture():
    candidate, baseline, pose = assisted_fixture()
    assisted = build_assisted_joint_draft(candidate, baseline, pose)
    points = {'root': [100, 380], 'pelvis': [95, 230], 'chest': [105, 130], 'neck': [103, 100], 'head': [101, 60]}
    for side, sign in (('left', 1), ('right', -1)):
        for name, dx, y in (('shoulder', 40, 135), ('elbow', 55, 180), ('wrist', 70, 220),
                            ('hip', 20, 230), ('knee', 25, 290), ('ankle', 30, 350)):
            points[f'{name}.{side}'] = [100+sign*dx, y]
    for row in assisted['draft']['records']:
        row.update(position=points[row['joint_id']], notes='Synthetic reviewed test point')
    assisted['reviewed_joint_ids'] = list(JOINTS)
    return candidate, assisted


class ReviewedSkeletonTests(unittest.TestCase):
    def test_twenty_bones_preserve_central_points_and_provenance(self):
        args = fixture()
        before = deepcopy(args)
        doc = build_reviewed_skeleton(*args)
        self.assertEqual(args, before)
        self.assertEqual(doc, validate_reviewed_skeleton(*args, doc))
        self.assertEqual(doc['status'], 'candidate_requires_review')
        self.assertEqual(len(doc['bones']), 20)
        bones = {b['id']: b for b in doc['bones']}
        self.assertEqual(bones['root']['head_xy'], [100, 380])
        self.assertEqual(bones['pelvis']['head_xy'], [95, 230])
        self.assertEqual(bones['chest']['head_xy'], [105, 130])
        self.assertEqual(bones['neck']['head_xy'], [103, 100])
        self.assertEqual(bones['head']['head_xy'], [101, 60])
        self.assertEqual(bones['chest']['provenance']['kind'], 'assisted_review')
        self.assertEqual(bones['head']['provenance']['kind'], 'fallback')
        self.assertFalse(doc['production_authorized'])

    def test_setup_local_fk_reconstructs_heads_and_tails(self):
        doc = build_reviewed_skeleton(*fixture())
        frames = {}
        for bone in doc['bones']:
            head, angle = frames[bone['parent_id']] if bone['parent_id'] else ([0, 0], 0)
            local = bone['setup_local']
            r = math.radians(angle)
            actual = [head[0]+local['x']*math.cos(r)-local['y']*math.sin(r),
                      head[1]+local['x']*math.sin(r)+local['y']*math.cos(r)]
            angle += local['rotation_degrees']
            tail = [actual[0]+bone['length']*math.cos(math.radians(angle)),
                    actual[1]+bone['length']*math.sin(math.radians(angle))]
            for a, b in zip(actual+tail, bone['head_xy']+bone['tail_xy']):
                self.assertAlmostEqual(a, b, places=9)
            frames[bone['id']] = (actual, angle)

    def test_unreviewed_and_unobservable_block_without_bones(self):
        candidate, assisted = fixture()
        assisted['reviewed_joint_ids'].pop()
        self.assertEqual(build_reviewed_skeleton(candidate, assisted)['reason_codes'], ['all_joint_reviews_required'])
        candidate, assisted = fixture()
        assisted['draft']['records'][0].update(status='unobservable', position=None, notes='Synthetic occlusion')
        doc = build_reviewed_skeleton(candidate, assisted)
        self.assertEqual(doc['reason_codes'], ['all_joint_positions_required'])
        self.assertEqual(doc['bones'], [])

    def test_vertical_degenerate_and_extension_outside_fail_closed(self):
        for joint, point in (('neck', [103, 150]), ('head', [101, 0]), ('elbow.left', [170, 220])):
            candidate, assisted = fixture()
            next(r for r in assisted['draft']['records'] if r['joint_id'] == joint)['position'] = point
            doc = build_reviewed_skeleton(candidate, assisted)
            self.assertEqual(doc['status'], 'blocked')
            self.assertEqual(doc['bones'], [])

    def test_tamper_and_schema(self):
        args = fixture()
        doc = build_reviewed_skeleton(*args)
        changed = deepcopy(doc)
        changed['production_authorized'] = True
        with self.assertRaises(ValueError):
            validate_reviewed_skeleton(*args, changed)
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('jsonschema unavailable')
        schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas/assisted-skeleton-candidate-v1.schema.json').read_text('utf-8'))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(doc)


if __name__ == '__main__':
    unittest.main()
