"""Saved authoring corrections synchronize explicitly without importing bbox points."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from tests import test_animated_joint_review as joint_fixtures
from autospine_workbench.automation import animated_inputs as inputs
from autospine_workbench.automation.animated_input_index import inspect_registration, assert_registered_current
from autospine_workbench.automation.animated_joint_review import get_joint_review, save_joint_review
from autospine_workbench.automation.animated_rebase import preview_rebase, rebase_inputs
from autospine_workbench.resolved_project import canonical_sha256


class AnimatedRebaseTests(unittest.TestCase):
    def setUp(self):
        self.fixture = joint_fixtures.AnimatedJointReviewTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store
        self.original = inspect_registration(self.store, 'fixture')
        self.overrides = dict(revision=0, joint_overrides={}, layer_overrides={},
                              joint_decisions={}, split_decisions={}, notes='')
        self.checkpoint = {'resolved_project_sha256': 'a' * 64, 'input_identity_sha256': 'b' * 64}
        patcher = patch.object(inputs, '_checkpoint', lambda *_: (
            {'overrides': deepcopy(self.overrides)}, deepcopy(self.checkpoint)))
        patcher.start()
        self.addCleanup(patcher.stop)
        rebase_checkpoint = patch('autospine_workbench.automation.animated_rebase._checkpoint',
                                  lambda *_: ({'overrides': deepcopy(self.overrides)}, deepcopy(self.checkpoint)))
        rebase_checkpoint.start()
        self.addCleanup(rebase_checkpoint.stop)
        audit = patch('autospine_workbench.automation.animated_rebase._match_audit', lambda *_: None)
        audit.start()
        self.addCleanup(audit.stop)
        self.store._record = lambda _: None
        self.store._build_project = lambda *_, **__: {'layers': [{'id': 'layer-000', 'visible': True}]}

    def author(self, **changes):
        self.overrides.update(deepcopy(changes))
        self.overrides['revision'] += 1
        sha = canonical_sha256(self.overrides)
        self.checkpoint = {'resolved_project_sha256': sha, 'input_identity_sha256': sha}

    def synchronize(self, plan=None):
        plan = plan or preview_rebase(self.store, 'fixture')
        return rebase_inputs(self.store, 'fixture', plan['expected_resolved_sha256'],
                             plan['expected_registration_sha256'])

    def test_semantic_override_sync_and_removal_keep_candidates_immutable(self):
        candidate = deepcopy(self.original['candidate'])
        layer_id = next(r['layer_id'] for r in self.original['draft']['records'] if r['action'] == 'bind')
        self.author(layer_overrides={layer_id: {'canonical_role': 'wear.sleeve'}})
        self.assertEqual(preview_rebase(self.store, 'fixture')['status'], 'ready')
        result = self.synchronize()
        self.assertTrue(result['binding_review_required'])
        registration = inputs._registrations(self.store, 'fixture')[-1][1]
        self.assertEqual(registration['authoring_rebase']['semantic_roles'], {layer_id: 'wear.sleeve'})
        after = inspect_registration(self.store, 'fixture')['draft']['records']
        self.assertEqual(next(r for r in after if r['layer_id'] == layer_id)['action'], 'pending')
        self.assertEqual(inspect_registration(self.store, 'fixture')['candidate'], candidate)
        self.author(layer_overrides={})
        self.synchronize()
        self.assertEqual(inputs._registrations(self.store, 'fixture')[-1][1]['authoring_rebase']['semantic_roles'], {})

    def test_rebase_preserves_completion_profile(self):
        from autospine_workbench.automation.animated_binding_completion import complete_bindings
        key = self.original['source_addresses']['input_identity_sha256']
        complete_bindings(self.store, 'fixture', 'a' * 64, key)
        self.author(notes='Updated author notes')
        self.synchronize()
        with inputs.load_inputs(self.store, 'fixture') as source:
            self.assertEqual(source.bindings['profile'], 'rigid-detail-completion-v4')

    def test_imports_only_authored_canonical_joint_and_keeps_eye_overrides(self):
        before = get_joint_review(self.store, 'fixture')
        elbow = next(r for r in before['records'] if r['joint_id'] == 'elbow.left')['position']
        self.author(joint_overrides={'elbow.left': {'x': elbow[0] + 1, 'y': elbow[1]},
                                     'eye.left': {'x': 1, 'y': 2}})
        unchanged = deepcopy(self.overrides)
        plan = preview_rebase(self.store, 'fixture')
        self.assertEqual(plan['changed_joint_ids'], ['elbow.left'])
        self.assertEqual(plan['ignored_joint_ids'], ['eye.left'])
        result = self.synchronize(plan)
        self.assertTrue(result['binding_review_required'])
        self.assertEqual(self.overrides, unchanged)
        self.assertEqual(inputs._registrations(self.store, 'fixture')[-1][1]['schema'],
                         'autospine.animated-input-registration/v2')
        after = get_joint_review(self.store, 'fixture')
        for old, new in zip(before['records'], after['records']):
            if old['joint_id'] != 'elbow.left':
                self.assertEqual(old, new)
        with inputs.load_inputs(self.store, 'fixture') as source:
            self.assertEqual(source.assisted['source_pose_sha256'], self.fixture.original_assisted['source_pose_sha256'])
            self.assertTrue(all(row['action'] != 'bind' for row in source.draft['records']))

    def test_noop_authoring_revision_preserves_geometry_but_invalidates_old_download(self):
        self.author(notes='Saved authoring note only')
        plan = preview_rebase(self.store, 'fixture')
        self.assertEqual(plan['changed_joint_ids'], [])
        with self.assertRaisesRegex(inputs.AnimatedSourceError, 'animated_source_stale'):
            assert_registered_current(self.store, 'fixture', self.original['source_addresses'])
        result = self.synchronize(plan)
        self.assertFalse(result['binding_review_required'])
        current = inspect_registration(self.store, 'fixture')
        self.assertEqual(current['draft'], self.original['draft'])
        self.assertNotEqual(current['source_addresses'], self.original['source_addresses'])
        self.assertFalse(self.synchronize()['changed'])

    def test_unsupported_real_layer_change_split_and_texture_are_explicitly_blocked(self):
        for edits, reason in [({'layer_overrides': {'layer-000': {'visible': False}}}, 'animated_rebase_layer_override_unsupported'),
                              ({'split_decisions': {'layer-000': {}}}, 'animated_rebase_split_unsupported'),
                              ({'joint_decisions': {'elbow.left': {}}}, 'animated_rebase_joint_decision_unsupported')]:
            self.overrides.update(layer_overrides={}, split_decisions={}, joint_decisions={})
            self.author(**edits)
            plan = preview_rebase(self.store, 'fixture')
            self.assertEqual(plan['status'], 'blocked')
            self.assertEqual(plan['unsupported_items'][0]['reason_code'], reason)
            with self.assertRaisesRegex(inputs.AnimatedSourceError, reason):
                self.synchronize(plan)
        self.overrides.update(layer_overrides={}, split_decisions={}, joint_decisions={})
        with patch('autospine_workbench.automation.animated_rebase._match_audit',
                   side_effect=ValueError('changed texture')):
            self.assertEqual(preview_rebase(self.store, 'fixture')['unsupported_items'][0]['reason_code'],
                             'animated_rebase_audit_or_texture_changed')
        self.assertEqual(len(inputs._registrations(self.store, 'fixture')), 1)

    def test_stale_plan_conflicts_and_old_overrides_never_replace_newer_animation_edits(self):
        review = get_joint_review(self.store, 'fixture')
        point = next(r for r in review['records'] if r['joint_id'] == 'elbow.left')['position']
        self.author(joint_overrides={'elbow.left': {'x': point[0] + 1, 'y': point[1]}})
        old_plan = preview_rebase(self.store, 'fixture')
        self.author(notes='Second authoring revision')
        with self.assertRaisesRegex(inputs.AnimatedSourceError, 'animated_review_conflict'):
            self.synchronize(old_plan)
        self.synchronize()
        review = get_joint_review(self.store, 'fixture')
        moved = next(r for r in review['records'] if r['joint_id'] == 'elbow.left')
        moved['position'][0] += 1
        save_joint_review(self.store, 'fixture', review['input_identity_sha256'],
                          review['records'], review['reviewed_joint_ids'])
        self.author(notes='No additional joint correction')
        self.assertEqual(preview_rebase(self.store, 'fixture')['changed_joint_ids'], [])
        self.synchronize()
        current = get_joint_review(self.store, 'fixture')
        self.assertEqual(next(r for r in current['records'] if r['joint_id'] == 'elbow.left')['position'], moved['position'])
        self.author(joint_overrides={})
        plan = preview_rebase(self.store, 'fixture')
        self.assertEqual(plan['status'], 'blocked')
        self.assertEqual(plan['unsupported_items'][0]['reason_code'], 'animated_rebase_joint_override_removed')


if __name__ == '__main__':
    unittest.main()
