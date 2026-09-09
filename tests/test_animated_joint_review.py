"""Joint review uses real source contracts and never grants implicit approvals."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import test_region_binding_cli as fixtures
from autospine_workbench.asset.joints.layer_binding import build_layer_bindings
from autospine_workbench.benchmark.artifacts import publish_report, read_report
from autospine_workbench.benchmark.assisted_joint_cli import read_assisted_joint_draft
from autospine_workbench.benchmark.layer_binding_draft import build_layer_binding_draft
from autospine_workbench.benchmark.region_binding_cli import sources
from autospine_workbench.automation import animated_inputs as inputs
from autospine_workbench.automation.animated_input_index import inspect_registration
from autospine_workbench.automation.animated_joint_review import get_joint_review, save_joint_review
from autospine_workbench.resolved_project import canonical_sha256


class AnimatedJointReviewTests(unittest.TestCase):
    def setUp(self):
        f = fixtures.RegionBindingCliTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        f.build()
        self.f = f.f
        self.store = SimpleNamespace(state_root=self.f.state, workspace_root=self.f.root)
        skeleton = json.loads((self.f.root / 'skeleton.json').read_bytes())
        candidate, assisted, skeleton, _, _ = sources(self.f.state, self.f.manifest,
                                                     canonical_sha256(skeleton), self.f.root)
        self.original_assisted = assisted
        self.bindings = build_layer_bindings(candidate, assisted, skeleton)
        self.draft = build_layer_binding_draft(self.bindings)
        for row, binding in zip(self.draft['records'], self.bindings['bindings']):
            if binding['options']:
                row.update(action='bind', option_id=binding['options'][0]['id'])
                break
        self.assertTrue(any(row['action'] == 'bind' for row in self.draft['records']))
        for kind, doc in [('layer-binding-candidates-v2', self.bindings),
                          ('layer-binding-drafts-v2', self.draft)]:
            publish_report(self.f.state, self.f.manifest['dataset_id'], kind, doc)
        checkpoint = {'resolved_project_sha256': 'a' * 64, 'input_identity_sha256': 'b' * 64}
        for name, function in [('_checkpoint', lambda *_: ({'overrides': {'revision': 0}}, checkpoint)),
                               ('_match_audit', lambda *_: None)]:
            patcher = patch.object(inputs, name, function)
            patcher.start()
            self.addCleanup(patcher.stop)
        inputs.register_inputs(self.store, 'fixture', self.f.manifest, canonical_sha256(self.draft))

    def review(self):
        return get_joint_review(self.store, 'fixture')

    def save(self, review):
        return save_joint_review(self.store, 'fixture', review['input_identity_sha256'],
                                 review['records'], review['reviewed_joint_ids'])

    def test_all_points_visible_and_exact_noop_does_not_add_history(self):
        review = self.review()
        self.assertEqual(review['records'], self.original_assisted['draft']['records'])
        self.assertEqual(len(review['records']), 17)
        self.assertEqual(review['annotation_mode'], 'model_assisted')
        self.assertFalse(review['independent_annotation'])
        self.assertFalse(self.save(review)['changed'])
        self.assertEqual(len(inputs._registrations(self.store, 'fixture')), 1)

    def test_geometry_edit_resets_bound_layers_and_preserves_raw_pose(self):
        review = self.review()
        next(row for row in review['records'] if row['joint_id'] == 'elbow.left')['position'][0] += 1
        result = self.save(review)
        self.assertTrue(result['changed'])
        self.assertTrue(result['binding_review_required'])
        self.assertTrue(result['migration_suggestions'])
        current = inspect_registration(self.store, 'fixture')
        self.assertTrue(all(row['action'] != 'bind' for row in current['draft']['records']))
        with inputs.load_inputs(self.store, 'fixture') as source:
            self.assertEqual(source.assisted['source_pose_sha256'], self.original_assisted['source_pose_sha256'])
            self.assertEqual(source.assisted['source_baseline_sha256'], self.original_assisted['source_baseline_sha256'])
            exact = read_assisted_joint_draft(self.f.state, self.f.manifest, canonical_sha256(source.assisted),
                                             workspace=self.f.root)
            self.assertEqual(exact['draft']['records'], review['records'])
            self.assertFalse(exact['independent_annotation'])
        with self.assertRaisesRegex(inputs.AnimatedSourceError, 'animated_review_conflict'):
            self.save(review)

    def test_explicit_incomplete_review_saves_blocked_without_filling_reviews(self):
        review = self.review()
        review['reviewed_joint_ids'] = ['root']
        result = self.save(review)
        self.assertEqual(result['skeleton_status'], 'blocked')
        self.assertIn('all_joint_reviews_required', result['reason_codes'])
        self.assertEqual(self.review()['reviewed_joint_ids'], ['root'])
        with inputs.load_inputs(self.store, 'fixture') as source:
            self.assertEqual(source.skeleton['bones'], [])
            self.assertTrue(all(row['action'] != 'bind' for row in source.draft['records']))

    def test_notes_only_edit_preserves_existing_geometry_binding_selections(self):
        review = self.review()
        review['records'][0]['notes'] += ' Checked again'
        result = self.save(review)
        self.assertFalse(result['binding_review_required'])
        self.assertEqual(inspect_registration(self.store, 'fixture')['draft']['records'], self.draft['records'])

    def test_invalid_joint_input_does_not_advance_registration(self):
        review = self.review()
        for change in ('nonfinite', 'unknown_review', 'missing_record'):
            bad = deepcopy(review)
            if change == 'nonfinite':
                bad['records'][0]['position'][0] = float('nan')
            elif change == 'unknown_review':
                bad['reviewed_joint_ids'].append('invented')
            else:
                bad['records'].pop()
            with self.assertRaisesRegex(inputs.AnimatedSourceError, 'animated_joint_review_invalid'):
                self.save(bad)
        self.assertEqual(len(inputs._registrations(self.store, 'fixture')), 1)


if __name__ == '__main__':
    unittest.main()
