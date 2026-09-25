from copy import deepcopy
import json
import unittest

from autospine_workbench.automation.motion_moving_ankles import apply, check
from autospine_workbench.automation.motion_target_worker import build_candidate
from autospine_workbench.motion_validation import motion_ir_sha256
from autospine_workbench.resolved_project import canonical_sha256
from tests.test_moving_ankle_candidate import fixture
from tests.test_motion_target_intake import inputs


def observation(motion, displacement=.01):
    return dict(profile='source-ankle-displacement-v1', source_bundle_sha256='b'*64,
        motion_sha256=motion_ir_sha256(motion), yaw_degrees=0, source_reference_length=1,
        times=[0, motion['duration_ticks']/motion['ticks_per_second']],
        points=[[[0, 0, 0], [0, 0, 0]], [[displacement, -.005, 0], [displacement, -.005, 0]]])


class MovingAnkleStageTests(unittest.TestCase):
    def prepared(self):
        doc, _ = fixture()
        motion = inputs()[1]
        doc['animations']['move']['bones']['root']['translate'][-1]['time'] = 2
        return doc, motion, observation(motion)

    def test_success_preserves_input_and_checks_final_interpolation(self):
        doc, motion, obs = self.prepared()
        before = deepcopy((doc, motion, obs))
        candidate, report = apply(doc, 'move', motion, obs, [0, 1, 2], 20, bundle_sha256='b'*64)
        self.assertTrue(report['applied'])
        result = check(candidate, 'move', report, [0, .5, 1, 1.5, 2], 20)
        self.assertTrue(result['passed'])
        self.assertEqual(result['samples'], 5)
        self.assertEqual(result['skeleton_sha256'], canonical_sha256(candidate))
        self.assertEqual((doc, motion, obs), before)
        # A later-stage bone change must not reuse the successful solve report.
        candidate['animations']['move']['bones']['root']['translate'][-1]['x'] += 10
        self.assertFalse(check(candidate, 'move', report, [0, 1, 2], 20)['passed'])

    def test_wrong_identity_camera_or_clip_rejected(self):
        doc, motion, obs = self.prepared()
        for key, value in [('motion_sha256', 'c'*64), ('source_bundle_sha256', 'c'*64),
                           ('yaw_degrees', 30), ('times', [0, 1])]:
            wrong = dict(obs, **{key: value})
            with self.assertRaisesRegex(ValueError, 'identity_or_time'):
                apply(doc, 'move', motion, wrong, [0, 2], 20, bundle_sha256='b'*64)
        with self.assertRaisesRegex(ValueError, 'identity_or_time'):
            apply(doc, 'move', motion, obs, [0, 2], 20, bundle_sha256='b'*64, clip_bounds=(0, 2000000))

    def test_infeasible_preserves_original_and_remains_failed(self):
        doc, motion, _ = self.prepared()
        original = deepcopy(doc)
        candidate, report = apply(doc, 'move', motion, observation(motion, 100),
                                  [0, 1, 2], 20, bundle_sha256='b'*64)
        self.assertFalse(report['applied'])
        self.assertEqual(candidate, original)
        self.assertFalse(check(candidate, 'move', report, [0, 1, 2], 20)['passed'])

    def test_worker_serializes_stage_and_rechecks_final_contact_and_geometry(self):
        args = inputs()
        result, evidence, geometry = build_candidate(*args, character_digest='a'*64,
            motion_digest='b'*64, moving_ankles=observation(args[1], 100))
        stage = json.loads(result['motion-moving-ankles.json'])
        self.assertFalse(stage['applied'])
        self.assertIn('motion_moving_ankle_infeasible', [r['reason_code'] for r in evidence['issues']])
        self.assertEqual(evidence['status'], 'needs_changes')
        contact = json.loads(result['motion-contact.json'])
        self.assertEqual(stage['final_check']['samples'], contact['final_timeline_check']['samples'])
        self.assertEqual(geometry, json.loads(result['deformation.json']))
        self.assertEqual(result['images/point.png'], args[0]['images/point.png'])
        self.assertFalse(json.loads(result['character-manifest.json'])['production_authorized'])

    def test_empty_contact_hypothesis_survives_final_recheck(self):
        from autospine_workbench.targets.character43.inferred_contacts import PROFILE
        args = inputs()
        result, _, _ = build_candidate(*args, character_digest='a'*64, motion_digest='b'*64,
            moving_ankles=observation(args[1], 100), inferred_contact_profile=PROFILE)
        contact = json.loads(result['motion-contact.json'])
        self.assertIsNone(contact['after']['passed'])
        self.assertEqual(contact['after']['status'], 'unavailable_no_labels')

    def test_worker_success_is_still_unaccepted_and_geometry_checked(self):
        args = inputs()
        for track in args[1]['tracks']:
            track['keys'][-1]['value'] = deepcopy(track['keys'][0]['value'])
        # No source limb displacement: final motion remains exactly observable.
        obs = observation(args[1], 0)
        obs['points'][-1] = deepcopy(obs['points'][0])
        result, evidence, geometry = build_candidate(*args, character_digest='a'*64,
            motion_digest='b'*64, moving_ankles=obs)
        stage = json.loads(result['motion-moving-ankles.json'])
        self.assertTrue(stage['applied'])
        self.assertTrue(stage['final_check']['passed'])
        self.assertTrue(geometry['passed'])
        self.assertEqual(evidence['runtime_status'], 'not_evaluated')
        self.assertFalse(stage['selected'])
