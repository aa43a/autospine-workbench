"""Synthetic matching fixtures test diagnostics, never supply real pose evidence."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autospine_workbench.benchmark.contact_probe import build_contact_probe
from autospine_workbench.benchmark.contact_screen import build_contact_screen
from autospine_workbench.benchmark.pose_contact_match import build_pose_contact_match, validate_pose_contact_match
from autospine_workbench.pose_observations import PoseObservationSet, PoseJointObservation
from autospine_workbench.resolved_project import canonical_sha256
from tests.test_benchmark_contact_probe import inputs


def fixture():
    candidate, images = inputs(names=('topwear', 'handwear-l', 'handwear-r'),
                               boxes=((10, 10, 80, 20), (10, 10, 20, 40), (70, 10, 80, 40)))
    candidate.update(character_id='fixture', composite_sha256='c'*64)
    probe = build_contact_probe(candidate, images)
    screen = build_contact_screen(candidate, probe)
    points = [p['contacts'][0]['representative_xy'] for p in probe['relations'][0]['pairs']]
    adapter = {'mirror_state': 'not_mirrored', 'view_orientation': 'front'}
    document = {'format_version': 2, 'adapter': adapter}
    pose = PoseObservationSet('fixture', 'c'*64, (100, 100), 'test', '1', 'test', 'd'*64, 'test',
                             1, 0, 'single', {f'shoulder.{side}': PoseJointObservation(*point, .9, 'visible')
                             for side, point in zip(('left', 'right'), points)}, canonical_sha256(document),
                             adapter=adapter, document=document)
    return candidate, probe, screen, pose


class PoseContactMatchTests(unittest.TestCase):
    def test_schema_and_deep_rejected_contacts_excluded(self):
        candidate, images = inputs(names=('bottomwear', 'legwear-l', 'legwear-r'),
                                   boxes=((10, 10, 80, 20), (10, 10, 20, 40), (70, 10, 80, 40)))
        candidate.update(character_id='fixture', composite_sha256='c'*64)
        probe = build_contact_probe(candidate, images)
        screen = build_contact_screen(candidate, probe)
        self.assertEqual(screen['summary']['rejected_deep_overlap'], 2)
        pose = fixture()[3]
        pose = replace(pose, joints={key.replace('shoulder', 'hip'): value for key, value in pose.joints.items()})
        doc = build_pose_contact_match(candidate, probe, screen, pose)
        self.assertIn('distinct_contact_sites_required', doc['records'][2]['reason_codes'])
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest('jsonschema unavailable')
        schema = json.loads((Path(__file__).resolve().parents[1] /
                             'schemas/benchmark-pose-contact-match-v1.schema.json').read_text('utf-8'))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(doc)

    def test_missing_pose_is_blocked_without_fallback(self):
        candidate, probe, screen, _ = fixture()
        doc = build_pose_contact_match(candidate, probe, screen, None)
        self.assertEqual(doc['summary']['blocked'], 6)
        self.assertIsNone(doc['pose_sha256'])
        self.assertTrue(all(r['position'] is None and 'pose_observations_required' in r['reason_codes'] for r in doc['records']))

    def test_unique_bilateral_match_pure_and_exact(self):
        args = fixture()
        before = deepcopy(args)
        doc = build_pose_contact_match(*args)
        self.assertEqual(args, before)
        self.assertEqual(doc, validate_pose_contact_match(*args, doc))
        self.assertEqual(doc['summary']['candidate_requires_review'], 2)
        self.assertNotEqual(doc['records'][0]['contact_id'], doc['records'][1]['contact_id'])
        self.assertEqual(doc['records'][0]['distance_px'], 0)
        self.assertEqual(doc['authority'], 'none')

    def test_unknown_mirror_visibility_and_single_anchor_block(self):
        for change, reason in (({'mirror_state': 'unknown'}, 'pose_mirror_state_required'),
                               ({'view_orientation': 'back'}, 'pose_view_unsupported')):
            candidate, probe, screen, pose = fixture()
            adapter = dict(pose.adapter, **change)
            document = dict(pose.document, adapter=adapter)
            pose = replace(pose, adapter=adapter, document=document, document_sha256=canonical_sha256(document))
            self.assertIn(reason, build_pose_contact_match(candidate, probe, screen, pose)['records'][0]['reason_codes'])
        candidate, probe, screen, pose = fixture()
        pose = replace(pose, joints={'shoulder.left': pose.joints['shoulder.left']})
        self.assertIn('bilateral_pose_anchor_required', build_pose_contact_match(candidate, probe, screen, pose)['records'][0]['reason_codes'])
        pose = replace(pose, joints={key: PoseJointObservation(40, 15, .9, 'occluded') for key in ('shoulder.left', 'shoulder.right')})
        self.assertIn('pose_anchor_not_visible', build_pose_contact_match(candidate, probe, screen, pose)['records'][0]['reason_codes'])

    def test_ambiguity_and_distance_block(self):
        candidate, probe, screen, pose = fixture()
        points = {key: PoseJointObservation(40, 15, .9, 'visible') for key in ('shoulder.left', 'shoulder.right')}
        doc = build_pose_contact_match(candidate, probe, screen, replace(pose, joints=points))
        self.assertIn('contact_assignment_ambiguous', doc['records'][0]['reason_codes'])
        points = {key: replace(value, y=90) for key, value in pose.joints.items()}
        doc = build_pose_contact_match(candidate, probe, screen, replace(pose, joints=points))
        self.assertIn('contact_assignment_too_far', doc['records'][0]['reason_codes'])

    def test_source_numbers_and_document_tamper(self):
        candidate, probe, screen, pose = fixture()
        with self.assertRaises(ValueError):
            build_pose_contact_match(candidate, probe, screen, replace(pose, image_sha256='0'*64))
        points = dict(pose.joints, **{'shoulder.left': PoseJointObservation(10**1000, 0, .9, 'visible')})
        with self.assertRaisesRegex(ValueError, 'input_invalid'):
            build_pose_contact_match(candidate, probe, screen, replace(pose, joints=points))
        doc = build_pose_contact_match(candidate, probe, screen, pose)
        doc['records'][0]['position'] = [0, 0]
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            validate_pose_contact_match(candidate, probe, screen, pose, doc)


if __name__ == '__main__':
    unittest.main()
