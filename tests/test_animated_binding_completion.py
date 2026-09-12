"""Candidate upgrade, CAS and downstream profile continuity."""
import unittest
from tests import test_animated_joint_review as fixtures
from tests.test_layer_binding import fixture
from autospine_workbench.automation import animated_inputs as inputs
from autospine_workbench.automation.animated_binding_completion import complete_bindings, rebuild_bindings
from autospine_workbench.automation.animated_input_index import inspect_registration
from autospine_workbench.asset.joints.garment_completion import build_completion, PROFILE


class AnimatedCompletionTests(unittest.TestCase):
    setUp = fixtures.AnimatedJointReviewTests.setUp
    review = fixtures.AnimatedJointReviewTests.review
    save = fixtures.AnimatedJointReviewTests.save

    def test_upgrade_is_idempotent_preserves_decisions_and_replays(self):
        before = inspect_registration(self.store, 'fixture')
        key = before['source_addresses']['input_identity_sha256']
        result = complete_bindings(self.store, 'fixture', 'a' * 64, key)
        self.assertTrue(result['changed'])
        after = inspect_registration(self.store, 'fixture')
        self.assertEqual(after['draft']['records'], before['draft']['records'])
        with inputs.load_inputs(self.store, 'fixture') as source:
            self.assertEqual(source.bindings['profile'], PROFILE)
        current = after['source_addresses']['input_identity_sha256']
        count = len(inputs._registrations(self.store, 'fixture'))
        self.assertFalse(complete_bindings(self.store, 'fixture', 'a' * 64, current)['changed'])
        self.assertEqual(len(inputs._registrations(self.store, 'fixture')), count)
        for resolved, identity in [('c' * 64, current), ('a' * 64, key)]:
            with self.assertRaisesRegex(inputs.AnimatedSourceError, 'animated_review_conflict'):
                complete_bindings(self.store, 'fixture', resolved, identity)

    def test_joint_edit_keeps_completion_profile_and_resets_geometry_decisions(self):
        key = self.review()['input_identity_sha256']
        complete_bindings(self.store, 'fixture', 'a' * 64, key)
        review = self.review()
        next(row for row in review['records'] if row['joint_id'] == 'elbow.left')['position'][0] += 1
        self.assertTrue(self.save(review)['binding_review_required'])
        with inputs.load_inputs(self.store, 'fixture') as source:
            self.assertEqual(source.bindings['profile'], PROFILE)
            self.assertTrue(all(row['action'] != 'bind' for row in source.draft['records']))

    def test_rebuild_retains_head_detail_options(self):
        args = fixture('mouth')
        original = build_completion(*args)
        self.assertEqual(rebuild_bindings(*args, original), original)
        self.assertEqual(original['bindings'][1]['options'][0]['bone_ids'], ['head'])
