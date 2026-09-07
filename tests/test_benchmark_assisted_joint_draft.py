"""Synthetic assisted suggestions remain separate from independent references."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.benchmark.assisted_joint_draft import build_assisted_joint_draft, validate_assisted_joint_draft
from autospine_workbench.benchmark.joint_baseline import build_joint_baseline
from autospine_workbench.benchmark.joint_draft import validate_joint_draft
from autospine_workbench.asset.joints.optimizer import JOINTS as LIMBS
from autospine_workbench.pose_observations import PoseObservationSet, PoseJointObservation
from autospine_workbench.resolved_project import canonical_sha256
from tests.test_benchmark_joint_baseline import inputs


def fixture():
    candidate, audit = inputs()
    candidate.update(character_id='synthetic-test', composite_sha256='c'*64)
    baseline = build_joint_baseline(candidate, audit)
    joints = {joint: PoseJointObservation(20+i, 30+i, .8, 'visible') for i, joint in enumerate(LIMBS)}
    document = {'project_id': candidate['character_id'], 'source': {'image_sha256': 'c'*64, 'canvas_size': candidate['canvas']},
                'joints': {joint: {'xy': [row.x, row.y], 'detector_score': row.detector_score, 'visibility': row.visibility}
                           for joint, row in joints.items()}}
    pose = PoseObservationSet(candidate['character_id'], 'c'*64, tuple(candidate['canvas']), 'synthetic', '1', 'test',
                              'd'*64, 'test', 1, 0, 'single', joints, canonical_sha256(document), document=document)
    return candidate, baseline, pose


class AssistedJointDraftTests(unittest.TestCase):
    def test_seventeen_suggestions_twelve_from_pose_five_from_baseline(self):
        args = fixture()
        before = deepcopy(args)
        doc = build_assisted_joint_draft(*args)
        self.assertEqual(args, before)
        self.assertFalse(doc['independent_annotation'])
        self.assertEqual(doc['reviewed_joint_ids'], [])
        self.assertEqual(len(doc['draft']['records']), 17)
        for index, row in enumerate(doc['draft']['records']):
            expected = [args[2].joints[row['joint_id']].x, args[2].joints[row['joint_id']].y] if row['joint_id'] in LIMBS else args[1]['records'][index]['position']
            self.assertEqual(row['position'], expected)
            self.assertEqual(row['status'], 'observed')
        self.assertEqual(doc, validate_assisted_joint_draft(*args, doc))

    def test_drag_status_notes_and_reviewed_ids_are_editable(self):
        args = fixture()
        doc = build_assisted_joint_draft(*args)
        doc['draft']['records'][0].update(position=[7, 9], notes='Synthetic adjusted point')
        doc['draft']['records'][1].update(position=None, status='unobservable', notes='Synthetic occlusion')
        doc['reviewed_joint_ids'] = ['root', 'pelvis']
        checked = validate_assisted_joint_draft(*args, doc)
        self.assertEqual(checked, doc)
        checked['reviewed_joint_ids'].append('head')
        self.assertEqual(doc['reviewed_joint_ids'], ['root', 'pelvis'])

    def test_source_authority_independence_and_duplicate_review_rejected(self):
        for key, value in (('independent_annotation', True), ('independent_annotation', 0),
                           ('annotation_mode', 'independent'), ('authority', 'human'),
                           ('candidate_sha256', '0'*64), ('source_pose_sha256', '0'*64),
                           ('source_baseline_sha256', '0'*64), ('reviewed_joint_ids', ['root', 'root']),
                           ('reviewed_joint_ids', ['invented']), ('extra', True)):
            args = fixture()
            doc = build_assisted_joint_draft(*args)
            doc[key] = value
            with self.assertRaises(ValueError):
                validate_assisted_joint_draft(*args, doc)

    def test_invalid_sources_coordinates_and_legacy_draft_rejects_envelope(self):
        candidate, baseline, pose = fixture()
        with self.assertRaises(ValueError):
            build_assisted_joint_draft(candidate, baseline, replace(pose, image_sha256='0'*64))
        baseline['candidate_sha256'] = '0'*64
        with self.assertRaises(ValueError):
            build_assisted_joint_draft(candidate, baseline, pose)
        args = fixture()
        doc = build_assisted_joint_draft(*args)
        with self.assertRaises(ValueError):
            validate_joint_draft(args[0], doc)
        doc['draft']['records'][0]['position'] = [10**1000, 3]
        with self.assertRaises(ValueError):
            validate_assisted_joint_draft(*args, doc)

    def test_schema(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('jsonschema unavailable')
        schema = json.loads((Path(__file__).resolve().parents[1] / 'schemas/benchmark-assisted-joint-draft-v1.schema.json').read_text('utf-8'))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(build_assisted_joint_draft(*fixture()))


if __name__ == '__main__':
    unittest.main()
